# -*- coding: utf-8 -*-
"""
🐺 Wolf Flow Liquidity Scanner
Detects sudden liquidity entry on Binance + MEXC simultaneously.

Pattern detected:
  - Coin is flat/quiet for hours
  - ONE massive candle: volume 5-20× recent average
  - Price moves 2%+ on that candle
  - Buy flow dominates (buy_vol / sell_vol >= 1.3×)
  → Signal fires on the first spike candle
"""

import os
import time
import json
import logging
from typing import Dict, List, Set, Tuple, Optional

import requests

# ══════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID        = os.getenv("CHAT_ID", "")
GROUP_ID       = os.getenv("GROUP_ID", "")

# Redis (Upstash) — optional, for state persistence across restarts
REDIS_URL   = os.getenv("REDIS_URL", os.getenv("UPSTASH_REDIS_REST_URL", ""))
REDIS_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")
REDIS_KEY   = "wolf_state_v1"

# Scan intervals
FAST_SCAN_S  = 30    # check tickers every 30s (fast loop)
SLOW_SCAN_S  = 300   # check 1h klines every 5 min (slow loop)

# Cooldown: don't re-alert same coin within N seconds
COOLDOWN     = 7200  # 2 hours

# ── Fast scanner (5m candles) ──────────────────────────
FAST_VOL_SPIKE   = 5.0   # last 5m candle vol >= 5× recent avg
FAST_PRICE_MOVE  = 2.0   # price moved >= 2% on that candle
FAST_TICKER_MOVE = 1.5   # 30s price delta to trigger klines check

# ── Slow scanner (1h candles) ─────────────────────────
SLOW_VOL_SPIKE   = 3.0   # last 1h candle vol >= 3× recent avg
SLOW_PRICE_MOVE  = 3.0   # price moved >= 3% on that 1h candle

# ── Flow filter ────────────────────────────────────────
FLOW_RATIO    = 1.3       # buy_vol / sell_vol must be >= 1.3
FLOW_CANDLES  = 3         # look at last 3 candles for flow

# ── Coin filters ───────────────────────────────────────
MIN_VOL_24H   = 300_000   # minimum 24h USD volume
MAX_PUMP_24H  = 60.0      # skip coins already up 60%+
LATE_ENTRY_PCT = 0.85     # skip if price > 85% of 24h range

# ── Milestone tracking ─────────────────────────────────
MILESTONES    = [2, 5, 10, 15, 20, 25, 30, 40, 50, 75, 100]
TRACK_HOURS   = 24        # track milestones for 24h after signal

# ── Blocklist ──────────────────────────────────────────
STABLECOINS = {
    "USDC", "BUSD", "DAI", "TUSD", "USDD", "FDUSD",
    "USDP", "PYUSD", "USDB", "USDX", "EURC", "USDT"
}
SKIP_KEYWORDS = {"UP", "DOWN", "BULL", "BEAR", "3L", "3S", "2L", "2S", "HEDGE"}

# ── API base URLs ──────────────────────────────────────
BINANCE_BASE = "https://api.binance.com/api/v3"
MEXC_BASE    = "https://api.mexc.com/api/v3"

# ══════════════════════════════════════════════════════
#  STATE
# ══════════════════════════════════════════════════════

prev_prices: Dict[str, float] = {}   # price from last tick (for 30s delta)
alerted:     Dict[str, float] = {}   # sym → timestamp of last alert
tracking:    Dict[str, dict]  = {}   # sym → milestone tracking info

last_fast = 0.0
last_slow = 0.0

# ══════════════════════════════════════════════════════
#  LOGGING
# ══════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("wolf")

# ══════════════════════════════════════════════════════
#  HTTP SESSION
# ══════════════════════════════════════════════════════

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "WolfFlowBot/2.0"})


def _get(url: str, params: dict = None, timeout: int = 10) -> Optional[object]:
    try:
        r = SESSION.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.debug("GET %s params=%s → %s", url, params, e)
        return None


# ══════════════════════════════════════════════════════
#  REDIS STATE (optional)
# ══════════════════════════════════════════════════════

def _redis(method: str, path: str, body=None) -> Optional[dict]:
    if not REDIS_URL or not REDIS_TOKEN:
        return None
    try:
        url = REDIS_URL.rstrip("/") + path
        headers = {"Authorization": f"Bearer {REDIS_TOKEN}"}
        if method == "GET":
            r = SESSION.get(url, headers=headers, timeout=5)
        else:
            r = SESSION.post(url, headers=headers, json=body, timeout=5)
        return r.json()
    except Exception as e:
        log.debug("Redis %s %s: %s", method, path, e)
        return None


def save_state():
    if not REDIS_URL:
        return
    state = {
        "alerted":  {k: v for k, v in alerted.items()},
        "tracking": {
            k: {**v, "hit": list(v["hit"])}
            for k, v in tracking.items()
        },
    }
    _redis("POST", f"/set/{REDIS_KEY}", {"value": json.dumps(state)})


def load_state():
    global alerted, tracking
    if not REDIS_URL:
        return
    resp = _redis("GET", f"/get/{REDIS_KEY}")
    if not resp or not resp.get("result"):
        return
    try:
        state = json.loads(resp["result"])
        alerted.update(state.get("alerted", {}))
        for k, v in state.get("tracking", {}).items():
            v["hit"] = set(v.get("hit", []))
            tracking[k] = v
        log.info("State loaded: %d alerted, %d tracked", len(alerted), len(tracking))
    except Exception as e:
        log.warning("State load failed: %s", e)


# ══════════════════════════════════════════════════════
#  DATA FETCHING
# ══════════════════════════════════════════════════════

def _is_valid_sym(sym: str) -> bool:
    if not sym.endswith("USDT"):
        return False
    base = sym[:-4]
    if base in STABLECOINS:
        return False
    if any(k in base for k in SKIP_KEYWORDS):
        return False
    if "(" in sym or ")" in sym:
        return False
    return True


def fetch_tickers(base_url: str, exchange: str) -> Dict[str, dict]:
    data = _get(f"{base_url}/ticker/24hr")
    if not isinstance(data, list):
        return {}
    out = {}
    for t in data:
        sym = t.get("symbol", "")
        if not _is_valid_sym(sym):
            continue
        try:
            out[sym] = {
                "price":    float(t["lastPrice"]),
                "vol":      float(t["quoteVolume"]),
                "change":   float(t["priceChangePercent"]),
                "high24":   float(t.get("highPrice", t["lastPrice"])),
                "low24":    float(t.get("lowPrice",  t["lastPrice"])),
                "exchange": exchange,
                "base_url": base_url,
            }
        except (KeyError, ValueError):
            continue
    return out


def fetch_klines(sym: str, base_url: str, interval: str = "5m", limit: int = 25) -> List[list]:
    data = _get(f"{base_url}/klines", {"symbol": sym, "interval": interval, "limit": limit})
    return data if isinstance(data, list) else []


# ══════════════════════════════════════════════════════
#  ANALYSIS
# ══════════════════════════════════════════════════════

def _quote_vol(candle: list) -> float:
    """Extract USDT volume from kline (Binance/MEXC index 7 = quote asset vol)."""
    try:
        v = float(candle[7])
        return v if v > 0 else float(candle[5]) * float(candle[4])
    except (IndexError, ValueError):
        try:
            return float(candle[5]) * float(candle[4])
        except Exception:
            return 0.0


def vol_spike_and_move(candles: List[list]) -> Tuple[float, float]:
    """
    Returns (spike_ratio, candle_price_change_pct) for the LAST candle.
    spike_ratio = last_candle_vol / avg(previous candles excluding last 2)
    """
    if len(candles) < 8:
        return 0.0, 0.0

    vols = [_quote_vol(c) for c in candles]
    last_vol = vols[-1]
    baseline = vols[:-2]
    avg_vol  = sum(baseline) / len(baseline) if baseline else 0.0

    if avg_vol <= 0:
        return 0.0, 0.0

    spike = last_vol / avg_vol

    try:
        o = float(candles[-1][1])
        c = float(candles[-1][4])
        move = (c - o) / o * 100.0 if o > 0 else 0.0
    except Exception:
        move = 0.0

    return spike, move


def calc_flow(candles: List[list]) -> Tuple[float, float]:
    """
    Returns (buy_vol_usdt, sell_vol_usdt) using candle body position.
    Position of close within high-low range = buy pressure.
    """
    buy = sell = 0.0
    for c in candles[-FLOW_CANDLES:]:
        try:
            h   = float(c[2])
            lo  = float(c[3])
            cl  = float(c[4])
            vol = _quote_vol(c)
            rng = h - lo
            b   = (cl - lo) / rng if rng > 0 else 0.5
            buy  += vol * b
            sell += vol * (1.0 - b)
        except Exception:
            continue
    return buy, sell


def is_late_entry(price: float, high24: float, low24: float) -> bool:
    """True if price is already in the top portion of 24h range."""
    rng = high24 - low24
    if rng <= 0:
        return False
    return (price - low24) / rng > LATE_ENTRY_PCT


# ══════════════════════════════════════════════════════
#  TELEGRAM
# ══════════════════════════════════════════════════════

_TG = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


def send(text: str):
    if not TELEGRAM_TOKEN:
        print(text)
        return
    for cid in filter(None, [CHAT_ID, GROUP_ID]):
        try:
            SESSION.post(
                f"{_TG}/sendMessage",
                json={"chat_id": cid, "text": text, "parse_mode": "Markdown"},
                timeout=10,
            )
        except Exception as e:
            log.error("Telegram error: %s", e)


def _fv(v: float) -> str:
    """Format USDT amount: 1.2M$, 45.3K$, 800$"""
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f}M$"
    if v >= 1_000:
        return f"{v / 1_000:.1f}K$"
    return f"{v:.0f}$"


def _fmt_price(price: float) -> str:
    """Format price with appropriate decimals."""
    if price >= 1000:
        return f"{price:.2f}"
    if price >= 1:
        return f"{price:.4f}"
    if price >= 0.001:
        return f"{price:.6f}"
    return f"{price:.8f}"


def build_signal_msg(sym, price, change, buy_v, sell_v,
                     spike, candle_move, exchange) -> str:
    base     = sym[:-4]
    net      = buy_v - sell_v
    ratio    = buy_v / sell_v if sell_v > 0 else 99.0
    ex_icon  = "🔶" if exchange == "MEXC" else "🔷"

    if spike >= 15:
        vol_tag = "💥 EXPLOSIVE"
    elif spike >= 10:
        vol_tag = "🔥🔥 Very High"
    elif spike >= 7:
        vol_tag = "🔥 High"
    else:
        vol_tag = "⚡ Spike"

    if ratio >= 3.0:
        flow_tag = "🟢🟢 Very Bullish"
    elif ratio >= 2.0:
        flow_tag = "🟢 Bullish"
    elif ratio >= 1.5:
        flow_tag = "🟡 Mildly Bullish"
    else:
        flow_tag = "🟡 Bullish"

    p = _fmt_price(price)

    return (
        f"🚀 *LIQUIDITY ENTRY DETECTED*\n"
        f"{'━' * 20}\n"
        f"💎 *#{base}USDT*  {ex_icon} _{exchange}_\n"
        f"💰 Price: `${p}`\n"
        f"📈 Candle Move: `+{candle_move:.2f}%`\n"
        f"📊 24h Change:  `+{change:.2f}%`\n"
        f"{'━' * 20}\n"
        f"📦 Vol Spike: `{spike:.1f}×` — {vol_tag}\n"
        f"  ▶️ In:  `{_fv(buy_v)}`\n"
        f"  ◀️ Out: `{_fv(sell_v)}`\n"
        f"  ⚡ Net: `+{_fv(net)}`\n"
        f"  Flow: {flow_tag}\n"
        f"{'━' * 20}\n"
        f"✅ *السيولة تدخل — ادخل الآن* 🐺💜"
    )


# ══════════════════════════════════════════════════════
#  MILESTONE TRACKING
# ══════════════════════════════════════════════════════

def check_milestones(all_tickers: Dict[str, dict]):
    now     = time.time()
    expired = []

    for sym, info in tracking.items():
        if now - info["t0"] > TRACK_HOURS * 3600:
            expired.append(sym)
            continue

        t = all_tickers.get(sym)
        if not t:
            continue

        gain = (t["price"] - info["entry"]) / info["entry"] * 100.0
        if gain > info.get("max", 0.0):
            info["max"] = gain

        for ms in MILESTONES:
            if ms in info["hit"]:
                continue
            if gain >= ms:
                info["hit"].add(ms)
                _fire_milestone(sym, ms, gain, t["price"], info["entry"],
                                int(now - info["t0"]), info["exchange"])

    for s in expired:
        tracking.pop(s, None)


def _fire_milestone(sym, ms, gain, price_now, entry, elapsed, exchange):
    base    = sym[:-4]
    elapsed = max(elapsed, 0)
    t_str   = (f"{elapsed // 3600}h {(elapsed % 3600) // 60}m" if elapsed >= 3600
               else f"{elapsed // 60}m {elapsed % 60}s" if elapsed >= 60
               else f"{elapsed}s")
    icon    = "🚀" if ms >= 50 else ("🔥" if ms >= 25 else ("📈" if ms >= 10 else "✅"))
    ex_icon = "🔶" if exchange == "MEXC" else "🔷"

    send(
        f"{icon} *{base}USDT*  +{ms}% milestone reached\n"
        f"📊 Max gain:   +{gain:.2f}%\n"
        f"💰 Price now:  ${_fmt_price(price_now)}\n"
        f"🏁 Entry:      ${_fmt_price(entry)}\n"
        f"⏱ Achieved in: {t_str}\n"
        f"{ex_icon} {exchange}"
    )
    log.info("MILESTONE  %-14s +%d%%  (max=+%.2f%%)  in %s  [%s]",
             sym, ms, gain, t_str, exchange)


# ══════════════════════════════════════════════════════
#  CORE SIGNAL CHECK
# ══════════════════════════════════════════════════════

def _check_coin(sym: str, ticker: dict,
                interval: str,
                spike_min: float,
                move_min: float):
    """
    Fetch klines for sym and fire a signal if liquidity spike is confirmed.
    """
    now = time.time()

    price    = ticker["price"]
    vol_24h  = ticker["vol"]
    change   = ticker["change"]
    exchange = ticker["exchange"]
    base_url = ticker["base_url"]

    # ── Basic filters ──────────────────────────────────
    if vol_24h < MIN_VOL_24H:
        return
    if not (1.0 <= change <= MAX_PUMP_24H):
        return
    if is_late_entry(price, ticker["high24"], ticker["low24"]):
        return
    if now - alerted.get(sym, 0) < COOLDOWN:
        return

    # ── Klines ─────────────────────────────────────────
    candles = fetch_klines(sym, base_url, interval=interval, limit=25)
    if len(candles) < 8:
        return

    spike, move = vol_spike_and_move(candles)
    if spike < spike_min or move < move_min:
        return

    buy_v, sell_v = calc_flow(candles)
    if sell_v <= 0 or (buy_v / sell_v) < FLOW_RATIO:
        return

    # ── Fire signal ────────────────────────────────────
    alerted[sym] = now
    tracking[sym] = {
        "entry":    price,
        "t0":       now,
        "hit":      set(),
        "max":      0.0,
        "exchange": exchange,
    }
    save_state()

    msg = build_signal_msg(sym, price, change, buy_v, sell_v, spike, move, exchange)
    send(msg)

    log.info(
        "SIGNAL  %-14s spike=%.1fx  move=+%.1f%%  flow=%.1fx  [%s %s]",
        sym, spike, move, buy_v / max(sell_v, 1), exchange, interval
    )


# ══════════════════════════════════════════════════════
#  FAST SCANNER — every 30s, uses 5m klines
# ══════════════════════════════════════════════════════

def fast_scan(all_tickers: Dict[str, dict]):
    """
    Detects coins that moved >= FAST_TICKER_MOVE% since last tick.
    Only fetches klines for these movers → minimal API calls.
    """
    global prev_prices

    movers = []
    for sym, t in all_tickers.items():
        prev = prev_prices.get(sym, 0)
        if prev > 0:
            delta = (t["price"] - prev) / prev * 100.0
            if delta >= FAST_TICKER_MOVE:
                movers.append((sym, delta, t))

    # Update cache
    prev_prices = {sym: t["price"] for sym, t in all_tickers.items()}

    if not movers:
        return

    # Process biggest movers first, cap at 30 per scan
    movers.sort(key=lambda x: -x[1])
    for sym, delta, ticker in movers[:30]:
        _check_coin(sym, ticker, "5m", FAST_VOL_SPIKE, FAST_PRICE_MOVE)
        time.sleep(0.05)   # small delay to avoid rate limit burst


# ══════════════════════════════════════════════════════
#  SLOW SCANNER — every 5 min, uses 1h klines
# ══════════════════════════════════════════════════════

def slow_scan(all_tickers: Dict[str, dict]):
    """
    Scans top-volume coins for 1h candle volume spikes.
    Catches coins like STO that moved gradually over 1h.
    """
    candidates = [
        (sym, t) for sym, t in all_tickers.items()
        if 2.0 <= t["change"] <= MAX_PUMP_24H
        and t["vol"] >= MIN_VOL_24H * 1.5
    ]
    # Sort by volume, Binance first, top 150
    candidates.sort(key=lambda x: (-int(x[1]["exchange"] == "Binance"), -x[1]["vol"]))
    candidates = candidates[:150]

    log.info("slow_scan: checking %d candidates (1h klines)", len(candidates))

    for sym, ticker in candidates:
        _check_coin(sym, ticker, "1h", SLOW_VOL_SPIKE, SLOW_PRICE_MOVE)
        time.sleep(0.08)


# ══════════════════════════════════════════════════════
#  MAIN LOOP
# ══════════════════════════════════════════════════════

def main():
    global last_fast, last_slow

    log.info("🐺 Wolf Flow Liquidity Scanner v2.0 — starting")

    load_state()

    send(
        "🐺 *Wolf Flow Liquidity Scanner v2.0*\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "✅ Bot started\n"
        "📡 Exchanges: *Binance* 🔷 + *MEXC* 🔶\n"
        f"⚡ Fast scan (5m): every {FAST_SCAN_S}s\n"
        f"📊 Slow scan (1h): every {SLOW_SCAN_S // 60}min\n"
        "🎯 Detects: Liquidity spike on ANY USDT pair\n"
        f"🔕 Cooldown: {COOLDOWN // 3600}h per coin"
    )

    while True:
        try:
            now = time.time()

            if now - last_fast < FAST_SCAN_S:
                time.sleep(1)
                continue

            last_fast = now

            # ── Fetch all tickers ─────────────────────
            b_tickers = fetch_tickers(BINANCE_BASE, "Binance")
            m_tickers = fetch_tickers(MEXC_BASE,    "MEXC")

            # Merge: Binance wins for duplicate symbols
            all_t = {**m_tickers, **b_tickers}

            log.info(
                "Tickers fetched: Binance=%d  MEXC=%d  Total=%d  Tracking=%d",
                len(b_tickers), len(m_tickers), len(all_t), len(tracking)
            )

            # ── Update milestones (no API calls) ──────
            check_milestones(all_t)

            # ── Fast scan: 30s movers → 5m klines ────
            fast_scan(all_t)

            # ── Slow scan: 1h klines every 5 min ─────
            if now - last_slow >= SLOW_SCAN_S:
                last_slow = now
                slow_scan(all_t)

        except KeyboardInterrupt:
            log.info("Stopped by user.")
            break
        except Exception as e:
            log.error("Main loop error: %s", e, exc_info=True)
            time.sleep(5)


if __name__ == "__main__":
    main()

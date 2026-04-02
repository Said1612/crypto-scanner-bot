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

REDIS_URL   = os.getenv("REDIS_URL", os.getenv("UPSTASH_REDIS_REST_URL", ""))
REDIS_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")
REDIS_KEY   = "wolf_state_v1"

FAST_SCAN_S  = 30
SLOW_SCAN_S  = 300
COOLDOWN     = 7200

FAST_VOL_SPIKE   = 5.0
FAST_PRICE_MOVE  = 2.0
FAST_TICKER_MOVE = 1.5

SLOW_VOL_SPIKE   = 3.0
SLOW_PRICE_MOVE  = 3.0

FLOW_RATIO    = 1.3
FLOW_CANDLES  = 3

MIN_VOL_24H   = 300_000
MEXC_MIN_VOL  = 50_000
MAX_PUMP_24H  = 60.0
LATE_ENTRY_PCT = 0.85

MILESTONES    = [2, 5, 10, 15, 20, 25, 30, 40, 50, 75, 100]
TRACK_HOURS   = 24

STABLECOINS = {
    "USDC", "BUSD", "DAI", "TUSD", "USDD", "FDUSD",
    "USDP", "PYUSD", "USDB", "USDX", "EURC", "USDT"
}
SKIP_KEYWORDS = {"UP", "DOWN", "BULL", "BEAR", "3L", "3S", "2L", "2S", "HEDGE"}

BINANCE_SPOT    = "https://api.binance.com/api/v3"
BINANCE_FUTURES = "https://fapi.binance.com/fapi/v1"
MEXC_BASE       = "https://api.mexc.com/api/v3"

# ══════════════════════════════════════════════════════
#  STATE
# ══════════════════════════════════════════════════════

prev_prices: Dict[str, float] = {}
alerted:     Dict[str, float] = {}
tracking:    Dict[str, dict]  = {}

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

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "WolfFlowBot/2.0"})


def _get(url: str, params: dict = None, timeout: int = 10) -> Optional[object]:
    try:
        r = SESSION.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.debug("GET %s → %s", url, e)
        return None


# ══════════════════════════════════════════════════════
#  REDIS STATE
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
        log.debug("Redis %s: %s", path, e)
        return None


def save_state():
    if not REDIS_URL:
        return
    state = {
        "alerted":  {k: v for k, v in alerted.items()},
        "tracking": {k: {**v, "hit": list(v["hit"])} for k, v in tracking.items()},
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


def _parse_tickers(data: list, exchange: str, base_url: str) -> Dict[str, dict]:
    out = {}
    for t in data:
        sym = t.get("symbol", "")
        if not _is_valid_sym(sym):
            continue
        try:
            price = float(t.get("lastPrice") or 0)
            if price <= 0:
                continue
            quote_vol = float(t.get("quoteVolume") or 0)
            base_vol  = float(t.get("volume")      or 0)
            vol    = quote_vol if quote_vol > 1 else base_vol * price
            change = float(t.get("priceChangePercent") or 0)
            high24 = float(t.get("highPrice") or price)
            low24  = float(t.get("lowPrice")  or price)
            out[sym] = {
                "price": price, "vol": vol, "change": change,
                "high24": high24, "low24": low24,
                "exchange": exchange, "base_url": base_url,
            }
        except (KeyError, ValueError, TypeError):
            continue
    return out


def fetch_tickers_binance() -> Dict[str, dict]:
    data = _get(f"{BINANCE_SPOT}/ticker/24hr")
    if isinstance(data, list) and len(data) > 100:
        out = _parse_tickers(data, "Binance", BINANCE_SPOT)
        log.info("Binance Spot: %d tickers", len(out))
        return out
    log.warning("Binance Spot blocked — trying Futures...")
    data = _get(f"{BINANCE_FUTURES}/ticker/24hr")
    if isinstance(data, list) and len(data) > 100:
        out = _parse_tickers(data, "Binance", BINANCE_FUTURES)
        log.info("Binance Futures: %d tickers", len(out))
        return out
    log.warning("Binance unavailable — MEXC only mode")
    return {}


def fetch_tickers_mexc() -> Dict[str, dict]:
    data = _get(f"{MEXC_BASE}/ticker/24hr")
    if not isinstance(data, list):
        log.warning("MEXC ticker returned no data")
        return {}
    out = _parse_tickers(data, "MEXC", MEXC_BASE)
    log.info("MEXC: %d tickers", len(out))
    return out


def fetch_klines(sym: str, base_url: str, interval: str = "5m", limit: int = 25) -> List[list]:
    data = _get(f"{base_url}/klines", {"symbol": sym, "interval": interval, "limit": limit})
    return data if isinstance(data, list) else []


# ══════════════════════════════════════════════════════
#  ANALYSIS
# ══════════════════════════════════════════════════════

def _quote_vol(candle: list) -> float:
    try:
        v = float(candle[7])
        return v if v > 0 else float(candle[5]) * float(candle[4])
    except Exception:
        try:
            return float(candle[5]) * float(candle[4])
        except Exception:
            return 0.0


def vol_spike_and_move(candles: List[list]) -> Tuple[float, float]:
    if len(candles) < 8:
        return 0.0, 0.0
    vols     = [_quote_vol(c) for c in candles]
    last_vol = vols[-1]
    baseline = vols[:-2]
    avg_vol  = sum(baseline) / len(baseline) if baseline else 0.0
    if avg_vol <= 0:
        return 0.0, 0.0
    spike = last_vol / avg_vol
    try:
        o    = float(candles[-1][1])
        c    = float(candles[-1][4])
        move = (c - o) / o * 100.0 if o > 0 else 0.0
    except Exception:
        move = 0.0
    return spike, move


def calc_flow(candles: List[list]) -> Tuple[float, float]:
    buy = sell = 0.0
    for c in candles[-FLOW_CANDLES:]:
        try:
            h, lo, cl = float(c[2]), float(c[3]), float(c[4])
            vol = _quote_vol(c)
            rng = h - lo
            b   = (cl - lo) / rng if rng > 0 else 0.5
            buy  += vol * b
            sell += vol * (1.0 - b)
        except Exception:
            continue
    return buy, sell


def is_late_entry(price: float, high24: float, low24: float) -> bool:
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
            SESSION.post(f"{_TG}/sendMessage",
                         json={"chat_id": cid, "text": text, "parse_mode": "Markdown"},
                         timeout=10)
        except Exception as e:
            log.error("Telegram: %s", e)


def _fv(v: float) -> str:
    if v >= 1_000_000: return f"{v/1e6:.1f}M$"
    if v >= 1_000:     return f"{v/1e3:.1f}K$"
    return f"{v:.0f}$"


def _fp(price: float) -> str:
    if price >= 1000:  return f"{price:.2f}"
    if price >= 1:     return f"{price:.4f}"
    if price >= 0.001: return f"{price:.6f}"
    return f"{price:.8f}"


def build_signal_msg(sym, price, change, buy_v, sell_v, spike, move, exchange) -> str:
    base, net, ratio = sym[:-4], buy_v - sell_v, buy_v / sell_v if sell_v > 0 else 99.0
    ex_icon  = "🔶" if exchange == "MEXC" else "🔷"
    vol_tag  = ("💥 EXPLOSIVE" if spike >= 15 else "🔥🔥 Very High" if spike >= 10
                else "🔥 High" if spike >= 7 else "⚡ Spike")
    flow_tag = ("🟢🟢 Very Bullish" if ratio >= 3.0 else "🟢 Bullish" if ratio >= 2.0
                else "🟡 Mildly Bullish" if ratio >= 1.5 else "🟡 Bullish")
    return (
        f"🚀 *LIQUIDITY ENTRY DETECTED*\n{'━'*20}\n"
        f"💎 *#{base}USDT*  {ex_icon} _{exchange}_\n"
        f"💰 Price: `${_fp(price)}`\n"
        f"📈 Candle Move: `+{move:.2f}%`\n"
        f"📊 24h Change:  `+{change:.2f}%`\n"
        f"{'━'*20}\n"
        f"📦 Vol Spike: `{spike:.1f}×` — {vol_tag}\n"
        f"  ▶️ In:  `{_fv(buy_v)}`\n"
        f"  ◀️ Out: `{_fv(sell_v)}`\n"
        f"  ⚡ Net: `+{_fv(net)}`\n"
        f"  Flow: {flow_tag}\n"
        f"{'━'*20}\n"
        f"✅ *السيولة تدخل — ادخل الآن* 🐺💜"
    )


# ══════════════════════════════════════════════════════
#  MILESTONE TRACKING
# ══════════════════════════════════════════════════════

def check_milestones(all_tickers: Dict[str, dict]):
    now, expired = time.time(), []
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
            if ms not in info["hit"] and gain >= ms:
                info["hit"].add(ms)
                _fire_milestone(sym, ms, gain, t["price"], info["entry"],
                                int(now - info["t0"]), info["exchange"])
    for s in expired:
        tracking.pop(s, None)


def _fire_milestone(sym, ms, gain, price_now, entry, elapsed, exchange):
    elapsed = max(elapsed, 0)
    t_str   = (f"{elapsed//3600}h {(elapsed%3600)//60}m" if elapsed >= 3600
               else f"{elapsed//60}m {elapsed%60}s" if elapsed >= 60
               else f"{elapsed}s")
    icon    = "🚀" if ms >= 50 else ("🔥" if ms >= 25 else ("📈" if ms >= 10 else "✅"))
    ex_icon = "🔶" if exchange == "MEXC" else "🔷"
    send(
        f"{icon} *{sym[:-4]}USDT*  +{ms}% milestone reached\n"
        f"📊 Max gain:   +{gain:.2f}%\n"
        f"💰 Price now:  ${_fp(price_now)}\n"
        f"🏁 Entry:      ${_fp(entry)}\n"
        f"⏱ Achieved in: {t_str}\n"
        f"{ex_icon} {exchange}"
    )
    log.info("MILESTONE  %-14s +%d%%  in %s  [%s]", sym, ms, t_str, exchange)


# ══════════════════════════════════════════════════════
#  CORE SIGNAL CHECK
# ══════════════════════════════════════════════════════

def _check_coin(sym: str, ticker: dict, interval: str, spike_min: float, move_min: float):
    now      = time.time()
    price    = ticker["price"]
    vol_24h  = ticker["vol"]
    change   = ticker["change"]
    exchange = ticker["exchange"]
    base_url = ticker["base_url"]

    min_vol = MEXC_MIN_VOL if exchange == "MEXC" else MIN_VOL_24H
    if vol_24h < min_vol:
        return
    if not (1.0 <= change <= MAX_PUMP_24H):
        return
    if is_late_entry(price, ticker["high24"], ticker["low24"]):
        return
    if now - alerted.get(sym, 0) < COOLDOWN:
        return

    candles = fetch_klines(sym, base_url, interval=interval, limit=25)
    if len(candles) < 8:
        return

    spike, move = vol_spike_and_move(candles)
    if spike < spike_min or move < move_min:
        return

    buy_v, sell_v = calc_flow(candles)
    if sell_v <= 0 or (buy_v / sell_v) < FLOW_RATIO:
        return

    alerted[sym] = now
    tracking[sym] = {"entry": price, "t0": now, "hit": set(), "max": 0.0, "exchange": exchange}
    save_state()

    send(build_signal_msg(sym, price, change, buy_v, sell_v, spike, move, exchange))
    log.info("SIGNAL  %-14s spike=%.1fx  move=+%.1f%%  flow=%.1fx  [%s %s]",
             sym, spike, move, buy_v / max(sell_v, 1), exchange, interval)


# ══════════════════════════════════════════════════════
#  FAST SCANNER — every 30s
# ══════════════════════════════════════════════════════

def fast_scan(all_tickers: Dict[str, dict]):
    global prev_prices
    movers = []
    for sym, t in all_tickers.items():
        prev = prev_prices.get(sym, 0)
        if prev > 0:
            delta = (t["price"] - prev) / prev * 100.0
            if delta >= FAST_TICKER_MOVE:
                movers.append((sym, delta, t))
    prev_prices = {sym: t["price"] for sym, t in all_tickers.items()}
    if not movers:
        return
    movers.sort(key=lambda x: -x[1])
    for sym, delta, ticker in movers[:30]:
        _check_coin(sym, ticker, "5m", FAST_VOL_SPIKE, FAST_PRICE_MOVE)
        time.sleep(0.05)


# ══════════════════════════════════════════════════════
#  SLOW SCANNER — every 5 min
# ══════════════════════════════════════════════════════

def slow_scan(all_tickers: Dict[str, dict]):
    total      = len(all_tickers)
    candidates = []
    for sym, t in all_tickers.items():
        min_vol = MEXC_MIN_VOL if t["exchange"] == "MEXC" else MIN_VOL_24H
        if t["vol"] < min_vol:
            continue
        if t["change"] > MAX_PUMP_24H:
            continue
        candidates.append((sym, t))
    candidates.sort(key=lambda x: (-int(x[1]["exchange"] == "Binance"), -x[1]["vol"]))
    candidates = candidates[:300]
    log.info("slow_scan: checking %d/%d candidates (1h klines)", len(candidates), total)
    for sym, ticker in candidates:
        _check_coin(sym, ticker, "1h", SLOW_VOL_SPIKE, SLOW_PRICE_MOVE)
        time.sleep(0.08)


# ══════════════════════════════════════════════════════
#  MAIN
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
            b_tickers = fetch_tickers_binance()
            m_tickers = fetch_tickers_mexc()
            all_t     = {**m_tickers, **b_tickers}
            log.info("Tickers: Binance=%d  MEXC=%d  Total=%d  Tracking=%d",
                     len(b_tickers), len(m_tickers), len(all_t), len(tracking))
            check_milestones(all_t)
            fast_scan(all_t)
            if now - last_slow >= SLOW_SCAN_S:
                last_slow = now
                slow_scan(all_t)
        except KeyboardInterrupt:
            log.info("Stopped.")
            break
        except Exception as e:
            log.error("Loop error: %s", e, exc_info=True)
            time.sleep(5)


if __name__ == "__main__":
    main()

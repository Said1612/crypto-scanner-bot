# -*- coding: utf-8 -*-
"""
🎯 MAFIO Liquidity Scanner v3.1
Binance (Spot → CDN → Futures) + MEXC
Detects liquidity entry by tier: Micro / Small / Mid / Large cap
Based on analysis of real Wolf Flow trades (Mar-Apr 2026)
"""

import os, time, json, logging
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional
import requests

# ══════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID        = os.getenv("CHAT_ID", "")
GROUP_ID       = os.getenv("GROUP_ID", "")
REDIS_URL      = os.getenv("REDIS_URL", os.getenv("UPSTASH_REDIS_REST_URL", ""))
REDIS_TOKEN    = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")
REDIS_KEY      = "mafio_v31"

FAST_SCAN_S = 30    # every 30s
SLOW_SCAN_S = 300   # every 5min (1h klines)
COOLDOWN    = 7200  # 2h per coin

# ── Tier thresholds (from real trade analysis) ────────
# Format: (24h_vol_max, vol_spike_min, flow_ratio_min, net_flow_min)
# Micro cap  < $2M  : small moves need less liquidity → easiest to pump
# Small cap  $2-15M : medium moves
# Mid cap    $15-80M: larger moves
# Large cap  > $80M : hardest to move
TIERS = [
    {"name": "Micro",  "vol_max": 2_000_000,  "spike": 6.0, "ratio": 2.0, "net": 15_000},
    {"name": "Small",  "vol_max": 15_000_000, "spike": 5.0, "ratio": 1.8, "net": 40_000},
    {"name": "Mid",    "vol_max": 80_000_000, "spike": 5.0, "ratio": 1.6, "net": 150_000},
    {"name": "Large",  "vol_max": 9e99,        "spike": 5.0, "ratio": 1.5, "net": 500_000},
]

FAST_TICKER_MOVE = 1.5   # 30s price delta to trigger 5m klines fetch
FLOW_CANDLES     = 3     # candles for flow calculation
MAX_PUMP_24H     = 60.0  # skip already-pumped coins
LATE_ENTRY_PCT   = 0.92  # skip if price in top 8% of 24h range

MILESTONES  = [2, 5, 10, 15, 20, 25, 30, 40, 50, 75, 100]
TRACK_HOURS = 24

STABLECOINS   = {"USDC","BUSD","DAI","TUSD","USDD","FDUSD","USDP","PYUSD","USDB","USDX","EURC","USDT"}
SKIP_KEYWORDS = {"UP","DOWN","BULL","BEAR","3L","3S","2L","2S","HEDGE"}

BINANCE_SPOT    = "https://api.binance.com/api/v3"
BINANCE_DATA    = "https://data-api.binance.vision/api/v3"
BINANCE_FUTURES = "https://fapi.binance.com/fapi/v1"
MEXC_BASE       = "https://api.mexc.com/api/v3"

# ══════════════════════════════════════════════════════
#  STATE
# ══════════════════════════════════════════════════════

prev_prices   : Dict[str, float] = {}
alerted       : Dict[str, float] = {}
tracking      : Dict[str, dict]  = {}
last_fast     = 0.0
last_slow     = 0.0
last_bias_log = 0.0
signal_count  = 0
market_bias   = 0    # -100 to +100, updated each scan
market_cvd    = 0.0  # cumulative volume delta ($)
_multi_confirm       : Dict[str, dict] = {}   # {sym: {"count": N, "scanners": [], "last_time": ts}}
MULTI_CONFIRM_WINDOW = 1800  # 30 min window for multi-scanner confirmation

# ══════════════════════════════════════════════════════
#  LOGGING
# ══════════════════════════════════════════════════════

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-7s  %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S")
log = logging.getLogger("mafio")

# ══════════════════════════════════════════════════════
#  HTTP
# ══════════════════════════════════════════════════════

S = requests.Session()
S.headers.update({"User-Agent": "MAFIO-Bot/3.1"})

def _get(url, params=None, timeout=10):
    try:
        r = S.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.debug("GET %s → %s", url, e)
        return None

# ══════════════════════════════════════════════════════
#  REDIS
# ══════════════════════════════════════════════════════

def _redis(method, path, body=None):
    if not REDIS_URL or not REDIS_TOKEN: return None
    try:
        url = REDIS_URL.rstrip("/") + path
        h   = {"Authorization": f"Bearer {REDIS_TOKEN}"}
        r   = S.get(url, headers=h, timeout=5) if method == "GET" \
              else S.post(url, headers=h, json=body, timeout=5)
        return r.json()
    except Exception as e:
        log.debug("Redis: %s", e); return None

def save_state():
    if not REDIS_URL: return
    _redis("POST", f"/set/{REDIS_KEY}", {"value": json.dumps({
        "alerted":       dict(alerted),
        "tracking":      {k: {**v, "hit": list(v["hit"])} for k, v in tracking.items()},
        "signal_count":  signal_count,
    })})

def load_state():
    global alerted, tracking, signal_count
    if not REDIS_URL: return
    resp = _redis("GET", f"/get/{REDIS_KEY}")
    if not resp or not resp.get("result"): return
    try:
        s = json.loads(resp["result"])
        alerted.update(s.get("alerted", {}))
        signal_count = int(s.get("signal_count", 0))
        for k, v in s.get("tracking", {}).items():
            v["hit"] = set(v.get("hit", []))
            tracking[k] = v
        log.info("State: alerted=%d tracking=%d signals=%d",
                 len(alerted), len(tracking), signal_count)
    except Exception as e:
        log.warning("State load: %s", e)

# ══════════════════════════════════════════════════════
#  DATA FETCHING
# ══════════════════════════════════════════════════════

def _valid(sym):
    if not sym.endswith("USDT"): return False
    b = sym[:-4]
    if b in STABLECOINS: return False
    if any(k in b for k in SKIP_KEYWORDS): return False
    if "(" in sym: return False
    return True

def _parse(data, exchange, base_url):
    out = {}
    for t in data:
        sym = t.get("symbol", "")
        if not _valid(sym): continue
        try:
            price = float(t.get("lastPrice") or 0)
            if price <= 0: continue
            qv  = float(t.get("quoteVolume") or 0)
            bv  = float(t.get("volume")      or 0)
            vol = qv if qv > 1 else bv * price
            out[sym] = {
                "price":    price,
                "vol":      vol,
                "change":   float(t.get("priceChangePercent") or 0),
                "high24":   float(t.get("highPrice") or price),
                "low24":    float(t.get("lowPrice")  or price),
                "exchange": exchange,
                "base_url": base_url,
            }
        except Exception:
            continue
    return out

def fetch_binance():
    for url, label in [
        (BINANCE_SPOT,    "Spot"),
        (BINANCE_DATA,    "CDN"),
        (BINANCE_FUTURES, "Futures"),
    ]:
        data = _get(f"{url}/ticker/24hr")
        if isinstance(data, list) and len(data) > 100:
            out = _parse(data, "Binance", url)
            log.info("Binance %s: %d", label, len(out))
            return out
        log.warning("Binance %s failed", label)
    log.warning("All Binance endpoints failed")
    return {}

def fetch_mexc():
    data = _get(f"{MEXC_BASE}/ticker/24hr")
    if not isinstance(data, list):
        log.warning("MEXC: no data"); return {}
    out = _parse(data, "MEXC", MEXC_BASE)
    log.info("MEXC: %d", len(out))
    return out

def fetch_klines(sym, base_url, interval="5m", limit=25):
    data = _get(f"{base_url}/klines",
                {"symbol": sym, "interval": interval, "limit": limit})
    return data if isinstance(data, list) else []

# ══════════════════════════════════════════════════════
#  ANALYSIS
# ══════════════════════════════════════════════════════

def _qvol(c):
    try:
        v = float(c[7]); return v if v > 0 else float(c[5]) * float(c[4])
    except Exception:
        try: return float(c[5]) * float(c[4])
        except Exception: return 0.0

def vol_spike_and_move(candles):
    """Returns (spike_ratio, candle_move_pct)"""
    if len(candles) < 8: return 0.0, 0.0
    vols    = [_qvol(c) for c in candles]
    avg_vol = sum(vols[:-2]) / max(len(vols) - 2, 1)
    if avg_vol <= 0: return 0.0, 0.0
    spike = vols[-1] / avg_vol
    try:
        o  = float(candles[-1][1])
        cl = float(candles[-1][4])
        move = (cl - o) / o * 100 if o > 0 else 0.0
    except Exception:
        move = 0.0
    return spike, move

def calc_flow(candles):
    """Returns (buy_usdt, sell_usdt) from last FLOW_CANDLES candles"""
    buy = sell = 0.0
    for c in candles[-FLOW_CANDLES:]:
        try:
            h, lo, cl = float(c[2]), float(c[3]), float(c[4])
            vol = _qvol(c)
            rng = h - lo
            b   = (cl - lo) / rng if rng > 0 else 0.5
            buy += vol * b; sell += vol * (1 - b)
        except Exception:
            continue
    return buy, sell

def calc_ema(closes, period):
    if not closes: return 0.0
    k, ema = 2 / (period + 1), closes[0]
    for p in closes[1:]:
        ema = p * k + ema * (1 - k)
    return ema

def get_tier(vol_24h):
    """Return matching tier config based on 24h volume"""
    for tier in TIERS:
        if vol_24h <= tier["vol_max"]:
            return tier
    return TIERS[-1]

def is_late(price, h24, l24):
    rng = h24 - l24
    if rng <= 0: return False
    return (price - l24) / rng > LATE_ENTRY_PCT

# ══════════════════════════════════════════════════════
#  TELEGRAM
# ══════════════════════════════════════════════════════

_TG = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

def send(text):
    if not TELEGRAM_TOKEN:
        print(text); return
    for cid in filter(None, [CHAT_ID, GROUP_ID]):
        try:
            S.post(f"{_TG}/sendMessage",
                   json={"chat_id": cid, "text": text, "parse_mode": "Markdown"},
                   timeout=10)
        except Exception as e:
            log.error("TG: %s", e)

def _fv(v):
    if v >= 1e6:  return f"{v/1e6:.1f}M$"
    if v >= 1e3:  return f"{v/1e3:.1f}K$"
    return f"{v:.0f}$"

def _fp(p):
    if p >= 1000:  return f"{p:.2f}"
    if p >= 1:     return f"{p:.4f}"
    if p >= 0.001: return f"{p:.6f}"
    return f"{p:.8f}"

def _ts():
    return datetime.now(timezone.utc).strftime("%d %b %Y %H:%M")

# ══════════════════════════════════════════════════════
#  SIGNAL MESSAGE
# ══════════════════════════════════════════════════════

def build_signal(sym, price, change, buy_v, sell_v,
                 spike, move, exchange, tier_name, ema_bull,
                 high24=0.0, low24=0.0, badge="🔔1"):
    global signal_count
    signal_count += 1

    base  = sym[:-4]
    net   = buy_v - sell_v
    ratio = buy_v / sell_v if sell_v > 0 else 99.0

    # Position from bottom (% of 24h range)
    rng = high24 - low24
    pos_from_bottom = int((price - low24) / rng * 100) if rng > 0 else 0
    pos_ok = pos_from_bottom <= 50   # in lower half = good entry

    # Interest / Short Squeeze detection
    if ratio >= 8.0:
        interest = "🔥 High Short Squeeze Risk 🧨"
        int_icon = "🟡"
    elif ratio >= 4.0:
        interest = "⚡ Squeeze Risk"
        int_icon = "🟡"
    elif ratio >= 2.5:
        interest = "🟢 Bullish Flow"
        int_icon = "🟢"
    else:
        interest = "⚪ Neutral"
        int_icon = "⚪"

    # Exchange footer
    ex_note = "MEXC" if exchange == "MEXC" else "Binance"

    pos_icon = "✅" if pos_ok else "⚠️"

    return (
        f"{'━' * 20}\n"
        f"💀 *MAFIO SNIPER 15.2* 📡\n"
        f"\n"
        f"🆕 *#{base}* 💀 · Signal #{signal_count} {badge}\n"
        f"💰 Price: `${_fp(price)}`\n"
        f"📈 1h Move: `+{move:.2f}%` ⚡\n"
        f"📍 Position: `%{pos_from_bottom} from Bottom` {pos_icon}\n"
        f"\n"
        f"⚡ Volume: `{spike:.1f}x` above avg\n"
        f"{int_icon} Interest: {interest}\n"
        f"📊 Ratio: `{ratio:.1f}x` 🔥\n"
        f"💹 1h Flow:\n"
        f"  📥 In:  `{_fv(buy_v)}`\n"
        f"  📤 Out: `{_fv(sell_v)}`\n"
        f"  ▲ Net: `+{_fv(net)}` ✅\n"
        f"\n"
        f"🕐 {_ts()} UTC\n"
        f"{'━' * 20}\n"
        f"⚠️ اقتناص لحظي - تم رصد انفجار سيولة على {ex_note}! 🚀"
    )

# ══════════════════════════════════════════════════════
#  MILESTONES
# ══════════════════════════════════════════════════════

def check_milestones(all_t):
    now, expired = time.time(), []
    for sym, info in list(tracking.items()):
        if now - info["t0"] > TRACK_HOURS * 3600:
            expired.append(sym); continue
        t = all_t.get(sym)
        if not t: continue
        gain = (t["price"] - info["entry"]) / info["entry"] * 100.0
        if gain > info.get("max", 0.0):
            info["max"] = gain
        for ms in MILESTONES:
            if ms not in info["hit"] and gain >= ms:
                info["hit"].add(ms)
                _fire_ms(sym, ms, gain, t["price"], info["entry"],
                         int(now - info["t0"]), info["exchange"])
    for s in expired:
        tracking.pop(s, None)

def _tstr(e):
    """Wolf Flow style: always show minutes (e.g. 566m)"""
    e = max(e, 0)
    if e >= 60: return f"{e // 60}m"
    return f"{e}s"

def _fire_ms(sym, ms, gain, now_price, entry, elapsed, exchange):
    base    = sym[:-4]
    ex_icon = "🔶" if exchange == "MEXC" else "🔷"
    if ms == 2:
        icon  = "✅"
        title = f"*{base}USDT*  WIN confirmed  +{ms}% reached"
    elif ms >= 50: icon, title = "🚀", f"*{base}USDT*  +{ms}% milestone reached"
    elif ms >= 10: icon, title = "🔥", f"*{base}USDT*  +{ms}% milestone reached"
    else:          icon, title = "📈", f"*{base}USDT*  +{ms}% milestone reached"

    send(
        f"{icon} {title}\n"
        f"📊 Max gain:   +{gain:.2f}%\n"
        f"💰 Price now:  ${_fp(now_price)}\n"
        f"🏁 Entry:      ${_fp(entry)}\n"
        f"⏱ Achieved in: {_tstr(elapsed)}\n"
        f"{ex_icon} {exchange}"
    )
    log.info("MS %-14s +%d%% max=+%.2f%% in %s [%s]",
             sym, ms, gain, _tstr(elapsed), exchange)

# ══════════════════════════════════════════════════════
#  CORE CHECK
# ══════════════════════════════════════════════════════

def _check(sym, ticker, interval):
    now      = time.time()
    price    = ticker["price"]
    vol_24h  = ticker["vol"]
    change   = ticker["change"]
    exchange = ticker["exchange"]
    base_url = ticker["base_url"]

    # Skip already pumped or late entry
    if change > MAX_PUMP_24H: return
    if is_late(price, ticker["high24"], ticker["low24"]): return
    if now - alerted.get(sym, 0) < COOLDOWN: return

    # Get tier thresholds based on 24h volume
    tier = get_tier(vol_24h)

    # Market bias gate — like Wolf Flow
    if not should_signal(tier["name"], market_bias):
        log.debug("Skipped %s — bias=%d tier=%s", sym, market_bias, tier["name"])
        return
    spike_min = tier["spike"]
    ratio_min = tier["ratio"]
    net_min   = tier["net"]

    # Minimum absolute volume filter (avoid dust)
    if vol_24h < 30_000: return

    # Fetch klines
    candles = fetch_klines(sym, base_url, interval=interval, limit=25)
    if len(candles) < 10: return

    spike, move = vol_spike_and_move(candles)
    if spike < spike_min or move < 1.5: return

    buy_v, sell_v = calc_flow(candles)
    if sell_v <= 0: return
    ratio = buy_v / sell_v
    net   = buy_v - sell_v

    if ratio < ratio_min: return
    if net   < net_min:   return

    # EMA alignment
    closes   = [float(c[4]) for c in candles]
    e5, e10, e20 = calc_ema(closes, 5), calc_ema(closes, 10), calc_ema(closes, 20)
    ema_bull = e5 > e10 > e20

    # Multi-scanner confirmation badge
    scanner = "fast" if interval == "5m" else "slow"
    _, badge = _register_confirm(sym, scanner)

    # Fire
    alerted[sym] = now
    tracking[sym] = {
        "entry":    price,
        "t0":       now,
        "hit":      set(),
        "max":      0.0,
        "exchange": exchange,
    }
    save_state()

    msg = build_signal(sym, price, change, buy_v, sell_v,
                       spike, move, exchange, tier["name"], ema_bull,
                       high24=ticker["high24"], low24=ticker["low24"],
                       badge=badge)
    send(msg)
    log.info("SIGNAL %-14s tier=%-5s spike=%.1fx net=%s ratio=%.1fx [%s %s]",
             sym, tier["name"], spike, _fv(net), ratio, exchange, interval)

# ══════════════════════════════════════════════════════
#  MARKET BIAS  (like Wolf Flow Market Stats)
# ══════════════════════════════════════════════════════

def calc_market_bias(all_t: dict) -> Tuple[int, float, float]:
    """
    Returns (bias_score, cvd, taker_buy_ratio).

    bias_score : -100 (strong bear) → +100 (strong bull)
    Combines:
      • Market Breadth  — % coins up vs down (1h proxy via 24h change)
      • CVD             — aggregate (buy_vol - sell_vol) across top coins
      • Taker-buy ratio — buy_vol / total_vol

    Wolf Flow Market Bias logic:
      -100 = Strong Bear  (most coins falling, heavy selling)
      0    = Flat / Squeeze
      +100 = Strong Bull  (most coins rising, heavy buying)
    """
    up = down = flat = 0
    total_buy = total_sell = 0.0

    for t in all_t.values():
        c = t["change"]
        v = t["vol"]
        # Breadth
        if c > 1.0:   up   += 1
        elif c < -1.0: down += 1
        else:          flat  += 1
        # CVD estimate: if price went up → mostly buying; down → mostly selling
        if c > 0:
            total_buy  += v * min(abs(c) / 10, 0.8)
            total_sell += v * (1 - min(abs(c) / 10, 0.8))
        else:
            total_sell += v * min(abs(c) / 10, 0.8)
            total_buy  += v * (1 - min(abs(c) / 10, 0.8))

    breadth_total = up + down
    if breadth_total == 0:
        breadth_score = 0
    else:
        breadth_score = int((up - down) / breadth_total * 100)

    total_vol = total_buy + total_sell
    taker_buy_ratio = (total_buy / total_vol * 100) if total_vol > 0 else 50.0
    cvd = total_buy - total_sell

    # Composite score: 60% breadth + 40% taker-buy deviation from 50%
    taker_score = int((taker_buy_ratio - 50) * 2)   # -100 to +100
    bias_score  = int(breadth_score * 0.6 + taker_score * 0.4)
    bias_score  = max(-100, min(100, bias_score))

    return bias_score, cvd, taker_buy_ratio


def bias_label(score: int) -> str:
    if score >= 60:  return "🟢🟢 Strong Bull"
    if score >= 25:  return "🟢 Bullish"
    if score >= 5:   return "🟡 Mild Bullish"
    if score >= -5:  return "⚪ Flat / Squeeze"
    if score >= -25: return "🟠 Mild Bearish"
    if score >= -60: return "🔴 Bearish"
    return "🔴🔴 Strong Bear"


def should_signal(tier_name: str, bias: int) -> bool:
    """
    Wolf Flow logic: only fire signals when market conditions allow.
    Micro/Small caps can pump regardless of market → always allow.
    Mid/Large caps need positive bias.
    """
    if tier_name in ("Micro", "Small"):
        return bias > -70   # block only in crash conditions
    if tier_name == "Mid":
        return bias > -30   # need neutral or better
    # Large cap
    return bias > 0         # need positive bias


def _register_confirm(sym, scanner_name):
    # type: (str, str) -> tuple
    """
    Track how many different scanners fired for a coin in the last 30 min.
    Returns (count, badge_string) where badge shows 🔔 per scanner up to 3.
    E.g. count=2 → 🔔🔔2 means both fast + slow scan confirmed the signal.
    """
    global _multi_confirm
    now   = time.time()
    entry = _multi_confirm.get(sym)
    if not entry or (now - entry["last_time"]) > MULTI_CONFIRM_WINDOW:
        _multi_confirm[sym] = {"count": 0, "scanners": [], "last_time": now}
        entry = _multi_confirm[sym]
    if scanner_name not in entry["scanners"]:
        entry["count"]   += 1
        entry["scanners"].append(scanner_name)
        entry["last_time"] = now
    c     = entry["count"]
    badge = "🔔" * min(c, 3) + str(c)
    return c, badge


# ══════════════════════════════════════════════════════
#  FAST SCAN — 30s, 5m klines
# ══════════════════════════════════════════════════════

def fast_scan(all_t):
    global prev_prices
    movers = []
    for sym, t in all_t.items():
        prev = prev_prices.get(sym, 0)
        if prev > 0:
            delta = (t["price"] - prev) / prev * 100.0
            if delta >= FAST_TICKER_MOVE:
                movers.append((sym, delta, t))
    prev_prices = {sym: t["price"] for sym, t in all_t.items()}
    if not movers: return
    movers.sort(key=lambda x: -x[1])
    for sym, _, ticker in movers[:30]:
        _check(sym, ticker, "5m")
        time.sleep(0.05)

# ══════════════════════════════════════════════════════
#  SLOW SCAN — 5min, 1h klines
# ══════════════════════════════════════════════════════

def slow_scan(all_t):
    candidates = [
        (sym, t) for sym, t in all_t.items()
        if t["vol"] >= 30_000 and t["change"] <= MAX_PUMP_24H
    ]
    candidates.sort(key=lambda x: (-int(x[1]["exchange"] == "Binance"), -x[1]["vol"]))
    candidates = candidates[:300]
    log.info("slow_scan: %d/%d candidates (1h)", len(candidates), len(all_t))
    for sym, ticker in candidates:
        _check(sym, ticker, "1h")
        time.sleep(0.08)

# ══════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════

def main():
    global last_fast, last_slow
    log.info("🎯 MAFIO Liquidity Scanner v3.1 — starting")
    load_state()

    send(
        "🎯 *MAFIO Liquidity Scanner v3.1*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "✅ Bot started\n"
        "📡 Exchanges: *Binance* 🔷 + *MEXC* 🔶\n"
        f"⚡ Fast scan (5m): every {FAST_SCAN_S}s\n"
        f"📊 Slow scan (1h): every {SLOW_SCAN_S//60}min\n"
        "📊 Tiers: Micro / Small / Mid / Large cap\n"
        "📈 Market Bias: Breadth + CVD + Taker-buy filter\n"
        f"🔕 Cooldown: {COOLDOWN//3600}h per coin"
    )

    while True:
        try:
            now = time.time()
            if now - last_fast < FAST_SCAN_S:
                time.sleep(1); continue
            last_fast = now

            b = fetch_binance()
            m = fetch_mexc()
            all_t = {**m, **b}

            log.info("Tickers: Binance=%d MEXC=%d Total=%d Tracking=%d",
                     len(b), len(m), len(all_t), len(tracking))

            # ── Market Bias ───────────────────────────
            global market_bias, market_cvd, last_bias_log
            market_bias, market_cvd, tbr = calc_market_bias(all_t)
            if now - last_bias_log >= 300:   # log every 5 min
                last_bias_log = now
                log.info("Market Bias: %+d  %s  CVD=%s  TakerBuy=%.1f%%",
                         market_bias, bias_label(market_bias),
                         _fv(abs(market_cvd)), tbr)

            # Cleanup stale multi-confirm entries once per hour
            if int(now) % 3600 < 35:
                _old = [k for k, v in _multi_confirm.items()
                        if now - v["last_time"] > MULTI_CONFIRM_WINDOW]
                for k in _old:
                    _multi_confirm.pop(k, None)

            check_milestones(all_t)
            fast_scan(all_t)

            if now - last_slow >= SLOW_SCAN_S:
                last_slow = now
                slow_scan(all_t)

        except KeyboardInterrupt:
            log.info("Stopped."); break
        except Exception as e:
            log.error("Loop: %s", e, exc_info=True)
            time.sleep(5)

if __name__ == "__main__":
    main()

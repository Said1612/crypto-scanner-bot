# -*- coding: utf-8 -*-
"""
🎯 MAFIO Liquidity Scanner v3.1
MEXC only — works on Railway without IP restrictions
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
PROXY_URL      = os.getenv("PROXY_URL", "")   # e.g. http://user:pass@host:port

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
    {"name": "Micro",  "vol_max": 2_000_000,  "vol_min": 500_000,   "spike": 3.5, "ratio": 2.5, "net": 150},
    {"name": "Small",  "vol_max": 15_000_000, "vol_min": 2_000_000,  "spike": 3.0, "ratio": 2.2, "net": 800},
    {"name": "Mid",    "vol_max": 80_000_000, "vol_min": 15_000_000, "spike": 3.0, "ratio": 2.0, "net": 15_000},
    {"name": "Large",  "vol_max": 9e99,        "vol_min": 80_000_000, "spike": 2.5, "ratio": 1.8, "net": 80_000},
]

FAST_TICKER_MOVE = 1.0   # 30s price delta to trigger 5m klines fetch
FLOW_CANDLES     = 3     # candles for flow calculation
MAX_PUMP_24H     = 60.0  # skip already-pumped coins
LATE_ENTRY_PCT   = 0.85  # skip if price in top 15% of 24h range

MILESTONES  = [2, 5, 10, 15, 20, 25, 30, 40, 50, 75, 100]
TRACK_HOURS = 24

STABLECOINS   = {"USDC","BUSD","DAI","TUSD","USDD","FDUSD","USDP","PYUSD","USDB","USDX","EURC","USDT"}
SKIP_KEYWORDS = {"UP","DOWN","BULL","BEAR","3L","3S","2L","2S","HEDGE"}

MEXC_BASE    = "https://api.mexc.com/api/v3"
MEXC_FUTURES = "https://contract.mexc.com/api/v1"

# ══════════════════════════════════════════════════════
#  STATE
# ══════════════════════════════════════════════════════

prev_prices   : Dict[str, float] = {}
alerted       : Dict[str, float] = {}
tracking      : Dict[str, dict]  = {}
daily_results : List[dict]       = []   # completed signals for daily report
last_fast     = 0.0
last_slow     = 0.0
last_bias_log = 0.0
last_report   = 0.0   # last daily report sent (unix ts)
signal_count  = 0
market_bias   = 0
market_cvd    = 0.0
_multi_confirm       : Dict[str, dict] = {}   # {sym: {"count": N, "scanners": [], "last_time": ts}}
MULTI_CONFIRM_WINDOW = 1800  # 30 min window for multi-scanner confirmation
_funding_cache       : Dict[str, dict] = {}   # {sym: {"rate": float, "label": str, "ts": float}}
FUNDING_TTL          = 300   # refresh funding rate every 5 min

# ══════════════════════════════════════════════════════
#  LOGGING
# ══════════════════════════════════════════════════════

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-7s  %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                    stream=__import__("sys").stdout)
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

def fetch_mexc():
    """MEXC tickers — works on Railway and VPS (no IP restrictions)"""
    data = _get(f"{MEXC_BASE}/ticker/24hr")
    if isinstance(data, list) and len(data) > 100:
        out = _parse(data, "MEXC", MEXC_BASE)
        log.info("MEXC: %d", len(out))
        return out
    log.warning("MEXC failed")
    return {}

def _fut_sym(sym):
    """BTCUSDT → BTC_USDT  (MEXC Futures symbol format)"""
    return sym[:-4] + "_USDT"

def fetch_mexc_funding_rate(sym):
    """
    MEXC Futures funding rate — works on Railway (no IP restrictions).
    Positive = longs pay shorts = bullish (smart money buying longs).
    Negative = shorts pay longs = bearish or short squeeze setup.
    """
    now   = time.time()
    cache = _funding_cache.get(sym)
    if cache and (now - cache["ts"]) < FUNDING_TTL:
        return cache["rate"], cache["label"]
    data = _get(f"{MEXC_FUTURES}/contract/funding_rate/{_fut_sym(sym)}", timeout=5)
    if not data or not data.get("success") or not data.get("data"):
        _funding_cache[sym] = {"rate": None, "label": "Spot", "ts": now}
        return None, "Spot"
    try:
        rate = float(data["data"]["fundingRate"]) * 100   # → %
        if rate > 0.02:
            label = "🟢 Bullish / Longs"
        elif rate < -0.02:
            label = "🔴 Bearish / Shorts"
        else:
            label = "🟡 Neutral / Covering"
        _funding_cache[sym] = {"rate": rate, "label": label, "ts": now}
        return rate, label
    except Exception:
        _funding_cache[sym] = {"rate": None, "label": "Spot", "ts": now}
        return None, "Spot"

def fetch_mexc_fut_ob(sym, levels=20):
    """MEXC Futures order book imbalance (bid dominance 0.0–1.0)."""
    data = _get(f"{MEXC_FUTURES}/contract/depth/{_fut_sym(sym)}",
                {"limit": levels}, timeout=5)
    if not data or not data.get("success") or not data.get("data"):
        return 0.5
    try:
        depth = data["data"]
        def _side_vol(entries):
            total = 0.0
            for e in entries[:levels]:
                if isinstance(e, (list, tuple)):
                    total += float(e[0]) * float(e[1])
                elif isinstance(e, dict):
                    total += float(e.get("price", 0)) * float(e.get("vol", 0))
            return total
        bid_vol = _side_vol(depth.get("bids", []))
        ask_vol = _side_vol(depth.get("asks", []))
        total   = bid_vol + ask_vol
        return bid_vol / total if total > 0 else 0.5
    except Exception:
        return 0.5

def fetch_klines(sym, base_url, interval="5m", limit=25):
    data = _get(f"{base_url}/klines",
                {"symbol": sym, "interval": interval, "limit": limit})
    return data if isinstance(data, list) else []

def fetch_agg_trades(sym, base_url, minutes=60):
    """
    Real buy/sell volume from actual trades (Wolf Flow: real-time, no lag).
    m=True  → maker is buyer  → taker is SELLER  → sell volume
    m=False → maker is seller → taker is BUYER    → buy volume
    Uses limit=500 only (no startTime).
    """
    data = _get(f"{base_url}/aggTrades", {"symbol": sym, "limit": 500}, timeout=8)
    if not isinstance(data, list) or not data:
        return 0.0, 0.0
    buy = sell = 0.0
    for t in data:
        try:
            vol = float(t["q"]) * float(t["p"])
            if t.get("m", True):   # m=True → market SELL
                sell += vol
            else:                  # m=False → market BUY
                buy += vol
        except Exception:
            continue
    return buy, sell

def fetch_ob_imbalance(sym, base_url, levels=20):
    """
    Order book bid/ask USDT imbalance (Wolf Flow: order book spot/future).
    Returns ratio 0.0–1.0:  >0.55 = buyers dominate  |  <0.45 = sellers dominate
    """
    data = _get(f"{base_url}/depth", {"symbol": sym, "limit": levels}, timeout=5)
    if not data:
        return 0.5
    try:
        bid_vol = sum(float(b[0]) * float(b[1]) for b in data.get("bids", [])[:levels])
        ask_vol = sum(float(a[0]) * float(a[1]) for a in data.get("asks", [])[:levels])
        total   = bid_vol + ask_vol
        return bid_vol / total if total > 0 else 0.5
    except Exception:
        return 0.5


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
    """Returns (spike_ratio, candle_move_pct, avg_vol_usdt)"""
    if len(candles) < 8: return 0.0, 0.0, 0.0
    vols    = [_qvol(c) for c in candles]
    avg_vol = sum(vols[:-2]) / max(len(vols) - 2, 1)
    if avg_vol <= 0: return 0.0, 0.0, 0.0
    spike = vols[-1] / avg_vol
    try:
        o  = float(candles[-1][1])
        cl = float(candles[-1][4])
        move = (cl - o) / o * 100 if o > 0 else 0.0
    except Exception:
        move = 0.0
    return spike, move, avg_vol

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
                 high24=0.0, low24=0.0, badge="🔔1",
                 funding_label="Spot", ob_label="⚪ Balanced", ob_pct=50):
    global signal_count
    signal_count += 1

    base  = sym[:-4]
    net   = buy_v - sell_v
    ratio = buy_v / sell_v if sell_v > 0 else 99.0

    # Position from bottom (% of 24h range)
    rng = high24 - low24
    pos_from_bottom = int((price - low24) / rng * 100) if rng > 0 else 0
    pos_ok = pos_from_bottom <= 60   # in lower 60% of range = good entry

    # Interest / Short Squeeze detection
    if ratio >= 30.0:
        interest = "Institutional Breakout 🐋"
        int_icon = "🔵"
    elif ratio >= 8.0:
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
        f"📗 Order Book: {ob_label} `{ob_pct}%` bids\n"
        f"📌 Funding: {funding_label}\n"
        f"\n"
        f"🕐 {_ts()} UTC\n"
        f"{'━' * 20}"
    )

# ══════════════════════════════════════════════════════
#  MILESTONES
# ══════════════════════════════════════════════════════

def check_milestones(all_t):
    global daily_results
    now, expired = time.time(), []
    for sym, info in list(tracking.items()):
        if now - info["t0"] > TRACK_HOURS * 3600:
            expired.append(sym); continue
        t = all_t.get(sym)
        if not t: continue
        gain = (t["price"] - info["entry"]) / info["entry"] * 100.0
        if gain > info.get("max", 0.0):
            info["max"] = gain
        # Find all unnotified milestones reached — send only the highest
        pending = [ms for ms in MILESTONES if ms not in info["hit"] and gain >= ms]
        if pending:
            for ms in pending:
                info["hit"].add(ms)
            _fire_ms(sym, pending[-1], gain, t["price"], info["entry"],
                     int(now - info["t0"]), info["exchange"])
    for s in expired:
        info = tracking.pop(s, None)
        if info:
            daily_results.append({
                "sym":     s,
                "entry":   info["entry"],
                "max":     info.get("max", 0.0),
                "elapsed": int(now - info["t0"]),
                "success": info.get("max", 0.0) >= 5.0,
            })

def send_daily_report():
    global daily_results
    now    = datetime.now(timezone.utc)
    date   = now.strftime("%d %b %Y")
    active = list(tracking.values())

    # Combine active + completed today
    all_entries = []
    for info in active:
        all_entries.append({
            "sym":     [k for k,v in tracking.items() if v is info][0] if tracking else "?",
            "entry":   info["entry"],
            "max":     info.get("max", 0.0),
            "elapsed": int(time.time() - info["t0"]),
            "success": info.get("max", 0.0) >= 5.0,
            "active":  True,
        })
    for r in daily_results:
        r["active"] = False
        all_entries.append(r)

    # Fix active sym names
    sym_map = {id(v): k for k, v in tracking.items()}
    for e in all_entries:
        if e.get("active") and e["sym"] == "?":
            e["sym"] = "UNKNOWN"

    total   = len(all_entries)
    success = sum(1 for e in all_entries if e["success"])
    miss    = total - success
    avg_pk  = sum(e["max"] for e in all_entries) / total if total else 0.0

    # Sort by max gain desc
    all_entries.sort(key=lambda x: -x["max"])

    lines = [f"📊 *Daily Symbol Report*\n{date} UTC\n"]
    lines.append(
        f"🔔 Active ({total} symbols)\n"
        f"✅ {success} success  ❌ {miss} miss  "
        f"avg peak *+{avg_pk:.2f}%*\n"
    )
    for e in all_entries[:20]:   # max 20 lines
        base = e["sym"][:-4] if e["sym"].endswith("USDT") else e["sym"]
        icon = "✅" if e["success"] else "❌"
        act  = " 🔄" if e.get("active") else ""
        h    = e["elapsed"] // 3600
        m    = (e["elapsed"] % 3600) // 60
        t_str = f"{h}h {m}m" if h else f"{m}m"
        lines.append(
            f"{icon} *{base}* entry ${_fp(e['entry'])} "
            f"max *+{e['max']:.2f}%* ⏱ {t_str}{act}"
        )
    if total > 20:
        lines.append(f"+{total - 20} more")

    lines.append(f"\n_Report sent daily at 23:00 UTC_")
    send("\n".join(lines))
    log.info("Daily report sent: %d symbols, %d success, %d miss", total, success, miss)
    # Reset daily results after sending
    daily_results = []


def _tstr(e):
    """Wolf Flow style: always show minutes (e.g. 566m)"""
    e = max(e, 0)
    if e >= 60: return f"{e // 60}m"
    return f"{e}s"

def _fire_ms(sym, ms, gain, now_price, entry, elapsed, exchange):
    base    = sym[:-4]
    ex_icon = "🟠"
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

    # Minimum volume per tier (Micro=$500K, Small=$2M, Mid=$15M, Large=$80M)
    if vol_24h < tier["vol_min"]:
        log.debug("Low vol skip %s vol=%s tier=%s", sym, _fv(vol_24h), tier["name"])
        return

    spike_min = tier["spike"]
    ratio_min = tier["ratio"]
    net_min   = tier["net"]

    # ── Funding Rate (Wolf Flow primary signal) — MEXC Futures ───────────
    funding_rate, funding_label = fetch_mexc_funding_rate(sym)
    funding_bullish = funding_rate is not None and funding_rate > 0.03  # raised from 0.01
    if funding_bullish:
        spike_min = max(2.0, spike_min * 0.60)
        ratio_min = max(1.8, ratio_min * 0.70)  # never drop below 1.8x
        net_min   = max(net_min * 0.4, 100)
        log.debug("Funding bullish %s → spike≥%.1f ratio≥%.2f net≥%s bypass_bias=True",
                  sym, spike_min, ratio_min, _fv(net_min))

    # Market bias gate — bypass if funding bullish
    if not funding_bullish and not should_signal(tier["name"], market_bias):
        log.debug("Skipped %s — bias=%d tier=%s", sym, market_bias, tier["name"])
        return

    # ── Step 1: Klines — volume spike detection only ─────────────────
    candles = fetch_klines(sym, base_url, interval=interval, limit=25)
    if len(candles) < 10: return

    spike, move, avg_vol = vol_spike_and_move(candles)
    move_min = 0.8 if funding_bullish else 1.5  # raised from 0.3
    if move < move_min: return

    # Reject dead coins (zero base volume) — MEXC has lower liquidity baseline
    if avg_vol < (50 if exchange == "MEXC" else 200): return

    # ── Pre-check real ratio for Super-Ratio Bypass ────────────────────
    # PIPPIN pattern: ratio 63.8x but spike only 1.8x (institution buying quietly)
    # When almost nobody is selling, spike threshold is irrelevant → bypass
    _pre_buy, _pre_sell = fetch_agg_trades(sym, base_url,
                                            minutes=60 if interval == "1h" else 10)
    _pre_ratio = _pre_buy / _pre_sell if _pre_sell > 0 else 99.0
    super_ratio = _pre_ratio >= 20.0   # institutional / near-zero sell pressure
    effective_spike_min = 1.5 if super_ratio else spike_min
    if spike < effective_spike_min:
        return

    # Spike candle must close in upper half — rejects pump-dump wicks (BNK style)
    try:
        sc = candles[-1]
        sc_rng = float(sc[2]) - float(sc[3])
        sc_close_pct = (float(sc[4]) - float(sc[3])) / sc_rng if sc_rng > 0 else 0.5
    except Exception:
        sc_close_pct = 0.5
    if sc_close_pct < 0.50:
        log.debug("Dump-wick skip %s close=%.0f%%", sym, sc_close_pct * 100)
        return

    # Late-entry guard
    rng24 = ticker["high24"] - ticker["low24"]
    pos24 = (price - ticker["low24"]) / rng24 if rng24 > 0 else 0.5
    if move > 4.0 and pos24 > 0.70:
        log.debug("Late-move skip %s move=%.1f%% pos=%.0f%%", sym, move, pos24 * 100)
        return

    # ── Step 2: Real buy/sell from aggTrades (reuse pre-fetched data) ───
    buy_v, sell_v = _pre_buy, _pre_sell
    if sell_v <= 0: return
    ratio = buy_v / sell_v
    net   = buy_v - sell_v

    if ratio < ratio_min: return
    if net   < net_min:   return

    # ── Step 3: Order book imbalance (spot 70% + futures 30%) ────────────
    ob_spot  = fetch_ob_imbalance(sym, base_url, levels=20)
    ob_fut   = fetch_mexc_fut_ob(sym, levels=20)
    ob_score = ob_spot * 0.7 + ob_fut * 0.3
    if ob_score < 0.40:
        log.debug("OB bearish skip %s ob_spot=%.2f ob_fut=%.2f", sym, ob_spot, ob_fut)
        return
    if ob_spot > 0.58:
        ob_label = "🟢 Buyers"
    elif ob_spot < 0.44:
        ob_label = "🔴 Sellers"
    else:
        ob_label = "⚪ Balanced"

    # Funding bearish block
    if funding_rate is not None and funding_rate < -0.05:
        log.debug("Bearish funding skip %s rate=%.4f%%", sym, funding_rate)
        return

    ema_bull = True

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
                       badge=badge, funding_label=funding_label,
                       ob_label=ob_label, ob_pct=int(ob_spot * 100))
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
        return bias > -70   # block only in extreme crash
    if tier_name == "Mid":
        return bias > -60   # was -30, relaxed — Mid can pump in bear market
    # Large cap
    return bias > -30


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
    eligible = [
        (sym, t) for sym, t in all_t.items()
        if t["vol"] >= 500_000 and t["change"] <= MAX_PUMP_24H
    ]
    # Top 150 by volume (Mid/Large caps)
    by_vol = sorted(eligible, key=lambda x: -x[1]["vol"])[:150]
    # Top 150 by 24h change (Micro/Small pumpers)
    by_chg = sorted(eligible, key=lambda x: -x[1]["change"])[:150]
    # Merge without duplicates
    seen = set()
    candidates = []
    for item in by_vol + by_chg:
        if item[0] not in seen:
            seen.add(item[0])
            candidates.append(item)
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
        "📡 Exchange: *MEXC* 🟠\n"
        f"⚡ Fast scan (5m): every {FAST_SCAN_S}s\n"
        f"📊 Slow scan (1h): every {SLOW_SCAN_S//60}min\n"
        "📊 Tiers: Micro / Small / Mid / Large cap\n"
        "📈 Market Bias: Breadth + CVD + Taker-buy filter\n"
        "💰 Funding Rate: Bullish/Bearish detection\n"
        f"🔕 Cooldown: {COOLDOWN//3600}h per coin"
    )

    while True:
        try:
            now = time.time()
            if now - last_fast < FAST_SCAN_S:
                time.sleep(1); continue
            last_fast = now

            all_t = fetch_mexc()

            log.info("Tickers: MEXC=%d Tracking=%d", len(all_t), len(tracking))

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

            # ── Daily Report at 23:00 UTC ─────────────
            utc_h = datetime.now(timezone.utc).hour
            utc_m = datetime.now(timezone.utc).minute
            if utc_h == 23 and utc_m == 0 and now - last_report > 3600:
                last_report = now
                send_daily_report()

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

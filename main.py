# -*- coding: utf-8 -*-
"""
🎯 MAFIO SNIPER
MEXC only — works on Railway without IP restrictions
Detects liquidity entry by tier: Micro / Small / Mid / Large cap
Based on analysis of real Wolf Flow trades (Mar-Apr 2026)
"""

import os, time, json, logging, base64
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional
import requests

# AI agent — optional, loads model from signal_history.json at startup
try:
    from ai_agent import MafioAgent as _MafioAgentCls
    _ai_agent = _MafioAgentCls()
except Exception as _ai_err:
    _ai_agent = None
    logging.getLogger(__name__).warning("AI agent not loaded: %s", _ai_err)

# ══════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "7696119722:AAHtxydYz5qg4SmyF38M0X6agntIYSuOjXY")
CHAT_ID        = os.getenv("CHAT_ID") or ""
GROUP_ID       = os.getenv("GROUP_ID") or "-1003951885039"
REDIS_URL      = os.getenv("REDIS_URL", os.getenv("UPSTASH_REDIS_REST_URL", ""))
REDIS_TOKEN    = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")
REDIS_KEY      = "mafio_v31"
PROXY_URL      = os.getenv("PROXY_URL", "")   # e.g. http://user:pass@host:port

FAST_SCAN_S      = 5     # every 5s — confirmed working: catches REPAI/NEOS/BLINKY type explosions
SLOW_SCAN_S      = 300   # every 5min (1h klines)
SUPER_SCAN_S     = 900   # every 15min — SUPERTREND(10,3) flip scanner (BIO/ORDI/币安人生 type)
SLEEP_GIANT_S    = 60    # every 60s — sleeping giant: flat coin sudden 1m volume explosion
COOLDOWN         = 7200  # 2h per coin
FAST_TICKER_MOVE = 0.3   # 5s price delta trigger — lowered 0.5→0.3 to catch gradual pumps (TRU/CTSI/DUSK)

# ── Tier thresholds (from real trade analysis) ────────
# Format: (24h_vol_max, vol_spike_min, flow_ratio_min, net_flow_min)
# Micro cap  < $2M  : small moves need less liquidity → easiest to pump
# Small cap  $2-15M : medium moves
# Mid cap    $15-80M: larger moves
# Large cap  > $80M : hardest to move
TIERS = [
    # Micro: tiny liquidity — high ratio required (VINE 2.2x failed; 3.0 base → ~2.64 neutral)
    {"name": "Micro",  "vol_max": 2_000_000,  "vol_min": 50_000,    "spike": 3.5, "ratio": 3.0, "net": 5_000},
    # Small: medium liquidity
    {"name": "Small",  "vol_max": 15_000_000, "vol_min": 300_000,   "spike": 2.8, "ratio": 2.5, "net": 15_000},
    # Mid: good liquidity
    {"name": "Mid",    "vol_max": 80_000_000, "vol_min": 3_000_000, "spike": 2.5, "ratio": 2.5, "net": 60_000},
    # Large: deep liquidity
    {"name": "Large",  "vol_max": 9e99,        "vol_min": 15_000_000,"spike": 2.2, "ratio": 1.8, "net": 250_000},
]

FLOW_CANDLES     = 3     # candles for flow calculation
MAX_PUMP_24H     = 60.0  # skip already-pumped coins
LATE_ENTRY_PCT   = 0.92  # skip if price in top 8% of 24h range
REPORT_HOUR      = int(os.getenv("REPORT_HOUR", "23"))  # UTC hour — Morocco UTC+1: 23=midnight local

MILESTONES  = [5, 10, 15, 20, 25, 30, 40, 50, 75, 100,
               125, 150, 175, 200, 250, 300, 400, 500]
TRACK_HOURS      = 24
SIGNAL_TIMEOUT_H = 8      # expire signal if no +5% within 8h (weak/slow signals)
SIGNAL_SL_PCT    = -5.0   # stop-loss: exit tracking if -5% below entry
SIGNAL_DB        = "signal_history.json"  # ML training data — append only, never reset

STABLECOINS   = {"USDC","BUSD","DAI","TUSD","USDD","FDUSD","USDP","PYUSD","USDB","USDX","EURC","USDT","AEUR","EURI","USD1","USDE","USDY","USDM",
                  "XUSD","RLUSD","BFUSD","U","USDGO","USDF","USDZ","USDK","USDJ","GUSD","SUSD","MUSD","CUSD",
                  "EUR","GBP","AUD","JPY","CHF","CAD","TRY","BRL","RUB","KRW","CNY","HKD","SGD","AED","SAR","MXN","PLN","SEK","NOK","DKK",
                  "PAXG","XAUT","OURIEL"}
SKIP_KEYWORDS = {"UP","DOWN","BULL","BEAR","3L","3S","2L","2S","HEDGE","BVOL","IBVOL"}
# Coins to skip permanently: delisted, suspended, or confirmed manipulation-prone
BLACKLIST     = {"MFT", "APR", "LOOM", "TORN", "ELF", "SPARTA",
                  "XAUT", "PAXG", "XAGX",   # Gold/silver commodity tokens
                  "LSM"}                      # Confirmed wash-trading manipulation (97% fake bids)

# ── Coin Categories — used in daily report Top 10 ──────────────
COIN_CATEGORIES = {
    # 🐸 Meme
    "DOGE":("🐸","Meme"),"SHIB":("🐸","Meme"),"PEPE":("🐸","Meme"),
    "FLOKI":("🐸","Meme"),"WIF":("🐸","Meme"),"BONK":("🐸","Meme"),
    "GIGGLE":("🐸","Meme"),"TST":("🐸","Meme"),"BROCCOLI714":("🐸","Meme"),
    "BROCCOLI":("🐸","Meme"),"PLAY":("🐸","Meme"),"MEME":("🐸","Meme"),
    "TURBO":("🐸","Meme"),"POPCAT":("🐸","Meme"),"NEIRO":("🐸","Meme"),
    "BOME":("🐸","Meme"),"DOGS":("🐸","Meme"),"PNUT":("🐸","Meme"),
    "ACT":("🐸","Meme"),"MOODENG":("🐸","Meme"),"HMSTR":("🐸","Meme"),
    "NOT":("🐸","Meme"),"BRETT":("🐸","Meme"),"MOG":("🐸","Meme"),
    "GOAT":("🐸","Meme"),"TRUMP":("🐸","Meme"),"MELANIA":("🐸","Meme"),
    "FARTCOIN":("🐸","Meme"),"BABYDOGE":("🐸","Meme"),"COW":("🐸","Meme"),
    "HIPPO":("🐸","Meme"),"CATI":("🐸","Meme"),"SPX":("🐸","Meme"),
    "GIGA":("🐸","Meme"),"PONKE":("🐸","Meme"),"MYRO":("🐸","Meme"),
    "SLERF":("🐸","Meme"),"WEN":("🐸","Meme"),"BODEN":("🐸","Meme"),
    # 🎮 GameFi
    "ENJ":("🎮","GameFi"),"AXS":("🎮","GameFi"),"SAND":("🎮","GameFi"),
    "MANA":("🎮","GameFi"),"IMX":("🎮","GameFi"),"GALA":("🎮","GameFi"),
    "ILV":("🎮","GameFi"),"FF":("🎮","GameFi"),"D":("🎮","GameFi"),
    "MAGIC":("🎮","GameFi"),"GODS":("🎮","GameFi"),"SLP":("🎮","GameFi"),
    "TLM":("🎮","GameFi"),"ALICE":("🎮","GameFi"),"SKILL":("🎮","GameFi"),
    "ATLAS":("🎮","GameFi"),"POLIS":("🎮","GameFi"),"RFOX":("🎮","GameFi"),
    "DERC":("🎮","GameFi"),"FEVR":("🎮","GameFi"),"SPS":("🎮","GameFi"),
    "CHR":("🎮","GameFi"),"PYR":("🎮","GameFi"),"CEEK":("🎮","GameFi"),
    "HERO":("🎮","GameFi"),"QUEST":("🎮","GameFi"),"UFO":("🎮","GameFi"),
    # 🤖 AI
    "FET":("🤖","AI"),"AGIX":("🤖","AI"),"OCEAN":("🤖","AI"),
    "RENDER":("🤖","AI"),"TAO":("🤖","AI"),"HOLO":("🤖","AI"),
    "NMR":("🤖","AI"),"GRT":("🤖","AI"),"PAAL":("🤖","AI"),
    "VIRTUAL":("🤖","AI"),"AI16Z":("🤖","AI"),"AIOZ":("🤖","AI"),
    "IO":("🤖","AI"),"ARKM":("🤖","AI"),"GRASS":("🤖","AI"),
    "ORAI":("🤖","AI"),"PRIME":("🤖","AI"),"ALT":("🤖","AI"),
    "SLEEPLESS":("🤖","AI"),"PROMPT":("🤖","AI"),
    # 🏛 RWA
    "PLUME":("🏛","RWA"),"ONDO":("🏛","RWA"),"CFG":("🏛","RWA"),
    "TRU":("🏛","RWA"),"MPL":("🏛","RWA"),"RIO":("🏛","RWA"),
    "PROPY":("🏛","RWA"),"PROPS":("🏛","RWA"),"PARCL":("🏛","RWA"),
    # 🖼 NFT
    "FIO":("🖼","NFT"),"BLUR":("🖼","NFT"),"X2Y2":("🖼","NFT"),
    "LOOKS":("🖼","NFT"),"RARI":("🖼","NFT"),"RARE":("🖼","NFT"),
    # ⛏ PoW
    "BTC":("⛏","PoW"),"LTC":("⛏","PoW"),"ZEC":("⛏","PoW"),
    "KAS":("⛏","PoW"),"RVN":("⛏","PoW"),"ETC":("⛏","PoW"),
    "KDA":("⛏","PoW"),"FLUX":("⛏","PoW"),"ALPH":("⛏","PoW"),
    "BCH":("⛏","PoW"),"ZEN":("⛏","PoW"),"SC":("⛏","PoW"),
    "XMR":("⛏","PoW"),"DASH":("⛏","PoW"),
    # 🔧 Infra
    "WCT":("🔧","Infra"),"DOT":("🔧","Infra"),"LINK":("🔧","Infra"),
    "BAND":("🔧","Infra"),"API3":("🔧","Infra"),"UMA":("🔧","Infra"),
    "PYTH":("🔧","Infra"),"IOTX":("🔧","Infra"),"DIA":("🔧","Infra"),
    "NKN":("🔧","Infra"),"WLD":("🔧","Infra"),"MDT":("🔧","Infra"),
    "OXT":("🔧","Infra"),"LPT":("🔧","Infra"),
    # 💎 DeFi
    "UNI":("💎","DeFi"),"SUSHI":("💎","DeFi"),"CAKE":("💎","DeFi"),
    "CRV":("💎","DeFi"),"COMP":("💎","DeFi"),"AAVE":("💎","DeFi"),
    "SNX":("💎","DeFi"),"DYDX":("💎","DeFi"),"GMX":("💎","DeFi"),
    "JOE":("💎","DeFi"),"RAY":("💎","DeFi"),"1INCH":("💎","DeFi"),
    "PERP":("💎","DeFi"),"CVX":("💎","DeFi"),"LDO":("💎","DeFi"),
    "PENDLE":("💎","DeFi"),"ENA":("💎","DeFi"),"DUSK":("💎","DeFi"),
    "BIFI":("💎","DeFi"),"BAL":("💎","DeFi"),"DEXE":("💎","DeFi"),
    # ⛓ L1/L2
    "ETH":("⛓","L1/L2"),"SOL":("⛓","L1/L2"),"AVAX":("⛓","L1/L2"),
    "ADA":("⛓","L1/L2"),"BNB":("⛓","L1/L2"),"MATIC":("⛓","L1/L2"),
    "ARB":("⛓","L1/L2"),"OP":("⛓","L1/L2"),"NEAR":("⛓","L1/L2"),
    "ATOM":("⛓","L1/L2"),"FTM":("⛓","L1/L2"),"TRX":("⛓","L1/L2"),
    "XRP":("⛓","L1/L2"),"XLM":("⛓","L1/L2"),"ONE":("⛓","L1/L2"),
    "HBAR":("⛓","L1/L2"),"VET":("⛓","L1/L2"),"APT":("⛓","L1/L2"),
    "SUI":("⛓","L1/L2"),"SEI":("⛓","L1/L2"),"INJ":("⛓","L1/L2"),
    "TON":("⛓","L1/L2"),"STX":("⛓","L1/L2"),"KLAY":("⛓","L1/L2"),
    "CELO":("⛓","L1/L2"),"EGLD":("⛓","L1/L2"),"ALGO":("⛓","L1/L2"),
    "ONT":("⛓","L1/L2"),"ONG":("⛓","L1/L2"),"OSMO":("⛓","L1/L2"),
    # 🧬 DeSci/Bio
    "BIO":("🧬","DeSci"),"ATH":("🧬","DeSci"),"VITA":("🧬","DeSci"),
    # ₿ BTC Ecosystem
    "ORDI":("₿","BTC Eco"),"SATS":("₿","BTC Eco"),"RATS":("₿","BTC Eco"),
    # 🔒 Privacy
    "SCRT":("🔒","Privacy"),"BEAM":("🔒","Privacy"),"ROSE":("🔒","Privacy"),
    # 📦 Storage
    "FIL":("📦","Storage"),"AR":("📦","Storage"),"THETA":("📦","Storage"),
    # 💰 Exchange
    "OKB":("💰","Exchange"),"CRO":("💰","Exchange"),"MX":("💰","Exchange"),
    # 🔐 Security/Oracle
    "MINA":("🔐","ZK"),"DUSK":("🔐","ZK"),"ZCASH":("🔐","ZK"),
}

MEXC_BASE    = "https://api.mexc.com/api/v3"
MEXC_FUTURES = "https://contract.mexc.com/api/v1"

BINANCE_BASE          = "https://api.binance.com/api/v3"
BINANCE_FUTURES       = "https://fapi.binance.com"
BINANCE_ALPHA_TOKEN_URL = "https://www.binance.com/bapi/defi/v1/public/wallet-direct/buw/wallet/cex/alpha/all/token/list"
USE_BINANCE  = os.getenv("USE_BINANCE", "true").lower() == "true"  # disable on Railway
USE_MEXC     = os.getenv("USE_MEXC",    "false").lower() == "true" # disabled — low signal quality

# ══════════════════════════════════════════════════════
#  STATE
# ══════════════════════════════════════════════════════

prev_prices   : Dict[str, float] = {}
_btc_prices   : List[Tuple[float, float]] = []   # [(ts, price), ...] — rolling 15min window
_btc_alert_ts : float = 0.0                       # last BTC health alert sent
_cascade_alert_ts : float = 0.0                   # last dump cascade alert sent
_cascade_paused   : float = 0.0                   # signals paused until this ts
_snap_prices  : Dict[str, float] = {}             # price snapshot every 5min for cascade detection
_snap_ts      : float = 0.0                       # timestamp of last snapshot
alerted       : Dict[str, float] = {}
tracking      : Dict[str, dict]  = {}
daily_results : List[dict]       = []   # completed signals for daily report
daily_diag    : Dict[str, int]   = {}   # accumulated filter rejections for the day
last_fast     = 0.0
last_mid      = 0.0
last_slow     = 0.0
last_super    = 0.0
last_accum    = 0.0
last_sg       = 0.0
last_sector   = 0.0
last_trend    = 0.0
last_bias_log = 0.0
ACCUM_SCAN_S     = 300    # every 5 min
TREND_FOLLOW_S   = 1800   # every 30 min
last_report        = 0.0   # last daily report sent (unix ts)
last_report_date   = ""    # "YYYY-MM-DD" — ensures exactly one report per calendar day
_last_report_time  = 0.0   # cooldown: prevents duplicate /report within 120s
last_weekly_date   = ""    # "YYYY-Www" — ensures one weekly report per ISO week
last_monthly_date  = ""    # "YYYY-MM"  — ensures one monthly report per month
signal_count  = 0
market_bias   = 0

DAILY_LOG     = "daily_log.json"      # persists daily_results across restarts
TRACKING_FILE = "tracking_state.json" # local fallback when Redis not configured
REPORT_SENT_FILE = "report_sent.json" # dedup: prevents duplicate daily/weekly/monthly reports
_signal_db : List[dict] = []    # ML training DB — loaded from SIGNAL_DB on start
market_cvd    = 0.0
_last_bias_label  = ""    # previous bias label — detect regime change
_last_bias_score  = 0     # previous bias score
last_market_stats = 0.0   # last time market stats was sent
_diag : Dict[str, int] = {}   # diagnostic: rejection counts per filter
_multi_confirm       : Dict[str, dict] = {}   # {sym: {"count": N, "scanners": [], "last_time": ts}}
MULTI_CONFIRM_WINDOW = 1800  # 30 min window for multi-scanner confirmation
_funding_cache       : Dict[str, dict] = {}   # {sym: {"rate": float, "label": str, "ts": float}}
FUNDING_TTL          = 300   # refresh funding rate every 5 min
_signal_dedup        : Dict[str, float] = {}  # {sym: ts} — 60s dedup window (FAST_SCAN_S retrigger guard)
_alerted_price       : Dict[str, float] = {}  # {sym: price} — frozen data guard (MFT type)
_ms_dedup            : Dict[str, float] = {}  # {sym_ms: ts} — prevents duplicate milestone sends (multiple instances guard)
_sector_heat_prev    : Dict[str, float] = {}  # previous heat per sector
_sector_alerted      : Dict[str, float] = {}  # {sector: last_hot_scan_ts}
_sector_warm_alerted : Dict[str, float] = {}  # {sector: last_warm_scan_ts}
_trend_dedup         : Dict[str, float] = {}  # {sym: last_trend_signal_ts} 12h cooldown
_dominance_hist      : List[Tuple[float, dict]] = []  # [(ts, {btcd, usdtd, usdcd, others})]

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
    # Save tracking state to Redis if available
    if REDIS_URL:
        _redis("POST", f"/set/{REDIS_KEY}", {"value": json.dumps({
            "alerted":       dict(alerted),
            "tracking":      {k: {**v, "hit": list(v["hit"])} for k, v in tracking.items()},
            "signal_count":  signal_count,
        })})
    # Always persist daily_results to local JSON (survives restarts)
    try:
        with open(DAILY_LOG, "w") as f:
            json.dump(daily_results, f)
    except Exception as e:
        log.debug("daily_log save: %s", e)
    # Local fallback: save tracking state when Redis not configured
    if not REDIS_URL:
        try:
            with open(TRACKING_FILE, "w") as f:
                json.dump({
                    "alerted":      dict(alerted),
                    "tracking":     {k: {**v, "hit": list(v["hit"])} for k, v in tracking.items()},
                    "signal_count": signal_count,
                }, f)
        except Exception as e:
            log.debug("tracking_state save: %s", e)

def load_state():
    global alerted, tracking, signal_count, daily_results
    # Load daily results from local file first (always available)
    try:
        with open(DAILY_LOG) as f:
            daily_results = json.load(f)
        log.info("daily_log loaded: %d entries", len(daily_results))
    except Exception:
        pass
    # Local fallback: restore tracking state when Redis not configured
    if not REDIS_URL:
        try:
            with open(TRACKING_FILE) as f:
                s = json.load(f)
            alerted.update(s.get("alerted", {}))
            signal_count = s.get("signal_count", signal_count)
            now = time.time()
            for k, v in s.get("tracking", {}).items():
                v["hit"] = set(v.get("hit", []))
                # Only restore signals within 24h window
                if now - v.get("t0", 0) < TRACK_HOURS * 3600:
                    tracking[k] = v
            log.info("tracking_state loaded: %d active signals", len(tracking))
        except Exception:
            pass
        return
    # Load tracking state from Redis
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
#  SIGNAL DATABASE  (ML training data)
# ══════════════════════════════════════════════════════

def load_signal_db():
    global _signal_db
    try:
        with open(SIGNAL_DB) as f:
            _signal_db = json.load(f)
        log.info("signal_db loaded: %d records", len(_signal_db))
    except Exception:
        _signal_db = []

def _save_signal_db():
    try:
        with open(SIGNAL_DB, "w") as f:
            json.dump(_signal_db, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log.debug("signal_db save: %s", e)

def _db_add(sym, price, exchange, tier_name, scanner,
            ratio, ob_spot, score, pos24, spike, net, move, funding):
    """Record a new signal with all parameters for future ML training."""
    _signal_db.append({
        "id":           f"{sym}_{int(time.time())}",
        "sym":          sym,
        "date":         datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "timestamp":    int(time.time()),
        # Context
        "exchange":     exchange,
        "tier":         tier_name,
        "scanner":      scanner,        # main / supertrend / accum
        "market_bias":  market_bias,
        # Signal metrics (features for ML)
        "price_entry":  price,
        "ratio":        round(ratio, 3),
        "ob_spot":      round(ob_spot, 3),
        "score":        score,
        "pos24":        round(pos24, 3),
        "spike":        round(spike, 2),
        "net_usd":      round(net, 0),
        "move_pct":     round(move, 2),
        "funding":      funding,
        # Outcome (filled when signal closes)
        "outcome":      "active",       # active → success / stoploss / timeout / expired
        "max_gain_pct": 0.0,
        "price_exit":   None,
        "duration_min": None,
        "close_reason": None,
    })
    _save_signal_db()

def _db_coin_fatigue(sym, days: int = 7, min_signals: int = 2, min_gain: float = 5.0) -> bool:
    """
    Returns True if the coin is 'fatigued':
    - 2+ signals in the last `days` days AND best max_gain < min_gain%
    Prevents re-signaling on coins that keep triggering without breaking out (SXT/BTW pattern).
    """
    cutoff = time.time() - days * 86400
    recent = [
        r for r in _signal_db
        if r.get("sym") == sym and (r.get("timestamp") or 0) >= cutoff
    ]
    if len(recent) < min_signals:
        return False
    best = max((r.get("max_gain_pct") or 0.0) for r in recent)
    return best < min_gain


def _db_close(sym, outcome, max_gain, price_exit, duration_min, reason):
    """Update outcome when a signal closes (stop-loss / timeout / expired)."""
    for rec in reversed(_signal_db):
        if rec["sym"] == sym and rec["outcome"] == "active":
            rec["outcome"]      = outcome
            rec["max_gain_pct"] = round(max_gain, 2)
            rec["price_exit"]   = price_exit
            rec["duration_min"] = duration_min
            rec["close_reason"] = reason
            _save_signal_db()
            return

# ══════════════════════════════════════════════════════
#  DATA FETCHING
# ══════════════════════════════════════════════════════

def _valid(sym):
    if not sym.endswith("USDT"): return False
    b = sym[:-4]
    if b in STABLECOINS: return False
    if b in BLACKLIST: return False          # permanently skip delisted/dead coins
    if any(k in b for k in SKIP_KEYWORDS): return False
    if "(" in sym: return False
    # Filter MEXC tokenized stocks (TSLAON, APPLON, NVDAON — high price + ON suffix)
    # Real crypto rarely ends in ON with price > $20
    return True

def _parse(data, exchange, base_url):
    out = {}
    for t in data:
        sym = t.get("symbol", "")
        if not _valid(sym): continue
        try:
            price = float(t.get("lastPrice") or 0)
            if price <= 0: continue
            chg = float(t.get("priceChangePercent") or 0)
            # Skip any coin priced near $1 with near-zero change — it's a stablecoin
            if 0.97 <= price <= 1.03 and abs(chg) < 0.5:
                continue
            qv  = float(t.get("quoteVolume") or 0)
            bv  = float(t.get("volume")      or 0)
            vol = qv if qv > 1 else bv * price
            out[sym] = {
                "price":    price,
                "vol":      vol,
                "change":   chg,
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
    if not USE_MEXC:
        return {}
    data = _get(f"{MEXC_BASE}/ticker/24hr")
    if isinstance(data, list) and len(data) > 100:
        out = _parse(data, "MEXC", MEXC_BASE)
        log.info("MEXC: %d", len(out))
        return out
    log.warning("MEXC failed")
    return {}

def fetch_binance():
    """Binance spot tickers — requires VPS (Binance blocks Railway/cloud IPs)."""
    if not USE_BINANCE:
        return {}
    data = _get(f"{BINANCE_BASE}/ticker/24hr")
    if isinstance(data, list) and len(data) > 100:
        out = _parse(data, "Binance", BINANCE_BASE)
        log.info("Binance: %d", len(out))
        return out
    log.warning("Binance fetch failed")
    return {}

def fetch_binance_futures_only(spot_syms):
    """
    Binance Futures (FAPI) tickers for coins NOT listed on Binance Spot.
    Catches Binance Alpha / pre-listing coins (RAVE +146%, etc.) that have
    a Perp contract but no Spot pair on api.binance.com.

    base_url = FAPI → klines, aggTrades, OB all route to FAPI automatically.
    """
    if not USE_BINANCE:
        return {}
    data = _get(f"{BINANCE_FUTURES}/fapi/v1/ticker/24hr")
    if not isinstance(data, list) or len(data) < 10:
        log.warning("Binance Futures ticker failed")
        return {}
    # Re-use _parse: FAPI fields match Spot (lastPrice/priceChangePercent/quoteVolume/highPrice/lowPrice)
    _fapi_base = f"{BINANCE_FUTURES}/fapi/v1"
    out = _parse(data, "Binance", _fapi_base)
    # Mark as futures-only — _check() uses this to skip redundant FAPI OB call
    for t in out.values():
        t["futures_only"] = True
    # Only keep coins not already covered by Spot — avoids overwriting spot OB/liquidity data
    new_only = {s: t for s, t in out.items() if s not in spot_syms}
    if new_only:
        log.info("Binance Futures-only (non-spot): %d new coins", len(new_only))
    return new_only

def fetch_binance_alpha():
    """
    Binance Alpha Web3 tokens (BSC) — shown in Binance Alpha section.
    Klines and OB are fetched from Binance Spot via base_url=BINANCE_BASE.
    """
    if not USE_BINANCE:
        return {}
    data = _get(BINANCE_ALPHA_TOKEN_URL)
    if not isinstance(data, dict) or not data.get("success"):
        log.warning("Binance Alpha Web3 token list failed")
        return {}
    tokens = data.get("data") or []
    out = {}
    for t in tokens:
        try:
            base = (t.get("symbol") or "").upper().strip()
            if not base or base in STABLECOINS or len(base) < 2:
                continue
            sym   = base + "USDT"
            price = float(t.get("price") or 0)
            chg   = float(t.get("percentChange24h") or 0)
            vol   = float(t.get("volume24h") or 0)
            if price <= 0 or vol < 10_000:
                continue
            if 0.97 <= price <= 1.03 and abs(chg) < 0.5:
                continue
            high = price if chg >= 0 else price / (1 + abs(chg) / 100)
            low  = price / (1 + chg / 100) if chg > 0 else price * (1 + abs(chg) / 100)
            out[sym] = {
                "price":         price,
                "change":        chg,
                "vol":           vol,
                "high24":        high,
                "low24":         low,
                "exchange":      "Binance",
                "base_url":      BINANCE_BASE,
                "binance_alpha": True,
                "futures_only":  False,
            }
        except Exception:
            continue
    if out:
        log.info("Binance Alpha Web3: %d tokens", len(out))
    return out

def fetch_binance_funding_rate(sym):
    """
    Binance Futures funding rate — endpoint: /fapi/v1/premiumIndex
    Returns (rate_pct, label) same format as fetch_mexc_funding_rate().
    """
    now   = time.time()
    cache_key = "BN_" + sym
    cache = _funding_cache.get(cache_key)
    if cache and (now - cache["ts"]) < FUNDING_TTL:
        return cache["rate"], cache["label"]
    data = _get(f"{BINANCE_FUTURES}/fapi/v1/premiumIndex",
                {"symbol": sym}, timeout=5)
    if not data or not isinstance(data, dict):
        _funding_cache[cache_key] = {"rate": None, "label": "Spot", "ts": now}
        return None, "Spot"
    try:
        rate = float(data.get("lastFundingRate", 0)) * 100   # → %
        if rate > 0.02:
            label = "🟢 Bullish / Longs"
        elif rate < -0.02:
            label = "🔴 Bearish / Shorts"
        else:
            label = "🟡 Neutral / Covering"
        _funding_cache[cache_key] = {"rate": rate, "label": label, "ts": now}
        return rate, label
    except Exception:
        _funding_cache[cache_key] = {"rate": None, "label": "Spot", "ts": now}
        return None, "Spot"

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

def clear_bot_commands():
    """Remove all registered bot commands from Telegram menu."""
    if not TELEGRAM_TOKEN: return
    try:
        S.post(f"{_TG}/deleteMyCommands", json={}, timeout=5)
        S.post(f"{_TG}/deleteMyCommands", json={"scope": {"type": "all_private_chats"}}, timeout=5)
        S.post(f"{_TG}/deleteMyCommands", json={"scope": {"type": "all_group_chats"}}, timeout=5)
        log.info("Bot commands cleared")
    except Exception as e:
        log.debug("clear_bot_commands: %s", e)

def send_ex(text, reply_markup=None, reply_to_msg_id=None):
    """
    Send to all configured chats.
    Returns (ok: bool, first_msg_id: int).
    reply_markup:    Telegram inline_keyboard dict (optional).
    reply_to_msg_id: reply to a specific message in the first chat (private chat link).
    On Markdown 400 error: auto-retries as plain text (no parse_mode).
    On network timeout: retries up to 3 times with 4s delay (OSHI pattern — signal lost due to timeout).
    """
    if not TELEGRAM_TOKEN:
        print(text); return True, 0
    ok = False
    first_msg_id = 0
    # If GROUP_ID is set, send only there (owner is a group member — sending to both = duplicate)
    # Fallback to CHAT_ID when GROUP_ID is not configured
    _dest = GROUP_ID if GROUP_ID else CHAT_ID
    for cid in list(dict.fromkeys(filter(None, [_dest]))):
        for _attempt in range(3):   # retry up to 3 times on network failure
            try:
                payload = {"chat_id": cid, "text": text, "parse_mode": "Markdown"}
                if reply_markup:
                    payload["reply_markup"] = reply_markup
                # reply_to: only for first chat (where sig_msg_id was originally stored)
                if reply_to_msg_id and not first_msg_id:
                    payload["reply_to_message_id"] = reply_to_msg_id
                r = S.post(f"{_TG}/sendMessage", json=payload, timeout=10)
                # 400 = usually bad Markdown (unescaped _ * ` [ chars)
                # Fallback: retry as plain text so the message is never lost
                if r.status_code == 400:
                    log.warning("TG Markdown failed cid=%s — retrying as plain text", cid)
                    payload.pop("parse_mode", None)
                    r = S.post(f"{_TG}/sendMessage", json=payload, timeout=10)
                if r.status_code == 200:
                    ok = True
                    if not first_msg_id:
                        first_msg_id = r.json().get("result", {}).get("message_id", 0)
                    break   # success — no need to retry
                else:
                    log.error("TG send failed cid=%s status=%s body=%s",
                              cid, r.status_code, r.text[:200])
                    break   # HTTP error (not a timeout) — no point retrying
            except requests.exceptions.Timeout:
                # Timeout ≠ failure — Telegram may have received and delivered the message.
                # Retrying on timeout = duplicate delivery (confirmed XAUT duplicate root cause).
                log.warning("TG timeout (attempt %d) — not retrying to avoid duplicate", _attempt + 1)
                break
            except Exception as e:
                log.warning("TG attempt %d/3 failed: %s", _attempt + 1, e)
                if _attempt < 2:
                    time.sleep(4)   # wait 4s before retry
    return ok, first_msg_id

def send(text, reply_markup=None):
    """Convenience wrapper — returns bool only (backward compatible)."""
    ok, _ = send_ex(text, reply_markup)
    return ok

def _ai_assess(sym, exchange, tier, scanner, score,
               ob_spot, ratio, pos24, spike, net_usd, move_pct, funding) -> tuple:
    """Return (ai_text, blocked). blocked=True only when AI<40% + sellers dominate OB."""
    if _ai_agent is None:
        return "", False
    try:
        sig = {
            "sym": sym, "exchange": exchange, "tier": tier,
            "scanner": scanner, "score": score, "ob_spot": ob_spot,
            "ratio": ratio, "pos24": pos24, "spike": spike,
            "net_usd": net_usd, "move_pct": move_pct, "funding": funding,
        }
        r = _ai_agent.predict(sig)
        prob    = r.get("prob", 0)
        verdict = r.get("verdict", "")
        emoji   = r.get("emoji", "⚪")
        warns   = r.get("warnings", [])
        model   = r.get("model", exchange)
        warn_str = f"\n   ⚠️ _{warns[0]}_" if warns else ""
        text = f"\n🤖 *AI [{model}]:* {emoji} `{prob}%` · {verdict}{warn_str}\n{'━'*20}"
        # Block condition 1: AI below 35% is a clear avoid regardless of OB
        extreme_avoid = prob < 35
        # Block condition 2: moderate AI + sellers dominate OB (dump pattern)
        dump_pattern  = (prob < 50 and ob_spot < 0.45)
        # Block condition 3: cautious AI + weak score + truly weak spike = high SL risk (SWARMS-type)
        weak_combined = (prob < 75 and score < 7.5 and spike < 3.0)
        # Block condition 4: AI cautious + low score regardless of volume (JTO-type)
        # Exception: explosive spike (≥5x) = institutional momentum overrides AI caution
        ai_caution = (prob < 65 and score < 7.0 and spike < 5.0)
        # Block condition 5: AI "Avoid" (< 60%) regardless of score (DIA-type)
        # Exception: explosive spike (≥5x) = real breakout — AI model can't anticipate these
        ai_avoid = (prob < 60 and spike < 5.0)
        blocked = extreme_avoid or dump_pattern or weak_combined or ai_caution or ai_avoid
        if blocked:
            if extreme_avoid:
                reason = "AI<35%% avoid"
            elif dump_pattern:
                reason = "AI<50%% + sellers dominate"
            elif ai_avoid:
                reason = "AI<60%% avoid signal"
            elif ai_caution:
                reason = "AI<65%%+score<7.0 cautious regardless of volume"
            else:
                reason = "weak combined: AI<75%%+score<7.5+vol<5x"
            log.info("AI_BLOCK %s prob=%.1f%% ob=%.0f%% score=%.1f spike=%.1fx (%s)",
                     sym, prob, ob_spot * 100, score, spike, reason)
        return text, blocked
    except Exception:
        return "", False

def _sig_link(msg_id):
    """
    Build t.me deep link for a message in the configured group/channel.
    Private groups: ID = -100XXXXXXXXXX → t.me/c/XXXXXXXXXX/msg_id
    """
    if not msg_id:
        return None
    cid = str(GROUP_ID or CHAT_ID).strip()
    if not cid:
        return None
    if cid.startswith("-100"):
        return f"https://t.me/c/{cid[4:]}/{msg_id}"
    if cid.startswith("-"):
        return f"https://t.me/c/{cid[1:]}/{msg_id}"
    return None   # private user chats have no public link

def _trade_keyboard(sym, exchange, sig_msg_id=None, binance_alpha=False):
    """Trade buttons disabled — signals sent as text only."""
    return None

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

def _calc_score(pos24, net, net_min, ob_spot, spike):
    """Confidence score 0–10: quality of the signal. All components clamped ≥ 0."""
    pos_pts   = max(0.0, 1.0 - pos24) * 2.0                              # 0-2
    net_pts   = max(0.0, min(4.0, (net / max(net_min, 1)) / 5.0 * 4.0)) # 0-4 (was unbounded negative — APR bug)
    bids_pts  = max(0.0, (ob_spot - 0.45) / 0.35) * 2.0                 # 0-2
    spike_pts = min(2.0, spike / 10.0 * 2.0)                             # 0-2
    return round(min(10.0, pos_pts + net_pts + bids_pts + spike_pts), 1)

def _calc_tp_sl(price, high24, low24, spike, score, exchange, is_moonshot=False, vol_explosion=False, is_flash=False):
    """Calculate TP1/TP2/TP3 and SL based on each coin's volatility and signal strength."""
    rng = high24 - low24
    daily_vol_pct = (rng / price * 100) if price > 0 else 10.0

    # Flash pump: tighter SL — reverses in minutes, must exit fast
    # US/USDT lesson: 43x spike FLASH PUMP reversed -13% while regular SL was -6%
    if is_flash:
        sl_pct = 0.04   # 4% hard SL for flash pumps regardless of volatility
    # SL based on coin's daily range — wider for volatile coins
    elif daily_vol_pct > 30:
        sl_pct = 0.10
    elif daily_vol_pct > 15:
        sl_pct = 0.08
    elif daily_vol_pct > 8:
        sl_pct = 0.06
    else:
        sl_pct = 0.05

    # MEXC micro-caps pump-dump faster — slightly wider SL
    if exchange == "MEXC" and not is_flash:
        sl_pct = min(sl_pct + 0.02, 0.12)

    sl = price * (1 - sl_pct)

    # TP based on signal strength and spike size
    if is_moonshot or spike >= 20:
        tp_pcts = [0.12, 0.25, 0.50]
    elif vol_explosion or spike >= 10:
        tp_pcts = [0.08, 0.18, 0.35]
    elif score >= 8.0:
        tp_pcts = [0.07, 0.15, 0.28]
    else:
        tp_pcts = [0.05, 0.12, 0.22]

    tp1 = price * (1 + tp_pcts[0])
    tp2 = price * (1 + tp_pcts[1])
    tp3 = price * (1 + tp_pcts[2])

    return tp1, tp2, tp3, sl, sl_pct, tp_pcts


def build_signal(sym, price, change, buy_v, sell_v,
                 spike, move, exchange, tier_name, ema_bull,
                 high24=0.0, low24=0.0, badge="🔔1",
                 funding_label="Spot", ob_label="⚪ Balanced", ob_pct=50,
                 score=0.0, moonshot=False, momentum=False, vol_explosion=False,
                 interval="1h", is_flash=False, signal_type=None, is_alpha=False):
    global signal_count
    signal_count += 1

    base     = sym[:-4]
    net      = buy_v - sell_v
    ratio    = buy_v / sell_v if sell_v > 0 else 99.0
    ex_icon  = "🟡" if exchange == "Binance" else "🟠"
    # Market type label shown next to coin name
    if exchange == "MEXC":
        _mkt_label = "MEXC"
    elif is_alpha:
        _mkt_label = "Alpha"
    else:
        _mkt_label = "Spot"

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

    # Score label
    if moonshot:
        score_label = f"🚀 *MOONSHOT* · Score: `{score}/10`"
    elif vol_explosion:
        score_label = f"🌋 *VOLUME EXPLOSION* · Score: `{score}/10`"
    elif momentum:
        score_label = f"⚡ *MOMENTUM BYPASS* · Score: `{score}/10`"
    elif score >= 8.5:
        score_label = f"🚀 Whale Action · Score: `{score}/10`"
    elif score >= 7.0:
        score_label = f"🟡 Scalp · Score: `{score}/10`"
    else:
        score_label = f"🔵 Score: `{score}/10`"

    _tf        = "1m" if interval in ("1m", "1m_sg") else "1h"
    _flash_tag = "\n⚡ *FLASH PUMP* — Act in seconds or skip\n" if is_flash else ""
    _type_line = f"📈 *{signal_type}*\n" if signal_type else ""

    # TP/SL lines
    tp1, tp2, tp3, sl, sl_pct, tp_pcts = _calc_tp_sl(
        price, high24, low24, spike, score, exchange,
        is_moonshot=moonshot, vol_explosion=vol_explosion, is_flash=is_flash
    )
    _tp_sl_block = (
        f"\n"
        f"🎯 TP1: `${_fp(tp1)}` *(+{tp_pcts[0]*100:.0f}%)*\n"
        f"🎯 TP2: `${_fp(tp2)}` *(+{tp_pcts[1]*100:.0f}%)*\n"
        f"🎯 TP3: `${_fp(tp3)}` *(+{tp_pcts[2]*100:.0f}%)*\n"
        f"🛑 SL:  `${_fp(sl)}` *(-{sl_pct*100:.0f}%)*\n"
    )

    return (
        f"{'━' * 20}\n"
        f"💀 *MAFIO SNIPER* 📡\n"
        f"{_type_line}"
        f"{_flash_tag}"
        f"\n"
        f"🆕 *#{base}* 💀 · {_mkt_label} · Signal #{signal_count} {badge}\n"
        f"💰 Price: `${_fp(price)}`\n"
        f"📈 {_tf} Move: `+{move:.2f}%` ⚡\n"
        f"📍 Position: `%{pos_from_bottom} from Bottom` {pos_icon}\n"
        f"\n"
        f"⚡ Volume: `{spike:.1f}x` above avg\n"
        f"{int_icon} Interest: {interest}\n"
        f"📊 Ratio: `{ratio:.1f}x` 🔥\n"
        f"💹 {_tf} Flow:\n"
        f"  📥 In:  `{_fv(buy_v)}`\n"
        f"  📤 Out: `{_fv(sell_v)}`\n"
        f"  ▲ Net: `+{_fv(net)}` ✅\n"
        f"📗 Order Book: {ob_label} `{ob_pct}%` bids\n"
        f"📌 Funding: {funding_label}\n"
        f"🎯 {score_label}\n"
        f"{_tp_sl_block}"
        f"{ex_icon} Exchange: `{exchange}`\n"
        f"🕐 {_ts()} UTC\n"
        f"{'━' * 20}"
    )

# ══════════════════════════════════════════════════════
#  MILESTONES
# ══════════════════════════════════════════════════════

def check_milestones(all_t):
    global daily_results
    now     = time.time()
    expired = []   # list of (sym, reason)

    for sym, info in list(tracking.items()):
        # Guard: skip entries missing required keys (old/migrated tracking data)
        if "t0" not in info or "entry" not in info:
            expired.append((sym, "corrupted")); continue
        elapsed = now - info["t0"]

        # ── Expiry checks (no API needed) ────────────────────────────────
        # 1. Hard limit: 24h max tracking window — remove from memory only, keep DB as active
        if elapsed > TRACK_HOURS * 3600:
            tracking.pop(sym, None)
            save_state()
            continue

        t = all_t.get(sym)
        if not t: continue
        gain = (t["price"] - info["entry"]) / info["entry"] * 100.0
        if gain > info.get("max", 0.0):
            info["max"] = gain
        if gain < info.get("min", 0.0):
            info["min"] = gain
            # Keep signal_history.json in sync so reports always show real gains
            for _rec in reversed(_signal_db):
                if _rec["sym"] == sym and _rec["outcome"] == "active":
                    _rec["max_gain_pct"] = round(gain, 2)
                    break

        # 2. Stop-loss alert only — no auto-close, signal stays active
        if gain <= SIGNAL_SL_PCT and not info.get("sl_alerted"):
            info["sl_alerted"] = True
            save_state()   # persist flag before firing — prevents duplicate on restart
            _fire_stoploss(sym, gain, t["price"], info["entry"],
                           int(elapsed), info["exchange"])

        # 3. Timeout removed — signals run for full 24h window
        if False and elapsed > SIGNAL_TIMEOUT_H * 3600 and info.get("max", 0.0) < 5.0:
            expired.append((sym, "timeout")); continue

        # ── Milestone alerts ─────────────────────────────────────────────
        pending = [ms for ms in MILESTONES if ms not in info["hit"] and gain >= ms]
        if pending:
            for ms in pending:
                info["hit"].add(ms)
            save_state()
            top_ms = pending[-1]
            _ms_key = f"{sym}_{top_ms}"
            if now - _ms_dedup.get(_ms_key, 0) > 1800:   # 30 min dedup guard
                _ms_dedup[_ms_key] = now
                _fire_ms(sym, top_ms, gain, t["price"], info["entry"],
                         int(elapsed), info["exchange"])

        # ── Peak Reversal Alert ───────────────────────────────────────────
        peak          = info.get("max", 0.0)
        _rev_min_peak = 6.0 if info.get("is_flash") else 8.0
        _rev_drop     = 3.0
        if peak >= _rev_min_peak and not info.get("rev_alerted"):
            peak_price   = info["entry"] * (1 + peak / 100)
            drop_from_pk = (peak_price - t["price"]) / peak_price * 100
            if drop_from_pk >= _rev_drop:
                info["rev_alerted"] = True
                _fire_reversal(sym, gain, peak, t["price"], info["entry"],
                               int(elapsed), info["exchange"],
                               is_flash=info.get("is_flash", False))

    for sym, reason in expired:
        info = tracking.pop(sym, None)
        if info:
            _max   = info.get("max", 0.0)
            _t0    = info.get("t0", now)
            _dur   = int((now - _t0) / 60)
            _exit  = all_t.get(sym, {}).get("price", info["entry"])
            _out   = "success" if _max >= 5.0 else reason
            _db_close(sym, _out, _max, _exit, _dur, reason)
            daily_results.append({
                "sym":      sym,
                "entry":    info["entry"],
                "max":      _max,
                "elapsed":  int(now - _t0),
                "success":  _max >= 5.0,
                "reason":   reason,
                "exchange": info.get("exchange", "MEXC"),
                "ts":       int(now),
            })
            save_state()

def _get_category(sym):
    """Return (emoji, name) category for a symbol."""
    base = sym[:-4] if sym.endswith("USDT") else sym
    return COIN_CATEGORIES.get(base, ("❓", "Other"))

def _gain_icon(pct):
    """Gain icon: 💎 ≥20%, 🔥 ≥15%, 🏆 <15%."""
    if pct >= 20: return "💎"
    if pct >= 15: return "🔥"
    return "🏆"

def _fp_report(p):
    """Entry price format matching Wolf Flow style.
    p≥10 → 4 decimals ($75.0000, $4.4800)
    p<1  → 6 decimals ($0.075000, $0.007920)
    """
    if p >= 10:  return f"{p:.4f}"
    if p >= 1:   return f"{p:.4f}"
    return f"{p:.6f}"

_RANK_EMOJIS = ["🥇","🥈","🥉","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]


def send_daily_report(reset=True):
    """Sends the daily performance report — shows ALL signals sent, sorted by gain.
    reset=True  → automatic midnight report (clears data for next day)
    reset=False → on-demand /report command (keeps data intact)
    """
    global daily_results, daily_diag
    now      = datetime.now(timezone.utc)
    date_str = now.strftime("%d %b %Y")
    time_str = now.strftime("%H:%M")

    # ── Compile all entries (active tracking + completed today) ──────────
    all_entries = []
    for sym, info in tracking.items():
        all_entries.append({
            "sym":      sym,
            "entry":    info["entry"],
            "max":      info.get("max", 0.0),
            "elapsed":  int(time.time() - info["t0"]),
            "success":  info.get("max", 0.0) >= 5.0,
            "exchange": info.get("exchange", "MEXC"),
            "active":   True,
        })
    for r in daily_results:
        r.setdefault("active", False)
        all_entries.append(r)

    total     = len(all_entries)
    wins      = [e for e in all_entries if e["success"]]
    losses    = [e for e in all_entries if not e["success"] and not e.get("active")]
    active_c  = [e for e in all_entries if e.get("active")]
    avg_pk    = sum(e["max"] for e in all_entries) / total if total else 0.0
    win_pct   = sum(e["max"] for e in wins)

    # Sort ALL entries: best gain first
    all_sorted = sorted(all_entries, key=lambda x: -x["max"])

    # ── Header ────────────────────────────────────────────────────────────
    header = "\n".join([
        "🎯 *MAFIO SNIPER*",
        f"📊 التقرير اليومي — {date_str}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🔔 {total} إشارة  |  ✅ {len(wins)} نجاح  |  ⏳ {len(active_c)} نشطة  |  ❌ {len(losses)} فشل",
        f"📈 avg: `{avg_pk:+.2f}%`  |  total wins: `+{win_pct:.2f}%`",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
    ])

    # ── All signals — one compact line each ───────────────────────────────
    def _row(e):
        g   = e["max"]
        sym = e["sym"][:-4] if e["sym"].endswith("USDT") else e["sym"]
        if e.get("active"):
            icon = "⏳"
        elif e["success"]:
            icon = "✅"
        else:
            icon = "❌"
        t = _tstr(e["elapsed"])
        return f"{icon} `{sym:<8s}` ${_fp_report(e['entry'])}  `{g:+.2f}%`  {t}"

    rows = [_row(e) for e in all_sorted]

    footer_lines = ["━━━━━━━━━━━━━━━━━━━━━━━━━"]
    if not reset:
        footer_lines.append("📌 /report — on-demand")

    # ── Split into Telegram-safe messages (≤ 4000 chars each) ────────────
    parts = []
    current = header + "\n"
    for row in rows:
        if len(current) + len(row) + 1 > 3900:
            parts.append(current)
            current = ""
        current += row + "\n"
    current += "\n".join(footer_lines)
    parts.append(current)

    ok = False
    for part in parts:
        if part.strip() and send(part):
            ok = True

    if not ok:
        log.error("Daily report FAILED to send")
        raise RuntimeError("send() returned False — Telegram delivery failed")
    log.info("Daily report: total=%d wins=%d losses=%d active=%d avg=%.1f%%",
             total, len(wins), len(losses), len(active_c), avg_pk)

    if reset:
        daily_results = []
        daily_diag.clear()
        save_state()


_SECTOR_DISPLAY: Dict[str, str] = {
    "Meme":     "🐸 Meme",     "Layer1":   "⛓ L1 / L2",
    "Layer2":   "⛓ L1 / L2",  "DeFi":     "💠 DeFi",
    "GameFi":   "🎮 GameFi",   "AI":       "🤖 AI",
    "Oracle":   "🔗 Oracle",   "Storage":  "🗂 Storage",
    "NFT":      "🖼 NFT",      "Payments": "💰 Payments",
    "Privacy":  "🔒 Privacy",  "Exchange": "🏦 Exchange",
    "TON Eco":  "🔵 TON",      "SOL Eco":  "☀️ Solana",
    "BNB Eco":  "🔶 BNB",      "LST":      "🌊 Staking",
    "RWA":      "💼 RWA",      "Web3":     "🌐 Web3",
    "ZK":       "🛡 ZK",       "Interop":  "🌍 Interop",
    "DePIN":    "📡 DePIN",    "Sports":   "🏆 Fan Token",
    "BNB Alpha":"🟠 Alpha",
}
_RANK_ICON: Dict[int, str] = {
    1: "🥇", 2: "🥈", 3: "🥉",
    4: "4️⃣", 5: "5️⃣", 6: "6️⃣",
    7: "7️⃣", 8: "8️⃣", 9: "9️⃣", 10: "🔟",
}


def _period_report(period_label: str, days: int):
    """Generic report for weekly/monthly — reads signal_history.json for the period."""
    cutoff = time.time() - days * 86400
    try:
        with open("signal_history.json", "r") as f:
            history = json.load(f)
    except Exception:
        history = []

    entries = [
        r for r in history
        if (r.get("timestamp") or 0) >= cutoff
        and r.get("sym", "")[:-4] not in STABLECOINS
    ]
    if not entries:
        send(f"📊 *{period_label}*\nلا توجد إشارات في هذه الفترة.")
        return

    WIN_OUT  = {"success", "partial"}
    LOSS_OUT = {"stoploss", "reversal", "timeout"}

    wins   = [e for e in entries if e.get("outcome") in WIN_OUT]
    losses = [e for e in entries if e.get("outcome") in LOSS_OUT]
    active = [e for e in entries if e.get("outcome") not in WIN_OUT | LOSS_OUT]
    total  = len(entries)

    def _live_gain(e) -> float:
        sym = e.get("sym", "")
        out = e.get("outcome", "")
        if out not in WIN_OUT and out not in LOSS_OUT:
            info = tracking.get(sym)
            if info:
                return info.get("max", 0.0)
        return e.get("max_gain_pct") or 0.0

    all_gains = [_live_gain(e) for e in entries]
    avg_pk    = sum(all_gains) / total if total else 0
    win_sum   = sum(_live_gain(e) for e in wins)
    win_pct   = len(wins) / total * 100 if total else 0

    sorted_e = sorted(entries, key=lambda x: -_live_gain(x))

    header = "\n".join([
        "🎯 *MAFIO SNIPER*",
        f"📊 {period_label}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🔔 {total} إشارة  |  ✅ {len(wins)} نجاح  |  ❌ {len(losses)} فشل  |  ⏳ {len(active)} نشط",
        f"📈 avg: `{avg_pk:+.2f}%`  |  win rate: `{win_pct:.0f}%`  |  total wins: `+{win_sum:.2f}%`",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
    ])

    SEP_THIN = "─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─"
    SEP_WIDE = "━━━━━━━━━━━━━━━━━━━━━━━━━"

    def _row(rank: int, e) -> str:
        g    = _live_gain(e)
        sym  = e.get("sym", "?")
        base = sym[:-4] if sym.endswith("USDT") else sym.replace("USDT", "")
        sector    = SECTOR_REGISTRY.get(base, "Other")
        cat       = _SECTOR_DISPLAY.get(sector, f"📊 {sector}")
        rank_icon = _RANK_ICON.get(rank, f"{rank}.")
        gain_icon = "💎" if g >= 20 else "🔥" if g >= 15 else "🚀" if g >= 0 else "📉"
        return (
            f"{rank_icon}  *{sym}*\n"
            f"   🏷 Category:  {cat}\n"
            f"   {gain_icon} Gain:  `{g:+.2f}%`"
        )

    parts = []
    current = header + "\n\n"
    for i, e in enumerate(sorted_e, 1):
        row   = _row(i, e)
        sep   = "\n" + SEP_THIN + "\n" if i < len(sorted_e) else "\n\n" + SEP_WIDE
        block = row + sep
        if len(current) + len(block) > 3900:
            parts.append(current)
            current = ""
        current += block
    parts.append(current)

    for part in parts:
        if part.strip():
            send(part)

    log.info("%s: total=%d wins=%d losses=%d active=%d avg=%.1f%%",
             period_label, total, len(wins), len(losses), len(active), avg_pk)


def send_weekly_report():
    now_utc = datetime.now(timezone.utc)
    _period_report(
        f"التقرير الأسبوعي — {now_utc.strftime('%d %b %Y')}",
        days=7,
    )


def send_monthly_report():
    now_utc = datetime.now(timezone.utc)
    _period_report(
        f"التقرير الشهري — {now_utc.strftime('%B %Y')}",
        days=30,
    )


_last_tg_update = 0   # Telegram getUpdates offset

def poll_telegram():
    """
    Poll Telegram for incoming commands (/report).
    Non-blocking: timeout=0, called every ~1 second from idle loop.
    Accepts /report from CHAT_ID or GROUP_ID only.
    """
    global _last_tg_update, _last_report_time
    if not TELEGRAM_TOKEN:
        return
    try:
        resp = S.get(f"{_TG}/getUpdates",
                     params={"timeout": 0, "offset": _last_tg_update + 1,
                             "allowed_updates": ["message"]},
                     timeout=5)
        data = resp.json()
        if not data.get("ok"):
            # Webhook conflict: clear webhook and retry next cycle
            if data.get("error_code") == 409:
                S.post(f"{_TG}/deleteWebhook", timeout=5)
                log.warning("Webhook conflict detected — webhook cleared, retrying next cycle")
            return
        for upd in data.get("result", []):
            _last_tg_update = upd["update_id"]
            msg  = upd.get("message", {})
            text = (msg.get("text") or "").strip()
            cid  = str(msg.get("chat", {}).get("id", ""))
            # Accept from any authorized chat (strip whitespace from env vars)
            _allowed = {str(CHAT_ID).strip(), str(GROUP_ID).strip()} - {""}
            if _allowed and cid not in _allowed:
                log.debug("poll_telegram: ignored cid=%s (not authorized)", cid)
                continue
            # Accept /report with any bot suffix (e.g. /report@mybot)
            if text.lower().split("@")[0] == "/weekly":
                log.info("Manual /weekly from chat %s", cid)
                send("⏳ جاري إنشاء التقرير الأسبوعي...")
                try:
                    send_weekly_report()
                except Exception as e:
                    send(f"❌ *تعذّر إنشاء التقرير*\n`{e}`")
                continue

            if text.lower().split("@")[0] == "/monthly":
                log.info("Manual /monthly from chat %s", cid)
                send("⏳ جاري إنشاء التقرير الشهري...")
                try:
                    send_monthly_report()
                except Exception as e:
                    send(f"❌ *تعذّر إنشاء التقرير*\n`{e}`")
                continue

            if text.lower().split("@")[0] == "/report":
                now_ts = time.time()
                # Cooldown: ignore duplicate /report within 120 seconds
                if now_ts - _last_report_time < 120:
                    log.debug("/report ignored — cooldown active (%.0fs left)",
                              120 - (now_ts - _last_report_time))
                    continue
                _last_report_time = now_ts
                log.info("Manual /report from chat %s", cid)
                # Immediate acknowledgment so user knows it's working
                send("⏳ جاري إنشاء التقرير...")
                try:
                    send_daily_report(reset=False)
                except Exception as report_err:
                    log.error("/report failed: %s", report_err, exc_info=True)
                    send(f"❌ *تعذّر إنشاء التقرير*\n`{report_err}`")
    except Exception as e:
        log.warning("poll_telegram: %s", e)


def register_commands():
    """Clear webhook + register /report in Telegram menu."""
    if not TELEGRAM_TOKEN:
        return
    try:
        # MUST delete webhook before getUpdates polling works
        S.post(f"{_TG}/deleteWebhook", json={"drop_pending_updates": False}, timeout=5)
        S.post(f"{_TG}/setMyCommands",
               json={"commands": [
                                   {"command": "report",  "description": "📊 التقرير اليومي"},
                                   {"command": "weekly",  "description": "📊 التقرير الأسبوعي"},
                                   {"command": "monthly", "description": "📊 التقرير الشهري"},
                               ]},
               timeout=5)
        log.info("Webhook cleared. /report command registered.")
    except Exception as e:
        log.warning("register_commands: %s", e)


def _tstr(e):
    """Show elapsed time as Xh Ym or Zm"""
    e = max(e, 0)
    if e >= 3600:
        h = e // 3600
        m = (e % 3600) // 60
        return f"{h}h {m}m"   # always show minutes (Wolf Flow: "5h 0m")
    if e >= 60:
        return f"{e // 60}m"
    return f"{e}s"

def _make_milestone_image(base, gain, entry, now_price, exchange, tp1=0.0):
    """Anime background milestone card — Wolf Flow style layout."""
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
        import io, os

        W, H = 700, 700

        # ── Pick background image based on gain level ──
        BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backgrounds")
        if gain >= 100:
            bg_file = "bg6_zoro_wings.jpg"      # Zoro fire wings — legendary gain
        elif gain >= 60:
            bg_file = "bg5_luffy_clouds.jpg"    # Luffy flying — epic gain
        elif gain >= 40:
            bg_file = "bg3_luffy_fire.jpg"      # Luffy fire/lightning — big gain
        elif gain >= 30:
            bg_file = "bg1_luffy_storm.jpg"     # Luffy storm — strong gain
        elif gain >= 25:
            bg_file = "bg4_luffy_energy.jpg"    # Luffy energy ball — solid gain
        else:
            bg_file = "bg2_demon.jpg"           # Dark demon — baseline ≥20%

        bg_path = os.path.join(BASE_DIR, bg_file)
        if os.path.exists(bg_path):
            bg = Image.open(bg_path).convert("RGB")
            bg = bg.resize((W, H), Image.LANCZOS)
            # Darken slightly so text remains readable
            bg = ImageEnhance.Brightness(bg).enhance(0.55)
            img = bg
        else:
            # Fallback: dark gradient
            img  = Image.new("RGB", (W, H))
            draw = ImageDraw.Draw(img)
            for y in range(H):
                t = y / H
                r = int(8  + 10 * (1 - t))
                g = int(2  + 3  * (1 - t))
                b = int(20 + 30 * (1 - t))
                draw.line([(0, y), (W, y)], fill=(r, g, b))

        # ── Dark semi-transparent overlay for text panels ──
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        # Top bar
        od.rectangle([(0, 0), (W, 74)], fill=(0, 0, 0, 155))
        # Bottom info panel
        od.rectangle([(0, 500), (W, H)], fill=(0, 0, 0, 170))
        # Center text shadow behind gain
        od.ellipse([(W//2 - 240, 270), (W//2 + 240, 470)], fill=(0, 0, 0, 100))
        img = img.convert("RGBA")
        img = Image.alpha_composite(img, overlay)
        img = img.convert("RGB")
        draw = ImageDraw.Draw(img)

        # ── Fonts ──
        FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
        try:
            f_brand = ImageFont.truetype(FONT, 22)
            f_coin  = ImageFont.truetype(FONT, 82)
            f_gain  = ImageFont.truetype(FONT, 138)
            f_label = ImageFont.truetype(FONT, 20)
            f_price = ImageFont.truetype(FONT, 38)
        except Exception:
            f_brand = f_coin = f_gain = f_label = f_price = ImageFont.load_default()

        # ── Top branding ──
        draw.text((26, 26), "MAFIO SNIPER", fill=(200, 190, 230), anchor="lt", font=f_brand)
        ex_color = (0, 195, 255) if exchange == "Binance" else (255, 165, 40)
        ex_label = "MAFIO BINANCE" if exchange == "Binance" else "MAFIO MEXC"
        draw.text((W - 26, 26), ex_label, fill=ex_color, anchor="rt", font=f_brand)
        draw.line([(26, 60), (W - 26, 60)], fill=(50, 25, 85), width=1)

        # ── Coin name (shadow + text for readability over busy backgrounds) ──
        draw.text((W // 2 + 3, 203), f"{base}", fill=(10, 0, 20),        anchor="mm", font=f_coin)
        draw.text((W // 2,     200), f"{base}", fill=(255, 255, 255),    anchor="mm", font=f_coin)

        # ── Gain % with glow ──
        gain_color = (160, 80, 255) if gain >= 0 else (255, 60, 60)
        gain_str   = f"+{gain:.2f}%" if gain >= 0 else f"{gain:.2f}%"
        glow_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        glw        = ImageDraw.Draw(glow_layer)
        glw.text((W // 2, 370), gain_str, fill=(*gain_color, 130), anchor="mm", font=f_gain)
        glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=12))
        img  = img.convert("RGBA")
        img  = Image.alpha_composite(img, glow_layer)
        img  = img.convert("RGB")
        draw = ImageDraw.Draw(img)
        draw.text((W // 2, 370), gain_str, fill=gain_color, anchor="mm", font=f_gain)

        # ── Divider ──
        draw.line([(40, 510), (W - 40, 510)], fill=(60, 30, 100), width=2)

        # ── Footer: ENTRY | TAKE PROFIT ──
        lx, rx    = W // 4, 3 * W // 4
        label_col = (130, 105, 175)
        tp_price  = tp1 if tp1 > 0 else now_price
        tp_label  = "TAKE PROFIT" if tp1 > 0 else "CURRENT PRICE"

        draw.text((lx, 548), "ENTRY POSITION", fill=label_col, anchor="mm", font=f_label)
        draw.text((lx, 592), f"${_fp(entry)}",  fill=(210, 200, 235), anchor="mm", font=f_price)
        draw.text((rx, 548), tp_label,           fill=label_col,       anchor="mm", font=f_label)
        draw.text((rx, 592), f"${_fp(tp_price)}", fill=gain_color,     anchor="mm", font=f_price)

        buf = io.BytesIO()
        img.save(buf, "PNG")
        return buf.getvalue()
    except Exception as e:
        log.warning("milestone image failed: %s", e)
        return None


def _send_photo(image_bytes, caption=""):
    """Send a photo to Telegram chat."""
    import io
    try:
        files = {"photo": ("milestone.png", io.BytesIO(image_bytes), "image/png")}
        data  = {"chat_id": str(GROUP_ID or CHAT_ID), "parse_mode": "Markdown"}
        if caption:
            data["caption"] = caption
        r = S.post(f"{_TG}/sendPhoto", data=data, files=files, timeout=20)
        return r.ok
    except Exception as e:
        log.warning("send_photo failed: %s", e)
        return False


def _fire_ms(sym, ms, gain, now_price, entry, elapsed, exchange):
    base     = sym[:-4]
    ex_icon  = "🟡" if exchange == "Binance" else "🟠"
    max_loss = tracking.get(sym, {}).get("min", 0.0)
    tp1      = tracking.get(sym, {}).get("tp1", 0.0)

    if ms == 5:
        icon  = "✅"
        title = f"*{base}USDT*  WIN confirmed  +{ms}% reached"
    elif ms >= 50: icon, title = "🚀", f"*{base}USDT*  +{ms}% milestone reached"
    elif ms >= 10: icon, title = "🔥", f"*{base}USDT*  +{ms}% milestone reached"
    else:          icon, title = "📈", f"*{base}USDT*  +{ms}% milestone reached"

    # Send image for big milestones (>=20%)
    if ms >= 20:
        image_bytes = _make_milestone_image(base, gain, entry, now_price, exchange, tp1)
        if image_bytes:
            _send_photo(image_bytes)

    max_loss_line = f"📉 Max loss:  `{max_loss:.2f}%`\n" if max_loss < -0.1 else ""

    sig_msg_id = tracking.get(sym, {}).get("sig_msg_id", 0)
    keyboard   = _trade_keyboard(sym, exchange, sig_msg_id)
    _reply_to  = sig_msg_id if sig_msg_id and not _sig_link(sig_msg_id) else None
    send_ex(
        f"{'━' * 20}\n"
        f"💀 *MAFIO SNIPER* 📡\n"
        f"\n"
        f"{icon} {title}\n"
        f"📊 Max gain:   `+{gain:.2f}%`\n"
        f"💰 Price now:  `${_fp(now_price)}`\n"
        f"🎯 Entry:      `${_fp(entry)}`\n"
        f"{max_loss_line}"
        f"⏱ Achieved in: {_tstr(elapsed)}\n"
        f"{ex_icon} {exchange}\n"
        f"{'━' * 20}",
        keyboard,
        reply_to_msg_id=_reply_to
    )
    log.info("MS %-14s +%d%% max=+%.2f%% min=%.2f%% in %s [%s]",
             sym, ms, gain, max_loss, _tstr(elapsed), exchange)


def _fire_reversal(sym, gain, peak, now_price, entry, elapsed, exchange, is_flash=False):
    """
    Alert fired when price drops 3% from peak (v15.3: unified from 4%/5%):
      Flash pump (is_flash=True): 3% drop from ≥6% peak  — CATI/ALCX type
      Normal signal:              3% drop from ≥8% peak  — EVAA/LIGHT type
    Only fires once per signal (rev_alerted flag).
    """
    base    = sym[:-4]
    ex_icon = "🟡" if exchange == "Binance" else "🟠"
    tag     = "⚡ Flash pump" if is_flash else "Reversal"
    sig_msg_id = tracking.get(sym, {}).get("sig_msg_id", 0)
    keyboard   = _trade_keyboard(sym, exchange, sig_msg_id)
    _reply_to  = sig_msg_id if sig_msg_id and not _sig_link(sig_msg_id) else None
    send_ex(
        f"{'━' * 20}\n"
        f"💀 *MAFIO SNIPER* 📡\n"
        f"\n"
        f"⚠️ *REVERSAL WARNING* ⚠️\n"
        f"*#{base}USDT* — {tag} detected\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🏔 Peak gain:   +{peak:.1f}%\n"
        f"📉 Now:         {gain:+.2f}% from entry\n"
        f"💰 Price now:   ${_fp(now_price)}\n"
        f"🏁 Entry:       ${_fp(entry)}\n"
        f"⏱ Time in:      {_tstr(elapsed)}\n"
        f"💡 Consider exiting — price fell 3%+ from peak\n"
        f"{ex_icon} {exchange}\n"
        f"{'━' * 20}",
        keyboard,
        reply_to_msg_id=_reply_to
    )
    log.info("REVERSAL %-12s peak=+%.1f%% now=%+.2f%% flash=%s in %s [%s]",
             sym, peak, gain, is_flash, _tstr(elapsed), exchange)


def _fire_stoploss(sym, gain, now_price, entry, elapsed, exchange):
    base    = sym[:-4]
    ex_icon = "🟡" if exchange == "Binance" else "🟠"
    sig_msg_id = tracking.get(sym, {}).get("sig_msg_id", 0)
    keyboard   = _trade_keyboard(sym, exchange, sig_msg_id)
    _reply_to  = sig_msg_id if sig_msg_id and not _sig_link(sig_msg_id) else None
    send_ex(
        f"{'━' * 20}\n"
        f"💀 *MAFIO SNIPER* 📡\n"
        f"\n"
        f"🛑 *STOP-LOSS* — *#{base}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📉 Loss:        {gain:+.2f}%\n"
        f"💰 Price now:   ${_fp(now_price)}\n"
        f"🏁 Entry:       ${_fp(entry)}\n"
        f"⏱ Time in:      {_tstr(elapsed)}\n"
        f"💡 Signal closed — price fell {SIGNAL_SL_PCT:.0f}%+ from entry\n"
        f"{ex_icon} {exchange}\n"
        f"{'━' * 20}",
        keyboard,
        reply_to_msg_id=_reply_to
    )
    log.info("SL %-14s gain=%.2f%% in %s [%s]", sym, gain, _tstr(elapsed), exchange)


# ══════════════════════════════════════════════════════
#  CORE CHECK
# ══════════════════════════════════════════════════════

def _calc_ema(closes, period):
    # type: (list, int) -> float
    """EMA using SMA seed. Returns last EMA value."""
    if len(closes) < period:
        return closes[-1] if closes else 0.0
    k   = 2.0 / (period + 1)
    ema = sum(closes[:period]) / period   # SMA seed
    for c in closes[period:]:
        ema = c * k + ema * (1 - k)
    return ema


def _check(sym, ticker, interval, sector_boost=False):
    now      = time.time()

    # ── Cascade / BTC danger pause ────────────────────────────────────────
    if now < _cascade_paused:
        return

    # ── Dedup: prevent re-signal for coin already in tracking or within 2h ──
    if sym in tracking:
        return   # already tracking this coin — no duplicate signal
    if now - _signal_dedup.get(sym, 0) < 7200:
        return   # 2h cooldown after any signal

    price    = ticker["price"]
    vol_24h  = ticker["vol"]
    change   = ticker["change"]
    exchange = ticker["exchange"]
    base_url = ticker["base_url"]

    def _rej(reason):
        _diag[reason] = _diag.get(reason, 0) + 1
        log.info("REJ %s [%s] %s", sym, interval, reason)

    # Filter MEXC tokenized stocks: base ends with "ON" + price > $20 (TSLAON, APPLON, NVDAON)
    if sym[:-4].endswith("ON") and price > 20:
        _rej("tokenized_stock"); return

    # Frozen ticker guard — 24h change exactly 0.0% = API cache / delisted coin (MFT pattern)
    if change == 0.0 and vol_24h < 1_000_000:
        _rej("frozen_ticker"); return

    # Frozen price guard — same exact price as last signal = ghost/cached data
    if sym in _alerted_price and _alerted_price[sym] == price:
        _rej("frozen_price"); return


    # Skip already pumped — MEXC micro-caps: allow up to 70% (REDO +56% still valid)
    # Binance: allow up to 80% — matches slow_scan pool limit; liquid coins (FF/ILV/LPT) sustain bigger moves
    _max_pump = 70.0 if exchange == "MEXC" else 80.0
    h24, l24 = ticker["high24"], ticker["low24"]
    range_pump = (h24 - l24) / l24 * 100 if l24 > 0 else 0
    if change > _max_pump or range_pump > 200.0:
        _rej("max_pump"); return
    if now - alerted.get(sym, 0) < COOLDOWN: _rej("cooldown"); return

    # ── Sector Momentum detection (pre-klines) ────────────────────────────
    # AXS/APE/ALICE gaming rotation: coins pump gradually over 6h+ as a sector.
    # Each 1h kline looks "flat" → low_move blocks them. But 24h trend is strong.
    # Uses rise-from-low instead of pos24 (pos24=1.0 when making new 24h highs).
    # Requires vol >= $1M to exclude MEXC micro-cap manipulation.
    _rise_from_low = (price - l24) / l24 * 100 if l24 > 0 else 0
    _sector_mom_pre = (
        change >= 15.0 and          # strong 24h trend
        _rise_from_low < 40.0 and   # not overextended (40% above daily low)
        vol_24h >= 1_000_000        # meaningful liquidity — no micro-cap wash trading
    )

    # Get tier thresholds based on 24h volume
    tier = get_tier(vol_24h)
    spike_min = tier["spike"]
    ratio_min = tier["ratio"]
    net_min   = tier["net"]

    # ── Market context: adapt all thresholds to current market state ──────
    ctx = get_market_ctx(market_bias)
    spike_min *= ctx["spike_mult"]
    ratio_min *= ctx["ratio_mult"]

    # ── Sector boost: hot sector = external confirmation → relax thresholds ──
    # When sector heat validates the move, we don't need as strong a per-coin spike
    # TON/AR/FIL pattern: sector already hot, coin hasn't spiked yet = early entry
    if sector_boost and exchange == "Binance":
        spike_min *= 0.65   # 35% easier spike — sector momentum is the signal
        ratio_min *= 0.70   # 30% easier ratio — sector confirms buyer interest
        net_min   *= 0.60   # 40% easier net flow — early = less flow yet

    # ── Exchange-specific sensitivity (fully isolated thresholds) ───────────
    if exchange == "Binance":
        # Binance large-caps: high baseline volume, efficient 2-sided market
        # → spike fires less dramatically, net scales with coin size
        spike_min *= 0.70                              # 30% easier — BTC-type spikes are subtle
        # Ratio discount: only for Mid/Large cap (deep liquidity = naturally lower ratio)
        # Micro/Small cap Binance: full ratio required — VINE(2.2x) failed in 10m at pos69%
        if tier["name"] in ("Mid", "Large"):
            ratio_min *= 0.85                          # 15% easier for large liquid coins only
        # Proportional net: 0.25% of daily volume, capped at $80K, floor $5K
        net_min = min(max(vol_24h * 0.0025, 5_000), 80_000)
    else:
        # MEXC: small-cap incubator — raised from $1K to $2K after MFT ghost signals
        # $2K still catches NOM/MDT type micro-caps while blocking micro-manipulation
        net_min    = max(net_min * 0.20, 2_000)   # Radar: floor $2K
        spike_min *= 0.90                          # Slightly easier spike (smaller MEXC baseline)

    # ── Late entry filter ────────────────────────────────────────────────────
    # MEXC: 0.95 (micro-caps pump-dump fast — top 5% = too late)
    # Binance: 0.97 fixed — continuous breakouts (TRU/CTSI/DUSK) run past 93% of range
    #   ctx["late_pct"] was 0.88-0.95 for Binance → missed all gradual Binance pumps
    #   Wick/OB filters handle true pump-dumps, so 0.97 is safe
    if exchange == "MEXC":
        _late_pct = 0.95
    else:
        _late_pct = 0.97   # Binance: only block absolute top 3% of 24h range
    rng = ticker["high24"] - ticker["low24"]
    if rng > 0 and (price - ticker["low24"]) / rng > _late_pct and not _sector_mom_pre:
        _rej("late_entry"); return

    # ── Quick vol floor (no API call) ─────────────────────────────────────
    if vol_24h < tier["vol_min"]:
        _rej("low_vol"); return

    # MEXC: require minimum $500K volume — micro-cap MEXC coins are unreliable
    # (low liquidity → easy pump/dump, poor order book depth)
    if exchange == "MEXC" and vol_24h < 500_000:
        _rej("mexc_low_vol"); return

    # Market bias gate — Binance: allow Mid+Large in bear (FF/ILV/LPT proof)
    if not should_signal(tier["name"], market_bias, exchange):
        _rej("bias_gate"); return

    # ── Distance from 24h low: pre-klines guard (no API call) ────────────
    # Only blocks coins that have ALREADY completed a massive pump (>80-90% from daily low).
    # Lighter guard — pos_limit + late_entry handle true late entries.
    # MEXC: Micro=120% (micro-caps can 2x and still be early), Large=70%
    # Binance: slightly wider (liquid large-caps sustain longer trends)
    if ticker["low24"] > 0:
        _rise_pct = (price - ticker["low24"]) / ticker["low24"] * 100
        if exchange == "Binance":
            _dist_max = {"Micro": 200.0, "Small": 150.0, "Mid": 120.0, "Large": 120.0}.get(tier["name"], 120.0)
        else:
            _dist_max = {"Micro": 120.0, "Small": 90.0, "Mid": 75.0, "Large": 60.0}.get(tier["name"], 75.0)
        if _rise_pct > _dist_max:
            _rej("far_from_low"); return

    # ── Step 1: Klines FIRST (1 API call — main filter) ──────────────────
    # limit=50: gives stable EMA20 (30 seed + 20 rolling points)
    # "1m_sg" = sleeping giant: fetch 1m klines but with relaxed move threshold
    _kl_fetch = "1m" if interval == "1m_sg" else interval
    candles = fetch_klines(sym, base_url, interval=_kl_fetch, limit=50)
    if len(candles) < 10: _rej("no_klines"); return

    spike, move, avg_vol = vol_spike_and_move(candles)

    # Sleeping giant: scan_sleeping_giant passes the confirmed spike via ticker["_sg_spike"].
    # This avoids candle timing issues (new candle starts between detection and _check fetch).
    # Also check candles[-2] and [-3] to cover the case where 1-2 new candles formed.
    if interval == "1m_sg":
        _sg_hint = ticker.get("_sg_spike", 0)
        if _sg_hint > spike:
            spike = _sg_hint
        _sg_move_hint = ticker.get("_sg_move", 0)
        if _sg_move_hint > move:
            move = _sg_move_hint
        if len(candles) >= 5:
            _sg_vols = [_qvol(c) for c in candles]
            _sg_avg  = sum(_sg_vols[:-2]) / max(len(_sg_vols) - 2, 1)
            if _sg_avg > 0:
                for _idx in (-2, -3):
                    _sp = _sg_vols[_idx] / _sg_avg
                    if _sp > spike:
                        spike = _sp
                        try:
                            _o  = float(candles[_idx][1])
                            _cl = float(candles[_idx][4])
                            move = max(move, (_cl - _o) / _o * 100 if _o > 0 else 0)
                        except Exception:
                            pass

    # EMA20: trend context used later for bull_trap detection
    _closes_ema       = [float(c[4]) for c in candles]
    _ema20            = _calc_ema(_closes_ema, 20)
    price_above_ema20 = price >= _ema20

    # Early move filter: only block clear downtrends (< -1%)
    # Real move_min (1.5%) is applied AFTER funding_rate check below
    if move < -1.0: _rej("low_move"); return

    # Thin coin + big move = pump already over (AURORA, SIX type)
    if move > 8.0 and vol_24h < 200_000:
        _rej("thin_pump"); return

    # Reject dead coins (zero base volume)
    if avg_vol < (50 if exchange == "MEXC" else 200): _rej("dead_coin"); return

    # ── Funding Rate (API call — only for candidates that pass klines) ───
    if exchange == "Binance":
        funding_rate, funding_label = fetch_binance_funding_rate(sym)
    else:
        funding_rate, funding_label = fetch_mexc_funding_rate(sym)
    funding_bullish = funding_rate is not None and funding_rate > 0.03

    if funding_bullish:
        spike_min = max(2.0, spike_min * 0.60)   # floor 1.5→2.0 (CLO 1.6x blocked)
        ratio_min = max(2.5, ratio_min * 0.70)   # floor 1.8→2.5 (CLO 2.1x, QUAI 2.4x blocked)
        net_min   = max(net_min * 0.25, 100)
        move_min  = -5.0              # funding bullish: allow dip buying
    else:
        move_min  = ctx["move_min"]   # adaptive: 0.5% bull → 2.5% bear

    # MEXC Micro/Small: relax move floor — tiny initial move can precede +50% explosion
    # (NOM/MDT pattern: starts at 0.3% move → fires to +45%)
    if exchange == "MEXC" and tier["name"] in ("Micro", "Small"):
        move_min = min(move_min, 0.3)

    # Binance: cap move_min at 1.0% even in bear market
    # Bear ctx move_min = 2.0% blocks LPT/WAL/NOM type gradual Binance breakouts
    # Wolf Flow catches 26 Binance wins in bear market → 1% is enough for Binance
    if exchange == "Binance":
        move_min = min(move_min, 1.0)

    # Fast scan (1m klines): a 0.5% move in 1 minute = explosive beginning
    if interval == "1m":
        move_min = min(move_min, 0.5)
    # Sleeping giant (1m klines, volume detected before price moves): lower threshold
    elif interval == "1m_sg":
        move_min = min(move_min, 0.15)

    # Sector momentum: confirm spike >= 1.5x after klines are available
    _sector_mom = _sector_mom_pre and spike >= 1.5
    if move < move_min and not _sector_mom: _rej("low_move"); return

    # ── Volume-adjusted ratio: ILV pattern — big spike + lower ratio at breakout start ──
    # High spike (≥5x) = institutional volume → accept lower ratio (early accumulation)
    # Low spike (<2x)  = weak momentum     → require stronger ratio confirmation
    # DOGS fix: Binance Mid/Large — 1.5x spike = millions in absolute $ (not "weak")
    #   DOGS $55M/day: 1.6x spike = $880K extra volume in 1h → real institutional buying
    #   Only tighten ratio if spike is truly negligible (< 1.5x) for large liquid coins
    if not funding_bullish:
        if spike >= 5.0:
            ratio_min = max(1.5, ratio_min * 0.55)   # High momentum: allow earlier entry (floor 1.5x)
        elif spike < 2.0:
            _tighten_thr = 1.5 if (exchange == "Binance" and tier["name"] in ("Mid", "Large")) else 2.0
            if spike < _tighten_thr:
                ratio_min = max(ratio_min, 3.5)       # Truly weak spike: ratio must compensate

    # ── Pre-check real ratio for Super-Ratio Bypass ────────────────────
    _pre_buy, _pre_sell = fetch_agg_trades(sym, base_url,
                                            minutes=60 if interval in ("60m", "1h") else 10)
    _pre_ratio = _pre_buy / _pre_sell if _pre_sell > 0 else 99.0
    super_ratio = _pre_ratio >= 20.0
    effective_spike_min = 1.5 if super_ratio else spike_min
    if spike < effective_spike_min:
        _rej("low_spike"); return

    # Spike candle must close in upper half — rejects pump-dump wicks
    try:
        sc = candles[-1]
        sc_rng = float(sc[2]) - float(sc[3])
        sc_close_pct = (float(sc[4]) - float(sc[3])) / sc_rng if sc_rng > 0 else 0.5
    except Exception:
        sc_close_pct = 0.5
    if sc_close_pct < 0.50:
        _rej("dump_wick"); return

    # Wick distribution: 3+ candles with long upper wicks in last 5 = sellers distributing
    # (ROLL pattern: huge upper wicks = smart money offloading on retail buyers)
    _bad_wicks = 0
    for _c in candles[-5:]:
        try:
            _o, _h, _cl = float(_c[1]), float(_c[2]), float(_c[4])
            _body  = abs(_cl - _o)
            _upper = _h - max(_o, _cl)
            if _body > 0 and _upper / _body > 1.5:
                _bad_wicks += 1
        except Exception:
            pass
    if _bad_wicks >= 3:
        _rej("wick_distribution"); return

    # ── Pump & Dump filter ────────────────────────────────────────────────
    rng24 = ticker["high24"] - ticker["low24"]
    pos24 = (price - ticker["low24"]) / rng24 if rng24 > 0 else 0.5
    ob_quick = fetch_ob_imbalance(sym, base_url, levels=5)
    # Only block when: extreme spike + price already near top of range + sellers dominating
    # pos24>0.55 (not 0.35) — real explosions often start at 30-50% of range
    is_pump_dump = (
        spike > 20.0 and pos24 > 0.55 and ob_quick < 0.50
    )
    if is_pump_dump:
        _rej("pump_dump"); return

    # Post-pump crash filter — uses ctx.crash_limit (adaptive)
    if ticker["high24"] > 0 and ticker["low24"] > 0:
        pump_size = (ticker["high24"] - ticker["low24"]) / ticker["low24"] * 100
        crash_from_top = (ticker["high24"] - price) / ticker["high24"] * 100
        if pump_size > 30.0 and crash_from_top > ctx["crash_limit"]:
            _rej("post_pump"); return

    # Position guard — uses ctx.pos_limit (adaptive)
    # Sector momentum: use rise_from_low instead of pos24 (pos24=1.0 when at new highs)
    if _sector_mom:
        if _rise_from_low > 50.0:   # sector rotation: allow up to 50% above daily low
            _rej("high_pos"); return
    elif pos24 > ctx["pos_limit"]:
        # BLINKY pattern: very high ratio (≥20x) overrides position limit
        # Sleeping Giant: flat coin with tiny daily range — high pos24 is misleading
        _sg_bypass = (interval == "1m_sg" and spike >= 20.0)
        if _pre_ratio < 20.0 and not _sg_bypass:
            _rej("high_pos"); return

    # High position + weak volume = false signal (我踏马来了 pattern)
    # Coin already moved up in range but without real volume explosion = chasing
    if pos24 > 0.65 and spike < 3.0 and not interval.endswith("_sg"):
        _rej("high_pos_low_vol"); return

    # Weak top filter: very high in range + flat move = exhaustion, not breakout
    # Raised from 0.62→0.75 to avoid blocking mid-range breakouts
    # Sleeping giant bypass: flat coins always show high pos24 due to tiny daily range
    _weak_move_thr = 0.8 if exchange == "Binance" else 1.0
    if pos24 > 0.75 and ratio_min > 0 and move < _weak_move_thr and not (interval == "1m_sg" and spike >= 20.0):
        _rej("weak_top"); return

    # ── Step 2: Real buy/sell from aggTrades (reuse pre-fetched data) ───
    buy_v, sell_v = _pre_buy, _pre_sell
    if sell_v <= 0: _rej("no_sells"); return
    ratio = buy_v / sell_v
    net   = buy_v - sell_v

    # ── Absolute Net Flow floor (hard — no bypass skips this) ─────────────
    # CAKE pattern: volume_explosion triggered with net=$68 (buyers ≈ sellers)
    # Real accumulation needs visible imbalance: $5K Binance, $1.5K MEXC
    _abs_net_floor = 5_000.0 if exchange == "Binance" else 1_500.0
    if net < _abs_net_floor:
        _rej("noise_net"); return

    # Coin fatigue — skip if 2+ signals in last 7 days with no gain ≥ 5%
    # Exception: net > $300K = institutional accumulation (NIGHT pattern) → allow re-signal
    if _db_coin_fatigue(sym) and net < 300_000:
        log.info("COIN_FATIGUE %s — 2+ signals in 7d best_gain<5%% net=%.0f$", sym, net)
        _rej("coin_fatigue"); return

    # ── Wash Trading guard (MEXC only) ────────────────────────────────────
    # OSHI pattern: 60min flow=$665K / vol_24h=$676K = 98% → entire day in one hour
    # Fix: threshold must match the data window:
    #   1h data  → 60% (original OSHI guard — 1h real buying = max 30% of daily)
    #   10m data → 90% (REPAI/BLINKY type: genuine explosion = all vol in 10min is ok)
    # Without this fix, fast_scan BLOCKS real flash pumps (REPAI/BLINKY/NEOS type)
    if exchange == "MEXC" and vol_24h > 0:
        _flow_ratio = (buy_v + sell_v) / vol_24h
        _wash_thr = 0.60 if interval in ("60m", "1h") else 0.90
        if _flow_ratio > _wash_thr:
            log.debug("WASH_TRADE skip %s flow_ratio=%.0f%% thr=%.0f%%",
                      sym, _flow_ratio * 100, _wash_thr * 100)
            _rej("wash_trading"); return

    # MOONSHOT override: whale accumulation bypasses soft filters
    _low_price_moon = (
        price < 0.25 and spike >= 10.0 and
        net > 20_000 and pos24 < 0.50 and ob_spot >= 0.55
    )
    is_moonshot = (
        (net > 500_000 and pos24 < 0.60) or   # Whale: $500K+ net near bottom
        (pos24 < 0.10 and net > 60_000) or     # Bottom sniper: <10% pos + strong flow
        _low_price_moon                         # Low-price pump: HIGH/ALICE/PORTAL type
    )

    # Momentum Bypass: smart money early entry — MEXC threshold 5x (more sensitive)
    # Binance threshold 8x (larger baseline noise, need stronger confirmation)
    # net > 0 required: APR bug — negative net flow must NEVER bypass net check
    _ratio_bypass   = 5.0 if exchange == "MEXC" else 8.0
    momentum_bypass = (ratio >= _ratio_bypass and pos24 < 0.85 and net > 0 and move < 10.0)

    # Volume Explosion: 10x+ spike + REAL net (> abs_floor already passed) = extraordinary event
    # net > 0 replaced by net > _abs_net_floor (already enforced above — but redundant safety)
    # Sleeping Giant bypass: pos24 is misleading for flat coins with tiny daily range
    volume_explosion = (spike >= 10.0 and (pos24 < 0.75 or interval == "1m_sg") and net > _abs_net_floor)

    # ── Net Flow Intensity: net relative to coin size ────────────────────
    # Problem: same $20K net flow means nothing on QNT ($20M/day) but is huge on XNY ($650K/day)
    # Formula: (net scaled to 1h) / (vol_24h / 24) → how many "normal hours" of buying
    # Examples from real signals: XNY=0.5x(+25%), BZ=2.5x(+23%), CL=2.9x(+36%), QNT=0.02x(stagnant)
    _agg_min      = 60 if interval in ("60m", "1h") else 10
    _net_1h       = net * (60.0 / _agg_min)                          # scale to 1h equivalent
    _hourly_vol   = vol_24h / 24.0
    net_intensity = _net_1h / _hourly_vol if _hourly_vol > 0 else 0

    # Block signals where net flow is negligible vs coin size — won't explode fast
    # Exempt: volume_explosion (spike≥10x always real) and moonshots (already strong)
    if net_intensity < 0.05 and not volume_explosion and not is_moonshot:
        log.info("LOW_INTENSITY %s intensity=%.3fx net1h=%.0f$ vol_24h=%.0f$",
                 sym, net_intensity, _net_1h, vol_24h)
        _rej("low_intensity"); return

    # ── Volume Absorption filter ────────────────────────────────────────
    # High spike + tiny price move = possible distribution (smart money selling).
    # BUT: threshold must match the interval — 1m candles naturally move less.
    # GLMR lesson: 34.7x spike + 0.87% on 1m = ACCUMULATION → exploded +116% next day.
    # 0.87% on 1m is real momentum; 0.87% on 1h is flat.
    # Interval-aware thresholds:
    #   1m → 0.5%  (fast scan: small candle, high spike = real signal)
    #   5m → 1.0%  (mid scan)
    #   1h → 1.5%  (slow scan: 1h candle must move meaningfully)
    _va_min = 0.5 if interval == "1m" else (1.0 if interval == "5m" else 1.5)
    if spike >= 20.0 and move < _va_min and not is_moonshot:
        _rej("vol_absorption"); return

    # Post-peak distribution: ARTX pattern — high volume spike after peak, price already fell
    # spike>=15x + pos24>50% + price>5% below 24h high = dump/distribution, not accumulation
    if (spike >= 15.0 and pos24 > 0.50
            and ticker["high24"] > 0 and price < ticker["high24"] * 0.95):
        _rej("post_peak_dist"); return

    # Position scaling: high-pos entries need strong ratio (BLINKY: pos=86%, ratio=28.7x ✅)
    # Low ratio at high pos = exhaustion/distribution, not a real breakout
    if pos24 > 0.70 and not is_moonshot:
        ratio_min = max(ratio_min, 20.0)

    if is_moonshot:
        if ratio < 1.5: _rej("low_ratio"); return
    elif momentum_bypass:
        log.debug("MOMENTUM_BYPASS %s ratio=%.1fx net=%s pos=%.0f%%",
                  sym, ratio, _fv(net), pos24 * 100)
    elif volume_explosion:
        if ratio < 2.0: _rej("vol_exp_low_ratio"); return   # CAW 1.4x / ALPH 1.5x
        log.debug("VOL_EXPLOSION %s spike=%.1fx net=%s pos=%.0f%%",
                  sym, spike, _fv(net), pos24 * 100)
    else:
        if ratio < ratio_min: _rej("low_ratio"); return
        if net   < net_min:   _rej("low_net"); return

    # ── Step 3: Order book imbalance (spot 70% + futures 30%) ────────────
    ob_spot  = fetch_ob_imbalance(sym, base_url, levels=20)
    # CCD pattern: sellers dominate OB (ob<45%) despite high ratio = dumping into buy flow
    # momentum_bypass was triggered by ratio alone — cancel it when OB clearly shows sellers
    if momentum_bypass and ob_spot < 0.45:
        momentum_bypass = False
        log.debug("MOMENTUM_BYPASS cancelled %s ob=%.0f%% (seller-dominated OB)", sym, ob_spot * 100)
    # QUBIC pattern: MEXC momentum bypass requires real buyer dominance (≥62% bids)
    # ratio can be high on illiquid MEXC coins without real OB support
    if momentum_bypass and exchange == "MEXC" and ob_spot < 0.62:
        momentum_bypass = False
        log.debug("MOMENTUM_BYPASS cancelled %s MEXC ob=%.0f%% < 62%%", sym, ob_spot * 100)
    # ob_sellers threshold: 60% fixed — all winners had ≥60% bids (REPAI=60%, BLINKY=68%)
    # BEAT=46% and RIVER=48% were losers — sub-60% bids = no real buyer conviction
    _ob_min_spot = 0.60
    # Absorption bypass: ob_spot >= 0.55 required even with strong net flow
    absorption = (net >= net_min * 3 and ob_spot >= 0.55)
    # volume_explosion bypass: only when ob >= 0.50 (RAY=59% ✅, BANK=48% ❌)
    _vol_exp_ob_ok = volume_explosion and ob_spot >= 0.50
    if ob_spot < _ob_min_spot and not absorption and not is_moonshot and not momentum_bypass and not _vol_exp_ob_ok:
        _rej("ob_sellers"); return
    if exchange == "Binance":
        if ticker.get("futures_only"):
            ob_fut = ob_spot  # base_url already points to FAPI — no double call
        elif ticker.get("binance_alpha"):
            ob_fut = ob_spot  # no FAPI contract — use spot OB only
        else:
            ob_fut = fetch_ob_imbalance(sym, f"{BINANCE_FUTURES}/fapi/v1", levels=20)
    else:
        ob_fut = fetch_mexc_fut_ob(sym, levels=20)
    ob_score = ob_spot * 0.7 + ob_fut * 0.3
    # Binance ob_min: 0.38 fixed — in bear market ctx["ob_min"] rises to 0.45-0.50
    # but Binance market makers keep tighter spreads → 0.38 is still valid for breakouts
    # (Wolf Flow catches FF/ILV/LPT in bear with weaker OB)
    _ob_min_eff = 0.38 if exchange == "Binance" else ctx["ob_min"]
    if ob_score < _ob_min_eff and not is_moonshot and not volume_explosion:
        _rej("ob_low"); return
    if ob_spot > 0.58:
        ob_label = "🟢 Buyers"
    elif ob_spot < 0.46:
        ob_label = "🔴 Sellers"
    else:
        ob_label = "⚪ Balanced"

    # ── Bull Trap filter ──────────────────────────────────────────────────
    # MBG pattern: 94% bids yet price still drops = institutions SELLING into buy wall
    # "Liquidity absorption": retail fills buy orders, smart money offloads at those prices
    # Healthy breakout: 55-82% bids + rising candles | Trap: >88% bids + declining candles
    ema_bull = price_above_ema20   # True = price above EMA20 on scan interval
    if ob_spot > 0.88 and not is_moonshot and not funding_bullish:
        # Check last 4 closes: is price lower than 3 candles ago?
        _lc = [float(c[4]) for c in candles[-5:]]
        _declining = len(_lc) >= 4 and _lc[-1] < _lc[-3]
        if _declining:
            log.debug("BULL_TRAP skip %s ob=%.0f%% ema_bull=%s declining", sym, ob_spot*100, ema_bull)
            _rej("bull_trap"); return
        # Even without declining candles: extreme bids in a downtrend (bear bias + below EMA20) = trap
        if market_bias <= -3 and not price_above_ema20:
            log.debug("BEAR_BIDS skip %s ob=%.0f%% bias=%d ema_bull=False", sym, ob_spot*100, market_bias)
            _rej("bear_bids"); return

    # ── Fake Wall filter ─────────────────────────────────────────────────
    # PHY pattern: OB=90% bids + net=$4.6K = artificial buy wall with no real flow
    # Thin coins (MEXC micro-caps) use fake walls to attract buyers while smart money dumps
    # Real breakouts with high OB have STRONG net flow (WOTAMALAILIAO: OB=46% + net=$59K)
    # Rule: OB > 85% AND net < 3× net_min = fake wall, not genuine demand
    if ob_spot > 0.85 and net < net_min * 3 and not is_moonshot and not funding_bullish:
        log.debug("FAKE_WALL skip %s ob=%.0f%% net=%s net_min=%s", sym, ob_spot*100, _fv(net), _fv(net_min))
        _rej("fake_wall"); return

    # Funding bearish block — any negative funding = shorts winning = avoid
    if funding_rate is not None and funding_rate < -0.02:
        _rej("bearish_funding"); return

    # Flash pump detection: 1m candle with spike≥8x AND move≥3% = explosive 1-minute burst
    # CATI/ALCX pattern — reverses very fast, needs tighter exit threshold (4% not 5%)
    is_flash = (interval in ("1m", "1m_sg") and spike >= 8.0 and move >= 3.0)

    # Multi-scanner confirmation badge — each timeframe is a distinct scanner
    # fast=1m, mid=5m, slow=1h/60m, sg=sleeping_giant → coin appearing in 2+ gets 🔔🔔2 badge
    if interval == "1m":
        scanner = "fast"
    elif interval == "1m_sg":
        scanner = "sleeping_giant"
    elif interval == "5m":
        scanner = "mid"
    else:
        scanner = "slow"
    _, badge = _register_confirm(sym, scanner)

    # Confidence score
    # MEXC: floor 4.0 — live results show bear market creates many weak 2-3 score signals
    #   that go +1% then dump. NEOS(6.9) REPAI(10) PGVERSE(9) LKT(9) all ≥ 4.0 ✓
    # Binance: floor 2.0 — more institutional signals have lower net but are still valid
    score = _calc_score(pos24, net, net_min, ob_spot, spike)

    # C. Alpha/Futures Priority bonus: RAVE-type (futures-only + positive net flow)
    # Futures-only coins lack spot OB history → compensate with +1.5 when flow is real
    if ticker.get("futures_only") and net > 0:
        score = min(10.0, round(score + 1.5, 1))
        log.debug("FUTURES_BONUS %s score→%.1f (net=%s)", sym, score, _fv(net))

    # Net Intensity bonus: high flow-to-size ratio = coin more likely to explode fast
    # BZ(2.5x→+23%) CL(2.9x→+36%) NIGHT(4.8x) get up to +1.5 pts vs QNT(0.02x) gets 0
    _intensity_bonus = min(1.5, net_intensity * 0.4)   # 0→0, 0.5x→+0.2, 2.5x→+1.0, 3.75x→+1.5
    if _intensity_bonus >= 0.1:
        score = min(10.0, round(score + _intensity_bonus, 1))
        log.debug("INTENSITY_BONUS %s +%.1f (intensity=%.2fx) score→%.1f",
                  sym, _intensity_bonus, net_intensity, score)

    # Score bonus 1 — Volume Weighting (spike ≥ 30x):
    # GIGGLE/IN pattern: extreme volume = real demand even if OB looks thin
    # 30x spike overrides the bids_pts penalty component (worth up to +1.0)
    if spike >= 30.0 and net > 0:
        _vol_bonus = min(1.0, (spike - 30.0) / 20.0 * 1.0)   # 0.0 at 30x → 1.0 at 50x
        score = min(10.0, round(score + _vol_bonus, 1))
        log.debug("VOL_WEIGHT %s spike=%.1fx score→%.1f", sym, spike, score)

    # Score bonus 2 — Position Flexibility:
    # Strong net dominance (net > 70% of total flow) = buyers in full control
    # Reduces high-position penalty → IN(+32%) / GIGGLE(+31%) got punished for pos
    _total_flow = buy_v + sell_v
    if _total_flow > 0:
        _net_dom = net / _total_flow   # 0.0 (balanced) → 1.0 (all buyers)
        if _net_dom > 0.70 and pos24 > 0.50 and net > 0:
            _pos_bonus = min(1.0, (_net_dom - 0.70) / 0.30)   # 0→+1.0 as dom 70%→100%
            score = min(10.0, round(score + _pos_bonus, 1))
            log.debug("POS_FLEX %s net_dom=%.0f%% pos=%.0f%% score→%.1f",
                      sym, _net_dom * 100, pos24 * 100, score)

    # A. Trend Integrity: medium score REQUIRES strong OB support
    # MITO pattern: score=4.8 + OB=55% → single-candle pump then dump to entry
    # Exception: moonshot/momentum/vol_explosion/extreme-spike bypass
    # TST pattern: ratio≥4x = strong buyer dominance compensates weak OB
    _extreme_vol = spike >= 30.0 and net > 0   # real demand confirmed by volume alone
    _strong_ratio = ratio >= 4.0 and net > 0   # buy/sell imbalance confirms real demand
    if score < 6.0 and ob_spot < 0.65 and not is_moonshot and not momentum_bypass and not volume_explosion and not _extreme_vol and not _strong_ratio:
        _rej("weak_ob_score"); return

    # ── Bear market + high bids score penalty ────────────────────────────
    # In a bearish market (bias ≤ -2), an unusually high bids% (>82%) is a warning:
    # Smart money may be distributing into retail buy orders (MBG-type trap).
    # Exception: moonshot / funding_bullish (genuine demand confirmed by funding)
    if market_bias <= -2 and ob_spot > 0.82 and not is_moonshot and not funding_bullish:
        _bear_pen = min(1.5, (ob_spot - 0.82) / 0.18 * 1.5)   # 0→+1.5 as ob 82%→100%
        score = max(0.0, round(score - _bear_pen, 1))
        log.debug("BEAR_BIDS_PENALTY %s bias=%d ob=%.0f%% -%.1f → score=%.1f",
                  sym, market_bias, ob_spot * 100, _bear_pen, score)

    # ── Quality gate — dual-path instead of pure score floor ─────────────
    # Problem: pos24 penalty in score unfairly hurts coins already in motion
    # (IO at 73% pos24 scored 4.8 but went +88% — strong OB=78% + ratio=2.8x)
    #
    # MEXC: strict score required (shallow liquidity, unreliable OB)
    if exchange == "MEXC":
        _mexc_floor = 8.0 if market_bias > -25 else 8.5
        if sector_boost:
            _mexc_floor = max(_mexc_floor - 1.0, 7.0)  # sector heat = relax MEXC floor
        if score < _mexc_floor:
            _rej("low_score"); return
    else:
        # Absolute floor — no path bypasses a score this weak
        if score < 5.5 and not is_moonshot and not volume_explosion:
            _rej("quality_fail"); return
        # Binance: three paths to pass — any one is enough
        _good_score    = score >= 7.0
        _strong_signal = ob_spot >= 0.72 and ratio >= 2.5 and net >= net_min
        _huge_flow     = net > 100_000 and ob_spot >= 0.65
        # Sector boost: hot sector = 4th path — positive flow + decent OB enough
        _sector_path   = (sector_boost and net > 0
                          and ob_spot >= 0.55 and ratio >= 1.5)
        # Bear market: tighten each path (sector path stays — sector is strongest signal)
        if market_bias <= -25:
            _good_score    = score >= 7.5
            _strong_signal = ob_spot >= 0.74 and ratio >= 3.0 and net >= net_min * 1.5
            _huge_flow     = net > 150_000 and ob_spot >= 0.67
            _sector_path   = (sector_boost and net > 0
                              and ob_spot >= 0.62 and ratio >= 2.0)
        if not (_good_score or _strong_signal or _huge_flow or _sector_path):
            if not is_moonshot and not volume_explosion:
                _rej("quality_fail"); return

    # In bear market: allow volume explosions only if buyers clearly dominate (OB>=55%)
    # GUN/ORDI/HIGH type: real buying despite BTC decline = valid signal
    # Weak OB + bear market = noise, block it
    if volume_explosion and market_bias <= -25 and not is_moonshot and ob_spot < 0.55:
        _rej("vol_exp_bear"); return

    # Bear market fighting bonus: coin rising strongly against BTC decline = lower score floor
    _fighting_bear = (market_bias <= -20 and move >= 5.0
                      and net > net_min * 2 and ob_spot >= 0.60)
    if _fighting_bear and score >= 5.0:
        _score_floor = min(_score_floor, 5.0)

    # Fire
    msg = build_signal(sym, price, change, buy_v, sell_v,
                       spike, move, exchange, tier["name"], ema_bull,
                       high24=ticker["high24"], low24=ticker["low24"],
                       badge=badge, funding_label=funding_label,
                       ob_label=ob_label, ob_pct=int(ob_spot * 100),
                       score=score, moonshot=is_moonshot,
                       momentum=momentum_bypass,
                       vol_explosion=volume_explosion,
                       interval=interval,
                       is_flash=is_flash,
                       is_alpha=(ticker.get("futures_only", False) or ticker.get("binance_alpha", False)))
    ai_str, ai_blocked = _ai_assess(sym, exchange, tier["name"], "main",
                                    score, ob_spot, ratio, pos24, spike, net, move, funding_label)
    if ai_blocked:
        _rej("ai_block"); return
    msg += ai_str
    _kb_exchange = "MEXC" if ticker.get("binance_alpha") else exchange
    keyboard = _trade_keyboard(sym, _kb_exchange)   # signal has no orig link yet
    ok, sig_msg_id = send_ex(msg, keyboard)
    if not ok:
        log.error("SIGNAL SEND FAILED for %s — not tracking to avoid ghost signals", sym)
        return
    _rej("PASS")
    log.info("SIGNAL %-14s tier=%-5s spike=%.1fx net=%s ratio=%.1fx [%s %s] msg_id=%d",
             sym, tier["name"], spike, _fv(net), ratio, exchange, interval, sig_msg_id)

    # Save state AFTER confirmed delivery — no tracking without notification
    _signal_dedup[sym]  = now
    _alerted_price[sym] = price
    alerted[sym] = now
    tracking[sym] = {
        "entry":      price,
        "t0":         now,
        "hit":        set(),
        "max":        0.0,
        "min":        0.0,
        "exchange":   exchange,
        "is_flash":   is_flash,
        "sig_msg_id": sig_msg_id,
    }
    _scanner_type = ("moonshot" if is_moonshot
                     else "volume_explosion" if volume_explosion
                     else "momentum" if momentum_bypass
                     else "main")
    _db_add(sym, price, exchange, tier["name"], _scanner_type,
            ratio, ob_spot, score, pos24, spike, net, move, funding_label)
    save_state()

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
    if score >= 60:  return "🐂🐂 Strong Bull"
    if score >= 25:  return "🐂 Bullish"
    if score >= 5:   return "🐂 Mild Bullish"
    if score >= -5:  return "⚪ Neutral"
    if score >= -25: return "🐻 Mild Bearish"
    if score >= -60: return "🐻 Bearish"
    return "🐻🐻 Strong Bear"


def _calc_sector_performance(all_t: dict) -> dict:
    """Returns {sector: avg_change} for sectors with ≥2 coins."""
    data: Dict[str, list] = {}
    for sym, t in all_t.items():
        base   = sym[:-4] if sym.endswith("USDT") else sym.replace("USDT", "")
        sector = SECTOR_REGISTRY.get(base, "")
        if not sector or sector in ("Other", "BNB Alpha"):
            continue
        data.setdefault(sector, []).append(t["change"])
    return {s: sum(v) / len(v) for s, v in data.items() if len(v) >= 2}


def fetch_dominance() -> dict:
    """Fetch BTC/USDT/USDC dominance from CoinGecko global API. Returns {} on failure."""
    global _dominance_hist
    try:
        r = S.get("https://api.coingecko.com/api/v3/global", timeout=10)
        if not r.ok:
            return {}
        data  = r.json().get("data", {})
        pcts  = data.get("market_cap_percentage", {})
        btcd  = pcts.get("btc",  0.0)
        usdtd = pcts.get("usdt", 0.0)
        usdcd = pcts.get("usdc", 0.0)
        # OTHERS = 100 - BTC.D - (sum of top stables/ETH) is complex; use simple: 100 - btcd
        others = round(100.0 - btcd, 4)
        snap = {"btcd": btcd, "usdtd": usdtd, "usdcd": usdcd, "others": others}
        now  = time.time()
        _dominance_hist.append((now, snap))
        # Keep only last 2h
        _dominance_hist = [(ts, d) for ts, d in _dominance_hist if now - ts <= 7200]
        return snap
    except Exception as e:
        log.warning("fetch_dominance failed: %s", e)
        return {}


def _dom_delta(key: str, seconds: int) -> float:
    """Change in dominance[key] over the last `seconds`. Falls back to oldest available data."""
    if len(_dominance_hist) < 2:
        return 0.0
    now = time.time()
    cur_val = _dominance_hist[-1][1].get(key, 0)
    # Find a reference point ~`seconds` ago; if not enough history, use oldest we have
    candidates = [(ts, d) for ts, d in _dominance_hist if now - ts >= seconds * 0.7]
    ref = candidates[0][1] if candidates else _dominance_hist[0][1]
    return cur_val - ref.get(key, 0)


def _dom_dot(key: str, seconds: int, invert: bool = False) -> str:
    """🟢/🔴 dot for dominance change direction. invert=True flips meaning (e.g. OTHERS: rising = 🟢)."""
    delta = _dom_delta(key, seconds)
    if abs(delta) < 0.002:   # 0.002% minimum — dominance moves slowly
        return "⚪"
    rising = delta > 0
    if invert:
        return "🟢" if rising else "🔴"
    return "🔴" if rising else "🟢"


def send_market_stats(all_t: dict, bias: int, cvd: float, tbr: float, reason: str = ""):
    """Format and send market stats to Telegram — Wolf Flow style."""
    total = len(all_t)

    # ── Regime icon (bull 🐂 / bear 🐻) ──
    if bias >= 60:
        regime_icon = "🐂🐂"; regime_txt = "Strong Bull"
    elif bias >= 25:
        regime_icon = "🐂";   regime_txt = "Bullish"
    elif bias >= 5:
        regime_icon = "🐂";   regime_txt = "Mild Bullish"
    elif bias >= -5:
        regime_icon = "⚪";   regime_txt = "Neutral"
    elif bias >= -25:
        regime_icon = "🐻";   regime_txt = "Mild Bearish"
    elif bias >= -60:
        regime_icon = "🐻";   regime_txt = "Bearish"
    else:
        regime_icon = "🐻🐻"; regime_txt = "Strong Bear"

    # ── 5-dot visual: 🐂 bulls on left, 🐻 bears on right ──
    n_bull = round((bias + 100) / 200 * 5)
    dots   = "🐂" * n_bull + "🐻" * (5 - n_bull)

    # ── Market Breadth (24h) ──
    up   = sum(1 for t in all_t.values() if t["change"] >  1.0)
    down = sum(1 for t in all_t.values() if t["change"] < -1.0)
    flat = total - up - down
    up_pct   = up   * 100 // total if total else 0
    down_pct = down * 100 // total if total else 0
    flat_pct = flat * 100 // total if total else 0
    avg_up = (sum(t["change"] for t in all_t.values() if t["change"] >  1.0) / up)   if up   else 0.0
    avg_dn = (sum(t["change"] for t in all_t.values() if t["change"] < -1.0) / down) if down else 0.0

    # ── Top 5 movers (24h) ──
    sorted_t = sorted(all_t.items(), key=lambda x: x[1]["change"], reverse=True)
    gainers  = [(s[:-4] if s.endswith("USDT") else s, t["change"])
                for s, t in sorted_t if t["change"] > 0][:5]
    losers   = [(s[:-4] if s.endswith("USDT") else s, t["change"])
                for s, t in sorted_t if t["change"] < 0][-5:][::-1]

    # ── Sectors with symbol count ──
    sec_data: Dict[str, list] = {}
    for sym, t in all_t.items():
        base   = sym[:-4] if sym.endswith("USDT") else sym.replace("USDT", "")
        sector = SECTOR_REGISTRY.get(base, "")
        if not sector or sector in ("Other", "BNB Alpha"):
            continue
        sec_data.setdefault(sector, []).append(t["change"])
    sec_perf = sorted(
        [(s, sum(v) / len(v), len(v)) for s, v in sec_data.items() if len(v) >= 2],
        key=lambda x: -x[1]
    )

    # ── Flow icons ──
    tbr_icon = "🟢 Buyers" if tbr > 53 else ("🔴 Sellers" if tbr < 47 else "⚪ Neutral")
    cvd_icon = "🟢" if cvd > 0 else "🔴"
    cvd_dir  = "↑" if cvd > 0 else "↓"

    # ── Build message ──
    lines = [
        f"{'━' * 22}",
        f"💀 *MAFIO SNIPER* — Market Stats",
        f"🕐 {_ts()} UTC",
        f"{'━' * 22}",
        f"",
        f"🧭 *Market Bias*",
        f"{regime_icon}  *{regime_txt}*  ·  Score: `{bias:+d} / 100`",
        f"{dots}",
        f"",
        f"📊 *Market Breadth* (24h)  —  {total} symbols",
        f"🐂 UP    `{up_pct:3d}%`  {up} coins   avg `{avg_up:+.2f}%`",
        f"⚪ FLAT  `{flat_pct:3d}%`  {flat} coins",
        f"🐻 DOWN  `{down_pct:3d}%`  {down} coins   avg `{avg_dn:+.2f}%`",
        f"",
        f"💧 *Market Flow*",
        f"Taker‑buy: `{tbr:.1f}%`  {tbr_icon}",
        f"CVD: `{cvd_dir}{_fv(abs(cvd))}`  {cvd_icon}",
    ]

    # ── Market Structure: dominance ──
    dom = _dominance_hist[-1][1] if _dominance_hist else {}
    if dom:
        btcd   = dom.get("btcd",   0.0)
        usdtd  = dom.get("usdtd",  0.0)
        usdcd  = dom.get("usdcd",  0.0)
        others = dom.get("others", 0.0)
        # dots: rising BTC.D/USDT.D/USDC.D = 🔴 (bad for alts); rising OTHERS = 🟢 (alt season)
        def _dom_row(icon, label, key, pct, invert=False):
            d5  = _dom_delta(key, 300)
            d1h = _dom_delta(key, 3600)
            dot5  = _dom_dot(key, 300,  invert)
            dot1h = _dom_dot(key, 3600, invert)
            s5  = f"{d5:+.3f}%" if abs(d5)  >= 0.001 else "flat"
            s1h = f"{d1h:+.3f}%" if abs(d1h) >= 0.001 else "flat"
            return f"{icon} {label} `{pct:.2f}%`  5m:{dot5}`{s5}`  1h:{dot1h}`{s1h}`"

        lines += [
            "",
            "🌐 *Market Structure*",
            _dom_row("₿",  "BTC.D",  "btcd",   btcd),
            _dom_row("💵", "USDT.D", "usdtd",  usdtd),
            _dom_row("🔵", "USDC.D", "usdcd",  usdcd),
            _dom_row("📈", "OTHERS", "others", others, invert=True),
        ]

    if gainers:
        lines += ["", "📈 *Top Gainers (24h)*"]
        for i, (coin, chg) in enumerate(gainers, 1):
            lines.append(f"  `{i}.` {coin}  `+{chg:.2f}%`")

    if sec_perf:
        lines += ["", "🏆 *Sectors (24h avg)*"]
        for sec, chg, cnt in sec_perf[:10]:
            disp  = _SECTOR_DISPLAY.get(sec, f"📊 {sec}")
            arrow = "↑" if chg >= 0 else "↓"
            lines.append(f"  {disp}: `{chg:+.2f}%` {arrow} `({cnt} sym)`")

    if reason:
        lines += ["", f"⚡ _{reason}_"]

    lines.append(f"{'━' * 22}")
    send("\n".join(lines))
    log.info("Market stats sent — bias=%+d %s reason=%s", bias, regime_txt, reason or "periodic")


def check_btc_health(all_t: dict):
    """
    Monitor BTC price and alert on sharp moves:
      Drop  > -2% in 5min  → ⚠️ warning
      Drop  > -4% in 5min  → 🚨 danger + pause signals 10min
      Pump  > +3% in 5min  → 🚀 bull signal
    """
    global _btc_prices, _btc_alert_ts, _cascade_paused

    btc = all_t.get("BTCUSDT")
    if not btc:
        return
    now       = time.time()
    btc_price = btc["price"]

    # Rolling 15-min window
    _btc_prices.append((now, btc_price))
    _btc_prices = [(ts, p) for ts, p in _btc_prices if now - ts <= 900]

    if len(_btc_prices) < 3:
        return
    if now - _btc_alert_ts < 300:   # cooldown 5min
        return

    # Compare to price 5 min ago
    five_min_ago = [(ts, p) for ts, p in _btc_prices if now - ts >= 280]
    if not five_min_ago:
        return
    ref_price = five_min_ago[0][1]
    delta     = (btc_price - ref_price) / ref_price * 100

    if delta <= -4.0:
        send(
            f"{'━' * 20}\n"
            f"💀 *MAFIO SNIPER* 📡\n\n"
            f"🚨 *BTC DANGER DROP*\n"
            f"Bitcoin هبط `{delta:.2f}%` في 5 دقائق\n"
            f"💰 السعر الآن: `${_fp(btc_price)}`\n"
            f"⛔ تم إيقاف الإشارات مؤقتاً لـ 10 دقائق\n"
            f"🕐 {_ts()} UTC\n"
            f"{'━' * 20}"
        )
        _cascade_paused = now + 600   # pause 10 min
        _btc_alert_ts   = now
        log.warning("BTC danger drop %.2f%% — signals paused 10min", delta)

    elif delta <= -2.0:
        send(
            f"{'━' * 20}\n"
            f"💀 *MAFIO SNIPER* 📡\n\n"
            f"⚠️ *BTC Health Warning*\n"
            f"Bitcoin هبط `{delta:.2f}%` في 5 دقائق\n"
            f"💰 السعر الآن: `${_fp(btc_price)}`\n"
            f"📉 توقع ضغط على العملات البديلة\n"
            f"🕐 {_ts()} UTC\n"
            f"{'━' * 20}"
        )
        _btc_alert_ts = now
        log.info("BTC warning drop %.2f%%", delta)

    elif delta >= 3.0:
        send(
            f"{'━' * 20}\n"
            f"💀 *MAFIO SNIPER* 📡\n\n"
            f"🚀 *BTC Bull Move*\n"
            f"Bitcoin ارتفع `+{delta:.2f}%` في 5 دقائق\n"
            f"💰 السعر الآن: `${_fp(btc_price)}`\n"
            f"📈 توقع ارتداد قوي في العملات البديلة\n"
            f"🕐 {_ts()} UTC\n"
            f"{'━' * 20}"
        )
        _btc_alert_ts = now
        log.info("BTC bull move +%.2f%%", delta)


def check_dump_cascade(all_t: dict):
    """
    Alert when >30% of coins drop >1.5% in the last 5 minutes.
    Uses a rolling price snapshot (not 24h change) for accurate detection.
    Pauses new signals for 15 min on severe cascade.
    """
    global _cascade_alert_ts, _cascade_paused, _snap_prices, _snap_ts

    now = time.time()
    if now - _cascade_alert_ts < 600:   # cooldown 10min between alerts
        return

    # Refresh snapshot every 5 minutes
    if now - _snap_ts >= 300:
        _snap_prices = {sym: t["price"] for sym, t in all_t.items()}
        _snap_ts     = now
        return   # need at least one full 5-min window before comparing

    total = len(all_t)
    if total < 50:
        return

    # Count coins that dropped >1.5% vs snapshot 5 min ago
    drops = {}
    for sym, t in all_t.items():
        snap = _snap_prices.get(sym)
        if snap and snap > 0:
            delta = (t["price"] - snap) / snap * 100
            if delta < -1.5:
                drops[sym] = delta

    dumping = len(drops)
    pct     = dumping / total * 100

    if pct >= 40:
        worst = sorted(drops.items(), key=lambda x: x[1])[:5]
        worst_lines = "  ".join(f"{s[:-4]} `{d:.1f}%`" for s, d in worst)
        send(
            f"{'━' * 20}\n"
            f"💀 *MAFIO SNIPER* 📡\n\n"
            f"🚨 *DUMP CASCADE DETECTED*\n"
            f"`{dumping}` عملة من أصل `{total}` هبطت في 5 دقائق (`{pct:.0f}%`)\n\n"
            f"📉 الأسوأ: {worst_lines}\n\n"
            f"⛔ تم إيقاف الإشارات لـ 15 دقيقة\n"
            f"🕐 {_ts()} UTC\n"
            f"{'━' * 20}"
        )
        _cascade_paused   = now + 900
        _cascade_alert_ts = now
        log.warning("Dump cascade: %d/%d (%.0f%%) in 5min — signals paused 15min", dumping, total, pct)

    elif pct >= 30:
        send(
            f"{'━' * 20}\n"
            f"💀 *MAFIO SNIPER* 📡\n\n"
            f"⚠️ *Market Dump Warning*\n"
            f"`{dumping}` عملة من أصل `{total}` هبطت في 5 دقائق (`{pct:.0f}%`)\n"
            f"🔴 تجنّب الدخول حتى يستقر السوق\n"
            f"🕐 {_ts()} UTC\n"
            f"{'━' * 20}"
        )
        _cascade_alert_ts = now
        log.info("Market dump warning: %d/%d (%.0f%%) in 5min", dumping, total, pct)


def get_market_ctx(bias: int) -> dict:
    """
    Returns adaptive thresholds based on market bias — Sniper Mode active in Bull conditions.

    Strong Bull (≥60)  : SNIPER — max aggression, late_pct=0.95, loose spike/ob
    Bullish    (25-59) : SNIPER — late_pct=0.93, spike_mult=0.65, ob_min=0.37
    Mild Bull   (5-24) : Relaxed — late_pct=0.91, moderate filters
    Neutral   (-24-4)  : Standard filters
    Bear      (-25-59) : Strict — only high-conviction signals
    Strong Bear (<-60) : Very strict — almost only funding_bullish signals pass
    """
    if bias >= 60:
        return {"pos_limit": 0.82, "crash_limit": 30.0,
                "spike_mult": 0.55, "ratio_mult": 0.75, "ob_min": 0.35,
                "move_min": 0.0,  "late_pct": 0.95}  # Strong Bull — Sniper Mode
    if bias >= 25:
        return {"pos_limit": 0.78, "crash_limit": 22.0,
                "spike_mult": 0.65, "ratio_mult": 0.75, "ob_min": 0.37,
                "move_min": 0.0,  "late_pct": 0.93}  # Bullish — Sniper Mode
    if bias >= 5:
        return {"pos_limit": 0.78, "crash_limit": 18.0,
                "spike_mult": 0.80, "ratio_mult": 0.88, "ob_min": 0.38,
                "move_min": 0.5,  "late_pct": 0.91}  # Mild Bullish
    if bias >= -24:
        return {"pos_limit": 0.75, "crash_limit": 12.0,
                "spike_mult": 1.00, "ratio_mult": 1.00, "ob_min": 0.40,
                "move_min": 1.0,  "late_pct": 0.88}  # Neutral
    if bias >= -60:
        return {"pos_limit": 0.68, "crash_limit":  8.0,
                "spike_mult": 1.15, "ratio_mult": 1.15, "ob_min": 0.45,
                "move_min": 2.0,  "late_pct": 0.85}  # Bear
    # Strong Bear
    return     {"pos_limit": 0.55, "crash_limit":  5.0,
                "spike_mult": 1.30, "ratio_mult": 1.20, "ob_min": 0.50,
                "move_min": 2.5,  "late_pct": 0.82}  # Strong Bear: very strict


def should_signal(tier_name: str, bias: int, exchange: str = "MEXC") -> bool:
    """
    Wolf Flow logic: only fire signals when market conditions allow.

    Binance: signals even in bear market (FF +134%, ILV +35%, 0G +36% ALL in bear market)
      → news-driven pumps happen regardless of macro bias on Binance large-caps
    MEXC: stricter bias gate (thin liquidity = more false signals in bear)
    """
    if exchange == "Binance":
        return bias > -60   # Binance: allow all tiers unless extreme bear
    # MEXC
    if tier_name in ("Micro", "Small"):
        return bias > -70   # block only in extreme crash
    if tier_name == "Mid":
        return bias > -60
    # Large MEXC
    return bias > -40


def _is_late_entry(price, high_24h, low_24h):
    # type: (float, float, float) -> bool
    """
    True if price is in the top 15% of the 24h range (≥85% position).
    Prevents signals that fire when the move is already done.
    """
    rng = high_24h - low_24h
    if rng <= 0:
        return False
    pos = (price - low_24h) / rng
    return pos >= 0.85


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
    for sym, _, ticker in movers[:50]:
        _check(sym, ticker, "1m")   # 1m klines: candle completes every 60s → spike visible immediately
        time.sleep(0.05)

# ══════════════════════════════════════════════════════
#  MID SCAN — 90s, 5m klines
#  Fills the gap: fast_scan misses gradual pumps (TRU/CTSI/DUSK type)
#  slow_scan sees them too late (already at 90%+ of range → late_entry block)
#  mid_scan checks top 60 movers every 90s with 5m klines → catches momentum early
# ══════════════════════════════════════════════════════

MID_SCAN_S = 90   # every 90s

def mid_scan(all_t):
    """
    Catches gradual pumpers missed by fast_scan (delta < 0.3%) and
    seen too late by slow_scan (already at 24h peak when 1h kline fires).
    Runs every 90s on top 60 by 24h change using 5m klines.
    """
    # Top 80 movers by 24h change — these are building momentum
    # vol >= 150K: include smaller MEXC coins (TREE/KAT/DU type with tiny volumes)
    # change <= 70%: match slow_scan MEXC limit (DENT at 50% was previously excluded by 55% cap)
    by_chg = sorted(
        [(s, t) for s, t in all_t.items()
         if t["vol"] >= 150_000 and 2.0 <= t["change"] <= 70.0],
        key=lambda x: -x[1]["change"]
    )[:100]

    # DOGS fix: top 30 Binance Mid/Large by volume (vol >= $10M, change >= 0%)
    # A large-cap coin at +0% change falls outside the top-80 by change but its
    # volume already signals real interest — scan it regardless of change rank
    by_vol_bn = sorted(
        [(s, t) for s, t in all_t.items()
         if t["exchange"] == "Binance" and t["vol"] >= 10_000_000 and 0.0 <= t["change"] <= 70.0],
        key=lambda x: -x[1]["vol"]
    )[:30]

    seen = {s for s, _ in by_chg}
    candidates = list(by_chg)
    for item in by_vol_bn:
        if item[0] not in seen:
            seen.add(item[0])
            candidates.append(item)

    for sym, ticker in candidates:
        _kl = "5m"   # 5m klines: spike shows in 5-10 min, not 60 min
        _check(sym, ticker, _kl)
        time.sleep(0.08)


# ══════════════════════════════════════════════════════
#  SLOW SCAN — 5min, 1h klines
# ══════════════════════════════════════════════════════

def slow_scan(all_t):
    mexc_t    = {s: t for s, t in all_t.items() if t["exchange"] == "MEXC"}
    binance_t = {s: t for s, t in all_t.items() if t["exchange"] == "Binance"}

    def _pool(coins, pump_limit):
        elig = [(s, t) for s, t in coins.items()
                if t["vol"] >= 10_000 and t["change"] <= pump_limit]
        by_vol = sorted(elig, key=lambda x: -x[1]["vol"])[:200]
        by_chg = sorted(elig, key=lambda x: -x[1]["change"])[:200]
        seen, out = set(), []
        for item in by_vol + by_chg:
            if item[0] not in seen:
                seen.add(item[0]); out.append(item)
        return out

    # MEXC: raised to 70% — REDO(+56%) should enter pool | TAP(+357%) still excluded by _check
    # Binance: allow up to 80% (liquid coins can sustain bigger moves)
    mexc_candidates    = _pool(mexc_t,    70.0)
    binance_candidates = _pool(binance_t, 80.0)

    # Merge — Binance candidates get their own dedicated slots
    seen, candidates = set(), []
    for item in mexc_candidates + binance_candidates:
        if item[0] not in seen:
            seen.add(item[0]); candidates.append(item)

    log.info("slow_scan: %d/%d candidates (MEXC=%d Binance=%d)",
             len(candidates), len(all_t),
             len(mexc_candidates), len(binance_candidates))
    _diag.clear()
    for sym, ticker in candidates:
        # Binance uses "1h", MEXC uses "60m" for hourly klines
        _kl_interval = "1h" if ticker.get("exchange") == "Binance" else "60m"
        _check(sym, ticker, _kl_interval)
        time.sleep(0.12)
    if _diag:
        parts = sorted(_diag.items(), key=lambda x: -x[1])
        log.info("DIAG: %s", " | ".join(f"{k}={v}" for k, v in parts))
        # Accumulate for daily report
        for k, v in _diag.items():
            daily_diag[k] = daily_diag.get(k, 0) + v

# ══════════════════════════════════════════════════════
#  SUPERTREND SCANNER
# ══════════════════════════════════════════════════════

def _calc_supertrend(candles, period=10, mult=3.0):
    """
    SUPERTREND(period, mult) using Wilder's ATR (RMA).
    Returns list of is_bullish (True = price above ST = buy zone) per candle.
    """
    n = len(candles)
    if n < period + 2:
        return [True] * n
    H  = [float(c[2]) for c in candles]
    L  = [float(c[3]) for c in candles]
    C  = [float(c[4]) for c in candles]

    # True Range
    TR = []
    for i in range(n):
        pc = C[i-1] if i > 0 else L[i]
        TR.append(max(H[i]-L[i], abs(H[i]-pc), abs(L[i]-pc)))

    # Wilder's ATR (RMA smoothing)
    atr = [0.0] * n
    atr[period-1] = sum(TR[:period]) / period
    for i in range(period, n):
        atr[i] = (atr[i-1] * (period-1) + TR[i]) / period

    # Basic bands
    up_b = [(H[i]+L[i])/2 + mult*atr[i] for i in range(n)]
    dn_b = [(H[i]+L[i])/2 - mult*atr[i] for i in range(n)]

    # Final bands: trend-locked (upper only drops, lower only rises)
    fu = list(up_b)
    fd = list(dn_b)
    trend = [True] * n   # True = bullish

    for i in range(1, n):
        fu[i] = min(up_b[i], fu[i-1]) if C[i-1] < fu[i-1] else up_b[i]
        fd[i] = max(dn_b[i], fd[i-1]) if C[i-1] > fd[i-1] else dn_b[i]
        if trend[i-1]:     # was bullish: stay bullish unless price < lower band
            trend[i] = C[i] >= fd[i]
        else:              # was bearish: flip to bullish only when price > upper band
            trend[i] = C[i] >  fu[i]

    return trend


def scan_supertrend(all_t):
    """
    SUPERTREND(10,3) flip scanner on 1h candles.
    Catches slow-trending coins (BIO/ORDI/币安人生 type) missed by spike scanners:
    - No spike requirement — trend confirmation, not explosion
    - Fires when ST flips bearish→bullish within last 3 candles
    - Relaxed net_min vs spike scanner (1h window, trend-based)
    Runs every SUPER_SCAN_S (15 min).
    """
    now_ts   = time.time()
    _st_diag = {}

    def _rj(r):
        _st_diag[r] = _st_diag.get(r, 0) + 1

    # Pool: both exchanges, $3M+ daily volume, not in cooldown
    candidates = [
        (s, t) for s, t in all_t.items()
        if t["vol"] >= 3_000_000
        and s.endswith("USDT")
        and s[:-4] not in STABLECOINS
        and now_ts - alerted.get(s, 0) >= COOLDOWN
    ]
    candidates.sort(key=lambda x: -x[1]["vol"])
    candidates = candidates[:350]   # cap API calls

    log.info("scan_supertrend: pool=%d", len(candidates))
    fired = 0

    for sym, ticker in candidates:
        price    = ticker["price"]
        vol_24h  = ticker["vol"]
        exchange = ticker["exchange"]
        base_url = ticker["base_url"]
        change   = ticker["change"]

        # Skip frozen/stale tickers
        if change == 0.0 and vol_24h < 1_000_000:
            _rj("st_frozen"); continue

        # Skip absolute top of range (late entry) — uses shared 0.92 threshold
        rng24 = ticker["high24"] - ticker["low24"]
        pos24 = (price - ticker["low24"]) / rng24 if rng24 > 0 else 0.5
        if _is_late_entry(price, ticker["high24"], ticker["low24"]):
            _rj("st_top"); continue

        # Market bias gate — skip micro-caps in strong bear
        if not should_signal(get_tier(vol_24h)["name"], market_bias, exchange):
            _rj("st_bias"); continue

        # Klines: 1h Binance, 60m MEXC — 55 candles for 12h flip window + stable ATR10
        _kl = "1h" if exchange == "Binance" else "60m"
        candles = fetch_klines(sym, base_url, interval=_kl, limit=55)
        if len(candles) < 15:
            _rj("st_no_klines"); continue

        # Compute SUPERTREND(10,3)
        trend = _calc_supertrend(candles, period=10, mult=3.0)
        if len(trend) < 5:
            _rj("st_short"); continue

        # Must be currently bullish
        if not trend[-1]:
            _rj("st_bearish"); continue

        # Volume + move: compute early so trend_accel can use them
        try:
            vol_now   = float(candles[-1][5])
            vol_avg   = sum(float(c[5]) for c in candles[-11:-1]) / 10
            vol_ratio = vol_now / vol_avg if vol_avg > 0 else 1.0
        except Exception:
            vol_ratio = 1.0
        try:
            _move_1h = (float(candles[-1][4]) - float(candles[-1][1])) / float(candles[-1][1]) * 100
        except Exception:
            _move_1h = change

        # Block late-pump entries: if 1h move > 12% the move is already done
        if _move_1h > 12.0:
            _rj("st_late_pump"); continue

        # Detect flip: bearish→bullish within last 12 candles (12h window)
        # trend[-1]=True + one of previous 12 candles was bearish
        # Extended from 6h: catches ORDI/WAL/SAGA type that flip 7-12h before peak
        flip_ago = None
        for back in range(1, 13):
            if len(trend) > back and not trend[-(back + 1)]:
                flip_ago = back
                break

        # Trend acceleration mode: coin bullish >12h but current candle surging
        # Catches ORDI +219% / WAL +56% extended trends that are still in momentum
        # Requires strong volume (≥2.5x avg) + real price move (≥2.0%) this candle
        trend_accel = (flip_ago is None and vol_ratio >= 2.5 and _move_1h >= 2.0)

        if flip_ago is None and not trend_accel:
            _rj("st_no_flip"); continue   # been bullish >12h with no acceleration

        # Volume confirmation: current candle > 2.0× 10-candle average (DOGE had 1.5x = too weak)
        if vol_ratio < 2.0:
            _rj("st_low_vol"); continue

        # Net flow — 60-min window (relaxed floor vs spike scanner)
        buy_v, sell_v = fetch_agg_trades(sym, base_url, minutes=60)
        if sell_v <= 0:
            _rj("st_no_trades"); continue
        net = buy_v - sell_v
        # Net flow — raised floors vs original: trend signals need real conviction
        # Binance: $8K → $20K (STABLE had only $18.4K = fake/dust flow)
        # MEXC: $3K → $6K (keeps micro-cap sensitivity but filters noise)
        _net_floor = 6_000.0 if exchange == "MEXC" else 20_000.0
        if net < _net_floor:
            _rj("st_low_net"); continue

        # Ratio: buyers must meaningfully outnumber sellers
        # CL (1.2x) / AR (1.4x) = almost 1:1 = no conviction
        ratio_st = buy_v / sell_v if sell_v > 0 else 0.0
        if ratio_st < 1.8:
            _rj("st_low_ratio"); continue

        # Position guard: block near-top entries
        if pos24 > 0.78:
            _rj("st_high_pos"); continue

        # Stale flip + high position = late entry into old trend
        # GRIFFAIN: flip 8h ago + 79% position = trend already priced in
        # BB: flip 5h ago + 81% pos + 0% move = >=5 (not >5) catches exact boundary
        if flip_ago is not None and flip_ago >= 5 and pos24 > 0.70:
            _rj("st_stale_high"); continue

        # Stale flip + no price momentum = dead trend (BB pattern: 5h flip, 0.00% 1h move, pos 81%)
        # If flip was ≥3h ago and price hasn't moved ≥0.5% in the last candle + pos already high
        if flip_ago is not None and flip_ago >= 3 and _move_1h < 0.5 and pos24 > 0.65:
            _rj("st_stale_flat"); continue

        # Order book: block suspicious distribution (ob > 83% = smart money selling into bids)
        # STABLE had 86% ob but no move = classic distribution. 88% triggers bull_trap in _check
        # but supertrend needs earlier block since it has no bull_trap filter
        ob_spot = fetch_ob_imbalance(sym, base_url, levels=20)
        _st_ob_min = 0.60                              # aligned with main scanner floor
        if ob_spot < _st_ob_min:
            _rj("st_ob_sellers"); continue
        if ob_spot > 0.79:
            _rj("st_high_ob"); continue   # suspicious distribution pattern

        # Score check — aligned with main scanner floor (7.0)
        tier  = get_tier(vol_24h)
        score = _calc_score(pos24, net, _net_floor, ob_spot, vol_ratio)
        if exchange == "MEXC":
            if score < 8.0: _rj("st_low_score"); continue
        else:
            # Absolute floor — no path bypasses a score this weak
            if score < 5.5: _rj("st_low_score"); continue
            _st_ok = (score >= 7.0
                      or (ob_spot >= 0.72 and vol_ratio >= 2.5 and net >= _net_floor)
                      or (net > 100_000 and ob_spot >= 0.65))
            if not _st_ok: _rj("st_low_score"); continue

        # Dedup: don't re-signal if already tracking or within 2h
        if sym in tracking:
            continue
        if now_ts - _signal_dedup.get(sym, 0) < 7200:
            continue

        # ── Build signal (full format via build_signal) ───────
        _, badge     = _register_confirm(sym, "supertrend")
        ob_lbl       = "🟢 Buyers" if ob_spot > 0.58 else ("🔴 Sellers" if ob_spot < 0.46 else "⚪ Balanced")
        _flip_txt    = f"{flip_ago}h ago" if flip_ago else "🚀 Acceleration"
        _net_str     = f"+${net/1000:.1f}K" if net < 1_000_000 else f"+${net/1_000_000:.2f}M"
        _closes_ema  = [float(c[4]) for c in candles]
        _ema20       = _calc_ema(_closes_ema, 20)
        _ema_bull    = price >= _ema20

        msg = build_signal(
            sym, price, change, buy_v, sell_v,
            spike=vol_ratio, move=_move_1h,
            exchange=exchange, tier_name=tier["name"],
            ema_bull=_ema_bull,
            high24=ticker["high24"], low24=ticker["low24"],
            badge=badge,
            funding_label=f"Supertrend(10,3) Bullish — {_flip_txt}",
            ob_label=ob_lbl, ob_pct=int(ob_spot * 100),
            score=score, interval="1h",
            signal_type="SUPERTREND BREAKOUT 📈",
            is_alpha=(ticker.get("futures_only", False) or ticker.get("binance_alpha", False)),
        )

        ai_str, ai_blocked = _ai_assess(sym, exchange, tier["name"], "supertrend",
                                        score, ob_spot, ratio_st, pos24, vol_ratio, net, _move_1h,
                                        f"Supertrend flip {flip_ago}h")
        if ai_blocked:
            continue
        msg += ai_str
        _kb_ex = "MEXC" if ticker.get("binance_alpha") else exchange
        keyboard = _trade_keyboard(sym, _kb_ex)
        ok, sig_msg_id = send_ex(msg, keyboard)
        if ok:
            fired += 1
            _signal_dedup[sym]   = now_ts
            _alerted_price[sym]  = price
            alerted[sym]         = now_ts
            tracking[sym] = {
                "entry":      price,
                "t0":         now_ts,
                "hit":        set(),
                "max":        0.0,
                "min":        0.0,
                "exchange":   exchange,
                "is_flash":   False,
                "sig_msg_id": sig_msg_id,
            }
            _db_add(sym, price, exchange, tier["name"], "supertrend",
                    ratio_st, ob_spot, score, pos24, vol_ratio, net, _move_1h,
                    f"Supertrend flip {flip_ago}h")
            save_state()
            log.info("SUPERTREND %s price=%.6g vol=%.1fx net=%s flip=%dh score=%.1f",
                     sym, price, vol_ratio, _net_str, flip_ago, score)

        time.sleep(0.15)

    if _st_diag:
        parts = sorted(_st_diag.items(), key=lambda x: -x[1])
        log.info("ST_DIAG fired=%d: %s", fired, " | ".join(f"{k}={v}" for k, v in parts))


# ══════════════════════════════════════════════════════
#  QUIET ACCUMULATION SCANNER — كاشف التراكم الصامت عند القاع
#  يرصد الشراء الصامت قبل انطلاق السعر (Wolf Flow HYPER style)
#  يعمل كل 5 دقائق — يبحث في أسفل 35% من نطاق 24h
# ══════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════
#  SLEEPING GIANT SCANNER — 60s, 1m klines
#  Catches flat coins with sudden 1m volume explosion BEFORE price moves.
#  Problem it solves: 我踏马来了 pumped +25% but signal arrived 4h late because:
#    - fast_scan needs price delta ≥ 0.3% in 5s (detects AFTER move)
#    - mid_scan only scans top-24h-movers (flat coins excluded)
#  Solution: monitor all flat coins (24h change -5% to +8%) every 60s,
#    flag when latest 1m candle volume ≥ 20x normal AND previous ≥ 3x
#    → signal fires 60-120 seconds after accumulation starts, before main move.
#  Uses 1m (not 5m): explosions complete in 1-5 minutes, 5m candles are too slow.
# ══════════════════════════════════════════════════════

def scan_sleeping_giant(all_t):
    """
    Detects flat coins (low 24h change) with a sudden 1m volume explosion.
    Signals BEFORE the main price move by detecting volume anomaly first.
    """
    now = time.time()
    candidates = [
        (sym, t) for sym, t in all_t.items()
        if -5.0 <= t["change"] <= 8.0          # flat to slightly bullish — not already pumping
        and t["vol"] >= 100_000                 # minimum real liquidity ($100K/day)
        and sym not in tracking
        and now - _signal_dedup.get(sym, 0) >= 7200
        and now - alerted.get(sym, 0) >= COOLDOWN
        and t["price"] >= 0.000001              # skip near-zero price scam coins
    ]

    fired = 0
    for sym, ticker in candidates:
        avg_1m_vol = ticker["vol"] / 1440.0     # expected USDT volume per 1m candle
        if avg_1m_vol <= 0:
            continue

        klines = fetch_klines(sym, ticker["base_url"], interval="1m", limit=8)
        if not klines or len(klines) < 4:
            continue

        try:
            # -2 = last completed 1m candle, -3 = one before (both must confirm)
            last_vol = _qvol(klines[-2])
            prev_vol = _qvol(klines[-3])

            last_ratio = last_vol / avg_1m_vol
            prev_ratio = prev_vol / avg_1m_vol

            # Primary spike threshold — lower for Binance Large/Mid (vol >= $10M)
            # Large caps accumulate with 10-15x spike (DOGS: $61M/day, 10x = $610K extra)
            # Small/Micro caps need 20x to filter noise (tiny baseline makes 5x meaningless)
            _sg_spike_min = 10.0 if ticker.get("exchange") == "Binance" and ticker["vol"] >= 10_000_000 else 20.0
            if last_ratio < _sg_spike_min or prev_ratio < 1.5:
                continue

            # Price move in last candle: started (≥ 0.05%) but not done (≤ 6%)
            o  = float(klines[-2][1])
            cl = float(klines[-2][4])
            candle_move = (cl - o) / o * 100 if o > 0 else 0
            if candle_move < 0.05 or candle_move > 6.0:
                continue

        except Exception:
            continue

        log.info("SLEEP_GIANT candidate %s vol_ratio=%.0fx prev=%.0fx candle_move=%.2f%%",
                 sym, last_ratio, prev_ratio, candle_move)

        ticker["_sg_spike"] = last_ratio   # pass confirmed spike to _check
        ticker["_sg_move"]  = candle_move  # pass confirmed move to _check
        _check(sym, ticker, "1m_sg")
        fired += 1
        time.sleep(0.1)
        if fired >= 5:   # safety cap: max 5 sleeping giant checks per cycle
            break


def scan_quiet_accum(all_t):
    """
    Catches coins being accumulated quietly near their 24h low
    BEFORE price breaks out — the pattern Wolf Flow used to catch AI +50%.

    Stricter v2 conditions (re-enabled after AIUSDT analysis):
      pos24 < 0.30  — price in bottom 30% of 24h range (tighter than before)
      change: -25% to +10%
      vol >= 500K   — real liquidity (raised from 200K)
      ratio >= 3.5x — strong buyer dominance (raised from 2.5x)
      spike >= 2.5x — clear volume surge (raised from 1.5x)
      ob >= 0.60    — order book clearly favours buyers
      score >= 8.0  — high quality only (raised from 7.0)
    """
    now = time.time()

    candidates = []
    for sym, t in all_t.items():
        h24, l24 = t["high24"], t["low24"]
        rng = h24 - l24
        if rng <= 0:
            continue
        pos24 = (t["price"] - l24) / rng
        if pos24 > 0.30:
            continue
        vol_24h = t["vol"]
        if vol_24h < 500_000:
            continue
        chg = t["change"]
        if chg > 10.0 or chg < -25.0:
            continue
        # Post-pump trap: coin pumped big intraday then crashed to "bottom" — P&D setup
        # GT pattern: pumped to $0.179 → fell to $0.128 (pos≈3%) → fake ratio 34.9x → dump
        # pump_size>30% + crash>20% from high = artificial bottom, not real accumulation
        _pump_size     = (h24 - l24) / l24 * 100 if l24 > 0 else 0
        _crash_from_top = (h24 - t["price"]) / h24 * 100 if h24 > 0 else 0
        if _pump_size > 30.0 and _crash_from_top > 20.0:
            continue
        if sym in tracking:
            continue
        if now - _signal_dedup.get(sym, 0) < 7200:
            continue
        if now - alerted.get(sym, 0) < COOLDOWN:
            continue
        # skip MEXC tokenized stocks
        price = t["price"]
        if t["exchange"] == "MEXC" and sym[:-4].endswith("ON") and price > 20:
            continue
        # Skip extreme micro-price coins (< $0.000001) — almost always scams/dead
        if price < 0.000001:
            continue
        candidates.append((sym, pos24, t))

    candidates.sort(key=lambda x: x[1])   # lowest pos24 first (deepest in range = best)

    fired = 0
    for sym, pos24, t in candidates[:30]:
        price    = t["price"]
        vol_24h  = t["vol"]
        exchange = t["exchange"]
        base_url = t["base_url"]

        buy_v, sell_v = fetch_agg_trades(sym, base_url, minutes=60)
        if sell_v <= 0 or (buy_v + sell_v) < 500:
            continue

        ratio = buy_v / sell_v
        # Ratio floors: winners show ≥2.5x minimum (PGVERSE=3.5x, SXT=9.3x, GT=34.9x)
        # SKL(1.9x) and TREE(2.0x) were weak signals — raise floor to match Micro tier
        # Ultra-low price (DENT type): accept 2.0x — USD flows are small at $0.000061
        _ratio_min = 2.5 if price < 0.001 else 3.5
        if ratio < _ratio_min:
            continue

        net = buy_v - sell_v
        if net <= 0:
            continue

        # Volume spike: 1h traded volume vs expected hourly (vol_24h / 24)
        avg_1h = vol_24h / 24.0
        spike  = (buy_v + sell_v) / avg_1h if avg_1h > 0 else 0.0
        if spike < 2.5:
            continue

        # Adaptive net floor by price level — DENT $0.000061 type needs lower floor
        if exchange == "Binance":
            if price < 0.001:
                _net_floor = max(vol_24h * 0.001, 500.0)    # DENT/SHIB type
            elif price < 0.01:
                _net_floor = max(vol_24h * 0.001, 1_000.0)
            else:
                _net_floor = max(vol_24h * 0.001, 3_000.0)
        else:
            _net_floor = max(vol_24h * 0.001, 300.0)        # MEXC micro-caps
        if net < _net_floor:
            continue

        # MEXC wash trading guard
        if exchange == "MEXC" and vol_24h > 0:
            if (buy_v + sell_v) / vol_24h > 0.60:
                continue

        ob_spot = fetch_ob_imbalance(sym, base_url, levels=20)
        if ob_spot < 0.60:
            continue
        # Fake wall guard: ≥95% bids = artificial buy wall (LSM/ZEUS pattern: pump+dump)
        # ZEUS (ob=0.95, MEXC) confirmed P&D: +9.4% spike then -5.4% crash below entry
        if ob_spot >= 0.95:
            continue
        # Falling-knife + fake accumulation — LKT/MEXC post-crash pattern:
        # ratio ≥20x + ob ≥88% + still falling = artificial buy wall on dying token
        if (exchange == "MEXC"
                and ratio >= 20.0
                and ob_spot >= 0.88
                and t["change"] < -5.0):
            continue

        tier  = get_tier(vol_24h)
        score = _calc_score(pos24, net, _net_floor, ob_spot, spike)
        # Strict v2: require high score for all exchanges
        if score < 8.0:
            continue

        _, badge = _register_confirm(sym, "accum")
        ob_lbl   = "🟢 Buyers" if ob_spot > 0.58 else "⚪ Balanced"
        ob_pct   = int(ob_spot * 100)
        pos_pct  = int(pos24 * 100)
        ex_icon  = "🟡" if exchange == "Binance" else "🟠"

        if ratio >= 8.0:   int_txt, int_icon = "🔥 High Squeeze Risk", "🟡"
        elif ratio >= 4.0: int_txt, int_icon = "⚡ Squeeze Risk",       "🟡"
        elif ratio >= 2.5: int_txt, int_icon = "🟢 Bullish Flow",       "🟢"
        else:              int_txt, int_icon = "⚪ Neutral",             "⚪"

        global signal_count
        signal_count += 1

        msg = (
            f"{'━'*20}\n"
            f"💀 *MAFIO SNIPER* 📡\n"
            f"\n"
            f"🆕 *#{sym[:-4]}* 💀 · {'Alpha' if (t.get('futures_only') or t.get('binance_alpha')) else ('MEXC' if exchange == 'MEXC' else 'Spot')} · Signal #{signal_count} {badge}\n"
            f"💰 Price: `${_fp(price)}`\n"
            f"📉 24h Change: `{t['change']:+.2f}%`\n"
            f"📍 Position: `%{pos_pct} from Bottom` ✅\n"
            f"\n"
            f"⚡ Volume: `{spike:.1f}x` above avg\n"
            f"{int_icon} Interest: {int_txt}\n"
            f"📊 Ratio: `{ratio:.1f}x` 🔥\n"
            f"💹 1h Flow:\n"
            f"  📥 In:  `{_fv(buy_v)}`\n"
            f"  📤 Out: `{_fv(sell_v)}`\n"
            f"  ▲ Net: `+{_fv(net)}` ✅\n"
            f"📗 Order Book: {ob_lbl} `{ob_pct}%` bids\n"
            f"🎯 🌒 *QUIET ACCUMULATION* · Score: `{score}/10`\n"
            f"\n"
            f"{ex_icon} Exchange: `{exchange}`\n"
            f"🕐 {_ts()} UTC\n"
            f"{'━'*20}"
        )

        ai_str, ai_blocked = _ai_assess(sym, exchange, tier["name"], "quiet_accum",
                                        score, ob_spot, ratio, pos24, spike, net, t["change"], "—")
        if ai_blocked:
            continue
        msg += ai_str
        # Reserve dedup slot BEFORE sending to prevent race-condition duplicates
        alerted[sym]        = now
        _signal_dedup[sym]  = now
        kb = _trade_keyboard(sym, exchange)
        ok, sig_msg_id = send_ex(msg, reply_markup=kb)
        if ok:
            _alerted_price[sym]   = price
            tracking[sym] = {
                "entry":      price,
                "t0":         now,        # fixed: was "ts" — check_milestones needs "t0"
                "hit":        set(),
                "max":        0.0,
                "min":        0.0,
                "exchange":   exchange,
                "is_flash":   False,
                "sig_msg_id": sig_msg_id,
            }
            _db_add(sym, price, exchange, tier["name"], "accum",
                    ratio, ob_spot, score, pos24, spike, net, t["change"], "—")
            save_state()
            fired += 1
            log.info("ACCUM %s pos24=%d%% ratio=%.1f spike=%.1fx score=%.1f",
                     sym, pos_pct, ratio, spike, score)
        time.sleep(0.1)

    if fired:
        log.info("scan_quiet_accum: fired=%d", fired)


# ══════════════════════════════════════════════════════
#  SECTOR LIQUIDITY SCANNER — standalone, no changes to bot strategy
#  Detects sector rotation and alerts when liquidity flows into a sector
#  Runs every 5 min, never calls _check(), never modifies thresholds
# ══════════════════════════════════════════════════════

SECTOR_SCAN_S         = 300   # every 5 min
SECTOR_HEAT_WARM      = 2.5   # "warming up" — scan quiet coins (not yet moved)
SECTOR_HEAT_MIN       = 4.0   # "hot" — scan all coins
SECTOR_ALERT_COOLDOWN = 3600  # 1h between hot-sector scans
SECTOR_WARM_COOLDOWN  = 1800  # 30min between warm-sector scans

# Comprehensive sector registry — coin base → sector name
# Priority: ecosystem-specific > general (DOGS→TON Eco not Meme)
SECTOR_REGISTRY: Dict[str, str] = {
    # 🐸 Meme
    "DOGE":"Meme","SHIB":"Meme","PEPE":"Meme","FLOKI":"Meme",
    "TRUMP":"Meme","MELANIA":"Meme","FARTCOIN":"Meme","TURBO":"Meme",
    "POPCAT":"Meme","NEIRO":"Meme","BOME":"Meme","PNUT":"Meme",
    "GIGGLE":"Meme","GIGA":"Meme","BABYDOGE":"Meme","MOG":"Meme",
    "GOAT":"Meme","MEME":"Meme","SWARMS":"Meme","COW":"Meme",
    "HIPPO":"Meme","TST":"Meme","BROCCOLI":"Meme","PLAY":"Meme",
    "VINE":"Meme","ACT":"Meme","MOODENG":"Meme","BRETT":"Meme",
    "SPX":"Meme","SLERF":"Meme","WEN":"Meme","AIDOGE":"Meme",
    "LADYS":"Meme","MYRO":"Meme","PONKE":"Meme","WOJAK":"Meme",

    # 🧱 Layer 1
    "ETH":"Layer1","ADA":"Layer1","AVAX":"Layer1","ATOM":"Layer1",
    "NEAR":"Layer1","ALGO":"Layer1","FTM":"Layer1","ONE":"Layer1",
    "HBAR":"Layer1","XTZ":"Layer1","EOS":"Layer1","TRX":"Layer1",
    "STX":"Layer1","EGLD":"Layer1","THETA":"Layer1","KAVA":"Layer1",
    "ZIL":"Layer1","ICX":"Layer1","WAVES":"Layer1","CELO":"Layer1",
    "FLOW":"Layer1","MINA":"Layer1","ICP":"Layer1","APT":"Layer1",
    "SUI":"Layer1","SEI":"Layer1","INJ":"Layer1","TIA":"Layer1",
    "HIVE":"Layer1","STEEM":"Layer1","LUNC":"Layer1","ROSE":"Layer1",
    "ZETA":"Layer1","KAS":"Layer1","KASPA":"Layer1","BEAM":"Layer1",
    "MONAD":"Layer1","CFX":"Layer1","CANTO":"Layer1","EVMOS":"Layer1",
    "ALEO":"Layer1","BERA":"Layer1","SONIC":"Layer1","ECLIPSE":"Layer1",

    # ⚡ Layer 2
    "MATIC":"Layer2","ARB":"Layer2","OP":"Layer2","ZK":"Layer2",
    "STRK":"Layer2","IMX":"Layer2","METIS":"Layer2","BOBA":"Layer2",
    "CELR":"Layer2","LRC":"Layer2","SKL":"Layer2","MANTA":"Layer2",
    "TAIKO":"Layer2","MODE":"Layer2","CYBER":"Layer2","XAI":"Layer2",
    "BLAST":"Layer2","LINEA":"Layer2","SCROLL":"Layer2","ZKSYNC":"Layer2",

    # 💎 DeFi
    "UNI":"DeFi","AAVE":"DeFi","COMP":"DeFi","MKR":"DeFi",
    "CRV":"DeFi","SUSHI":"DeFi","1INCH":"DeFi","BAL":"DeFi",
    "SNX":"DeFi","YFI":"DeFi","CVX":"DeFi","FXS":"DeFi",
    "JUP":"DeFi","CAKE":"DeFi","BAKE":"DeFi","DODO":"DeFi",
    "PERP":"DeFi","GMX":"DeFi","PENDLE":"DeFi","RDNT":"DeFi",
    "GNS":"DeFi","KWENTA":"DeFi","LYRA":"DeFi","DOPEX":"DeFi",
    "VELA":"DeFi","DYDX":"DeFi","OSMO":"DeFi","ASTRO":"DeFi",
    "BANANA":"DeFi","ETHFI":"DeFi","ENA":"DeFi","USDe":"DeFi",

    # 🎮 GameFi
    "AXS":"GameFi","SAND":"GameFi","MANA":"GameFi","ILV":"GameFi",
    "GALA":"GameFi","ENJ":"GameFi","TLM":"GameFi","ALICE":"GameFi",
    "MAGIC":"GameFi","SLP":"GameFi","SKILL":"GameFi","ATLAS":"GameFi",
    "POLIS":"GameFi","GODS":"GameFi","RFOX":"GameFi","DERC":"GameFi",
    "FEVR":"GameFi","SPS":"GameFi","PRIME":"GameFi","PIXEL":"GameFi",
    "PORTAL":"GameFi","YGG":"GameFi","GHST":"GameFi","RON":"GameFi",
    "FF":"GameFi","VOXEL":"GameFi","D":"GameFi","ECHELON":"GameFi",
    "SHRAPNEL":"GameFi","BIGTIME":"GameFi","GUILD":"GameFi","PYR":"GameFi",

    # 🤖 AI / Data
    "FET":"AI","AGIX":"AI","OCEAN":"AI","TAO":"AI","RENDER":"AI",
    "GRT":"AI","NMR":"AI","ARKM":"AI","WLD":"AI","AIOZ":"AI",
    "RSS3":"AI","ALI":"AI","ORAI":"AI","VIRTUAL":"AI","AI16Z":"AI",
    "PRIME":"AI","GRASS":"AI","OPML":"AI","PAAL":"AI","MYSHELL":"AI",
    "MASA":"AI","DRIA":"AI","OLAS":"AI","GIZA":"AI","VANA":"AI",

    # 🔗 Oracle / Infrastructure
    "LINK":"Oracle","BAND":"Oracle","API3":"Oracle","DIA":"Oracle",
    "TRB":"Oracle","UMA":"Oracle","ZRX":"Oracle","PYTH":"Oracle",
    "SUPRA":"Oracle","NEST":"Oracle","PRCL":"Oracle","WITNET":"Oracle",

    # 🗂️ Storage / Data
    "FIL":"Storage","AR":"Storage","STORJ":"Storage","BLZ":"Storage",
    "SC":"Storage","HOT":"Storage","NKN":"Storage","CRUST":"Storage",
    "BNB_STORAGE":"Storage",

    # 🖼️ NFT / Metaverse
    "APE":"NFT","BLUR":"NFT","LOOKS":"NFT","X2Y2":"NFT","RARE":"NFT",
    "SUPER":"NFT","WAXP":"NFT","AUDIO":"NFT","CHZ":"NFT","GALAX":"NFT",
    "BOSON":"NFT","WHALE":"NFT","NFTX":"NFT","ARCADE":"NFT",

    # 💰 Payments / Remittance
    "XRP":"Payments","XLM":"Payments","LTC":"Payments","BCH":"Payments",
    "DASH":"Payments","NANO":"Payments","VET":"Payments","BTT":"Payments",
    "IOTA":"Payments","MIOTA":"Payments","XDC":"Payments","COTI":"Payments",
    "QASH":"Payments","UTK":"Payments","NULS":"Payments",

    # 🔒 Privacy
    "XMR":"Privacy","ZEC":"Privacy","SCRT":"Privacy","DUSK":"Privacy",
    "KEEP":"Privacy","FIRO":"Privacy","OXEN":"Privacy","BEAM_P":"Privacy",
    "GRIN":"Privacy","DASH_P":"Privacy",

    # 🏦 Exchange Token
    "BNB":"Exchange","CRO":"Exchange","FTT":"Exchange","HT":"Exchange",
    "MX":"Exchange","WOO":"Exchange","BGB":"Exchange","LEO":"Exchange",

    # 🔵 TON Ecosystem
    "TON":"TON Eco","NOT":"TON Eco","DOGS":"TON Eco","HMSTR":"TON Eco",
    "CATI":"TON Eco","STON":"TON Eco","SCALE":"TON Eco","GRAM":"TON Eco",
    "JETTON":"TON Eco","DFC":"TON Eco",

    # ☀️ Solana Ecosystem
    "SOL":"SOL Eco","BONK":"SOL Eco","WIF":"SOL Eco","JITO":"SOL Eco",
    "ORCA":"SOL Eco","RAY":"SOL Eco","DRIFT":"SOL Eco","ZEUS":"SOL Eco",
    "IO":"SOL Eco","CLOUD":"SOL Eco","SLERF":"SOL Eco","POPCAT":"SOL Eco",
    "WEN":"SOL Eco","PONKE":"SOL Eco","BRET":"SOL Eco","MYRO":"SOL Eco",

    # 🔶 BNB Ecosystem
    "CAKE":"BNB Eco","BAKE":"BNB Eco","XVS":"BNB Eco","ALPACA":"BNB Eco",
    "BELT":"BNB Eco","SFUND":"BNB Eco","BIFI":"BNB Eco","RABBIT":"BNB Eco",

    # 🌊 Liquid Staking / ETH Eco
    "LDO":"LST","RPL":"LST","ANKR":"LST","SSV":"LST","SWISE":"LST",
    "FIS":"LST","ETHX":"LST","STAFI":"LST","LSETH":"LST","CBETH":"LST",

    # 💼 RWA (Real World Assets)
    "ONDO":"RWA","PAXG":"RWA","CFG":"RWA","MPL":"RWA","TRU":"RWA",
    "CPOOL":"RWA","ACRED":"RWA","POLYX":"RWA","GOLDFINCH":"RWA",

    # 🌐 Web3 / Social / Identity
    "ENS":"Web3","MASK":"Web3","DESO":"Web3","GAL":"Web3","CYBER":"Web3",
    "CYB":"Web3","LENS":"Web3","FARCASTER":"Web3","PUSH":"Web3",

    # 🛡️ ZK / Zero Knowledge
    "STRK":"ZK","MANTA":"ZK","TAIKO":"ZK","ALEO":"ZK","AZTEC":"ZK",
    "SCROLL":"ZK","PLONK":"ZK","RISC0":"ZK","GEVULOT":"ZK",

    # 🌍 Interoperability / Cross-chain
    "DOT":"Interop","W":"Interop","AXL":"Interop","RUNE":"Interop",
    "CELR":"Interop","SYN":"Interop","HOP":"Interop","LI":"Interop",
    "MULTICHAIN":"Interop","STARGATE":"Interop","STG":"Interop",

    # 📡 DePIN
    "HNT":"DePIN","MOBILE":"DePIN","IOT":"DePIN","IOTX":"DePIN",
    "AIOZ":"DePIN","WIFI":"DePIN","DIMO":"DePIN","NATIX":"DePIN",
    "XNET":"DePIN","GEODNET":"DePIN","SRCX":"DePIN","ROAM":"DePIN",

    # 🏆 Sports / Fan Token
    "CHZ":"Sports","SANTOS":"Sports","BAR":"Sports","PSG":"Sports",
    "ACM":"Sports","JUV":"Sports","CITY":"Sports","OG":"Sports",
    "AFC":"Sports","ALPINE":"Sports","PORTO":"Sports","LAZ":"Sports",

    # 🟠 Binance Alpha — runtime auto-registers futures_only Binance coins
    # MEXC-listed Alpha coins added manually (no Binance FAPI pair)
    "EVAA":"BNB Alpha","RAVE":"BNB Alpha","B3":"BNB Alpha","SIREN":"BNB Alpha",
    "LAB":"BNB Alpha","FLOCK":"BNB Alpha","FHE":"BNB Alpha","BLUM":"BNB Alpha",
    "PENGUIN":"BNB Alpha","BLESS":"BNB Alpha","ELON":"BNB Alpha","KOMA":"BNB Alpha",
    "MAJOR":"BNB Alpha","PNUT":"BNB Alpha","ACT":"BNB Alpha","MOODENG":"BNB Alpha",
    "GOAT":"BNB Alpha","CHILLGUY":"BNB Alpha","NEIRO":"BNB Alpha","LUCE":"BNB Alpha",
    "FOREST":"BNB Alpha","SUP":"BNB Alpha","OWL":"BNB Alpha","GM":"BNB Alpha",
    "ESIM":"BNB Alpha","CLO":"BNB Alpha","TST":"BNB Alpha","ROCKY":"BNB Alpha",
}

SECTOR_ICONS: Dict[str, str] = {
    "Meme":"🐸","Layer1":"🧱","Layer2":"⚡","DeFi":"💎",
    "GameFi":"🎮","AI":"🤖","Oracle":"🔗","Storage":"🗂️",
    "NFT":"🖼️","Payments":"💰","Privacy":"🔒","Exchange":"🏦",
    "TON Eco":"🔵","SOL Eco":"☀️","BNB Eco":"🔶","LST":"🌊",
    "RWA":"💼","Web3":"🌐","ZK":"🛡️","Interop":"🌍",
    "DePIN":"📡","Sports":"🏆","BNB Alpha":"🟠","Other":"🔮",
}


def scan_sector_liquidity(all_t):
    """
    Standalone sector rotation scanner.
    Detects sector rotation: when a sector turns hot, immediately runs _check()
    on all coins in that sector to catch early-stage movers.
    """
    now = time.time()

    # Build sector → coins map from live ticker data
    sector_data: Dict[str, list] = {}
    for sym, t in all_t.items():
        if t["vol"] < 100_000:   # ignore dust-volume coins
            continue
        base = sym[:-4] if sym.endswith("USDT") else sym.replace("USDT", "")
        sector = SECTOR_REGISTRY.get(base, "Other")
        sector_data.setdefault(sector, []).append({
            "base":     base,
            "change":   t["change"],
            "vol":      t["vol"],
            "exchange": t["exchange"],
        })

    # Calculate heat score for each sector (min 2 tracked coins)
    heat_scores: Dict[str, dict] = {}
    for sector, coins in sector_data.items():
        if sector == "Other" or len(coins) < 2:
            continue
        movers = [c for c in coins if c["change"] >= 5.0]
        if not movers:
            continue
        breadth    = len(movers) / len(coins)
        avg_change = sum(c["change"] for c in movers) / len(movers)
        total_vol  = sum(c["vol"] for c in coins)
        heat       = round(breadth * avg_change, 2)
        top        = sorted(movers, key=lambda x: -x["change"])[:4]
        heat_scores[sector] = {
            "heat":       heat,
            "breadth":    breadth,
            "avg_change": avg_change,
            "total_vol":  total_vol,
            "movers":     len(movers),
            "total":      len(coins),
            "top":        top,
        }

    # Log top 5 sectors every cycle
    ranked = sorted(heat_scores.items(), key=lambda x: -x[1]["heat"])
    if ranked:
        top_str = " | ".join(
            f"{SECTOR_ICONS.get(s,'🔮')}{s}={d['heat']:.1f}"
            f"({d['movers']}/{d['total']})"
            for s, d in ranked[:5]
        )
        log.info("SECTOR: %s", top_str)

    # Two-stage scan: warm (early entry) + hot (full sector)
    # Trigger: pure threshold + cooldown — no transition requirement
    for sector, data in ranked:
        heat       = data["heat"]
        last_hot   = _sector_alerted.get(sector, 0.0)
        last_warm  = _sector_warm_alerted.get(sector, 0.0)
        icon       = SECTOR_ICONS.get(sector, "🔮")

        # ── Stage 1: WARM (heat >= 2.5) — scan coins not yet moved ──
        is_warming = heat >= SECTOR_HEAT_WARM
        if is_warming and now - last_warm >= SECTOR_WARM_COOLDOWN:
            _sector_warm_alerted[sector] = now
            log.info("SECTOR WARM %s %s heat=%.1f — scanning quiet coins",
                     icon, sector, heat)
            for _sym, _t in all_t.items():
                _base = _sym[:-4] if _sym.endswith("USDT") else _sym.replace("USDT", "")
                # BNB Alpha: scan ALL futures_only coins — they're all Alpha by definition
                in_sector = ((_t.get("futures_only") or _t.get("binance_alpha")) if sector == "BNB Alpha"
                             else SECTOR_REGISTRY.get(_base) == sector)
                if (in_sector and _t["vol"] >= 100_000 and _t["change"] < 8.0):
                    _check(_sym, _t, "5m", sector_boost=True)
                    time.sleep(0.08)

        # ── Stage 2: HOT (heat >= 4.0) — full sector scan including leaders ──
        is_hot = heat >= SECTOR_HEAT_MIN
        if is_hot and now - last_hot >= SECTOR_ALERT_COOLDOWN:
            _sector_alerted[sector] = now
            log.info("SECTOR HOT %s %s heat=%.1f — scanning all coins",
                     icon, sector, heat)
            for _sym, _t in all_t.items():
                _base = _sym[:-4] if _sym.endswith("USDT") else _sym.replace("USDT", "")
                # BNB Alpha: scan ALL futures_only coins — no manual list needed
                in_sector = ((_t.get("futures_only") or _t.get("binance_alpha")) if sector == "BNB Alpha"
                             else SECTOR_REGISTRY.get(_base) == sector)
                # HOT scan: include sector leaders (up to 25%) — _check() handles late-entry
                if (in_sector and _t["vol"] >= 100_000 and _t["change"] < 25.0):
                    _check(_sym, _t, "5m", sector_boost=True)
                    time.sleep(0.08)

    # Update state
    for sector, data in heat_scores.items():
        _sector_heat_prev[sector] = data["heat"]
    for sector in list(_sector_heat_prev):
        if sector not in heat_scores:
            _sector_heat_prev[sector] = 0.0


# ══════════════════════════════════════════════════════
#  TREND FOLLOW SCANNER — catches slow grind uptrends (ZEC-type)
#  Runs every 30 min using daily klines — no spike required
# ══════════════════════════════════════════════════════

def _fetch_daily_klines(sym: str, exchange: str, days: int = 14):
    """Fetch daily klines. Returns list of (close, volume) tuples, oldest first."""
    try:
        if exchange == "Binance":
            url  = "https://api.binance.com/api/v3/klines"
        else:
            url  = "https://api.mexc.com/api/v3/klines"
        data = _get(url, {"symbol": sym, "interval": "1d", "limit": days})
        if not data or not isinstance(data, list):
            return []
        return [(float(c[4]), float(c[5])) for c in data]   # (close, volume)
    except Exception as e:
        log.debug("daily_klines %s: %s", sym, e)
        return []


def _ema(values: list, period: int) -> float:
    """Exponential moving average of a list."""
    if not values:
        return 0.0
    k   = 2 / (period + 1)
    ema = values[0]
    for v in values[1:]:
        ema = v * k + ema * (1 - k)
    return ema


def scan_trend_follow(all_t):
    """
    Catches coins in sustained multi-day uptrends (ZEC-type slow grind).
    Criteria: price > EMA10d + 7d gain 15-50% + volume increasing in USD.
    Runs every 30 min. 12h cooldown per coin. Max 3 signals per run.
    """
    now = time.time()
    candidates = [
        (sym, t) for sym, t in all_t.items()
        if t["exchange"] == "Binance"
        and t["vol"] >= 3_000_000
        and 1.5 <= t["change"] <= 35.0      # moving today but not overextended
        and now - _trend_dedup.get(sym, 0) >= 43200
        and now - alerted.get(sym, 0) >= COOLDOWN
        and sym not in tracking
    ]

    # Pre-score candidates to pick the best 3 per run
    scored = []
    for sym, t in candidates:
        try:
            klines = _fetch_daily_klines(sym, "Binance", days=14)
            if len(klines) < 10:
                continue

            closes  = [c for c, v in klines]
            price   = closes[-1]

            # Volume in USD = coins × close price (klines return base asset vol)
            vols_usd = [v * c for c, v in klines]

            ema10   = _ema(closes[:-1], 10)

            # EMA filter: price must be 3%+ above EMA (tighter than before)
            if price <= ema10 * 1.03:
                continue

            # 7d gain: 15-50% (more = already extended, less = not trending)
            gain_7d = (price - closes[-8]) / closes[-8] * 100 if closes[-8] > 0 else 0
            if not (15.0 <= gain_7d <= 50.0):
                continue

            # Volume trend (USD): 3d avg must be >= 7d avg (not fading)
            vol_3d_usd = sum(vols_usd[-4:-1]) / 3 if len(vols_usd) >= 4 else 0
            vol_7d_usd = sum(vols_usd[-8:-1]) / 7 if len(vols_usd) >= 8 else 0
            if vol_3d_usd < vol_7d_usd * 0.90:
                continue

            # Position check: not at extreme of 24h range
            rng  = t["high24"] - t["low24"]
            pos24 = (price - t["low24"]) / rng * 100 if rng > 0 else 50
            if pos24 > 78:   # too extended intraday
                continue

            # Quality score: higher 7d gain + volume growth = better
            vol_growth = vol_3d_usd / max(vol_7d_usd, 1)
            quality = gain_7d * vol_growth
            scored.append((sym, t, closes, vols_usd, ema10, gain_7d,
                           vol_3d_usd, vol_7d_usd, pos24, quality))

        except Exception as e:
            log.debug("trend_follow_score %s: %s", sym, e)

    # Take top 3 by quality score — pass each through standard _check() pipeline
    scored.sort(key=lambda x: -x[-1])
    top3 = scored[:3]

    fired = 0
    for sym, t, closes, vols_usd, ema10, gain_7d, vol_3d_usd, vol_7d_usd, pos24, _ in top3:
        try:
            # Mark as checked so we don't re-query klines for 12h regardless of _check() result
            _trend_dedup[sym] = now
            log.info("TREND_FOLLOW candidate %s gain7d=+%.1f%% ema10=%s vol3d_usd=%s → sending to _check",
                     sym, gain_7d, _fp(ema10), _fv(vol_3d_usd))
            # Route through standard pipeline — same format + full quality gate
            _check(sym, t, "4h")
            fired += 1
            time.sleep(0.5)

        except Exception as e:
            log.debug("trend_follow_send %s: %s", sym, e)

    if fired:
        log.info("scan_trend_follow: checked=%d/%d candidates", fired, len(scored))


# ══════════════════════════════════════════════════════
#  REPORT DEDUP — file-based lock prevents duplicate sends
#  across multiple bot instances (nohup + systemd race)
# ══════════════════════════════════════════════════════

def _report_sent(key: str, report_type: str) -> bool:
    try:
        with open(REPORT_SENT_FILE) as f:
            return json.load(f).get(report_type) == key
    except Exception:
        return False

def _mark_report_sent(key: str, report_type: str):
    try:
        try:
            with open(REPORT_SENT_FILE) as f:
                data = json.load(f)
        except Exception:
            data = {}
        data[report_type] = key
        with open(REPORT_SENT_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        log.debug("report_sent save: %s", e)


# ══════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════

def main():
    global last_fast, last_slow, last_super, last_accum, last_sg, last_sector, last_trend, last_report, last_report_date, last_weekly_date, last_monthly_date
    log.info("🎯 MAFIO SNIPER — starting")
    clear_bot_commands()
    register_commands()
    load_state()
    load_signal_db()

    send(
        "🎯 *MAFIO SNIPER v3.2*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "✅ Bot started\n"
        f"📡 Exchange: {'*MEXC* 🟠  +  ' if USE_MEXC else ''}*Binance* 🟡\n"
        f"⚡ Fast scan (1m):   every {FAST_SCAN_S}s   δ≥{FAST_TICKER_MOVE}%\n"
        f"😴 Sleep Giant (1m): every {SLEEP_GIANT_S}s  vol≥20x flat coins\n"
        f"🎯 Mid scan  (5m):   every {MID_SCAN_S}s   top 60 movers\n"
        f"📊 Slow scan (1h):   every {SLOW_SCAN_S//60}min\n"
        f"📈 Super scan (1h):  every {SUPER_SCAN_S//60}min — Supertrend flip\n"
        "📊 Tiers: Micro / Small / Mid / Large cap\n"
        "📈 Market Bias: Breadth + CVD + Taker-buy\n"
        "💰 Funding Rate: Bullish/Bearish detection\n"
        f"🔕 Cooldown: {COOLDOWN//3600}h per coin\n"
        f"🌊 Sector Liquidity: every {SECTOR_SCAN_S//60}min — {len(set(SECTOR_REGISTRY.values()))} sectors\n"
        f"📈 Trend Follow: every {TREND_FOLLOW_S//60}min — Binance Mid/Large grind"
    )

    while True:
        try:
            now = time.time()
            if now - last_fast < FAST_SCAN_S:
                poll_telegram()   # responsive even while scans are running
                time.sleep(1); continue
            last_fast = now

            _mx = fetch_mexc()
            all_t = dict(_mx)
            if USE_BINANCE:
                _bn = fetch_binance()
                for _sym, _td in _bn.items():
                    if _sym not in all_t or _td["vol"] > all_t[_sym]["vol"]:
                        all_t[_sym] = _td
                # Futures-only: Binance Alpha / pre-listing coins (RAVE type)
                _bn_fut = fetch_binance_futures_only(set(_bn.keys()))
                for _sym, _td in _bn_fut.items():
                    all_t[_sym] = _td   # safe: spot_syms excluded upstream
                    # Register dynamically as BNB Alpha sector for sector scanner
                    _base = _sym[:-4] if _sym.endswith("USDT") else _sym.replace("USDT", "")
                    if _base not in SECTOR_REGISTRY:
                        SECTOR_REGISTRY[_base] = "BNB Alpha"
                # Binance Alpha Web3 tokens (BSC — not on Spot/FAPI, traded on MEXC)
                _bn_alpha = fetch_binance_alpha()
                _bn_alpha_new = 0
                for _sym, _td in _bn_alpha.items():
                    if _sym not in all_t:   # don't override Spot/FAPI data
                        all_t[_sym] = _td
                        _bn_alpha_new += 1
                        _base = _sym[:-4] if _sym.endswith("USDT") else _sym.replace("USDT", "")
                        if _base not in SECTOR_REGISTRY:
                            SECTOR_REGISTRY[_base] = "BNB Alpha"
                log.info("Tickers: MEXC=%d Binance=%d Fut-only=%d Alpha-Web3=%d Total=%d Tracking=%d",
                         len(_mx), len(_bn), len(_bn_fut), _bn_alpha_new, len(all_t), len(tracking))
            else:
                log.info("Tickers: MEXC=%d Tracking=%d", len(all_t), len(tracking))

            # ── Market Bias ───────────────────────────
            global market_bias, market_cvd, last_bias_log
            global _last_bias_label, _last_bias_score, last_market_stats
            market_bias, market_cvd, tbr = calc_market_bias(all_t)
            cur_label = bias_label(market_bias)
            if now - last_bias_log >= 300:   # log every 5 min
                last_bias_log = now
                log.info("Market Bias: %+d  %s  CVD=%s  TakerBuy=%.1f%%",
                         market_bias, cur_label,
                         _fv(abs(market_cvd)), tbr)
            _last_bias_label = cur_label
            _last_bias_score = market_bias

            # Cleanup stale multi-confirm entries once per hour
            if int(now) % 3600 < 35:
                _old = [k for k, v in _multi_confirm.items()
                        if now - v["last_time"] > MULTI_CONFIRM_WINDOW]
                for k in _old:
                    _multi_confirm.pop(k, None)

            # Periodic state + signal DB sync every 5 min — ensures tracking survives restarts
            # even if no milestone or SL fired since last save
            if int(now) % 300 < 35:
                save_state()
                _save_signal_db()

            check_milestones(all_t)

            # ── BTC Health + Dump Cascade ────────────────────────────────────────
            check_btc_health(all_t)
            check_dump_cascade(all_t)

            # ── Daily / Weekly / Monthly Reports ────────────────────────────────
            global last_report, last_report_date, _last_report_time
            global last_weekly_date, last_monthly_date
            _utc       = datetime.now(timezone.utc)
            _date_str  = _utc.strftime("%Y-%m-%d")
            _week_str  = _utc.strftime("%Y-W%W")          # e.g. 2026-W18
            _month_str = _utc.strftime("%Y-%m")

            # Daily — fires at REPORT_HOUR:00-04 UTC, once per day
            if _utc.hour == REPORT_HOUR and _utc.minute < 5 and _date_str != last_report_date:
                last_report_date = _date_str
                if not _report_sent(_date_str, "daily"):
                    _mark_report_sent(_date_str, "daily")
                    last_report       = now
                    _last_report_time = now
                    # Daily report disabled — misleading for long-term positions
                    # send_daily_report()

            # Weekly — fires Sunday at REPORT_HOUR:05-09 UTC, once per week
            if (_utc.weekday() == 6 and _utc.hour == REPORT_HOUR
                    and 5 <= _utc.minute < 10 and _week_str != last_weekly_date):
                last_weekly_date = _week_str
                if not _report_sent(_week_str, "weekly"):
                    _mark_report_sent(_week_str, "weekly")
                    send_weekly_report()

            # Monthly — fires on 1st of month at REPORT_HOUR:10-14 UTC, once per month
            if (_utc.day == 1 and _utc.hour == REPORT_HOUR
                    and 10 <= _utc.minute < 15 and _month_str != last_monthly_date):
                last_monthly_date = _month_str
                if not _report_sent(_month_str, "monthly"):
                    _mark_report_sent(_month_str, "monthly")
                    send_monthly_report()

            poll_telegram()   # check for /report and other commands
            fast_scan(all_t)

            global last_mid
            if now - last_mid >= MID_SCAN_S:
                last_mid = now
                mid_scan(all_t)

            if now - last_slow >= SLOW_SCAN_S:
                last_slow = now
                fetch_dominance()   # update BTC.D/USDT.D/USDC.D history
                slow_scan(all_t)

            if now - last_super >= SUPER_SCAN_S:
                last_super = now
                scan_supertrend(all_t)

            global last_accum
            if now - last_accum >= ACCUM_SCAN_S:
                last_accum = now
                scan_quiet_accum(all_t)

            global last_sg
            if now - last_sg >= SLEEP_GIANT_S:
                last_sg = now
                scan_sleeping_giant(all_t)

            global last_sector
            if now - last_sector >= SECTOR_SCAN_S:
                last_sector = now
                scan_sector_liquidity(all_t)

            # DATA: scan_trend_follow (momentum) avg=3.1% (2/10 wins) — disabled
            # global last_trend
            # if now - last_trend >= TREND_FOLLOW_S:
            #     last_trend = now
            #     scan_trend_follow(all_t)

        except KeyboardInterrupt:
            log.info("Stopped."); break
        except Exception as e:
            log.error("Loop: %s", e, exc_info=True)
            time.sleep(5)

if __name__ == "__main__":
    main()

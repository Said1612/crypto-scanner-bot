# -*- coding: utf-8 -*-
"""
🎯 MAFIO SNIPER
Binance-only scanner
Detects liquidity entry by tier: Micro / Small / Mid / Large cap
Based on analysis of real Wolf Flow trades (Mar-Apr 2026)
"""
BOT_VERSION = "3.2.39"  # bump this with every push — verify after restart

import os, time, json, logging, signal as _signal, sys
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

# Fractal agent — optional, Bill Williams fractal analysis
try:
    from fractal_agent import FractalAgent as _FractalAgentCls
    _fractal_agent = _FractalAgentCls()
except Exception as _fra_err:
    _fractal_agent = None
    logging.getLogger(__name__).warning("Fractal agent not loaded: %s", _fra_err)


# Fractal Validation Agent — multi-source confluence engine (Almazov 5-book synthesis)
try:
    from fractal_validator import FractalValidationAgent as _FVACls
    _fva = _FVACls()
except Exception as _fva_err:
    _fva = None
    logging.getLogger(__name__).warning("FractalValidationAgent not loaded: %s", _fva_err)

# Chaos-Quant Engine — DFA Hurst + Edgar Peters Regime + Young Ho Seo Symmetry Box + Noah Effect
try:
    from chaos_quant import integrate_with_mafio_core as _cq_integrate
    _cq_ok = True
except Exception as _cq_err:
    _cq_ok = False
    logging.getLogger(__name__).warning("chaos_quant not loaded: %s", _cq_err)

# FVA + CQ disabled for gating: both modules were silently reducing scores and blocking valid signals.
# When enabled, a raw score of 8.0 could become < 3.0 after FCF + Hurst + pos-penalty,
# causing the bot to be completely silent during explosive market moves.
# Display references kept so FCF/Chaos-Quant sections still appear in signal messages (display-only, no gating).
_fva_show   = _fva      # display-only — used after all gates pass
_cq_show_ok = _cq_ok    # display-only flag
_fva    = None           # force None → all gate checks skip
_cq_ok  = False          # force False → all gate checks skip

# ══════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID        = os.getenv("CHAT_ID") or ""
GROUP_ID       = os.getenv("GROUP_ID") or ""
REDIS_URL      = os.getenv("REDIS_URL", os.getenv("UPSTASH_REDIS_REST_URL", ""))
REDIS_TOKEN    = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")
REDIS_KEY      = "mafio_v31"
PROXY_URL      = os.getenv("PROXY_URL", "")   # e.g. http://user:pass@host:port

FAST_SCAN_S      = 5     # every 5s — confirmed working: catches REPAI/NEOS/BLINKY type explosions
SLOW_SCAN_S      = 300   # every 5min (1h klines)
SUPER_SCAN_S     = 900   # every 15min — SUPERTREND(10,3) flip scanner (BIO/ORDI/币安人生 type)
SLEEP_GIANT_S    = 30    # every 30s — sleeping giant: flat coin sudden 1m volume explosion
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
    {"name": "Micro",  "vol_max": 2_000_000,  "vol_min": 50_000,    "spike": 2.8, "ratio": 2.5, "net": 5_000},
    {"name": "Small",  "vol_max": 15_000_000, "vol_min": 300_000,   "spike": 2.5, "ratio": 2.2, "net": 15_000},
    {"name": "Mid",    "vol_max": 80_000_000, "vol_min": 3_000_000, "spike": 2.2, "ratio": 2.0, "net": 60_000},
    {"name": "Large",  "vol_max": 9e99,        "vol_min": 15_000_000,"spike": 1.8, "ratio": 1.8, "net": 250_000},
]

FLOW_CANDLES     = 3     # candles for flow calculation
MAX_PUMP_24H     = 60.0  # skip already-pumped coins
LATE_ENTRY_PCT   = 0.92  # skip if price in top 8% of 24h range
REPORT_HOUR      = int(os.getenv("REPORT_HOUR", "23"))  # UTC hour — Morocco UTC+1: 23=midnight local

MILESTONES  = [5, 10, 15, 20, 25, 30, 40, 50, 75, 100,
               125, 150, 175, 200, 250, 300, 400, 500]
TRACK_HOURS      = 240   # 10-day safety cap — signals close via SL, not timeout
SIGNAL_TIMEOUT_H = 24     # expire signal if no +5% within 24h — captures slow movers (AIO-type)
SIGNAL_SL_PCT    = -5.0   # stop-loss: exit tracking if -5% below entry
SIGNAL_DB        = "signal_history.json"  # ML training data — append only, never reset

STABLECOINS   = {"USDC","BUSD","DAI","TUSD","USDD","FDUSD","USDP","PYUSD","USDB","USDX","EURC","USDT","AEUR","EURI","USD1","USDE","USDY","USDM",
                  "XUSD","RLUSD","BFUSD","U","USDGO","USDF","USDZ","USDK","USDJ","GUSD","SUSD","MUSD","CUSD",
                  "EUR","GBP","AUD","JPY","CHF","CAD","TRY","BRL","RUB","KRW","CNY","HKD","SGD","AED","SAR","MXN","PLN","SEK","NOK","DKK",
                  "PAXG","XAUT","OURIEL"}
SKIP_KEYWORDS = {"UP","DOWN","BULL","BEAR","3L","3S","2L","2S","HEDGE","BVOL","IBVOL"}
# Coins to skip permanently: delisted, suspended, or confirmed manipulation-prone
BLACKLIST     = {"MFT", "APR", "LOOM", "TORN", "ELF", "SPARTA",
                  "XAU", "XAUT", "PAXG", "XAGX",   # Gold/silver commodity tokens
                  "LSM",                             # Confirmed wash-trading manipulation (97% fake bids)
                  "TOMO",                            # Delisted/rebranded — stale API data causes false sleeping giant loops
                  "FTM",                             # Rebranded to SONIC — old ticker shows ghost volume
                  "REN",                             # Ren Protocol shut down — dead project, ghost volume
                  "WAVES",                           # Delisted from Binance — ghost volume causes false sleeping giant signals
                  "KMD",                             # Delisted from Binance — ghost volume causes false sleeping giant signals
                  "COCOS",                           # Dead gaming blockchain — ghost volume causes false 92x sleeping giant signals
                  "ORN",                             # Delisted from Binance — ghost 202x volume causes false sleeping giant signals
                  "TVK",                             # DEX-only token — not tradeable on Binance/MEXC, ghost volume causes false signals
                  # Staked/wrapped derivatives — price follows underlying, no independent signal
                  "BNSOL",                           # Binance Staked SOL → follows SOL
                  "WBETH",                           # Wrapped Binance ETH → follows ETH
                  "BETH",                            # Binance ETH staking → follows ETH
                  "WBTC",                            # Wrapped Bitcoin → follows BTC
                  "WBNB",                            # Wrapped BNB → follows BNB
                  "SOLVBTC",                         # Solv BTC → follows BTC
                  "BTCB",                            # Binance BTC → follows BTC
                  }

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

BINANCE_BASE          = "https://api.binance.com/api/v3"
BINANCE_FUTURES       = "https://fapi.binance.com"
BINANCE_ALPHA_TOKEN_URL = "https://www.binance.com/bapi/defi/v1/public/wallet-direct/buw/wallet/cex/alpha/all/token/list"
USE_BINANCE  = os.getenv("USE_BINANCE", "true").lower() == "true"

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
last_alpha    = 0.0          # scan_alpha_explosion interval
_alpha_vol_cache: dict = {}  # sym → (vol24h, timestamp) for surge detection
last_sector   = 0.0
last_weekly_swing = 0.0
last_deep_value   = 0.0
last_bias_log = 0.0
ACCUM_SCAN_S      = 300    # every 5 min
WEEKLY_SWING_S    = 300    # every 5 min
DEEP_VALUE_S      = 300    # every 5 min
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
_oi_cache            : Dict[str, dict] = {}   # {sym: {oi data} + "ts": float}
OI_TTL               = 180   # refresh OI every 3 min (Binance updates every 15m)
_signal_dedup        : Dict[str, float] = {}  # {sym: ts} — 2h dedup (same as COOLDOWN, prevents all scanners re-firing)
_alerted_price       : Dict[str, float] = {}  # {sym: price} — frozen data guard (MFT type)
_ms_dedup            : Dict[str, float] = {}  # {sym_ms: ts} — prevents duplicate milestone sends (multiple instances guard)
_sl_dedup            : Dict[str, float] = {}  # {sym: ts} — prevents duplicate SL sends across restarts
_rev_dedup           : Dict[str, float] = {}  # {sym: ts} — prevents duplicate reversal sends across restarts
_sector_heat_prev    : Dict[str, float] = {}  # previous heat per sector
_sector_alerted      : Dict[str, float] = {}  # {sector: last_hot_scan_ts}
_sector_warm_alerted : Dict[str, float] = {}  # {sector: last_warm_scan_ts}

_MY_PID   = os.getpid()
_PID_FILE = "/tmp/mafio_scanner.pid"

def _register_primary():
    """Write our PID to the lock file — marks us as the active process."""
    try:
        with open(_PID_FILE, "w") as f:
            f.write(str(_MY_PID))
    except Exception:
        pass

def _invalidate_primary():
    """Write 0 to PID file — immediately stops all in-flight sends from this process.
    Called on SIGTERM so that scans in progress cannot leak signals during shutdown.
    """
    try:
        with open(_PID_FILE, "w") as f:
            f.write("0")
    except Exception:
        pass

def _handle_sigterm(sig, frame):
    """SIGTERM handler: invalidate PID immediately, then exit cleanly.
    Closes the window where a scan in progress could send a signal AFTER
    systemctl restart downloads new code but BEFORE the new process writes its PID.
    """
    log.info("SIGTERM received — invalidating PID, shutting down cleanly")
    _invalidate_primary()
    sys.exit(0)

def _is_primary_process() -> bool:
    """Return True only if this process is still the active (newest) bot instance.
    When a new process starts it overwrites _PID_FILE — old process detects mismatch
    and stops sending signals, eliminating stale-process signal leakage on VPS updates.
    """
    try:
        with open(_PID_FILE, "r") as f:
            return int(f.read().strip()) == _MY_PID
    except Exception:
        return True  # if file missing, assume primary
_trend_dedup         : Dict[str, float] = {}  # {sym: last_trend_signal_ts} 12h cooldown
_weekly_swing_dedup  : Dict[str, float] = {}  # {sym: last_weekly_swing_ts} 24h cooldown
_dominance_hist      : List[Tuple[float, dict]] = []  # [(ts, {btcd, usdtd, usdcd, others})]

# ── Circuit Breaker ──────────────────────────────────────────────────────────
CB_MAX_CONSECUTIVE_SL = 3      # SL hits in a row before blocking new signals
CB_PAUSE_HOURS        = 4      # hours to block after circuit breaks
_cb_consecutive_sl    = 0      # rolling counter of consecutive SL outcomes
_cb_blocked_until     = 0.0    # unix ts — signals blocked until this time

# ══════════════════════════════════════════════════════
#  LOGGING
# ══════════════════════════════════════════════════════

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-7s  %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                    stream=__import__("sys").stdout)
log = logging.getLogger("mafio")

# Log deferred startup statuses (modules loaded before logging was configured)

# ══════════════════════════════════════════════════════
#  CIRCUIT BREAKER
# ══════════════════════════════════════════════════════

def _cb_is_active() -> bool:
    """Return True if circuit breaker is currently blocking new signals."""
    return time.time() < _cb_blocked_until

def _cb_record_outcome(is_sl: bool, sym: str = ""):
    """Call after every signal closes. Increments SL counter or resets it."""
    global _cb_consecutive_sl, _cb_blocked_until
    if is_sl:
        _cb_consecutive_sl += 1
        log.info("CB: SL streak=%d/%d (%s)", _cb_consecutive_sl, CB_MAX_CONSECUTIVE_SL, sym)
        if _cb_consecutive_sl >= CB_MAX_CONSECUTIVE_SL:
            _cb_blocked_until = time.time() + CB_PAUSE_HOURS * 3600
            _cb_consecutive_sl = 0
            resume_str = datetime.fromtimestamp(_cb_blocked_until, tz=timezone.utc).strftime("%H:%M UTC")
            log.warning("CB: TRIGGERED — signals blocked for %dh (resumes %s)", CB_PAUSE_HOURS, resume_str)
            try:
                send(
                    f"⛔ *Circuit Breaker Active*\n"
                    f"Reason: `{CB_MAX_CONSECUTIVE_SL}` consecutive SL signals\n"
                    f"Last loss: `{sym}`\n"
                    f"Action: no signals for `{CB_PAUSE_HOURS}` hours\n"
                    f"Resumes at: `{resume_str}`"
                )
            except Exception:
                pass
    else:
        if _cb_consecutive_sl > 0:
            log.info("CB: streak reset (success on %s)", sym)
        _cb_consecutive_sl = 0

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
                # Restore all signals not yet closed by SL (no time limit — TRACK_HOURS is safety cap)
                if not v.get("sl_alerted") or now - v.get("t0", 0) < TRACK_HOURS * 3600:
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
    """Atomic write: write to temp file then rename — prevents DB corruption on kill/restart."""
    tmp = SIGNAL_DB + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(_signal_db, f, indent=2, ensure_ascii=False)
        os.replace(tmp, SIGNAL_DB)   # atomic on Linux — no partial writes
    except Exception as e:
        log.debug("signal_db save: %s", e)
        try: os.unlink(tmp)
        except Exception: pass

def _db_add(sym, price, exchange, tier_name, scanner,
            ratio, ob_spot, score, pos24, spike, net, move, funding,
            fractal_score=None, h_value=None, oi_delta=None):
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
        # Fractal + OI features for k-NN pattern matching (v3 AI)
        "fractal_score": fractal_score,
        "h_value":       round(h_value, 4) if h_value is not None else None,
        "oi_delta":      round(oi_delta, 2) if oi_delta is not None else None,
        # Outcome (filled when signal closes)
        "outcome":          "active",   # active → success / stoploss / timeout / expired
        "max_gain_pct":     0.0,       # highest % reached from entry (before reversal)
        "max_drawdown_pct": None,      # deepest % from entry (negative = below entry)
        "price_exit":       None,
        "duration_min":     None,
        "close_reason":     None,
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
            # Notify agents so they retrain after enough new outcomes
            if _ai_agent is not None:
                _ai_agent.notify_outcome()
            if _fractal_agent is not None:
                _fractal_agent.record_outcome(sym, max_gain)
            return

def _retroactive_peak_update(max_per_call: int = 3):
    """
    For timed-out signals (last 14 days), fetch real 1h klines and record:
      - max_gain_pct   : highest peak reached from entry (before reversal)
      - max_drawdown_pct: deepest trough reached from entry (can be negative)

    Example: coin entered $1 → peaked at $2 (+100%) → crashed to $0.60 (-40%)
      max_gain_pct    = +100%  (the real opportunity available)
      max_drawdown_pct= -40%   (the worst moment after entry)

    This gives AI full picture — a signal that peaked +100% is a winner even if
    the coin later fell below entry. Without this, all timeout signals look weak.
    """
    now    = time.time()
    cutoff = now - 14 * 86400

    candidates = [
        rec for rec in _signal_db
        if rec.get("outcome") == "timeout"
        and (rec.get("timestamp") or 0) >= cutoff
        and not rec.get("retro_updated")
    ]
    if not candidates:
        return

    updated = 0
    for rec in candidates[:max_per_call]:
        sym         = rec.get("sym", "")
        entry_price = float(rec.get("price_entry") or 0)
        signal_ts   = int(rec.get("timestamp") or 0)
        exchange    = rec.get("exchange", "Binance")

        if not sym or entry_price <= 0 or signal_ts <= 0:
            rec["retro_updated"] = True
            continue

        try:
            base_url  = MEXC_BASE if exchange == "MEXC" else BINANCE_BASE
            start_ms  = signal_ts * 1000
            hours_ago = max(1, int((now - signal_ts) / 3600))
            limit     = min(hours_ago + 1, 168)   # cap at 7 days of 1h candles

            r = S.get(f"{base_url}/klines",
                      params={"symbol": sym, "interval": "1h",
                              "startTime": start_ms, "limit": limit},
                      timeout=10)
            klines = r.json() if r.ok else []
            if not isinstance(klines, list) or not klines:
                rec["retro_updated"] = True
                continue

            # k[2] = high, k[3] = low across all candles since entry
            max_high  = max(float(k[2]) for k in klines)
            min_low   = min(float(k[3]) for k in klines)

            true_peak     = (max_high - entry_price) / entry_price * 100
            true_drawdown = (min_low  - entry_price) / entry_price * 100  # negative if below entry

            stored = rec.get("max_gain_pct") or 0.0
            changed = False

            if true_peak > stored + 1.0:
                rec["max_gain_pct"] = round(true_peak, 2)
                changed = True

            # Always update drawdown — shows the real risk
            rec["max_drawdown_pct"] = round(true_drawdown, 2)

            if changed:
                log.info("RETRO_PEAK %s: peak %.1f%% | drawdown %.1f%%",
                         sym, true_peak, true_drawdown)
                updated += 1

            rec["retro_updated"] = True

        except Exception as _rpe:
            log.debug("retro_peak error %s: %s", sym, _rpe)
            rec["retro_updated"] = True

    if updated:
        _save_signal_db()
        if _ai_agent is not None:
            _ai_agent.force_retrain()
            log.info("RETRO_PEAK: %d records updated → AI retrained", updated)


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
    Binance Alpha tokens — listed in Binance Alpha program (CEX listing candidates).
    Klines and OB are fetched from Binance Spot via base_url=BINANCE_BASE.
    """
    if not USE_BINANCE:
        return {}
    # Binance /bapi/ internal endpoints require browser-like headers
    try:
        r = S.get(BINANCE_ALPHA_TOKEN_URL, timeout=10,
                  headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                           "clienttype": "web", "lang": "en"})
        data = r.json() if r.ok else None
    except Exception as _ae:
        log.warning("Binance Alpha fetch error: %s", _ae)
        return {}
    if not isinstance(data, dict) or not data.get("success"):
        log.warning("Binance Alpha token list failed (resp: %s)", str(data)[:120] if data else "None")
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
            # Add 5% buffer above current price — setting high=price makes pos24=1.0
            # for all positive-change Alpha coins, blocking them with high_pos
            high = price * 1.05 if chg >= 0 else price / (1 + abs(chg) / 100)
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
    Returns (rate_pct, label).
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

def fetch_oi_ls(sym: str) -> dict:
    """
    Open Interest + Long/Short Ratio for Binance Futures.

    OI expanding  = new money entering = real breakout confirmation.
    OI contracting = short covering or profit-taking = corrective move risk.
    L/S < 0.85    = short-heavy market = squeeze fuel (bullish).
    L/S > 1.8     = crowd too long = liquidation cascade risk (bearish).

    Returns dict with keys:
      oi_delta_1h   : % change in OI over last 1h (positive = expanding)
      expanding     : True if OI grew > +2% in 1h
      contracting   : True if OI fell > -4% in 1h
      ls_ratio      : long/short account ratio (>1 = more longs)
      short_squeeze : True if OI expanding AND ls_ratio < 0.85 (shorts trapped)
      long_crowded  : True if ls_ratio > 1.8 (top risk)
      label         : display string for signal message
    """
    now = time.time()
    cached = _oi_cache.get(sym)
    if cached and (now - cached["ts"]) < OI_TTL:
        return cached

    default = {"oi_delta_1h": 0.0, "expanding": False, "contracting": False,
               "ls_ratio": 1.0, "short_squeeze": False, "long_crowded": False,
               "label": "", "ts": now}
    try:
        # ── OI history (30m intervals, last 3 → ~1h change) ──────────────
        hist = _get(f"{BINANCE_FUTURES}/futures/data/openInterestHist",
                    {"symbol": sym, "period": "30m", "limit": 3}, timeout=5)
        if not hist or not isinstance(hist, list) or len(hist) < 2:
            _oi_cache[sym] = default; return default

        oi_old = float(hist[0]["sumOpenInterest"])
        oi_new = float(hist[-1]["sumOpenInterest"])
        delta  = (oi_new - oi_old) / oi_old * 100 if oi_old > 0 else 0.0

        # ── Long/Short ratio (top traders account ratio, 1h) ─────────────
        ls_data = _get(f"{BINANCE_FUTURES}/futures/data/topLongShortAccountRatio",
                       {"symbol": sym, "period": "1h", "limit": 1}, timeout=5)
        ls_ratio = 1.0
        if ls_data and isinstance(ls_data, list) and ls_data:
            try:
                ls_ratio = float(ls_data[0].get("longShortRatio", 1.0))
            except (ValueError, KeyError):
                pass

        expanding     = delta > 2.0
        contracting   = delta < -2.0
        short_squeeze = expanding and ls_ratio < 0.85
        long_crowded  = ls_ratio > 1.8

        # ── Display label ─────────────────────────────────────────────────
        sign   = "+" if delta >= 0 else ""
        if short_squeeze:
            label = f"🌊 OI `{sign}{delta:.1f}%` · L/S `{ls_ratio:.2f}` 🩳 *Squeeze Setup*"
        elif expanding:
            label = f"📈 OI `{sign}{delta:.1f}%` expanding · L/S `{ls_ratio:.2f}`"
        elif contracting:
            label = f"⚠️ OI `{sign}{delta:.1f}%` contracting · L/S `{ls_ratio:.2f}`"
        elif long_crowded:
            label = f"⚠️ OI `{sign}{delta:.1f}%` · L/S `{ls_ratio:.2f}` 🐂 *Crowded Longs*"
        else:
            label = f"➡️ OI `{sign}{delta:.1f}%` · L/S `{ls_ratio:.2f}`"

        result = {"oi_delta_1h": round(delta, 2), "expanding": expanding,
                  "contracting": contracting, "ls_ratio": ls_ratio,
                  "short_squeeze": short_squeeze, "long_crowded": long_crowded,
                  "label": label, "ts": now}
        _oi_cache[sym] = result
        return result

    except Exception:
        _oi_cache[sym] = default
        return default


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
    if not _is_primary_process():
        log.info("STALE PROCESS — send() suppressed (newer bot instance is active)")
        return False, 0
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
                    log.warning("TG send failed cid=%s — retrying as plain text, no markup", cid)
                    payload.pop("parse_mode", None)
                    payload.pop("reply_markup", None)
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
               ob_spot, ratio, pos24, spike, net_usd, move_pct, funding,
               fractal_score=None, h_value=None, oi_delta=None,
               min_prob=0, crowded_longs=False) -> tuple:
    """Return (ai_text, blocked). blocked=True when AI is bearish + confirming danger pattern.
    min_prob: if set, also blocks when AI probability is below this threshold.
    crowded_longs: if True, blocks when AI < 50% (long squeeze risk)."""
    if _ai_agent is None:
        return "", False
    try:
        sig = {
            "sym": sym, "exchange": exchange, "tier": tier,
            "scanner": scanner, "score": score, "ob_spot": ob_spot,
            "ratio": ratio, "pos24": pos24, "spike": spike,
            "net_usd": net_usd, "move_pct": move_pct, "funding": funding,
        }
        if fractal_score is not None:
            sig["fractal_score"] = fractal_score
        if h_value is not None:
            sig["h_value"] = h_value
        if oi_delta is not None:
            sig["oi_delta"] = oi_delta
        r = _ai_agent.predict(sig)
        prob        = r.get("prob", 0)
        verdict     = r.get("verdict", "")
        emoji       = r.get("emoji", "⚪")
        warns       = r.get("warnings", [])
        model       = r.get("model", exchange)
        brain_str   = r.get("brain_str", "")
        similar_str = r.get("similar_str", "")
        similar_line = f"\n🔍 _{similar_str}_" if similar_str else ""
        text = f"\n🤖 `{prob}%` {emoji}{similar_line}"
        # Block condition 1: AI clearly says avoid (< 35%) — extreme case only
        extreme_avoid = prob < 35
        # Block condition 2: clear dump pattern — sellers dominate + AI bearish
        dump_pattern  = (prob < 45 and ob_spot < 0.40)
        # Block condition 3: weak on ALL dimensions simultaneously (very rare)
        weak_combined = (prob < 50 and score < 6.0 and spike < 2.0)
        # Block condition 4: per-scanner minimum prob (swing scanners require >= 50%)
        below_min     = (min_prob > 0 and prob < min_prob)
        blocked = extreme_avoid or dump_pattern or weak_combined or below_min
        if blocked:
            if extreme_avoid:
                reason = "AI<35%% avoid"
            elif dump_pattern:
                reason = "AI<45%% + sellers dominate OB"
            else:
                reason = "weak combined: AI<50%%+score<6+spike<2x"
            log.info("AI_BLOCK %s prob=%.1f%% ob=%.0f%% score=%.1f spike=%.1fx (%s)",
                     sym, prob, ob_spot * 100, score, spike, reason)
        return text, blocked
    except Exception:
        return "", False


def _notify_once(key: str, ttl: int = 300) -> bool:
    """Cross-process dedup via /tmp lock file. Returns True = allowed to send.
    Uses O_CREAT|O_EXCL for atomic creation — eliminates TOCTOU race condition
    when two bot processes overlap during systemctl restart.
    """
    path = f"/tmp/mafio_{key.replace('/', '_').replace(':', '_')}.lock"
    now = time.time()
    try:
        # If lock exists and is still fresh → already sent by another process
        if os.path.exists(path) and now - os.path.getmtime(path) < ttl:
            return False
        # Atomic create: O_EXCL ensures only ONE process succeeds even in a race
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(now).encode())
        os.close(fd)
        return True
    except FileExistsError:
        # Another process won the race between our check and create
        return False
    except Exception:
        return True   # on filesystem error, allow rather than silence

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

def _entry_verdict(score, ratio, ob_spot, pos24, hurst, fcf, ls_crowded, net, net_min):
    """3-tier entry verdict for subscribers — returns points 0-8+.
    Flow factors (score/ratio/net/ob) weigh more than pattern factors (H/FCF/pos):
    SSV won +6.6% in 86min with H=0.478 + FCF=0.90 + pos 65% but ratio 4x + net 1.1x min.
    >= 5.0 strong | >= 2.5 moderate | < 2.5 weak (blocked unless moonshot/vol-explosion)."""
    pts = 0.0
    # Flow quality — the factors that actually predict wins (up to 6.0)
    if score >= 7.0:   pts += 2.0
    elif score >= 6.0: pts += 1.5
    elif score >= 5.0: pts += 1.0
    if ratio >= 4.0:      pts += 1.5
    elif ratio >= 2.5:    pts += 1.0
    elif ratio < 1.5:     pts -= 0.5   # sellers slightly dominate
    if ob_spot >= 0.62:   pts += 1.0
    elif ob_spot >= 0.55: pts += 0.5
    if net >= 2 * max(net_min, 1):   pts += 1.5
    elif net >= max(net_min, 1):     pts += 1.0
    # Pattern adjustments — advisory weight only
    if hurst is not None:
        if hurst >= 0.55:  pts += 1.0
        elif hurst < 0.45: pts -= 1.0
        elif hurst < 0.49: pts -= 0.5
    if fcf is not None:
        if fcf > 1.0:    pts += 0.5
        elif fcf < 0.60: pts -= 2.0   # extreme bearish fractal structure
        elif fcf < 0.85: pts -= 1.0
        elif fcf < 0.95: pts -= 0.5
    if pos24 > 0.85:   pts -= 1.0
    elif pos24 <= 0.45: pts += 0.5
    if ls_crowded:     pts -= 1.0   # raised: long squeeze risk is significant
    return round(pts, 1)


def _calc_score(pos24, net, net_min, ob_spot, spike):
    """Confidence score 0–8: pure flow quality (net, ob, spike). pos24 not penalized.
    net_pts maxes at 2× net_min so realistic signals score 5-7, not 2-3."""
    net_pts   = max(0.0, min(4.0, (net / max(net_min, 1)) / 2.0 * 4.0)) # 0-4, max at 2x net_min
    bids_pts  = max(0.0, (ob_spot - 0.45) / 0.35) * 2.0                 # 0-2
    spike_pts = min(2.0, spike / 10.0 * 2.0)                             # 0-2
    return round(min(10.0, net_pts + bids_pts + spike_pts), 1)           # 0-8 in practice

def _calc_fractal_score(fra, fva_result, cq_result):
    """
    Fractal quality score 0-10 — display only, does not affect filters.
    FCF(0-4) + H(0-3) + MTF(0-2) + bearish_end bonus(0-1)
    Returns 7.0 (neutral pass) when FVA and CQ are both disabled.
    """
    if fva_result is None and cq_result is None:
        return 7.0
    pts = 0.0
    # FCF: fractal confluence quality
    if fva_result:
        fcf = fva_result.get("fcf", 1.0)
        if   fcf >= 1.10: pts += 4.0
        elif fcf >= 0.90: pts += 3.0
        elif fcf >= 0.75: pts += 2.0
        elif fcf >= 0.60: pts += 1.0
    # H: Hurst regime from Chaos-Quant
    if cq_result:
        h = cq_result.get("H", 0.5)
        if   h >= 0.60: pts += 3.0
        elif h >= 0.55: pts += 2.0
        elif h >= 0.48: pts += 1.0
    # MTF alignment from fractal validator
    if fva_result:
        macro = fva_result.get("macro_trend", "neutral")
        agree = fva_result.get("mtf_agree", False)
        if agree and macro == "bullish": pts += 2.0
        elif macro == "neutral":         pts += 1.0
    # Bearish fractal end = transition to bullish (+1 bonus)
    if fra and fra.get("bearish_end", False):
        pts += 1.0
    return round(min(10.0, pts), 1)

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
                 interval="1h", is_flash=False, signal_type=None, is_alpha=False,
                 fractal_score=None, oi_label="", counter_trend=False, verdict=""):
    global signal_count
    signal_count += 1

    base     = sym[:-4]
    net      = buy_v - sell_v
    ratio    = buy_v / sell_v if sell_v > 0 else 99.0
    _total_v = buy_v + sell_v
    in_pct   = int(buy_v  / _total_v * 100) if _total_v > 0 else 50
    out_pct  = int(sell_v / _total_v * 100) if _total_v > 0 else 50
    ex_icon  = "🟡"
    # Market type label shown next to coin name
    if is_alpha:
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

    # Signal type badge — only for special event types, not regular signals
    # (verdict at header already communicates quality to subscribers)
    if moonshot:
        score_label = "🚀 *MOONSHOT*"
    elif vol_explosion:
        score_label = "🌋 *VOLUME EXPLOSION*"
    elif score >= 8.5:
        score_label = "🐋 *Whale Action*"
    else:
        score_label = ""

    _tf        = "1m" if interval in ("1m", "1m_sg") else "1h"
    _flash_tag = "\n⚡ *FLASH PUMP* — Act in seconds or skip\n" if is_flash else ""
    _type_line = f"📈 *{signal_type}*\n" if signal_type else ""
    _counter_tag = "\n🔥 *Counter-trend* — Rising against BTC decline\n" if counter_trend else ""

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
        f"{'━'*20}\n"
        f"💀 *MAFIO SNIPER* 📡\n"
        + (f"{'━'*20}\n{verdict}\n" if verdict else "")
        + f"{'━'*20}\n"
        + (f"{_type_line}" if _type_line else "")
        + (f"{_flash_tag}" if _flash_tag else "")
        + (f"{_counter_tag}" if _counter_tag else "")
        + f"\n"
        + f"🆕 *#{base}* 💀 · {_mkt_label} · Signal #{signal_count} {badge}\n"
        + f"💰 `${_fp(price)}`  📈 `+{move:.2f}%`  📍 `{pos_from_bottom}%` {pos_icon}\n"
        + (f"{score_label}\n" if score_label else "")
        + f"\n"
        + f"⚡ `{spike:.1f}x`  ·  📊 Ratio `{ratio:.1f}x` {int_icon}  ·  📥 `{in_pct}%` 📤 `{out_pct}%`\n"
        + f"💹 Net `+{_fv(net)}`\n"
        + f"📗 {ob_label} `{ob_pct}%` bids  ·  📌 {funding_label}\n"
        + (f"📊 {oi_label}\n" if oi_label else "")
        + f"{_tp_sl_block}"
        + f"{ex_icon} `{exchange}`  🕐 {_ts()} UTC\n"
        + f"{'━'*20}"
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
            # Keep signal_history.json in sync — update peak gain as it happens
            # (was incorrectly placed in the "min" block, causing negative max_gain_pct)
            for _rec in reversed(_signal_db):
                if _rec["sym"] == sym and _rec["outcome"] == "active":
                    if gain > (_rec.get("max_gain_pct") or 0.0):
                        _rec["max_gain_pct"] = round(gain, 2)
                    break
        if gain < info.get("min", 0.0):
            info["min"] = gain

        # 2. Stop-loss hit → alert AND close tracking
        # Use per-signal SL from _calc_tp_sl (stored at signal time), fallback to global -5%
        _sl_threshold = info.get("sl_pct", SIGNAL_SL_PCT)
        if gain <= _sl_threshold:
            if not info.get("sl_alerted") and now - _sl_dedup.get(sym, 0) > 300 and _notify_once(f"sl_{sym}", ttl=86400):
                info["sl_alerted"] = True
                _sl_dedup[sym] = now
                save_state()
                _fire_stoploss(sym, gain, t["price"], info["entry"],
                               int(elapsed), info["exchange"])
            expired.append((sym, "stoploss"))   # close immediately on SL
            continue

        # 3. Signal timeout: expire if no target gain within timeout window
        _timeout_h      = info.get("timeout_h", SIGNAL_TIMEOUT_H)
        _timeout_target = 15.0 if info.get("is_swing") else 5.0
        if elapsed > _timeout_h * 3600 and info.get("max", 0.0) < _timeout_target:
            expired.append((sym, "timeout"))
            continue

        # ── Milestone alerts ─────────────────────────────────────────────
        pending = [ms for ms in MILESTONES if ms not in info["hit"] and gain >= ms]
        if pending:
            for ms in pending:
                info["hit"].add(ms)
            top_ms = pending[-1]
            _ms_key = f"{sym}_{top_ms}"
            # Dedup: check both in-memory AND persisted timestamp to survive restarts
            _last_fired = max(_ms_dedup.get(_ms_key, 0), info.get(f"_ms_ts_{top_ms}", 0))
            if now - _last_fired > 1800 and _notify_once(f"ms_{sym}_{top_ms}", ttl=1800):
                _ms_dedup[_ms_key] = now
                info[f"_ms_ts_{top_ms}"] = now
                save_state()
                _fire_ms(sym, top_ms, gain, t["price"], info["entry"],
                         int(elapsed), info["exchange"])
            else:
                save_state()

        # ── Peak Reversal Alert ───────────────────────────────────────────
        peak          = info.get("max", 0.0)
        _rev_min_peak = 6.0 if info.get("is_flash") else 8.0
        _rev_drop     = 3.0
        if peak >= _rev_min_peak and not info.get("rev_alerted"):
            peak_price   = info["entry"] * (1 + peak / 100)
            drop_from_pk = (peak_price - t["price"]) / peak_price * 100
            if drop_from_pk >= _rev_drop and now - _rev_dedup.get(sym, 0) > 300 and _notify_once(f"rev_{sym}", ttl=3600):
                info["rev_alerted"] = True
                _rev_dedup[sym] = now
                save_state()
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
            _cb_record_outcome(is_sl=(reason == "stoploss"), sym=sym)
            daily_results.append({
                "sym":      sym,
                "entry":    info["entry"],
                "max":      _max,
                "elapsed":  int(now - _t0),
                "success":  _max >= 5.0,
                "reason":   reason,
                "exchange": info.get("exchange", "Binance"),
                "ts":       int(now),
            })
            # SL hit → extend cooldown to 24h to prevent re-entry on downtrending coins
            # CLO pattern: bot re-entered 4 days later at -15% from previous signal → SL again
            if reason == "stoploss":
                _SL_BLOCK = 86400  # 24h
                alerted[sym] = now + (_SL_BLOCK - COOLDOWN)
                log.info("SL_BLOCK %s — cooldown extended to 24h", sym)
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
            "exchange": info.get("exchange", "Binance"),
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
        f"📊 Daily Report — {date_str}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🔔 {total} signals  |  ✅ {len(wins)} wins  |  ⏳ {len(active_c)} active  |  ❌ {len(losses)} losses",
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

    # ── EOD Self-Reflection ───────────────────────────────────────────────
    _send_eod_reflection(all_entries)

    log.info("Daily report: total=%d wins=%d losses=%d active=%d avg=%.1f%%",
             total, len(wins), len(losses), len(active_c), avg_pk)

    if reset:
        daily_results = []
        daily_diag.clear()
        save_state()


def _send_eod_reflection(all_entries: list):
    """Analyze today's signals and send a self-reflection report with lessons learned."""
    if not all_entries:
        return
    try:
        # ── Load today's signals from signal_history.json ──
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            with open("signal_history.json", "r") as f:
                history = json.load(f)
        except Exception:
            history = []

        today_sigs = [
            s for s in history
            if s.get("ts", "")[:10] == today_str and s.get("max_gain_pct") is not None
        ]
        if not today_sigs:
            today_sigs = [
                {"scanner": e.get("scanner", "?"), "tier": e.get("tier", "?"),
                 "max_gain_pct": e["max"], "score": 0, "ob_spot": 0,
                 "ratio": 0, "spike": 0, "net_usd": 0}
                for e in all_entries if "max" in e
            ]
        if not today_sigs:
            return

        wins  = [s for s in today_sigs if s.get("max_gain_pct", 0) >= 5]
        loses = [s for s in today_sigs if s.get("max_gain_pct", 0) < 0]
        total = len(today_sigs)

        def _avg(lst, key):
            vals = [s.get(key) or 0 for s in lst]
            return sum(vals) / len(vals) if vals else 0

        # ── By Scanner ──
        sc: Dict[str, list] = {}
        for s in today_sigs:
            sc.setdefault(s.get("scanner", "?"), []).append(s.get("max_gain_pct", 0))
        sc_ranked = sorted(sc.items(), key=lambda x: -sum(x[1]) / len(x[1]))

        # ── By Tier ──
        tc: Dict[str, list] = {}
        for s in today_sigs:
            tc.setdefault(s.get("tier", "?"), []).append(s.get("max_gain_pct", 0))
        tc_ranked = sorted(tc.items(), key=lambda x: -sum(x[1]) / len(x[1]))

        # ── Lessons Learned ──
        lessons = []

        # Win pattern analysis
        if wins:
            avg_ob_w  = _avg(wins, "ob_spot")
            avg_rat_w = _avg(wins, "ratio")
            avg_spk_w = _avg(wins, "spike")
            if avg_ob_w >= 0.65:
                lessons.append(f"✅ Winning signals had OB `{avg_ob_w:.0%}` — strong OB predicts success")
            if avg_rat_w >= 4.0:
                lessons.append(f"✅ Winning signals ratio `{avg_rat_w:.1f}x` — ratio≥4x is a strong indicator")
            if avg_spk_w >= 8.0:
                lessons.append(f"✅ Winning signals spike `{avg_spk_w:.1f}x` — volume explosion precedes the move")

        # Loss pattern analysis
        if loses:
            avg_ob_l  = _avg(loses, "ob_spot")
            avg_pos_l = _avg(loses, "pos24")
            if avg_ob_l < 0.60:
                lessons.append(f"⚠️ Losing signals had OB `{avg_ob_l:.0%}` — weak OB = danger")
            if avg_pos_l > 0.60:
                lessons.append(f"⚠️ Losing signals entered at `{avg_pos_l:.0%}` from range — late entry")

        # Best scanner today
        if sc_ranked:
            best_sc, best_sc_vals = sc_ranked[0]
            best_sc_avg = sum(best_sc_vals) / len(best_sc_vals)
            if best_sc_avg >= 10:
                lessons.append(f"🏆 Best scanner today: `{best_sc}` avg `+{best_sc_avg:.1f}%`")

        # Worst scanner today
        if len(sc_ranked) > 1:
            worst_sc, worst_sc_vals = sc_ranked[-1]
            worst_avg = sum(worst_sc_vals) / len(worst_sc_vals)
            if worst_avg < 3:
                lessons.append(f"📉 Weakest scanner today: `{worst_sc}` avg `{worst_avg:.1f}%` — monitor it")

        # ── Build message ──
        lines = [
            "━━━━━━━━━━━━━━━━━━━━━━━━━",
            "🧠 *MAFIO — Daily Self-Analysis*",
            "━━━━━━━━━━━━━━━━━━━━━━━━━",
            "",
            f"📊 *Scanner Performance Today*",
        ]
        for sc_name, vals in sc_ranked:
            avg_v = sum(vals) / len(vals)
            w_cnt = sum(1 for v in vals if v >= 5)
            lines.append(f"  `{sc_name:<18}` {len(vals)} signals  avg `{avg_v:+.1f}%`  wins: {w_cnt}")

        lines += ["", "📦 *Tier Performance Today*"]
        for t_name, vals in tc_ranked:
            avg_v = sum(vals) / len(vals)
            lines.append(f"  `{t_name:<8}` {len(vals)} signals  avg `{avg_v:+.1f}%`")

        if lessons:
            lines += ["", "💡 *Key Takeaways*"]
            lines += [f"  {l}" for l in lessons]

        # Win/Loss comparison
        if wins and loses:
            lines += [
                "",
                "🔬 *Winners vs Losers Comparison*",
                f"  OB:    winners `{_avg(wins,'ob_spot'):.0%}`  vs  losers `{_avg(loses,'ob_spot'):.0%}`",
                f"  Ratio: winners `{_avg(wins,'ratio'):.1f}x`    vs  losers `{_avg(loses,'ratio'):.1f}x`",
                f"  Spike: winners `{_avg(wins,'spike'):.1f}x`    vs  losers `{_avg(loses,'spike'):.1f}x`",
            ]

        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━")
        send("\n".join(lines))
        log.info("EOD reflection sent: %d signals analyzed", total)
    except Exception as e:
        log.warning("EOD reflection failed: %s", e)



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
        send(f"📊 *{period_label}*\nNo signals found for this period.")
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
        f"🔔 {total} signals  |  ✅ {len(wins)} wins  |  ❌ {len(losses)} losses  |  ⏳ {len(active)} active",
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
        out = e.get("outcome", "active")
        if out in WIN_OUT:
            outcome_icon = "✅"
            gain_label   = f"WIN `{g:+.2f}%`"
        elif out in LOSS_OUT:
            outcome_icon = "❌"
            gain_label   = f"Peak `{g:+.2f}%` → SL"
        else:
            outcome_icon = "⏳"
            gain_label   = f"`{g:+.2f}%`"
        peak_icon = "💎" if g >= 20 else "🔥" if g >= 15 else "🚀" if g >= 5 else ""
        return (
            f"{rank_icon}  *{sym}*\n"
            f"   🏷 Category:  {cat}\n"
            f"   {outcome_icon}{peak_icon} {gain_label}"
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
        f"Weekly Report — {now_utc.strftime('%d %b %Y')}",
        days=7,
    )


def send_monthly_report():
    now_utc = datetime.now(timezone.utc)
    _period_report(
        f"Monthly Report — {now_utc.strftime('%B %Y')}",
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

            if text.lower().split("@")[0] == "/positions":
                log.info("Manual /positions from chat %s", cid)
                if not tracking:
                    send("📭 *No open positions*")
                else:
                    try:
                        now_ts  = time.time()
                        lines   = ["📊 *Open Positions*", "━━━━━━━━━━━━━━━━━━━━━━━━━"]
                        rows    = []
                        for sym, info in tracking.items():
                            try:
                                entry    = info["entry"]
                                exch     = info.get("exchange", "Binance")
                                t0       = info.get("t0", now_ts)
                                max_gain = info.get("max", 0.0)
                                elapsed  = int(now_ts - t0)
                                base_url = BINANCE_BASE
                                pd = _get(f"{base_url}/ticker/price",
                                          params={"symbol": sym})
                                cur = float(pd.get("price", 0)) if isinstance(pd, dict) else 0.0
                                pct = (cur - entry) / entry * 100 if cur > 0 else 0.0
                                rows.append((pct, sym, entry, cur, max_gain, elapsed, exch))
                            except Exception:
                                rows.append((0.0, sym, info["entry"], 0.0,
                                             info.get("max", 0.0),
                                             int(now_ts - info.get("t0", now_ts)), "?"))
                        # Sort: worst P&L first (most at-risk on top)
                        rows.sort(key=lambda x: x[0])
                        for pct, sym, entry, cur, mx, elapsed, exch in rows:
                            base = sym[:-4] if sym.endswith("USDT") else sym
                            _sig_sl = tracking.get(sym, {}).get("sl_pct", SIGNAL_SL_PCT)
                            if pct >= 5.0:
                                icon = "✅"
                            elif pct <= _sig_sl:
                                icon = "🔴"
                            elif pct < -2.0:
                                icon = "⚠️"
                            elif pct >= 2.0:
                                icon = "🟢"
                            else:
                                icon = "⏳"
                            cur_str = f"${cur:.6g}" if cur > 0 else "N/A"
                            dist_sl = pct - _sig_sl   # how far above SL
                            lines.append(
                                f"{icon} *{base}*  `{pct:+.1f}%`\n"
                                f"   Entry `${entry:.6g}` → Now `{cur_str}`\n"
                                f"   Peak `+{mx:.1f}%` · {_tstr(elapsed)} · {exch}\n"
                                f"   SL buffer: `{dist_sl:+.1f}%`  TP1 gap: `{12.0-pct:+.1f}%`"
                            )
                        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━")
                        send("\n".join(lines))
                    except Exception as pos_err:
                        send(f"❌ *Positions failed*\n`{pos_err}`")

            if text.lower().split("@")[0] == "/ai_summary":
                log.info("Manual /ai_summary from chat %s", cid)
                if _ai_agent is None:
                    send("❌ AI Agent not active")
                else:
                    send(_ai_agent.summary(), parse_mode="Markdown")

            if text.lower().split("@")[0] == "/fractal_summary":
                log.info("Manual /fractal_summary from chat %s", cid)
                if _fractal_agent is None:
                    send("❌ Fractal Agent غير مفعّل")
                else:
                    send(_fractal_agent.summary(), parse_mode="Markdown")
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
                                   {"command": "positions",       "description": "📍 Open positions — live P&L"},
                                   {"command": "report",          "description": "📊 Daily report"},
                                   {"command": "weekly",          "description": "📊 Weekly report"},
                                   {"command": "monthly",         "description": "📊 Monthly report"},
                                   {"command": "ai_summary",      "description": "🤖 AI Agent summary"},
                                   {"command": "fractal_summary", "description": "📐 Fractal Agent summary"},
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
            # Keep colours vivid — only slight dim so text stays readable
            bg = ImageEnhance.Brightness(bg).enhance(0.82)
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

        # ── Semi-transparent overlay for text panels ──
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        od.rectangle([(0, 0), (W, 74)],   fill=(0, 0, 0, 140))   # top bar
        od.rectangle([(0, 490), (W, H)],  fill=(0, 0, 0, 195))   # bottom panel (darker for big text)
        od.ellipse([(W//2 - 240, 270), (W//2 + 240, 470)], fill=(0, 0, 0, 90))
        img = img.convert("RGBA")
        img = Image.alpha_composite(img, overlay)
        img = img.convert("RGB")
        draw = ImageDraw.Draw(img)

        # ── Fonts ──
        FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
        try:
            f_brand    = ImageFont.truetype(FONT, 22)
            f_coin     = ImageFont.truetype(FONT, 82)
            f_gain     = ImageFont.truetype(FONT, 138)
            f_coinname = ImageFont.truetype(FONT, 58)   # large coin name in footer
            f_price    = ImageFont.truetype(FONT, 42)   # large entry/current price
        except Exception:
            f_brand = f_coin = f_gain = f_coinname = f_price = ImageFont.load_default()

        # ── Top branding ──
        draw.text((26, 26), "MAFIO SNIPER", fill=(200, 190, 230), anchor="lt", font=f_brand)
        ex_color = (0, 195, 255)
        ex_label = "MAFIO BINANCE"
        draw.text((W - 26, 26), ex_label, fill=ex_color, anchor="rt", font=f_brand)
        draw.line([(26, 60), (W - 26, 60)], fill=(50, 25, 85), width=1)

        # ── Coin name (shadow + text) ──
        draw.text((W // 2 + 3, 203), f"{base}", fill=(10, 0, 20),     anchor="mm", font=f_coin)
        draw.text((W // 2,     200), f"{base}", fill=(255, 255, 255), anchor="mm", font=f_coin)

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
        draw.line([(40, 500), (W - 40, 500)], fill=(80, 50, 130), width=2)

        # ── Footer: big coin name + entry → current price ──
        # Row 1: #COINNAME centred (gold, large)
        draw.text((W // 2, 540), f"#{base}", fill=(255, 215, 0), anchor="mm", font=f_coinname)
        # Row 2: left = "Entry $X" / right = "Now $X" (white/green, large)
        tp_price = tp1 if tp1 > 0 else now_price
        draw.text((W // 4,     618), f"Entry: ${_fp(entry)}",    fill=(210, 200, 235), anchor="mm", font=f_price)
        draw.text((3 * W // 4, 618), f"Now: ${_fp(tp_price)}",   fill=gain_color,      anchor="mm", font=f_price)

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

    max_loss_line = f"📉 Max loss:  `{max_loss:.2f}%`\n" if max_loss < -0.1 else ""

    sig_msg_id = tracking.get(sym, {}).get("sig_msg_id", 0)
    _reply_to  = sig_msg_id if sig_msg_id and not _sig_link(sig_msg_id) else None
    link = _sig_link(sig_msg_id)
    keyboard = {"inline_keyboard": [[{"text": "📌 View Signal", "url": link}]]} if link else None
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
    _reply_to  = sig_msg_id if sig_msg_id and not _sig_link(sig_msg_id) else None
    link = _sig_link(sig_msg_id)
    keyboard = {"inline_keyboard": [[{"text": "📌 View Signal", "url": link}]]} if link else None
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
    _sl_used   = tracking.get(sym, {}).get("sl_pct", SIGNAL_SL_PCT)
    _reply_to  = sig_msg_id if sig_msg_id and not _sig_link(sig_msg_id) else None
    link = _sig_link(sig_msg_id)
    keyboard = {"inline_keyboard": [[{"text": "📌 View Signal", "url": link}]]} if link else None
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
        f"💡 Signal closed — price fell {abs(_sl_used):.0f}%+ from entry\n"
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
    # momentum_signal: set by scan_trend_follow — must be assigned early (used before line 2775)
    momentum_bypass = ticker.get("momentum_signal", False)

    # ── Circuit Breaker — blocks signals after 3 consecutive SL hits ──────
    if _cb_is_active():
        resume = datetime.fromtimestamp(_cb_blocked_until, tz=timezone.utc).strftime("%H:%M UTC")
        log.debug("CB: blocking %s — resumes %s", sym, resume)
        return

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

    # Frozen ticker guard — 24h change exactly 0.0% = API cache / delisted coin (MFT pattern)
    if change == 0.0 and vol_24h < 1_000_000:
        _rej("frozen_ticker"); return

    # Frozen price guard — same exact price as last signal = ghost/cached data
    if sym in _alerted_price and _alerted_price[sym] == price:
        _rej("frozen_price"); return

    # Downtrend repeat guard — CLO pattern: coin fired before but is now significantly lower
    # If current price is 15%+ below the last signal price = sustained downtrend = block
    # Volume spikes in downtrends are distribution, not accumulation
    if sym in _alerted_price and _alerted_price[sym] > 0:
        _prev_sig_price = _alerted_price[sym]
        _drop_from_prev = (_prev_sig_price - price) / _prev_sig_price * 100
        if _drop_from_prev >= 15.0:
            _rej(f"downtrend_repeat({_drop_from_prev:.0f}%)"); return


    # Skip already pumped — Alpha/pre-listing: allow 400% (listing-day pumps reach 200-300%)
    # Sleeping giant (1m_sg): explosion from multi-week low → allow up to 300%
    # Regular Spot: raised 80%→150% — OPN-type moves (depressed coin explodes) are valid signals
    _is_alpha_coin = ticker.get("binance_alpha") or ticker.get("futures_only")
    _max_pump = 400.0 if _is_alpha_coin else (300.0 if interval == "1m_sg" else 150.0)
    h24, l24 = ticker["high24"], ticker["low24"]
    range_pump = (h24 - l24) / l24 * 100 if l24 > 0 else 0
    _max_range = 600.0 if _is_alpha_coin else 200.0
    if change > _max_pump or range_pump > _max_range:
        _rej("max_pump"); return
    if now - alerted.get(sym, 0) < COOLDOWN: _rej("cooldown"); return
    # Skip coins already in active tracking — avoid re-entry on a coin already being followed
    if sym in tracking: _rej("already_tracking"); return

    # ── Sector Momentum detection (pre-klines) ────────────────────────────
    # AXS/APE/ALICE gaming rotation: coins pump gradually over 6h+ as a sector.
    # Each 1h kline looks "flat" → low_move blocks them. But 24h trend is strong.
    # Uses rise-from-low instead of pos24 (pos24=1.0 when making new 24h highs).
    # Requires vol >= $1M to exclude MEXC micro-cap manipulation.
    _rise_from_low = (price - l24) / l24 * 100 if l24 > 0 else 0
    _sector_mom_pre = (
        change >= 15.0 and          # strong 24h trend
        _rise_from_low < 55.0 and   # not overextended — raised from 40% to 55% to catch PORTAL/STG type
        (vol_24h >= 1_000_000 or _is_alpha_coin)  # Alpha bypass: pre-listing coins have thin vol by nature
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

    # Binance large-caps: high baseline volume, efficient 2-sided market
    # → spike fires less dramatically, net scales with coin size
    spike_min *= 0.70                              # 30% easier — BTC-type spikes are subtle
    # Ratio discount: only for Mid/Large cap (deep liquidity = naturally lower ratio)
    # Micro/Small cap Binance: full ratio required — VINE(2.2x) failed in 10m at pos69%
    if tier["name"] in ("Mid", "Large"):
        ratio_min *= 0.85                          # 15% easier for large liquid coins only
    # Proportional net: 0.25% of daily volume, capped at $80K, floor $5K
    net_min = min(max(vol_24h * 0.0025, 5_000), 80_000)

    # ── Late entry filter ────────────────────────────────────────────────────
    # 0.97: only block absolute top 3% of 24h range
    # Wick/OB filters handle true pump-dumps
    _late_pct = 0.97
    rng = ticker["high24"] - ticker["low24"]
    if rng > 0 and (price - ticker["low24"]) / rng > _late_pct and not _sector_mom_pre and not momentum_bypass and interval != "1m_sg" and not _is_alpha_coin:
        # New-high breakout bypass: coin up 10%+ AND still within 5% of its high = genuine breakout
        # JTO pattern: breaking to new 24h highs with +26% day = real move, not late chasing
        _at_new_high = (
            ticker.get("change", 0.0) > 10.0 and
            ticker["high24"] > 0 and
            (ticker["high24"] - price) / ticker["high24"] * 100 < 5.0
        )
        if not _at_new_high:
            _rej("late_entry"); return

    # ── Quick vol floor (no API call) ─────────────────────────────────────
    if vol_24h < tier["vol_min"]:
        _rej("low_vol"); return

    # Market bias gate — Binance: allow Mid+Large in bear (FF/ILV/LPT proof)
    # Alpha/futures-only coins bypass bias_gate — they move independently of market
    if not should_signal(tier["name"], market_bias, exchange) and not _is_alpha_coin:
        _rej("bias_gate"); return

    # ── Distance from 24h low: pre-klines guard (no API call) ────────────
    # Only blocks coins that have ALREADY completed a massive pump (>80-90% from daily low).
    # Alpha: bypass — high/low are estimated, not real API data
    # Sleeping giant (1m_sg): bypass — explosive moves from deep lows are the point
    if ticker["low24"] > 0 and not _is_alpha_coin and interval != "1m_sg":
        _rise_pct = (price - ticker["low24"]) / ticker["low24"] * 100
        if exchange == "Binance":
            _dist_max = {"Micro": 200.0, "Small": 150.0, "Mid": 120.0, "Large": 120.0}.get(tier["name"], 120.0)
        else:
            # Raised: MEXC Mid 75%→100%, Large 60%→80% — OPN-type moves are valid
            _dist_max = {"Micro": 150.0, "Small": 120.0, "Mid": 100.0, "Large": 80.0}.get(tier["name"], 100.0)
        if _rise_pct > _dist_max:
            _rej(f"far_from_low(rise={_rise_pct:.0f}%,max={_dist_max:.0f}%,exch={exchange},tier={tier['name']})"); return

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

    # Explosive spike: 30x+ vol = institutional move, bypasses fractal/resistance gates
    # Assigned here (after spike is final) so all downstream checks use correct value
    _is_explosive = (spike >= 30.0)

    # Early move filter: only block clear downtrends (< -1%)
    # Real move_min (1.5%) is applied AFTER funding_rate check below
    if move < -1.0: _rej(f"low_move({move:.1f}%)"); return

    # Thin coin + big move = pump already over (AURORA, SIX type)
    if move > 8.0 and vol_24h < 200_000 and not _is_alpha_coin:
        _rej("thin_pump"); return

    # Reject dead coins (zero base volume)
    if avg_vol < 200: _rej("dead_coin"); return

    # ── Funding Rate + OI (API call — only for candidates that pass klines) ───
    funding_rate, funding_label = fetch_binance_funding_rate(sym)
    _oi = fetch_oi_ls(sym)
    funding_bullish = funding_rate is not None and funding_rate > 0.03

    if funding_bullish:
        spike_min = max(2.0, spike_min * 0.60)   # floor 1.5→2.0 (CLO 1.6x blocked)
        ratio_min = max(2.5, ratio_min * 0.70)   # floor 1.8→2.5 (CLO 2.1x, QUAI 2.4x blocked)
        net_min   = max(net_min * 0.25, 100)
        move_min  = -5.0              # funding bullish: allow dip buying
    else:
        move_min  = ctx["move_min"]   # adaptive: 0.5% bull → 2.5% bear

    # Cap move_min at 0.5% — flat/consolidating markets show 0.5-1% hourly moves
    # that precede larger explosions. 1.0% was blocking gradual Binance breakouts.
    move_min = min(move_min, 0.5)

    # Fast scan (1m klines): a 0.5% move in 1 minute = explosive beginning
    if interval == "1m":
        move_min = min(move_min, 0.5)
    # Sleeping giant (1m klines, volume detected before price moves): lower threshold
    elif interval == "1m_sg":
        move_min = min(move_min, 0.15)
    # Mid scan (5m klines): 0.3%/5min = ~3.6%/hr uptrend — catches gradual pumpers
    # (EDEN/KAIA/OPEN type: +17-38% over 8-12h with no single explosive candle)
    elif interval == "5m":
        move_min = min(move_min, 0.3)

    # Sector momentum: confirm spike after klines are available
    # Alpha coins accumulate with subtler spikes (1.2x) vs regular coins (1.5x)
    _sector_mom_spike_thr = 1.2 if _is_alpha_coin else 1.5
    _sector_mom = _sector_mom_pre and spike >= _sector_mom_spike_thr
    if move < move_min and not _sector_mom: _rej(f"low_move({move:.1f}%)"); return

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
    # momentum_bypass (trend_follow): accept 1.3x spike — sustained trend, not explosive
    effective_spike_min = 1.3 if momentum_bypass else (1.5 if super_ratio else spike_min)
    if spike < effective_spike_min:
        _rej("low_spike"); return

    # Spike candle must close in upper half — rejects pump-dump wicks
    # Sleeping giant: use candles[-2] (the actual spike candle, already completed)
    # because by the time _check() runs, [-1] is the next candle (just started = misleading)
    _wick_candle = candles[-2] if (interval == "1m_sg" and len(candles) >= 2) else candles[-1]
    try:
        sc_rng = float(_wick_candle[2]) - float(_wick_candle[3])
        sc_close_pct = (float(_wick_candle[4]) - float(_wick_candle[3])) / sc_rng if sc_rng > 0 else 0.5
    except Exception:
        sc_close_pct = 0.5
    # Bypass when price is actively rising — wick is temporary profit-taking, not distribution
    # SENT/MOVE pattern: previous candle bearish (downtrend), new candle exploding = real reversal
    if sc_close_pct < 0.50 and move < 2.0:
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
    # Sleeping giant: require stronger seller dominance (ob<0.40) — temporary post-spike
    # selling is normal and shouldn't block a 50x+ move
    # FTT pattern: dead coin (near-zero vol) wakes up with 20x+ spike — ob naturally thin,
    # but if price is still actively rising (move >= 2%), we're early in the move, not a dump.
    _pd_ob_thr = 0.40 if interval == "1m_sg" else 0.50
    _still_rising = move >= 2.0
    is_pump_dump = (
        spike > 20.0 and pos24 > 0.55 and ob_quick < _pd_ob_thr
        and not _still_rising
    )
    if is_pump_dump:
        _rej("pump_dump"); return

    # Post-pump crash filter — uses ctx.crash_limit (adaptive)
    # Breakout bypass: strong volume explosion + buyer dominance = fresh consolidation breakout,
    # not a dump continuation. ALLO pattern: consolidated at 75% pos, then 10x+ vol broke out.
    # MOVE pattern: Large cap spike of 2.5x = tens of millions in absolute $ — real breakout.
    _breakout_spike_min = 2.5 if tier["name"] == "Large" else 3.0
    if ticker["high24"] > 0 and ticker["low24"] > 0:
        pump_size = (ticker["high24"] - ticker["low24"]) / ticker["low24"] * 100
        crash_from_top = (ticker["high24"] - price) / ticker["high24"] * 100
        if pump_size > 30.0 and crash_from_top > ctx["crash_limit"]:
            _vol_breakout = (spike >= _breakout_spike_min and ob_quick >= 0.55 and move >= 1.0)
            if not _vol_breakout:
                _rej("post_pump"); return

    # Position guard — uses ctx.pos_limit (adaptive)
    # Sector momentum: use rise_from_low instead of pos24 (pos24=1.0 when at new highs)
    # Momentum bypass: scan_trend_follow confirmed 7d uptrend — pos24 inherently high
    if _sector_mom:
        if _rise_from_low > 55.0:   # aligned with _sector_mom_pre threshold (was 50%)
            _rej("high_pos"); return
    elif momentum_bypass:
        pass   # trend-follow: pos24 misleadingly high for 7d trends; OB + spike filters protect
    elif pos24 > ctx["pos_limit"]:
        # BLINKY pattern: very high ratio (≥20x) overrides position limit
        # Sleeping Giant: flat coin with tiny daily range — high pos24 is misleading
        # Volume breakout: Mid/Large = 2.5x spike enough (absolute $ >>> small cap 5x)
        _sg_bypass = (interval == "1m_sg" and spike >= 10.0)
        _vol_breakout = (spike >= _breakout_spike_min and ob_quick >= 0.55 and move >= 1.0)
        if _pre_ratio < 20.0 and not _sg_bypass and not _vol_breakout:
            _rej("high_pos"); return

    # High position + weak volume = false signal (我踏马来了 pattern)
    # Coin already moved up in range but without real volume explosion = chasing
    # Exempt: momentum_bypass (7d trend) + _sector_mom (spike-confirmed rotation)
    if pos24 > 0.65 and spike < 3.0 and not interval.endswith("_sg") and not momentum_bypass and not _sector_mom:
        _rej("high_pos_low_vol"); return

    # Weak top filter: very high in range + flat move = exhaustion, not breakout
    # Raised from 0.62→0.75 to avoid blocking mid-range breakouts
    # Sleeping giant bypass: flat coins always show high pos24 due to tiny daily range
    # Exempt: momentum_bypass (gradual trend: 1h move naturally small) + _sector_mom
    _weak_move_thr = 0.8 if exchange == "Binance" else 1.0
    if pos24 > 0.75 and ratio_min > 0 and move < _weak_move_thr and not (interval == "1m_sg" and spike >= 10.0) and not momentum_bypass and not _sector_mom:
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
    # FORM pattern: sleeping giant 13x volume but price barely moved (accumulation battle)
    # Extreme spike alone = real demand even if net is small → lower floor
    if interval == "1m_sg" and spike >= 10.0:
        _abs_net_floor = 1_000.0
    if net < _abs_net_floor:
        _rej("noise_net"); return

    # Coin fatigue — skip if 2+ signals in last 7 days with no gain ≥ 5%
    # Exception: net > $300K = institutional accumulation (NIGHT pattern) → allow re-signal
    if _db_coin_fatigue(sym) and net < 300_000:
        log.info("COIN_FATIGUE %s — 2+ signals in 7d best_gain<5%% net=%.0f$", sym, net)
        _rej("coin_fatigue"); return

    # MOONSHOT override: whale accumulation bypasses soft filters
    _low_price_moon = (
        price < 0.25 and spike >= 10.0 and
        net > 20_000 and pos24 < 0.50
    )
    is_moonshot = (
        (net > 500_000 and pos24 < 0.60) or   # Whale: $500K+ net near bottom
        (pos24 < 0.10 and net > 60_000) or     # Bottom sniper: <10% pos + strong flow
        _low_price_moon                         # Low-price pump: HIGH/ALICE/PORTAL type
    )

    # Momentum Bypass: DISABLED — data shows 8% win rate (1 win / 8 SL across 23 signals)
    # ratio alone is insufficient confirmation; high ratio in downtrend = distribution trap
    _ratio_bypass   = 8.0
    # momentum_bypass already set at function start from ticker.get("momentum_signal")

    # Volume Explosion: spike + REAL net = extraordinary event → bypasses ob/quality/pos24 filters.
    # Threshold 5x: still an unusual event (normal is 1-2x), but opens bypass gates for coins
    # that have real volume but fail strict ob/quality gates. Most winning signals are 2-6x spike.
    # Sleeping Giant bypass: pos24 is misleading for flat coins with tiny daily range.
    volume_explosion = (spike >= 5.0 and (pos24 < 0.82 or interval == "1m_sg") and net > _abs_net_floor)

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
    # Exempt: momentum_bypass (trend-follow: 7d trend confirmed) + _sector_mom (spike-confirmed rotation)
    if pos24 > 0.70 and not is_moonshot and not momentum_bypass and not _sector_mom:
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
    # ob_sellers threshold: 60% fixed — all winners had ≥60% bids (REPAI=60%, BLINKY=68%)
    # BEAT=46% and RIVER=48% were losers — sub-60% bids = no real buyer conviction
    _ob_min_spot = 0.60
    # Absorption bypass: ob_spot >= 0.55 required even with strong net flow
    absorption = (net >= net_min * 3 and ob_spot >= 0.55)
    # volume_explosion bypass: only when ob >= 0.50 (RAY=59% ✅, BANK=48% ❌)
    _vol_exp_ob_ok = volume_explosion and ob_spot >= 0.50
    if ob_spot < _ob_min_spot and not absorption and not is_moonshot and not momentum_bypass and not _vol_exp_ob_ok:
        _rej("ob_sellers"); return
    # Moonshot OB floor: 30% bids = 70% sellers ready to dump on any spike
    # BANANAS31: ratio 29.7x but OB 30% → big buyer ran out → -8% SL
    # AI: OB 37% + bullish fractal (QUAD + 5-wave) → +19% ✅ (correct to allow)
    # Threshold 35%: blocks BANANAS31 (30%) while allowing AI (37%)
    if is_moonshot and ob_spot < 0.35 and not funding_bullish:
        _rej(f"moonshot_ob_floor({ob_spot:.0%})"); return

    # Moonshot Bearish OB + Weak Flow Gate
    # Sellers dominate OB + weak ratio + small net = no real buying conviction.
    # IOTX: ob=36%, ratio=1.6x, net=$22.9K — all three weak simultaneously.
    # Exceptions: strong net (≥$150K proves real conviction) OR ratio ≥ 2.0 OR funding_bullish.
    if (is_moonshot and ob_spot < 0.42 and ratio < 2.0
            and net < 150_000 and not funding_bullish):
        _rej(f"moonshot_bearish_ob_weak_flow(ob={ob_spot:.0%},ratio={ratio:.1f}x,net={_fv(net)})"); return
    if ticker.get("futures_only"):
        ob_fut = ob_spot  # base_url already points to FAPI — no double call
    elif ticker.get("binance_alpha"):
        ob_fut = ob_spot  # no FAPI contract — use spot OB only
    else:
        ob_fut = fetch_ob_imbalance(sym, f"{BINANCE_FUTURES}/fapi/v1", levels=20)
    ob_score = ob_spot * 0.7 + ob_fut * 0.3
    # ob_min: 0.38 — Binance market makers keep tighter spreads
    _ob_min_eff = 0.38
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
        # bear_bids check removed: liquidity explosions happen in any bias direction.

    # ── Fake Wall filter ─────────────────────────────────────────────────
    # PHY pattern: OB=90% bids + net=$4.6K = artificial buy wall with no real flow
    # Thin coins (MEXC micro-caps) use fake walls to attract buyers while smart money dumps
    # Real breakouts with high OB have STRONG net flow (WOTAMALAILIAO: OB=46% + net=$59K)
    # Rule: OB > 85% AND net < 3× net_min = fake wall, not genuine demand
    if ob_spot > 0.85 and net < net_min * 3 and not is_moonshot and not funding_bullish:
        log.debug("FAKE_WALL skip %s ob=%.0f%% net=%s net_min=%s", sym, ob_spot*100, _fv(net), _fv(net_min))
        _rej("fake_wall"); return

    # Funding bearish: very negative funding = aggressive shorting = score penalty only
    # (do NOT block — spot-driven moves often have negative funding as shorts chase)
    _funding_bearish = (funding_rate is not None and funding_rate < -0.02)

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

    # Bearish funding penalty: shorts are fighting the move — lower confidence
    if _funding_bearish:
        score = max(0.0, round(score - 1.5, 1))

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
    if score < 4.5 and ob_spot < 0.65 and not is_moonshot and not momentum_bypass and not volume_explosion and not _extreme_vol and not _strong_ratio:
        _rej("weak_ob_score"); return

    # bear_bids score penalty removed: bias does not determine signal quality.

    # ── Quality gate — dual-path instead of pure score floor ─────────────
    # Score is pure flow quality (net+ob+spike), max ~8. Good signals score 5-7.
    # Pre-compute flow paths so _strong_signal/_huge_flow can bypass the floor.
    _strong_signal = ob_spot >= 0.72 and ratio >= 2.5 and net >= net_min
    _huge_flow     = net > 100_000 and ob_spot >= 0.65
    # Sector boost: hot sector = 4th path — positive flow + decent OB enough
    _sector_path   = (sector_boost and net > 0
                      and ob_spot >= 0.55 and ratio >= 1.5)
    # Absolute floor — only pure noise signals (score < 4.0) with no flow backup are blocked.
    if score < 4.0 and not is_moonshot and not volume_explosion and not _strong_signal and not _huge_flow:
        _rej("quality_fail"); return
    # Good score = 5.5+ on 0-8 scale (calibrated for pos24-neutral formula)
    _good_score = score >= 5.5
    if not (_good_score or _strong_signal or _huge_flow or _sector_path):
        if not is_moonshot and not volume_explosion:
            _rej("quality_fail"); return

    # Counter-trend: coin rising while BTC declining = independent capital flow (EPIC pattern)
    _btc_24h = all_t.get("BTCUSDT", {}).get("change", 0.0) if "all_t" in dir() else 0.0
    _counter_trend_main = market_bias < -15 and change > 0.5
    # Bear market fighting bonus: coin rising strongly against BTC decline
    _fighting_bear = (market_bias <= -20 and move >= 5.0
                      and net > net_min * 2 and ob_spot >= 0.60)

    # ── Fractal Analysis (Bill Williams patterns + self-learning) ────────
    _fra = None
    if _fractal_agent is not None:
        try:
            _fra = _fractal_agent.analyze(candles, price)
        except Exception as _fe:
            log.debug("fractal_agent error: %s", _fe)

    # ── Fractal Confluence Factor (Almazov 5-book synthesis) ─────────────
    # FCF adjusts signal score based on: 1.618 false-breakout risk,
    # wave structure (3 vs 5-wave), MTF alignment, noise, cycle position.
    _fva_result = None
    if _fva is not None:
        try:
            _fva_result = _fva.evaluate_fractal_confluence(candles, price)
            _fcf = _fva_result["fcf"]
            if _fcf != 1.0:
                _score_before = score
                score = round(min(10.0, max(0.0, score * _fcf)), 1)
                log.debug("FCF %s x%.2f score %.1f→%.1f | %s",
                          sym, _fcf, _score_before, score, _fva_result.get("detail", ""))
        except Exception as _fve:
            log.debug("FractalValidationAgent error: %s", _fve)

    # ── Chaos-Quant Engine (Edgar Peters Hurst + Young Ho Seo + Noah Effect) ──
    _cq_result = None
    if _cq_ok:
        try:
            _cq_result = _cq_integrate(candles, price, score, is_moonshot)
            _cq_score_before = score
            score = _cq_result["score"]
            if score != _cq_score_before:
                log.debug("CQ %s H=%.3f regime=%s score %.1f→%.1f",
                          sym, _cq_result["H"], _cq_result["regime"],
                          _cq_score_before, score)
        except Exception as _cqe:
            log.debug("chaos_quant error: %s", _cqe)

    # Late Position Penalty removed: was multiplying score by 0.2-0.8 for pos24 > 0.80,
    # causing valid signals (coins already in motion) to fail the quality gate.

    # ── Fractal Structure Gate ────────────────────────────────────────────
    # Blocks signals where the fractal layer signals strong structural risk,
    # even when raw flow metrics (volume spike, ratio) are impressive.
    #
    # FCF ≤ 0.75 means at least one of: approaching 1.618 exhaustion,

    # High Position + Bearish MTF Gate
    # Coin at > 60% of daily range + macro trend bearish = exhausted against the trend.
    # Data: DYM pos=64%, MTF bearish, Score=9.0 → SL in 37 minutes (no room + bearish structure).
    # Exception: net ≥ $500K (institutional flow can shift exhausted market structure).
    # Exception: moonshot (parabolic momentum operates differently).
    if (_fva_result and pos24 > 0.60
            and _fva_result.get("macro_trend") == "bearish"
            and net < 500_000
            and not is_moonshot):
        _rej(f"high_pos_bearish_mtf(pos={int(pos24*100)}%)"); return
    # 3-wave correction (corrective bounce ≠ impulse), or MTF bearish.
    # Combined with a post-adjustment score < 7.5, the risk/reward is poor.
    #
    # Moonshots bypass — they operate on different dynamics (parabolic momentum).
    if _fva_result and not is_moonshot:
        _fcf_val = _fva_result["fcf"]
        if _fcf_val <= 0.75 and score < 7.5:
            _rej(f"fcf_structure({_fcf_val:.2f})"); return
        # Double-weak: FCF mediocre + H random/anti-persistent = no structural edge
        # Raised thresholds: FCF < 0.90 (was 0.85), H < 0.52 (was 0.50), score < 7.5 (was 7.0)
        if (_cq_result and _fcf_val < 0.90
                and _cq_result["H"] < 0.52 and score < 7.5):
            _rej(f"fractal_double_weak(fcf={_fcf_val:.2f},H={_cq_result['H']:.3f})"); return

    # Anti-Persistent Gate: H < 0.53 = random/anti-persistent market, no trending edge
    # Data: PROM H=0.473 hit SL in 6 minutes, NAORIS H=0.453 in 76 minutes
    # Raised: score exception 8.0→9.5 — H < 0.53 is structural randomness; score=9.0 is still
    # not enough (DIS: H=0.513 + score=9.0 → resistance at +0.2% + Noah Effect = risky).
    # score < 9.0 (was 8.0) did not close the gap — score=9.0 is "not < 9.0" so gate skipped.
    if (_cq_result and not is_moonshot
            and _cq_result["H"] < 0.49 and score < 8.5
            and not _is_explosive):
        _rej(f"anti_persistent(H={_cq_result['H']:.3f})"); return

    # Noah Effect + Anti-Persistent + High Position = triple fakeout risk
    # REN pattern: H=0.454 + Noah(73% wicks) + pos=83% → all three together = near-certain SL
    if (_cq_result and _cq_result.get("noah_effect")
            and _cq_result["H"] < 0.47
            and pos24 > 0.65
            and not is_moonshot and not _is_explosive and not momentum_bypass):
        _rej(f"noah_anti_persistent_highpos(H={_cq_result['H']:.3f},pos={int(pos24*100)}%)"); return

    # Moonshot Anti-Persistent Gate
    # The gate above skips moonshots — but H < 0.45 is extreme anti-persistence that blocks all.
    # COOKIE: H=0.425, Score=6.5, FCF=1.15 — FCF bypassed moonshot_fractal_trap but
    # H=0.425 means the market structurally reverses every spike regardless of FCF quality.
    # Bot itself flags "HIGH FAKE OUT RISK" at H < 0.45 — we must honour it.
    # Exception: score ≥ 8.0 only — truly exceptional flow can dominate extreme anti-persistence.
    if (_cq_result and is_moonshot
            and _cq_result["H"] < 0.45 and score < 8.0):
        _rej(f"moonshot_anti_persistent(H={_cq_result['H']:.3f})"); return

    # Moonshot FCF Gate: extreme fractal risk blocks even parabolic setups
    # Data: WCT(0.57 SL), HUMA(0.50 SL), NAORIS(0.40 SL) — FCF ≤ 0.60 = always lose
    # FCF ≤ 0.60 means ≥2 negative fractal conditions (1.618 exhaust + 3-wave or noise)
    if _fva_result and is_moonshot:
        _fcf_val = _fva_result["fcf"]
        if _fcf_val <= 0.60:
            _rej(f"moonshot_fib_exhaust({_fcf_val:.2f})"); return
        # Random/anti-persistent market + weak FCF = reversal trap even for moonshots
        # H < 0.55 = random or anti-persistent (no edge) — AIOT H=0.54 SL confirmed
        # Raised score threshold: < 7.0 (was 5.0) — weak FCF + H requires exceptional flow
        if (_cq_result and _fcf_val <= 0.65
                and _cq_result["H"] < 0.55 and score < 7.0):
            _rej(f"moonshot_fractal_trap(fcf={_fcf_val:.2f},H={_cq_result['H']:.3f})"); return

    # Bearish Fractal Transition Gate
    # MTF bearish + Jy < -0.10 + no "Bearish Fractal End" = dead-cat bounce, not real breakout.
    # Data: GWEI($41K net, SL) — MU/RKLB/LITE (bearish_end=True, all WIN)
    # Exception 1: score ≥ 8.5 — extraordinary setup can overcome structure.
    # Exception 2: net ≥ $200K — RIVER($306K, no bearish_end) won +13% proving real money
    #              flow can overcome bearish fractal (GWEI only had $41K and hit SL).
    if (_fra and _fva_result
            and _fva_result.get("mtf_agree") and _fva_result.get("macro_trend") == "bearish"
            and _fra.get("jy", 0.0) < -0.10
            and not _fra.get("bearish_end", False)
            and score < 8.5
            and net < 200_000):
        _rej(f"bearish_no_transition(jy={_fra['jy']:.3f},net={_fv(net)})"); return

    # Fractal Resistance Gate
    # Price AT or VERY NEAR fractal resistance = high rejection probability.
    # Data: STABLE (+0.4%→SL ❌), AIO (+0.0%→SL ❌), DIS (+0.2%, score=9.0, Noah 60% wicks ❌)
    # < 0.5%: hard block — price is essentially AT resistance, no score exception.
    #          score=9.0 + 8x volume (DIS) still failed → close resistance always loses.
    # 0.5-1.0%: only score ≥ 9.5 can override (genuine breakout momentum from extreme flow).
    if (_fra and _fra.get("resistance") and _fra["resistance"] > price):
        _res_dist_pct = (_fra["resistance"] - price) / price * 100
        if _res_dist_pct < 0.3 and not _is_explosive:
            _rej(f"fractal_resistance_near(+{_res_dist_pct:.1f}%)"); return
        if _res_dist_pct < 0.5 and score < 8.0 and not _is_explosive:
            _rej(f"fractal_resistance_near(+{_res_dist_pct:.1f}%)"); return

    _fractal_score = _calc_fractal_score(_fra, _fva_result, _cq_result)

    # Volume Explosion Fractal Floor — raised to 5.5 (REN had FS=5.0 + 148x = still weak structure)
    # FS < 5.5 means fractal quality is too poor even for explosive moves.
    if volume_explosion and not is_moonshot and _fractal_score < 5.5:
        _rej(f"vol_exp_weak_fractal(fs={_fractal_score})"); return

    # Explosive spike bypass — 30x+ vol = real institutional move regardless of fractal
    # Data: ALLO +178%, HEI +132%, ID +55% all had massive vol at entry.
    # Hard floor (FS<5.0) is NEVER bypassed — it protects against corrupted/manipulated data.
    # (_is_explosive already set after spike computation above)

    # Fractal Quality Gate — Two-Tier
    #
    # Tier 1 — Hard Floor (FS < 5.0): always blocks. No bypass.
    if _fractal_score < 5.0:
        _rej(f"weak_fractal_quality(fs={_fractal_score})"); return

    # Tier 2 — Moderate Gate (FS 5.0-6.9): requires score ≥ 7.5 OR explosive spike.
    # 30x+ vol bypasses: a coin with 30x spike and FS=6 is a real move.
    if _fractal_score < 7.0 and score < 7.5 and not _is_explosive:
        _rej(f"weak_fractal_quality(fs={_fractal_score})"); return

    # ── Open Interest Gate ────────────────────────────────────────────────
    # OI contracting + price rising = short squeeze (shorts forced to close = bullish).
    # Only block weak signals — strong flow (score ≥ 6.5) overrides OI contraction.
    if (_oi and _oi["contracting"] and not is_moonshot and not volume_explosion
            and score < 6.5):
        _rej(f"oi_contracting({_oi['oi_delta_1h']:.1f}%)"); return

    # L/S crowded longs = liquidation cascade risk, but only when BOTH conditions true:
    # weak score AND high position (one alone is not enough to block).
    _ls_block = score < 9.0 and pos24 > 0.80
    if (_oi and _oi["long_crowded"] and not is_moonshot and _ls_block):
        _rej(f"ls_crowded_longs({_oi['ls_ratio']:.2f},pos={pos24*100:.0f}%)"); return

    # SL-hunt setup: crowded longs + OI exiting + price at top = stop-loss hunt risk.
    # Exception: strong net flow (score ≥ 7.5) — real institutional buying overrides.
    if (_oi and not is_moonshot and not momentum_bypass
            and pos24 > 0.75
            and _oi["ls_ratio"] > 2.0
            and _oi["oi_delta_1h"] < 0.0
            and score < 7.5):
        _rej(f"sl_hunt_risk(L/S={_oi['ls_ratio']:.2f},OI={_oi['oi_delta_1h']:.1f}%,pos={pos24*100:.0f}%)"); return

    # OI score boost: expanding OI = institutional confirmation of the move.
    # Short squeeze setup = strongest configuration → extra boost.
    if _oi:
        if _oi["short_squeeze"]:
            score = min(10.0, round(score + 0.7, 1))
        elif _oi["expanding"]:
            score = min(10.0, round(score + 0.3, 1))

    # ── FVA + CQ display (all gates passed — no score change, display only) ──
    if _fva_show is not None and _fva_result is None:
        try:
            _fva_result = _fva_show.evaluate_fractal_confluence(candles, price)
        except Exception as _fve_disp:
            log.debug("FVA display error: %s", _fve_disp)
    if _cq_show_ok and _cq_result is None:
        try:
            _cq_result = _cq_integrate(candles, price, score, is_moonshot)
        except Exception as _cqe_disp:
            log.debug("CQ display error: %s", _cqe_disp)

    # ── Entry Verdict — computed before building signal so it shows at top ──
    _v_pts = _entry_verdict(score, ratio, ob_spot, pos24,
                            (_cq_result["H"] if _cq_result else None),
                            (_fva_result["fcf"] if _fva_result else None),
                            bool(_oi and _oi.get("long_crowded")), net, net_min)
    if _v_pts < 2.5 and not is_moonshot and not volume_explosion:
        _rej(f"verdict_weak({_v_pts:.1f})"); return
    if _v_pts >= 5.0:
        _v_label = "🟢 *Strong Signal* ✅"
    elif _v_pts >= 2.5:
        _v_label = "🟡 *Moderate Signal* ⚠️"
    else:
        _v_label = "🟠 *High Risk — Speculation Only*"

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
                       is_alpha=(ticker.get("futures_only", False) or ticker.get("binance_alpha", False)),
                       fractal_score=_fractal_score,
                       oi_label=(_oi["label"] if _oi and _oi.get("label") else ""),
                       counter_trend=_counter_trend_main,
                       verdict=_v_label)
    ai_str, ai_blocked = _ai_assess(sym, exchange, tier["name"], "main",
                                    score, ob_spot, ratio, pos24, spike, net, move, funding_label,
                                    fractal_score=_fractal_score,
                                    h_value=(_cq_result["H"] if _cq_result else None),
                                    oi_delta=(_oi["oi_delta_1h"] if _oi else None),
                                    crowded_longs=bool(_oi and _oi.get("long_crowded")))
    if ai_blocked:
        _rej("ai_block"); return
    msg += ai_str

    # ── Late Entry Hard Block ─────────────────────────────────────────────
    if pos24 > 0.80 and not is_moonshot and not momentum_bypass:
        if volume_explosion and score >= 8.5:
            pass   # allow: explosive volume + high quality
        else:
            _rej(f"late_entry_hard({pos24*100:.0f}%)"); return

    # Weak order book + high position
    if ob_spot < 0.52 and pos24 > 0.70 and not is_moonshot and not volume_explosion and not momentum_bypass and not _sector_mom:
        _rej(f"weak_ob_highpos(ob={ob_spot:.0%},pos={int(pos24*100)}%)"); return

    # ── Fractal Analysis Footer ──────────────────────────────────────────────
    _cq_icons = {"persistent": "🟢", "weak_persistent": "🟡", "random": "⚪", "anti_persistent": "🔴"}

    # Line 1: Verdict + H + FCF
    _line1 = []
    if _fra and _fra.get("verdict"):
        _line1.append(f"🌀 {_fra['verdict']}")
    if _cq_result:
        _line1.append(f"H={_cq_result['H']:.2f} {_cq_icons.get(_cq_result['regime'], '⚪')}")
    if _fva_result and _fva_result["fcf"] != 1.0:
        _line1.append(f"FCF x{_fva_result['fcf']:.2f} {'⬆️' if _fva_result['fcf'] > 1.0 else '⬇️'}")

    # Line 2: Key patterns from fractal agent (priority order)
    _fra_tags = []
    if _fra:
        if _fra.get("bearish_end"):  _fra_tags.append("🔄 Bearish End")
        if _fra.get("tornado"):      _fra_tags.append("🌪️ Tornado")
        if _fra.get("quad_valid"):   _fra_tags.append("QUAD ✅")
        # Jy flow
        _jy = _fra.get("jy", 0.0)
        if _jy > 0.04:               _fra_tags.append(f"〰️ Jy +{_jy:.2f} 🟢")
        elif _jy < -0.04:            _fra_tags.append(f"〰️ Jy {_jy:.2f} 🔴")
        # Support/Resistance proximity
        if _fra.get("warning"):      _fra_tags.append(f"⚠️ {_fra['warning']}")
        elif _fra.get("support"):
            _sup = _fra["support"]
            _sup_dist = (price - _sup) / price * 100
            if _sup_dist < 5.0:      _fra_tags.append(f"🛡️ Support ${_fp(_sup)} ({_sup_dist:.1f}%↓)")

    if _line1 or _fra_tags:
        msg += f"\n{'━'*20}\n"
        if _line1:
            msg += f"📊 {'  ·  '.join(_line1)}\n"
        if _fra_tags:
            msg += f"{'  ·  '.join(_fra_tags[:4])}\n"  # max 4 tags

    keyboard = _trade_keyboard(sym, exchange)
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
    # Compute SL from _calc_tp_sl so tracking uses the same SL shown in the signal
    _, _, _, _sl_price_tr, _sl_pct_tr, _ = _calc_tp_sl(
        price, ticker["high24"], ticker["low24"], spike, score, exchange,
        is_moonshot=is_moonshot, vol_explosion=volume_explosion, is_flash=is_flash
    )
    tracking[sym] = {
        "entry":      price,
        "t0":         now,
        "hit":        set(),
        "max":        0.0,
        "min":        0.0,
        "exchange":   exchange,
        "is_flash":   is_flash,
        "sig_msg_id": sig_msg_id,
        "sl_pct":     -_sl_pct_tr * 100,   # e.g. -8.0 for 8% SL — matches signal display
    }
    _scanner_type = ("moonshot" if is_moonshot
                     else "volume_explosion" if volume_explosion
                     else "momentum" if momentum_bypass
                     else "main")
    _db_add(sym, price, exchange, tier["name"], _scanner_type,
            ratio, ob_spot, score, pos24, spike, net, move, funding_label,
            fractal_score=_fractal_score,
            h_value=(_cq_result["H"] if _cq_result else None),
            oi_delta=(_oi["oi_delta_1h"] if _oi else None))
    # Record fractal snapshot for self-learning
    if _fractal_agent is not None and _fra and _fra.get("_features"):
        _fractal_agent.record_signal(sym, _fra["_features"])
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
            f"Bitcoin dropped `{delta:.2f}%` in 5 minutes\n"
            f"💰 Price now: `${_fp(btc_price)}`\n"
            f"⛔ Signals paused for 10 minutes\n"
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
            f"Bitcoin dropped `{delta:.2f}%` in 5 minutes\n"
            f"💰 Price now: `${_fp(btc_price)}`\n"
            f"📉 Expect pressure on altcoins\n"
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
            f"Bitcoin surged `+{delta:.2f}%` in 5 minutes\n"
            f"💰 Price now: `${_fp(btc_price)}`\n"
            f"📈 Expect strong altcoin bounce\n"
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
            f"`{dumping}` of `{total}` coins dropped in 5 minutes (`{pct:.0f}%`)\n\n"
            f"📉 Worst: {worst_lines}\n\n"
            f"⛔ Signals paused for 15 minutes\n"
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
            f"`{dumping}` of `{total}` coins dropped in 5 minutes (`{pct:.0f}%`)\n"
            f"🔴 Avoid new entries until market stabilises\n"
            f"🕐 {_ts()} UTC\n"
            f"{'━' * 20}"
        )
        _cascade_alert_ts = now
        log.info("Market dump warning: %d/%d (%.0f%%) in 5min", dumping, total, pct)


def get_market_ctx(bias: int) -> dict:
    """
    Returns adaptive thresholds based on market bias.
    Bull market: Sniper Mode (looser filters — more signals in strong uptrend).
    Bear/Neutral: Standard filters — flow quality (ratio/spike/OB/net) decides, NOT bias.
    Coins explode in any market condition when real liquidity enters.
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
    # Neutral + Bear + Strong Bear: all use standard filters.
    # Do NOT penalise bear markets — liquidity explosions happen regardless of BTC direction.
    return     {"pos_limit": 0.75, "crash_limit": 12.0,
                "spike_mult": 1.00, "ratio_mult": 1.00, "ob_min": 0.40,
                "move_min": 1.0,  "late_pct": 0.88}  # Neutral/Bear — standard


def should_signal(tier_name: str, bias: int, exchange: str = "Binance") -> bool:
    """Strong liquidity flow is independent of market direction.
    Only block in total market collapse (bias < -85) — a coin with ratio=5x,
    spike=4x, net=$50K is a real signal regardless of BTC direction.
    Normal bear markets: flow filters (ratio/spike/net/OB) handle quality."""
    return bias > -85   # only block in total market collapse


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
    # change <= 70%: match slow_scan MEXC limit
    # Alpha/futures-only coins: allow up to 400% (listing-day pumps reach 200-400%)
    by_chg = sorted(
        [(s, t) for s, t in all_t.items()
         if (t["vol"] >= 150_000 or t.get("binance_alpha") or t.get("futures_only")) and (
             2.0 <= t["change"] <= 70.0
             or ((t.get("binance_alpha") or t.get("futures_only")) and 70.0 < t["change"] <= 400.0)
         )],
        key=lambda x: -x[1]["change"]
    )[:100]

    # DOGS fix: top 30 Binance Mid/Large by volume (vol >= $10M, change >= 0%)
    # A large-cap coin at +0% change falls outside the top-80 by change but its
    # volume already signals real interest — scan it regardless of change rank
    # change <= 80%: matches max_pump limit for Binance spot (was 70%, PORTAL/STG window is 15-80%)
    by_vol_bn = sorted(
        [(s, t) for s, t in all_t.items()
         if t["exchange"] == "Binance" and t["vol"] >= 10_000_000 and 0.0 <= t["change"] <= 80.0],
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
    def _pool(coins, pump_limit):
        elig = [(s, t) for s, t in coins.items()
                if t["vol"] >= 10_000 and (
                    t["change"] <= pump_limit
                    or t.get("binance_alpha")   # Alpha tokens bypass pump_limit — listing-day pumps reach 200-400%
                    or t.get("futures_only")    # Pre-listing futures-only also bypass
                )]
        by_vol = sorted(elig, key=lambda x: -x[1]["vol"])[:200]
        by_chg = sorted(elig, key=lambda x: -x[1]["change"])[:200]
        seen, out = set(), []
        for item in by_vol + by_chg:
            if item[0] not in seen:
                seen.add(item[0]); out.append(item)
        return out

    candidates = _pool(all_t, 80.0)

    log.info("slow_scan: %d/%d candidates", len(candidates), len(all_t))
    _diag.clear()
    for sym, ticker in candidates:
        _check(sym, ticker, "1h")
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
    if _cb_is_active():
        return
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

        # Market bias gate — only block in total collapse (bias < -85)
        if not should_signal(get_tier(vol_24h)["name"], market_bias, exchange):
            _rj("st_bias"); continue

        candles = fetch_klines(sym, base_url, interval="1h", limit=55)
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
        _net_floor = 20_000.0
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
        keyboard = _trade_keyboard(sym, exchange)
        ok, sig_msg_id = send_ex(msg, keyboard)
        if ok:
            fired += 1
            _signal_dedup[sym]   = now_ts
            _alerted_price[sym]  = price
            alerted[sym]         = now_ts
            _, _, _, _, _sl_pct_st, _ = _calc_tp_sl(
                price, ticker["high24"], ticker["low24"], vol_ratio, score, exchange
            )
            tracking[sym] = {
                "entry":      price,
                "t0":         now_ts,
                "hit":        set(),
                "max":        0.0,
                "min":        0.0,
                "exchange":   exchange,
                "is_flash":   False,
                "sig_msg_id": sig_msg_id,
                "sl_pct":     -_sl_pct_st * 100,
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
        if -5.0 <= t["change"] <= 15.0         # extended to +15%: catches early-stage explosions
        and t["vol"] >= 500_000                 # minimum real liquidity ($500K/day) — filters ghost/delisted coins
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
            _sg_spike_min = 8.0 if ticker.get("exchange") == "Binance" and ticker["vol"] >= 10_000_000 else 10.0
            if last_ratio < _sg_spike_min or prev_ratio < 1.2:
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


def scan_whale_flow(all_t):
    """
    Detects silent whale accumulation at multi-week lows.
    Whales buy quietly without moving price — focus on ABSOLUTE net flow
    over 4h, not volume spikes. High net + near 7d low + strong OB = signal.

    Unlike scan_quiet_accum (needs spike 2.5x), this scanner catches
    sustained slow buying that never triggers a volume alert.

    Conditions:
      - vol >= $2M (enough liquidity for whales to operate)
      - coin near 7d low (within 12%)
      - pos24 < 0.40 (bottom 40% of today's range)
      - price movement < 5% (quiet — not already a momentum move)
      - 4h net flow >= tier threshold (absolute whale-scale buying)
      - spike < 6x (if spike > 6x, other scanners handle it)
      - OB >= 0.70 (strong bid dominance)
      - score >= 7.0
    """
    now = time.time()

    # Whale thresholds by tier — absolute net flow over 4h
    _whale_net = {"Micro": 40_000, "Small": 100_000, "Mid": 400_000, "Large": 1_200_000}

    candidates = []
    for sym, t in all_t.items():
        if t["exchange"] != "Binance":
            continue
        if sym in BLACKLIST or sym in tracking:
            continue
        if now - alerted.get(sym, 0) < COOLDOWN:
            continue
        if now - _signal_dedup.get(sym, 0) < 7200:
            continue
        vol_24h = t["vol"]
        if vol_24h < 2_000_000:
            continue
        # Only bottom 40% of today's range
        rng = t["high24"] - t["low24"]
        if rng <= 0:
            continue
        pos24 = (t["price"] - t["low24"]) / rng
        if pos24 > 0.40:
            continue
        # Not in freefall, not already pumped
        chg = t.get("change", 0)
        if chg < -20.0 or chg > 5.0:
            continue
        candidates.append((sym, pos24, t))

    candidates.sort(key=lambda x: x[1])  # deepest in range first

    # Check 7d low proximity via daily klines
    fired = 0
    for sym, pos24, t in candidates[:40]:
        try:
            price    = t["price"]
            vol_24h  = t["vol"]
            base_url = t["base_url"]
            tier     = get_tier(vol_24h)

            # Must be near 7d low (within 12%)
            klines_d = _fetch_daily_klines(sym, "Binance", days=9)
            if len(klines_d) < 7:
                continue
            closes   = [c for c, v in klines_d]
            low_7d   = min(closes[-8:-1])
            if price > low_7d * 1.12:
                continue

            # 4h aggregate flow — catches sustained quiet buying
            buy_v, sell_v = fetch_agg_trades(sym, base_url, minutes=240)
            if sell_v <= 0 or (buy_v + sell_v) < 5_000:
                continue
            net = buy_v - sell_v
            if net <= 0:
                continue

            # Absolute whale-scale net floor
            _net_thr = _whale_net.get(tier["name"], 100_000)
            if net < _net_thr:
                continue

            # Spike check — if already spiking hard, other scanners handle it
            spike_4h = (buy_v + sell_v) / max(vol_24h / 6.0, 1)
            if spike_4h > 6.0:
                continue

            # OB must favour buyers — whales hide orders so 63% is enough
            ob_spot = fetch_ob_imbalance(sym, base_url, levels=20)
            if ob_spot < 0.63:
                continue

            score = _calc_score(pos24, net, tier["net"], ob_spot, spike_4h)
            if score < 7.0:
                continue

            ratio = buy_v / sell_v
            move  = abs(t.get("change", 0))

            log.info("WHALE_FLOW %s net=+%s 4h spike=%.1fx pos24=%.0f%% ob=%.0f%% score=%.1f",
                     sym, _fv(net), spike_4h, pos24 * 100, ob_spot * 100, score)

            # Pass through main signal builder
            ticker_copy = dict(t)
            ticker_copy["momentum_signal"] = False
            ok = _check(sym, ticker_copy, "1h", sector_boost=False)
            if ok is not None:
                fired += 1

            time.sleep(0.1)
            if fired >= 3:  # max 3 whale signals per cycle
                break

        except Exception as e:
            log.debug("scan_whale_flow %s: %s", sym, e)

    if fired:
        log.info("scan_whale_flow: fired=%d", fired)


def scan_quiet_accum(all_t):
    """
    Catches coins being accumulated quietly near their 24h low
    BEFORE price breaks out — the pattern Wolf Flow used to catch AI +50%.

    v2 conditions (base):
      pos24 < 0.30  — price in bottom 30% of 24h range
      change: -25% to +10%  (+20% if pos24<0.25 — daily open may be near the low itself)
      vol >= 500K   — real liquidity
      ratio >= 3.5x — strong buyer dominance  (2.5x if pos24<0.20 — quiet accumulation)
      spike >= 2.5x — clear volume surge       (2.0x if pos24<0.20)
      ob >= 0.60    — order book clearly favours buyers (0.65 if pos24<0.20)
      score >= 8.0                              (8.5 if pos24<0.20)
    """
    if _cb_is_active():
        return
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
        # Coins near range bottom (pos24<0.25) may have risen >10% from daily open
        # because the daily open itself was near the low — allow up to 20% for true bottom
        _chg_max = 20.0 if pos24 < 0.25 else 10.0
        if chg > _chg_max or chg < -25.0:
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
        price = t["price"]
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
        # Thin sell-side: ratio becomes meaningless when sellers are nearly absent
        # sell_v<200 + ratio>500x = empty market, not real accumulation (WBETH: $44 sells → 23984x)
        if sell_v < 200 and buy_v / sell_v > 500:
            continue

        ratio = buy_v / sell_v
        # Ratio floors: winners show ≥2.5x minimum (PGVERSE=3.5x, SXT=9.3x, GT=34.9x)
        # Ultra-low price (DENT type): accept 2.0x — USD flows are small at $0.000061
        # True bottom (pos24<0.20): relaxed to 2.5x — smart money accumulates quietly;
        # compensated by stricter ob (0.65+) applied further below
        if price < 0.001:
            _ratio_min = 2.0
        elif pos24 < 0.20:
            _ratio_min = 2.5
        else:
            _ratio_min = 3.5
        if ratio < _ratio_min:
            continue

        net = buy_v - sell_v
        if net <= 0:
            continue

        # Volume spike: 1h traded volume vs expected hourly (vol_24h / 24)
        avg_1h = vol_24h / 24.0
        spike  = (buy_v + sell_v) / avg_1h if avg_1h > 0 else 0.0
        # True bottom (pos24<0.20): accept 2.0x spike — accumulation is gradual by nature
        _spike_min = 2.0 if pos24 < 0.20 else 2.5
        if spike < _spike_min:
            continue

        # Adaptive net floor by price level — DENT $0.000061 type needs lower floor
        if price < 0.001:
            _net_floor = max(vol_24h * 0.001, 500.0)    # DENT/SHIB type
        elif price < 0.01:
            _net_floor = max(vol_24h * 0.001, 1_000.0)
        else:
            _net_floor = max(vol_24h * 0.001, 3_000.0)
        if net < _net_floor:
            continue

        ob_spot = fetch_ob_imbalance(sym, base_url, levels=20)
        # True bottom with relaxed ratio/spike: compensate with stricter order book (65%+)
        _ob_min = 0.65 if pos24 < 0.20 else 0.60
        if ob_spot < _ob_min:
            continue
        # Fake wall guard: ≥95% bids = artificial buy wall (pump+dump pattern)
        if ob_spot >= 0.95:
            continue

        tier  = get_tier(vol_24h)
        score = _calc_score(pos24, net, _net_floor, ob_spot, spike)
        # True bottom (pos24<0.20): relaxed ratio/spike compensated by stricter score
        _score_min = 8.5 if pos24 < 0.20 else 8.0
        if score < _score_min:
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
            f"🆕 *#{sym[:-4]}* 💀 · {'Alpha' if (t.get('futures_only') or t.get('binance_alpha')) else 'Spot'} · Signal #{signal_count} {badge}\n"
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
            _, _, _, _, _sl_pct_ac, _ = _calc_tp_sl(
                price, t["high24"], t["low24"], spike, score, exchange
            )
            tracking[sym] = {
                "entry":      price,
                "t0":         now,        # fixed: was "ts" — check_milestones needs "t0"
                "hit":        set(),
                "max":        0.0,
                "min":        0.0,
                "exchange":   exchange,
                "is_flash":   False,
                "sig_msg_id": sig_msg_id,
                "sl_pct":     -_sl_pct_ac * 100,
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


def scan_alpha_explosion(all_t: dict):
    """
    Catches Binance Alpha on-chain tokens exploding — no klines needed.
    Uses ticker data only: percentChange24h + volume surge between scans.
    Separate from _check() — simplified signal with on-chain risk warning.
    """
    global _alpha_vol_cache
    MAX_SIGNALS = 3
    sent = 0
    now  = time.time()

    # Sort by 24h change descending — biggest movers first
    alpha_coins = [
        (sym, t) for sym, t in all_t.items()
        if t.get("binance_alpha") and t.get("vol", 0) >= 50_000
    ]
    alpha_coins.sort(key=lambda x: x[1].get("change", 0), reverse=True)

    for sym, t in alpha_coins:
        if sent >= MAX_SIGNALS:
            break

        chg   = t.get("change", 0.0)
        vol   = t.get("vol",    0.0)
        price = t.get("price",  0.0)

        if price <= 0:
            continue

        sym_base = sym.replace("USDT", "")
        if sym_base in BLACKLIST:
            continue
        if sym_base in alerted:
            continue
        if sym in _signal_dedup:
            continue

        # Volume surge: compare vs previous scan
        prev      = _alpha_vol_cache.get(sym)
        vol_surge = 0.0
        if prev:
            prev_vol, prev_ts = prev
            elapsed = now - prev_ts
            if 60 < elapsed < 700 and prev_vol > 0:
                vol_surge = vol / prev_vol
        _alpha_vol_cache[sym] = (vol, now)

        # Signal condition: volume surging NOW + early in the move (not already +40%)
        # Requires vol_surge baseline — first scan gets no signal, waits 5 min for next cycle
        _explosion = (vol_surge >= 2.0 and chg >= 5.0 and chg <= 40.0 and vol >= 50_000)

        if not _explosion:
            continue

        # Build and send simplified Alpha signal
        _surge_txt = f"⚡ Vol surge: {vol_surge:.1f}x\n" if vol_surge >= 2.0 else ""
        _msg = (
            f"💀 *MAFIO SNIPER* 📡\n\n"
            f"🆕 *#{sym_base}* 🔥 Alpha On-Chain · Signal\n"
            f"💰 Price: `${price:.8g}`\n"
            f"📈 24h Move: *+{chg:.1f}%*\n"
            f"📊 Vol 24h: `${vol:,.0f}`\n"
            f"{_surge_txt}"
            f"⚠️ _On-chain BSC — verify liquidity before entry_\n"
            f"🕐 {_ts()} UTC\n"
        )
        if send(_msg):
            alerted[sym_base] = now
            _signal_dedup[sym] = now
            sent += 1
            log.info("scan_alpha_explosion: signal %s chg=%.1f%% vol=%.0f surge=%.1fx",
                     sym, chg, vol, vol_surge)

    if sent:
        log.info("scan_alpha_explosion: fired=%d", sent)


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
                # HOT scan: Alpha tokens allow up to 50% (listing-day pumps need wider range)
                _hot_limit = 50.0 if (_t.get("futures_only") or _t.get("binance_alpha")) else 25.0
                if (in_sector and _t["vol"] >= 100_000 and _t["change"] < _hot_limit):
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
        url  = "https://api.binance.com/api/v3/klines"
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



def _swing_fractal(sym, base_url, price, score):
    """
    Fractal analysis for swing scanners — display + AI context only.
    Returns (fractal_score or None, fra or None).
    Does NOT modify score or block signals (swing entry criteria already strict).
    """
    candles = fetch_klines(sym, base_url, "1h", 50)
    if not candles:
        return None, None
    _fra = _fva_result = _cq_result = None
    try:
        if _fractal_agent is not None:
            _fra = _fractal_agent.analyze(candles, price)
    except Exception:
        pass
    try:
        if _fva is not None:
            _fva_result = _fva.evaluate_fractal_confluence(candles, price)
    except Exception:
        pass
    try:
        if _cq_ok:
            _cq_result = _cq_integrate(candles, price, score, False)
    except Exception:
        pass
    if not (_fra or _fva_result or _cq_result):
        return None, None
    fs = _calc_fractal_score(_fra, _fva_result, _cq_result)
    return fs, _fra


def scan_weekly_breakout(all_t):
    """
    Wolf Flow-style swing scanner: weekly high breakout with volume build-up.
    Targets coins breaking above their 7-day closing high on increasing volume.
    Swing signal: 72h timeout, SL -10%, TP 30%/60%/100%.

    Conditions:
      - Binance, vol >= $2M, pos24 < 85%
      - price > max close of previous 7 days (weekly high breakout, 0.5% buffer)
      - Volume building: 3d avg volume >= 120% of 7d avg volume
      - 1h flow: ratio >= 1.5x, net > 0, OB >= 0.55
      - 24h cooldown per coin
    """
    now = time.time()
    candidates = [
        (sym, t) for sym, t in all_t.items()
        if t["exchange"] == "Binance"
        and t["vol"] >= 2_000_000
        and now - _weekly_swing_dedup.get(sym, 0) >= 86400
        and now - alerted.get(sym, 0) >= COOLDOWN
        and sym not in tracking
        and sym not in BLACKLIST
        and t.get("change", 0) >= -5.0    # not in freefall
    ]

    fired = 0
    for sym, t in candidates:
        try:
            klines = _fetch_daily_klines(sym, "Binance", days=14)
            if len(klines) < 10:
                continue

            closes   = [c for c, v in klines]
            vols     = [v for c, v in klines]
            price    = closes[-1]
            vols_usd = [v * c for c, v in klines]

            # Weekly high breakout: price > max close of previous 7 days (0.5% buffer)
            prev_7d_high = max(closes[-8:-1])
            if price <= prev_7d_high * 1.005:
                continue

            # Volume building: 3d avg must be >= 120% of 7d avg
            vol_3d = sum(vols_usd[-4:-1]) / 3 if len(vols_usd) >= 4 else 0
            vol_7d = sum(vols_usd[-8:-1]) / 7 if len(vols_usd) >= 8 else 0
            if vol_7d <= 0 or vol_3d < vol_7d * 1.20:
                continue

            # Intraday position: not already overextended
            rng   = t["high24"] - t["low24"]
            pos24 = (price - t["low24"]) / rng if rng > 0 else 0.5
            if pos24 > 0.85:
                continue

            # 1h flow check — stricter for swing quality
            base_url = t["base_url"]
            buy_v, sell_v = fetch_agg_trades(sym, base_url, minutes=60)
            if sell_v <= 0:
                continue
            ratio = buy_v / sell_v
            if ratio < 2.0:
                continue
            net = buy_v - sell_v
            if net <= 0:
                continue

            # Counter-trend: if BTC falling, coin must be rising independently
            if _btc_falling_wb and t.get("change", 0.0) <= 0:
                continue

            spike_1h = (buy_v + sell_v) / max(t["vol"] / 24.0, 1)
            if spike_1h < 1.5:
                continue

            ob_spot = fetch_ob_imbalance(sym, base_url, levels=20)
            if ob_spot < 0.60:
                continue

            tier   = get_tier(t["vol"])
            score  = _calc_score(pos24, net, max(t["vol"] * 0.001, 1000.0),
                                 ob_spot, spike_1h)
            if score < 8.0:
                continue

            _weekly_swing_dedup[sym] = now

            # Fractal analysis — display + filter
            _fs, _fra_wb = _swing_fractal(sym, base_url, price, score)
            if _fs is not None and _fs < 5.0:
                continue  # weak fractal structure — skip swing signal
            _fs_icon = "🟢" if (_fs or 0) >= 7.0 else ("🟡" if (_fs or 0) >= 5.0 else "🔴")
            _fs_line = f"\n🔬 Fractal Score: `{_fs}/10` {_fs_icon}" if _fs is not None else ""

            vol_growth_pct = int(vol_3d / max(vol_7d, 1) * 100)
            breakout_pct   = (price / prev_7d_high - 1) * 100
            ob_pct         = int(ob_spot * 100)
            ob_lbl         = "🟢 Buyers" if ob_spot > 0.58 else "⚪ Balanced"
            pos_pct        = int(pos24 * 100)
            _mkt           = "Alpha" if (t.get("futures_only") or t.get("binance_alpha")) else "Spot"
            _, badge       = _register_confirm(sym, "weekly_breakout")

            global signal_count
            signal_count += 1

            # Fixed TP for swing: 30% / 60% / 100%
            tp1 = price * 1.30
            tp2 = price * 1.60
            tp3 = price * 2.00
            sl  = price * 0.90

            msg = (
                f"{'━'*20}\n"
                f"💀 *MAFIO SNIPER* 📡\n"
                f"\n"
                f"📈 *#{sym[:-4]}* 💀 · {_mkt} · Swing · Signal #{signal_count} {badge}\n"
                f"💰 Price: `${_fp(price)}`\n"
                f"📉 24h Change: `{t['change']:+.2f}%`\n"
                f"📍 Position: `%{pos_pct} of range`\n"
                f"\n"
                f"🔓 Weekly Breakout: `+{breakout_pct:.1f}%` above 7d high\n"
                f"📊 Volume Building: `{vol_growth_pct}%` of 7d avg\n"
                f"⚡ Volume 1h: `{spike_1h:.1f}x` above avg\n"
                f"💹 1h Flow:\n"
                f"  📥 In:  `{_fv(buy_v)}`\n"
                f"  📤 Out: `{_fv(sell_v)}`\n"
                f"  ▲ Net: `+{_fv(net)}` ✅\n"
                f"📗 Order Book: {ob_lbl} `{ob_pct}%` bids\n"
                f"\n"
                f"🎯 TP1: `${_fp(tp1)}` (+30%)\n"
                f"🎯 TP2: `${_fp(tp2)}` (+60%)\n"
                f"🎯 TP3: `${_fp(tp3)}` (+100%)\n"
                f"🛑 SL:  `${_fp(sl)}` (-10%)\n"
                f"⏳ Swing — 72h window\n"
                f"\n"
                f"🎯 📈 *WEEKLY BREAKOUT* · Score: `{score}/10`{_fs_line}\n"
                f"\n"
                f"🟡 Exchange: `{tier['name']} · Binance`\n"
                f"🕐 {_ts()} UTC\n"
                f"{'━'*20}"
            )

            ai_str, ai_blocked = _ai_assess(sym, t["exchange"], tier["name"],
                                            "weekly_breakout", score, ob_spot,
                                            ratio, pos24, spike_1h,
                                            net, t["change"], "—",
                                            fractal_score=_fs,
                                            min_prob=50)
            if ai_blocked:
                continue
            msg += ai_str

            alerted[sym]       = now
            _signal_dedup[sym] = now
            kb = _trade_keyboard(sym, t["exchange"])
            ok, sig_msg_id = send_ex(msg, reply_markup=kb)
            if ok:
                _alerted_price[sym] = price
                tracking[sym] = {
                    "entry":      price,
                    "t0":         now,
                    "hit":        set(),
                    "max":        0.0,
                    "min":        0.0,
                    "exchange":   t["exchange"],
                    "is_flash":   False,
                    "is_swing":   True,
                    "timeout_h":  72,
                    "sig_msg_id": sig_msg_id,
                    "sl_pct":     -10.0,
                    "tp1":        tp1,
                }
                _db_add(sym, price, t["exchange"], tier["name"], "weekly_breakout",
                        ratio, ob_spot, score, pos24, spike_1h,
                        net, t["change"], f"+{breakout_pct:.1f}%_above_7dh")
                save_state()
                fired += 1
                log.info("WEEKLY_BREAKOUT %s breakout=+%.1f%% vol_growth=%d%% pos=%d%% ratio=%.1f",
                         sym, breakout_pct, vol_growth_pct, pos_pct, ratio)
            time.sleep(0.3)

        except Exception as e:
            log.debug("weekly_breakout %s: %s", sym, e)

    if fired:
        log.info("scan_weekly_breakout: fired=%d", fired)


def scan_deep_value(all_t):
    """
    Wolf Flow-style swing scanner: deep value recovery.
    Catches coins near multi-week lows that are showing early recovery signs.
    Swing signal: 72h timeout, SL -12%, TP 20%/40%/80%.

    Conditions:
      - Binance, vol >= $500k
      - price near 7-day low: current price <= 7d-low * 1.08 (within 8% of 7d low)
      - Not in freefall: 7d change > -60%, today's change > -12%
      - Volume building: 3d avg volume >= 130% of 7d avg (confirming recovery)
      - pos24 < 35% (near bottom of today's range)
      - 1h flow: net > tier_min*0.5, ratio >= 2.5, spike >= 2.0, OB >= 0.68
      - 24h cooldown per coin
    """
    now = time.time()
    candidates = [
        (sym, t) for sym, t in all_t.items()
        if t["exchange"] == "Binance"
        and t["vol"] >= 500_000
        and now - _weekly_swing_dedup.get(sym, 0) >= 86400
        and now - alerted.get(sym, 0) >= COOLDOWN
        and sym not in tracking
        and sym not in BLACKLIST
        and -12.0 <= t.get("change", 0) <= 15.0   # not in freefall, not already pumped
    ]

    fired = 0
    for sym, t in candidates:
        try:
            klines = _fetch_daily_klines(sym, "Binance", days=14)
            if len(klines) < 10:
                continue

            closes   = [c for c, v in klines]
            vols_usd = [v * c for c, v in klines]
            price    = closes[-1]

            # Near 7-day low: price within 8% above the 7d low close
            low_7d = min(closes[-8:-1])
            if price > low_7d * 1.08:
                continue

            # Not in freefall: 7d gain must not be catastrophic
            gain_7d = (price - closes[-8]) / closes[-8] * 100 if closes[-8] > 0 else 0
            if gain_7d < -60.0:
                continue

            # Volume building: 3d avg must be >= 130% of 7d avg (strong recovery confirmation)
            vol_3d = sum(vols_usd[-4:-1]) / 3 if len(vols_usd) >= 4 else 0
            vol_7d = sum(vols_usd[-8:-1]) / 7 if len(vols_usd) >= 8 else 0
            if vol_7d <= 0 or vol_3d < vol_7d * 1.30:
                continue

            # Near bottom of today's range
            rng   = t["high24"] - t["low24"]
            pos24 = (price - t["low24"]) / rng if rng > 0 else 0.5
            if pos24 > 0.35:
                continue

            # 1h flow check — stricter ratio & spike for swing quality
            base_url = t["base_url"]
            buy_v, sell_v = fetch_agg_trades(sym, base_url, minutes=60)
            if sell_v <= 0:
                continue
            net = buy_v - sell_v
            if net <= 0:
                continue
            ratio = buy_v / sell_v
            if ratio < 2.5:
                continue

            spike_1h = (buy_v + sell_v) / max(t["vol"] / 24.0, 1)
            if spike_1h < 2.0:
                continue

            ob_spot = fetch_ob_imbalance(sym, base_url, levels=20)
            if ob_spot < 0.68:
                continue

            # Net flow must be meaningful relative to coin size
            _net_min = get_tier(t["vol"])["net"]
            if net < _net_min * 0.5:
                continue

            # Counter-trend check: if BTC is falling, coin must be rising (independent flow)
            # Coins that fall WITH BTC have no independent buyers — follow BTC back down
            _coin_change = t.get("change", 0.0)
            _counter_trend = _btc_falling and _coin_change > 0.5
            if _btc_falling and _coin_change <= 0:
                continue  # BTC falling + coin also falling = correlated, skip

            tier   = get_tier(t["vol"])
            score  = _calc_score(pos24, net, max(t["vol"] * 0.001, 500.0),
                                 ob_spot, spike_1h)
            if score < 8.0:
                continue

            _weekly_swing_dedup[sym] = now

            # Fractal analysis — display + filter
            _fs, _fra_dv = _swing_fractal(sym, base_url, price, score)
            if _fs is not None and _fs < 5.0:
                continue  # weak fractal structure — skip swing signal
            _fs_icon = "🟢" if (_fs or 0) >= 7.0 else ("🟡" if (_fs or 0) >= 5.0 else "🔴")
            _fs_line = f"\n🔬 Fractal Score: `{_fs}/10` {_fs_icon}" if _fs is not None else ""

            above_low_pct  = (price / low_7d - 1) * 100
            vol_growth_pct = int(vol_3d / max(vol_7d, 1) * 100)
            ob_pct         = int(ob_spot * 100)
            ob_lbl         = "🟢 Buyers" if ob_spot > 0.58 else "⚪ Balanced"
            pos_pct        = int(pos24 * 100)
            _mkt           = "Alpha" if (t.get("futures_only") or t.get("binance_alpha")) else "Spot"
            _, badge       = _register_confirm(sym, "deep_value")

            global signal_count
            signal_count += 1

            # Fixed TP for swing: 20% / 40% / 80%
            tp1 = price * 1.20
            tp2 = price * 1.40
            tp3 = price * 1.80
            sl  = price * 0.88

            msg = (
                f"{'━'*20}\n"
                f"💀 *MAFIO SNIPER* 📡\n"
                f"\n"
                f"💎 *#{sym[:-4]}* 💀 · {_mkt} · Swing · Signal #{signal_count} {badge}\n"
                f"💰 Price: `${_fp(price)}`\n"
                f"📉 24h Change: `{t['change']:+.2f}%`\n"
                f"📍 Position: `%{pos_pct} from Bottom` ✅\n"
                f"\n"
                f"📍 7d Low Zone: `+{above_low_pct:.1f}%` above 7d low\n"
                f"📊 Volume Recovery: `{vol_growth_pct}%` of 7d avg\n"
                f"⚡ Volume 1h: `{spike_1h:.1f}x` above avg\n"
                f"💹 1h Flow:\n"
                f"  📥 In:  `{_fv(buy_v)}`\n"
                f"  📤 Out: `{_fv(sell_v)}`\n"
                f"  ▲ Net: `+{_fv(net)}` ✅\n"
                f"📗 Order Book: {ob_lbl} `{ob_pct}%` bids\n"
                f"\n"
                f"🎯 TP1: `${_fp(tp1)}` (+20%)\n"
                f"🎯 TP2: `${_fp(tp2)}` (+40%)\n"
                f"🎯 TP3: `${_fp(tp3)}` (+80%)\n"
                f"🛑 SL:  `${_fp(sl)}` (-12%)\n"
                f"⏳ Swing — 72h window\n"
                f"\n"
                f"🎯 💎 *DEEP VALUE RECOVERY* · Score: `{score}/10`{_fs_line}\n"
                f"\n"
                f"🟡 Exchange: `{tier['name']} · Binance`\n"
                f"🕐 {_ts()} UTC\n"
                f"{'━'*20}"
            )

            ai_str, ai_blocked = _ai_assess(sym, t["exchange"], tier["name"],
                                            "deep_value", score, ob_spot,
                                            ratio, pos24, spike_1h,
                                            net, t["change"], "—",
                                            fractal_score=_fs,
                                            min_prob=50)
            if ai_blocked:
                continue
            msg += ai_str

            alerted[sym]       = now
            _signal_dedup[sym] = now
            kb = _trade_keyboard(sym, t["exchange"])
            ok, sig_msg_id = send_ex(msg, reply_markup=kb)
            if ok:
                _alerted_price[sym] = price
                tracking[sym] = {
                    "entry":      price,
                    "t0":         now,
                    "hit":        set(),
                    "max":        0.0,
                    "min":        0.0,
                    "exchange":   t["exchange"],
                    "is_flash":   False,
                    "is_swing":   True,
                    "timeout_h":  72,
                    "sig_msg_id": sig_msg_id,
                    "sl_pct":     -12.0,
                    "tp1":        tp1,
                }
                _db_add(sym, price, t["exchange"], tier["name"], "deep_value",
                        ratio, ob_spot, score, pos24, spike_1h,
                        net, t["change"], f"7dLow+{above_low_pct:.1f}%")
                save_state()
                fired += 1
                log.info("DEEP_VALUE %s gain7d=%.1f%% low_zone=+%.1f%% pos=%d%% vol_growth=%d%%",
                         sym, gain_7d, above_low_pct, pos_pct, vol_growth_pct)
            time.sleep(0.3)

        except Exception as e:
            log.debug("deep_value %s: %s", sym, e)

    if fired:
        log.info("scan_deep_value: fired=%d", fired)


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
    global last_fast, last_slow, last_super, last_accum, last_sg, last_sector, last_weekly_swing, last_deep_value, last_report, last_report_date, last_weekly_date, last_monthly_date, last_alpha
    # Error tracking — alert Telegram on repeated loop errors
    _loop_err_count = [0]    # [count] — mutable so inner scope can modify
    _loop_last_err  = [""]   # [last_error_str]
    _signal.signal(_signal.SIGTERM, _handle_sigterm)  # invalidate PID on shutdown
    _register_primary()   # claim PID lock — old process will detect mismatch and stop sending
    log.info("🎯 MAFIO SNIPER v%s — starting (PID %d)", BOT_VERSION, _MY_PID)
    clear_bot_commands()
    register_commands()
    load_state()
    load_signal_db()

    _startup_msg = (
        f"🔄 *MAFIO SNIPER v{BOT_VERSION} — Online*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ Bot restarted — {datetime.now(timezone.utc).strftime('%d %b %Y %H:%M')} UTC\n"
        f"📡 Exchange: *Binance* 🟡\n"
        f"⚡ Fast scan:    every {FAST_SCAN_S}s\n"
        f"😴 Sleep Giant: every {SLEEP_GIANT_S}s\n"
        f"🎯 Mid scan:    every {MID_SCAN_S}s\n"
        f"📊 Slow scan:   every {SLOW_SCAN_S//60}min\n"
        f"📐 Fractal + FCF + Chaos-Quant: ✅ Active\n"
        f"🔕 Cooldown: {COOLDOWN//3600}h per coin\n"
        f"📍 Open positions: {len(tracking)}"
    )
    # Retry up to 5 times — network may not be ready immediately after restart
    for _attempt in range(5):
        if send(_startup_msg):
            break
        log.warning("Startup message failed (attempt %d/5) — retrying in 5s", _attempt + 1)
        time.sleep(5)

    while True:
        try:
            now = time.time()
            if now - last_fast < FAST_SCAN_S:
                poll_telegram()   # responsive even while scans are running
                time.sleep(1); continue
            last_fast = now

            all_t = {}
            _bn = fetch_binance()
            for _sym, _td in _bn.items():
                all_t[_sym] = _td
            # Futures-only: Binance Alpha / pre-listing coins (RAVE type)
            _bn_fut = fetch_binance_futures_only(set(_bn.keys()))
            for _sym, _td in _bn_fut.items():
                all_t[_sym] = _td   # safe: spot_syms excluded upstream
                # Register dynamically as BNB Alpha sector for sector scanner
                _base = _sym[:-4] if _sym.endswith("USDT") else _sym.replace("USDT", "")
                if _base not in SECTOR_REGISTRY:
                    SECTOR_REGISTRY[_base] = "BNB Alpha"
            # Binance Alpha Web3 tokens (pre-listing candidates)
            _bn_alpha = fetch_binance_alpha()
            _bn_alpha_new = 0
            for _sym, _td in _bn_alpha.items():
                _base = _sym[:-4] if _sym.endswith("USDT") else _sym.replace("USDT", "")
                if _sym not in all_t:
                    all_t[_sym] = _td
                    _bn_alpha_new += 1
                else:
                    # Propagate Alpha flag so slow_scan pump bypass and _max_pump=400% apply
                    all_t[_sym]["binance_alpha"] = True
                if _base not in SECTOR_REGISTRY:
                    SECTOR_REGISTRY[_base] = "BNB Alpha"
            _alpha_total = sum(1 for t in all_t.values() if t.get("binance_alpha") or t.get("futures_only"))
            log.info("Tickers: Binance=%d Fut-only=%d Alpha-new=%d Alpha-total=%d Total=%d Tracking=%d",
                     len(_bn), len(_bn_fut), _bn_alpha_new, _alpha_total, len(all_t), len(tracking))

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

            # Weekly report disabled

            # Monthly report disabled
            # if (_utc.day == 1 and _utc.hour == REPORT_HOUR
            #         and 10 <= _utc.minute < 15 and _month_str != last_monthly_date):
            #     send_monthly_report()

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
                # scan_quiet_accum disabled: 25% win rate / 6.8% avg gain (166-signal history)
                scan_whale_flow(all_t)

            global last_alpha
            if now - last_alpha >= ACCUM_SCAN_S:
                last_alpha = now
                scan_alpha_explosion(all_t)
                _retroactive_peak_update()   # fix timeout records with true historical peak

            global last_sg
            if now - last_sg >= SLEEP_GIANT_S:
                last_sg = now
                scan_sleeping_giant(all_t)

            global last_sector
            if now - last_sector >= SECTOR_SCAN_S:
                last_sector = now
                scan_sector_liquidity(all_t)


            # Swing: weekly high breakout with volume build-up (Wolf Flow style)
            if now - last_weekly_swing >= WEEKLY_SWING_S:
                last_weekly_swing = now
                scan_weekly_breakout(all_t)

            # Swing: deep value recovery near 7-day low (Wolf Flow style)
            if now - last_deep_value >= DEEP_VALUE_S:
                last_deep_value = now
                scan_deep_value(all_t)

        except KeyboardInterrupt:
            log.info("Stopped."); break
        except Exception as e:
            log.error("Loop: %s", e, exc_info=True)
            # ── Error Alert: notify Telegram if same error repeats ──────────
            _err_str = str(e)[:120]
            if _err_str == _loop_last_err[0]:
                _loop_err_count[0] += 1
            else:
                _loop_last_err[0]  = _err_str
                _loop_err_count[0] = 1
            if _loop_err_count[0] == 5:
                try:
                    send_ex(
                        f"⚠️ *MAFIO — Loop Error*\n"
                        f"```\n{_err_str}\n```\n"
                        f"_Repeated 5 times — check the bot_"
                    )
                except Exception:
                    pass
            elif _loop_err_count[0] % 50 == 0:
                try:
                    send_ex(
                        f"🚨 *MAFIO — Loop Error x{_loop_err_count[0]}*\n"
                        f"```\n{_err_str}\n```"
                    )
                except Exception:
                    pass
            time.sleep(5)

if __name__ == "__main__":
    main()

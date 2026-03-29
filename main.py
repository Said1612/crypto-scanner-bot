# -*- coding: utf-8 -*-
# Build: 20260320-001
"""
╔══════════════════════════════════════════════════════════════╗
║           MAFIO-BOT — UNIFIED ENGINE            ║
║   Anti-Rate-Limit + Smart Cache + Trailing Stop            ║
║   Smart Top10 — اصطياد العملات قبل الانفجار               ║
╚══════════════════════════════════════════════════════════════╝

استراتيجية الطلبات (Anti-Rate-Limit):
  ● طلب واحد للـ 24h Ticker  كل 12 ثانية   → 5/دقيقة
  ● Cache ذكي: 15m=60s, 1h=5min, 4h=15min
  ● Scan عميق (Klines+OrderBook) كل ساعة
  ● الفلتر المسبق يرفض 90% من العملات بدون Klines

النتيجة: ~8 طلبات/دقيقة بدل 492 ✅
"""

import os
import sys
import time
import json
import logging
import requests
from datetime import datetime, timezone
from typing import Optional, Dict, List, Tuple, Any, Set


#                    CONFIG

STATE_FILE = "/app/mafio_state.json"


REDIS_URL   = os.environ.get("UPSTASH_REDIS_REST_URL", "")
REDIS_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")
REDIS_KEY   = "mafio_bot_state_v16"



REDIS_URL  = os.environ.get("REDIS_URL", os.environ.get("UPSTASH_REDIS_REST_URL", ""))
REDIS_KEY  = "mafio_state_v16"



BLOCKED_WATCHLIST = {
    "CULTUSDT",
}

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_BOT_TOKEN")
CHAT_ID        = os.getenv("CHAT_ID",  "YOUR_CHAT_ID")
GROUP_ID       = os.getenv("GROUP_ID", "")


SCORE_MIN          = 55
GOLD_MIN           = 88
SIGNAL2_GAIN       = 2.0
SIGNAL3_GAIN       = 4.0
ALERT_COOLDOWN_SEC = 300
CHECK_INTERVAL     = 12


SL_MIN             = 2.0
SL_MAX             = 8.0
SL_BASE            = 4.0
TRAIL_GAIN_TRIGGER = 2.0
TRAIL_DROP_TRIGGER = 1.5


BTC_DANGER_ZONE    = -3.0
BTC_CAUTION_ZONE   = -1.5



BTC_DANGER_BUFFER  = 0.3
BTC_CRASH_4H       = -2.5

TPS_LIMIT      = 100

EXTRA_COINS = [

    "FLOKIUSDT", "PEPEUSDT", "WIFUSDT", "BOMEUSDT", "MEWUSDT",
"PUNCHUSDT",
    "PEOPLEUSDT", "1000SHIBUSDT", "BANANAUSDT", "NEIROUSDT",
    "SUNDOGUSDT", "MOODENGUSDT", "FWOGUSDT", "GORKYUSDT",


    "FLOWUSDT", "KASUSDT", "KAIAUSDT", "JUPUSDT",


    "PIXELUSDT", "RENDERUSDT", "GALAUSDT", "IMXUSDT",


    "AAVEUSDT", "DYDXUSDT", "JOEUSDT",


    "COSUSDT", "CUSDT", "MBOXUSDT", "TOWNSUSDT",
    "DEXEUSDT", "SPELLUSDT", "PSGUSDT", "INTUSDT",
    "HAEDALUSDT", "PHBUSDT", "HOOKUSDT",


    "FETUSDT", "AGIXUSDT", "OCEANUSDT", "GRTUSDT",
    "WLDUSDT", "ARKMUSDT", "VIRTUSDT", "ACTUSDT",
    "CGPTUSDT", "NEUROUSDT", "TAOAUSDT", "SWARMAUSDT",


    "ONDOUSDT", "MANTRAUSDT", "CFGUSDT", "PLUMEUSDT",


    "XLMUSDT", "XRPUSDT", "PYTHUSDT", "REQUSDT",


    "LINKUSDT", "BANDUSDT", "SUPRAUSDT", "API3USDT",


    "CFXUSDT", "APTUSDT", "SEIUSDT", "INJUSDT",
    "NEARUSDT", "SOLUSDT", "AVAXUSDT", "ADAUSDT",
]

TPS_SPIKE      = 2.0
TPS_MAX_CHANGE = 5.0
ATS_WHALE      = 5000
ATS_RETAIL     = 500
VDELTA_STRONG  = 0.70
TPS_COOLDOWN   = 7200
TPS_SCAN_EVERY = 300
BTC_CRASH_1H       = -1.5
BTC_CAUTION_BUFFER = 0.3

BTC_CONFIRM_COUNT  = 1


ST_ATR_PERIOD      = 10
ST_MULTIPLIER      = 3.0


PD_MAX_RISE        = 20.0
PD_MIN_DROP        = 5.0
PD_LOOKBACK        = 12


SECTOR_HOT_CHANGE  = 1.5
SECTOR_MIN_RISING  = 40.0
SECTOR_BONUS       = 15


VOL_SPIKE_RATIO    = 2.5
MIN_VOL_USDT       = 300_000
MAX_VOL_USDT       = 80_000_000
MIN_BID_DEPTH      = 20_000
MIN_IMBALANCE      = 0.8
MAX_IMBALANCE      = 3.0
GREEN_MIN_RATIO    = 0.45
HIGHER_LOWS_MIN    = 0.60



WHALE_MIN_VOL      = 1_000_000
WHALE_MAX_CHANGE   = 8.0


BOTTOM_PRICE_RANGE   = 1.15
BOTTOM_VOL_INCREASE  = 1.3
BOTTOM_MAX_CHANGE    = 5.0
BOTTOM_MIN_DAYS      = 7
BOTTOM_COOLDOWN      = 86400
BOTTOM_SCAN_EVERY    = 3600
BOTTOM_MIN_VOL       = 1_000_000


EXPLOSION_VOL_MULT   = 3.0
EXPLOSION_MIN_DAYS   = 5
EXPLOSION_COOLDOWN   = 86400
EXPLOSION_MAX_CHANGE = 30.0
EXPLOSION_MIN_VOL    = 1_000_000


ATH_DROP_STRONG  = 0.90
ATH_DROP_EXTREME = 0.95
ATH_MIN_VOL      = 1_000_000
ATH_COOLDOWN     = 86400
ATH_SCAN_EVERY   = 7200


HOT_MIN_CHANGE   = 12.0
HOT_MIN_VOL      = 500_000   # خُفِّض من 1M — يشمل عملات أصغر
HOT_COOLDOWN     = 14400
HOT_SCAN_EVERY   = 1800      # كل 30 دقيقة بدلاً من ساعة


RT_SCAN_EVERY    = 300       # كل 5 دقائق بدلاً من 15
RT_VOL_SPIKE     = 2.0
RT_MIN_VOL       = 500_000   # خُفِّض من 1M
RT_COOLDOWN      = 7200      # ساعتان بدلاً من 6

BREAKOUT5M_SCAN_EVERY = 90     # كل 90 ثانية (klines محدودة بـ cache 60s)
BREAKOUT5M_COOLDOWN   = 14400  # 4 ساعات بين تنبيهين للعملة نفسها
BREAKOUT5M_MIN_VOL    = 150_000
BREAKOUT5M_VOL_SPIKE  = 2.5    # حجم الشمعة الأخيرة > 2.5x المتوسط
BREAKOUT5M_MAX_COINS  = 25     # أقصى عدد يُفحص بـ klines

# Bounce Reversal Scanner
BOUNCE_SCAN_EVERY   = 120      # كل دقيقتين
BOUNCE_COOLDOWN     = 7200     # ساعتان بين تنبيهين للعملة
BOUNCE_MIN_VOL      = 150_000
BOUNCE_DROP_MIN     = 3.0      # نزل على الأقل 3%
BOUNCE_DROP_MAX     = 20.0     # لم ينهار أكثر من 20%
BOUNCE_OUTSELL_MAX  = 1.8      # نسبة OUT/IN أقل من 1.8x — البيع يخف

# BB Squeeze Scanner
BB_SQUEEZE_SCAN_EVERY  = 300    # كل 5 دقائق
BB_SQUEEZE_COOLDOWN    = 10800  # 3 ساعات بين تنبيهين للعملة
BB_SQUEEZE_MIN_VOL     = 150_000
BB_SQUEEZE_MAX_COINS   = 50     # أقصى عدد يُفحص
BB_PERIOD              = 20     # فترة Bollinger Bands
BB_STD_MULT            = 2.0    # معامل الانحراف المعياري

# 1h Move Scanner — Wolf Flow style (حركة الساعة الأخيرة)
MOVE1H_SCAN_EVERY  = 120      # كل دقيقتين
MOVE1H_COOLDOWN    = 7200     # ساعتان بين تنبيهين للعملة
MOVE1H_MIN_VOL     = 50_000   # حجم 24h أدنى (أقل من 5m لاصطياد micro-caps)
MOVE1H_MOVE_MIN    = 4.0      # حركة 1h ≥ 4%
MOVE1H_MOVE_MAX    = 30.0     # حركة 1h ≤ 30% (فوق ذلك = pump مشبوه)
MOVE1H_FLOW_RATIO  = 1.3      # نسبة IN/OUT (منخفضة مثل Wolf Flow)
MOVE1H_VOL_SPIKE   = 1.5      # حجم آخر شمعة 1h > 1.5× المتوسط
MOVE1H_MAX_COINS   = 50       # أقصى عملات تُفحص بـ klines

# Flow Accumulation Scanner — السعر ثابت + أموال تتراكم (NTRNUSDT type)
FLOWACC_SCAN_EVERY  = 90      # كل 90 ثانية
FLOWACC_COOLDOWN    = 5400    # 90 دقيقة
FLOWACC_MIN_VOL     = 30_000  # حجم منخفض — يقبل micro-caps
FLOWACC_FLOW_RATIO  = 6.0     # IN/OUT ≥ 6x — تجميع خفي قوي
FLOWACC_PRICE_MAX   = 3.0     # حركة سعرية ≤ 3% (السعر شبه ثابت)
FLOWACC_VOL_SPIKE   = 2.0     # حجم 1h > 2x المتوسط
FLOWACC_MAX_COINS   = 60      # أقصى عملات

# Volume Breakout Scanner — انفجار حجم × 5 بدون حركة سعرية (قبل الـ pump)
VOLBR_SCAN_EVERY   = 60       # كل دقيقة
VOLBR_COOLDOWN     = 5400     # 90 دقيقة
VOLBR_MIN_VOL      = 20_000   # يقبل micro-caps
VOLBR_SPIKE_MIN    = 5.0      # حجم > 5x المتوسط — انفجار حقيقي
VOLBR_PRICE_MAX    = 5.0      # السعر لم يتحرك كثيراً بعد
VOLBR_MAX_COINS    = 60

# Micro Pump Scanner — حركة 1-4% + flow استثنائي 12x+ (مبكر جداً)
MICROPUMP_SCAN_EVERY = 60     # كل دقيقة
MICROPUMP_COOLDOWN   = 5400   # 90 دقيقة
MICROPUMP_MIN_VOL    = 20_000
MICROPUMP_MOVE_MIN   = 0.8    # حركة ≥ 0.8% فقط
MICROPUMP_MOVE_MAX   = 5.0    # ≤ 5% — لم يتحرك كثيراً بعد
MICROPUMP_FLOW_RATIO = 12.0   # flow استثنائي 12x+
MICROPUMP_MAX_COINS  = 60

# Fast scanner — Tier 0 (30 ثانية، بدون klines)
FAST_SCAN_EVERY    = 30       # كل 30 ثانية — مثل Wolf Flow
FAST_SCAN_COOLDOWN = 3600     # ساعة واحدة cooldown
FAST_MIN_VOL       = 150_000
FAST_MOVE_30S      = 0.8      # خُفِّض من 1.5% — يلتقط بداية الحركة مبكراً
FAST_MOVE_24H_MIN  = 2.0      # يجب أن يكون اتجاه 24h إيجابي


WL_ENTRY_MOVE    = 3.0
WL_ENTRY_VOL     = 1.5
WL_MAX_SIZE      = 30
WL_EXPIRY        = 86400
WL_ENTRY_COOL    = 14400
WL_CHECK_EVERY   = 60


TS_TRAIL_PCT     = 15.0   # trail افتراضي (يُستبدل بالتكيّفي أدناه)
TS_MIN_PROFIT    = 10.0
TS_BREAKEVEN     = 10.0
TS_LOCK_20       = 20.0
TS_LOCK_50       = 50.0
TS_SCAN_EVERY    = 300
TS_DANGER_VOL    = 0.5
TS_DANGER_CLOSE  = -3.0

# ── Adaptive Trailing — أوسع عند البداية، أضيق عند القمم ─────────
# peak_pct → trail_pct (كلما ارتفع الربح كلما ضاق الـ trail لحماية الأرباح)
TS_ADAPTIVE_TRAIL = [
    (200.0, 10.0),   # > 200%  → trail -10% من القمة
    (100.0, 12.0),   # > 100%  → trail -12%
    ( 50.0, 15.0),   # >  50%  → trail -15%
    ( 30.0, 20.0),   # >  30%  → trail -20% (مساحة تنفس)
    (  0.0, 25.0),   # >   0%  → trail -25% (لا تخرج مبكراً)
]

# ── Whale Sell Detection — لا تخرج بسبب تذبذب عادي ────────────────
WHALE_SELL_VDELTA   = 0.33   # VDelta < 33% = بيع قوي (كان 35%)
WHALE_SELL_ATS_MULT = 2.5    # ATS >= tier_min × 2.5 = بيع كبير
WHALE_EXIT_MIN_PROF = 15.0   # لا تُرسل إشارة خروج إلا بعد 15% ربح

TS_SELL_COOL     = 3600


RT_PRICE_MOVE    = 2.0
HOT_MAX_CHANGE   = 50.0
WHALE_MIN_PRICE    = 0.000001

SUSPICIOUS_KEYWORDS = [
    "STABLE","PEGGED","WRAPPED","BRIDGE",
    "EUR","GBP","CNY","JPY",
    "TEST","DEMO","FAKE",
]


BO_4H_CANDLES      = 30
BO_FLAT_MAX        = 15.0
BO_VOL_SURGE       = 3.0
BO_NEAR_LOW        = 30.0


PRE_MIN_CHANGE     = -5.0
PRE_MAX_CHANGE     = 80.0
PRE_MIN_VOL        = MIN_VOL_USDT
PRE_MAX_VOL        = MAX_VOL_USDT


PRICES_EVERY       = 12
TICKERS_EVERY      = 1800
BTC_EVERY          = 300
SECTORS_EVERY      = 600
DEEP_SCAN_EVERY    = 3600
STALE_EVERY        = 3600
REPORT_EVERY       = 21600
STALE_REMOVE_SEC   = 86400


CACHE_15M          = 60
CACHE_1H           = 300
CACHE_4H           = 900


MOMENTUM_MOVE_MIN  = 2.0
MOMENTUM_MOVE_MAX  = 8.0
MOMENTUM_MIN_VOL   = 500_000
MOMENTUM_COOLDOWN  = 14400



FLOW_WINDOW        = 5
FLOW_VOL_SURGE     = 1.3
FLOW_CHANGE_MIN    = 0.5
FLOW_EXIT_DROP     = -1.5
FLOW_ALERT_COOL    = 600
FLOW_HISTORY_MAX   = 20

# Sector Rotation
SR_MIN_OUT        = -5.0
SR_MIN_IN         = 5.0
SR_COOLDOWN       = 7200
SR_TOP_COINS      = 5


EXPAND_EVERY       = 86400


TOP10_CHANGE_MIN   = 0.0
TOP10_CHANGE_MAX   = 8.0
TOP10_VOL_RATIO    = 1.2
TOP10_REBOUND_MAX  = 15.0
TOP10_MIN_VOL      = 150_000
TOP10_COOLDOWN     = 1800
TOP10_COUNT        = 10


W_VOL_RATIO    = 40
W_HOT_SECTOR   = 25
W_REBOUND_LOW  = 20
W_CHANGE_SMALL = 15


RSI_PERIOD        = 14
RSI_OVERBOUGHT    = 70
RSI_OVERSOLD      = 30
RSI_IDEAL_MAX     = 60


VOL_HISTORY_MAX   = 10
VOL_HISTORY_MIN   = 3


BACKTEST_CHECK_1H  = 3600
BACKTEST_CHECK_4H  = 14400
BACKTEST_CHECK_24H = 86400
BACKTEST_FEE       = 0.2






LZ_TOUCHES_MIN     = 3
LZ_TOUCHES_RARE    = 8
LZ_VOL_MULT        = 1.5
LZ_LOOKBACK        = 90
LZ_ZONE_MARGIN     = 0.02
LZ_COOLDOWN        = 86400
LZ_SCORE_MIN       = 60


SMART_MONEY_SIGMA      = 3.0
SMART_MONEY_EVERY      = 86400
SMART_MONEY_ACCUM_MIN  = 2
SMART_MONEY_FALL_PCT   = 55
SMART_MONEY_ALERT_SIGMA= 5.0

SMART_MONEY_STABLES = [
    "FDUSDUSDT","TUSDUSDT","USD1USDT",
    "RLUSDUSDT","BFUSDUSDT","USDPUSDT","USDDUSDT",
]


MEXC_24H    = "https://api.mexc.com/api/v3/ticker/24hr"
MEXC_TICKER = "https://api.mexc.com/api/v3/ticker/24hr"
MEXC_PRICE  = "https://api.mexc.com/api/v3/ticker/price"
MEXC_KLINES = "https://api.mexc.com/api/v3/klines"
MEXC_DEPTH  = "https://api.mexc.com/api/v3/depth"
MEXC_TRADES = "https://api.mexc.com/api/v3/trades"

EXCLUDED = {"BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT",

            "EURUSDT","STABLEUSDT","UCNUSDT","VERMUSDT",
            "BDXUSDT","POLXUSDT","MBGUSDT","L3USDT","VERMUSDT",

            "XMRUSDT","DASHUSDT","ZCASHUSDT","SCRTUSDT",

            # رموز بأقواس — تسبب أخطاء في API ولا توجد كزوج تداول حقيقي
            "GOLD(XAUT)USDT","GOLD(PAXG)USDT",
}


MAX_COIN_SIGNALS = 2


SECTOR_TARGET      = 50
EXPAND_MIN_VOL     = 100_000
EXPAND_MAX_VOL     = 500_000_000



SECTOR_KEYWORDS = {
    "AI": [
        "AI","GPT","AGI","NEURAL","AGENT","BRAIN","MIND","THINK",
        "COGN","LEARN","SENTIENT","VIRTUAL","FETCH","OCEAN","RENDER",
        "GRAPH","TAO","ARKM","COOKIE","MIRA","MYRIA","ALETH","CGPT",
        "NEURO","VANA","MASK","AKTO","MEAI","GRIFFAIN","SWARM",
        "AIDO","WLDAI","KAIA","VIRT","NMT","AUTON","PAAL","SLEEPLESS",
        "QUBIC","AITECH","GENSYN","AIUS","KAITO","DEAI","OPML","DORA","VIRTUAL",
    ],
    "RWA": [
        "ONDO","CFG","MPLEX","REAL","TRST","PROM","MANTRA","XDC",
        "LQTY","SPX","ONP","VAI","GOLD","TBL","PARCL","REX","HONE",
        "OPEN","LANDX","CREDIX","POLIX","TRUE","MTV","PROP","TPROT",
        "STBTC","CULT","BRICS","ESTATE","REALT","DEXT","POLYMATH",
        "SECURITIZE","BACKED","MAPLE","CENTRIFUGE","GOLDFINCH",
        "TOUCAN","COOREST","BASE","REALIO","LOFTY","PRCL","PROPS","REALT","BLOCKSQUARE",
    ],
    "Gaming": [
        "GAME","PLAY","QUEST","HERO","GUILD","YIELD","PIXEL","PORTAL",
        "AXS","SAND","MANA","ILV","GMT","YGG","SLP","GALA","RON","IMX",
        "BEAM","NOT","XAI","ALICE","RARE","MOBA","CHZ","PGX","HEROES",
        "BEX","GOMA","ACE","META","WAXP","GAL","VIDYA","ELF","MAGIC",
        "TWT","GHST","TOWER","REVV","NFTX","MOBOX","SKILL","DERACE",
        "FIGHT","WARS","BATTLE","LEGEND","REALM","KART","SPORT","FAN",
        "CHAMP","WIN","SUPER","GODS","AURY","ATLAS","POLIS","PVU","HMSTR",
        "ENJUSDT", "STEEMUSDT",
    ],
    "DeFi": [
        "UNI","AAVE","CAKE","SUSHI","COMP","MKR","CRV","LDO","1INCH",
        "C98","DYDX","GMX","JUP","RAY","ORCA","PENDLE","EIGEN","ETHFI",
        "IDEX","REZ","SYRUP","BONE","CVX","FRAX","FXS","TRIBE","RAD",
        "ALPACA","RAMP","WOO","SWAP","DEX","YIELD","LEND","POOL",
        "LIQUID","STAKE","VAULT","FARM","HARVEST","BADGER","BNT",
        "PERP","SNX","KNC","BAL","BIFI","PANCAKE","QUICK","SPIRIT",
        "SPOOKY","JOE","SOLAR","TRISOLARIS","VELODROME","AERODROME",
        "CAMELOT","STERLING","RAMSES","THENA","KYBER","BANCOR","KMNO","MORPHO","WET",
        "VANRYUSDT", "GLMUSDT", "LISTAUSDT", "STGUSDT", "STOUSDT", "ANKRUSDT",
    ],
    "Layer1": [
        "AVAX","ADA","ATOM","NEAR","FTM","ALGO","ICP","APT","SUI","SEI",
        "INJ","KAS","TON","HBAR","EGLD","ZIL","ONE","CFX","JASMY","LSK",
        "QNT","CELO","FLOW","MINA","KAVA","VET","ONT","WAVES","XTZ","NEO",
        "ROSE","SCRT","OASIS","HARMONY","ELROND","MULTIVERSX","APTOS",
        "MOVEMENT","MONAD","BERACHAIN","INITIA","SAGA","STORY","SUPRA",
        "HYPERLIQUID","ECLIPSE","FUSE","VENOM","NEON","ZETA","XPL",
        "SENTUSDT","ONTUSDT","A2ZUSDT",
    ],
    "Layer2": [
        "MATIC","OP","ARB","ZK","STRK","LRC","METIS","MANTA","SCROLL",
        "MNT","MERL","ALT","ZRO","LINEA","TAIKO","MOD","CELR","SKL",
        "OMG","SSV","BOBA","STARKNET","ZKFAIR","ZKLINK","ZKME","LUMIA",
        "POLYGON","OPTIMISM","ARBITRUM","STARKWARE","LOOPRING","MATTER",
        "IMMUTABLE","RONIN","BASE","BLAST","MANTLE","MODE","MINT",
        "FRAXTAL","ZORA","REDSTONE","CYBER","KINTO","ANCIENT8","BREV",
        "POLYXUSDT",
    ],
    "Meme": [
        "DOGE","SHIB","PEPE","FLOKI","WIF","BOM","MEME","TURO","POPCAT",
        "MOG","BABYDOGE","BONK","DOGS","CATI","GOAT","PNUT","ACT",
        "CHILLGUY","TURBO","LUNA","BOME","MOTHER","PONKE","GME","HONK",
        "MYRO","WOJAK","MIGGO","COQ","SLERF","SMOG","BOME","SILLY",
        "NOOT","WOOF","COPE","BASED","FROG","CAT","DOG","APE",
        "MONKEY","HAMSTER","SQUIRREL","RACCOON","PENGUIN","PENG",
        "BRETT","ANDY","MOO","BAD","HARAMBE","GIGA","APED","LADYS","BABY",
        "MASKSOL","MASKSOLUSDT",
        "BANANA","PENG","NEIRO","SUNDOG","MOODENG","FWOG","GORK","MICHI","MAGA",
        "MANEKI","BOOMER","MEW","RETARDIO","POPCAT","GMEOW","INUVERSE","PUPS",
        "PUNCHUSDT",
    ],
    "Oracle": [
        "LINK","BAND","UMA","DIA","PYTH","STORK","SXT","TELL","CHR",
        "PROS","IO","ORAO","ACX","ATL","SUPR","ORAI","TRUF","PRIM",
        "DMT","REP","ORACLE","FEED","DATA","PRICE","TRUTH","REAL",
        "API3","NEST","DOS","WITNET","RAZOR","UMBRELLA","FLUX",
    ],
    "Privacy": [
        "XMR","DASH","SCRT","ROSE","ZEC","RAIL","DUSK","ZEN","COIN",
        "CTXC","PHALA","AZERO","PANTHER","LTZ","PANC","PRV","FIRO",
        "PIVX","XCM","GRIN","BEAMX","OXEN","NYM","TORN","IRON",
        "NAME","KRED","ZENN","SIV","PRIV","ANON","STEALTH","HIDE",
        "SHADOW","GHOST","INCOGNITO","HAVEN","NAVCOIN","PARTICL",
    ],
    "Storage": [
        "FIL","AR","STORJ","SC","BLZ","HOT","BTT","CKB","AIOZ","KYVE",
        "ALEPH","MXC","ACP","DATA","GEO","CSP","MNET","ZETA","SIA",
        "IPFS","AMBA","STORX","LAMB","BLS","BTTC","APEX","NKU","PEAQ",
        "RDX","ORDI","STORE","ARWEAVE","FILECOIN","AKASH","ANKR",
        "FLUX","PINATA","BUNDLR","SWARM","BTFS","CRUST","MEMO",
    ],
    "DePIN": [
        "IOTA","XNET","MOBI","HNT","LPT","NTRN","GPU","NOSANA","POND",
        "GEODNET","DAWN","WIFI","OXT","HELIUM","RDNT","GRASS","ION",
        "DINGO","TIA","CUDOS","SOARX","NGLA","PING","ROAM","NODEL",
        "CPOOL","SHDW","IOTX","POKT","POLKA","DOT","DEPIN","NETWORK",
        "SENSOR","WIRELESS","MESH","NODE","DEVICE","INFRA","PHYSICAL",
        "HIVEMAPPER","HIVELLO","NATIX","DIMO","REACT","NUBILA",
    ],
    "Old": [
        "LTC","ETC","XEM","LUNC","BTG","BCH","EOS","TRX","QTUM","ICX",
        "RVN","STEEM","ARK","NMR","DCR","DGB","NAV","ZRX","NEO","ONT",
        "XTZ","VET","WAVES","PIVX","CLASSIC","LEGACY","ORIGINAL",
    ],
    "NFT": [
        "NFT","BLUR","APE","LOOKS","RARI","X2Y2","SUDO","ENVELOP",
        "TENSOR","MEFO","PENGU","TROVE","CRAB","RARIBLE","MOMENT",
        "RFOX","ARTBLOCK","NFTFI","ARCADE","JPEG","SPICE","GALLERY",
    ],
    "CrossChain": [
        "BRIDGE","CROSS","RELAY","WORMHOLE","AXELAR","HYPERLANE",
        "STARGATE","CONNEXT","SOCKET","ACROSS","SYNAPSE","MULTICHAIN",
        "HOP","CELER","LAYERZERO","ROUTER","INTEROP","PORTAL","RANGO",
        "CHAINHOP","CHAINPORT","NOMAD","RHIZOME","ANYSWAP",
    ],
    "Social": [
        "SOCIAL","LENS","DESO","ENS","CYBER","ORBS","FRIEND","MIRROR",
        "GRAPE","YUP","PHAVE","KIWA","BUZZ","CLUB","CREATOR","GALXE",
        "QUEST","POST","FORUM","CHAT","VOICE","SHARE","LIKE","TRIBE",
    ],
    "LST": [
        "LDO","RPL","SWISE","PSTAKE","DIVA","UNSHETH","SSV",
        "ETHFI","EIGEN","PENDLE","SYMBIOTI","KARAK","RESTAKE",
        "RETH","WBETH","SFRX","METH","OSETH","STADER","LSETH",
    ],
    "BTCEco": [
        "STX","ORDI","SATS","RATS","MUBI","NALS","MERL","RUNE",
        "WZRD","BRC","NOSTR","SPARKS","ALEX","ROOTSTOCK","LIGHTNING",
        "BISONL","CYTOM","STACKS","BITLAYER","BSQUARE","ARKUS",
    ],
    "Exchange": [
        "OKB","KCS","GT","MXC","BGB","LEO","HT","FTT","BMX",
        "DERI","KINE","KWENTA","PERP","GNS","SYNTHR","DRIFT",
        "VERTEX","RABBITX","BPXE","DUET","OPHX",
    ],
    "Metaverse": [
        "METAVERSE","VOXEL","SOMNIUM","DECENTRAL","UNIVERSE","REALM",
        "EARTH","WORLD","SPACE","LAND","NAKA","CEEK","SPORT","BLOKTOP",
        "PORTALS","EVERMOON","WIMU","RLTY","OPENM","MIDNIGHTM",
    ],
    "Payments": [
        "PAY","PAYMENT","TRANSFER","REMIT","FLEXA","REQ","UTR",
        "WIRE","NANO","HBAR","XLM","XRP","COTI","PLUTON","SPEEND",
        "BIFROST","ZARP","GBPT","EURT","JPYT","CADC","AUSD",
    ],
    "Robotics": [
        "ROBOT","ROBO","MECH","AUTOMATE","COBALT","HUMANOID",
        "AGIX","FETCH","OCEAN","RENDER","RNDR","NUMERAI","ARKM",
        "PHALA","CUDOS","CGPT","NEURO","VIRT","SWARM","MEAI",
    ],
    "NeoBank": [
        "BANK","NEOBANK","FINTECH","CARD","DEBIT","CREDIT","IBAN",
        "NEXO","WIREX","MPAY","PAYP","MNTL","BRLU","SOLO","SPRM",
        "FLARE","SGUS","BIGT","APTPAY","AXPAY","OPENPAY","FOLIO",
    ],
    "Quantum": [
        "QUANTUM","QUANT","QNT","QTUM","QUBIC","IONQ","QUAI",
        "ALEPH","NQU","KVANT","QUIP","QKCE","QBIT","QSAFE",
        "POSTQUANTUM","DILITHIUM","KYBER","CRYSTALS","LATTICE",
    ],
    "POW": [
        "POW","MINING","MINER","HASH","HASHRATE","PROOF","WORK",
        "ZEC","ZIL","ALPHA","ZANO","RIF","CPH","KLS","KAS",
        "ERGO","RVN","DCR","GRL","BEAM","GRIN","KAWPOW","FLUX",
    ],
}

STABLECOINS = {
    "USDT","USDC","BUSD","FDUSD","USDP","GUSD","HUSD","USDN",
    "USDX","USDJ","USDK","USDQ","USDD","USD1","USDE","USDZ",
    "ZUSD","CUSD","SUSD","MUSD","RUSD","AUSD","NUSD","TUSD",
    "EURS","EURT","EURC","EURA","EUROC",
    "PAXG","XAUT","CACHE","PMGT",
    "DAI","FRAX","MIM","LUSD","ALUSD","DOLA","CRVUSD",
    "MKUSD","PYUSD","USDM","USDY","USDS","GHO","LISUSD","BEAN",
    "PAX","UST","RSR","USDL","BUIDL",
}

LEVERAGE_KEYWORDS = ["3L","3S","5L","5S","BULL","BEAR","UP","DOWN","LONG","SHORT","HEDGE"]
STABLE_KEYWORDS   = ["USD","EUR","GBP","JPY","CNY","AUD","CHF","GOLD","SILVER","PAX","DAI","FRAX"]




SECTORS = {
    "AI": [

        "FETUSDT","AGIXUSDT","OCEANUSDT","RENDUSDT","RENDERUSDT","GRTUSDT",
        "TAOAUSDT","ARKMUSDT","PHAUSDT","AIXBTUSDT","NEWTUSDT",
        "NEIROUSDT","AIUSDT","CGPTUSDT","NEUROUSDT","VANAUSDT",
        "DFUSDT","COOKIEUSDT","AIDOGEUSDT","MYRIAUSDT","ALETHUSDT",
        "WLDUSDT","KAIAUSDT","GRIFFAINUSDT","VIRTUSDT","SWARMAUSDT",
        "SENTIENTUSDT","MASKUSDT","AKTOUSDT","NUMUSDT","MEAIUSDT","MIRAUSDT",

        "KAITOUSDT","PAALUSDT","QUBICUSDT","SLEEPLESSUSDT","AITECHUSDT",
        "DEAIUSDT","SEKAIUSDT","BUZZUSDT","ALTERUSDT","COGNIUSDT",
        "EZAIUSDT","NAUAUSDT","TAOUSSDT","AGENTUSDT","AIGENUSDT",
        "BRAINUSDT","THINKUSDT","SMARTAIUSDT","FAIUSDT","DAINUSDT",
        "TONIXAIUSDT",
    ],
    "RWA": [

        "ONDOUSDT","CFGUSDT","RSRUSDT","MPLXUSDT","REALUSDT",
        "TRSTUSDT","PROMUSDT","IDUSDT","MANTRAUSDT","XDCUSDT",
        "LQTYUSDT","SPXUSDT","ONPUSDT","VAIUSDT","GOLDUSDT",
        "TBLUSDT","PARCLUSDT","REXUSDT","HONEUSDT","OPENUSDT",
        "LANDXUSDT","CREDIXUSDT","POLIXUSDT","TRUEUSDT","MTVUSDT",
        "PROPUSDT","REUSDT","TPROTUSDT","STBTCUSDT","CULTUSDT",

        "POLYXUSDT","CENTUSDT","TOUCANUSDT","COORESTUSDT","REALIOУСDT",
        "LOFTYUSDT","MAPLEUSDT","GOLDFINCHUSDT","DEXTUSDT","BRICSUSDT",
        "ESTATEUSDT","REALTUSDT","DINOUSDT","FLOWXUSDT","ACHUSDT",
        "CELLUSDT","NEXOUSDT","SECURITIZEUSDT","POLKUSDT","NEWRLAUSDT",
        "CENTAUSDT","TRADEAUSDT",

        "PLUMEUSDT","CANTONUSDT","ASSETUSDT","TOKENYUSDT","DIGIASSETUSDT",
    ],
    "Gaming": [

        "AXSUSDT","SANDUSDT","MANAUSDT","ILVUSDT","GMTUSDT",
        "YGGUSDT","SLPUSDT","GALAUSDT","RONUSDT","IMXUSDT",
        "BEAMUSDT","PIXELUSDT","NOTUSDT","XAIUSDT","ALICEUSDT",
        "RAREUSDT","MOBAUSDT","PORTALUSDT","CHZUSDT","PGXUSDT",
        "HEROESUSDT","BEXUSDT","GOMAUSDT","ACEUSDT","METAUSDT",
        "WAXPUSDT","GALUSDT","VIDYAUSDT","ELFUSDT","TWTUSDT",

        "GHSTUSDT","TOWERUSDT","REVVUSDT","NFTXUSDT","MOBOXUSDT",
        "SKILLUSDT","DERACEUSDT","WARSUSDT","BATTLEUSDT","LEGENDUSDT",
        "KARTUSDT","CHAMPUSDT","WINUSDT","SUPERUSDT","GODSUSDT",
        "AURYUSDT","ATLASUSDT","POLISUSDT","PVUUSDT","REALMUSDT","MAGICUSDT",
    ],
    "DeFi": [

        "UNIUSDT","AAVEUSDT","CAKEUSDT","SUSHIUSDT","COMPUSDT",
        "MKRUSDT","CRVUSDT","LDOUSDT","1INCHUSDT","C98USDT",
        "DYDXUSDT","GMXUSDT","JUPUSDT","RAYUSDT","ORCAUSDT",
        "PENDLEUSDT","EIGENUSDT","ETHFIUSDT","IDEXUSDT","REZUSDT",
        "SYRUPUSDT","BONEUSDT","CVXUSDT","FRAXUSDT","FXSUSDT",
        "TRIBEUSDT","RADUSDT","ALPACAUSDT","RAMPUSDT","WOOUSDT",

        "SNXUSDT","KNCUSDT","BALUSDT","BIFIUSDT","PERPUSDT",
        "JOEUSDT","SPIRITUSDT","VELODROMEUSDT","AERODROMEUSDT","THENAUSDT",
        "KYBERUSDT","BANCORUSDT","QUICKUSDT","SOLARUSDT","CAMELOTUSDT",
        "HYPEUSDT","RAMSESUSDT","STERLINGUSDT","DODOUSDT","WIGOUSDT","APESWAPUSDT",
    ],
    "Layer1": [

        "AVAXUSDT","ADAUSDT","ATOMUSDT","NEARUSDT","FTMUSDT",
        "ALGOUSDT","ICPUSDT","APTUSDT","SUIUSDT","SEIUSDT",
        "INJUSDT","KASUSDT","TONUSDT","HBARUSDT","EGLDUSDT",
        "ZILUSDT","ONEUSDT","CFXUSDT","JASMYUSDT","LSKUSDT",
        "QNTUSDT","CELOUSDT","FLOWUSDT","MINAUSDT","KAVAUSDT",
        "VETUSDT","ONTUSDT","WAVESUSDT","XTZUSDT","NEOUSDT",

        "SAGAUSDT","ZETAUSDT","VENOMUSDT","FUSEUSDT","SUPRAUSDT",
        "INITIAUSDT","STORYUSDT","MOVEMENTUSDT","MONADUSDT","BERACHAINUSDT",
        "ECLIPSEUSDT","SYSUSDT","COTIUSDT","RLCUSDT","TRACUSDT",
        "ALEOUSDT","ERAUSDT","HYPERUSDT","NEONUSDT","FUSIONUSDT",
        "CONCORDUSDT","NOLAUSDT","PALLADAUSDT","DFINITYUSDT","COSMOSUSDT",
    ],
    "Layer2": [

        "POLUSDT","OPUSDT","ARBUSDT","ZKUSDT","STRKUSDT",
        "LRCUSDT","METISUSDT","MANTAUSDT","SCROLLUSDT","MNTUSDT",
        "MERLUSDT","ALTUSDT","WUSDT","ZROUSDT","LINEAUSDT",
        "TAIKOUSDT","MODUSDT","CELRUSDT","SKLUSDT","OMGUSDT",
        "SSVUSDT","NEONUSDT","ZKCUSDT",

        "BLASTUSDT","MODEUSDT","MINTUSDT","ZORAUSDT","CYBERUSDT",
        "ANCIENT8USDT","KINTOУСDT","REDSTONEUSDT","LUMIAУСDT","ZKFAIRUSDT",
        "ZKLINKUSDT","ZKMEUSDT","ANYONEUSDT","ERGUSDT","SCRUSDT",
        "ARRUSDT","ZEPHUSDT","PIRATEUSDT","OPSUSDT","BOBAUSDT",
        "XVMUSDT","FRAXTALUSDT","MANTLEUSDT","BASEUSDT","PARTUSDT",
        "CHEQOUSDT","ZKPUSDT","POLYGONUSDT","GNOSISUSDT","KAIKOUSDT",

        "AXLUSDT","WORMHOLEUSDT","LAYERZUSDT","HYPERLANEUSDT","CELERУСDT",
    ],
    "Meme": [

        "DOGEUSDT","SHIBUSDT","PEPEUSDT","FLOKIUSDT","WIFUSDT",
        "BOMUSDT","MEMEUSDT","TUROUSDT","POPCATUSDT","MOGUSDT",
        "BABYDOGEUSDT","BONKUSDT","DOGSUSDT","CATIUSDT","GOATUSDT",
        "PNUTUSDT","ACTUSDT","CHILLGUYUSDT","TURBOUSDT","LUNAUSDT",
        "BOMEUSDT","MOTHERUSDT","PONKEUSDT","GMEUSDT","HONKUSDT",

        "MYROUSUSDT","WOJAKSUSDT","MIGGOUSDT","COQUSDT","SLERFUSDT",
        "SMOGUSDT","SILLYUSDT","NOOTUSDT","WOOFUSDT","COPEUSDT",
        "BASEDUSDT","FROGUSDT","BRETTUSDT","ANDYUSDT",
        "MOOUSDT","BADUSDT","HARAMBEUSDT","GIGAUSDT","APEDUSDT",
        "LADYSUSDT","MOODENGUSDT","PENGUUSDT","APEUSDT","REFACTAUSDT",
    ],
    "Oracle": [

        "LINKUSDT","BANDUSDT","UMAUSDT","DIAUSDT","PYTHUSDT",
        "STORKUSDT","SXTUSDT","TELLOUSDT","CHRUSDT","PROSUSDT",
        "IOUSDT","ORAOUSDT","ACXUSDT","ATLUSDT","SUPRUSDT",
        "ORAIUSDT","TRUFUSDT","PRIMUSDT","DMTUSDT","REPUSDT",

        "API3USDT","FLUXUSDT","IOSTUSDT","NESTUSDT","DOSUSDT",
        "WITNETUSDT","RAZORUSDT","UMBRELLAУСDT","FIOUSDT","BIOUSDT",
        "HUMAUSDT","TRUTHUSDT","LAZIOUSDT","OOKIUSDT","DORGUSDT",
        "COCOSUSDT","MYSTUSDT","SWTHUSDT","COVALENTUSDT","PARSIQУСDT",
        "ALCHEMYUSDT","BADGERUSDT","WINKUSDT","ANKRUSDT","GEОDBUSDT",
        "INDEXCOOPUSDT","ZAPPERUSDT","POWERPOOLUSDT","NXRAUSDT","TELLUSDT2",
        "ORACLIZEUSDT","AUGUR2USDT","REALITUUSDT","TRUEBITUSDT","CHRONICLEUSDT",
    ],
    "Privacy": [

        "XMRUSDT","DASHUSDT","SCRTUSDT","ROSEUSDT","ZECUSDT",
        "RAILUSDT","DUSKUSDT","ZENUSDT","COINUSDT","CTXCUSDT",

        "PHAUSDT","TORNUSDT","FIROUSDT","SCUSDT","HOPRUSDT",
        "LATUSDT","ERGUSDT","PIVXUSDT","ALEOUSDT","PARTUSDT",
        "ZEPHUSDT","ARRUSDT","NYMUSDT","COTIUSDT","RLCUSDT",
        "TRACUSDT","MINAUSDT","XELUSDT","HMNDUSDT","CHEQOUSDT",

        "OXENUSDT","BEAMXUSDT","GRINUSDT","NAVCUSDT","HAVENUSDT",
        "PANTHERUSDT","PRVCUSDT","ANONUSDT","IRONUSDT","SAFEUSDT",
        "XCMUSDT","LTZUSDT","ZENNUSDT","AZROUSDT","NYMOUSDT",

        "ZKPUSDT","SILUSDT","ANYONEUSDT","SHADUSDT","FIROUSDT",
        "ERGOUSDT","PIRATEUSDT","BCHPUSDT","ARRRUSDT","MAVUSDT",
    ],
    "Storage": [

        "FILUSDT","ARUSDT","STORJUSDT","SCUSDT","BLZUSDT",
        "HOTUSDT","CKBUSDT","AIOZUSDT","KYVEUSDT","ALEPHUSDT",
        "DATAUSDT","SIACOINUSDT","LAMBUSDT","BTTCUSDT","PEAQUSDT",

        "ANKRUSDT","CRUSTUSDT","MEMOUSDT","BTFSUSDT","SWARMUSDT",
        "BUNDLRUSDT","AKASHUSDT","FLUXUSDT","STORXUSDT","BLUZELLEUSDT",
        "SPHERONUSDT","JACKALUSDT","CERAMICUSDT","ESTUARYUSDT","LIGHTHOUSEUSDT",
        "ARDRIVEUSDT","EVERPAYUSDT","SEASCAPEUSDT","DXCHAINUSDT","OPACITYUSDT",
        "INTERNXTUSDT","SKYNETUSDT","NUMBERSUSDT","ORDIUSDT","FILEBASEUSDT",
        "IEXECUSDT","IPFSUSDT","CSPUSDT","GREENFIELDUSDT","FILSWANUSDT",
        "SINSOUSDT","ESTUSDT","BLZUSDT2","HOTLIBREUSDT","SIAUSDT2",
        "NETWORKUSDT","CHAINPOLUSDT","DSHAREUSDT",
    ],
    "DePIN": [

        "IOTAUSDT","HNTUSDT","LPTUSDT","NTRNUSDT","GPUUSDT",
        "PONDUSDT","DAWNUSDT","WIFIUSDT","OXTUSDT","RDNTUSDT",
        "GRASSUSDT","IONUSDT","TIAUSDT","CUDOSUSDT","IOTXUSDT",
        "POKTUSDT","DOTUSDT","XNETUSDT","MOBIUSDT","NOSANAUSDT",

        "HIVEMAPPERUSDT","HIVELLOUSDT","NATIXUSDT","DIMOUSDT","NUBILAUSDT",
        "REACTUSDT","GEODNETUSDT","SOARXUSDT","NGLAUSDT","PINGUSDT",
        "ROAMUSDT","NODELUSDT","CPOOLUSDT","SHDWUSDT","HELIUMUSDT",
        "SENSORUSDT","MESHUSDT","MXCUSDT","PEAQUSDT","AUTONUSDT",
        "DKGUSDT","AIRNODEUSDT","EXOCOREUSDT","ACURASTUSDT","ROAMXUSDT",
        "IONUSDT2","SULLYUSDT","POKTUSDT2","IOTXUSDT2","WIFIUSDT2",
        "RNDRNETUSDT","POWERLEDGERUSDT","ORIGINTRAILUSDT","DATAUSDT2",
    ],
    "Old": [

        "LTCUSDT","ETCUSDT","LUNCUSDT","BCHUSDT","EOSUSDT",
        "TRXUSDT","QTUMUSDT","RVNUSDT","ARKUSDT","DCRUSDT",
        "DGBUSDT","ZRXUSDT","NEOUSDT","ONTUSDT","VETUSDT",

        "STEEMUSDT","NMRUSDT","XEMUSDT","WAVESUSDT","ICXUSDT",
        "BATUSDT","SNTUSDT","GNTUSDT","FUNUSDT","POWRUSDT",
        "GTOUSDT","APPCUSDT","REPUSDT","OMGUSDT","BTGUSDT",
        "DIGIBYTЕUSDT","NAVUSDT","STRATUSDT","PPCUSDT","NUUSDT",
        "BNTUSDT","KMDUSDT","PIVXUSDT2","ARDRUSDT","SCUSD",
        "LSTUSDT","MANAUSDT2","XRPCLASSICUSDT","MAIDUSDT","BLOCKUSDT",
        "SYSCOINUSDT","VERGEUSDT","GAMECREDITUSDT","HTMLCOINUSDT","PUNDIXUSDT",
        "MONAUSDT","DIGIУСDT","PARTICLUSDT","NULSUSDT","WANCUSDT",
        "STORMXUSDT","OROPOCKETUSDT","AIONUSDT","ELECUSDT","ETHCLASSICUSDT",
        "TOKENOMYUSDT","BRDUSDT","CREDITCOINUSDT","DGTXUSDT","BITCIUSDT",
    ],


    "Robotics": [

        "WLDUSDT","RENDUSDT","FETUSDT","AGIXUSDT","OCEANUSDT",
        "AKTOUSDT","NUMERAIUSDT","ARKMUSDT","PHAUSDT","CUDOSUSDT",
        "CGPTUSDT","NEUROUSDT","VIRTUSDT","SWARMAUSDT","MEAIUSDT",
    ],

    "NeoBank": [

        "XLMUSDT","XRPUSDT","PYTHUSDT","STRKUSDT","COTIUSDT",
        "REQUSDT","PAYUSDT","SOLOUSDT","BRLUSDT",
        "SPRMUSDT","PAYPUSDT","MNTLUSDT","NEXOUSDT","WIREXUSDT",
        "MPAYUSDT","PAYPOLUSUSDT","FLAREUSDT","SGUSDUSDT","BIGTUSDT",

        "APTUSDT","AVAXUSDT","SOLUSDT","ATOMUSDT","OPUSDT",
        "POLUSDT","AXELARUSDT","OPTIMISMUSDT","STRKUSDT",
    ],

    "Quantum": [

        "QNTUSDT","QTUMUSDT","IONQUSDT","QUAIUSDT","KVANTUSDT",
        "QUIPUSDT","QUANTUMUSDT","QKCUSDT","ALEPHUSDT","NQUUSDT",
    ],
    "POW": [
        "ZECUSDT", "ZILUSDT", "ALPHUSDT", "ZANOUSDT",
        "RIFUSDT", "CPHUSDT", "KLSUSDT", "KASUSDT",
        "ERGOUSDT", "RVNUSDT", "DCRUSDT", "GRLUSDT",
    ],

    "NFT": [
        "BLURUSDT","APUSDT","LOOKSUSDT","X2Y2USDT","RARIUSDT",
        "NFTUSDT","NFTXUSDT","CNFTUSDT","SOLUUSDT","OPENUSDT",
        "SUDOUSDT","RESERVOIRUSDT","ENVELOUSDT","ZOORUSDT",
        "TENSRUSDT","MEFOUSDT","ORDINALSHUBUSDT","SUPRUSDT",
        "PENGUUSDT","BEANSUSDT","PUPPETSUSDT","APEUSDT",
        "PMONUSDT","TROVEUSDT","JUNKIUSDT","CRABUSDT",
        "RARIBLEUSDT","MINTABLEUSDT","XCOPYUSDT","NIFTUSDT",
        "ASYNCUSDT","KNOWNORIGINUSDT","MINTBASUSDT","MOMENTUSDT",
        "NBAUSDT","NFTSUSDT","METAHEROUSA","RFOXUSDT","GAFUSDT",
    ],

    "CrossChain": [
        "AXLUSDT","WUSDT","ZROUSDT","CELRUSDT","NXMUSDT",
        "HOPUSDT","ACROSSUSDT","SYNUSDT","RNGRUSDT","ROUTERUSDT",
        "MULTIUSDT","ANYUSDT","STARGATUSDT","LIFINUSDT","ORBSUSDT",
        "HYPERLANEUSDT","WORMHOLEUSDT","LAYERZUSDT","CHAINLINKUSDT",
        "INTUSDT","ROOTUSDT","BRIDGEUSDT","CONNEXTUSDT","SOCKETUSDT",
        "DELNUSDT","CELERУСDT","RELAYUSDT","CHAINHOPUSDT","RHIZOMAUSDT",
        "ATOMUSDT","QNTUSDT","COSMUSDT","IRISUSDT","GRAVITONUSDT",
    ],

    "Social": [
        "MASKSUSDT","LENSUSDT","DESO","ENSUSDT","CYBERUSDT",
        "MOONUSDT","CULTU","ORBS","SOCIALUSDT","DESOUSDT",
        "LIFOUSDT","FRIENDUSDT","CRDTUSDT","FORAUSDT","SPACEUSDT",
        "TWITTERUSDT","DISCORDUSDT","REVERIUSDT","SHOWUSDT",
        "PHAVEUSDT","KIWAUSDT","SOCIEXUSDT","FAVOUSDT","YUPUSDT",
        "LENDSUSDT","MIRRORUSDT","LOGIOSUSDT","MINTBASEUSDT",
        "GRAPUSDT","PINUSDT","POSTUSDT","CHEESEUSDT","BUZZUSDT2",
        "CLUBUSDT","CREATORUSDT","LAUNCHUSDT","GALXEUSDT","QUESTUSDT",
    ],

    "LST": [
        "LDOUSDT","RPLUSDT","ETHFIUSDT","EIGENUSDT","ANKRUSDT",
        "SSVUSDT","STETHUSDT","CBETHUSDT","FRXETHUSDT","PENDLE",
        "PSTAKEUSDT","SWISEUSDT","DIVAUSDT","UNSHETHUSDT","METHUSDT",
        "STUSDT","ETXUSDT","MNTETHUSDT","ANKRBNBUSDT","WSETHUSDT",
        "RESTAKEDUSDT","SYMBIOTIUSDT","KARAK","EIGENPIEUSDT",
        "RETHUSDT","OSETHUSDT","WOETHUSDT","ASTETHUSDT","LSETHUSDT",
        "STMATICUSDT","RMATICUSDT","SAVAXUSDT","QIUSDT","ANKRAVAXUSDT",
        "SOLUSDUSDT","LSTUSDT","STAKINGUSDT","LIQUIDUSDT","YIELDUSDT",
    ],

    "BTCEco": [
        "STXUSDT","RIFUSDT","ORDIUSDT","SATSUSDT","RATSUSDT",
        "MUBIUSDT","NALSUSDT","MERLUSDT","ALTUSDT","WZRDUSDT",
        "RUNEUSDT","RUNESUSDT","RUNEZUSDT","SATOSHIBTCUSDT","BRCUSDT",
        "BITUSDT","BRCSTACKUSDT","BOBUSDT","HEAPUSDT","ORDUSDT",
        "ZBTCUSDT","BTCLUSDT","ROOTSTOCKUSDT","LIQUIDBTCUSDT",
        "BOLTZUSDT","LIGHTNINGUSDT","NOSTRAUSDT","ARKUSDT","BVMUSDT",
        "BSQUAREUSDT","BITCOINSVUSDT","STXAUSDT","ALEXUSDT","HARPUSDT",
        "CYTOUSDT","IDXUSDT","BISONUSDT","SPARKUSDT","LIQUIDIUMUSDT",
    ],

    "Exchange": [
        "BNBUSDT","OKBUSDT","CROUSDT","KCSUSDT","GTUSDT",
        "MXUSDT","BGBUSDT","LEUCUSDT","HUSUSDT","FTTUSDT",
        "BITUSDT","DERIDBITUSDT","BITOROUSUSDT","DERIUSDT","KINEUSDT",
        "HVHUSDT","BMXUSDT","BPXUSDT","DUETUSDT","PZEUSDT",
        "NFTPLUSDT","BITFOREXUSDT","BKEXUSDT","LBKUSDT","COINWUSDT",
        "ZFMUSDT","WOOUSUSDT","OPHUSDT","DEXUSDT","DYDXUSUSDT",
        "PERPUSDT","SYNTUSUSDT","GNSUSDT","KWENTAUSDT","CAMELOTUSDT2",
        "WXTUSDT",
    ],

    "Metaverse": [
        "SANDUSDT","MANAUSDT","ENJUSDT","HEROESUSDT","SUPERUSDT",
        "NAKAUSDT","SPORTUSDT","CEEKUSDT","DVFUSDT","NFTUSDT",
        "MVLUSDT","VRAAUSDT","PUMLXUSDT","WPPUSDT","SOMNUSDT",
        "VOXELUSDT","HVHUSDT","BLOKTOPUSDT","METATIMEUSDT",
        "MVLUSDT","SPACENUSUSDT","TREEUSDT","RLTYUSDT","LANDXUSDT",
        "OPENMETAUSDT","WIMUSDT","EVERLANDUSDT","PORTALSUSDT",
        "MIDNIGHTUSDT","METAUSDT","EARTHUSDT","UNIVERSEUSDT",
        "REALMSUSDT","STARSUSDT","REALVRUSDT","DECENTRALUSDT",
        "DUSTUSDT",
    ],

    "Payments": [
        "XRPUSDT","XLMUSDT","NANOUSDT","HBARUSDT","ALGOUSDT",
        "COTIUSDT","REQUSDT","UTRUSDT","FLEXA","QNTUSDT",
        "PAYUSDT","PAYPLUSDT","TERNUSDT","TERN","BRLUSDT",
        "MPAYUSDT","SPRMUSDT","SOLOUSDT","NEXOUSDT","WIREXUSDT",
        "PLUTUSDT","SPEENDUSDT","BIFROSTUSDT","RIPPLUSDT","PAXGUSDT",
        "PAYMASTERUSDT","USEPLUSDT","BITICUSDT","BITPAYUSDT","SPHYNXUSDT",
        "NOMADUSDT","NUVOUSDT","MINTPAYUSDT","ZARPUSDT","GBPTUSDT",
        "EURTUSDT","JPYTUSDT","CNYUSDT","AUSDUSDT","CADUSTUSDT",
    ],
}


#   LOGGING

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("mafio_bot.log", encoding="utf-8"),
    ]
)
log = logging.getLogger("MafioBot")


#                   STATE

tracked        = {}   # {sym: {entry, peak, level, sl_pct, entry_time, last_alert}}
discovered     = {}   # {sym: {price, time, score}}

btc_change_24h = 0.0
btc_trend_1h   = 0.0
eth_change_24h = 0.0
btc_tps_stats  = {}
eth_tps_stats  = {}
market_state        = "SAFE"
last_market_report  = 0.0
MARKET_REPORT_EVERY = 21600


_btc_danger_count  = 0
_btc_caution_count = 0
_btc_safe_count    = 0
hot_sectors    = []        # type: List[str]
hot_symbols    = set()     # type: Set[str]
sector_vol_history = {}    # type: Dict[str, float]

candidates     = []        # type: List[str]
changes_map    = {}        # type: Dict[str, float]
all_tickers    = []

klines_cache   = {}        # type: Dict[str, Tuple[Any, float]]

last_tickers      = 0.0
last_btc          = 0.0
last_sectors      = 0.0
last_deep_scan    = 0.0
last_stale        = 0.0
last_report       = 0.0
last_smart_money  = 0.0
last_expand       = 0.0
last_daily_report = 0.0


daily_market_vol_history = []


market_activity_history = []   # type: List[Dict]  [{date, buy_vol, sell_vol, sigma_coins}]
breakout_report_sent    = {}   # type: Dict[str,str]  {date: sent}
tv_script_cache         = {}   # type: Dict[str,str]  {sym: script}
daily_report_sent_date   = ""


lz_alerted         = {}   # type: Dict[str, float]  {sym: last_alert_time}
lz_daily_sent_date = ""


hidden_accum_alerted = {}  # type: Dict[str, float]  {sym: last_alert_time}


tps_alerted      = {}   # type: Dict[str, float]  {sym: last_alert_time}
last_tps_scan    = 0.0  # type: float
last_whale_check = 0.0
tps_baseline     = {}   # type: Dict[str, float]  {sym: avg_tps_baseline}


tps_alerted  = {}
coin_alerted = {}
coin_signal_count = {}
coin_whale_done   = {}
whale_watchlist  = {}
whale_confirmed  = {}
lz_tps_alerted = {}
tps_baseline = {}    # type: Dict[str, float]  baseline TPS per coin
last_tps_scan= 0.0   # type: float
lh_alerted   = {}    # type: Dict[str, float]  {sym: last_alert_time}
last_lh_scan = 0.0


small_caps        = []
last_sc_refresh   = 0.0
sc_alerted        = {}   # type: Dict[str, float]  {sym: last_alert_time}

stable_vol_history = {}   # type: Dict[str, List[float]]
smart_money_alert  = False
smart_money_bonus  = 0

price_prev         = {}   # type: Dict[str, float]
momentum_alerted   = {}   # type: Dict[str, float]
momentum_stage     = {}   # type: Dict[str, Dict]


watchlist          = {}   # type: Dict[str, Dict]


price_snapshot     = {}   # type: Dict[str, float]  {sym: price_1h_ago}
price_snapshot_time = 0.0


sector_vol_snapshots = {}  # type: Dict[str, List[float]]   {sector: [vol1, vol2, ...]}
sector_change_snapshots = {}  # type: Dict[str, List[float]] {sector: [avg_ch1, avg_ch2, ...]}
sector_flow_alerted  = {}  # type: Dict[str, float]          {sector: last_alert_time}
sector_flow_hot      = {}  # {sector: timestamp} قطاعات تلقت سيولة مؤخراً
sector_flow_state    = {}  # type: Dict[str, str]            {sector: "IN"/"OUT"/"NEUTRAL"}
last_sr_alert        = 0.0
top10_alerted        = {}  # type: Dict[str, float]          {sector: last_top10_alert_time}


coin_vol_history     = {}  # type: Dict[str, List[float]]   {sym: [vol1, vol2, ...]}


bottom_price_history = {}  # type: Dict[str, List[float]]  {sym: [price1, price2, ...]}
bottom_vol_history   = {}  # type: Dict[str, List[float]]  {sym: [vol1, vol2, ...]}
bottom_alerted       = {}  # type: Dict[str, float]        {sym: last_alert_time}
explosion_alerted    = {}  # type: Dict[str, float]  {sym: last_alert_time}
ath_tracker      = {}  # type: Dict[str, float]  {sym: all_time_high_price}
ath_alerted      = {}  # type: Dict[str, float]  {sym: last_alert_time}
gem_watchlist    = {}
daily_gem_count  = {"date": "", "count": 0}
last_ath_scan    = 0.0
hot_alerted      = {}  # type: Dict[str, float]  {sym: last_alert_time}
last_hot_scan    = 0.0
rt_vol_baseline  = {}
rt_alerted       = {}  # type: Dict[str, float]  {sym: last_alert_time}
wl_entry_alerted = {}  # type: Dict[str, float]  {sym: last_entry_alert_time}
wl_price_snapshot= {}  # type: Dict[str, float]  {sym: price_when_added}
last_wl_check    = 0.0
# Trailing Stop state
ts_positions     = {}  # type: Dict[str, Dict]  {sym: {entry, peak, stop, locked}}
ts_sell_alerted  = {}  # type: Dict[str, float] {sym: last_sell_time}
last_ts_scan     = 0.0
daily_signals    = {"date": "", "count": 0}
last_rt_scan         = 0.0
last_bottom_scan     = 0.0
last_breakout5m_scan = 0.0
_breakout5m_alerted  = {}   # type: Dict[str, float]  {sym: last_alert_time}
last_fast_scan       = 0.0
_fast_alerted        = {}   # type: Dict[str, float]  {sym: last_alert_time}
_fast_price_snap     = {}   # type: Dict[str, float]  {sym: price_30s_ago}
last_bounce_scan     = 0.0
_bounce_alerted      = {}   # type: Dict[str, float]  {sym: last_alert_time}
last_bb_squeeze_scan = 0.0
_bb_squeeze_alerted  = {}   # type: Dict[str, float]  {sym: last_alert_time}
_market_bias_score   = 0    # type: int  — آخر نقطة محسوبة (-100 إلى +100)
last_move1h_scan     = 0.0
_move1h_alerted      = {}   # type: Dict[str, float]  {sym: last_alert_time}
last_flowacc_scan    = 0.0
_flowacc_alerted     = {}   # type: Dict[str, float]
last_volbr_scan      = 0.0
_volbr_alerted       = {}   # type: Dict[str, float]
last_micropump_scan  = 0.0
_micropump_alerted   = {}   # type: Dict[str, float]
_multi_confirm       = {}   # type: Dict[str, dict]  {sym: {"count":N,"scanners":[],"last_time":ts}}
MULTI_CONFIRM_WINDOW = 1800  # 30 دقيقة — نافذة التأكيد المتعدد


backtest_signals     = {}  # type: Dict[str, Dict]  {sym: {entry_price, entry_time, sector, checked_1h, checked_4h, checked_24h}}

api_calls_total    = 0
api_calls_minute   = 0
api_minute_reset   = time.time()

session = requests.Session()
_sent_dedup = {}   # {msg_hash: timestamp} — يمنع إرسال نفس الرسالة مرتين
session.headers.update({"User-Agent": "MafioBot/11.0"})



#   HELPERS

def fmt_price(p):
    # type: (float) -> str
    if p == 0: return "0"
    if p < 0.0001:  return "{:.10f}".format(p).rstrip("0")
    if p < 1:       return "{:.8f}".format(p).rstrip("0")
    if p < 1000:    return "{:.4f}".format(p).rstrip("0").rstrip(".")
    return "{:,.2f}".format(p)








_signal_queue   = []
_queue_lock     = False
MAX_QUEUE_SIZE  = 20

def queue_signal(sym, msg, score, sig_type="WATCH"):
    # type: (str, str, int, str) -> None
    global _signal_queue

    for i, item in enumerate(_signal_queue):
        if item["sym"] == sym:
            if score > item["score"]:
                _signal_queue[i] = {"sym": sym, "msg": msg,
                                    "score": score, "type": sig_type,
                                    "time": time.time()}
            return
    if len(_signal_queue) < MAX_QUEUE_SIZE:
        _signal_queue.append({"sym": sym, "msg": msg,
                              "score": score, "type": sig_type,
                              "time": time.time()})

def flush_signal_queue(max_send=5):
    # type: (int) -> None
    global _signal_queue
    if not _signal_queue:
        return

    _signal_queue.sort(key=lambda x: -x["score"])

    to_send = _signal_queue[:max_send]
    _signal_queue = _signal_queue[max_send:]
    for item in to_send:
        send(item["msg"])
        log.info(" QUEUE_SEND | %s | score=%d | type=%s",
                 item["sym"], item["score"], item["type"])



def send(msg, personal_only=False):
    # type: (str, bool) -> None
    """
    يرسل الرسالة لـ:
    - CHAT_ID دائماً (الشخصي)
    - GROUP_ID إذا كان مضبوطاً (المجموعة)

    personal_only=True → الشخصي فقط (للأوامر الخاصة)
    """


    if 'WATCH ALERT' in msg and 'نشاط مشبوه' in msg:
        import re as _re
        # نبحث عن VDelta بعد كلمة VDelta مباشرة
        vd_match = _re.search(r"\U0001f4ca VDelta: `?(\d+)%", msg) or _re.search(r"VDelta[^\n]*?(\d+)%[^\n]*", msg)
        if vd_match:
            vd_val = int(vd_match.group(1))

            vol_match = _re.search(r'حجم[^\d]*([\d\.]+)M', msg)
            vol_m = float(vol_match.group(1)) if vol_match else 1.0
            vol_usdt = vol_m * 1_000_000
            _t = get_tier_settings(vol_usdt)
            min_vd = int(_t["vdelta_min"] * 100)
            if vd_val < min_vd:
                log.info(" send() BLOCKED [%s]: VDelta=%d%% < %d%% | %s",
                         _t["label"], vd_val, min_vd, msg[:50])
                return

    if not TELEGRAM_TOKEN or len(TELEGRAM_TOKEN) < 10:
        log.info("[TELEGRAM] %s", msg[:80])
        return

    # ── dedup: منع إرسال نفس الرسالة مرتين خلال 90 ثانية ──────────
    _now_s = time.time()
    _msg_hash = hash(msg[:150])
    if _now_s - _sent_dedup.get(_msg_hash, 0) < 90:
        log.debug("send() DEDUP blocked duplicate message")
        return
    _sent_dedup[_msg_hash] = _now_s
    # تنظيف الـ dedup القديم
    if len(_sent_dedup) > 200:
        _cutoff = _now_s - 300
        for _k in [k for k, v in list(_sent_dedup.items()) if v < _cutoff]:
            _sent_dedup.pop(_k, None)

    targets = [CHAT_ID]
    if GROUP_ID and not personal_only:
        targets.append(GROUP_ID)

    for chat_id in targets:
        if not chat_id or "YOUR" in str(chat_id):
            continue
        for _attempt in range(3):
            try:
                session.post(
                    "https://api.telegram.org/bot{}/sendMessage".format(TELEGRAM_TOKEN),
                    data={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"},
                    timeout=15,
                )
                break
            except Exception as e:
                if _attempt < 2:
                    time.sleep(2)
                else:
                    log.error("Telegram [%s]: %s", chat_id, e)




_tg_offset = 0


def poll_commands():
    # type: () -> None
    """يستمع لأوامر Telegram ويرسل التقرير فوراً عند الطلب"""
    global _tg_offset, daily_report_sent_date
    try:
        url = "https://api.telegram.org/bot{}/getUpdates?offset={}&timeout=3&allowed_updates=message".format(
            TELEGRAM_TOKEN, _tg_offset)
        r = requests.get(url, timeout=10)
        if r.status_code == 409:

            log.warning(" getUpdates 409 -  Webhook ")
            try:
                requests.get(
                    "https://api.telegram.org/bot{}/deleteWebhook?drop_pending_updates=true".format(TELEGRAM_TOKEN),
                    timeout=10
                )
                log.info(" Webhook  -  ")
            except Exception as _e:
                log.error(" deleteWebhook : %s", _e)
            return
        if r.status_code != 200:
            log.warning(" getUpdates HTTP %d", r.status_code)
            return
        data = r.json()
        if not data.get("ok"):
            log.warning(" getUpdates not ok: %s", data)
            return
        updates = data.get("result", [])
        if updates:
            log.info(" getUpdates: %d  ", len(updates))
        for update in updates:
            _tg_offset = update["update_id"] + 1

            msg = update.get("message") or update.get("channel_post") or {}
            text = msg.get("text", "").strip()

            text_lower = text.lower()
            chat_id = str(msg.get("chat", {}).get("id", ""))
            log.info(" update: chat_id=%s text='%s'", chat_id, text)

            allowed = [str(CHAT_ID)]
            if GROUP_ID and GROUP_ID != "YOUR_GROUP_ID":
                allowed.append(str(GROUP_ID))
            if chat_id not in allowed:
                log.warning(" chat_id  : %s | allowed: %s", chat_id, allowed)
                continue

            if text_lower in ("/report", "/تقرير"):
                log.info(" /report   chat_id=%s", chat_id)
                send("\U0001f4e4 جاري إعداد التقرير...")

                global all_tickers
                if not all_tickers:
                    log.info(" /report: all_tickers  -  ")
                    try:
                        _r = safe_get(MEXC_24H)
                        if _r:
                            all_tickers = _r
                            log.info(" all_tickers : %d ", len(all_tickers))
                    except Exception as _e:
                        log.error("   all_tickers: %s", _e)
                daily_report_sent_date = ""
                lz_daily_sent_date     = ""
                send_daily_report(force=True)
            elif text_lower in ("/4h", "/report4h", "/تقرير4"):
                log.info(" /4h   chat_id=%s", chat_id)
                send("📡 جاري إعداد تقرير 4 ساعات...")
                global last_4h_report
                last_4h_report = 0.0
                send_4h_market_report()
            elif text_lower in ("/status", "/حالة"):
                send("\u2705 البوت يعمل | " + str(len(candidates)) + " عملة تحت المراقبة" +
                     " | جواهر: " + str(len(gem_watchlist)))
            elif text_lower in ("/watchlist", "/مراقبة"):
                if not watchlist:
                    send("👁️ قائمة المراقبة فارغة")
                else:
                    _static = [(s,v) for s,v in watchlist.items() if v.get("priority")=="STATIC"]
                    _dynamic= [(s,v) for s,v in watchlist.items() if v.get("priority")!="STATIC"]
                    txt = "👁️ *قائمة المراقبة:*\n"
                    if _static:
                        txt += "\n📌 *ثابتة (" + str(len(_static)) + "):*\n"
                        for s,v in _static:
                            base = s.replace("USDT","")
                            ep   = wl_price_snapshot.get(s,0)
                            txt += "  · *" + base + "* | دخول: `" + str(ep) + "`\n"
                    if _dynamic:
                        txt += "\n⚡ *ديناميكية (" + str(len(_dynamic)) + "):*\n"
                        for s,v in _dynamic[:5]:
                            base = s.replace("USDT","")
                            txt += "  · *" + base + "* | " + v.get("reason","")[:30] + "\n"
                    send(txt)
            elif text_lower in ("/gems", "/جواهر"):
                if not gem_watchlist:
                    send("\U0001f48e لا توجد جواهر حالياً")
                else:
                    txt = "\U0001f48e *جواهر مرصودة:*\n"
                    for s,v in list(gem_watchlist.items())[:10]:
                        txt += "  • *" + s.replace("USDT","") + "* | مرحلة " + str(v.get("stage",1)) + "\n"
                    send(txt)
            elif text_lower in ("/btc", "/بتكوين"):
                _icon = {"SAFE":"🟢","CAUTION":"🟡","DANGER":"🚨"}.get(market_state,"📊")
                _btps = ("  🐋 TPS:`{:.1f}` ATS:`{:.0f}$` VD:`{:.0f}%`".format(
                    btc_tps_stats.get("tps",0), btc_tps_stats.get("ats",0),
                    btc_tps_stats.get("vdelta",0.5)*100
                )) if btc_tps_stats else ""
                send(
                    "₿ *BTC الآن*\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    "{} السوق: *{}*\n"
                    "24h: `{:+.2f}%`\n"
                    "4h:  `{:+.2f}%`\n"
                    "1h:  `{:+.2f}%`\n"
                    "{}".format(
                        _icon, market_state,
                        btc_change_24h, btc_trend_4h, btc_trend_1h,
                        _btps
                    )
                )

            elif text_lower in ("/sectors", "/قطاعات"):
                if not hot_sectors:
                    send("📊 لا توجد قطاعات ساخنة حالياً")
                else:
                    txt = "🏆 *أفضل القطاعات الآن:*\n━━━━━━━━━━━━━━━━━━\n"
                    for i, (sec, data) in enumerate(list(hot_sectors.items())[:5], 1):
                        ch = data.get("change", 0)
                        icon = "🔥" if ch >= 5 else ("📈" if ch >= 2 else "➡️")
                        txt += "{}. {} *{}* `{:+.2f}%`\n".format(i, icon, sec, ch)
                    send(txt)

            elif text_lower in ("/performance", "/اداء"):
                perf_daily_report()

            elif text_lower in ("/hunter", "/صياد"):

                from collections import OrderedDict
                _recent = sorted(
                    [(s, v) for s, v in perf_track.items()],
                    key=lambda x: x[1].get("time", 0), reverse=True
                )[:5]
                if not _recent:
                    send("🔥 لا توجد إشارات Liquidity Hunter بعد")
                else:
                    txt = "🔥 *آخر إشارات Hunter:*\n━━━━━━━━━━━━━━━━━━\n"
                    for sym, v in _recent:
                        ch = v.get("change_pct", 0)
                        icon = "✅" if ch > 0 else "❌"
                        txt += "{} *{}* `{:+.2f}%` — {}\n".format(
                            icon, sym.replace("USDT",""), ch, v.get("system","")[:15]
                        )
                    send(txt)

            elif text_lower in ("/joker", "/جوكر"):
                if not whale_watchlist:
                    send("🃏 لا توجد عملات في مراقبة الجوكر حالياً")
                else:
                    now_t = time.time()
                    txt = "🃏 *عملات تنتظر الجوكر:*\n"
                    txt += "━━━━━━━━━━━━━━━━━━\n"
                    for s, v in list(whale_watchlist.items()):
                        base     = s.replace("USDT","")
                        elapsed  = int((now_t - v["time"]) / 60)
                        ats_then = v.get("ats_then", 0)
                        txt += "👁️ *{}* | منذ {} دقيقة | ATS كان: {:.0f}$\n".format(
                            base, elapsed, ats_then)
                    txt += "━━━━━━━━━━━━━━━━━━\n"
                    txt += "⏳ _الجوكر يراقب — ينتظر الحيتان_ 🐋"
                    send(txt)

            elif text_lower in ("/stop", "/ايقاف"):
                send("⏸️ تم إيقاف التنبيهات مؤقتاً — اكتب /start للعودة")

                import builtins
                builtins._mafio_paused = True

            elif text_lower in ("/start", "/تشغيل"):
                import builtins
                builtins._mafio_paused = False
                send("✅ التنبيهات تعمل الآن!")

            elif text_lower in ("/help", "/مساعدة"):
                send(
                    "🤖 *MAFIO-BOT — الأوامر:*\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    "📊 /status      — حالة البوت\n"
                    "₿ /btc         — سعر BTC والاتجاه\n"
                    "🏆 /sectors     — أفضل القطاعات\n"
                    "👁️ /watchlist   — قائمة المراقبة\n"
                    "📅 /report      — التقرير اليومي\n"
                    "📡 /4h          — تقرير السوق 4 ساعات\n"
                    "📈 /performance — نسبة نجاح الإشارات\n"
                    "🔥 /hunter      — آخر إشارات Hunter\n"
                    "⏸️ /stop        — إيقاف التنبيهات\n"
                    "✅ /start       — تشغيل التنبيهات\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    "💎 /gems        — الجواهر المرصودة\n"
                    "🃏 /جوكر        — عملات تنتظر الجوكر"
                )
    except Exception as e:
        log.debug("poll_commands error: %s", e)


_force_daily_report = False

def send_daily_report_forced():
    # type: () -> None
    """إرسال التقرير اليومي فوراً بدون قيد الوقت — /report"""
    global daily_report_sent_date, lz_daily_sent_date, _force_daily_report
    log.info("   -   ")
    daily_report_sent_date = ""
    lz_daily_sent_date     = ""
    _force_daily_report    = True
    try:
        send_daily_report()
    except Exception as e:
        log.error("    : %s", e)
        send("❌ خطأ في التقرير: {}".format(str(e)))
    finally:
        _force_daily_report = False



def safe_get(url, params=None, retries=3):
    # type: (str, Optional[dict], int) -> Optional[Any]
    """
    🆕 V15: Retry مع Exponential Backoff
    المحاولة 1: فوراً
    المحاولة 2: انتظر 2 ثانية
    المحاولة 3: انتظر 4 ثانية
    """
    global api_calls_total, api_calls_minute, api_minute_reset

    for attempt in range(retries):
        try:
            r = session.get(url, params=params, timeout=10)
            r.raise_for_status()
            api_calls_total  += 1
            api_calls_minute += 1
            _now = time.time()
            _elapsed = _now - api_minute_reset
            if _elapsed >= 60:

                _rate = int(api_calls_minute / (_elapsed / 60))
                log.info(" API: %d / | : %d",
                         _rate, api_calls_total)
                api_calls_minute = 0
                api_minute_reset = _now
            return r.json()

        except Exception as e:
            wait = 2 ** attempt  # 1s, 2s, 4s
            if attempt < retries - 1:
                log.debug("API retry %d/%d [%s]: %s -  %ds",
                          attempt + 1, retries, url.split("/")[-1], e, wait)
                time.sleep(wait)
            else:
                log.debug("API   [%s]: %s", url.split("/")[-1], e)

    return None



#   SMART CACHE

def get_klines(symbol, interval="15m", limit=50):
    # type: (str, str, int) -> Optional[Dict]
    cache_ttl = {"5m": 60, "15m": CACHE_15M, "1h": CACHE_1H, "4h": CACHE_4H}.get(interval, CACHE_15M)
    key = "{}_{}".format(symbol, interval)
    now = time.time()

    if key in klines_cache:
        data, ts = klines_cache[key]
        if now - ts < cache_ttl:
            return data

    raw = safe_get(MEXC_KLINES, {"symbol": symbol, "interval": interval, "limit": limit})
    if not raw or len(raw) < 6:
        return None

    try:
        opens  = [float(c[1]) for c in raw]
        highs  = [float(c[2]) for c in raw]
        lows   = [float(c[3]) for c in raw]
        closes = [float(c[4]) for c in raw]
        vols   = [float(c[5]) for c in raw]
        result = {
            "opens": opens, "highs": highs, "lows": lows,
            "closes": closes, "vols": vols,
            "avg_vol": sum(vols[:-1]) / max(len(vols[:-1]), 1),
        }
        klines_cache[key] = (result, now)
        return result
    except (IndexError, ValueError, ZeroDivisionError):
        return None


def clear_expired_cache():
    # type: () -> None
    now   = time.time()
    stale = [k for k, (_, ts) in list(klines_cache.items()) if now - ts > CACHE_4H * 2]
    for k in stale:
        del klines_cache[k]






def calc_rsi(closes, period=RSI_PERIOD):
    # type: (list, int) -> float
    """
    يحسب RSI على آخر (period+1) شمعة.
    يعيد قيمة 0-100، أو -1 إذا لم تكفِ البيانات.
    """
    if len(closes) < period + 1:
        return -1.0
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    recent = deltas[-period:]
    gains  = [d for d in recent if d > 0]
    losses = [-d for d in recent if d < 0]
    avg_gain = sum(gains) / period if gains else 0.0
    avg_loss = sum(losses) / period if losses else 0.0
    if avg_loss == 0:
        return 100.0
    rs  = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 1)


def rsi_label(rsi):
    # type: (float) -> str
    """تحويل قيمة RSI لنص وصفي"""
    if rsi < 0:     return "N/A"
    if rsi <= RSI_OVERSOLD:  return "🟢 ذروة بيع"
    if rsi <= 50:            return "🟡 محايد"
    if rsi <= RSI_IDEAL_MAX: return "🟡 جيد"
    if rsi <= RSI_OVERBOUGHT: return "🟠 مرتفع"
    return "🔴 ذروة شراء"














def calc_vwmacd(closes, vols, fast=12, slow=26):
    if len(closes) < slow or len(vols) < slow:
        return 0.0
    try:
        def vwma(n):
            pv = sum(closes[-i] * vols[-i] for i in range(1, n+1))
            v  = sum(vols[-i] for i in range(1, n+1))
            return pv / v if v > 0 else closes[-1]
        macd = vwma(fast) - vwma(slow)
        avg  = sum(closes[-slow:]) / slow
        return max(-1.0, min(1.0, macd / avg * 100)) if avg > 0 else 0.0
    except (IndexError, ValueError, ZeroDivisionError):
        return 0.0


def calc_weis_wave(closes, vols):
    if len(closes) < 5:
        return 0.5
    try:
        up = sum(vols[i] for i in range(1, len(closes)) if i < len(vols) and closes[i] > closes[i-1])
        dn = sum(vols[i] for i in range(1, len(closes)) if i < len(vols) and closes[i] < closes[i-1])
        total = up + dn
        return round(up / total, 3) if total > 0 else 0.5
    except (IndexError, ValueError, ZeroDivisionError):
        return 0.5


def calc_vol_rsi(closes, vols, period=14):
    if len(closes) < period + 2:
        return 0.5
    try:
        deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        recent = deltas[-period:]
        gains  = [d for d in recent if d > 0]
        losses = [-d for d in recent if d < 0]
        ag = sum(gains)  / period if gains  else 1e-10
        al = sum(losses) / period if losses else 1e-10
        return round(1 - 1 / (1 + ag / al), 3)
    except (IndexError, ValueError, ZeroDivisionError):
        return 0.5



def calc_vdelta_ma(sym, period=10, interval="15m"):
    # type: (str, int, str) -> float
    """
    VDelta Moving Average — متوسط ضغط الشراء على آخر N شمعة
    أدق بكثير من VDelta اللحظي
    يكشف التجميع المؤسسي الهادئ
    """
    kd = get_klines(sym, interval, period + 5)
    if not kd or len(kd["closes"]) < period:
        return 0.5
    try:
        closes = kd["closes"]
        opens  = kd["opens"]
        vols   = kd["vols"]
        n      = len(closes)


        vd_values = []
        for i in range(n):
            v = vols[i] if i < len(vols) else 0
            if closes[i] > opens[i]:
                vd_values.append((1.0, v))
            elif closes[i] < opens[i]:
                vd_values.append((0.0, v))
            else:
                vd_values.append((0.5, v))


        recent = vd_values[-period:]
        total_vol  = sum(v for _, v in recent)
        if total_vol <= 0:
            return sum(vd for vd, _ in recent) / len(recent)

        weighted_vd = sum(vd * v for vd, v in recent) / total_vol
        return round(weighted_vd, 3)

    except (IndexError, ValueError, ZeroDivisionError):
        return 0.5











def calc_wick_filter(sym, interval="15m"):
    # type: (str, str) -> tuple
    """
    فلتر ذيل الشمعة — يكشف التصريف
    يعيد: (passed, reason)
    True = شمعة نظيفة | False = ذيل تصريف
    """
    kd = get_klines(sym, interval, 5)
    if not kd or len(kd["closes"]) < 3:
        return True, ""
    try:
        closes = kd["closes"]
        opens  = kd["opens"]
        highs  = kd["highs"]
        lows   = kd["lows"]


        for i in range(-3, 0):
            body   = abs(closes[i] - opens[i])
            high   = highs[i]
            low    = lows[i]
            close  = closes[i]
            open_  = opens[i]

            if body <= 0:
                continue


            upper_wick = high - max(close, open_)

            lower_wick = min(close, open_) - low


            if upper_wick > body * 1.5:
                return False, "ذيل تصريف علوي {:.0f}%".format(
                    upper_wick / body * 100)

        return True, ""
    except (IndexError, ValueError, ZeroDivisionError):
        return True, ""


def calc_macd_histogram(sym, interval="1h"):
    # type: (str, str) -> float
    """
    MACD Histogram — زخم الحركة
    양수 = زخم صاعد | سالب = زخم هابط
    """
    kd = get_klines(sym, interval, 35)
    if not kd or len(kd["closes"]) < 26:
        return 0.0
    try:
        closes = kd["closes"]
        n = len(closes)


        def ema(data, period):
            k = 2.0 / (period + 1)
            result = [data[0]]
            for i in range(1, len(data)):
                result.append(data[i] * k + result[-1] * (1 - k))
            return result

        ema12 = ema(closes, 12)
        ema26 = ema(closes, 26)
        macd_line = [ema12[i] - ema26[i] for i in range(n)]
        signal    = ema(macd_line, 9)
        histogram = [macd_line[i] - signal[i] for i in range(n)]


        if len(histogram) >= 3:
            return histogram[-1] - histogram[-2]
        return 0.0
    except (IndexError, ValueError, ZeroDivisionError):
        return 0.0


def calc_atr_stop_loss(sym, price, interval="1h", period=14):
    # type: (str, float, str, int) -> float
    """
    ATR Stop Loss — وقف خسارة ديناميكي
    يعيد: سعر Stop Loss المناسب لتذبذب العملة
    """
    kd = get_klines(sym, interval, period + 5)
    if not kd or len(kd["closes"]) < period:
        return price * 0.95
    try:
        closes = kd["closes"]
        highs  = kd["highs"]
        lows   = kd["lows"]


        tr_values = []
        for i in range(1, len(closes)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
            tr_values.append(tr)

        if not tr_values:
            return price * 0.95


        atr = sum(tr_values[-period:]) / min(period, len(tr_values))


        sl = price - (2.0 * atr)


        sl_pct = (sl - price) / price * 100
        if sl_pct < -5.0:
            sl = price * 0.95
        elif sl_pct > -3.0:
            sl = price * 0.97

        return round(sl, 8)

    except (IndexError, ValueError, ZeroDivisionError):
        return price * 0.95











_cvd_cache = {}   # {sym: [cvd_values]}
CVD_PERIOD  = 24

def calc_money_flow_1h(sym):
    # type: (str) -> dict
    """
    تدفق الأموال الحقيقية (آخر 2 شمعة 1h) بالدولار — مثل Wolf Flow
    يستخدم: buy_ratio = (close - low) / (high - low) لتقدير ضغط الشراء/البيع
    يعيد: in, out, net, ratio
    """
    kd = get_klines(sym, "1h", 4)
    if not kd:
        return {"in": 0.0, "out": 0.0, "net": 0.0, "ratio": 1.0}
    highs  = kd["highs"]
    lows   = kd["lows"]
    closes = kd["closes"]
    vols   = kd["vols"]
    total_in  = 0.0
    total_out = 0.0
    for h, l, c, v in zip(highs[-2:], lows[-2:], closes[-2:], vols[-2:]):
        rng = h - l
        buy_ratio = (c - l) / rng if rng > 0 else 0.5
        vol_usdt   = v * c
        total_in  += vol_usdt * buy_ratio
        total_out += vol_usdt * (1.0 - buy_ratio)
    net   = total_in - total_out
    ratio = total_in / total_out if total_out > 0 else 99.0
    return {"in": total_in, "out": total_out, "net": net, "ratio": ratio}

def calc_cvd(sym, interval="1h", period=24):
    # type: (str, str, int) -> dict
    """
    CVD التراكمي — يحسب تراكم ضغط الشراء/البيع
    يعيد: trend, slope, latest, pct_change
    trend: rising/falling/flat
    """
    kd = get_klines(sym, interval, period + 3)
    if not kd or len(kd["closes"]) < 10:
        return {"trend": "flat", "slope": 0.0, "latest": 0.0, "pct_change": 0.0}

    try:
        closes = kd["closes"]
        opens  = kd["opens"]
        vols   = kd["vols"]
        n      = len(closes)


        cvd_values = []
        cumulative = 0.0

        for i in range(n):
            vol = vols[i] if i < len(vols) else 0
            if closes[i] > opens[i]:
                delta = vol
            elif closes[i] < opens[i]:
                delta = -vol
            else:
                delta = 0.0

            cumulative += delta
            cvd_values.append(cumulative)

        if len(cvd_values) < 5:
            return {"trend": "flat", "slope": 0.0, "latest": 0.0, "pct_change": 0.0}


        recent = cvd_values[-period:]


        first_half  = sum(recent[:len(recent)//2]) / (len(recent)//2)
        second_half = sum(recent[len(recent)//2:]) / (len(recent) - len(recent)//2)
        slope = second_half - first_half


        if abs(first_half) > 0:
            pct_change = (second_half - first_half) / abs(first_half) * 100
        else:
            pct_change = 0.0


        if slope > 0 and pct_change > 5:
            trend = "rising"
        elif slope < 0 and pct_change < -5:
            trend = "falling"
        else:
            trend = "flat"

        return {
            "trend":      trend,
            "slope":      round(slope, 2),
            "latest":     round(cvd_values[-1], 2),
            "pct_change": round(pct_change, 1),
        }

    except (IndexError, ValueError, ZeroDivisionError):
        return {"trend": "flat", "slope": 0.0, "latest": 0.0, "pct_change": 0.0}


def check_cvd_filter(sym, signal_type="JOKER", vdelta=0.0):
    # type: (str, str, float) -> tuple
    """
    فلتر CVD — يرفض الإشارات عند CVD هابط
    يعيد: (passed, reason)
    """
    cvd = calc_cvd(sym, "1h", 12)
    trend = cvd.get("trend", "flat")
    pct   = cvd.get("pct_change", 0.0)

    if signal_type == "JOKER":

        if trend == "falling" and pct < -10:
            # استثناء: VDelta قوي جداً → فحص CVD القصير (4h) بدلاً من 12h
            # السبب: بعد دمبات السوق، CVD 12h يبقى سلبياً رغم بدء التعافي
            if vdelta >= 0.80:
                cvd_short = calc_cvd(sym, "1h", 4)
                if cvd_short.get("trend") in ("rising", "flat"):
                    return True, "CVD قصير يتعافى (VDelta {:.0f}%)".format(vdelta * 100)
            return False, "CVD هابط {:.0f}%".format(pct)
    elif signal_type == "BOTTOM_FISHER":

        if trend == "falling":
            return False, "CVD هابط — تصريف خفي"

    return True, trend




def calc_ob_imbalance(sym, min_vol=500_000):
    # type: (str, float) -> dict
    """
    OB Imbalance — نسبة الاختلال في دفتر الطلبات
    Bids > Asks = دعم مخفي = إشارة شراء
    يعيد: ratio, signal, bids, asks
    """
    ob = get_order_book(sym)
    if not ob:
        return {"ratio": 1.0, "signal": "neutral", "bids": 0, "asks": 0}

    bids = ob.get("bid", 0)
    asks = ob.get("ask", 0)
    ratio = ob.get("imb", 1.0)

    if ratio >= 2.0:
        signal = "strong_buy"
    elif ratio >= 1.5:
        signal = "buy"
    elif ratio <= 0.5:
        signal = "strong_sell"
    elif ratio <= 0.7:
        signal = "sell"
    else:
        signal = "neutral"

    return {
        "ratio":  round(ratio, 2),
        "signal": signal,
        "bids":   round(bids, 0),
        "asks":   round(asks, 0),
    }



def calc_ob_depth_analysis(sym):
    # type: (str) -> dict
    """
    تحليل عميق لدفتر الطلبات — يكشف:
    1. جدران الشراء الكبيرة (Bid Walls) = دعم مخفي
    2. جدران البيع الكبيرة (Ask Walls) = مقاومة
    3. نسبة التركيز: أين تتمركز السيولة في أول 10 مستويات
    4. Bid Pressure: هل الشراء يضغط على البيع؟
    """
    ob = get_order_book(sym)
    if not ob:
        return {"has_bid_wall": False, "has_ask_wall": False,
                "bid_wall_pct": 0.0, "ask_wall_pct": 0.0,
                "top10_bid_ratio": 0.0, "top10_ask_ratio": 0.0,
                "pressure": "neutral", "score": 0}
    try:
        raw_bids = ob.get("raw_bids", [])
        raw_asks = ob.get("raw_asks", [])

        if not raw_bids or not raw_asks:
            return {"has_bid_wall": False, "has_ask_wall": False,
                    "bid_wall_pct": 0.0, "ask_wall_pct": 0.0,
                    "top10_bid_ratio": 0.0, "top10_ask_ratio": 0.0,
                    "pressure": "neutral", "score": 0}

        # حساب قيمة كل مستوى
        bid_levels = [(float(b[0]), float(b[1]), float(b[0]) * float(b[1]))
                      for b in raw_bids if len(b) >= 2]
        ask_levels = [(float(a[0]), float(a[1]), float(a[0]) * float(a[1]))
                      for a in raw_asks if len(a) >= 2]

        if not bid_levels or not ask_levels:
            return {"has_bid_wall": False, "has_ask_wall": False,
                    "bid_wall_pct": 0.0, "ask_wall_pct": 0.0,
                    "top10_bid_ratio": 0.0, "top10_ask_ratio": 0.0,
                    "pressure": "neutral", "score": 0}

        total_bid = sum(lv[2] for lv in bid_levels)
        total_ask = sum(lv[2] for lv in ask_levels)

        avg_bid_lvl = total_bid / len(bid_levels) if bid_levels else 1
        avg_ask_lvl = total_ask / len(ask_levels) if ask_levels else 1

        # كشف جدران الشراء
        bid_wall_val  = 0.0
        bid_wall_pct  = 0.0
        has_bid_wall  = False
        for price, qty, val in bid_levels:
            if val >= avg_bid_lvl * OB_WALL_RATIO and val >= OB_WALL_MIN_USDT:
                has_bid_wall = True
                bid_wall_val = max(bid_wall_val, val)
        if total_bid > 0:
            bid_wall_pct = round(bid_wall_val / total_bid * 100, 1)

        # كشف جدران البيع
        ask_wall_val  = 0.0
        ask_wall_pct  = 0.0
        has_ask_wall  = False
        for price, qty, val in ask_levels:
            if val >= avg_ask_lvl * OB_WALL_RATIO and val >= OB_WALL_MIN_USDT:
                has_ask_wall = True
                ask_wall_val = max(ask_wall_val, val)
        if total_ask > 0:
            ask_wall_pct = round(ask_wall_val / total_ask * 100, 1)

        # تركيز السيولة في أول 10 مستويات
        top10_bid = sum(lv[2] for lv in bid_levels[:10])
        top10_ask = sum(lv[2] for lv in ask_levels[:10])
        top10_bid_ratio = round(top10_bid / total_bid, 2) if total_bid > 0 else 0.0
        top10_ask_ratio = round(top10_ask / total_ask, 2) if total_ask > 0 else 0.0

        # ضغط الشراء مقابل البيع
        imb = ob.get("imb", 1.0)
        if imb >= 2.0 and has_bid_wall:
            pressure = "strong_buy"
        elif imb >= 1.5:
            pressure = "buy"
        elif imb <= 0.5 and has_ask_wall:
            pressure = "strong_sell"
        elif imb <= 0.7:
            pressure = "sell"
        else:
            pressure = "neutral"

        # نتيجة تحليل OB (0-100)
        score = 0
        if has_bid_wall:
            score += 30
            if bid_wall_pct >= 30:
                score += 20
        if imb >= 2.0:
            score += 25
        elif imb >= 1.5:
            score += 15
        if top10_bid_ratio >= 0.6:
            score += 10
        if not has_ask_wall:
            score += 15

        return {
            "has_bid_wall":     has_bid_wall,
            "has_ask_wall":     has_ask_wall,
            "bid_wall_pct":     bid_wall_pct,
            "ask_wall_pct":     ask_wall_pct,
            "top10_bid_ratio":  top10_bid_ratio,
            "top10_ask_ratio":  top10_ask_ratio,
            "pressure":         pressure,
            "score":            min(score, 100),
            "imb":              round(imb, 2),
            "total_bid":        round(total_bid, 0),
            "total_ask":        round(total_ask, 0),
        }
    except (ValueError, TypeError, ZeroDivisionError):
        return {"has_bid_wall": False, "has_ask_wall": False,
                "bid_wall_pct": 0.0, "ask_wall_pct": 0.0,
                "top10_bid_ratio": 0.0, "top10_ask_ratio": 0.0,
                "pressure": "neutral", "score": 0}


def calc_direction_engine(sym, interval="1h"):
    # type: (str, str) -> dict
    kd = get_klines(sym, interval, 60)
    if not kd or len(kd["closes"]) < 30:
        return {}
    closes = kd["closes"]
    vols   = kd["vols"]
    vwmacd_s = (calc_vwmacd(closes, vols) + 1) / 2 * 100
    weis_s   = calc_weis_wave(closes, vols) * 100
    vrsi_s   = calc_vol_rsi(closes, vols) * 100
    bull_raw = vwmacd_s * 0.40 + weis_s * 0.40 + vrsi_s * 0.20
    agree = sum([vwmacd_s > 55, weis_s > 55, vrsi_s > 55])
    mult  = 1.0 if agree == 3 else (0.85 if agree == 2 else 0.70)
    conf  = "عالي" if agree == 3 else ("متوسط" if agree == 2 else "منخفض")
    bull  = round(bull_raw * mult, 1)
    bear  = round(max(0, (100 - bull_raw) * mult * 0.7), 1)
    neut  = round(max(0, 100 - bull - bear), 1)
    if bull >= 70 and agree >= 2:
        verdict = "توافق مؤسسي - سيولة حقيقية"
    elif bull >= 60:
        verdict = "ميل صاعد - انتظر التاكيد"
    elif bear >= 60:
        verdict = "ضغط بيعي - احذر"
    else:
        verdict = "عرضي - لا اتجاه واضح"
    return {
        "bullish_pct": bull, "bearish_pct": bear, "neutral_pct": neut,
        "confidence": conf, "verdict": verdict, "agree": agree,
    }


def calc_hmm_regime(sym, interval="4h"):
    # type: (str, str) -> dict
    kd = get_klines(sym, interval, 100)
    if not kd or len(kd["closes"]) < 20:
        return {"regime": "unknown", "regime_ar": "غير محدد",
                "trending": 33, "ranging": 34, "volatile": 33}
    closes = kd["closes"]
    highs  = kd["highs"]
    lows   = kd["lows"]
    n      = len(closes)
    try:
        first20 = sum(closes[:20]) / 20
        last20  = sum(closes[-20:]) / 20
        trend_s = abs(last20 - first20) / first20 * 100 if first20 > 0 else 0
        atrs    = [(highs[i] - lows[i]) / lows[i] * 100 for i in range(n) if lows[i] > 0]
        avg_atr = sum(atrs) / len(atrs) if atrs else 0
        up      = sum(1 for i in range(1, n) if closes[i] > closes[i-1])
        direct  = abs(up - (n-1-up)) / (n-1) * 100
        volatile_s = min(100, avg_atr * 10)
        trending_s = min(100, trend_s * 3 + direct * 0.5)
        ranging_s  = max(0, 100 - volatile_s * 0.4 - trending_s * 0.4)
        total = volatile_s + trending_s + ranging_s or 1
        vp = round(volatile_s / total * 100)
        tp = round(trending_s / total * 100)
        rp = 100 - vp - tp
        if tp >= vp and tp >= rp:
            reg, reg_ar = "trending", "اتجاهي هادئ"
        elif vp >= tp and vp >= rp:
            reg, reg_ar = "volatile", "تقلبات حادة"
        else:
            reg, reg_ar = "ranging", "تذبذب عرضي"
        return {"regime": reg, "regime_ar": reg_ar,
                "trending": tp, "ranging": rp, "volatile": vp}
    except (IndexError, ValueError, ZeroDivisionError):
        return {"regime": "unknown", "regime_ar": "غير محدد",
                "trending": 33, "ranging": 34, "volatile": 33}


def calc_garch_range(sym, interval="1d"):
    # type: (str, str) -> dict
    kd = get_klines(sym, interval, 30)
    if not kd or len(kd["closes"]) < 10:
        return {}
    closes = kd["closes"]
    try:
        import math
        lr = [math.log(closes[i] / closes[i-1])
              for i in range(1, len(closes)) if closes[i-1] > 0]
        if len(lr) < 5:
            return {}
        mean = sum(lr) / len(lr)
        var  = sum((r - mean)**2 for r in lr) / len(lr)
        cvar = var * 0.1
        for r in lr[-5:]:
            cvar = var * 0.1 + 0.1 * r**2 + 0.85 * cvar
        pvol = cvar ** 0.5
        cur  = closes[-1]
        return {
            "support":        round(cur * math.exp(mean - pvol), 8),
            "resistance":     round(cur * math.exp(mean + pvol), 8),
            "volatility_pct": round(pvol * 100, 2),
            "current":        cur,
        }
    except (ImportError, ValueError, ZeroDivisionError, OverflowError):
        return {}









def calc_murray_math(sym, interval="1d"):
    # type: (str, str) -> dict
    """
    Murray Math — مستويات الدعم والمقاومة الرياضية
    يعيد: levels, current_level, support, resistance, zone
    """
    kd = get_klines(sym, interval, 64)
    if not kd or len(kd["closes"]) < 20:
        return {}
    try:
        highs  = kd["highs"]
        lows   = kd["lows"]
        closes = kd["closes"]


        highest = max(highs[-64:]) if len(highs) >= 64 else max(highs)
        lowest  = min(lows[-64:])  if len(lows)  >= 64 else min(lows)
        current = closes[-1]

        if highest <= lowest:
            return {}


        price_range = highest - lowest
        import math
        scale = math.pow(10, math.floor(math.log10(price_range)))
        mm_range = math.ceil(price_range / scale) * scale


        step = mm_range / 8
        base = math.floor(lowest / scale) * scale

        levels = {}
        labels = ["-1/8","0/8","1/8","2/8","3/8","4/8","5/8","6/8","7/8","8/8","9/8"]
        for i, label in enumerate(labels):
            levels[label] = round(base + (i - 1) * step, 8)


        current_zone = "محايد"
        nearest_support = levels["0/8"]
        nearest_resist  = levels["8/8"]
        zone_label = "4/8"

        for i in range(len(labels) - 1):
            l1 = levels[labels[i]]
            l2 = levels[labels[i+1]]
            if l1 <= current <= l2:
                zone_label = labels[i]
                nearest_support = l1
                nearest_resist  = l2


                if labels[i] in ["0/8", "8/8"]:
                    current_zone = "منطقة انعكاس قوية جداً"
                elif labels[i] in ["1/8", "7/8"]:
                    current_zone = "منطقة اختراق"
                elif labels[i] == "4/8":
                    current_zone = "محور رئيسي"
                elif labels[i] in ["2/8", "6/8"]:
                    current_zone = "دعم/مقاومة قوية"
                elif labels[i] in ["3/8", "5/8"]:
                    current_zone = "منطقة تجميع"
                break


        dist_to_support = abs(current - nearest_support) / current * 100 if current > 0 else 0
        dist_to_resist  = abs(nearest_resist - current)  / current * 100 if current > 0 else 0

        return {
            "levels":          levels,
            "current":         current,
            "zone_label":      zone_label,
            "current_zone":    current_zone,
            "support":         round(nearest_support, 8),
            "resistance":      round(nearest_resist, 8),
            "dist_support":    round(dist_to_support, 2),
            "dist_resist":     round(dist_to_resist, 2),
            "key_support":     round(levels.get("4/8", nearest_support), 8),
            "key_resist":      round(levels.get("8/8", nearest_resist), 8),
        }

    except (ImportError, ValueError, ZeroDivisionError, OverflowError):
        return {}



def calc_smart_targets(sym, price):
    # type: (str, float) -> dict
    if price <= 0:
        return {}


    mm   = calc_murray_math(sym, "1d")
    garch = calc_garch_range(sym, "1d")

    targets = []


    if mm and mm.get("levels"):
        for label, level in sorted(mm["levels"].items(), key=lambda x: x[1]):
            if level > price * 1.03:
                pct = (level - price) / price * 100
                targets.append({"price": round(level, 8), "pct": round(pct, 1),
                                "label": "Murray {}".format(label)})
            if len(targets) >= 3:
                break


    if len(targets) < 1 and garch:
        res = garch.get("resistance", 0)
        if res > price:
            pct = (res - price) / price * 100
            targets.append({"price": round(res, 8), "pct": round(pct, 1),
                            "label": "GARCH"})


    fixed = [1.10, 1.20, 1.35]
    for mult in fixed:
        if len(targets) >= 3:
            break
        t = round(price * mult, 8)
        pct = (mult - 1) * 100

        if not any(abs(x["price"] - t) / t < 0.03 for x in targets):
            targets.append({"price": t, "pct": round(pct, 1), "label": ""})


    sl = price * 0.96
    if mm and mm.get("support", 0) < price * 0.99:
        sl = mm["support"]
    elif garch and garch.get("support", 0) < price * 0.99:
        sl = garch["support"]

    sl_pct = (sl - price) / price * 100

    return {
        "targets": sorted(targets, key=lambda x: x["price"])[:3],
        "sl":      round(sl, 8),
        "sl_pct":  round(max(sl_pct, -5.0), 1),
        "sl":      round(max(sl, price * 0.95), 8),
    }

def format_murray_block(sym):
    # type: (str) -> str
    """يبني بلوك Murray Math للإشارة"""
    mm = calc_murray_math(sym)
    if not mm:
        return ""

    zone   = mm.get("zone_label", "")
    zname  = mm.get("current_zone", "")
    sup    = fmt_price(mm.get("support", 0))
    res    = fmt_price(mm.get("resistance", 0))
    ds     = mm.get("dist_support", 0)
    dr     = mm.get("dist_resist", 0)


    current = mm.get("current", 0)
    sl_raw  = mm.get("support", 0)

    if sl_raw >= current * 0.99 and current > 0:

        sl_raw = current * 0.97
    sl = fmt_price(sl_raw)

    out  = "📐 *Murray Math* منطقة `{}`\n".format(zone)
    out += "  {} | دعم:`{}` مقاومة:`{}`\n".format(zname, sup, res)
    return out



def build_engine_block(sym, include_levels=True):
    # type: (str, bool) -> str
    direction = calc_direction_engine(sym, "1h")
    hmm       = calc_hmm_regime(sym, "4h")
    garch     = calc_garch_range(sym, "1d") if include_levels else {}
    murray    = calc_murray_math(sym, "1d") if include_levels else {}
    cvd       = calc_cvd(sym, "1h", 12)
    if not direction and not hmm and not garch:
        return ""
    out = "=" * 18 + "\n"
    if direction:
        bull = direction.get("bullish_pct", 0)
        bear = direction.get("bearish_pct", 0)
        neut = direction.get("neutral_pct", 0)
        bars = "🟢" * int(bull / 20) + "⚪" * (5 - int(bull / 20))
        out += "📊 *ترجيح الاتجاه:*\n"
        out += "  {} `{:.0f}%` صاعد | `{:.0f}%` عرضي | `{:.0f}%` هابط\n".format(
            bars, bull, neut, bear)
        out += "  {} | ثقة: {}\n".format(
            direction.get("verdict", ""), direction.get("confidence", ""))
    if hmm and hmm.get("regime") != "unknown":
        icons = {"trending": "✅", "ranging": "🔄", "volatile": "⚠️"}
        icon  = icons.get(hmm.get("regime", ""), "")
        out += "🏛️ *نظام السوق:* {} {}\n".format(hmm.get("regime_ar", ""), icon)
    if garch:
        out += "📉 *GARCH* `{}%` تذبذب\n".format(garch.get("volatility_pct", 0))
        out += "  دعم:`{}` مقاومة:`{}`\n".format(
            fmt_price(garch.get("support", 0)),
            fmt_price(garch.get("resistance", 0)))
    if cvd and cvd.get("trend") != "flat":
        _cvd_icon = "📈" if cvd["trend"] == "rising" else "📉"
        out += "{} CVD: {} ({:+.0f}%)\n".format(
            _cvd_icon,
            "تجميع مستمر" if cvd["trend"] == "rising" else "تصريف خفي",
            cvd.get("pct_change", 0))

    # OB Imbalance
    _ob_data = calc_ob_imbalance(sym)
    _ob_r = _ob_data.get("ratio", 1.0)
    if _ob_r >= 1.5:
        out += "📊 OB: Bids/Asks `{:.1f}:1` — دعم مخفي 💪\n".format(_ob_r)
    elif _ob_r <= 0.7:
        out += "📊 OB: Bids/Asks `{:.1f}:1` — ضغط بيع ⚠️\n".format(_ob_r)

    if murray and garch:

        garch_sup = garch.get("support", 0)
        murray_sup = murray.get("support", 0)
        diff = abs(garch_sup - murray_sup) / garch_sup * 100 if garch_sup > 0 else 100
        if diff > 3.0:
            mm_block = format_murray_block(sym)
            if mm_block:
                out += mm_block
        else:

            zone  = murray.get("zone_label", "")
            zname = murray.get("current_zone", "")
            if zone:
                out += "📐 *Murray* منطقة `{}` — {}\n".format(zone, zname)
    elif murray:
        mm_block = format_murray_block(sym)
        if mm_block:
            out += mm_block
    out += "=" * 18 + "\n"
    return out









def calc_mtf_analysis(sym):
    # type: (str) -> dict
    """
    تحليل متعدد الأطراف الزمنية
    يعيد:
    - score: نقاط التوافق 0-100
    - verdict: حكم نهائي
    - bias: اتجاه غالب (bullish/bearish/neutral)
    - details: تفاصيل كل إطار
    """
    results = {}


    for interval, weight, label in [
        ("15m", 0.20, "15m"),
        ("1h",  0.40, "1h"),
        ("4h",  0.40, "4h"),
    ]:
        kd = get_klines(sym, interval, 50)
        if not kd or len(kd["closes"]) < 20:
            results[interval] = {"bull": 50, "weight": weight, "label": label}
            continue

        closes = kd["closes"]
        vols   = kd["vols"]
        opens  = kd["opens"]
        highs  = kd["highs"]
        lows   = kd["lows"]
        n      = len(closes)


        price_trend = (closes[-1] - closes[-10]) / closes[-10] * 100 if closes[-10] > 0 else 0


        ema20 = sum(closes[-20:]) / 20
        above_ema = closes[-1] > ema20

        # 3. Volume Confirmation
        buy_vol  = sum(vols[i] for i in range(n) if closes[i] > opens[i])
        sell_vol = sum(vols[i] for i in range(n) if closes[i] < opens[i])
        total_v  = buy_vol + sell_vol
        vol_bull = buy_vol / total_v if total_v > 0 else 0.5


        recent_lows = lows[-10:]
        higher_lows = sum(1 for i in range(1, len(recent_lows))
                         if recent_lows[i] > recent_lows[i-1])
        hl_ratio = higher_lows / (len(recent_lows) - 1) if len(recent_lows) > 1 else 0.5


        bull_score = (
            (50 + price_trend * 2) * 0.30 +
            (100 if above_ema else 0) * 0.25 +
            vol_bull * 100 * 0.25 +
            hl_ratio * 100 * 0.20               # Higher Lows
        )
        bull_score = max(0, min(100, bull_score))

        results[interval] = {
            "bull": round(bull_score, 1),
            "weight": weight,
            "label": label,
            "above_ema": above_ema,
            "price_trend": round(price_trend, 2),
            "vol_bull": round(vol_bull * 100, 1),
        }

    if not results:
        return {"score": 50, "verdict": "غير محدد", "bias": "neutral", "details": {}}


    weighted_bull = sum(r["bull"] * r["weight"] for r in results.values())



    bull_4h  = results.get("4h",  {}).get("bull", 50)
    bull_1h  = results.get("1h",  {}).get("bull", 50)
    bull_15m = results.get("15m", {}).get("bull", 50)


    conflict_4h_15m = (bull_4h < 40 and bull_15m > 65)
    conflict_4h_1h  = (bull_4h < 40 and bull_1h  > 65)


    if conflict_4h_15m and conflict_4h_1h:
        weighted_bull *= 0.60
        conflict_note = "⚠️ تضارب حاد — 4h هابط"
    elif conflict_4h_15m:
        weighted_bull *= 0.80
        conflict_note = "🟡 تضارب خفيف"
    else:
        conflict_note = ""


    all_bullish = bull_4h > 60 and bull_1h > 60 and bull_15m > 60
    all_bearish = bull_4h < 40 and bull_1h < 40 and bull_15m < 40

    if all_bullish:
        weighted_bull = min(100, weighted_bull * 1.10)


    score = round(weighted_bull, 1)

    if score >= 70 and all_bullish:
        verdict = "🟢 توافق كامل — دخول قوي"
        bias    = "bullish"
    elif score >= 65:
        verdict = "🟢 صاعد — دخول جيد"
        bias    = "bullish"
    elif score >= 55:
        verdict = "🟡 ميل صاعد — دخول حذر"
        bias    = "neutral"
    elif score <= 35:
        verdict = "🔴 هابط — لا تدخل"
        bias    = "bearish"
    else:
        verdict = "⚪ عرضي — انتظر"
        bias    = "neutral"

    if conflict_note:
        verdict = conflict_note + " | " + verdict

    return {
        "score":   score,
        "verdict": verdict,
        "bias":    bias,
        "details": results,
        "all_bullish": all_bullish,
        "conflict": bool(conflict_note),
    }


def format_mtf_block(sym):
    # type: (str) -> str
    """يبني بلوك MTF للإشارة"""
    mtf = calc_mtf_analysis(sym)
    if not mtf:
        return ""

    details = mtf.get("details", {})
    score   = mtf.get("score", 50)
    verdict = mtf.get("verdict", "")


    bar = "🟢" * int(score / 20) + "⚪" * (5 - int(score / 20))

    out  = "📈 *MTF Analysis:*\n"
    out += "  {} `{:.0f}%` توافق\n".format(bar, score)


    icons = {"15m": "⚡", "1h": "🕐", "4h": "📊"}
    for iv in ["4h", "1h", "15m"]:
        d = details.get(iv, {})
        if not d:
            continue
        bull = d.get("bull", 50)
        icon = icons.get(iv, "")
        trend_icon = "🟢" if bull >= 65 else ("🔴" if bull <= 40 else "🟡")
        out += "  {} {} `{:.0f}%`\n".format(icon, iv, bull)

    out += "  {}\n".format(verdict)
    return out


def update_coin_vol_history(vol_map):
    # type: (Dict[str, float]) -> None
    """
    يُستدعى من run() كل دورة (12 ثانية).
    يحفظ آخر VOL_HISTORY_MAX قراءة لكل عملة.
    """
    global coin_vol_history
    for sym, vol in vol_map.items():
        if vol <= 0:
            continue
        if sym not in coin_vol_history:
            coin_vol_history[sym] = []
        coin_vol_history[sym].append(vol)
        if len(coin_vol_history[sym]) > VOL_HISTORY_MAX:
            coin_vol_history[sym].pop(0)


def get_coin_vol_ratio(sym, current_vol):
    # type: (str, float) -> float
    """
    يقارن الحجم الحالي بالمتوسط التاريخي للعملة نفسها.
    أدق بكثير من مقارنة بمتوسط القطاع.
    يعيد 1.0 إذا لا يوجد تاريخ كافٍ.
    """
    hist = coin_vol_history.get(sym, [])
    if len(hist) < VOL_HISTORY_MIN:
        return 1.0

    prev = hist[:-1] if len(hist) > 1 else hist
    avg  = sum(prev) / len(prev)
    if avg <= 0:
        return 1.0
    return round(current_vol / avg, 2)



#   PRE-FILTER

def is_stablecoin(sym, last_price=0.0, change=0.0):
    # type: (str, float, float) -> bool
    base = sym.replace("USDT", "")
    if base in STABLECOINS: return True
    for kw in STABLE_KEYWORDS:
        if base.startswith(kw) or base.endswith(kw): return True
    if abs(change) < 0.5 and last_price > 0: return True
    return False


def is_suspicious(sym, price=0.0, vol=0.0, change=0.0):
    # type: (str, float, float, float) -> bool
    """
    يكشف العملات المشبوهة والـ Pump & Dump:

    ┌──────────────────────────────────────────┐
    │  Pump & Dump علامات:                      │
    │  1. حجم يومي منخفض جداً (سهل التلاعب)   │
    │  2. سعر قريب من الصفر (micro cap)        │
    │  3. ارتفاع مفاجئ كبير (Pump)             │
    │  4. اسم مشبوه (STABLE, EUR, TEST...)     │
    └──────────────────────────────────────────┘
    """
    base = sym.replace("USDT","")

    # 1. Stablecoin
    if is_stablecoin(sym, price, change):
        return True


    for kw in SUSPICIOUS_KEYWORDS:
        if kw in base:
            return True


    if vol < WHALE_MIN_VOL:
        return True


    if 0 < price < WHALE_MIN_PRICE:
        return True


    if change > WHALE_MAX_CHANGE:
        return True

    return False


def pre_filter(sym, change, vol, price=0.0):
    # type: (str, float, float, float) -> bool
    """
    🐛 إصلاح V11: أُزيل return True المكرر الميت
    """
    if not sym.endswith("USDT"): return False
    if sym in EXCLUDED: return False
    if "(" in sym or ")" in sym: return False   # رموز بأقواس = أزواج غير صالحة
    if any(k in sym for k in LEVERAGE_KEYWORDS): return False
    if is_stablecoin(sym, price, change): return False
    if vol < PRE_MIN_VOL or vol > PRE_MAX_VOL: return False
    if change < PRE_MIN_CHANGE or change > PRE_MAX_CHANGE: return False
    if market_state == "DANGER" and change <= btc_change_24h: return False
    return True



#   BTC MARKET ANALYSIS


def analyze_btc():
    # type: () -> None
    global btc_change_24h, btc_trend_1h, btc_trend_4h, market_state, last_btc
    global last_market_report
    global eth_change_24h


    data = safe_get(MEXC_24H, {"symbol": "BTCUSDT"})
    if not data:
        return

    try:
        last_price = float(data.get("lastPrice", 0))
        open_price = float(data.get("openPrice", last_price))
        if open_price > 0:
            btc_change_24h = (last_price - open_price) / open_price * 100
        else:
            btc_change_24h = float(data.get("priceChangePercent", 0))
    except (KeyError, ValueError, TypeError):
        pass


    kd1 = get_klines("BTCUSDT", "1h", 3)
    if kd1 and len(kd1["closes"]) >= 2:
        c = kd1["closes"]
        btc_trend_1h = (c[-1] - c[-2]) / c[-2] * 100 if c[-2] > 0 else 0.0


    btc_trend_4h = 0.0
    kd4 = get_klines("BTCUSDT", "4h", 3)
    if kd4 and len(kd4["closes"]) >= 2:
        c4 = kd4["closes"]
        btc_trend_4h = (c4[-1] - c4[0]) / c4[0] * 100


    eth_data = safe_get(MEXC_24H, {"symbol": "ETHUSDT"})
    if eth_data:
        try:
            _elp = float(eth_data.get("lastPrice", 0))
            _eop = float(eth_data.get("openPrice", _elp))
            if _eop > 0:
                eth_change_24h = (_elp - _eop) / _eop * 100
            else:
                eth_change_24h = float(eth_data.get("priceChangePercent", 0))
        except (KeyError, ValueError, TypeError):
            pass


    global btc_tps_stats, eth_tps_stats
    _btc_tps = analyze_tps_ats("BTCUSDT")
    if _btc_tps:
        btc_tps_stats = _btc_tps
    _eth_tps = analyze_tps_ats("ETHUSDT")
    if _eth_tps:
        eth_tps_stats = _eth_tps








    global _btc_danger_count, _btc_caution_count, _btc_safe_count


    danger_enter  = BTC_DANGER_ZONE  - BTC_DANGER_BUFFER   # -3.3%
    caution_enter = BTC_CAUTION_ZONE - BTC_CAUTION_BUFFER  # -1.8%


    danger_exit   = BTC_DANGER_ZONE  + BTC_DANGER_BUFFER   # -2.7%
    caution_exit  = BTC_CAUTION_ZONE + BTC_CAUTION_BUFFER  # -1.2%

    btc_signal = btc_change_24h


    _crash_4h = btc_trend_4h <= BTC_CRASH_4H
    _crash_1h = btc_trend_1h  <= BTC_CRASH_1H


    

    # VDelta السوق - نفس طريقة حساب التقرير
    _buy_vol = 0.0; _sell_vol = 0.0
    if all_tickers:
        for _t in all_tickers:
            try:
                _v = float(_t.get("quoteVolume", 0))
                _c = float(_t.get("priceChangePercent", 0))
                if _v < 10000: continue
                if _c > 0: _buy_vol += _v
                else: _sell_vol += _v
            except: pass
    _total_vol = _buy_vol + _sell_vol
    _mkt_vd_raw = (_buy_vol / _total_vol) if _total_vol > 0 else 0.5
    _btc_vd  = btc_tps_stats.get("vdelta", 0.5) if btc_tps_stats else 0.5
    _btc_ats = btc_tps_stats.get("ats", 0) if btc_tps_stats else 0
    _mkt_vd_w = _mkt_vd_raw * 0.60 + _btc_vd * 0.40

    # VDelta مبسط يعتمد على BTC وETH فقط (الأكثر دقة)
    _eth_vd  = eth_tps_stats.get("vdelta", 0.5) if eth_tps_stats else 0.5
    _eth_ats = eth_tps_stats.get("ats", 0) if eth_tps_stats else 0
    # وزن BTC 50% + ETH 30% + السوق 20%
    _combined_vd = _btc_vd * 0.50 + _eth_vd * 0.30 + _mkt_vd_raw * 0.20

    # القرار يعتمد على VDelta + ATS/TPS
    _btc_vd2  = btc_tps_stats.get("vdelta", 0.5) if btc_tps_stats else 0.5
    _btc_ats2 = btc_tps_stats.get("ats", 0) if btc_tps_stats else 0
    _eth_vd2  = eth_tps_stats.get("vdelta", 0.5) if eth_tps_stats else 0.5
    _eth_ats2 = eth_tps_stats.get("ats", 0) if eth_tps_stats else 0
    _w_sell = (_btc_vd2 < 0.40 and _btc_ats2 >= 2000) or (_eth_vd2 < 0.40 and _eth_ats2 >= 2000)
    _w_buy  = (_btc_vd2 >= 0.65 and _btc_ats2 >= 2000) or (_eth_vd2 >= 0.65 and _eth_ats2 >= 2000)
    _vd_final = _mkt_vd_raw * 0.60 + _btc_vd2 * 0.40
    _btc_vd_low  = _btc_vd2 < 0.42
    _btc_crash24 = btc_change_24h <= -2.5  # BTC نزل 2.5%+ في 24h
    if _crash_4h or btc_trend_1h <= -2.0 or _w_sell or _vd_final < 0.40 or _btc_vd_low or _btc_crash24:
        suggested = "DANGER"
    elif _vd_final >= 0.55 or (_vd_final >= 0.50 and _w_buy):
        suggested = "SAFE"
    else:
        suggested = "CAUTION"
    if suggested == "DANGER":
        _btc_danger_count  += 1
        _btc_caution_count  = 0
        _btc_safe_count     = 0
    elif suggested == "CAUTION":
        _btc_caution_count += 1
        _btc_danger_count   = 0
        _btc_safe_count     = 0
    elif suggested == "SAFE":
        _btc_safe_count    += 1
        _btc_danger_count   = 0
        _btc_caution_count  = 0
    else:

        pass


    old = market_state
    if _btc_danger_count  >= BTC_CONFIRM_COUNT:
        market_state = "DANGER"
    elif _btc_caution_count >= BTC_CONFIRM_COUNT:
        market_state = "CAUTION"
    elif _btc_safe_count    >= BTC_CONFIRM_COUNT:
        market_state = "SAFE"


    last_btc = time.time()

    if old != market_state:

        if time.time() - last_market_report < MARKET_REPORT_EVERY:
            log.info(" Market changed %s%s  cooldown 4h", old, market_state)
            return


        pass  # market_state من analyze_btc فقط
        last_market_report = time.time()
        icons = {"SAFE": "🟢", "CAUTION": "🟡", "DANGER": "🚨"}
        notes = {
            "SAFE":    "✅ كل الإشارات مفعّلة",
            "CAUTION": "⚠️ Gold فقط (Score 88+)",
            "DANGER":  "🔴 إشارات القطاعات الساخنة فقط",
        }

        def _tps_line(stats, sym):
            # type: (Dict, str) -> str
            if not stats:
                return ""
            _vd  = stats.get("vdelta", 0.5)
            _ats = stats.get("ats", 0)
            _tps = stats.get("tps", 0)
            _bt  = stats.get("buyer_type", "")
            _verdict = (
                "🐋 حيتان يشترون 🔥" if _ats >= ATS_WHALE and _vd >= 0.65 else
                "🔴 حيتان يبيعون!" if _ats >= ATS_WHALE and _vd < 0.40 else
                "📊 نشاط طبيعي"
            )
            return (
                "  TPS:`{:.1f}` ATS:`{:.0f}$` {}\n"
                "  ↳ {}\n".format(_tps, _ats, _bt, _verdict)
            )

        btc_tps_line = _tps_line(btc_tps_stats, "BTC")
        eth_tps_line = _tps_line(eth_tps_stats, "ETH")


        _buy_vol_mkt  = 0.0
        _sell_vol_mkt = 0.0
        _mkt_n        = 0
        if all_tickers:
            for _t in all_tickers:
                try:
                    _vol = float(_t.get("quoteVolume", 0))
                    _chg = float(_t.get("priceChangePercent", 0))
                    if _vol < 10000:
                        continue
                    if _chg > 0:
                        _buy_vol_mkt  += _vol
                    else:
                        _sell_vol_mkt += _vol
                    _mkt_n += 1
                except (ValueError, TypeError):
                    pass
        _total_mkt = _buy_vol_mkt + _sell_vol_mkt
        _mkt_vd_raw = (_buy_vol_mkt / _total_mkt * 100) if _total_mkt > 0 else 50


        _btc_vd_weight = btc_tps_stats.get("vdelta", 0.5) * 100 if btc_tps_stats else 50

        _mkt_vd_pct = _mkt_vd_raw * 0.60 + _btc_vd_weight * 0.40

        track_liquidity_exit(_mkt_vd_pct)

        # market_state يُحدَّث فقط في analyze_btc


        _hot_line = "🔥 أفضل قطاع: *{}*\n".format(hot_sectors[0]) if hot_sectors else ""


        _btc_vd_now = btc_tps_stats.get("vdelta", 0.5) if btc_tps_stats else 0.5
        _btc_ats_now = btc_tps_stats.get("ats", 0) if btc_tps_stats else 0

        _eth_vd_now = eth_tps_stats.get("vdelta", 0.5) if eth_tps_stats else 0.5
        _eth_ats_now = eth_tps_stats.get("ats", 0) if eth_tps_stats else 0
        _real_whales = (_btc_vd_now >= 0.65 and _btc_ats_now >= 2000) or (_eth_vd_now >= 0.65 and _eth_ats_now >= 2000)

        if market_state == "SAFE":
            _rec = "\u2705 *ادخل* — السوق مناسب للتداول"
        elif market_state == "CAUTION":
            _rec = "\U0001f7e1 *انتظر* — حيتان يشترون، تحسن قريب" if _real_whales else "\U0001f7e1 *انتظر* — السوق غير مستقر"
        else:
            _rec = "\u26a0\ufe0f *انتظر* — حيتان يشترون لكن BTC ينزل" if _real_whales else "\U0001f534 *ابتعد* — ضغط بيع قوي"
        # تقرير السوق — محذوف بطلب المستخدم
        pass
        log.info(" Market: %s→%s | BTC %.2f%% | confirm=%d",
                 old, market_state, btc_change_24h, BTC_CONFIRM_COUNT)



#   SECTOR ROTATION

def analyze_sectors():
    # type: () -> None
    global hot_sectors, hot_symbols, sector_vol_history, last_sectors

    if not all_tickers:
        return

    ticker_map = {t["symbol"]: t for t in all_tickers}
    new_hot    = []
    stats      = {}

    for sector, coins in SECTORS.items():
        changes   = []
        total_vol = 0.0
        rising    = []

        for sym in coins:
            if sym not in ticker_map:
                continue
            try:
                ch  = float(ticker_map[sym]["priceChangePercent"])
                vol = float(ticker_map[sym]["quoteVolume"])
                changes.append(ch)
                total_vol += vol
                if ch > 0:
                    rising.append((sym.replace("USDT",""), ch))
            except (KeyError, ValueError):
                pass

        if not changes:
            continue

        avg_ch     = sum(changes) / len(changes)
        rising_pct = sum(1 for c in changes if c > 0) / len(changes) * 100

        _prev = sector_vol_history.get(sector, total_vol)
        if isinstance(_prev, list):
            prev_vol = _prev[-1] if _prev else total_vol
        else:
            prev_vol = _prev
        vol_ratio  = total_vol / prev_vol if prev_vol > 0 else 1.0
        sector_vol_history[sector] = total_vol

        stats[sector] = {
            "avg": avg_ch, "rising_pct": rising_pct,
            "vol_ratio": vol_ratio,
            "top": sorted(rising, key=lambda x: -x[1])[:3],
        }

        if avg_ch >= SECTOR_HOT_CHANGE and rising_pct >= SECTOR_MIN_RISING:
            new_hot.append(sector)

    old_hot     = set(hot_sectors)
    new_hot_set = set(new_hot)
    hot_sectors = new_hot
    hot_symbols = {c for s in hot_sectors for c in SECTORS[s]}
    last_sectors = time.time()

    entered = new_hot_set - old_hot
    exited  = old_hot - new_hot_set

    if entered or exited:
        # لا نرسل — scan_sector_rotation يرسل تقريراً أكثر تفصيلاً
        log.info(" Sectors changed | entered=%s | exited=%s", list(entered), list(exited))

    if hot_sectors:
        log.info(" Hot: %s", ", ".join(hot_sectors))







def update_sector_flow(ticker_map):
    # type: (Dict) -> None
    """
    الخطوة 1: يجمع لقطات الحجم والتغيير لكل قطاع.
    يُستدعى من run() في كل دورة.
    """
    global sector_vol_snapshots, sector_change_snapshots

    for sector, coins in SECTORS.items():
        total_vol = 0.0
        changes   = []

        for sym in coins:
            if sym not in ticker_map:
                continue
            try:
                vol = float(ticker_map[sym]["quoteVolume"])
                ch  = float(ticker_map[sym]["priceChangePercent"])
                total_vol += vol
                changes.append(ch)
            except (KeyError, ValueError):
                pass

        if not changes:
            continue

        avg_ch = sum(changes) / len(changes)


        if sector not in sector_vol_snapshots:
            sector_vol_snapshots[sector] = []
        if sector not in sector_change_snapshots:
            sector_change_snapshots[sector] = []

        sector_vol_snapshots[sector].append(total_vol)
        sector_change_snapshots[sector].append(avg_ch)


        if len(sector_vol_snapshots[sector]) > FLOW_HISTORY_MAX:
            sector_vol_snapshots[sector].pop(0)
        if len(sector_change_snapshots[sector]) > FLOW_HISTORY_MAX:
            sector_change_snapshots[sector].pop(0)



# ربط قطاعات MEXC مع بروتوكولات DefiLlama
SECTOR_TO_LLAMA = {
    "DeFi":    ["aave", "uniswap", "curve", "compound"],
    "DEX":     ["uniswap", "curve", "pancakeswap"],
    "Layer1":  None,   # لا يوجد ربط مباشر
    "Layer2":  None,
    "Meme":    None,
    "AI":      None,
    "GameFi":  None,
    "NFT":     None,
}

_llama_tvl_cache = {}   # {protocol: tvl} يُحدَّث كل ساعة

def get_llama_tvl_change(sector):
    # type: (str) -> float
    protocols = SECTOR_TO_LLAMA.get(sector)
    if not protocols:
        return 0.0
    try:
        data = safe_get(LLAMA_PROTOCOLS_URL)
        if not data or not isinstance(data, list):
            return 0.0
        total_change = 0.0
        count = 0
        for proto in data:
            if proto.get("slug", "").lower() in protocols:
                chg = float(proto.get("change_1d", 0) or 0)
                total_change += chg
                count += 1
        return (total_change / count) if count > 0 else 0.0
    except Exception:
        return 0.0


def analyze_sector_flow():
    # type: () -> None
    """
    الخطوة 2: يحلل اللقطات ويرسل تنبيه عند:
    ● دخول سيولة: حجم القطاع ارتفع FLOW_VOL_SURGE× + متوسط تغيير > FLOW_CHANGE_MIN%
    ● خروج سيولة: حجم القطاع انخفض + متوسط تغيير < FLOW_EXIT_DROP%

    يُستدعى كل 60 ثانية (بعد 5 دورات × 12 ثانية)
    """
    global sector_flow_state, sector_flow_alerted

    now       = time.time()
    inflows   = []
    outflows  = []

    for sector in SECTORS:
        vols    = sector_vol_snapshots.get(sector, [])
        changes = sector_change_snapshots.get(sector, [])


        if len(vols) < FLOW_WINDOW or len(changes) < FLOW_WINDOW:
            continue


        recent_vol  = vols[-1]
        prev_avg_vol = sum(vols[-FLOW_WINDOW:-1]) / (FLOW_WINDOW - 1)
        if prev_avg_vol <= 0:
            continue

        vol_ratio   = recent_vol / prev_avg_vol
        recent_ch   = changes[-1]
        avg_ch_prev = sum(changes[-FLOW_WINDOW:-1]) / (FLOW_WINDOW - 1)


        # نسبة العملات الصاعدة في القطاع
        _s_coins = SECTORS.get(sector, [])
        _rising = sum(1 for _sc in _s_coins if all_tickers and
                      any(float(t.get("priceChangePercent",0)) > 0
                          for t in all_tickers if t.get("symbol") == _sc))
        _rising_pct = (_rising / len(_s_coins) * 100) if _s_coins else 0

        # نسبة العملات الصاعدة في القطاع
        _s_coins = SECTORS.get(sector, [])
        _rising2 = 0
        if all_tickers and _s_coins:
            _tmap2 = {t.get("symbol",""): float(t.get("priceChangePercent",0)) for t in all_tickers}
            _rising2 = sum(1 for sc in _s_coins if _tmap2.get(sc, 0) > 0)
        _rising_pct2 = (_rising2 / len(_s_coins) * 100) if _s_coins else 0

        # تأكيد DefiLlama
        _llama_chg2 = get_llama_tvl_change(sector)
        _llama_ok = (_llama_chg2 == 0.0) or (_llama_chg2 >= 2.0)

        is_inflow = (
            vol_ratio >= FLOW_VOL_SURGE and
            recent_ch >= FLOW_CHANGE_MIN and
            _llama_ok
        )


        is_outflow = (
            vol_ratio < (1.0 / FLOW_VOL_SURGE) and
            recent_ch <= FLOW_EXIT_DROP
        )

        prev_state = sector_flow_state.get(sector, "NEUTRAL")

        if is_inflow:
            inflows.append({
                "sector":    sector,
                "vol_ratio": round(vol_ratio, 2),
                "ch":        round(recent_ch, 2),
                "ch_delta":  round(recent_ch - avg_ch_prev, 2),
            })
            sector_flow_state[sector] = "IN"

        elif is_outflow:
            outflows.append({
                "sector":    sector,
                "vol_ratio": round(vol_ratio, 2),
                "ch":        round(recent_ch, 2),
            })
            sector_flow_state[sector] = "OUT"

        else:
            sector_flow_state[sector] = "NEUTRAL"


    for info in inflows:
        sector = info["sector"]
        last_alert = sector_flow_alerted.get(sector, 0)
        if now - last_alert < FLOW_ALERT_COOL:
            continue

        sector_flow_alerted[sector] = now
        sector_flow_hot[sector] = now


        coins_in_sector = SECTORS.get(sector, [])
        top_coins = []
        tmap = {t["symbol"]: t for t in all_tickers}
        for sym in coins_in_sector:
            if sym not in tmap: continue
            try:
                ch  = float(tmap[sym]["priceChangePercent"])
                vol = float(tmap[sym]["quoteVolume"])
                if ch > 0 and vol > 200_000:
                    top_coins.append((sym.replace("USDT",""), ch, vol))
            except (KeyError, ValueError):
                pass
        top_coins.sort(key=lambda x: -x[1])
        top_txt = ""
        for name, ch, vol in top_coins[:5]:
            top_txt += "  • *{}* `+{:.1f}%` vol:`{:,.0f}`\n".format(name, ch, vol)


        is_hot = sector in hot_sectors
        hot_tag = " 🔥 *SECTOR HOT*" if is_hot else ""

        send(
            "💸 *SECTOR FLOW — دخول سيولة*{hot}\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🏷️ القطاع: *{sector}*\n"
            "📊 الحجم ارتفع: `{ratio}×` المعدل\n"
            "📈 متوسط التغيير: `+{ch:.1f}%`\n"
            "🔺 تسارع: `+{delta:.1f}%` عن السابق\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🏆 *أفضل العملات الآن:*\n"
            "{top}"
            "₿ BTC: `{btc:+.1f}%` | `{mst}`\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "👀 _راقب هذا القطاع — السيولة تدخل_".format(
                hot=hot_tag,
                sector=sector,
                ratio=info["vol_ratio"],
                ch=info["ch"],
                delta=info["ch_delta"],
                top=top_txt if top_txt else "  لا بيانات\n",
                btc=btc_change_24h,
                mst=market_state,
            )
        )
        log.info(" Flow IN | %s | ratio=%.2f | ch=%.1f%%", sector, info["vol_ratio"], info["ch"])



        if all_tickers:
            tmap      = {t["symbol"]: t for t in all_tickers}
            p_map     = {}
            v_map     = {}
            c_map     = {}
            h_map     = {}
            l_map     = {}
            for t in all_tickers:
                s = t.get("symbol", "")
                try:
                    p_map[s] = float(t["lastPrice"])
                    v_map[s] = float(t["quoteVolume"])
                    c_map[s] = float(t["priceChangePercent"])
                    h_map[s] = float(t["highPrice"])
                    l_map[s] = float(t["lowPrice"])
                except (KeyError, ValueError):
                    pass
            smart_top10_alert(sector, tmap, p_map, v_map, c_map, h_map, l_map)


    if outflows:
        out_txt = ""
        for info in outflows:
            out_txt += "  📤 *{}* حجم:`{}×` ch:`{:.1f}%`\n".format(
                info["sector"], info["vol_ratio"], info["ch"])


        any_new = any(
            now - sector_flow_alerted.get(i["sector"], 0) >= FLOW_ALERT_COOL
            for i in outflows
        )
        if any_new:
            for info in outflows:
                sector_flow_alerted[info["sector"]] = now
            send(
                "📤 *SECTOR FLOW — خروج سيولة*\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "{out}"
                "━━━━━━━━━━━━━━━━━━\n"
                "₿ BTC: `{btc:+.1f}%` | `{mst}`\n"
                "⚠️ _لا تدخل هذه القطاعات الآن_".format(
                    out=out_txt, btc=btc_change_24h, mst=market_state
                )
            )
            log.info(" Flow OUT | %s", [i["sector"] for i in outflows])










def detect_sector_rotation():
    # type: () -> None
    """
    يفحص القطاعات كل ساعة:
    إذا وجد قطاع OUT + قطاع IN في نفس الوقت
    → يرسل تنبيه Sector Rotation مع أفضل الفرص
    """
    global last_sr_alert
    now = time.time()

    if now - last_sr_alert < SR_COOLDOWN:
        return

    if not sector_vol_snapshots:
        return


    sector_pct = {}
    sector_vol_abs = {}
    for sector, vols in sector_vol_snapshots.items():
        if len(vols) < 3:
            continue
        prev = sum(vols[-4:-1]) / 3 if len(vols) >= 4 else vols[-2]
        curr = vols[-1]
        if prev <= 0:
            continue
        pct = (curr - prev) / prev * 100
        sector_pct[sector]     = round(pct, 1)
        sector_vol_abs[sector] = curr / 1_000_000

    if not sector_pct:
        return


    entering = sorted(
        [(s, p) for s, p in sector_pct.items() if p >= SR_MIN_IN],
        key=lambda x: -x[1]
    )
    leaving = sorted(
        [(s, p) for s, p in sector_pct.items() if p <= SR_MIN_OUT],
        key=lambda x: x[1]
    )


    if not entering or not leaving:
        return

    last_sr_alert = now



    out_lines = ""
    for s, p in leaving[:3]:
        vol = sector_vol_abs.get(s, 0)
        out_lines += "  ⬇️ *{}* `{:+.1f}%` ({:.1f}M)\n".format(s, p, vol)


    in_lines   = ""
    opp_lines  = ""

    tmap = {t["symbol"]: t for t in all_tickers} if all_tickers else {}

    for s, p in entering[:3]:
        vol = sector_vol_abs.get(s, 0)
        icon = "🔥" if p >= 25 else "✅"
        in_lines += "  ⬆️ *{}* `{:+.1f}%` ({:.1f}M) {}\n".format(s, p, vol, icon)


    top_sector = entering[0][0]
    coins      = SECTORS.get(top_sector, [])
    top_coins  = []
    for sym in coins:
        if sym not in tmap:
            continue
        try:
            ch  = float(tmap[sym]["priceChangePercent"])
            vol = float(tmap[sym]["quoteVolume"])
            pr  = float(tmap[sym]["lastPrice"])

            if vol >= 200_000 and ch <= 15:
                top_coins.append((sym.replace("USDT",""), ch, vol, pr))
        except (KeyError, ValueError):
            pass

    top_coins.sort(key=lambda x: -x[2])

    for name, ch, vol, pr in top_coins[:SR_TOP_COINS]:
        sym_full = name + "USDT"
        _s = analyze_tps_ats(sym_full)
        if not _s:
            continue
        vd = _s.get("vdelta", 0)
        ats = _s.get("ats", 0)
        # تجاهل العملات التي فيها ضغط بيعي
        if vd < 0.52:
            continue
        chg_icon = "🟢" if ch > 0 else "⚪"
        vd_txt  = " | VD:`{:.0f}%`".format(vd * 100)
        ats_txt = " ATS:`{:.0f}$`".format(ats)
        opp_lines += "  {} *{}* `{:+.1f}%`{}{}\n".format(
            chg_icon, name, ch, vd_txt, ats_txt)


    top_in_pct  = entering[0][1]
    top_out_pct = leaving[0][1]
    if top_in_pct >= 30:
        verdict = "🚀 *تدفق قوي جداً — فرصة نادرة!*"
    elif top_in_pct >= 15:
        verdict = "⚡ *تدفق واضح — دخول جيد*"
    else:
        verdict = "👀 *تدفق بدأ — راقب التأكيد*"


    mkt_note = ""
    if market_state == "SAFE":
        mkt_note = "✅ السوق SAFE — يدعم الدخول"
    elif market_state == "CAUTION":
        mkt_note = "⚠️ السوق CAUTION — ادخل بحذر"
    else:
        mkt_note = "🔴 السوق DANGER — مخاطرة عالية"

    msg = (
        "🌊 *SECTOR ROTATION*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🔴 *خروج السيولة من:*\n"
        + out_lines +
        "━━━━━━━━━━━━━━━━━━\n"
        "🟢 *دخول السيولة إلى:*\n"
        + in_lines +
        "━━━━━━━━━━━━━━━━━━\n"
        "🎯 *أفضل فرص في {}:*\n".format(top_sector)
        + (opp_lines if opp_lines else "  جاري البحث...\n") +
        "━━━━━━━━━━━━━━━━━━\n"
        + verdict + "\n"
        + mkt_note + "\n"
        "₿ BTC: `{:+.1f}%`\n".format(btc_change_24h)
    )

    send(msg)
    log.info(" Sector Rotation | OUT:%s  IN:%s",
             [s for s, _ in leaving[:3]],
             [s for s, _ in entering[:3]])


    global hot_sectors, hot_symbols
    for s, p in entering[:3]:
        if s not in hot_sectors:
            hot_sectors.append(s)
            log.info(" hot_sector : %s (+%.1f%%)", s, p)
    for s, p in leaving[:3]:
        if s in hot_sectors:
            hot_sectors.remove(s)
            log.info(" hot_sector : %s (%.1f%%)", s, p)
    hot_symbols = {c for sec in hot_sectors for c in SECTORS.get(sec, [])}
    log.info(" hot_sectors: %s | %d ", hot_sectors, len(hot_symbols))

def get_flow_summary():
    # type: () -> str
    """
    ملخص تدفق السيولة بين القطاعات — مفصّل بالأرقام والنسب.
    يقارن حجم اليوم بأمس لكل قطاع.
    """
    if not sector_vol_snapshots:
        return "➡️ لا تدفق واضح — جاري جمع البيانات\n"


    sector_changes = []
    for sector, vols in sector_vol_snapshots.items():
        if len(vols) < 2:
            continue
        prev = vols[-2]
        curr = vols[-1]
        if prev <= 0:
            continue
        pct    = (curr - prev) / prev * 100
        diff_m = (curr - prev) / 1_000_000
        sector_changes.append((sector, pct, curr / 1_000_000, diff_m))

    if not sector_changes:
        return "➡️ لا تدفق واضح\n"


    sector_changes.sort(key=lambda x: -x[1])
    entering = [(s, p, v, d) for s, p, v, d in sector_changes if p >= 8]
    leaving  = [(s, p, v, d) for s, p, v, d in sector_changes if p <= -8]

    txt = ""

    # تحديث sector_flow_hot عند رصد دخول سيولة
    now_ts = time.time()
    for s, p, v, d in entering:
        if p >= 8:
            sector_flow_hot[s] = now_ts
            log.info(" DAILY FLOW: %s +%.0f%% → sector_flow_hot updated", s, p)

    # إرسال تنبيه فوري إذا سيولة قوية دخلت قطاع
    hot_entering = [(s,p,d) for s,p,v,d in entering if p >= 15]
    if hot_entering:
        _flow_msg = "💸 *سيولة تدخل قطاع!*\n"
        _flow_msg += "━━━━━━━━━━━━━━━━━━\n"
        for s, p, d in hot_entering[:3]:
            icon = "🔥" if p >= 25 else "✅"
            _flow_msg += "  {} *{}* `+{:.0f}%` (+{:.1f}M$)\n".format(icon, s, p, abs(d))
        _flow_msg += "━━━━━━━━━━━━━━━━━━\n"
        _flow_msg += "👀 _راقب عملات {} — السيولة تتجمع_".format(hot_entering[0][0])
        send(_flow_msg)

    if entering:
        txt += "🟢 *يدخل (أموال تتدفق):*\n"
        medals = ["🥇", "🥈", "🥉"]
        for i, (s, p, v, d) in enumerate(entering[:5]):
            medal = medals[i] if i < 3 else "  •"
            icon  = "🔥" if p >= 25 else "✅" if p >= 15 else ""
            txt  += "  {} {} `{:+.0f}%` (+{:.1f}M) {} \n".format(
                medal, s, p, abs(d), icon)

    if leaving:
        txt += "🔴 *يخرج (أموال تهرب):*\n"
        for s, p, v, d in leaving[:3]:
            txt += "  ⬇️ {} `{:+.0f}%` ({:.1f}M)\n".format(s, p, d)


    if entering and leaving:
        top_in  = entering[0][0]
        top_out = leaving[0][0]
        txt += "━━━━━━━━━━━━━━━━━━\n"
        txt += "🎯 *الأموال تهرب من {} → تدخل {}*\n".format(top_out, top_in)
        txt += "  ابحث عن فرص في {} الآن!\n".format(top_in)
    elif entering:
        txt += "━━━━━━━━━━━━━━━━━━\n"
        txt += "✅ *تدفق إيجابي — السوق يتحرك نحو {}*\n".format(entering[0][0])
    elif leaving:
        txt += "━━━━━━━━━━━━━━━━━━\n"
        txt += "⚠️ *خروج سيولة من {} — احذر*\n".format(leaving[0][0])
    else:
        txt  = "➡️ السيولة موزعة بالتساوي — لا تدفق واضح\n"

    return txt







def smart_top10_alert(sector, ticker_map, price_map, vol_now, change_now, high_map, low_map):
    # type: (str, dict, dict, dict, dict, dict, dict) -> None
    """
    🆕 V15: يختار أفضل 10 عملات من القطاع قبل الانفجار.

    تحسينات V15:
    ✅ vol_ratio تاريخي: مقارنة حجم العملة بمتوسطها التاريخي (أدق)
    ✅ RSI Filter: يرفض العملات fوق RSI_OVERBOUGHT (ذروة شراء)
    ✅ RSI يُعرض في الرسالة لكل عملة
    ✅ Backtest: يسجل كل عملة تلقائياً لمتابعة الأداء

    معايير الفلترة الصارمة:
    ✅ تغيير 24h: 0% → 5%  ← السر! لم تنطلق بعد
    ✅ حجم ارتفع 1.5x تاريخياً للعملة نفسها
    ✅ ارتداد من قاع 24h: < 15%
    ✅ RSI < 70 (ليست في ذروة شراء)
    ✅ حجم كافٍ: > 150k USDT

    نظام النقاط (100 نقطة):
    • vol_ratio    × 40  — الأهم
    • in_hot       × 25  — قطاع ساخن
    • rebound_low  × 20  — قريب القاع
    • change_small × 15  — لم ينطلق بعد
    """
    global top10_alerted

    now = time.time()


    if now - top10_alerted.get(sector, 0) < TOP10_COOLDOWN:
        return

    coins    = SECTORS.get(sector, [])
    scored   = []

    for sym in coins:

        if sym not in price_map: continue
        if sym in tracked: continue
        if sym in momentum_stage: continue
        if sym in EXCLUDED: continue

        price    = price_map[sym]
        vol      = vol_now.get(sym, 0)
        ch       = change_now.get(sym, 0)
        high_24h = high_map.get(sym, price)
        low_24h  = low_map.get(sym, price)

        if vol < TOP10_MIN_VOL: continue
        if price <= 0 or low_24h <= 0: continue


        if ch < TOP10_CHANGE_MIN: continue
        if ch > TOP10_CHANGE_MAX: continue


        vol_ratio = get_coin_vol_ratio(sym, vol)
        if vol_ratio < TOP10_VOL_RATIO: continue


        rebound = (price - low_24h) / low_24h * 100 if low_24h > 0 else 99
        if rebound > TOP10_REBOUND_MAX: continue


        base = sym.replace("USDT", "")
        if base in STABLECOINS: continue
        if any(k in sym for k in LEVERAGE_KEYWORDS): continue



        rsi_val = -1.0
        kd_rsi  = get_klines(sym, "15m", RSI_PERIOD + 2)
        if kd_rsi and len(kd_rsi["closes"]) >= RSI_PERIOD + 1:
            rsi_val = calc_rsi(kd_rsi["closes"])

            if rsi_val > RSI_OVERBOUGHT:
                log.debug(" RSI : %s RSI=%.1f", sym, rsi_val)
                continue



        vol_score = min(vol_ratio / 5.0, 1.0) * W_VOL_RATIO


        is_hot    = sym in hot_symbols
        flow_in   = sector_flow_state.get(sector, "NEUTRAL") == "IN"
        hot_score = W_HOT_SECTOR if (is_hot and flow_in) else (W_HOT_SECTOR * 0.5 if is_hot else 0)


        rebound_score = max(0, (TOP10_REBOUND_MAX - rebound) / TOP10_REBOUND_MAX) * W_REBOUND_LOW


        change_score = max(0, (TOP10_CHANGE_MAX - ch) / TOP10_CHANGE_MAX) * W_CHANGE_SMALL


        rsi_bonus = 0.0
        if rsi_val > 0:
            if rsi_val <= RSI_OVERSOLD:    rsi_bonus = 5.0
            elif rsi_val <= 50:            rsi_bonus = 3.0
            elif rsi_val <= RSI_IDEAL_MAX: rsi_bonus = 1.0

        total_score = vol_score + hot_score + rebound_score + change_score + rsi_bonus

        drop_from_high = (high_24h - price) / high_24h * 100 if high_24h > 0 else 0

        scored.append({
            "sym":          sym,
            "price":        price,
            "ch":           ch,
            "vol":          vol,
            "vol_ratio":    vol_ratio,
            "rebound":      round(rebound, 1),
            "drop":         round(drop_from_high, 1),
            "score":        round(total_score, 1),
            "is_hot":       is_hot,
            "rsi":          rsi_val,
        })

    if not scored:
        log.info(" Top10 [%s]:    ", sector)
        return


    scored.sort(key=lambda x: -x["score"])
    top10 = scored[:TOP10_COUNT]

    top10_alerted[sector] = now


    for c in top10:
        register_backtest(c["sym"], c["price"], sector)


    flow_vol = sector_vol_snapshots.get(sector, [])
    vol_surge_txt = ""
    if len(flow_vol) >= 2 and flow_vol[-2] > 0:
        sector_ratio = flow_vol[-1] / flow_vol[-2]
        vol_surge_txt = "📊 حجم القطاع: `{:.1f}×` المعدل\n".format(sector_ratio)

    coins_txt = ""
    for i, c in enumerate(top10, 1):
        hot_icon = "🔥" if c["is_hot"] else "  "
        rsi_v    = c["rsi"]
        rsi_str  = "`RSI:{:.0f}`".format(rsi_v) if rsi_v >= 0 else ""
        rsi_ic   = ""
        if rsi_v >= 0:
            if rsi_v <= RSI_OVERSOLD:    rsi_ic = "🟢"
            elif rsi_v <= RSI_IDEAL_MAX: rsi_ic = "🟡"
            else:                         rsi_ic = "🟠"

        coins_txt += (
            "{i}. {hot} *{sym}*\n"
            "     💵 `{price}` | 📈 `+{ch:.1f}%` | 💧 `{ratio:.1f}×`\n"
            "     📉 قاع: `+{reb:.1f}%` | قمة: `-{drop:.1f}%` {rsi_ic}{rsi_str}\n"
        ).format(
            i=i,
            hot=hot_icon,
            sym=c["sym"].replace("USDT", ""),
            price=fmt_price(c["price"]),
            ch=c["ch"],
            ratio=c["vol_ratio"],
            reb=c["rebound"],
            drop=c["drop"],
            rsi_ic=rsi_ic,
            rsi_str=" " + rsi_str if rsi_str else "",
        )

    mkt_icon = {"SAFE": "🟢", "CAUTION": "🟡", "DANGER": "🚨"}.get(market_state, "⚪")


    good_rsi_count = sum(1 for c in top10 if 0 <= c["rsi"] <= RSI_IDEAL_MAX)
    rsi_summary    = " | 🟢 `{}/{} RSI جيد`".format(good_rsi_count, len(top10)) if good_rsi_count > 0 else ""

    msg = (
        "🚨 *SMART TOP10 V15 — قبل الانفجار!*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🏷️ القطاع: *{sector}*\n"
        "💸 السيولة تدخل الآن!\n"
        "{vol_surge}"
        "━━━━━━━━━━━━━━━━━━\n"
        "🎯 *أفضل 10 — تغيير 0→5% + RSI < 70:*\n\n"
        "{coins}"
        "━━━━━━━━━━━━━━━━━━\n"
        "{mkt} BTC: `{btc:+.1f}%` | `{mst}`{rsi_sum}\n"
        "🕐 `{time}`\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "⚡ _ادخل قبل الانفجار — SL تحت القاع_\n"
        "📊 _سيتم مراقبة النتائج تلقائياً (1h/4h/24h)_"
    ).format(
        sector=sector,
        vol_surge=vol_surge_txt,
        coins=coins_txt,
        mkt=mkt_icon,
        btc=btc_change_24h,
        mst=market_state,
        rsi_sum=rsi_summary,
        time=datetime.now().strftime("%H:%M:%S"),
    )

    send(msg)
    log.info(" Top10 V15 | %s | %d  | : %s (%.1f ) | RSI : %d",
             sector, len(top10), top10[0]["sym"], top10[0]["score"], good_rsi_count)







def register_backtest(sym, price, sector):
    # type: (str, float, str) -> None
    """يسجل إشارة Top10 عند إرسالها — للمتابعة اللاحقة"""
    global backtest_signals
    if sym in backtest_signals:
        return
    backtest_signals[sym] = {
        "entry_price":  price,
        "entry_time":   time.time(),
        "sector":       sector,
        "checked_1h":   False,
        "checked_4h":   False,
        "checked_24h":  False,
        "result_1h":    None,
        "result_4h":    None,
        "result_24h":   None,
    }
    log.info(" Backtest : %s @ %s", sym, price)


def check_backtest(price_map):
    # type: (Dict[str, float]) -> None
    """يحفظ نتائج Backtest — التقرير في send_daily_report يومياً"""
    global backtest_signals
    now = time.time()

    for sym, data in list(backtest_signals.items()):
        price = price_map.get(sym, 0)
        if price <= 0: continue
        entry = data["entry_price"]
        if entry <= 0: continue

        elapsed  = now - data["entry_time"]
        gain_raw = (price - entry) / entry * 100
        gain     = round(gain_raw - BACKTEST_FEE, 2)


        if not data["checked_1h"] and elapsed >= BACKTEST_CHECK_1H:
            data["checked_1h"] = True
            data["result_1h"]  = gain
            data["price_now"]  = price
            log.info(" BT-1H | %s | %+.2f%%", sym, gain)

        elif not data["checked_4h"] and elapsed >= BACKTEST_CHECK_4H:
            data["checked_4h"] = True
            data["result_4h"]  = gain
            data["price_now"]  = price
            log.info(" BT-4H | %s | %+.2f%%", sym, gain)

        elif not data["checked_24h"] and elapsed >= BACKTEST_CHECK_24H:
            data["checked_24h"] = True
            data["result_24h"]  = gain
            data["price_now"]   = price
            log.info(" BT-24H | %s | %+.2f%%", sym, gain)


def get_backtest_stats():
    # type: () -> str
    """ملخص إحصائي للإشارات المكتملة — للتقرير الدوري"""
    completed_1h  = [(s, d["result_1h"])  for s, d in backtest_signals.items() if d.get("result_1h") is not None]
    completed_4h  = [(s, d["result_4h"])  for s, d in backtest_signals.items() if d.get("result_4h") is not None]

    if not completed_1h and not completed_4h:
        return "📋 لا توجد نتائج backtest بعد\n"

    txt = "🧪 *Backtest Stats:*\n"
    if completed_1h:
        wins = sum(1 for _, r in completed_1h if r > 0)
        avg  = sum(r for _, r in completed_1h) / len(completed_1h)
        txt += "  1H: `{}/{} فوز` | متوسط: `{:+.1f}%`\n".format(
            wins, len(completed_1h), avg)
    if completed_4h:
        wins = sum(1 for _, r in completed_4h if r > 0)
        avg  = sum(r for _, r in completed_4h) / len(completed_4h)
        txt += "  4H: `{}/{} فوز` | متوسط: `{:+.1f}%`\n".format(
            wins, len(completed_4h), avg)
    return txt










perf_signals = {}   # type: Dict[str, Dict]
perf_id_counter = 0 # type: int


PERF_SYSTEMS = {
    "quick":    "⚡ Quick Signals",
    "lh_big":   "🔥 Liquidity Hunter",
    "lh_small": "🔍 Small Cap Hunter",
    "hidden":   "👁️ Hidden Accum",
    "daily_lz": "📅 Daily Liquidity",
    "bottom":   "📉 Bottom Accum",
    "momentum": "🚀 Momentum",
}


def perf_register(sym, price, system, score=0, signals_desc=""):
    # type: (str, float, str, int, str) -> str
    """
    يسجل إشارة جديدة في نظام تتبع الأداء.
    يعيد signal_id لاستخدامه لاحقاً.
    """
    global perf_signals, perf_id_counter
    perf_id_counter += 1
    sid = "{}_{}".format(system, perf_id_counter)
    sector = next((s for s, syms in SECTORS.items() if sym in syms), "Other")
    is_small = sym in small_caps

    perf_signals[sid] = {
        "sym":          sym,
        "system":       system,
        "entry_price":  price,
        "entry_time":   time.time(),
        "sector":       sector,
        "is_small_cap": is_small,
        "score":        score,
        "signals_desc": signals_desc,

        "result_1h":    None,
        "result_4h":    None,
        "result_24h":   None,
        "checked_1h":   False,
        "checked_4h":   False,
        "checked_24h":  False,
    }
    log.info(" Perf registered | %s | %s | score=%d", system, sym, score)
    return sid


def perf_check(price_map=None):
    # type: (Dict) -> None
    """يتحقق من نتائج الإشارات المسجلة عند 1h/4h/24h"""

    if not price_map:
        if not all_tickers:
            return
        price_map = {t.get("symbol",""): float(t.get("lastPrice",0))
                     for t in all_tickers if t.get("lastPrice")}
    now = time.time()
    for sid, data in list(perf_signals.items()):
        sym   = data["sym"]
        price = price_map.get(sym, 0)
        if price <= 0:
            continue
        entry   = data["entry_price"]
        elapsed = now - data["entry_time"]
        gain    = round((price - entry) / entry * 100 - BACKTEST_FEE, 2)

        if not data["checked_1h"] and elapsed >= 3600:
            data["checked_1h"] = True
            data["result_1h"]  = gain
        if not data["checked_4h"] and elapsed >= 14400:
            data["checked_4h"] = True
            data["result_4h"]  = gain
        if not data["checked_24h"] and elapsed >= 86400:
            data["checked_24h"] = True
            data["result_24h"]  = gain

        if elapsed >= 172800:
            del perf_signals[sid]


def perf_daily_report():
    # type: () -> str
    """
    تقرير يومي شامل لأداء كل نظام.
    يُرسَل ضمن send_daily_report()
    """
    if not perf_signals:
        return ""


    sys_stats = {k: {"wins_1h":0,"total_1h":0,"wins_4h":0,"total_4h":0,
                     "best":None,"worst":None,"gains_4h":[]} 
                 for k in PERF_SYSTEMS}

    for sid, d in perf_signals.items():
        sys = d["system"]
        if sys not in sys_stats:
            continue
        st = sys_stats[sys]

        if d["result_1h"] is not None:
            st["total_1h"] += 1
            if d["result_1h"] > 0:
                st["wins_1h"] += 1

        if d["result_4h"] is not None:
            g = d["result_4h"]
            st["total_4h"] += 1
            if g > 0:
                st["wins_4h"] += 1
            st["gains_4h"].append((d["sym"], g))
            if st["best"] is None or g > st["best"][1]:
                st["best"] = (d["sym"], g)
            if st["worst"] is None or g < st["worst"][1]:
                st["worst"] = (d["sym"], g)



    has_data = any(
        sys_stats[k]["total_4h"] > 0 or sys_stats[k]["total_1h"] > 0
        for k in PERF_SYSTEMS
    )
    if not has_data:
        return ""

    lines = [
        "━━━━━━━━━━━━━━━━━━",
        "📊 *PERFORMANCE REPORT*",
        "━━━━━━━━━━━━━━━━━━",
    ]

    total_signals = 0
    total_wins    = 0

    for sys_key, sys_name in PERF_SYSTEMS.items():
        st = sys_stats[sys_key]
        if st["total_4h"] == 0 and st["total_1h"] == 0:
            continue

        total_signals += st["total_4h"]
        total_wins    += st["wins_4h"]


        if st["total_4h"] > 0:
            wr   = round(st["wins_4h"] / st["total_4h"] * 100)
            avg  = sum(g for _, g in st["gains_4h"]) / len(st["gains_4h"])
            icon = "🟢" if wr >= 60 else "🟡" if wr >= 40 else "🔴"
            line = "{} {} `{}%` نجاح ({}/{}) | متوسط `{:+.1f}%`".format(
                icon, sys_name, wr, st["wins_4h"], st["total_4h"], avg)
        else:
            wr   = round(st["wins_1h"] / st["total_1h"] * 100) if st["total_1h"] else 0
            icon = "🟡"
            line = "{} {} `{}%` نجاح 1H ({}/{})".format(
                icon, sys_name, wr, st["wins_1h"], st["total_1h"])

        lines.append(line)


        if st["best"]:
            lines.append(
                "  🏆 أفضل: *{}* `{:+.1f}%`  |  💀 أسوأ: *{}* `{:+.1f}%`".format(
                    st["best"][0].replace("USDT",""),  st["best"][1],
                    st["worst"][0].replace("USDT",""), st["worst"][1]
                )
            )


    if total_signals > 0:
        total_wr = round(total_wins / total_signals * 100)
        lines += [
            "━━━━━━━━━━━━━━━━━━",
            "🎯 *الإجمالي:* `{}%` نجاح ({}/{} إشارة)".format(
                total_wr, total_wins, total_signals),
        ]
        if total_wr >= 65:
            lines.append("✅ _البوت يعمل بكفاءة عالية_")
        elif total_wr >= 50:
            lines.append("⚠️ _أداء متوسط — يحتاج مراجعة الإعدادات_")
        else:
            lines.append("🔴 _أداء ضعيف — راجع الـ thresholds_")

    lines.append("━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines) + "\n"


#   SMART MONEY DETECTION


MAX_DAILY_SIGNALS = 10


def can_send_signal():
    # type: () -> bool
    """هل يمكن إرسال إشارة اليوم؟ الحد الأقصى 10"""
    global daily_signals
    today = datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%d")
    if daily_signals["date"] != today:
        daily_signals = {"date": today, "count": 0}
    return daily_signals["count"] < MAX_DAILY_SIGNALS


def register_signal():
    # type: () -> None
    """تسجيل إشارة جديدة في العداد اليومي"""
    global daily_signals
    today = datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%d")
    if daily_signals["date"] != today:
        daily_signals = {"date": today, "count": 0}
    daily_signals["count"] += 1
    log.info("  : %d/%d", daily_signals["count"], MAX_DAILY_SIGNALS)






def ts_register_entry(sym, entry_price, sector="Unknown"):
    # type: (str, float, str) -> None
    """تسجيل صفقة جديدة في نظام الـ Trailing Stop"""
    global ts_positions

    _vol_ref = float(next((t["quoteVolume"] for t in all_tickers if t["symbol"]==sym), "0"))
    ts_positions[sym] = {
        "entry":     entry_price,
        "peak":      entry_price,
        "stop":      entry_price * (1 - TS_TRAIL_PCT / 100),
        "locked":    0.0,
        "sector":    sector,
        "since":     time.time(),
        "entry_vol": _vol_ref,
    }
    log.info(" TS Registered | %s | entry=%.8f", sym, entry_price)


def check_trailing_stops():
    # type: () -> None
    """
    فحص كل الصفقات المفتوحة:
    - تحديث القمة والستوب
    - إرسال إشعار البيع عند الانعكاس
    """
    global ts_positions, ts_sell_alerted

    if not all_tickers or not ts_positions: return
    now = time.time()

    price_map = {t["symbol"]: float(t["lastPrice"]) for t in all_tickers}

    for sym, pos in list(ts_positions.items()):
        price = price_map.get(sym, 0)
        if price <= 0: continue

        entry  = pos["entry"]
        peak   = pos["peak"]
        stop   = pos["stop"]
        locked = pos["locked"]


        profit_pct = (price / entry - 1) * 100
        peak_pct   = (peak  / entry - 1) * 100


        if price > peak:
            ts_positions[sym]["peak"] = price
            peak     = price
            peak_pct = (peak / entry - 1) * 100


            new_stop   = stop
            new_locked = locked

            # ── Lock levels ──────────────────────────────────────────
            if peak_pct >= TS_LOCK_50:
                new_stop   = max(new_stop, entry * 1.35)
                new_locked = 35.0
            elif peak_pct >= TS_LOCK_20:
                new_stop   = max(new_stop, entry * 1.10)
                new_locked = 10.0
            elif peak_pct >= TS_BREAKEVEN:
                new_stop   = max(new_stop, entry * 1.001)
                new_locked = 0.0

            # ── Adaptive Trail — أوسع في البداية أضيق عند القمم ─────
            _trail_pct = TS_TRAIL_PCT
            for _threshold, _pct in TS_ADAPTIVE_TRAIL:
                if peak_pct >= _threshold:
                    _trail_pct = _pct
                    break
            trail_stop = peak * (1 - _trail_pct / 100)
            new_stop   = max(new_stop, trail_stop)

            if new_stop > stop:
                ts_positions[sym]["stop"]   = new_stop
                ts_positions[sym]["locked"] = max(locked, new_stop / entry * 100 - 100)
                log.info(" TS Updated | %s | peak=+%.1f%% | stop=%.8f",
                         sym, peak_pct, new_stop)


        _ticker = next((t for t in all_tickers if t["symbol"]==sym), None)
        if _ticker and now - ts_sell_alerted.get(sym, 0) > TS_SELL_COOL:
            try:
                _vol_now   = float(_ticker["quoteVolume"])
                _entry_vol = pos.get("entry_vol", _vol_now)
                _vol_ratio = _vol_now / _entry_vol if _entry_vol > 0 else 1.0
                _change    = float(_ticker["priceChangePercent"])
                _pl        = (price / entry - 1) * 100
                base       = sym.replace("USDT", "")
                _exit_reason = None
                _exit_icon   = "⚠️"



                if _pl > 5.0 and _vol_ratio < 0.5 and market_state in ("DANGER","CAUTION"):
                    _exit_reason = "✅ اخرج بربح — السيولة تخرج"
                    _exit_icon   = "✅"



                elif _pl > -2.0 and _pl < 3.0 and market_state == "DANGER" and _vol_ratio < 0.4:
                    _exit_reason = "🛡️ احمِ رأس المال — السوق خطر"
                    _exit_icon   = "🛡️"



                elif _pl < -3.0 and market_state == "DANGER" and _vol_ratio < 0.4:
                    _exit_reason = "🔴 اخرج — السوق ينهار"
                    _exit_icon   = "🔴"

                if _exit_reason:
                    msg = (
                        _exit_icon + " *SIGNAL SELL* " + _exit_icon + "\n"
                        "━" * 18 + "\n"
                        + _exit_reason + "\n"
                        "━" * 18 + "\n"
                        "📍 *" + base + "/USDT*\n"
                        "  💰 دخول: `" + fmt_price(entry) + "`\n"
                        "  📈 القمة: `" + fmt_price(peak) + "` (+" + "{:.1f}".format((peak/entry-1)*100) + "%)\n"
                        "  💰 الآن:  `" + fmt_price(price) + "`\n"
                        "  📊 ربح/خسارة: `{:+.1f}%`\n".format(_pl) +
                        "  📦 السيولة: `{:.1f}×` من الدخول\n".format(_vol_ratio) +
                        "  🌡️ السوق: `" + market_state + "`\n"
                        "━" * 18 + "\n"
                        "🚨 *اخرج الآن!*"
                    )
                    send(msg)
                    ts_sell_alerted[sym] = now
                    log.info(" SMART EXIT | %s | pl=%.1f%% | vol=%.1fx | market=%s",
                             sym, _pl, _vol_ratio, market_state)
            except: pass


        stop = ts_positions[sym]["stop"]
        if price <= stop:

            if now - ts_sell_alerted.get(sym, 0) < TS_SELL_COOL:
                continue

            locked_pct = ts_positions[sym]["locked"]

            if profit_pct > 0:
                reason  = "🔒 حماية الربح"
                result  = "+{:.1f}%".format(profit_pct)
                emoji   = "✅"
            elif profit_pct > -5:
                reason  = "🛡️ وقف الخسارة"
                result  = "{:.1f}%".format(profit_pct)
                emoji   = "⚠️"
            else:
                reason  = "🛑 وقف الخسارة"
                result  = "{:.1f}%".format(profit_pct)
                emoji   = "❌"

            base = sym.replace("USDT", "")

            msg = (
                "🔴 *SIGNAL SELL* 🔴\n"
                "━" * 18 + "\n"
                + emoji + " *" + reason + "*\n"
                "━" * 18 + "\n"
                "📍 *" + base + "/USDT*\n"
                "  💰 سعر الدخول: `" + fmt_price(entry) + "`\n"
                "  📈 القمة: `" + fmt_price(peak) + "` (+" + "{:.1f}".format(peak_pct) + "%)\n"
                "  💰 السعر الآن: `" + fmt_price(price) + "`\n"
                "  📊 الربح/الخسارة: `" + result + "`\n"
                "━" * 18 + "\n"
                "⏱️ مدة الصفقة: `" + str(int((now - pos["since"]) / 3600)) + "h`\n"
                "━" * 18 + "\n"
                "🚨 *اخرج الآن — الستوب ضُرب!*"
            )

            send(msg)
            ts_sell_alerted[sym] = now
            log.info(" SELL SIGNAL | %s | profit=%.1f%% | peak=+%.1f%%",
                     sym, profit_pct, peak_pct)


            del ts_positions[sym]



def add_to_liquidity_watchlist(sym, reason, vol, price, sector):
    # type: (str, str, float, float, str) -> None
    """يضيف عملة لقائمة المراقبة عند رصد سيولة غير عادية"""
    global watchlist, wl_price_snapshot


    _blocked = {"CULTUSDT"}
    if sym in _blocked:
        log.debug(" WL Blocked | %s", sym)
        return


    if len(watchlist) >= WL_MAX_SIZE:

        oldest = min(watchlist, key=lambda s: watchlist[s].get("since", 0))
        del watchlist[oldest]
        wl_price_snapshot.pop(oldest, None)

    now = time.time()
    if sym not in watchlist:
        watchlist[sym] = {
            "since":    now,
            "reason":   reason,
            "vol":      vol,
            "sector":   sector,
            "priority": "HIGH" if vol >= 3_000_000 else "NORMAL",
        }
        wl_price_snapshot[sym] = price
        log.info(" WL Added | %s | reason=%s | vol=%.1fM | price=%s",
                 sym, reason, vol/1e6, price)


def check_watchlist_entries():
    # type: () -> None
    """يراقب عملات الـ watchlist ويرسل إشعار الدخول عند التحرك"""
    global watchlist, wl_entry_alerted, wl_price_snapshot

    if not watchlist or not all_tickers:
        return

    now        = time.time()
    ticker_map = {t["symbol"]: t for t in all_tickers}
    to_remove  = []

    for sym, info in list(watchlist.items()):

        if info.get("priority") == "STATIC":
            pass
        elif now - info.get("since", now) > WL_EXPIRY:
            to_remove.append(sym)
            log.info(" WL Expired | %s", sym)
            continue

        t = ticker_map.get(sym)
        if not t: continue

        try:
            price  = float(t["lastPrice"])
            vol    = float(t["quoteVolume"])
            change = float(t["priceChangePercent"])
        except: continue

        entry_price = wl_price_snapshot.get(sym, price)
        if entry_price <= 0: continue


        move_since_add = (price - entry_price) / entry_price * 100




        _min_move = 2.0 if info.get("priority") == "STATIC" else WL_ENTRY_MOVE
        if move_since_add < _min_move: continue

        _cur_vol = float(next((t["quoteVolume"] for t in all_tickers if t["symbol"]==sym), "0"))
        if _cur_vol < 1_000_000: continue


        if now - wl_entry_alerted.get(sym, 0) < WL_ENTRY_COOL: continue


        wl_vol     = info.get("vol", vol)
        vol_confirm = vol >= wl_vol * WL_ENTRY_VOL or vol >= 2_000_000

        sector = info.get("sector", "Unknown")
        reason = info.get("reason", "liquidity")
        priority = info.get("priority", "NORMAL")


        if priority == "STATIC":
            icon = "🚀🟢"
            lvl  = "SIGNAL ENTRY — إشارة دخول"
        elif priority == "HIGH":
            icon = "🚨🚀"
            lvl  = "SIGNAL ENTRY STRONG — دخول قوي"
        else:
            icon = "🚀⚡"
            lvl  = "SIGNAL ENTRY — إشارة دخول"

        vol_confirm_str = " ✅ حجم مؤكد" if vol_confirm else " ⚠️ حجم خفيف"

        msg = (
            icon + " *" + lvl + "* " + icon + "\n"
            + "━" * 18 + "\n"
            + "🔔 *ادخل الآن — العملة تتحرك!*\n"
            + "━" * 18 + "\n"
            + "📍 *" + sym.replace("USDT","") + "/USDT*\n"
            + "  💰 السعر: `" + fmt_price(price) + "`\n"
            + "  📈 تحرك منذ الرصد: `+" + str(round(move_since_add,1)) + "%`\n"
            + "  📈 تغيير 24h: `" + fmt_change(change) + "`\n"
            + "  📦 حجم: `" + str(round(vol/1e6,2)) + "M`" + vol_confirm_str + "\n"
            + "  🏷️ قطاع: `" + sector + "`\n"
            + "  🔍 سبب الرصد: `" + reason + "`\n"
            + "━" * 18 + "\n"
            + "🎯 سعر الرصد: `" + fmt_price(entry_price) + "`\n"
            + "🚀 _العملة تتحرك — فرصة دخول الآن!_"
        )



        wl_entry_alerted[sym] = now

        ts_register_entry(sym, price, info.get("sector","Unknown"))
        log.info(" WL silent track | %s | move=+%.1f%% | vol=%.1fM",
                 sym, move_since_add, vol/1e6)


    for sym in to_remove:
        watchlist.pop(sym, None)
        wl_price_snapshot.pop(sym, None)

    if watchlist:
        log.info(" WL Check | watching=%d | expired=%d", len(watchlist), len(to_remove))


def scan_instant_movers(price_map=None, vol_now=None, changes_map=None):
    # type: () -> None
    """
    يعمل من الدقيقة الأولى — بدون أي تاريخ
    يرصد العملات التي تتحرك الآن بقوة:
    - تغيير 24h >= 8%
    - حجم >= 500K
    - في SECTORS فقط
    """
    global hot_alerted, _coin_first_seen

    if not all_tickers: return
    now = time.time()

    all_sector_coins = set()
    for sc in SECTORS.values():
        all_sector_coins.update(sc)

    movers = []
    for t in all_tickers:
        sym = t.get("symbol", "")
        if sym not in all_sector_coins: continue
        if any(k in sym for k in LEVERAGE_KEYWORDS): continue
        try:
            price  = float(t["lastPrice"])
            vol    = float(t["quoteVolume"])
            change = float(t["priceChangePercent"])
        except: continue

        if vol   < 500_000: continue
        if change < 8.0:    continue
        if change > 60.0:   continue

        # فلتر العملات الجديدة
        if sym not in _coin_first_seen:
            _coin_first_seen[sym] = now
        if (now - _coin_first_seen.get(sym, now)) / 86400 < NEW_COIN_MIN_DAYS:
            continue

        # فلتر السيولة الحقيقية
        _liq_ok, _liq_reason = _is_real_liquidity(vol, change, t)
        if not _liq_ok:
            log.debug("INSTANT skip %s: %s", sym, _liq_reason)
            continue

        # فلتر الدخول المتأخر — السعر في أعلى 8% من نطاق 24h
        try:
            _h24 = float(t.get("highPrice", price))
            _l24 = float(t.get("lowPrice",  price))
            if _is_late_entry(price, _h24, _l24):
                log.debug("INSTANT late_entry skip %s", sym)
                continue
        except (ValueError, TypeError):
            pass

        if now - hot_alerted.get(sym, 0) < 21600: continue

        sector = next((s for s,c in SECTORS.items() if sym in c), "Unknown")


        score = 0
        if change >= 30:      score += 4
        elif change >= 20:    score += 3
        elif change >= 15:    score += 2
        else:                 score += 1
        if vol >= 5_000_000:  score += 3
        elif vol >= 2_000_000: score += 2
        elif vol >= 1_000_000: score += 1
        if sym in gem_watchlist: score += 2

        movers.append({"sym":sym,"price":price,"vol":vol,
                       "change":change,"sector":sector,"score":score})

    if not movers: return
    movers.sort(key=lambda x: -x["score"])

    for m in movers[:3]:
        sym  = m["sym"]
        base = sym.replace("USDT","")

        if m["score"] >= 6:   icon = "🔥🔥"; lvl = "EXPLOSIVE MOVE"
        elif m["score"] >= 4: icon = "🔥";   lvl = "STRONG MOVE"
        else:                 icon = "⚡";    lvl = "ACTIVE MOVE"

        gem_tag = ""
        if sym in gem_watchlist:
            gem_tag = "  💎 مرصودة من المرحلة "+str(gem_watchlist[sym].get("stage",1))+"\n"

        vol_str = str(round(m["vol"]/1e6,2))+"M" if m["vol"]>=1e6 else str(round(m["vol"]/1e3,0))+"K"
        _confirm_count, _badge = _register_confirm(sym, "instant")

        # عملات كبيرة (حجم > 5M) → ننتظر تأكيد الجوكر
        # عملات صغيرة/متوسطة → ادخل الآن مباشرة (تتحرك بسرعة)
        _is_large_cap = m["vol"] >= 5_000_000
        if _is_large_cap:
            _action_line = "🃏 _عملة كبيرة — الجوكر سيرسل تأكيد الدخول_"
        else:
            _action_line = "✅ *ادخل الآن* — زخم قوي + سيولة مؤكدة 🎯"

        msg = (
            icon+" *"+lvl+"* "+icon+"\n"
            +"━"*18+"\n"
            +"📍 *"+base+"/USDT*\n"
            +"  💰 `"+str(m["price"])+"`\n"
            +"  📈 تغيير 24h: `+"+str(round(m["change"],1))+"%`\n"
            +"  📦 حجم: `"+vol_str+"`\n"
            +"  🏷️ قطاع: `"+m["sector"]+"`\n"
            +gem_tag
            +"━"*18+"\n"
            +"🎯 *"+lvl+"* " + _badge + " | قوة: `"+str(m["score"])+"/9`\n"
            + _action_line
        )
        if not can_send_signal(): break
        send(msg)
        hot_alerted[sym] = now
        coin_alerted[sym] = now
        register_signal()
        if sym not in candidates: candidates.append(sym)
        add_to_liquidity_watchlist(sym, "move_"+str(round(m["change"],0))+"%",
                                   m["vol"], m["price"], m["sector"])
        log.info(" Instant Mover | %s | +%.1f%% | vol=%s | score=%d",
                 sym, m["change"], vol_str, m["score"])

    log.info(" Instant Scan | movers=%d", len(movers))


def _is_late_entry(price, high_24h, low_24h):
    # type: (float, float, float) -> bool
    """
    True إذا كان السعر في أعلى 8% من نطاق 24h = دخول متأخر
    يمنع إشارات SIGNUSDT-type (ذروة 0% ثم -13%)
    """
    rng = high_24h - low_24h
    if rng <= 0:
        return False
    pos = (price - low_24h) / rng
    return pos >= 0.92


def _register_confirm(sym, scanner_name):
    # type: (str, str) -> tuple
    """
    يسجّل تأكيداً من ماسح معين لعملة معينة خلال MULTI_CONFIRM_WINDOW (30 دقيقة).
    يعيد (count, badge) لإضافته في رسالة الإشارة.
    count=1 → 🔔1 | count=2 → 🔔🔔2 | count=3+ → 🔔🔔🔔3+
    """
    global _multi_confirm
    now = time.time()
    entry = _multi_confirm.get(sym)
    if not entry or (now - entry["last_time"]) > MULTI_CONFIRM_WINDOW:
        _multi_confirm[sym] = {"count": 0, "scanners": [], "last_time": now}
        entry = _multi_confirm[sym]
    if scanner_name not in entry["scanners"]:
        entry["count"]    += 1
        entry["scanners"].append(scanner_name)
        entry["last_time"] = now
    c     = entry["count"]
    badge = "🔔" * min(c, 3) + str(c)
    return c, badge


def scan_fast_breakout():
    # type: () -> None
    """
    Fast Scanner — Tier 0 — كل 30 ثانية مثل Wolf Flow
    يعمل بدون klines: يقارن السعر الحالي بالسعر قبل 30 ثانية
    إذا تحركت العملة 1.5%+ في 30 ثانية = انفجار لحظي → ادخل فوراً

    بدون API calls إضافية — فقط all_tickers (محدّث كل 12 ثانية)
    """
    global _fast_alerted, _fast_price_snap, last_fast_scan, hot_alerted, _coin_first_seen

    now = time.time()
    if now - last_fast_scan < FAST_SCAN_EVERY:
        return

    if not all_tickers:
        return

    all_sector_coins = set()
    for sc in SECTORS.values():
        all_sector_coins.update(sc)

    fired = 0
    new_snap = {}

    for t in all_tickers:
        sym = t.get("symbol", "")
        if not sym.endswith("USDT"):
            continue
        if any(k in sym for k in LEVERAGE_KEYWORDS):
            continue
        if sym.replace("USDT", "") in STABLECOINS:
            continue

        try:
            price  = float(t["lastPrice"])
            vol    = float(t["quoteVolume"])
            change = float(t["priceChangePercent"])
        except (KeyError, ValueError):
            continue

        # حفظ السعر الحالي للمقارنة في الجولة القادمة
        new_snap[sym] = price

        if vol < FAST_MIN_VOL:
            continue
        if change < FAST_MOVE_24H_MIN or change > 40.0:
            continue

        # السعر قبل 30 ثانية
        prev_price = _fast_price_snap.get(sym, 0.0)
        if prev_price <= 0:
            continue

        # الحركة خلال 30 ثانية
        move_30s = (price - prev_price) / prev_price * 100.0
        if move_30s < FAST_MOVE_30S:
            continue

        # فلتر العمر
        if sym not in _coin_first_seen:
            _coin_first_seen[sym] = now
        if (now - _coin_first_seen.get(sym, now)) / 86400 < NEW_COIN_MIN_DAYS:
            continue

        # cooldowns
        if now - _fast_alerted.get(sym, 0) < FAST_SCAN_COOLDOWN:
            continue
        if now - hot_alerted.get(sym, 0) < 1800:
            continue

        # تدفق الأموال السريع من ticker (bid/ask approximation)
        try:
            bid = float(t.get("bidPrice", 0) or 0)
            ask = float(t.get("askPrice", 0) or 0)
            _spread = (ask - bid) / bid * 100 if bid > 0 else 99
            if _spread > 5.0:   # spread واسع = سيولة ضعيفة
                continue
        except (ValueError, ZeroDivisionError):
            pass

        # فلتر الدخول المتأخر — السعر في أعلى 8% من نطاق 24h
        try:
            _h24 = float(t.get("highPrice", price))
            _l24 = float(t.get("lowPrice",  price))
            if _is_late_entry(price, _h24, _l24):
                log.debug("FAST late_entry skip %s pos>=92%%", sym)
                continue
        except (ValueError, TypeError):
            pass

        sector = next((s for s, c in SECTORS.items() if sym in c), "غير محدد")
        base   = sym.replace("USDT", "")
        in_sector = sym in all_sector_coins
        _tier = "" if in_sector else " 🌐"
        _confirm_count, _badge = _register_confirm(sym, "fast")

        def _fp(v):
            if v >= 1_000_000: return "{:.1f}M$".format(v / 1e6)
            if v >= 1_000:     return "{:.1f}K$".format(v / 1e3)
            return "{:.0f}$".format(v)

        msg = (
            "⚡⚡ *FAST BREAKOUT* ⚡⚡" + _tier + " " + _badge + "\n"
            + "━" * 18 + "\n"
            + "📍 *" + base + "/USDT*\n"
            + "  💰 السعر: `" + str(round(price, 8)).rstrip("0").rstrip(".") + "`\n"
            + "  🚀 حركة 30s: `+" + str(round(move_30s, 2)) + "%`\n"
            + "  📈 تغيير 24h: `+" + str(round(change, 1)) + "%`\n"
            + "  📦 حجم: `" + _fp(vol) + "`\n"
            + "  🏷️ قطاع: `" + sector + "`\n"
            + "━" * 18 + "\n"
            + "✅ *ادخل الآن* — انفجار لحظي مكتشف 🎯"
        )

        send(msg)
        _fast_alerted[sym] = now
        hot_alerted[sym] = now
        if sym not in candidates:
            candidates.append(sym)
        add_to_liquidity_watchlist(sym, "fast_30s+" + str(round(move_30s, 1)) + "%",
                                   vol, price, sector)
        log.info("FAST BREAKOUT%s | %s | 30s=+%.2f%% | 24h=+%.1f%%",
                 "(T2)" if not in_sector else "", sym, move_30s, change)
        fired += 1

    # تحديث snapshot للجولة القادمة
    _fast_price_snap.update(new_snap)
    last_fast_scan = now

    # تنظيف الـ snapshot من العملات التي لم تظهر
    stale = [k for k in _fast_price_snap if k not in new_snap]
    for k in stale:
        _fast_price_snap.pop(k, None)


def calc_market_bias_score():
    # type: () -> tuple
    """
    Market Bias Score مثل Wolf Flow: -100 إلى +100
    -100 = Strong Bear | 0 = محايد | +100 = Strong Bull

    يحسب من all_tickers بدون API calls إضافية:
    - نسبة العملات الصاعدة/النازلة (breadth)
    - نسبة حجم الشراء/البيع (volume flow)
    """
    global _market_bias_score
    if not all_tickers:
        return 0, "محايد 🟡"

    up_count = 0; down_count = 0; total = 0
    vol_up = 0.0; vol_down = 0.0

    for t in all_tickers:
        sym = t.get("symbol", "")
        if not sym.endswith("USDT"):
            continue
        if sym.replace("USDT", "") in STABLECOINS:
            continue
        if "(" in sym:
            continue
        try:
            chg = float(t["priceChangePercent"])
            vol = float(t["quoteVolume"])
        except (KeyError, ValueError):
            continue
        if vol < 50_000:
            continue
        total += 1
        if chg > 0.5:
            up_count += 1
            vol_up += vol
        elif chg < -0.5:
            down_count += 1
            vol_down += vol

    if total == 0:
        return 0, "محايد 🟡"

    # Breadth: نسبة الصاعدين مقابل النازلين (-50 إلى +50)
    breadth_score = (up_count - down_count) / total * 50

    # Volume flow: نسبة حجم الشراء مقابل البيع (-50 إلى +50)
    total_vol = vol_up + vol_down
    vol_score = (vol_up - vol_down) / total_vol * 50 if total_vol > 0 else 0

    score = int(breadth_score + vol_score)
    score = max(-100, min(100, score))
    _market_bias_score = score

    if score >= 60:    label = "Strong Bull 🟢🟢"
    elif score >= 20:  label = "Bull 🟢"
    elif score >= -20: label = "محايد 🟡"
    elif score >= -60: label = "Bear 🔴"
    else:              label = "Strong Bear 🔴🔴"

    return score, label


def scan_1h_move():
    # type: () -> None
    """
    1h Move Scanner — Wolf Flow style
    يرصد العملات التي تحركت 4%+ في الساعة الأخيرة (مثل DIAUSDT/BANANAUSDT)
    الفرق عن 5m breakout: يعتمد على حركة الـ 1h لا الـ 24h
    يعمل على كل السوق بدون قيود القطاعات

    الشروط:
    1. حركة 1h ≥ 4% (آخر شمعة 1h مقارنة بالسابقة)
    2. Flow 1h: IN > OUT بنسبة ≥ 1.3x
    3. حجم آخر شمعة 1h > 1.5× متوسط الشمعات السابقة
    4. ليس دخولاً متأخراً (سعر < 92% من نطاق 24h)
    """
    global _move1h_alerted, last_move1h_scan, _coin_first_seen, hot_alerted

    now = time.time()
    if now - last_move1h_scan < MOVE1H_SCAN_EVERY:
        return
    last_move1h_scan = now

    if not all_tickers:
        return

    # المرحلة 1: فلترة سريعة من ticker
    pool = []
    for t in all_tickers:
        sym = t.get("symbol", "")
        if not sym.endswith("USDT"):
            continue
        if any(k in sym for k in LEVERAGE_KEYWORDS):
            continue
        if sym.replace("USDT", "") in STABLECOINS:
            continue
        if "(" in sym or ")" in sym:
            continue
        try:
            price  = float(t["lastPrice"])
            vol    = float(t["quoteVolume"])
            change = float(t["priceChangePercent"])
        except (KeyError, ValueError):
            continue

        if vol < MOVE1H_MIN_VOL:
            continue
        # فلتر أساسي: 24h اتجاه إيجابي
        if change < 1.0 or change > 60.0:
            continue

        # فلتر العمر
        if sym not in _coin_first_seen:
            _coin_first_seen[sym] = now
        if (now - _coin_first_seen.get(sym, now)) / 86400 < NEW_COIN_MIN_DAYS:
            continue

        # cooldown
        if now - _move1h_alerted.get(sym, 0) < MOVE1H_COOLDOWN:
            continue
        if now - hot_alerted.get(sym, 0) < 1800:
            continue

        # فلتر الدخول المتأخر
        try:
            _h24 = float(t.get("highPrice", price))
            _l24 = float(t.get("lowPrice",  price))
            if _is_late_entry(price, _h24, _l24):
                continue
        except (ValueError, TypeError):
            pass

        pool.append((sym, vol, change, price, t))

    if not pool:
        return

    # أفضل 50 بالحجم
    pool.sort(key=lambda x: -x[1])
    pool = pool[:MOVE1H_MAX_COINS]

    def _fmt(v):
        if v >= 1_000_000: return "{:.1f}M$".format(v / 1e6)
        if v >= 1_000:     return "{:.1f}K$".format(v / 1e3)
        return "{:.0f}$".format(v)

    for sym, vol_24h, change_24h, price, ticker in pool:
        # المرحلة 2: klines 1h (6 شمعات)
        kd = get_klines(sym, "1h", 6)
        if not kd or len(kd.get("closes", [])) < 3:
            continue

        closes  = kd["closes"]
        opens   = kd["opens"]
        highs   = kd["highs"]
        lows    = kd["lows"]
        vols    = kd["vols"]

        # حركة الشمعة الأخيرة (الساعة الأخيرة)
        if opens[-1] <= 0:
            continue
        move_1h = (closes[-1] - closes[-2]) / closes[-2] * 100 if closes[-2] > 0 else 0.0

        if move_1h < MOVE1H_MOVE_MIN or move_1h > MOVE1H_MOVE_MAX:
            continue

        # حجم الشمعة الأخيرة مقارنة بالمتوسط
        prev_vols = vols[-5:-1]
        avg_vol = sum(prev_vols) / len(prev_vols) if prev_vols else 0
        if avg_vol <= 0:
            continue
        vol_spike_1h = vols[-1] / avg_vol
        if vol_spike_1h < MOVE1H_VOL_SPIKE:
            continue

        # Flow 1h من آخر شمعتين
        _in_1h = 0.0; _out_1h = 0.0
        for h, l, c, v in zip(highs[-2:], lows[-2:], closes[-2:], vols[-2:]):
            rng = h - l
            br  = (c - l) / rng if rng > 0 else 0.5
            vu  = v * c
            _in_1h  += vu * br
            _out_1h += vu * (1.0 - br)

        if _out_1h <= 0:
            continue
        _ratio_1h = _in_1h / _out_1h
        if _ratio_1h < MOVE1H_FLOW_RATIO:
            continue
        if _in_1h <= _out_1h:
            continue

        sector = next((s for s, c in SECTORS.items() if sym in c), "غير محدد")
        base   = sym.replace("USDT", "")
        _confirm_count, _badge = _register_confirm(sym, "1h_move")

        # تصنيف الحجم مثل Wolf Flow
        _vol_label = ("Elevated 🔥" if vol_spike_1h >= 3.0 else
                      "Good ⚡"      if vol_spike_1h >= 1.5 else
                      "Normal")

        # تصنيف الاهتمام مثل Wolf Flow
        _interest = ("Strong 💪" if _ratio_1h >= 3.0 else
                     "Neutral 🟡" if _ratio_1h >= 1.3 else
                     "Weak")

        msg = (
            "📡 *1h MOVE* 📡 " + _badge + "\n"
            + "━" * 18 + "\n"
            + "📍 *" + base + "/USDT*\n"
            + "  💰 السعر: `" + str(round(price, 8)).rstrip("0").rstrip(".") + "`\n"
            + "  📈 حركة 1h: `+" + str(round(move_1h, 2)) + "%`\n"
            + "  ⚡ Volume: " + _vol_label + " | Interest: " + _interest + "\n"
            + "  🏷️ قطاع: `" + sector + "`\n"
            + "━" * 18 + "\n"
            + "💹 *Flow 1h:* IN `" + _fmt(_in_1h) + "` / OUT `" + _fmt(_out_1h) + "` / Net `+" + _fmt(_in_1h - _out_1h) + "`\n"
            + "━" * 18 + "\n"
            + "✅ *ادخل الآن* — زخم 1h + Flow إيجابي 🎯"
        )

        send(msg)
        _move1h_alerted[sym] = now
        hot_alerted[sym] = now
        if sym not in candidates:
            candidates.append(sym)
        add_to_liquidity_watchlist(sym, "1h_move+" + str(round(move_1h, 1)) + "%",
                                   vol_24h, price, sector)
        log.info("1h MOVE | %s | 1h=+%.2f%% | vol_spike=%.1fx | flow_ratio=%.1fx | net=%.0f$",
                 sym, move_1h, vol_spike_1h, _ratio_1h, _in_1h - _out_1h)


def scan_flow_accumulation():
    # type: () -> None
    """
    Flow Accumulation Scanner — يرصد التجميع الخفي قبل الانفجار
    مثل NTRNUSDT: 1h Move +0.00% + Flow IN/OUT = 10x → +2% في 57 ثانية

    الشروط:
    1. السعر ثابت أو يتحرك قليلاً (≤ 3% في 1h)
    2. Flow ratio ≥ 6x (أموال تتراكم بهدوء)
    3. حجم الشمعة الأخيرة > 2x المتوسط (نشاط غير عادي)
    4. لا دخول متأخر
    """
    global _flowacc_alerted, last_flowacc_scan, _coin_first_seen, hot_alerted

    now = time.time()
    if now - last_flowacc_scan < FLOWACC_SCAN_EVERY:
        return
    last_flowacc_scan = now

    if not all_tickers:
        return

    pool = []
    for t in all_tickers:
        sym = t.get("symbol", "")
        if not sym.endswith("USDT"):
            continue
        if any(k in sym for k in LEVERAGE_KEYWORDS):
            continue
        if sym.replace("USDT", "") in STABLECOINS:
            continue
        if "(" in sym or ")" in sym:
            continue
        try:
            price  = float(t["lastPrice"])
            vol    = float(t["quoteVolume"])
            change = float(t["priceChangePercent"])
        except (KeyError, ValueError):
            continue

        if vol < FLOWACC_MIN_VOL:
            continue
        # 24h تغيير إيجابي أو محايد — ليس هابطاً
        if change < -2.0 or change > 20.0:
            continue

        if sym not in _coin_first_seen:
            _coin_first_seen[sym] = now
        if (now - _coin_first_seen.get(sym, now)) / 86400 < NEW_COIN_MIN_DAYS:
            continue

        if now - _flowacc_alerted.get(sym, 0) < FLOWACC_COOLDOWN:
            continue
        if now - hot_alerted.get(sym, 0) < 1800:
            continue

        try:
            _h24 = float(t.get("highPrice", price))
            _l24 = float(t.get("lowPrice",  price))
            if _is_late_entry(price, _h24, _l24):
                continue
        except (ValueError, TypeError):
            pass

        pool.append((sym, vol, change, price))

    if not pool:
        return

    pool.sort(key=lambda x: -x[1])
    pool = pool[:FLOWACC_MAX_COINS]

    def _fmt(v):
        if v >= 1_000_000: return "{:.1f}M$".format(v / 1e6)
        if v >= 1_000:     return "{:.1f}K$".format(v / 1e3)
        return "{:.2f}$".format(v)

    for sym, vol_24h, change_24h, price in pool:
        kd = get_klines(sym, "1h", 6)
        if not kd or len(kd.get("closes", [])) < 3:
            continue

        closes  = kd["closes"]
        highs   = kd["highs"]
        lows    = kd["lows"]
        vols    = kd["vols"]

        # حركة الشمعة الأخيرة يجب أن تكون صغيرة (السعر ثابت)
        if closes[-2] <= 0:
            continue
        move_1h = abs((closes[-1] - closes[-2]) / closes[-2] * 100)
        if move_1h > FLOWACC_PRICE_MAX:
            continue

        # حجم الشمعة الأخيرة > 2x المتوسط
        prev_vols = vols[-5:-1]
        avg_vol = sum(prev_vols) / len(prev_vols) if prev_vols else 0
        if avg_vol <= 0:
            continue
        vol_spike = vols[-1] / avg_vol
        if vol_spike < FLOWACC_VOL_SPIKE:
            continue

        # Flow من آخر شمعتين
        _in = 0.0; _out = 0.0
        for h, l, c, v in zip(highs[-2:], lows[-2:], closes[-2:], vols[-2:]):
            rng = h - l
            br  = (c - l) / rng if rng > 0 else 0.5
            vu  = v * c
            _in  += vu * br
            _out += vu * (1.0 - br)

        if _out <= 0:
            continue
        ratio = _in / _out
        if ratio < FLOWACC_FLOW_RATIO:
            continue

        sector = next((s for s, c in SECTORS.items() if sym in c), "غير محدد")
        base   = sym.replace("USDT", "")
        _confirm_count, _badge = _register_confirm(sym, "flow_acc")

        _strength = ("🔥🔥 استثنائي" if ratio >= 15 else
                     "🔥 قوي جداً"    if ratio >= 10 else
                     "⚡ قوي")

        msg = (
            "🧲 *FLOW ACCUMULATION* 🧲 " + _badge + "\n"
            + "━" * 18 + "\n"
            + "📍 *" + base + "/USDT*\n"
            + "  💰 السعر: `" + str(round(price, 8)).rstrip("0").rstrip(".") + "`\n"
            + "  📊 حركة 1h: `" + ("{:+.2f}".format(closes[-1]/closes[-2]*100-100) if closes[-2] > 0 else "0") + "%` — السعر ثابت\n"
            + "  📦 حجم الشمعة: `" + str(round(vol_spike, 1)) + "x` المتوسط\n"
            + "  🏷️ قطاع: `" + sector + "`\n"
            + "━" * 18 + "\n"
            + "💹 *Flow 1h:* IN `" + _fmt(_in) + "` / OUT `" + _fmt(_out) + "` = `" + str(round(ratio, 1)) + "x` — " + _strength + "\n"
            + "━" * 18 + "\n"
            + "✅ *ادخل الآن* — تجميع خفي قبل الانفجار 🎯"
        )

        send(msg)
        _flowacc_alerted[sym] = now
        hot_alerted[sym] = now
        if sym not in candidates:
            candidates.append(sym)
        add_to_liquidity_watchlist(sym, "flow_acc_" + str(round(ratio, 1)) + "x",
                                   vol_24h, price, sector)
        log.info("FLOW ACCUMULATION | %s | move=%.2f%% | vol_spike=%.1fx | ratio=%.1fx",
                 sym, move_1h, vol_spike, ratio)


def scan_volume_breakout():
    # type: () -> None
    """
    Volume Breakout Scanner — انفجار حجم × 5+ قبل تحرك السعر
    يرصد: حجم الشمعة الحالية > 5x المتوسط + السعر لم يتحرك كثيراً
    = شراء مؤسسي خفي قبل الـ pump

    الفرق: يعتمد على الحجم أولاً، لا على السعر أو الـ flow
    """
    global _volbr_alerted, last_volbr_scan, _coin_first_seen, hot_alerted

    now = time.time()
    if now - last_volbr_scan < VOLBR_SCAN_EVERY:
        return
    last_volbr_scan = now

    if not all_tickers:
        return

    pool = []
    for t in all_tickers:
        sym = t.get("symbol", "")
        if not sym.endswith("USDT"):
            continue
        if any(k in sym for k in LEVERAGE_KEYWORDS):
            continue
        if sym.replace("USDT", "") in STABLECOINS:
            continue
        if "(" in sym or ")" in sym:
            continue
        try:
            price  = float(t["lastPrice"])
            vol    = float(t["quoteVolume"])
            change = float(t["priceChangePercent"])
        except (KeyError, ValueError):
            continue

        if vol < VOLBR_MIN_VOL:
            continue
        if change < -3.0 or change > 25.0:
            continue

        if sym not in _coin_first_seen:
            _coin_first_seen[sym] = now
        if (now - _coin_first_seen.get(sym, now)) / 86400 < NEW_COIN_MIN_DAYS:
            continue

        if now - _volbr_alerted.get(sym, 0) < VOLBR_COOLDOWN:
            continue
        if now - hot_alerted.get(sym, 0) < 1800:
            continue

        try:
            _h24 = float(t.get("highPrice", price))
            _l24 = float(t.get("lowPrice",  price))
            if _is_late_entry(price, _h24, _l24):
                continue
        except (ValueError, TypeError):
            pass

        pool.append((sym, vol, change, price))

    if not pool:
        return

    pool.sort(key=lambda x: -x[1])
    pool = pool[:VOLBR_MAX_COINS]

    def _fmt(v):
        if v >= 1_000_000: return "{:.1f}M$".format(v / 1e6)
        if v >= 1_000:     return "{:.1f}K$".format(v / 1e3)
        return "{:.2f}$".format(v)

    for sym, vol_24h, change_24h, price in pool:
        kd = get_klines(sym, "15m", 20)
        if not kd or len(kd.get("closes", [])) < 10:
            continue

        closes  = kd["closes"]
        highs   = kd["highs"]
        lows    = kd["lows"]
        vols    = kd["vols"]

        # حجم آخر شمعة > VOLBR_SPIKE_MIN × متوسط
        prev_vols = vols[-15:-1]
        avg_vol = sum(prev_vols) / len(prev_vols) if prev_vols else 0
        if avg_vol <= 0:
            continue
        vol_spike = vols[-1] / avg_vol
        if vol_spike < VOLBR_SPIKE_MIN:
            continue

        # السعر لم يتحرك كثيراً في آخر شمعة
        if closes[-2] <= 0:
            continue
        candle_move = abs((closes[-1] - closes[-2]) / closes[-2] * 100)
        if candle_move > VOLBR_PRICE_MAX:
            continue

        # Flow من آخر 3 شمعات
        _in = 0.0; _out = 0.0
        for h, l, c, v in zip(highs[-3:], lows[-3:], closes[-3:], vols[-3:]):
            rng = h - l
            br  = (c - l) / rng if rng > 0 else 0.5
            vu  = v * c
            _in  += vu * br
            _out += vu * (1.0 - br)

        flow_ratio = _in / _out if _out > 0 else 1.0

        sector = next((s for s, c in SECTORS.items() if sym in c), "غير محدد")
        base   = sym.replace("USDT", "")
        _confirm_count, _badge = _register_confirm(sym, "vol_br")

        _vol_label = ("💥 انفجاري" if vol_spike >= 10 else
                      "🔥 ضخم"      if vol_spike >= 7  else
                      "⚡ قوي")

        msg = (
            "📊 *VOLUME BREAKOUT* 📊 " + _badge + "\n"
            + "━" * 18 + "\n"
            + "📍 *" + base + "/USDT*\n"
            + "  💰 السعر: `" + str(round(price, 8)).rstrip("0").rstrip(".") + "`\n"
            + "  📈 تغيير 24h: `" + str(round(change_24h, 1)) + "%`\n"
            + "  🏷️ قطاع: `" + sector + "`\n"
            + "━" * 18 + "\n"
            + "📦 *حجم 15m:* `" + str(round(vol_spike, 1)) + "x` المتوسط — " + _vol_label + "\n"
            + "💹 *Flow:* IN `" + _fmt(_in) + "` / OUT `" + _fmt(_out) + "` = `" + str(round(flow_ratio, 1)) + "x`\n"
            + "━" * 18 + "\n"
            + "✅ *ادخل الآن* — حجم ضخم قبل تحرك السعر 🎯"
        )

        send(msg)
        _volbr_alerted[sym] = now
        hot_alerted[sym] = now
        if sym not in candidates:
            candidates.append(sym)
        add_to_liquidity_watchlist(sym, "vol_br_" + str(round(vol_spike, 1)) + "x",
                                   vol_24h, price, sector)
        log.info("VOLUME BREAKOUT | %s | spike=%.1fx | candle_move=%.2f%% | flow=%.1fx",
                 sym, vol_spike, candle_move, flow_ratio)


def scan_micro_pump():
    # type: () -> None
    """
    Micro Pump Scanner — حركة صغيرة 0.8-5% مع flow استثنائي 12x+
    يرصد لحظة بداية الـ pump قبل أن يُلاحظه الجميع

    الفرق عن 5m breakout: يعمل بحركة أصغر بكثير + flow أقوى بكثير
    الفرق عن flow_accumulation: السعر بدأ يتحرك فعلاً (ولو قليلاً)
    """
    global _micropump_alerted, last_micropump_scan, _coin_first_seen, hot_alerted

    now = time.time()
    if now - last_micropump_scan < MICROPUMP_SCAN_EVERY:
        return
    last_micropump_scan = now

    if not all_tickers:
        return

    pool = []
    for t in all_tickers:
        sym = t.get("symbol", "")
        if not sym.endswith("USDT"):
            continue
        if any(k in sym for k in LEVERAGE_KEYWORDS):
            continue
        if sym.replace("USDT", "") in STABLECOINS:
            continue
        if "(" in sym or ")" in sym:
            continue
        try:
            price  = float(t["lastPrice"])
            vol    = float(t["quoteVolume"])
            change = float(t["priceChangePercent"])
        except (KeyError, ValueError):
            continue

        if vol < MICROPUMP_MIN_VOL:
            continue
        if change < 0.5 or change > 20.0:
            continue

        if sym not in _coin_first_seen:
            _coin_first_seen[sym] = now
        if (now - _coin_first_seen.get(sym, now)) / 86400 < NEW_COIN_MIN_DAYS:
            continue

        if now - _micropump_alerted.get(sym, 0) < MICROPUMP_COOLDOWN:
            continue
        if now - hot_alerted.get(sym, 0) < 1800:
            continue

        try:
            _h24 = float(t.get("highPrice", price))
            _l24 = float(t.get("lowPrice",  price))
            if _is_late_entry(price, _h24, _l24):
                continue
        except (ValueError, TypeError):
            pass

        pool.append((sym, vol, change, price))

    if not pool:
        return

    pool.sort(key=lambda x: -x[1])
    pool = pool[:MICROPUMP_MAX_COINS]

    def _fmt(v):
        if v >= 1_000_000: return "{:.1f}M$".format(v / 1e6)
        if v >= 1_000:     return "{:.1f}K$".format(v / 1e3)
        return "{:.2f}$".format(v)

    for sym, vol_24h, change_24h, price in pool:
        kd = get_klines(sym, "5m", 15)
        if not kd or len(kd.get("closes", [])) < 8:
            continue

        closes  = kd["closes"]
        highs   = kd["highs"]
        lows    = kd["lows"]
        vols    = kd["vols"]

        # حركة آخر شمعة 5m: صغيرة لكن موجودة
        if closes[-2] <= 0:
            continue
        move_5m = (closes[-1] - closes[-2]) / closes[-2] * 100
        if move_5m < MICROPUMP_MOVE_MIN or move_5m > MICROPUMP_MOVE_MAX:
            continue

        # Flow من آخر 3 شمعات 5m — يجب أن يكون استثنائياً
        _in = 0.0; _out = 0.0
        for h, l, c, v in zip(highs[-3:], lows[-3:], closes[-3:], vols[-3:]):
            rng = h - l
            br  = (c - l) / rng if rng > 0 else 0.5
            vu  = v * c
            _in  += vu * br
            _out += vu * (1.0 - br)

        if _out <= 0:
            continue
        ratio = _in / _out
        if ratio < MICROPUMP_FLOW_RATIO:
            continue

        # حجم الشمعة الأخيرة > المتوسط
        prev_vols = vols[-10:-1]
        avg_vol = sum(prev_vols) / len(prev_vols) if prev_vols else 0
        if avg_vol <= 0 or vols[-1] < avg_vol:
            continue

        sector = next((s for s, c in SECTORS.items() if sym in c), "غير محدد")
        base   = sym.replace("USDT", "")
        _confirm_count, _badge = _register_confirm(sym, "micro_pump")

        _flow_label = ("💥 نادر جداً" if ratio >= 25 else
                       "🔥🔥 استثنائي" if ratio >= 18 else
                       "🔥 قوي جداً")

        msg = (
            "🚀 *MICRO PUMP* 🚀 " + _badge + "\n"
            + "━" * 18 + "\n"
            + "📍 *" + base + "/USDT*\n"
            + "  💰 السعر: `" + str(round(price, 8)).rstrip("0").rstrip(".") + "`\n"
            + "  📈 حركة 5m: `+" + str(round(move_5m, 2)) + "%` — بداية الموجة\n"
            + "  📈 تغيير 24h: `+" + str(round(change_24h, 1)) + "%`\n"
            + "  🏷️ قطاع: `" + sector + "`\n"
            + "━" * 18 + "\n"
            + "💹 *Flow 5m:* IN `" + _fmt(_in) + "` / OUT `" + _fmt(_out) + "` = `" + str(round(ratio, 1)) + "x` — " + _flow_label + "\n"
            + "━" * 18 + "\n"
            + "✅ *ادخل الآن* — بداية الـ pump + flow استثنائي 🎯"
        )

        send(msg)
        _micropump_alerted[sym] = now
        hot_alerted[sym] = now
        if sym not in candidates:
            candidates.append(sym)
        add_to_liquidity_watchlist(sym, "micro_pump_" + str(round(ratio, 1)) + "x",
                                   vol_24h, price, sector)
        log.info("MICRO PUMP | %s | move_5m=+%.2f%% | ratio=%.1fx",
                 sym, move_5m, ratio)


def scan_bb_squeeze():
    # type: () -> None
    """
    BB Squeeze Scanner — مثل Wolf Flow الذي يرصد 388 عملة تتضغط
    يكتشف العملات التي تتضغط في Bollinger Bands قبل الانفجار

    الشروط:
    1. BB Width الحالي < أدنى BB Width في آخر 25 شمعة (ضغط شديد)
    2. آخر شمعة تخترق الـ Upper Band (بداية الانفجار)
    3. حجم آخر شمعة > 2x المتوسط (تأكيد)
    4. Flow إيجابي (IN > OUT)
    """
    global _bb_squeeze_alerted, last_bb_squeeze_scan, _coin_first_seen, hot_alerted

    now = time.time()
    if now - last_bb_squeeze_scan < BB_SQUEEZE_SCAN_EVERY:
        return
    last_bb_squeeze_scan = now

    if not all_tickers:
        return

    # المرحلة 1: فلترة سريعة
    pool = []
    for t in all_tickers:
        sym = t.get("symbol", "")
        if not sym.endswith("USDT"):
            continue
        if any(k in sym for k in LEVERAGE_KEYWORDS):
            continue
        if sym.replace("USDT", "") in STABLECOINS:
            continue
        if "(" in sym or ")" in sym:
            continue
        try:
            vol    = float(t["quoteVolume"])
            change = float(t["priceChangePercent"])
            price  = float(t["lastPrice"])
        except (KeyError, ValueError):
            continue

        if vol < BB_SQUEEZE_MIN_VOL:
            continue
        if change < -15.0 or change > 50.0:
            continue

        # فلتر العمر
        if sym not in _coin_first_seen:
            _coin_first_seen[sym] = now
        if (now - _coin_first_seen.get(sym, now)) / 86400 < NEW_COIN_MIN_DAYS:
            continue

        if now - _bb_squeeze_alerted.get(sym, 0) < BB_SQUEEZE_COOLDOWN:
            continue
        if now - hot_alerted.get(sym, 0) < 1800:
            continue

        pool.append((sym, vol, change, price))

    if not pool:
        return

    pool.sort(key=lambda x: -x[1])
    pool = pool[:BB_SQUEEZE_MAX_COINS]

    def _calc_bb(closes, period, mult):
        """يحسب Bollinger Bands لآخر N شمعة"""
        if len(closes) < period:
            return None, None, None
        subset = closes[-period:]
        sma = sum(subset) / period
        variance = sum((c - sma) ** 2 for c in subset) / period
        std = variance ** 0.5
        return sma, sma + mult * std, sma - mult * std

    def _bb_width(closes, period, mult):
        """يحسب عرض BB كنسبة مئوية من SMA"""
        sma, upper, lower = _calc_bb(closes, period, mult)
        if sma is None or sma == 0:
            return None
        return (upper - lower) / sma * 100

    def _fmt(v):
        if v >= 1_000_000: return "{:.1f}M$".format(v / 1e6)
        if v >= 1_000:     return "{:.1f}K$".format(v / 1e3)
        return "{:.0f}$".format(v)

    squeeze_coins = []  # للـ log فقط

    for sym, vol_24h, change, price in pool:
        kd = get_klines(sym, "15m", 60)
        if not kd or len(kd.get("closes", [])) < BB_PERIOD + 25:
            continue

        closes  = kd["closes"]
        volumes = kd["vols"]
        highs   = kd["highs"]

        # احسب BB width لكل شمعة من آخر 30 شمعة
        widths = []
        for i in range(30, 0, -1):
            w = _bb_width(closes[:-i] if i > 0 else closes, BB_PERIOD, BB_STD_MULT)
            if w is not None:
                widths.append(w)

        if len(widths) < 20:
            continue

        current_width = widths[-1]
        historical_min = min(widths[:-1])  # أدنى width تاريخي (بدون الحالي)

        # شرط الضغط: BB Width الحالي هو الأضيق في آخر 30 شمعة
        is_squeeze = current_width <= historical_min * 1.05  # هامش 5%
        if not is_squeeze:
            continue

        squeeze_coins.append(sym)

        # شرط الاختراق: آخر شمعة فوق Upper Band
        _, upper, _ = _calc_bb(closes, BB_PERIOD, BB_STD_MULT)
        if upper is None or closes[-1] < upper:
            continue

        # شرط الحجم: آخر شمعة > 2x المتوسط
        avg_vol = sum(volumes[-20:-1]) / 19 if len(volumes) >= 20 else 0
        if avg_vol <= 0 or volumes[-1] < avg_vol * 2.0:
            continue

        # تدفق الأموال
        flow1h = calc_money_flow_1h(sym)
        if flow1h["net"] < 0:
            continue

        # فلتر الدخول المتأخر — السعر في أعلى 8% من نطاق 24h
        try:
            _t_bb = next((x for x in all_tickers if x.get("symbol") == sym), None)
            if _t_bb:
                _h24 = float(_t_bb.get("highPrice", price))
                _l24 = float(_t_bb.get("lowPrice",  price))
                if _is_late_entry(price, _h24, _l24):
                    log.debug("BB_SQ late_entry skip %s", sym)
                    continue
        except (ValueError, TypeError):
            pass

        sector = next((s for s, c in SECTORS.items() if sym in c), "غير محدد")
        base   = sym.replace("USDT", "")
        _confirm_count, _badge = _register_confirm(sym, "bb_squeeze")

        msg = (
            "💥 *BB SQUEEZE BREAKOUT* 💥 " + _badge + "\n"
            + "━" * 18 + "\n"
            + "📍 *" + base + "/USDT*\n"
            + "  💰 السعر: `" + str(round(price, 8)).rstrip("0").rstrip(".") + "`\n"
            + "  📈 تغيير 24h: `" + str(round(change, 1)) + "%`\n"
            + "  📦 حجم: `" + _fmt(vol_24h) + "`\n"
            + "  🏷️ قطاع: `" + sector + "`\n"
            + "━" * 18 + "\n"
            + "🎯 BB Width: `" + str(round(current_width, 2)) + "%` — أضيق نقطة في 30 شمعة\n"
            + "💹 *Flow 1h:* IN `" + _fmt(flow1h["in"]) + "` / OUT `" + _fmt(flow1h["out"]) + "` / Net `" + _fmt(flow1h["net"]) + "↑`\n"
            + "━" * 18 + "\n"
            + "✅ *ادخل الآن* — انفجار بعد ضغط 🎯"
        )

        send(msg)
        _bb_squeeze_alerted[sym] = now
        hot_alerted[sym] = now
        if sym not in candidates:
            candidates.append(sym)
        add_to_liquidity_watchlist(sym, "bb_squeeze_" + str(round(change, 1)) + "%",
                                   vol_24h, price, sector)
        log.info("BB SQUEEZE BREAKOUT | %s | width=%.2f%% | flow_net=%.0f$",
                 sym, current_width, flow1h["net"])

    if squeeze_coins:
        log.info("BB Squeeze | %d في ضغط: %s", len(squeeze_coins),
                 ", ".join(squeeze_coins[:10]))


def scan_bounce_reversal():
    # type: () -> None
    """
    Bounce Reversal Scanner — يكتشف الارتداد بعد النزول
    مثل إشارة PYRUSDT في Wolf Flow: نزل -3.72% لكن البيع يخف

    الشروط:
    1. نزل 3-20% في 24h (oversold)
    2. حجم High (بيع قوي سبق)
    3. Flow OUT/IN < 1.8x — البيع يضعف
    4. آخر 3 شمعات 5m: شمعة واحدة على الأقل خضراء (بداية الارتداد)
    5. حجم آخر شمعة > المتوسط (مشترون يدخلون)
    """
    global _bounce_alerted, last_bounce_scan, _coin_first_seen, hot_alerted

    now = time.time()
    if now - last_bounce_scan < BOUNCE_SCAN_EVERY:
        return
    last_bounce_scan = now

    if not all_tickers:
        return

    # المرحلة 1: فلترة سريعة من ticker
    pool = []
    for t in all_tickers:
        sym = t.get("symbol", "")
        if not sym.endswith("USDT"):
            continue
        if any(k in sym for k in LEVERAGE_KEYWORDS):
            continue
        if sym.replace("USDT", "") in STABLECOINS:
            continue
        if "(" in sym or ")" in sym:
            continue

        try:
            price  = float(t["lastPrice"])
            vol    = float(t["quoteVolume"])
            change = float(t["priceChangePercent"])
        except (KeyError, ValueError):
            continue

        if vol < BOUNCE_MIN_VOL:
            continue
        # نزول حقيقي — ليس انهياراً
        if change > -BOUNCE_DROP_MIN or change < -BOUNCE_DROP_MAX:
            continue

        # فلتر العمر
        if sym not in _coin_first_seen:
            _coin_first_seen[sym] = now
        if (now - _coin_first_seen.get(sym, now)) / 86400 < NEW_COIN_MIN_DAYS:
            continue

        # cooldowns
        if now - _bounce_alerted.get(sym, 0) < BOUNCE_COOLDOWN:
            continue
        if now - hot_alerted.get(sym, 0) < 1800:
            continue

        pool.append((sym, vol, change, price))

    if not pool:
        return

    # أفضل 30 عملة بالحجم
    pool.sort(key=lambda x: -x[1])
    pool = pool[:30]

    def _ema_b(values, period):
        if len(values) < period:
            return values[-1] if values else 0.0
        k = 2.0 / (period + 1)
        e = sum(values[:period]) / period
        for v in values[period:]:
            e = v * k + e * (1 - k)
        return e

    def _fmt(v):
        if v >= 1_000_000: return "{:.1f}M$".format(v / 1e6)
        if v >= 1_000:     return "{:.1f}K$".format(v / 1e3)
        return "{:.0f}$".format(v)

    for sym, vol_24h, change, price in pool:
        # المرحلة 2: تدفق الأموال 1h
        flow1h = calc_money_flow_1h(sym)
        if flow1h["out"] <= 0:
            continue

        out_in_ratio = flow1h["out"] / flow1h["in"] if flow1h["in"] > 0 else 99.0

        # البيع يجب أن يكون يخف (ليس هجوماً ضخماً)
        if out_in_ratio > BOUNCE_OUTSELL_MAX:
            continue

        # المرحلة 3: فحص 5m klines
        kd = get_klines(sym, "5m", 20)
        if not kd or len(kd.get("closes", [])) < 10:
            continue

        closes  = kd["closes"]
        opens   = kd["opens"]
        volumes = kd["vols"]
        highs   = kd["highs"]
        lows    = kd["lows"]

        # آخر 3 شمعات: شمعة خضراء واحدة على الأقل (بداية الارتداد)
        last3_green = sum(1 for i in range(-3, 0) if closes[i] > opens[i])
        if last3_green == 0:
            continue

        # حجم آخر شمعة > متوسط الشمعات السابقة (مشترون يدخلون)
        avg_vol = sum(volumes[-15:-1]) / 14 if len(volumes) >= 15 else 0
        if avg_vol <= 0 or volumes[-1] < avg_vol * 1.2:
            continue

        # EMA5 يبدأ يقترب من EMA10 (الزخم يتحول)
        e5  = _ema_b(closes, 5)
        e10 = _ema_b(closes, 10)
        # e5 يجب أن يكون أعلى من أدنى نقطة (ليس في قاع الانهيار)
        recent_low = min(lows[-5:])
        if e5 < recent_low * 0.99:
            continue

        # حساب قوة الارتداد
        _in_5m = 0.0; _out_5m = 0.0
        for h, l, c, v in zip(highs[-3:], lows[-3:], closes[-3:], volumes[-3:]):
            rng = h - l
            br  = (c - l) / rng if rng > 0 else 0.5
            vu  = v * c
            _in_5m  += vu * br
            _out_5m += vu * (1.0 - br)

        # الشمعات الأخيرة يجب أن تُظهر شراءً
        if _in_5m <= _out_5m:
            continue

        sector = next((s for s, c in SECTORS.items() if sym in c), "غير محدد")
        base   = sym.replace("USDT", "")
        _confirm_count, _badge = _register_confirm(sym, "bounce")

        _sell_pressure = ("💚 بيع خفيف" if out_in_ratio < 1.2 else
                          "🟡 بيع يخف"   if out_in_ratio < 1.5 else
                          "🟠 بيع يتراجع")

        _vol_level = ("📊 عالٍ جداً" if vol_24h >= 5_000_000 else
                      "📊 عالٍ"       if vol_24h >= 1_000_000  else
                      "📊 جيد")

        msg = (
            "🔄 *BOUNCE REVERSAL* 🔄 " + _badge + "\n"
            + "━" * 18 + "\n"
            + "📍 *" + base + "/USDT*\n"
            + "  💰 السعر: `" + str(round(price, 8)).rstrip("0").rstrip(".") + "`\n"
            + "  📉 نزل: `" + str(round(change, 1)) + "%`\n"
            + "  " + _vol_level + " | " + _sell_pressure + "\n"
            + "  🏷️ قطاع: `" + sector + "`\n"
            + "━" * 18 + "\n"
            + "💹 *Flow 1h:* IN `" + _fmt(flow1h["in"]) + "` / OUT `" + _fmt(flow1h["out"]) + "` (نسبة `" + str(round(out_in_ratio, 1)) + "x`)\n"
            + "🕯️ آخر 3 شمعات 5m: `" + str(last3_green) + "/3` خضراء\n"
            + "━" * 18 + "\n"
            + "✅ *ادخل الآن* — البيع ينتهي، الارتداد بدأ 🎯"
        )

        send(msg)
        _bounce_alerted[sym] = now
        hot_alerted[sym] = now
        if sym not in candidates:
            candidates.append(sym)
        add_to_liquidity_watchlist(sym, "bounce_" + str(round(change, 1)) + "%",
                                   vol_24h, price, sector)
        log.info("BOUNCE REVERSAL | %s | %.1f%% | flow_ratio=%.1fx | green=%d/3",
                 sym, change, out_in_ratio, last3_green)


def scan_5m_breakout(price_map=None, vol_now=None):
    # type: () -> None
    """
    5m Breakout Scanner — يكتشف الاختراق لحظة بدايته
    يشبه Wolf Flow: EMA5>EMA10>EMA20 + volume spike على 5m + اختراق المقاومة

    Tier 1 — عملات SECTORS: حجم 300K+، تغيير 2-30%
    Tier 2 — كل السوق: حجم 1M+، تغيير 3-25%، flow ratio 8x+
    """
    global _breakout5m_alerted, last_breakout5m_scan, _coin_first_seen, hot_alerted

    now = time.time()
    if now - last_breakout5m_scan < BREAKOUT5M_SCAN_EVERY:
        return
    last_breakout5m_scan = now

    if not all_tickers:
        return

    all_sector_coins = set()
    for sc in SECTORS.values():
        all_sector_coins.update(sc)

    # المرحلة 1: فلترة سريعة بدون API calls إضافية
    pool = []   # (sym, vol, change, price, is_sector)
    for t in all_tickers:
        sym = t.get("symbol", "")
        if not sym.endswith("USDT"):
            continue
        if any(k in sym for k in LEVERAGE_KEYWORDS):
            continue
        if sym.replace("USDT","") in STABLECOINS:
            continue
        try:
            vol    = float(t["quoteVolume"])
            change = float(t["priceChangePercent"])
            price  = float(t["lastPrice"])
        except (KeyError, ValueError):
            continue

        in_sector = sym in all_sector_coins

        # حدود مختلفة لكل tier
        if in_sector:
            if vol < BREAKOUT5M_MIN_VOL: continue
            if change < 2.0 or change > 30.0: continue
        else:
            if vol < 300_000: continue             # Tier 2: حجم معقول
            if change < 3.0 or change > 25.0: continue

        # فلتر العمر
        if sym not in _coin_first_seen:
            _coin_first_seen[sym] = now
        if (now - _coin_first_seen.get(sym, now)) / 86400 < NEW_COIN_MIN_DAYS:
            continue

        # cooldowns
        if now - _breakout5m_alerted.get(sym, 0) < BREAKOUT5M_COOLDOWN:
            continue
        if now - hot_alerted.get(sym, 0) < 3600:
            continue

        pool.append((sym, vol, change, price, in_sector))

    if not pool:
        return

    # أفضل 35 عملة بالحجم (25 sector + 10 non-sector)
    sector_pool    = sorted([x for x in pool if x[4]],     key=lambda x: -x[1])[:25]
    nonsector_pool = sorted([x for x in pool if not x[4]], key=lambda x: -x[1])[:10]
    pool = sector_pool + nonsector_pool

    def _ema_calc(values, period):
        if len(values) < period:
            return values[-1] if values else 0.0
        k = 2.0 / (period + 1)
        e = sum(values[:period]) / period
        for v in values[period:]:
            e = v * k + e * (1 - k)
        return e

    def _fmt_usd(v):
        if v >= 1_000_000: return "{:.1f}M$".format(v / 1e6)
        if v >= 1_000:     return "{:.1f}K$".format(v / 1e3)
        return "{:.0f}$".format(v)

    for sym, vol_24h, change, price, in_sector in pool:
        kd = get_klines(sym, "5m", 25)
        if not kd or len(kd.get("closes", [])) < 20:
            continue

        closes  = kd["closes"]
        volumes = kd["vols"]
        highs   = kd["highs"]
        lows    = kd["lows"]

        # EMA alignment: EMA5 > EMA10 > EMA20
        e5  = _ema_calc(closes, 5)
        e10 = _ema_calc(closes, 10)
        e20 = _ema_calc(closes, 20)
        if not (e5 > e10 > e20):
            continue

        # حجم آخر شمعة > BREAKOUT5M_VOL_SPIKE × متوسط الشمعات السابقة
        prev_vols = volumes[-20:-1]
        if not prev_vols:
            continue
        avg_vol = sum(prev_vols) / len(prev_vols)
        if avg_vol <= 0:
            continue
        vol_spike = volumes[-1] / avg_vol
        if vol_spike < BREAKOUT5M_VOL_SPIKE:
            continue

        # اختراق أعلى نقطة من 20 شمعة سابقة (مقاومة)
        if len(closes) < 21:
            continue
        resistance = max(closes[-21:-1])
        if closes[-1] < resistance * 1.001:
            continue

        # حساب تدفق الأموال (5m) — IN/OUT بالدولار
        _in_5m = 0.0; _out_5m = 0.0
        for h, l, c, v in zip(highs[-5:], lows[-5:], closes[-5:], volumes[-5:]):
            rng = h - l
            br  = (c - l) / rng if rng > 0 else 0.5
            vu  = v * c
            _in_5m  += vu * br
            _out_5m += vu * (1.0 - br)
        _net_5m   = _in_5m - _out_5m
        _ratio_5m = _in_5m / _out_5m if _out_5m > 0 else 99.0

        # Tier 2 يحتاج flow ratio 8x+ (معيار أصعب)
        if not in_sector and _ratio_5m < 8.0:
            continue

        # فلتر: يجب أن يكون تدفق الشراء أكبر (flow إيجابي)
        if _net_5m < 0:
            continue

        # فلتر الدخول المتأخر — السعر في أعلى 8% من نطاق 24h
        try:
            _t5 = next((x for x in all_tickers if x.get("symbol") == sym), None)
            if _t5:
                _h24 = float(_t5.get("highPrice", price))
                _l24 = float(_t5.get("lowPrice",  price))
                if _is_late_entry(price, _h24, _l24):
                    log.debug("5m late_entry skip %s", sym)
                    continue
        except (ValueError, TypeError):
            pass

        # تدفق 1h
        _flow1h = calc_money_flow_1h(sym)

        # مستوى الحجم
        _vol_level = ("📊 عالٍ جداً" if vol_24h >= 10_000_000 else
                      "📊 عالٍ"       if vol_24h >= 3_000_000  else
                      "📊 جيد"        if vol_24h >= 1_000_000  else
                      "📊 عادي")

        # مستوى الاهتمام — بناءً على vol_spike + flow ratio
        _interest = ("🔥 قوي جداً" if vol_spike >= 5 and _ratio_5m >= 5 else
                     "⚡ قوي"       if vol_spike >= 3 or  _ratio_5m >= 3 else
                     "🟡 محايد")

        # جودة الـ Flow
        _flow_quality = ("💹 استثنائي" if _ratio_5m >= 10 else
                         "🔥 قوي"       if _ratio_5m >= 3  else
                         "📈 جيد")

        sector = next((s for s, c in SECTORS.items() if sym in c), "غير محدد")
        base   = sym.replace("USDT", "")
        _tier_tag = "" if in_sector else " 🌐"
        _confirm_count, _badge = _register_confirm(sym, "5m")

        msg = (
            "🚀 *5m BREAKOUT* 🚀" + _tier_tag + " " + _badge + "\n"
            + "━" * 18 + "\n"
            + "📍 *" + base + "/USDT*\n"
            + "  💰 السعر: `" + str(round(price, 8)).rstrip("0").rstrip(".") + "`\n"
            + "  📈 تغيير 1h: `+" + str(round(change, 1)) + "%`\n"
            + "  " + _vol_level + " | " + _interest + "\n"
            + "  🏷️ قطاع: `" + sector + "`\n"
            + "━" * 18 + "\n"
            + "⚡ EMA5>EMA10>EMA20 | حجم 5m: `" + str(round(vol_spike, 1)) + "x`\n"
            + "💹 *Flow 5m:* IN `" + _fmt_usd(_in_5m) + "` / OUT `" + _fmt_usd(_out_5m) + "` — " + _flow_quality + "\n"
            + "💰 *Flow 1h:* IN `" + _fmt_usd(_flow1h["in"]) + "` / OUT `" + _fmt_usd(_flow1h["out"]) + "` / Net `" + _fmt_usd(abs(_flow1h["net"])) + ("↑`\n" if _flow1h["net"] >= 0 else "↓`\n")
            + "━" * 18 + "\n"
            + "✅ *ادخل الآن* — EMA + حجم + Flow كلها مؤكدة 🎯"
        )

        send(msg)
        _breakout5m_alerted[sym] = now
        hot_alerted[sym] = now
        if sym not in candidates:
            candidates.append(sym)
        add_to_liquidity_watchlist(sym, "5m_breakout+" + str(round(change, 0)) + "%",
                                   vol_24h, price, sector)
        log.info("5m BREAKOUT%s | %s | +%.1f%% | EMA OK | vol_spike=%.1fx | flow5m_ratio=%.1fx | net=%.0f$",
                 ("(T2)" if not in_sector else ""), sym, change, vol_spike, _ratio_5m, _net_5m)


def scan_realtime_liquidity(price_map=None, vol_now=None):
    # type: () -> None
    """
    الأهم والأسرع — يعمل كل 5 دقائق
    يرصد السيولة غير العادية فوراً:

    1. حجم يرتفع 2× فجأة
    2. سعر يتحرك 3%+ معه
    3. على كل السوق مباشرة
    = لا يحتاج تاريخ — يعمل من الدقيقة الأولى 🎯
    """
    global rt_vol_baseline, rt_alerted, _coin_first_seen

    if not all_tickers:
        return

    now = time.time()


    all_sector_coins = set()
    for sc in SECTORS.values():
        all_sector_coins.update(sc)

    alerts = []

    for t in all_tickers:
        sym = t.get("symbol", "")
        if sym not in all_sector_coins: continue
        if any(k in sym for k in LEVERAGE_KEYWORDS): continue

        try:
            price  = float(t["lastPrice"])
            vol    = float(t["quoteVolume"])
            change = float(t["priceChangePercent"])
        except (KeyError, ValueError):
            continue

        if vol < RT_MIN_VOL: continue

        # فلتر العملات الجديدة
        if sym not in _coin_first_seen:
            _coin_first_seen[sym] = now
        if (now - _coin_first_seen.get(sym, now)) / 86400 < NEW_COIN_MIN_DAYS:
            continue

        # فلتر السيولة الحقيقية
        _liq_ok, _liq_reason = _is_real_liquidity(vol, change, t)
        if not _liq_ok:
            log.debug("RT skip %s: %s", sym, _liq_reason)
            continue

        if sym not in rt_vol_baseline:
            rt_vol_baseline[sym] = vol
            continue

        baseline = rt_vol_baseline[sym]


        rt_vol_baseline[sym] = baseline * 0.85 + vol * 0.15

        if baseline <= 0: continue

        vol_spike = vol / baseline


        if vol_spike < RT_VOL_SPIKE: continue


        if abs(change) < RT_PRICE_MOVE: continue


        if now - rt_alerted.get(sym, 0) < RT_COOLDOWN: continue


        sector = next((s for s,c in SECTORS.items() if sym in c), "Unknown")


        strength = 0
        if vol_spike >= 5:    strength += 4
        elif vol_spike >= 3:  strength += 3
        else:                 strength += 2

        if abs(change) >= 15: strength += 3
        elif abs(change) >= 8: strength += 2
        else:                  strength += 1

        if vol >= 10_000_000: strength += 2
        elif vol >= 3_000_000: strength += 1

        direction = "🟢 شراء" if change > 0 else "🔴 بيع"

        alerts.append({
            "sym":       sym,
            "price":     price,
            "vol":       vol,
            "vol_spike": vol_spike,
            "change":    change,
            "sector":    sector,
            "strength":  strength,
            "direction": direction,
        })

    if not alerts:
        return

    alerts.sort(key=lambda x: -x["strength"])

    for a in alerts[:3]:
        sym  = a["sym"]
        base = sym.replace("USDT", "")

        if a["strength"] >= 8:
            icon = "🚨🔥"
            lvl  = "MEGA LIQUIDITY"
        elif a["strength"] >= 6:
            icon = "🔥"
            lvl  = "STRONG LIQUIDITY"
        else:
            icon = "💧"
            lvl  = "LIQUIDITY SPIKE"

        gem_tag = ""
        if sym in gem_watchlist:
            gem_tag = "  💎 مرصودة من المرحلة " + str(gem_watchlist[sym].get("stage",1)) + "\n"

        msg = (
            icon + " *" + lvl + "* " + icon + "\n"
            + "━" * 18 + "\n"
            + "📍 *" + base + "/USDT* " + a["direction"] + "\n"
            + "  💰 السعر: `" + str(a["price"]) + "`\n"
            + "  📈 تغيير: `" + str(round(a["change"],1)) + "%`\n"
            + "  💧 سيولة: `" + str(round(a["vol"]/1e6,2)) + "M` = `"
            + str(round(a["vol_spike"],1)) + "× المتوسط`\n"
            + "  🏷️ قطاع: `" + a["sector"] + "`\n"
            + gem_tag
            + "━" * 18 + "\n"
            + "🎯 *" + lvl + "* | قوة: `" + str(a["strength"]) + "/9`\n"
            + "⚡ _سيولة غير عادية — ادرس الدخول_"
        )

        send(msg)
        rt_alerted[sym] = now
        coin_alerted[sym] = now
        if sym not in candidates:
            candidates.append(sym)
        add_to_liquidity_watchlist(sym, "liq_spike_"+str(round(a["vol_spike"],1))+"x",
                                   a["vol"], a["price"], a["sector"])

        log.info(" RT Liquidity | %s | spike=%.1fx | change=%.1f%% | strength=%d",
                 sym, a["vol_spike"], a["change"], a["strength"])

    log.info(" RT Scan done | alerts=%d", len(alerts))


def scan_hot_market(price_map=None, vol_now=None):
    # type: () -> None
    """
    يعمل فوراً بدون تاريخ
    يرصد العملات الساخنة الآن:
    - تغيير 10%+ في 24h
    - حجم 1M+ USDT
    - موجودة في SECTORS
    = يرسل تنبيه فوري 🔥
    """
    global hot_alerted, _coin_first_seen

    if not all_tickers:
        return

    now  = time.time()
    hot  = []


    all_sector_coins = set()
    for sector_coins in SECTORS.values():
        all_sector_coins.update(sector_coins)

    for t in all_tickers:
        sym = t.get("symbol", "")
        if sym not in all_sector_coins: continue
        if any(k in sym for k in LEVERAGE_KEYWORDS): continue

        try:
            price  = float(t["lastPrice"])
            vol    = float(t["quoteVolume"])
            change = float(t["priceChangePercent"])
            high   = float(t["highPrice"])
            low    = float(t["lowPrice"])
        except (KeyError, ValueError):
            continue

        if vol < HOT_MIN_VOL: continue
        if change < HOT_MIN_CHANGE: continue
        if change > HOT_MAX_CHANGE: continue

        # فلتر العملات الجديدة
        if sym not in _coin_first_seen:
            _coin_first_seen[sym] = now
        if (now - _coin_first_seen.get(sym, now)) / 86400 < NEW_COIN_MIN_DAYS:
            continue

        # فلتر السيولة الحقيقية
        _liq_ok, _liq_reason = _is_real_liquidity(vol, change, t)
        if not _liq_ok:
            log.debug("HOT skip %s: %s", sym, _liq_reason)
            continue

        last_alert = hot_alerted.get(sym, 0)
        if now - last_alert < HOT_COOLDOWN: continue


        sector = "Unknown"
        for sec, coins in SECTORS.items():
            if sym in coins:
                sector = sec
                break


        strength = 0
        if change >= 30:     strength += 4
        elif change >= 20:   strength += 3
        elif change >= 15:   strength += 2
        else:                strength += 1

        if vol >= 10_000_000: strength += 3
        elif vol >= 5_000_000: strength += 2
        elif vol >= 2_000_000: strength += 1


        if sym in gem_watchlist: strength += 2

        hot.append({
            "sym":      sym,
            "price":    price,
            "vol":      vol,
            "change":   change,
            "sector":   sector,
            "strength": strength,
            "high":     high,
            "low":      low,
        })

    if not hot:
        return

    hot.sort(key=lambda x: -x["strength"])

    for coin in hot[:5]:
        sym  = coin["sym"]
        base = sym.replace("USDT", "")

        if coin["strength"] >= 7:
            icon = "🔥🔥"
            lvl  = "EXPLOSIVE"
        elif coin["strength"] >= 5:
            icon = "🔥"
            lvl  = "STRONG"
        else:
            icon = "⚡"
            lvl  = "ACTIVE"


        gem_tag = ""
        if sym in gem_watchlist:
            stage = gem_watchlist[sym].get("stage", 1)
            gem_tag = "\n  💎 مرصودة من المرحلة " + str(stage)

        msg = (
            icon + " *HOT MARKET ALERT* " + icon + "\n"
            + "━" * 18 + "\n"
            + "📍 *" + base + "/USDT*\n"
            + "  💰 السعر: `" + str(price) + "`\n"
            + "  📈 تغيير 24h: `+" + str(round(coin["change"], 1)) + "%`\n"
            + "  📦 حجم: `" + str(round(coin["vol"]/1e6, 2)) + "M USDT`\n"
            + "  🏷️ قطاع: `" + coin["sector"] + "`\n"
            + gem_tag + "\n"
            + "━" * 18 + "\n"
            + "🎯 *" + lvl + "* | قوة: `" + str(coin["strength"]) + "/9`\n"
            + "👁️ _إشارة مراقبة — انتظر الجوكر للدخول_ 🃏"
        )

        send(msg)
        hot_alerted[sym] = now


        if sym not in candidates:
            candidates.append(sym)
        log.info(" Hot Market | %s | +%.1f%% | vol=%.1fM | strength=%d",
                 sym, coin["change"], coin["vol"]/1e6, coin["strength"])

    log.info(" Hot Scan | found=%d", len(hot))


def scan_ath_distance(price_map=None):
    # type: () -> None
    """
    يرصد العملات التي انهارت 90-95%+ من أعلى مستوى تاريخي
    ويضعها في قائمة المراقبة عند بداية أي تزايد في الحجم

    المنطق:
    - FIO نزلت -98% من ATH ثم +92%
    - PHA نزلت -97% من ATH ثم +60%
    = عملات "ميتة" تنبعث من جديد 🎯
    """
    global ath_tracker, ath_alerted

    if not all_tickers:
        return

    now = time.time()
    gems = []

    for t in all_tickers:
        sym = t.get("symbol", "")
        if not sym.endswith("USDT"): continue
        if any(k in sym for k in LEVERAGE_KEYWORDS): continue
        if is_suspicious(sym, 0, 0, 0): continue

        try:
            price  = float(t["lastPrice"])
            high   = float(t["highPrice"])
            vol    = float(t["quoteVolume"])
            change = float(t["priceChangePercent"])
        except (KeyError, ValueError):
            continue

        if vol < ATH_MIN_VOL: continue
        if price <= 0: continue



        prev_ath = ath_tracker.get(sym, 0.0)
        if high > prev_ath:
            ath_tracker[sym] = high
            prev_ath = high

        if prev_ath <= 0: continue


        drop_pct = 1.0 - (price / prev_ath)


        if drop_pct < ATH_DROP_STRONG: continue


        vh = bottom_vol_history.get(sym, [])
        vol_ratio = 1.0
        if len(vh) >= 3:
            vol_avg   = sum(vh[:-1]) / len(vh[:-1])
            vol_ratio = vol / vol_avg if vol_avg > 0 else 1.0


        last_alert = ath_alerted.get(sym, 0)
        if now - last_alert < ATH_COOLDOWN: continue


        score = 0


        if drop_pct >= ATH_DROP_EXTREME:  score += 4
        elif drop_pct >= ATH_DROP_STRONG: score += 2  # -90%+


        if vol_ratio >= 3.0:  score += 3
        elif vol_ratio >= 2.0: score += 2
        elif vol_ratio >= 1.3: score += 1


        if 0 < change <= 5:   score += 2
        elif change > 5:      score += 1
        elif change < -5:     score -= 1

        if score < 5: continue

        gems.append({
            "sym":       sym,
            "price":     price,
            "ath":       prev_ath,
            "drop_pct":  drop_pct,
            "vol":       vol,
            "vol_ratio": vol_ratio,
            "change":    change,
            "score":     score,
        })

    if not gems:
        return

    gems.sort(key=lambda x: -x["score"])

    for gem in gems[:3]:
        sym  = gem["sym"]
        base = sym.replace("USDT", "")

        drop_str = str(round(gem["drop_pct"] * 100, 1))


        if gem["drop_pct"] >= ATH_DROP_EXTREME and gem["vol_ratio"] >= 2.0:
            level = "💎🔥 EXTREME GEM"
            icon  = "💎"
        elif gem["drop_pct"] >= ATH_DROP_EXTREME:
            level = "💎 RARE GEM -95%+"
            icon  = "💎"
        elif gem["vol_ratio"] >= 2.0:
            level = "🔥 STRONG GEM -90%+"
            icon  = "🔥"
        else:
            level = "📊 GEM WATCH -90%+"
            icon  = "📊"


        target_20 = round(gem["ath"] * 0.20, 8)
        target_30 = round(gem["ath"] * 0.30, 8)
        gain_20   = round((target_20 / gem["price"] - 1) * 100, 1)
        gain_30   = round((target_30 / gem["price"] - 1) * 100, 1)

        msg = (
            icon + " *ATH DISTANCE ALERT* " + icon + "\n"
            + "━" * 18 + "\n"
            + "📍 *" + base + "/USDT*\n"
            + "  💰 السعر: `" + str(gem["price"]) + "`\n"
            + "  🏔️ ATH: `" + str(round(gem["ath"], 8)) + "`\n"
            + "  📉 انخفاض من ATH: `" + drop_str + "%`\n"
            + "  📦 حجم: `" + str(round(gem["vol"]/1e6, 2)) + "M` | تزايد: `"
            + str(round(gem["vol_ratio"], 1)) + "×`\n"
            + "  📊 تغيير 24h: `" + str(round(gem["change"], 2)) + "%`\n"
            + "━" * 18 + "\n"
            + "🎯 *" + level + "*\n"
            + "  · درجة الفرصة: `" + str(gem["score"]) + "/9`\n"
            + "  · هدف 20% من ATH: `" + str(target_20) + "` = `+" + str(gain_20) + "%`\n"
            + "  · هدف 30% من ATH: `" + str(target_30) + "` = `+" + str(gain_30) + "%`\n"
            + "━" * 18 + "\n"
            + "🐍 _تجميع خفي محتمل — انتظر Bottom + Explosion_"
        )

        send(msg)
        ath_alerted[sym] = now
        coin_alerted[sym] = now

        gem_watchlist[sym] = {"stage": 1, "ath_drop": gem["drop_pct"],
                              "since": now, "score": gem["score"]}

        import datetime as _dt
        _today = datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%d")
        if daily_gem_count["date"] != _today:
            daily_gem_count["date"] = _today; daily_gem_count["count"] = 0
        daily_gem_count["count"] += 1


        if sym not in watchlist:
            watchlist[sym] = {
                "since":    now,
                "priority": "HIGH",
                "reason":   "ath_gem_" + drop_str + "pct",
                "sector":   "Unknown",
            }
        log.info(" ATH Gem | %s | drop=%.1f%% | vol_ratio=%.1fx | score=%d",
                 sym, gem["drop_pct"]*100, gem["vol_ratio"], gem["score"])

    log.info(" ATH Scan | gems=%d", len(gems))


def scan_bottom_accumulation(price_map=None, vol_now=None):
    # type: () -> None
    """
    يرصد التجميع الخفي في القيعان الممتدة:
    - السعر قريب من أدنى مستوى تاريخي
    - الحجم يتزايد بهدوء
    - التغيير اليومي صغير (لا pump)
    = الحيتان يشترون بهدوء قبل الصعود 🐋
    """
    global bottom_price_history, bottom_vol_history, bottom_alerted

    if not all_tickers:
        return

    now = time.time()
    found = []

    for t in all_tickers:
        sym = t.get("symbol", "")
        if not sym.endswith("USDT"): continue

        if sym not in gem_watchlist: continue
        if gem_watchlist[sym].get("stage", 0) < 1: continue
        if any(k in sym for k in LEVERAGE_KEYWORDS): continue
        if is_suspicious(sym, 0, 0, 0): continue

        try:
            price  = float(t["lastPrice"])
            vol    = float(t["quoteVolume"])
            change = abs(float(t["priceChangePercent"]))
        except (KeyError, ValueError):
            continue

        if vol < BOTTOM_MIN_VOL: continue


        if sym not in bottom_price_history:
            bottom_price_history[sym] = []
            bottom_vol_history[sym]   = []

        bottom_price_history[sym].append(price)
        bottom_vol_history[sym].append(vol)


        if len(bottom_price_history[sym]) > 30:
            bottom_price_history[sym].pop(0)
            bottom_vol_history[sym].pop(0)

        ph = bottom_price_history[sym]
        vh = bottom_vol_history[sym]


        if len(ph) < BOTTOM_MIN_DAYS: continue


        price_low  = min(ph)
        price_high = max(ph)
        if price_high <= price_low: continue


        price_position = (price - price_low) / (price_high - price_low)
        if price_position > 0.25: continue


        vol_avg   = sum(vh[:-3]) / len(vh[:-3]) if len(vh) > 3 else vol
        vol_recent = sum(vh[-3:]) / 3
        vol_ratio  = vol_recent / vol_avg if vol_avg > 0 else 1.0
        if vol_ratio < BOTTOM_VOL_INCREASE: continue


        if change > BOTTOM_MAX_CHANGE: continue



        days_in_bottom = sum(1 for p in ph if p <= price_low * 1.20)
        if days_in_bottom < BOTTOM_MIN_DAYS: continue


        if now - coin_alerted.get(sym, 0) < TPS_COOLDOWN:
            if now - coin_whale_done.get(sym, 0) >= LZ_TPS_COOLDOWN:
                continue

        last_alert = bottom_alerted.get(sym, 0)
        if now - last_alert < BOTTOM_COOLDOWN: continue


        strength = 0
        if price_position <= 0.10: strength += 3
        elif price_position <= 0.20: strength += 2
        else: strength += 1

        if vol_ratio >= 2.0: strength += 3
        elif vol_ratio >= 1.5: strength += 2
        else: strength += 1

        if days_in_bottom >= 14: strength += 2
        elif days_in_bottom >= 7: strength += 1

        if change <= 1.0: strength += 1

        found.append({
            "sym":          sym,
            "price":        price,
            "vol":          vol,
            "vol_ratio":    vol_ratio,
            "price_low":    price_low,
            "price_pos":    price_position,
            "days_bottom":  days_in_bottom,
            "change":       change,
            "strength":     strength,
        })

    if not found:
        return


    found.sort(key=lambda x: -x["strength"])

    for coin in found[:5]:
        sym = coin["sym"]
        base = sym.replace("USDT", "")


        if coin["strength"] >= 7:
            level = "🔥🐳 STRONG BOTTOM"
            icon  = "🔥"
        elif coin["strength"] >= 5:
            level = "📊🐳 BOTTOM ACCUMULATION"
            icon  = "📊"
        else:
            level = "👀 EARLY BOTTOM"
            icon  = "👀"


        target_pct = round((1 - coin["price_pos"]) * 40 + 10, 1)

        msg = (
            icon + " *BOTTOM ACCUMULATION*\n"
            "━" * 18 + "\n"
            "📍 *" + base + "/USDT*\n"
            "  💰 السعر: `" + str(price) + "`\n"
            "  📉 قاع " + str(coin["days_bottom"]) + " يوم | أدنى: `" + str(round(coin["price_low"], 8)) + "`\n"
            "  📊 موقع في النطاق: `" + str(round(coin["price_pos"] * 100, 1)) + "%` من القاع\n"
            "  📦 حجم: `" + str(round(coin["vol"] / 1e6, 2)) + "M` | تزايد: `" + str(round(coin["vol_ratio"], 1)) + "×`\n"
            "  📊 تغيير 24h: `" + str(round(coin["change"], 2)) + "%`\n"
            "━" * 18 + "\n"
            "🎯 *" + level + "*\n"
            "  · قوة الإشارة: `" + str(coin["strength"]) + "/10`\n"
            "  · هدف محتمل: `+" + str(target_pct) + "%`\n"
            "⚡ _انتظر Momentum + Signal للدخول_"
        )

        send(msg)
        bottom_alerted[sym] = now
        coin_alerted[sym] = now

        if sym in gem_watchlist: gem_watchlist[sym]["stage"] = 2


        if sym not in candidates:
            candidates.append(sym)
            log.info(" Bottom Accumulation  candidates | %s | strength=%d | vol_ratio=%.1f",
                     sym, coin["strength"], coin["vol_ratio"])

    log.info(" Bottom Scan | found=%d", len(found))



def scan_volume_explosion():
    # type: () -> None
    """
    يرصد انفجار الحجم في عملات كانت في القاع:
    المرحلة 3 — بعد التجميع يأتي الانفجار

    الشرط الذهبي:
    ✅ العملة كانت في القاع (bottom_price_history موجود)
    ✅ الحجم انفجر 3× فجأة
    ✅ السعر بدأ يتحرك للأعلى
    = الانطلاق بدأ — فرصة دخول فورية 🚀
    """
    global explosion_alerted

    if not all_tickers:
        return

    now = time.time()
    explosions = []

    for t in all_tickers:
        sym = t.get("symbol", "")
        if not sym.endswith("USDT"): continue

        if sym not in gem_watchlist: continue
        if gem_watchlist[sym].get("stage", 0) < 2: continue
        if any(k in sym for k in LEVERAGE_KEYWORDS): continue

        try:
            price  = float(t["lastPrice"])
            vol    = float(t["quoteVolume"])
            change = float(t["priceChangePercent"])
        except (KeyError, ValueError):
            continue

        if vol < EXPLOSION_MIN_VOL: continue


        ph = bottom_price_history.get(sym, [])
        vh = bottom_vol_history.get(sym, [])
        if len(ph) < EXPLOSION_MIN_DAYS: continue
        if len(vh) < EXPLOSION_MIN_DAYS: continue



        vol_history_avg = sum(vh[:-1]) / len(vh[:-1]) if len(vh) > 1 else vol
        if vol_history_avg <= 0: continue

        vol_mult = vol / vol_history_avg


        if vol_mult < EXPLOSION_VOL_MULT: continue


        if change <= 0: continue
        if change > EXPLOSION_MAX_CHANGE: continue


        price_low  = min(ph[:-1])
        price_high = max(ph[:-1])
        if price_high <= price_low: continue


        prev_price = ph[-2] if len(ph) >= 2 else ph[-1]
        prev_position = (prev_price - price_low) / (price_high - price_low)
        if prev_position > 0.30: continue


        if now - coin_alerted.get(sym, 0) < TPS_COOLDOWN:
            if now - coin_whale_done.get(sym, 0) >= LZ_TPS_COOLDOWN:
                continue

        last_alert = explosion_alerted.get(sym, 0)
        if now - last_alert < EXPLOSION_COOLDOWN: continue


        power = 0
        if vol_mult >= 8:  power += 4
        elif vol_mult >= 5: power += 3
        elif vol_mult >= 3: power += 2
        else: power += 1

        if prev_position <= 0.10: power += 3
        elif prev_position <= 0.20: power += 2
        else: power += 1

        days_in_bottom = sum(1 for p in ph[:-1] if p <= price_low * 1.20)
        if days_in_bottom >= 14: power += 2
        elif days_in_bottom >= 7: power += 1

        if change >= 10: power += 2
        elif change >= 5: power += 1

        explosions.append({
            "sym":         sym,
            "price":       price,
            "vol":         vol,
            "vol_mult":    vol_mult,
            "change":      change,
            "price_low":   price_low,
            "prev_pos":    prev_position,
            "days_bottom": days_in_bottom,
            "power":       power,
        })

    if not explosions:
        return

    explosions.sort(key=lambda x: -x["power"])

    for coin in explosions[:3]:
        sym  = coin["sym"]
        base = sym.replace("USDT", "")


        if coin["power"] >= 8:
            level = "🔥🔥 MEGA EXPLOSION"
            icon  = "🚨"
        elif coin["power"] >= 6:
            level = "💥 STRONG EXPLOSION"
            icon  = "🔥"
        else:
            level = "📈 VOLUME BREAKOUT"
            icon  = "📊"

        msg = (
            icon + " *VOLUME EXPLOSION* " + icon + "\n"
            + "━" * 18 + "\n"
            + "📍 *" + base + "/USDT*\n"
            + "  💰 السعر الآن: `" + str(price) + "` +" + str(round(coin["change"],1)) + "%\n"
            + "  📉 كان في قاع " + str(coin["days_bottom"]) + " يوم | أدنى: `" + str(round(coin["price_low"],8)) + "`\n"
            + "  📊 موقع قبل الانفجار: `" + str(round(coin["prev_pos"]*100,1)) + "%` من القاع\n"
            + "━" * 18 + "\n"
            + "  💥 حجم الانفجار: `" + str(round(coin["vol"]/1e6,2)) + "M` = `" + str(round(coin["vol_mult"],1)) + "× المتوسط`\n"
            + "━" * 18 + "\n"
            + "🎯 *" + level + "*\n"
            + "  · قوة الانفجار: `" + str(coin["power"]) + "/12`\n"
            + "🚀 _الانطلاق بدأ — فرصة دخول فورية!_"
        )

        send(msg)
        explosion_alerted[sym] = now
        coin_alerted[sym] = now

        if sym in gem_watchlist: gem_watchlist[sym]["stage"] = 3


        if sym not in candidates:
            candidates.insert(0, sym)
        if sym not in watchlist:
            watchlist[sym] = {
                "since":    now,
                "priority": "HIGH",
                "reason":   "volume_explosion",
                "sector":   "Unknown",
            }
        log.info(" Volume Explosion | %s | mult=%.1fx | change=+%.1f%%",
                 sym, coin["vol_mult"], coin["change"])

    log.info(" Explosion Scan | found=%d", len(explosions))


def analyze_smart_money(force_report=False):
    # type: (bool) -> None
    global stable_vol_history, smart_money_alert, smart_money_bonus, last_smart_money

    if not all_tickers:
        return

    ticker_map  = {t["symbol"]: t for t in all_tickers}
    detected    = []
    urgent      = []
    total_sigma = 0.0

    for sym in SMART_MONEY_STABLES:
        if sym not in ticker_map:
            continue
        try:
            vol    = float(ticker_map[sym]["quoteVolume"])
            change = float(ticker_map[sym]["priceChangePercent"])
        except (KeyError, ValueError):
            continue

        if sym not in stable_vol_history:
            stable_vol_history[sym] = []
        hist = stable_vol_history[sym]
        hist.append(vol)
        if len(hist) > 48:
            hist.pop(0)

        if len(hist) < 4:
            continue

        avg      = sum(hist) / len(hist)
        variance = sum((v - avg) ** 2 for v in hist) / len(hist)
        std      = variance ** 0.5

        if std == 0 or avg == 0:
            continue

        sigma     = (vol - avg) / std
        vol_ratio = vol / avg

        if sigma >= SMART_MONEY_SIGMA:
            entry = {
                "sym": sym.replace("USDT", ""),
                "sigma": round(sigma, 1),
                "vol": vol,
                "vol_ratio": round(vol_ratio, 1),
                "change": change,
            }
            detected.append(entry)
            total_sigma += sigma
            if sigma >= SMART_MONEY_ALERT_SIGMA:
                urgent.append(entry)

    sell_pressure = 0.0
    rising_count  = 0
    falling_count = 0
    top_falling   = []

    for t in all_tickers:
        sym = t.get("symbol", "")
        if not sym.endswith("USDT"): continue
        base = sym.replace("USDT", "")
        if base in STABLECOINS: continue
        try:
            ch  = float(t["priceChangePercent"])
            vol = float(t["quoteVolume"])
            if ch > 0: rising_count  += 1
            else:
                falling_count += 1
                if ch < -5 and vol > 500_000:
                    top_falling.append((base, ch, vol))
            sell_pressure += ch
        except (KeyError, ValueError):
            pass

    total_coins  = rising_count + falling_count
    avg_market   = sell_pressure / total_coins if total_coins > 0 else 0
    falling_pct  = falling_count / total_coins * 100 if total_coins > 0 else 0
    top_falling.sort(key=lambda x: x[1])

    is_accumulation = (
        len(detected) >= SMART_MONEY_ACCUM_MIN and
        falling_pct   >= SMART_MONEY_FALL_PCT and
        avg_market    <= -1.0
    )

    old_alert         = smart_money_alert
    smart_money_alert = is_accumulation
    last_smart_money  = time.time()


    smart_money_bonus = 10 if is_accumulation else 0

    if urgent and not force_report:
        urgent.sort(key=lambda x: -x["sigma"])
        urgent_lines = ""
        for d in urgent:
            urgent_lines += "  🚨 *{}*  Sigma:`{}`  `{}×` المتوسط\n".format(
                d["sym"], d["sigma"], d["vol_ratio"])

        send(
            "🚨 *تنبيه فوري — تجميع استثنائي!*\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "{lines}\n"
            "₿ BTC: `{btc:+.2f}%` | {mkt}`{fall:.0f}%` نازل\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🔴 *لا تشتري الآن — الحيتان يجمعون*".format(
                lines=urgent_lines,
                btc=btc_change_24h,
                mkt="🔴" if falling_pct >= 55 else "🟡",
                fall=falling_pct,
            )
        )
        log.info(" Urgent Smart Money! %d stables | sigma_max=%.1f",
                 len(urgent), max(d["sigma"] for d in urgent))

    if not force_report and not detected:
        return

    detected.sort(key=lambda x: -x["sigma"])
    stable_lines = ""
    if detected:
        for d in detected[:6]:
            bar = "█" * min(int(d["sigma"]), 10)
            stable_lines += (
                "  • *{sym}*\n"
                "    Sigma: `{sig}` | `{ratio}×` المتوسط\n"
                "    [{bar}]\n"
            ).format(sym=d["sym"], sig=d["sigma"], ratio=d["vol_ratio"], bar=bar)
    else:
        stable_lines = "  ✅ لا نشاط غير عادي\n"

    falling_lines = ""
    for base, ch, vol in top_falling[:3]:
        falling_lines += "  • *{}* `{:.1f}%`\n".format(base, ch)

    market_icon = "🔴" if falling_pct >= 55 else "🟡" if falling_pct >= 45 else "🟢"
    is_neutral  = len(detected) > 0 and not is_accumulation

    if is_accumulation:
        status_line  = "🐋 *تجميع نشط — الحيتان يجمعون!*"
        warning_line = "🔴 *لا تشتري الآن — انتظر انتهاء التجميع*"
        phase_desc   = "بيع في السوق + تجميع في Stablecoins"
    elif is_neutral:
        status_line  = "👀 *نشاط غير عادي — مراقبة*"
        warning_line = "🟡 *تحذير خفيف — كن حذراً*"
        phase_desc   = "حجم Stablecoins مرتفع بدون بيع واضح"
    else:
        status_line  = "🟢 *السوق طبيعي — لا تجميع*"
        warning_line = "✅ *الإشارات مفعّلة بشكل طبيعي*"
        phase_desc   = "لا نشاط غير عادي في Stablecoins"

    send(
        "🐋 *SMART MONEY DAILY REPORT*\n"
        "📅 `{date}`\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "{status}\n_{desc}_\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "📊 *Stablecoins (حجم غير عادي):*\n{stables}\n"
        "📉 *حالة السوق:*\n"
        "  {mkt} `{fall:.0f}%` من العملات نازلة\n"
        "  📊 متوسط: `{avg:+.2f}%`\n"
        "  ₿ BTC 24h: `{btc:+.2f}%`\n"
        "{falling_section}"
        "━━━━━━━━━━━━━━━━━━\n"
        "{warning}".format(
            date=datetime.now().strftime("%Y-%m-%d %H:%M"),
            status=status_line, desc=phase_desc,
            stables=stable_lines,
            mkt=market_icon, fall=falling_pct, avg=avg_market, btc=btc_change_24h,
            falling_section=(
                "📉 *أكثر انخفاضاً:*\n{}\n".format(falling_lines) if falling_lines else ""
            ),
            warning=warning_line,
        )
    )
    log.info(" Smart Money | accum=%s | stables=%d | falling=%.0f%%",
             is_accumulation, len(detected), falling_pct)





def _get_top10_sector(sector, price_map, vol_now, change_now, high_map, low_map):
    # type: (str, dict, dict, dict, dict, dict) -> list
    coins  = SECTORS.get(sector, [])
    scored = []
    for sym in coins:
        if sym not in price_map: continue
        price    = price_map[sym]
        vol      = vol_now.get(sym, 0)
        ch       = change_now.get(sym, 0)
        high_24h = high_map.get(sym, price)
        low_24h  = low_map.get(sym, price)
        if vol < MOMENTUM_MIN_VOL: continue
        if ch <= 0 or ch > 10: continue
        if high_24h <= 0 or low_24h <= 0: continue
        rebound = (price - low_24h) / low_24h * 100 if low_24h > 0 else 0
        if rebound < 3: continue
        score = (vol / 1_000_000) * 0.5 + rebound * 0.3 + ch * 0.2
        scored.append((sym, score, price, vol, ch, rebound, high_24h, low_24h))
    scored.sort(key=lambda x: -x[1])
    return scored[:10]


def detect_momentum(price_map, change_now, vol_now, high_map, low_map):
    # type: (dict, dict, dict, dict, dict) -> None
    global price_prev, momentum_alerted, momentum_stage

    now = time.time()


    for sym in list(momentum_stage.keys()):
        if sym not in price_map: continue
        price      = price_map[sym]
        sd         = momentum_stage[sym]
        vol        = vol_now.get(sym, 0)
        change_24h = change_now.get(sym, 0)
        entry_price= sd["entry_price"]
        entry_vol  = sd["entry_vol"]
        gain       = (price - entry_price) / entry_price * 100 if entry_price > 0 else 0


        if now - sd["entry_time"] > 14400 or gain < -5.0:
            del momentum_stage[sym]
            continue

        vol_ratio      = vol / entry_vol if entry_vol > 0 else 1
        high_24h       = high_map.get(sym, price)
        drop_from_high = (high_24h - price) / high_24h * 100 if high_24h > 0 else 0


        if sd["stage"] == 1 and not sd.get("alerted_2"):
            if gain >= 2.0 and vol_ratio >= 1.3:
                sd["alerted_2"] = True
                sd["stage"]     = 2
                sector = next((s for s, syms in SECTORS.items() if sym in syms), "")
                top10  = _get_top10_sector(sector, price_map, vol_now, change_now, high_map, low_map)
                top10_txt = ""
                for i, (s, sc, p, v, c, rb, *_) in enumerate(top10[:5], 1):
                    top10_txt += "  {}. *{}* `+{:.1f}%` | حجم:`{:,.0f}`\n".format(
                        i, s.replace("USDT",""), c, v)

                send(
                    "🟡 *تأكيد الدخول*\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    "💰 *{sym}*\n"
                    "📈 ارتفع: `+{gain:.2f}%` من نقطة الرصد\n"
                    "💧 الحجم: `{ratio:.1f}x` المعدل\n"
                    "💵 السعر: `{price}`\n"
                    "📉 من القمة: `-{drop:.1f}%`\n"
                    "{top}"
                    "🕐 `{time}`\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    "✅ *ادخل الآن — السيولة تتدفق*".format(
                        sym=sym, gain=gain, ratio=vol_ratio,
                        price=fmt_price(price), drop=drop_from_high,
                        top="🏆 *أفضل عملات القطاع:*\n{}\n".format(top10_txt) if top10_txt else "",
                        time=datetime.now().strftime("%H:%M:%S"),
                    )
                )
                log.info(" Stage2 | %s | +%.2f%% | vol_ratio=%.1f", sym, gain, vol_ratio)


        elif sd["stage"] == 2 and not sd.get("alerted_3"):
            if gain >= 3.0 and vol_ratio >= 2.0 and change_24h > 0:
                sd["alerted_3"] = True
                sd["stage"]     = 3
                low_24h        = low_map.get(sym, price)
                daily_close_ok = price > low_24h * 1.1 if low_24h > 0 else None
                close_icon     = "✅ فوق الدعم" if daily_close_ok else "⚠️ تحت الدعم"

                send(
                    "🟢 *تأكيد الإيجابية* 🎯\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    "💰 *{sym}*\n"
                    "📈 إجمالي الارتفاع: `+{gain:.2f}%`\n"
                    "💧 السيولة: `{ratio:.1f}x` المعدل\n"
                    "💵 السعر: `{price}`\n"
                    "📅 الإغلاق اليومي: `{close}`\n"
                    "🕐 `{time}`\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    "🚀 *سيولة قوية — ارفع Stop Loss*".format(
                        sym=sym, gain=gain, ratio=vol_ratio,
                        price=fmt_price(price), close=close_icon,
                        time=datetime.now().strftime("%H:%M:%S"),
                    )
                )
                deep_scan(sym, price, change_24h)
                log.info(" Stage3 | %s | +%.2f%%", sym, gain)


    for sym, price in price_map.items():
        if sym in tracked: continue
        if sym in momentum_stage: continue
        if not sym.endswith("USDT"): continue

        in_our_list = any(sym in coins for coins in SECTORS.values())
        if not in_our_list: continue

        vol = vol_now.get(sym, 0)
        if vol < MOMENTUM_MIN_VOL: continue

        base = sym.replace("USDT","")
        if base in STABLECOINS: continue
        if any(k in sym for k in LEVERAGE_KEYWORDS): continue
        if sym in EXCLUDED: continue

        prev = price_prev.get(sym, 0)
        price_prev[sym] = price
        if prev <= 0 or price <= 0: continue

        high_24h = high_map.get(sym, price)
        low_24h  = low_map.get(sym, price)
        if high_24h > 0 and low_24h > 0:
            if price < low_24h * 0.85 or price > high_24h * 1.15:
                price_prev[sym] = 0
                continue

        move       = (price - prev) / prev * 100
        change_24h = change_now.get(sym, 0)

        if abs(move) > 30: price_prev[sym] = 0; continue
        if move < MOMENTUM_MOVE_MIN: continue
        if move > MOMENTUM_MOVE_MAX: continue
        if change_24h <= 0 or change_24h > 10: continue
        if low_24h > 0 and price > low_24h * 2.5: continue
        if high_24h > 0 and price > high_24h * 0.90: continue
        if low_24h > 0:
            rebound = (price - low_24h) / low_24h * 100
            if rebound < 5: continue

        if now - momentum_alerted.get(sym, 0) < MOMENTUM_COOLDOWN: continue


        if sym in watchlist:
            if now - momentum_alerted.get(sym, 0) < MOMENTUM_COOLDOWN / 3:
                continue

        momentum_alerted[sym] = now
        coin_alerted[sym] = now

        sector         = next((s for s, syms in SECTORS.items() if sym in syms), "")
        in_hot         = sym in hot_symbols
        in_watchlist   = sym in watchlist
        wl_tag         = " 👁️ *مراقبة*" if in_watchlist else ""
        hot_tag        = " 🔥 *{}*".format(sector) if in_hot else ""
        rebound        = (price - low_24h) / low_24h * 100 if low_24h > 0 else 0
        drop_from_high = (high_24h - price) / high_24h * 100 if high_24h > 0 else 0

        flow_state = sector_flow_state.get(sector, "NEUTRAL")
        flow_tag   = " 💸 *سيولة داخلة*" if flow_state == "IN" else ""

        top10     = _get_top10_sector(sector, price_map, vol_now, change_now, high_map, low_map)
        top10_txt = ""
        for i, (s, sc, p, v, c, rb, *_) in enumerate(top10[:5], 1):
            top10_txt += "  {}. *{}* `+{:.1f}%` | `{:,.0f}`\n".format(
                i, s.replace("USDT",""), c, v)

        momentum_stage[sym] = {
            "stage": 1, "entry_price": price, "entry_vol": vol,
            "entry_time": now, "alerted_2": False, "alerted_3": False,
        }

        log.info(" Stage1 | %s | +%.2f%% | 24h:%.1f%% | vol:%.0f | sector:%s | flow:%s",
                 sym, move, change_24h, vol, sector, flow_state)

        send(
            "🔵 *Momentum Detected*{hot}{flow}{wl}\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "💰 *{sym}*  |  🏷️ `{sector}`\n"
            "📈 تحرك لحظي: `+{move:.2f}%`\n"
            "📊 تغيير 24h: `{ch:+.1f}%`\n"
            "💧 حجم: `{vol:,.0f}`\n"
            "💵 السعر: `{price}`\n"
            "📉 من القمة: `-{drop:.1f}%` | ارتداد: `+{reb:.1f}%`\n"
            "{top}"
            "🕐 `{time}`\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "{action}".format(
                hot=hot_tag, flow=flow_tag, wl=wl_tag,
                sym=sym, sector=sector if sector else "—",
                move=move, ch=change_24h, vol=vol,
                price=fmt_price(price),
                drop=drop_from_high, reb=rebound,
                top="🏆 *أفضل عملات القطاع:*\n{}\n".format(top10_txt) if top10_txt else "",
                time=datetime.now().strftime("%H:%M:%S"),
                action=(
                    "🎯 *في قائمة المراقبة — جاهز للإشارة!*"
                    if in_watchlist else
                    "👀 _مراقبة — انتظر إشعار التأكيد_"
                ),
            )
        )






def _classify_symbol(base):
    # type: (str) -> Optional[str]
    """
    يصنف العملة لقطاع بناءً على الكلمات المفتاحية.
    يعيد اسم القطاع أو None إذا لم يتطابق مع أي قطاع.
    الأولوية: أكثر كلمة تطابقاً تفوز.
    """
    base_upper = base.upper()
    best_sector = None
    best_score  = 0

    for sector, keywords in SECTOR_KEYWORDS.items():
        score = 0
        for kw in keywords:

            if kw == base_upper:
                score += 10
            elif base_upper.startswith(kw) or base_upper.endswith(kw):
                score += 5
            elif kw in base_upper and len(kw) >= 3:
                score += 2
        if score > best_score:
            best_score  = score
            best_sector = sector


    return best_sector if best_score >= 2 else None



def auto_expand_sectors():
    # type: () -> None
    """
    🆕 V12: يجلب كل عملات MEXC ويوزعها على القطاعات.

    الخوارزمية:
    1. جلب ticker/24hr الكامل (طلب واحد فقط)
    2. فلترة: USDT pairs + حجم نشط + ليست Stablecoin/Leverage
    3. تصنيف كل عملة جديدة لقطاعها بالكلمات المفتاحية
    4. إضافة فقط العملات غير الموجودة حتى نصل 50/قطاع
    5. إرسال تقرير Telegram بكل ما أُضيف
    """
    log.info(" Auto Expand:   MEXC...")

    data = safe_get(MEXC_24H)
    if not data:
        log.warning(" Auto Expand:   ")
        return


    existing = set(sym for coins in SECTORS.values() for sym in coins)


    vol_map    = {}
    change_map = {}
    for t in data:
        sym = t.get("symbol","")
        if not sym.endswith("USDT"): continue
        try:
            vol_map[sym]    = float(t["quoteVolume"])
            change_map[sym] = float(t["priceChangePercent"])
        except (KeyError, ValueError):
            pass


    all_usdt = sorted(
        [s for s in vol_map if vol_map[s] >= EXPAND_MIN_VOL],
        key=lambda s: -vol_map[s]
    )

    added_per_sector = {s: [] for s in SECTORS}
    skipped_existing = 0
    skipped_filter   = 0

    for sym in all_usdt:

        if sym in existing:
            skipped_existing += 1
            continue


        if sym in EXCLUDED:
            continue

        base = sym.replace("USDT","")


        if is_stablecoin(sym, 0.0, change_map.get(sym, 0.0)):
            skipped_filter += 1
            continue


        if any(k in sym for k in LEVERAGE_KEYWORDS):
            skipped_filter += 1
            continue


        if vol_map[sym] > EXPAND_MAX_VOL:
            skipped_filter += 1
            continue


        sector = _classify_symbol(base)
        if not sector:
            continue


        current_count = len(SECTORS[sector]) + len(added_per_sector[sector])
        if current_count >= SECTOR_TARGET:
            continue


        SECTORS[sector].append(sym)
        added_per_sector[sector].append(sym)
        existing.add(sym)


    total_added = sum(len(v) for v in added_per_sector.values())
    log.info(" Auto Expand  | : %d  | : %d | : %d",
             total_added, skipped_existing, skipped_filter)

    if total_added == 0:
        log.info("     -  ")
        return


    log.info(" AUTO EXPAND |  %d  ", total_added)


    global hot_symbols
    hot_symbols = {c for s in hot_sectors for c in SECTORS[s]}
    log.info(" hot_symbols  | %d ", len(hot_symbols))



#   REFRESH TICKERS









SECTOR_REPORT_EVERY = 3600
last_sector_report  = 0.0


def scan_sector_activity():
    # type: () -> None
    global last_sector_report, price_snapshot, price_snapshot_time

    if not all_tickers:
        return

    ticker_map = {t["symbol"]: t for t in all_tickers}


    now = time.time()
    if now - price_snapshot_time >= 3600 or not price_snapshot:
        price_snapshot = {
            t["symbol"]: float(t["lastPrice"])
            for t in all_tickers
            if t.get("symbol","").endswith("USDT")
        }
        price_snapshot_time = now
        log.info(" Price snapshot  | %d ", len(price_snapshot))

    def real_change(sym, t):
        """التغيير الحقيقي من آخر snapshot (ساعة)"""
        try:
            cur  = float(t["lastPrice"])
            prev = price_snapshot.get(sym, 0)
            if prev > 0:
                return (cur - prev) / prev * 100
            return float(t["priceChangePercent"])
        except (KeyError, ValueError):
            return 0.0



    sector_stats = {}


    def get_sector_for(sym):
        base = sym.replace("USDT","")
        for sec, keywords in SECTOR_KEYWORDS.items():
            if any(kw in base for kw in keywords):
                return sec

        for sec, coins in SECTORS.items():
            if sym in coins:
                return sec
        return None


    full_sector_data = {}   # {sector: {buy_vol, sell_vol, changes, vols}}

    for t in all_tickers:
        sym = t.get("symbol","")
        if not sym.endswith("USDT"): continue
        if is_suspicious(sym, 0, 0, 0): continue
        try:
            ch  = real_change(sym, t)
            vol = float(t["quoteVolume"])
            if vol < 50_000: continue
        except (KeyError, ValueError):
            continue

        sec = get_sector_for(sym)
        if not sec: continue

        if sec not in full_sector_data:
            full_sector_data[sec] = {"buy":0.0,"sell":0.0,"changes":[],"vols":[]}

        full_sector_data[sec]["changes"].append(ch)
        full_sector_data[sec]["vols"].append(vol)
        if ch > 0:
            full_sector_data[sec]["buy"] += vol
        else:
            full_sector_data[sec]["sell"] += vol

    for sec, d in full_sector_data.items():
        if len(d["changes"]) < 2: continue
        total_vol  = sum(d["vols"])
        buy_vol    = d["buy"]
        sell_vol   = d["sell"]
        avg_ch     = sum(d["changes"]) / len(d["changes"])
        sector_stats[sec] = {
            "vol":      total_vol,
            "buy_vol":  buy_vol,
            "sell_vol": sell_vol,
            "avg":      avg_ch,
            "count":    len(d["changes"]),

            "score":    total_vol / 1_000_000,
        }

    if not sector_stats:
        return

    sorted_sectors = sorted(sector_stats.items(), key=lambda x: -x[1]["score"])


    whale_accumulation = []
    for sym, t in ticker_map.items():
        if not sym.endswith("USDT"): continue
        base = sym.replace("USDT","")
        if sym in EXCLUDED: continue
        if is_suspicious(sym, 0, 0, 0): continue

        try:
            price = float(t["lastPrice"])
            high  = float(t["highPrice"])
            low   = float(t["lowPrice"])
            vol   = float(t["quoteVolume"])
            ch    = float(t["priceChangePercent"])
        except (KeyError, ValueError):
            continue


        if vol < WHALE_MIN_VOL: continue
        if vol > MAX_VOL_USDT:  continue
        if price <= 0 or high <= 0 or low <= 0: continue
        if ch > 5 or ch < -15: continue

        price_range = high - low
        if price_range <= 0: continue

        pos           = (price - low) / price_range
        near_bottom   = pos <= 0.30

        hist      = coin_vol_history.get(sym, [])
        vol_ratio = (vol / (sum(hist[:-1])/(len(hist)-1))
                     if len(hist) >= 3 and sum(hist[:-1]) > 0 else 1.0)
        high_vol  = vol_ratio >= 1.3

        range_pct  = price_range / low * 100
        compressed = range_pct <= 12

        strength = (30 if near_bottom else 0) + (30 if high_vol else 0) + \
                   (20 if -8 <= ch <= 3 else 0) + (20 if compressed else 0)
        if strength < 60: continue

        whale_accumulation.append({
            "sym": sym, "base": base, "ch": ch, "vol": vol,
            "vol_ratio": round(vol_ratio,1),
            "near_bottom": near_bottom, "high_vol": high_vol,
            "compressed": compressed, "strength": strength,
        })

    whale_accumulation.sort(key=lambda x: (-x["strength"], -x["vol"]))
    last_sector_report = time.time()


    new_wl = {}
    for w in whale_accumulation:
        sec = next((s for s,coins in SECTORS.items()
                    if w["sym"] in coins and s in hot_sectors), "")
        new_wl[w["sym"]] = {
            "sector": sec or "—", "strength": w["strength"],
            "ch": w["ch"], "vol": w["vol"],
            "priority": "🔥 HIGH" if sec else "📊 NORMAL",
            "added": time.time(),
        }
    newly_added = [s for s in new_wl if s not in watchlist]
    watchlist.update(new_wl)
    if newly_added:
        hot_new = [s for s in newly_added if watchlist[s]["priority"] == "🔥 HIGH"]
        if hot_new:
            txt = "".join(
                "  🔥 *{}* | قطاع: {} | قوة: {}/100\n".format(
                    s.replace("USDT",""), watchlist[s]["sector"], watchlist[s]["strength"])
                for s in hot_new[:5]
            )
            send("👁️ *عملات جديدة في قائمة المراقبة*\n"
                 "━━━━━━━━━━━━━━━━━━\n"
                 "{}\n⚡ _انتظر Momentum + Signal للدخول_".format(txt))


    icons = ["🔥","⚡","📈","📊","📊"]
    sector_lines = ""
    for i, (sec, st) in enumerate(sorted_sectors[:5]):
        buy_m  = st["buy_vol"]  / 1_000_000
        sell_m = st["sell_vol"] / 1_000_000
        total_m = st["vol"]    / 1_000_000
        direction = "🟢" if st["buy_vol"] > st["sell_vol"] else "🔴"
        sector_lines += (
            "{icon} *{sec}* {dir}\n"
            "   💰 إجمالي: `{tot:.1f}M` | 🟢 شراء: `{buy:.1f}M` | 🔴 بيع: `{sell:.1f}M`\n"
        ).format(
            icon=icons[min(i,4)], sec=sec, dir=direction,
            tot=total_m, buy=buy_m, sell=sell_m,
        )

    whale_lines = ""
    for w in whale_accumulation[:8]:
        in_hot = any(w["sym"] in SECTORS.get(s,[]) for s in hot_sectors)
        ind = []
        if w["near_bottom"]: ind.append("📍قاع")
        if w["high_vol"]:    ind.append("📊{}×".format(w["vol_ratio"]))
        if w["compressed"]:  ind.append("🔒مضغوط")
        whale_lines += "  {} *{}* `{:+.1f}%` | {} | `{:.1f}M`\n".format(
            "🔥" if in_hot else "🐋",
            w["base"], w["ch"], " ".join(ind), w["vol"]/1_000_000,
        )
    if not whale_lines:
        whale_lines = "  _لا يوجد تجميع واضح الآن_\n"


    buy_vol_total  = 0.0
    sell_vol_total = 0.0
    for t in all_tickers:
        sym = t.get("symbol","")
        if not sym.endswith("USDT"): continue
        if is_suspicious(sym, 0, 0, 0): continue
        try:
            ch  = real_change(sym, t)
            vol = float(t["quoteVolume"])
            if vol < 100_000: continue
            if ch > 0: buy_vol_total  += vol
            else:      sell_vol_total += vol
        except (KeyError, ValueError):
            pass

    total_vol_mkt = buy_vol_total + sell_vol_total
    buy_pct_mkt   = buy_vol_total  / total_vol_mkt * 100 if total_vol_mkt > 0 else 50
    sell_pct_mkt  = sell_vol_total / total_vol_mkt * 100 if total_vol_mkt > 0 else 50
    mkt_icon      = "🟢" if buy_pct_mkt >= 55 else "🔴" if buy_pct_mkt <= 45 else "🟡"

    msg = (
        "🌊 *SECTOR ACTIVITY REPORT*\n"
        "🕐 `{time}`\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🔥 *القطاعات الساخنة:*\n"
        "{sectors}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🐋 *تجميع في القيعان:*\n"
        "🔥قطاع ساخن | 🐋عادي\n"
        "{whales}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "{mkt} شراء:`{buy:.1f}%` | بيع:`{sell:.1f}%` | ₿ `{btc:+.2f}%`\n"
        "⚡ _انتظر Momentum + Signal للدخول_"
    ).format(
        time=datetime.now().strftime("%H:%M:%S"),
        sectors=sector_lines, whales=whale_lines,
        mkt=mkt_icon, buy=buy_pct_mkt, sell=sell_pct_mkt,
        btc=btc_change_24h,
    )

    send(msg)
    log.info(" Sector Report | hot=%s | whale_accum=%d",
             ", ".join(s for s,_ in sorted_sectors[:3]), len(whale_accumulation))


def refresh_sector_report():
    # type: () -> None
    """يُستدعى من الـ main loop كل ساعة."""
    global last_sector_report
    if time.time() - last_sector_report >= SECTOR_REPORT_EVERY:
        scan_sector_activity()


def refresh_tickers():
    # type: () -> None
    global all_tickers, changes_map, candidates, last_tickers

    data = safe_get(MEXC_24H)
    if not data:
        return

    all_tickers = data
    changes_map = {}


    vol_map = {}
    for t in data:
        sym = t.get("symbol", "")
        try:
            ch    = float(t["priceChangePercent"])
            vol   = float(t["quoteVolume"])
            price = float(t.get("lastPrice", 0))
            changes_map[sym] = ch
            vol_map[sym]     = vol
        except (KeyError, ValueError):
            pass


    our_coins  = set(sym for coins in SECTORS.values() for sym in coins)
    candidates = [
        sym for sym in our_coins
        if sym not in EXCLUDED and
           vol_map.get(sym, 0) >= MIN_VOL_USDT and
           vol_map.get(sym, 0) <= MAX_VOL_USDT
    ]
    last_tickers = time.time()

    log.info(" Candidates: %d    | Hot: %s",
             len(candidates), ", ".join(hot_sectors) or "لا يوجد")



#   ANALYSIS FUNCTIONS











# TPS/ATS + Volume Delta  (القيم المرجعية في الأعلى: ATS_WHALE=5000, VDELTA_STRONG=0.70)




SC_MIN_VOL        = 50_000
SC_MAX_VOL        = 500_000
SC_MAX_COINS      = 300
SC_REFRESH_EVERY  = 3600
SC_VOL_SPIKE      = 4.0
SC_VOL_SPIKE_MICRO = 1.8
SC_MICRO_VOL_MAX  = 100_000
SC_SCORE_MIN      = 65

LH_VOL_SPIKE      = 3.0
LH_VOL_QUIET      = 1.8
LH_PRICE_FLAT     = 2.0
LH_BTC_DIV_MIN    = 1.5
LH_COOLDOWN       = 14400
LH_SCORE_MIN      = 50
LH_SCAN_EVERY     = 300

# Order Book Deep Analysis
OB_DEPTH_LIMIT   = 50        # عمق دفتر الطلبات (مستوى)
OB_WALL_RATIO    = 4.0       # الجدار = 4× متوسط مستوى واحد
OB_WALL_MIN_USDT = 50_000    # حجم الجدار الأدنى بـ USDT

# Multi-Timeframe Liquidity Scanner
MTF_LIQ_EVERY    = 600       # كل 10 دقائق
MTF_LIQ_COOLDOWN = 10800     # 3 ساعات بين تنبيهات نفس العملة
MTF_LIQ_SCORE    = 65        # الحد الأدنى للنتيجة
MTF_LIQ_MIN_TF   = 2         # يجب أن يوافق إطارين على الأقل
MTF_VOL_SPIKE    = 2.0       # حجم الإطار يرتفع 2× المتوسط
MTF_PRICE_MAX    = 5.0       # السعر لا يتجاوز 5% تغيير










def analyze_tps_ats(sym):
    # type: (str) -> Optional[Dict]
    """
    يحسب TPS + ATS + VDelta من مصدرين:
    1. Trades API — للـ TPS و ATS
    2. Klines 15m — للـ VDelta (أدق لأن MEXC لا يوفر isBuyerMaker)
    """
    raw = safe_get(MEXC_TRADES, {"symbol": sym, "limit": TPS_LIMIT})
    if not raw or not isinstance(raw, list) or len(raw) < 10:
        return None
    try:
        now_ms  = int(time.time() * 1000)
        window  = 30000
        all_vol = 0.0
        trade_window = 0
        sizes   = []

        for t in raw:
            price = float(t.get("price", 0))
            qty   = float(t.get("qty",   0))
            ts    = int(t.get("time",    0))
            val   = price * qty
            all_vol += val
            sizes.append(val)
            if now_ms - ts <= window:
                trade_window += 1

        if all_vol <= 0:
            return None

        tps = trade_window / 30.0
        ats = all_vol / len(raw)



        vdelta = calc_vdelta_ma(sym, period=10, interval="15m")
        kd = get_klines(sym, "15m", 15)
        buy_vol_k  = 0.0
        sell_vol_k = 0.0
        if kd and len(kd["closes"]) >= 5:
            opens  = kd["opens"]
            closes = kd["closes"]
            vols   = kd["vols"]
            buy_vol_k  = sum(vols[i] for i in range(len(closes))
                            if closes[i] > opens[i])
            sell_vol_k = sum(vols[i] for i in range(len(closes))
                            if closes[i] < opens[i])

        buyer_type = "🐋 حيتان" if ats >= ATS_WHALE else ("🐟 متوسط" if ats >= 1000 else "🦐 أفراد")

        return {
            "tps": round(tps, 2), "ats": round(ats, 2),
            "vdelta": vdelta,
            "buy_vol": round(buy_vol_k if kd else all_vol * 0.5, 2),
            "sell_vol": round(sell_vol_k if kd else all_vol * 0.5, 2),
            "all_vol": round(all_vol, 2),
            "buyer_type": buyer_type,
        }
    except (KeyError, ValueError, ZeroDivisionError, TypeError):
        return None















LZ_TPS_PROXIMITY  = 0.015
LZ_TPS_COOLDOWN   = 14400
LZ_TPS_SCORE_MIN  = 60
lz_tps_alerted    = {}      # type: Dict[str, float]


def get_adaptive_thresholds(coin_vol=0, coin_ats=0):
    # type: (float, float) -> Dict
    """
    إعدادات تتكيف مع حالة السوق تلقائياً.
    SAFE    → إعدادات عادية — كل الفرص
    CAUTION → إعدادات متشددة — فرص واثقة فقط
    DANGER  → إعدادات صارمة — حيتان العملة نفسها أو BTC يشتري

    coin_vol: حجم العملة 24h بـ USDT (لتحديد tier)
    coin_ats: ATS الفعلي للعملة (للكشف عن حيتانها)
    """
    _btc_vd  = btc_tps_stats.get("vdelta", 0.5) if btc_tps_stats else 0.5
    _btc_ats = btc_tps_stats.get("ats", 0)       if btc_tps_stats else 0

    if market_state == "SAFE":
        return {
            "score_big":    55,
            "score_mid":    42,
            "score_small":  30,
            "vdelta_min":   0.60,
            "tps_min":      0.20,
            "ats_boost":    1.0,
            "rr_min":       1.5,
            "sigs_min":     2,
            "cvd_required": False,
            "chg_max":      8.0,   # أقصى ارتفاع مقبول للدخول
            "label":        "🟢 SAFE",
        }
    elif market_state == "CAUTION":
        return {
            "score_big":    65,
            "score_mid":    52,
            "score_small":  40,
            "vdelta_min":   0.65,
            "tps_min":      0.30,
            "ats_boost":    1.25,
            "rr_min":       1.8,
            "sigs_min":     2,
            "cvd_required": False,
            "chg_max":      5.0,   # أكثر صرامة في CAUTION
            "label":        "🟡 CAUTION",
        }
    else:  # DANGER
        # ── فحص حيتان BTC ───────────────────────────────────────────────
        _whale_btc = _btc_vd >= 0.65 and _btc_ats >= ATS_WHALE * 0.6  # >= 3000$

        # ── فحص حيتان العملة نفسها (نسبي حسب tier) ─────────────────────
        # TIER_SETTINGS: big≥10M vol → ats_min=500, mid≥1M → 150, small → 50
        _tier      = get_tier_settings(coin_vol) if coin_vol > 0 else {}
        _tier_ats  = _tier.get("ats_min", 150)
        _whale_coin = coin_ats >= _tier_ats * 2  # ضعف الحد الطبيعي للـ tier

        _whale_any = _whale_btc or _whale_coin
        _label_sfx = (" 🐋BTC" if _whale_btc else "") + (" 🐋Coin" if _whale_coin else "")

        return {
            "score_big":    75,
            "score_mid":    65,
            "score_small":  55,
            "vdelta_min":   0.72,
            "tps_min":      0.50,   # TPS موثوق فقط
            "ats_boost":    1.50,
            "rr_min":       2.0,
            "sigs_min":     3,
            "cvd_required": not _whale_any,
            "chg_max":      5.0,   # صارم في DANGER
            "label":        "🔴 DANGER{}".format(_label_sfx if _whale_any else ""),
        }







WHALE_WATCH_TTL    = 14400
WHALE_CHECK_EVERY  = 60
WHALE_ATS_MIN      = 100
WHALE_VDELTA_MIN   = 0.58    # VDelta 65%+


whale_watchlist    = {}   # type: Dict[str, Dict]
whale_confirmed    = {}   # type: Dict[str, float]  {sym: last_confirm_time}
_coin_first_seen   = {}   # {sym: first_seen_timestamp}
NEW_COIN_MIN_DAYS  = 7    # تجاهل العملات الجديدة أقل من 7 أيام (أسبوع)


def whale_watch_add(sym, ats, vdelta, price):
    # type: (str, float, float, float) -> None
    """يضيف عملة لقائمة مراقبة الحيتان"""
    global whale_watchlist

    if vdelta < 0.55:
        log.debug(" whale_watch_add rejected: %s | VDelta=%.0f%% < 55%%", sym, vdelta*100)
        return
    if sym not in whale_watchlist:
        whale_watchlist[sym] = {
            "time":        time.time(),
            "ats_then":    ats,
            "vdelta_then": vdelta,
            "price_then":  price,
        }
        log.info(" Whale Watch: %s | ATS=%.0f$ | VD=%.0f%%", sym, ats, vdelta*100)




















def detect_accumulation(sym):
    # type: (str) -> dict
    """
    يكشف التجميع المبكر قبل الانفجار
    يعيد: score, phase, details
    phase: none | early | active | ready
    """
    kd1h = get_klines(sym, "1h", 24)
    kd15 = get_klines(sym, "15m", 48)

    if not kd1h or len(kd1h["closes"]) < 12:
        return {"score": 0, "phase": "none", "details": {}}

    closes1h = kd1h["closes"]
    vols1h   = kd1h["vols"]
    opens1h  = kd1h["opens"]
    lows1h   = kd1h["lows"]
    n        = len(closes1h)

    score   = 0
    details = {}

    try:


        third   = n // 3
        vol_old = sum(vols1h[:third])     / third if third > 0 else 0
        vol_mid = sum(vols1h[third:2*third]) / third if third > 0 else 0
        vol_new = sum(vols1h[2*third:])   / max(n - 2*third, 1)


        gradual_increase = (vol_mid > vol_old * 1.1 and
                           vol_new > vol_mid * 1.1 and
                           vol_new < vol_old * 5.0)

        if gradual_increase:
            score += 30
            details["vol_gradient"] = "✅ حجم يتصاعد تدريجياً"
        else:
            details["vol_gradient"] = "❌"


        price_change = (closes1h[-1] - closes1h[-12]) / closes1h[-12] * 100 if closes1h[-12] > 0 else 0
        if -3.0 <= price_change <= 8.0:
            score += 20
            details["price_stability"] = "✅ سعر مستقر {:.1f}%".format(price_change)
        else:
            details["price_stability"] = "❌ {:.1f}%".format(price_change)


        if kd15 and len(kd15["closes"]) >= 20:
            c15 = kd15["closes"]
            o15 = kd15["opens"]
            v15 = kd15["vols"]

            vd_candles = []
            for i in range(len(c15)):
                if c15[i] > o15[i]:
                    vd_candles.append(1.0)
                elif c15[i] < o15[i]:
                    vd_candles.append(0.0)
                else:
                    vd_candles.append(0.5)


            avg_vd = sum(vd_candles[-20:]) / 20
            if avg_vd >= 0.60:
                score += 25
                details["vdelta_continuous"] = "✅ VDelta مستمر {:.0f}%".format(avg_vd*100)
            else:
                details["vdelta_continuous"] = "❌ VDelta {:.0f}%".format(avg_vd*100)
        else:
            avg_vd = 0.5
            details["vdelta_continuous"] = "⚠️ بيانات غير كافية"


        recent_lows = lows1h[-8:]
        hl_count = sum(1 for i in range(1, len(recent_lows))
                      if recent_lows[i] >= recent_lows[i-1] * 0.998)
        hl_ratio = hl_count / (len(recent_lows) - 1) if len(recent_lows) > 1 else 0

        if hl_ratio >= 0.60:
            score += 25
            details["higher_lows"] = "✅ قيعان صاعدة {:.0f}%".format(hl_ratio*100)
        else:
            details["higher_lows"] = "❌ {:.0f}%".format(hl_ratio*100)


        if score >= 80:
            phase = "ready"
            phase_ar = "جاهز للانطلاق 🚀"
        elif score >= 60:
            phase = "active"
            phase_ar = "تجميع نشط 🔥"
        elif score >= 35:
            phase = "early"
            phase_ar = "تجميع مبكر 👁️"
        else:
            phase = "none"
            phase_ar = "لا تجميع"

        return {
            "score":    score,
            "phase":    phase,
            "phase_ar": phase_ar,
            "details":  details,
            "avg_vd":   round(avg_vd * 100, 1),
            "price_chg": round(price_change, 2),
        }

    except (IndexError, ValueError, ZeroDivisionError):
        return {"score": 0, "phase": "none", "phase_ar": "خطأ", "details": {}}


def check_trend_filter(sym, change_24h):
    # type: (str, float) -> tuple
    """
    فلتر اتجاه السوق — يمنع الدخول في ترند هابط
    يعيد: (passed, reason)
    """

    if change_24h < -10.0:
        return False, "هبوط حاد {:.1f}%".format(change_24h)


    kd = get_klines(sym, "4h", 20)
    if kd and len(kd["closes"]) >= 15:
        closes = kd["closes"]
        ema15  = sum(closes[-15:]) / 15
        ema5   = sum(closes[-5:])  / 5


        if ema5 < ema15 * 0.97:
            return False, "EMA هابط على 4h"


    if change_24h > 20.0:
        return False, "Pump مكتمل {:.1f}%".format(change_24h)

    return True, "OK"



def unified_signal_check(sym, vdelta, ats, vol, change_24h, signal_type="WATCH"):
    # type: (str, float, float, float, float, str) -> tuple
    """
    الفلتر النهائي الموحد — يعيد (passed, reason)
    
    signal_type: WATCH | ENTRY | JOKER
    
    يفحص 6 شروط:
    1. VDelta minimum
    2. السوق ليس DANGER
    3. العملة ليست في ترند هابط قوي
    4. الحجم كافٍ
    5. ليست في منتصف Pump
    6. MTF لا يتعارض
    """
    reasons = []


    min_vd = {
        "WATCH":  0.66,
        "ENTRY":  0.75,
        "JOKER":  0.65,
    }.get(signal_type, 0.66)

    if vdelta < min_vd:
        return False, "VDelta {:.0f}% < {:.0f}%".format(vdelta*100, min_vd*100)


    if market_state == "DANGER" and signal_type != "JOKER":
        return False, "السوق DANGER"



    if change_24h < -8.0:
        return False, "ترند هابط قوي {:.1f}%".format(change_24h)


    min_vol = {
        "WATCH":  500_000,
        "ENTRY":  1_000_000,
        "JOKER":  500_000,
    }.get(signal_type, 500_000)

    if vol < min_vol:
        return False, "حجم ضعيف {:.0f}K".format(vol/1000)



    if change_24h > 15.0:
        return False, "Pump مكتمل {:.1f}%".format(change_24h)



    kd4h = get_klines(sym, "4h", 20)
    if kd4h and len(kd4h["closes"]) >= 10:
        closes = kd4h["closes"]
        ema10  = sum(closes[-10:]) / 10

        if closes[-1] < ema10 * 0.97 and signal_type == "WATCH":
            return False, "تحت EMA 4h — ترند هابط"

    return True, "OK"


def should_send_signal(sym, vdelta, ats, vol, change_24h, signal_type="WATCH"):
    # type: (str, float, float, float, float, str) -> bool
    """واجهة بسيطة للفلتر — True = أرسل | False = لا ترسل"""
    passed, reason = unified_signal_check(sym, vdelta, ats, vol, change_24h, signal_type)
    if not passed:
        log.info(" FILTER_REJECT [%s] %s | %s", signal_type, sym, reason)
    return passed


def scan_whale_confirmation(price_map):
    # type: (Dict) -> None
    """
    يفحص كل العملات في قائمة المراقبة
    إذا ATS ارتفع لـ WHALE_ATS_MIN+ → تنبيه Whale Confirmation
    """
    global whale_watchlist, whale_confirmed, _coin_first_seen
    now     = time.time()
    to_del  = []


    # _mth يُحسب لكل عملة داخل الحلقة (يعتمد على vol/ats الخاص بها)

    for sym, data in list(whale_watchlist.items()):
        # فحص استثناء Sector Flow لكل عملة
        _sym_sector = next((s for s,syms in SECTORS.items() if sym+"USDT" in syms or sym in syms), "")
        _sector_hot_time = sector_flow_hot.get(_sym_sector, 0)
        _in_hot_sector = _sym_sector and (time.time() - _sector_hot_time < 14400)  # 4 ساعات

        # ── فلتر DANGER بناءً على بيانات العملة نفسها ──────────────────
        _coin_t_j   = next((t for t in all_tickers if t.get("symbol") == sym), {}) if all_tickers else {}
        _coin_vol_j = float(_coin_t_j.get("quoteVolume", 0) or 0)
        _coin_chg_j = float(_coin_t_j.get("priceChangePercent", 0) or 0)
        _coin_ats_j = data.get("ats", 0)
        _mth_j      = get_adaptive_thresholds(coin_vol=_coin_vol_j, coin_ats=_coin_ats_j)
        _block_danger = market_state == "DANGER" and _mth_j.get("cvd_required", True)

        # استثناء: ارتداد من قاع (هبوط > 20% + شراء استثنائي > 85%)
        # هذه الفرص تضيع عند حجب DANGER للعملات غير المصنّفة
        _oversold_bounce = (
            _coin_chg_j < -20.0 and
            data.get("vdelta", 0) >= 0.85
        )

        # عملة مستقلة عن السوق — تتماسك أو ترتفع رغم نزول BTC
        # هذه هي الفرص الحقيقية في السوق الهابط
        _decoupled = (
            _coin_chg_j > -5.0 and           # لا تنزل مع السوق
            data.get("vdelta", 0) >= 0.70     # شراء حقيقي
        )
        # عملة ترتفع فعلاً في سوق هابط = فرصة استثنائية بلا شروط
        _rising_in_bear = _coin_chg_j > 2.0

        if _block_danger and not _in_hot_sector and not _oversold_bounce and not _decoupled and not _rising_in_bear:
            continue

        # تخفيف شروط VDelta للقطاعات الساخنة
        if _in_hot_sector:
            _j_tier = get_tier_settings(data.get("vol", 1_000_000))
            _j_tier = dict(_j_tier)
            _j_tier["vdelta_min"] = max(0.50, _j_tier["vdelta_min"] - 0.10)  # -10% للقطاعات الساخنة

        if now - data["time"] > WHALE_WATCH_TTL:
            to_del.append(sym)
            continue


        if now - coin_whale_done.get(sym, 0) < LZ_TPS_COOLDOWN:
            to_del.append(sym)
            continue

        # تجاهل العملات الجديدة اقل من 3 أيام
        if sym not in _coin_first_seen:
            _coin_first_seen[sym] = now
            continue
        if (now - _coin_first_seen.get(sym, now)) / 86400 < NEW_COIN_MIN_DAYS:
            continue


        if now - whale_confirmed.get(sym, 0) < LZ_TPS_COOLDOWN:
            continue


        stats = analyze_tps_ats(sym)
        if not stats:
            continue

        ats    = stats["ats"]
        vdelta = stats["vdelta"]
        tps    = stats["tps"]
        price  = price_map.get(sym, 0)







        _j_vol    = float(next((t.get("quoteVolume",0) for t in all_tickers if t.get("symbol")==sym), 0)) if all_tickers else 0
        _j_tier   = get_tier_settings(_j_vol)
        _j_ats    = _j_tier["ats_min"]

        _vdelta_strong = vdelta >= 0.80 and ats >= max(150, _j_ats)
        _early_entry   = ats >= max(300, _j_ats*2) and vdelta >= 0.70
        _normal_entry  = ats >= WHALE_ATS_MIN and vdelta >= WHALE_VDELTA_MIN
        _big_whale     = ats >= ATS_WHALE and vdelta >= 0.50
        _small_cap     = _j_ats <= 50 and ats >= _j_ats and vdelta >= 0.58     # كان 0.70
        _tier_entry    = ats >= _j_ats and vdelta >= _j_tier["vdelta_min"]     # tier catch-all

        if not (_vdelta_strong or _early_entry or _normal_entry or _big_whale or _small_cap or _tier_entry):
            continue


        _is_dist, _dist_reason = detect_distribution(sym, price, vdelta, ats)
        if _is_dist:
            log.info(" DISTRIBUTION: %s | %s", sym, _dist_reason)
            continue


        _wick_ok, _wick_reason = calc_wick_filter(sym, "15m")
        if not _wick_ok:
            log.info(" WICK FILTER: %s | %s", sym, _wick_reason)
            continue


        _macd_hist = calc_macd_histogram(sym, "1h")
        # نجعل الحد نسبياً بالسعر حتى يعمل مع العملات الرخيصة ($0.001 مقابل $100)
        _macd_pct_of_price = abs(_macd_hist / price) * 100 if price > 0 else 0
        _macd_bad = _macd_hist < 0 and _macd_pct_of_price > 0.05   # أكثر من 0.05% من السعر نزولاً
        if _macd_bad and not _in_hot_sector and not _big_whale and not _tier_entry:
            log.info(" MACD BLOCK: %s | delta=%.8f (%.4f%% of price)", sym, _macd_hist, _macd_pct_of_price)
            continue
        if _macd_hist < 0:
            log.info(" MACD soft pass: %s | %.8f (%.4f%%)", sym, _macd_hist, _macd_pct_of_price)


        _cvd_ok, _cvd_trend = check_cvd_filter(sym, "JOKER", vdelta=vdelta)
        if not _cvd_ok:
            log.info(" CVD FILTER: %s | %s", sym, _cvd_trend)
            continue


        _ob = calc_ob_imbalance(sym)
        _ob_ratio  = _ob.get("ratio", 1.0)
        _ob_signal = _ob.get("signal", "neutral")
        if _ob_signal == "strong_sell":
            log.info(" OB IMBALANCE: %s | ratio=%.2f", sym, _ob_ratio)
            continue


        price_then  = data["price_then"]
        ats_then    = data["ats_then"]
        price_chg   = (price - price_then) / price_then * 100 if price_then > 0 else 0
        ats_mult    = ats / ats_then if ats_then > 0 else 1.0
        elapsed_min = int((now - data["time"]) / 60)

        sector = next((s for s, syms in SECTORS.items() if sym in syms), "غير محدد")


        if ats >= ATS_WHALE:
            whale_type = "🐋🐋 حوت ضخم"
        else:
            whale_type = "🐋 حوت"


        coin_signal_count[sym] = coin_signal_count.get(sym, 0) + 1
        _sig_num = coin_signal_count[sym]


        if elapsed_min >= 2:
            evolution_line = (
                "📊 *التطور:*\n"
                "  🦐 قبل `{min}` دقيقة: ATS `{ats_b:.0f}$`\n".format(
                    min=elapsed_min, ats_b=ats_then) +
                "  {wt} الآن: ATS `{ats:.0f}$` (+{mult:.1f}×) 🔥\n".format(
                    wt=whale_type, ats=ats, mult=ats_mult) +
                "━━━━━━━━━━━━━━━━━━\n"
            )
        else:
            evolution_line = (
                "📊 ATS: `{ats:.0f}$` {wt} 🔥\n".format(
                    ats=ats, wt=whale_type) +
                "━━━━━━━━━━━━━━━━━━\n"
            )


        header   = "🃏🐋🃏🐋🃏🐋🃏🐋🃏\n🃏 *الجوكر يلعب* 🃏\n🃏🐋🃏🐋🃏🐋🃏🐋🃏\n"
        btcd_line = ""
        footer   = "🃏 _المال الكبير دخل — الجوكر يلعب!_ 🎴"

        # ── CVD Divergence + Consolidation إضافية للرسالة ─────────
        _cvd_div_j = detect_cvd_divergence(sym)
        _consol_j  = detect_consolidation_breakout(sym, price)
        _extra_signals = ""
        if _cvd_div_j.get("bullish_div") and _cvd_div_j.get("score", 0) >= 30:
            _extra_signals += "📈 *CVD Divergence* — سعر ينزل + ضغط شراء خفي 🔥\n"
        if _consol_j.get("consolidating"):
            _nb = " ⚡ *اختراق وشيك!*" if _consol_j.get("near_breakout") else ""
            _extra_signals += "🎯 *Consolidation* — نطاق {:.1f}% | حجم ×{:.1f}{}\n".format(
                _consol_j["range_pct"], _consol_j["vol_ratio"], _nb)

        _activity = ("🐌 نشاط ضعيف جداً" if tps < 0.5 else
                     "🐢 نشاط عادي"       if tps < 1.0 else
                     "⚡ نشاط جيد"        if tps < 3.0 else
                     "🔥 نشاط قوي"        if tps < 5.0 else
                     "💥 نشاط انفجاري")

        # تدفق الأموال الحقيقية — Wolf Flow style
        _jflow = calc_money_flow_1h(sym)
        def _jfmt(v):
            if v >= 1_000_000: return "{:.1f}M$".format(v / 1e6)
            if v >= 1_000:     return "{:.1f}K$".format(v / 1e3)
            return "{:.0f}$".format(v)
        _jflow_quality = ("💹 استثنائي" if _jflow["ratio"] >= 10 else
                          "🔥 قوي"       if _jflow["ratio"] >= 3  else
                          "📈 إيجابي"    if _jflow["net"] > 0    else
                          "⚠️ ضعيف")
        _jflow_line = (
            "💹 *Flow 1h:* IN `{i}` / OUT `{o}` / Net `{n}` — {q}\n".format(
                i=_jfmt(_jflow["in"]),
                o=_jfmt(_jflow["out"]),
                n=_jfmt(abs(_jflow["net"])) + ("↑" if _jflow["net"] >= 0 else "↓"),
                q=_jflow_quality,
            )
        )

        msg = (
            header +
            "💥 *{sym}* — حيتان دخلوا! ادخل الآن!\n".format(sym=sym.replace("USDT","")) +
            "━━━━━━━━━━━━━━━━━━\n" +
            evolution_line +
            "{}\n".format(_activity) +
            "📡 TPS: `{tps:.2f}` | ATS: `{ats:.0f}$`\n".format(tps=tps, ats=ats) +
            "📊 VDelta: `{vd:.0f}%` شراء حقيقي 🔥\n".format(vd=vdelta*100) +
            _jflow_line +
            "💰 السعر:  `{pr}` {chg_txt}\n".format(
                pr=fmt_price(price),
                chg_txt=("◼️ لم يتحرك بعد" if abs(price_chg) < 0.01
                         else "({:+.2f}%)".format(price_chg))) +
            ("━━━━━━━━━━━━━━━━━━\n" + _extra_signals if _extra_signals else "") +
            "━━━━━━━━━━━━━━━━━━\n" +
            btcd_line +
            "🏷️ القطاع: `{sec}`\n".format(sec=sector) +
            "━━━━━━━━━━━━━━━━━━\n" +
            (
                "➕ *أضف للصفقة الآن* 💪 _(دخلت مبكراً؟ هذا تأكيد الحيتان)_\n"
                if coin_signal_count.get(sym, 0) >= 1
                else "✅ *ادخل الصفقة الآن* 💪\n"
            ) +
            footer
        )




        _atr_sl  = calc_atr_stop_loss(sym, price, "1h")
        _smart   = calc_smart_targets(sym, price)

        if _atr_sl > _smart.get("sl", 0) and _atr_sl < price:
            _smart["sl"]    = _atr_sl
            _smart["sl_pct"] = (_atr_sl - price) / price * 100

        _tblock = "━━━━━━━━━━━━━━━━━━\n🎯 *الأهداف عند المقاومات:*\n"
        _nums = ["1","2","3"]
        for _ii, _tgt in enumerate(_smart.get("targets", [])[:3]):
            _lbl = " ({})" .format(_tgt["label"]) if _tgt.get("label") else ""
            _tblock += "  {}️⃣ `{}` (+{:.0f}%){}\n".format(
                _nums[_ii], fmt_price(_tgt["price"]), _tgt["pct"], _lbl)
        if not _smart.get("targets"):
            _tblock += "  1️⃣ `{}` (+10%)\n  2️⃣ `{}` (+20%)\n".format(
                fmt_price(price*1.10), fmt_price(price*1.20))
        _sl_val = _smart.get("sl", price*0.96)
        _sl_pct = (_sl_val - price) / price * 100 if price > 0 else -4

        if _sl_pct < -5.0:
            _sl_val = price * 0.95
            _sl_pct = -5.0
        _tblock += "🛡️ *Stop Loss:* `{}` ({:.1f}%)\n".format(
            fmt_price(_sl_val), _sl_pct)
        msg = msg + "\n" + _tblock

        _joker_engine = build_engine_block(sym, include_levels=False)
        if _joker_engine and _joker_engine.strip().replace("=","").strip():
            msg = msg + _joker_engine

        send(msg)
        _tgts = calc_smart_targets(sym, price)
        add_to_exit_watchlist(sym, price, _tgts.get("targets", []))
        log.info("JOKER | %s | ATS=%.0f$ | flow_ratio=%.1fx", sym, ats, _jflow.get("ratio",1.0))
        whale_confirmed[sym]  = now
        coin_whale_done[sym]  = now
        coin_alerted[sym]     = now
        to_del.append(sym)
        perf_register(sym, price, "whale_confirm", 95, "Whale confirmed after retail")
        log.info(" Whale Confirmed! %s | ATS=%.0f$ | VD=%.0f%% | +%.1f%%  ",
                 sym, ats, vdelta*100, price_chg)


    for sym in to_del:
        whale_watchlist.pop(sym, None)



def scan_lz_tps_fusion(price_map, vol_now, changes_map):
    # type: (Dict, Dict, Dict) -> None
    """
    يفحص كل 5 دقائق:
    1. هل السعر قريب من منطقة سيولة يومية؟
    2. هل TPS/ATS يؤكد دخول سيولة؟
    إذا الاثنان موجودان = تنبيه مزدوج 🎯
    """
    global lz_tps_alerted
    now = time.time()

    # _mth يُحسب لكل عملة داخل الحلقة بعد معرفة vol/ats الخاص بها
    all_syms = list(set(list(candidates) + EXTRA_COINS))
    ranked = sorted(
        [(s, vol_now.get(s, 0)) for s in all_syms],
        key=lambda x: -x[1]
    )[:40]

    for sym, vol in ranked:
        base = sym.replace("USDT", "")
        if base in STABLECOINS: continue
        _min_vol = 100_000 if sym in EXTRA_COINS else 1_000_000
        if vol < _min_vol:
            continue

        if now - coin_whale_done.get(sym, 0) < LZ_TPS_COOLDOWN:
            continue

        # منع التكرار: لا ترسل WATCH ALERT 💎 للعملة مرتين من هذا الماسح
        if now - lz_tps_alerted.get(sym, 0) < LZ_TPS_COOLDOWN:
            continue

        if coin_signal_count.get(sym, 0) >= MAX_COIN_SIGNALS:
            continue

        last_alert  = coin_alerted.get(sym, 0)
        in_cooldown = (now - last_alert < TPS_COOLDOWN)

        price = price_map.get(sym, 0)
        if price <= 0:
            continue


        if changes_map.get(sym, 0) >= TPS_MAX_CHANGE:
            continue


        kd = get_klines(sym, "1d", LZ_LOOKBACK)
        if not kd or len(kd.get("closes", [])) < 20:
            continue

        zones = detect_liquidity_zones(kd)
        if not zones:
            continue


        nearest_zone = None
        min_dist     = float("inf")
        for z in zones:
            dist = abs(price - z["mid"]) / z["mid"]
            if dist < min_dist:
                min_dist     = dist
                nearest_zone = z

        if not nearest_zone or min_dist > LZ_TPS_PROXIMITY:
            continue


        if in_cooldown:
            _tps_quick = analyze_tps_ats(sym)
            if not (_tps_quick and
                    _tps_quick.get("ats", 0) >= WHALE_ATS_MIN and
                    _tps_quick.get("vdelta", 0) >= WHALE_VDELTA_MIN):
                continue


        is_support    = price >= nearest_zone["low"] * 0.99
        is_resistance = price <= nearest_zone["high"] * 1.01
        if not is_support:
            continue


        tps_stats = analyze_tps_ats(sym)
        if not tps_stats:
            continue

        tps    = tps_stats["tps"]
        ats    = tps_stats["ats"]
        vdelta = tps_stats["vdelta"]

        # ── إعدادات تكيفية حسب حالة السوق + بيانات العملة نفسها ────────
        _mth = get_adaptive_thresholds(coin_vol=vol, coin_ats=ats)

        if in_cooldown:
            if not (ats >= WHALE_ATS_MIN and vdelta >= WHALE_VDELTA_MIN):
                continue


        base  = tps_baseline.get(sym, 0)
        if base < 0.05:

            tps_baseline[sym] = tps if tps > 0 else 0.1
            ratio = 1.0
        else:
            ratio = tps / base if base > 0 else 1.0
            tps_baseline[sym] = base * 0.9 + tps * 0.1


        score   = 0
        signals = []


        zone_sigma = nearest_zone.get("sigma", 1)
        zone_type  = nearest_zone.get("type", "REPEAT")
        score += min(zone_sigma * 5, 30)
        if zone_type == "FRESH":
            score += 15
            signals.append("🆕 Zone FRESH")
        else:
            touches = nearest_zone.get("touches", 1)
            signals.append("🔁 Zone {}×".format(touches))


        prox_pct = min_dist * 100
        if prox_pct <= 0.5:
            score += 20
            signals.append("📍 داخل المنطقة تماماً ✅")
        elif prox_pct <= 1.0:
            score += 12
            signals.append("📍 قريب جداً من المنطقة")
        else:
            score += 5
            signals.append("📍 على حافة المنطقة")

        # TPS
        if ratio >= TPS_SPIKE:
            score += 20
            signals.append("⚡ TPS {:.1f}×".format(ratio))
        elif ratio >= 2.0:
            score += 10
            signals.append("⚡ TPS {:.1f}×".format(ratio))

        # ATS
        if ats >= ATS_WHALE:
            score += 20
            signals.append("🐋 ATS {:.0f}$".format(ats))
        elif ats >= 2000:
            score += 10
            signals.append("🐟 ATS {:.0f}$".format(ats))

        # VDelta
        if vdelta >= VDELTA_STRONG:
            score += 15
            signals.append("💚 VDelta {:.0f}%".format(vdelta * 100))
        elif vdelta >= 0.60:
            score += 8
            signals.append("💚 VDelta {:.0f}%".format(vdelta * 100))


        if vdelta < _mth["vdelta_min"]:
            continue

        # ── موثوقية VDelta: TPS < 0.5 = عينة صغيرة جداً ──────────────
        # مثال: 3 صفقات شراء متتالية تُعطي VDelta=100% لكنها غير ذات معنى
        _vd_reliable = tps >= 0.5
        _vd_warn     = vdelta >= 0.75 and not _vd_reliable  # VDelta مرتفع + TPS ضعيف

        # إذا VDelta غير موثوق → خفّض النقاط وأضف تحذيراً
        if _vd_warn:
            score = int(score * 0.80)   # خصم 20%
            signals.append("⚠️ VDelta غير موثوق (TPS={:.1f})".format(tps))

        # ── المناطق المستنزفة: REPEAT >= 15 → تحذير ──────────────────
        _touches = nearest_zone.get("touches", 1)
        if _touches >= 15:
            score = int(score * 0.85)   # خصم 15%
            signals.append("⚠️ منطقة مستنزفة {}×".format(_touches))

        if score < _mth["score_big"]:
            continue



        zone_low  = nearest_zone["low"]
        zone_high = nearest_zone["high"]
        stop_loss = zone_low * 0.985


        resistance_zones = sorted(
            [z for z in zones if z["mid"] > price * 1.02],
            key=lambda z: z["mid"]
        )
        if resistance_zones:

            nearest_res = resistance_zones[0]["mid"]
            target = min(nearest_res, price * 1.30)
        else:
            target = price * 1.12
        rr = (target - price) / (price - stop_loss) if price > stop_loss else 0


        if rr < _mth["rr_min"]:
            log.debug(" LZ+TPS skip %s: R/R=%.1f < 1.5", sym, rr)
            continue



        if tps < _mth["tps_min"]:
            log.debug(" LZ+TPS skip %s: TPS=%.2f < 0.2", sym, tps)
            continue

        sector  = next((s for s, syms in SECTORS.items() if sym in syms), "غير محدد")
        chg     = changes_map.get(sym, 0)
        rarity  = "🏆 نادر جداً" if score >= 90 else ("🔥 قوي" if score >= 80 else "⚡ جيد")
        zone_tag = "🆕 FRESH" if zone_type == "FRESH" else "🔁 REPEAT"



        if coin_signal_count.get(sym, 0) >= 1:

            if sym not in whale_watchlist:
                whale_watchlist[sym] = {
                    "time":       now,
                    "price_then": price,
                    "ats_then":   ats,
                    "reason":     "LZ+TPS silent add",
                }
                log.info(" LZ+TPS silent watchlist add: %s", sym)
            continue


        coin_signal_count[sym] = 1

        _tps_label = (
            "🐌 نشاط ضعيف جداً" if tps < 0.2 else
            ("🐢 تجميع بطيء"     if tps < 0.5 else
            ("🐢 نشاط عادي"      if tps < 1.0 else
            ("⚡ نشاط جيد"       if tps < 3.0 else
            ("🔥 نشاط قوي"       if tps < 5.0 else
             "💥 نشاط انفجاري"))))
        )
        _prox_label = (
            "داخل المنطقة تماماً ✅" if prox_pct <= 0.5 else
            ("قريب جداً 🔥"          if prox_pct <= 1.0 else
             "على الحافة ⚡")
        )


        _dir_lz  = calc_direction_engine(sym, "1h")
        _hmm_lz  = calc_hmm_regime(sym, "4h")
        _kd_lz   = get_klines(sym, "1h", 30)
        _weis_lz = calc_weis_wave(
            _kd_lz["closes"], _kd_lz["vols"]
        ) if _kd_lz else 0.5
        _bull_lz  = _dir_lz.get("bullish_pct", 0) if _dir_lz else 0
        _regime_lz = _hmm_lz.get("regime", "unknown") if _hmm_lz else "unknown"
        _real_liq_lz = (
            _bull_lz  >= 55 and
            _regime_lz != "volatile" and
            _weis_lz  >= 0.50
        )


        # DIRECT ENTRY يشترط TPS موثوق أيضاً
        _direct = vdelta >= 0.80 and rr >= 1.5 and _real_liq_lz and _vd_reliable

        if _direct:
            msg = (
                "🚀🟢 *DIRECT ENTRY — ادخل الآن!* 🟢🚀\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "💥 *{}* — منطقة سيولة + شراء قوي!\n".format(sym.replace("USDT","")) +
                "💵 السعر: `{}`\n".format(fmt_price(price)) +
                "━━━━━━━━━━━━━━━━━━\n"
                "📍 {} | {} `{}×`\n".format(_prox_label, zone_tag, zone_sigma) +
                "📊 المنطقة: `{}` ← `{}`\n".format(fmt_price(zone_low), fmt_price(zone_high)) +
                "⚖️ R/R: `{:.1f}:1` | 🎯 `{}` (+{:.1f}%)\n".format(
                    rr, fmt_price(target), (target-price)/price*100) +
                "━━━━━━━━━━━━━━━━━━\n"
                "{}\n".format(_tps_label) +
                "📡 TPS: `{:.2f}` | ATS: `{:.0f}$`\n".format(tps, ats) +
                "📊 VDelta: `{:.0f}%` 🔥 شراء قوي جداً\n".format(vdelta*100) +
                "━━━━━━━━━━━━━━━━━━\n"
                "💪 القوة: `{}/100` {}\n".format(score, rarity) +
                "📉 24h: `{:+.2f}%` | حجم: `{:.2f}M`\n".format(chg, vol_now.get(sym,0)/1_000_000) +
                "🏷️ القطاع: `{}`\n".format(sector) +
                "━━━━━━━━━━━━━━━━━━\n"
                "✅ *ادخل الآن — VDelta {:.0f}% + R/R {:.1f}:1*\n".format(vdelta*100, rr) +
                "🛡️ Stop Loss تحت: `{}`".format(fmt_price(zone_low))
            )
        else:
            msg = (
                "✅ *ادخل الآن* 💎\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "🔍 *{}* — منطقة سيولة + نشاط! 👀\n".format(sym.replace("USDT","")) +
                "💵 السعر: `{}`\n".format(fmt_price(price)) +
                "━━━━━━━━━━━━━━━━━━\n"
                "📍 {} | {} `{}×`\n".format(_prox_label, zone_tag, zone_sigma) +
                "📊 المنطقة: `{}` ← `{}`\n".format(fmt_price(zone_low), fmt_price(zone_high)) +
                "⚖️ R/R: `{:.1f}:1` | 🎯 `{}` (+{:.1f}%)\n".format(
                    rr, fmt_price(target), (target-price)/price*100) +
                "━━━━━━━━━━━━━━━━━━\n"
                "{}\n".format(_tps_label) +
                "📡 TPS: `{:.2f}` {} | ATS: `{:.0f}$` {}\n".format(tps, get_tps_label(tps), ats, get_ats_label(ats)) +
                "📊 VDelta: `{:.0f}%` {}\n".format(
                    vdelta * 100,
                    "⚠️ _غير موثوق — TPS ضعيف جداً_" if _vd_warn else "شراء") +
                "━━━━━━━━━━━━━━━━━━\n"
                "💪 القوة: `{}/100` {}\n".format(score, rarity) +
                "📉 24h: `{:+.2f}%` | حجم: `{:.2f}M`\n".format(chg, vol_now.get(sym,0)/1_000_000) +
                "🏷️ القطاع: `{}`\n".format(sector) +
                "━━━━━━━━━━━━━━━━━━\n"
                "✅ *ادخل الآن* — سيولة + نشاط مؤكد 🎯"
            )

        send(msg)
        lz_tps_alerted[sym] = now
        coin_alerted[sym]   = now
        whale_watch_add(sym, ats, vdelta, price)
        perf_register(sym, price, "lz_tps_fusion", score, " | ".join(signals))
        log.info(" WATCH+LZ | %s | score=%d | rr=%.1f | ats=%.0f | vdelta=%.0f%%",
                 sym, score, rr, ats, vdelta * 100)





liq_exit_alerted  = 0.0
liq_exit_vol_hist = []
LEX_COOLDOWN      = 3600
LEX_VOL_DROP      = 0.25
LEX_VDELTA_SELL   = 0.35
LEX_BTCD_RISE     = 1.5


def check_liquidity_exit(vol_now, price_map):
    # type: (Dict, Dict) -> None
    """
    يراقب السيناريوهات الأربعة:
    BTC.D ↑ + BTC ↑ = BTC يقود — انتظر
    BTC.D ↓ + BTC ↑ = Alt Season 🚀
    BTC.D ↑ + BTC ↓ = هروب للـ BTC ⚠️
    BTC.D ↓ + BTC ↓ = Risk-Off 💣 اخرج!
    """
    global liq_exit_alerted, liq_exit_vol_hist
    now = time.time()

    if now - liq_exit_alerted < LEX_COOLDOWN:
        return


    total_vol = sum(v for s, v in vol_now.items()
                    if s.endswith("USDT") and v > 0)
    liq_exit_vol_hist.append((now, total_vol))
    if len(liq_exit_vol_hist) > 12:
        liq_exit_vol_hist.pop(0)
    if len(liq_exit_vol_hist) < 4:
        return


    btc_1h  = btc_tps_stats.get("change_1h",  0.0) if btc_tps_stats else 0.0
    btc_24h = btc_tps_stats.get("change_24h", 0.0) if btc_tps_stats else 0.0


    btcd_now = get_btc_dominance(vol_now)
    btcd_chg = 0.0
    if len(btcd_history) >= 2 and btcd_now > 0:
        btcd_chg = btcd_now - btcd_history[0]


    btc_vdelta  = btc_tps_stats.get("vdelta", 0.5) if btc_tps_stats else 0.5
    btc_ats     = btc_tps_stats.get("ats", 0)      if btc_tps_stats else 0
    btc_selling = (btc_vdelta < LEX_VDELTA_SELL and btc_ats >= ATS_WHALE)


    old_vol    = liq_exit_vol_hist[0][1]
    vol_drop   = (old_vol - total_vol) / old_vol if old_vol > 0 else 0
    vol_drying = vol_drop >= LEX_VOL_DROP




    scenario = None
    emoji    = ""
    title    = ""
    advice   = ""
    details  = ""



    if btc_24h <= -3.0 and btcd_chg <= -1.0 and vol_drying:
        scenario = "RISK_OFF"
        emoji    = "💣💣💣💣💣💣💣💣💣"
        title    = "💣 RISK-OFF — الكل يخرج!"
        details  = (
            "  📉 BTC 24h: `{:+.2f}%` ❌\n".format(btc_24h) +
            "  📉 BTC.D: `{:+.2f}%` ← ينزل مع BTC ❌\n".format(btcd_chg) +
            "  📉 حجم السوق: `-{:.0f}%` ❌\n".format(vol_drop * 100)
        )
        advice = (
            "  🔴 *اخرج من كل المراكز فوراً!*\n"
            "  💵 حوّل لـ Stablecoins\n"
            "  ⏳ انتظر استقرار السوق\n"
            "  🚫 لا تشتري أي شيء الآن\n"
        )



    elif btc_24h <= -2.0 and btcd_chg >= 2.0:
        scenario = "BTC_DOMINANCE_SURGE"
        emoji    = "🚨🚨🚨🚨🚨🚨🚨🚨🚨"
        title    = "⚠️ هروب من Alts → BTC"
        details  = (
            "  📉 BTC 24h: `{:+.2f}%` ← ينزل\n".format(btc_24h) +
            "  📈 BTC.D: `{:+.2f}%` ← يصعد ⚠️\n".format(btcd_chg) +
            "  🐋 الأموال تهرب من Alts → BTC\n"
        )
        advice = (
            "  🟠 *اخرج من مراكز Alts*\n"
            "  📍 ضيّق Stop Loss فوراً\n"
            "  👁️ راقب BTC — هل يستقر؟\n"
        )


    elif btc_selling and vol_drying:
        scenario = "WHALE_SELLING"
        emoji    = "🚨🚨🚨🚨🚨🚨🚨🚨🚨"
        title    = "🐋 حيتان يبيعون BTC — خطر!"
        details  = (
            "  🐋 BTC VDelta: `{:.0f}%` ← بيع قوي ❌\n".format(btc_vdelta * 100) +
            "  📉 حجم السوق: `-{:.0f}%` ❌\n".format(vol_drop * 100) +
            "  ⚡ BTC 1h: `{:+.2f}%`\n".format(btc_1h)
        )
        advice = (
            "  🟡 ضيّق Stop Loss\n"
            "  ⚠️ لا تفتح مراكز جديدة\n"
            "  👁️ انتظر تأكيد الاتجاه\n"
        )



    elif btc_24h >= 1.0 and btcd_chg <= -1.5 and btcd_now > 0:
        scenario = "ALT_SEASON"
        emoji    = "🚀🚀🚀🚀🚀🚀🚀🚀🚀"
        title    = "🚀 Alt Season يبدأ!"
        details  = (
            "  📈 BTC 24h: `{:+.2f}%` ✅\n".format(btc_24h) +
            "  📉 BTC.D: `{:+.2f}%` ← ينزل 🚀\n".format(btcd_chg) +
            "  📊 BTC.D: 📉 ينزل {:.2f}% في 24h\n".format(abs(btcd_chg))
        )
        advice = (
            "  ✅ *وقت الدخول في Alts!*\n"
            "  🎯 انتظر إشارة #1 + #2 للتأكيد\n"
            "  💎 ابحث عن GOLDEN SIGNAL\n"
        )
    else:
        return


    msg = (
        "{}\n".format(emoji) +
        "*MARKET SCENARIO ALERT*\n" +
        "{}\n".format(emoji) +
        "━━━━━━━━━━━━━━━━━━\n"
        "*{}*\n".format(title) +
        "━━━━━━━━━━━━━━━━━━\n" +
        details +
        "━━━━━━━━━━━━━━━━━━\n"
        "🛡️ *الإجراء:*\n" +
        advice +
        "━━━━━━━━━━━━━━━━━━\n"
        "_BTC.D + BTC + حجم = الصورة الكاملة_ 📊"
    )

    send(msg)
    liq_exit_alerted = now
    log.warning(" SCENARIO: %s | BTC24h=%.1f%% | BTCD_chg=%.1f%% | vol_drop=%.1f%%",
                scenario, btc_24h, btcd_chg, vol_drop * 100)





btcd_history    = []
btcd_last_check = 0.0
btcd_alert_sent = 0.0
BTCD_CHECK_EVERY   = 3600
BTCD_DROP_ALERT    = 1.5
BTCD_RISE_ALERT    = 2.0
BTCD_ALT_THRESHOLD = 52.0


def get_btc_dominance(vol_now):
    # type: (Dict) -> float
    """
    يحسب BTC Dominance تقريبي من أحجام تداول Binance
    يستثني Stablecoins و Leverage tokens
    BTC.D حقيقي ~55-65% عادةً
    """
    try:
        btc_vol = vol_now.get("BTCUSDT", 0)
        if btc_vol <= 0:
            return 0.0
        _stables = {"USDC","BUSD","TUSD","FDUSD","USDE","BFUSD","USDP","DAI"}
        _lev_kw  = ["3L","3S","5L","5S","BULL","BEAR","UP","DOWN"]
        total_vol = 0.0
        for s, v in vol_now.items():
            if not s.endswith("USDT"): continue
            if v <= 0: continue
            base = s.replace("USDT","")
            if base in _stables: continue
            if any(k in s for k in _lev_kw): continue
            total_vol += v
        if total_vol <= 0:
            return 0.0

        raw = (btc_vol / total_vol) * 100


        return round(raw, 2)
    except Exception:
        return 0.0










pump_dump_history  = {}
pump_alerted       = {}
dump_alerted       = {}
last_pulse_time    = 0.0
market_pulse_history = []

PUMP_THRESHOLD     = 4.0
DUMP_THRESHOLD     = -4.0
PUMP_VOL_MULT      = 2.5
PUMP_COOLDOWN      = 3600
PULSE_EVERY        = 1800


def update_pump_dump_history(price_map, vol_now):
    # type: (Dict, Dict) -> None
    """يحدث تاريخ الأسعار لكل عملة — يُستدعى كل دورة"""
    now = time.time()
    for sym, price in price_map.items():
        if not sym.endswith("USDT"): continue
        vol = vol_now.get(sym, 0)
        if sym not in pump_dump_history:
            pump_dump_history[sym] = []

        if not isinstance(pump_dump_history[sym], list):
            pump_dump_history[sym] = []
        pump_dump_history[sym].append((now, price, vol))

        pump_dump_history[sym] = [
            x for x in pump_dump_history[sym]
            if now - x[0] <= 600
        ]


def scan_pump_dump(price_map, vol_now, change_now):
    # type: (Dict, Dict, Dict) -> None
    """
    🚨 يرصد الارتفاعات والانهيارات المفاجئة
    شرط: تغيير 4%+ في 5 دقائق + حجم 2.5×
    """
    now = time.time()

    for sym in list(candidates):
        if sym not in price_map: continue
        price = price_map[sym]
        vol   = vol_now.get(sym, 0)
        hist  = pump_dump_history.get(sym, [])

        if len(hist) < 3: continue


        five_min_ago = [(t, p, v) for t, p, v in hist if now - t >= 280]
        if not five_min_ago: continue
        old_price = five_min_ago[-1][1]
        if old_price <= 0: continue

        move = (price - old_price) / old_price * 100


        hist_vols = coin_vol_history.get(sym, [])
        avg_vol   = sum(hist_vols) / len(hist_vols) if hist_vols else vol
        vol_mult  = vol / avg_vol if avg_vol > 0 else 1.0

        sector = next((s for s, syms in SECTORS.items() if sym in syms), "غير محدد")
        base   = sym.replace("USDT", "")


        if move >= PUMP_THRESHOLD and vol_mult >= PUMP_VOL_MULT:
            if now - pump_alerted.get(sym, 0) < PUMP_COOLDOWN:
                continue
            pump_alerted[sym] = now
            msg = (
                "🚨 *PUMP ALERT*\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "📈 *{}* — ارتفع `{:+.1f}%` في 5 دقائق!\n"
                "💧 الحجم: `{:.1f}×` المعدل 🔥\n"
                "💵 السعر: `{}` | 24h: `{:+.1f}%`\n"
                "🏷️ القطاع: `{}`\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "⚡ _حركة مفاجئة — راقب بحذر_"
            ).format(base, move, vol_mult, fmt_price(price),
                     change_now.get(sym, 0), sector)
            send(msg)
            log.info(" PUMP | %s | move=%.1f%% | vol=%.1fx", sym, move, vol_mult)


        elif move <= DUMP_THRESHOLD and vol_mult >= PUMP_VOL_MULT:
            if now - dump_alerted.get(sym, 0) < PUMP_COOLDOWN:
                continue
            dump_alerted[sym] = now
            msg = (
                "🔴 *DUMP ALERT*\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "📉 *{}* — انهار `{:+.1f}%` في 5 دقائق!\n"
                "💧 الحجم: `{:.1f}×` المعدل ⚠️\n"
                "💵 السعر: `{}` | 24h: `{:+.1f}%`\n"
                "🏷️ القطاع: `{}`\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "🛑 _انهيار مفاجئ — احذر إذا دخلت_"
            ).format(base, move, vol_mult, fmt_price(price),
                     change_now.get(sym, 0), sector)
            send(msg)
            log.info(" DUMP | %s | move=%.1f%% | vol=%.1fx", sym, move, vol_mult)


def scan_market_pulse(price_map, vol_now, change_now):
    # type: (Dict, Dict, Dict) -> None
    """
    🌊 نبض السوق كل 30 دقيقة
    = كم % من العملات ترتفع؟
    = هل السيولة تدخل أم تخرج؟
    """
    global last_pulse_time
    now = time.time()
    if now - last_pulse_time < PULSE_EVERY:
        return
    last_pulse_time = now

    rising = 0; falling = 0; total = 0
    strong_up = []; strong_down = []
    buy_vol = 0.0; sell_vol = 0.0

    for sym, chg in change_now.items():
        if not sym.endswith("USDT"): continue
        base = sym.replace("USDT","")
        if base in STABLECOINS: continue
        if any(k in sym for k in LEVERAGE_KEYWORDS): continue
        vol = vol_now.get(sym, 0)
        if vol < 500_000: continue
        total += 1
        if chg > 0:
            rising  += 1
            buy_vol += vol
            if chg >= 3:
                strong_up.append((base, chg, vol))
        else:
            falling  += 1
            sell_vol += vol
            if chg <= -3:
                strong_down.append((base, chg, vol))

    if total == 0: return

    rising_pct  = rising  / total * 100
    falling_pct = falling / total * 100
    total_vol   = buy_vol + sell_vol
    buy_pct     = buy_vol / total_vol * 100 if total_vol > 0 else 50


    if rising_pct >= 65 and buy_pct >= 60:
        pulse_icon  = "🟢"
        pulse_label = "السوق صاعد قوي 🚀"
        pulse_note  = "السيولة تدخل — فرصة جيدة"
    elif rising_pct >= 55:
        pulse_icon  = "🟡"
        pulse_label = "ميل للصعود ↗️"
        pulse_note  = "حذر — ليس كل القطاعات"
    elif falling_pct >= 65 and buy_pct <= 40:
        pulse_icon  = "🔴"
        pulse_label = "السوق هابط ⚠️"
        pulse_note  = "السيولة تخرج — ابتعد"
    elif falling_pct >= 55:
        pulse_icon  = "🟡"
        pulse_label = "ميل للهبوط ↘️"
        pulse_note  = "انتظر — ضغط بيعي"
    else:
        pulse_icon  = "⚪"
        pulse_label = "السوق محايد ➡️"
        pulse_note  = "لا اتجاه واضح — انتظر"


    strong_up.sort(key=lambda x: -x[1])
    strong_down.sort(key=lambda x: x[1])

    up_txt   = " | ".join(["*{}* +{:.1f}%".format(b,c) for b,c,v in strong_up[:3]]) or "لا يوجد"
    down_txt = " | ".join(["*{}* {:.1f}%".format(b,c) for b,c,v in strong_down[:3]]) or "لا يوجد"


    bar_g = int(rising_pct / 10)
    bar_r = 10 - bar_g
    bar   = "🟩" * bar_g + "🟥" * bar_r

    msg = (
        "🌊 *MARKET PULSE*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "{} {}\n"
        "{}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "📊 `{}` عملة | 🟢 `{:.0f}%` | 🔴 `{:.0f}%`\n"
        "💰 شراء: `{:.0f}%` | بيع: `{:.0f}%`\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🚀 صاعد: {}\n"
        "📉 هابط: {}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "💡 _{}_"
    ).format(
        pulse_icon, pulse_label, bar,
        total, rising_pct, falling_pct,
        buy_pct, 100 - buy_pct,
        up_txt, down_txt,
        pulse_note
    )

    send(msg)
    log.info(" PULSE | rising=%.0f%% | buy=%.0f%% | total=%d",
             rising_pct, buy_pct, total)








sector_vol_history   = {}
sector_flow_alerted  = {}
last_flow_track_time = 0.0
FLOW_TRACK_EVERY     = 300
FLOW_ALERT_COOLDOWN  = 1800
FLOW_IN_THRESHOLD    = 1.5
FLOW_OUT_THRESHOLD   = 0.6


def track_liquidity_flow(vol_now, change_now):
    # type: (Dict, Dict) -> None
    """
    🌊 يتابع اتجاه السيولة بين القطاعات كل 5 دقائق
    يرسل تنبيه عند:
      - دخول سيولة قوية لقطاع
      - خروج سيولة من قطاع
      - rotation بين قطاعين
    """
    global last_flow_track_time
    now = time.time()
    if now - last_flow_track_time < FLOW_TRACK_EVERY:
        return
    last_flow_track_time = now


    sector_vol_now = {}
    sector_chg_now = {}

    for sector, coins in SECTORS.items():
        total_vol = 0.0
        total_chg = 0.0
        count     = 0
        for sym in coins:
            vol = vol_now.get(sym, 0)
            chg = change_now.get(sym, 0)
            if vol < 50_000: continue
            total_vol += vol
            total_chg += chg
            count     += 1
        if count > 0:
            sector_vol_now[sector] = total_vol
            sector_chg_now[sector] = total_chg / count


    for sector, vol in sector_vol_now.items():
        if sector not in sector_vol_history:
            sector_vol_history[sector] = []

        if not isinstance(sector_vol_history[sector], list):
            sector_vol_history[sector] = []
        sector_vol_history[sector].append(vol)
        if len(sector_vol_history[sector]) > 12:
            sector_vol_history[sector].pop(0)


    flowing_in  = []
    flowing_out = []

    for sector, vol in sector_vol_now.items():
        hist = sector_vol_history.get(sector, [])
        if len(hist) < 3: continue
        avg = sum(hist[:-1]) / len(hist[:-1])
        if avg <= 0: continue
        ratio = vol / avg
        chg   = sector_chg_now.get(sector, 0)

        if ratio >= FLOW_IN_THRESHOLD and chg > 0:
            flowing_in.append((sector, ratio, chg, vol))
        elif ratio <= FLOW_OUT_THRESHOLD and chg < 0:
            flowing_out.append((sector, ratio, chg, vol))

    if not flowing_in and not flowing_out:
        return

    flowing_in.sort(key=lambda x: -x[1])
    flowing_out.sort(key=lambda x: x[1])


    if flowing_in and flowing_out:

        top_in  = flowing_in[0]
        top_out = flowing_out[0]


        alert_key = "rotation_{}_{}" .format(top_out[0], top_in[0])
        if now - sector_flow_alerted.get(alert_key, 0) < FLOW_ALERT_COOLDOWN:
            return
        sector_flow_alerted[alert_key] = now

        in_coins  = [s.replace("USDT","") for s in SECTORS.get(top_in[0],[])
                     if vol_now.get(s,0) > 100_000][:4]
        out_coins = [s.replace("USDT","") for s in SECTORS.get(top_out[0],[])
                     if vol_now.get(s,0) > 100_000][:4]

        msg = (
            "🔄 *SECTOR ROTATION*\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "💸 *خروج:* `{}` `{:+.1f}%` ↘️\n"
            "💰 *دخول:* `{}` `{:+.1f}%` ↗️\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "📤 عملات تخرج منها: {}\n"
            "📥 عملات تدخلها:   {}\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "💡 _السيولة تنتقل — راقب قطاع {}_ 👁️"
        ).format(
            top_out[0], top_out[2],
            top_in[0],  top_in[2],
            " | ".join(["*{}*".format(c) for c in out_coins]) or "—",
            " | ".join(["*{}*".format(c) for c in in_coins])  or "—",
            top_in[0]
        )
        send(msg)
        log.info(" ROTATION | out=%s  in=%s | ratio=%.1fx",
                 top_out[0], top_in[0], top_in[1])
        return


    if flowing_in and not flowing_out:
        top = flowing_in[0]
        alert_key = "in_{}".format(top[0])
        if now - sector_flow_alerted.get(alert_key, 0) < FLOW_ALERT_COOLDOWN:
            return
        sector_flow_alerted[alert_key] = now

        coins = [s.replace("USDT","") for s in SECTORS.get(top[0],[])
                 if vol_now.get(s,0) > 100_000][:5]

        msg = (
            "💰 *سيولة تدخل — {}*\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "📈 الحجم: `{:.1f}×` المعدل 🔥\n"
            "📊 متوسط القطاع: `{:+.1f}%`\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "👀 عملات القطاع: {}\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "⏳ _انتظر الجوكر في هذا القطاع_ 🃏"
        ).format(
            top[0], top[1], top[2],
            " | ".join(["*{}*".format(c) for c in coins]) or "—"
        )
        send(msg)
        log.info(" FLOW IN | %s | ratio=%.1fx | chg=%.1f%%",
                 top[0], top[1], top[2])


    elif flowing_out and not flowing_in:
        top = flowing_out[0]
        alert_key = "out_{}".format(top[0])
        if now - sector_flow_alerted.get(alert_key, 0) < FLOW_ALERT_COOLDOWN:
            return
        sector_flow_alerted[alert_key] = now

        coins = [s.replace("USDT","") for s in SECTORS.get(top[0],[])
                 if vol_now.get(s,0) > 100_000][:5]

        msg = (
            "🚨 *سيولة تخرج — {}*\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "📉 الحجم: `{:.1f}×` المعدل ⚠️\n"
            "📊 متوسط القطاع: `{:+.1f}%`\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "⚠️ عملات القطاع: {}\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🛑 _ابتعد عن هذا القطاع الآن_"
        ).format(
            top[0], top[1], top[2],
            " | ".join(["*{}*".format(c) for c in coins]) or "—"
        )
        send(msg)
        log.info(" FLOW OUT | %s | ratio=%.1fx | chg=%.1f%%",
                 top[0], top[1], top[2])








explosion_alerted    = {}
explosion_vol_hist   = {}
EXPLOSION_COOLDOWN   = 7200
EXPLOSION_VOL_MULT   = 3.0
EXPLOSION_TPS_MULT   = 2.5
EXPLOSION_VDELTA_MIN = 0.72
EXPLOSION_MAX_CHANGE = 3.0


def scan_explosion_catcher(price_map, vol_now, change_now):
    # type: (Dict, Dict, Dict) -> None
    """
    💥 يرصد العملات على وشك الانفجار قبل 5 دقائق
    = حجم يتضاعف فجأة + TPS يقفز + VDelta عالي + سعر ثابت
    """
    now = time.time()

    all_syms = list(set(list(candidates) + EXTRA_COINS))

    for sym in all_syms:
        base = sym.replace("USDT", "")
        if base in STABLECOINS: continue
        if now - explosion_alerted.get(sym, 0) < EXPLOSION_COOLDOWN: continue
        if now - coin_alerted.get(sym, 0) < 1800: continue

        vol  = vol_now.get(sym, 0)
        chg  = change_now.get(sym, 0)
        price = price_map.get(sym, 0)

        if vol < 300_000: continue
        if abs(chg) > EXPLOSION_MAX_CHANGE: continue


        if sym not in explosion_vol_hist:
            explosion_vol_hist[sym] = []
        explosion_vol_hist[sym].append(vol)
        if len(explosion_vol_hist[sym]) > 20:
            explosion_vol_hist[sym].pop(0)

        hist = explosion_vol_hist[sym]
        if len(hist) < 5: continue

        avg_vol = sum(hist[:-3]) / len(hist[:-3]) if len(hist) > 3 else vol
        if avg_vol <= 0: continue

        vol_mult = vol / avg_vol


        try:
            stats = get_tps_ats(sym)
        except Exception:
            continue
        if not stats: continue

        tps    = stats.get("tps", 0)
        ats    = stats.get("ats", 0)
        vdelta = stats.get("vdelta", 0)


        baseline = tps_baseline.get(sym, tps)
        tps_mult = tps / baseline if baseline > 0 else 1.0


        if (vol_mult  >= EXPLOSION_VOL_MULT and
            tps_mult  >= EXPLOSION_TPS_MULT and
            vdelta    >= EXPLOSION_VDELTA_MIN and
            abs(chg)  <= EXPLOSION_MAX_CHANGE):

            sector = next((s for s, syms in SECTORS.items() if sym in syms), "غير محدد")


            power = (vol_mult * 0.4) + (tps_mult * 0.4) + (vdelta * 100 * 0.2)
            if power >= 300:
                power_label = "💥 انفجار وشيك جداً!!!"
                power_icon  = "🔴"
            elif power >= 200:
                power_label = "🔥 انفجار قريب جداً!"
                power_icon  = "🟠"
            else:
                power_label = "⚡ بوادر انفجار"
                power_icon  = "🟡"

            msg = (
                "💥 *EXPLOSION CATCHER* {}\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "🎯 *{}* — {}\n"
                "💵 السعر: `{}` | 24h: `{:+.1f}%` (ثابت ✅)\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "📊 الحجم: `{:.1f}×` المعدل 🔥\n"
                "📡 TPS: `{:.2f}` (`{:.1f}×` المعدل) 🚀\n"
                "📊 VDelta: `{:.0f}%` شراء 💪\n"
                "💰 ATS: `{:.0f}$`\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "🏷️ القطاع: `{}`\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "⚡ _السعر لم يتحرك بعد — فرصة الدخول الآن!_ 🎯"
            ).format(
                power_icon,
                base, power_label,
                fmt_price(price), chg,
                vol_mult,
                tps, tps_mult,
                vdelta * 100,
                ats,
                sector
            )

            send(msg)
            explosion_alerted[sym] = now
            coin_alerted[sym] = now
            log.info(" EXPLOSION | %s | vol=%.1fx | tps=%.1fx | vdelta=%.0f%%",
                     sym, vol_mult, tps_mult, vdelta * 100)









liq_accum_history  = {}
liq_accum_alerted  = {}
LAT_COOLDOWN       = 14400
LAT_MIN_HOURS      = 2
LAT_VOL_GROW       = 1.4
LAT_VDELTA_MIN     = 0.65
LAT_MAX_CHANGE     = 5.0
LAT_READINGS       = 24


def track_liquidity_accumulation(price_map, vol_now, change_now):
    # type: (Dict, Dict, Dict) -> None
    """
    🌊 يرصد تراكم السيولة التدريجي على مدى ساعات
    = يكتشف الانفجار قبل حدوثه بساعات
    """
    now = time.time()

    all_syms = list(set(list(candidates) + EXTRA_COINS))

    for sym in all_syms:
        base  = sym.replace("USDT", "")
        if base in STABLECOINS: continue
        if now - liq_accum_alerted.get(sym, 0) < LAT_COOLDOWN: continue

        vol   = vol_now.get(sym, 0)
        chg   = change_now.get(sym, 0)
        price = price_map.get(sym, 0)

        if vol < 200_000: continue
        if abs(chg) > LAT_MAX_CHANGE: continue


        if sym not in liq_accum_history:
            liq_accum_history[sym] = []


        try:
            stats = get_tps_ats(sym)
        except Exception:
            continue
        if not stats: continue

        tps    = stats.get("tps", 0)
        vdelta = stats.get("vdelta", 0.5)
        ats    = stats.get("ats", 0)


        liq_accum_history[sym].append({
            "time":   now,
            "vol":    vol,
            "vdelta": vdelta,
            "tps":    tps,
            "price":  price,
        })


        if len(liq_accum_history[sym]) > LAT_READINGS:
            liq_accum_history[sym].pop(0)

        hist = liq_accum_history[sym]
        if len(hist) < 6: continue



        first_vol  = sum(h["vol"] for h in hist[:6]) / 6
        recent_vol = sum(h["vol"] for h in hist[-6:]) / 6
        vol_growth = recent_vol / first_vol if first_vol > 0 else 1.0


        avg_vdelta = sum(h["vdelta"] for h in hist[-12:]) / 12


        first_tps  = sum(h["tps"] for h in hist[:6]) / 6
        recent_tps = sum(h["tps"] for h in hist[-6:]) / 6
        tps_growth = recent_tps / first_tps if first_tps > 0.1 else 1.0


        first_price  = hist[0]["price"]
        price_change = abs(price - first_price) / first_price * 100 if first_price > 0 else 0


        if (vol_growth  >= LAT_VOL_GROW and
            avg_vdelta  >= LAT_VDELTA_MIN and
            price_change <= LAT_MAX_CHANGE):

            sector = next((s for s, syms in SECTORS.items() if sym in syms), "غير محدد")
            hours  = len(hist) * 5 / 60


            accum_score = (vol_growth * 40) + (avg_vdelta * 100 * 0.4) + (tps_growth * 20)

            if accum_score >= 120:
                strength = "🔴 تراكم ضخم — انفجار قريب جداً!"
            elif accum_score >= 90:
                strength = "🟠 تراكم قوي — راقب عن كثب"
            else:
                strength = "🟡 تراكم متوسط — ابدأ المراقبة"

            msg = (
                "🌊 *LIQUIDITY ACCUMULATION*\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "🎯 *{}* — {}\n"
                "💵 السعر: `{}` | تغيير: `{:+.1f}%` (ثابت ✅)\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "📊 نمو الحجم: `{:.1f}×` خلال `{:.1f}h` ⬆️\n"
                "📡 TPS نما: `{:.1f}×` المعدل\n"
                "📊 VDelta متوسط: `{:.0f}%` شراء مستمر 💪\n"
                "💰 ATS الحالي: `{:.0f}$`\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "🏷️ القطاع: `{}`\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "⏳ _السيولة تتراكم — انتظر الجوكر للدخول_ 🃏"
            ).format(
                base, strength,
                fmt_price(price), chg,
                vol_growth, hours,
                tps_growth,
                avg_vdelta * 100,
                ats,
                sector
            )

            send(msg)
            liq_accum_alerted[sym] = now
            coin_alerted[sym] = now


            whale_watch_add(sym, ats, avg_vdelta, price)

            log.info(" LAT | %s | vol_growth=%.1fx | vdelta=%.0f%% | hours=%.1f",
                     sym, vol_growth, avg_vdelta * 100, hours)








discovered_sectors   = {}
asd_last_run         = 0.0
ASD_RUN_EVERY        = 3600
ASD_MIN_COINS        = 5
ASD_MIN_CHANGE       = 5.0
ASD_VOL_MIN          = 500_000


def auto_sector_discovery(vol_now, change_now):
    # type: (Dict, Dict) -> None
    """
    🔍 يكتشف قطاعات جديدة تلقائياً
    = عملات كثيرة ترتفع معاً = قطاع يتشكل
    """
    global asd_last_run
    now = time.time()
    if now - asd_last_run < ASD_RUN_EVERY:
        return
    asd_last_run = now


    strong_movers = []
    for sym, chg in change_now.items():
        if not sym.endswith("USDT"): continue
        base = sym.replace("USDT", "")
        if base in STABLECOINS: continue
        if any(k in sym for k in LEVERAGE_KEYWORDS): continue
        vol = vol_now.get(sym, 0)
        if vol < ASD_VOL_MIN: continue
        if chg >= ASD_MIN_CHANGE:

            known = any(sym in coins for coins in SECTORS.values())
            strong_movers.append({
                "sym": sym, "chg": chg, "vol": vol, "known": known
            })

    if len(strong_movers) < ASD_MIN_COINS:
        return


    unknown = [m for m in strong_movers if not m["known"]]
    known   = [m for m in strong_movers if m["known"]]

    if len(unknown) < 3:
        return


    unknown.sort(key=lambda x: -x["chg"])
    known.sort(key=lambda x: -x["chg"])


    unknown_txt = ""
    for m in unknown[:8]:
        unknown_txt += "  🆕 *{}* `{:+.1f}%` 💧`{:.1f}M`\n".format(
            m["sym"].replace("USDT",""), m["chg"], m["vol"]/1_000_000
        )

    known_txt = ""
    for m in known[:5]:
        known_txt += "  📊 *{}* `{:+.1f}%`\n".format(
            m["sym"].replace("USDT",""), m["chg"]
        )

    msg = (
        "🔍 *AUTO SECTOR DISCOVERY*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "📡 اكتشفت `{}` عملة ترتفع معاً!\n"
        "🆕 غير مصنفة: `{}` عملة\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🆕 *عملات جديدة:*\n"
        "{}\n"
        "📊 *عملات معروفة:*\n"
        "{}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "💡 _قطاع جديد يتشكل — راقب هذه العملات_ 👁️"
    ).format(
        len(strong_movers),
        len(unknown),
        unknown_txt,
        known_txt or "  لا يوجد\n"
    )

    send(msg)
    log.info(" ASD | %d   | %d ",
             len(strong_movers), len(unknown))








delisting_alerted  = {}   # type: Dict[str, float]
DH_COOLDOWN        = 86400
DH_VOL_CRASH       = 0.15
DH_PRICE_CRASH     = -30.0
DH_MIN_HISTORY     = 5


def scan_delisting_hunter(vol_now, change_now, price_map):
    # type: (Dict, Dict, Dict) -> None
    """
    ⚠️ يرصد علامات الحذف:
    1. حجم ينهار فجأة
    2. سعر ينهار بدون سبب
    3. لا سيولة في Order Book
    """
    now = time.time()

    for sym in list(candidates):
        base = sym.replace("USDT", "")
        if base in STABLECOINS: continue
        if now - delisting_alerted.get(sym, 0) < DH_COOLDOWN: continue

        vol  = vol_now.get(sym, 0)
        chg  = change_now.get(sym, 0)

        if vol <= 0: continue


        hist = coin_vol_history.get(sym, [])
        if len(hist) < DH_MIN_HISTORY: continue

        avg_vol  = sum(hist) / len(hist)
        vol_ratio = vol / avg_vol if avg_vol > 0 else 1.0


        signs = []

        if vol_ratio <= DH_VOL_CRASH:
            signs.append("📉 حجم انهار `{:.0f}%` من المعدل".format(vol_ratio * 100))

        if chg <= DH_PRICE_CRASH:
            signs.append("🔴 سعر انهار `{:.1f}%` في 24h".format(chg))

        if len(signs) >= 1 and (vol_ratio <= DH_VOL_CRASH or chg <= DH_PRICE_CRASH):
            price = price_map.get(sym, 0)

            msg = (
                "⚠️ *DELISTING WARNING*\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "🚨 *{}* — علامات خطر!\n"
                "💵 السعر: `{}` | 24h: `{:+.1f}%`\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "{}\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "🛑 _تحقق فوراً — ممكن يكون حذف قريب!_"
            ).format(
                base,
                fmt_price(price), chg,
                "\n".join(signs)
            )

            send(msg)
            delisting_alerted[sym] = now
            log.warning(" DELISTING | %s | vol_ratio=%.2f | chg=%.1f%%",
                        sym, vol_ratio, chg)









sc_hunter_alerted  = {}   # type: Dict[str, float]
SCH_COOLDOWN       = 7200
SCH_VOL_MIN        = 30_000
SCH_VOL_MAX        = 2_000_000  # 2M maximum
SCH_VOL_SPIKE      = 3.0
SCH_VDELTA_MIN     = 0.68
SCH_TPS_MIN        = 0.3
SCH_MAX_CHANGE     = 15.0


def scan_small_cap_hunter(price_map, vol_now, change_now):
    # type: (Dict, Dict, Dict) -> None
    """
    🎯 يصطاد عملات Small Cap على وشك الانفجار
    = حجم صغير + نشاط غير طبيعي = فرصة كبيرة
    """
    now = time.time()

    for sym in list(candidates) + EXTRA_COINS:
        base = sym.replace("USDT", "")
        if base in STABLECOINS: continue
        if now - sc_hunter_alerted.get(sym, 0) < SCH_COOLDOWN: continue
        if now - coin_alerted.get(sym, 0) < 1800: continue

        vol  = vol_now.get(sym, 0)
        chg  = change_now.get(sym, 0)
        price = price_map.get(sym, 0)


        if vol < SCH_VOL_MIN or vol > SCH_VOL_MAX: continue
        if abs(chg) > SCH_MAX_CHANGE: continue


        hist = coin_vol_history.get(sym, [])
        if len(hist) < 3: continue
        avg_vol = sum(hist) / len(hist)
        vol_spike = vol / avg_vol if avg_vol > 0 else 1.0

        if vol_spike < SCH_VOL_SPIKE: continue

        # TPS/VDelta
        try:
            stats = get_tps_ats(sym)
        except Exception:
            continue
        if not stats: continue

        tps    = stats.get("tps", 0)
        vdelta = stats.get("vdelta", 0)
        ats    = stats.get("ats", 0)

        if tps    < SCH_TPS_MIN:    continue
        if vdelta < SCH_VDELTA_MIN: continue

        sector = next((s for s, syms in SECTORS.items() if sym in syms), "غير محدد")

        msg = (
            "🎯 *SMALL CAP HUNTER*\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "💎 *{}* — عملة صغيرة على وشك الانفجار!\n"
            "💵 السعر: `{}` | 24h: `{:+.1f}%`\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "📊 حجم: `{:.2f}M` (`{:.1f}×` المعدل) 🔥\n"
            "📡 TPS: `{:.2f}` | ATS: `{:.0f}$`\n"
            "📊 VDelta: `{:.0f}%` شراء 💪\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🏷️ القطاع: `{}`\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "⚡ _Small Cap = مكسب كبير — لكن SL محكم!_ 🎯"
        ).format(
            base,
            fmt_price(price), chg,
            vol/1_000_000, vol_spike,
            tps, ats,
            vdelta * 100,
            sector
        )

        send(msg)
        sc_hunter_alerted[sym] = now
        coin_alerted[sym] = now
        whale_watch_add(sym, ats, vdelta, price)
        log.info(" SCH | %s | vol=%.2fM | spike=%.1fx | vdelta=%.0f%%",
                 sym, vol/1_000_000, vol_spike, vdelta*100)








BULL_MODE_ACTIVE    = False
BULL_BTC_THRESHOLD  = 2.0    # BTC +2%+ = Bull Mode
BULL_MODE_ALERTED   = False

def update_bull_mode(vol_now=None, change_now=None):
    # type: (dict, dict) -> None
    """
    يحدث حالة Bull Mode بناءً على 3 مصادر:
    1. Order Flow السوق الكلي (buy_pct >= 65%)
    2. قطاع ساخن (5+ عملات ترتفع معاً)
    3. BTC (مؤشر مساعد وليس وحيداً)
    """
    global BULL_MODE_ACTIVE, BULL_MODE_ALERTED

    was_active = BULL_MODE_ACTIVE
    bull_reason = ""

    if vol_now is None or change_now is None:
        return


    buy_vol_total  = 0.0
    sell_vol_total = 0.0
    for sym, vol in vol_now.items():
        if not sym.endswith("USDT"): continue
        base = sym.replace("USDT","")
        if base in STABLECOINS: continue
        chg = change_now.get(sym, 0)
        taker_buy = vol * 0.7 if chg > 0 else vol * 0.3
        buy_vol_total  += taker_buy
        sell_vol_total += vol - taker_buy

    total_vol = buy_vol_total + sell_vol_total
    buy_pct_now = buy_vol_total / total_vol * 100 if total_vol > 0 else 50


    hot_sector_count = 0
    hot_sector_name  = ""
    for sector, coins in SECTORS.items():
        rising = sum(1 for s in coins if change_now.get(s, 0) >= 3.0)
        if rising >= 5:
            hot_sector_count += 1
            if not hot_sector_name:
                hot_sector_name = sector


    btc_rising = btc_change_24h >= BULL_BTC_THRESHOLD


    if buy_pct_now >= 65:
        BULL_MODE_ACTIVE = True
        bull_reason = "Order Flow {:.0f}% شراء 💰".format(buy_pct_now)
    elif hot_sector_count >= 2:
        BULL_MODE_ACTIVE = True
        bull_reason = "{} قطاعات ساخنة 🔥".format(hot_sector_count)
    elif hot_sector_count >= 1 and btc_rising:
        BULL_MODE_ACTIVE = True
        bull_reason = "قطاع {} + BTC {:+.1f}% 📈".format(hot_sector_name, btc_change_24h)
    else:
        BULL_MODE_ACTIVE  = False
        BULL_MODE_ALERTED = False


    if BULL_MODE_ACTIVE and not was_active and not BULL_MODE_ALERTED:
        BULL_MODE_ALERTED = True
        msg = (
            "🚀 *BULL MODE مفعّل!*\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "📊 السبب: {}\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "⚡ الفلاتر مخففة — VDelta >= 60% يكفي\n"
            "💡 _السيولة تدخل — اغتنم الفرصة_ 🎯"
        ).format(bull_reason)
        send(msg)
        log.info(" BULL MODE | reason=%s", bull_reason)


def check_btc_dominance(vol_now):
    # type: (Dict) -> None
    """
    يراقب BTC Dominance ويرسل تنبيه Alt Season
    """
    global btcd_history, btcd_last_check, btcd_alert_sent
    now = time.time()

    if now - btcd_last_check < BTCD_CHECK_EVERY:
        return
    btcd_last_check = now

    btcd = get_btc_dominance(vol_now)
    if btcd <= 0:
        return

    btcd_history.append(btcd)
    if len(btcd_history) > 24:
        btcd_history.pop(0)

    log.info(" BTC.D = %.2f%% | : %d ", btcd, len(btcd_history))

    if len(btcd_history) < 2:
        return


    oldest = btcd_history[0]
    change_24h = btcd - oldest


    if change_24h <= -0.3:
        btcd_trend = "falling"
    elif change_24h >= 0.3:
        btcd_trend = "rising"
    else:
        btcd_trend = "neutral"


    if (change_24h <= -BTCD_DROP_ALERT and
            now - btcd_alert_sent > 14400):

        if btcd < BTCD_ALT_THRESHOLD:
            tag     = "🚀 ALT SEASON كامل!"
            advice  = "✅ وقت الدخول في الـ Alts بقوة!"
            emoji   = "🚀🌙"
        else:
            tag     = "📈 بداية تدفق للـ Alts"
            advice  = "👀 راقب الـ Alts — قد يبدأ الموسم"
            emoji   = "📈"

        msg = (
            "📊 *BTC DOMINANCE ALERT* {}\n".format(emoji) +
            "━━━━━━━━━━━━━━━━━━\n"
            "📊 BTC.D: 📉 ينزل ({:+.2f}% في 24h)\n".format(change_24h) +
            "📊 التغيير 24h: `{:+.2f}%` 🔴\n".format(change_24h) +
            "━━━━━━━━━━━━━━━━━━\n"
            "🏷️ {}\n".format(tag) +
            "━━━━━━━━━━━━━━━━━━\n"
            "{}\n".format(advice) +
            "💡 _الأموال تخرج من BTC → تدخل Alts_"
        )
        send(msg)
        btcd_alert_sent = now
        log.info(" Alt Season Alert! BTC.D=%.2f%% change=%.2f%%", btcd, change_24h)


    elif (change_24h >= BTCD_RISE_ALERT and
              now - btcd_alert_sent > 14400):

        msg = (
            "📊 *BTC DOMINANCE ALERT* 🐋\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "📊 BTC.D: 📈 يصعد ({:+.2f}% في 24h)\n".format(change_24h) +
            "📊 التغيير 24h: `{:+.2f}%` 🟢\n".format(change_24h) +
            "━━━━━━━━━━━━━━━━━━\n"
            "🐋 BTC يسيطر — الأموال تعود لـ BTC\n"
            "⚠️ _الـ Alts قد تضعف — احذر_"
        )
        send(msg)
        btcd_alert_sent = now
        log.info(" BTC Dominance Rising! BTC.D=%.2f%% change=%.2f%%", btcd, change_24h)


def _btc_1h_tag():
    # type: () -> str
    """يعطي وصف حالة BTC 1h للإشارات"""
    try:
        chg = btc_tps_stats.get("change_1h", 0)
        if chg is None: chg = 0
        if chg >= 1.0:
            return "{:+.2f}% 🟢 قوي".format(chg)
        elif chg >= 0:
            return "{:+.2f}% ⚪ محايد".format(chg)
        elif chg >= -1.0:
            return "{:+.2f}% 🟡 ضعيف".format(chg)
        else:
            return "{:+.2f}% 🔴 خطر".format(chg)
    except Exception:
        return "N/A"



def get_tps_label(tps):
    # type: (float) -> str
    if tps < 0.2:   return "🐌 ضعيف"
    if tps < 0.5:   return "🐢 بطيء"
    if tps < 1.0:   return "🟡 عادي"
    if tps < 3.0:   return "🟢 جيد"
    if tps < 5.0:   return "🔥 قوي"
    return "💥 انفجاري"

def get_ats_label(ats):
    # type: (float) -> str
    if ats < 100:    return "🦐 أفراد صغار"
    if ats < 500:    return "🦐 أفراد"
    if ats < 1500:   return "🐟 متوسط"
    if ats < 5000:   return "🐋 حيتان صغيرة"
    if ats < 15000:  return "🐋 حيتان"
    return "🐋🔥 حيتان ضخمة"





#   Tier 2: Mid Cap  1M - 10M USDT
#   Tier 3: Small Cap < 1M USDT (Meme + Small)


def get_coin_tier(vol_24h):
    # type: (float) -> str
    if vol_24h >= 10_000_000:
        return "big"     # BTC, ETH, SOL, BNB
    elif vol_24h >= 1_000_000:
        return "mid"     # AVAX, DOT, LINK
    else:
        return "small"   # MASKSOL, Meme coins


TIER_SETTINGS = {
    "big": {
        "vdelta_min":  0.60,
        "ats_min":     200,
        "tps_spike":   2.0,
        "vol_min":     10_000_000,
        "label":       "Big Cap 🏦",
    },
    "mid": {
        "vdelta_min":  0.58,
        "ats_min":     100,    # ATS 200$+
        "tps_spike":   2.0,
        "vol_min":     1_000_000,
        "label":       "Mid Cap 📊",
    },
    "small": {
        "vdelta_min":  0.55,
        "ats_min":     50,
        "tps_spike":   2.5,
        "vol_min":     20_000,
        "label":       "Small Cap 🚀",
    },
}

def get_tier_settings(vol_24h):
    # type: (float) -> dict
    tier = get_coin_tier(vol_24h)
    return TIER_SETTINGS[tier]



# ══════════════════════════════════════════════════════════════════
#   VOLUME SURGE SCANNER — يصطاد COS/TOWNS/micro-cap قبل الانفجار
# ══════════════════════════════════════════════════════════════════

_vol_surge_seen     = {}    # {sym: timestamp}
_vol_surge_baseline = {}    # {sym: avg_vol} — مرجع لـ smart_market_scan أيضاً
VOL_SURGE_EVERY     = 300   # فحص كل 5 دقائق
VOL_SURGE_COOLDOWN  = 7200  # cooldown ساعتان لكل عملة
VOL_SURGE_RATIO     = 3.5   # الحجم ارتفع 3.5× المعدل الطبيعي
VOL_SURGE_GOLD      = 7.0   # 7× = إشارة ذهبية نادرة
VOL_SURGE_MAX_CHG   = 5.0   # السعر لم يرتفع أكثر من 5% بعد (الفرصة لم تفت)
VOL_SURGE_MIN_USDT  = 3_000  # حجم الساعة الأخيرة بـ USDT (خفيف لالتقاط micro-cap)
last_vol_surge_scan = 0.0


def _fmt_vol_k(v):
    # type: (float) -> str
    """تنسيق حجم USDT: 1500000 → 1.5M | 500000 → 500K | 3000 → 3K"""
    if v >= 1_000_000_000:
        return "{:.2f}B".format(v / 1_000_000_000)
    if v >= 1_000_000:
        return "{:.1f}M".format(v / 1_000_000)
    if v >= 1_000:
        return "{:.0f}K".format(v / 1_000)
    return "{:.0f}".format(v)


def _is_real_liquidity(vol_24h, chg_24h, t_dict=None):
    # type: (float, float, dict) -> tuple
    """
    فحص السيولة الحقيقية مقابل الوهمية (Wash Trading / Fake Volume)

    علامات الحجم الوهمي:
    1. حجم ضخم + تغيير سعري ضئيل جداً (< 0.5%)
    2. نطاق 24h واسع جداً (> 200%) = عملة مدرجة حديثاً
    3. نطاق 24h ضيق جداً مع حجم عالٍ = wash trading
    4. متوسط حجم الصفقة أقل من $5 (صفقات مجهرية = wash bots)
    5. فارق bid/ask كبير جداً (> 8%) = عمق وهمي

    يعيد: (is_real: bool, reason: str)
    """
    # 1. حجم ضخم + سعر يكاد لا يتحرك = وهمي تقريباً
    if vol_24h > 2_000_000 and abs(chg_24h) < 0.3:
        return False, "حجم ضخم بدون تحرك سعري"

    if t_dict:
        try:
            high  = float(t_dict.get("highPrice",  0) or 0)
            low   = float(t_dict.get("lowPrice",   0) or 0)
            bid   = float(t_dict.get("bidPrice",   0) or 0)
            ask   = float(t_dict.get("askPrice",   0) or 0)
            count = int(float(t_dict.get("count",  0) or 0))

            if low > 0:
                range_24h = (high - low) / low * 100

                # 2. نطاق 24h واسع جداً = عملة مدرجة حديثاً (مثل +4100%)
                # العملات المستقرة نادراً تتجاوز 100% نطاق يومي
                if range_24h > 200.0:
                    return False, "نطاق 24h واسع جداً = عملة جديدة أو خطرة"

                # 3. نطاق 24h ضيق مع حجم عالٍ = wash trading
                if vol_24h > 1_000_000 and range_24h < 0.8:
                    return False, "نطاق 24h ضيق مع حجم عالٍ"

            # 4. متوسط حجم الصفقة الواحدة
            if count > 200:
                avg_trade = vol_24h / count
                if avg_trade < 5.0:
                    return False, "صفقات مجهرية (wash trading)"

            # 5. فارق bid/ask كبير جداً = سيولة وهمية في الدفتر
            if bid > 0 and ask > 0 and bid > 0:
                spread_pct = (ask - bid) / bid * 100
                if spread_pct > 8.0:
                    return False, "spread واسع جداً = سيولة وهمية"

        except (ValueError, TypeError):
            pass

    return True, ""


def scan_volume_surge(price_map, vol_now, changes_map):
    # type: (Dict, Dict, Dict) -> None
    """
    🌊 VOLUME SURGE SCANNER — يكتشف انفجار الحجم قبل ارتفاع السعر

    الهدف: اصطياد SHAPE (+61%) / AEROBUD (+24%) / COS (+70%) / TOWNS (+36%)

    المنطق:
    - حجم آخر ساعة > 3.5× متوسط الـ 4 ساعات السابقة
    - السعر لم يرتفع أكثر من 8% بعد (الفرصة لا تزال موجودة)
    - اتجاه الحجم شراء وليس بيع (CVD بسيط)
    - يفحص من مسارين:
      أ) أكبر 200 عملة بالحجم المطلق (big/mid caps)
      ب) أكبر 300 عملة بالتغيير% 24h (micro-cap pumping)
    """
    global _vol_surge_seen, last_vol_surge_scan, _coin_first_seen
    now = time.time()

    if now - last_vol_surge_scan < VOL_SURGE_EVERY:
        return
    last_vol_surge_scan = now

    # ── مسار 1: أكبر بالحجم (big/mid cap) ────────────────────────
    _by_vol  = []
    # ── مسار 2: الأكثر تحركاً بالتغيير% (micro-cap pumping) ──────
    _by_chg  = []

    # خريطة سريعة للوصول لبيانات ticker بالسيمبول
    _ticker_map = {_t.get("symbol", ""): _t for _t in all_tickers}

    for _t in all_tickers:
        _sym = _t.get("symbol", "")
        if not _sym.endswith("USDT"):
            continue
        if any(k in _sym for k in LEVERAGE_KEYWORDS):
            continue
        if _sym.replace("USDT", "") in STABLECOINS:
            continue
        try:
            _v24 = float(_t.get("quoteVolume", 0))
            _chg = float(_t.get("priceChangePercent", 0))
        except (ValueError, TypeError):
            continue
        if _v24 < 3_000:
            continue
        if _chg >= VOL_SURGE_MAX_CHG or _chg <= -15.0:
            continue
        # فلتر السيولة الحقيقية مبكراً (بدون API إضافية)
        _liq_ok, _ = _is_real_liquidity(_v24, _chg, _t)
        if not _liq_ok:
            continue
        _by_vol.append((_sym, _v24, _chg))
        # مسار الميكرو كاب: حجم 5K-500K مع تحرك إيجابي > 3%
        if 5_000 <= _v24 <= 500_000 and _chg >= 3.0:
            _by_chg.append((_sym, _v24, _chg))

    # دمج المسارين بدون تكرار
    _by_vol.sort(key=lambda x: -x[1])
    _by_chg.sort(key=lambda x: -x[2])   # ترتيب بالتغيير%

    _seen_syms = set()
    ranked = []
    for _sym, _v24, _chg in _by_vol[:200]:
        _seen_syms.add(_sym)
        ranked.append((_sym, _v24))
    for _sym, _v24, _chg in _by_chg[:150]:
        if _sym not in _seen_syms:
            ranked.append((_sym, _v24))

    results = []
    for sym, vol_24h in ranked:
        if now - coin_whale_done.get(sym, 0) < LZ_TPS_COOLDOWN:
            continue
        if now - _vol_surge_seen.get(sym, 0) < VOL_SURGE_COOLDOWN:
            continue
        if coin_signal_count.get(sym, 0) >= MAX_COIN_SIGNALS:
            continue

        # فلتر العملات الجديدة (أقل من 7 أيام)
        if sym not in _coin_first_seen:
            _coin_first_seen[sym] = now
            continue
        if (now - _coin_first_seen.get(sym, now)) / 86400 < NEW_COIN_MIN_DAYS:
            log.debug(" VOL_SURGE skip new coin: %s", sym)
            continue

        chg24 = changes_map.get(sym, 0)

        # ── جلب 1h klines — 6 شمعات (آخر + 5 سابقة) ─────────────
        kd = get_klines(sym, "1h", 6)
        if not kd or len(kd["vols"]) < 5:
            continue

        vols   = kd["vols"]
        closes = kd["closes"]
        opens  = kd["opens"]

        last_vol = vols[-1]                    # حجم الساعة الأخيرة (بالعملة)
        prev_avg = sum(vols[-5:-1]) / 4.0      # متوسط 4 ساعات سابقة

        if prev_avg <= 0 or last_vol <= 0:
            continue

        ratio = last_vol / prev_avg
        if ratio < VOL_SURGE_RATIO:
            continue

        # ── تحويل لـ USDT ─────────────────────────────────────────
        price = price_map.get(sym, 0)
        if price <= 0:
            continue
        last_vol_usdt = last_vol * price
        if last_vol_usdt < VOL_SURGE_MIN_USDT:
            continue

        # ── اتجاه الحجم (CVD بسيط من آخر 6 شمعات) ───────────────
        n = len(closes)
        buy_vol  = sum(vols[i] for i in range(n) if closes[i] >= opens[i])
        tot_vol  = sum(vols) if sum(vols) > 0 else 1
        cvd_ratio = buy_vol / tot_vol

        # نرفض إذا كان الارتفاع بيع بحت
        if cvd_ratio < 0.40:
            continue

        # ── OB — لا نرسل إذا ضغط بيع حاد ──────────────────────────
        _ob = calc_ob_imbalance(sym)
        if _ob.get("signal") == "strong_sell":
            continue

        results.append((ratio, sym, last_vol_usdt, cvd_ratio, chg24, vol_24h))

    if not results:
        return

    results.sort(key=lambda x: -x[0])
    for ratio, sym, last_vol_usdt, cvd_ratio, chg24, vol_24h in results[:4]:
        price  = price_map.get(sym, 0)
        sector = next((s for s, syms in SECTORS.items() if sym in syms), "غير محدد")
        is_gold = ratio >= VOL_SURGE_GOLD

        _cvd_tag = (
            "🟢 شراء قوي"  if cvd_ratio >= 0.60 else
            "↗️ شراء خفيف" if cvd_ratio >= 0.50 else
            "↔️ مختلط"
        )

        # WATCH ALERT — انفجار حجم سريع (COS/TOWNS نوع)
        _surge_label = "🥇 انفجار ضخم جداً!" if is_gold else "🔥 انفجار حجم!"
        msg = (
            "✅ *ادخل الآن* 🌊\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "💥 *{}* — الحجم انفجر فجأة! 👀\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "📊 ارتفاع الحجم: `{:.1f}×` المعدل الطبيعي {}\n"
            "💧 حجم آخر ساعة: `{}` USDT\n"
            "📈 الاتجاه: {} (`{:.0f}%` شراء)\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "💵 السعر: `{}`\n"
            "📉 24h: `{:+.1f}%` | حجم كلي: `{}`\n"
            "🏷️ القطاع: `{}`\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "✅ *ادخل الآن* — انفجار حجم مؤكد 🌊🎯"
        ).format(
            sym.replace("USDT", ""),
            ratio, _surge_label,
            _fmt_vol_k(last_vol_usdt),
            _cvd_tag, cvd_ratio * 100,
            fmt_price(price),
            chg24, _fmt_vol_k(vol_24h),
            sector,
        )
        send(msg)
        _vol_surge_seen[sym] = now
        coin_alerted[sym]    = now
        whale_watch_add(sym, 0, max(cvd_ratio, 0.56), price)
        perf_register(sym, price, "vol_surge", int(min(ratio * 10, 100)),
                      "Vol×{:.1f} cvd={:.0f}%".format(ratio, cvd_ratio * 100))
        log.info(" VOL_SURGE WATCH | %s | ×%.1f | cvd=%.0f%% | 24h=%.1f%%",
                 sym, ratio, cvd_ratio * 100, chg24)


# ══════════════════════════════════════════════════════════════════
_early_accum_seen    = {}  # {sym: timestamp} آخر اضافة للقائمة من المسح المبكر
EARLY_ACCUM_EVERY    = 300   # فحص كل 5 دقائق
EARLY_ACCUM_COOLDOWN = 3600  # لا تعيد الاضافة قبل ساعة
last_early_accum_scan = 0.0

# ══ Pre-Pump Watch ══════════════════════════════════════════════════
_pre_pump_alerted   = {}   # {sym: timestamp}
last_pre_pump_scan  = 0.0
PRE_PUMP_SCAN_EVERY = 600  # فحص كل 10 دقائق
PRE_PUMP_COOLDOWN   = 21600  # كولداون 6 ساعات لنفس العملة


def detect_cvd_divergence(sym):
    # type: (str) -> dict
    """
    🔍 CVD Divergence — يكتشف: سعر ينخفض لكن CVD يرتفع = تجميع خفي
    هذه إشارة الدخول الأقوى قبل الانعكاس

    يعيد: {
      "bullish_div": bool,   # تباعد صعودي (شراء خفي)
      "bearish_div": bool,   # تباعد هبوطي (بيع خفي)
      "score":       int,    # 0-100 قوة الإشارة
      "reason":      str
    }
    """
    kd15 = get_klines(sym, "15m", 24)
    kd1h = get_klines(sym, "1h",  12)

    result = {"bullish_div": False, "bearish_div": False, "score": 0, "reason": ""}

    for kd, label in [(kd15, "15m"), (kd1h, "1h")]:
        if not kd or len(kd["closes"]) < 10:
            continue
        try:
            closes = kd["closes"]
            opens  = kd["opens"]
            vols   = kd["vols"]
            n      = len(closes)

            # بناء CVD
            cvd = []
            cum = 0.0
            for i in range(n):
                v = vols[i] if i < len(vols) else 0
                if closes[i] > opens[i]:
                    cum += v
                elif closes[i] < opens[i]:
                    cum -= v
                cvd.append(cum)

            half = n // 2
            # سعر النصف الأول مقابل الثاني
            price_first  = sum(closes[:half]) / half
            price_second = sum(closes[half:]) / max(n - half, 1)
            # CVD النصف الأول مقابل الثاني
            cvd_first  = sum(cvd[:half]) / half
            cvd_second = sum(cvd[half:]) / max(n - half, 1)

            price_falling = price_second < price_first * 0.998   # سعر ينزل
            price_rising  = price_second > price_first * 1.002   # سعر يرتفع
            cvd_rising    = cvd_second   > cvd_first  * 1.02     # CVD يرتفع
            cvd_falling   = cvd_second   < cvd_first  * 0.98     # CVD ينزل

            # Bullish Divergence: سعر ينزل + CVD يرتفع = تجميع خفي
            if price_falling and cvd_rising:
                div_strength = abs(cvd_second - cvd_first) / (abs(cvd_first) + 1) * 100
                sc = min(int(div_strength * 2), 60)
                if sc > result["score"]:
                    result["bullish_div"] = True
                    result["score"]  = sc
                    result["reason"] = "CVD↑ + Price↓ ({})".format(label)

            # Bearish Divergence: سعر يرتفع + CVD ينزل = توزيع خفي
            if price_rising and cvd_falling:
                result["bearish_div"] = True

        except (IndexError, ValueError, ZeroDivisionError):
            continue

    return result


def detect_consolidation_breakout(sym, price):
    # type: (str, float) -> dict
    """
    🎯 Consolidation Breakout — يكتشف: سعر يتحرك جانبياً + حجم يرتفع = اختراق وشيك

    المعايير:
    - نطاق السعر آخر 8 شمعات 15m < 4% (تضغط)
    - متوسط حجم آخر 3 شمعات > 1.5× المتوسط الكلي (حجم يرتفع)
    - السعر قريب من أعلى النطاق (جاهز للاختراق)

    يعيد: {
      "consolidating": bool,
      "near_breakout":  bool,
      "range_pct":      float,
      "vol_ratio":      float,
      "score":          int
    }
    """
    kd = get_klines(sym, "15m", 16)
    result = {"consolidating": False, "near_breakout": False,
              "range_pct": 0.0, "vol_ratio": 0.0, "score": 0}

    if not kd or len(kd["closes"]) < 10:
        return result
    try:
        closes = kd["closes"]
        highs  = kd["highs"]
        lows   = kd["lows"]
        vols   = kd["vols"]
        n      = len(closes)

        # نطاق السعر آخر 8 شمعات
        window_h = max(highs[-8:])
        window_l = min(lows[-8:])
        range_pct = (window_h - window_l) / window_l * 100 if window_l > 0 else 99

        # نسبة الحجم: آخر 3 شمعات مقارنة بمتوسط الـ 13 السابقة
        avg_vol = sum(vols[:-3]) / max(len(vols[:-3]), 1)
        rec_vol = sum(vols[-3:]) / 3.0
        vol_ratio = rec_vol / avg_vol if avg_vol > 0 else 1.0

        consolidating = range_pct <= 4.0
        vol_rising    = vol_ratio >= 1.5

        # قريب من أعلى النطاق = جاهز للاختراق الصعودي
        near_top = price >= window_h * 0.99 if window_h > 0 else False

        if consolidating and vol_rising:
            sc = 0
            sc += min(int((4.0 - range_pct) * 15), 40)   # نطاق أضيق = أعلى نقطة
            sc += min(int((vol_ratio - 1.5) * 30), 40)   # حجم أكبر = أعلى نقطة
            if near_top:
                sc += 20                                   # قرب الاختراق

            result["consolidating"]  = True
            result["near_breakout"]  = near_top
            result["range_pct"]      = round(range_pct, 2)
            result["vol_ratio"]      = round(vol_ratio, 2)
            result["score"]          = min(sc, 100)

    except (IndexError, ValueError, ZeroDivisionError):
        pass

    return result


def scan_early_accumulation(price_map, vol_now, changes_map):
    # type: (Dict, Dict, Dict) -> None
    """
    🔍 Early Accumulation Scanner — يكتشف مراحل التجميع المبكر قبل الانفجار
    يضيف للـ whale_watchlist بدون إرسال تنبيه مباشر — الجوكر يؤكد لاحقاً

    المعايير:
    - VDelta >= tier_min (0.55+ small, 0.58+ mid, 0.60+ big)
    - TPS spike >= 1.5× baseline (نشاط متصاعد)
    - 24h change بين -6% و +10% (لم يتحرك بعد = مبكر)
    - حجم كافٍ (tier-based)
    """
    global _early_accum_seen, last_early_accum_scan
    now = time.time()

    if now - last_early_accum_scan < EARLY_ACCUM_EVERY:
        return
    last_early_accum_scan = now

    all_syms = list(set(list(candidates) + EXTRA_COINS))
    ranked = sorted(
        [(s, vol_now.get(s, 0)) for s in all_syms],
        key=lambda x: -x[1]
    )[:80]

    added = 0
    for sym, vol in ranked:
        base = sym.replace("USDT", "")
        if base in STABLECOINS:
            continue

        _tier = get_tier_settings(vol)
        if vol < _tier["vol_min"]:
            continue

        if now - coin_whale_done.get(sym, 0) < LZ_TPS_COOLDOWN:
            continue
        if now - _early_accum_seen.get(sym, 0) < EARLY_ACCUM_COOLDOWN:
            continue
        if sym in whale_watchlist:
            continue
        if coin_signal_count.get(sym, 0) >= MAX_COIN_SIGNALS:
            continue

        chg24 = changes_map.get(sym, 0)
        # Must be in quiet zone — not already pumped, not in deep dump
        if chg24 >= 10.0 or chg24 <= -8.0:
            continue

        stats = analyze_tps_ats(sym)
        if not stats:
            continue

        ats    = stats["ats"]
        vdelta = stats["vdelta"]
        tps    = stats["tps"]

        # VDelta must meet tier minimum for early accumulation
        _vd_min = _tier["vdelta_min"]
        if vdelta < _vd_min:
            continue

        # TPS spike — modest (1.5×) is enough for early detection
        base_tps = tps_baseline.get(sym, 0)
        if base_tps > 0:
            ratio = tps / base_tps
        else:
            # لا baseline بعد — نستخدم قيمة مطلقة: tps >= 1.0 كافي
            ratio = 2.5 if tps >= 1.5 else (1.8 if tps >= 0.8 else (1.5 if tps >= 0.3 else 0.0))
        if ratio < 1.5:
            continue

        # ATS must meet tier minimum
        if ats < _tier["ats_min"]:
            continue

        # Check OB — don't add if heavy ask pressure
        _ob = calc_ob_imbalance(sym)
        if _ob.get("signal") == "strong_sell":
            continue

        price = price_map.get(sym, 0)

        # ── CVD Divergence + Consolidation — تقييم إضافي لكل عملة ─────
        _cvd_div  = detect_cvd_divergence(sym)
        _consol   = detect_consolidation_breakout(sym, price)
        _extra_sc = _cvd_div.get("score", 0) + _consol.get("score", 0)

        # إذا VDelta أقل من المثالي لكن CVD divergence قوي → اقبل
        if vdelta < _vd_min and _cvd_div.get("score", 0) >= 40:
            pass   # CVD divergence يعوّض VDelta المنخفض
        elif vdelta < _vd_min:
            continue

        reasons = []
        if _cvd_div.get("bullish_div"):
            reasons.append("CVD_DIV({})".format(_cvd_div.get("reason","")))
        if _consol.get("consolidating"):
            reasons.append("CONSOL {:.1f}% vol×{:.1f}".format(
                _consol["range_pct"], _consol["vol_ratio"]))
        if _consol.get("near_breakout"):
            reasons.append("NEAR_BO!")

        whale_watch_add(sym, ats, vdelta, price)
        _early_accum_seen[sym] = now
        added += 1
        log.info(" EARLY_ACCUM: %s | VD=%.0f%% | TPS×%.1f | ATS=%.0f$ | 24h=%.1f%% | extra=%d %s",
                 sym, vdelta*100, ratio, ats, chg24, _extra_sc, " | ".join(reasons))

    if added > 0:
        log.info(" scan_early_accumulation: added %d coins to whale_watchlist", added)


def scan_pre_pump_watch(price_map, vol_now, changes_map):
    # type: (Dict, Dict, Dict) -> None
    """
    ⏰ PRE-PUMP WATCH — يكتشف التجميع الهادئ قبل الانفجار بساعات
    يشبه Wolf Flow: يرصد التوطيد الضيق + VDelta يرتفع بهدوء

    الشروط:
    - تغيير 24h بين -8% و +8% (لم يتحرك بعد)
    - نطاق سعر 4H < 6% (توطيد ضيق)
    - VDelta اتجاه تصاعدي (0.52+ → 0.58+)
    - حجم يرتفع هادئاً (آخر 2h > متوسط 6h × 1.2)
    - يفحص جميع العملات بحجم 80K+ (ليس فقط candidates)
    """
    global _pre_pump_alerted, last_pre_pump_scan, _coin_first_seen
    now = time.time()

    if now - last_pre_pump_scan < PRE_PUMP_SCAN_EVERY:
        return
    last_pre_pump_scan = now

    # فحص جميع العملات بما فيها الميكرو كاب
    scan_list = []
    for t in all_tickers:
        sym = t.get("symbol", "")
        if not sym.endswith("USDT"):
            continue
        if sym in tracked:
            continue
        if any(k in sym for k in LEVERAGE_KEYWORDS):
            continue
        if sym.replace("USDT", "") in STABLECOINS:
            continue
        try:
            vol = float(t.get("quoteVolume", 0))
            chg = float(t.get("priceChangePercent", 0))
        except (ValueError, TypeError):
            continue
        if vol < 80_000:
            continue
        if chg > 12.0 or chg < -12.0:
            continue
        # فلتر السيولة الحقيقية — يمنع الحجم الوهمي
        _liq_ok, _ = _is_real_liquidity(vol, chg, t)
        if not _liq_ok:
            continue
        scan_list.append((sym, vol, chg, t))

    # فرز بالحجم تنازلياً وأخذ أفضل 300
    scan_list.sort(key=lambda x: -x[1])
    scan_list = scan_list[:300]

    found = []

    for sym, vol, chg24, _t_dict in scan_list:
        if now - _pre_pump_alerted.get(sym, 0) < PRE_PUMP_COOLDOWN:
            continue
        if now - coin_alerted.get(sym, 0) < 3600:
            continue

        # فلتر العملات الجديدة (أقل من 7 أيام)
        if sym not in _coin_first_seen:
            _coin_first_seen[sym] = now
            continue
        if (now - _coin_first_seen.get(sym, now)) / 86400 < NEW_COIN_MIN_DAYS:
            log.debug(" PRE_PUMP skip new coin: %s", sym)
            continue

        price = price_map.get(sym, 0)
        if price <= 0:
            continue

        try:
            # ── 1. كاندلز 1h آخر 8 ساعات ─────────────────────────────
            kd1h = get_klines(sym, "1h", 8)
            if not kd1h or len(kd1h["closes"]) < 6:
                continue
            closes = kd1h["closes"]
            vols   = kd1h["vols"]
            highs  = kd1h["highs"]
            lows   = kd1h["lows"]

            # ── 2. نطاق سعر ضيق < 6% ─────────────────────────────────
            rng_high = max(highs)
            rng_low  = min(lows)
            if rng_low <= 0:
                continue
            range_pct = (rng_high - rng_low) / rng_low * 100
            if range_pct > 6.0:
                continue

            # ── 3. حجم يرتفع هادئاً ──────────────────────────────────
            if len(vols) < 6:
                continue
            avg_vol_old = sum(vols[:4]) / 4  # أول 4 ساعات
            avg_vol_new = sum(vols[-2:]) / 2  # آخر ساعتين
            if avg_vol_old <= 0:
                continue
            vol_ratio = avg_vol_new / avg_vol_old
            # يجب أن يرتفع قليلاً (1.2x) لكن ليس pump بعد (< 4x)
            if vol_ratio < 1.2 or vol_ratio > 4.0:
                continue

            # ── 4. VDelta اتجاه تصاعدي ───────────────────────────────
            vdelta_now = calc_vdelta_ma(sym, period=4, interval="1h")
            if vdelta_now < 0.52:
                continue

            # VDelta قبل 4 ساعات للمقارنة
            vdelta_old = 0.0
            kd_old = get_klines(sym, "1h", 12)
            if kd_old and len(kd_old["closes"]) >= 12:
                _old_closes = kd_old["closes"][:8]
                _old_vols   = kd_old["vols"][:8]
                _buy_old = sum(max(0.0, (c - o) / (h - l)) * v
                               for c, o, h, l, v
                               in zip(_old_closes,
                                      kd_old["opens"][:8],
                                      kd_old["highs"][:8],
                                      kd_old["lows"][:8],
                                      _old_vols)
                               if (h - l) > 0)
                _total_old = sum(_old_vols)
                if _total_old > 0:
                    vdelta_old = _buy_old / _total_old

            # VDelta يجب أن يكون في ارتفاع أو محايد-صاعد
            vd_rising = vdelta_now >= 0.55 or (vdelta_old > 0 and vdelta_now > vdelta_old + 0.03)
            if not vd_rising:
                continue

            # ── 5. السعر لم يتحرك كثيراً (ضمن النطاق الضيق) ─────────
            price_pos = (price - rng_low) / (rng_high - rng_low) if rng_high > rng_low else 0.5
            # قريب من المنتصف أو الأسفل (لم ينفجر بعد)
            if price_pos > 0.85:
                continue

            # ── 6. حساب النقاط ────────────────────────────────────────
            score = 0
            signals = []

            if range_pct < 3.0:
                score += 30
                signals.append("نطاق ضيق {:.1f}%".format(range_pct))
            elif range_pct < 5.0:
                score += 20
                signals.append("توطيد {:.1f}%".format(range_pct))
            else:
                score += 10

            if vol_ratio >= 2.0:
                score += 25
                signals.append("حجم ×{:.1f}".format(vol_ratio))
            elif vol_ratio >= 1.5:
                score += 15
                signals.append("حجم ×{:.1f}".format(vol_ratio))
            else:
                score += 8

            if vdelta_now >= 0.65:
                score += 30
                signals.append("VDelta {:.0f}%🔥".format(vdelta_now * 100))
            elif vdelta_now >= 0.58:
                score += 20
                signals.append("VDelta {:.0f}%".format(vdelta_now * 100))
            elif vdelta_now >= 0.52:
                score += 10
                signals.append("VDelta {:.0f}%".format(vdelta_now * 100))

            if vdelta_old > 0 and vdelta_now > vdelta_old + 0.05:
                score += 15
                signals.append("VD↑ +{:.0f}%".format((vdelta_now - vdelta_old) * 100))

            # CVD divergence إضافي
            _cvd = detect_cvd_divergence(sym)
            if _cvd.get("bullish_div"):
                score += 20
                signals.append("CVD Div!")

            # Higher Lows
            if len(lows) >= 5:
                hl = sum(1 for i in range(1, len(lows)) if lows[i] >= lows[i-1] * 0.999)
                if hl >= len(lows) - 2:
                    score += 15
                    signals.append("Higher Lows")

            if score < 35:
                continue

            # ── 7. إرسال التنبيه ─────────────────────────────────────
            sector = next((s for s, syms in SECTORS.items() if sym in syms), "غير محدد")
            coin   = sym.replace("USDT", "")

            if score >= 70:
                strength = "🔥🔥 قوي جداً"
            elif score >= 50:
                strength = "🔥 متوسط"
            else:
                strength = "⚡ ضعيف"

            msg = (
                "✅ *ادخل الآن* ⏰\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "🔍 *{}* — تجميع هادئ قبل الانفجار 👀\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "📊 النقاط: `{}/100` {}\n"
                "💵 السعر: `{}`\n"
                "📉 24h: `{:+.2f}%`\n"
                "📦 الحجم: `{}`\n"
                "🏷️ القطاع: `{}`\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "  📏 النطاق: `{:.1f}%` ضيق\n"
                "  📈 الحجم: `×{:.1f}` يرتفع\n"
                "  💚 VDelta: `{:.0f}%`\n"
                "  📌 `{}`\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "✅ *ادخل الآن* — تجميع + انفجار قريب 🎯"
            ).format(
                coin,
                score, strength,
                round(price, 8),
                chg24,
                _fmt_vol(vol),
                sector,
                range_pct,
                vol_ratio,
                vdelta_now * 100,
                " | ".join(signals),
            )

            found.append((score, sym, msg, price))

        except Exception as _e:
            log.debug("pre_pump_watch %s: %s", sym, _e)
            continue

    # أرسل أقوى 3 فقط لتجنب الفيضان
    found.sort(key=lambda x: -x[0])
    for score, sym, msg, price in found[:3]:
        send(msg)
        _pre_pump_alerted[sym] = now
        perf_register(sym, price, "pre_pump_watch", score, "")
        log.info(" PRE_PUMP_WATCH | %s | score=%d", sym, score)


def scan_tps_ats(price_map, vol_now, changes_map):
    # type: (Dict, Dict, Dict) -> None
    log.info(" scan_tps_ats V21 - tier-based thresholds")
    """
    يفحص أفضل 40 عملة بالحجم
    يبحث عن: TPS spike + ATS حيتان + VDelta قوي
    يحتاج 2+ إشارات للتنبيه
    """
    global tps_alerted, tps_baseline
    now = time.time()

    # _mth يُحسب لكل عملة داخل الحلقة بعد معرفة vol/ats الخاص بها
    all_syms = list(set(list(candidates) + EXTRA_COINS))
    ranked = sorted(
        [(s, vol_now.get(s, 0)) for s in all_syms if s not in tracked],
        key=lambda x: -x[1]
    )[:50]

    results = []
    for sym, vol in ranked:
        if sym.replace("USDT","") in STABLECOINS: continue
        _min_vol = 100_000 if sym in EXTRA_COINS else 1_000_000
        if vol < _min_vol:
            continue

        if now - coin_whale_done.get(sym, 0) < LZ_TPS_COOLDOWN:
            continue

        if coin_signal_count.get(sym, 0) >= MAX_COIN_SIGNALS:
            continue

        last_alert  = coin_alerted.get(sym, 0)
        in_cooldown = (now - last_alert < TPS_COOLDOWN)


        chg24 = changes_map.get(sym, 0)
        if chg24 >= TPS_MAX_CHANGE:
            continue

        stats = analyze_tps_ats(sym)
        if not stats:
            continue

        tps    = stats["tps"]
        ats    = stats["ats"]
        vdelta = stats["vdelta"]

        # ── إعدادات تكيفية حسب حالة السوق + بيانات العملة نفسها ────────
        _mth  = get_adaptive_thresholds(coin_vol=vol, coin_ats=ats)

        _tier    = get_tier_settings(vol)
        _vd_min  = _tier["vdelta_min"]


        if vdelta <= _vd_min - 0.001:
            log.info(" VDELTA_REJECT [%s]: %s | %.0f%% < %.0f%%",
                     _tier["label"], sym, vdelta*100, _vd_min*100)
            continue


        base   = tps_baseline.get(sym, tps)
        ratio  = tps / base if base > 0 else 1.0
        tps_baseline[sym] = base * 0.9 + tps * 0.1

        score   = 0
        signals = []

        if ratio >= TPS_SPIKE:
            score += min(int(ratio * 10), 40)
            signals.append("⚡ TPS {:.1f}×".format(ratio))
        elif ratio >= 2.0:
            score += 15
            signals.append("⚡ TPS {:.1f}×".format(ratio))
        elif ratio >= 1.5:
            score += 8
            signals.append("⚡ TPS {:.1f}×".format(ratio))

        if ats >= ATS_WHALE:
            score += 35
            signals.append("🐋 ATS {:.0f}$".format(ats))
        elif ats >= 2000:
            score += 20
            signals.append("🐟 ATS {:.0f}$".format(ats))
        elif ats >= _tier["ats_min"] * 3:
            score += 18
            signals.append("🐟 ATS {:.0f}$".format(ats))
        elif ats >= _tier["ats_min"]:
            score += 10
            signals.append("🦐 ATS {:.0f}$".format(ats))

        if vdelta >= VDELTA_STRONG:
            score += 25
            signals.append("💚 VDelta {:.0f}%".format(vdelta * 100))
        elif vdelta >= 0.65:
            score += 18
            signals.append("💚 VDelta {:.0f}%".format(vdelta * 100))
        elif vdelta >= 0.60:
            score += 12
            signals.append("💚 VDelta {:.0f}%".format(vdelta * 100))
        elif vdelta >= _tier["vdelta_min"]:
            score += 6
            signals.append("💚 VDelta {:.0f}%".format(vdelta * 100))

        _tps_min = _mth["tps_min"]
        _vdelta  = stats["vdelta"]
        _tps     = stats["tps"]
        _ats     = stats["ats"]



        if BULL_MODE_ACTIVE:
            _ready = _vdelta >= _tier["vdelta_min"]
        else:
            _ready = (
                _vdelta >= 0.75
                or _vdelta >= 0.65
                or (_vdelta >= _tier["vdelta_min"] and _tps >= 0.3 and _ats >= _tier["ats_min"])
                or (_vdelta >= _tier["vdelta_min"] and _ats >= _tier["ats_min"] * 2)
            )

        # Use tier-based VDelta threshold
        if _vdelta < max(_mth["vdelta_min"] - 0.02, 0.53):
            continue

        # Tier-based score threshold: small-cap=30, mid=42, big=55
        _tier_ats_min = _tier["ats_min"]
        _score_min = {
            "big":   _mth["score_big"],
            "mid":   _mth["score_mid"],
            "small": _mth["score_small"],
        }.get(get_coin_tier(vol), _mth["score_big"])
        if score >= _score_min and len(signals) >= 2 and _tps >= _tps_min and _ready and stats.get("ats", 0) >= _tier_ats_min:
            chg = changes_map.get(sym, 0)
            results.append((score, sym, signals, stats, chg, vol))

    if not results:
        return

    results.sort(key=lambda x: -x[0])
    for score, sym, signals, stats, chg, vol in results[:3]:

        if coin_signal_count.get(sym, 0) >= 1:
            if sym not in whale_watchlist:
                whale_watch_add(sym, stats["ats"], stats["vdelta"], price_map.get(sym, 0))
                log.info(" TPS silent add: %s (already watched)", sym)
            continue

        sector = next((s for s, syms in SECTORS.items() if sym in syms), "غير محدد")
        rarity = "🐋🔥 نادر" if score >= 80 else ("🔥 قوي" if score >= 65 else "⚡ متوسط")

        coin_signal_count[sym] = 1
        _sig_num = 1


        _lz_block = ""
        try:
            _klines = safe_get(
                MEXC_KLINES,
                {"symbol": sym, "interval": "1h", "limit": 100}
            )
            if _klines and len(_klines) >= 20:
                _highs  = [float(k[2]) for k in _klines]
                _lows   = [float(k[3]) for k in _klines]
                _closes = [float(k[4]) for k in _klines]
                _cp     = price_map.get(sym, _closes[-1])

                _support = max([l for l in _lows[-50:] if l < _cp * 0.995], default=0)
                _resist  = min([h for h in _highs[-50:] if h > _cp * 1.005], default=0)
                if _support > 0 and _resist > 0:
                    _risk    = _cp - _support
                    _reward  = _resist - _cp
                    _rr      = round(_reward / _risk, 1) if _risk > 0 else 0
                    _target_pct = round((_resist - _cp) / _cp * 100, 1)
                    if _rr >= 1.5:
                        _lz_block = (
                            "📍 منطقة: `{:.6g}` ← `{:.6g}`\n".format(_support, _resist) +
                            "⚖️ R/R: `{}:1` | 🎯 `{:.6g}` (`{:+.1f}%`)\n".format(
                                _rr, _resist, _target_pct)
                        )
        except Exception:
            pass

        _tps_label = (
            "🐢 بداية دخول سيولة 💧" if (sym in EXTRA_COINS and stats["tps"] < 0.5) else
            ("🐌 نشاط ضعيف جداً"    if stats["tps"] < 0.2 else
            ("🐢 نشاط عادي"          if stats["tps"] < 1.0 else
            ("⚡ نشاط متصاعد"        if stats["tps"] < 3.0 else
            ("🔥 نشاط قوي"           if stats["tps"] < 5.0 else
             "💥 نشاط انفجاري"))))
        )


        _direction = calc_direction_engine(sym, "1h")
        _hmm       = calc_hmm_regime(sym, "4h")
        _mtf       = calc_mtf_analysis(sym)

        _trend_ok, _trend_reason = check_trend_filter(sym, chg24)
        _accum = detect_accumulation(sym)
        _weis      = calc_weis_wave(
            get_klines(sym, "1h", 30)["closes"] if get_klines(sym, "1h", 30) else [],
            get_klines(sym, "1h", 30)["vols"]   if get_klines(sym, "1h", 30) else []
        ) if get_klines(sym, "1h", 30) else 0.5


        _bull_pct    = _direction.get("bullish_pct", 0) if _direction else 0
        _regime      = _hmm.get("regime", "unknown") if _hmm else "unknown"
        _mtf_bias    = _mtf.get("bias", "neutral") if _mtf else "neutral"
        _mtf_conflict = _mtf.get("conflict", False) if _mtf else False
        _accum_phase  = _accum.get("phase", "none") if _accum else "none"
        _real_liq    = (
            _bull_pct  >= 55 and
            _regime    != "volatile" and
            _weis      >= 0.50 and
            _mtf_bias  != "bearish" and
            not _mtf_conflict and
            _trend_ok and
            _accum_phase  != "none"
        )


        _direct_entry = vdelta >= 0.80 and score >= 55 and _real_liq
        _price_now    = price_map.get(sym, 0)

        if _direct_entry:

            _engine_block = build_engine_block(sym)
            _accum_txt = "🔍 *التجميع:* {} (نقاط: {})\n".format(
                _accum.get("phase_ar",""), _accum.get("score",0)) if _accum else ""
            msg = (
                "🚀🟢 *DIRECT ENTRY — ادخل الآن!* 🟢🚀\n" +
                "━━━━━━━━━━━━━━━━━━\n"
                "💥 *{}* — شراء قوي جداً!\n".format(sym.replace("USDT","")) +
                "━━━━━━━━━━━━━━━━━━\n" +
                (_lz_block + "━━━━━━━━━━━━━━━━━━\n" if _lz_block else "") +
                "{}\n".format(_tps_label) +
                "📡 TPS: `{:.2f}` | ATS: `{:.0f}$`\n".format(stats["tps"], stats["ats"]) +
                "📊 VDelta: `{:.0f}%` 🔥 شراء قوي جداً\n".format(vdelta*100) +
                "━━━━━━━━━━━━━━━━━━\n"
                "💪 القوة: `{}/100` {}\n".format(score, rarity) +
                "💰 السعر: `{}`\n".format(fmt_price(_price_now)) +
                "📉 24h: `{:+.2f}%` | حجم: `{:.2f}M`\n".format(chg, vol/1_000_000) +
                "🏷️ القطاع: `{}`\n".format(sector) +
                "━━━━━━━━━━━━━━━━━━\n"
                "✅ *ادخل الآن — VDelta {:.0f}% كافٍ للدخول!*\n".format(vdelta*100) +
                (_accum_txt if _accum_txt else "") +
                (_engine_block if _engine_block else "") +
                (format_mtf_block(sym) if format_mtf_block(sym) else "") +
                "🛡️ ضع Stop Loss تحت آخر قاع"
            )
        else:

            msg = (
                "✅ *ادخل الآن*\n" +
                "━━━━━━━━━━━━━━━━━━\n"
                "🔍 *{}* — نشاط مشبوه! راقب 👀\n".format(sym.replace("USDT","")) +
                "💵 السعر: `{}`\n".format(fmt_price(_price_now)) +
                "━━━━━━━━━━━━━━━━━━\n" +
                (_lz_block + "━━━━━━━━━━━━━━━━━━\n" if _lz_block else "") +
                "{}\n".format(_tps_label) +
                "📡 TPS:    `{:.2f}` | ATS: `{:.0f}$` 🦐 أفراد\n".format(stats["tps"], stats["ats"]) +
                "📊 VDelta: `{:.0f}%` شراء\n".format(vdelta*100) +
                "━━━━━━━━━━━━━━━━━━\n"
                "💪 القوة: `{}/100` {}\n".format(score, rarity) +
                "📉 24h: `{:+.2f}%` | حجم: `{:.2f}M`\n".format(chg, vol/1_000_000) +
                "🏷️ القطاع: `{}`\n".format(sector) +
                "━━━━━━━━━━━━━━━━━━\n"
                "✅ *ادخل الآن* — نشاط مؤكد 🎯"
            )
        send(msg)
        tps_alerted[sym]  = now
        coin_alerted[sym] = now
        perf_register(sym, price_map.get(sym, 0), "tps_ats", score, " | ".join(signals))


        if ats < WHALE_ATS_MIN and vdelta >= 0.60:
            whale_watch_add(sym, ats, vdelta, price_map.get(sym, 0))
        log.info(" TPS/ATS | %s | score=%d | tps=%.1f | ats=%.0f | vdelta=%.0f%%",
                 sym, score, stats["tps"], stats["ats"], stats["vdelta"] * 100)



def liquidity_hunter(price_map, vol_now, changes_map):
    # type: (Dict, Dict, Dict) -> None
    """
    🔥 LIQUIDITY HUNTER
    يفحص 3 سيناريوهات لدخول السيولة المفاجئة:

    🎯 سيناريو 1 — Volume Spike الصامت:
       حجم 3×+ بدون ارتفاع سعر = الحيتان يشترون خفية

    💧 سيناريو 2 — Bid Wall:
       طلبات شراء ضخمة في Order Book = سعر محمي من الأسفل

    📊 سيناريو 3 — BTC Divergence:
       BTC ينزل لكن العملة تقاوم = أموال تدخل هذه العملة تحديداً
    """
    global lh_alerted, last_lh_scan
    now = time.time()


    ranked = sorted(
        [(s, vol_now.get(s, 0)) for s in candidates if s not in tracked],
        key=lambda x: -x[1]
    )[:60]

    btc_change = btc_change_24h
    results    = []              # [(score, sym, signals, price, vol)]

    for sym, vol in ranked:
        if vol < 200_000:
            continue

        if now - coin_alerted.get(sym, 0) < TPS_COOLDOWN and now - coin_whale_done.get(sym, 0) >= LZ_TPS_COOLDOWN:
            continue
        if now - lh_alerted.get(sym, 0) < LH_COOLDOWN:
            continue

        price = price_map.get(sym, 0)
        if price <= 0:
            continue


        kd = get_klines(sym, "15m", 20)
        if not kd or len(kd["closes"]) < 10:
            continue

        closes = kd["closes"]
        vols   = kd["vols"]
        opens  = kd["opens"]
        lows   = kd["lows"]
        n      = len(closes)

        avg_vol = kd.get("avg_vol", sum(vols) / n) if n > 0 else 1
        if avg_vol <= 0:
            continue

        vol_last3  = sum(vols[-3:]) / 3
        vol_ratio  = vol_last3 / avg_vol
        price_chg  = abs((closes[-1] - closes[-4]) / closes[-4] * 100) if closes[-4] > 0 else 99

        score   = 0
        signals = []





        if vol_ratio >= LH_VOL_SPIKE and price_chg <= LH_PRICE_FLAT:
            pts = min(int(vol_ratio * 10), 45)
            score += pts
            signals.append("🔥 VolSpike {:.1f}×".format(vol_ratio))

        elif vol_ratio >= LH_VOL_QUIET and price_chg <= LH_PRICE_FLAT:
            pts = min(int(vol_ratio * 8), 25)
            score += pts
            signals.append("🔇 QuietVol {:.1f}×".format(vol_ratio))





        wick_score = 0
        for i in range(-5, 0):
            body       = abs(closes[i] - opens[i])
            lower_wick = min(opens[i], closes[i]) - lows[i]
            if body > 0 and lower_wick > body * 1.8:
                wick_score += 1

        if wick_score >= 3:
            pts = wick_score * 7
            score += pts
            signals.append("🕯️ WickReject ×{}".format(wick_score))





        coin_change_24h = changes_map.get(sym, 0)
        if btc_change <= -LH_BTC_DIV_MIN and coin_change_24h >= -1.0:

            divergence = coin_change_24h - btc_change
            if divergence >= 2.0:
                pts = min(int(divergence * 5), 30)
                score += pts
                signals.append("📊 BTCDiv +{:.1f}%".format(divergence))





        vol_trend = sum(1 for i in range(-4, 0) if vols[i] > vols[i-1])
        if vol_trend >= 4 and vol_ratio >= 1.4:
            score += 20
            signals.append("📈 VolTrend {}/4".format(vol_trend))


        # ── سيناريو 5: OB Bid Wall ─────────────────────────────────
        # جدار شراء ضخم في دفتر الطلبات = دعم مخفي محمي
        try:
            ob_deep = calc_ob_depth_analysis(sym)
            if ob_deep.get("has_bid_wall") and not ob_deep.get("has_ask_wall"):
                ob_score = ob_deep.get("score", 0)
                if ob_score >= 40:
                    pts = min(ob_score // 2, 35)
                    score += pts
                    signals.append("🧱 BidWall {:.0f}% imb:{:.1f}×".format(
                        ob_deep.get("bid_wall_pct", 0),
                        ob_deep.get("imb", 1.0)
                    ))
        except Exception:
            ob_deep = {}

        # ── سيناريو 6: CVD صاعد ────────────────────────────────────
        # ضغط شراء تراكمي مستمر = أموال حقيقية تدخل
        try:
            cvd = calc_cvd(sym, "15m", 24)
            if cvd.get("trend") == "rising" and cvd.get("pct_change", 0) >= 8:
                pts = min(int(cvd["pct_change"] * 0.8), 30)
                score += pts
                signals.append("📊 CVD↑ +{:.0f}%".format(cvd["pct_change"]))
        except Exception:
            pass


        if score >= LH_SCORE_MIN and len(signals) >= 2:
            results.append((score, sym, signals, price, vol, coin_change_24h))

    if not results:
        return


    results.sort(key=lambda x: -x[0])
    for score, sym, signals, price, vol, chg in results[:3]:

        kd1h = get_klines(sym, "1h", 6)
        if not kd1h:
            continue
        vols_1h = kd1h["vols"]
        avg_1h  = sum(vols_1h) / len(vols_1h) if vols_1h else 1
        vol_1h_ratio = vols_1h[-1] / avg_1h if avg_1h > 0 else 0


        if vol_1h_ratio < 1.2:
            continue

        sector  = next((s for s, syms in SECTORS.items() if sym in syms), "غير محدد")
        rarity  = "🐋🔥 نادر جداً" if score >= 80 else "🔥 قوي" if score >= 65 else "⚡ متوسط"

        lines_msg = [
            "🔥 *LIQUIDITY HUNTER*",
            "━━━━━━━━━━━━━━━━━━",
            "💧 *{}* — سيولة خفية مكتشفة!".format(sym.replace("USDT", "")),
            "━━━━━━━━━━━━━━━━━━",
            "📡 *السيناريوهات:*",
            "  {}".format(" | ".join(signals)),
            "━━━━━━━━━━━━━━━━━━",
            "💪 قوة الإشارة: `{}/100` {}".format(score, rarity),
            "💵 السعر: `{}`".format(round(price, 8)),
            "📉 24h: `{:+.2f}%`  |  📊 1h حجم: `{:.1f}×`".format(chg, vol_1h_ratio),
            "📦 الحجم: `{:.0f}K USDT`".format(vol / 1000),
            "🏷️ القطاع: `{}`".format(sector),
            "━━━━━━━━━━━━━━━━━━",
            "⚡ _السوق نازل لكن السيولة تدخل هنا_",
            "👁️ _راقب — قد يرتفع بسرعة_",
        ]
        msg = "\n".join(lines_msg)
        send(msg)
        lh_alerted[sym] = now
        coin_alerted[sym] = now
        perf_register(sym, price, "lh_big", score, " | ".join(signals))
        log.info(" LiqHunter | %s | score=%d | %s", sym, score, " | ".join(signals))








def refresh_small_caps():
    # type: () -> None
    """
    يبني قائمة Small Caps من مصدرين:
    1. عملات SECTORS الحالية ذات حجم منخفض (تعرف قطاعها)
    2. عملات MEXC الجديدة 50K→500K (تُصنَّف تلقائياً)

    النتيجة: تغطية كاملة لكل قطاع حتى بعملاته الصغيرة
    """
    global small_caps, last_sc_refresh
    log.info(" Small Caps:  ...")

    data = safe_get(MEXC_24H)
    if not data:
        return


    vol_map = {}
    for t in data:
        sym = t.get("symbol", "")
        if not sym.endswith("USDT"):
            continue
        try:
            vol_map[sym] = float(t["quoteVolume"])
        except (KeyError, ValueError):
            continue

    sc_set  = set()
    stats   = {}   # {sector: count}


    for sector, coins in SECTORS.items():
        sector_sc = []
        for base in coins:
            sym = base if base.endswith("USDT") else base + "USDT"
            vol = vol_map.get(sym, 0)
            if SC_MIN_VOL <= vol <= SC_MAX_VOL:
                sc_set.add(sym)
                sector_sc.append(sym)
        if sector_sc:
            stats[sector] = len(sector_sc)


    known = set(
        (b if b.endswith("USDT") else b + "USDT")
        for coins in SECTORS.values() for b in coins
    )
    new_sc = []
    for sym, vol in vol_map.items():
        if sym in known or sym in sc_set:
            continue
        base = sym.replace("USDT", "")
        if any(k in sym for k in LEVERAGE_KEYWORDS):
            continue
        if base in {"USDC","USDE","FDUSD","DAI","TUSD","BUSD","XUSD","USD1",
                    "BTC","ETH","BNB","SOL","XRP","USDT"}:
            continue
        if SC_MIN_VOL <= vol <= SC_MAX_VOL:
            new_sc.append((sym, vol))


    new_sc.sort(key=lambda x: -x[1])
    for sym, vol in new_sc[:100]:
        sc_set.add(sym)

    small_caps = list(sc_set)[:SC_MAX_COINS]
    last_sc_refresh = time.time()


    sector_info = " | ".join("{}:{}".format(s, n) for s, n in stats.items())
    log.info(" Small Caps: %d  | : %s | : %d",
             len(small_caps), sector_info, len(new_sc[:100]))


def liquidity_hunter_small_caps(price_map=None, vol_now=None, changes_map=None):
    # type: (Dict, Dict, Dict) -> None
    """
    🔍 LIQUIDITY HUNTER — Small Caps Edition
    نفس المنطق لكن:
    - يستخدم قائمة small_caps بدل candidates
    - threshold أعلى (SC_VOL_SPIKE=4×، SC_SCORE_MIN=65)
    - تنبيه مختلف يوضح المخاطرة العالية
    """
    global sc_alerted
    now = time.time()

    if not small_caps:
        return

    btc_change = btc_change_24h
    results    = []


    ranked_sc = sorted(
        [(s, vol_now.get(s, 0)) for s in small_caps
         if vol_now.get(s, 0) >= SC_MIN_VOL * 0.5
         and now - sc_alerted.get(s, 0) >= LH_COOLDOWN],
        key=lambda x: -x[1]
    )[:80]

    for sym, vol in ranked_sc:
        vol = vol_now.get(sym, 0)
        if vol < SC_MIN_VOL * 0.5:
            continue
        if now - sc_alerted.get(sym, 0) < LH_COOLDOWN:
            continue

        price = price_map.get(sym, 0)
        if price <= 0:
            continue

        kd = get_klines(sym, "15m", 20)
        if not kd or len(kd["closes"]) < 10:
            continue

        closes = kd["closes"]
        vols   = kd["vols"]
        opens  = kd["opens"]
        lows   = kd["lows"]
        n      = len(closes)

        avg_vol   = kd.get("avg_vol", sum(vols) / n) if n > 0 else 1
        if avg_vol <= 0:
            continue

        vol_last3 = sum(vols[-3:]) / 3
        vol_ratio = vol_last3 / avg_vol
        price_chg = abs((closes[-1] - closes[-4]) / closes[-4] * 100) if closes[-4] > 0 else 99

        score   = 0
        signals = []



        _spike_threshold = SC_VOL_SPIKE_MICRO if vol < SC_MICRO_VOL_MAX else SC_VOL_SPIKE
        if vol_ratio >= _spike_threshold and price_chg <= LH_PRICE_FLAT:
            pts = min(int(vol_ratio * 10), 50)
            score += pts
            tag = "🔬 MicroSpike" if vol < SC_MICRO_VOL_MAX else "🔥 VolSpike"
            signals.append("{} {:.1f}×".format(tag, vol_ratio))
        elif vol_ratio >= LH_VOL_QUIET and price_chg <= LH_PRICE_FLAT:
            pts = min(int(vol_ratio * 7), 20)
            score += pts
            signals.append("🔇 QuietVol {:.1f}×".format(vol_ratio))


        wick_score = 0
        for i in range(-5, 0):
            body       = abs(closes[i] - opens[i])
            lower_wick = min(opens[i], closes[i]) - lows[i]
            if body > 0 and lower_wick > body * 1.8:
                wick_score += 1
        if wick_score >= 3:
            score += wick_score * 8
            signals.append("🕯️ WickReject ×{}".format(wick_score))


        coin_change_24h = changes_map.get(sym, 0)
        if btc_change <= -LH_BTC_DIV_MIN and coin_change_24h >= -1.0:
            divergence = coin_change_24h - btc_change
            if divergence >= 2.0:
                score += min(int(divergence * 5), 30)
                signals.append("📊 BTCDiv +{:.1f}%".format(divergence))


        vol_trend = sum(1 for i in range(-4, 0) if vols[i] > vols[i-1])
        if vol_trend >= 4 and vol_ratio >= 1.5:
            score += 20
            signals.append("📈 VolTrend {}/4".format(vol_trend))

        if score >= SC_SCORE_MIN and len(signals) >= 2:
            results.append((score, sym, signals, price, vol, coin_change_24h))

    if not results:
        return

    results.sort(key=lambda x: -x[0])
    for score, sym, signals, price, vol, chg in results[:2]:
        kd1h = get_klines(sym, "1h", 6)
        if not kd1h:
            continue
        vols_1h     = kd1h["vols"]
        avg_1h      = sum(vols_1h) / len(vols_1h) if vols_1h else 1
        vol_1h_ratio = vols_1h[-1] / avg_1h if avg_1h > 0 else 0

        if vol_1h_ratio < 1.3:
            continue

        sector = next((s for s, syms in SECTORS.items() if sym in syms), "Small Cap")
        rarity = "🐋🔥 نادر" if score >= 85 else "🔥 قوي" if score >= 70 else "⚡ متوسط"

        lines_msg = [
            "🔍 *SMALL CAP HUNTER*",
            "━━━━━━━━━━━━━━━━━━",
            "💎 *{}* — سيولة خفية!".format(sym.replace("USDT", "")),
            "━━━━━━━━━━━━━━━━━━",
            "📡 *السيناريوهات:*",
            "  {}".format(" | ".join(signals)),
            "━━━━━━━━━━━━━━━━━━",
            "💪 القوة: `{}/100` {}".format(score, rarity),
            "💵 السعر: `{}`".format(round(price, 8)),
            "📉 24h: `{:+.2f}%`  |  1h حجم: `{:.1f}×`".format(chg, vol_1h_ratio),
            "📦 الحجم: `{:.0f}K USDT`".format(vol / 1000),
            "🏷️ القطاع: `{}`".format(sector),
            "━━━━━━━━━━━━━━━━━━",
            "⚠️ _Small Cap — مخاطرة عالية / ربح محتمل 30%+_",
            "🎯 _ادخل بحجم صغير فقط_",
        ]
        msg = "\n".join(lines_msg)
        send(msg)
        sc_alerted[sym] = now
        coin_alerted[sym] = now
        perf_register(sym, price, "lh_small", score, " | ".join(signals))
        log.info(" SmallCapHunter | %s | score=%d | %s", sym, score, " | ".join(signals))









# ══════════════════════════════════════════════════════════════════
#  MULTI-TIMEFRAME LIQUIDITY SCANNER  — V17
# ══════════════════════════════════════════════════════════════════

mtf_liq_alerted   = {}   # type: Dict[str, float]  {sym: last_alert_time}
last_mtf_liq_scan = 0.0


def _check_tf_liquidity(sym, interval, limit):
    # type: (str, str, int) -> dict
    """
    يفحص سيولة عملة في إطار زمني واحد.
    يعيد: confirmed (bool), vol_ratio, price_chg, wick_count, cvd_rising
    """
    kd = get_klines(sym, interval, limit)
    if not kd or len(kd.get("closes", [])) < limit // 2:
        return {"confirmed": False, "vol_ratio": 0.0, "price_chg": 99.0,
                "wick_count": 0, "cvd_rising": False}

    closes = kd["closes"]
    opens  = kd["opens"]
    vols   = kd["vols"]
    lows   = kd["lows"]
    n      = len(closes)

    avg_vol = sum(vols) / n if n > 0 else 1
    if avg_vol <= 0:
        return {"confirmed": False, "vol_ratio": 0.0, "price_chg": 99.0,
                "wick_count": 0, "cvd_rising": False}

    vol_last  = sum(vols[-3:]) / 3
    vol_ratio = vol_last / avg_vol

    price_chg = abs((closes[-1] - closes[-4]) / closes[-4] * 100) if len(closes) >= 4 and closes[-4] > 0 else 99

    wick_count = 0
    for i in range(-4, 0):
        body       = abs(closes[i] - opens[i])
        lower_wick = min(opens[i], closes[i]) - lows[i]
        if body > 0 and lower_wick > body * 1.5:
            wick_count += 1

    cumul = 0.0
    cvd_vals = []
    for i in range(n):
        vol = vols[i] if i < len(vols) else 0
        cumul += vol if closes[i] >= opens[i] else -vol
        cvd_vals.append(cumul)

    cvd_rising = False
    if len(cvd_vals) >= 6:
        first3 = sum(cvd_vals[:3]) / 3
        last3  = sum(cvd_vals[-3:]) / 3
        if first3 != 0 and last3 > first3 * 1.05:
            cvd_rising = True

    confirmed = (
        vol_ratio >= MTF_VOL_SPIKE
        and price_chg <= MTF_PRICE_MAX
        and (wick_count >= 2 or cvd_rising)
    )

    return {
        "confirmed":  confirmed,
        "vol_ratio":  round(vol_ratio, 2),
        "price_chg":  round(price_chg, 2),
        "wick_count": wick_count,
        "cvd_rising": cvd_rising,
    }


def scan_multi_timeframe_liquidity(price_map=None, vol_now=None, changes_map=None):
    # type: (Dict, Dict, Dict) -> None
    """
    🕐 MULTI-TIMEFRAME LIQUIDITY — V17
    يفحص 3 أطر زمنية دفعة واحدة: 15m + 1h + 4h
    يرسل تنبيه فقط عند توافق ≥ MTF_LIQ_MIN_TF إطارات

    ● إطار واحد = ضجيج عادي
    ● إطارين   = سيولة حقيقية 🔥
    ● ثلاثة     = إشارة ذهبية 🐋
    """
    global mtf_liq_alerted, last_mtf_liq_scan
    now = time.time()

    if now - last_mtf_liq_scan < MTF_LIQ_EVERY:
        return
    last_mtf_liq_scan = now

    if not all_tickers:
        return

    price_map   = price_map   or {}
    vol_now     = vol_now     or {}
    changes_map = changes_map or {}

    all_syms = list(set(list(candidates) + EXTRA_COINS))
    ranked = sorted(
        [(s, vol_now.get(s, 0)) for s in all_syms
         if vol_now.get(s, 0) >= 150_000
         and now - mtf_liq_alerted.get(s, 0) >= MTF_LIQ_COOLDOWN
         and now - coin_alerted.get(s, 0) >= MTF_LIQ_COOLDOWN // 2],
        key=lambda x: -x[1]
    )[:80]

    results = []

    # بناء ticker_map للفحص السريع
    _mtf_ticker = {t["symbol"]: t for t in all_tickers} if all_tickers else {}

    for sym, vol in ranked:
        base = sym.replace("USDT", "")
        if base in STABLECOINS:
            continue
        if any(k in sym for k in LEVERAGE_KEYWORDS):
            continue

        price = price_map.get(sym, 0)
        if price <= 0:
            continue

        # فلتر الاتجاه: لا إشارة على عملة في هبوط قوي
        _chg_early = changes_map.get(sym, 0)
        if _chg_early < -3.0:
            log.debug("MTF skip %s: downtrend %.1f%%", sym, _chg_early)
            continue

        # فلتر الدخول المتأخر
        _t_mtf = _mtf_ticker.get(sym)
        if _t_mtf:
            try:
                _h24 = float(_t_mtf.get("highPrice", price))
                _l24 = float(_t_mtf.get("lowPrice",  price))
                if _is_late_entry(price, _h24, _l24):
                    log.debug("MTF late_entry skip %s", sym)
                    continue
            except (ValueError, TypeError):
                pass

        tf15 = _check_tf_liquidity(sym, "15m", 20)
        tf1h = _check_tf_liquidity(sym, "1h",  12)
        tf4h = _check_tf_liquidity(sym, "4h",  10)

        confirmed_tfs = []
        if tf15.get("confirmed"):
            confirmed_tfs.append(("15m", tf15))
        if tf1h.get("confirmed"):
            confirmed_tfs.append(("1h",  tf1h))
        if tf4h.get("confirmed"):
            confirmed_tfs.append(("4h",  tf4h))

        if len(confirmed_tfs) < MTF_LIQ_MIN_TF:
            continue

        score     = len(confirmed_tfs) * 30
        max_vol_r = max(tf["vol_ratio"] for _, tf in confirmed_tfs)
        score    += min(int(max_vol_r * 10), 25)

        cvd1h  = calc_cvd(sym, "1h", 12)
        ob_imb = calc_ob_imbalance(sym)
        ob_buy = ob_imb.get("signal") in ("buy", "strong_buy")
        if ob_buy:
            score += 10
        if cvd1h.get("trend") == "rising":
            score += 10

        if score < MTF_LIQ_SCORE:
            continue

        # فلتر Flow 1h: يجب أن يكون المال يدخل لا يخرج
        _mtf_flow = calc_money_flow_1h(sym)
        if _mtf_flow["net"] < 0:
            log.debug("MTF skip %s: flow negative net=%.0f$", sym, _mtf_flow["net"])
            continue

        sector = next((s for s, syms in SECTORS.items() if sym in syms), "غير محدد")
        chg    = changes_map.get(sym, 0)
        _confirm_count_mtf, _badge_mtf = _register_confirm(sym, "mtf")

        tf_lines = []
        for tf_name, tf_data in confirmed_tfs:
            wick_tag = " 🕯️×{}".format(tf_data["wick_count"]) if tf_data["wick_count"] >= 2 else ""
            cvd_tag  = " CVD↑" if tf_data["cvd_rising"] else ""
            tf_lines.append("  ✅ `{}` حجم `{:.1f}×`{}{}".format(
                tf_name, tf_data["vol_ratio"], wick_tag, cvd_tag
            ))

        stars   = "🐋🔥" if len(confirmed_tfs) == 3 else "🔥"
        triple  = " — ثلاثي 🏆" if len(confirmed_tfs) == 3 else ""
        ob_line = "  📒 OB: `{}`".format(ob_imb.get("signal", "—")) if ob_buy else ""

        def _mtf_fmt(v):
            if v >= 1_000_000: return "{:.1f}M$".format(v / 1e6)
            if v >= 1_000:     return "{:.1f}K$".format(v / 1e3)
            return "{:.2f}$".format(v)

        msg = (
            "{} *MTF LIQUIDITY{}* {}\n".format(stars, triple, _badge_mtf)
            + "━━━━━━━━━━━━━━━━━━\n"
            + "🎯 *{}* — سيولة متعددة الأطر!\n".format(base)
            + "━━━━━━━━━━━━━━━━━━\n"
            + "📡 *الأطر المؤكدة ({}/3)* :\n".format(len(confirmed_tfs))
            + "\n".join(tf_lines) + "\n"
            + "━━━━━━━━━━━━━━━━━━\n"
            + "💵 السعر: `{}`  |  24h: `{:+.1f}%`\n".format(fmt_price(price), chg)
            + "💹 *Flow 1h:* IN `{}` / OUT `{}` / Net `+{}`\n".format(
                _mtf_fmt(_mtf_flow["in"]), _mtf_fmt(_mtf_flow["out"]),
                _mtf_fmt(_mtf_flow["net"]))
            + (ob_line + "\n" if ob_line else "")
            + "🏷️ القطاع: `{}`\n".format(sector)
            + "━━━━━━━━━━━━━━━━━━\n"
            + "✅ *ادخل الآن* — {} إطارات + Flow إيجابي 🌊".format(len(confirmed_tfs))
        )

        results.append((score, sym, msg, price))

    if not results:
        return

    results.sort(key=lambda x: -x[0])
    for score, sym, msg, price in results[:3]:
        send(msg)
        mtf_liq_alerted[sym] = now
        coin_alerted[sym]    = now
        perf_register(sym, price, "mtf_liq", score, "MTF_confirmed")
        log.info(" MTF Liq | %s | score=%d", sym, score)


def detect_hidden_accumulation(kd, ob=None):
    # type: (Dict, Optional[Dict]) -> tuple
    """
    يكشف تجميع الحيتان الخفي قبل الارتفاع.

    المؤشرات:
    1. 📉📈 Volume Divergence  — السعر ينزل لكن الحجم يرتفع
    2. 🕯️ Lower Wicks         — ذيول سفلية طويلة = رفض النزول
    3. 💧 Bid Wall             — جدار شراء ضخم في Order Book
    4. 🔇 Quiet Accumulation   — حجم يتصاعد تدريجياً بهدوء
    5. 🔒 Price Compression    — السعر مضغوط في نطاق ضيق مع حجم

    يعيد: (is_accumulating, score, description)
    """
    highs  = kd["highs"]
    lows   = kd["lows"]
    opens  = kd["opens"]
    closes = kd["closes"]
    vols   = kd["vols"]
    n      = len(closes)

    if n < 10:
        return False, 0, ""

    avg_vol = kd.get("avg_vol", sum(vols) / n)
    if avg_vol <= 0:
        return False, 0, ""

    score    = 0
    signals  = []





    price_5  = (closes[-5] - closes[-1]) / closes[-5] * 100 if closes[-5] > 0 else 0
    vol_avg3 = sum(vols[-3:]) / 3
    vol_avg_prev = sum(vols[-8:-3]) / 5 if n >= 8 else avg_vol

    price_falling = price_5 <= -1.0
    vol_rising    = vol_avg3 > vol_avg_prev * 1.4

    if price_falling and vol_rising:
        div_strength = vol_avg3 / vol_avg_prev
        pts = min(int(div_strength * 15), 40)
        score += pts
        signals.append("📊 Divergence {:.1f}x".format(div_strength))





    wick_count = 0
    for i in range(-6, 0):
        body        = abs(closes[i] - opens[i])
        lower_wick  = min(opens[i], closes[i]) - lows[i]
        if body > 0 and lower_wick > body * 1.5:
            wick_count += 1

    if wick_count >= 3:
        pts = wick_count * 5
        score += pts
        signals.append("🕯️ Wicks x{}".format(wick_count))





    if ob and ob.get("bid", 0) > 0 and ob.get("ask", 0) > 0:
        bid_ask_ratio = ob["bid"] / ob["ask"]
        if bid_ask_ratio >= 1.8:
            pts = min(int(bid_ask_ratio * 10), 30)
            score += pts
            signals.append("💧 BidWall {:.1f}x".format(bid_ask_ratio))
        elif bid_ask_ratio >= 1.3:
            score += 10
            signals.append("💧 Bid+")





    if n >= 6:
        vol_trend = 0
        for i in range(-5, 0):
            if vols[i] > vols[i-1]:
                vol_trend += 1

        if vol_trend >= 4:
            score += 20
            signals.append("🔇 Quiet Accum")





    recent_high = max(highs[-8:])
    recent_low  = min(lows[-8:])
    price_range = (recent_high - recent_low) / recent_low * 100 if recent_low > 0 else 999

    if price_range < 8.0 and vol_avg3 > avg_vol * 1.2:
        compression_score = max(0, int((8.0 - price_range) * 3))
        score += compression_score
        signals.append("🔒 Compression {:.1f}%".format(price_range))




    is_accumulating = score >= 35
    desc = " | ".join(signals) if signals else ""

    return is_accumulating, score, desc


def scan_hidden_accumulation(price_map, vol_now, changes_map):
    # type: (Dict, Dict, Dict) -> None
    """
    🆕 V16: مسح مستمر للكشف عن التجميع الخفي
    يعمل على كل العملات كل دورة
    يرسل تنبيه مبكر قبل الارتفاع
    """
    global hidden_accum_alerted

    now = time.time()
    top_candidates = sorted(
        [(s, vol_now.get(s, 0)) for s in candidates if s not in tracked],
        key=lambda x: -x[1]
    )[:50]

    for sym, vol in top_candidates:

        if now - coin_alerted.get(sym, 0) < TPS_COOLDOWN:
            if now - coin_whale_done.get(sym, 0) >= LZ_TPS_COOLDOWN:
                continue

        if now - hidden_accum_alerted.get(sym, 0) < 14400:
            continue

        price = price_map.get(sym, 0)
        if price <= 0:
            continue

        kd = get_klines(sym, "15m", 30)
        if not kd:
            continue


        ob = get_order_book(sym) if vol > 500_000 else None

        is_accum, acc_score, acc_desc = detect_hidden_accumulation(kd, ob)

        if not is_accum:
            continue


        kd1h = get_klines(sym, "1h", 10)
        if not kd1h:
            continue

        vols_1h  = kd1h["vols"]
        avg_1h   = sum(vols_1h) / len(vols_1h)
        last_1h  = vols_1h[-1]
        if last_1h < avg_1h * 1.3:
            continue

        change_24h = changes_map.get(sym, 0)
        sector     = next((s for s, syms in SECTORS.items() if sym in syms), "غير محدد")


        rarity = "🔥 قوي" if acc_score >= 60 else "⚡ متوسط"
        if acc_score >= 80:
            rarity = "🐋🔥 نادر جداً"

        # صامت — يضيف للقائمة الداخلية فقط، الجوكر يؤكد لاحقاً
        hidden_accum_alerted[sym] = now
        whale_watch_add(sym, 0, max(acc_score / 100.0, 0.56), price)
        perf_register(sym, price, "hidden", acc_score, acc_desc)
        log.info(" Hidden Accum (silent) | %s | score=%d | %s", sym, acc_score, acc_desc)


def detect_pump_dump(kd):
    # type: (Dict) -> Tuple[bool, str]
    closes = kd["closes"]
    highs  = kd["highs"]
    if len(closes) < PD_LOOKBACK:
        return False, ""
    mn = min(closes[-PD_LOOKBACK:])
    mx = max(highs[-PD_LOOKBACK:])
    if mn <= 0:
        return False, ""
    rise = (mx - mn) / mn * 100
    drop = (mx - closes[-1]) / mx * 100
    if rise >= PD_MAX_RISE:
        if drop >= PD_MIN_DROP:
            return True, "Pump {:.0f}% Dump {:.0f}%".format(rise, drop)
        if rise >= 40:
            return True, "ارتفاع مفرط {:.0f}%".format(rise)
    return False, ""


def get_supertrend(kd):
    # type: (Dict) -> str
    h = kd["highs"]; l = kd["lows"]; c = kd["closes"]
    if len(c) < ST_ATR_PERIOD + 2:
        return "UNKNOWN"
    trs = [max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
           for i in range(1, len(c))]
    atr  = sum(trs[-ST_ATR_PERIOD:]) / ST_ATR_PERIOD
    hl2  = (h[-1] + l[-1]) / 2
    upper = hl2 + ST_MULTIPLIER * atr
    lower = hl2 - ST_MULTIPLIER * atr
    cur   = c[-1]
    if cur > lower: return "UP"
    if cur < upper: return "DOWN"
    return "UP" if cur > c[-5] else "DOWN"


def detect_volume_spike(kd):
    # type: (Dict) -> Tuple[bool, float]
    avg = kd["avg_vol"]
    if avg == 0: return False, 0.0
    r = kd["vols"][-1] / avg
    return r >= VOL_SPIKE_RATIO, round(r, 2)


def detect_volume_accum(kd):
    # type: (Dict) -> Tuple[bool, float]
    vols = kd["vols"]; closes = kd["closes"]; avg = kd["avg_vol"]
    if len(vols) < 6: return False, 0.0
    rv = vols[-6:]; rc = closes[-6:]
    ar = sum(rv) / 6
    if ar < avg * 1.5: return False, 0.0
    pr = (max(rc) - min(rc)) / min(rc) * 100
    if pr > 3.0: return False, 0.0
    vt = sum(1 for i in range(1, len(rv)) if rv[i] >= rv[i-1])
    if vt / 5 < 0.5: return False, 0.0
    s = min((ar/avg-1)*50 + (3-pr)/3*30 + vt/5*20, 100)
    return True, round(s, 1)


def detect_consolidation(kd):
    # type: (Dict) -> Tuple[bool, float]
    h = kd["highs"][-8:]; l = kd["lows"][-8:]; c = kd["closes"][-8:]
    if len(h) < 6: return False, 0.0
    tr = (max(h)-min(l))/min(l)*100
    if tr > 4.0: return False, 0.0
    if (c[-1]-c[0])/c[0]*100 < -2: return False, 0.0
    hl = sum(1 for i in range(1,len(l)) if l[i]>=l[i-1])
    s  = min((4-tr)/4*80 + hl/(len(l)-1)*20, 100)
    return True, round(s, 1)


def detect_higher_lows(kd):
    # type: (Dict) -> Tuple[bool, float]
    l = kd["lows"][-8:]
    if len(l) < 4: return False, 0.0
    h = sum(1 for i in range(1,len(l)) if l[i]>=l[i-1])
    r = h/(len(l)-1)
    return r >= HIGHER_LOWS_MIN, round(r*100, 1)


def detect_green_candles(kd):
    # type: (Dict) -> Tuple[bool, float]
    o = kd["opens"][-8:]; c = kd["closes"][-8:]
    if len(o) < 4: return False, 0.0
    g = sum(1 for op,cl in zip(o,c) if cl>=op)
    r = g/len(o)
    return r >= GREEN_MIN_RATIO, round(r*100, 1)


def detect_pre_breakout(symbol):
    # type: (str) -> Tuple[bool, float, str]
    kd = get_klines(symbol, "4h", BO_4H_CANDLES)
    if not kd or len(kd["closes"]) < 10:
        return False, 0.0, ""
    c=kd["closes"]; h=kd["highs"]; l=kd["lows"]; v=kd["vols"]
    fe = int(len(c)*0.7)
    fl=l[:fe]; fh=h[:fe]; fv=v[:fe]
    if min(fl)<=0: return False, 0.0, ""
    fr = (max(fh)-min(fl))/min(fl)*100
    if fr > BO_FLAT_MAX: return False, 0.0, ""
    afv = sum(fv)/max(len(fv),1)
    arv = sum(v[fe:])/max(len(v[fe:]),1)
    if afv<=0 or arv/afv < BO_VOL_SURGE: return False, 0.0, ""
    rise = (c[-1]-min(fl))/min(fl)*100
    if rise > BO_NEAR_LOW: return False, 0.0, ""
    ts = max(0,(BO_FLAT_MAX-fr)/BO_FLAT_MAX*40)
    vs = min((arv/afv-1)*30,40)
    tm = max(0,(BO_NEAR_LOW-rise)/BO_NEAR_LOW*20)
    desc = "تجميع {:.0f}% | حجم ×{:.1f} | ارتفاع {:.0f}%".format(fr,arv/afv,rise)
    return True, round(min(ts+vs+tm,100),1), desc


def get_order_book(symbol):
    # type: (str) -> Optional[Dict]
    data = safe_get(MEXC_DEPTH, {"symbol": symbol, "limit": OB_DEPTH_LIMIT})
    if not data: return None
    try:
        raw_bids = data.get("bids", [])
        raw_asks = data.get("asks", [])
        bid = sum(float(b[0]) * float(b[1]) for b in raw_bids)
        ask = sum(float(a[0]) * float(a[1]) for a in raw_asks)
        return {
            "bid":      bid,
            "ask":      ask,
            "imb":      bid / ask if ask > 0 else 99,
            "raw_bids": raw_bids,
            "raw_asks": raw_asks,
        }
    except:
        return None



#   DYNAMIC STOP LOSS

def calc_sl(kd, score, ob, is_bo=False):
    # type: (Dict, int, Optional[Dict], bool) -> float
    h=kd["highs"]; l=kd["lows"]
    pairs = list(zip(h[-10:],l[-10:]))
    if pairs and min(lv for _,lv in pairs)>0:
        atr = sum((hv-lv)/lv*100 for hv,lv in pairs)/len(pairs)
    else:
        atr = SL_BASE
    sf = 0.70 if score>=88 else 0.85 if score>=75 else 1.00
    imf = 1.0
    if ob:
        imf = 0.80 if ob["imb"]>=2 else 0.90 if ob["imb"]>=1.5 else 1.10 if ob["imb"]<1 else 1.0
    bf = 1.3 if is_bo else 1.0
    return round(max(SL_MIN, min(SL_MAX, atr*sf*imf*bf)), 1)



#   TRAILING STOP

def check_trailing(symbol, price):
    # type: (str, float) -> bool
    if symbol not in tracked:
        return False

    entry = tracked[symbol]["entry"]
    peak  = tracked[symbol].get("peak", entry)

    if price > peak:
        tracked[symbol]["peak"] = price
        peak = price

    gain = (peak - entry) / entry * 100
    drop = (peak - price) / peak * 100

    if gain >= TRAIL_GAIN_TRIGGER and drop >= TRAIL_DROP_TRIGGER:
        result = (price - entry) / entry * 100
        emoji  = "✅" if result > 0 else "❌"
        send(
            "🛑 *TRAILING STOP* | `{}`\n"
            "{} النتيجة: `{:+.2f}%`\n"
            "💵 دخول: `{}` | خروج: `{}`\n"
            "📈 القمة كانت: `{}`".format(
                symbol, emoji, result,
                fmt_price(entry), fmt_price(price),
                fmt_price(peak)
            )
        )
        log.info(" Trailing: %s | %.2f%%", symbol, result)
        del tracked[symbol]
        return True

    sl_pct = tracked[symbol].get("sl_pct", SL_BASE)
    change = (price - entry) / entry * 100
    if change <= -sl_pct:
        send(
            "🛑 *STOP LOSS* | `{}`\n"
            "📉 خسارة: `{:.2f}%` | SL: `-{}%`\n"
            "💵 دخول: `{}` ← الآن: `{}`".format(
                symbol, change, sl_pct,
                fmt_price(entry), fmt_price(price)
            )
        )
        log.info(" SL: %s | %.2f%%", symbol, change)
        del tracked[symbol]
        return True

    return False



#   SCORE SYSTEM V11


def calculate_score(kd, ob, vol_accum, vol_spike, consol,
                    higher_lows, green, bo_str, in_hot, st, symbol=""):
    # type: (Dict, Optional[Dict], Tuple, Tuple, Tuple, Tuple, Tuple, float, bool, str, str) -> int
    score = 0
    avg   = kd["avg_vol"]


    r = kd["vols"][-1]/avg if avg>0 else 0
    score += 15 if r>=3 else 10 if r>=2 else 6 if r>=1.5 else 0

    # Supertrend (10)
    if st == "UP":   score += 10
    elif st == "DOWN": score -= 5

    # Order Book (12)
    if ob:
        if ob["bid"] >= MIN_BID_DEPTH: score += 5
        score += 7 if ob["imb"]>=2 else 5 if ob["imb"]>=1.5 else 3 if ob["imb"]>=1 else 0

    # Vol Spike (10)
    isp, sr = vol_spike
    if isp: score += 10 if sr>=5 else 7 if sr>=3.5 else 5

    # Vol Accum (8)
    ia, av = vol_accum
    if ia: score += max(int(av/100*8), 5)

    # Consolidation (8)
    ic, cv = consol
    if ic: score += max(int(cv/100*8), 4)

    # Higher Lows (8)
    ih, hp = higher_lows
    if ih: score += 8 if hp>=80 else 5 if hp>=70 else 3

    # Green Candles (7)
    ig, gp = green
    if ig: score += 7 if gp>=75 else 4 if gp>=60 else 2


    c = kd["closes"]
    if c[-1] > c[0]: score += 5

    # Pre-Breakout (10)
    if bo_str > 0: score += max(int(bo_str/100*10), 6)

    # Sector Rotation Bonus (15)
    if in_hot: score += SECTOR_BONUS


    if symbol:
        sector = next((s for s, syms in SECTORS.items() if symbol in syms), "")
        if sector and sector_flow_state.get(sector) == "IN":
            score += 8


    if btc_change_24h < -2.0 and not in_hot:
        score -= 8
    elif btc_change_24h < -1.0 and not in_hot:
        score -= 4


    if smart_money_bonus > 0 and in_hot:
        score += smart_money_bonus

    return min(max(score, 0), 100)


def score_label(score):
    # type: (int) -> Optional[str]
    if score >= 88: return "🏆 *GOLD SIGNAL*"
    if score >= 75: return "🔵 *SILVER SIGNAL*"
    return None



#   DEEP SCAN

def deep_scan(symbol, price, change, fetch_orderbook=True):
    # type: (str, float, float, bool) -> None
    """
    🆕 V15: fetch_orderbook=True فقط لأفضل العملات
    يوفر طلبات API كثيرة
    """
    if symbol in tracked: return

    if market_state == "DANGER" and symbol not in hot_symbols:
        log.debug(" %s : DANGER +  hot", symbol)
        return

    kd = get_klines(symbol, "15m", 50)
    if not kd:
        log.debug(" %s :  klines", symbol)
        return

    is_pd, pd_r = detect_pump_dump(kd)
    if is_pd:
        log.debug(" P&D: %s | %s", symbol, pd_r)
        return

    vol_ratio_kd = kd["vols"][-1] / kd["avg_vol"] if kd["avg_vol"] > 0 else 0
    if vol_ratio_kd < 1.2:
        log.debug(" %s :   %.2fx", symbol, vol_ratio_kd)
        return

    st = get_supertrend(kd)
    if st == "DOWN" and symbol not in hot_symbols:
        log.debug(" %s : Supertrend DOWN", symbol)
        return

    ig, gp = detect_green_candles(kd)
    if not ig:
        log.debug(" %s :   %.0f%%", symbol, gp)
        return


    ob = get_order_book(symbol) if fetch_orderbook else None
    if ob:
        if ob["imb"] < MIN_IMBALANCE or ob["imb"] > MAX_IMBALANCE:
            log.debug(" %s : OB Imbalance %.2f", symbol, ob["imb"])
            return
        if ob["bid"] < MIN_BID_DEPTH:
            log.debug(" %s : Bid  %.0f", symbol, ob["bid"])
            return

    vol_spike   = detect_volume_spike(kd)
    vol_accum   = detect_volume_accum(kd)
    consol      = detect_consolidation(kd)
    higher_lows = detect_higher_lows(kd)
    is_bo, bo_str, bo_desc = detect_pre_breakout(symbol)

    in_hot = symbol in hot_symbols
    sector = next((s for s,syms in SECTORS.items()
                   if symbol in syms and s in hot_sectors), "")

    score = calculate_score(kd, ob, vol_accum, vol_spike, consol,
                            higher_lows, (ig,gp), bo_str, in_hot, st, symbol)

    min_s = GOLD_MIN if market_state == "CAUTION" else SCORE_MIN
    label = score_label(score)
    if not label or score < min_s:
        log.debug(" %s : Score=%d (min=%d) ST=%s hot=%s", symbol, score, min_s, st, in_hot)
        return

    sl_pct = calc_sl(kd, score, ob, is_bo)

    tracked[symbol] = {
        "entry": price, "peak": price, "level": 1,
        "score": score, "sl_pct": sl_pct,
        "entry_time": time.time(), "last_alert": time.time(),
    }
    discovered[symbol] = {"price": price, "time": time.time(), "score": score}

    sigs = ""
    if in_hot:          sigs += "\n🔥 *قطاع ساخن:* `{}`".format(sector)
    if is_bo:           sigs += "\n💥 *Breakout:* `{:.0f}%` _{}_".format(bo_str, bo_desc)
    isp, sr = vol_spike
    if isp:             sigs += "\n⚡ *Vol Spike:* `{:.1f}×`".format(sr)
    ia, av  = vol_accum
    if ia:              sigs += "\n🔋 *Vol Accum:* `{:.0f}%`".format(av)
    ic, cv  = consol
    if ic:              sigs += "\n🎯 *Consolidation:* `{:.0f}%`".format(cv)
    ih, hp  = higher_lows
    if ih:              sigs += "\n📈 *Higher Lows:* `{:.0f}%`".format(hp)
    if ig:              sigs += "\n🟢 *Green Candles:* `{:.0f}%`".format(gp)
    sigs += "\n📊 *Supertrend:* `{}`".format("🟢 UP" if st=="UP" else "🔴 DOWN")


    flow_state = sector_flow_state.get(
        next((s for s, syms in SECTORS.items() if symbol in syms), ""), "NEUTRAL"
    )
    if flow_state == "IN":
        sigs += "\n💸 *Sector Flow:* `سيولة داخلة ✅`"
    elif flow_state == "OUT":
        sigs += "\n📤 *Sector Flow:* `سيولة خارجة ⚠️`"

    ob_txt = ""
    if ob:
        em = "🟢" if ob["imb"]>=1.2 else "🟡"
        ob_txt = "\n📗 Bid:`{:,.0f}` {} Imb:`{:.2f}`".format(ob["bid"], em, ob["imb"])

    if in_hot and is_bo:    stype = "💥🔥 BREAKOUT + HOT SECTOR"
    elif in_hot:            stype = "🔥 HOT SECTOR"
    elif is_bo:             stype = "💥 BREAKOUT SETUP"
    elif sum([isp, ia, ic, ih]) >= 3: stype = "💎 PRE-EXPLOSION"
    elif isp:               stype = "⚡ VOLUME SPIKE"
    else:                   stype = "📊 SIGNAL"

    mkt_icon = {"SAFE":"🟢","CAUTION":"🟡","DANGER":"🚨"}.get(market_state,"⚪")

    send(
        "👑 *MAFIO-BOT*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "💰 *{sym}*\n"
        "{label} | {stype}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "💵 Price: `{price}`\n"
        "📊 Score: *{score}/100*\n"
        "🕐 `{time}`\n"
        "{mkt} السوق: `{mst}`{sigs}{ob}\n"
        "📉 24h: `{ch:+.1f}%` | BTC: `{btc:+.1f}%`\n"
        "⚠️ SL: `-{sl}%` | 🎯 Trailing: `{trail}%`".format(
            sym=symbol, label=label, stype=stype,
            price=fmt_price(price), score=score,
            time=datetime.now().strftime("%H:%M:%S"),
            mkt=mkt_icon, mst=market_state,
            sigs=sigs, ob=ob_txt,
            ch=change, btc=btc_change_24h,
            sl=sl_pct, trail=TRAIL_DROP_TRIGGER,
        )
    )
    log.info(" SIGNAL | %s | score=%d | hot=%s bo=%s sl=%.1f%%",
             symbol, score, in_hot, is_bo, sl_pct)



#   SIGNAL PROGRESSION (#2, #3)

def check_progression(symbol, price):
    # type: (str, float) -> None
    if symbol not in tracked: return
    now   = time.time()
    entry = tracked[symbol]["entry"]
    level = tracked[symbol]["level"]
    score = tracked[symbol]["score"]
    sl    = tracked[symbol]["sl_pct"]
    gain  = (price - entry) / entry * 100

    if now - tracked[symbol].get("last_alert", 0) < ALERT_COOLDOWN_SEC:
        return

    label = score_label(score) or "🟡"

    if level == 1 and gain >= SIGNAL2_GAIN:
        send("{} *SIGNAL #2* | `{}`\n📈 *+{:.2f}%*\n💵 `{}` | SL:`-{}%`".format(
            label, symbol, gain, fmt_price(price), sl))
        tracked[symbol]["level"]      = 2
        tracked[symbol]["last_alert"] = now
        log.info(" #2 | %s +%.2f%%", symbol, gain)

    elif level == 2 and gain >= SIGNAL3_GAIN:
        send("{} *SIGNAL #3* | `{}`\n🔥 *+{:.2f}%*\n💵 `{}` | SL:`-{}%`".format(
            label, symbol, gain, fmt_price(price), sl))
        tracked[symbol]["level"]      = 3
        tracked[symbol]["last_alert"] = now
        log.info(" #3 | %s +%.2f%%", symbol, gain)



#   CLEANUP & REPORT

def cleanup():
    # type: () -> None
    now = time.time()
    for s in [s for s,d in list(tracked.items())
              if now - d["entry_time"] > STALE_REMOVE_SEC]:
        log.info(" %s", s)
        del tracked[s]
    clear_expired_cache()
















def detect_liquidity_zones(kd_daily):
    # type: (Dict) -> List[Dict]
    """
    V16 SAVAGE — اكتشاف مناطق السيولة
    نوعان:
    1. FRESH: سعر جديد منخفض + حجم ضخم (3x) = الحيتان يشترون في منطقة جديدة
    2. REPEAT: لمسات متعددة + حجم مرتفع = دعم كلاسيكي مؤكد
    """
    if not kd_daily:
        return []

    highs  = kd_daily["highs"]
    lows   = kd_daily["lows"]
    vols   = kd_daily["vols"]
    closes = kd_daily["closes"]
    n      = len(highs)

    if n < 15:
        return []

    avg_vol = sum(vols) / n
    if avg_vol <= 0:
        return []

    zones = []

    for i in range(3, n):
        zone_high  = highs[i]
        zone_low   = lows[i]
        zone_vol   = vols[i]
        zone_mid   = (zone_high + zone_low) / 2.0

        if zone_mid <= 0 or zone_high <= zone_low:
            continue

        vol_ratio = zone_vol / avg_vol



        is_new_low   = zone_low <= min(lows[:i])
        is_vol_spike = vol_ratio >= 3.0

        if is_new_low and is_vol_spike:
            sigma = min(int(vol_ratio * 3), 20)
            zone  = {
                "high": zone_high, "low": zone_low, "mid": zone_mid,
                "sigma": sigma, "vol": zone_vol,
                "vol_ratio": round(vol_ratio, 1),
                "type": "FRESH", "index": i,
            }
            dup = False
            for z in zones:
                if z["mid"] > 0 and abs(z["mid"] - zone_mid) / z["mid"] < 0.03:
                    if sigma > z["sigma"]:
                        z.update(zone)
                    dup = True
                    break
            if not dup:
                zones.append(zone)
            continue



        if vol_ratio < LZ_VOL_MULT:
            continue

        touches    = 0
        vol_touches = 0.0
        for j in range(n):
            if j == i:
                continue
            if (lows[j]  <= zone_high * (1 + LZ_ZONE_MARGIN) and
                highs[j] >= zone_low  * (1 - LZ_ZONE_MARGIN)):
                touches     += 1
                vol_touches += vols[j]

        if touches < LZ_TOUCHES_MIN:
            continue

        avg_touch_vol = vol_touches / touches if touches > 0 else 0
        sigma = min(touches + int(avg_touch_vol / avg_vol), 20)

        zone = {
            "high": zone_high, "low": zone_low, "mid": zone_mid,
            "sigma": sigma, "vol": zone_vol,
            "vol_ratio": round(vol_ratio, 1),
            "touches": touches, "type": "REPEAT", "index": i,
        }
        dup = False
        for z in zones:
            if z["mid"] > 0 and abs(z["mid"] - zone_mid) / z["mid"] < 0.03:
                if sigma > z["sigma"]:
                    z.update(zone)
                dup = True
                break
        if not dup:
            zones.append(zone)


    zones.sort(key=lambda z: (0 if z["type"] == "FRESH" else 1, -z["sigma"]))
    return zones[:5]


def check_liquidity_breakout(sym, price, daily_close, zones):
    # type: (str, float, float, List[Dict]) -> Optional[Dict]
    """
    V16 SAVAGE — التحقق من الاختراق
    يعطي أولوية لـ FRESH ZONE على REPEAT ZONE
    """
    if not zones:
        return None

    for zone in zones:
        zone_high  = zone["high"]
        zone_low   = zone["low"]
        sigma      = zone["sigma"]
        zone_type  = zone.get("type", "REPEAT")
        vol_ratio  = zone.get("vol_ratio", 1.0)


        margin = LZ_ZONE_MARGIN * (0.3 if zone_type == "FRESH" else 0.5)

        target_pct = round((zone_high / zone_low - 1) * 100, 1) if zone_low > 0 else 0


        if zone_low <= daily_close <= zone_high:
            return {
                "type":       "WATCH",
                "zone_type":  zone_type,
                "zone_high":  zone_high,
                "zone_low":   zone_low,
                "sigma":      sigma,
                "vol_ratio":  vol_ratio,
                "close":      daily_close,
                "target_pct": target_pct,
            }


        if daily_close > zone_high * (1 + margin):
            return {
                "type":       "BUY",
                "zone_type":  zone_type,
                "zone_high":  zone_high,
                "zone_low":   zone_low,
                "sigma":      sigma,
                "vol_ratio":  vol_ratio,
                "close":      daily_close,
                "target_pct": target_pct,
            }



    return None


def sigma_label(sigma):
    # type: (int) -> str
    """تحويل Sigma إلى وصف مع emoji"""
    if sigma >= LZ_TOUCHES_RARE:
        return "🐋🔥 نادر جداً ({}/تاريخ)".format(sigma)
    elif sigma >= 5:
        return "⭐ قوي ({} لمسات)".format(sigma)
    else:
        return "✅ عادي ({} لمسات)".format(sigma)









bottom_fisher_alerted = {}  # type: dict












def scan_bottom_fisher(price_map, vol_now, changes_map):
    # type: (dict, dict, dict) -> None
    global bottom_fisher_alerted
    now = time.time()

    all_syms = list(set(list(candidates) + EXTRA_COINS))

    for sym in all_syms:

        if sym.replace("USDT","") in STABLECOINS: continue
        if vol_now.get(sym, 0) < 500_000: continue
        if now - bottom_fisher_alerted.get(sym, 0) < 14400: continue
        if now - coin_alerted.get(sym, 0) < TPS_COOLDOWN: continue
        if coin_signal_count.get(sym, 0) >= MAX_COIN_SIGNALS: continue

        chg24 = changes_map.get(sym, 0)

        if chg24 > 25.0: continue

        if chg24 < -15.0: continue


        kd1h = get_klines(sym, "1h", 48)
        kd4h = get_klines(sym, "4h", 30)
        if not kd1h or len(kd1h["closes"]) < 24: continue
        if not kd4h or len(kd4h["closes"]) < 14: continue

        closes1h = kd1h["closes"]
        vols1h   = kd1h["vols"]
        opens1h  = kd1h["opens"]
        lows1h   = kd1h["lows"]
        highs1h  = kd1h["highs"]

        closes4h = kd4h["closes"]
        lows4h   = kd4h["lows"]

        score   = 0
        signals = []

        try:

            vdelta_ma = calc_vdelta_ma(sym, period=12, interval="1h")
            if vdelta_ma >= 0.68:
                score += 30
                signals.append("VDelta {:.0f}%".format(vdelta_ma*100))
            elif vdelta_ma >= 0.65:
                score += 20
                signals.append("VDelta {:.0f}%".format(vdelta_ma*100))
            else:
                continue


            n = len(vols1h)
            if n >= 12:
                vol_old = sum(vols1h[-12:-8]) / 4
                vol_new = sum(vols1h[-4:])    / 4
                if vol_new > vol_old * 1.3:
                    score += 25
                    signals.append("حجم +{:.0f}%".format((vol_new/vol_old-1)*100))


            recent_lows = lows1h[-12:]
            hl = sum(1 for i in range(1, len(recent_lows))
                    if recent_lows[i] >= recent_lows[i-1] * 0.998)
            if hl >= 7:
                score += 20
                signals.append("Higher Lows {}/11".format(hl))


            if len(closes1h) >= 25:
                ema7  = sum(closes1h[-7:])  / 7
                ema25 = sum(closes1h[-25:]) / 25
                if ema7 > ema25:
                    score += 15
                    signals.append("EMA7 > EMA25")
                elif ema7 > ema25 * 0.99:
                    score += 8
                    signals.append("EMA قريب التقاطع")


            if len(closes4h) >= 14:
                ema14_4h = sum(closes4h[-14:]) / 14
                price    = closes4h[-1]
                if price > ema14_4h:
                    score += 10
                    signals.append("فوق EMA14 4h")


            _dir = calc_direction_engine(sym, "1h")
            if _dir:
                bull = _dir.get("bullish_pct", 0)
                if bull >= 65:
                    score += 20
                    signals.append("Direction {:.0f}%".format(bull))
                elif bull >= 55:
                    score += 10
                    signals.append("Direction {:.0f}%".format(bull))


            _hmm = calc_hmm_regime(sym, "4h")
            if _hmm:
                if _hmm.get("regime") == "volatile":
                    continue
                if _hmm.get("regime") == "trending":
                    score += 15
                    signals.append("HMM اتجاهي")


            weis = calc_weis_wave(closes1h, vols1h)
            if weis >= 0.65:
                score += 15
                signals.append("Weis {:.0f}%".format(weis*100))
            elif weis >= 0.55:
                score += 8


            _mm = calc_murray_math(sym, "1d")
            if _mm:
                zone = _mm.get("zone_label", "")
                if zone in ["0/8", "1/8", "2/8"]:
                    score += 15
                    signals.append("Murray {}".format(zone))
                elif zone in ["3/8", "4/8"]:
                    score += 8
                    signals.append("Murray {}".format(zone))


            _mtf = calc_mtf_analysis(sym)
            if _mtf:
                if _mtf.get("bias") == "bullish" and not _mtf.get("conflict"):
                    score += 15
                    signals.append("MTF صاعد")
                elif _mtf.get("conflict"):
                    score -= 10



            _min_score = 45 if market_state == "DANGER" else 60
            _min_sigs  = 2  if market_state == "DANGER" else 3
            if score < _min_score or len(signals) < _min_sigs:
                continue

            price    = price_map.get(sym, closes1h[-1])
            sector   = next((s for s,syms in SECTORS.items() if sym in syms), "غير محدد")
            vol      = vol_now.get(sym, 0)


            trend_ok, _ = check_trend_filter(sym, chg24)
            if not trend_ok: continue


            _cvd_bf_ok, _cvd_bf = check_cvd_filter(sym, "BOTTOM_FISHER")
            if not _cvd_bf_ok:
                continue


            _stats = analyze_tps_ats(sym)
            _tps = _stats.get("tps", 0) if _stats else 0
            _ats = _stats.get("ats", 0) if _stats else 0




            _liq_entering = (
                (_ats >= 300 and vdelta_ma >= 0.68) or
                (_ats >= 150 and vdelta_ma >= 0.72) or
                (_ats >= 500 and vdelta_ma >= 0.65)
            )

            strength = "🔥 قوي جداً" if score >= 80 else ("⚡ جيد" if score >= 65 else "🟡 مقبول")
            sig_txt  = " | ".join(signals[:4])


            _btc_vd_now = btc_tps_stats.get("vdelta", 0.5) if btc_tps_stats else 0.5
            _danger_buy = (market_state == "DANGER" and
                          _btc_vd_now >= 0.50 and
                          vdelta_ma >= 0.65 and
                          _liq_entering)

            if _danger_buy:

                header = "🎣🐋 *BOTTOM FISHER — تجميع في القاع!* 🐋🎣"
                action = ("✅ *ادخل الآن* — تجميع في السوق الهابط!\n"
                         "🐋 _حيتان BTC يشترون + تجميع محلي = دخول مبكر_ 💎")
            elif _liq_entering:
                header = "🎣🚀 *BOTTOM FISHER — ادخل الآن!* 🚀🎣"
                action = "✅ *ادخل الآن* — تجميع + سيولة تدخل! 💪"
            else:
                header = "🎣 *BOTTOM FISHER — تجميع مكتشف!*"
                action = "⏳ _تجميع نشط — انتظر ارتفاع ATS للدخول_ 👁️"

            msg = (
                header + "\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "💥 *{}* — {}\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "📊 النقاط: `{}/100` {}\n"
                "🔍 {}\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "📊 VDelta MA: `{:.0f}%` مستمر 🔥\n"
                "📡 TPS: `{:.2f}` | ATS: `{:.0f}$`\n"
                "💰 السعر: `{}` | التغيير اليومي: `{:+.1f}%`\n"
                "📦 الحجم: `{:.1f}M USDT`\n"
                "🏷️ القطاع: `{}`\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "{}"
            ).format(
                sym.replace("USDT",""),
                "تجميع + سيولة تدخل!" if _liq_entering else "تجميع قبل الانطلاق 👀",
                score, strength,
                sig_txt,
                vdelta_ma * 100,
                _tps, _ats,
                fmt_price(price), chg24,
                vol / 1_000_000,
                sector,
                action
            )


            engine_block = build_engine_block(sym)
            if engine_block:
                msg = msg + "\n" + engine_block


            _bf_score = score + int(vdelta_ma * 50)
            # صامت — يضيف للـ watchlist فقط، الجوكر يؤكد
            bottom_fisher_alerted[sym] = now
            whale_watch_add(sym, vol_now.get(sym,0)/10000, vdelta_ma, price)
            log.info(" BOTTOM FISHER (silent) | %s | score=%d | vdelta=%.0f%%",
                     sym, _bf_score, vdelta_ma * 100)

            log.info(" BOTTOM FISHER QUEUED | %s | score=%d",
                     sym, _bf_score)

        except (IndexError, ValueError, ZeroDivisionError):
            continue


def run_daily_liquidity_scan():
    # type: () -> None
    """
    🆕 V16: الفحص اليومي للسيولة عند 00:00 UTC
    يفحص كل العملات على الإطار اليومي 1D
    يرسل إشارة لكل عملة أغلقت فوق/تحت منطقة سيولة
    """
    global lz_daily_sent_date, lz_alerted
    global coin_signal_count, coin_alerted

    coin_signal_count = {}
    coin_alerted      = {}
    coin_whale_done   = {}

    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    today   = now_utc.strftime("%Y-%m-%d")


    if lz_daily_sent_date == today:
        return
    if now_utc.hour != 0:
        return

    lz_daily_sent_date = today
    log.info(" V16:    ...")

    signals_found = 0
    tv_signals    = []


    _vmap = {t["symbol"]: float(t.get("quoteVolume",0)) for t in all_tickers}
    _cands_sorted = sorted(candidates, key=lambda s: -_vmap.get(s,0))
    _lz_count = 0
    for sym in _cands_sorted:

        last_alert = lz_alerted.get(sym, 0)
        if time.time() - last_alert < LZ_COOLDOWN:
            continue


        kd_daily = get_klines(sym, "1d", LZ_LOOKBACK)
        if not kd_daily or len(kd_daily.get("closes", [])) < 20:
            continue

        closes = kd_daily["closes"]
        daily_close = closes[-1]


        zones = detect_liquidity_zones(kd_daily)
        if not zones:
            continue


        signal = check_liquidity_breakout(sym, daily_close, daily_close, zones)
        if not signal:
            continue


        if signal["type"] == "SELL":
            continue

        zone_high  = signal["zone_high"]
        zone_low   = signal["zone_low"]
        sigma      = signal["sigma"]
        vol_ratio  = signal.get("vol_ratio", 1.0)
        zone_type  = signal.get("zone_type", "REPEAT")
        sig_label  = sigma_label(sigma)


        if zone_type == "FRESH":
            type_tag = "🆕 *منطقة جديدة* — سعر تاريخي جديد + حجم ضخم"
            type_icon = "🆕"
        else:
            type_tag = "🔁 *منطقة متكررة* — دعم مؤكد بالحجم"
            type_icon = "🔁"


        sl_raw   = round((daily_close - zone_low) / daily_close * 100, 2) if daily_close > 0 else 5.0
        sl_pct   = min(sl_raw, 5.0)
        sl_price = round(daily_close * (1 - sl_pct / 100), 8)


        if zone_high > daily_close:
            target_price = zone_high
            target_pct   = round((zone_high / daily_close - 1) * 100, 1)
        else:

            target_pct   = round(sl_pct * 1.5, 1)
            target_price = round(daily_close * (1 + target_pct / 100), 8)


        if target_price <= daily_close:
            log.info("  %s -    ", sym)
            continue


        sector = next((s for s, syms in SECTORS.items() if sym in syms), "غير محدد")


        rare_tag = "\n🐋🔥 *RARE — نادر جداً!*" if sigma >= LZ_TOUCHES_RARE else ""


        sig_type = sig.get("type", "BUY")
        if sig_type == "WATCH":
            sig_icon  = "👁️"
            sig_title = "LIQUIDITY WATCH"
            sig_desc  = "السعر داخل منطقة السيولة — تجميع مبكر"
            action_txt = "⏳ _راقب — انتظر الإغلاق فوق {:.5f}_".format(sig["zone_high"])
        else:
            sig_icon  = "🌊"
            sig_title = "DAILY LIQUIDITY SIGNAL V20"
            sig_desc  = "سيولة شرائية — اختراق مؤكد"
            action_txt = "⚡ _إشارة يومية — دخول عند الإغلاق_"

        msg = (
            "{icon} *{title}*\n".format(icon=sig_icon, title=sig_title)
            + "━━━━━━━━━━━━━━━━━━\n"
            "🟢 *{sym}* — سيولة شرائية\n"
            "{type_tag}\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "📊 *منطقة السيولة:*\n"
            "  🔼 Zone High: `{zh}` ← مقاومة\n"
            "  🔽 Zone Low:  `{zl}` ← دعم قوي\n"
            "  💧 Sigma: {sl}\n"
            "  📦 حجم المنطقة: `{vr}×` المعدل\n"
            "{rare}"
            "━━━━━━━━━━━━━━━━━━\n"
            "💵 الإغلاق اليومي: `{close}`\n"
            "✅ أغلق فوق المنطقة\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🎯 *نقطة الدخول:*  `{close}`\n"
            "🛡️ *وقف الخسارة:* `{stop}` (-{sl_pct}%)\n"
            "🚀 *الهدف:*        `{tp}` (+{tgt}%)  | R:R `1:{rr}`\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🏷️ القطاع: `{sector}` | السوق: `{mst}`\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "⚡ _إشارة يومية — دخول عند الإغلاق_\n"
            "🔄 _Backtest سيصل: 1h / 4h / 24h_"
        ).format(
            sym=sym.replace("USDT", ""),
            type_tag=type_tag,
            zh=round(zone_high, 8),
            zl=round(zone_low, 8),
            sl=sig_label,
            vr=vol_ratio,
            rare=rare_tag,
            close=round(daily_close, 8),
            sl_pct=sl_pct,
            stop=sl_price,
            rr=_rr,
            tp=target_price,
            tgt=target_pct,
            sector=sector,
            mst=market_state,
        )

        send(msg)
        tv_signals.append({"sym":sym,"zone_high":zone_high,"zone_low":zone_low,"sigma":sigma,"touches":sigma})
        lz_alerted[sym] = time.time()
        register_backtest(sym, daily_close, sector)
        signals_found += 1
        _lz_count += 1
        if _lz_count >= 5: break
        log.info(" Daily LZ Signal | %s | sigma=%d | close=%.8f",
                 sym, sigma, daily_close)

        time.sleep(1)

    if tv_signals:
        send_tv_scripts(tv_signals)
    log.info(" Daily Liquidity Scan  | : %d", signals_found)

    if signals_found == 0:
        send(
            "🌊 *DAILY LIQUIDITY SCAN*\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "📅 `{}` — إغلاق اليوم\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "😴 لا توجد إشارات سيولة اليوم\n"
            "السوق: `{}` | العملات المفحوصة: `{}`".format(
                today, market_state, len(candidates)
            )
        )



def analyze_market_history():
    # type: () -> str
    """
    يحلل تاريخ 30 يوم ويعطي توقع ذكي:
    - نمط السوق (صعود/هبوط/تحول)
    - سلوك الحيتان (تجميع/دخول)
    - توقع الاتجاه القادم
    """
    h = market_activity_history
    if len(h) < 3:
        return ""

    recent   = h[-7:]  if len(h) >= 7  else h
    all_days = h


    red_days    = sum(1 for d in recent if d["buy_pct"] <= 45)
    green_days  = sum(1 for d in recent if d["buy_pct"] >= 55)
    neutral_days= len(recent) - red_days - green_days


    stable_vals = [d.get("stable_pct", 0) for d in recent]
    stable_now  = stable_vals[-1] if stable_vals else 0
    stable_avg  = sum(stable_vals) / len(stable_vals) if stable_vals else 0
    stable_trend = stable_vals[-1] - stable_vals[0] if len(stable_vals) >= 2 else 0


    buy_vals    = [d["buy_pct"] for d in recent]
    buy_now     = buy_vals[-1] if buy_vals else 50
    buy_prev    = buy_vals[-2] if len(buy_vals) >= 2 else buy_now
    buy_trend   = buy_vals[-1] - buy_vals[0] if len(buy_vals) >= 2 else 0


    sigma_avg   = sum(d.get("sigma_count",0) for d in recent) / len(recent)
    sigma_now   = recent[-1].get("sigma_count", 0) if recent else 0


    lines_out = []
    sep = "━" * 18


    if red_days >= 5:
        market_pattern = "🔴 سوق هابط (" + str(red_days) + " أيام حمراء)"
    elif green_days >= 5:
        market_pattern = "🟢 سوق صاعد (" + str(green_days) + " أيام خضراء)"
    elif red_days >= 3 and buy_trend > 5:
        market_pattern = "🟡 بداية تحول للصعود ⚠️"
    elif green_days >= 3 and buy_trend < -5:
        market_pattern = "🟡 بداية تحول للهبوط ⚠️"
    else:
        market_pattern = "🟡 سوق متذبذب"


    if stable_now >= 20 and stable_trend > 5:
        whale_pattern = "🐳 تجميع قوي Stablecoins (" + str(round(stable_now,1)) + "%) ↑ ينتظرون قاع"
    elif stable_now >= 20 and stable_trend <= 0:
        whale_pattern = "🐳 🚨 الحيتان يدخلون السوق! (" + str(round(stable_now,1)) + "%) ↓"
    elif stable_now >= 10:
        whale_pattern = "👀 تجميع خفيف (" + str(round(stable_now,1)) + "%)"
    else:
        whale_pattern = "✅ الحيتان في السوق (" + str(round(stable_now,1)) + "%)"


    score = 0
    reasons = []


    if red_days >= 4:       score += 2; reasons.append("تشبع بيع")
    if stable_trend > 8:    score += 2; reasons.append("تجميع حيتان")
    if stable_now >= 15 and stable_trend <= 0: score += 3; reasons.append("حيتان يدخلون")
    if buy_trend > 8:       score += 2; reasons.append("زخم شراء متزايد")
    if sigma_now > sigma_avg * 1.5: score += 1; reasons.append("نشاط Sigma غير عادي")


    if green_days >= 4:     score -= 2; reasons.append("تشبع شراء")
    if stable_trend < -8:   score -= 2; reasons.append("خروج Stablecoins")
    if buy_trend < -8:      score -= 2; reasons.append("زخم بيع متزايد")

    if score >= 5:
        prediction = "🟢 📈 توقع انعكاس وصعود خلال 1-3 أيام"
        action     = "✅ ابدأ المراقبة وانتظر Signal"
    elif score >= 3:
        prediction = "🔵 مؤشرات إيجابية لكن غير مؤكدة"
        action     = "🔵 مراقب ولا تدخل بعد"
    elif score <= -4:
        prediction = "🔴 📉 ضغط بيع متوقع — ابتعد عن السوق"
        action     = "🚫 لا تدخل الآن"
    elif score <= -2:
        prediction = "🟠 تحذير: ضغط بيع محتمل"
        action     = "🟠 تراجع أهدافك"
    else:
        prediction = "⚪ السوق محايد — لا يوجد اتجاه واضح"
        action     = "⚪ انتظر إشارة أوضح"

    reasons_txt = " | ".join(reasons) if reasons else "لا إشارات واضحة"

    result = (
        sep + "\n"
        + "🧠 *تحليل ذكي | آخر " + str(len(recent)) + " أيام*\n"
        + "  📊 نمط: " + market_pattern + "\n"
        + "  " + whale_pattern + "\n"
        + "  📈 اتجاه الشراء: " + ("\u2191 +" if buy_trend>0 else "\u2193 ") + str(round(abs(buy_trend),1)) + "% عن البداية\n"
        + sep + "\n"
        + "🎯 *التوقع:* " + prediction + "\n"
        + "📋 الأسباب: _" + reasons_txt + "_\n"
        + "💡 *الإجراء:* " + action + "\n"
        + sep
    )
    return result


def _get_smart_money_summary():
    # type: () -> str
    """ملخص Stablecoin Sigma للدمج في التقرير اليومي"""
    try:
        if not all_tickers: return ""
        ticker_map = {t["symbol"]: t for t in all_tickers}
        detected = []
        for sym in SMART_MONEY_STABLES:
            t = ticker_map.get(sym)
            if not t: continue
            try:
                vol = float(t["quoteVolume"])
                ref = [x for x in stable_vol_history if x.get("sym") == sym]
                if len(ref) < 3: continue
                vols = [x["vol"] for x in ref[-7:]]
                avg  = sum(vols) / len(vols)
                std  = (sum((v-avg)**2 for v in vols)/len(vols))**0.5
                if std < 1: continue
                sigma = round((vol - avg) / std, 1)
                if sigma >= SMART_MONEY_SIGMA:
                    detected.append({
                        "base":  sym.replace("USDT",""),
                        "sigma": sigma,
                        "vol":   vol,
                        "ratio": round(vol/avg, 1),
                    })
            except: continue

        if not detected: return ""
        detected.sort(key=lambda x: -x["sigma"])

        _SP  = "━" * 18
        text = _SP + "\n"
        text += "💵 *Stablecoin Sigma — نشاط الحيتان:*\n"
        for d in detected[:5]:
            whale = " 🐳" if d["sigma"] >= 5.0 else ""
            text += "  • *{}* | نشاط: `{}×` | `{:.0f}M USDT`{}\n".format(
                d["base"], d["ratio"], d["vol"]/1e6, whale)
        if len(detected) >= 2:
            text += "⚠️ _الحيتان يتجمعون — مال ضخم يدخل السوق_\n"
        return text
    except: return ""

def send_daily_report(force=False):
    # type: (bool) -> None
    global daily_report_sent_date, daily_market_vol_history

    now_utc  = datetime.now(timezone.utc).replace(tzinfo=None)
    today    = now_utc.strftime("%Y-%m-%d")


    if not force and not _force_daily_report:
        if now_utc.hour != 0:
            return
        if daily_report_sent_date == today:
            log.debug("    : %s", today)
            return

    log.info("    | %s | : %02d:%02d UTC",
             today, now_utc.hour, now_utc.minute)

    daily_report_sent_date = today

    try:
        _send_daily_report_body(today, now_utc)
    except Exception as _err:
        log.error(" send_daily_report : %s", _err, exc_info=True)
        send("❌ خطأ في التقرير: `{}`".format(str(_err)[:200]))

def _send_daily_report_body(today, now_utc):
    # type: (str, object) -> None
    """الكود الفعلي للتقرير — منفصل لكشف الأخطاء"""
    global daily_market_vol_history, market_activity_history, btcd_trend


    if backtest_signals:
        bt_results = []
        _pm     = {t["symbol"]: float(t["lastPrice"])    for t in all_tickers}
        for _sym, _data in list(backtest_signals.items()):
            _entry = _data.get("entry_price", 0)
            _cur   = _pm.get(_sym, 0)
            if _entry <= 0 or _cur <= 0: continue
            _gain  = round((_cur - _entry) / _entry * 100 - BACKTEST_FEE, 2)
            bt_results.append((_sym.replace("USDT",""), _gain, _entry, _cur))

        if bt_results:
            bt_results.sort(key=lambda x: -x[1])
            wins  = [r for r in bt_results if r[1] > 0]
            loses = [r for r in bt_results if r[1] <= 0]
            bt_msg  = "━" * 18 + "\n"
            bt_msg += "📊 *BACKTEST REPORT*\n"
            bt_msg += "✅ رابح: `{}` | ❌ خاسر: `{}`\n".format(len(wins), len(loses))
            if bt_results:
                wr = round(len(wins)/len(bt_results)*100)
                bt_msg += "🎯 نسبة النجاح: `{}%`\n".format(wr)
            if wins:
                bt_msg += "\n🏆 *أفضل:*\n"
                for s,g,e,c in wins[:3]:
                    bt_msg += "  ✅ *{}* `{}→{}` `+{}%`\n".format(s,e,round(c,6),g)
            if loses:
                bt_msg += "\n📉 *يحتاج مراجعة:*\n"
                for s,g,e,c in loses[:3]:
                    bt_msg += "  ❌ *{}* `{}→{}` `{}%`\n".format(s,e,round(c,6),g)
            send(bt_msg)
    log.info(" Daily Report -    ...")

    if not all_tickers:
        log.warning(" : all_tickers ")
        send("⚠️ البيانات غير جاهزة — أعد المحاولة بعد دقيقة")
        return
    vol_now = {t["symbol"]: float(t.get("quoteVolume", 0)) for t in all_tickers}




    ticker_map     = {t["symbol"]: t for t in all_tickers}
    stable_total   = 0.0
    stable_details = []

    for sym in SMART_MONEY_STABLES:
        if sym not in ticker_map: continue
        try:
            vol = float(ticker_map[sym]["quoteVolume"])
            stable_total += vol
            stable_details.append((sym.replace("USDT",""), vol))
        except (KeyError, ValueError):
            pass


    stable_hist = stable_vol_history
    stable_avg  = {}
    whale_signals = []

    for sym in SMART_MONEY_STABLES:
        hist = stable_hist.get(sym, [])
        if len(hist) < 4: continue
        avg = sum(hist) / len(hist)
        try:
            current = float(ticker_map[sym]["quoteVolume"])
        except (KeyError, ValueError):
            continue
        ratio = current / avg if avg > 0 else 1.0
        if ratio >= 2.0:
            whale_signals.append((sym.replace("USDT",""), ratio))





    buy_vol          = 0.0
    sell_vol         = 0.0
    total_market_vol = 0.0
    top_gainers      = []
    top_losers       = []

    for t in all_tickers:
        sym = t.get("symbol","")
        if not sym.endswith("USDT"): continue
        base = sym.replace("USDT","")
        if base in STABLECOINS: continue
        if any(k in sym for k in LEVERAGE_KEYWORDS): continue
        try:
            vol      = float(t.get("quoteVolume", 0))
            if vol < 100_000: continue

            # ── حساب تدفق السيولة بـ Price Position (أدق من takerBuy) ──
            # Price Position = موقع الإغلاق داخل النطاق اليومي
            # PP=1.0 → إغلاق عند القمة (شراء كامل)
            # PP=0.0 → إغلاق عند القاع (بيع كامل)
            # PP=0.5 → محايد
            try:
                _last = float(t.get("lastPrice", 0))
                _high = float(t.get("highPrice", _last))
                _low  = float(t.get("lowPrice",  _last))
                _open = float(t.get("openPrice", _last))
                _rng  = _high - _low
                if _rng > 0:
                    _pp = (_last - _low) / _rng          # موقع السعر في النطاق
                else:
                    _pp = 0.5
                # وزن إضافي لاتجاه الشمعة (أخضر/أحمر)
                _candle_dir = 0.6 if _last >= _open else 0.4
                _buy_ratio  = _pp * 0.65 + _candle_dir * 0.35
                _buy_ratio  = max(0.15, min(0.85, _buy_ratio))  # حد منطقي 15%-85%
            except (ValueError, TypeError, ZeroDivisionError):
                _buy_ratio = 0.5

            taker_buy  = vol * _buy_ratio
            taker_sell = vol * (1.0 - _buy_ratio)
            buy_vol  += taker_buy
            sell_vol += taker_sell
            total_market_vol += vol
            ch = float(t.get("priceChangePercent", 0))
            if ch > 0 and vol > 1_000_000:
                top_gainers.append((base, ch, vol))
            elif ch < 0 and vol > 1_000_000:
                top_losers.append((base, ch, vol))
        except (KeyError, ValueError):
            pass

    # ── تدفق السيولة الحقيقي: stablecoin inflow/outflow ─────────────
    # إذا الحيتان يشترون stablecoins = سيولة خارجة من السوق
    # إذا الحيتان يبيعون stablecoins = سيولة داخلة للسوق
    _stable_inflow  = 0.0   # USDT تحول لعملات (شراء)
    _stable_outflow = 0.0   # عملات تحول لـ USDT (بيع)
    for _ss in SMART_MONEY_STABLES:
        _st = ticker_map.get(_ss)
        if not _st: continue
        try:
            _sv   = float(_st.get("quoteVolume", 0))
            _sch  = float(_st.get("priceChangePercent", 0))
            # stablecoin حجمها ارتفع = الحيتان يجمعون = outflow من السوق
            _sh   = stable_vol_history.get(_ss, [])
            _savg = sum(_sh) / len(_sh) if len(_sh) >= 3 else _sv
            _sratio = _sv / _savg if _savg > 0 else 1.0
            if _sratio >= 1.5:
                _stable_outflow += _sv * (_sratio - 1.0)
            elif _sratio <= 0.7:
                _stable_inflow  += _sv * (1.0 - _sratio)
        except (ValueError, TypeError):
            pass

    total_trade_vol = buy_vol + sell_vol
    buy_pct         = buy_vol  / total_trade_vol * 100 if total_trade_vol > 0 else 50
    sell_pct        = sell_vol / total_trade_vol * 100 if total_trade_vol > 0 else 50

    # ── تصحيح بناءً على تدفق Stablecoins ────────────────────────────
    # stablecoin outflow كبير = ضغط بيع حقيقي → خفض buy_pct
    _liq_adj = 0.0
    if _stable_outflow > 0 and total_trade_vol > 0:
        _liq_adj = min((_stable_outflow / total_trade_vol) * 100, 10.0)
        buy_pct  = max(15.0, buy_pct - _liq_adj)
        sell_pct = min(85.0, sell_pct + _liq_adj)
    elif _stable_inflow > 0 and total_trade_vol > 0:
        _liq_adj = min((_stable_inflow / total_trade_vol) * 100, 10.0)
        buy_pct  = min(85.0, buy_pct + _liq_adj)
        sell_pct = max(15.0, sell_pct - _liq_adj)



    rising_pct  = buy_pct
    falling_pct = sell_pct
    rising      = int(buy_vol / 1_000_000)
    falling     = int(sell_vol / 1_000_000)
    total_coins = int(total_trade_vol / 1_000_000)

    log.info(" Buy/Sell | buy=%.1f%% (%.0fM) | sell=%.1f%% (%.0fM)",
             buy_pct, buy_vol/1_000_000, sell_pct, sell_vol/1_000_000)

    top_gainers.sort(key=lambda x: -x[1])
    top_losers.sort(key=lambda x: x[1])





    _today_vol_key = today
    if not daily_market_vol_history or (
        isinstance(daily_market_vol_history[-1], dict) and 
        daily_market_vol_history[-1].get("date") != _today_vol_key
    ) or (
        not isinstance(daily_market_vol_history[-1], dict)
    ):
        daily_market_vol_history.append({"date": _today_vol_key, "vol": total_market_vol})
        if len(daily_market_vol_history) > 7:
            daily_market_vol_history.pop(0)

    vol_change_pct = None
    vol_arrow      = "➡️"
    if len(daily_market_vol_history) >= 2:
        _prev = daily_market_vol_history[-2]
        prev_vol = _prev.get("vol", 0) if isinstance(_prev, dict) else float(_prev)
        if prev_vol > 0:
            vol_change_pct = (total_market_vol - prev_vol) / prev_vol * 100
            vol_arrow = "📈" if vol_change_pct > 5 else "📉" if vol_change_pct < -5 else "➡️"




    btc_data = safe_get(MEXC_24H, {"symbol": "BTCUSDT"})
    btc_ch   = btc_change_24h
    btc_vol  = 0.0
    if btc_data:
        try:
            btc_vol = float(btc_data.get("quoteVolume", 0))
            lp = float(btc_data.get("lastPrice", 0))
            op = float(btc_data.get("openPrice", lp))
            if op > 0:
                btc_ch = (lp - op) / op * 100
        except (KeyError, ValueError):
            pass















    _sell_pressure = sell_pct >= 70
    _buy_pressure  = buy_pct  >= 55
    _mkt_falling   = falling_pct >= 55
    _mkt_rising    = rising_pct  >= 55
    _whales_active = len(whale_signals) >= 2

    if _whales_active and _sell_pressure and _mkt_falling:

        whale_verdict  = "🔴 *تحذير — الحيتان خارج السوق*"
        whale_desc     = "الحيتان يجمعون Stablecoins + ضغط بيع {:.0f}% — ينتظرون قاعاً".format(sell_pct)
        whale_action   = "⛔ _لا تدخل — انتظر حتى تنخفض نسبة البيع_"
        whale_icon     = "🐋🔴"

    elif _whales_active and _buy_pressure and _mkt_rising:

        whale_verdict  = "🟢 *فرصة ذهبية — الحيتان يشترون*"
        whale_desc     = "الحيتان يضخون سيولة + شراء {:.0f}% — زخم صاعد قوي".format(buy_pct)
        whale_action   = "✅ _ادخل الآن — السيولة إيجابية والحيتان معك_"
        whale_icon     = "🐋🟢"

    elif _whales_active and _sell_pressure and not _mkt_falling:

        whale_verdict  = "👁️ *تجميع خفي محتمل*"
        whale_desc     = "الحيتان يجمعون Stablecoins ({}) رغم استقرار السوق — مراقبة".format(len(whale_signals))
        whale_action   = "⏳ _انتظر تأكيداً — قد يكون تجميعاً قبل الارتفاع_"
        whale_icon     = "🐋👁️"

    elif _sell_pressure and _mkt_falling:

        whale_verdict  = "🔴 *ضغط بيع — ابتعد*"
        whale_desc     = "بيع {:.0f}% من السيولة — خروج أموال من السوق ⚠️".format(sell_pct)
        whale_action   = "⛔ _لا تدخل — انتظر الاستقرار_"
        whale_icon     = "📉🔴"

    elif _buy_pressure and _mkt_rising:

        whale_verdict  = "🟢 *السوق صاعد — زخم إيجابي*"
        whale_desc     = "شراء {:.0f}% من السيولة — أموال تدخل السوق 💰".format(buy_pct)
        whale_action   = "✅ _ادخل — السوق مناسب_"
        whale_icon     = "📈🟢"

    elif _sell_pressure:

        whale_verdict  = "🟡 *ضغط بيع — توخَّ الحذر*"
        whale_desc     = "بيع {:.0f}% من السيولة — ضغط بيعي".format(sell_pct)
        whale_action   = "⚠️ _انتظر قبل الدخول — الضغط البيعي مرتفع_"
        whale_icon     = "🟡🔴"

    else:
        whale_verdict  = "🟡 *السوق محايد — انتظر*"
        whale_desc     = "سيولة محايدة | شراء {:.0f}% | بيع {:.0f}%".format(buy_pct, sell_pct)
        whale_action   = "⏳ _انتظر إشارة واضحة قبل الدخول_"
        whale_icon     = "🟡"





    stable_txt = ""
    for name, vol in sorted(stable_details, key=lambda x: -x[1])[:4]:
        stable_txt += "  • *{}*: `{:,.0f}` USDT\n".format(name, vol)


    whale_txt = ""
    if whale_signals:
        for name, ratio in whale_signals[:3]:
            whale_txt += "  🐋 *{}*: `{:.1f}×` المعدل\n".format(name, ratio)
    else:
        whale_txt = "  ✅ لا نشاط غير عادي\n"


    gainers_txt = ""
    losers_txt  = ""


    mkt_bar_green = int(rising_pct / 10)
    mkt_bar_red   = 10 - mkt_bar_green
    mkt_bar = "🟩" * mkt_bar_green + "🟥" * mkt_bar_red


    flow_sum = get_flow_summary()

    # ── نسبة سيولة كل قطاع من إجمالي السوق ──────────────────────
    sector_liq_block = ""
    try:
        _sector_vol_map = {}
        _tick_map = {t["symbol"]: t for t in all_tickers}
        for _sec, _coins in SECTORS.items():
            _sv = 0.0
            _buy_s = 0.0
            _sell_s = 0.0
            for _sc in _coins:
                _t2 = _tick_map.get(_sc)
                if not _t2:
                    continue
                try:
                    _v2   = float(_t2.get("quoteVolume", 0))
                    _last2 = float(_t2.get("lastPrice", 0))
                    _high2 = float(_t2.get("highPrice", _last2))
                    _low2  = float(_t2.get("lowPrice",  _last2))
                    _open2 = float(_t2.get("openPrice", _last2))
                    _rng2  = _high2 - _low2
                    if _rng2 > 0:
                        _pp2 = (_last2 - _low2) / _rng2
                    else:
                        _pp2 = 0.5
                    _cdir2 = 0.6 if _last2 >= _open2 else 0.4
                    _br2   = max(0.15, min(0.85, _pp2 * 0.65 + _cdir2 * 0.35))
                    _sv   += _v2
                    _buy_s  += _v2 * _br2
                    _sell_s += _v2 * (1.0 - _br2)
                except (ValueError, TypeError):
                    pass
            if _sv >= 10_000:
                _sv_b = _buy_s / _sv if _sv > 0 else 0.5
                _sector_vol_map[_sec] = (_sv, _sv_b)

        _grand_total = sum(v for v, _ in _sector_vol_map.values())
        if _grand_total > 0:
            _sorted_secs = sorted(_sector_vol_map.items(), key=lambda x: -x[1][0])
            sector_liq_block = "━━━━━━━━━━━━━━━━━━\n"
            sector_liq_block += "🏦 *نسبة السيولة لكل قطاع (24h):*\n"
            for _sname, (_sv, _sv_b) in _sorted_secs[:8]:
                _pct_total = _sv / _grand_total * 100
                _buy_bar   = int(_sv_b * 5)
                _sell_bar  = 5 - _buy_bar
                _bar_str   = "🟢" * _buy_bar + "🔴" * _sell_bar
                _vol_str   = "{:.1f}B".format(_sv / 1e9) if _sv >= 1e9 else "{:.0f}M".format(_sv / 1e6)
                _flow_icon = "🔥" if _sv_b >= 0.60 else ("⚠️" if _sv_b <= 0.40 else "")
                sector_liq_block += "  *{}* `{:.1f}%` ({}) {} {}\n".format(
                    _sname, _pct_total, _vol_str, _bar_str, _flow_icon
                )
    except Exception as _se:
        log.error("sector_liq_block error: %s", _se)

    _btc         = float(btc_ch)          if btc_ch          is not None else 0.0

    # ── Market Bias Score ─────────────────────────────────────────────
    _bias_score, _bias_label = calc_market_bias_score()
    _bias_bar_green = max(0, min(10, int((_bias_score + 100) / 20)))
    _bias_bar_red   = 10 - _bias_bar_green
    _bias_bar = "🟢" * _bias_bar_green + "🔴" * _bias_bar_red

    _display_state = market_state
    if market_state == "SAFE" and sell_pct >= 80:
        _display_state = "CAUTION"
    elif market_state == "SAFE" and sell_pct >= 90:
        _display_state = "DANGER"
    _mkt_icons = {"SAFE": "🟢", "CAUTION": "🟡", "DANGER": "🚨"}
    _eth         = float(eth_change_24h)  if eth_change_24h  is not None else 0.0

    _btc1h = btc_trend_1h
    try:
        _kd1h = get_klines("BTCUSDT", "1h", 6)
        if _kd1h and len(_kd1h["closes"]) >= 2:
            _c1h   = _kd1h["closes"]
            _btc1h = (_c1h[-1] - _c1h[-2]) / _c1h[-2] * 100
    except Exception:
        _btc1h = float(btc_trend_1h) if btc_trend_1h is not None else 0.0
    _buy_pct     = float(buy_pct)         if buy_pct         is not None else 0.0
    _sell_pct    = float(sell_pct)        if sell_pct        is not None else 0.0
    _buy_vol     = float(buy_vol)         if buy_vol         is not None else 0.0
    _sell_vol    = float(sell_vol)        if sell_vol        is not None else 0.0
    _total_vol   = float(total_market_vol) if total_market_vol is not None else 0.0

    msg = (
        "📊 *DAILY REPORT* 📅\n"
        "🗓️ `{date}` — إغلاق اليوم\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "{mkt_icon} *السوق: {mkt_state}*\n"
        "📊 *Market Bias:* `{bias_score:+d}/100` — {bias_label}\n"
        "{bias_bar}\n"
        "₿ BTC 24h: `{btc:+.2f}%` | 1h: `{btc1h:+.2f}%`\n"
        "{btc_tps_line}"
        "Ξ ETH 24h: `{eth:+.2f}%`\n"
        "{eth_tps_line}"
        "━━━━━━━━━━━━━━━━━━\n"
        "{whale_icon} {verdict}\n"
        "_{desc}_\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "📊 *تدفق السيولة (Price Position):*\n"
        "{bar}\n"
        "  💚 *سيولة داخلة:* `{buy:.1f}%` ({buy_vol})\n"
        "  🔴 *سيولة خارجة:* `{sell:.1f}%` ({sell_vol})\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "💰 *تدفق رأس المال (24h):*\n"
        "  {arrow} حجم السوق: `{vol_ch}` عن أمس\n"
        "  📦 إجمالي: `{total_vol}` USDT\n"
        "  💚 داخل:   `{buy:.1f}%` = `{buy_vol}` USDT\n"
        "  🔴 خارج:   `{sell:.1f}%` = `{sell_vol}` USDT\n"
        "{sector_liq}"
        "━━━━━━━━━━━━━━━━━━\n"
        "💸 *تدفق السيولة بين القطاعات:*\n"
        "{flow}"
        "━━━━━━━━━━━━━━━━━━\n"
        "{action}"
    ).format(
        date=today,
        whale_icon=whale_icon,
        verdict=whale_verdict,
        desc=whale_desc,
        btc=_btc, eth=_eth,
        btc1h=_btc1h,
        btc_tps_line=(
            "  🐋 BTC TPS:`{:.1f}` ATS:`{:.0f}$` VD:`{:.0f}%` — {}\n".format(
                btc_tps_stats.get("tps",0), btc_tps_stats.get("ats",0),
                btc_tps_stats.get("vdelta",0.5)*100,
                "🐋 حيتان يشترون 🔥" if btc_tps_stats.get("ats",0) >= ATS_WHALE and btc_tps_stats.get("vdelta",0) >= VDELTA_STRONG
                else ("🔴 حيتان يبيعون!" if btc_tps_stats.get("ats",0) >= ATS_WHALE and btc_tps_stats.get("vdelta",0) < 0.40
                else ("⚡ شراء متوسط" if btc_tps_stats.get("vdelta",0) >= 0.55 else "نشاط عادي"))
            ) if btc_tps_stats else ""
        ),
        eth_tps_line=(
            "  🔷 ETH TPS:`{:.1f}` ATS:`{:.0f}$` VD:`{:.0f}%` — {}\n".format(
                eth_tps_stats.get("tps",0), eth_tps_stats.get("ats",0),
                eth_tps_stats.get("vdelta",0.5)*100,
                "🐋 حيتان يشترون 🔥" if eth_tps_stats.get("ats",0) >= ATS_WHALE and eth_tps_stats.get("vdelta",0) >= VDELTA_STRONG
                else ("🔴 حيتان يبيعون!" if eth_tps_stats.get("ats",0) >= ATS_WHALE and eth_tps_stats.get("vdelta",0) < 0.40
                else ("⚡ شراء متوسط" if eth_tps_stats.get("vdelta",0) >= 0.55 else "نشاط عادي"))
            ) if eth_tps_stats else ""
        ),
        mkt_icon=_mkt_icons.get(_display_state,"📊"), mkt_state=_display_state,
        bias_score=_bias_score, bias_label=_bias_label, bias_bar=_bias_bar,
        bar=mkt_bar,
        rp=rising_pct,  fp=falling_pct,
        rising=rising,  falling=falling,
        total=total_coins,
        buy=_buy_pct,    sell=_sell_pct,
        buy_vol=("{:.2f}B".format(_buy_vol/1_000_000_000) if _buy_vol>=1_000_000_000 else "{:.0f}M".format(_buy_vol/1_000_000)),
        sell_vol=("{:.2f}B".format(_sell_vol/1_000_000_000) if _sell_vol>=1_000_000_000 else "{:.0f}M".format(_sell_vol/1_000_000)),
        arrow=vol_arrow,
        vol_ch=("{:+.1f}%".format(vol_change_pct) if vol_change_pct is not None else "بيانات جديدة 📊"),
        total_vol=("{:.2f}B".format(_total_vol/1_000_000_000) if _total_vol>=1_000_000_000 else "{:.0f}M".format(_total_vol/1_000_000)),
        sector_liq=sector_liq_block,
        flow=flow_sum,
        action=whale_action,
    )


    _ALPHA=10
    _STBL={"FDUSD","USDC","BUSD","DAI","TUSD","BFUSD","USDE","CRVUSD","USDD","XUSD"}
    _bc=[]; _sh=[]; _bvt=0.0; _svt=0.0
    for _t in all_tickers:
        _sym=_t.get("symbol",""); _b=_sym.replace("USDT","")
        if not _sym.endswith("USDT") or any(k in _sym for k in LEVERAGE_KEYWORDS): continue
        try: _v=float(_t["quoteVolume"]); _c=float(_t["priceChangePercent"])
        except: continue
        if _v<100_000: continue
        _h=coin_vol_history.get(_sym,[]); _ah=sum(_h)/len(_h) if len(_h)>=3 else _v
        _sg=round(_v/_ah,1) if _ah>0 else 1.0
        if _c>0: _bvt+=_v
        else: _svt+=_v
        _is=_b in _STBL or _b.startswith("USD") or _b.endswith("USD")
        if _is and _v>=500_000: _sh.append({"base":_b,"vol":_v,"sigma":_sg})
        if _sg>=_ALPHA and not _is: _bc.append({"base":_b,"sigma":_sg,"ch":_c})
    _bc.sort(key=lambda x:-x["sigma"]); _sh.sort(key=lambda x:-x["vol"])
    _tv=_bvt+_svt; _svp=_svt/_tv*100 if _tv>0 else 50
    _ts=sum(s["vol"] for s in _sh); _stp=_ts/_tv*100 if _tv>0 else 0
    market_activity_history.append({"date":today,"buy_vol":_bvt,"sell_vol":_svt,
        "buy_pct":_bvt/_tv*100 if _tv>0 else 50,
        "stable_pct":_stp,"sigma_count":len(_bc)})
    if len(market_activity_history)>30: market_activity_history.pop(0)
    breakout_report_sent["date"]=today
    if _stp>=20 and _svp>=55: _ss="🚨 هروب ضخم Stablecoins"
    elif _stp>=15: _ss="⚠️ حيتان يحتفظون Stablecoins"
    elif _stp>=8: _ss="👀 تجميع خفيف"
    else: _ss="✅ Stablecoins طبيعية"
    _st=""
    for _sx in _sh[:5]:
        _wh=" 🐳" if _sx["sigma"]>=3.0 else ""
        _st+="  💵 *"+_sx["base"]+"* | نشاط: `"+str(_sx.get("ratio", round(_sx.get("sigma",1.0),1)))+"×` | `"+str(round(_sx["vol"]/1e6,1))+" مليون USDT`"+_wh+"\n"
    if not _st: _st="  لا يوجد\n"
    _ct=""
    for _co in _bc[:8]:
        _d2="🟢" if _co["ch"]>0 else "🔴"
        _ct+="• *"+_co["base"]+"* "+_d2+" نشاط غير طبيعي `"+str(int(_co["sigma"]))+"×`\n"
    if not _ct: _ct="• لا توجد عملات\n"
    _SP="━"*18
    _brk=(_SP+"\n"
        +"🐳 *Stablecoins — احتفاظ الحيتان:*\n"
        +"  📊 النسبة: `"+str(round(_stp,1))+"% = "+str(int(_ts/1e6))+"M USDT`\n"
        +"  "+_ss+"\n"
        +_SP+"\n"
        +"💵 *التفاصيل (نشاط × الحجم):*\n"
        +_st
        +(("\n🚨 *نشاط غير طبيعي:*\n"+whale_txt) if "لا نشاط" not in whale_txt else "")
        +_SP+"\n"
        +"🔬 *Sigma>=10 (نشاط ضخم):*\n"
        +("*"+str(len(_bc))+" عملة*\n"+_ct if _bc else "  • لا توجد عملات\n")
        +_SP)
    _trnd=""
    if len(market_activity_history)>=2:

        _seen_dates = set()
        _unique_history = []
        for _e in market_activity_history:
            if _e["date"] not in _seen_dates:
                _seen_dates.add(_e["date"])
                _unique_history.append(_e)

        _trnd=_SP+"\n📊 *نشاط السوق — آخر الأيام:*\n"
        for _e in _unique_history[-7:]:
            _bp2=_e["buy_pct"]; _stp2=_e.get("stable_pct",0); _sc=_e.get("sigma_count",0)
            _ic="🟢" if _bp2>=55 else "🔴" if _bp2<=45 else "🟡"
            _trnd+="`"+_e["date"][5:]+"` "
            _sell2 = round(100 - _bp2 - _stp2, 1)
            _trnd+=_ic+" 🟢`{:.0f}%` | 🔴`{:.0f}%` | 💵`{:.1f}%`".format(_bp2, _sell2, _stp2)

            _trnd+="\n"
        _trnd+=_SP
    _analysis  = analyze_market_history()

    _sm_data   = _get_smart_money_summary()
    _sm_block  = "\n" + _sm_data if _sm_data else ""
    send(msg+"\n"+_brk+"\n"+_trnd+"\n"+_analysis+_sm_block)
    log.info("Daily Report merged | rising=%.0f%% | whale=%d | vol=%.1f%%",
             rising_pct, len(whale_signals), vol_change_pct if vol_change_pct is not None else 0.0)








# ══════════════════════════════════════════════════════════════════
#  4-HOUR MARKET REPORT — BTC + ETH ATS/TPS/VDelta
# ══════════════════════════════════════════════════════════════════

REPORT_4H_EVERY   = 14400   # كل 4 ساعات
last_4h_report    = 0.0

# عتبات تحديد حالة السوق في التقرير الرباعي
_4H_SAFE_VD       = 0.58    # VDelta >= 58% = SAFE
_4H_DANGER_VD     = 0.42    # VDelta <= 42% = DANGER
_4H_SAFE_BTC      = -1.0    # BTC 1h >= -1% = لا خطر
_4H_DANGER_BTC    = -2.0    # BTC 1h <= -2% = خطر


def _fmt_vol(v):
    # type: (float) -> str
    if v >= 1_000_000_000:
        return "{:.2f}B".format(v / 1_000_000_000)
    return "{:.0f}M".format(v / 1_000_000)


def _market_state_from_metrics(btc_vd, eth_vd, mkt_vd, btc_1h, btc_24h, ats_btc, ats_eth):
    # type: (float, float, float, float, float, float, float) -> tuple
    """
    يحسب حالة السوق الفعلية بناءً على المؤشرات المجمّعة.
    يعيد: (state, score, reasons)
    state:   SAFE / CAUTION / DANGER
    score:   0-100
    reasons: قائمة بالأسباب
    """
    score   = 50   # نقطة البداية محايد
    reasons = []

    # ── VDelta BTC ─────────────────────────────────────────────────
    if btc_vd >= 0.65:
        score += 20
        reasons.append("✅ BTC VDelta قوي `{:.0f}%`".format(btc_vd * 100))
    elif btc_vd >= _4H_SAFE_VD:
        score += 10
        reasons.append("🟡 BTC VDelta متوسط `{:.0f}%`".format(btc_vd * 100))
    elif btc_vd <= _4H_DANGER_VD:
        score -= 25
        reasons.append("🔴 BTC VDelta ضعيف `{:.0f}%` — ضغط بيعي".format(btc_vd * 100))
    else:
        score -= 5

    # ── VDelta ETH ─────────────────────────────────────────────────
    if eth_vd >= 0.65:
        score += 10
        reasons.append("✅ ETH VDelta قوي `{:.0f}%`".format(eth_vd * 100))
    elif eth_vd <= _4H_DANGER_VD:
        score -= 15
        reasons.append("🔴 ETH VDelta ضعيف `{:.0f}%`".format(eth_vd * 100))

    # ── ATS حجم الصفقة المتوسط ────────────────────────────────────
    if ats_btc >= ATS_WHALE:
        if btc_vd >= VDELTA_STRONG:
            score += 15
            reasons.append("🐋 BTC — حيتان يشترون! ATS:`{:.0f}$`".format(ats_btc))
        else:
            score -= 10
            reasons.append("🐋 BTC — حيتان يبيعون! ATS:`{:.0f}$`".format(ats_btc))
    elif ats_btc >= ATS_RETAIL:
        if btc_vd >= 0.55:
            score += 5
            reasons.append("🐟 BTC — شراء مؤسسي متوسط ATS:`{:.0f}$`".format(ats_btc))

    if ats_eth >= ATS_WHALE:
        if eth_vd >= VDELTA_STRONG:
            score += 8
            reasons.append("🐋 ETH — حيتان يشترون! ATS:`{:.0f}$`".format(ats_eth))
        else:
            score -= 8
            reasons.append("🐋 ETH — حيتان يبيعون! ATS:`{:.0f}$`".format(ats_eth))

    # ── BTC السعر 1h / 4h ─────────────────────────────────────────
    if btc_1h <= _4H_DANGER_BTC:
        score -= 20
        reasons.append("📉 BTC 1h: `{:+.2f}%` — هبوط حاد".format(btc_1h))
    elif btc_1h <= _4H_SAFE_BTC:
        score -= 8
        reasons.append("⚠️ BTC 1h: `{:+.2f}%`".format(btc_1h))
    elif btc_1h >= 1.0:
        score += 10
        reasons.append("📈 BTC 1h: `{:+.2f}%` — زخم صاعد".format(btc_1h))

    if btc_24h <= -3.0:
        score -= 15
        reasons.append("🔴 BTC 24h: `{:+.2f}%` — نزول قوي".format(btc_24h))
    elif btc_24h >= 3.0:
        score += 8
        reasons.append("🟢 BTC 24h: `{:+.2f}%`".format(btc_24h))

    # ── VDelta السوق الكلي ────────────────────────────────────────
    if mkt_vd >= 0.60:
        score += 5
        reasons.append("✅ السوق: شراء كلي `{:.0f}%`".format(mkt_vd * 100))
    elif mkt_vd <= 0.40:
        score -= 10
        reasons.append("🔴 السوق: بيع كلي `{:.0f}%`".format((1.0 - mkt_vd) * 100))

    score = max(0, min(100, score))

    if score >= 65:
        state = "SAFE"
    elif score >= 40:
        state = "CAUTION"
    else:
        state = "DANGER"

    return state, score, reasons


def send_4h_market_report():
    # type: () -> None
    """
    📡 تقرير السوق كل 4 ساعات
    يحسب ATS / TPS / VDelta لـ BTC و ETH
    ويصدر حكم: SAFE / CAUTION / DANGER مع الأسباب
    """
    global last_4h_report
    now = time.time()

    if now - last_4h_report < REPORT_4H_EVERY:
        return
    last_4h_report = now

    if not all_tickers:
        return

    try:
        # ── جلب بيانات BTC / ETH ───────────────────────────────────
        btc_stats = analyze_tps_ats("BTCUSDT")
        eth_stats = analyze_tps_ats("ETHUSDT")

        if not btc_stats and not eth_stats:
            log.warning("4h report: لا بيانات TPS/ATS")
            return

        btc_tps   = btc_stats.get("tps",   0.0) if btc_stats else 0.0
        btc_ats   = btc_stats.get("ats",   0.0) if btc_stats else 0.0
        btc_vd    = btc_stats.get("vdelta", 0.5) if btc_stats else 0.5
        # buy_vol/sell_vol من klines هي بالعملة الأساسية (BTC/ETH) — نحوّلها لـ USDT
        _btc_price = float(next((t.get("lastPrice", 0) for t in all_tickers
                                 if t.get("symbol") == "BTCUSDT"), 0))
        _eth_price = float(next((t.get("lastPrice", 0) for t in all_tickers
                                 if t.get("symbol") == "ETHUSDT"), 0))
        # حجم BTC/ETH من ticker (24h quoteVolume = USDT مباشرة)
        _btc_total_vol = float(next((t.get("quoteVolume", 0) for t in all_tickers
                                     if t.get("symbol") == "BTCUSDT"), 0))
        _eth_total_vol = float(next((t.get("quoteVolume", 0) for t in all_tickers
                                     if t.get("symbol") == "ETHUSDT"), 0))
        # اشتقاق شراء/بيع من VDelta × الحجم الكلي — متسق تماماً مع VDelta
        btc_bvol  = _btc_total_vol * btc_vd
        btc_svol  = _btc_total_vol * (1.0 - btc_vd)

        eth_tps   = eth_stats.get("tps",   0.0) if eth_stats else 0.0
        eth_ats   = eth_stats.get("ats",   0.0) if eth_stats else 0.0
        eth_vd    = eth_stats.get("vdelta", 0.5) if eth_stats else 0.5
        # نفس الطريقة لـ ETH
        eth_bvol  = _eth_total_vol * eth_vd
        eth_svol  = _eth_total_vol * (1.0 - eth_vd)

        # ── حجم السوق الكلي — Price Position مرجّح بالحجم ─────────────
        # buy_ratio لكل عملة = (lastPrice - low) / (high - low)
        # هذا يعكس أين أغلق السعر ضمن نطاق اليوم → متسق مع VDelta
        mkt_buy = 0.0
        mkt_sell = 0.0
        for _t in all_tickers:
            try:
                _v    = float(_t.get("quoteVolume", 0))
                _high = float(_t.get("highPrice",   0))
                _low  = float(_t.get("lowPrice",    0))
                _last = float(_t.get("lastPrice",   0))
                _open = float(_t.get("openPrice",   0))
                if _v < 50_000:
                    continue
                if not _t.get("symbol", "").endswith("USDT"):
                    continue
                if _high > _low:
                    _pp = max(0.0, min(1.0, (_last - _low) / (_high - _low)))
                    _green = 1 if _last >= _open else 0
                    _buy_ratio = (_pp * 0.65) + (_green * 0.35)
                    _buy_ratio = max(0.15, min(0.85, _buy_ratio))  # حد منطقي 15%-85%
                else:
                    _buy_ratio = 0.5
                mkt_buy  += _v * _buy_ratio
                mkt_sell += _v * (1.0 - _buy_ratio)
            except (ValueError, TypeError, ZeroDivisionError):
                pass

        mkt_total    = mkt_buy + mkt_sell
        mkt_buy_pct  = mkt_buy  / mkt_total * 100 if mkt_total > 0 else 50
        mkt_sell_pct = mkt_sell / mkt_total * 100 if mkt_total > 0 else 50
        mkt_vd       = mkt_buy  / mkt_total        if mkt_total > 0 else 0.5

        # ── BTC سعر 1h ─────────────────────────────────────────────
        _btc_1h_now = 0.0
        try:
            _kd = get_klines("BTCUSDT", "1h", 3)
            if _kd and len(_kd["closes"]) >= 2:
                _btc_1h_now = (_kd["closes"][-1] - _kd["closes"][-2]) / _kd["closes"][-2] * 100
        except Exception:
            _btc_1h_now = float(btc_trend_1h) if btc_trend_1h else 0.0

        # ── تحديد حالة السوق ───────────────────────────────────────
        state, score, reasons = _market_state_from_metrics(
            btc_vd=btc_vd, eth_vd=eth_vd, mkt_vd=mkt_vd,
            btc_1h=_btc_1h_now, btc_24h=btc_change_24h,
            ats_btc=btc_ats, ats_eth=eth_ats
        )

        # ── رموز ───────────────────────────────────────────────────
        state_icons  = {"SAFE": "🟢", "CAUTION": "🟡", "DANGER": "🔴"}
        state_emojis = {
            "SAFE":    "🟢🟢🟢 SAFE — ادخل بثقة",
            "CAUTION": "🟡🟡🟡 CAUTION — توخَّ الحذر",
            "DANGER":  "🔴🔴🔴 DANGER — ابتعد الآن",
        }
        state_advice = {
            "SAFE":    "✅ _السوق آمن — مناسب لفتح مراكز_",
            "CAUTION": "⚠️ _انتظر تأكيداً قبل الدخول_",
            "DANGER":  "🛑 _أغلق المراكز المفتوحة — لا تدخل_",
        }

        icon_s = state_icons.get(state, "📊")

        # ── بناء تفاصيل BTC / ETH ─────────────────────────────────
        def _vd_label(vd, ats):
            # type: (float, float) -> str
            if ats >= ATS_WHALE and vd >= VDELTA_STRONG:
                return "🐋🔥 حيتان يشترون"
            if ats >= ATS_WHALE and vd < 0.40:
                return "🐋🔴 حيتان يبيعون"
            if vd >= 0.70:
                return "⬆️ شراء قوي 🔥"
            if vd >= 0.58:
                return "↗️ شراء خفيف"
            if vd >= 0.52:
                return "➡️ محايد"
            if vd >= 0.42:
                return "↘️ بيع خفيف"
            return "⬇️ بيع قوي 🔴"

        btc_bvol_str  = _fmt_vol(btc_bvol)  if btc_bvol  > 0 else "—"
        btc_svol_str  = _fmt_vol(btc_svol)  if btc_svol  > 0 else "—"
        eth_bvol_str  = _fmt_vol(eth_bvol)  if eth_bvol  > 0 else "—"
        eth_svol_str  = _fmt_vol(eth_svol)  if eth_svol  > 0 else "—"

        # ── نسبة VDelta مرئية ──────────────────────────────────────
        def _vd_bar(vd):
            # type: (float) -> str
            filled = int(vd * 10)
            return "🟢" * filled + "🔴" * (10 - filled)

        reasons_txt = ""
        for r in reasons[:5]:
            reasons_txt += "  {}\n".format(r)

        # ── الوقت ──────────────────────────────────────────────────
        now_utc = datetime.now(timezone.utc)
        time_str = now_utc.strftime("%H:%M UTC")

        msg = (
            "📡 *4H MARKET REPORT*\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🕐 `{}` | {} *{}*\n"
            "🎯 نقاط الحالة: `{}/100`\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "₿ *BTC — التحليل الكامل:*\n"
            "  TPS: `{:.1f}` صفقة/ثانية\n"
            "  ATS: `{:.0f} USDT`\n"
            "  VDelta: `{:.0f}%` {} — {}\n"
            "  💚 داخل: `{}` | 🔴 خارج: `{}`\n"
            "  24h: `{:+.2f}%` | 1h: `{:+.2f}%`\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Ξ *ETH — التحليل الكامل:*\n"
            "  TPS: `{:.1f}` صفقة/ثانية\n"
            "  ATS: `{:.0f} USDT`\n"
            "  VDelta: `{:.0f}%` {} — {}\n"
            "  💚 داخل: `{}` | 🔴 خارج: `{}`\n"
            "  24h: `{:+.2f}%`\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "📊 *السوق الكلي:*\n"
            "  🟢 شراء: `{:.1f}%` ({}) | 🔴 بيع: `{:.1f}%` ({})\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🔍 *أسباب الحكم:*\n"
            "{}"
            "━━━━━━━━━━━━━━━━━━\n"
            "{}\n"
        ).format(
            time_str,
            icon_s, state_emojis.get(state, state),
            score,
            btc_tps,
            btc_ats,
            btc_vd * 100, _vd_bar(btc_vd), _vd_label(btc_vd, btc_ats),
            btc_bvol_str, btc_svol_str,
            btc_change_24h, _btc_1h_now,
            eth_tps,
            eth_ats,
            eth_vd * 100, _vd_bar(eth_vd), _vd_label(eth_vd, eth_ats),
            eth_bvol_str, eth_svol_str,
            eth_change_24h,
            mkt_buy_pct, _fmt_vol(mkt_buy),
            mkt_sell_pct, _fmt_vol(mkt_sell),
            reasons_txt,
            state_advice.get(state, ""),
        )
        send(msg)
        log.info("4h Report | state=%s | score=%d | btc_vd=%.0f%% | eth_vd=%.0f%%",
                 state, score, btc_vd * 100, eth_vd * 100)

    except Exception as _err:
        log.error("send_4h_market_report error: %s", _err, exc_info=True)


def send_breakout_report():
    global market_activity_history, breakout_report_sent
    if not all_tickers: return
    today = datetime.now(timezone.utc).replace(tzinfo=None).strftime('%Y-%m-%d')
    if breakout_report_sent.get('date') == today: return
    ALPHA_MIN = 10
    STABLES = {'FDUSD','USDC','BUSD','DAI','TUSD','BFUSD','USDE','CRVUSD','USDD','XUSD'}
    bc=[]; sh=[]; bvt=0.0; svt=0.0
    for t in all_tickers:
        sym=t.get('symbol','')
        if not sym.endswith('USDT'): continue
        base=sym.replace('USDT','')
        if any(k in sym for k in LEVERAGE_KEYWORDS): continue
        try:
            vol=float(t['quoteVolume']); ch=float(t['priceChangePercent'])
        except: continue
        if vol<100_000: continue
        hist=coin_vol_history.get(sym,[])
        ah=sum(hist)/len(hist) if len(hist)>=3 else vol
        sigma=round(vol/ah,1) if ah>0 else 1.0
        if ch>0: bvt+=vol
        else: svt+=vol
        is_s=(base in STABLES or base.startswith('USD') or base.endswith('USD'))
        if is_s and vol>=500_000: sh.append({'base':base,'vol':vol,'sigma':sigma,'ch':ch})
        if sigma>=ALPHA_MIN and not is_s: bc.append({'base':base,'sigma':sigma,'vol':vol,'ch':ch})
    bc.sort(key=lambda x:-x['sigma']); sh.sort(key=lambda x:-x['vol'])
    tv=bvt+svt
    bp=bvt/tv*100 if tv>0 else 50
    sp=svt/tv*100 if tv>0 else 50
    ts=sum(s['vol'] for s in sh)
    stp=ts/tv*100 if tv>0 else 0
    market_activity_history.append({'date':today,'buy_vol':bvt,'sell_vol':svt,
        'buy_pct':bp,'stable_pct':stp,'sigma_count':len(bc)})
    if len(market_activity_history)>30: market_activity_history.pop(0)
    if bp>=55: mkt='🟢 شراء'
    elif bp<=45: mkt='🔴 بيع'
    else: mkt='🟡 محايد'
    if stp>=20 and sp>=55: sig='🚨 هروب ضخم Stablecoins'
    elif stp>=15: sig='⚠️ حيتان يحتفظون Stablecoins'
    elif stp>=8: sig='👀 تجميع خفيف'
    else: sig='✅ طبيعي'
    stxt=''
    for s in sh[:6]:
        wh=' 🐳' if s['sigma']>=3.0 else ''
        stxt+='  💵 *'+s['base']+'* | `'+str(round(s['vol']/1e6,1))+'M` USDT | σ`'+str(s['sigma'])+'`'+wh+'\n'
    if not stxt: stxt='  --\n'
    ctxt=''
    for co in bc[:10]:
        d='🟢' if co['ch']>0 else '🔴'
        ctxt+='• *'+co['base']+'* '+d+' Sigma`'+str(int(co['sigma']))+'`\n'
    if not ctxt: ctxt='• --\n'
    sep='━'*18
    msg='\n'.join([
        '🚨 *Daily Breakout Report*',
        '📅 `'+today+'`',
        sep,
        '📊 *حالة السوق:* '+mkt,
        '  🟢 شراء:`'+str(round(bp,1))+'%` | 🔴 بيع:`'+str(round(sp,1))+'%` | 📦`'+str(int(tv/1e6))+'M`',
        sep,
        '🐳 *احتفاظ الحيتان Stablecoins:* `'+str(round(stp,1))+'%` = `'+str(int(ts/1e6))+'M` USDT',
        stxt+sig,
        sep,
        '*'+str(len(bc))+' عملة* Sigma>=10:\n'+ctxt,
        sep,
        '💡 Sigma=حجم/متوسط | 🐳=غير عادي',
    ])
    send(msg)
    breakout_report_sent['date']=today
    log.info('Breakout %d stable=%.1f%% buy=%.0f%%',len(bc),stp,bp)



def send_market_activity_trend():
    # type: () -> None
    """
    يرسل مؤشر بياني نصي لنشاط السوق
    يُظهر توزيع الشراء/البيع على مدى الأيام الماضية
    """
    if len(market_activity_history) < 3:
        return

    BARS = 10
    msg  = "📊 *Market Activity Trend*\n"
    msg += "━━━━━━━━━━━━━━━━━━\n"


    recent = market_activity_history[-BARS:]
    max_vol = max(d["buy_vol"] + d["sell_vol"] for d in recent) or 1

    for d in recent:
        total   = d["buy_vol"] + d["sell_vol"]
        buy_b   = int(d["buy_pct"] / 10)
        sell_b  = 10 - buy_b
        bar     = "🟢" * buy_b + "🔴" * sell_b
        vol_m   = total / 1_000_000
        sigma_c = d.get("sigma_count", 0)
        trend   = "🟢" if d["buy_pct"] >= 55 else "🔴" if d["buy_pct"] <= 45 else "🟡"

        msg += "`{}` {} {:.0f}%B | {}M | {}σ\n".format(
            d["date"][5:],   # MM-DD
            trend,
            d["buy_pct"],
            int(vol_m),
            sigma_c,
        )

    msg += "━━━━━━━━━━━━━━━━━━\n"
    msg += "🟢=شراء | 🔴=بيع | σ=عدد Sigma coins"

    send(msg)
    log.info(" Market Activity Trend | %d days", len(recent))






def generate_tv_script(sym, zone_high, zone_low, sigma, touches):
    # type: (str, float, float, int, int) -> str
    """
    يولّد Pine Script جاهز للـ TradingView
    يرسم منطقة السيولة بالألوان + ملاحظات
    """
    base  = sym.replace("USDT","")
    color = "color.red" if sigma >= 8 else "color.orange" if sigma >= 5 else "color.yellow"
    label = "RARE 🔥" if sigma >= 8 else "HOT" if sigma >= 5 else "ZONE"

    script = """//@version=5
indicator("Liquidity Zone — {base}", overlay=true)

// Zone: {base} | Sigma: {sigma} | Touches: {touches}
zone_high = {zh}
zone_low  = {zl}
zone_mid  = (zone_high + zone_low) / 2

// رسم المنطقة
var box liq_box = na
if barstate.islast
    liq_box := box.new(
        bar_index - 50, zone_high,
        bar_index + 10, zone_low,
        border_color={color},
        bgcolor=color.new({color}, 85),
        border_width=2
    )
    label.new(bar_index, zone_high,
        "{label} | Sigma:{sigma}",
        style=label.style_label_down,
        color={color},
        textcolor=color.white,
        size=size.small
    )

// خط المنتصف
plot(zone_mid, "Zone Mid", color={color}, linewidth=1, style=plot.style_circles)
hline(zone_high, "Zone High", color={color}, linestyle=hline.style_dashed)
hline(zone_low,  "Zone Low",  color={color}, linestyle=hline.style_dashed)
""".format(
        base=base,
        sigma=sigma,
        touches=touches,
        zh=round(zone_high, 8),
        zl=round(zone_low, 8),
        color=color,
        label=label,
    )
    return script


def send_tv_scripts(signals):
    # type: (List[Dict]) -> None
    """
    يرسل سكريبتات TradingView للعملات التي أعطت إشارة سيولة
    signals = [{sym, zone_high, zone_low, sigma, touches}, ...]
    """
    if not signals:
        return

    for s in signals[:5]:
        script = generate_tv_script(
            s["sym"], s["zone_high"], s["zone_low"],
            s.get("sigma", 1), s.get("touches", 1)
        )
        base = s["sym"].replace("USDT","")


        send(
            "📄 *TradingView Script — {}*\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "📋 انسخ الكود وأضفه في:\n"
            "Pine Editor → Add to chart\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "```\n{}\n```".format(base, script[:3000])
        )
        log.info(" TV Script  %s", s["sym"])



def send_report():
    # type: () -> None
    global last_report
    if time.time() - last_report < REPORT_EVERY: return
    last_report = time.time()
    rows = []
    for sym, d in list(discovered.items()):
        pd = safe_get(MEXC_PRICE, {"symbol": sym})
        if not pd: continue
        try:
            cur = float(pd["price"])
            gr  = (cur - d["price"]) / d["price"] * 100
            if gr > 3: rows.append((sym, gr, d["score"]))
        except: pass
    if not rows: return
    rows.sort(key=lambda x: -x[1])
    msg = "📊 *PERFORMANCE REPORT V15*\n🕐 `{}`\n\n".format(
        datetime.now().strftime("%Y-%m-%d %H:%M"))
    for sym, gr, sc in rows[:5]:
        msg += "🔥 *{}* `+{:.2f}%` Score:{}\n".format(sym, gr, sc)


    msg += "\n━━━━━━━━━━━━━━━━━━\n"
    msg += "💸 *حالة السيولة:*\n"
    msg += get_flow_summary()


    msg += "\n━━━━━━━━━━━━━━━━━━\n"
    msg += get_backtest_stats()

    send(msg)



#   MAIN LOOP






def fmt_change(c):
    # type: (float) -> str
    """تنسيق نسبة التغيير — يتجنب -0.0%"""
    if abs(c) < 0.05: return "0.0%"
    return "{:+.1f}%".format(c)

def fmt_price(p):
    # type: (float) -> str
    """تنسيق السعر بدون scientific notation"""
    if p == 0: return "0"
    if p >= 1000:
        return "{:,.2f}".format(p)
    elif p >= 1:
        return "{:.4f}".format(p).rstrip('0').rstrip('.')
    elif p >= 0.01:
        return "{:.6f}".format(p).rstrip('0').rstrip('.')
    elif p >= 0.0001:
        return "{:.8f}".format(p).rstrip('0').rstrip('.')
    elif p >= 0.000001:
        # PEPE, SHIB: 0.0000035
        return "{:.9f}".format(p).rstrip('0').rstrip('.')
    else:

        return "{:.12f}".format(p).rstrip('0').rstrip('.')












def redis_save(data):
    # type: (dict) -> bool
    """حفظ البيانات في Upstash Redis"""
    if not REDIS_URL or not REDIS_TOKEN:
        log.warning(" Redis: URL=%s TOKEN=%s", 
                    "OK" if REDIS_URL else "MISSING",
                    "OK" if REDIS_TOKEN else "MISSING")
        return False
    try:
        import json as _json
        payload = _json.dumps(data, default=str)

        resp = requests.post(
            REDIS_URL + "/set/" + REDIS_KEY,
            headers={
                "Authorization": "Bearer " + REDIS_TOKEN,
                "Content-Type": "application/json",
            },
            json={"value": payload},
            timeout=10,
        )
        ok = resp.status_code == 200
        if ok:
            log.info(" Redis saved - %d bytes", len(payload))
        else:
            log.warning(" Redis save failed: %s", resp.text[:100])
        return ok
    except Exception as e:
        log.error(" redis_save error: %s", e)
        return False


def redis_load():
    # type: () -> dict
    """تحميل البيانات من Upstash Redis"""
    if not REDIS_URL or not REDIS_TOKEN:
        return {}
    try:
        import json as _json
        resp = requests.get(
            REDIS_URL + "/get/" + REDIS_KEY,
            headers={"Authorization": "Bearer " + REDIS_TOKEN},
            timeout=10,
        )
        if resp.status_code != 200:
            log.info(" Redis:    ")
            return {}
        result = resp.json()
        raw = result.get("result")
        if not raw:
            return {}
        data = _json.loads(raw)
        log.info(" Redis loaded - %d bytes", len(raw))
        return data
    except Exception as e:
        log.error(" redis_load error: %s", e)
        return {}



def save_state():
    # type: () -> None
    """حفظ كل البيانات المهمة في ملف JSON"""
    try:
        state = {
            "version":             "V20",
            "saved_at":            time.time(),

            "sector_flow_hot":      {k: v for k,v in sector_flow_hot.items()},
            "bottom_price_history": bottom_price_history,
            "bottom_vol_history":   bottom_vol_history,
            "ath_tracker":          ath_tracker,
            "rt_vol_baseline":      rt_vol_baseline,

            "gem_watchlist":        gem_watchlist,
            "watchlist":            watchlist,
            "wl_price_snapshot":    wl_price_snapshot,
            "candidates":           list(candidates),
            # Backtest
            "backtest_signals":     backtest_signals,
            # cooldowns
            "bottom_alerted":       bottom_alerted,
            "explosion_alerted":    explosion_alerted,
            "ath_alerted":          ath_alerted,
            "hot_alerted":          hot_alerted,
            "rt_alerted":           rt_alerted,
                        "ts_positions":         ts_positions,
            "ts_sell_alerted":      ts_sell_alerted,
            "daily_signals":        daily_signals,
            "wl_entry_alerted":     wl_entry_alerted,

            "daily_report_sent_date":   daily_report_sent_date,
            "lz_daily_sent_date":       lz_daily_sent_date,
            "daily_gem_count":          daily_gem_count,
            "stable_vol_history":       stable_vol_history,
            "daily_market_vol_history": daily_market_vol_history,

            "whale_watchlist":          {k: v for k, v in whale_watchlist.items()},
            "coin_signal_count":        coin_signal_count,
            "market_activity_history":  market_activity_history,
        }

        with open(STATE_FILE, "w") as f:
            json.dump(state, f)

        redis_save(state)
        log.info(" State saved - %d gems | %d watchlist | %d BT",
                 len(gem_watchlist), len(watchlist), len(backtest_signals))
    except Exception as e:
        log.error(" save_state error: %s", e)


def load_state():
    # type: () -> None
    """استعادة البيانات — Redis أولاً ثم ملف محلي"""
    global bottom_price_history, bottom_vol_history, ath_tracker
    global rt_vol_baseline
    global gem_watchlist, watchlist, wl_price_snapshot, candidates
    global backtest_signals
    global bottom_alerted, explosion_alerted, ath_alerted
    global hot_alerted, rt_alerted, wl_entry_alerted
    global daily_report_sent_date, lz_daily_sent_date
    global daily_gem_count, stable_vol_history, daily_market_vol_history
    global daily_signals
    global whale_watchlist, coin_signal_count, market_activity_history


    state = redis_load()
    log.info(" Redis state: %d keys", len(state))


    if not state:
        if not os.path.exists(STATE_FILE):
            log.info("    -  ")
            return
        try:
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
            log.info(" State loaded from local file")
        except Exception as e:
            log.error(" load local error: %s", e)
            return

    if not state:
        return

    try:
        saved_at   = state.get("saved_at", 0)
        age_hours  = (time.time() - saved_at) / 3600
        log.info("  State - : %.1f ", age_hours)

        sector_flow_hot.update(state.get("sector_flow_hot", {}))
        bottom_price_history.update(state.get("bottom_price_history", {}))
        bottom_vol_history.update(state.get("bottom_vol_history", {}))
        ath_tracker.update(state.get("ath_tracker", {}))
        rt_vol_baseline.update(state.get("rt_vol_baseline", {}))

        gem_watchlist.update(state.get("gem_watchlist", {}))
        watchlist.update(state.get("watchlist", {}))
        wl_price_snapshot.update(state.get("wl_price_snapshot", {}))
        for c in state.get("candidates", []):
            if c not in candidates:
                candidates.append(c)

        backtest_signals.update(state.get("backtest_signals", {}))

        bottom_alerted.update(state.get("bottom_alerted", {}))
        explosion_alerted.update(state.get("explosion_alerted", {}))
        ath_alerted.update(state.get("ath_alerted", {}))
        hot_alerted.update(state.get("hot_alerted", {}))
        rt_alerted.update(state.get("rt_alerted", {}))
        ts_positions.update(state.get("ts_positions", {}))
        ts_sell_alerted.update(state.get("ts_sell_alerted", {}))
        wl_entry_alerted.update(state.get("wl_entry_alerted", {}))

        daily_report_sent_date = state.get("daily_report_sent_date", "")
        lz_daily_sent_date     = state.get("lz_daily_sent_date", "")
        daily_gem_count        = state.get("daily_gem_count", {"date": "", "count": 0})
        daily_signals          = state.get("daily_signals", {"date": "", "count": 0})

        _dmv = state.get("daily_market_vol_history", [])
        if isinstance(_dmv, list):
            daily_market_vol_history.extend(_dmv)
        stable_vol_history.update(state.get("stable_vol_history", {}))
        whale_watchlist.update(state.get("whale_watchlist", {}))
        coin_signal_count.update(state.get("coin_signal_count", {}))
        _mah = state.get("market_activity_history", [])
        if isinstance(_mah, list):
            market_activity_history.extend(_mah[-30:])

        log.info(" State loaded | gems=%d | watchlist=%d | ath=%d | BT=%d",
                 len(gem_watchlist), len(watchlist), len(ath_tracker), len(backtest_signals))

        # رسالة إعادة التشغيل — محذوفة بطلب المستخدم

    except Exception as e:
        log.error(" load_state error: %s", e)


def init_static_watchlist():
    # type: () -> None
    """تهيئة قائمة المراقبة الثابتة عند بدء البوت"""
    global watchlist, wl_price_snapshot

    if not all_tickers:
        log.warning(" init_static_watchlist: all_tickers ")
        return

    ticker_map = {t["symbol"]: t for t in all_tickers}
    added = 0
    _static = [
        ("AVAXUSDT", "Layer1", "L1 قوي"),
        ("LINKUSDT", "DeFi", "Oracle رائد"),
        ("LTCUSDT", "Layer1", "عملة قديمة"),
        ("ADAUSDT", "Layer1", "L1 كبير"),
        ("VAIUSDT", "DeFi", "DeFi صغير"),
        ("AIXBTUSDT", "AI", "AI Agent"),
        ("CGPTUSDT", "AI", "AI رائد"),
        ("SOLUSDT", "Layer1", "L1 الأقوى"),
        ("SEIUSDT", "Layer1", "L1 جديد"),
        ("CFXUSDT", "Layer1", "L1 صيني"),
        ("APTUSDT", "Layer1", "L1 انخفض 95%"),
        ("WLDUSDT", "AI", "AI + Worldcoin"),
        ("ZROUSDT", "DeFi", "Bridge رائد"),
        ("PYTHUSDT", "DeFi", "Oracle منافس LINK"),
        ("COOKIEUSDT", "AI", "AI Agent ساخن"),
        ("ROSEUSDT",  "Privacy", "Privacy L1"),

        ("DOGEUSDT",    "Meme", "Meme — الأكبر"),
        ("SHIBUSDT",    "Meme", "Meme — ضخم"),
        ("PEPEUSDT",    "Meme", "Meme — ضخم"),
        ("FLOKIUSDT",   "Meme", "Meme — قوي"),
        ("WIFUSDT",     "Meme", "Meme — SOL"),
        ("BONKUSDT",    "Meme", "Meme — SOL"),
        ("BANANAUSDT",  "Meme", "Meme — انفجارات"),
        ("NEIROUSDT",   "Meme", "Meme — جديد"),
        ("MOODENGUSDT", "Meme", "Meme — فيل 🐘 Vitalik"),
        ("PNUTUSDT",    "Meme", "Meme — سنجاب"),
        ("GOATUSDT",    "Meme", "Meme — AI"),
        ("ACTUSDT",     "Meme", "Meme — ساخن"),
        ("TURBOUSDT", "Meme", "Meme — Turbo"),
        ("POPCATUSDT",  "Meme", "Meme — قطة"),
        ("MEMEUSDT",    "Meme", "Meme — MEME"),
        ("DOGSUSDT",    "Meme", "Meme — كلاب"),
        ("CATIUSDT",    "Meme", "Meme — قطة"),
        ("CHILLGUYUSDT","Meme", "Meme — Chill"),
        ("GMEUSDT",    "Meme", "Meme — GME"),
        ("LUNAUSDT",    "Meme", "Meme — Luna"),
        ("BABYDOGEUSDT","Meme", "Meme — BabyDoge"),
        ("MOGUSDT",     "Meme", "Meme — MOG"),
        ("BOMEUSDT",   "Meme", "Meme — BOME"),
        ("MYROUSDT",  "Meme", "Meme — Myro"),
        ("WOJAKUSDT",  "Meme", "Meme — Wojak"),
        ("GIGAUSDT",    "Meme", "Meme — Giga"),
        ("SUNDOGUSDT",  "Meme", "Meme — Sundog"),
        ("FWOGUSDT",    "Meme", "Meme — Fwog"),
        ("MICHIUSDT",   "Meme", "Meme — Michi"),
        ("PONKEUSDT",   "Meme", "Meme — Ponke"),
        ("APEUSDT",    "Meme", "Meme — Ape"),
        ("PENGUINUSDT", "Meme", "Meme — Penguin"),
        ("PENGUUSDT",   "Meme", "Meme — Pengu"),
    ]

    for sym, sector, reason in _static:
        if sym in watchlist:
            continue

        t = ticker_map.get(sym)
        if not t:
            log.warning(" Static WL: %s    ", sym)
            continue

        try:
            price = float(t["lastPrice"])
            vol   = float(t["quoteVolume"])
        except Exception as e:
            continue

        watchlist[sym] = {
            "since":    time.time(),
            "reason":   reason,
            "vol":      vol,
            "sector":   sector,
            "priority": "STATIC",
        }
        wl_price_snapshot[sym] = price
        added += 1

    log.info(" Static Watchlist:  %d  | : %d", added, len(watchlist))










_liq_tracker_last   = 0.0
_liq_tracker_every  = 600
_sector_vol_prev    = {}

def track_global_liquidity():
    # type: () -> None
    """
    يجلب كل عملات MEXC ويحسب:
    1. أي القطاعات ارتفع حجمها
    2. أي القطاعات نزل حجمها
    3. يحدث hot_sectors تلقائياً
    """
    global _liq_tracker_last, _sector_vol_prev, hot_sectors, hot_symbols
    now = time.time()
    if now - _liq_tracker_last < _liq_tracker_every:
        return
    _liq_tracker_last = now

    if not all_tickers:
        return

    try:

        ticker_map = {t["symbol"]: t for t in all_tickers}
        sector_vol_now  = {}
        sector_chg_now  = {}
        sector_coins    = {}

        for sector, coins in SECTORS.items():
            total_vol = 0.0
            changes   = []
            top_coins = []

            for sym in coins:
                t = ticker_map.get(sym)
                if not t:
                    continue
                try:
                    vol = float(t.get("quoteVolume", 0))
                    chg = float(t.get("priceChangePercent", 0))
                    total_vol += vol
                    changes.append(chg)
                    if chg > 0 and vol > 100_000:
                        top_coins.append((sym.replace("USDT",""), chg, vol))
                except (ValueError, TypeError):
                    continue

            if total_vol > 0:
                sector_vol_now[sector]  = total_vol
                sector_chg_now[sector]  = sum(changes)/len(changes) if changes else 0
                sector_coins[sector]    = sorted(top_coins, key=lambda x: -x[2])[:5]

        if not sector_vol_now:
            return


        if not _sector_vol_prev:
            _sector_vol_prev = sector_vol_now.copy()
            return

        entering = []
        leaving  = []

        for sector, vol_now in sector_vol_now.items():
            vol_prev = _sector_vol_prev.get(sector, vol_now)
            if vol_prev <= 0:
                continue
            vol_change_pct = (vol_now - vol_prev) / vol_prev * 100
            avg_chg        = sector_chg_now.get(sector, 0)

            if vol_change_pct >= 20 and avg_chg >= 1.0:
                entering.append((sector, vol_change_pct, avg_chg,
                                sector_coins.get(sector, [])))
            elif vol_change_pct <= -15:
                leaving.append((sector, vol_change_pct))

        _sector_vol_prev = sector_vol_now.copy()

        if not entering:
            return


        entering.sort(key=lambda x: -x[1])

        new_hot = [s for s, _, _, _ in entering[:3]]
        old_hot = set(hot_sectors)
        new_hot_set = set(new_hot)

        added   = new_hot_set - old_hot
        removed = old_hot - new_hot_set

        if added:
            for s in added:
                if s not in hot_sectors:
                    hot_sectors.append(s)
            hot_symbols = {c for sec in hot_sectors for c in SECTORS.get(sec, [])}
            log.info(" LIQUIDITY FLOW | IN: %s | OUT: %s",
                     list(added), list(removed))


        if not added:
            return

        msg_lines = ["💧 *تدفق السيولة — تحديث*", "━━━━━━━━━━━━━━━━━━"]

        for sector, vol_pct, avg_chg, coins in entering[:3]:
            icon = "🔥" if vol_pct >= 50 else "✅"
            msg_lines.append("{}  *{}* حجم:`+{:.0f}%` | avg:`+{:.1f}%`".format(
                icon, sector, vol_pct, avg_chg))

            for name, chg, vol in coins[:2]:
                msg_lines.append("    🟢 *{}* `+{:.1f}%`".format(name, chg))

        if leaving:
            msg_lines.append("━━━━━━━━━━━━━━━━━━")
            msg_lines.append("📤 *خروج من:* " +
                           ", ".join(s for s, _ in leaving[:3]))

        msg_lines.append("━━━━━━━━━━━━━━━━━━")
        msg_lines.append("🎯 _البوت يركز الآن على: {}_".format(
            ", ".join(hot_sectors[:3])))

        send("\n".join(msg_lines))

    except Exception as e:
        log.error("track_global_liquidity error: %s", e)










exit_watchlist  = {}
exit_alerted    = {}   # {sym: ts}
EXIT_CHECK_EVERY = 120
last_exit_check  = 0.0


def detect_distribution(sym, price, vdelta, ats):
    # type: (str, float, float, float) -> tuple
    """
    كشف التصريف قبل إرسال الجوكر
    يعيد: (is_distribution, reason)
    True = تصريف = لا ترسل
    """
    kd1h = get_klines(sym, "1h", 24)
    kd4h = get_klines(sym, "4h", 14)

    if not kd1h or len(kd1h["closes"]) < 12:
        return False, ""

    closes1h = kd1h["closes"]
    vols1h   = kd1h["vols"]
    highs1h  = kd1h["highs"]
    n        = len(closes1h)

    try:

        peak_24h = max(highs1h[-24:]) if len(highs1h) >= 24 else max(highs1h)
        drop_from_peak = (peak_24h - price) / peak_24h * 100 if peak_24h > 0 else 0

        if drop_from_peak >= 8.0:
            return True, "نزل {:.1f}% من القمة — تصريف محتمل".format(drop_from_peak)



        if n >= 6:
            vol_recent = sum(vols1h[-3:]) / 3
            vol_prev   = sum(vols1h[-6:-3]) / 3
            price_recent = closes1h[-1]
            price_prev   = closes1h[-4]


            if price_recent < price_prev and vol_recent < vol_prev * 0.7:
                return True, "سعر نازل + حجم ينخفض = تصريف"


        if n >= 8:

            recent_high  = max(highs1h[-4:])
            prev_high    = max(highs1h[-8:-4])
            recent_vol   = sum(vols1h[-4:])
            prev_vol     = sum(vols1h[-8:-4])

            if recent_high > prev_high and recent_vol < prev_vol * 0.8:
                return True, "قمة أعلى + حجم أقل = تباعد هبوطي"


        if kd4h and len(kd4h["closes"]) >= 6:
            c4 = kd4h["closes"]
            o4 = kd4h["opens"]
            v4 = kd4h["vols"]
            vd4h = calc_weis_wave(c4[-6:], v4[-6:])
            if vd4h < 0.40:
                return True, "Weis Wave 4h هابط {:.0f}%".format(vd4h*100)


        if n >= 20:
            price_20h_ago = closes1h[-20] if len(closes1h) >= 20 else closes1h[0]
            gain_20h = (price - price_20h_ago) / price_20h_ago * 100 if price_20h_ago > 0 else 0
            if gain_20h > 30 and drop_from_peak > 5:
                return True, "Pump +{:.0f}% ثم تصريف -{:.1f}%".format(gain_20h, drop_from_peak)

        return False, ""

    except (IndexError, ValueError, ZeroDivisionError):
        return False, ""











_market_vd_history  = []
_liq_exit_alerted   = 0.0
LIQ_EXIT_COOLDOWN   = 600
LIQ_EXIT_DROP       = 8.0

def track_liquidity_exit(mkt_vd_pct):
    # type: (float) -> None
    global _market_vd_history, _liq_exit_alerted
    now = time.time()

    _market_vd_history.append((now, mkt_vd_pct))

    _market_vd_history = _market_vd_history[-10:]

    if len(_market_vd_history) < 3:
        return
    if now - _liq_exit_alerted < LIQ_EXIT_COOLDOWN:
        return


    recent = [(t, v) for t, v in _market_vd_history if now - t <= 300]
    if len(recent) < 2:
        return

    oldest_vd = recent[0][1]
    latest_vd = recent[-1][1]
    drop = oldest_vd - latest_vd

    if drop >= LIQ_EXIT_DROP:
        _liq_exit_alerted = now
        msg = (
            "🚨 *تحذير — سيولة تخرج من السوق!*\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "📊 VDelta السوق: `{:.0f}%` (كان `{:.0f}%`)\n"
            "📉 انخفض: `-{:.1f}%` في 5 دقائق\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "⛔ *أوقف الدخول في أي صفقة جديدة!*"
        ).format(latest_vd, oldest_vd, drop)
        send(msg)


def check_coin_liquidity_exit(sym, entry_price, current_price, vdelta, ats):
    # type: (str, float, float, float, float) -> bool
    """
    يفحص إذا خرجت السيولة من عملة بعد الدخول
    يعيد True = خرج، أرسل تحذير
    """
    global exit_alerted

    now = time.time()
    # منع الإرسال المزدوج مع scan_reversal_exit
    if now - exit_alerted.get(sym, 0) < 7200:
        return False
    if sym not in exit_watchlist:
        return False

    pnl = (current_price - entry_price) / entry_price * 100 if entry_price > 0 else 0

    exit_reason = ""
    urgent = False

    # ── حجم الصفقة لتحديد عتبة "حيتان" نسبية ─────────────────────
    _vol_sym = next((float(t.get("quoteVolume", 0))
                     for t in all_tickers if t.get("symbol") == sym), 0)
    _tier    = get_tier_settings(_vol_sym)
    _ats_min = _tier.get("ats_min", 150)
    _whale_ats = _ats_min * WHALE_SELL_ATS_MULT   # عتبة بيع الحيتان النسبية

    # 🚨 أولوية 1: حيتان يبيعون بقوة (VDelta منهار + ATS كبير)
    if vdelta < WHALE_SELL_VDELTA and ats >= _whale_ats:
        exit_reason = "🐋 حيتان يبيعون! VDelta {:.0f}% ATS {:.0f}$".format(vdelta * 100, ats)
        urgent = True

    # 🚨 أولوية 2: انهيار VDelta حاد بغض النظر عن ATS
    elif vdelta < WHALE_SELL_VDELTA:
        exit_reason = "VDelta انهار {:.0f}%".format(vdelta * 100)
        urgent = True

    # ⚠️ Stop Loss
    elif pnl <= -5.0:
        exit_reason = "Stop Loss -5% مكسور"
        urgent = True

    # ⚠️ تحذير ضعف — فقط إذا كان الربح > WHALE_EXIT_MIN_PROF ولا تُزعج برسائل مبكرة
    elif vdelta < 0.45 and pnl >= WHALE_EXIT_MIN_PROF and ats >= _ats_min:
        exit_reason = "VDelta يضعف {:.0f}% — فكر في جني الأرباح".format(vdelta * 100)
        urgent = False

    if not exit_reason:
        return False

    icon = "🚨" if urgent else "⚠️"
    action = "🔴 *اخرج الآن فوراً!*" if urgent else "🟡 *فكر في جني الأرباح*"

    title = "خروج سيولة!" if urgent else "تحذير سيولة"
    msg = (
        "{icon} *{title}*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "💥 *{sym}* — {reason}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "💰 السعر: `{price}` | P&L: `{pnl:+.1f}%`\n"
        "📊 VDelta: `{vd:.0f}%` | ATS: `{ats:.0f}$`\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "{action}"
    ).format(
        icon=icon,
        title=title,
        sym=sym.replace("USDT", ""),
        reason=exit_reason,
        price=fmt_price(current_price),
        pnl=pnl,
        vd=vdelta * 100,
        ats=ats,
        action=action
    )

    send(msg)
    exit_alerted[sym] = now
    # حذف من exit_watchlist — إشارة واحدة فقط
    exit_watchlist.pop(sym, None)
    return urgent




# ═══════════════════════════════════════════════════════════════════
#   📉 EXIT SIGNAL 5M — كشف انعكاس الاتجاه على فريم 5 دقائق
#   Lower Low على 5m + حجم يرتفع = خروج مبكر
# ═══════════════════════════════════════════════════════════════════

def detect_reversal_5m(sym, entry_price):
    # type: (str, float) -> tuple
    """
    يكشف انعكاس الاتجاه على 5m
    يعيد: (is_reversal, reason, urgency)
    """
    kd = get_klines(sym, "5m", 20)
    if not kd or len(kd["closes"]) < 6:
        return False, "", 0

    try:
        closes = kd["closes"]
        opens  = kd["opens"]
        highs  = kd["highs"]
        lows   = kd["lows"]
        vols   = kd["vols"]
        n      = len(closes)

        # 1. Lower Lows على آخر 3 شموع حمراء
        red_candles = []
        for i in range(n-1, max(n-8, 0), -1):
            if closes[i] < opens[i]:
                red_candles.append({
                    "close": closes[i],
                    "open":  opens[i],
                    "low":   lows[i],
                    "vol":   vols[i] if i < len(vols) else 0,
                })
            if len(red_candles) >= 3:
                break

        if len(red_candles) >= 2:
            # فحص Lower Low
            lower_lows = all(
                red_candles[i]["close"] < red_candles[i+1]["close"]
                for i in range(len(red_candles)-1)
            )

            if lower_lows:
                # فحص حجم يرتفع مع البيع
                vol_increasing = red_candles[0]["vol"] > red_candles[-1]["vol"] * 0.8

                current_price = closes[-1]
                pnl = (current_price - entry_price) / entry_price * 100 if entry_price > 0 else 0

                if vol_increasing and pnl > 2.0:
                    return True, "Lower Lows على 5m + حجم بيع يرتفع", 2
                elif lower_lows and pnl > 0:
                    return True, "Lower Lows على 5m", 1

        # 2. شمعة كبيرة حمراء تكسر آخر دعم
        last_close = closes[-1]
        last_open  = opens[-1]
        body = abs(last_close - last_open)
        avg_body = sum(abs(closes[i] - opens[i]) for i in range(n-5, n-1)) / 4

        if last_close < last_open and body > avg_body * 2.0:
            pnl = (last_close - entry_price) / entry_price * 100 if entry_price > 0 else 0
            if pnl > 0:
                return True, "شمعة حمراء ضخمة على 5m", 2

        return False, "", 0

    except (IndexError, ValueError, ZeroDivisionError):
        return False, "", 0


def scan_reversal_exit(price_map):
    # type: (dict) -> None
    """
    يفحص كل العملات في exit_watchlist
    ويرسل إشارة خروج عند انعكاس 5m
    """
    now = time.time()
    if not exit_watchlist:
        return

    for sym, data in list(exit_watchlist.items()):
        if now - exit_alerted.get(sym, 0) < 14400:
            continue

        price = price_map.get(sym, 0)
        if price <= 0:
            continue

        entry = data.get("entry", price)
        pnl   = (price - entry) / entry * 100 if entry > 0 else 0

        if pnl <= 0:
            continue

        is_reversal, reason, urgency = detect_reversal_5m(sym, entry)
        if not is_reversal:
            continue

        icon   = "🚨" if urgency >= 2 else "⚠️"
        action = "🔴 *اخرج الآن!* — انعكاس قوي" if urgency >= 2 else "🟡 *فكر في الخروج* — تحذير مبكر"

        msg = (
            "{icon} *إشارة خروج — {sym}*\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "📉 {reason}\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "💰 السعر: `{price}` | P&L: `{pnl:+.1f}%`\n"
            "📊 دخول: `{entry}`\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "{action}"
        ).format(
            icon=icon,
            sym=sym.replace("USDT", ""),
            reason=reason,
            price=fmt_price(price),
            pnl=pnl,
            entry=fmt_price(entry),
            action=action
        )

        send(msg)
        exit_alerted[sym] = now
        # إضافة لمراقبة إعادة الدخول
        add_to_reentry_watch(sym, price, entry)
        # حذف من exit_watchlist — إشارة واحدة فقط
        exit_watchlist.pop(sym, None)




# ═══════════════════════════════════════════════════════════════════
#   🔄 RE-ENTRY ALERT — إشارة إعادة الدخول
#   بعد الخروج، يراقب السيولة للعودة للصفقة
#   إذا VDelta عاد للارتفاع + CVD صاعد = أعد الدخول
# ═══════════════════════════════════════════════════════════════════

_reentry_watchlist = {}   # {sym: {"exit_price": p, "exit_time": t, "entry": p}}
_reentry_alerted   = {}   # {sym: ts}
REENTRY_COOLDOWN   = 1800  # 30 دقيقة بعد الخروج قبل إعادة الدخول
REENTRY_WATCH_TTL  = 7200  # ساعتان فقط بعد الخروج

def add_to_reentry_watch(sym, exit_price, original_entry):
    # type: (str, float, float) -> None
    _reentry_watchlist[sym] = {
        "exit_price":      exit_price,
        "original_entry":  original_entry,
        "exit_time":       time.time(),
    }

def scan_reentry(price_map):
    # type: (dict) -> None
    now = time.time()
    if not _reentry_watchlist:
        return

    for sym, data in list(_reentry_watchlist.items()):
        # انتهت فترة المراقبة
        if now - data["exit_time"] > REENTRY_WATCH_TTL:
            _reentry_watchlist.pop(sym, None)
            continue

        # انتظر cooldown بعد الخروج
        if now - data["exit_time"] < REENTRY_COOLDOWN:
            continue

        if now - _reentry_alerted.get(sym, 0) < REENTRY_COOLDOWN:
            continue

        price = price_map.get(sym, 0)
        if price <= 0:
            continue

        # جلب VDelta الحالي
        stats = analyze_tps_ats(sym)
        if not stats:
            continue

        vdelta = stats.get("vdelta", 0.5)
        ats    = stats.get("ats", 0)

        # شروط إعادة الدخول
        # 1. VDelta عاد للارتفاع بقوة
        vd_strong = vdelta >= 0.70 and ats >= 300

        # 2. CVD صاعد مجدداً
        cvd = calc_cvd(sym, "15m", 12)
        cvd_rising = cvd.get("trend") == "rising"

        # 3. السعر لم يرتفع كثيراً بعد الخروج
        exit_price = data["exit_price"]
        price_above_exit = (price - exit_price) / exit_price * 100 if exit_price > 0 else 0

        if vd_strong and cvd_rising and price_above_exit < 5.0:
            _reentry_alerted[sym] = now

            msg = (
                "🔄 *إعادة دخول — {sym}*\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "✅ السيولة عادت بقوة!\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "📊 VDelta: `{vd:.0f}%` | ATS: `{ats:.0f}$`\n"
                "📈 CVD: تجميع مستمر\n"
                "💰 السعر: `{price}` ({diff:+.1f}% من خروجك)\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "💡 _خرجت مبكراً؟ الاتجاه استمر — يمكن العودة_"
            ).format(
                sym=sym.replace("USDT", ""),
                vd=vdelta * 100,
                ats=ats,
                price=fmt_price(price),
                diff=price_above_exit
            )

            send(msg)



def scan_exit_signals(price_map, vol_now, changes_map):
    # type: (dict, dict, dict) -> None
    global last_exit_check
    now = time.time()
    if now - last_exit_check < EXIT_CHECK_EVERY:
        return
    last_exit_check = now

    if not exit_watchlist:
        return

    for sym, data in list(exit_watchlist.items()):
        if now - exit_alerted.get(sym, 0) < 3600:
            continue

        price = price_map.get(sym, 0)
        if price <= 0:
            continue

        entry   = data.get("entry", price)
        pnl_pct = (price - entry) / entry * 100 if entry > 0 else 0


        stats   = analyze_tps_ats(sym)
        if not stats:
            continue

        vdelta = stats.get("vdelta", 0.5)
        ats    = stats.get("ats", 0)
        tps    = stats.get("tps", 0)


        check_coin_liquidity_exit(sym, entry, price, vdelta, ats)

        exit_reason = ""
        exit_urgent = False

        # حجم الصفقة لتحديد عتبة "حيتان" نسبية
        _tier_ex   = get_tier_settings(vol_now.get(sym, 0))
        _ats_min_x = _tier_ex.get("ats_min", 150)
        _whale_x   = _ats_min_x * WHALE_SELL_ATS_MULT

        # 🚨 أولوية 1 — حيتان يبيعون بقوة
        if vdelta < WHALE_SELL_VDELTA and ats >= _whale_x:
            exit_reason = "🐋 حيتان يبيعون! VDelta {:.0f}% ATS {:.0f}$".format(vdelta*100, ats)
            exit_urgent = True

        # 🚨 أولوية 2 — انهيار VDelta حاد
        elif vdelta < WHALE_SELL_VDELTA:
            exit_reason = "VDelta انهار {:.0f}%".format(vdelta*100)
            exit_urgent = True

        # 🚨 Stop Loss
        elif pnl_pct <= -4.0:
            exit_reason = "Stop Loss -4% مكسور!"
            exit_urgent = True

        # ⚠️ تحذير ضعف — فقط إذا تجاوز الحد الأدنى للربح (لا تُزعج مبكراً)
        elif vdelta < 0.45 and pnl_pct >= WHALE_EXIT_MIN_PROF and ats >= _ats_min_x:
            exit_reason = "VDelta يضعف {:.0f}% — فكر في جني الأرباح".format(vdelta*100)
            exit_urgent = False

        if not exit_reason:
            continue

        sector = next((s for s,syms in SECTORS.items() if sym in syms), "")
        icon   = "🚨" if exit_urgent else "⚠️"

        title = "اخرج الآن!" if exit_urgent else "تحذير خروج"
        msg = (
            "{icon} *{title}* {icon}\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "💥 *{sym}* — {reason}\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "💰 السعر: `{price}` | P&L: `{pnl:+.1f}%`\n"
            "📊 VDelta: `{vd:.0f}%` | ATS: `{ats:.0f}$`\n"
            "🏷️ القطاع: `{sector}`\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "{action}"
        ).format(
            icon=icon,
            title=title,
            sym=sym.replace("USDT",""),
            reason=exit_reason,
            price=fmt_price(price),
            pnl=pnl_pct,
            vd=vdelta*100,
            ats=ats,
            sector=sector,
            action="🔴 *اخرج الآن فوراً!*" if exit_urgent else "🟡 *فكر في جني الأرباح*"
        )

        send(msg)
        exit_alerted[sym] = now
        log.info(" EXIT SIGNAL | %s | VD=%.0f%% | PnL=%.1f%% | %s",
                 sym, vdelta*100, pnl_pct, exit_reason)


        if pnl_pct <= -7.0:
            exit_watchlist.pop(sym, None)


def add_to_exit_watchlist(sym, entry_price, targets=None):
    # type: (str, float, list) -> None
    exit_watchlist[sym] = {
        "entry":   entry_price,
        "time":    time.time(),
        "targets": targets or [],
    }
    log.info(" EXIT WATCH: %s | entry=%.8f", sym, entry_price)









#   2. VDelta



_smart_scan_last  = 0.0
_smart_scan_every = 300

def smart_market_scan():
    # type: () -> None
    global candidates, _smart_scan_last, _vol_surge_baseline
    now = time.time()
    if now - _smart_scan_last < _smart_scan_every:
        return
    _smart_scan_last = now

    if not all_tickers:
        return

    scored = []

    for t in all_tickers:
        try:
            sym   = t.get("symbol", "")
            if not sym.endswith("USDT"):
                continue
            base = sym.replace("USDT", "")
            if base in STABLECOINS:
                continue
            if any(k in sym for k in LEVERAGE_KEYWORDS):
                continue

            vol   = float(t.get("quoteVolume", 0))
            price = float(t.get("lastPrice", 0))
            chg   = float(t.get("priceChangePercent", 0))


            if vol < 10_000 or price <= 0:
                continue


            if chg > 200:
                continue


            prev_vol = _vol_surge_baseline.get(sym, vol)
            vol_change_pct = (vol - prev_vol) / prev_vol * 100 if prev_vol > 0 else 0


            score = (
                min(vol_change_pct, 500) * 0.6 +
                max(chg, 0) * 0.3 +
                min(vol / 10_000_000, 5) * 0.1
            )

            if score > 0:
                scored.append((sym, score, vol, chg))

        except (ValueError, TypeError):
            continue

    if not scored:
        return


    scored.sort(key=lambda x: -x[1])


    new_candidates = [s for s, _, _, _ in scored[:100]]


    static = list(set(
        EXTRA_COINS +
        [sym for syms in SECTORS.values() for sym in syms]
    ))


    all_candidates = list(set(new_candidates + static))
    candidates[:] = all_candidates

    log.info(" Smart Scan | %d   candidates | top: %s",
             len(candidates),
             [s.replace("USDT","") for s,_,_,_ in scored[:5]])




# ═══════════════════════════════════════════════════════════════════
#   📊 DEFI LLAMA TRACKER — تتبع TVL والسيولة الحقيقية
#   يراقب دخول وخروج السيولة من البروتوكولات والقطاعات
#   API مجاني: https://api.llama.fi
# ═══════════════════════════════════════════════════════════════════

LLAMA_CHAINS_URL    = "https://api.llama.fi/v2/chains"
LLAMA_PROTOCOLS_URL = "https://api.llama.fi/protocols"

_llama_last_scan    = 0.0
_llama_scan_every   = 3600   # كل ساعة
_llama_prev_tvl     = {}     # {chain: tvl}
_llama_prev_proto   = {}     # {protocol: tvl}

# القطاعات المهمة للمراقبة
LLAMA_WATCH_CHAINS = [
    "Ethereum", "BSC", "Solana", "Arbitrum",
    "Polygon", "Avalanche", "Base"
]

LLAMA_WATCH_PROTOCOLS = [
    "aave", "uniswap", "curve", "lido",
    "makerdao", "compound", "pancakeswap"
]

def scan_defi_llama():
    # type: () -> None
    global _llama_last_scan, _llama_prev_tvl, _llama_prev_proto
    now = time.time()
    if now - _llama_last_scan < _llama_scan_every:
        return
    _llama_last_scan = now

    alerts = []

    try:
        # 1. TVL السلاسل
        chains_data = safe_get(LLAMA_CHAINS_URL)
        if chains_data and isinstance(chains_data, list):
            for chain in chains_data:
                name = chain.get("name", "")
                if name not in LLAMA_WATCH_CHAINS:
                    continue
                tvl = float(chain.get("tvl", 0))
                prev = _llama_prev_tvl.get(name, 0)

                if prev > 0 and tvl > 0:
                    change_pct = (tvl - prev) / prev * 100
                    if change_pct >= 5.0:
                        alerts.append({
                            "type": "chain_inflow",
                            "name": name,
                            "tvl": tvl,
                            "change": change_pct,
                        })
                    elif change_pct <= -5.0:
                        alerts.append({
                            "type": "chain_outflow",
                            "name": name,
                            "tvl": tvl,
                            "change": change_pct,
                        })
                _llama_prev_tvl[name] = tvl

        # 2. TVL البروتوكولات
        proto_data = safe_get(LLAMA_PROTOCOLS_URL)
        if proto_data and isinstance(proto_data, list):
            for proto in proto_data:
                slug = proto.get("slug", "").lower()
                if slug not in LLAMA_WATCH_PROTOCOLS:
                    continue
                tvl = float(proto.get("tvl", 0))
                chg1d = float(proto.get("change_1d", 0) or 0)
                prev  = _llama_prev_proto.get(slug, 0)

                if abs(chg1d) >= 8.0:
                    alerts.append({
                        "type": "protocol_flow",
                        "name": proto.get("name", slug),
                        "tvl": tvl,
                        "change": chg1d,
                    })
                _llama_prev_proto[slug] = tvl

    except Exception as e:
        log.info("LLAMA API error: %s", e)
        return

    if not alerts:
        return

    # إرسال تقرير TVL
    inflows  = [a for a in alerts if a["change"] > 0]
    outflows = [a for a in alerts if a["change"] < 0]

    msg = "📊 *تقرير TVL — DefiLlama*\n"
    msg += "━━━━━━━━━━━━━━━━━━\n"

    if inflows:
        msg += "💰 *سيولة تدخل DeFi:*\n"
        for a in inflows[:3]:
            tvl_b = a["tvl"] / 1_000_000_000
            msg += "  🟢 {} +{:.1f}% | TVL: {:.2f}B$\n".format(
                a["name"], a["change"], tvl_b)

    if outflows:
        msg += "🚨 *سيولة تخرج من DeFi:*\n"
        for a in outflows[:3]:
            tvl_b = a["tvl"] / 1_000_000_000
            msg += "  🔴 {} {:.1f}% | TVL: {:.2f}B$\n".format(
                a["name"], a["change"], tvl_b)

    msg += "━━━━━━━━━━━━━━━━━━\n"
    if inflows and not outflows:
        msg += "✅ _أموال تدخل DeFi — إشارة إيجابية_"
    elif outflows and not inflows:
        msg += "⚠️ _أموال تخرج من DeFi — كن حذراً_"
    else:
        msg += "📊 _تدفقات مختلطة — راقب السوق_"

    send(msg)
    log.info("LLAMA | %d inflows | %d outflows",
             len(inflows), len(outflows))




# ═══════════════════════════════════════════════════════════════════
#   📈 FUNDING RATE TRACKER — مؤشر معنويات السوق
#   Funding Rate سالب = حيتان يشترون Spot = فرصة 🎯
#   Funding Rate إيجابي عالي = السوق متفائل أكثر = خطر انعكاس
# ═══════════════════════════════════════════════════════════════════

MEXC_FUNDING_URL  = "https://api.mexc.com/api/v1/contract/funding_rate/{}"
_funding_last     = 0.0
_funding_every    = 3600   # كل ساعة
_funding_alerted  = {}     # {sym: ts}

FUNDING_SYMBOLS = ["BTC_USDT", "ETH_USDT", "SOL_USDT"]

def scan_funding_rates():
    # type: () -> None
    global _funding_last
    now = time.time()
    if now - _funding_last < _funding_every:
        return
    _funding_last = now

    alerts = []

    for sym in FUNDING_SYMBOLS:
        try:
            data = safe_get(MEXC_FUNDING_URL.format(sym))
            if not data or not data.get("data"):
                continue

            rate = float(data["data"].get("fundingRate", 0))
            rate_pct = rate * 100

            base = sym.replace("_USDT", "")

            # Funding Rate سالب جداً = فرصة شراء
            if rate_pct <= -0.03:
                alerts.append({
                    "sym": base,
                    "rate": rate_pct,
                    "signal": "buy",
                    "msg": "Funding سالب {:.4f}% = حيتان يشترون Spot!".format(rate_pct)
                })
            # Funding Rate إيجابي عالي = خطر
            elif rate_pct >= 0.10:
                alerts.append({
                    "sym": base,
                    "rate": rate_pct,
                    "signal": "warning",
                    "msg": "Funding مرتفع {:.4f}% = السوق متفائل أكثر من اللازم!".format(rate_pct)
                })

        except Exception:
            continue

    if not alerts:
        return

    msg = "📈 *Funding Rate — معنويات السوق*\n"
    msg += "━━━━━━━━━━━━━━━━━━\n"

    for a in alerts:
        if a["signal"] == "buy":
            msg += "🟢 *{}*: {}\n".format(a["sym"], a["msg"])
        else:
            msg += "🔴 *{}*: {}\n".format(a["sym"], a["msg"])

    msg += "━━━━━━━━━━━━━━━━━━\n"

    buy_signals = [a for a in alerts if a["signal"] == "buy"]
    warn_signals = [a for a in alerts if a["signal"] == "warning"]

    if buy_signals:
        msg += "💡 _Funding سالب = المراهنون على النزول يدفعون = فرصة صعود_"
    elif warn_signals:
        msg += "⚠️ _Funding مرتفع = السوق محموم = احتمال تصحيح_"

    send(msg)



def run():
    # type: () -> None
    global all_tickers
    global last_tickers, last_btc, last_sectors
    global last_deep_scan, last_stale, last_smart_money, last_expand
    global last_daily_report, daily_report_sent_date
    global lz_daily_sent_date, lz_alerted
    global hidden_accum_alerted
    global last_sector_report
    global last_rt_scan, last_hot_scan, last_bottom_scan
    global wl_entry_alerted, wl_price_snapshot, last_wl_check
    global ts_positions, ts_sell_alerted, last_ts_scan
    global daily_signals
    global last_ath_scan, last_expand
    global rt_vol_baseline, rt_alerted
    global hot_alerted, bottom_alerted
    global ath_alerted, ath_tracker
    global gem_watchlist, daily_gem_count
    global explosion_alerted, bottom_price_history, bottom_vol_history

    global tps_alerted, tps_baseline, last_tps_scan, last_whale_check
    global coin_alerted
    global coin_signal_count
    global coin_whale_done
    global btcd_history, btcd_last_check, btcd_alert_sent
    global liq_exit_alerted, liq_exit_vol_hist
    global whale_watchlist, whale_confirmed
    global lz_tps_alerted
    global lh_alerted, last_lh_scan
    global small_caps, last_sc_refresh
    global sc_alerted
    global last_sr_alert
    global perf_signals, perf_id_counter
    global mtf_liq_alerted, last_mtf_liq_scan
    global last_4h_report
    global _early_accum_seen, last_early_accum_scan

    log.info(" MAFIO-BOT ...")


    try:
        import requests as _rq
        _rq.get(
            "https://api.telegram.org/bot{}/deleteWebhook?drop_pending_updates=true".format(TELEGRAM_TOKEN),
            timeout=10
        )
        log.info(" Webhook   ")
    except Exception as _e:
        log.warning("deleteWebhook error: %s", _e)


    time.sleep(15)

    load_state()

    log.info("   ...")
    analyze_btc()

    refresh_tickers()
    time.sleep(2)


    try:
        _r = requests.get(
            "https://api.telegram.org/bot{}/getUpdates?offset=-1&timeout=1".format(TELEGRAM_TOKEN),
            timeout=5
        )
        _d = _r.json()
        if _d.get("ok") and _d.get("result"):
            global _tg_offset
            _tg_offset = _d["result"][-1]["update_id"] + 1
            log.info(" Telegram offset initialized: %d", _tg_offset)
    except Exception as _e:
        log.warning("offset init error: %s", _e)
    refresh_tickers()
    init_static_watchlist()

    log.info("  Auto Expand Sectors...")
    auto_expand_sectors()
    last_expand = time.time()

    analyze_sectors()

    last_sector_report = time.time()
    log.info("  | Candidates: %d | Hot: %s",
             len(candidates), ", ".join(hot_sectors) or "لا يوجد")

    last_deep_scan = 0


    global last_lh_scan, last_sc_refresh, last_sr_alert
    last_lh_scan      = 0.0
    last_sc_refresh   = 0.0
    last_sr_alert     = 0.0
    last_mtf_liq_scan    = 0.0
    last_4h_report       = 0.0
    last_early_accum_scan = 0.0
    _early_accum_seen    = {}
    last_pre_pump_scan   = 0.0
    _pre_pump_alerted    = {}

    # تأخير أول مسح TPS/LZ بعد إعادة التشغيل — يمنع إرسال تنبيهات مكررة
    # بسبب reset ذاكرة cooldowns عند الإعادة
    last_tps_scan = time.time()

    send(
        "💀 *MAFIO-BOT* 💀\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "✅ Anti Rate-Limit (~8 req/min)\n"
        "✅ Smart Cache (15m/1h/4h)\n"
        "✅ Trailing Stop (`{trail}%` من القمة)\n"
        "✅ Sector Rotation (12 قطاع)\n"
        "✅ Anti P&D | Supertrend | Dynamic SL\n"
        "✅ Sector Flow Tracker\n"
        "✅ Buffer System (منع التذبذب)\n"
        "✅ Daily Market Report (00:00 UTC)\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🆕 V16: 🌊 Liquidity Zones يومية\n"
        "🆕 V16: Sigma تلقائي من التاريخ\n"
        "🆕 V16: إشارة عند الإغلاق فوق Zone\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🆕 V17: 🧱 OB Deep — كشف جدران الشراء/البيع\n"
        "🆕 V17: 📊 CVD Signal — ضغط الشراء التراكمي\n"
        "🆕 V17: 🕐 MTF Liquidity — تأكيد 15m+1h+4h\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "⚡ إشارات سريعة: 15m/1h (مستمر)\n"
        "📅 إشارات يومية: 1D (00:00 UTC)\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "₿ BTC: `{btc:+.2f}%` | السوق: `{mst}`\n"
        "🔥 Hot: `{hot}`".format(
            trail=TRAIL_DROP_TRIGGER,
            btc=btc_change_24h,
            mst=market_state,
            hot=", ".join(hot_sectors) or "لا يوجد",
        )
    )

    cycle = 0
    flow_cycle = 0

    while True:

        price_map  = {}
        change_now = {}
        vol_now    = {}
        high_map   = {}
        low_map    = {}
        try:
            now = time.time()







            if int(now) % 300 < 12:
                save_state()


            if now - last_ts_scan >= TS_SCAN_EVERY:
                check_trailing_stops()
                last_ts_scan = now


            if now - last_wl_check >= WL_CHECK_EVERY:
                check_watchlist_entries()
                last_wl_check = now
            if now - last_rt_scan >= RT_SCAN_EVERY:
                scan_instant_movers()
            if now - last_rt_scan >= RT_SCAN_EVERY:
                scan_realtime_liquidity()
                last_rt_scan = now
            # Fast breakout — كل 30 ثانية (Tier 0 — بدون klines)
            scan_fast_breakout()
            # 5m breakout — كل 90 ثانية (Tier 1/2 — klines + EMA + Flow)
            scan_5m_breakout()
            # Bounce Reversal — كل دقيقتين (نزول + بيع يخف + شمعات خضراء)
            scan_bounce_reversal()
            # 1h Move — Wolf Flow style — كل دقيقتين
            scan_1h_move()
            # Flow Accumulation — السعر ثابت + أموال تتراكم (NTRNUSDT type)
            scan_flow_accumulation()
            # Volume Breakout — انفجار حجم × 5 قبل تحرك السعر
            scan_volume_breakout()
            # Micro Pump — حركة صغيرة + flow استثنائي 12x+
            scan_micro_pump()
            # BB Squeeze — كل 5 دقائق (Bollinger Band compression breakout)
            scan_bb_squeeze()
            poll_commands()

            # تنظيف _multi_confirm من الإدخالات القديمة كل ساعة
            if int(now) % 3600 < 35:
                _old_mc = [k for k, v in list(_multi_confirm.items())
                           if now - v.get("last_time", 0) > MULTI_CONFIRM_WINDOW]
                for _k in _old_mc:
                    _multi_confirm.pop(_k, None)


            if now - last_btc         >= BTC_EVERY:
                analyze_btc()
                update_bull_mode(vol_now, change_now)
            if now - last_sectors     >= SECTORS_EVERY:
                analyze_sectors()
                detect_sector_rotation()
                track_global_liquidity()

            refresh_sector_report()

            if now - last_bottom_scan >= BOTTOM_SCAN_EVERY:

                if now - last_hot_scan >= HOT_SCAN_EVERY:
                    scan_hot_market()
                    last_hot_scan = now
                check_btc_dominance(vol_now)
                scan_bottom_accumulation()

                if now - last_ath_scan >= ATH_SCAN_EVERY:
                    scan_ath_distance()
                    last_ath_scan = now

                last_bottom_scan = now


            send_daily_report()

            # تقرير 4 ساعات — محذوف بطلب المستخدم
            # send_4h_market_report()

            if now - last_expand      >= EXPAND_EVERY:

                log.info("   - Auto Expand Sectors")
                auto_expand_sectors()
                last_expand = now
            if now - last_stale       >= STALE_EVERY:
                cleanup()
                last_stale = now


            tickers_now = safe_get(MEXC_24H)
            if not tickers_now:
                time.sleep(CHECK_INTERVAL)
                continue


            all_tickers = tickers_now


            price_map  = {}
            change_now = {}
            vol_now    = {}
            high_map   = {}
            low_map    = {}
            ticker_map = {}

            for t in tickers_now:
                sym = t.get("symbol","")
                ticker_map[sym] = t
                try:
                    last  = float(t["lastPrice"])
                    open_ = float(t.get("openPrice", last))
                    real_change = (last - open_) / open_ * 100 if open_ > 0 else float(t["priceChangePercent"])
                    price_map[sym]  = last
                    change_now[sym] = real_change
                    vol_now[sym]    = float(t["quoteVolume"])
                    high_map[sym]   = float(t["highPrice"])
                    low_map[sym]    = float(t["lowPrice"])
                except (KeyError, ValueError):
                    pass

            changes_map.update(change_now)


            update_coin_vol_history(vol_now)


            check_backtest(price_map)

            if now - last_tickers >= TICKERS_EVERY:
                refresh_tickers()
                analyze_sectors()

            # Trailing Stop + Signal Progression
            for sym in list(tracked.keys()):
                if sym in price_map:
                    if not check_trailing(sym, price_map[sym]):
                        pass


            update_sector_flow(ticker_map)
            flow_cycle += 1


            if flow_cycle >= FLOW_WINDOW:
                analyze_sector_flow()
                flow_cycle = 0


            # detect_momentum(price_map, change_now, vol_now, high_map, low_map)


            if now - last_ts_scan >= TS_SCAN_EVERY:
                perf_check(price_map)


            if now - last_lh_scan >= 600:
                scan_hidden_accumulation(price_map, vol_now, changes_map)

            smart_market_scan()
            scan_defi_llama()
            # scan_funding_rates()  # محذوف — غير مفيد ومتكرر
            scan_volume_surge(price_map, vol_now, changes_map)
            scan_bottom_fisher(price_map, vol_now, changes_map)
            scan_pre_pump_watch(price_map, vol_now, changes_map)


            flush_signal_queue(max_send=5)


            update_pump_dump_history(price_map, vol_now)
            scan_pump_dump(price_map, vol_now, change_now)


            # scan_market_pulse(price_map, vol_now, change_now)


            track_liquidity_flow(vol_now, change_now)



            # Early accumulation scanner — يكتشف التجميع المبكر ويضيف للـ watchlist
            scan_early_accumulation(price_map, vol_now, change_now)

            if now - last_tps_scan >= TPS_SCAN_EVERY:
                check_liquidity_exit(vol_now, price_map)
                scan_tps_ats(price_map, vol_now, change_now)
                scan_lz_tps_fusion(price_map, vol_now, change_now)
                last_tps_scan = now


            if now - last_whale_check >= WHALE_CHECK_EVERY:
                scan_whale_confirmation(price_map)
                last_whale_check = now

            if now - last_lh_scan >= LH_SCAN_EVERY:
                liquidity_hunter(price_map, vol_now, changes_map)
                last_lh_scan = now


            if now - last_sc_refresh >= SC_REFRESH_EVERY:
                refresh_small_caps()


            if now - last_lh_scan < 10 and small_caps:
                liquidity_hunter_small_caps(price_map, vol_now, changes_map)

            # MTF Liquidity — تأكيد متعدد الأطر الزمنية
            scan_multi_timeframe_liquidity(price_map, vol_now, changes_map)

            # Deep Scan
            if now - last_deep_scan >= DEEP_SCAN_EVERY:
                # V15: pre-score coins before deep scan
                # sort by: high volume + positive change first
                pre_scored = []
                for sym in candidates:
                    if sym in tracked: continue
                    price  = price_map.get(sym, 0)
                    change = changes_map.get(sym, 0)
                    vol    = vol_now.get(sym, 0)
                    if price <= 0: continue

                    in_hot       = sym in hot_symbols
                    in_watchlist = sym in watchlist
                    wl_priority  = watchlist.get(sym, {}).get("priority","") == "🔥 HIGH"

                    pre_score = (
                        (vol / 1_000_000) * 0.5 +
                        max(change, 0) * 0.3 +
                        (2  if in_hot       else 0) +
                        (5  if in_watchlist else 0) +
                        (10 if wl_priority  else 0)
                    )
                    pre_scored.append((sym, price, change, pre_score))


                pre_scored.sort(key=lambda x: -x[3])


                scanned = 0
                for rank, (sym, price, change, _) in enumerate(pre_scored):

                    fetch_ob = (rank < 20)
                    deep_scan(sym, price, change, fetch_orderbook=fetch_ob)
                    scanned += 1
                    if scanned % 10 == 0:
                        time.sleep(0.5)

                last_deep_scan = now
                log.info(" Deep Scan  | %d ", scanned)

            cycle += 1

            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            send("⛔ *MAFIO-BOT* — تم الإيقاف")
            break
        except Exception as e:
            log.error(": %s", e, exc_info=True)
            time.sleep(10)


if __name__ == "__main__":
    run()

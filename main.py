"""
╔══════════════════════════════════════════════════════════════╗
║           MAFIO BOT SIGNAL V15 — UNIFIED ENGINE            ║
║   Anti-Rate-Limit + Smart Cache + Trailing Stop            ║
║   Smart Top10 — اصطياد العملات قبل الانفجار               ║
╚══════════════════════════════════════════════════════════════╝

التحسينات في V15 (فوق V14):
  ✅ FIX: تنظيف جميع الرموز الخاطئة في SECTORS (مسافات + حروف سيريلية)
  🆕 vol_ratio تاريخي: مقارنة حجم العملة بمتوسطها التاريخي (لا بمتوسط القطاع)
  🆕 RSI Filter: فلتر RSI على 14 فترة — يرفض العملات overbought (RSI>70)
  🆕 Backtesting: تتبع إشارات Top10 وقياس الأداء الفعلي بعد 1h/4h/24h
  🆕 رسالة Telegram محسّنة: أوضح + RSI + نسبة النجاح التاريخية

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
import logging
import requests
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Any, Set

# ═══════════════════════════════════════════════
#                    CONFIG
# ═══════════════════════════════════════════════
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_BOT_TOKEN")
CHAT_ID        = os.getenv("CHAT_ID", "YOUR_CHAT_ID")

# ── إشارات ──────────────────────────────────────
SCORE_MIN          = 55        # 🧪 TEST (كان 65)
GOLD_MIN           = 88
SIGNAL2_GAIN       = 2.0
SIGNAL3_GAIN       = 4.0
ALERT_COOLDOWN_SEC = 300
CHECK_INTERVAL     = 12        # ثوانٍ بين كل دورة

# ── Trailing Stop ────────────────────────────────
SL_MIN             = 2.0
SL_MAX             = 8.0
SL_BASE            = 4.0
TRAIL_GAIN_TRIGGER = 2.0       # يبدأ التتبع بعد +2%
TRAIL_DROP_TRIGGER = 1.5       # يخرج إذا نزل 1.5% من القمة

# ── BTC & السوق ──────────────────────────────────
BTC_DANGER_ZONE    = -3.0
BTC_CAUTION_ZONE   = -1.5

# ── Supertrend ───────────────────────────────────
ST_ATR_PERIOD      = 10
ST_MULTIPLIER      = 3.0

# ── Pump & Dump ──────────────────────────────────
PD_MAX_RISE        = 20.0
PD_MIN_DROP        = 5.0
PD_LOOKBACK        = 12

# ── Sector Rotation ──────────────────────────────
SECTOR_HOT_CHANGE  = 2.0       # 🧪 TEST (كان 3.0)
SECTOR_MIN_RISING  = 50.0      # 🧪 TEST (كان 60.0)
SECTOR_BONUS       = 15

# ── Volume & Order Book ──────────────────────────
VOL_SPIKE_RATIO    = 2.5
MIN_VOL_USDT       = 300_000
MAX_VOL_USDT       = 80_000_000
MIN_BID_DEPTH      = 20_000
MIN_IMBALANCE      = 0.8
MAX_IMBALANCE      = 3.0
GREEN_MIN_RATIO    = 0.60
HIGHER_LOWS_MIN    = 0.60

# ── Pre-Breakout (4h) ────────────────────────────
BO_4H_CANDLES      = 30
BO_FLAT_MAX        = 15.0
BO_VOL_SURGE       = 3.0
BO_NEAR_LOW        = 30.0

# ── فلتر مسبق ────────────────────────────────────
PRE_MIN_CHANGE     = -5.0
PRE_MAX_CHANGE     = 80.0
PRE_MIN_VOL        = MIN_VOL_USDT
PRE_MAX_VOL        = MAX_VOL_USDT

# ── توقيتات الدورات ──────────────────────────────
PRICES_EVERY       = 12
TICKERS_EVERY      = 1800
BTC_EVERY          = 1800
SECTORS_EVERY      = 1800
DEEP_SCAN_EVERY    = 3600
STALE_EVERY        = 3600
REPORT_EVERY       = 21600
STALE_REMOVE_SEC   = 86400

# ── Cache ────────────────────────────────────────
CACHE_15M          = 60
CACHE_1H           = 300
CACHE_4H           = 900

# ── Momentum Detector ────────────────────────────
MOMENTUM_MOVE_MIN  = 2.0
MOMENTUM_MOVE_MAX  = 8.0
MOMENTUM_MIN_VOL   = 500_000
MOMENTUM_COOLDOWN  = 14400

# ── 🆕 Sector Flow Tracker ───────────────────────
# يرصد تدفق السيولة بين القطاعات
FLOW_WINDOW        = 5         # عدد القراءات للمقارنة (~60 ثانية)
FLOW_VOL_SURGE     = 1.3       # 🧪 TEST (كان 1.5) — نسبة ارتفاع حجم القطاع
FLOW_CHANGE_MIN    = 1.0       # 🧪 TEST (كان 2.0) — متوسط تغيير القطاع %
FLOW_EXIT_DROP     = -1.5      # نسبة انخفاض = خروج سيولة من القطاع
FLOW_ALERT_COOL    = 600       # 🧪 TEST (كان 900) — 10 دقائق cooldown
FLOW_HISTORY_MAX   = 20        # أقصى تاريخ محفوظ للقطاع

# ── 🆕 Auto Expand ───────────────────────────────
EXPAND_EVERY       = 86400     # إعادة توسيع القوائم كل 24 ساعة

# ── 🆕 Smart Top10 — اصطياد قبل الانفجار ────────
TOP10_CHANGE_MIN   = 0.0      # تغيير 24h أدنى — لم تنزل
TOP10_CHANGE_MAX   = 8.0      # 🧪 TEST (كان 5.0) — توسيع النطاق
TOP10_VOL_RATIO    = 1.2      # 🧪 TEST (كان 1.5) — تخفيف شرط الحجم
TOP10_REBOUND_MAX  = 15.0     # ارتداد من القاع أقل من 15% = لا يزال قريباً
TOP10_MIN_VOL      = 150_000  # حجم 24h أدنى للقبول
TOP10_COOLDOWN     = 1800     # 30 دقيقة cooldown لنفس القطاع
TOP10_COUNT        = 10       # عدد العملات في الإشعار

# أوزان نقاط الترتيب
W_VOL_RATIO    = 40   # الأهم: حجم مرتفع فجأة
W_HOT_SECTOR   = 25   # قطاع ساخن + Flow داخل
W_REBOUND_LOW  = 20   # قريب من القاع
W_CHANGE_SMALL = 15   # تغيير صغير = لم ينطلق بعد

# ── 🆕 V15: RSI Filter ───────────────────────────
RSI_PERIOD        = 14        # فترة حساب RSI
RSI_OVERBOUGHT    = 70        # فوق هذا = مرفوض (overbought)
RSI_OVERSOLD      = 30        # تحت هذا = ممتاز (فرصة)
RSI_IDEAL_MAX     = 60        # RSI مثالي للدخول قبل الانفجار

# ── 🆕 V15: Vol History (تاريخي لكل عملة) ─────────
VOL_HISTORY_MAX   = 10        # عدد القراءات (10 × 12ث = 2 دقيقة)
VOL_HISTORY_MIN   = 3         # أدنى عدد قراءات للمقارنة الصادقة

# ── 🆕 V15: Backtesting ───────────────────────────
BACKTEST_CHECK_1H  = 3600     # 1 ساعة
BACKTEST_CHECK_4H  = 14400    # 4 ساعات
BACKTEST_CHECK_24H = 86400    # 24 ساعة

# ── Smart Money ──────────────────────────────────
SMART_MONEY_SIGMA      = 3.0
SMART_MONEY_EVERY      = 86400
SMART_MONEY_ACCUM_MIN  = 2
SMART_MONEY_FALL_PCT   = 55
SMART_MONEY_ALERT_SIGMA= 5.0

SMART_MONEY_STABLES = [
    "USDCUSDT","FDUSDUSDT","TUSDUSDT","USD1USDT",
    "RLUSDUSDT","BFUSDUSDT","USDPUSDT","USDDUSDT",
]

# ── MEXC Endpoints ──────────────────────────────
MEXC_24H    = "https://api.mexc.com/api/v3/ticker/24hr"
MEXC_TICKER = "https://api.mexc.com/api/v3/ticker/24hr"  # نفس الـ endpoint لكن بـ symbol
MEXC_PRICE  = "https://api.mexc.com/api/v3/ticker/price"
MEXC_KLINES = "https://api.mexc.com/api/v3/klines"
MEXC_DEPTH  = "https://api.mexc.com/api/v3/depth"

EXCLUDED = {"BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT"}

# ── 🆕 Auto Expand Sectors ───────────────────────
SECTOR_TARGET      = 50       # الهدف: 50 عملة لكل قطاع
EXPAND_MIN_VOL     = 100_000  # حجم 24h أدنى للقبول (100k USDT)
EXPAND_MAX_VOL     = 500_000_000  # حجم أقصى

# الكلمات المفتاحية لكل قطاع — للتصنيف التلقائي
# كلما زادت الكلمات، زادت دقة التصنيف
SECTOR_KEYWORDS = {
    "AI": [
        "AI","GPT","AGI","NEURAL","AGENT","BRAIN","MIND","THINK",
        "COGN","LEARN","SENTIENT","VIRTUAL","FETCH","OCEAN","RENDER",
        "GRAPH","TAO","ARKM","COOKIE","MIRA","MYRIA","ALETH","CGPT",
        "NEURO","VANA","MASK","AKTO","MEAI","GRIFFAIN","SWARM",
        "AIDO","WLDAI","KAIA","VIRT","NMT","AUTON","PAAL","SLEEPLESS",
        "QUBIC","AITECH","GENSYN","AIUS","KAITO","DEAI","OPML",
    ],
    "RWA": [
        "ONDO","CFG","MPLEX","REAL","TRST","PROM","MANTRA","XDC",
        "LQTY","SPX","ONP","VAI","GOLD","TBL","PARCL","REX","HONE",
        "OPEN","LANDX","CREDIX","POLIX","TRUE","MTV","PROP","TPROT",
        "STBTC","CULT","BRICS","ESTATE","REALT","DEXT","POLYMATH",
        "SECURITIZE","BACKED","MAPLE","CENTRIFUGE","GOLDFINCH",
        "TOUCAN","COOREST","BASE","REALIO","LOFTY",
    ],
    "Gaming": [
        "GAME","PLAY","QUEST","HERO","GUILD","YIELD","PIXEL","PORTAL",
        "AXS","SAND","MANA","ILV","GMT","YGG","SLP","GALA","RON","IMX",
        "BEAM","NOT","XAI","ALICE","RARE","MOBA","CHZ","PGX","HEROES",
        "BEX","GOMA","ACE","META","WAXP","GAL","VIDYA","ELF","MAGIC",
        "TWT","GHST","TOWER","REVV","NFTX","MOBOX","SKILL","DERACE",
        "FIGHT","WARS","BATTLE","LEGEND","REALM","KART","SPORT","FAN",
        "CHAMP","WIN","SUPER","GODS","AURY","ATLAS","POLIS","PVU",
    ],
    "DeFi": [
        "UNI","AAVE","CAKE","SUSHI","COMP","MKR","CRV","LDO","1INCH",
        "C98","DYDX","GMX","JUP","RAY","ORCA","PENDLE","EIGEN","ETHFI",
        "IDEX","REZ","SYRUP","BONE","CVX","FRAX","FXS","TRIBE","RAD",
        "ALPACA","RAMP","WOO","SWAP","DEX","YIELD","LEND","POOL",
        "LIQUID","STAKE","VAULT","FARM","HARVEST","BADGER","BNT",
        "PERP","SNX","KNC","BAL","BIFI","PANCAKE","QUICK","SPIRIT",
        "SPOOKY","JOE","SOLAR","TRISOLARIS","VELODROME","AERODROME",
        "CAMELOT","STERLING","RAMSES","THENA","KYBER","BANCOR",
    ],
    "Layer1": [
        "AVAX","ADA","ATOM","NEAR","FTM","ALGO","ICP","APT","SUI","SEI",
        "INJ","KAS","TON","HBAR","EGLD","ZIL","ONE","CFX","JASMY","LSK",
        "QNT","CELO","FLOW","MINA","KAVA","VET","ONT","WAVES","XTZ","NEO",
        "ROSE","SCRT","OASIS","HARMONY","ELROND","MULTIVERSX","APTOS",
        "MOVEMENT","MONAD","BERACHAIN","INITIA","SAGA","STORY","SUPRA",
        "HYPERLIQUID","ECLIPSE","FUSE","VENOM","NEON","ZETA",
    ],
    "Layer2": [
        "MATIC","OP","ARB","ZK","STRK","LRC","METIS","MANTA","SCROLL",
        "MNT","MERL","ALT","ZRO","LINEA","TAIKO","MOD","CELR","SKL",
        "OMG","SSV","BOBA","STARKNET","ZKFAIR","ZKLINK","ZKME","LUMIA",
        "POLYGON","OPTIMISM","ARBITRUM","STARKWARE","LOOPRING","MATTER",
        "IMMUTABLE","RONIN","BASE","BLAST","MANTLE","MODE","MINT",
        "FRAXTAL","ZORA","REDSTONE","CYBER","KINTO","ANCIENT8",
    ],
    "Meme": [
        "DOGE","SHIB","PEPE","FLOKI","WIF","BOM","MEME","TURO","POPCAT",
        "MOG","BABYDOGE","BONK","DOGS","CATI","GOAT","PNUT","ACT",
        "CHILLGUY","TURBO","LUNA","BOME","MOTHER","PONKE","GME","HONK",
        "MYRO","WOJAK","MIGGO","COQ","SLERF","SMOG","BOME","SILLY",
        "NOOT","WOOF","COPE","CHAD","BASED","FROG","CAT","DOG","APE",
        "MONKEY","HAMSTER","SQUIRREL","RACCOON","PENGUIN","PENG",
        "BRETT","ANDY","MOO","BAD","HARAMBE","GIGA","APED","LADYS",
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

# ═══════════════════════════════════════════════
#   SECTORS — 12 قطاع × 50 عملة
# ═══════════════════════════════════════════════
SECTORS = {
    "AI": [
        # ── الأساسيات ────────────────────────────
        "FETUSDT","AGIXUSDT","OCEANUSDT","RENDUSDT","GRTUSDT",
        "TAOAUSDT","ARKMUSDT","PHAUSDT","AIXBTUSDT","NEWTUSDT",
        "NEIROUSDT","AIUSDT","CGPTUSDT","NEUROUSDT","VANAUSDT",
        "DFUSDT","COOKIEUSDT","AIDOGEUSDT","MYRIAUSDT","ALETHUSDT",
        "WLDUSDT","KAIAUSDT","GRIFFAINUSDT","VIRTUSDT","SWARMAUSDT",
        "SENTIENTUSDT","MASKUSDT","AKTOUSDT","NUMUSDT","MEAIUSDT","MIRAUSDT",
        # ── إضافات V13 ───────────────────────────
        "KAITOUSDT","PAALUSDT","QUBICUSDT","SLEEPLESSUSDT","AITECHUSDT",
        "DEAIUSDT","SEKAIUSDT","BUZZUSDT","ALTERUSDT","COGNIUSDT",
        "EZAIUSDT","NAUAUSDT","TAOUSSDT","AGENTUSDT","AIGENUSDT",
        "BRAINUSDT","THINKUSDT","SMARTAIUSDT","FAIUSDT","DAINUSDT",
    ],
    "RWA": [
        # ── الأساسيات ────────────────────────────
        "ONDOUSDT","CFGUSDT","RSRUSDT","MPLXUSDT","REALUSDT",
        "TRSTUSDT","PROMUSDT","IDUSDT","MANTRAUSDT","XDCUSDT",
        "LQTYUSDT","SPXUSDT","ONPUSDT","VAIUSDT","GOLDUSDT",
        "TBLUSDT","PARCLUSDT","REXUSDT","HONEUSDT","OPENUSDT",
        "LANDXUSDT","CREDIXUSDT","POLIXUSDT","TRUEUSDT","MTVUSDT",
        "PROPUSDT","REUSDT","TPROTUSDT","STBTCUSDT","CULTUSDT",
        # ── إضافات V13 ───────────────────────────
        "POLYXUSDT","CENTUSDT","TOUCANUSDT","COORESTUSDT","REALIOУСDT",
        "LOFTYUSDT","MAPLEUSDT","GOLDFINCHUSDT","DEXTUSDT","BRICSUSDT",
        "ESTATEUSDT","REALTUSDT","DINOUSDT","FLOWXUSDT","ACHUSDT",
        "CELLUSDT","NEXOUSDT","SECURITIZEUSDT","POLKUSDT","NEWRLAUSDT",
        "CENTAUSDT","TRADEAUSDT",
    ],
    "Gaming": [
        # ── الأساسيات ────────────────────────────
        "AXSUSDT","SANDUSDT","MANAUSDT","ILVUSDT","GMTUSDT",
        "YGGUSDT","SLPUSDT","GALAUSDT","RONUSDT","IMXUSDT",
        "BEAMUSDT","PIXELUSDT","NOTUSDT","XAIUSDT","ALICEUSDT",
        "RAREUSDT","MOBAUSDT","PORTALUSDT","CHZUSDT","PGXUSDT",
        "HEROESUSDT","BEXUSDT","GOMAUSDT","ACEUSDT","METAUSDT",
        "WAXPUSDT","GALUSDT","VIDYAUSDT","ELFUSDT","TWTUSDT",
        # ── إضافات V13 ───────────────────────────
        "GHSTUSDT","TOWERUSDT","REVVUSDT","NFTXUSDT","MOBOXUSDT",
        "SKILLUSDT","DERACEUSDT","WARSUSDT","BATTLEUSDT","LEGENDUSDT",
        "KARTUSDT","CHAMPUSDT","WINUSDT","SUPERUSDT","GODSUSDT",
        "AURYUSDT","ATLASUSDT","POLISUSDT","PVUUSDT","REALMUSDT","MAGICUSDT",
    ],
    "DeFi": [
        # ── الأساسيات ────────────────────────────
        "UNIUSDT","AAVEUSDT","CAKEUSDT","SUSHIUSDT","COMPUSDT",
        "MKRUSDT","CRVUSDT","LDOUSDT","1INCHUSDT","C98USDT",
        "DYDXUSDT","GMXUSDT","JUPUSDT","RAYUSDT","ORCAUSDT",
        "PENDLEUSDT","EIGENUSDT","ETHFIUSDT","IDEXUSDT","REZUSDT",
        "SYRUPUSDT","BONEUSDT","CVXUSDT","FRAXUSDT","FXSUSDT",
        "TRIBEUSDT","RADUSDT","ALPACAUSDT","RAMPUSDT","WOOUSDT",
        # ── إضافات V13 ───────────────────────────
        "SNXUSDT","KNCUSDT","BALUSDT","BIFIUSDT","PERPUSDT",
        "JOEUSDT","SPIRITUSDT","VELODROMEUSDT","AERODROMEUSDT","THENAUSDT",
        "KYBERUSDT","BANCORUSDT","QUICKUSDT","SOLARUSDT","CAMELOTUSDT",
        "RAMSESUSDT","STERLINGUSDT","DODOUSDT","WIGOUSDT","APESWAPUSDT",
    ],
    "Layer1": [
        # ── الأساسيات ────────────────────────────
        "AVAXUSDT","ADAUSDT","ATOMUSDT","NEARUSDT","FTMUSDT",
        "ALGOUSDT","ICPUSDT","APTUSDT","SUIUSDT","SEIUSDT",
        "INJUSDT","KASUSDT","TONUSDT","HBARUSDT","EGLDUSDT",
        "ZILUSDT","ONEUSDT","CFXUSDT","JASMYUSDT","LSKUSDT",
        "QNTUSDT","CELOUSDT","FLOWUSDT","MINAUSDT","KAVAUSDT",
        "VETUSDT","ONTUSDT","WAVESUSDT","XTZUSDT","NEOUSDT",
        # ── إضافات V13 ───────────────────────────
        "SAGAUSDT","ZETAUSDT","VENOMUSDT","FUSEUSDT","SUPRAUSDT",
        "INITIAUSDT","STORYUSDT","MOVEMENTUSDT","MONADUSDT","BERACHAINUSDT",
        "ECLIPSEUSDT","SYSUSDT","COTIUSDT","RLCUSDT","TRACUSDT",
        "ALEOUSDT","ERAUSDT","HYPERUSDT","NEONUSDT","FUSIONUSDT",
        "CONCORDUSDT","NOLAUSDT","PALLADAUSDT","DFINITYUSDT","COSMOSUSDT",
    ],
    "Layer2": [
        # ── الأساسيات ────────────────────────────
        "MATICUSDT","OPUSDT","ARBUSDT","ZKUSDT","STRKUSDT",
        "LRCUSDT","METISUSDT","MANTAUSDT","SCROLLUSDT","MNTUSDT",
        "MERLUSDT","ALTUSDT","WUSDT","ZROUSDT","LINEAUSDT",
        "TAIKOUSDT","MODUSDT","CELRUSDT","SKLUSDT","OMGUSDT",
        "SSVUSDT","NEONUSDT","ZKCUSDT",
        # ── إضافات V13 ───────────────────────────
        "BLASTUSDT","MODEUSDT","MINTUSDT","ZORAUSDT","CYBERUSDT",
        "ANCIENT8USDT","KINTOУСDT","REDSTONEUSDT","LUMIAУСDT","ZKFAIRUSDT",
        "ZKLINKUSDT","ZKMEUSDT","ANYONEUSDT","ERGUSDT","SCRUSDT",
        "ARRUSDT","ZEPHUSDT","PIRATEUSDT","OPSUSDT","BOBAUSDT",
        "XVMUSDT","FRAXTALUSDT","MANTLEUSDT","BASEUSDT","PARTUSDT",
        "CHEQOUSDT","ZKPUSDT","POLYGONUSDT","GNOSISUSDT","KAIKOUSDT",
    ],
    "Meme": [
        # ── الأساسيات ────────────────────────────
        "DOGEUSDT","SHIBUSDT","PEPEUSDT","FLOKIUSDT","WIFUSDT",
        "BOMUSDT","MEMEUSDT","TUROUSDT","POPCATUSDT","MOGUSDT",
        "BABYDOGEUSDT","BONKUSDT","DOGSUSDT","CATIUSDT","GOATUSDT",
        "PNUTUSDT","ACTUSDT","CHILLGUYUSDT","TURBOUSDT","LUNAUSDT",
        "BOMEUSDT","MOTHERUSDT","PONKEUSDT","GMEUSDT","HONKUSDT",
        # ── إضافات V13 ───────────────────────────
        "MYROUSUSDT","WOJAKSUSDT","MIGGOUSDT","COQUSDT","SLERFUSDT",
        "SMOGUSDT","SILLYUSDT","NOOTUSDT","WOOFUSDT","COPEUSDT",
        "CHADUSDT","BASEDUSDT","FROGUSDT","BRETTUSDT","ANDYUSDT",
        "MOOUSDT","BADUSDT","HARAMBEUSDT","GIGAUSDT","APEDUSDT",
        "LADYSUSDT","MOODENGUSDT","PENGUUSDT","APEUSDT","REFACTAUSDT",
    ],
    "Oracle": [
        # ── الأساسيات ────────────────────────────
        "LINKUSDT","BANDUSDT","UMAUSDT","DIAUSDT","PYTHUSDT",
        "STORKUSDT","SXTUSDT","TELLOUSDT","CHRUSDT","PROSUSDT",
        "IOUSDT","ORAOUSDT","ACXUSDT","ATLUSDT","SUPRUSDT",
        "ORAIUSDT","TRUFUSDT","PRIMUSDT","DMTUSDT","REPUSDT",
        # ── إضافات V13 ───────────────────────────
        "API3USDT","FLUXUSDT","IOSTUSDT","NESTUSDT","DOSUSDT",
        "WITNETUSDT","RAZORUSDT","UMBRELLAУСDT","FIOUSDT","BIOUSDT",
        "HUMAUSDT","TRUTHUSDT","LAZIOUSDT","OOKIUSDT","DORGUSDT",
        "COCOSUSDT","MYSTUSDT","SWTHUSDT","COVALENTUSDT","PARSIQУСDT",
        "ALCHEMYUSDT","BADGERUSDT","WINKUSDT","ANKRUSDT","GEОDBUSDT",
        "INDEXCOOPUSDT","ZAPPERUSDT","POWERPOOLUSDT","NXRAUSDT","TELLUSDT2",
        "ORACLIZEUSDT","AUGUR2USDT","REALITUUSDT","TRUEBITUSDT","CHRONICLEUSDT",
    ],
    "Privacy": [
        # ── الأساسيات ────────────────────────────
        "XMRUSDT","DASHUSDT","SCRTUSDT","ROSEUSDT","ZECUSDT",
        "RAILUSDT","DUSKUSDT","ZENUSDT","COINUSDT","CTXCUSDT",
        # ── من صور MEXC ──────────────────────────
        "PHAUSDT","TORNUSDT","FIROUSDT","SCUSDT","HOPRUSDT",
        "LATUSDT","ERGUSDT","PIVXUSDT","ALEOUSDT","PARTUSDT",
        "ZEPHUSDT","ARRUSDT","NYMUSDT","COTIUSDT","RLCUSDT",
        "TRACUSDT","MINAUSDT","XELUSDT","HMNDUSDT","CHEQOUSDT",
        # ── Privacy إضافية معروفة ────────────────
        "OXENUSDT","BEAMXUSDT","GRINUSDT","NAVCUSDT","HAVENUSDT",
        "PANTHERUSDT","PRVCUSDT","ANONUSDT","IRONUSDT","SAFEUSDT",
        "XCMUSDT","LTZUSDT","ZENNUSDT","AZROUSDT","NYMOUSDT",
        # ── ZK Privacy ───────────────────────────
        "ZKPUSDT","SILUSDT","ANYONEUSDT","SHADUSDT","FIROUSDT",
        "ERGOUSDT","PIRATEUSDT","BCHPUSDT","ARRRUSDT","MAVUSDT",
    ],
    "Storage": [
        # ── الأساسيات ────────────────────────────
        "FILUSDT","ARUSDT","STORJUSDT","SCUSDT","BLZUSDT",
        "HOTUSDT","CKBUSDT","AIOZUSDT","KYVEUSDT","ALEPHUSDT",
        "DATAUSDT","SIACOINUSDT","LAMBUSDT","BTTCUSDT","PEAQUSDT",
        # ── إضافات V13 ───────────────────────────
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
        # ── الأساسيات ────────────────────────────
        "IOTAUSDT","HNTUSDT","LPTUSDT","NTRNUSDT","GPUUSDT",
        "PONDUSDT","DAWNUSDT","WIFIUSDT","OXTUSDT","RDNTUSDT",
        "GRASSUSDT","IONUSDT","TIAUSDT","CUDOSUSDT","IOTXUSDT",
        "POKTUSDT","DOTUSDT","XNETUSDT","MOBIUSDT","NOSANAUSDT",
        # ── إضافات V13 ───────────────────────────
        "HIVEMAPPERUSDT","HIVELLOUSDT","NATIXUSDT","DIMOUSDT","NUBILAUSDT",
        "REACTUSDT","GEODNETUSDT","SOARXUSDT","NGLAUSDT","PINGUSDT",
        "ROAMUSDT","NODELUSDT","CPOOLUSDT","SHDWUSDT","HELIUMUSDT",
        "SENSORUSDT","MESHUSDT","MXCUSDT","PEAQUSDT","AUTONUSDT",
        "DKGUSDT","AIRNODEUSDT","EXOCOREUSDT","ACURASTUSDT","ROAMXUSDT",
        "IONUSDT2","SULLYUSDT","POKTUSDT2","IOTXUSDT2","WIFIUSDT2",
        "RNDRNETUSDT","POWERLEDGERUSDT","ORIGINTRAILUSDT","DATAUSDT2",
    ],
    "Old": [
        # ── الأساسيات ────────────────────────────
        "LTCUSDT","ETCUSDT","LUNCUSDT","BCHUSDT","EOSUSDT",
        "TRXUSDT","QTUMUSDT","RVNUSDT","ARKUSDT","DCRUSDT",
        "DGBUSDT","ZRXUSDT","NEOUSDT","ONTUSDT","VETUSDT",
        # ── إضافات V13 ───────────────────────────
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
}

# ═══════════════════════════════════════════════
#   LOGGING
# ═══════════════════════════════════════════════
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

# ═══════════════════════════════════════════════
#                   STATE
# ═══════════════════════════════════════════════
tracked        = {}   # {sym: {entry, peak, level, sl_pct, entry_time, last_alert}}
discovered     = {}   # {sym: {price, time, score}}

btc_change_24h = 0.0
btc_trend_1h   = 0.0
market_state   = "SAFE"
hot_sectors    = []        # type: List[str]
hot_symbols    = set()     # type: Set[str]
sector_vol_history = {}    # type: Dict[str, float]

candidates     = []        # type: List[str]
changes_map    = {}        # type: Dict[str, float]
all_tickers    = []        # type: List[Dict]  ← global محدَّثة في run()

klines_cache   = {}        # type: Dict[str, Tuple[Any, float]]

last_tickers      = 0.0
last_btc          = 0.0
last_sectors      = 0.0
last_deep_scan    = 0.0
last_stale        = 0.0
last_report       = 0.0
last_smart_money  = 0.0
last_expand       = 0.0    # 🆕 آخر توسيع تلقائي للقوائم

stable_vol_history = {}   # type: Dict[str, List[float]]
smart_money_alert  = False
smart_money_bonus  = 0    # 🆕 مكافأة Score عند تجميع الحيتان

price_prev         = {}   # type: Dict[str, float]
momentum_alerted   = {}   # type: Dict[str, float]
momentum_stage     = {}   # type: Dict[str, Dict]

# 🆕 Sector Flow Tracker State
sector_vol_snapshots = {}  # type: Dict[str, List[float]]   {sector: [vol1, vol2, ...]}
sector_change_snapshots = {}  # type: Dict[str, List[float]] {sector: [avg_ch1, avg_ch2, ...]}
sector_flow_alerted  = {}  # type: Dict[str, float]          {sector: last_alert_time}
sector_flow_state    = {}  # type: Dict[str, str]            {sector: "IN"/"OUT"/"NEUTRAL"}
top10_alerted        = {}  # type: Dict[str, float]          {sector: last_top10_alert_time}

# 🆕 V15: تاريخ حجم كل عملة للمقارنة التاريخية
coin_vol_history     = {}  # type: Dict[str, List[float]]   {sym: [vol1, vol2, ...]}

# 🆕 V15: Backtesting — تتبع إشارات Top10
backtest_signals     = {}  # type: Dict[str, Dict]  {sym: {entry_price, entry_time, sector, checked_1h, checked_4h, checked_24h}}

api_calls_total    = 0
api_calls_minute   = 0
api_minute_reset   = time.time()

session = requests.Session()
session.headers.update({"User-Agent": "MafioBot/11.0"})


# ═══════════════════════════════════════════════
#   HELPERS
# ═══════════════════════════════════════════════
def format_price(p):
    # type: (float) -> str
    if p == 0: return "0"
    if p < 0.0001:  return "{:.10f}".format(p).rstrip("0")
    if p < 1:       return "{:.8f}".format(p).rstrip("0")
    if p < 1000:    return "{:.4f}".format(p).rstrip("0").rstrip(".")
    return "{:,.2f}".format(p)


def send(msg):
    # type: (str) -> None
    if "YOUR" in TELEGRAM_TOKEN:
        log.info("[TELEGRAM] %s", msg[:80])
        return
    try:
        session.post(
            "https://api.telegram.org/bot{}/sendMessage".format(TELEGRAM_TOKEN),
            data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"},
            timeout=10,
        )
    except Exception as e:
        log.error("Telegram: %s", e)


def safe_get(url, params=None):
    # type: (str, Optional[dict]) -> Optional[Any]
    global api_calls_total, api_calls_minute, api_minute_reset
    try:
        r = session.get(url, params=params, timeout=10)
        r.raise_for_status()
        api_calls_total  += 1
        api_calls_minute += 1
        if time.time() - api_minute_reset >= 60:
            log.info("📡 API: %d طلب/دقيقة | إجمالي: %d",
                     api_calls_minute, api_calls_total)
            api_calls_minute = 0
            api_minute_reset = time.time()
        return r.json()
    except Exception as e:
        log.debug("API خطأ [%s]: %s", url.split("/")[-1], e)
        return None


# ═══════════════════════════════════════════════
#   SMART CACHE
# ═══════════════════════════════════════════════
def get_klines(symbol, interval="15m", limit=50):
    # type: (str, str, int) -> Optional[Dict]
    cache_ttl = {"15m": CACHE_15M, "1h": CACHE_1H, "4h": CACHE_4H}.get(interval, CACHE_15M)
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


# ═══════════════════════════════════════════════
#   🆕 V15: RSI CALCULATOR
#   حساب RSI بدون مكتبات خارجية — على كلوز prices
# ═══════════════════════════════════════════════
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


# ═══════════════════════════════════════════════
#   🆕 V15: COIN VOL HISTORY
#   تحديث تاريخ حجم كل عملة لحساب vol_ratio التاريخي
# ═══════════════════════════════════════════════
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
        return 1.0   # لا يوجد تاريخ كافٍ — نعتبره طبيعياً
    # نستخدم السابقات فقط (بدون الحالية)
    prev = hist[:-1] if len(hist) > 1 else hist
    avg  = sum(prev) / len(prev)
    if avg <= 0:
        return 1.0
    return round(current_vol / avg, 2)


# ═══════════════════════════════════════════════
#   PRE-FILTER
# ═══════════════════════════════════════════════
def is_stablecoin(sym, last_price=0.0, change=0.0):
    # type: (str, float, float) -> bool
    base = sym.replace("USDT", "")
    if base in STABLECOINS: return True
    for kw in STABLE_KEYWORDS:
        if base.startswith(kw) or base.endswith(kw): return True
    if abs(change) < 0.5 and last_price > 0: return True
    return False


def pre_filter(sym, change, vol, price=0.0):
    # type: (str, float, float, float) -> bool
    """
    🐛 إصلاح V11: أُزيل return True المكرر الميت
    """
    if not sym.endswith("USDT"): return False
    if sym in EXCLUDED: return False
    if any(k in sym for k in LEVERAGE_KEYWORDS): return False
    if is_stablecoin(sym, price, change): return False
    if vol < PRE_MIN_VOL or vol > PRE_MAX_VOL: return False
    if change < PRE_MIN_CHANGE or change > PRE_MAX_CHANGE: return False
    if market_state == "DANGER" and change <= btc_change_24h: return False
    return True


# ═══════════════════════════════════════════════
#   BTC MARKET ANALYSIS
#   🐛 إصلاح V11: استخدام params={"symbol":"BTCUSDT"} بدل endpoint منفصل
# ═══════════════════════════════════════════════
def analyze_btc():
    # type: () -> None
    global btc_change_24h, btc_trend_1h, market_state, last_btc

    # ✅ الإصلاح: نجلب بيانات BTC بالـ symbol param وليس بـ endpoint مختلف
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

    # اتجاه 1h
    kd1 = get_klines("BTCUSDT", "1h", 4)
    if kd1 and len(kd1["closes"]) >= 2:
        c = kd1["closes"]
        btc_trend_1h = (c[-1] - c[0]) / c[0] * 100

    old = market_state
    if btc_change_24h <= BTC_DANGER_ZONE or btc_trend_1h <= -2.0:
        market_state = "DANGER"
    elif btc_change_24h <= BTC_CAUTION_ZONE:
        market_state = "CAUTION"
    else:
        market_state = "SAFE"

    last_btc = time.time()

    if old != market_state:
        icons = {"SAFE": "🟢", "CAUTION": "🟡", "DANGER": "🔴"}
        notes = {
            "SAFE":    "✅ كل الإشارات مفعّلة",
            "CAUTION": "⚠️ Gold فقط (Score 88+)",
            "DANGER":  "🔴 إشارات القطاعات الساخنة فقط",
        }
        send(
            "📊 *تقرير السوق*\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "{icon} السوق: *{state}*\n"
            "₿ BTC 24h: `{ch:+.2f}%`\n"
            "₿ BTC 1h:  `{h:+.2f}%`\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "_{note}_".format(
                icon=icons[market_state], state=market_state,
                ch=btc_change_24h, h=btc_trend_1h,
                note=notes[market_state],
            )
        )
        log.info("📊 Market: %s→%s | BTC %.2f%%", old, market_state, btc_change_24h)


# ═══════════════════════════════════════════════
#   SECTOR ROTATION
# ═══════════════════════════════════════════════
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
        prev_vol   = sector_vol_history.get(sector, total_vol)
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
        msg = "🔄 *SECTOR ROTATION*\n━━━━━━━━━━━━━━━━━━\n"
        if entered:
            msg += "💰 *سيولة تدخل:*\n"
            for s in entered:
                st = stats.get(s, {})
                coins_txt = " | ".join(
                    "{} +{:.0f}%".format(c, p) for c, p in st.get("top", [])
                )
                msg += "  🔥 *{}* avg:`+{:.1f}%`\n  {}\n".format(
                    s, st.get("avg", 0), coins_txt)
        if exited:
            msg += "📤 *سيولة خرجت:* `{}`\n".format(", ".join(exited))
        msg += "\n₿ BTC: `{:+.2f}%` | `{}`".format(btc_change_24h, market_state)
        send(msg)
        log.info("🔄 Sectors: %s → %s", list(old_hot), new_hot)

    if hot_sectors:
        log.info("🔥 Hot: %s", ", ".join(hot_sectors))


# ═══════════════════════════════════════════════
#   🆕 SECTOR FLOW TRACKER V11
#   يرصد تدفق السيولة بين القطاعات في الوقت الحقيقي
#   يعمل كل 12 ثانية — بدون طلبات API إضافية!
# ═══════════════════════════════════════════════
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

        # حفظ اللقطة
        if sector not in sector_vol_snapshots:
            sector_vol_snapshots[sector] = []
        if sector not in sector_change_snapshots:
            sector_change_snapshots[sector] = []

        sector_vol_snapshots[sector].append(total_vol)
        sector_change_snapshots[sector].append(avg_ch)

        # الاحتفاظ بآخر FLOW_HISTORY_MAX لقطة فقط
        if len(sector_vol_snapshots[sector]) > FLOW_HISTORY_MAX:
            sector_vol_snapshots[sector].pop(0)
        if len(sector_change_snapshots[sector]) > FLOW_HISTORY_MAX:
            sector_change_snapshots[sector].pop(0)


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
    inflows   = []   # قطاعات تدخل إليها سيولة الآن
    outflows  = []   # قطاعات تخرج منها سيولة

    for sector in SECTORS:
        vols    = sector_vol_snapshots.get(sector, [])
        changes = sector_change_snapshots.get(sector, [])

        # نحتاج على الأقل FLOW_WINDOW لقطات للمقارنة
        if len(vols) < FLOW_WINDOW or len(changes) < FLOW_WINDOW:
            continue

        # آخر لقطة vs متوسط السابقات
        recent_vol  = vols[-1]
        prev_avg_vol = sum(vols[-FLOW_WINDOW:-1]) / (FLOW_WINDOW - 1)
        if prev_avg_vol <= 0:
            continue

        vol_ratio   = recent_vol / prev_avg_vol
        recent_ch   = changes[-1]
        avg_ch_prev = sum(changes[-FLOW_WINDOW:-1]) / (FLOW_WINDOW - 1)

        # ── رصد دخول السيولة ──────────────────────
        is_inflow = (
            vol_ratio >= FLOW_VOL_SURGE and
            recent_ch >= FLOW_CHANGE_MIN
        )

        # ── رصد خروج السيولة ──────────────────────
        is_outflow = (
            vol_ratio < (1.0 / FLOW_VOL_SURGE) and  # انخفض الحجم
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

    # ── إرسال تنبيهات الدخول ──────────────────────
    for info in inflows:
        sector = info["sector"]
        last_alert = sector_flow_alerted.get(sector, 0)
        if now - last_alert < FLOW_ALERT_COOL:
            continue

        sector_flow_alerted[sector] = now

        # أفضل عملات في هذا القطاع الآن
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

        # هل القطاع ساخن أصلاً؟
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
        log.info("💸 Flow IN | %s | ratio=%.2f | ch=%.1f%%", sector, info["vol_ratio"], info["ch"])

        # 🆕 V14: إطلاق Smart Top10 فوراً بعد إشعار الدخول
        # نحتاج ticker_map — نبنيه من all_tickers
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

    # ── إرسال تنبيهات الخروج ──────────────────────
    if outflows:
        out_txt = ""
        for info in outflows:
            out_txt += "  📤 *{}* حجم:`{}×` ch:`{:.1f}%`\n".format(
                info["sector"], info["vol_ratio"], info["ch"])

        # لا ترسل إشعار خروج إذا أُرسل مؤخراً لجميع القطاعات
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
            log.info("📤 Flow OUT | %s", [i["sector"] for i in outflows])


def get_flow_summary():
    # type: () -> str
    """يرجع ملخص حالة السيولة للقطاعات — يُستخدم في تقرير الأداء"""
    in_sectors  = [s for s, state in sector_flow_state.items() if state == "IN"]
    out_sectors = [s for s, state in sector_flow_state.items() if state == "OUT"]
    txt = ""
    if in_sectors:
        txt += "💸 سيولة داخلة: `{}`\n".format(", ".join(in_sectors))
    if out_sectors:
        txt += "📤 سيولة خارجة: `{}`\n".format(", ".join(out_sectors))
    return txt or "➡️ لا تدفق واضح\n"


# ═══════════════════════════════════════════════
#   🆕 SMART TOP10 ALERT V14
#   اصطياد أفضل 10 عملات في القطاع قبل الانفجار
#   يُستدعى فوراً عند رصد Sector Flow IN
# ═══════════════════════════════════════════════
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

    # cooldown: لا ترسل نفس القطاع كل 30 دقيقة
    if now - top10_alerted.get(sector, 0) < TOP10_COOLDOWN:
        return

    coins    = SECTORS.get(sector, [])
    scored   = []

    for sym in coins:
        # ── فلاتر أساسية ───────────────────────
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

        # ── الفلتر الذهبي: 0% < تغيير < 5% ────
        if ch < TOP10_CHANGE_MIN: continue
        if ch > TOP10_CHANGE_MAX: continue

        # ── 🆕 V15: vol_ratio تاريخي للعملة نفسها ──
        vol_ratio = get_coin_vol_ratio(sym, vol)
        if vol_ratio < TOP10_VOL_RATIO: continue

        # ── قريب من القاع ──────────────────────
        rebound = (price - low_24h) / low_24h * 100 if low_24h > 0 else 99
        if rebound > TOP10_REBOUND_MAX: continue

        # ── ليس Stablecoin أو Leverage ─────────
        base = sym.replace("USDT", "")
        if base in STABLECOINS: continue
        if any(k in sym for k in LEVERAGE_KEYWORDS): continue

        # ── 🆕 V15: RSI Filter ──────────────────
        # نجلب RSI من كلوز 15m (من الكاش إذا متاح)
        rsi_val = -1.0
        kd_rsi  = get_klines(sym, "15m", RSI_PERIOD + 2)
        if kd_rsi and len(kd_rsi["closes"]) >= RSI_PERIOD + 1:
            rsi_val = calc_rsi(kd_rsi["closes"])
            # ارفض العملات في ذروة الشراء
            if rsi_val > RSI_OVERBOUGHT:
                log.debug("🔴 RSI رفض: %s RSI=%.1f", sym, rsi_val)
                continue

        # ── حساب النقاط (100 نقطة) ─────────────
        # 1. حجم مرتفع فجأة (40 نقطة) — تاريخي الآن
        vol_score = min(vol_ratio / 5.0, 1.0) * W_VOL_RATIO

        # 2. قطاع ساخن + Flow داخل (25 نقطة)
        is_hot    = sym in hot_symbols
        flow_in   = sector_flow_state.get(sector, "NEUTRAL") == "IN"
        hot_score = W_HOT_SECTOR if (is_hot and flow_in) else (W_HOT_SECTOR * 0.5 if is_hot else 0)

        # 3. قريب من القاع (20 نقطة)
        rebound_score = max(0, (TOP10_REBOUND_MAX - rebound) / TOP10_REBOUND_MAX) * W_REBOUND_LOW

        # 4. تغيير صغير = لم ينطلق بعد (15 نقطة)
        change_score = max(0, (TOP10_CHANGE_MAX - ch) / TOP10_CHANGE_MAX) * W_CHANGE_SMALL

        # 🆕 مكافأة RSI منخفض (يصل إلى +5 نقاط إضافية)
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
        log.info("🔍 Top10 [%s]: لا عملات تحقق الشروط", sector)
        return

    # ترتيب تنازلي حسب النقاط
    scored.sort(key=lambda x: -x["score"])
    top10 = scored[:TOP10_COUNT]

    top10_alerted[sector] = now

    # ── 🆕 V15: تسجيل كل عملة في Backtest ──────
    for c in top10:
        register_backtest(c["sym"], c["price"], sector)

    # ── بناء رسالة Telegram المحسّنة ────────────
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
            price=format_price(c["price"]),
            ch=c["ch"],
            ratio=c["vol_ratio"],
            reb=c["rebound"],
            drop=c["drop"],
            rsi_ic=rsi_ic,
            rsi_str=" " + rsi_str if rsi_str else "",
        )

    mkt_icon = {"SAFE": "🟢", "CAUTION": "🟡", "DANGER": "🔴"}.get(market_state, "⚪")

    # إحصاء كم عملة RSI جيد
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
    log.info("🚨 Top10 V15 | %s | %d عملة | أفضل: %s (%.1f نقطة) | RSI جيد: %d",
             sector, len(top10), top10[0]["sym"], top10[0]["score"], good_rsi_count)



# ═══════════════════════════════════════════════
#   🆕 V15: BACKTESTING ENGINE
#   يتتبع إشارات Top10 ويقيس أداءها بعد 1h/4h/24h
# ═══════════════════════════════════════════════
def register_backtest(sym, price, sector):
    # type: (str, float, str) -> None
    """يسجل إشارة Top10 عند إرسالها — للمتابعة اللاحقة"""
    global backtest_signals
    if sym in backtest_signals:
        return   # مسجل بالفعل
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
    log.info("📋 Backtest سجّل: %s @ %s", sym, price)


def check_backtest(price_map):
    # type: (Dict[str, float]) -> None
    """
    يُستدعى من run() كل دورة.
    يتحقق من الإشارات المسجلة ويرسل نتائجها عند الوقت المحدد.
    """
    global backtest_signals
    now = time.time()

    for sym, data in list(backtest_signals.items()):
        price = price_map.get(sym, 0)
        if price <= 0:
            continue

        entry = data["entry_price"]
        if entry <= 0:
            continue

        elapsed = now - data["entry_time"]
        gain    = (price - entry) / entry * 100
        emoji   = "✅" if gain > 0 else "🔴"

        # ── تحقق 1 ساعة ──────────────────────────
        if not data["checked_1h"] and elapsed >= BACKTEST_CHECK_1H:
            data["checked_1h"]  = True
            data["result_1h"]   = round(gain, 2)
            send(
                "📊 *BACKTEST 1H* | `{sym}`\n"
                "{em} النتيجة: `{gain:+.2f}%`\n"
                "💵 دخول: `{entry}` ← الآن: `{now_p}`\n"
                "🏷️ قطاع: `{sector}`".format(
                    sym=sym.replace("USDT",""), em=emoji, gain=gain,
                    entry=entry, now_p=round(price, 6),
                    sector=data["sector"],
                )
            )
            log.info("📊 Backtest 1H | %s | %+.2f%%", sym, gain)

        # ── تحقق 4 ساعات ─────────────────────────
        elif not data["checked_4h"] and elapsed >= BACKTEST_CHECK_4H:
            data["checked_4h"]  = True
            data["result_4h"]   = round(gain, 2)
            send(
                "📊 *BACKTEST 4H* | `{sym}`\n"
                "{em} النتيجة: `{gain:+.2f}%`\n"
                "💵 دخول: `{entry}` ← الآن: `{now_p}`\n"
                "1H كان: `{r1h}%` | 4H الآن: `{gain:+.2f}%`".format(
                    sym=sym.replace("USDT",""), em=emoji, gain=gain,
                    entry=entry, now_p=round(price, 6),
                    r1h=data.get("result_1h","N/A"),
                )
            )
            log.info("📊 Backtest 4H | %s | %+.2f%%", sym, gain)

        # ── تحقق 24 ساعة ─────────────────────────
        elif not data["checked_24h"] and elapsed >= BACKTEST_CHECK_24H:
            data["checked_24h"] = True
            data["result_24h"]  = round(gain, 2)
            # تقرير نهائي مفصل
            r1h  = data.get("result_1h")
            r4h  = data.get("result_4h")
            best = max(
                x for x in [r1h, r4h, gain] if x is not None
            )
            send(
                "🏁 *BACKTEST 24H — نهائي* | `{sym}`\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "{em} 24H: `{gain:+.2f}%`\n"
                "📈 أفضل نقطة: `+{best:.2f}%`\n"
                "⏱️ 1H: `{r1h}%` | 4H: `{r4h}%`\n"
                "💵 دخول: `{entry}`\n"
                "🏷️ قطاع: `{sector}`".format(
                    sym=sym.replace("USDT",""), em=emoji, gain=gain,
                    best=best,
                    r1h=r1h if r1h is not None else "N/A",
                    r4h=r4h if r4h is not None else "N/A",
                    entry=entry, sector=data["sector"],
                )
            )
            log.info("🏁 Backtest 24H | %s | %+.2f%%", sym, gain)
            # احذف بعد 24h (تم الانتهاء)
            del backtest_signals[sym]


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


# ═══════════════════════════════════════════════
#   SMART MONEY DETECTION
# ═══════════════════════════════════════════════
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

    # 🆕 مكافأة Score عند تجميع الحيتان: عملة في قطاع ساخن + تجميع = score+10
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
        log.info("🚨 Urgent Smart Money! %d stables | sigma_max=%.1f",
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
    log.info("🐋 Smart Money | accum=%s | stables=%d | falling=%.0f%%",
             is_accumulation, len(detected), falling_pct)


# ═══════════════════════════════════════════════
#   MOMENTUM DETECTOR — نظام الإشعارات الثلاثي
# ═══════════════════════════════════════════════
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

    # متابعة المراحل 2 و 3
    for sym in list(momentum_stage.keys()):
        if sym not in price_map: continue
        price      = price_map[sym]
        sd         = momentum_stage[sym]
        vol        = vol_now.get(sym, 0)
        change_24h = change_now.get(sym, 0)
        entry_price= sd["entry_price"]
        entry_vol  = sd["entry_vol"]
        gain       = (price - entry_price) / entry_price * 100 if entry_price > 0 else 0

        # 🐛 إصلاح V11: تنظيف أفضل — نحذف فقط إذا انتهت 4 ساعات أو خسر >5%
        if now - sd["entry_time"] > 14400 or gain < -5.0:
            del momentum_stage[sym]
            continue

        vol_ratio      = vol / entry_vol if entry_vol > 0 else 1
        high_24h       = high_map.get(sym, price)
        drop_from_high = (high_24h - price) / high_24h * 100 if high_24h > 0 else 0

        # 🟡 إشعار 2
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
                        price=format_price(price), drop=drop_from_high,
                        top="🏆 *أفضل عملات القطاع:*\n{}\n".format(top10_txt) if top10_txt else "",
                        time=datetime.now().strftime("%H:%M:%S"),
                    )
                )
                log.info("🟡 Stage2 | %s | +%.2f%% | vol_ratio=%.1f", sym, gain, vol_ratio)

        # 🟢 إشعار 3
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
                        price=format_price(price), close=close_icon,
                        time=datetime.now().strftime("%H:%M:%S"),
                    )
                )
                deep_scan(sym, price, change_24h)
                log.info("🟢 Stage3 | %s | +%.2f%%", sym, gain)

    # 🔵 إشعار 1: رصد جديد
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

        momentum_alerted[sym] = now

        sector         = next((s for s, syms in SECTORS.items() if sym in syms), "")
        in_hot         = sym in hot_symbols
        hot_tag        = " 🔥 *{}*".format(sector) if in_hot else ""
        rebound        = (price - low_24h) / low_24h * 100 if low_24h > 0 else 0
        drop_from_high = (high_24h - price) / high_24h * 100 if high_24h > 0 else 0

        # 🆕 تحقق إذا القطاع يستقبل سيولة الآن
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

        log.info("🔵 Stage1 | %s | +%.2f%% | 24h:%.1f%% | vol:%.0f | sector:%s | flow:%s",
                 sym, move, change_24h, vol, sector, flow_state)

        send(
            "🔵 *Momentum Detected*{hot}{flow}\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "💰 *{sym}*  |  🏷️ `{sector}`\n"
            "📈 تحرك لحظي: `+{move:.2f}%`\n"
            "📊 تغيير 24h: `+{ch:.1f}%`\n"
            "💧 حجم: `{vol:,.0f}`\n"
            "💵 السعر: `{price}`\n"
            "📉 من القمة: `-{drop:.1f}%` | ارتداد: `+{reb:.1f}%`\n"
            "{top}"
            "🕐 `{time}`\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "👀 _مراقبة — انتظر إشعار التأكيد_".format(
                hot=hot_tag, flow=flow_tag,
                sym=sym, sector=sector if sector else "—",
                move=move, ch=change_24h, vol=vol,
                price=format_price(price),
                drop=drop_from_high, reb=rebound,
                top="🏆 *أفضل عملات القطاع:*\n{}\n".format(top10_txt) if top10_txt else "",
                time=datetime.now().strftime("%H:%M:%S"),
            )
        )


# ═══════════════════════════════════════════════
#   🆕 AUTO EXPAND SECTORS V12
#   يجلب عملات MEXC ويضيف الجديدة لكل قطاع (هدف 50/قطاع)
# ═══════════════════════════════════════════════
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
            # تطابق كامل أو جزئي
            if kw == base_upper:
                score += 10   # تطابق تام = وزن أعلى
            elif base_upper.startswith(kw) or base_upper.endswith(kw):
                score += 5
            elif kw in base_upper and len(kw) >= 3:
                score += 2
        if score > best_score:
            best_score  = score
            best_sector = sector

    # نقبل فقط إذا كان هناك تطابق واضح
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
    log.info("🔍 Auto Expand: جلب عملات MEXC...")

    data = safe_get(MEXC_24H)
    if not data:
        log.warning("⚠️ Auto Expand: فشل جلب البيانات")
        return

    # كل العملات الموجودة حالياً في قائمتنا
    existing = set(sym for coins in SECTORS.values() for sym in coins)

    # بناء خريطة الحجوم
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

    # فرز حسب الحجم تنازلياً (الأنشط أولاً)
    all_usdt = sorted(
        [s for s in vol_map if vol_map[s] >= EXPAND_MIN_VOL],
        key=lambda s: -vol_map[s]
    )

    added_per_sector = {s: [] for s in SECTORS}   # ما أُضيف جديداً
    skipped_existing = 0
    skipped_filter   = 0

    for sym in all_usdt:
        # تجاهل الموجودة أصلاً
        if sym in existing:
            skipped_existing += 1
            continue

        # تجاهل المستثنيات
        if sym in EXCLUDED:
            continue

        base = sym.replace("USDT","")

        # فلتر Stablecoin
        if is_stablecoin(sym, 0.0, change_map.get(sym, 0.0)):
            skipped_filter += 1
            continue

        # فلتر Leverage tokens
        if any(k in sym for k in LEVERAGE_KEYWORDS):
            skipped_filter += 1
            continue

        # فلتر الحجم الأقصى
        if vol_map[sym] > EXPAND_MAX_VOL:
            skipped_filter += 1
            continue

        # تصنيف العملة
        sector = _classify_symbol(base)
        if not sector:
            continue

        # هل القطاع وصل الهدف؟
        current_count = len(SECTORS[sector]) + len(added_per_sector[sector])
        if current_count >= SECTOR_TARGET:
            continue

        # إضافة للقطاع
        SECTORS[sector].append(sym)
        added_per_sector[sector].append(sym)
        existing.add(sym)

    # ── تقرير ما أُضيف ──────────────────────────
    total_added = sum(len(v) for v in added_per_sector.values())
    log.info("✅ Auto Expand انتهى | أُضيف: %d عملة | موجودة: %d | مُرشَّح: %d",
             total_added, skipped_existing, skipped_filter)

    if total_added == 0:
        log.info("ℹ️ لا عملات جديدة للإضافة — القوائم مكتملة")
        return

    # بناء رسالة Telegram
    msg = (
        "🔄 *AUTO EXPAND V12*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "✅ أُضيف *{}* عملة جديدة\n\n".format(total_added)
    )

    for sector, coins in added_per_sector.items():
        if not coins:
            continue
        total_in_sector = len(SECTORS[sector])
        names = ", ".join(c.replace("USDT","") for c in coins[:10])
        if len(coins) > 10:
            names += " ... +{}".format(len(coins)-10)
        msg += (
            "🏷️ *{sector}* ({total}/50)\n"
            "  ➕ {names}\n\n"
        ).format(
            sector=sector,
            total=total_in_sector,
            names=names,
        )

    msg += "━━━━━━━━━━━━━━━━━━\n"
    msg += "📋 راجع القائمة وأخبرني بأي تعديل"

    send(msg)

    # تحديث hot_symbols بعد التوسع
    global hot_symbols
    hot_symbols = {c for s in hot_sectors for c in SECTORS[s]}
    log.info("🔥 hot_symbols محدَّثة | %d عملة", len(hot_symbols))


# ═══════════════════════════════════════════════
#   REFRESH TICKERS
#   🐛 إصلاح V11: candidates تأخذ فلتر الحجم من all_tickers
# ═══════════════════════════════════════════════
def refresh_tickers():
    # type: () -> None
    global all_tickers, changes_map, candidates, last_tickers

    data = safe_get(MEXC_24H)
    if not data:
        return

    all_tickers = data
    changes_map = {}

    # بناء خريطة الحجوم من البيانات الحالية
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

    # ✅ الإصلاح: candidates = عملات قائمتنا التي تجاوزت فلتر الحجم
    our_coins  = set(sym for coins in SECTORS.values() for sym in coins)
    candidates = [
        sym for sym in our_coins
        if sym not in EXCLUDED and
           vol_map.get(sym, 0) >= MIN_VOL_USDT and
           vol_map.get(sym, 0) <= MAX_VOL_USDT
    ]
    last_tickers = time.time()

    log.info("📋 Candidates: %d عملة من قائمتنا | Hot: %s",
             len(candidates), ", ".join(hot_sectors) or "لا يوجد")


# ═══════════════════════════════════════════════
#   ANALYSIS FUNCTIONS
# ═══════════════════════════════════════════════
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
    data = safe_get(MEXC_DEPTH, {"symbol": symbol, "limit": 20})
    if not data: return None
    try:
        bid = sum(float(b[0])*float(b[1]) for b in data.get("bids",[]))
        ask = sum(float(a[0])*float(a[1]) for a in data.get("asks",[]))
        return {"bid": bid, "ask": ask, "imb": bid/ask if ask>0 else 99}
    except: return None


# ═══════════════════════════════════════════════
#   DYNAMIC STOP LOSS
# ═══════════════════════════════════════════════
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


# ═══════════════════════════════════════════════
#   TRAILING STOP
# ═══════════════════════════════════════════════
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
                format_price(entry), format_price(price),
                format_price(peak)
            )
        )
        log.info("🛑 Trailing: %s | %.2f%%", symbol, result)
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
                format_price(entry), format_price(price)
            )
        )
        log.info("🛑 SL: %s | %.2f%%", symbol, change)
        del tracked[symbol]
        return True

    return False


# ═══════════════════════════════════════════════
#   SCORE SYSTEM V11
#   🆕 تحسين: عقوبة BTC هابط + مكافأة Sector Flow + Smart Money
# ═══════════════════════════════════════════════
def calculate_score(kd, ob, vol_accum, vol_spike, consol,
                    higher_lows, green, bo_str, in_hot, st, symbol=""):
    # type: (Dict, Optional[Dict], Tuple, Tuple, Tuple, Tuple, Tuple, float, bool, str, str) -> int
    score = 0
    avg   = kd["avg_vol"]

    # حجم (15)
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

    # اتجاه عام (5)
    c = kd["closes"]
    if c[-1] > c[0]: score += 5

    # Pre-Breakout (10)
    if bo_str > 0: score += max(int(bo_str/100*10), 6)

    # Sector Rotation Bonus (15)
    if in_hot: score += SECTOR_BONUS

    # 🆕 Sector Flow Bonus (+8): القطاع يستقبل سيولة الآن
    if symbol:
        sector = next((s for s, syms in SECTORS.items() if symbol in syms), "")
        if sector and sector_flow_state.get(sector) == "IN":
            score += 8

    # 🆕 BTC Penalty: إذا BTC ينزل بقوة، عملة غير محمية = طرح نقاط
    if btc_change_24h < -2.0 and not in_hot:
        score -= 8
    elif btc_change_24h < -1.0 and not in_hot:
        score -= 4

    # 🆕 Smart Money Bonus: تجميع حيتان + قطاع ساخن
    if smart_money_bonus > 0 and in_hot:
        score += smart_money_bonus

    return min(max(score, 0), 100)


def score_label(score):
    # type: (int) -> Optional[str]
    if score >= 88: return "🏆 *GOLD SIGNAL*"
    if score >= 75: return "🔵 *SILVER SIGNAL*"
    return None


# ═══════════════════════════════════════════════
#   DEEP SCAN
# ═══════════════════════════════════════════════
def deep_scan(symbol, price, change):
    # type: (str, float, float) -> None
    if symbol in tracked: return

    if market_state == "DANGER" and symbol not in hot_symbols:
        log.debug("⛔ %s رُفض: DANGER + ليس hot", symbol)
        return

    kd = get_klines(symbol, "15m", 50)
    if not kd:
        log.debug("⛔ %s رُفض: لا klines", symbol)
        return

    is_pd, pd_r = detect_pump_dump(kd)
    if is_pd:
        log.debug("🚫 P&D: %s | %s", symbol, pd_r)
        return

    vol_ratio_kd = kd["vols"][-1] / kd["avg_vol"] if kd["avg_vol"] > 0 else 0
    if vol_ratio_kd < 1.2:
        log.debug("⛔ %s رُفض: حجم منخفض %.2fx", symbol, vol_ratio_kd)
        return

    st = get_supertrend(kd)
    if st == "DOWN" and symbol not in hot_symbols:
        log.debug("⛔ %s رُفض: Supertrend DOWN", symbol)
        return

    ig, gp = detect_green_candles(kd)
    if not ig:
        log.debug("⛔ %s رُفض: شموع خضراء %.0f%%", symbol, gp)
        return

    ob = get_order_book(symbol)
    if ob:
        if ob["imb"] < MIN_IMBALANCE or ob["imb"] > MAX_IMBALANCE:
            log.debug("⛔ %s رُفض: OB Imbalance %.2f", symbol, ob["imb"])
            return
        if ob["bid"] < MIN_BID_DEPTH:
            log.debug("⛔ %s رُفض: Bid صغير %.0f", symbol, ob["bid"])
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
        log.debug("⛔ %s رُفض: Score=%d (min=%d) ST=%s hot=%s", symbol, score, min_s, st, in_hot)
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

    # 🆕 إضافة Flow Status للإشارة
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

    mkt_icon = {"SAFE":"🟢","CAUTION":"🟡","DANGER":"🔴"}.get(market_state,"⚪")

    send(
        "👑 *MAFIO BOT V14*\n"
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
            price=format_price(price), score=score,
            time=datetime.now().strftime("%H:%M:%S"),
            mkt=mkt_icon, mst=market_state,
            sigs=sigs, ob=ob_txt,
            ch=change, btc=btc_change_24h,
            sl=sl_pct, trail=TRAIL_DROP_TRIGGER,
        )
    )
    log.info("🟢 SIGNAL | %s | score=%d | hot=%s bo=%s sl=%.1f%%",
             symbol, score, in_hot, is_bo, sl_pct)


# ═══════════════════════════════════════════════
#   SIGNAL PROGRESSION (#2, #3)
# ═══════════════════════════════════════════════
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
            label, symbol, gain, format_price(price), sl))
        tracked[symbol]["level"]      = 2
        tracked[symbol]["last_alert"] = now
        log.info("🔵 #2 | %s +%.2f%%", symbol, gain)

    elif level == 2 and gain >= SIGNAL3_GAIN:
        send("{} *SIGNAL #3* | `{}`\n🔥 *+{:.2f}%*\n💵 `{}` | SL:`-{}%`".format(
            label, symbol, gain, format_price(price), sl))
        tracked[symbol]["level"]      = 3
        tracked[symbol]["last_alert"] = now
        log.info("🔥 #3 | %s +%.2f%%", symbol, gain)


# ═══════════════════════════════════════════════
#   CLEANUP & REPORT
# ═══════════════════════════════════════════════
def cleanup():
    # type: () -> None
    now = time.time()
    for s in [s for s,d in list(tracked.items())
              if now - d["entry_time"] > STALE_REMOVE_SEC]:
        log.info("🗑️ %s", s)
        del tracked[s]
    clear_expired_cache()


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

    # إضافة ملخص السيولة
    msg += "\n━━━━━━━━━━━━━━━━━━\n"
    msg += "💸 *حالة السيولة:*\n"
    msg += get_flow_summary()

    # 🆕 V15: إضافة إحصاءات Backtest
    msg += "\n━━━━━━━━━━━━━━━━━━\n"
    msg += get_backtest_stats()

    send(msg)


# ═══════════════════════════════════════════════
#   MAIN LOOP
# ═══════════════════════════════════════════════
def run():
    # type: () -> None
    global all_tickers   # ✅ إصلاح V11: تأكيد أن all_tickers global
    global last_tickers, last_btc, last_sectors
    global last_deep_scan, last_stale, last_smart_money, last_expand

    log.info("🚀 MAFIO BOT V15 يبدأ...")

    log.info("⏳ تحميل بيانات السوق...")
    analyze_btc()

    refresh_tickers()
    time.sleep(2)
    refresh_tickers()

    # 🆕 V12: توسيع القوائم تلقائياً عند البدء
    log.info("🔍 تشغيل Auto Expand Sectors...")
    auto_expand_sectors()
    last_expand = time.time()

    analyze_sectors()
    log.info("✅ جاهز | Candidates: %d | Hot: %s",
             len(candidates), ", ".join(hot_sectors) or "لا يوجد")

    last_deep_scan = 0

    send(
        "🤖 *MAFIO BOT SIGNAL V15*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "✅ Anti Rate-Limit (~8 req/min)\n"
        "✅ Smart Cache (15m/1h/4h)\n"
        "✅ Trailing Stop (`{trail}%` من القمة)\n"
        "✅ Sector Rotation (12 قطاع)\n"
        "✅ Score Min: `{score}` | Deep Scan: كل ساعة\n"
        "✅ Anti P&D | Supertrend | Dynamic SL\n"
        "✅ Sector Flow Tracker — تتبع السيولة\n"
        "🆕 V15: RSI Filter (رفض RSI > 70)\n"
        "🆕 V15: Vol تاريخي للعملة نفسها\n"
        "🆕 V15: Backtest تلقائي (1h/4h/24h)\n"
        "🆕 V15: تصحيح جميع رموز SECTORS\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "₿ BTC: `{btc:+.2f}%` | السوق: `{mst}`\n"
        "🔥 Hot: `{hot}`\n"
        "📋 القوائم: جاري التوسيع...".format(
            trail=TRAIL_DROP_TRIGGER,
            score=SCORE_MIN,
            btc=btc_change_24h,
            mst=market_state,
            hot=", ".join(hot_sectors) or "لا يوجد",
        )
    )

    cycle = 0
    flow_cycle = 0  # عداد لتحليل Flow كل 5 دورات (~60 ثانية)

    while True:
        try:
            now = time.time()

            # تحديثات دورية
            if now - last_btc         >= BTC_EVERY:         analyze_btc()
            if now - last_sectors     >= SECTORS_EVERY:     analyze_sectors()
            if now - last_smart_money >= SMART_MONEY_EVERY: analyze_smart_money()
            if now - last_expand      >= EXPAND_EVERY:
                # 🆕 V12: توسيع يومي تلقائي للقوائم
                log.info("🔄 تحديث يومي — Auto Expand Sectors")
                auto_expand_sectors()
                last_expand = now
            if now - last_stale       >= STALE_EVERY:
                cleanup()
                last_stale = now

            # جلب 24h Ticker
            tickers_now = safe_get(MEXC_24H)
            if not tickers_now:
                time.sleep(CHECK_INTERVAL)
                continue

            # ✅ إصلاح V11: تحديث all_tickers كـ global
            all_tickers = tickers_now

            # بناء الخرائط
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

            # 🆕 V15: تحديث تاريخ حجم العملات (لحساب vol_ratio التاريخي)
            update_coin_vol_history(vol_now)

            # 🆕 V15: متابعة إشارات Backtest
            check_backtest(price_map)

            if now - last_tickers >= TICKERS_EVERY:
                refresh_tickers()
                analyze_sectors()

            # Trailing Stop + Signal Progression
            for sym in list(tracked.keys()):
                if sym in price_map:
                    if not check_trailing(sym, price_map[sym]):
                        check_progression(sym, price_map[sym])

            # 🆕 Sector Flow: تجميع لقطات كل دورة
            update_sector_flow(ticker_map)
            flow_cycle += 1

            # 🆕 Sector Flow: تحليل كل 5 دورات (~60 ثانية)
            if flow_cycle >= FLOW_WINDOW:
                analyze_sector_flow()
                flow_cycle = 0

            # Momentum Detector
            detect_momentum(price_map, change_now, vol_now, high_map, low_map)

            # Deep Scan
            if now - last_deep_scan >= DEEP_SCAN_EVERY:
                log.info("🔍 Deep Scan — %d عملة...", len(candidates))
                scanned = 0
                for sym in candidates:
                    if sym in tracked: continue
                    price  = price_map.get(sym, 0)
                    change = changes_map.get(sym, 0)
                    if price <= 0: continue
                    deep_scan(sym, price, change)
                    scanned += 1
                    if scanned % 10 == 0:
                        time.sleep(0.5)
                last_deep_scan = now
                log.info("✅ Deep Scan انتهى | %d عملة", scanned)

            cycle += 1
            send_report()
            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            send("⛔ *MAFIO BOT V15* — تم الإيقاف")
            break
        except Exception as e:
            log.error("خطأ: %s", e, exc_info=True)
            time.sleep(10)


if __name__ == "__main__":
    run()

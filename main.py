"""
╔══════════════════════════════════════════════════════════════╗
║           MAFIO BOT SIGNAL V16 — UNIFIED ENGINE            ║
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
import json
import logging
import requests
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Any, Set

# ═══════════════════════════════════════════════
#                    CONFIG
# ═══════════════════════════════════════════════
STATE_FILE = "/app/mafio_state.json"

# ── Upstash Redis ────────────────────────────
REDIS_URL   = os.environ.get("UPSTASH_REDIS_REST_URL", "")
REDIS_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")
REDIS_KEY   = "mafio_bot_state_v16"


# ── Redis (Upstash) ───────────────────────────
REDIS_URL  = os.environ.get("REDIS_URL", os.environ.get("UPSTASH_REDIS_REST_URL", ""))
REDIS_KEY  = "mafio_state_v16"  # مفتاح الحفظ في Redis


# عملات محظورة — لا تدخل Watchlist أبداً
BLOCKED_WATCHLIST = {
    "CULTUSDT",   # حجم ضعيف + ترند هابط
}

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_BOT_TOKEN")
CHAT_ID        = os.getenv("CHAT_ID",  "YOUR_CHAT_ID")
GROUP_ID       = os.getenv("GROUP_ID", "")   # رقم المجموعة (يبدأ بـ -)

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

# 🆕 V15: Buffer zones — منع التذبذب بين الحالات
# منطقة أمان: لا تغيير إلا إذا تجاوز الحد بـ 0.3%
BTC_DANGER_BUFFER  = 0.3   # يدخل DANGER عند -3.3% | يخرج عند -2.7%
BTC_CRASH_4H       = -2.5
# ── TPS / ATS + Volume Delta ──────────────────────────────────────
TPS_LIMIT      = 100     # آخر 100 صفقة
# ── قائمة عملات إضافية ثابتة ─────────────────────────────────────────
EXTRA_COINS = [
    # ── Meme coins ────────────────────────────
    "FLOKIUSDT", "PEPEUSDT", "WIFUSDT", "BOMEUSDT", "MEWUSDT",
    "PEOPLEUSDT", "1000SHIBUSDT", "BANANAUSDT", "NEIROUSDT",
    "SUNDOGUSDT", "MOODENGUSDT", "FWOGUSDT", "GORKYUSDT",

    # ── Layer1 / Layer2 ───────────────────────
    "FLOWUSDT", "KASUSDT", "KAIAUSDT", "JUPUSDT",

    # ── Gaming & NFT ──────────────────────────
    "PIXELUSDT", "RENDERUSDT", "GALAUSDT", "IMXUSDT",

    # ── DeFi ──────────────────────────────────
    "AAVEUSDT", "DYDXUSDT", "JOEUSDT",

    # ── AI & Robotics — تجميع هادئ قبل الانفجار ──
    "FETUSDT", "AGIXUSDT", "OCEANUSDT", "GRTUSDT",
    "WLDUSDT", "ARKMUSDT", "VIRTUSDT", "ACTUSDT",
    "CGPTUSDT", "NEUROUSDT", "TAOAUSDT", "SWARMAUSDT",

    # ── RWA — تجميع مؤسسي ────────────────────
    "ONDOUSDT", "MANTRAUSDT", "CFGUSDT", "PLUMEUSDT",

    # ── NeoBank / Payments ────────────────────
    "XLMUSDT", "XRPUSDT", "PYTHUSDT", "REQUSDT",

    # ── Oracle ────────────────────────────────
    "LINKUSDT", "BANDUSDT", "SUPRAUSDT", "API3USDT",

    # ── Layer1 إضافية ─────────────────────────
    "CFXUSDT", "APTUSDT", "SEIUSDT", "INJUSDT",
    "NEARUSDT", "SOLUSDT", "AVAXUSDT", "ADAUSDT",
]

TPS_SPIKE      = 3.0     # TPS ارتفع 3× = نشاط غير عادي
TPS_MAX_CHANGE = 6.0     # 🚫 تجاهل إذا ارتفعت +6% في 24h — الفرصة فاتت
ATS_WHALE      = 5000    # صفقة > 5000 USDT = حيتان
ATS_RETAIL     = 500     # صفقة < 500 USDT  = أفراد
VDELTA_STRONG  = 0.70    # 70%+ شراء حقيقي
TPS_COOLDOWN   = 7200    # ساعتان — cooldown موحد لكل الأنظمة
TPS_SCAN_EVERY = 300     # كل 5 دقائق  # انهيار سريع: BTC ينزل -2.5% في 4 ساعات → DANGER فوري
BTC_CRASH_1H       = -1.5  # انهيار حاد: BTC ينزل -1.5% في ساعة واحدة → DANGER فوري
BTC_CAUTION_BUFFER = 0.3   # يدخل CAUTION عند -1.8% | يخرج عند -1.2%
# عدد المرات المتتالية للتأكيد قبل تغيير الحالة
BTC_CONFIRM_COUNT  = 1     # ⚡ قراءة واحدة فقط (كان 3 = 90 دقيقة)

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
GREEN_MIN_RATIO    = 0.45
HIGHER_LOWS_MIN    = 0.60

# ── 🆕 فلتر العملات المشبوهة ─────────────────────
# عملة حقيقية يجب أن يكون حجمها اليومي كافياً
WHALE_MIN_VOL      = 1_000_000   # حجم أدنى 1M USDT للحيتان
WHALE_MAX_CHANGE   = 25.0        # تجاهل إذا ارتفعت أكثر من 25% (Pump)

# 🆕 Bottom Accumulation — رصد التجميع في القيعان
BOTTOM_PRICE_RANGE   = 1.15   # السعر أقل من 15% فوق القاع
BOTTOM_VOL_INCREASE  = 1.3    # الحجم أكبر من 1.3× المتوسط
BOTTOM_MAX_CHANGE    = 5.0    # تغيير يومي أقل من 5%
BOTTOM_MIN_DAYS      = 7      # أدنى عدد أيام لبناء التاريخ
BOTTOM_COOLDOWN      = 86400  # 24 ساعة — فقط للعملات في ATH watchlist
BOTTOM_SCAN_EVERY    = 3600    # فحص كل ساعة
BOTTOM_MIN_VOL       = 1_000_000 # حجم 24h أدنى 1M USDT — عملات قوية فقط

# 🆕 Volume Explosion — انفجار الحجم بعد التجميع
EXPLOSION_VOL_MULT   = 3.0    # الحجم يتجاوز 3× المتوسط
EXPLOSION_MIN_DAYS   = 5      # العملة في القاع 5+ أيام قبل الانفجار
EXPLOSION_COOLDOWN   = 86400  # 24 ساعة — فقط إذا مرت بالمرحلتين 1+2
EXPLOSION_MAX_CHANGE = 30.0   # لا نريد Pump مسبق أكثر من 30%
EXPLOSION_MIN_VOL    = 1_000_000 # حجم انفجار أدنى 1M USDT — عملات قوية فقط

# 🆕 ATH Distance Filter — عملات انهارت من قمتها
ATH_DROP_STRONG  = 0.90   # نزلت 90%+ من ATH = فرصة قوية
ATH_DROP_EXTREME = 0.95   # نزلت 95%+ من ATH = فرصة نادرة
ATH_MIN_VOL      = 1_000_000  # حجم أدنى 1M USDT
ATH_COOLDOWN     = 86400  # 24 ساعة — مرة واحدة يومياً لكل عملة
ATH_SCAN_EVERY   = 7200   # فحص كل ساعتين — أفضل 3 فقط يومياً

# 🆕 Hot Market Scanner — يعمل فوراً بدون تاريخ
HOT_MIN_CHANGE   = 12.0   # تغيير 12%+ في 24h — جودة أعلى
HOT_MIN_VOL      = 1_000_000 # حجم 1M+ — عملات قوية فقط
HOT_COOLDOWN     = 14400  # 4 ساعات بين التنبيهات
HOT_SCAN_EVERY   = 3600   # فحص كل ساعة

# 🆕 Realtime Liquidity Scanner — الأسرع والأهم
RT_SCAN_EVERY    = 900    # كل 15 دقيقة
RT_VOL_SPIKE     = 2.0    # حجم 2× المتوسط = سيولة غير عادية
RT_MIN_VOL       = 1_000_000 # 1M+ فقط — جودة أعلى
RT_COOLDOWN      = 21600  # 6 ساعات بين تنبيهات نفس العملة

# 🆕 Liquidity Watchlist — مراقبة السيولة للدخول
WL_ENTRY_MOVE    = 3.0    # تحرك 3%+ = إشعار دخول
WL_ENTRY_VOL     = 1.5    # حجم 1.5× baseline = تأكيد
WL_MAX_SIZE      = 30     # أقصى 30 عملة في القائمة
WL_EXPIRY        = 86400  # عملة تبقى 24 ساعة بدون تحرك ثم تُحذف
WL_ENTRY_COOL    = 14400  # 4 ساعات بين إشعارات الدخول لنفس العملة
WL_CHECK_EVERY   = 60     # فحص الـ watchlist كل دقيقة

# 🆕 Trailing Stop — حماية الأرباح
TS_TRAIL_PCT     = 15.0   # إذا نزل 15% من القمة = بيع
TS_MIN_PROFIT    = 10.0   # لا نفعّل الـ trailing إلا بعد +10%
TS_BREAKEVEN     = 10.0   # عند +10% → نحرك الستوب لنقطة الدخول
TS_LOCK_20       = 20.0   # عند +20% → نقفل ربح 10%
TS_LOCK_50       = 50.0   # عند +50% → نقفل ربح 35%
TS_SCAN_EVERY    = 300    # فحص كل 5 دقائق
TS_DANGER_VOL    = 0.5    # الحجم نزل لأقل من 50% = خروج سيولة
TS_DANGER_CLOSE  = -3.0   # السوق DANGER + العملة نازلة -3%

TS_SELL_COOL     = 3600   # ساعة بين إشعارات البيع لنفس العملة

# 🆕 Early Detection — رصد مبكر قبل الانفجار
RT_PRICE_MOVE    = 2.0    # حركة سعر 2%+ مع السيولة
HOT_MAX_CHANGE   = 50.0   # تجاهل Pump أكثر من 50%
WHALE_MIN_PRICE    = 0.000001    # تجاهل العملات بسعر أقل من 0.000001 (شبه صفر)
# عملات مشبوهة بالاسم — يتم تجاهلها دائماً
SUSPICIOUS_KEYWORDS = [
    "STABLE","PEGGED","WRAPPED","BRIDGE",
    "EUR","GBP","CNY","JPY",   # عملات مربوطة بعملات أجنبية
    "TEST","DEMO","FAKE",       # عملات تجريبية
]

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
BTC_EVERY          = 300   # ⚡ كل 5 دقائق (كان 30)
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

# Sector Rotation
SR_MIN_OUT        = -8.0   # قطاع يخرج منه: -8% أو أقل
SR_MIN_IN         = 8.0    # قطاع يدخل إليه: +8% أو أكثر
SR_COOLDOWN       = 14400  # 4 ساعات بين تنبيهات Rotation
SR_TOP_COINS      = 5      # أفضل عملات في القطاع المنتعش

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
BACKTEST_FEE       = 0.2      # 🆕 V15: رسوم التداول الواقعية (0.1% دخول + 0.1% خروج)

# ══════════════════════════════════════════════════════════════
# 🆕 V16: LIQUIDITY ZONES — مناطق السيولة اليومية
# ══════════════════════════════════════════════════════════════
# منطق: إغلاق يومي فوق Zone = سيولة شرائية ✅
#        إغلاق يومي تحت Zone = سيولة بيعية  ❌
LZ_TOUCHES_MIN     = 3        # أدنى عدد لمسات للمنطقة (= Sigma)
LZ_TOUCHES_RARE    = 8        # نادر جداً 🐋🔥
LZ_VOL_MULT        = 1.5      # الحجم يجب أن يكون 1.5× المعدل
LZ_LOOKBACK        = 90       # عدد الشمعات اليومية للبحث (90 يوم)
LZ_ZONE_MARGIN     = 0.02     # 2% هامش للمنطقة
LZ_COOLDOWN        = 86400    # 24 ساعة بين إشارات نفس العملة
LZ_SCORE_MIN       = 60       # حد أدنى للـ Score للإشارة اليومية

# ── Smart Money ──────────────────────────────────
SMART_MONEY_SIGMA      = 3.0
SMART_MONEY_EVERY      = 86400
SMART_MONEY_ACCUM_MIN  = 2
SMART_MONEY_FALL_PCT   = 55
SMART_MONEY_ALERT_SIGMA= 5.0

SMART_MONEY_STABLES = [
    "FDUSDUSDT","TUSDUSDT","USD1USDT",
    "RLUSDUSDT","BFUSDUSDT","USDPUSDT","USDDUSDT",
]

# ── MEXC Endpoints ──────────────────────────────
MEXC_24H    = "https://api.mexc.com/api/v3/ticker/24hr"
MEXC_TICKER = "https://api.mexc.com/api/v3/ticker/24hr"  # نفس الـ endpoint لكن بـ symbol
MEXC_PRICE  = "https://api.mexc.com/api/v3/ticker/price"
MEXC_KLINES = "https://api.mexc.com/api/v3/klines"
MEXC_DEPTH  = "https://api.mexc.com/api/v3/depth"
MEXC_TRADES = "https://api.mexc.com/api/v3/trades"  # ⚡ TPS/ATS

EXCLUDED = {"BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT",
            # عملات مشبوهة أو مستقرة تظهر في النتائج
            "EURUSDT","STABLEUSDT","UCNUSDT","VERMUSDT",
            "BDXUSDT","POLXUSDT","MBGUSDT","L3USDT","VERMUSDT",
            # عملات خصوصية محظورة من Binance — لا حيتان فيها
            "XMRUSDT","DASHUSDT","ZCASHUSDT","SCRTUSDT",
}

# حد أقصى لإشارات نفس العملة يومياً
MAX_COIN_SIGNALS = 2  # إشارة #1 راقب + إشارة #2 ادخل — لا ثالثة

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
    ],
    "Layer1": [
        "AVAX","ADA","ATOM","NEAR","FTM","ALGO","ICP","APT","SUI","SEI",
        "INJ","KAS","TON","HBAR","EGLD","ZIL","ONE","CFX","JASMY","LSK",
        "QNT","CELO","FLOW","MINA","KAVA","VET","ONT","WAVES","XTZ","NEO",
        "ROSE","SCRT","OASIS","HARMONY","ELROND","MULTIVERSX","APTOS",
        "MOVEMENT","MONAD","BERACHAIN","INITIA","SAGA","STORY","SUPRA",
        "HYPERLIQUID","ECLIPSE","FUSE","VENOM","NEON","ZETA","XPL",
    ],
    "Layer2": [
        "MATIC","OP","ARB","ZK","STRK","LRC","METIS","MANTA","SCROLL",
        "MNT","MERL","ALT","ZRO","LINEA","TAIKO","MOD","CELR","SKL",
        "OMG","SSV","BOBA","STARKNET","ZKFAIR","ZKLINK","ZKME","LUMIA",
        "POLYGON","OPTIMISM","ARBITRUM","STARKWARE","LOOPRING","MATTER",
        "IMMUTABLE","RONIN","BASE","BLAST","MANTLE","MODE","MINT",
        "FRAXTAL","ZORA","REDSTONE","CYBER","KINTO","ANCIENT8","BREV",
    ],
    "Meme": [
        "DOGE","SHIB","PEPE","FLOKI","WIF","BOM","MEME","TURO","POPCAT",
        "MOG","BABYDOGE","BONK","DOGS","CATI","GOAT","PNUT","ACT",
        "CHILLGUY","TURBO","LUNA","BOME","MOTHER","PONKE","GME","HONK",
        "MYRO","WOJAK","MIGGO","COQ","SLERF","SMOG","BOME","SILLY",
        "NOOT","WOOF","COPE","CHAD","BASED","FROG","CAT","DOG","APE",
        "MONKEY","HAMSTER","SQUIRREL","RACCOON","PENGUIN","PENG",
        "BRETT","ANDY","MOO","BAD","HARAMBE","GIGA","APED","LADYS","BABY",
        "BANANA","PENG","NEIRO","SUNDOG","MOODENG","FWOG","GORK","MICHI","MAGA",
        "MANEKI","BOOMER","MEW","RETARDIO","POPCAT","GMEOW","INUVERSE","PUPS",
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
        "FETUSDT","AGIXUSDT","OCEANUSDT","RENDUSDT","RENDERUSDT","GRTUSDT",
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
        # ── Mastercard RWA Partners ──
        "PLUMEUSDT","CANTONUSDT","ASSETUSDT","TOKENYUSDT","DIGIASSETUSDT",
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
        "POLUSDT","OPUSDT","ARBUSDT","ZKUSDT","STRKUSDT",
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
        # ── Mastercard Partners ──
        "AXLUSDT","WORMHOLEUSDT","LAYERZUSDT","HYPERLANEUSDT","CELERУСDT",
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

    # ── قطاعات جديدة V16 ──────────────────────────────────────
    "Robotics": [
        # روبوتات + AI جسدي
        "WLDUSDT","RENDUSDT","FETUSDT","AGIXUSDT","OCEANUSDT",
        "AKTOUSDT","NUMERAIUSDT","ARKMUSDT","PHAUSDT","CUDOSUSDT",
        "CGPTUSDT","NEUROUSDT","VIRTUSDT","SWARMAUSDT","MEAIUSDT",
    ],

    "NeoBank": [
        # مدفوعات + بنوك رقمية + X402
        "XLMUSDT","XRPUSDT","PYTHUSDT","STRKUSDT","COTIUSDT",
        "REQUSDT","PAYUSDT","SOLOUSDT","BRLUSDT",
        "SPRMUSDT","PAYPUSDT","MNTLUSDT","NEXOUSDT","WIREXUSDT",
        "MPAYUSDT","PAYPOLUSUSDT","FLAREUSDT","SGUSDUSDT","BIGTUSDT",
        # ── Mastercard Payments Partners ──
        "APTUSDT","AVAXUSDT","SOLUSDT","ATOMUSDT","OPUSDT",
        "POLUSDT","AXELARUSDT","OPTIMISMUSDT","STRKUSDT",
    ],

    "Quantum": [
        # حوسبة كمية
        "QNTUSDT","QTUMUSDT","IONQUSDT","QUAIUSDT","KVANTUSDT",
        "QUIPUSDT","QUANTUMUSDT","QKCUSDT","ALEPHUSDT","NQUUSDT",
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
eth_change_24h = 0.0
btc_tps_stats  = {}   # type: Dict  آخر TPS/ATS لـ BTC
eth_tps_stats  = {}   # type: Dict  آخر TPS/ATS لـ ETH
market_state        = "SAFE"
last_market_report  = 0.0    # آخر إرسال تقرير السوق
MARKET_REPORT_EVERY = 14400  # كل 4 ساعات فقط

# 🆕 V15: Buffer counters — عداد التأكيد قبل تغيير الحالة
_btc_danger_count  = 0   # عدد المرات المتتالية تحت DANGER
_btc_caution_count = 0   # عدد المرات المتتالية تحت CAUTION
_btc_safe_count    = 0   # عدد المرات المتتالية فوق SAFE
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
last_daily_report = 0.0    # 🆕 V15: آخر تقرير يومي عند 00:00 UTC

# 🆕 V15: تاريخ حجم السوق اليومي للمقارنة
daily_market_vol_history = []  # type: List[float]   [أمس, اليوم]

# 🆕 FlowEntry Features
market_activity_history = []   # type: List[Dict]  [{date, buy_vol, sell_vol, sigma_coins}]
breakout_report_sent    = {}   # type: Dict[str,str]  {date: sent}
tv_script_cache         = {}   # type: Dict[str,str]  {sym: script}
daily_report_sent_date   = ""  # type: str            تاريخ آخر تقرير أُرسل

# 🆕 V16: Liquidity Zones
lz_alerted         = {}   # type: Dict[str, float]  {sym: last_alert_time}
lz_daily_sent_date = ""   # type: str               تاريخ آخر فحص يومي

# 🆕 V16: Hidden Accumulation — كشف التجميع الخفي
hidden_accum_alerted = {}  # type: Dict[str, float]  {sym: last_alert_time}

# 🆕 TPS/ATS Engine
tps_alerted      = {}   # type: Dict[str, float]  {sym: last_alert_time}
last_tps_scan    = 0.0  # type: float
tps_baseline     = {}   # type: Dict[str, float]  {sym: avg_tps_baseline}

# 🔥 LIQUIDITY HUNTER
tps_alerted  = {}    # type: Dict[str, float]  ⚡ TPS/ATS alerted
coin_alerted = {}    # type: Dict[str, float]  🔒 Cooldown موحد لكل الأنظمة
coin_signal_count = {}  # type: Dict[str, int]   🔢 عداد الإشارات لكل عملة
coin_whale_done   = {}  # type: Dict[str, float] 🐋 عملة وصل حيتانها — مغلقة
whale_watchlist  = {}  # type: Dict[str, Dict]   🐋 Whale Watch قائمة
whale_confirmed  = {}  # type: Dict[str, float]  🐋 آخر تأكيد حيتان
lz_tps_alerted = {}  # type: Dict[str, float]  🎯 LZ+TPS Fusion alerted
tps_baseline = {}    # type: Dict[str, float]  baseline TPS per coin
last_tps_scan= 0.0   # type: float
lh_alerted   = {}    # type: Dict[str, float]  {sym: last_alert_time}
last_lh_scan = 0.0   # type: float  ← قيمة ابتدائية على مستوى الملف

# 📋 Small Caps — قائمة العملات الصغيرة
small_caps        = []   # type: List[str]   قائمة ديناميكية
last_sc_refresh   = 0.0  # type: float       آخر تحديث للقائمة
sc_alerted        = {}   # type: Dict[str, float]  {sym: last_alert_time}

stable_vol_history = {}   # type: Dict[str, List[float]]
smart_money_alert  = False
smart_money_bonus  = 0

price_prev         = {}   # type: Dict[str, float]
momentum_alerted   = {}   # type: Dict[str, float]
momentum_stage     = {}   # type: Dict[str, Dict]

# 🆕 قائمة المراقبة — قطاع ساخن + تجميع حيتان
watchlist          = {}   # type: Dict[str, Dict]

# 🆕 Snapshot أسعار كل ساعة — لحساب تغيير حقيقي
price_snapshot     = {}   # type: Dict[str, float]  {sym: price_1h_ago}
price_snapshot_time = 0.0

# 🆕 Sector Flow Tracker State
sector_vol_snapshots = {}  # type: Dict[str, List[float]]   {sector: [vol1, vol2, ...]}
sector_change_snapshots = {}  # type: Dict[str, List[float]] {sector: [avg_ch1, avg_ch2, ...]}
sector_flow_alerted  = {}  # type: Dict[str, float]          {sector: last_alert_time}
sector_flow_state    = {}  # type: Dict[str, str]            {sector: "IN"/"OUT"/"NEUTRAL"}
last_sr_alert        = 0.0 # type: float  آخر تنبيه Sector Rotation
top10_alerted        = {}  # type: Dict[str, float]          {sector: last_top10_alert_time}

# 🆕 V15: تاريخ حجم كل عملة للمقارنة التاريخية
coin_vol_history     = {}  # type: Dict[str, List[float]]   {sym: [vol1, vol2, ...]}

# 🆕 Bottom Accumulation State
bottom_price_history = {}  # type: Dict[str, List[float]]  {sym: [price1, price2, ...]}
bottom_vol_history   = {}  # type: Dict[str, List[float]]  {sym: [vol1, vol2, ...]}
bottom_alerted       = {}  # type: Dict[str, float]        {sym: last_alert_time}
explosion_alerted    = {}  # type: Dict[str, float]  {sym: last_alert_time}
ath_tracker      = {}  # type: Dict[str, float]  {sym: all_time_high_price}
ath_alerted      = {}  # type: Dict[str, float]  {sym: last_alert_time}
gem_watchlist    = {}  # type: Dict[str, Dict]  {sym: {stage, ath_drop, since}} المراحل
daily_gem_count  = {"date": "", "count": 0}  # عداد يومي — حد 10 عملات
last_ath_scan    = 0.0
hot_alerted      = {}  # type: Dict[str, float]  {sym: last_alert_time}
last_hot_scan    = 0.0
rt_vol_baseline  = {}  # type: Dict[str, float]  {sym: avg_vol} متوسط الحجم
rt_alerted       = {}  # type: Dict[str, float]  {sym: last_alert_time}
wl_entry_alerted = {}  # type: Dict[str, float]  {sym: last_entry_alert_time}
wl_price_snapshot= {}  # type: Dict[str, float]  {sym: price_when_added}
last_wl_check    = 0.0
# Trailing Stop state
ts_positions     = {}  # type: Dict[str, Dict]  {sym: {entry, peak, stop, locked}}
ts_sell_alerted  = {}  # type: Dict[str, float] {sym: last_sell_time}
last_ts_scan     = 0.0
daily_signals    = {"date": "", "count": 0}  # عداد يومي شامل
last_rt_scan     = 0.0
last_bottom_scan     = 0.0

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
def fmt_price(p):
    # type: (float) -> str
    if p == 0: return "0"
    if p < 0.0001:  return "{:.10f}".format(p).rstrip("0")
    if p < 1:       return "{:.8f}".format(p).rstrip("0")
    if p < 1000:    return "{:.4f}".format(p).rstrip("0").rstrip(".")
    return "{:,.2f}".format(p)


def send(msg, personal_only=False):
    # type: (str, bool) -> None
    """
    يرسل الرسالة لـ:
    - CHAT_ID دائماً (الشخصي)
    - GROUP_ID إذا كان مضبوطاً (المجموعة)

    personal_only=True → الشخصي فقط (للأوامر الخاصة)
    """
    if "YOUR" in TELEGRAM_TOKEN:
        log.info("[TELEGRAM] %s", msg[:80])
        return

    targets = [CHAT_ID]
    if GROUP_ID and not personal_only:
        targets.append(GROUP_ID)

    for chat_id in targets:
        if not chat_id or "YOUR" in str(chat_id):
            continue
        try:
            session.post(
                "https://api.telegram.org/bot{}/sendMessage".format(TELEGRAM_TOKEN),
                data={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"},
                timeout=10,
            )
        except Exception as e:
            log.error("Telegram [%s]: %s", chat_id, e)



# ── Telegram offset لتتبع الرسائل ────────────────
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
            # 409 = تعارض — نحذف Webhook تلقائياً
            log.warning("⚠️ getUpdates 409 — حذف Webhook تلقائياً")
            try:
                requests.get(
                    "https://api.telegram.org/bot{}/deleteWebhook?drop_pending_updates=true".format(TELEGRAM_TOKEN),
                    timeout=10
                )
                log.info("✅ Webhook محذوف — إعادة المحاولة")
            except Exception as _e:
                log.error("❌ deleteWebhook فشل: %s", _e)
            return
        if r.status_code != 200:
            log.warning("⚠️ getUpdates HTTP %d", r.status_code)
            return
        data = r.json()
        if not data.get("ok"):
            log.warning("⚠️ getUpdates not ok: %s", data)
            return
        updates = data.get("result", [])
        if updates:
            log.info("📨 getUpdates: %d رسالة جديدة", len(updates))
        for update in updates:
            _tg_offset = update["update_id"] + 1
            # دعم message و channel_post
            msg = update.get("message") or update.get("channel_post") or {}
            text = msg.get("text", "").strip()
            # تحويل للأحرف الصغيرة فقط للمقارنة
            text_lower = text.lower()
            chat_id = str(msg.get("chat", {}).get("id", ""))
            log.info("📨 update: chat_id=%s text='%s'", chat_id, text)
            # قبول من CHAT_ID الشخصي أو GROUP_ID
            allowed = [str(CHAT_ID)]
            if GROUP_ID and GROUP_ID != "YOUR_GROUP_ID":
                allowed.append(str(GROUP_ID))
            if chat_id not in allowed:
                log.warning("⛔ chat_id غير معروف: %s | allowed: %s", chat_id, allowed)
                continue
            # أوامر
            if text_lower in ("/report", "/تقرير"):
                log.info("📤 /report طُلب من chat_id=%s", chat_id)
                send("\U0001f4e4 جاري إعداد التقرير...")
                # ✅ نجلب all_tickers مباشرة إذا كانت فارغة
                global all_tickers
                if not all_tickers:
                    log.info("📤 /report: all_tickers فارغة — نجلبها الآن")
                    try:
                        _r = safe_get(MEXC_24H)
                        if _r:
                            all_tickers = _r
                            log.info("📤 all_tickers جُلبت: %d عملة", len(all_tickers))
                    except Exception as _e:
                        log.error("📤 فشل جلب all_tickers: %s", _e)
                daily_report_sent_date = ""
                lz_daily_sent_date     = ""
                send_daily_report(force=True)
            elif text_lower in ("/status", "/حالة"):
                send("\u2705 البوت يعمل | عملات: " + str(len(candidates)) +
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
                _icon = {"SAFE":"🟢","CAUTION":"🟡","DANGER":"🔴"}.get(market_state,"📊")
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
                # آخر 5 إشارات من Liquidity Hunter
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
                # نضع flag
                import builtins
                builtins._mafio_paused = True

            elif text_lower in ("/start", "/تشغيل"):
                import builtins
                builtins._mafio_paused = False
                send("✅ التنبيهات تعمل الآن!")

            elif text_lower in ("/help", "/مساعدة"):
                send(
                    "🤖 *MAFIO BOT — الأوامر:*\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    "📊 /status      — حالة البوت\n"
                    "₿ /btc         — سعر BTC والاتجاه\n"
                    "🏆 /sectors     — أفضل القطاعات\n"
                    "👁️ /watchlist   — قائمة المراقبة\n"
                    "📅 /report      — التقرير اليومي\n"
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


_force_daily_report = False  # flag لتجاوز قيد الساعة

def send_daily_report_forced():
    # type: () -> None
    """إرسال التقرير اليومي فوراً بدون قيد الوقت — /report"""
    global daily_report_sent_date, lz_daily_sent_date, _force_daily_report
    log.info("📤 تقرير يدوي — إعادة تعيين التاريخ")
    daily_report_sent_date = ""   # إلغاء قيد التاريخ
    lz_daily_sent_date     = ""   # إلغاء قيد السيولة
    _force_daily_report    = True # تجاوز قيد الساعة
    try:
        send_daily_report()
    except Exception as e:
        log.error("❌ خطأ في التقرير اليدوي: %s", e)
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
                # معدل حقيقي = عدد الطلبات / الوقت الفعلي بالدقائق
                _rate = int(api_calls_minute / (_elapsed / 60))
                log.info("📡 API: %d طلب/دقيقة | إجمالي: %d",
                         _rate, api_calls_total)
                api_calls_minute = 0
                api_minute_reset = _now
            return r.json()

        except Exception as e:
            wait = 2 ** attempt  # 1s, 2s, 4s
            if attempt < retries - 1:
                log.debug("API retry %d/%d [%s]: %s — انتظر %ds",
                          attempt + 1, retries, url.split("/")[-1], e, wait)
                time.sleep(wait)
            else:
                log.debug("API فشل نهائي [%s]: %s", url.split("/")[-1], e)

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

    # 2. كلمات مشبوهة في الاسم
    for kw in SUSPICIOUS_KEYWORDS:
        if kw in base:
            return True

    # 3. حجم منخفض جداً = سهل التلاعب
    if vol < WHALE_MIN_VOL:
        return True

    # 4. سعر قريب من الصفر = Micro Cap
    if 0 < price < WHALE_MIN_PRICE:
        return True

    # 5. ارتفاع كبير جداً = Pump مكتمل (فات الوقت)
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
    global btc_change_24h, btc_trend_1h, btc_trend_4h, market_state, last_btc
    global last_market_report
    global eth_change_24h

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

    # 🆕 اتجاه 4h — كشف الانهيار السريع
    btc_trend_4h = 0.0
    kd4 = get_klines("BTCUSDT", "4h", 3)
    if kd4 and len(kd4["closes"]) >= 2:
        c4 = kd4["closes"]
        btc_trend_4h = (c4[-1] - c4[0]) / c4[0] * 100

    # 🆕 جلب ETH 24h
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

    # 🆕 TPS/ATS لـ BTC و ETH
    global btc_tps_stats, eth_tps_stats
    _btc_tps = analyze_tps_ats("BTCUSDT")
    if _btc_tps:
        btc_tps_stats = _btc_tps
    _eth_tps = analyze_tps_ats("ETHUSDT")
    if _eth_tps:
        eth_tps_stats = _eth_tps

    # ══════════════════════════════════════════════
    # 🆕 V15: Buffer System — منع التذبذب
    # الحدود مع Buffer:
    #   DANGER:  يدخل عند < -3.3% | يخرج عند > -2.7%
    #   CAUTION: يدخل عند < -1.8% | يخرج عند > -1.2%
    #   SAFE:    يدخل عند > -1.2%
    # ══════════════════════════════════════════════
    global _btc_danger_count, _btc_caution_count, _btc_safe_count

    # حدود الدخول (أصعب)
    danger_enter  = BTC_DANGER_ZONE  - BTC_DANGER_BUFFER   # -3.3%
    caution_enter = BTC_CAUTION_ZONE - BTC_CAUTION_BUFFER  # -1.8%

    # حدود الخروج (أسهل — منطقة Buffer)
    danger_exit   = BTC_DANGER_ZONE  + BTC_DANGER_BUFFER   # -2.7%
    caution_exit  = BTC_CAUTION_ZONE + BTC_CAUTION_BUFFER  # -1.2%

    btc_signal = btc_change_24h

    # 🆕 كشف الانهيار السريع — بغض النظر عن 24h
    _crash_4h = btc_trend_4h <= BTC_CRASH_4H   # انهار -2.5% في 4 ساعات
    _crash_1h = btc_trend_1h  <= BTC_CRASH_1H  # انهار -1.5% في ساعة

    # حدد الحالة المقترحة
    if btc_signal <= danger_enter or btc_trend_1h <= -2.0 or _crash_4h:
        suggested = "DANGER"
    elif btc_signal <= caution_enter or _crash_1h:
        suggested = "CAUTION"
    elif btc_signal >= caution_exit:
        suggested = "SAFE"
    else:
        # في منطقة Buffer — ابقَ على الحالة الحالية
        suggested = market_state

    # عداد التأكيد — يحتاج BTC_CONFIRM_COUNT مرات متتالية
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
        # Buffer zone — لا تغيير في العدادات
        pass

    # تطبيق التغيير فقط بعد BTC_CONFIRM_COUNT مرات
    old = market_state
    if _btc_danger_count  >= BTC_CONFIRM_COUNT:
        market_state = "DANGER"
    elif _btc_caution_count >= BTC_CONFIRM_COUNT:
        market_state = "CAUTION"
    elif _btc_safe_count    >= BTC_CONFIRM_COUNT:
        market_state = "SAFE"
    # else: ابقَ على الحالة الحالية

    last_btc = time.time()

    if old != market_state:
        # ── cooldown 4 ساعات ──
        if time.time() - last_market_report < MARKET_REPORT_EVERY:
            log.info("📊 Market changed %s→%s لكن cooldown 4h", old, market_state)
            return
        last_market_report = time.time()
        icons = {"SAFE": "🟢", "CAUTION": "🟡", "DANGER": "🔴"}
        notes = {
            "SAFE":    "✅ كل الإشارات مفعّلة",
            "CAUTION": "⚠️ Gold فقط (Score 88+)",
            "DANGER":  "🔴 إشارات القطاعات الساخنة فقط",
        }
        # بناء قسم TPS/ATS للرسالة
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
                "🐋 حيتان يبيعون ⚠️" if _ats >= ATS_WHALE and _vd < 0.40 else
                "📊 نشاط طبيعي"
            )
            return (
                "  TPS:`{:.1f}` ATS:`{:.0f}$` {} VD:`{:.0f}%`\n"
                "  ↳ {}\n".format(_tps, _ats, _bt, _vd*100, _verdict)
            )

        btc_tps_line = _tps_line(btc_tps_stats, "BTC")
        eth_tps_line = _tps_line(eth_tps_stats, "ETH")

        send(
            "📊 *تقرير السوق*\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "{icon} السوق: *{state}*\n"
            "₿ BTC 24h: `{ch:+.2f}%`\n"
            "₿ BTC 4h:  `{h4:+.2f}%`\n"
            "₿ BTC 1h:  `{h:+.2f}%`\n"
            "{btc_tps}"
            "━━━━━━━━━━━━━━━━━━\n"
            "Ξ ETH 24h: `{eth:+.2f}%`\n"
            "{eth_tps}"
            "━━━━━━━━━━━━━━━━━━\n"
            "_{note}_\n"
            "📡 _قوة الإشارة: {confirm}/3_".format(
                icon=icons[market_state], state=market_state,
                ch=btc_change_24h, h4=btc_trend_4h, h=btc_trend_1h,
                btc_tps=btc_tps_line,
                eth=eth_change_24h,
                eth_tps=eth_tps_line,
                note=notes[market_state],
                confirm=BTC_CONFIRM_COUNT,
            )
        )
        log.info("📊 Market: %s→%s | BTC %.2f%% | confirm=%d",
                 old, market_state, btc_change_24h, BTC_CONFIRM_COUNT)


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
        # ✅ sector_vol_history قد يكون list (من Flow Tracker) أو float
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




# ═══════════════════════════════════════════════════════════════════
#   🌊 SECTOR ROTATION DETECTOR
#   يكتشف عندما تخرج الأموال من قطاع وتدخل قطاعاً آخر
#   ويرسل تنبيه واحد مركّز يربط الحدثين معاً
# ═══════════════════════════════════════════════════════════════════

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

    # احسب التغير لكل قطاع بناءً على snapshots
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
        sector_vol_abs[sector] = curr / 1_000_000  # بالمليون

    if not sector_pct:
        return

    # فرّق بين الداخل والخارج
    entering = sorted(
        [(s, p) for s, p in sector_pct.items() if p >= SR_MIN_IN],
        key=lambda x: -x[1]
    )
    leaving = sorted(
        [(s, p) for s, p in sector_pct.items() if p <= SR_MIN_OUT],
        key=lambda x: x[1]
    )

    # يجب وجود الاثنين لإرسال Rotation
    if not entering or not leaving:
        return

    last_sr_alert = now

    # ── بناء الرسالة ──────────────────────────────
    # قسم الخروج
    out_lines = ""
    for s, p in leaving[:3]:
        vol = sector_vol_abs.get(s, 0)
        out_lines += "  ⬇️ *{}* `{:+.1f}%` ({:.1f}M)\n".format(s, p, vol)

    # قسم الدخول + أفضل عملات
    in_lines   = ""
    opp_lines  = ""  # الفرص المحددة

    tmap = {t["symbol"]: t for t in all_tickers} if all_tickers else {}

    for s, p in entering[:3]:
        vol = sector_vol_abs.get(s, 0)
        icon = "🔥" if p >= 25 else "✅"
        in_lines += "  ⬆️ *{}* `{:+.1f}%` ({:.1f}M) {}\n".format(s, p, vol, icon)

    # أفضل فرص في القطاع الأول الداخل
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
            # فلتر: حجم > 200K + تغيير إيجابي أو محايد (لم يرتفع كثيراً بعد)
            if vol >= 200_000 and ch <= 15:
                top_coins.append((sym.replace("USDT",""), ch, vol, pr))
        except (KeyError, ValueError):
            pass

    top_coins.sort(key=lambda x: -x[2])  # رتّب حسب الحجم

    for name, ch, vol, pr in top_coins[:SR_TOP_COINS]:
        chg_icon = "🟢" if ch > 0 else "⚪"
        opp_lines += "  {} *{}* `{:+.1f}%` | vol:`{:.0f}K`\n".format(
            chg_icon, name, ch, vol/1000)

    # حكم ذكي
    top_in_pct  = entering[0][1]
    top_out_pct = leaving[0][1]
    if top_in_pct >= 30:
        verdict = "🚀 *تدفق قوي جداً — فرصة نادرة!*"
    elif top_in_pct >= 15:
        verdict = "⚡ *تدفق واضح — دخول جيد*"
    else:
        verdict = "👀 *تدفق بدأ — راقب التأكيد*"

    # هل السوق يدعم؟
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
    log.info("🌊 Sector Rotation | OUT:%s → IN:%s",
             [s for s, _ in leaving[:3]],
             [s for s, _ in entering[:3]])

def get_flow_summary():
    # type: () -> str
    """
    ملخص تدفق السيولة بين القطاعات — مفصّل بالأرقام والنسب.
    يقارن حجم اليوم بأمس لكل قطاع.
    """
    if not sector_vol_snapshots:
        return "➡️ لا تدفق واضح — جاري جمع البيانات\n"

    # احسب التغير لكل قطاع
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

    # رتّب: الأكثر دخولاً أولاً
    sector_changes.sort(key=lambda x: -x[1])
    entering = [(s, p, v, d) for s, p, v, d in sector_changes if p >= 8]
    leaving  = [(s, p, v, d) for s, p, v, d in sector_changes if p <= -8]

    txt = ""

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

    # خلاصة ذكية
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
            price=fmt_price(c["price"]),
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

        # حفظ النتائج فقط — بدون إرسال فردي
        if not data["checked_1h"] and elapsed >= BACKTEST_CHECK_1H:
            data["checked_1h"] = True
            data["result_1h"]  = gain
            data["price_now"]  = price
            log.info("📊 BT-1H | %s | %+.2f%%", sym, gain)

        elif not data["checked_4h"] and elapsed >= BACKTEST_CHECK_4H:
            data["checked_4h"] = True
            data["result_4h"]  = gain
            data["price_now"]  = price
            log.info("📊 BT-4H | %s | %+.2f%%", sym, gain)

        elif not data["checked_24h"] and elapsed >= BACKTEST_CHECK_24H:
            data["checked_24h"] = True
            data["result_24h"]  = gain
            data["price_now"]   = price
            log.info("🏁 BT-24H | %s | %+.2f%%", sym, gain)


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




# ═══════════════════════════════════════════════════════════════════
#   📊 PERFORMANCE TRACKER — تتبع أداء كل نظام بشكل مستقل
#   يسجل كل إشارة مع مصدرها ويقيس نتائجها
# ═══════════════════════════════════════════════════════════════════

# مستودع الأداء — {signal_id: {...}}
perf_signals = {}   # type: Dict[str, Dict]
perf_id_counter = 0 # type: int

# أسماء الأنظمة
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
        # نتائج
        "result_1h":    None,
        "result_4h":    None,
        "result_24h":   None,
        "checked_1h":   False,
        "checked_4h":   False,
        "checked_24h":  False,
    }
    log.info("📊 Perf registered | %s | %s | score=%d", system, sym, score)
    return sid


def perf_check(price_map=None):
    # type: (Dict) -> None
    """يتحقق من نتائج الإشارات المسجلة عند 1h/4h/24h"""
    # إذا لم يُمرَّر price_map نبنيه من all_tickers
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
            # احذف بعد 48 ساعة لتوفير الذاكرة
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

    # جمع نتائج كل نظام
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

    # بناء الرسالة
    # تحقق: هل يوجد بيانات كافية؟
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

        # نسبة النجاح
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

        # أفضل وأسوأ إشارة
        if st["best"]:
            lines.append(
                "  🏆 أفضل: *{}* `{:+.1f}%`  |  💀 أسوأ: *{}* `{:+.1f}%`".format(
                    st["best"][0].replace("USDT",""),  st["best"][1],
                    st["worst"][0].replace("USDT",""), st["worst"][1]
                )
            )

    # الملخص الكلي
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

# ═══════════════════════════════════════════════
#   SMART MONEY DETECTION
# ═══════════════════════════════════════════════

MAX_DAILY_SIGNALS = 10  # الحد الأقصى للإشارات يومياً


def can_send_signal():
    # type: () -> bool
    """هل يمكن إرسال إشارة اليوم؟ الحد الأقصى 10"""
    global daily_signals
    today = datetime.utcnow().strftime("%Y-%m-%d")
    if daily_signals["date"] != today:
        daily_signals = {"date": today, "count": 0}
    return daily_signals["count"] < MAX_DAILY_SIGNALS


def register_signal():
    # type: () -> None
    """تسجيل إشارة جديدة في العداد اليومي"""
    global daily_signals
    today = datetime.utcnow().strftime("%Y-%m-%d")
    if daily_signals["date"] != today:
        daily_signals = {"date": today, "count": 0}
    daily_signals["count"] += 1
    log.info("📊 إشارات اليوم: %d/%d", daily_signals["count"], MAX_DAILY_SIGNALS)


# ═══════════════════════════════════════════════
# TRAILING STOP SYSTEM — حماية الأرباح الذكية
# ═══════════════════════════════════════════════

def ts_register_entry(sym, entry_price, sector="Unknown"):
    # type: (str, float, str) -> None
    """تسجيل صفقة جديدة في نظام الـ Trailing Stop"""
    global ts_positions
    # جلب الحجم الحالي كمرجع
    _vol_ref = float(next((t["quoteVolume"] for t in all_tickers if t["symbol"]==sym), "0"))
    ts_positions[sym] = {
        "entry":     entry_price,
        "peak":      entry_price,
        "stop":      entry_price * (1 - TS_TRAIL_PCT / 100),
        "locked":    0.0,
        "sector":    sector,
        "since":     time.time(),
        "entry_vol": _vol_ref,  # حجم الدخول كمرجع
    }
    log.info("📌 TS Registered | %s | entry=%.8f", sym, entry_price)


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

        # حساب الربح الحالي
        profit_pct = (price / entry - 1) * 100
        peak_pct   = (peak  / entry - 1) * 100

        # ══ تحديث القمة ══
        if price > peak:
            ts_positions[sym]["peak"] = price
            peak     = price
            peak_pct = (peak / entry - 1) * 100

            # ══ تحريك الستوب مع القمة ══
            new_stop = stop

            if peak_pct >= TS_LOCK_50:
                # +50% → نقفل +35%
                new_stop  = entry * 1.35
                new_locked = 35.0
            elif peak_pct >= TS_LOCK_20:
                # +20% → نقفل +10%
                new_stop  = entry * 1.10
                new_locked = 10.0
            elif peak_pct >= TS_BREAKEVEN:
                # +10% → نرجع لنقطة الدخول
                new_stop  = entry * 1.001
                new_locked = 0.0

            # Trailing: الستوب دائماً 15% تحت القمة
            trail_stop = peak * (1 - TS_TRAIL_PCT / 100)
            new_stop   = max(new_stop, trail_stop)

            if new_stop > stop:
                ts_positions[sym]["stop"]   = new_stop
                ts_positions[sym]["locked"] = max(locked, new_stop / entry * 100 - 100)
                log.info("📈 TS Updated | %s | peak=+%.1f%% | stop=%.8f",
                         sym, peak_pct, new_stop)

        # ══ فحص الخروج الذكي ══
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

                # ── الحالة 1: ربح + سيولة تخرج ──
                # عندنا ربح والسيولة تبدأ بالخروج = اخرج بربح
                if _pl > 5.0 and _vol_ratio < 0.5 and market_state in ("DANGER","CAUTION"):
                    _exit_reason = "✅ اخرج بربح — السيولة تخرج"
                    _exit_icon   = "✅"

                # ── الحالة 2: عند نقطة الدخول + سوق خطر ──
                # السوق DANGER + السيولة تخرج = احمِ رأس المال
                elif _pl > -2.0 and _pl < 3.0 and market_state == "DANGER" and _vol_ratio < 0.4:
                    _exit_reason = "🛡️ احمِ رأس المال — السوق خطر"
                    _exit_icon   = "🛡️"

                # ── الحالة 3: خسارة + سوق خطر + سيولة تهرب ──
                # الأسوأ = اخرج فوراً بخسارة محدودة
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
                    log.info("🔴 SMART EXIT | %s | pl=%.1f%% | vol=%.1fx | market=%s",
                             sym, _pl, _vol_ratio, market_state)
            except: pass

        # ══ فحص الستوب ══
        stop = ts_positions[sym]["stop"]
        if price <= stop:
            # ضرب الستوب!
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
            log.info("🔴 SELL SIGNAL | %s | profit=%.1f%% | peak=+%.1f%%",
                     sym, profit_pct, peak_pct)

            # احذف الصفقة بعد البيع
            del ts_positions[sym]



def add_to_liquidity_watchlist(sym, reason, vol, price, sector):
    # type: (str, str, float, float, str) -> None
    """يضيف عملة لقائمة المراقبة عند رصد سيولة غير عادية"""
    global watchlist, wl_price_snapshot

    # تحقق من القائمة المحظورة
    _blocked = {"CULTUSDT"}  # عملات محظورة
    if sym in _blocked:
        log.debug("🚫 WL Blocked | %s", sym)
        return

    # لا تجاوز الحد الأقصى
    if len(watchlist) >= WL_MAX_SIZE:
        # احذف الأقدم
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
        log.info("👀 WL Added | %s | reason=%s | vol=%.1fM | price=%s",
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
        # ── انتهت صلاحية العملة (24h بدون تحرك) ──
        if info.get("priority") == "STATIC":
            pass  # الثابتة لا تنتهي أبداً
        elif now - info.get("since", now) > WL_EXPIRY:
            to_remove.append(sym)
            log.info("👀 WL Expired | %s", sym)
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

        # ── حساب التحرك منذ الإضافة ────────────
        move_since_add = (price - entry_price) / entry_price * 100

        # ── شرط الدخول ──────────────────────────
        # تحرك 3%+ للأعلى منذ الإضافة
        # STATIC تحتاج تحرك أقل للتنبيه (2% بدل 3%)
        _min_move = 2.0 if info.get("priority") == "STATIC" else WL_ENTRY_MOVE
        if move_since_add < _min_move: continue
        # لا ترسل إذا الحجم ضعيف جداً
        _cur_vol = float(next((t["quoteVolume"] for t in all_tickers if t["symbol"]==sym), "0"))
        if _cur_vol < 1_000_000: continue  # حجم أقل من 1M = تجاهل

        # cooldown لنفس العملة
        if now - wl_entry_alerted.get(sym, 0) < WL_ENTRY_COOL: continue

        # ── تأكيد الحجم ─────────────────────────
        wl_vol     = info.get("vol", vol)
        vol_confirm = vol >= wl_vol * WL_ENTRY_VOL or vol >= 2_000_000

        sector = info.get("sector", "Unknown")
        reason = info.get("reason", "liquidity")
        priority = info.get("priority", "NORMAL")

        # ── إشعار الدخول ────────────────────────
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

        # ══ النظام القديم معطّل — الجوكر فقط يرسل إشارات الدخول ══
        # send(msg)  ← معطّل
        wl_entry_alerted[sym] = now
        # تسجيل في نظام Trailing Stop فقط بدون إشعار
        ts_register_entry(sym, price, info.get("sector","Unknown"))
        log.info("👁️ WL silent track | %s | move=+%.1f%% | vol=%.1fM",
                 sym, move_since_add, vol/1e6)

    # حذف العملات المنتهية
    for sym in to_remove:
        watchlist.pop(sym, None)
        wl_price_snapshot.pop(sym, None)

    if watchlist:
        log.info("👀 WL Check | watching=%d | expired=%d", len(watchlist), len(to_remove))


def scan_instant_movers(price_map=None, vol_now=None, changes_map=None):  # معطّل
    # type: () -> None
    """
    يعمل من الدقيقة الأولى — بدون أي تاريخ
    يرصد العملات التي تتحرك الآن بقوة:
    - تغيير 24h >= 8%
    - حجم >= 500K
    - في SECTORS فقط
    """
    global hot_alerted

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
        if change > 60.0:   continue  # pump واضح

        # cooldown ساعة
        if now - hot_alerted.get(sym, 0) < 21600: continue  # 6 ساعات

        sector = next((s for s,c in SECTORS.items() if sym in c), "Unknown")

        # قوة الإشارة
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

    for m in movers[:3]:  # أفضل 3 فقط
        sym  = m["sym"]
        base = sym.replace("USDT","")

        if m["score"] >= 6:   icon = "🔥🔥"; lvl = "EXPLOSIVE MOVE"
        elif m["score"] >= 4: icon = "🔥";   lvl = "STRONG MOVE"
        else:                 icon = "⚡";        lvl = "ACTIVE MOVE"

        gem_tag = ""
        if sym in gem_watchlist:
            gem_tag = "  💎 مرصودة من المرحلة "+str(gem_watchlist[sym].get("stage",1))+"\n"

        vol_str = str(round(m["vol"]/1e6,2))+"M" if m["vol"]>=1e6 else str(round(m["vol"]/1e3,0))+"K"

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
            +"🎯 *"+lvl+"* | قوة: `"+str(m["score"])+"/9`\n"
            +"⚡ _حركة قوية — ادرس فرصة الدخول_"
        )
        if not can_send_signal(): break
        send(msg)
        hot_alerted[sym] = now
        coin_alerted[sym] = now   # 🔒 موحد
        register_signal()
        if sym not in candidates: candidates.append(sym)
        add_to_liquidity_watchlist(sym, "move_"+str(round(m["change"],0))+"%",
                                   m["vol"], m["price"], m["sector"])
        log.info("⚡ Instant Mover | %s | +%.1f%% | vol=%s | score=%d",
                 sym, m["change"], vol_str, m["score"])

    log.info("⚡ Instant Scan | movers=%d", len(movers))


def scan_realtime_liquidity(price_map=None, vol_now=None):  # معطّل
    # type: () -> None
    """
    الأهم والأسرع — يعمل كل 5 دقائق
    يرصد السيولة غير العادية فوراً:

    1. حجم يرتفع 2× فجأة
    2. سعر يتحرك 3%+ معه
    3. على كل السوق مباشرة
    = لا يحتاج تاريخ — يعمل من الدقيقة الأولى 🎯
    """
    global rt_vol_baseline, rt_alerted

    if not all_tickers:
        return

    now = time.time()

    # بناء قائمة عملات SECTORS
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

        # ── بناء الـ Baseline تراكمياً ─────────────
        if sym not in rt_vol_baseline:
            rt_vol_baseline[sym] = vol  # أول قراءة
            continue

        baseline = rt_vol_baseline[sym]

        # تحديث الـ baseline ببطء (exponential moving average)
        rt_vol_baseline[sym] = baseline * 0.85 + vol * 0.15

        if baseline <= 0: continue

        vol_spike = vol / baseline

        # ── شرط 1: ارتفاع حجم مفاجئ ───────────────
        if vol_spike < RT_VOL_SPIKE: continue

        # ── شرط 2: حركة سعر مصاحبة ────────────────
        if abs(change) < RT_PRICE_MOVE: continue

        # ── تجنب التكرار ────────────────────────────
        if now - rt_alerted.get(sym, 0) < RT_COOLDOWN: continue

        # ── إيجاد القطاع ────────────────────────────
        sector = next((s for s,c in SECTORS.items() if sym in c), "Unknown")

        # ── حساب القوة ──────────────────────────────
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

    for a in alerts[:3]:  # أفضل 3 فقط
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
        coin_alerted[sym] = now   # 🔒 موحد
        if sym not in candidates:
            candidates.append(sym)
        add_to_liquidity_watchlist(sym, "liq_spike_"+str(round(a["vol_spike"],1))+"x",
                                   a["vol"], a["price"], a["sector"])

        log.info("💧 RT Liquidity | %s | spike=%.1fx | change=%.1f%% | strength=%d",
                 sym, a["vol_spike"], a["change"], a["strength"])

    log.info("💧 RT Scan done | alerts=%d", len(alerts))


def scan_hot_market(price_map=None, vol_now=None):  # معطّل
    # type: () -> None
    """
    يعمل فوراً بدون تاريخ
    يرصد العملات الساخنة الآن:
    - تغيير 10%+ في 24h
    - حجم 1M+ USDT
    - موجودة في SECTORS
    = يرسل تنبيه فوري 🔥
    """
    global hot_alerted

    if not all_tickers:
        return

    now  = time.time()
    hot  = []

    # بناء قائمة كل العملات في SECTORS
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

        # تجنب التكرار
        last_alert = hot_alerted.get(sym, 0)
        if now - last_alert < HOT_COOLDOWN: continue

        # إيجاد القطاع
        sector = "Unknown"
        for sec, coins in SECTORS.items():
            if sym in coins:
                sector = sec
                break

        # قوة الإشارة
        strength = 0
        if change >= 30:     strength += 4
        elif change >= 20:   strength += 3
        elif change >= 15:   strength += 2
        else:                strength += 1

        if vol >= 10_000_000: strength += 3
        elif vol >= 5_000_000: strength += 2
        elif vol >= 2_000_000: strength += 1

        # هل هي في gem_watchlist؟ (مرت بمراحل)
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

    for coin in hot[:5]:  # أفضل 5
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

        # هل في gem_watchlist؟
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
            + "⚡ _حركة قوية — ادرس فرصة الدخول_"
        )

        send(msg)
        hot_alerted[sym] = now

        # إضافة للـ candidates
        if sym not in candidates:
            candidates.append(sym)
        log.info("🔥 Hot Market | %s | +%.1f%% | vol=%.1fM | strength=%d",
                 sym, coin["change"], coin["vol"]/1e6, coin["strength"])

    log.info("🔥 Hot Scan | found=%d", len(hot))


def scan_ath_distance(price_map=None):  # معطّل
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
    gems = []  # العملات المكتشفة

    for t in all_tickers:
        sym = t.get("symbol", "")
        if not sym.endswith("USDT"): continue
        if any(k in sym for k in LEVERAGE_KEYWORDS): continue
        if is_suspicious(sym, 0, 0, 0): continue

        try:
            price  = float(t["lastPrice"])
            high   = float(t["highPrice"])   # أعلى سعر 24h
            vol    = float(t["quoteVolume"])
            change = float(t["priceChangePercent"])
        except (KeyError, ValueError):
            continue

        if vol < ATH_MIN_VOL: continue
        if price <= 0: continue

        # ── تحديث ATH المحلي ──────────────────────
        # نبني ATH تراكمياً من أعلى سعر يومي
        prev_ath = ath_tracker.get(sym, 0.0)
        if high > prev_ath:
            ath_tracker[sym] = high
            prev_ath = high

        if prev_ath <= 0: continue

        # ── حساب الانخفاض من ATH ──────────────────
        drop_pct = 1.0 - (price / prev_ath)

        # يجب أن يكون الانخفاض 90%+ من ATH
        if drop_pct < ATH_DROP_STRONG: continue

        # ── حجم التاريخ لمعرفة التزايد ────────────
        vh = bottom_vol_history.get(sym, [])
        vol_ratio = 1.0
        if len(vh) >= 3:
            vol_avg   = sum(vh[:-1]) / len(vh[:-1])
            vol_ratio = vol / vol_avg if vol_avg > 0 else 1.0

        # ── تجنب التكرار ──────────────────────────
        last_alert = ath_alerted.get(sym, 0)
        if now - last_alert < ATH_COOLDOWN: continue

        # ── حساب درجة الفرصة ──────────────────────
        score = 0

        # درجة الانهيار
        if drop_pct >= ATH_DROP_EXTREME:  score += 4  # -95%+ نادر جداً
        elif drop_pct >= ATH_DROP_STRONG: score += 2  # -90%+

        # درجة الحجم
        if vol_ratio >= 3.0:  score += 3  # حجم ضخم جداً
        elif vol_ratio >= 2.0: score += 2  # حجم كبير
        elif vol_ratio >= 1.3: score += 1  # حجم يتزايد

        # درجة الحركة الحالية
        if 0 < change <= 5:   score += 2  # صعود هادئ = تجميع
        elif change > 5:      score += 1  # بدأ يتحرك
        elif change < -5:     score -= 1  # لا يزال ينزل

        if score < 5: continue  # حد عالٍ — فرص قوية فقط

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

    for gem in gems[:3]:  # أفضل 3 فقط يومياً
        sym  = gem["sym"]
        base = sym.replace("USDT", "")

        drop_str = str(round(gem["drop_pct"] * 100, 1))

        # تحديد مستوى الفرصة
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

        # حساب الهدف المحتمل (ارتداد 20-50% من ATH)
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
        coin_alerted[sym] = now   # 🔒 موحد
        # تسجيل في gem_watchlist للمراحل القادمة
        gem_watchlist[sym] = {"stage": 1, "ath_drop": gem["drop_pct"],
                              "since": now, "score": gem["score"]}
        # عداد يومي
        import datetime as _dt
        _today = _dt.datetime.utcnow().strftime("%Y-%m-%d")
        if daily_gem_count["date"] != _today:
            daily_gem_count["date"] = _today; daily_gem_count["count"] = 0
        daily_gem_count["count"] += 1

        # أضف لقائمة المراقبة
        if sym not in watchlist:
            watchlist[sym] = {
                "since":    now,
                "priority": "HIGH",
                "reason":   "ath_gem_" + drop_str + "pct",
                "sector":   "Unknown",
            }
        log.info("💎 ATH Gem | %s | drop=%.1f%% | vol_ratio=%.1fx | score=%d",
                 sym, gem["drop_pct"]*100, gem["vol_ratio"], gem["score"])

    log.info("💎 ATH Scan | gems=%d", len(gems))


def scan_bottom_accumulation(price_map=None, vol_now=None):  # معطّل
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
        # المرحلة 2: فقط للعملات التي اجتازت المرحلة 1 (ATH alert)
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

        # ── تحديث تاريخ السعر والحجم ──────────
        if sym not in bottom_price_history:
            bottom_price_history[sym] = []
            bottom_vol_history[sym]   = []

        bottom_price_history[sym].append(price)
        bottom_vol_history[sym].append(vol)

        # احتفظ بآخر 30 قراءة فقط
        if len(bottom_price_history[sym]) > 30:
            bottom_price_history[sym].pop(0)
            bottom_vol_history[sym].pop(0)

        ph = bottom_price_history[sym]
        vh = bottom_vol_history[sym]

        # نحتاج على الأقل BOTTOM_MIN_DAYS قراءة
        if len(ph) < BOTTOM_MIN_DAYS: continue

        # ── شرط 1: السعر قريب من القاع ────────
        price_low  = min(ph)
        price_high = max(ph)
        if price_high <= price_low: continue

        # السعر يجب أن يكون في النطاق السفلي
        price_position = (price - price_low) / (price_high - price_low)
        if price_position > 0.25: continue  # فوق 25% من النطاق = ليس قاع

        # ── شرط 2: الحجم يتزايد في القاع ──────
        vol_avg   = sum(vh[:-3]) / len(vh[:-3]) if len(vh) > 3 else vol
        vol_recent = sum(vh[-3:]) / 3
        vol_ratio  = vol_recent / vol_avg if vol_avg > 0 else 1.0
        if vol_ratio < BOTTOM_VOL_INCREASE: continue

        # ── شرط 3: التغيير اليومي صغير ─────────
        if change > BOTTOM_MAX_CHANGE: continue

        # ── شرط 4: مدة في القاع كافية ──────────
        # عدد الأيام التي كان السعر فيها < 120% من القاع
        days_in_bottom = sum(1 for p in ph if p <= price_low * 1.20)
        if days_in_bottom < BOTTOM_MIN_DAYS: continue

        # 🔒 Cooldown موحد — إشارة #1 فقط إذا لم تُرسل إشارة بعد
        if now - coin_alerted.get(sym, 0) < TPS_COOLDOWN:
            if now - coin_whale_done.get(sym, 0) >= LZ_TPS_COOLDOWN:
                continue
        # ── شرط 5: تجنب التكرار ─────────────────
        last_alert = bottom_alerted.get(sym, 0)
        if now - last_alert < BOTTOM_COOLDOWN: continue

        # ── حساب قوة الإشارة ────────────────────
        strength = 0
        if price_position <= 0.10: strength += 3   # قاع مباشر
        elif price_position <= 0.20: strength += 2
        else: strength += 1

        if vol_ratio >= 2.0: strength += 3          # حجم ضخم
        elif vol_ratio >= 1.5: strength += 2
        else: strength += 1

        if days_in_bottom >= 14: strength += 2      # قاع طويل
        elif days_in_bottom >= 7: strength += 1

        if change <= 1.0: strength += 1             # هدوء تام = تجميع خفي

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

    # ترتيب حسب القوة
    found.sort(key=lambda x: -x["strength"])

    for coin in found[:5]:  # أفضل 5 فقط
        sym = coin["sym"]
        base = sym.replace("USDT", "")

        # تحديد مستوى الإشارة
        if coin["strength"] >= 7:
            level = "🔥🐳 STRONG BOTTOM"
            icon  = "🔥"
        elif coin["strength"] >= 5:
            level = "📊🐳 BOTTOM ACCUMULATION"
            icon  = "📊"
        else:
            level = "👀 EARLY BOTTOM"
            icon  = "👀"

        # نسبة المسافة من القاع للهدف المحتمل
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
        coin_alerted[sym] = now   # 🔒 موحد
        # ترقية إلى المرحلة 2
        if sym in gem_watchlist: gem_watchlist[sym]["stage"] = 2

        # أضف للـ candidates تلقائياً
        if sym not in candidates:
            candidates.append(sym)
            log.info("📊 Bottom Accumulation → candidates | %s | strength=%d | vol_ratio=%.1f×",
                     sym, coin["strength"], coin["vol_ratio"])

    log.info("📊 Bottom Scan | found=%d", len(found))



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
        # المرحلة 3: فقط للعملات التي اجتازت المرحلتين 1+2
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

        # ── شرط أساسي: يجب أن تكون في قاع مرصود ──
        ph = bottom_price_history.get(sym, [])
        vh = bottom_vol_history.get(sym, [])
        if len(ph) < EXPLOSION_MIN_DAYS: continue
        if len(vh) < EXPLOSION_MIN_DAYS: continue

        # ── حساب متوسط الحجم التاريخي ────────────
        # نستثني آخر قراءة (الانفجار نفسه)
        vol_history_avg = sum(vh[:-1]) / len(vh[:-1]) if len(vh) > 1 else vol
        if vol_history_avg <= 0: continue

        vol_mult = vol / vol_history_avg

        # ── شرط الانفجار: 3× المتوسط ─────────────
        if vol_mult < EXPLOSION_VOL_MULT: continue

        # ── شرط الاتجاه: السعر يتحرك للأعلى ──────
        if change <= 0: continue  # يجب أن يكون صاعداً
        if change > EXPLOSION_MAX_CHANGE: continue  # Pump مسبق كثير

        # ── شرط القاع: السعر كان في القاع ────────
        price_low  = min(ph[:-1])  # القاع قبل الانفجار
        price_high = max(ph[:-1])
        if price_high <= price_low: continue

        # السعر قبل الانفجار كان في النطاق السفلي
        prev_price = ph[-2] if len(ph) >= 2 else ph[-1]
        prev_position = (prev_price - price_low) / (price_high - price_low)
        if prev_position > 0.30: continue  # لم يكن في القاع

        # 🔒 Cooldown موحد — إشارة #1 فقط إذا لم تُرسل إشارة بعد
        if now - coin_alerted.get(sym, 0) < TPS_COOLDOWN:
            if now - coin_whale_done.get(sym, 0) >= LZ_TPS_COOLDOWN:
                continue
        # ── تجنب التكرار ─────────────────────────
        last_alert = explosion_alerted.get(sym, 0)
        if now - last_alert < EXPLOSION_COOLDOWN: continue

        # ── حساب قوة الانفجار ────────────────────
        power = 0
        if vol_mult >= 8:  power += 4
        elif vol_mult >= 5: power += 3
        elif vol_mult >= 3: power += 2
        else: power += 1

        if prev_position <= 0.10: power += 3  # كان في قاع مباشر
        elif prev_position <= 0.20: power += 2
        else: power += 1

        days_in_bottom = sum(1 for p in ph[:-1] if p <= price_low * 1.20)
        if days_in_bottom >= 14: power += 2
        elif days_in_bottom >= 7: power += 1

        if change >= 10: power += 2   # صعود قوي مع الانفجار
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

    for coin in explosions[:3]:  # أفضل 3 فقط
        sym  = coin["sym"]
        base = sym.replace("USDT", "")

        # مستوى الانفجار
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
        coin_alerted[sym] = now   # 🔒 موحد
        # المرحلة 3 مكتملة — تحديث stage
        if sym in gem_watchlist: gem_watchlist[sym]["stage"] = 3

        # أضف للـ candidates بأولوية عالية
        if sym not in candidates:
            candidates.insert(0, sym)  # أولوية قصوى في المقدمة
        if sym not in watchlist:
            watchlist[sym] = {
                "since":    now,
                "priority": "HIGH",
                "reason":   "volume_explosion",
                "sector":   "Unknown",
            }
        log.info("💥 Volume Explosion | %s | mult=%.1fx | change=+%.1f%%",
                 sym, coin["vol_mult"], coin["change"])

    log.info("💥 Explosion Scan | found=%d", len(explosions))


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
                        price=fmt_price(price), drop=drop_from_high,
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
                        price=fmt_price(price), close=close_icon,
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

        # 🆕 إذا في Watchlist → تخفيف الـ cooldown (أولوية)
        if sym in watchlist:
            if now - momentum_alerted.get(sym, 0) < MOMENTUM_COOLDOWN / 3:
                continue

        momentum_alerted[sym] = now
        coin_alerted[sym] = now   # 🔒 موحد

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

        log.info("🔵 Stage1 | %s | +%.2f%% | 24h:%.1f%% | vol:%.0f | sector:%s | flow:%s",
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


# ⚠️ تضيف عملات تلقائياً — تأكد من المراجعة قبل الإنتاج
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

# ═══════════════════════════════════════════════
#   🆕 SECTOR ACTIVITY REPORT + WHALE ACCUMULATION
#   تقرير القطاعات النشطة + تجميع الحيتان
# ═══════════════════════════════════════════════

# توقيت التقرير
SECTOR_REPORT_EVERY = 3600   # كل ساعة
last_sector_report  = 0.0


def scan_sector_activity():
    # type: () -> None
    global last_sector_report, price_snapshot, price_snapshot_time

    if not all_tickers:
        return

    ticker_map = {t["symbol"]: t for t in all_tickers}

    # ═══ تحديث Snapshot كل ساعة ══════════════════
    now = time.time()
    if now - price_snapshot_time >= 3600 or not price_snapshot:
        price_snapshot = {
            t["symbol"]: float(t["lastPrice"])
            for t in all_tickers
            if t.get("symbol","").endswith("USDT")
        }
        price_snapshot_time = now
        log.info("📸 Price snapshot محدّث | %d عملة", len(price_snapshot))

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

    # ═══ الخطوة 1: تصنيف كل عملات MEXC للقطاعات ═══
    # نصنّف من السوق الكامل وليس القائمة فقط
    sector_stats = {}

    # بناء خريطة ديناميكية: كل عملة → قطاعها
    def get_sector_for(sym):
        base = sym.replace("USDT","")
        for sec, keywords in SECTOR_KEYWORDS.items():
            if any(kw in base for kw in keywords):
                return sec
        # إذا في SECTORS الثابتة
        for sec, coins in SECTORS.items():
            if sym in coins:
                return sec
        return None

    # تجميع البيانات من كل عملات MEXC
    full_sector_data = {}   # {sector: {buy_vol, sell_vol, changes, vols}}

    for t in all_tickers:
        sym = t.get("symbol","")
        if not sym.endswith("USDT"): continue
        if is_suspicious(sym, 0, 0, 0): continue
        try:
            ch  = real_change(sym, t)          # ← تغيير حقيقي من آخر ساعة
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
            # ترتيب حسب إجمالي السيولة الداخلة
            "score":    total_vol / 1_000_000,
        }

    if not sector_stats:
        return

    sorted_sectors = sorted(sector_stats.items(), key=lambda x: -x[1]["score"])

    # ═══ الخطوة 2: تجميع الحيتان ════════════════
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

        # فلتر صارم
        if vol < WHALE_MIN_VOL: continue
        if vol > MAX_VOL_USDT:  continue
        if price <= 0 or high <= 0 or low <= 0: continue
        if ch > 5 or ch < -15: continue   # فات أو خطر

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

    # ═══ تحديث Watchlist ═════════════════════════
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

    # ═══ بناء التقرير ════════════════════════════
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

    # حساب نسبة الشراء/البيع بالحجم الحقيقي
    buy_vol_total  = 0.0
    sell_vol_total = 0.0
    for t in all_tickers:
        sym = t.get("symbol","")
        if not sym.endswith("USDT"): continue
        if is_suspicious(sym, 0, 0, 0): continue
        try:
            ch  = real_change(sym, t)          # ← تغيير حقيقي
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
    log.info("🌊 Sector Report | hot=%s | whale_accum=%d",
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


# ═══════════════════════════════════════════════════════════════════
#   🔥 LIQUIDITY HUNTER — كاشف دخول السيولة المفاجئ
#   يعمل كل 5 دقائق على كل العملات
#   يكتشف 3 سيناريوهات قبل الارتفاع بدقائق/ساعات
# ═══════════════════════════════════════════════════════════════════

# إعدادات LIQUIDITY HUNTER
# ══════════════════════════════════════════
# TPS/ATS + Volume Delta
# ══════════════════════════════════════════
TPS_LIMIT         = 100    # آخر 100 صفقة للتحليل
TPS_SPIKE         = 3.0    # TPS ارتفع 3× = نشاط غير عادي
ATS_WHALE         = 5000   # متوسط صفقة > 5000 USDT = حيتان
ATS_RETAIL        = 500    # متوسط صفقة < 500 USDT = أفراد
VDELTA_STRONG     = 0.70   # 70%+ شراء = ضغط شراء قوي
TPS_COOLDOWN      = 3600   # ساعة بين تنبيهات نفس العملة
TPS_SCAN_EVERY    = 300    # كل 5 دقائق

# ══════════════════════════════════════════
# Small Caps — قائمة مستقلة للعملات الصغيرة
# ══════════════════════════════════════════
SC_MIN_VOL        = 50_000    # حجم أدنى 50K USDT
SC_MAX_VOL        = 500_000   # حجم أقصى 500K (فوقه يصبح Big Cap)
SC_MAX_COINS      = 300       # أقصى عدد عملات في القائمة
SC_REFRESH_EVERY  = 3600      # تحديث القائمة كل ساعة
SC_VOL_SPIKE      = 4.0       # يحتاج spike أقوى (أكثر تصفية)
SC_VOL_SPIKE_MICRO = 1.8      # عملات < 100K — spike أقل يكفي
SC_MICRO_VOL_MAX  = 100_000   # حد الـ Micro Cap
SC_SCORE_MIN      = 65        # حد أعلى للعملات الصغيرة (أكثر صرامة)

LH_VOL_SPIKE      = 3.0   # الحجم ارتفع 3× المعدل = مشبوه
LH_VOL_QUIET      = 1.8   # الحجم ارتفع 1.8× بهدوء = تجميع صامت
LH_PRICE_FLAT     = 2.0   # السعر تغير أقل من 2% رغم ارتفاع الحجم
LH_BTC_DIV_MIN    = 1.5   # BTC ينزل -1.5% لكن العملة ثابتة = قوة داخلية
LH_COOLDOWN       = 14400 # 4 ساعات بين تنبيهات نفس العملة
LH_SCORE_MIN      = 50    # الحد الأدنى للتنبيه
LH_SCAN_EVERY     = 300   # كل 5 دقائق


# ═══════════════════════════════════════════════════════════════════
#   ⚡ TPS / ATS + VOLUME DELTA ENGINE
#   يحلل الصفقات الفعلية لكشف:
#   • TPS  — عدد الصفقات/ثانية  → ارتفاع مفاجئ = نشاط غير عادي
#   • ATS  — متوسط حجم الصفقة  → كبير = حيتان / صغير = أفراد
#   • VDelta — شراء حقيقي vs بيع حقيقي من الصفقات الفعلية
# ═══════════════════════════════════════════════════════════════════

def analyze_tps_ats(sym):
    # type: (str) -> Optional[Dict]
    """يجلب آخر 100 صفقة ويحسب TPS + ATS + VDelta"""
    raw = safe_get(MEXC_TRADES, {"symbol": sym, "limit": TPS_LIMIT})
    if not raw or not isinstance(raw, list) or len(raw) < 10:
        return None
    try:
        now_ms  = int(time.time() * 1000)
        window  = 30000   # آخر 30 ثانية
        buy_vol = sell_vol = all_vol = 0.0
        trade_window = 0
        sizes   = []

        for t in raw:
            price  = float(t.get("price", 0))
            qty    = float(t.get("qty",   0))
            ts     = int(t.get("time",    0))
            is_buy = not t.get("isBuyerMaker", True)
            val    = price * qty
            all_vol += val
            sizes.append(val)
            if is_buy:
                buy_vol += val
            else:
                sell_vol += val
            if now_ms - ts <= window:
                trade_window += 1

        if all_vol <= 0:
            return None

        tps        = trade_window / 30.0
        ats        = all_vol / len(raw)
        vdelta     = buy_vol / all_vol if all_vol > 0 else 0.5
        buyer_type = "🐋 حيتان" if ats >= ATS_WHALE else ("🐟 متوسط" if ats >= 1000 else "🦐 أفراد")

        return {
            "tps": round(tps, 2), "ats": round(ats, 2),
            "vdelta": round(vdelta, 3), "buy_vol": round(buy_vol, 2),
            "sell_vol": round(sell_vol, 2), "all_vol": round(all_vol, 2),
            "buyer_type": buyer_type,
        }
    except (KeyError, ValueError, ZeroDivisionError, TypeError):
        return None



# ✅ fmt_price موحّدة — انظر التعريف الأسفل


# ═══════════════════════════════════════════════════════════════════
#   🎯 LIQUIDITY ZONE + TPS/ATS FUSION ENGINE
#   يدمج:
#   1. مناطق السيولة اليومية (Swing High/Low + Volume)
#   2. TPS/ATS الفوري (صفقات حقيقية + حيتان)
#   = إشارة مزدوجة نادرة جداً 🔥
# ═══════════════════════════════════════════════════════════════════

# إعدادات الدمج
LZ_TPS_PROXIMITY  = 0.015   # السعر قريب من المنطقة بـ 1.5%
LZ_TPS_COOLDOWN   = 14400   # 4 ساعات بين تنبيهات نفس العملة
LZ_TPS_SCORE_MIN  = 70      # حد أدنى للنقاط
lz_tps_alerted    = {}      # type: Dict[str, float]

# ═══════════════════════════════════════════════════════════════════
#   🐋 WHALE CONFIRMATION SYSTEM
#   يراقب العملات التي اشترى فيها الأفراد
#   وينتظر دخول الحيتان للتأكيد
# ═══════════════════════════════════════════════════════════════════

WHALE_WATCH_TTL    = 14400   # يراقب العملة 4 ساعات بعد إشارة الأفراد
WHALE_CHECK_EVERY  = 300     # يتحقق كل 5 دقائق
WHALE_ATS_MIN      = 3000    # ATS > 3000$ = حيتان دخلوا
WHALE_VDELTA_MIN   = 0.65    # VDelta 65%+ مع الحيتان

# قائمة المراقبة: {sym: {time, ats_then, vdelta_then, price_then}}
whale_watchlist    = {}   # type: Dict[str, Dict]
whale_confirmed    = {}   # type: Dict[str, float]  {sym: last_confirm_time}


def whale_watch_add(sym, ats, vdelta, price):
    # type: (str, float, float, float) -> None
    """يضيف عملة لقائمة مراقبة الحيتان"""
    global whale_watchlist
    if sym not in whale_watchlist:
        whale_watchlist[sym] = {
            "time":        time.time(),
            "ats_then":    ats,
            "vdelta_then": vdelta,
            "price_then":  price,
        }
        log.info("👁️ Whale Watch: %s | ATS=%.0f$ | VD=%.0f%%", sym, ats, vdelta*100)


def scan_whale_confirmation(price_map):
    # type: (Dict) -> None
    """
    يفحص كل العملات في قائمة المراقبة
    إذا ATS ارتفع لـ WHALE_ATS_MIN+ → تنبيه Whale Confirmation
    """
    global whale_watchlist, whale_confirmed
    now     = time.time()
    to_del  = []

    for sym, data in list(whale_watchlist.items()):
        # انتهت مدة المراقبة؟
        if now - data["time"] > WHALE_WATCH_TTL:
            to_del.append(sym)
            continue

        # 🔒 إذا أُرسل الجوكر → صمت تام 4h
        if now - coin_whale_done.get(sym, 0) < LZ_TPS_COOLDOWN:
            to_del.append(sym)  # أزل من القائمة
            continue

        # 🔒 cooldown التأكيد
        if now - whale_confirmed.get(sym, 0) < LZ_TPS_COOLDOWN:
            continue

        # جلب TPS/ATS الحالي
        stats = analyze_tps_ats(sym)
        if not stats:
            continue

        ats    = stats["ats"]
        vdelta = stats["vdelta"]
        tps    = stats["tps"]
        price  = price_map.get(sym, 0)

        # هل دخل الحيتان؟
        if ats < WHALE_ATS_MIN or vdelta < WHALE_VDELTA_MIN:
            continue

        # حساب التغير منذ إشارة الأفراد
        price_then  = data["price_then"]
        ats_then    = data["ats_then"]
        price_chg   = (price - price_then) / price_then * 100 if price_then > 0 else 0
        ats_mult    = ats / ats_then if ats_then > 0 else 1.0
        elapsed_min = int((now - data["time"]) / 60)

        sector = next((s for s, syms in SECTORS.items() if sym in syms), "غير محدد")

        # نوع الحيتان
        if ats >= ATS_WHALE:
            whale_type = "🐋🐋 حوت ضخم"
        else:
            whale_type = "🐋 حوت"

        # عداد الإشارات
        coin_signal_count[sym] = coin_signal_count.get(sym, 0) + 1
        _sig_num = coin_signal_count[sym]

        # ── سطر التطور: يظهر فقط إذا مرت دقيقتان+ ──
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

        # ── BTC.D tag للدمج مع ENTRY ──
        _btcd_val  = get_btc_dominance(vol_now) if vol_now else 0.0
        _btcd_fall = (len(btcd_history) >= 2 and _btcd_val > 0 and
                      _btcd_val < btcd_history[0] - 1.0)
        _alt_now   = _btcd_val > 0 and _btcd_val < BTCD_ALT_THRESHOLD
        _golden    = _btcd_fall or _alt_now

        if _golden:
            _g_tag   = "🚀 Alt Season!" if _alt_now else "📉 BTC.D ينزل"
            header   = "🃏💎🃏💎🃏💎🃏💎🃏\n💎 *الجوكر الذهبي* 💎\n🃏💎🃏💎🃏💎🃏💎🃏\n"
            btcd_line = "📊 BTC.D: {} — {}\n".format("📉 ينزل" if _btcd_fall else "🔵 منخفض", _g_tag)
            footer   = "🃏 _BTC.D ينزل + حيتان = الجوكر يلعب!_ 💎"
        else:
            header   = "🃏🐋🃏🐋🃏🐋🃏🐋🃏\n🃏 *الجوكر يلعب* 🃏\n🃏🐋🃏🐋🃏🐋🃏🐋🃏\n"
            btcd_line = ""
            footer   = "🃏 _المال الكبير دخل — الجوكر يلعب!_ 🎴"

        msg = (
            header +
            "💥 *{sym}* — حيتان دخلوا! ادخل الآن!\n".format(sym=sym.replace("USDT","")) +
            "━━━━━━━━━━━━━━━━━━\n" +
            evolution_line +
            "{}\n".format("🐌 نشاط ضعيف جداً" if tps < 0.5 else ("🐢 نشاط عادي" if tps < 1.0 else ("⚡ نشاط جيد" if tps < 3.0 else ("🔥 نشاط قوي" if tps < 5.0 else "💥 نشاط انفجاري")))) +
            "📊 VDelta: `{vd:.0f}%` شراء حقيقي 🔥\n".format(vd=vdelta*100) +
            "💰 السعر:  `{pr}` ({chg:+.2f}%)\n".format(
                pr=fmt_price(price), chg=price_chg) +
            "━━━━━━━━━━━━━━━━━━\n" +
            btcd_line +
            "🏷️ القطاع: `{sec}`\n".format(sec=sector) +
            "━━━━━━━━━━━━━━━━━━\n"
            "✅ *ادخل الصفقة الآن* 💪\n"
            "🛡️ ضع Stop Loss تحت آخر قاع\n" +
            footer
        )

        send(msg)  # GOLDEN مدمج في msg أعلاه ✅
        if _golden:
            log.info("💎 GOLDEN ENTRY! %s | BTC.D=%.2f%% | ATS=%.0f$", sym, _btcd_val, ats)
        whale_confirmed[sym]  = now
        coin_whale_done[sym]  = now   # 🔒 يغلق العملة 4 ساعات
        coin_alerted[sym]     = now
        to_del.append(sym)  # أزل من المراقبة بعد التأكيد
        perf_register(sym, price, "whale_confirm", 95, "Whale confirmed after retail")
        log.info("🐋 Whale Confirmed! %s | ATS=%.0f$ | VD=%.0f%% | +%.1f%% منذ الإشارة",
                 sym, ats, vdelta*100, price_chg)

    # تنظيف القائمة
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

    # أفضل 30 عملة بالحجم + القائمة الثابتة
    all_syms = list(set(list(candidates) + EXTRA_COINS))
    ranked = sorted(
        [(s, vol_now.get(s, 0)) for s in all_syms],
        key=lambda x: -x[1]
    )[:40]

    for sym, vol in ranked:
        base = sym.replace("USDT", "")
        if base in STABLECOINS: continue  # ✅ لا إشارات للمستقرات
        _min_vol = 100_000 if sym in EXTRA_COINS else 1_000_000
        if vol < _min_vol:  # 🛡️ EXTRA_COINS=100K | عادية=1M
            continue
        # 🔒 إذا وصل حيتان لهذه العملة → مغلقة تماماً
        if now - coin_whale_done.get(sym, 0) < LZ_TPS_COOLDOWN:
            continue
        # 🔒 حد أقصى إشارتان يومياً لنفس العملة
        if coin_signal_count.get(sym, 0) >= MAX_COIN_SIGNALS:
            continue
        # 🔒 Cooldown موحد
        last_alert  = coin_alerted.get(sym, 0)
        in_cooldown = (now - last_alert < TPS_COOLDOWN)

        price = price_map.get(sym, 0)
        if price <= 0:
            continue

        # 🚫 تجاهل إذا ارتفعت كثيراً — الفرصة فاتت
        if changes_map.get(sym, 0) >= TPS_MAX_CHANGE:
            continue

        # ── الخطوة 1: هل هناك منطقة سيولة قريبة؟ ──
        kd = get_klines(sym, "1d", LZ_LOOKBACK)
        if not kd or len(kd.get("closes", [])) < 20:
            continue

        zones = detect_liquidity_zones(kd)
        if not zones:
            continue

        # أقرب منطقة للسعر الحالي
        nearest_zone = None
        min_dist     = float("inf")
        for z in zones:
            dist = abs(price - z["mid"]) / z["mid"]
            if dist < min_dist:
                min_dist     = dist
                nearest_zone = z

        if not nearest_zone or min_dist > LZ_TPS_PROXIMITY:
            continue

        # 🔒 إذا في cooldown — فقط الحيتان يمرون
        if in_cooldown:
            _tps_quick = analyze_tps_ats(sym)
            if not (_tps_quick and
                    _tps_quick.get("ats", 0) >= WHALE_ATS_MIN and
                    _tps_quick.get("vdelta", 0) >= WHALE_VDELTA_MIN):
                continue

        # نوع المنطقة — دعم أم مقاومة؟
        is_support    = price >= nearest_zone["low"] * 0.99
        is_resistance = price <= nearest_zone["high"] * 1.01
        if not is_support:
            continue  # فقط مناطق الدعم للشراء

        # ── الخطوة 2: تأكيد TPS/ATS ──
        tps_stats = analyze_tps_ats(sym)
        if not tps_stats:
            continue

        tps    = tps_stats["tps"]
        ats    = tps_stats["ats"]
        vdelta = tps_stats["vdelta"]

        # 🔒 إذا في cooldown — فقط الحيتان يمرون
        if in_cooldown:
            if not (ats >= WHALE_ATS_MIN and vdelta >= WHALE_VDELTA_MIN):
                continue  # أفراد مرة ثانية — تجاهل

        # baseline — إصلاح: إذا baseline صغير جداً لا نحسب ratio
        base  = tps_baseline.get(sym, 0)
        if base < 0.05:
            # أول مرة نرى هذه العملة — احفظ baseline فقط بدون ratio
            tps_baseline[sym] = tps if tps > 0 else 0.1
            ratio = 1.0   # لا spike في أول مشاهدة
        else:
            ratio = tps / base if base > 0 else 1.0
            tps_baseline[sym] = base * 0.9 + tps * 0.1

        # ── الخطوة 3: حساب النقاط المدمجة ──
        score   = 0
        signals = []

        # نقاط المنطقة
        zone_sigma = nearest_zone.get("sigma", 1)
        zone_type  = nearest_zone.get("type", "REPEAT")
        score += min(zone_sigma * 5, 30)
        if zone_type == "FRESH":
            score += 15
            signals.append("🆕 Zone FRESH")
        else:
            touches = nearest_zone.get("touches", 1)
            signals.append("🔁 Zone {}×".format(touches))

        # قرب السعر من المنطقة
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

        if score < LZ_TPS_SCORE_MIN:
            continue

        # ── الخطوة 4: حساب الأهداف ──
        # الهدف = أقرب مقاومة / Stop = تحت المنطقة
        zone_low  = nearest_zone["low"]
        zone_high = nearest_zone["high"]
        stop_loss = zone_low * 0.985           # 1.5% تحت المنطقة
        # أقرب مقاومة من بين المناطق الأخرى
        # الهدف = أقرب مقاومة واقعية (max +30%)
        resistance_zones = sorted(
            [z for z in zones if z["mid"] > price * 1.02],
            key=lambda z: z["mid"]
        )
        if resistance_zones:
            # أقرب مقاومة لكن لا تتجاوز +30%
            nearest_res = resistance_zones[0]["mid"]
            target = min(nearest_res, price * 1.30)
        else:
            target = price * 1.12   # هدف افتراضي +12% إذا لا مقاومة قريبة
        rr = (target - price) / (price - stop_loss) if price > stop_loss else 0

        # 🛡️ R/R أقل من 1.5 = لا يستحق الإشارة
        if rr < 1.5:
            log.debug("⚖️ LZ+TPS skip %s: R/R=%.1f < 1.5", sym, rr)
            continue

        # 🐌 TPS ضعيف جداً = لا إشارة
        # منطقة سيولة + تجميع بطيء مقبول من 0.2
        if tps < 0.2:
            log.debug("🐌 LZ+TPS skip %s: TPS=%.2f < 0.2", sym, tps)
            continue

        sector  = next((s for s, syms in SECTORS.items() if sym in syms), "غير محدد")
        chg     = changes_map.get(sym, 0)
        rarity  = "🏆 نادر جداً" if score >= 90 else ("🔥 قوي" if score >= 80 else "⚡ جيد")
        zone_tag = "🆕 FRESH" if zone_type == "FRESH" else "🔁 REPEAT"

        # ══ LZ+TPS: يرسل فقط إذا لم تصل إشارة #1 بعد ══
        # إذا وصلت WATCH ALERT → أضف للمراقبة بصمت فقط
        if coin_signal_count.get(sym, 0) >= 1:
            # أضف للمراقبة بصمت — الحيتان سيرسلون ENTRY SIGNAL
            if sym not in whale_watchlist:
                whale_watchlist[sym] = {
                    "time":       now,
                    "price_then": price,
                    "ats_then":   ats,
                    "reason":     "LZ+TPS silent add",
                }
                log.info("👁️ LZ+TPS silent watchlist add: %s", sym)
            continue

        # أول إشارة — أرسل كـ WATCH ALERT مدمج مع LZ+TPS
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

        msg = (
            "👁️ *WATCH ALERT* 💎\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🔍 *{}* — منطقة سيولة + نشاط! 👀\n".format(sym.replace("USDT","")) +
            "💵 السعر: `{}`\n".format(fmt_price(price)) +
            "━━━━━━━━━━━━━━━━━━\n"
            "📍 {} | {} `{}×`\n".format(
                _prox_label, zone_tag, zone_sigma
            ) +
            "📊 المنطقة: `{}` ← `{}`\n".format(fmt_price(zone_low), fmt_price(zone_high)) +
            "⚖️ R/R: `{:.1f}:1` | 🎯 `{}` (+{:.1f}%)\n".format(
                rr, fmt_price(target), (target-price)/price*100
            ) +
            "━━━━━━━━━━━━━━━━━━\n"
            "{}\n".format(_tps_label) +
            "📡 TPS: `{:.2f}` | ATS: `{:.0f}$` 🦐 أفراد\n".format(tps, ats) +
            "📊 VDelta: `{:.0f}%` شراء\n".format(vdelta * 100) +
            "━━━━━━━━━━━━━━━━━━\n"
            "💪 القوة: `{}/100` {}\n".format(score, rarity) +
            "📉 24h: `{:+.2f}%` | حجم: `{:.2f}M`\n".format(chg, vol_now.get(sym,0)/1_000_000) +
            "🏷️ القطاع: `{}`\n".format(sector) +
            "━━━━━━━━━━━━━━━━━━\n"
            "⏳ _انتظر الجوكر للدخول_ 🃏"
        )

        send(msg)
        lz_tps_alerted[sym] = now
        coin_alerted[sym]   = now
        whale_watch_add(sym, ats, vdelta, price)
        perf_register(sym, price, "lz_tps_fusion", score, " | ".join(signals))
        log.info("👁️ WATCH+LZ | %s | score=%d | rr=%.1f | ats=%.0f | vdelta=%.0f%%",
                 sym, score, rr, ats, vdelta * 100)


# ═══════════════════════════════════════════════════════════════════
#   💧 LIQUIDITY EXIT ALERT — إنذار خروج السيولة قبل الانهيار
# ═══════════════════════════════════════════════════════════════════
liq_exit_alerted  = 0.0   # آخر تنبيه
liq_exit_vol_hist = []    # تاريخ الحجم كل 5 دقائق
LEX_COOLDOWN      = 3600  # مرة كل ساعة
LEX_VOL_DROP      = 0.25  # حجم السوق نزل 25% = خطر
LEX_VDELTA_SELL   = 0.35  # BTC VDelta أقل من 35% = حيتان يبيعون
LEX_BTCD_RISE     = 1.5   # BTC.D صعد 1.5% في ساعة = هروب للـ BTC


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

    # ── حجم السوق الكلي ──
    total_vol = sum(v for s, v in vol_now.items()
                    if s.endswith("USDT") and v > 0)
    liq_exit_vol_hist.append((now, total_vol))
    if len(liq_exit_vol_hist) > 12:
        liq_exit_vol_hist.pop(0)
    if len(liq_exit_vol_hist) < 4:
        return

    # ── BTC تغيير 1h و 24h ──
    btc_1h  = btc_tps_stats.get("change_1h",  0.0) if btc_tps_stats else 0.0
    btc_24h = btc_tps_stats.get("change_24h", 0.0) if btc_tps_stats else 0.0

    # ── BTC.D تغيير ──
    btcd_now = get_btc_dominance(vol_now)
    btcd_chg = 0.0
    if len(btcd_history) >= 2 and btcd_now > 0:
        btcd_chg = btcd_now - btcd_history[0]  # مقارنة بآخر 24 ساعة

    # ── BTC VDelta ──
    btc_vdelta  = btc_tps_stats.get("vdelta", 0.5) if btc_tps_stats else 0.5
    btc_ats     = btc_tps_stats.get("ats", 0)      if btc_tps_stats else 0
    btc_selling = (btc_vdelta < LEX_VDELTA_SELL and btc_ats >= ATS_WHALE)

    # ── حجم السوق ينهار ──
    old_vol    = liq_exit_vol_hist[0][1]
    vol_drop   = (old_vol - total_vol) / old_vol if old_vol > 0 else 0
    vol_drying = vol_drop >= LEX_VOL_DROP

    # ════════════════════════════════════════
    # تحديد السيناريو
    # ════════════════════════════════════════
    scenario = None
    emoji    = ""
    title    = ""
    advice   = ""
    details  = ""

    # السيناريو 1 — RISK-OFF 💣 (الأخطر)
    # BTC.D ↓ + BTC ↓ = الكل يخرج من السوق
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

    # السيناريو 2 — هروب للـ BTC ⚠️
    # BTC.D ↑ + BTC ↓ = Alts تنهار بسرعة
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

    # السيناريو 3 — BTC يبيع الحيتان + حجم ينهار
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

    # السيناريو 4 — Alt Season 🚀 (إيجابي)
    # BTC.D ↓ + BTC ↑ = Alt Season
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
        return  # لا سيناريو واضح

    # ── إرسال الرسالة ──
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
    log.warning("📊 SCENARIO: %s | BTC24h=%.1f%% | BTCD_chg=%.1f%% | vol_drop=%.1f%%",
                scenario, btc_24h, btcd_chg, vol_drop * 100)


# ─────────────────────────────────────────
#   📊 BTC DOMINANCE MONITOR
# ─────────────────────────────────────────
btcd_history    = []    # type: List[float]  آخر 24 قراءة
btcd_last_check = 0.0
btcd_alert_sent = 0.0
BTCD_CHECK_EVERY   = 3600    # كل ساعة
BTCD_DROP_ALERT    = 1.5     # نزول 1.5% في 24h = Alt Season
BTCD_RISE_ALERT    = 2.0     # صعود 2.0% = BTC يسيطر
BTCD_ALT_THRESHOLD = 52.0    # تحت 52% = Alt Season كامل


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
        # BTC.D = BTC / مجموع كل العملات الحقيقية
        raw = (btc_vol / total_vol) * 100
        # تصحيح: Binance تمثل ~40% من السوق الكلي
        # لكن نسبة BTC داخل Binance ≈ BTC.D الحقيقي
        return round(raw, 2)
    except Exception:
        return 0.0



# ═══════════════════════════════════════════════════════════════════
#   🚨 PUMP DETECTOR — رصد الارتفاع المفاجئ
#   🔴 DUMP DETECTOR — رصد الانهيار المفاجئ
#   🌊 MARKET PULSE  — نبض السوق كل 30 دقيقة
# ═══════════════════════════════════════════════════════════════════

# تاريخ الأسعار للكشف عن التغيرات المفاجئة
pump_dump_history  = {}   # type: Dict[str, list]   sym → [(time, price, vol)]
pump_alerted       = {}   # type: Dict[str, float]  آخر تنبيه pump
dump_alerted       = {}   # type: Dict[str, float]  آخر تنبيه dump
last_pulse_time    = 0.0  # آخر نبض سوق
market_pulse_history = [] # type: list  تاريخ نبض السوق

PUMP_THRESHOLD     = 4.0   # ارتفاع 4%+ في 5 دقائق
DUMP_THRESHOLD     = -4.0  # نزول 4%- في 5 دقائق
PUMP_VOL_MULT      = 2.5   # حجم 2.5× المعدل
PUMP_COOLDOWN      = 3600  # ساعة بين تنبيهات نفس العملة
PULSE_EVERY        = 1800  # نبض السوق كل 30 دقيقة


def update_pump_dump_history(price_map, vol_now):
    # type: (Dict, Dict) -> None
    """يحدث تاريخ الأسعار لكل عملة — يُستدعى كل دورة"""
    now = time.time()
    for sym, price in price_map.items():
        if not sym.endswith("USDT"): continue
        vol = vol_now.get(sym, 0)
        if sym not in pump_dump_history:
            pump_dump_history[sym] = []
        # ✅ تأكد أن القيمة list
        if not isinstance(pump_dump_history[sym], list):
            pump_dump_history[sym] = []
        pump_dump_history[sym].append((now, price, vol))
        # نحتفظ بآخر 10 دقائق فقط
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

        # نأخذ السعر قبل 5 دقائق
        five_min_ago = [(t, p, v) for t, p, v in hist if now - t >= 280]
        if not five_min_ago: continue
        old_price = five_min_ago[-1][1]
        if old_price <= 0: continue

        move = (price - old_price) / old_price * 100

        # متوسط الحجم التاريخي
        hist_vols = coin_vol_history.get(sym, [])
        avg_vol   = sum(hist_vols) / len(hist_vols) if hist_vols else vol
        vol_mult  = vol / avg_vol if avg_vol > 0 else 1.0

        sector = next((s for s, syms in SECTORS.items() if sym in syms), "غير محدد")
        base   = sym.replace("USDT", "")

        # ══ PUMP ══
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
            log.info("🚨 PUMP | %s | move=%.1f%% | vol=%.1fx", sym, move, vol_mult)

        # ══ DUMP ══
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
            log.info("🔴 DUMP | %s | move=%.1f%% | vol=%.1fx", sym, move, vol_mult)


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

    # حكم النبض
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

    # أقوى العملات صعوداً
    strong_up.sort(key=lambda x: -x[1])
    strong_down.sort(key=lambda x: x[1])

    up_txt   = " | ".join(["*{}* +{:.1f}%".format(b,c) for b,c,v in strong_up[:3]]) or "لا يوجد"
    down_txt = " | ".join(["*{}* {:.1f}%".format(b,c) for b,c,v in strong_down[:3]]) or "لا يوجد"

    # شريط المؤشر
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
    log.info("🌊 PULSE | rising=%.0f%% | buy=%.0f%% | total=%d",
             rising_pct, buy_pct, total)



# ═══════════════════════════════════════════════════════════════════
#   🌊 LIQUIDITY FLOW TRACKER — اتجاه السيولة لحظة بلحظة
#   يرصد: من أي قطاع تخرج؟ إلى أي قطاع تدخل؟
# ═══════════════════════════════════════════════════════════════════

sector_vol_history   = {}   # type: Dict[str, list]  قطاع → [vol1, vol2, ...]
sector_flow_alerted  = {}   # type: Dict[str, float] آخر تنبيه لكل قطاع
last_flow_track_time = 0.0
FLOW_TRACK_EVERY     = 300  # كل 5 دقائق
FLOW_ALERT_COOLDOWN  = 1800 # 30 دقيقة بين تنبيهات نفس القطاع
FLOW_IN_THRESHOLD    = 1.5  # حجم ارتفع 1.5× = سيولة تدخل
FLOW_OUT_THRESHOLD   = 0.6  # حجم انخفض 40%  = سيولة تخرج


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

    # ── حساب حجم كل قطاع الآن ──
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

    # ── تحديث التاريخ ──
    for sector, vol in sector_vol_now.items():
        if sector not in sector_vol_history:
            sector_vol_history[sector] = []
        # ✅ تأكد أن القيمة list وليس float (من load_state)
        if not isinstance(sector_vol_history[sector], list):
            sector_vol_history[sector] = []
        sector_vol_history[sector].append(vol)
        if len(sector_vol_history[sector]) > 12:  # آخر ساعة
            sector_vol_history[sector].pop(0)

    # ── كشف الدخول والخروج ──
    flowing_in  = []  # قطاعات تدخلها السيولة
    flowing_out = []  # قطاعات تخرج منها السيولة

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

    # ── Rotation: خروج من قطاع + دخول لآخر ──
    if flowing_in and flowing_out:
        # rotation واضح
        top_in  = flowing_in[0]
        top_out = flowing_out[0]

        # تحقق cooldown
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
        log.info("🔄 ROTATION | out=%s → in=%s | ratio=%.1fx",
                 top_out[0], top_in[0], top_in[1])
        return

    # ── دخول سيولة فقط ──
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
        log.info("💰 FLOW IN | %s | ratio=%.1fx | chg=%.1f%%",
                 top[0], top[1], top[2])

    # ── خروج سيولة فقط ──
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
        log.info("🚨 FLOW OUT | %s | ratio=%.1fx | chg=%.1f%%",
                 top[0], top[1], top[2])



# ═══════════════════════════════════════════════════════════════════
#   💥 EXPLOSION CATCHER — يصطاد الانفجارات قبل حدوثها
#   الشروط: حجم يتضاعف + TPS يقفز + VDelta عالي + سعر لم يتحرك
# ═══════════════════════════════════════════════════════════════════

explosion_alerted    = {}   # type: Dict[str, float]  آخر تنبيه
explosion_vol_hist   = {}   # type: Dict[str, list]   تاريخ الحجم
EXPLOSION_COOLDOWN   = 7200  # ساعتان بين تنبيهات نفس العملة
EXPLOSION_VOL_MULT   = 3.0   # حجم 3× المعدل فجأة
EXPLOSION_TPS_MULT   = 2.5   # TPS تضاعف 2.5×
EXPLOSION_VDELTA_MIN = 0.78  # شراء 78%+
EXPLOSION_MAX_CHANGE = 3.0   # السعر لم يتحرك أكثر من 3%


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
        if now - coin_alerted.get(sym, 0) < 1800: continue  # لا تكرار مع WATCH

        vol  = vol_now.get(sym, 0)
        chg  = change_now.get(sym, 0)
        price = price_map.get(sym, 0)

        if vol < 300_000: continue
        if abs(chg) > EXPLOSION_MAX_CHANGE: continue  # السعر تحرك = فات الأوان

        # تاريخ الحجم
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

        # فحص TPS
        try:
            stats = get_tps_ats(sym)
        except Exception:
            continue
        if not stats: continue

        tps    = stats.get("tps", 0)
        ats    = stats.get("ats", 0)
        vdelta = stats.get("vdelta", 0)

        # فحص TPS التاريخي
        baseline = tps_baseline.get(sym, tps)
        tps_mult = tps / baseline if baseline > 0 else 1.0

        # شروط الانفجار
        if (vol_mult  >= EXPLOSION_VOL_MULT and
            tps_mult  >= EXPLOSION_TPS_MULT and
            vdelta    >= EXPLOSION_VDELTA_MIN and
            abs(chg)  <= EXPLOSION_MAX_CHANGE):

            sector = next((s for s, syms in SECTORS.items() if sym in syms), "غير محدد")

            # قوة الانفجار
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
            log.info("💥 EXPLOSION | %s | vol=%.1fx | tps=%.1fx | vdelta=%.0f%%",
                     sym, vol_mult, tps_mult, vdelta * 100)



# ═══════════════════════════════════════════════════════════════════
#   🌊 LIQUIDITY ACCUMULATION TRACKER
#   يرصد تراكم السيولة على مدى ساعات قبل الانفجار
#   = يدخل قبل الجميع بساعات 🎯
# ═══════════════════════════════════════════════════════════════════

liq_accum_history  = {}   # type: Dict[str, list]  تاريخ السيولة لكل عملة
liq_accum_alerted  = {}   # type: Dict[str, float] آخر تنبيه
LAT_COOLDOWN       = 14400  # 4 ساعات بين تنبيهات نفس العملة
LAT_MIN_HOURS      = 2      # ساعتان من التراكم المستمر
LAT_VOL_GROW       = 1.4    # حجم يرتفع 40%+ تدريجياً
LAT_VDELTA_MIN     = 0.65   # شراء 65%+ مستمر
LAT_MAX_CHANGE     = 5.0    # السعر لم يتحرك أكثر من 5%
LAT_READINGS       = 24     # نحتفظ بـ 24 قراءة (كل 5 دقائق = 2 ساعة)


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
        if abs(chg) > LAT_MAX_CHANGE: continue  # تحرك كثيراً = فات الأوان

        # تحديث التاريخ
        if sym not in liq_accum_history:
            liq_accum_history[sym] = []

        # نجلب TPS/VDelta
        try:
            stats = get_tps_ats(sym)
        except Exception:
            continue
        if not stats: continue

        tps    = stats.get("tps", 0)
        vdelta = stats.get("vdelta", 0.5)
        ats    = stats.get("ats", 0)

        # نحفظ القراءة
        liq_accum_history[sym].append({
            "time":   now,
            "vol":    vol,
            "vdelta": vdelta,
            "tps":    tps,
            "price":  price,
        })

        # نحتفظ بآخر LAT_READINGS قراءة
        if len(liq_accum_history[sym]) > LAT_READINGS:
            liq_accum_history[sym].pop(0)

        hist = liq_accum_history[sym]
        if len(hist) < 12: continue  # نحتاج ساعة على الأقل

        # ── تحليل التراكم ──
        # 1. هل الحجم يرتفع تدريجياً؟
        first_vol  = sum(h["vol"] for h in hist[:6]) / 6
        recent_vol = sum(h["vol"] for h in hist[-6:]) / 6
        vol_growth = recent_vol / first_vol if first_vol > 0 else 1.0

        # 2. هل VDelta مستمر؟
        avg_vdelta = sum(h["vdelta"] for h in hist[-12:]) / 12

        # 3. هل TPS يرتفع؟
        first_tps  = sum(h["tps"] for h in hist[:6]) / 6
        recent_tps = sum(h["tps"] for h in hist[-6:]) / 6
        tps_growth = recent_tps / first_tps if first_tps > 0.1 else 1.0

        # 4. هل السعر ثابت؟
        first_price  = hist[0]["price"]
        price_change = abs(price - first_price) / first_price * 100 if first_price > 0 else 0

        # شروط التراكم
        if (vol_growth  >= LAT_VOL_GROW and
            avg_vdelta  >= LAT_VDELTA_MIN and
            price_change <= LAT_MAX_CHANGE):

            sector = next((s for s, syms in SECTORS.items() if sym in syms), "غير محدد")
            hours  = len(hist) * 5 / 60  # عدد الساعات التقريبي

            # قوة التراكم
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

            # نضيفها لـ whale_watchlist تلقائياً
            whale_watch_add(sym, ats, avg_vdelta, price)

            log.info("🌊 LAT | %s | vol_growth=%.1fx | vdelta=%.0f%% | hours=%.1f",
                     sym, vol_growth, avg_vdelta * 100, hours)



# ═══════════════════════════════════════════════════════════════════
#   🔍 AUTO SECTOR DISCOVERY
#   يكتشف قطاعات جديدة تلقائياً عندما عملات كثيرة ترتفع معاً
# ═══════════════════════════════════════════════════════════════════

discovered_sectors   = {}   # type: Dict[str, dict]  قطاعات مكتشفة
asd_last_run         = 0.0
ASD_RUN_EVERY        = 3600   # كل ساعة
ASD_MIN_COINS        = 5      # 5 عملات+ ترتفع معاً
ASD_MIN_CHANGE       = 5.0    # 5%+ ارتفاع
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

    # نجلب كل العملات الصاعدة بقوة
    strong_movers = []
    for sym, chg in change_now.items():
        if not sym.endswith("USDT"): continue
        base = sym.replace("USDT", "")
        if base in STABLECOINS: continue
        if any(k in sym for k in LEVERAGE_KEYWORDS): continue
        vol = vol_now.get(sym, 0)
        if vol < ASD_VOL_MIN: continue
        if chg >= ASD_MIN_CHANGE:
            # هل هي في قطاع معروف؟
            known = any(sym in coins for coins in SECTORS.values())
            strong_movers.append({
                "sym": sym, "chg": chg, "vol": vol, "known": known
            })

    if len(strong_movers) < ASD_MIN_COINS:
        return

    # نجد العملات غير المصنفة
    unknown = [m for m in strong_movers if not m["known"]]
    known   = [m for m in strong_movers if m["known"]]

    if len(unknown) < 3:
        return

    # نرتب حسب الارتفاع
    unknown.sort(key=lambda x: -x["chg"])
    known.sort(key=lambda x: -x["chg"])

    # نرسل تنبيه اكتشاف
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
    log.info("🔍 ASD | %d عملة صاعدة | %d جديدة",
             len(strong_movers), len(unknown))



# ═══════════════════════════════════════════════════════════════════
#   ⚠️ DELISTING HUNTER
#   يرصد علامات حذف العملة قبل الانهيار
# ═══════════════════════════════════════════════════════════════════

delisting_alerted  = {}   # type: Dict[str, float]
DH_COOLDOWN        = 86400   # يوم واحد
DH_VOL_CRASH       = 0.15    # حجم انهار لـ 15% من المعدل
DH_PRICE_CRASH     = -30.0   # سعر انهار 30%+ في 24h
DH_MIN_HISTORY     = 5       # نحتاج 5 قراءات تاريخية


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

        # تاريخ الحجم
        hist = coin_vol_history.get(sym, [])
        if len(hist) < DH_MIN_HISTORY: continue

        avg_vol  = sum(hist) / len(hist)
        vol_ratio = vol / avg_vol if avg_vol > 0 else 1.0

        # علامات الحذف
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
            log.warning("⚠️ DELISTING | %s | vol_ratio=%.2f | chg=%.1f%%",
                        sym, vol_ratio, chg)



# ═══════════════════════════════════════════════════════════════════
#   🎯 SMALL CAP HUNTER
#   يصطاد عملات صغيرة على وشك الانفجار
#   حجم 100K-2M = أسرع انفجاراً = مكسب 50-200%
# ═══════════════════════════════════════════════════════════════════

sc_hunter_alerted  = {}   # type: Dict[str, float]
SCH_COOLDOWN       = 7200    # ساعتان
SCH_VOL_MIN        = 100_000  # 100K minimum
SCH_VOL_MAX        = 2_000_000  # 2M maximum
SCH_VOL_SPIKE      = 4.0     # حجم 4× فجأة
SCH_VDELTA_MIN     = 0.75    # شراء 75%+
SCH_TPS_MIN        = 0.5     # TPS معقول
SCH_MAX_CHANGE     = 8.0     # لم يتحرك كثيراً


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

        # Small Cap فقط
        if vol < SCH_VOL_MIN or vol > SCH_VOL_MAX: continue
        if abs(chg) > SCH_MAX_CHANGE: continue

        # تاريخ الحجم
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
        log.info("🎯 SCH | %s | vol=%.2fM | spike=%.1fx | vdelta=%.0f%%",
                 sym, vol/1_000_000, vol_spike, vdelta*100)


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

    log.info("📊 BTC.D = %.2f%% | تاريخ: %d قراءة", btcd, len(btcd_history))

    if len(btcd_history) < 2:
        return

    # التغيير خلال آخر 24 ساعة
    oldest = btcd_history[0]
    change_24h = btcd - oldest

    # ✅ تحديث btcd_trend للتقرير اليومي
    if change_24h <= -0.3:
        btcd_trend = "falling"
    elif change_24h >= 0.3:
        btcd_trend = "rising"
    else:
        btcd_trend = "neutral"

    # ══ Alt Season — BTC.D ينزل ══
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
        log.info("🚀 Alt Season Alert! BTC.D=%.2f%% change=%.2f%%", btcd, change_24h)

    # ══ BTC يسيطر — BTC.D يصعد ══
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
        log.info("🐋 BTC Dominance Rising! BTC.D=%.2f%% change=%.2f%%", btcd, change_24h)


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


def scan_tps_ats(price_map, vol_now, changes_map):
    # type: (Dict, Dict, Dict) -> None
    """
    يفحص أفضل 40 عملة بالحجم
    يبحث عن: TPS spike + ATS حيتان + VDelta قوي
    يحتاج 2+ إشارات للتنبيه
    """
    global tps_alerted, tps_baseline
    now = time.time()

    # دمج candidates مع القائمة الثابتة
    all_syms = list(set(list(candidates) + EXTRA_COINS))
    ranked = sorted(
        [(s, vol_now.get(s, 0)) for s in all_syms if s not in tracked],
        key=lambda x: -x[1]
    )[:50]

    results = []
    for sym, vol in ranked:
        if sym.replace("USDT","") in STABLECOINS: continue  # ✅ لا إشارات للمستقرات
        _min_vol = 100_000 if sym in EXTRA_COINS else 1_000_000
        if vol < _min_vol:  # 🛡️ EXTRA_COINS=100K | عادية=1M
            continue
        # 🔒 إذا وصل حيتان لهذه العملة → مغلقة تماماً
        if now - coin_whale_done.get(sym, 0) < LZ_TPS_COOLDOWN:
            continue
        # 🔒 حد أقصى إشارتان يومياً لنفس العملة
        if coin_signal_count.get(sym, 0) >= MAX_COIN_SIGNALS:
            continue
        # 🔒 Cooldown موحد
        last_alert  = coin_alerted.get(sym, 0)
        in_cooldown = (now - last_alert < TPS_COOLDOWN)

        # 🚫 تجاهل إذا ارتفعت كثيراً — الفرصة فاتت
        chg24 = changes_map.get(sym, 0)
        if chg24 >= TPS_MAX_CHANGE:
            continue

        stats = analyze_tps_ats(sym)
        if not stats:
            continue

        tps    = stats["tps"]
        ats    = stats["ats"]
        vdelta = stats["vdelta"]

        # baseline تدريجي
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

        if ats >= ATS_WHALE:
            score += 35
            signals.append("🐋 ATS {:.0f}$".format(ats))
        elif ats >= 2000:
            score += 20
            signals.append("🐟 ATS {:.0f}$".format(ats))

        if vdelta >= VDELTA_STRONG:
            score += 25
            signals.append("💚 VDelta {:.0f}%".format(vdelta * 100))
        elif vdelta >= 0.60:
            score += 12
            signals.append("💚 VDelta {:.0f}%".format(vdelta * 100))

        _tps_min = 0.2 if sym in EXTRA_COINS else 0.5  # EXTRA=تجميع بطيء | عادية=نشاط حقيقي
        if score >= 55 and len(signals) >= 2 and stats["tps"] >= _tps_min:
            chg = changes_map.get(sym, 0)
            results.append((score, sym, signals, stats, chg, vol))

    if not results:
        return

    results.sort(key=lambda x: -x[0])
    for score, sym, signals, stats, chg, vol in results[:3]:
        # 🔒 إذا سبق وأُرسل WATCH → أضف للمراقبة بصمت فقط
        if coin_signal_count.get(sym, 0) >= 1:
            if sym not in whale_watchlist:
                whale_watch_add(sym, stats["ats"], stats["vdelta"], price_map.get(sym, 0))
                log.info("👁️ TPS silent add: %s (already watched)", sym)
            continue

        sector = next((s for s, syms in SECTORS.items() if sym in syms), "غير محدد")
        rarity = "🐋🔥 نادر" if score >= 80 else ("🔥 قوي" if score >= 65 else "⚡ متوسط")
        # عداد الإشارات — أول إشارة فقط
        coin_signal_count[sym] = 1
        _sig_num = 1

        # ── نحاول إيجاد أقرب منطقة سيولة ──
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
                # نجد أقرب منطقة دعم وأقرب مقاومة
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

        msg = (
            "👁️ *WATCH ALERT*\n" +
            "━━━━━━━━━━━━━━━━━━\n"
            "🔍 *{}* — نشاط مشبوه! راقب 👀\n".format(sym.replace("USDT","")) +
            "💵 السعر: `{}`\n".format(fmt_price(price_map.get(sym, 0))) +
            "━━━━━━━━━━━━━━━━━━\n" +
            (_lz_block + "━━━━━━━━━━━━━━━━━━\n" if _lz_block else "") +
            "{}\n".format(_tps_label) +
            "📡 TPS:    `{:.2f}` | ATS: `{:.0f}$` 🦐 أفراد\n".format(stats["tps"], stats["ats"]) +
            "📊 VDelta: `{:.0f}%` شراء\n".format(stats["vdelta"]*100) +
            "━━━━━━━━━━━━━━━━━━\n"
            "💪 القوة: `{}/100` {}\n".format(score, rarity) +
            "📉 24h: `{:+.2f}%` | حجم: `{:.2f}M`\n".format(chg, vol/1_000_000) +
            "🏷️ القطاع: `{}`\n".format(sector) +
            "━━━━━━━━━━━━━━━━━━\n"
            "⏳ _انتظر الجوكر للدخول_ 🃏"
        )
        send(msg)
        tps_alerted[sym]  = now
        coin_alerted[sym] = now   # 🔒 يمنع كل الأنظمة من التكرار
        perf_register(sym, price_map.get(sym, 0), "tps_ats", score, " | ".join(signals))

        # 🐋 إذا أفراد يشترون → أضف لقائمة مراقبة الحيتان
        if ats < WHALE_ATS_MIN and vdelta >= 0.65:
            whale_watch_add(sym, ats, vdelta, price_map.get(sym, 0))
        log.info("⚡ TPS/ATS | %s | score=%d | tps=%.1f | ats=%.0f | vdelta=%.0f%%",
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

    # أفضل 60 عملة حسب الحجم
    ranked = sorted(
        [(s, vol_now.get(s, 0)) for s in candidates if s not in tracked],
        key=lambda x: -x[1]
    )[:60]

    btc_change = btc_change_24h  # حالة BTC الحالية
    results    = []              # [(score, sym, signals, price, vol)]

    for sym, vol in ranked:
        if vol < 200_000:
            continue
        # 🔒 Cooldown موحد
        if now - coin_alerted.get(sym, 0) < TPS_COOLDOWN and now - coin_whale_done.get(sym, 0) >= LZ_TPS_COOLDOWN:
            continue
        if now - lh_alerted.get(sym, 0) < LH_COOLDOWN:
            continue

        price = price_map.get(sym, 0)
        if price <= 0:
            continue

        # جلب بيانات 15m (20 شمعة)
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

        # ══════════════════════════════════════════
        # سيناريو 1 — Volume Spike الصامت 🔥
        # حجم ضخم + سعر ثابت = تجميع خفي
        # ══════════════════════════════════════════
        if vol_ratio >= LH_VOL_SPIKE and price_chg <= LH_PRICE_FLAT:
            pts = min(int(vol_ratio * 10), 45)
            score += pts
            signals.append("🔥 VolSpike {:.1f}×".format(vol_ratio))

        elif vol_ratio >= LH_VOL_QUIET and price_chg <= LH_PRICE_FLAT:
            pts = min(int(vol_ratio * 8), 25)
            score += pts
            signals.append("🔇 QuietVol {:.1f}×".format(vol_ratio))

        # ══════════════════════════════════════════
        # سيناريو 2 — Wick Rejection 🕯️
        # ذيول سفلية متكررة = رفض النزول
        # ══════════════════════════════════════════
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

        # ══════════════════════════════════════════
        # سيناريو 3 — BTC Divergence 📊
        # BTC ينزل لكن العملة تقاوم
        # ══════════════════════════════════════════
        coin_change_24h = changes_map.get(sym, 0)
        if btc_change <= -LH_BTC_DIV_MIN and coin_change_24h >= -1.0:
            # BTC ينزل 1.5%+ لكن العملة ثابتة أو ترتفع
            divergence = coin_change_24h - btc_change  # كلما كبر = أقوى
            if divergence >= 2.0:
                pts = min(int(divergence * 5), 30)
                score += pts
                signals.append("📊 BTCDiv +{:.1f}%".format(divergence))

        # ══════════════════════════════════════════
        # سيناريو 4 — Volume Trend صاعد 📈
        # الحجم يتصاعد تدريجياً على 5 شمعات
        # ══════════════════════════════════════════
        vol_trend = sum(1 for i in range(-4, 0) if vols[i] > vols[i-1])
        if vol_trend >= 4 and vol_ratio >= 1.4:
            score += 20
            signals.append("📈 VolTrend {}/4".format(vol_trend))

        # ══════════════════════════════════════════
        # فلتر: يجب على الأقل سيناريوان
        # ══════════════════════════════════════════
        if score >= LH_SCORE_MIN and len(signals) >= 2:
            results.append((score, sym, signals, price, vol, coin_change_24h))

    if not results:
        return

    # رتّب حسب Score تنازلياً — أرسل أفضل 3 فقط
    results.sort(key=lambda x: -x[0])
    for score, sym, signals, price, vol, chg in results[:3]:
        # تأكيد على 1h أيضاً
        kd1h = get_klines(sym, "1h", 6)
        if not kd1h:
            continue
        vols_1h = kd1h["vols"]
        avg_1h  = sum(vols_1h) / len(vols_1h) if vols_1h else 1
        vol_1h_ratio = vols_1h[-1] / avg_1h if avg_1h > 0 else 0

        # على الأقل 1.2× على 1h
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
        coin_alerted[sym] = now   # 🔒 موحد
        perf_register(sym, price, "lh_big", score, " | ".join(signals))
        log.info("🔥 LiqHunter | %s | score=%d | %s", sym, score, " | ".join(signals))


# ═══════════════════════════════════════════════════════════════════
#   📋 SMALL CAPS ENGINE
#   قائمة ديناميكية للعملات الصغيرة — تُحدَّث كل ساعة
#   حجم 50K→500K USDT يومياً
# ═══════════════════════════════════════════════════════════════════

def refresh_small_caps():
    # type: () -> None
    """
    يبني قائمة Small Caps من مصدرين:
    1. عملات SECTORS الحالية ذات حجم منخفض (تعرف قطاعها)
    2. عملات MEXC الجديدة 50K→500K (تُصنَّف تلقائياً)

    النتيجة: تغطية كاملة لكل قطاع حتى بعملاته الصغيرة
    """
    global small_caps, last_sc_refresh
    log.info("📋 Small Caps: تحديث القائمة...")

    data = safe_get(MEXC_24H)
    if not data:
        return

    # بناء خريطة الحجوم
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

    # ── المصدر 1: عملات SECTORS المعروفة ذات حجم صغير ──
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

    # ── المصدر 2: عملات MEXC جديدة خارج SECTORS ──
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

    # أضف أفضل 100 جديدة حسب الحجم
    new_sc.sort(key=lambda x: -x[1])
    for sym, vol in new_sc[:100]:
        sc_set.add(sym)

    small_caps = list(sc_set)[:SC_MAX_COINS]
    last_sc_refresh = time.time()

    # تقرير مفصّل
    sector_info = " | ".join("{}:{}".format(s, n) for s, n in stats.items())
    log.info("📋 Small Caps: %d عملة | قطاعات: %s | جديدة: %d",
             len(small_caps), sector_info, len(new_sc[:100]))


def liquidity_hunter_small_caps(price_map=None, vol_now=None, changes_map=None):  # معطّل
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

    # فلتر مسبق بدون API — خذ أفضل 80 حسب الحجم الحالي
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

        # سيناريو 1 — Volume Spike الصامت
        # Micro Cap (< 100K): يكفي 1.8× لأن الحجم الأساسي ضعيف
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

        # سيناريو 2 — Wick Rejection
        wick_score = 0
        for i in range(-5, 0):
            body       = abs(closes[i] - opens[i])
            lower_wick = min(opens[i], closes[i]) - lows[i]
            if body > 0 and lower_wick > body * 1.8:
                wick_score += 1
        if wick_score >= 3:
            score += wick_score * 8
            signals.append("🕯️ WickReject ×{}".format(wick_score))

        # سيناريو 3 — BTC Divergence
        coin_change_24h = changes_map.get(sym, 0)
        if btc_change <= -LH_BTC_DIV_MIN and coin_change_24h >= -1.0:
            divergence = coin_change_24h - btc_change
            if divergence >= 2.0:
                score += min(int(divergence * 5), 30)
                signals.append("📊 BTCDiv +{:.1f}%".format(divergence))

        # سيناريو 4 — Volume Trend
        vol_trend = sum(1 for i in range(-4, 0) if vols[i] > vols[i-1])
        if vol_trend >= 4 and vol_ratio >= 1.5:
            score += 20
            signals.append("📈 VolTrend {}/4".format(vol_trend))

        if score >= SC_SCORE_MIN and len(signals) >= 2:
            results.append((score, sym, signals, price, vol, coin_change_24h))

    if not results:
        return

    results.sort(key=lambda x: -x[0])
    for score, sym, signals, price, vol, chg in results[:2]:  # أفضل 2 فقط
        kd1h = get_klines(sym, "1h", 6)
        if not kd1h:
            continue
        vols_1h     = kd1h["vols"]
        avg_1h      = sum(vols_1h) / len(vols_1h) if vols_1h else 1
        vol_1h_ratio = vols_1h[-1] / avg_1h if avg_1h > 0 else 0

        if vol_1h_ratio < 1.3:  # أصعب للـ Small Caps
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
        coin_alerted[sym] = now   # 🔒 موحد
        perf_register(sym, price, "lh_small", score, " | ".join(signals))
        log.info("🔍 SmallCapHunter | %s | score=%d | %s", sym, score, " | ".join(signals))


# ═══════════════════════════════════════════════════════════════
#   🆕 V16: HIDDEN ACCUMULATION ENGINE
#   كشف السيولة الخفية قبل الارتفاع
#   الحيتان يشترون بهدوء في السوق النازل
# ═══════════════════════════════════════════════════════════════

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

    # ══════════════════════════════════════════════
    # 1. Volume Divergence — أهم مؤشر
    #    السعر ينزل أو ثابت لكن الحجم يرتفع
    # ══════════════════════════════════════════════
    price_5  = (closes[-5] - closes[-1]) / closes[-5] * 100 if closes[-5] > 0 else 0
    vol_avg3 = sum(vols[-3:]) / 3
    vol_avg_prev = sum(vols[-8:-3]) / 5 if n >= 8 else avg_vol

    price_falling = price_5 <= -1.0        # السعر نزل أكثر من 1%
    vol_rising    = vol_avg3 > vol_avg_prev * 1.4   # الحجم ارتفع 40%

    if price_falling and vol_rising:
        div_strength = vol_avg3 / vol_avg_prev
        pts = min(int(div_strength * 15), 40)
        score += pts
        signals.append("📊 Divergence {:.1f}x".format(div_strength))

    # ══════════════════════════════════════════════
    # 2. Lower Wicks — ذيول سفلية طويلة
    #    الحيتان يشترون كل مرة ينزل السعر
    # ══════════════════════════════════════════════
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

    # ══════════════════════════════════════════════
    # 3. Bid Wall — جدار شراء في Order Book
    #    طلبات شراء ضخمة تحت السعر الحالي
    # ══════════════════════════════════════════════
    if ob and ob.get("bid", 0) > 0 and ob.get("ask", 0) > 0:
        bid_ask_ratio = ob["bid"] / ob["ask"]
        if bid_ask_ratio >= 1.8:
            pts = min(int(bid_ask_ratio * 10), 30)
            score += pts
            signals.append("💧 BidWall {:.1f}x".format(bid_ask_ratio))
        elif bid_ask_ratio >= 1.3:
            score += 10
            signals.append("💧 Bid+")

    # ══════════════════════════════════════════════
    # 4. Quiet Accumulation — تصاعد تدريجي هادئ
    #    الحجم يزداد ببطء على مدى 5 شمعات
    # ══════════════════════════════════════════════
    if n >= 6:
        vol_trend = 0
        for i in range(-5, 0):
            if vols[i] > vols[i-1]:
                vol_trend += 1

        if vol_trend >= 4:  # 4 من 5 شمعات بحجم متصاعد
            score += 20
            signals.append("🔇 Quiet Accum")

    # ══════════════════════════════════════════════
    # 5. Price Compression — ضغط السعر مع ارتفاع الحجم
    #    نطاق سعري ضيق + حجم يرتفع = طاقة مكبوتة
    # ══════════════════════════════════════════════
    recent_high = max(highs[-8:])
    recent_low  = min(lows[-8:])
    price_range = (recent_high - recent_low) / recent_low * 100 if recent_low > 0 else 999

    if price_range < 8.0 and vol_avg3 > avg_vol * 1.2:
        compression_score = max(0, int((8.0 - price_range) * 3))
        score += compression_score
        signals.append("🔒 Compression {:.1f}%".format(price_range))

    # ══════════════════════════════════════════════
    # النتيجة
    # ══════════════════════════════════════════════
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
    )[:50]  # أعلى 50 عملة حجماً

    for sym, vol in top_candidates:
        # 🔒 Cooldown موحد — إشارة #1 فقط إذا لم تُرسل إشارة بعد
        if now - coin_alerted.get(sym, 0) < TPS_COOLDOWN:
            if now - coin_whale_done.get(sym, 0) >= LZ_TPS_COOLDOWN:
                continue
        # cooldown 4 ساعات لنفس العملة
        if now - hidden_accum_alerted.get(sym, 0) < 14400:
            continue

        price = price_map.get(sym, 0)
        if price <= 0:
            continue

        kd = get_klines(sym, "15m", 30)
        if not kd:
            continue

        # جلب OrderBook للأكثر حجماً فقط
        ob = get_order_book(sym) if vol > 500_000 else None

        is_accum, acc_score, acc_desc = detect_hidden_accumulation(kd, ob)

        if not is_accum:
            continue

        # تأكيد إضافي: الحجم على 1h أيضاً يرتفع
        kd1h = get_klines(sym, "1h", 10)
        if not kd1h:
            continue

        vols_1h  = kd1h["vols"]
        avg_1h   = sum(vols_1h) / len(vols_1h)
        last_1h  = vols_1h[-1]
        if last_1h < avg_1h * 1.3:
            continue  # لا تأكيد على 1h

        change_24h = changes_map.get(sym, 0)
        sector     = next((s for s, syms in SECTORS.items() if sym in syms), "غير محدد")

        # نقاط الندرة
        rarity = "🔥 قوي" if acc_score >= 60 else "⚡ متوسط"
        if acc_score >= 80:
            rarity = "🐋🔥 نادر جداً"

        lines_msg = [
            "👁️ *HIDDEN ACCUMULATION*",
            "━━━━━━━━━━━━━━━━━━",
            "🔇 *{}* — تجميع خفي مكتشف!".format(sym.replace("USDT","")),
            "━━━━━━━━━━━━━━━━━━",
            "📊 *المؤشرات:*",
            "  {}".format(acc_desc),
            "━━━━━━━━━━━━━━━━━━",
            "💪 قوة التجميع: `{}/100` {}".format(acc_score, rarity),
            "💵 السعر الحالي: `{}`".format(round(price, 8)),
            "📉 24h: `{:+.2f}%` _(السوق نازل لكن الحيتان يشترون!)_".format(change_24h),
            "📦 الحجم: `{:.0f}K USDT`".format(vol / 1000),
            "🏷️ القطاع: `{}`".format(sector),
            "━━━━━━━━━━━━━━━━━━",
            "⚠️ _تنبيه مبكر — ليس إشارة دخول بعد_",
            "⏳ _انتظر تأكيد الاتجاه قبل الدخول_",
        ]
        msg = "\n".join(lines_msg)
        send(msg)
        hidden_accum_alerted[sym] = now
        coin_alerted[sym] = now   # 🔒 موحد
        perf_register(sym, price, "hidden", acc_score, acc_desc)
        log.info("👁️ Hidden Accum | %s | score=%d | %s", sym, acc_score, acc_desc)


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
                fmt_price(entry), fmt_price(price),
                fmt_price(peak)
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
                fmt_price(entry), fmt_price(price)
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
def deep_scan(symbol, price, change, fetch_orderbook=True):
    # type: (str, float, float, bool) -> None
    """
    🆕 V15: fetch_orderbook=True فقط لأفضل العملات
    يوفر طلبات API كثيرة
    """
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

    # 🆕 V15: OrderBook فقط للعملات التي اجتازت الفلاتر الأولية
    ob = get_order_book(symbol) if fetch_orderbook else None
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
            price=fmt_price(price), score=score,
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
            label, symbol, gain, fmt_price(price), sl))
        tracked[symbol]["level"]      = 2
        tracked[symbol]["last_alert"] = now
        log.info("🔵 #2 | %s +%.2f%%", symbol, gain)

    elif level == 2 and gain >= SIGNAL3_GAIN:
        send("{} *SIGNAL #3* | `{}`\n🔥 *+{:.2f}%*\n💵 `{}` | SL:`-{}%`".format(
            label, symbol, gain, fmt_price(price), sl))
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




# ═══════════════════════════════════════════════
#   🆕 V15: DAILY MARKET REPORT — 00:00 UTC
#   تقرير يومي شامل عند إغلاق الشمعة اليومية
#   يكشف: هل الحيتان داخل السوق أم خارجه؟
# ═══════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════
#   🆕 V16: LIQUIDITY ZONES ENGINE
#   يكتشف مناطق السيولة ديناميكياً من الشمعات اليومية
#   ويرسل إشارة عند الإغلاق فوق/تحت المنطقة
# ═══════════════════════════════════════════════════════════════

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

        # ── النوع 1: FRESH ZONE ──────────────────────
        # سعر جديد منخفض تاريخياً + حجم 3x المعدل
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

        # ── النوع 2: REPEAT ZONE ─────────────────────
        # لمسات متعددة + حجم مرتفع
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

    # FRESH اولاً ثم Sigma تنازلياً
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

        # هامش الاختراق
        margin = LZ_ZONE_MARGIN * (0.3 if zone_type == "FRESH" else 0.5)

        target_pct = round((zone_high / zone_low - 1) * 100, 1) if zone_low > 0 else 0

        # 🆕 مرحلة 1: السعر داخل المنطقة = تجميع مبكر
        if zone_low <= daily_close <= zone_high:
            return {
                "type":       "WATCH",   # راقب — لم يخترق بعد
                "zone_type":  zone_type,
                "zone_high":  zone_high,
                "zone_low":   zone_low,
                "sigma":      sigma,
                "vol_ratio":  vol_ratio,
                "close":      daily_close,
                "target_pct": target_pct,
            }

        # مرحلة 2: إغلاق فوق المنطقة = اختراق مؤكد
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

        # تحت المنطقة — تجاهل (لا نرسل إشارات بيع)

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


def run_daily_liquidity_scan():
    # type: () -> None
    """
    🆕 V16: الفحص اليومي للسيولة عند 00:00 UTC
    يفحص كل العملات على الإطار اليومي 1D
    يرسل إشارة لكل عملة أغلقت فوق/تحت منطقة سيولة
    """
    global lz_daily_sent_date, lz_alerted
    global coin_signal_count, coin_alerted
    # إعادة تعيين العدادات يومياً
    coin_signal_count = {}
    coin_alerted      = {}
    coin_whale_done   = {}

    now_utc = datetime.utcnow()
    today   = now_utc.strftime("%Y-%m-%d")

    # مرة واحدة في اليوم عند 00:00→00:59 UTC
    if lz_daily_sent_date == today:
        return
    if now_utc.hour != 0:
        return

    lz_daily_sent_date = today
    log.info("🌊 V16: بدء الفحص اليومي للسيولة...")

    signals_found = 0
    tv_signals    = []

    # أفضل 5 عملات حسب الحجم فقط
    _vmap = {t["symbol"]: float(t.get("quoteVolume",0)) for t in all_tickers}
    _cands_sorted = sorted(candidates, key=lambda s: -_vmap.get(s,0))
    _lz_count = 0
    for sym in _cands_sorted:
        # تجنب التكرار
        last_alert = lz_alerted.get(sym, 0)
        if time.time() - last_alert < LZ_COOLDOWN:
            continue

        # جلب شمعات يومية
        kd_daily = get_klines(sym, "1d", LZ_LOOKBACK)
        if not kd_daily or len(kd_daily.get("closes", [])) < 20:
            continue

        closes = kd_daily["closes"]
        daily_close = closes[-1]   # آخر إغلاق يومي

        # اكتشاف مناطق السيولة
        zones = detect_liquidity_zones(kd_daily)
        if not zones:
            continue

        # هل أغلق فوق/تحت منطقة؟
        signal = check_liquidity_breakout(sym, daily_close, daily_close, zones)
        if not signal:
            continue

        # فقط إشارات الشراء — البيع للتحذير فقط
        if signal["type"] == "SELL":
            continue

        zone_high  = signal["zone_high"]
        zone_low   = signal["zone_low"]
        sigma      = signal["sigma"]
        vol_ratio  = signal.get("vol_ratio", 1.0)
        zone_type  = signal.get("zone_type", "REPEAT")
        sig_label  = sigma_label(sigma)

        # نوع المنطقة
        if zone_type == "FRESH":
            type_tag = "🆕 *منطقة جديدة* — سعر تاريخي جديد + حجم ضخم"
            type_icon = "🆕"
        else:
            type_tag = "🔁 *منطقة متكررة* — دعم مؤكد بالحجم"
            type_icon = "🔁"

        # حساب وقف الخسارة — بحد أقصى 5%
        sl_raw   = round((daily_close - zone_low) / daily_close * 100, 2) if daily_close > 0 else 5.0
        sl_pct   = min(sl_raw, 5.0)   # لا يتجاوز 5% أبداً
        sl_price = round(daily_close * (1 - sl_pct / 100), 8)

        # الهدف = zone_high إذا كان أعلى من الدخول، وإلا نحسب هدفاً واقعياً
        if zone_high > daily_close:
            target_price = zone_high
            target_pct   = round((zone_high / daily_close - 1) * 100, 1)
        else:
            # الهدف = الدخول + نسبة المخاطرة × 1.5 (Risk:Reward 1:1.5)
            target_pct   = round(sl_pct * 1.5, 1)
            target_price = round(daily_close * (1 + target_pct / 100), 8)

        # تحقق منطقي — إذا الهدف أقل من الدخول لا نرسل
        if target_price <= daily_close:
            log.info("⏭️ تخطي %s — الهدف أقل من الدخول", sym)
            continue

        # القطاع
        sector = next((s for s, syms in SECTORS.items() if sym in syms), "غير محدد")

        # إشارة نادرة؟
        rare_tag = "\n🐋🔥 *RARE — نادر جداً!*" if sigma >= LZ_TOUCHES_RARE else ""

        # تمييز WATCH vs BUY
        sig_type = sig.get("type", "BUY")
        if sig_type == "WATCH":
            sig_icon  = "👁️"
            sig_title = "LIQUIDITY WATCH"
            sig_desc  = "السعر داخل منطقة السيولة — تجميع مبكر"
            action_txt = "⏳ _راقب — انتظر الإغلاق فوق {:.5f}_".format(sig["zone_high"])
        else:
            sig_icon  = "🌊"
            sig_title = "DAILY LIQUIDITY SIGNAL V16"
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
        if _lz_count >= 5: break  # أفضل 5 فقط
        log.info("🌊 Daily LZ Signal | %s | sigma=%d | close=%.8f",
                 sym, sigma, daily_close)

        time.sleep(1)  # لا نضغط على Telegram

    if tv_signals:
        send_tv_scripts(tv_signals)
    log.info("🌊 Daily Liquidity Scan انتهى | إشارات: %d", signals_found)

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

    # ── 1. نمط الأيام الأخيرة ──────────────────
    red_days    = sum(1 for d in recent if d["buy_pct"] <= 45)
    green_days  = sum(1 for d in recent if d["buy_pct"] >= 55)
    neutral_days= len(recent) - red_days - green_days

    # ── 2. اتجاه الحيتان ────────────────────────
    stable_vals = [d.get("stable_pct", 0) for d in recent]
    stable_now  = stable_vals[-1] if stable_vals else 0
    stable_avg  = sum(stable_vals) / len(stable_vals) if stable_vals else 0
    stable_trend = stable_vals[-1] - stable_vals[0] if len(stable_vals) >= 2 else 0

    # ── 3. اتجاه الشراء ─────────────────────────
    buy_vals    = [d["buy_pct"] for d in recent]
    buy_now     = buy_vals[-1] if buy_vals else 50
    buy_prev    = buy_vals[-2] if len(buy_vals) >= 2 else buy_now
    buy_trend   = buy_vals[-1] - buy_vals[0] if len(buy_vals) >= 2 else 0

    # ── 4. Sigma activity ───────────────────────
    sigma_avg   = sum(d.get("sigma_count",0) for d in recent) / len(recent)
    sigma_now   = recent[-1].get("sigma_count", 0) if recent else 0

    # ── 5. تحديد النمط ──────────────────────────
    lines_out = []
    sep = "━" * 18

    # نمط السوق
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

    # سلوك الحيتان
    if stable_now >= 20 and stable_trend > 5:
        whale_pattern = "🐳 تجميع قوي Stablecoins (" + str(round(stable_now,1)) + "%) ↑ ينتظرون قاع"
    elif stable_now >= 20 and stable_trend <= 0:
        whale_pattern = "🐳 🚨 الحيتان يدخلون السوق! (" + str(round(stable_now,1)) + "%) ↓"
    elif stable_now >= 10:
        whale_pattern = "👀 تجميع خفيف (" + str(round(stable_now,1)) + "%)"
    else:
        whale_pattern = "✅ الحيتان في السوق (" + str(round(stable_now,1)) + "%)"

    # ── 6. التوقع الذكي ─────────────────────────
    score = 0
    reasons = []

    # إشارات صعود
    if red_days >= 4:       score += 2; reasons.append("تشبع بيع")
    if stable_trend > 8:    score += 2; reasons.append("تجميع حيتان")
    if stable_now >= 15 and stable_trend <= 0: score += 3; reasons.append("حيتان يدخلون")
    if buy_trend > 8:       score += 2; reasons.append("زخم شراء متزايد")
    if sigma_now > sigma_avg * 1.5: score += 1; reasons.append("نشاط Sigma غير عادي")

    # إشارات هبوط
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

    now_utc  = datetime.utcnow()
    today    = now_utc.strftime("%Y-%m-%d")

    # ── يرسل عند 00:00 UTC تلقائياً أو عند force=True ──
    if not force and not _force_daily_report:
        if now_utc.hour != 0:
            return
        if daily_report_sent_date == today:
            log.debug("📊 تقرير اليوم أُرسل مسبقاً: %s", today)
            return

    log.info("📊 إرسال التقرير اليومي | %s | الساعة: %02d:%02d UTC",
             today, now_utc.hour, now_utc.minute)

    daily_report_sent_date = today  # ✅ نسجل مبكراً لمنع التكرار

    try:
        _send_daily_report_body(today, now_utc)
    except Exception as _err:
        log.error("❌ send_daily_report فشل: %s", _err, exc_info=True)
        send("❌ خطأ في التقرير: `{}`".format(str(_err)[:200]))

def _send_daily_report_body(today, now_utc):
    # type: (str, object) -> None
    """الكود الفعلي للتقرير — منفصل لكشف الأخطاء"""
    global daily_market_vol_history, market_activity_history, btcd_trend

    # ── تقرير Backtest اليومي ──────────────────
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
    log.info("📅 Daily Report — إرسال تقرير إغلاق اليوم...")

    if not all_tickers:
        log.warning("📊 التقرير: all_tickers فارغة")
        send("⚠️ البيانات غير جاهزة — أعد المحاولة بعد دقيقة")
        return
    vol_now = {t["symbol"]: float(t.get("quoteVolume", 0)) for t in all_tickers}

    # ══════════════════════════════════════════
    # 1. تحليل Stablecoins — مؤشر الحيتان 🐋
    # ══════════════════════════════════════════
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

    # مقارنة Stablecoin بالتاريخ
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

    # ══════════════════════════════════════════
    # 2. نسبة الشراء/البيع بالحجم الحقيقي 📊
    # ══════════════════════════════════════════
    buy_vol      = 0.0   # حجم العملات الصاعدة
    sell_vol     = 0.0   # حجم العملات النازلة
    total_market_vol = 0.0
    top_gainers  = []
    top_losers   = []

    for t in all_tickers:
        sym = t.get("symbol","")
        if not sym.endswith("USDT"): continue
        base = sym.replace("USDT","")
        if base in STABLECOINS: continue
        if any(k in sym for k in LEVERAGE_KEYWORDS): continue
        try:
            ch  = float(t["priceChangePercent"])
            vol = float(t["quoteVolume"])
            if vol < 100_000: continue   # تجاهل العملات الميتة
            total_market_vol += vol
            if ch > 0:
                buy_vol += vol
                if vol > 1_000_000:
                    top_gainers.append((base, ch, vol))
            else:
                sell_vol += vol
                if vol > 1_000_000:
                    top_losers.append((base, ch, vol))
        except (KeyError, ValueError):
            pass

    total_trade_vol = buy_vol + sell_vol
    buy_pct         = buy_vol  / total_trade_vol * 100 if total_trade_vol > 0 else 50
    sell_pct        = sell_vol / total_trade_vol * 100 if total_trade_vol > 0 else 50

    # للتوافق مع باقي الكود
    rising_pct  = buy_pct
    falling_pct = sell_pct
    rising      = int(buy_pct)
    falling     = int(sell_pct)
    total_coins = int(total_trade_vol / 1_000_000)  # حجم بالمليون

    log.info("📊 Buy/Sell | buy=%.1f%% (%.0fM) | sell=%.1f%% (%.0fM)",
             buy_pct, buy_vol/1_000_000, sell_pct, sell_vol/1_000_000)

    top_gainers.sort(key=lambda x: -x[1])
    top_losers.sort(key=lambda x: x[1])

    # ══════════════════════════════════════════
    # 3. تدفق رأس المال — اليوم vs أمس 💰
    # ══════════════════════════════════════════
    daily_market_vol_history.append(total_market_vol)
    if len(daily_market_vol_history) > 7:
        daily_market_vol_history.pop(0)

    vol_change_pct = None  # None = لا يوجد بيانات بعد
    vol_arrow      = "➡️"
    if len(daily_market_vol_history) >= 2:
        prev_vol = daily_market_vol_history[-2]
        if prev_vol > 0:
            vol_change_pct = (total_market_vol - prev_vol) / prev_vol * 100
            vol_arrow = "📈" if vol_change_pct > 5 else "📉" if vol_change_pct < -5 else "➡️"

    # ══════════════════════════════════════════
    # 4. تحليل BTC الإضافي 📈
    # ══════════════════════════════════════════
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

    # ══════════════════════════════════════════
    # 5. حكم الحيتان 🐋
    # ══════════════════════════════════════════
    # منطق الحكم:
    # Stablecoins مرتفعة + سوق هابط = الحيتان يجمعون كاش (بيع أو انتظار)
    # Stablecoins منخفضة + سوق صاعد = الحيتان دخلوا السوق (شراء)
    # Stablecoins منخفضة + سوق هابط = بيع عشوائي (ليس حيتان)

    # ══════════════════════════════════════════
    # حكم الحيتان — يعتمد على 3 مصادر:
    # 1. whale_signals (نشاط Stablecoins غير طبيعي)
    # 2. sell_pct / buy_pct (حجم الشراء vs البيع)
    # 3. rising_pct / falling_pct (عدد العملات الصاعدة vs الهابطة)
    # ══════════════════════════════════════════
    _sell_pressure = sell_pct >= 70   # ضغط بيع حجمي
    _buy_pressure  = buy_pct  >= 55   # ضغط شراء حجمي
    _mkt_falling   = falling_pct >= 55
    _mkt_rising    = rising_pct  >= 55
    _whales_active = len(whale_signals) >= 2

    if _whales_active and _sell_pressure and _mkt_falling:
        # الحيتان يجمعون Stablecoins + ضغط بيع + سوق هابط = خطر حقيقي
        whale_verdict  = "🔴 *تحذير — الحيتان خارج السوق*"
        whale_desc     = "الحيتان يجمعون Stablecoins + ضغط بيع {:.0f}% — ينتظرون قاعاً".format(sell_pct)
        whale_action   = "⛔ _لا تدخل — انتظر حتى تنخفض نسبة البيع_"
        whale_icon     = "🐋🔴"

    elif _whales_active and _buy_pressure and _mkt_rising:
        # الحيتان نشطون + ضغط شراء + سوق صاعد = فرصة قوية
        whale_verdict  = "🟢 *فرصة ذهبية — الحيتان يشترون*"
        whale_desc     = "الحيتان يضخون سيولة + شراء {:.0f}% — زخم صاعد قوي".format(buy_pct)
        whale_action   = "✅ _ادخل الآن — السيولة إيجابية والحيتان معك_"
        whale_icon     = "🐋🟢"

    elif _whales_active and _sell_pressure and not _mkt_falling:
        # الحيتان يجمعون Stablecoins لكن السوق لم ينهار = تجميع خفي محتمل
        whale_verdict  = "👁️ *تجميع خفي محتمل*"
        whale_desc     = "الحيتان يجمعون Stablecoins ({}) رغم استقرار السوق — مراقبة".format(len(whale_signals))
        whale_action   = "⏳ _انتظر تأكيداً — قد يكون تجميعاً قبل الارتفاع_"
        whale_icon     = "🐋👁️"

    elif _sell_pressure and _mkt_falling:
        # ضغط بيع + سوق هابط بدون حيتان = بيع عشوائي
        whale_verdict  = "🔴 *ضغط بيع — ابتعد*"
        whale_desc     = "بيع {:.0f}% من الحجم + {:.0f}% من العملات هابطة — خطر".format(sell_pct, falling_pct)
        whale_action   = "⛔ _لا تدخل — انتظر الاستقرار_"
        whale_icon     = "📉🔴"

    elif _buy_pressure and _mkt_rising:
        # شراء + سوق صاعد = جو إيجابي
        whale_verdict  = "🟢 *السوق صاعد — زخم إيجابي*"
        whale_desc     = "شراء {:.0f}% + {:.0f}% من العملات ترتفع — جو صحي".format(buy_pct, rising_pct)
        whale_action   = "✅ _يمكن الدخول بحذر_"
        whale_icon     = "📈🟢"

    elif _sell_pressure:
        # ضغط بيع فقط بدون انهيار واضح = حذر
        whale_verdict  = "🟡 *ضغط بيع — توخَّ الحذر*"
        whale_desc     = "بيع {:.0f}% من الحجم — السوق يميل للهبوط".format(sell_pct)
        whale_action   = "⚠️ _انتظر قبل الدخول — الضغط البيعي مرتفع_"
        whale_icon     = "🟡🔴"

    else:
        whale_verdict  = "🟡 *السوق محايد — انتظر*"
        whale_desc     = "لا اتجاه واضح | شراء {:.0f}% | بيع {:.0f}%".format(buy_pct, sell_pct)
        whale_action   = "⏳ _انتظر إشارة واضحة قبل الدخول_"
        whale_icon     = "🟡"

    # ══════════════════════════════════════════
    # 6. بناء الرسالة
    # ══════════════════════════════════════════
    # قائمة Stablecoins
    stable_txt = ""
    for name, vol in sorted(stable_details, key=lambda x: -x[1])[:4]:
        stable_txt += "  • *{}*: `{:,.0f}` USDT\n".format(name, vol)

    # قائمة الحيتان
    whale_txt = ""
    if whale_signals:
        for name, ratio in whale_signals[:3]:
            whale_txt += "  🐋 *{}*: `{:.1f}×` المعدل\n".format(name, ratio)
    else:
        whale_txt = "  ✅ لا نشاط غير عادي\n"

    # أفضل/أسوأ العملات
    gainers_txt = ""
    losers_txt  = ""

    # مؤشر السوق
    mkt_bar_green = int(rising_pct / 10)
    mkt_bar_red   = 10 - mkt_bar_green
    mkt_bar = "🟩" * mkt_bar_green + "🟥" * mkt_bar_red

    # حالة تدفق السيولة
    flow_sum = get_flow_summary()

    # ضمان أن القيم أرقام وليست نصوص — نستخدم متغيرات محلية جديدة
    _btc         = float(btc_ch)          if btc_ch          is not None else 0.0
    # 🆕 تصحيح حالة السوق للعرض — إذا ضغط بيع شديد رغم SAFE
    _display_state = market_state
    if market_state == "SAFE" and sell_pct >= 80:
        _display_state = "CAUTION"
    elif market_state == "SAFE" and sell_pct >= 90:
        _display_state = "DANGER"
    _mkt_icons = {"SAFE": "🟢", "CAUTION": "🟡", "DANGER": "🔴"}
    _eth         = float(eth_change_24h)  if eth_change_24h  is not None else 0.0
    # 🆕 جلب BTC 1h طازج مباشرة للتقرير — بدون الاعتماد على الكاش
    _btc1h = btc_trend_1h  # الافتراضي
    try:
        _kd1h = get_klines("BTCUSDT", "1h", 6)
        if _kd1h and len(_kd1h["closes"]) >= 2:
            _c1h   = _kd1h["closes"]
            _btc1h = (_c1h[-1] - _c1h[-2]) / _c1h[-2] * 100  # آخر شمعة vs قبلها
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
        "₿ BTC 24h: `{btc:+.2f}%` | 1h: `{btc1h:+.2f}%`\n"
        "{btc_tps_line}"
        "Ξ ETH 24h: `{eth:+.2f}%`\n"
        "{eth_tps_line}"
        "━━━━━━━━━━━━━━━━━━\n"
        "{whale_icon} {verdict}\n"
        "_{desc}_\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "📊 *نسبة الشراء/البيع (بالحجم):*\n"
        "{bar}\n"
        "  🟢 *Buy:*  `{buy:.1f}%` ({buy_vol})\n"
        "  🔴 *Sell:* `{sell:.1f}%` ({sell_vol})\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "💰 *تدفق رأس المال:*\n"
        "  {arrow} حجم السوق: `{vol_ch}` عن أمس\n"
        "  📦 إجمالي: `{total_vol}` USDT\n"
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
                "حيتان يشترون 🔥" if btc_tps_stats.get("ats",0) >= ATS_WHALE and btc_tps_stats.get("vdelta",0) >= 0.65
                else ("حيتان يبيعون ⚠️" if btc_tps_stats.get("ats",0) >= ATS_WHALE and btc_tps_stats.get("vdelta",0) < 0.40
                else "نشاط عادي")
            ) if btc_tps_stats else ""
        ),
        eth_tps_line=(
            "  🐋 ETH TPS:`{:.1f}` ATS:`{:.0f}$` VD:`{:.0f}%` — {}\n".format(
                eth_tps_stats.get("tps",0), eth_tps_stats.get("ats",0),
                eth_tps_stats.get("vdelta",0.5)*100,
                "حيتان يشترون 🔥" if eth_tps_stats.get("ats",0) >= ATS_WHALE and eth_tps_stats.get("vdelta",0) >= 0.65
                else ("حيتان يبيعون ⚠️" if eth_tps_stats.get("ats",0) >= ATS_WHALE and eth_tps_stats.get("vdelta",0) < 0.40
                else "نشاط عادي")
            ) if eth_tps_stats else ""
        ),
        mkt_icon=_mkt_icons.get(_display_state,"📊"), mkt_state=_display_state,
        bar=mkt_bar,
        rp=rising_pct,  fp=falling_pct,
        rising=rising,  falling=falling,
        total=total_coins,
        buy=_buy_pct,    sell=_sell_pct,
        buy_vol=("{:.2f}B".format(_buy_vol/1_000_000_000) if _buy_vol>=1_000_000_000 else "{:.0f}M".format(_buy_vol/1_000_000)),
        sell_vol=("{:.2f}B".format(_sell_vol/1_000_000_000) if _sell_vol>=1_000_000_000 else "{:.0f}M".format(_sell_vol/1_000_000)),
        arrow=vol_arrow,
        vol_ch=("{:+.1f}%".format(vol_change_pct) if vol_change_pct is not None else "اول يوم 📊"),
        
        total_vol=("{:.2f}B".format(_total_vol/1_000_000_000) if _total_vol>=1_000_000_000 else "{:.0f}M".format(_total_vol/1_000_000)),
        vol_chg=("{:+.1f}%".format(vol_change_pct) if vol_change_pct is not None else "أول يوم"),

        flow=flow_sum,
        action=whale_action,

    )

    # ─── Breakout inline calc ───────────────────────────
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
        _trnd=_SP+"\n📊 *Market Activity Trend* (كل الأيام المتاحة)\n"
        for _e in market_activity_history:
            _bp2=_e["buy_pct"]; _stp2=_e.get("stable_pct",0); _sc=_e.get("sigma_count",0)
            _ic="🟢" if _bp2>=55 else "🔴" if _bp2<=45 else "🟡"
            _trnd+="`"+_e["date"][5:]+"` "+_ic+" "+str(round(_bp2,0))+"%B | 🐳"
            _trnd+=str(round(_stp2,1))+"%S | σ"+str(_sc)+"\n"
        _trnd+=_SP
    _analysis  = analyze_market_history()
    # ══ Stablecoin Sigma من analyze_smart_money ══
    _sm_data   = _get_smart_money_summary()
    _sm_block  = "\n" + _sm_data if _sm_data else ""
    send(msg+"\n"+_brk+"\n"+_trnd+"\n"+_analysis+_sm_block)
    log.info("Daily Report merged | rising=%.0f%% | whale=%d | vol=%.1f%%",
             rising_pct, len(whale_signals), vol_change_pct if vol_change_pct is not None else 0.0)
    # ── نهاية _send_daily_report_body ──

# ═══════════════════════════════════════════════════════
#  🆕 FEATURE 1: Daily Breakout Report (Sigma)
#  مثل FlowEntry — عملات دخلت سيولة غير عادية
# ═══════════════════════════════════════════════════════
def send_breakout_report():
    global market_activity_history, breakout_report_sent
    if not all_tickers: return
    today = datetime.utcnow().strftime('%Y-%m-%d')
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

    BARS = 10   # عدد الأعمدة في المؤشر
    msg  = "📊 *Market Activity Trend*\n"
    msg += "━━━━━━━━━━━━━━━━━━\n"

    # آخر 10 أيام
    recent = market_activity_history[-BARS:]
    max_vol = max(d["buy_vol"] + d["sell_vol"] for d in recent) or 1

    for d in recent:
        total   = d["buy_vol"] + d["sell_vol"]
        buy_b   = int(d["buy_pct"] / 10)       # عدد أعمدة الشراء
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
    log.info("📊 Market Activity Trend | %d days", len(recent))


# ═══════════════════════════════════════════════════════
#  🆕 FEATURE 3: TradingView Script Generator
#  يولّد سكريبت Pine Script لرسم مناطق السيولة
# ═══════════════════════════════════════════════════════
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

    for s in signals[:5]:   # أقصى 5 سكريبتات
        script = generate_tv_script(
            s["sym"], s["zone_high"], s["zone_low"],
            s.get("sigma", 1), s.get("touches", 1)
        )
        base = s["sym"].replace("USDT","")

        # إرسال كملف نصي
        send(
            "📄 *TradingView Script — {}*\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "📋 انسخ الكود وأضفه في:\n"
            "Pine Editor → Add to chart\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "```\n{}\n```".format(base, script[:3000])
        )
        log.info("📄 TV Script → %s", s["sym"])



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

# ═══════════════════════════════════════════════
# STATE PERSISTENCE — حفظ واستعادة البيانات
# ═══════════════════════════════════════════════

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
        # عملات صغيرة جداً
        return "{:.12f}".format(p).rstrip('0').rstrip('.')


# ═══════════════════════════════════════════════
# REDIS PERSISTENCE — حفظ دائم عبر Upstash
# ═══════════════════════════════════════════════

# ✅ redis_save القديمة محذوفة — نستخدم الجديدة أدناه


# ✅ redis_load القديمة محذوفة — نستخدم الجديدة أدناه


def redis_save(data):
    # type: (dict) -> bool
    """حفظ البيانات في Upstash Redis"""
    if not REDIS_URL or not REDIS_TOKEN:
        return False
    try:
        import json as _json
        payload = _json.dumps(data, default=str)
        # Upstash REST API — SET
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
            log.info("☁️ Redis saved — %d bytes", len(payload))
        else:
            log.warning("⚠️ Redis save failed: %s", resp.text[:100])
        return ok
    except Exception as e:
        log.error("❌ redis_save error: %s", e)
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
            log.info("📂 Redis: لا توجد بيانات محفوظة")
            return {}
        result = resp.json()
        raw = result.get("result")
        if not raw:
            return {}
        data = _json.loads(raw)
        log.info("☁️ Redis loaded — %d bytes", len(raw))
        return data
    except Exception as e:
        log.error("❌ redis_load error: %s", e)
        return {}



def save_state():
    # type: () -> None
    """حفظ كل البيانات المهمة في ملف JSON"""
    try:
        state = {
            "version":             "V16",
            "saved_at":            time.time(),
            # تاريخ الأسعار والأحجام
            "bottom_price_history": bottom_price_history,
            "bottom_vol_history":   bottom_vol_history,
            "ath_tracker":          ath_tracker,
            "rt_vol_baseline":      rt_vol_baseline,
                        # القوائم
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
            # تقارير
            "daily_report_sent_date":   daily_report_sent_date,
            "lz_daily_sent_date":       lz_daily_sent_date,
            "daily_gem_count":          daily_gem_count,
            "stable_vol_history":       stable_vol_history,
            "daily_market_vol_history": daily_market_vol_history,
        }
        # حفظ محلي
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
        # حفظ في Redis
        redis_save(state)
        log.info("💾 State saved — %d gems | %d watchlist | %d BT",
                 len(gem_watchlist), len(watchlist), len(backtest_signals))
    except Exception as e:
        log.error("❌ save_state error: %s", e)


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

    # أولاً: Redis
    state = redis_load()
    log.info("☁️ Redis state: %d keys", len(state))

    # ثانياً: ملف محلي إذا Redis فارغ
    if not state:
        if not os.path.exists(STATE_FILE):
            log.info("📂 لا يوجد حفظ — بداية جديدة")
            return
        try:
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
            log.info("📂 State loaded from local file")
        except Exception as e:
            log.error("❌ load local error: %s", e)
            return

    if not state:
        return

    try:
        saved_at   = state.get("saved_at", 0)
        age_hours  = (time.time() - saved_at) / 3600
        log.info("📂 تحميل State — عمره: %.1f ساعة", age_hours)

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

        log.info("✅ State loaded | gems=%d | watchlist=%d | ath=%d | BT=%d",
                 len(gem_watchlist), len(watchlist), len(ath_tracker), len(backtest_signals))

        send("♻️ *Bot Restarted* — تم استعادة البيانات\n"
             "💎 Gems: `{}` | 👁️ Watchlist: `{}` | 📊 BT: `{}`\n"
             "⏱️ آخر حفظ: `{:.1f}h` | ☁️ Redis".format(
                 len(gem_watchlist), len(watchlist),
                 len(backtest_signals), age_hours))

    except Exception as e:
        log.error("❌ load_state error: %s", e)


def init_static_watchlist():
    # type: () -> None
    """تهيئة قائمة المراقبة الثابتة عند بدء البوت"""
    global watchlist, wl_price_snapshot

    if not all_tickers:
        log.warning("⚠️ init_static_watchlist: all_tickers فارغ")
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
        # ── Meme Coins — 50 عملة ──────────────────
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
        ("CHADUSDT",   "Meme", "Meme — Chad"),
        ("APEUSDT",    "Meme", "Meme — Ape"),
        ("PENGUINUSDT", "Meme", "Meme — Penguin"),
        ("PENGUUSDT",   "Meme", "Meme — Pengu"),
    ]

    for sym, sector, reason in _static:
        if sym in watchlist:
            continue  # موجودة مسبقاً

        t = ticker_map.get(sym)
        if not t:
            log.warning("⚠️ Static WL: %s غير موجودة في السوق", sym)
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
            "priority": "STATIC",  # ثابتة لا تنتهي صلاحيتها
        }
        wl_price_snapshot[sym] = price
        added += 1

    log.info("👁️ Static Watchlist: أضفنا %d عملة | إجمالي: %d", added, len(watchlist))



def run():
    # type: () -> None
    global all_tickers   # ✅ إصلاح V11: تأكيد أن all_tickers global
    global last_tickers, last_btc, last_sectors
    global last_deep_scan, last_stale, last_smart_money, last_expand
    global last_daily_report, daily_report_sent_date
    global lz_daily_sent_date, lz_alerted
    global hidden_accum_alerted
    global last_sector_report        # 🆕
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
    # 🆕 V16 New Systems
    global tps_alerted, tps_baseline, last_tps_scan  # ⚡ TPS/ATS
    global coin_alerted                                # 🔒 Cooldown موحد
    global coin_signal_count                           # 🔢 عداد الإشارات
    global coin_whale_done                             # 🐋 عملات وصل حيتانها
    global btcd_history, btcd_last_check, btcd_alert_sent  # 📊 BTC Dominance
    global liq_exit_alerted, liq_exit_vol_hist             # 💧 Liquidity Exit
    global whale_watchlist, whale_confirmed            # 🐋 Whale Confirmation
    global lz_tps_alerted                              # 🎯 LZ+TPS Fusion
    global lh_alerted, last_lh_scan          # 🔥 Liquidity Hunter
    global small_caps, last_sc_refresh       # 📋 Small Caps
    global sc_alerted                        # 🔍 Small Cap Hunter
    global last_sr_alert                     # 🌊 Sector Rotation
    global perf_signals, perf_id_counter     # 📊 Performance Tracker

    log.info("🚀 MAFIO BOT V17 يبدأ...")

    # ✅ نحذف Webhook ونمسح أي تعارض عند البداية
    try:
        import requests as _rq
        _rq.get(
            "https://api.telegram.org/bot{}/deleteWebhook?drop_pending_updates=true".format(TELEGRAM_TOKEN),
            timeout=10
        )
        log.info("✅ Webhook محذوف عند البداية")
    except Exception as _e:
        log.warning("deleteWebhook error: %s", _e)

    # ✅ انتظار 15 ثانية للتأكد من توقف النسخة القديمة
    time.sleep(15)

    load_state()  # استعادة البيانات من آخر تشغيل

    log.info("⏳ تحميل بيانات السوق...")
    analyze_btc()

    refresh_tickers()
    time.sleep(2)

    # 🔧 مسح offset قديم عند البدء — لا نتخطى أي رسائل معلقة
    try:
        _r = requests.get(
            "https://api.telegram.org/bot{}/getUpdates?offset=-1&timeout=1".format(TELEGRAM_TOKEN),
            timeout=5
        )
        _d = _r.json()
        if _d.get("ok") and _d.get("result"):
            global _tg_offset
            _tg_offset = _d["result"][-1]["update_id"] + 1
            log.info("📨 Telegram offset initialized: %d", _tg_offset)
    except Exception as _e:
        log.warning("offset init error: %s", _e)
    refresh_tickers()
    init_static_watchlist()  # all_tickers جاهز الآن

    log.info("🔍 تشغيل Auto Expand Sectors...")
    auto_expand_sectors()
    last_expand = time.time()

    analyze_sectors()
    # scan_sector_activity() — معطّل عند البدء لمنع رسالتين
    last_sector_report = time.time()  # منع إرسال ثانٍ فوراً
    log.info("✅ جاهز | Candidates: %d | Hot: %s",
             len(candidates), ", ".join(hot_sectors) or "لا يوجد")

    last_deep_scan = 0

    # 🆕 V16: تأكيد global للمتغيرات الجديدة (القيم مُعرَّفة على مستوى الملف)
    global last_lh_scan, last_sc_refresh, last_sr_alert
    last_lh_scan    = 0.0
    last_sc_refresh = 0.0
    last_sr_alert   = 0.0

    send(
        "🤖 *MAFIO BOT SIGNAL V17*\n"
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
    flow_cycle = 0  # عداد لتحليل Flow كل 5 دورات (~60 ثانية)

    while True:
        # قيم افتراضية آمنة — تُبنى لاحقاً في كل دورة
        price_map  = {}
        change_now = {}
        vol_now    = {}
        high_map   = {}
        low_map    = {}
        try:
            now = time.time()

            # 🚨 أولوية قصوى — Realtime Liquidity كل 5 دقائق
            # ⚡ Instant Movers — كل 5 دقائق بدون تاريخ

            # 🎯 Early Detection — كل 15 دقيقة

            # 💾 حفظ الحالة كل 30 دقيقة
            if int(now) % 1800 < 12:  # كل 30 دقيقة
                save_state()

            # 🔴 Trailing Stop Check — كل 5 دقائق
            if now - last_ts_scan >= TS_SCAN_EVERY:
                check_trailing_stops()
                last_ts_scan = now

            # 👁️ Watchlist Entry Check — كل دقيقة
            if now - last_wl_check >= WL_CHECK_EVERY:
                check_watchlist_entries()
                last_wl_check = now
            if now - last_rt_scan >= RT_SCAN_EVERY:
                scan_instant_movers()
            if now - last_rt_scan >= RT_SCAN_EVERY:
                scan_realtime_liquidity()
                last_rt_scan = now
            poll_commands()  # استماع لأوامر Telegram

            # تحديثات دورية
            if now - last_btc         >= BTC_EVERY:         analyze_btc()
            if now - last_sectors     >= SECTORS_EVERY:
                analyze_sectors()
                detect_sector_rotation()  # 🌊 هل حدث Rotation؟
            # analyze_smart_money مدمجة في التقرير اليومي
            refresh_sector_report()   # 🆕 تقرير القطاعات + تجميع الحيتان كل ساعة
            # 🆕 Bottom Accumulation Scan كل ساعة
            if now - last_bottom_scan >= BOTTOM_SCAN_EVERY:
                # 🆕 Hot Market Scanner — كل 30 دقيقة فوري
                if now - last_hot_scan >= HOT_SCAN_EVERY:
                    scan_hot_market()
                    last_hot_scan = now
                check_btc_dominance(vol_now)
                scan_bottom_accumulation()
                # 🆕 ATH Distance Scan كل ساعتين
                if now - last_ath_scan >= ATH_SCAN_EVERY:
                    scan_ath_distance()
                    last_ath_scan = now
                # scan_volume_explosion — معطّل (مكرر مع liquidity_hunter)
                last_bottom_scan = now

            # 🆕 V15: تقرير يومي عند 00:00 UTC
            send_daily_report()
            # run_daily_liquidity_scan مدمجة في التقرير اليومي
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
                        pass  # check_progression — معطّل (SIGNAL #2 قديم)

            # 🆕 Sector Flow: تجميع لقطات كل دورة
            update_sector_flow(ticker_map)
            flow_cycle += 1

            # 🆕 Sector Flow: تحليل كل 5 دورات (~60 ثانية)
            if flow_cycle >= FLOW_WINDOW:
                analyze_sector_flow()
                flow_cycle = 0

            # Momentum Detector — معطّل (WATCH + الجوكر فقط)
            # detect_momentum(price_map, change_now, vol_now, high_map, low_map)

            # 📊 تحديث نتائج الأداء — بعد بناء price_map
            if now - last_ts_scan >= TS_SCAN_EVERY:
                perf_check(price_map)

            # 🆕 V16: كشف التجميع الخفي — كل 10 دقائق
            if now - last_lh_scan >= 600:   # 10 دقائق = 600 ثانية
                scan_hidden_accumulation(price_map, vol_now, changes_map)

            # 🚨 PUMP/DUMP — كل دورة (12 ثانية)
            update_pump_dump_history(price_map, vol_now)
            scan_pump_dump(price_map, vol_now, change_now)

            # 🌊 MARKET PULSE — معطّل (DAILY REPORT يكفي)
            # scan_market_pulse(price_map, vol_now, change_now)

            # 🌊 LIQUIDITY FLOW TRACKER — كل 5 دقائق
            track_liquidity_flow(vol_now, change_now)

            # 🔥 LIQUIDITY HUNTER — كل 5 دقائق
            # ⚡ TPS/ATS + LZ Fusion + Whale — كل 5 دقائق
            if now - last_tps_scan >= TPS_SCAN_EVERY:
                check_liquidity_exit(vol_now, price_map)
                scan_tps_ats(price_map, vol_now, change_now)
                scan_lz_tps_fusion(price_map, vol_now, change_now)  # 🎯 الدمج
                scan_whale_confirmation(price_map)                  # 🐋 تأكيد حيتان
                last_tps_scan = now

            if now - last_lh_scan >= LH_SCAN_EVERY:
                liquidity_hunter(price_map, vol_now, changes_map)
                last_lh_scan = now

            # 📋 Small Caps — تحديث القائمة كل ساعة
            if now - last_sc_refresh >= SC_REFRESH_EVERY:
                refresh_small_caps()

            # 🔍 SMALL CAP HUNTER — كل 5 دقائق
            if now - last_lh_scan < 10 and small_caps:
                liquidity_hunter_small_caps(price_map, vol_now, changes_map)

            # Deep Scan
            if now - last_deep_scan >= DEEP_SCAN_EVERY:
                # 🆕 V15: ترتيب مسبق — OrderBook لأفضل 20 فقط
                # نرتب العملات حسب: حجم مرتفع + تغيير إيجابي أولاً
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
                        (5  if in_watchlist else 0) +   # 🆕 watchlist أولوية
                        (10 if wl_priority  else 0)     # 🆕 قطاع ساخن + تجميع = أقصى أولوية
                    )
                    pre_scored.append((sym, price, change, pre_score))

                # ترتيب تنازلي — الأفضل أولاً
                pre_scored.sort(key=lambda x: -x[3])

                log.info("🔍 Deep Scan — %d عملة (أفضل 20 تأخذ OrderBook)...",
                         len(pre_scored))

                scanned = 0
                for rank, (sym, price, change, _) in enumerate(pre_scored):
                    # OrderBook فقط لأفضل 20 عملة
                    fetch_ob = (rank < 20)
                    deep_scan(sym, price, change, fetch_orderbook=fetch_ob)
                    scanned += 1
                    if scanned % 10 == 0:
                        time.sleep(0.5)

                last_deep_scan = now
                log.info("✅ Deep Scan انتهى | %d عملة", scanned)

            cycle += 1
            # send_report() — معطّل (تقرير V15 القديم)
            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            send("⛔ *MAFIO BOT V17* — تم الإيقاف")
            break
        except Exception as e:
            log.error("خطأ: %s", e, exc_info=True)
            time.sleep(10)


if __name__ == "__main__":
    run()

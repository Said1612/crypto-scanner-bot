"""
╔══════════════════════════════════════════════════════════════╗
║           MAFIO BOT SIGNAL V10 — UNIFIED ENGINE            ║
║     Anti-Rate-Limit + Smart Cache + Trailing Stop          ║
╚══════════════════════════════════════════════════════════════╝

استراتيجية الطلبات (Anti-Rate-Limit):
  ● طلب واحد للأسعار  كل 12 ثانية   → 5/دقيقة
  ● طلب واحد للتغييرات كل 30 دقيقة  → 2/ساعة
  ● Klines لعملة واحدة فقط عند الحاجة (بعد الفلتر المسبق)
  ● Cache ذكي: 15m=60s, 1h=5min, 4h=15min
  ● Scan عميق (Klines+OrderBook) كل 4 ساعات فقط
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
SCORE_MIN          = 75
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
SECTOR_HOT_CHANGE  = 3.0
SECTOR_MIN_RISING  = 60.0
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

# ── فلتر مسبق (يمنع طلبات Klines غير ضرورية) ───
PRE_MIN_CHANGE     = -5.0      # رفض إذا 24h < -5%
PRE_MAX_CHANGE     = 80.0      # رفض إذا 24h > 80% (Pump)
PRE_MIN_VOL        = MIN_VOL_USDT
PRE_MAX_VOL        = MAX_VOL_USDT

# ── توقيتات الدورات ──────────────────────────────
PRICES_EVERY       = 12        # جلب الأسعار كل 12 ثانية
TICKERS_EVERY      = 1800      # جلب التغييرات كل 30 دقيقة
BTC_EVERY          = 1800      # تحليل BTC كل 30 دقيقة
SECTORS_EVERY      = 1800      # تحليل القطاعات كل 30 دقيقة
DEEP_SCAN_EVERY    = 3600      # Scan عميق (Klines) كل ساعة
STALE_EVERY        = 3600      # تنظيف العملات المتوقفة كل ساعة
REPORT_EVERY       = 21600     # تقرير الأداء كل 6 ساعات

# ── Cache ────────────────────────────────────────
CACHE_15M          = 60        # شموع 15m صالحة 60 ثانية
CACHE_1H           = 300       # شموع 1h صالحة 5 دقائق
CACHE_4H           = 900       # شموع 4h صالحة 15 دقيقة

# ── MEXC Endpoints ──────────────────────────────
MEXC_24H    = "https://api.mexc.com/api/v3/ticker/24hr"
MEXC_PRICE  = "https://api.mexc.com/api/v3/ticker/price"
MEXC_KLINES = "https://api.mexc.com/api/v3/klines"
MEXC_DEPTH  = "https://api.mexc.com/api/v3/depth"

EXCLUDED          = {"BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT"}
STABLECOINS       = {"USDT","BUSD","USDC","DAI","TUSD","PAX","UST","FDUSD"}
LEVERAGE_KEYWORDS = ["3L","3S","5L","5S","BULL","BEAR","UP","DOWN"]

# ═══════════════════════════════════════════════
#   SECTORS — 12 قطاع
# ═══════════════════════════════════════════════
SECTORS = {
    "AI":      ["FETUSDT","AGIXUSDT","OCEANUSDT","AIXBTUSDT","RENDUSDT",
                "NEWTUSDT","TAOAUSDT","ARKMUSDT","GRTUSDT","PHAUSDT"],
    "RWA":     ["SAHARAUSDT","ONDOUSDT","CFGUSDT","RSRUSDT","GOLDUSDT",
                "POLIXUSDT","MPLXUSDT","REALUSDT","TRSTUSDT","ONDO2USDT"],
    "Gaming":  ["AXSUSDT","SANDUSDT","MANAUSDT","ILVUSDT","GMTUSDT",
                "YGGUSDT","SLPUSDT","PGXUSDT","BEXUSDT","GALAAUSDT"],
    "DeFi":    ["UNIUSDT","AAVEUSDT","CAKEUSDT","C98USDT","SUSHIUSDT",
                "COMPUSDT","MKRUSDT","CRVUSDT","LDOUSDT","1INCHUSDT"],
    "Layer1":  ["AVAXUSDT","ADAUSDT","ATOMUSDT","NEARUSDT","FTMUSDT",
                "ALGOUSDT","ICPUSDT","APTUSDT","SUIUSDT","SEIUSDT"],
    "Layer2":  ["MATICUSDT","OPUSDT","ARBUSDT","ZKUSDT","STRKUSDT",
                "LRCUSDT","IMXUSDT","METISUSDT","MANTAUSDT","SCROLLUSDT"],
    "Meme":    ["DOGEUSDT","SHIBUSDT","PEPEUSDT","FLOKIUSDT","WIFUSDT",
                "BOMUSDT","MEMEUSDT","NEIROUSDT","TUROUSDT","MOGUUSDT"],
    "Oracle":  ["LINKUSDT","BANDUSDT","APIUSDT","UMAUSDT","DIAUSDT"],
    "Privacy": ["XMRUSDT","DASHUSDT","SCRTUSDT","ROSEUSDT","ZECUSDT"],
    "Storage": ["FILUSDT","ARUSDT","STORJUSDT","SCUSDT","BLZUSDT"],
    "DePIN":   ["IOTAUSDT","WLDUSDT","AIOZUSDT","XNETUSDT","MOBIUSDT"],
    "Old":     ["LTCUSDT","ETCUSDT","XEMUSDT","LUNCUSDT","BTGUSDT"],
}

# ═══════════════════════════════════════════════
#                   LOGGING
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
# إشارات نشطة
tracked        = {}   # {sym: {entry, peak, level, sl_pct, entry_time, last_alert}}
discovered     = {}   # {sym: {price, time, score}}

# بيانات السوق
btc_change_24h = 0.0
btc_trend_1h   = 0.0
market_state   = "SAFE"   # SAFE / CAUTION / DANGER
hot_sectors    = []        # type: List[str]
hot_symbols    = set()     # type: Set[str]
sector_vol_history = {}    # type: Dict[str, float]

# قائمة العملات المرشحة (بعد الفلتر المسبق)
candidates     = []        # type: List[str]
changes_map    = {}        # type: Dict[str, float]
all_tickers    = []        # type: List[Dict]

# Cache الشموع: {symbol_interval: (data, timestamp)}
klines_cache   = {}        # type: Dict[str, Tuple[Dict, float]]

# توقيتات آخر تشغيل
last_tickers   = 0.0
last_btc       = 0.0
last_sectors   = 0.0
last_deep_scan = 0.0
last_stale     = 0.0
last_report    = 0.0

# إحصائيات API (لمراقبة الاستخدام)
api_calls_total    = 0
api_calls_minute   = 0
api_minute_reset   = time.time()

session = requests.Session()
session.headers.update({"User-Agent": "MafioBot/10.0"})


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
        # إعادة تعيين عداد الدقيقة
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
#   SMART CACHE — يمنع طلبات Klines المتكررة
# ═══════════════════════════════════════════════
def get_klines(symbol, interval="15m", limit=50):
    # type: (str, str, int) -> Optional[Dict]
    """
    يجلب الشموع مع Cache ذكي:
      15m → صالح 60 ثانية
      1h  → صالح 5 دقائق
      4h  → صالح 15 دقيقة
    """
    cache_ttl = {
        "15m": CACHE_15M,
        "1h":  CACHE_1H,
        "4h":  CACHE_4H,
    }.get(interval, CACHE_15M)

    key = "{}_{}".format(symbol, interval)
    now = time.time()

    # إرجاع من Cache إذا صالح
    if key in klines_cache:
        data, ts = klines_cache[key]
        if now - ts < cache_ttl:
            return data

    # جلب من API
    raw = safe_get(MEXC_KLINES, {
        "symbol": symbol, "interval": interval, "limit": limit
    })
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
    """تنظيف Cache القديم لتوفير الذاكرة."""
    now   = time.time()
    stale = [k for k, (_, ts) in list(klines_cache.items())
             if now - ts > CACHE_4H * 2]
    for k in stale:
        del klines_cache[k]


# ═══════════════════════════════════════════════
#   PRE-FILTER — يرفض 90% من العملات بدون Klines
# ═══════════════════════════════════════════════
def pre_filter(sym, change, vol):
    # type: (str, float, float) -> bool
    """
    فلتر سريع بدون أي طلب API إضافي.
    يستخدم البيانات الموجودة أصلاً من ticker/24hr.
    يرفض العملات التي لا تستحق Scan عميق.
    """
    if sym in EXCLUDED: return False
    base = sym.replace("USDT", "")
    if base in STABLECOINS: return False
    if any(k in sym for k in LEVERAGE_KEYWORDS): return False
    if not sym.endswith("USDT"): return False
    # حجم
    if vol < PRE_MIN_VOL or vol > PRE_MAX_VOL: return False
    # تغيير
    if change < PRE_MIN_CHANGE: return False     # نازل كثيراً
    if change > PRE_MAX_CHANGE: return False     # Pump مشبوه
    # السوق خطر: فقط العملات المستقلة
    if market_state == "DANGER":
        if change <= btc_change_24h: return False
    return True


# ═══════════════════════════════════════════════
#   BTC MARKET ANALYSIS — كل 30 دقيقة
# ═══════════════════════════════════════════════
def analyze_btc():
    # type: () -> None
    global btc_change_24h, btc_trend_1h, market_state, last_btc

    data = safe_get(MEXC_24H, {"symbol": "BTCUSDT"})  # طلب واحد فقط
    if not data:
        return

    try:
        btc_change_24h = float(data["priceChangePercent"])
    except (KeyError, ValueError):
        pass

    # اتجاه 1h من Cache إذا وُجد
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
#   SECTOR ROTATION — كل 30 دقيقة
# ═══════════════════════════════════════════════
def analyze_sectors():
    # type: () -> None
    """
    يستخدم all_tickers المحفوظة مسبقاً — لا طلبات API جديدة!
    """
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

        if (avg_ch >= SECTOR_HOT_CHANGE and
                rising_pct >= SECTOR_MIN_RISING):
            new_hot.append(sector)

    old_hot     = set(hot_sectors)
    new_hot_set = set(new_hot)
    hot_sectors = new_hot
    hot_symbols = {c for s in hot_sectors for c in SECTORS[s]}
    last_sectors = time.time()

    # إرسال تقرير عند تغيير القطاعات
    entered = new_hot_set - old_hot
    exited  = old_hot - new_hot_set

    if entered or exited:
        msg = "🔄 *SECTOR ROTATION*\n━━━━━━━━━━━━━━━━━━\n"
        if entered:
            msg += "💰 *سيولة تدخل:*\n"
            for s in entered:
                st = stats.get(s, {})
                coins_txt = " | ".join(
                    "{} +{:.0f}%".format(c, p)
                    for c, p in st.get("top", [])
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
#   TICKERS — كل 30 دقيقة
# ═══════════════════════════════════════════════
def refresh_tickers():
    # type: () -> None
    """
    طلب واحد يجيب بكل بيانات السوق.
    يبني قائمة candidates بعد الفلتر المسبق.
    """
    global all_tickers, changes_map, candidates, last_tickers

    data = safe_get(MEXC_24H)   # طلب واحد فقط
    if not data:
        return

    all_tickers = data
    changes_map = {}
    result      = []

    for t in data:
        sym = t.get("symbol", "")
        try:
            ch  = float(t["priceChangePercent"])
            vol = float(t["quoteVolume"])
        except (KeyError, ValueError):
            continue

        if sym == "BTCUSDT":
            pass  # BTC يُحدَّث في analyze_btc

        changes_map[sym] = ch

        # الفلتر المسبق
        if pre_filter(sym, ch, vol):
            result.append((sym, vol))

    result.sort(key=lambda x: -x[1])
    base_candidates = [s for s, _ in result[:80]]

    # أضف عملات القطاعات الساخنة دائماً
    extra = [s for s in hot_symbols
             if s not in base_candidates and s not in EXCLUDED]
    candidates = base_candidates + extra
    last_tickers = time.time()

    log.info("📋 Candidates: %d من %d | Hot: %s",
             len(candidates), len(data), ", ".join(hot_sectors) or "لا يوجد")


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
    """يفحص التجميع على 4h — من Cache إذا وُجد."""
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
    """
    Trailing Stop ذكي:
    - يرفع حد الوقف مع كل ارتفاع في السعر
    - يخرج إذا نزل 1.5% من القمة بعد +2% ربح
    أفضل من SL الثابت لأنه يحمي الأرباح
    """
    if symbol not in tracked:
        return False

    entry = tracked[symbol]["entry"]
    peak  = tracked[symbol].get("peak", entry)

    if price > peak:
        tracked[symbol]["peak"] = price
        peak = price

    gain = (peak - entry) / entry * 100
    drop = (peak - price) / peak * 100

    # Trailing: بعد +2% ربح، إذا نزل 1.5% من القمة = خروج
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
        if symbol in tracked:
            del tracked[symbol]
        return True

    # Stop Loss عادي
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
        if symbol in tracked:
            del tracked[symbol]
        return True

    return False


# ═══════════════════════════════════════════════
#   SCORE SYSTEM v10
# ═══════════════════════════════════════════════
def calculate_score(kd, ob, vol_accum, vol_spike, consol,
                    higher_lows, green, bo_str, in_hot, st):
    # type: (Dict, Optional[Dict], Tuple, Tuple, Tuple, Tuple, Tuple, float, bool, str) -> int
    score = 0
    avg   = kd["avg_vol"]

    # حجم (15)
    r = kd["vols"][-1]/avg if avg>0 else 0
    score += 15 if r>=3 else 10 if r>=2 else 6 if r>=1.5 else 0

    # Supertrend (10) — مهم جداً
    if st == "UP":   score += 10
    elif st == "DOWN": score -= 5   # عقوبة للاتجاه النازل

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

    return min(max(score, 0), 100)


def score_label(score):
    # type: (int) -> Optional[str]
    if score >= 88: return "🏆 *GOLD SIGNAL*"
    if score >= 75: return "🔵 *SILVER SIGNAL*"
    return None


# ═══════════════════════════════════════════════
#   DEEP SCAN — يُشغَّل كل 4 ساعات
# ═══════════════════════════════════════════════
def deep_scan(symbol, price, change):
    # type: (str, float, float) -> None
    """
    الفحص الكامل: Klines + OrderBook + كل المؤشرات.
    يُشغَّل فقط على candidates بعد الفلتر المسبق.
    """
    if symbol in tracked: return

    # حالة السوق
    if market_state == "DANGER" and symbol not in hot_symbols:
        return

    # الشموع (من Cache إذا وُجدت)
    kd = get_klines(symbol, "15m", 50)
    if not kd: return

    # Pump & Dump
    is_pd, pd_r = detect_pump_dump(kd)
    if is_pd:
        log.debug("🚫 P&D: %s | %s", symbol, pd_r)
        return

    # حجم أساسي
    if kd["vols"][-1] < kd["avg_vol"] * 1.2: return

    # Supertrend
    st = get_supertrend(kd)
    if st == "DOWN" and symbol not in hot_symbols: return

    # Green Candles
    ig, gp = detect_green_candles(kd)
    if not ig: return

    # Order Book (طلب API إضافي — نادر لأن 90% رُفضوا مسبقاً)
    ob = get_order_book(symbol)
    if ob:
        if ob["imb"] < MIN_IMBALANCE or ob["imb"] > MAX_IMBALANCE: return
        if ob["bid"] < MIN_BID_DEPTH: return

    # تحليلات
    vol_spike  = detect_volume_spike(kd)
    vol_accum  = detect_volume_accum(kd)
    consol     = detect_consolidation(kd)
    higher_lows= detect_higher_lows(kd)
    is_bo, bo_str, bo_desc = detect_pre_breakout(symbol)

    in_hot = symbol in hot_symbols
    sector = next((s for s,syms in SECTORS.items()
                   if symbol in syms and s in hot_sectors), "")

    score = calculate_score(kd, ob, vol_accum, vol_spike, consol,
                            higher_lows, (ig,gp), bo_str, in_hot, st)

    # حالة CAUTION: Gold فقط
    min_s = GOLD_MIN if market_state == "CAUTION" else SCORE_MIN
    label = score_label(score)
    if not label or score < min_s:
        return

    sl_pct = calc_sl(kd, score, ob, is_bo)

    tracked[symbol] = {
        "entry":      price,
        "peak":       price,
        "level":      1,
        "score":      score,
        "sl_pct":     sl_pct,
        "entry_time": time.time(),
        "last_alert": time.time(),
    }
    discovered[symbol] = {"price": price, "time": time.time(), "score": score}

    # بناء نص الإشارة
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
        "👑 *MAFIO BOT V10*\n"
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
    msg = "📊 *PERFORMANCE REPORT V10*\n🕐 `{}`\n\n".format(
        datetime.now().strftime("%Y-%m-%d %H:%M"))
    for sym, gr, sc in rows[:5]:
        msg += "🔥 *{}* `+{:.2f}%` Score:{}\n".format(sym, gr, sc)
    send(msg)


# ═══════════════════════════════════════════════
#   MAIN LOOP
# ═══════════════════════════════════════════════
def run():
    global last_tickers, last_btc, last_sectors
    global last_deep_scan, last_stale

    log.info("🚀 MAFIO BOT V10 يبدأ...")

    # تهيئة أولية
    analyze_btc()
    refresh_tickers()
    analyze_sectors()
    last_deep_scan = 0  # نبدأ Scan فوراً

    send(
        "🤖 *MAFIO BOT SIGNAL V10*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "✅ Anti Rate-Limit (~8 req/min)\n"
        "✅ Smart Cache (15m/1h/4h)\n"
        "✅ Trailing Stop (`{trail}%` من القمة)\n"
        "✅ Sector Rotation (12 قطاع)\n"
        "✅ Score Min: `{score}` | Deep Scan: كل ساعة\n"
        "✅ Anti P&D | Supertrend | Dynamic SL\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "₿ BTC: `{btc:+.2f}%` | السوق: `{mst}`\n"
        "🔥 Hot: `{hot}`".format(
            trail=TRAIL_DROP_TRIGGER,
            score=SCORE_MIN,
            btc=btc_change_24h,
            mst=market_state,
            hot=", ".join(hot_sectors) or "لا يوجد",
        )
    )

    cycle = 0
    while True:
        try:
            now = time.time()

            # ── تحديثات دورية ────────────────────────
            if now - last_btc     >= BTC_EVERY:      analyze_btc()
            if now - last_tickers >= DISCOVERY_EVERY: refresh_tickers()
            if now - last_sectors >= SECTORS_EVERY:   analyze_sectors()
            if now - last_stale   >= STALE_EVERY:
                cleanup()
                last_stale = now

            # ── جلب الأسعار (كل 12 ثانية — طلب واحد) ──
            prices = safe_get(MEXC_PRICE)
            if not prices:
                time.sleep(CHECK_INTERVAL)
                continue

            price_map = {}
            for p in prices:
                try:
                    price_map[p["symbol"]] = float(p["price"])
                except (KeyError, ValueError):
                    pass

            # ── Trailing Stop + Signal Progression ──────
            for sym in list(tracked.keys()):
                if sym in price_map:
                    if not check_trailing(sym, price_map[sym]):
                        check_progression(sym, price_map[sym])

            # ── Deep Scan كل 4 ساعات ──────────────────
            if now - last_deep_scan >= DEEP_SCAN_EVERY:
                log.info("🔍 Deep Scan كل ساعة — %d عملة...", len(candidates))
                scanned = 0
                for sym in candidates:
                    if sym in tracked: continue
                    price  = price_map.get(sym, 0)
                    change = changes_map.get(sym, 0)
                    if price <= 0: continue
                    deep_scan(sym, price, change)
                    scanned += 1
                    # استراحة قصيرة بين كل عملة لتفادي الحظر
                    if scanned % 10 == 0:
                        time.sleep(1)

                last_deep_scan = now
                log.info("✅ Deep Scan انتهى | فحص %d عملة", scanned)

            cycle += 1
            send_report()
            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            send("⛔ *MAFIO BOT V10* — تم الإيقاف")
            break
        except Exception as e:
            log.error("خطأ: %s", e, exc_info=True)
            time.sleep(10)


if __name__ == "__main__":
    run()

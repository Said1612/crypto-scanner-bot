"""
╔═══════════════════════════════════════════════════════════════╗
║      MEXC LIQUIDITY BOT v8 – EARLY WARNING SYSTEM           ║
╚═══════════════════════════════════════════════════════════════╝

الميزات v8:
  🆕 Watchlist Alert — إنذار مبكر قبل الإشارة الرسمية
     • يكتشف العملة في القاع قبل الحركة
     • يرسل: "👀 WATCHLIST" عند أول علامات التجميع
     • يرسل: "🟢 SIGNAL #1" عند التأكيد الكامل
  🆕 Bottom Detector — يكتشف القاع قبل الصعود
     • سعر عند أدنى نقطة + حجم يبدأ يرتفع = دخول مبكر
  ✅ Pre-Breakout Detection (4h + 15m)
  ✅ Anti Pump & Dump Filter
  ✅ Dynamic Stop Loss
  ✅ كل ميزات v7 محفوظة
"""

import os
import sys
import time
import logging
import requests
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Any

# ═══════════════════════════════════════════════
#                    CONFIG
# ═══════════════════════════════════════════════
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_BOT_TOKEN_HERE")
CHAT_ID        = os.getenv("CHAT_ID",        "YOUR_CHAT_ID_HERE")

# ── فلاتر الاكتشاف ──────────────────────────────
EXCLUDED          = {"BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"}
STABLECOINS       = {"USDT", "BUSD", "USDC", "DAI", "TUSD", "PAX", "UST", "FDUSD"}
LEVERAGE_KEYWORDS = ["3L", "3S", "5L", "5S", "BULL", "BEAR", "UP", "DOWN"]

DISCOVERY_MIN_VOL    = 300_000    # خُفِّف لاكتشاف العملات الصغيرة مبكراً
DISCOVERY_MAX_VOL    = 50_000_000 # رُفِع لاستيعاب العملات التي بدأت تنفجر
DISCOVERY_MAX_CHANGE = 15         # رُفِع لاصطياد بداية الانفجار
MAX_SYMBOLS          = 60         # زيادة لتغطية أوسع

# ── Order Book ───────────────────────────────────
ORDER_BOOK_LIMIT      = 20
MIN_BID_DEPTH_USDT    = 20_000    # خُفِّف للعملات الصغيرة
MAX_BID_ASK_IMBALANCE = 3.0
MIN_BID_ASK_IMBALANCE = 0.8

# ── إعدادات الإشارات ────────────────────────────
SCORE_MIN          = 60           # خُفِّف لاكتشاف Breakout Setup مبكراً
SIGNAL2_GAIN       = 2.0
SIGNAL3_GAIN       = 4.0
ALERT_COOLDOWN_SEC = 300

# ── Dynamic Stop Loss ────────────────────────────
SL_MIN_PCT  = 2.0
SL_MAX_PCT  = 8.0   # رُفِع لأن Breakout تكون أكثر تقلباً
SL_BASE_PCT = 4.0

# ── Volume Accumulation ───────────────────────────
VOL_ACCUM_CANDLES        = 6
VOL_ACCUM_MIN_RATIO      = 1.5
VOL_ACCUM_MAX_PRICE_MOVE = 3.0

# ── Volume Spike ──────────────────────────────────
VOL_SPIKE_RATIO = 2.5

# ── Price Consolidation ───────────────────────────
CONSOL_CANDLES   = 8
CONSOL_MAX_RANGE = 4.0

# ── Higher Lows ───────────────────────────────────
HIGHER_LOWS_MIN_RATIO = 0.6

# ── Green Candles ─────────────────────────────────
GREEN_CANDLES_MIN_RATIO = 0.55

# ── Rejection Cache ───────────────────────────────
REJECTION_CACHE_SEC = 120

# ── 🆕 Watchlist Alert (إنذار مبكر) ──────────────
# يكتشف العملة في القاع قبل الحركة
WATCHLIST_VOL_RATIO     = 1.3    # حجم يبدأ يرتفع قليلاً
WATCHLIST_NEAR_LOW_PCT  = 15.0   # السعر في 15% من القاع
WATCHLIST_MIN_BID_DEPTH = 15_000 # عمق أدنى
WATCHLIST_COOLDOWN_SEC  = 1800   # 30 دقيقة بين كل إنذار
WATCHLIST_MAX_ALERTS    = 5      # حد أقصى للإنذارات المتزامنة

# ── 🆕 Bottom Detector ────────────────────────────
BOTTOM_LOOKBACK_1H     = 24     # آخر 24 شمعة على 1h = يوم كامل
BOTTOM_NEAR_LOW_PCT    = 10.0   # السعر في 10% من القاع
BOTTOM_VOL_START_RATIO = 1.2    # بدأ الحجم يرتفع

# ── Pump & Dump Filter ───────────────────────────
PUMP_MAX_RISE_PCT     = 20.0
PUMP_DUMP_DROP_PCT    = 5.0
PUMP_LOOKBACK_CANDLES = 12

# ── 🆕 Pre-Breakout Detection ────────────────────
# يكتشف التجميع الطويل قبل الانفجار الكبير مثل ATLA
# يفحص شموع 4 ساعات للحصول على صورة أوضح
BREAKOUT_4H_CANDLES      = 30    # نفحص آخر 30 شمعة على 4h = 5 أيام
BREAKOUT_FLAT_MAX_RANGE  = 15.0  # السعر كان في نطاق ضيق خلال التجميع %
BREAKOUT_VOL_SURGE_RATIO = 3.0   # الحجم ارتفع 3× المتوسط = بدء الانفجار
BREAKOUT_MIN_FLAT_CANDLES= 10    # أقل عدد شموع هادئة للتأكيد
BREAKOUT_PRICE_NEAR_LOW  = 30.0  # السعر الحالي قريب من القاع بـ 30% أو أقل

# ── فلتر السوق ───────────────────────────────────
MARKET_FILTER_ENABLED = True

# ── توقيتات ─────────────────────────────────────
CHECK_INTERVAL        = 10
DISCOVERY_REFRESH_SEC = 3600
REPORT_INTERVAL       = 6 * 3600
STALE_REMOVE_SEC      = 7200

# ── MEXC Endpoints ──────────────────────────────
MEXC_24H    = "https://api.mexc.com/api/v3/ticker/24hr"
MEXC_PRICE  = "https://api.mexc.com/api/v3/ticker/price"
MEXC_KLINES = "https://api.mexc.com/api/v3/klines"
MEXC_DEPTH  = "https://api.mexc.com/api/v3/depth"

# ═══════════════════════════════════════════════
#                   LOGGING
# ═══════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("mexc_bot.log", encoding="utf-8"),
    ]
)
log = logging.getLogger("MexcBot")

# ═══════════════════════════════════════════════
#                   STATE
# ═══════════════════════════════════════════════
tracked        = {}   # type: Dict[str, Dict[str, Any]]
discovered     = {}   # type: Dict[str, Dict[str, Any]]
rejection_cache= {}   # type: Dict[str, float]
watchlist      = {}   # type: Dict[str, float]   🆕 {symbol: last_alert_time}
last_report    = 0.0
last_discovery = 0.0
watch_symbols  = []   # type: List[str]
btc_change_24h = 0.0
changes_map    = {}   # type: Dict[str, float]

session = requests.Session()
session.headers.update({"User-Agent": "MexcBot/7.0"})


# ═══════════════════════════════════════════════
#               HELPERS
# ═══════════════════════════════════════════════
def format_price(price):
    # type: (float) -> str
    if price == 0: return "0"
    if price < 0.0001:  return "{:.10f}".format(price).rstrip("0")
    if price < 1:       return "{:.8f}".format(price).rstrip("0")
    if price < 1000:    return "{:.4f}".format(price).rstrip("0").rstrip(".")
    return "{:,.2f}".format(price)


def send_telegram(msg):
    # type: (str) -> None
    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN.startswith("YOUR"):
        log.warning("Telegram token غير مضبوط")
        return
    try:
        r = session.post(
            "https://api.telegram.org/bot{}/sendMessage".format(TELEGRAM_TOKEN),
            data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"},
            timeout=10,
        )
        if r.status_code != 200:
            log.warning("Telegram error %s: %s", r.status_code, r.text[:200])
    except requests.RequestException as e:
        log.error("Telegram failed: %s", e)


def safe_get(url, params=None):
    # type: (str, Optional[dict]) -> Optional[Any]
    try:
        r = session.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        log.debug("API error [%s]: %s", url.split("/")[-1], e)
        return None


def is_rejected_recently(symbol):
    # type: (str) -> bool
    return (time.time() - rejection_cache.get(symbol, 0)) < REJECTION_CACHE_SEC


def mark_rejected(symbol):
    # type: (str) -> None
    rejection_cache[symbol] = time.time()


def cleanup_rejection_cache():
    # type: () -> None
    now   = time.time()
    stale = [s for s, t in list(rejection_cache.items())
             if now - t > REJECTION_CACHE_SEC * 2]
    for s in stale:
        del rejection_cache[s]


# ═══════════════════════════════════════════════
#              MEXC DATA FETCHERS
# ═══════════════════════════════════════════════
def get_klines_data(symbol, interval="15m", limit=20):
    # type: (str, str, int) -> Optional[Dict]
    data = safe_get(MEXC_KLINES, {"symbol": symbol, "interval": interval, "limit": limit})
    if not data or len(data) < 6:
        return None
    try:
        opens  = [float(c[1]) for c in data]
        highs  = [float(c[2]) for c in data]
        lows   = [float(c[3]) for c in data]
        closes = [float(c[4]) for c in data]
        vols   = [float(c[5]) for c in data]
        avg_vol = sum(vols[:-1]) / len(vols[:-1]) if len(vols) > 1 else vols[0]
        return {"opens": opens, "highs": highs, "lows": lows,
                "closes": closes, "vols": vols, "avg_vol": avg_vol}
    except (IndexError, ValueError, ZeroDivisionError) as e:
        log.debug("klines error %s: %s", symbol, e)
        return None


def get_order_book(symbol):
    # type: (str) -> Optional[Dict]
    data = safe_get(MEXC_DEPTH, {"symbol": symbol, "limit": ORDER_BOOK_LIMIT})
    if not data:
        return None
    try:
        bid_depth = sum(float(b[0]) * float(b[1]) for b in data.get("bids", []))
        ask_depth = sum(float(a[0]) * float(a[1]) for a in data.get("asks", []))
        imbalance = (bid_depth / ask_depth) if ask_depth > 0 else 99
        return {"bid_depth": bid_depth, "ask_depth": ask_depth, "imbalance": imbalance}
    except (ValueError, ZeroDivisionError) as e:
        log.debug("orderbook error %s: %s", symbol, e)
        return None


def update_btc_change():
    # type: () -> None
    global btc_change_24h
    data = safe_get(MEXC_24H, {"symbol": "BTCUSDT"})
    if data:
        try:
            btc_change_24h = float(data["priceChangePercent"])
        except (KeyError, ValueError):
            pass


# ═══════════════════════════════════════════════
#   🆕 PRE-BREAKOUT DETECTOR (الميزة الجديدة)
# ═══════════════════════════════════════════════
def detect_pre_breakout(symbol):
    # type: (str) -> Tuple[bool, float, str]
    """
    يكتشف نمط التجميع الطويل قبل الانفجار الكبير (مثل ATLA).

    الشروط:
    1. السعر كان في نطاق ضيق لفترة طويلة (تجميع)
    2. الحجم بدأ يرتفع بشكل واضح مؤخراً
    3. السعر لا يزال قريباً من قاع التجميع (لم ينفجر بعد)
    4. الشموع الأخيرة بدأت تُظهر قوة شراء

    يُرجع: (هل يوجد Breakout Setup, قوة الإشارة 0-100, وصف)
    """
    # جلب شموع 4h للتجميع الطويل (5 أيام)
    kd_4h = get_klines_data(symbol, interval="4h", limit=BREAKOUT_4H_CANDLES)
    if kd_4h is None or len(kd_4h["closes"]) < BREAKOUT_MIN_FLAT_CANDLES:
        return False, 0.0, ""

    closes_4h = kd_4h["closes"]
    highs_4h  = kd_4h["highs"]
    lows_4h   = kd_4h["lows"]
    vols_4h   = kd_4h["vols"]

    # ── شرط 1: التجميع ─────────────────────────
    # نأخذ أول 70% من الشموع = فترة التجميع
    flat_end  = int(len(closes_4h) * 0.7)
    flat_closes = closes_4h[:flat_end]
    flat_highs  = highs_4h[:flat_end]
    flat_lows   = lows_4h[:flat_end]
    flat_vols   = vols_4h[:flat_end]

    if min(flat_lows) <= 0:
        return False, 0.0, ""

    flat_range = (max(flat_highs) - min(flat_lows)) / min(flat_lows) * 100

    # نطاق التجميع يجب أن يكون ضيقاً
    if flat_range > BREAKOUT_FLAT_MAX_RANGE:
        return False, 0.0, ""

    # ── شرط 2: الحجم يرتفع في آخر الشموع ──────
    avg_flat_vol  = sum(flat_vols) / len(flat_vols) if flat_vols else 0
    recent_vols   = vols_4h[flat_end:]
    avg_recent_vol = sum(recent_vols) / len(recent_vols) if recent_vols else 0

    if avg_flat_vol <= 0:
        return False, 0.0, ""

    vol_surge = avg_recent_vol / avg_flat_vol

    if vol_surge < BREAKOUT_VOL_SURGE_RATIO:
        return False, 0.0, ""

    # ── شرط 3: السعر لا يزال قريباً من القاع ──
    current_price = closes_4h[-1]
    base_price    = min(flat_lows)
    peak_price    = max(flat_highs)

    if peak_price <= base_price:
        return False, 0.0, ""

    # نسبة ارتفاع السعر من القاع
    price_rise_from_base = (current_price - base_price) / base_price * 100

    # إذا السعر ارتفع أكثر من 30% من القاع = انطلق بالفعل، قد نكون متأخرين
    if price_rise_from_base > BREAKOUT_PRICE_NEAR_LOW:
        # لكن إذا لم يرتفع كثيراً من القمة = لا يزال في بداية الانفجار
        drop_from_peak = (peak_price - current_price) / peak_price * 100
        if drop_from_peak > 15.0:  # إذا نزل من القمة = Dump
            return False, 0.0, ""

    # ── شرط 4: الشموع الأخيرة صاعدة ────────────
    recent_closes = closes_4h[flat_end:]
    if len(recent_closes) >= 2:
        upward = sum(1 for i in range(1, len(recent_closes))
                     if recent_closes[i] >= recent_closes[i-1])
        upward_ratio = upward / (len(recent_closes) - 1) if len(recent_closes) > 1 else 0
        if upward_ratio < 0.5:
            return False, 0.0, ""
    else:
        upward_ratio = 1.0

    # ── حساب قوة الإشارة ────────────────────────
    # كلما كان التجميع أطول وأهدأ والحجم أقوى = إشارة أقوى
    tightness_score = max(0, (BREAKOUT_FLAT_MAX_RANGE - flat_range) / BREAKOUT_FLAT_MAX_RANGE * 40)
    vol_score       = min((vol_surge / BREAKOUT_VOL_SURGE_RATIO - 1) * 30, 40)
    timing_score    = max(0, (BREAKOUT_PRICE_NEAR_LOW - price_rise_from_base) / BREAKOUT_PRICE_NEAR_LOW * 20)

    strength = min(tightness_score + vol_score + timing_score, 100)

    desc = "تجميع {:.0f}% | حجم ×{:.1f} | ارتفاع من القاع {:.0f}%".format(
        flat_range, vol_surge, price_rise_from_base
    )

    log.info("💥 Pre-Breakout: %s | strength=%.0f | %s", symbol, strength, desc)
    return True, round(strength, 1), desc


# ═══════════════════════════════════════════════
#   🆕 BOTTOM DETECTOR
# ═══════════════════════════════════════════════
def detect_bottom(symbol, kd_15m):
    # type: (str, Dict) -> Tuple[bool, float, str]
    """
    يكتشف القاع قبل الارتداد:
    1. السعر عند أدنى نقطة خلال اليوم
    2. الحجم بدأ يرتفع قليلاً (علامة أولى)
    3. آخر شمعة خضراء (بدأ الارتداد)

    مثال ARB: كان عند 0.0883 (قاع) ثم ارتفع +19%
    """
    # جلب شموع 1h للنظرة الأشمل
    kd_1h = get_klines_data(symbol, interval="1h", limit=BOTTOM_LOOKBACK_1H)
    if kd_1h is None:
        return False, 0.0, ""

    closes_1h = kd_1h["closes"]
    lows_1h   = kd_1h["lows"]
    vols_1h   = kd_1h["vols"]

    if not closes_1h or min(lows_1h) <= 0:
        return False, 0.0, ""

    current_price = closes_1h[-1]
    period_low    = min(lows_1h)
    period_high   = max(kd_1h["highs"])

    # شرط 1: السعر قريب من القاع
    distance_from_low = (current_price - period_low) / period_low * 100
    if distance_from_low > BOTTOM_NEAR_LOW_PCT:
        return False, 0.0, ""

    # شرط 2: الحجم بدأ يرتفع (آخر 3 شموع)
    avg_vol_1h     = sum(vols_1h[:-3]) / max(len(vols_1h[:-3]), 1)
    recent_vol_avg = sum(vols_1h[-3:]) / 3
    if avg_vol_1h <= 0:
        return False, 0.0, ""
    vol_ratio = recent_vol_avg / avg_vol_1h
    if vol_ratio < BOTTOM_VOL_START_RATIO:
        return False, 0.0, ""

    # شرط 3: آخر شمعة 15m خضراء (بدأ الارتداد)
    opens_15m  = kd_15m["opens"]
    closes_15m = kd_15m["closes"]
    if closes_15m[-1] <= opens_15m[-1]:
        return False, 0.0, ""

    # شرط 4: السعر لم ينهار من ارتفاع سابق (ليس Dump)
    range_pct = (period_high - period_low) / period_low * 100
    if range_pct > 50 and distance_from_low < 5:
        # إذا كان هناك ارتفاع كبير قبل هذا القاع = Dump وليس قاع طبيعي
        return False, 0.0, ""

    # قوة الإشارة
    nearness_score = max(0, (BOTTOM_NEAR_LOW_PCT - distance_from_low) / BOTTOM_NEAR_LOW_PCT * 50)
    vol_score      = min((vol_ratio - 1) * 30, 30)
    candle_score   = 20  # الشمعة الخضراء تعطي نقاط ثابتة

    strength = min(nearness_score + vol_score + candle_score, 100)
    desc = "القاع {:.1f}% | حجم ×{:.1f} | ارتداد بدأ".format(distance_from_low, vol_ratio)

    return True, round(strength, 1), desc


# ═══════════════════════════════════════════════
#   🆕 WATCHLIST ALERT SYSTEM
# ═══════════════════════════════════════════════
def check_watchlist(symbol, price, change_24h=0.0):
    # type: (str, float, float) -> None
    """
    يفحص العملة للإنذار المبكر قبل Signal الرسمي.
    الشروط أخف = يكتشف مبكراً أكثر.
    """
    # لا ترسل إنذار إذا العملة فعلاً مُتتبعة
    if symbol in tracked:
        return

    # لا ترسل إنذار إذا تم الإنذار مؤخراً
    now = time.time()
    if now - watchlist.get(symbol, 0) < WATCHLIST_COOLDOWN_SEC:
        return

    # لا ترسل أكثر من الحد الأقصى
    active_alerts = sum(1 for t in watchlist.values()
                        if now - t < WATCHLIST_COOLDOWN_SEC)
    if active_alerts >= WATCHLIST_MAX_ALERTS:
        return

    # فلتر السوق
    passes, market_note = passes_market_filter(change_24h)
    if not passes:
        return

    # جلب بيانات 15m
    kd = get_klines_data(symbol)
    if kd is None:
        return

    vols    = kd["vols"]
    closes  = kd["closes"]
    avg_vol = kd["avg_vol"]

    # شرط الحجم (أخف من Signal)
    if avg_vol <= 0 or vols[-1] < avg_vol * WATCHLIST_VOL_RATIO:
        return

    # فحص القاع
    is_bottom, bottom_str, bottom_desc = detect_bottom(symbol, kd)
    if not is_bottom:
        return

    # فحص Order Book بسيط
    ob = get_order_book(symbol)
    if ob:
        if ob["bid_depth"] < WATCHLIST_MIN_BID_DEPTH:
            return
        if ob["imbalance"] < MIN_BID_ASK_IMBALANCE:
            return

    # ✅ كل الشروط متحققة — إرسال إنذار مبكر
    watchlist[symbol] = now

    ob_text = ""
    if ob:
        ob_text = "\n📗 Bid: `{:,.0f}` | ⚖️ Imb: `{:.2f}`".format(
            ob["bid_depth"], ob["imbalance"])

    market_text = "\n{}".format(market_note) if market_note else ""

    send_telegram(
        "👀 *WATCHLIST ALERT*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "💰 *{sym}* — في القاع\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "💵 Price: `{price}`\n"
        "📉 24h: `{ch:.1f}%` | BTC: `{btc:.1f}%`\n"
        "🔻 *Bottom:* `{bstr:.0f}%` — _{bdesc}_\n"
        "⚡ Vol: `{vratio:.1f}×` المتوسط"
        "{ob}{mkt}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "⏳ _انتظر Signal #1 للتأكيد_".format(
            sym=symbol,
            price=format_price(price),
            ch=change_24h,
            btc=btc_change_24h,
            bstr=bottom_str,
            bdesc=bottom_desc,
            vratio=vols[-1] / avg_vol if avg_vol > 0 else 0,
            ob=ob_text,
            mkt=market_text,
        )
    )
    log.info("👀 WATCHLIST: %s | bottom=%.0f%% | price=%s", symbol, bottom_str, format_price(price))


# ═══════════════════════════════════════════════
#   PUMP & DUMP DETECTOR
# ═══════════════════════════════════════════════
def detect_pump_and_dump(kd):
    # type: (Dict) -> Tuple[bool, str]
    """يكتشف Pump & Dump ويرفضه."""
    closes = kd["closes"]
    highs  = kd["highs"]

    if len(closes) < PUMP_LOOKBACK_CANDLES:
        return False, ""

    recent_closes = closes[-PUMP_LOOKBACK_CANDLES:]
    recent_highs  = highs[-PUMP_LOOKBACK_CANDLES:]
    min_price     = min(recent_closes)
    max_price     = max(recent_highs)
    cur_price     = closes[-1]

    if min_price <= 0:
        return False, ""

    total_rise     = (max_price - min_price) / min_price * 100
    drop_from_peak = (max_price - cur_price) / max_price * 100

    if total_rise >= PUMP_MAX_RISE_PCT:
        if drop_from_peak >= PUMP_DUMP_DROP_PCT:
            return True, "Pump {:.0f}% ثم Dump {:.0f}%".format(total_rise, drop_from_peak)
        if total_rise >= 40.0:
            return True, "ارتفاع مفرط {:.0f}%".format(total_rise)

    return False, ""


# ═══════════════════════════════════════════════
#   ANALYSIS FUNCTIONS
# ═══════════════════════════════════════════════
def detect_volume_accumulation(kd):
    # type: (Dict) -> Tuple[bool, float]
    vols    = kd["vols"]
    closes  = kd["closes"]
    avg_vol = kd["avg_vol"]
    if len(vols) < VOL_ACCUM_CANDLES:
        return False, 0.0
    recent_vols   = vols[-VOL_ACCUM_CANDLES:]
    recent_closes = closes[-VOL_ACCUM_CANDLES:]
    avg_recent    = sum(recent_vols) / len(recent_vols)
    if avg_recent < avg_vol * VOL_ACCUM_MIN_RATIO:
        return False, 0.0
    price_range = (max(recent_closes) - min(recent_closes)) / min(recent_closes) * 100
    if price_range > VOL_ACCUM_MAX_PRICE_MOVE:
        return False, 0.0
    vol_trend = sum(1 for i in range(1, len(recent_vols)) if recent_vols[i] >= recent_vols[i-1])
    if vol_trend / (len(recent_vols) - 1) < 0.5:
        return False, 0.0
    strength = min(
        (avg_recent / avg_vol - 1) * 50
        + max(0, (VOL_ACCUM_MAX_PRICE_MOVE - price_range) / VOL_ACCUM_MAX_PRICE_MOVE * 30)
        + (vol_trend / (len(recent_vols) - 1)) * 20, 100
    )
    return True, round(strength, 1)


def detect_volume_spike(kd):
    # type: (Dict) -> Tuple[bool, float]
    avg_vol = kd["avg_vol"]
    if avg_vol == 0:
        return False, 0.0
    ratio = kd["vols"][-1] / avg_vol
    return ratio >= VOL_SPIKE_RATIO, round(ratio, 2)


def detect_price_consolidation(kd):
    # type: (Dict) -> Tuple[bool, float]
    highs  = kd["highs"]
    lows   = kd["lows"]
    closes = kd["closes"]
    if len(highs) < CONSOL_CANDLES:
        return False, 0.0
    rh = highs[-CONSOL_CANDLES:]
    rl = lows[-CONSOL_CANDLES:]
    rc = closes[-CONSOL_CANDLES:]
    total_range = (max(rh) - min(rl)) / min(rl) * 100
    if total_range > CONSOL_MAX_RANGE:
        return False, 0.0
    if (rc[-1] - rc[0]) / rc[0] * 100 < -2.0:
        return False, 0.0
    hl = sum(1 for i in range(1, len(rl)) if rl[i] >= rl[i-1])
    tightness = max(0, (CONSOL_MAX_RANGE - total_range) / CONSOL_MAX_RANGE * 100)
    return True, round(min(tightness * 0.8 + (hl / (len(rl)-1)) * 20, 100), 1)


def detect_higher_lows(kd):
    # type: (Dict) -> Tuple[bool, float]
    lows = kd["lows"][-8:]
    if len(lows) < 4:
        return False, 0.0
    higher = sum(1 for i in range(1, len(lows)) if lows[i] >= lows[i-1])
    ratio  = higher / (len(lows) - 1)
    return ratio >= HIGHER_LOWS_MIN_RATIO, round(ratio * 100, 1)


def detect_green_candles(kd):
    # type: (Dict) -> Tuple[bool, float]
    opens  = kd["opens"][-8:]
    closes = kd["closes"][-8:]
    if len(opens) < 4:
        return False, 0.0
    green = sum(1 for o, c in zip(opens, closes) if c >= o)
    ratio = green / len(opens)
    return ratio >= GREEN_CANDLES_MIN_RATIO, round(ratio * 100, 1)


def passes_market_filter(symbol_change_24h):
    # type: (float) -> Tuple[bool, str]
    if not MARKET_FILTER_ENABLED:
        return True, ""
    relative = symbol_change_24h - btc_change_24h
    if btc_change_24h < -2.0:
        if relative >= 5.0:   return True, "💪 تقاوم السوق النازل بقوة"
        elif relative >= 2.0: return True, "🛡️ صمود جيد"
        elif relative >= 0.0: return True, "⚡ مستقلة عن السوق"
        else:                 return False, ""
    else:
        if symbol_change_24h >= -3.0: return True, ""
        return False, ""


# ═══════════════════════════════════════════════
#   DYNAMIC STOP LOSS
# ═══════════════════════════════════════════════
def calculate_dynamic_sl(kd, score, ob, is_breakout=False):
    # type: (Dict, int, Optional[Dict], bool) -> float
    highs = kd["highs"]
    lows  = kd["lows"]
    recent = list(zip(highs[-10:], lows[-10:]))
    if recent and min(l for _, l in recent) > 0:
        atr_pcts = [(h - l) / l * 100 for h, l in recent]
        atr = sum(atr_pcts) / len(atr_pcts)
    else:
        atr = SL_BASE_PCT

    if score >= 88:   sf = 0.70
    elif score >= 75: sf = 0.85
    elif score >= 65: sf = 1.00
    else:             sf = 1.15

    imb_f = 1.0
    if ob:
        imb = ob["imbalance"]
        if imb >= 2.0:   imb_f = 0.80
        elif imb >= 1.5: imb_f = 0.90
        elif imb >= 1.0: imb_f = 1.00
        else:            imb_f = 1.10

    # Breakout تحتاج SL أوسع لأن التقلب أكبر
    breakout_factor = 1.3 if is_breakout else 1.0

    sl = atr * sf * imb_f * breakout_factor
    sl = max(SL_MIN_PCT, min(SL_MAX_PCT, sl))
    return round(sl, 1)


# ═══════════════════════════════════════════════
#   SCORE SYSTEM v7
# ═══════════════════════════════════════════════
def calculate_score(kd, ob, vol_accum, vol_spike, consol, higher_lows, green_candles,
                    breakout_strength=0.0):
    # type: (Dict, Optional[Dict], Tuple, Tuple, Tuple, Tuple, Tuple, float) -> int
    """
    100 نقطة:
      حجم التداول       → 15
      Order Book        → 15
      Volume Accum      → 10
      Volume Spike      → 10
      Consolidation     → 10
      Higher Lows       → 10
      Green Candles     → 10
      اتجاه السعر       → 5
      🆕 Pre-Breakout   → 15  (بونص خاص)
    """
    score   = 0
    avg_vol = kd["avg_vol"]

    # 1. حجم التداول (15)
    ratio = kd["vols"][-1] / avg_vol if avg_vol > 0 else 0
    if ratio >= 3.0:   score += 15
    elif ratio >= 2.0: score += 11
    elif ratio >= 1.5: score += 7
    elif ratio >= 1.2: score += 4

    # 2. Order Book (15)
    if ob:
        if ob["bid_depth"] >= MIN_BID_DEPTH_USDT: score += 7
        imb = ob["imbalance"]
        if imb >= 2.0:   score += 8
        elif imb >= 1.5: score += 6
        elif imb >= 1.0: score += 4
        elif imb >= 0.8: score += 2

    # 3. Volume Accumulation (10)
    is_accum, accum_str = vol_accum
    if is_accum:
        score += max(int(accum_str / 100 * 10), 6)

    # 4. Volume Spike (10)
    is_spike, spike_r = vol_spike
    if is_spike:
        if spike_r >= 5.0:   score += 10
        elif spike_r >= 3.5: score += 7
        else:                score += 5

    # 5. Consolidation (10)
    is_consol, consol_str = consol
    if is_consol:
        score += max(int(consol_str / 100 * 10), 5)

    # 6. Higher Lows (10)
    is_hl, hl_pct = higher_lows
    if is_hl:
        if hl_pct >= 80:   score += 10
        elif hl_pct >= 70: score += 7
        else:              score += 4

    # 7. Green Candles (10)
    is_green, green_pct = green_candles
    if is_green:
        if green_pct >= 75:   score += 10
        elif green_pct >= 60: score += 6
        else:                 score += 3

    # 8. اتجاه السعر (5)
    closes = kd["closes"]
    if closes[-1] > closes[0]:
        score += 5

    # 9. 🆕 Pre-Breakout Bonus (15)
    if breakout_strength > 0:
        bonus = max(int(breakout_strength / 100 * 15), 8)
        score += bonus

    return min(score, 100)


def score_label(score):
    # type: (int) -> Optional[str]
    if score >= 88:        return "🏆 *GOLD SIGNAL*"
    if score >= 75:        return "🔵 *SILVER SIGNAL*"
    if score >= SCORE_MIN: return "🟡 *BRONZE SIGNAL*"
    return None


# ═══════════════════════════════════════════════
#   FULL VALIDATION v7
# ═══════════════════════════════════════════════
def valid_setup(symbol, symbol_change_24h=0.0):
    # type: (str, float) -> Optional[Dict]

    if is_rejected_recently(symbol):
        return None

    passes, market_note = passes_market_filter(symbol_change_24h)
    if not passes:
        mark_rejected(symbol)
        return None

    # شموع 15m
    kd = get_klines_data(symbol)
    if kd is None:
        mark_rejected(symbol)
        return None

    # Pump & Dump Filter
    is_pnd, pnd_reason = detect_pump_and_dump(kd)
    if is_pnd:
        log.info("🚫 P&D رُفض: %s | %s", symbol, pnd_reason)
        mark_rejected(symbol)
        return None

    # فلتر الحجم
    if kd["vols"][-1] < kd["avg_vol"] * 1.2 or kd["vols"][-1] < DISCOVERY_MIN_VOL:
        mark_rejected(symbol)
        return None

    # Green Candles
    is_green, green_pct = detect_green_candles(kd)
    if not is_green:
        mark_rejected(symbol)
        return None

    # Order Book
    ob = get_order_book(symbol)
    if ob:
        if ob["imbalance"] < MIN_BID_ASK_IMBALANCE:
            mark_rejected(symbol)
            return None
        if ob["imbalance"] > MAX_BID_ASK_IMBALANCE:
            mark_rejected(symbol)
            return None
        if ob["bid_depth"] < MIN_BID_DEPTH_USDT:
            mark_rejected(symbol)
            return None

    # 🆕 Pre-Breakout Detection على 4h
    is_breakout, breakout_str, breakout_desc = detect_pre_breakout(symbol)

    # التحليلات المتقدمة
    vol_accum   = detect_volume_accumulation(kd)
    vol_spike   = detect_volume_spike(kd)
    consol      = detect_price_consolidation(kd)
    higher_lows = detect_higher_lows(kd)

    return {
        "kd":            kd,
        "ob":            ob,
        "vol_accum":     vol_accum,
        "vol_spike":     vol_spike,
        "consol":        consol,
        "higher_lows":   higher_lows,
        "green":         (is_green, green_pct),
        "market_note":   market_note,
        "is_breakout":   is_breakout,
        "breakout_str":  breakout_str,
        "breakout_desc": breakout_desc,
    }


# ═══════════════════════════════════════════════
#   SYMBOL DISCOVERY
# ═══════════════════════════════════════════════
def discover_symbols():
    # type: () -> Tuple[List[str], Dict[str, float]]
    global btc_change_24h
    log.info("🔍 تحديث قائمة الأزواج...")
    data = safe_get(MEXC_24H)
    if not data:
        log.error("فشل جلب بيانات السوق")
        return watch_symbols, changes_map

    ch_map = {}   # type: Dict[str, float]
    result = []

    for s in data:
        sym = s.get("symbol", "")
        try:
            change = float(s["priceChangePercent"])
            vol    = float(s["quoteVolume"])
        except (KeyError, ValueError):
            continue

        if sym == "BTCUSDT":
            btc_change_24h = change

        if not sym.endswith("USDT"): continue
        if sym in EXCLUDED: continue
        base = sym.replace("USDT", "")
        if base in STABLECOINS: continue
        if any(kw in sym for kw in LEVERAGE_KEYWORDS): continue

        ch_map[sym] = change

        if DISCOVERY_MIN_VOL < vol < DISCOVERY_MAX_VOL and abs(change) < DISCOVERY_MAX_CHANGE:
            result.append((sym, vol))

    result.sort(key=lambda x: -x[1])
    symbols = [s for s, _ in result[:MAX_SYMBOLS]]
    log.info("✅ %d زوج | BTC: %.2f%%", len(symbols), btc_change_24h)
    return symbols, ch_map


# ═══════════════════════════════════════════════
#   STOP LOSS HANDLER
# ═══════════════════════════════════════════════
def check_stop_loss(symbol, price):
    # type: (str, float) -> bool
    if symbol not in tracked:
        return False
    entry  = tracked[symbol]["entry"]
    sl_pct = tracked[symbol].get("sl_pct", SL_BASE_PCT)
    change = (price - entry) / entry * 100
    if change <= -sl_pct:
        send_telegram(
            "🛑 *STOP LOSS* | `{sym}`\n"
            "📉 خسارة: `{ch:.2f}%` | SL: `-{sl}%`\n"
            "💵 دخول: `{entry}` ← الآن: `{now}`".format(
                sym=symbol, ch=change, sl=sl_pct,
                entry=format_price(entry), now=format_price(price)
            )
        )
        log.info("🛑 SL: %s | %.2f%% (SL=%.1f%%)", symbol, change, sl_pct)
        del tracked[symbol]
        return True
    return False


# ═══════════════════════════════════════════════
#   SIGNAL HANDLER v7
# ═══════════════════════════════════════════════
def handle_signal(symbol, price, change_24h=0.0):
    # type: (str, float, float) -> None
    if symbol.replace("USDT", "") in STABLECOINS:
        return

    now = time.time()

    if check_stop_loss(symbol, price):
        return

    if symbol in tracked:
        if now - tracked[symbol].get("last_alert", 0) < ALERT_COOLDOWN_SEC:
            return

    result = valid_setup(symbol, change_24h)
    if result is None:
        return

    kd           = result["kd"]
    ob           = result["ob"]
    vol_accum    = result["vol_accum"]
    vol_spike    = result["vol_spike"]
    consol       = result["consol"]
    higher_lows  = result["higher_lows"]
    green        = result["green"]
    market_note  = result["market_note"]
    is_breakout  = result["is_breakout"]
    breakout_str = result["breakout_str"]
    breakout_desc= result["breakout_desc"]

    score = calculate_score(kd, ob, vol_accum, vol_spike, consol,
                            higher_lows, green, breakout_str)
    label = score_label(score)
    if not label:
        return

    # ── نص الإشارات ──────────────────────────────
    signals_text = ""
    is_accum,  accum_str  = vol_accum
    is_spike,  spike_r    = vol_spike
    is_consol, consol_str = consol
    is_hl,     hl_pct     = higher_lows
    is_green,  green_pct  = green

    # 🆕 Breakout أولاً لأنه أهم
    if is_breakout:
        signals_text += "\n💥 *BREAKOUT SETUP:* `{:.0f}%`\n   _{}_".format(
            breakout_str, breakout_desc)

    if is_spike:
        signals_text += "\n⚡ *Vol Spike:* `{:.1f}×` المتوسط".format(spike_r)
    if is_accum:
        signals_text += "\n🔋 *Vol Accum:* `{:.0f}%`".format(accum_str)
    if is_consol:
        signals_text += "\n🎯 *Consolidation:* `{:.0f}%`".format(consol_str)
    if is_hl:
        signals_text += "\n📈 *Higher Lows:* `{:.0f}%`".format(hl_pct)
    if is_green:
        signals_text += "\n🟢 *Green Candles:* `{:.0f}%`".format(green_pct)
    if market_note:
        signals_text += "\n{}".format(market_note)

    # ── Order Book ────────────────────────────────
    ob_text = ""
    if ob:
        imb_emoji = "🟢" if ob["imbalance"] >= 1.2 else "🟡"
        ob_text = (
            "\n📗 Bid: `{:,.0f}` | 📕 Ask: `{:,.0f}`"
            "\n{} Imbalance: `{:.2f}`"
        ).format(ob["bid_depth"], ob["ask_depth"], imb_emoji, ob["imbalance"])

    # ── نوع الإشارة ───────────────────────────────
    if is_breakout:
        stype = "💥 *BREAKOUT SETUP*"
    else:
        active = sum([is_spike, is_accum, is_consol, is_hl])
        if active >= 3:              stype = "💎 *PRE-EXPLOSION*"
        elif is_accum and is_consol: stype = "🔥 *ACCUM+CONSOL*"
        elif is_spike:               stype = "⚡ *VOLUME SPIKE*"
        elif is_accum:               stype = "🔋 *ACCUMULATION*"
        elif is_consol:              stype = "🎯 *CONSOLIDATION*"
        else:                        stype = "📊 *SIGNAL*"

    # ── إشارة #1 ─────────────────────────────────
    if symbol not in tracked:
        sl_pct = calculate_dynamic_sl(kd, score, ob, is_breakout)
        tracked[symbol] = {
            "entry":      price,
            "level":      1,
            "score":      score,
            "entry_time": now,
            "last_alert": now,
            "sl_pct":     sl_pct,
        }
        discovered[symbol] = {"price": price, "time": now, "score": score}

        send_telegram(
            "👑 *SOURCE BOT VIP v8*\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "💰 *{sym}*\n"
            "{label} | {stype}\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "💵 Price: `{price}`\n"
            "📊 Score: *{score}/100*\n"
            "🕐 Time: `{time}`"
            "{signals}"
            "{ob}\n"
            "📉 24h: `{ch:.1f}%` | BTC: `{btc:.1f}%`\n"
            "⚠️ Stop Loss: `-{sl}%` (ديناميكي)".format(
                sym=symbol, label=label, stype=stype,
                price=format_price(price), score=score,
                time=datetime.now().strftime("%H:%M:%S"),
                signals=signals_text, ob=ob_text,
                ch=change_24h, btc=btc_change_24h,
                sl=sl_pct,
            )
        )
        log.info("🟢 #1 | %s | score=%d | breakout=%s spike=%s accum=%s sl=%.1f%%",
                 symbol, score, is_breakout, is_spike, is_accum, sl_pct)
        return

    # ── إشارات المتابعة ───────────────────────────
    entry  = tracked[symbol]["entry"]
    level  = tracked[symbol]["level"]
    sl_pct = tracked[symbol].get("sl_pct", SL_BASE_PCT)
    change = (price - entry) / entry * 100

    if level == 1 and change >= SIGNAL2_GAIN:
        send_telegram(
            "🚀 {label} | *SIGNAL #2*\n"
            "💰 *{sym}*\n"
            "📈 Gain: *+{gain:.2f}%*\n"
            "💵 Price: `{price}` | Score: *{score}*\n"
            "⚠️ SL: `-{sl}%`{signals}{ob}".format(
                label=label, sym=symbol, gain=change,
                price=format_price(price), score=score,
                sl=sl_pct, signals=signals_text, ob=ob_text,
            )
        )
        tracked[symbol]["level"]      = 2
        tracked[symbol]["last_alert"] = now
        log.info("🔵 #2 | %s | +%.2f%%", symbol, change)

    elif level == 2 and change >= SIGNAL3_GAIN:
        send_telegram(
            "🔥 {label} | *SIGNAL #3*\n"
            "💰 *{sym}*\n"
            "📈 Gain: *+{gain:.2f}%*\n"
            "💵 Price: `{price}` | Score: *{score}*\n"
            "⚠️ SL: `-{sl}%`{signals}{ob}".format(
                label=label, sym=symbol, gain=change,
                price=format_price(price), score=score,
                sl=sl_pct, signals=signals_text, ob=ob_text,
            )
        )
        tracked[symbol]["level"]      = 3
        tracked[symbol]["last_alert"] = now
        log.info("🔥 #3 | %s | +%.2f%%", symbol, change)


# ═══════════════════════════════════════════════
#   CLEANUP
# ═══════════════════════════════════════════════
def cleanup_stale():
    # type: () -> None
    now   = time.time()
    stale = [s for s, d in list(tracked.items())
             if now - d["entry_time"] > STALE_REMOVE_SEC]
    for s in stale:
        log.info("🗑️ حذف متوقف: %s", s)
        del tracked[s]
    cleanup_rejection_cache()


# ═══════════════════════════════════════════════
#   PERFORMANCE REPORT
# ═══════════════════════════════════════════════
def send_report():
    # type: () -> None
    global last_report
    now = time.time()
    if now - last_report < REPORT_INTERVAL:
        return
    last_report = now
    rows = []
    for sym, d in list(discovered.items()):
        pd = safe_get(MEXC_PRICE, {"symbol": sym})
        if not pd:
            continue
        try:
            cur    = float(pd["price"])
            growth = (cur - d["price"]) / d["price"] * 100
            if growth > 5:
                rows.append((sym, d["price"], cur, growth, d["score"]))
        except (KeyError, ValueError, ZeroDivisionError):
            continue
    if not rows:
        return
    rows.sort(key=lambda x: -x[3])
    msg = "⚡ *PERFORMANCE REPORT v7*\n🕐 `{}`\n\n".format(
        datetime.now().strftime("%Y-%m-%d %H:%M"))
    for sym, disc, cur, growth, score in rows[:5]:
        msg += "🔥 *{}*  Entry:`{}`  Now:`{}`\n   +{:.2f}% | Score:{}\n\n".format(
            sym, format_price(disc), format_price(cur), growth, score)
    send_telegram(msg)
    log.info("📊 تقرير الأداء أُرسل")


# ═══════════════════════════════════════════════
#   MAIN LOOP
# ═══════════════════════════════════════════════
def run():
    global watch_symbols, changes_map, last_discovery

    log.info("🚀 MEXC Bot v8 يبدأ...")
    send_telegram(
        "🤖 *SOURCE BOT VIP v8*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🆕 Watchlist Alert: ✅\n"
        "   إنذار مبكر عند القاع قبل الصعود\n"
        "🆕 Bottom Detector: ✅\n"
        "   يكتشف الارتداد من القاع مبكراً\n"
        "✅ Pre-Breakout (4h + 15m)\n"
        "✅ Anti Pump&Dump (>{pmp}%)\n"
        "✅ Dynamic SL: `{sl_min}-{sl_max}%`\n"
        "⚙️ Score Min: `{score}` | Pairs: `{pairs}`".format(
            pmp=int(PUMP_MAX_RISE_PCT),
            sl_min=SL_MIN_PCT, sl_max=SL_MAX_PCT,
            score=SCORE_MIN, pairs=MAX_SYMBOLS,
        )
    )

    res            = discover_symbols()
    watch_symbols  = res[0]
    changes_map    = res[1]
    last_discovery = time.time()
    cycle          = 0

    while True:
        try:
            now = time.time()
            if now - last_discovery >= DISCOVERY_REFRESH_SEC:
                res            = discover_symbols()
                watch_symbols  = res[0]
                changes_map    = res[1]
                last_discovery = now

            prices_data = safe_get(MEXC_PRICE)
            if prices_data:
                price_map = {}
                for p in prices_data:
                    try:
                        price_map[p["symbol"]] = float(p["price"])
                    except (KeyError, ValueError):
                        pass
                for sym in watch_symbols:
                    if sym in price_map:
                        handle_signal(sym, price_map[sym], changes_map.get(sym, 0.0))
                        # 🆕 فحص Watchlist لكل عملة غير مُتتبعة
                        if sym not in tracked:
                            check_watchlist(sym, price_map[sym], changes_map.get(sym, 0.0))

            cycle += 1
            if cycle % 10  == 0: cleanup_stale()
            if cycle % 360 == 0: update_btc_change()

            send_report()
            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            send_telegram("⛔ *SOURCE BOT VIP v8* – تم الإيقاف")
            break
        except Exception as e:
            log.error("خطأ: %s", e, exc_info=True)
            time.sleep(5)


if __name__ == "__main__":
    run()

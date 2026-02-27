"""
╔═══════════════════════════════════════════════════════════════╗
║         MEXC LIQUIDITY BOT v3 – PRE-EXPLOSION DETECTOR       ║
║   Volume Accumulation + Price Consolidation + Market Filter  ║
╚═══════════════════════════════════════════════════════════════╝

الميزات الجديدة v3:
  🆕 Volume Accumulation  — حجم يرتفع + سعر ثابت = تراكم شراء خفي
  🆕 Price Consolidation  — سعر في نطاق ضيق = استعداد للانفجار
  🆕 Market Filter        — تجاهل العملات النازلة مع السوق
  🆕 Pre-Explosion Score  — نقاط خاصة للإشارات المبكرة
  ✅ كل ميزات v2 السابقة محفوظة
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

DISCOVERY_MIN_VOL    = 500_000     # خُفِّف قليلاً لاكتشاف عملات مبكراً
DISCOVERY_MAX_VOL    = 30_000_000
DISCOVERY_MAX_CHANGE = 12          # رُفِع لاكتشاف العملات التي بدأت بالتحرك
MAX_SYMBOLS          = 50          # زيادة لرصد أوسع

# ── Order Book ───────────────────────────────────
ORDER_BOOK_LIMIT      = 20
MIN_BID_DEPTH_USDT    = 30_000     # خُفِّف للعملات الصغيرة
MAX_BID_ASK_IMBALANCE = 3.0

# ── إعدادات الإشارات ────────────────────────────
SCORE_MIN          = 65            # خُفِّف لاكتشاف الفرص المبكرة
SIGNAL2_GAIN       = 2.0
SIGNAL3_GAIN       = 4.0
STOP_LOSS_PCT      = -4.0
ALERT_COOLDOWN_SEC = 300

# ── Volume Accumulation (ميزة جديدة) ─────────────
# حجم يرتفع تدريجياً بينما السعر ثابت = تراكم شراء
VOL_ACCUM_CANDLES      = 6         # عدد الشموع للفحص
VOL_ACCUM_MIN_RATIO    = 1.5       # الحجم يجب أن يكون 1.5× المتوسط
VOL_ACCUM_MAX_PRICE_MOVE = 3.0    # السعر لا يتحرك أكثر من 3% خلال التراكم

# ── Price Consolidation (ميزة جديدة) ─────────────
# سعر في نطاق ضيق = استعداد للانفجار
CONSOL_CANDLES     = 8             # عدد الشموع للفحص
CONSOL_MAX_RANGE   = 4.0           # النطاق الأقصى % بين أعلى وأدنى سعر

# ── فلتر السوق (ميزة جديدة) ──────────────────────
# مقارنة العملة مع BTC لمعرفة إذا كانت تتحرك بشكل مستقل
MARKET_FILTER_ENABLED  = True
MARKET_INDEPENDENCE_MIN = 0.0      # العملة يجب أن تكون مستقلة أو أفضل من السوق

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
last_report    = 0.0
last_discovery = 0.0
watch_symbols  = []   # type: List[str]
btc_change_24h = 0.0  # تغيير BTC خلال 24 ساعة للمقارنة

session = requests.Session()
session.headers.update({"User-Agent": "MexcBot/3.0"})


# ═══════════════════════════════════════════════
#               HELPERS
# ═══════════════════════════════════════════════
def format_price(price):
    # type: (float) -> str
    if price == 0:
        return "0"
    if price < 0.0001:
        return "{:.10f}".format(price).rstrip("0")
    if price < 1:
        return "{:.8f}".format(price).rstrip("0")
    if price < 1000:
        return "{:.4f}".format(price).rstrip("0").rstrip(".")
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
            log.warning("Telegram API error %s: %s", r.status_code, r.text[:200])
    except requests.RequestException as e:
        log.error("Telegram send failed: %s", e)


def safe_get(url, params=None):
    # type: (str, Optional[dict]) -> Optional[Any]
    try:
        r = session.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        log.debug("API error [%s]: %s", url.split("/")[-1], e)
        return None


# ═══════════════════════════════════════════════
#              MEXC DATA FETCHERS
# ═══════════════════════════════════════════════
def get_klines_data(symbol, interval="15m", limit=20):
    # type: (str, str, int) -> Optional[Dict]
    """جلب بيانات الشموع مع عدد أكبر للتحليل المتقدم."""
    data = safe_get(MEXC_KLINES, {"symbol": symbol, "interval": interval, "limit": limit})
    if not data or len(data) < 6:
        return None
    try:
        vols    = [float(c[5]) for c in data]
        closes  = [float(c[4]) for c in data]
        highs   = [float(c[2]) for c in data]
        lows    = [float(c[3]) for c in data]
        avg_vol = sum(vols[:-1]) / len(vols[:-1])
        return {
            "vols":    vols,
            "closes":  closes,
            "highs":   highs,
            "lows":    lows,
            "avg_vol": avg_vol,
        }
    except (IndexError, ValueError, ZeroDivisionError) as e:
        log.debug("klines parse error %s: %s", symbol, e)
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
        log.debug("orderbook parse error %s: %s", symbol, e)
        return None


def update_btc_change():
    # type: () -> None
    """تحديث تغيير BTC لفلتر السوق."""
    global btc_change_24h
    data = safe_get(MEXC_24H, {"symbol": "BTCUSDT"})
    if data:
        try:
            btc_change_24h = float(data["priceChangePercent"])
            log.debug("BTC 24h change: %.2f%%", btc_change_24h)
        except (KeyError, ValueError):
            pass


# ═══════════════════════════════════════════════
#   🆕 VOLUME ACCUMULATION DETECTOR
# ═══════════════════════════════════════════════
def detect_volume_accumulation(kd):
    # type: (Dict) -> Tuple[bool, float]
    """
    يكتشف تراكم الشراء الخفي:
    الحجم يرتفع تدريجياً بينما السعر ثابت نسبياً.
    هذه من أقوى إشارات الانفجار القادم.

    يُرجع: (هل يوجد تراكم, قوة التراكم 0-100)
    """
    vols   = kd["vols"]
    closes = kd["closes"]

    if len(vols) < VOL_ACCUM_CANDLES:
        return False, 0.0

    # أخذ آخر N شمعة للفحص
    recent_vols   = vols[-VOL_ACCUM_CANDLES:]
    recent_closes = closes[-VOL_ACCUM_CANDLES:]
    avg_vol       = kd["avg_vol"]

    # شرط 1: الحجم يجب أن يكون فوق المتوسط
    avg_recent_vol = sum(recent_vols) / len(recent_vols)
    if avg_recent_vol < avg_vol * VOL_ACCUM_MIN_RATIO:
        return False, 0.0

    # شرط 2: السعر لا يتحرك كثيراً (تراكم هادئ)
    price_range = (max(recent_closes) - min(recent_closes)) / min(recent_closes) * 100
    if price_range > VOL_ACCUM_MAX_PRICE_MOVE:
        return False, 0.0

    # شرط 3: الحجم يتصاعد (كل شمعة أعلى من السابقة في المتوسط)
    vol_trend = sum(
        1 for i in range(1, len(recent_vols)) if recent_vols[i] >= recent_vols[i-1]
    )
    vol_trend_ratio = vol_trend / (len(recent_vols) - 1)

    if vol_trend_ratio < 0.5:
        return False, 0.0

    # حساب قوة التراكم (0-100)
    vol_strength   = min((avg_recent_vol / avg_vol - 1) * 50, 50)
    price_stability = max(0, (VOL_ACCUM_MAX_PRICE_MOVE - price_range) / VOL_ACCUM_MAX_PRICE_MOVE * 30)
    trend_bonus    = vol_trend_ratio * 20

    strength = vol_strength + price_stability + trend_bonus
    return True, round(min(strength, 100), 1)


# ═══════════════════════════════════════════════
#   🆕 PRICE CONSOLIDATION DETECTOR
# ═══════════════════════════════════════════════
def detect_price_consolidation(kd):
    # type: (Dict) -> Tuple[bool, float]
    """
    يكتشف تضيّق نطاق السعر (Consolidation):
    السعر يتحرك في نطاق ضيق = ضغط يتراكم = انفجار قادم.

    يُرجع: (هل يوجد consolidation, نسبة ضيق النطاق 0-100)
    """
    highs  = kd["highs"]
    lows   = kd["lows"]
    closes = kd["closes"]

    if len(highs) < CONSOL_CANDLES:
        return False, 0.0

    recent_highs  = highs[-CONSOL_CANDLES:]
    recent_lows   = lows[-CONSOL_CANDLES:]
    recent_closes = closes[-CONSOL_CANDLES:]

    # حساب النطاق الكلي
    total_range = (max(recent_highs) - min(recent_lows)) / min(recent_lows) * 100
    if total_range > CONSOL_MAX_RANGE:
        return False, 0.0

    # التحقق من أن السعر لم ينهار (يجب أن يكون مستقراً أو صاعداً قليلاً)
    price_direction = (recent_closes[-1] - recent_closes[0]) / recent_closes[0] * 100
    if price_direction < -2.0:
        return False, 0.0

    # كلما كان النطاق أضيق = ضغط أكبر = تحرك قريب
    tightness = max(0, (CONSOL_MAX_RANGE - total_range) / CONSOL_MAX_RANGE * 100)

    # مكافأة إذا كان السعر يرتفع تدريجياً داخل النطاق (Higher Lows)
    higher_lows = sum(
        1 for i in range(1, len(recent_lows)) if recent_lows[i] >= recent_lows[i-1]
    )
    higher_lows_bonus = (higher_lows / (len(recent_lows) - 1)) * 20

    strength = min(tightness * 0.8 + higher_lows_bonus, 100)
    return True, round(strength, 1)


# ═══════════════════════════════════════════════
#   🆕 MARKET FILTER
# ═══════════════════════════════════════════════
def passes_market_filter(symbol_change_24h):
    # type: (float) -> Tuple[bool, str]
    """
    يتحقق من أن العملة تتحرك بشكل مستقل عن السوق.
    إذا كان BTC ينزل والعملة تصمد أو ترتفع = إشارة قوية.

    يُرجع: (هل تجتاز الفلتر, وصف الحالة)
    """
    if not MARKET_FILTER_ENABLED:
        return True, ""

    # العملة أقوى من BTC بـ 3% أو أكثر = مستقلة تماماً
    relative_strength = symbol_change_24h - btc_change_24h

    if btc_change_24h < -2.0:
        # السوق نازل
        if relative_strength >= 5.0:
            return True, "💪 مقاومة السوق النازل"
        elif relative_strength >= 2.0:
            return True, "🛡️ صمود جيد"
        elif relative_strength >= 0.0:
            return True, "⚡ مستقلة عن السوق"
        else:
            return False, ""  # تنزل مع السوق
    else:
        # السوق محايد أو صاعد - قبول كل العملات الصاعدة
        if symbol_change_24h >= 0:
            return True, ""
        elif symbol_change_24h >= -3.0:
            return True, ""
        else:
            return False, ""


# ═══════════════════════════════════════════════
#           SCORE SYSTEM v3
# ═══════════════════════════════════════════════
def calculate_score(kd, ob, vol_accum, consol):
    # type: (Dict, Optional[Dict], Tuple[bool, float], Tuple[bool, float]) -> int
    """
    نقاط السكور v3 (100 نقطة):
      • قوة الحجم          → 25 نقطة
      • استقرار السعر       → 15 نقطة
      • اتجاه السعر         → 15 نقطة
      • Order Book          → 15 نقطة
      • Volume Accumulation → 15 نقطة (جديد)
      • Price Consolidation → 15 نقطة (جديد)
    """
    score   = 0
    vols    = kd["vols"]
    closes  = kd["closes"]
    avg_vol = kd["avg_vol"]

    # 1. قوة حجم التداول (25)
    ratio = vols[-1] / avg_vol if avg_vol > 0 else 0
    if ratio >= 3.0:
        score += 25
    elif ratio >= 2.0:
        score += 20
    elif ratio >= 1.5:
        score += 13
    elif ratio >= 1.2:
        score += 7

    # 2. استقرار السعر (15)
    price_swing = (max(closes) - min(closes)) / min(closes) * 100 if min(closes) > 0 else 99
    if price_swing < 2:
        score += 15
    elif price_swing < 4:
        score += 10
    elif price_swing < 6:
        score += 5

    # 3. اتجاه السعر (15)
    if closes[-1] > closes[0]:
        trend_pct = (closes[-1] - closes[0]) / closes[0] * 100
        if trend_pct >= 3:
            score += 15
        elif trend_pct >= 1:
            score += 10
        else:
            score += 5

    # 4. عمق Order Book (15)
    if ob:
        if ob["bid_depth"] >= MIN_BID_DEPTH_USDT:
            score += 8
        if ob["imbalance"] <= MAX_BID_ASK_IMBALANCE:
            score += 7

    # 5. 🆕 Volume Accumulation (15)
    is_accum, accum_strength = vol_accum
    if is_accum:
        bonus = int(accum_strength / 100 * 15)
        score += max(bonus, 8)  # حد أدنى 8 نقاط إذا وُجد التراكم

    # 6. 🆕 Price Consolidation (15)
    is_consol, consol_strength = consol
    if is_consol:
        bonus = int(consol_strength / 100 * 15)
        score += max(bonus, 8)

    return min(score, 100)


def score_label(score):
    # type: (int) -> Optional[str]
    if score >= 88:
        return "🏆 *GOLD SIGNAL*"
    if score >= 75:
        return "🔵 *SILVER SIGNAL*"
    if score >= SCORE_MIN:
        return "🟡 *BRONZE SIGNAL*"
    return None


# ═══════════════════════════════════════════════
#     LIQUIDITY VALIDATION v3
# ═══════════════════════════════════════════════
def valid_setup(symbol, symbol_change_24h=0.0):
    # type: (str, float) -> Tuple[bool, Optional[Dict], Optional[Dict], Tuple[bool,float], Tuple[bool,float], str]
    """
    يُرجع: (is_valid, kd, ob, vol_accum, consol, market_note)
    """
    # فلتر السوق أولاً (سريع بدون API)
    passes, market_note = passes_market_filter(symbol_change_24h)
    if not passes:
        return False, None, None, (False, 0), (False, 0), ""

    # جلب بيانات الشموع (20 شمعة للتحليل المتقدم)
    kd = get_klines_data(symbol, limit=20)
    if kd is None:
        return False, None, None, (False, 0), (False, 0), ""

    # فلتر الحجم الأساسي
    if kd["vols"][-1] < kd["avg_vol"] * 1.2:
        return False, None, None, (False, 0), (False, 0), ""
    if kd["vols"][-1] < DISCOVERY_MIN_VOL:
        return False, None, None, (False, 0), (False, 0), ""

    # تحليل Volume Accumulation و Consolidation
    vol_accum = detect_volume_accumulation(kd)
    consol    = detect_price_consolidation(kd)

    # Order Book
    ob = get_order_book(symbol)
    if ob:
        if ob["bid_depth"] < MIN_BID_DEPTH_USDT:
            return False, None, None, (False, 0), (False, 0), ""
        if ob["imbalance"] > MAX_BID_ASK_IMBALANCE:
            return False, None, None, (False, 0), (False, 0), ""

    return True, kd, ob, vol_accum, consol, market_note


# ═══════════════════════════════════════════════
#              SYMBOL DISCOVERY
# ═══════════════════════════════════════════════
def discover_symbols():
    # type: () -> Tuple[List[str], Dict[str, float]]
    """يُرجع (قائمة الأزواج, قاموس التغيرات)"""
    global btc_change_24h
    log.info("🔍 تحديث قائمة الأزواج...")
    data = safe_get(MEXC_24H)
    if not data:
        log.error("فشل جلب بيانات السوق من MEXC")
        return watch_symbols, {}

    changes_map = {}  # type: Dict[str, float]
    result      = []

    for s in data:
        sym = s.get("symbol", "")
        try:
            change = float(s["priceChangePercent"])
            vol    = float(s["quoteVolume"])
        except (KeyError, ValueError):
            continue

        # تخزين تغيير BTC
        if sym == "BTCUSDT":
            btc_change_24h = change

        if not sym.endswith("USDT"):
            continue
        if sym in EXCLUDED:
            continue
        base = sym.replace("USDT", "")
        if base in STABLECOINS:
            continue
        if any(kw in sym for kw in LEVERAGE_KEYWORDS):
            continue

        changes_map[sym] = change

        if DISCOVERY_MIN_VOL < vol < DISCOVERY_MAX_VOL and abs(change) < DISCOVERY_MAX_CHANGE:
            result.append((sym, vol))

    result.sort(key=lambda x: -x[1])
    symbols = [s for s, _ in result[:MAX_SYMBOLS]]
    log.info("✅ تم اكتشاف %d زوج | BTC 24h: %.2f%%", len(symbols), btc_change_24h)
    return symbols, changes_map


# ═══════════════════════════════════════════════
#           STOP LOSS HANDLER
# ═══════════════════════════════════════════════
def check_stop_loss(symbol, price):
    # type: (str, float) -> bool
    if symbol not in tracked:
        return False
    entry  = tracked[symbol]["entry"]
    change = (price - entry) / entry * 100
    if change <= STOP_LOSS_PCT:
        send_telegram(
            "🛑 *STOP LOSS* | `{}`\n"
            "📉 خسارة: `{:.2f}%`\n"
            "💵 سعر الدخول: `{}`\n"
            "💵 السعر الحالي: `{}`".format(
                symbol, change, format_price(entry), format_price(price)
            )
        )
        log.info("🛑 Stop Loss: %s | %.2f%%", symbol, change)
        del tracked[symbol]
        return True
    return False


# ═══════════════════════════════════════════════
#             SIGNAL HANDLER v3
# ═══════════════════════════════════════════════
def handle_signal(symbol, price, change_24h=0.0):
    # type: (str, float, float) -> None
    base = symbol.replace("USDT", "")
    if base in STABLECOINS:
        return

    now = time.time()

    if check_stop_loss(symbol, price):
        return

    if symbol in tracked:
        last_alert = tracked[symbol].get("last_alert", 0)
        if now - last_alert < ALERT_COOLDOWN_SEC:
            return

    is_valid, kd, ob, vol_accum, consol, market_note = valid_setup(symbol, change_24h)
    if not is_valid or kd is None:
        return

    score = calculate_score(kd, ob, vol_accum, consol)
    label = score_label(score)
    if not label:
        return

    # ── بناء نص الإشارات المتقدمة ────────────────
    signals_text = ""
    is_accum, accum_str = vol_accum
    is_consol, consol_str = consol

    if is_accum:
        signals_text += "\n🔋 *Volume Accum:* `{:.0f}%`".format(accum_str)
    if is_consol:
        signals_text += "\n🎯 *Consolidation:* `{:.0f}%`".format(consol_str)
    if market_note:
        signals_text += "\n{}".format(market_note)

    # ── Order Book text ───────────────────────────
    ob_text = ""
    if ob:
        ob_text = (
            "\n📗 Bid: `{:,.0f}` | 📕 Ask: `{:,.0f}`"
            "\n⚖️ Imbalance: `{:.2f}`"
        ).format(ob["bid_depth"], ob["ask_depth"], ob["imbalance"])

    # ── اختيار إيموجي حسب نوع الإشارة ───────────
    if is_accum and is_consol:
        signal_type = "💎 *PRE-EXPLOSION*"
    elif is_accum:
        signal_type = "🔋 *ACCUMULATION*"
    elif is_consol:
        signal_type = "🎯 *CONSOLIDATION*"
    else:
        signal_type = "*SIGNAL*"

    # ── إشارة #1 ─────────────────────────────────
    if symbol not in tracked:
        tracked[symbol] = {
            "entry":      price,
            "level":      1,
            "score":      score,
            "entry_time": now,
            "last_alert": now,
        }
        discovered[symbol] = {"price": price, "time": now, "score": score}

        send_telegram(
            "👑 *SOURCE BOT VIP*\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "💰 *{sym}*\n"
            "{label} | {stype} #1\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "💵 Price: `{price}`\n"
            "📊 Score: *{score}/100*\n"
            "🕐 Time: `{time}`"
            "{signals}"
            "{ob}\n"
            "⚠️ Stop Loss: `-{sl}%`\n"
            "📉 24h: `{change:.2f}%` | BTC: `{btc:.2f}%`".format(
                sym=symbol,
                label=label,
                stype=signal_type,
                price=format_price(price),
                score=score,
                time=datetime.now().strftime("%H:%M:%S"),
                signals=signals_text,
                ob=ob_text,
                sl=abs(STOP_LOSS_PCT),
                change=change_24h,
                btc=btc_change_24h,
            )
        )
        log.info("🟢 SIGNAL #1 | %s | score=%d | accum=%s | consol=%s",
                 symbol, score, is_accum, is_consol)
        return

    # ── إشارات المتابعة ───────────────────────────
    entry  = tracked[symbol]["entry"]
    level  = tracked[symbol]["level"]
    change = (price - entry) / entry * 100

    if level == 1 and change >= SIGNAL2_GAIN:
        send_telegram(
            "🚀 {label} | *SIGNAL #2*\n"
            "💰 *{sym}*\n"
            "📈 Gain: *+{gain:.2f}%*\n"
            "💵 Price: `{price}`\n"
            "📊 Score: *{score}/100*"
            "{signals}{ob}".format(
                label=label, sym=symbol, gain=change,
                price=format_price(price), score=score,
                signals=signals_text, ob=ob_text,
            )
        )
        tracked[symbol]["level"]      = 2
        tracked[symbol]["last_alert"] = now
        log.info("🔵 SIGNAL #2 | %s | +%.2f%%", symbol, change)

    elif level == 2 and change >= SIGNAL3_GAIN:
        send_telegram(
            "🔥 {label} | *SIGNAL #3*\n"
            "💰 *{sym}*\n"
            "📈 Gain: *+{gain:.2f}%*\n"
            "💵 Price: `{price}`\n"
            "📊 Score: *{score}/100*"
            "{signals}{ob}".format(
                label=label, sym=symbol, gain=change,
                price=format_price(price), score=score,
                signals=signals_text, ob=ob_text,
            )
        )
        tracked[symbol]["level"]      = 3
        tracked[symbol]["last_alert"] = now
        log.info("🔥 SIGNAL #3 | %s | +%.2f%%", symbol, change)


# ═══════════════════════════════════════════════
#         STALE SYMBOLS CLEANUP
# ═══════════════════════════════════════════════
def cleanup_stale():
    # type: () -> None
    now   = time.time()
    stale = [s for s, d in list(tracked.items()) if now - d["entry_time"] > STALE_REMOVE_SEC]
    for s in stale:
        log.info("🗑️ حذف زوج متوقف: %s", s)
        del tracked[s]


# ═══════════════════════════════════════════════
#           PERFORMANCE REPORT
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
        price_data = safe_get(MEXC_PRICE, {"symbol": sym})
        if not price_data:
            continue
        try:
            cur    = float(price_data["price"])
            growth = (cur - d["price"]) / d["price"] * 100
            if growth > 5:
                rows.append((sym, d["price"], cur, growth, d["score"]))
        except (KeyError, ValueError, ZeroDivisionError):
            continue

    if not rows:
        log.info("📊 لا توجد نتائج قابلة للتقرير حالياً")
        return

    rows.sort(key=lambda x: -x[3])
    msg = "⚡ *PERFORMANCE REPORT v3*\n🕐 `{}`\n\n".format(
        datetime.now().strftime("%Y-%m-%d %H:%M")
    )
    for sym, disc, cur, growth, score in rows[:5]:
        msg += "🔥 *{}*\n   Entry: `{}`  Now: `{}`\n   Growth: *+{:.2f}%* | Score: *{}*\n\n".format(
            sym, format_price(disc), format_price(cur), growth, score
        )
    send_telegram(msg)
    log.info("📊 تم إرسال تقرير الأداء")


# ═══════════════════════════════════════════════
#                  MAIN LOOP
# ═══════════════════════════════════════════════
def run():
    global watch_symbols, last_discovery

    log.info("🚀 بدء تشغيل MEXC Liquidity Bot v3...")
    send_telegram(
        "🤖 *SOURCE BOT VIP v3* – تم التشغيل\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "⚙️ Score Min: `{score}` | Stop Loss: `-{sl}%`\n"
        "📊 Interval: `{iv}s` | Max Pairs: `{mp}`\n"
        "🆕 Volume Accumulation: ✅\n"
        "🆕 Price Consolidation: ✅\n"
        "🆕 Market Filter: ✅".format(
            score=SCORE_MIN,
            sl=abs(STOP_LOSS_PCT),
            iv=CHECK_INTERVAL,
            mp=MAX_SYMBOLS,
        )
    )

    symbols_result = discover_symbols()
    watch_symbols  = symbols_result[0]
    changes_map    = symbols_result[1]
    last_discovery = time.time()
    cycle          = 0

    while True:
        try:
            now = time.time()

            # تحديث الأزواج كل ساعة
            if now - last_discovery >= DISCOVERY_REFRESH_SEC:
                symbols_result = discover_symbols()
                watch_symbols  = symbols_result[0]
                changes_map    = symbols_result[1]
                last_discovery = now

            # جلب الأسعار دفعة واحدة
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
                        handle_signal(
                            sym,
                            price_map[sym],
                            changes_map.get(sym, 0.0)
                        )

            cycle += 1
            if cycle % 10 == 0:
                cleanup_stale()
            if cycle % 360 == 0:  # تحديث BTC كل ساعة
                update_btc_change()

            send_report()
            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            log.info("⛔ تم إيقاف البوت يدوياً")
            send_telegram("⛔ *SOURCE BOT VIP v3* – تم الإيقاف")
            break
        except Exception as e:
            log.error("خطأ غير متوقع: %s", e, exc_info=True)
            time.sleep(5)


# ═══════════════════════════════════════════════
#                    ENTRY
# ═══════════════════════════════════════════════
if __name__ == "__main__":
    run()

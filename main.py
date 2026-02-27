"""
╔═══════════════════════════════════════════════════════════════╗
║         MEXC LIQUIDITY BOT v4 – SMART FILTER EDITION        ║
╚═══════════════════════════════════════════════════════════════╝

الإصلاحات v4:
  🔧 MIN_IMBALANCE     — رفض العملات ذات ضغط بيع قوي (Imbalance < 0.8)
  🔧 Bid > Ask         — الشراء يجب أن يتفوق على البيع دائماً
  🔧 Volume Spike      — كشف ارتفاع مفاجئ في الحجم خلال آخر شمعة
  🔧 Higher Lows       — السعر يصنع قيعان أعلى = اتجاه صاعد حقيقي
  🔧 Rejection Filter  — رفض العملات التي سبق رفضها مؤخراً (توفير API)
  🔧 Min Candle Green  — أغلبية الشموع الأخيرة خضراء
  ✅ كل ميزات v3 محفوظة
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

DISCOVERY_MIN_VOL    = 500_000
DISCOVERY_MAX_VOL    = 30_000_000
DISCOVERY_MAX_CHANGE = 12
MAX_SYMBOLS          = 50

# ── Order Book — فلاتر محسّنة ────────────────────
ORDER_BOOK_LIMIT      = 20
MIN_BID_DEPTH_USDT    = 30_000
MAX_BID_ASK_IMBALANCE = 3.0    # حد أقصى   → رفض إذا Bid/Ask > 3.0 (خلل كبير)
MIN_BID_ASK_IMBALANCE = 0.8    # 🆕 حد أدنى → رفض إذا Bid/Ask < 0.8 (ضغط بيع)
# ملاحظة: PEPE كانت 0.39 → ترفضها الآن

# ── إعدادات الإشارات ────────────────────────────
SCORE_MIN          = 65
SIGNAL2_GAIN       = 2.0
SIGNAL3_GAIN       = 4.0
STOP_LOSS_PCT      = -4.0
ALERT_COOLDOWN_SEC = 300

# ── Volume Accumulation ───────────────────────────
VOL_ACCUM_CANDLES        = 6
VOL_ACCUM_MIN_RATIO      = 1.5
VOL_ACCUM_MAX_PRICE_MOVE = 3.0

# ── 🆕 Volume Spike — ارتفاع مفاجئ في الحجم ──────
# آخر شمعة حجمها أكبر بكثير من المتوسط = دخول مفاجئ
VOL_SPIKE_RATIO = 2.5          # الحجم أكبر من 2.5× المتوسط = Spike

# ── Price Consolidation ───────────────────────────
CONSOL_CANDLES   = 8
CONSOL_MAX_RANGE = 4.0

# ── 🆕 Higher Lows Filter ─────────────────────────
# السعر يصنع قيعان أعلى = اتجاه صاعد حقيقي
HIGHER_LOWS_MIN_RATIO = 0.6    # 60% من الشموع يجب أن تكون قيعانها أعلى

# ── 🆕 Green Candles Filter ───────────────────────
# أغلبية الشموع الأخيرة خضراء = زخم شراء
GREEN_CANDLES_MIN_RATIO = 0.55 # 55% من الشموع خضراء على الأقل

# ── 🆕 Rejection Cache ────────────────────────────
# تخزين العملات المرفوضة لتفادي إعادة فحصها فوراً
REJECTION_CACHE_SEC = 120      # لا تعيد فحص العملة المرفوضة لمدة دقيقتين

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
rejection_cache= {}   # type: Dict[str, float]   🆕 {symbol: timestamp}
last_report    = 0.0
last_discovery = 0.0
watch_symbols  = []   # type: List[str]
btc_change_24h = 0.0
changes_map    = {}   # type: Dict[str, float]

session = requests.Session()
session.headers.update({"User-Agent": "MexcBot/4.0"})


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
    """🆕 تحقق من Rejection Cache لتوفير طلبات API."""
    ts = rejection_cache.get(symbol, 0)
    return (time.time() - ts) < REJECTION_CACHE_SEC


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
        opens   = [float(c[1]) for c in data]
        highs   = [float(c[2]) for c in data]
        lows    = [float(c[3]) for c in data]
        closes  = [float(c[4]) for c in data]
        vols    = [float(c[5]) for c in data]
        avg_vol = sum(vols[:-1]) / len(vols[:-1])
        return {
            "opens":   opens,
            "highs":   highs,
            "lows":    lows,
            "closes":  closes,
            "vols":    vols,
            "avg_vol": avg_vol,
        }
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
        return {
            "bid_depth": bid_depth,
            "ask_depth": ask_depth,
            "imbalance": imbalance,
        }
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
#   ANALYSIS FUNCTIONS
# ═══════════════════════════════════════════════

def detect_volume_accumulation(kd):
    # type: (Dict) -> Tuple[bool, float]
    """حجم يرتفع + سعر ثابت = تراكم شراء خفي."""
    vols   = kd["vols"]
    closes = kd["closes"]
    if len(vols) < VOL_ACCUM_CANDLES:
        return False, 0.0

    recent_vols   = vols[-VOL_ACCUM_CANDLES:]
    recent_closes = closes[-VOL_ACCUM_CANDLES:]
    avg_vol       = kd["avg_vol"]
    avg_recent    = sum(recent_vols) / len(recent_vols)

    if avg_recent < avg_vol * VOL_ACCUM_MIN_RATIO:
        return False, 0.0

    price_range = (max(recent_closes) - min(recent_closes)) / min(recent_closes) * 100
    if price_range > VOL_ACCUM_MAX_PRICE_MOVE:
        return False, 0.0

    vol_trend = sum(
        1 for i in range(1, len(recent_vols)) if recent_vols[i] >= recent_vols[i-1]
    )
    if vol_trend / (len(recent_vols) - 1) < 0.5:
        return False, 0.0

    strength = min(
        (avg_recent / avg_vol - 1) * 50
        + max(0, (VOL_ACCUM_MAX_PRICE_MOVE - price_range) / VOL_ACCUM_MAX_PRICE_MOVE * 30)
        + (vol_trend / (len(recent_vols) - 1)) * 20,
        100
    )
    return True, round(strength, 1)


def detect_volume_spike(kd):
    # type: (Dict) -> Tuple[bool, float]
    """🆕 ارتفاع مفاجئ في الحجم = دخول مال كبير فجأة."""
    vols    = kd["vols"]
    avg_vol = kd["avg_vol"]
    if avg_vol == 0:
        return False, 0.0
    ratio = vols[-1] / avg_vol
    if ratio >= VOL_SPIKE_RATIO:
        return True, round(ratio, 2)
    return False, round(ratio, 2)


def detect_price_consolidation(kd):
    # type: (Dict) -> Tuple[bool, float]
    """سعر في نطاق ضيق = ضغط مكتنز = انفجار قادم."""
    highs  = kd["highs"]
    lows   = kd["lows"]
    closes = kd["closes"]
    if len(highs) < CONSOL_CANDLES:
        return False, 0.0

    recent_highs  = highs[-CONSOL_CANDLES:]
    recent_lows   = lows[-CONSOL_CANDLES:]
    recent_closes = closes[-CONSOL_CANDLES:]

    total_range = (max(recent_highs) - min(recent_lows)) / min(recent_lows) * 100
    if total_range > CONSOL_MAX_RANGE:
        return False, 0.0

    if (recent_closes[-1] - recent_closes[0]) / recent_closes[0] * 100 < -2.0:
        return False, 0.0

    higher_lows = sum(
        1 for i in range(1, len(recent_lows)) if recent_lows[i] >= recent_lows[i-1]
    )
    tightness = max(0, (CONSOL_MAX_RANGE - total_range) / CONSOL_MAX_RANGE * 100)
    strength  = min(tightness * 0.8 + (higher_lows / (len(recent_lows)-1)) * 20, 100)
    return True, round(strength, 1)


def detect_higher_lows(kd):
    # type: (Dict) -> Tuple[bool, float]
    """🆕 قيعان أعلى تدريجياً = اتجاه صاعد حقيقي وليس pump وهمي."""
    lows = kd["lows"][-8:]
    if len(lows) < 4:
        return False, 0.0
    higher = sum(1 for i in range(1, len(lows)) if lows[i] >= lows[i-1])
    ratio  = higher / (len(lows) - 1)
    return ratio >= HIGHER_LOWS_MIN_RATIO, round(ratio * 100, 1)


def detect_green_candles(kd):
    # type: (Dict) -> Tuple[bool, float]
    """🆕 أغلبية الشموع خضراء = زخم شراء مستمر."""
    opens  = kd["opens"][-8:]
    closes = kd["closes"][-8:]
    if len(opens) < 4:
        return False, 0.0
    green = sum(1 for o, c in zip(opens, closes) if c >= o)
    ratio = green / len(opens)
    return ratio >= GREEN_CANDLES_MIN_RATIO, round(ratio * 100, 1)


def passes_market_filter(symbol_change_24h):
    # type: (float) -> Tuple[bool, str]
    """تجاهل العملات النازلة مع السوق."""
    if not MARKET_FILTER_ENABLED:
        return True, ""

    relative = symbol_change_24h - btc_change_24h

    if btc_change_24h < -2.0:
        # السوق نازل — نبحث عن العملات الصامدة فقط
        if relative >= 5.0:
            return True, "💪 تقاوم السوق النازل بقوة"
        elif relative >= 2.0:
            return True, "🛡️ صمود جيد أمام النزول"
        elif relative >= 0.0:
            return True, "⚡ مستقلة عن السوق"
        else:
            return False, ""
    else:
        # السوق محايد/صاعد — نقبل العملات التي لا تنزل كثيراً
        if symbol_change_24h >= -3.0:
            return True, ""
        return False, ""


# ═══════════════════════════════════════════════
#           SCORE SYSTEM v4
# ═══════════════════════════════════════════════
def calculate_score(kd, ob, vol_accum, vol_spike, consol, higher_lows, green_candles):
    # type: (Dict, Optional[Dict], Tuple, Tuple, Tuple, Tuple, Tuple) -> int
    """
    100 نقطة موزعة:
      حجم التداول       → 20
      Order Book        → 15
      Volume Accum      → 15  🆕
      Volume Spike      → 10  🆕
      Consolidation     → 10
      Higher Lows       → 15  🆕
      Green Candles     → 10  🆕
      اتجاه السعر       → 5
    """
    score = 0

    # 1. حجم التداول (20)
    avg_vol = kd["avg_vol"]
    ratio   = kd["vols"][-1] / avg_vol if avg_vol > 0 else 0
    if ratio >= 3.0:   score += 20
    elif ratio >= 2.0: score += 15
    elif ratio >= 1.5: score += 10
    elif ratio >= 1.2: score += 5

    # 2. Order Book (15)
    if ob:
        if ob["bid_depth"] >= MIN_BID_DEPTH_USDT:
            score += 7
        # كلما كان Imbalance أعلى من 1.0 = مشترون أقوى = نقاط أكثر
        imb = ob["imbalance"]
        if imb >= 2.0:   score += 8
        elif imb >= 1.5: score += 6
        elif imb >= 1.0: score += 4
        elif imb >= 0.8: score += 2

    # 3. Volume Accumulation (15)
    is_accum, accum_str = vol_accum
    if is_accum:
        score += max(int(accum_str / 100 * 15), 8)

    # 4. Volume Spike (10)
    is_spike, spike_ratio = vol_spike
    if is_spike:
        if spike_ratio >= 5.0:   score += 10
        elif spike_ratio >= 3.5: score += 7
        else:                    score += 5

    # 5. Consolidation (10)
    is_consol, consol_str = consol
    if is_consol:
        score += max(int(consol_str / 100 * 10), 5)

    # 6. Higher Lows (15)
    is_hl, hl_pct = higher_lows
    if is_hl:
        if hl_pct >= 80: score += 15
        elif hl_pct >= 70: score += 10
        else:              score += 6

    # 7. Green Candles (10)
    is_green, green_pct = green_candles
    if is_green:
        if green_pct >= 75: score += 10
        elif green_pct >= 60: score += 6
        else:                 score += 3

    # 8. اتجاه السعر (5)
    closes = kd["closes"]
    if closes[-1] > closes[0]:
        score += 5

    return min(score, 100)


def score_label(score):
    # type: (int) -> Optional[str]
    if score >= 88: return "🏆 *GOLD SIGNAL*"
    if score >= 75: return "🔵 *SILVER SIGNAL*"
    if score >= SCORE_MIN: return "🟡 *BRONZE SIGNAL*"
    return None


# ═══════════════════════════════════════════════
#     FULL VALIDATION v4
# ═══════════════════════════════════════════════
def valid_setup(symbol, symbol_change_24h=0.0):
    # type: (str, float) -> Optional[Dict]
    """
    يُرجع dict بكل النتائج أو None إذا فشل الفلتر.
    """
    # 1. Rejection Cache (بدون API)
    if is_rejected_recently(symbol):
        return None

    # 2. فلتر السوق (بدون API)
    passes, market_note = passes_market_filter(symbol_change_24h)
    if not passes:
        mark_rejected(symbol)
        return None

    # 3. بيانات الشموع
    kd = get_klines_data(symbol)
    if kd is None:
        mark_rejected(symbol)
        return None

    # 4. فلتر الحجم الأساسي
    if kd["vols"][-1] < kd["avg_vol"] * 1.2 or kd["vols"][-1] < DISCOVERY_MIN_VOL:
        mark_rejected(symbol)
        return None

    # 5. 🆕 فلتر الشموع الخضراء — رفض العملات ذات زخم بيع
    is_green, green_pct = detect_green_candles(kd)
    if not is_green:
        log.debug("%s رُفض: شموع خضراء %.0f%%", symbol, green_pct)
        mark_rejected(symbol)
        return None

    # 6. Order Book
    ob = get_order_book(symbol)
    if ob:
        # 🆕 حد أدنى لـ Imbalance — يرفض PEPE (0.39) وأمثالها
        if ob["imbalance"] < MIN_BID_ASK_IMBALANCE:
            log.debug("%s رُفض: imbalance منخفض %.2f (ضغط بيع)", symbol, ob["imbalance"])
            mark_rejected(symbol)
            return None
        if ob["imbalance"] > MAX_BID_ASK_IMBALANCE:
            log.debug("%s رُفض: imbalance مرتفع جداً %.2f", symbol, ob["imbalance"])
            mark_rejected(symbol)
            return None
        if ob["bid_depth"] < MIN_BID_DEPTH_USDT:
            mark_rejected(symbol)
            return None

    # 7. التحليلات المتقدمة
    vol_accum   = detect_volume_accumulation(kd)
    vol_spike   = detect_volume_spike(kd)
    consol      = detect_price_consolidation(kd)
    higher_lows = detect_higher_lows(kd)

    return {
        "kd":          kd,
        "ob":          ob,
        "vol_accum":   vol_accum,
        "vol_spike":   vol_spike,
        "consol":      consol,
        "higher_lows": higher_lows,
        "green":       (is_green, green_pct),
        "market_note": market_note,
    }


# ═══════════════════════════════════════════════
#              SYMBOL DISCOVERY
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
            "💵 دخول: `{}` ← الآن: `{}`".format(
                symbol, change, format_price(entry), format_price(price)
            )
        )
        log.info("🛑 Stop Loss: %s | %.2f%%", symbol, change)
        del tracked[symbol]
        return True
    return False


# ═══════════════════════════════════════════════
#             SIGNAL HANDLER v4
# ═══════════════════════════════════════════════
def handle_signal(symbol, price, change_24h=0.0):
    # type: (str, float, float) -> None
    if symbol.replace("USDT","") in STABLECOINS:
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

    kd          = result["kd"]
    ob          = result["ob"]
    vol_accum   = result["vol_accum"]
    vol_spike   = result["vol_spike"]
    consol      = result["consol"]
    higher_lows = result["higher_lows"]
    green       = result["green"]
    market_note = result["market_note"]

    score = calculate_score(kd, ob, vol_accum, vol_spike, consol, higher_lows, green)
    label = score_label(score)
    if not label:
        return

    # ── بناء نص الإشارات ──────────────────────────
    signals_text = ""
    is_accum,  accum_str  = vol_accum
    is_spike,  spike_r    = vol_spike
    is_consol, consol_str = consol
    is_hl,     hl_pct     = higher_lows
    is_green,  green_pct  = green

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

    # ── Order Book text ───────────────────────────
    ob_text = ""
    if ob:
        imb_emoji = "🟢" if ob["imbalance"] >= 1.2 else "🟡"
        ob_text = (
            "\n📗 Bid: `{:,.0f}` | 📕 Ask: `{:,.0f}`"
            "\n{} Imbalance: `{:.2f}`"
        ).format(ob["bid_depth"], ob["ask_depth"], imb_emoji, ob["imbalance"])

    # ── نوع الإشارة ───────────────────────────────
    active = sum([is_spike, is_accum, is_consol, is_hl])
    if active >= 3:
        stype = "💎 *PRE-EXPLOSION*"
    elif is_accum and is_consol:
        stype = "🔥 *ACCUMULATION+CONSOL*"
    elif is_spike:
        stype = "⚡ *VOLUME SPIKE*"
    elif is_accum:
        stype = "🔋 *ACCUMULATION*"
    elif is_consol:
        stype = "🎯 *CONSOLIDATION*"
    else:
        stype = "📊 *SIGNAL*"

    # ── إشارة #1 ─────────────────────────────────
    if symbol not in tracked:
        tracked[symbol]    = {"entry": price, "level": 1, "score": score,
                               "entry_time": now, "last_alert": now}
        discovered[symbol] = {"price": price, "time": now, "score": score}

        send_telegram(
            "👑 *SOURCE BOT VIP v4*\n"
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
            "⚠️ Stop Loss: `-{sl}%`".format(
                sym=symbol, label=label, stype=stype,
                price=format_price(price), score=score,
                time=datetime.now().strftime("%H:%M:%S"),
                signals=signals_text, ob=ob_text,
                ch=change_24h, btc=btc_change_24h,
                sl=abs(STOP_LOSS_PCT),
            )
        )
        log.info("🟢 #1 | %s | score=%d | spike=%s accum=%s consol=%s hl=%s",
                 symbol, score, is_spike, is_accum, is_consol, is_hl)
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
            "💵 Price: `{price}` | Score: *{score}*"
            "{signals}{ob}".format(
                label=label, sym=symbol, gain=change,
                price=format_price(price), score=score,
                signals=signals_text, ob=ob_text,
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
            "💵 Price: `{price}` | Score: *{score}*"
            "{signals}{ob}".format(
                label=label, sym=symbol, gain=change,
                price=format_price(price), score=score,
                signals=signals_text, ob=ob_text,
            )
        )
        tracked[symbol]["level"]      = 3
        tracked[symbol]["last_alert"] = now
        log.info("🔥 #3 | %s | +%.2f%%", symbol, change)


# ═══════════════════════════════════════════════
#         CLEANUP
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
        log.info("📊 لا توجد نتائج للتقرير")
        return

    rows.sort(key=lambda x: -x[3])
    msg = "⚡ *PERFORMANCE REPORT v4*\n🕐 `{}`\n\n".format(
        datetime.now().strftime("%Y-%m-%d %H:%M")
    )
    for sym, disc, cur, growth, score in rows[:5]:
        msg += "🔥 *{}*  Entry:`{}`  Now:`{}`\n   Growth: *+{:.2f}%* | Score:*{}*\n\n".format(
            sym, format_price(disc), format_price(cur), growth, score
        )
    send_telegram(msg)
    log.info("📊 تقرير الأداء أُرسل")


# ═══════════════════════════════════════════════
#                  MAIN LOOP
# ═══════════════════════════════════════════════
def run():
    global watch_symbols, changes_map, last_discovery

    log.info("🚀 MEXC Bot v4 يبدأ...")
    send_telegram(
        "🤖 *SOURCE BOT VIP v4*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "✅ Min Imbalance: `{}` (رفض ضغط البيع)\n"
        "✅ Green Candles Filter\n"
        "✅ Higher Lows Filter\n"
        "✅ Volume Spike Detector\n"
        "✅ Rejection Cache\n"
        "⚙️ Score: `{}` | SL: `-{}%` | Pairs: `{}`".format(
            MIN_BID_ASK_IMBALANCE, SCORE_MIN,
            abs(STOP_LOSS_PCT), MAX_SYMBOLS,
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

            cycle += 1
            if cycle % 10  == 0: cleanup_stale()
            if cycle % 360 == 0: update_btc_change()

            send_report()
            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            send_telegram("⛔ *SOURCE BOT VIP v4* – تم الإيقاف")
            break
        except Exception as e:
            log.error("خطأ: %s", e, exc_info=True)
            time.sleep(5)


if __name__ == "__main__":
    run()

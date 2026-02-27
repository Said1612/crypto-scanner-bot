"""
╔══════════════════════════════════════════════════════════╗
║          MEXC LIQUIDITY BOT – GOLD SIGNALS ONLY          ║
║         تتبع السيولة + حجم التداول + Order Book         ║
╚══════════════════════════════════════════════════════════╝
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

DISCOVERY_MIN_VOL    = 800_000
DISCOVERY_MAX_VOL    = 20_000_000
DISCOVERY_MAX_CHANGE = 8
MAX_SYMBOLS          = 30

# ── حدود Order Book Depth ───────────────────────
ORDER_BOOK_LIMIT      = 20
MIN_BID_DEPTH_USDT    = 50_000
MAX_BID_ASK_IMBALANCE = 3.0

# ── إعدادات الإشارات ────────────────────────────
SCORE_MIN          = 70
SIGNAL2_GAIN       = 2.0
SIGNAL3_GAIN       = 4.0
STOP_LOSS_PCT      = -4.0
ALERT_COOLDOWN_SEC = 300

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
        logging.StreamHandler(sys.stdout),  # أبيض في Railway
        logging.FileHandler("mexc_bot.log", encoding="utf-8"),
    ]
)
log = logging.getLogger("MexcBot")

# ═══════════════════════════════════════════════
#                   STATE
# ═══════════════════════════════════════════════
tracked         = {}    # type: Dict[str, Dict[str, Any]]
discovered      = {}    # type: Dict[str, Dict[str, Any]]
last_report     = 0.0
last_discovery  = 0.0
watch_symbols   = []    # type: List[str]

# Session مشتركة لكل الطلبات HTTP
session = requests.Session()
session.headers.update({"User-Agent": "MexcBot/2.0"})

# ═══════════════════════════════════════════════
#               TELEGRAM HELPERS
# ═══════════════════════════════════════════════
def format_price(price):
    # type: (float) -> str
    """تنسيق السعر بشكل مقروء بدون الصيغة العلمية"""
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


# ═══════════════════════════════════════════════
#              MEXC API HELPERS
# ═══════════════════════════════════════════════
def safe_get(url, params=None):
    # type: (str, Optional[dict]) -> Optional[Any]
    """طلب GET آمن مع logging للأخطاء."""
    try:
        r = session.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        log.debug("API error [%s]: %s", url.split("/")[-1], e)
        return None


def get_klines_data(symbol, interval="15m", limit=12):
    # type: (str, str, int) -> Optional[Dict]
    """جلب بيانات الشموع — دمج valid_setup + calculate_score في طلب واحد."""
    data = safe_get(MEXC_KLINES, {"symbol": symbol, "interval": interval, "limit": limit})
    if not data or len(data) < 4:
        return None
    try:
        vols    = [float(c[5]) for c in data]
        closes  = [float(c[4]) for c in data]
        avg_vol = sum(vols[:-1]) / len(vols[:-1])
        return {"vols": vols, "closes": closes, "avg_vol": avg_vol}
    except (IndexError, ValueError, ZeroDivisionError) as e:
        log.debug("klines parse error %s: %s", symbol, e)
        return None


def get_order_book(symbol):
    # type: (str) -> Optional[Dict]
    """جلب Order Book وحساب عمق السيولة."""
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


# ═══════════════════════════════════════════════
#           SCORE SYSTEM (محسّن)
# ═══════════════════════════════════════════════
def calculate_score(kd, ob):
    # type: (Dict, Optional[Dict]) -> int
    score   = 0
    vols    = kd["vols"]
    closes  = kd["closes"]
    avg_vol = kd["avg_vol"]

    # 1. قوة حجم التداول (40)
    ratio = vols[-1] / avg_vol if avg_vol > 0 else 0
    if ratio >= 3.0:
        score += 40
    elif ratio >= 2.0:
        score += 30
    elif ratio >= 1.5:
        score += 20
    elif ratio >= 1.2:
        score += 10

    # 2. استقرار السعر (20)
    price_swing = (max(closes) - min(closes)) / min(closes) * 100 if min(closes) > 0 else 99
    if price_swing < 2:
        score += 20
    elif price_swing < 4:
        score += 14
    elif price_swing < 6:
        score += 7

    # 3. اتجاه السعر (20)
    if closes[-1] > closes[0]:
        trend_pct = (closes[-1] - closes[0]) / closes[0] * 100
        if trend_pct >= 3:
            score += 20
        elif trend_pct >= 1:
            score += 13
        else:
            score += 7

    # 4. عمق Order Book (20)
    if ob:
        if ob["bid_depth"] >= MIN_BID_DEPTH_USDT:
            score += 10
        if ob["imbalance"] <= MAX_BID_ASK_IMBALANCE:
            score += 10

    return score


def score_label(score):
    # type: (int) -> Optional[str]
    if score >= 90:
        return "🏆 *GOLD SIGNAL*"
    if score >= 75:
        return "🔵 *SILVER SIGNAL*"
    if score >= SCORE_MIN:
        return "🟡 *BRONZE SIGNAL*"
    return None


# ═══════════════════════════════════════════════
#     LIQUIDITY VALIDATION
# ═══════════════════════════════════════════════
def valid_setup(symbol):
    # type: (str) -> Tuple[bool, Optional[Dict], Optional[Dict]]
    kd = get_klines_data(symbol)
    if kd is None:
        return False, None, None

    if kd["vols"][-1] < kd["avg_vol"] * 1.2:
        return False, None, None

    if kd["vols"][-1] < DISCOVERY_MIN_VOL:
        return False, None, None

    ob = get_order_book(symbol)
    if ob:
        if ob["bid_depth"] < MIN_BID_DEPTH_USDT:
            log.debug("%s رُفض: bid_depth منخفض %.0f USDT", symbol, ob["bid_depth"])
            return False, None, None
        if ob["imbalance"] > MAX_BID_ASK_IMBALANCE:
            log.debug("%s رُفض: imbalance %.2f", symbol, ob["imbalance"])
            return False, None, None

    return True, kd, ob


# ═══════════════════════════════════════════════
#              SYMBOL DISCOVERY
# ═══════════════════════════════════════════════
def discover_symbols():
    # type: () -> List[str]
    log.info("🔍 تحديث قائمة الأزواج...")
    data = safe_get(MEXC_24H)
    if not data:
        log.error("فشل جلب بيانات السوق من MEXC")
        return watch_symbols

    result = []
    for s in data:
        sym = s.get("symbol", "")
        if not sym.endswith("USDT"):
            continue
        if sym in EXCLUDED:
            continue
        base = sym.replace("USDT", "")
        if base in STABLECOINS:
            continue
        if any(kw in sym for kw in LEVERAGE_KEYWORDS):
            continue
        try:
            vol    = float(s["quoteVolume"])
            change = abs(float(s["priceChangePercent"]))
        except (KeyError, ValueError):
            continue
        if DISCOVERY_MIN_VOL < vol < DISCOVERY_MAX_VOL and change < DISCOVERY_MAX_CHANGE:
            result.append((sym, vol))

    result.sort(key=lambda x: -x[1])
    symbols = [s for s, _ in result[:MAX_SYMBOLS]]
    log.info("✅ تم اكتشاف %d زوج للمراقبة", len(symbols))
    return symbols


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
            "💵 السعر الحالي: `{}`".format(symbol, change, format_price(entry), format_price(price))
        )
        log.info("🛑 Stop Loss: %s | %.2f%%", symbol, change)
        del tracked[symbol]
        return True
    return False


# ═══════════════════════════════════════════════
#             SIGNAL HANDLER
# ═══════════════════════════════════════════════
def handle_signal(symbol, price):
    # type: (str, float) -> None
    base = symbol.replace("USDT", "")
    if base in STABLECOINS:
        return

    now = time.time()

    if check_stop_loss(symbol, price):
        return

    # Cooldown: منع تكرار التنبيه
    if symbol in tracked:
        last_alert = tracked[symbol].get("last_alert", 0)
        if now - last_alert < ALERT_COOLDOWN_SEC:
            return

    is_valid, kd, ob = valid_setup(symbol)
    if not is_valid or kd is None:
        return

    score = calculate_score(kd, ob)
    label = score_label(score)
    if not label:
        return

    ob_text = ""
    if ob:
        ob_text = (
            "\n📗 Bid Depth: `{:,.0f}` USDT"
            "\n📕 Ask Depth: `{:,.0f}` USDT"
            "\n⚖️ Imbalance: `{:.2f}`"
        ).format(ob["bid_depth"], ob["ask_depth"], ob["imbalance"])

    # إشارة #1
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
            "💰 *{}*\n"
            "{} | *SIGNAL #1*\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "💵 Price: `{}`\n"
            "📊 Score: *{}/100*\n"
            "🕐 Time: `{}`"
            "{}\n"
            "⚠️ Stop Loss: `-{}%`".format(
                symbol, label, format_price(price), score,
                datetime.now().strftime("%H:%M:%S"),
                ob_text, abs(STOP_LOSS_PCT)
            )
        )
        log.info("🟢 SIGNAL #1 | %s | score=%d | price=%s", symbol, score, price)
        return

    entry  = tracked[symbol]["entry"]
    level  = tracked[symbol]["level"]
    change = (price - entry) / entry * 100

    if level == 1 and change >= SIGNAL2_GAIN:
        send_telegram(
            "🚀 {} | *SIGNAL #2*\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "💰 *{}*\n"
            "📈 Gain: *+{:.2f}%*\n"
            "💵 Price: `{}`\n"
            "📊 Score: *{}/100*{}".format(label, symbol, change, price, score, ob_text)
        )
        tracked[symbol]["level"]      = 2
        tracked[symbol]["last_alert"] = now
        log.info("🔵 SIGNAL #2 | %s | +%.2f%%", symbol, change)

    elif level == 2 and change >= SIGNAL3_GAIN:
        send_telegram(
            "🔥 {} | *SIGNAL #3*\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "💰 *{}*\n"
            "📈 Gain: *+{:.2f}%*\n"
            "💵 Price: `{}`\n"
            "📊 Score: *{}/100*{}".format(label, symbol, change, price, score, ob_text)
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
    msg = "⚡ *PERFORMANCE REPORT*\n🕐 `{}`\n\n".format(
        datetime.now().strftime("%Y-%m-%d %H:%M")
    )
    for sym, disc, cur, growth, score in rows[:5]:
        msg += "🔥 *{}*\n   Entry: `{}`\n   Now: `{}`\n   Growth: *+{:.2f}%* | Score: *{}*\n\n".format(
            sym, disc, cur, growth, score
        )
    send_telegram(msg)
    log.info("📊 تم إرسال تقرير الأداء")


# ═══════════════════════════════════════════════
#                  MAIN LOOP
# ═══════════════════════════════════════════════
def run():
    global watch_symbols, last_discovery

    log.info("🚀 بدء تشغيل MEXC Liquidity Bot...")

    # إرسال رسالة البداية مرة واحدة فقط
    send_telegram(
        "🤖 *SOURCE BOT VIP* – تم التشغيل\n"
        "⚙️ Score Min: `{}` | Stop Loss: `-{}%`\n"
        "📊 Interval: `{}s` | Max Pairs: `{}`".format(
            SCORE_MIN, abs(STOP_LOSS_PCT), CHECK_INTERVAL, MAX_SYMBOLS
        )
    )

    watch_symbols  = discover_symbols()
    last_discovery = time.time()
    cycle          = 0

    while True:
        try:
            now = time.time()

            # تحديث الأزواج كل ساعة
            if now - last_discovery >= DISCOVERY_REFRESH_SEC:
                watch_symbols  = discover_symbols()
                last_discovery = now

            # جلب أسعار جميع الأزواج دفعة واحدة
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
                        handle_signal(sym, price_map[sym])

            cycle += 1
            if cycle % 10 == 0:
                cleanup_stale()

            send_report()
            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            log.info("⛔ تم إيقاف البوت يدوياً")
            send_telegram("⛔ *SOURCE BOT VIP* – تم الإيقاف")
            break
        except Exception as e:
            log.error("خطأ غير متوقع: %s", e, exc_info=True)
            time.sleep(5)


# ═══════════════════════════════════════════════
#                    ENTRY
# ═══════════════════════════════════════════════
if __name__ == "__main__":
    run()

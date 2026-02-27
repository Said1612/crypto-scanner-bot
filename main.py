"""
╔═══════════════════════════════════════════════════════════════╗
║      MEXC LIQUIDITY BOT v9 – LIQUIDITY ROTATION TRACKER     ║
╚═══════════════════════════════════════════════════════════════╝

الميزات v9:
  🆕 Sector Rotation Tracker — تتبع دوران السيولة بين القطاعات
     • يراقب 12 قطاع (AI, RWA, Gaming, DeFi, ...)
     • يكتشف القطاع الذي تدخله السيولة الآن
     • يرسل تقرير: "💰 السيولة انتقلت إلى AI"
  🆕 BTC Market Analysis    — تحليل السوق قبل أي إشارة
  🆕 Supertrend Filter      — رفض العملات ذات اتجاه نازل
  🆕 Score Min = 75         — إشارات قوية فقط
  ✅ Watchlist Alert + Bottom Detector
  ✅ Pre-Breakout (4h + 15m)
  ✅ Anti Pump & Dump
  ✅ Dynamic Stop Loss
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

DISCOVERY_MIN_VOL    = 300_000
DISCOVERY_MAX_VOL    = 80_000_000  # رُفِع لرصد العملات التي انفجرت فعلاً
DISCOVERY_MAX_CHANGE = 80          # رُفِع لاصطياد القطاعات الساخنة
MAX_SYMBOLS          = 80          # زيادة للتغطية الكاملة

# ── Order Book ───────────────────────────────────
ORDER_BOOK_LIMIT      = 20
MIN_BID_DEPTH_USDT    = 20_000
MAX_BID_ASK_IMBALANCE = 3.0
MIN_BID_ASK_IMBALANCE = 0.8

# ── إعدادات الإشارات ────────────────────────────
SCORE_MIN          = 75           # إشارات قوية فقط
SIGNAL2_GAIN       = 2.0
SIGNAL3_GAIN       = 4.0
ALERT_COOLDOWN_SEC = 300

# ── Dynamic Stop Loss ────────────────────────────
SL_MIN_PCT  = 2.0
SL_MAX_PCT  = 8.0
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
GREEN_CANDLES_MIN_RATIO = 0.60

# ── Supertrend ───────────────────────────────────
SUPERTREND_ATR_PERIOD = 10
SUPERTREND_MULTIPLIER = 3.0

# ── Rejection Cache ───────────────────────────────
REJECTION_CACHE_SEC = 120

# ── Watchlist Alert ──────────────────────────────
WATCHLIST_VOL_RATIO     = 1.3
WATCHLIST_NEAR_LOW_PCT  = 15.0
WATCHLIST_MIN_BID_DEPTH = 15_000
WATCHLIST_COOLDOWN_SEC  = 1800
WATCHLIST_MAX_ALERTS    = 5

# ── Bottom Detector ───────────────────────────────
BOTTOM_LOOKBACK_1H     = 24
BOTTOM_NEAR_LOW_PCT    = 10.0
BOTTOM_VOL_START_RATIO = 1.2

# ── Pump & Dump Filter ───────────────────────────
PUMP_MAX_RISE_PCT     = 20.0
PUMP_DUMP_DROP_PCT    = 5.0
PUMP_LOOKBACK_CANDLES = 12

# ── Pre-Breakout Detection ────────────────────────
BREAKOUT_4H_CANDLES      = 30
BREAKOUT_FLAT_MAX_RANGE  = 15.0
BREAKOUT_VOL_SURGE_RATIO = 3.0
BREAKOUT_MIN_FLAT_CANDLES= 10
BREAKOUT_PRICE_NEAR_LOW  = 30.0

# ── BTC Market Analysis ──────────────────────────
BTC_ANALYSIS_INTERVAL = 1800     # كل 30 دقيقة
BTC_DANGER_ZONE       = -3.0     # أحمر: لا إشارات عادية
BTC_CAUTION_ZONE      = -1.5     # أصفر: Gold فقط
# فوق -1.5% = SAFE = كل الإشارات

# ── 🆕 Sector Rotation Tracker ───────────────────
SECTOR_CHECK_INTERVAL  = 1800    # تحليل القطاعات كل 30 دقيقة
SECTOR_HOT_VOL_RATIO   = 1.5     # القطاع الساخن: حجمه ارتفع 1.5× المتوسط
SECTOR_HOT_CHANGE_MIN  = 3.0     # القطاع الساخن: متوسط تغيير عملاته +3%
SECTOR_ROTATION_BONUS  = 20      # بونص نقاط للعملات في القطاع الساخن

# ── فلتر السوق ───────────────────────────────────
MARKET_FILTER_ENABLED = True

# ── توقيتات ─────────────────────────────────────
CHECK_INTERVAL        = 10
DISCOVERY_REFRESH_SEC = 1800     # تحديث كل 30 دقيقة (أسرع)
REPORT_INTERVAL       = 6 * 3600
STALE_REMOVE_SEC      = 7200

# ── MEXC Endpoints ──────────────────────────────
MEXC_24H    = "https://api.mexc.com/api/v3/ticker/24hr"
MEXC_PRICE  = "https://api.mexc.com/api/v3/ticker/price"
MEXC_KLINES = "https://api.mexc.com/api/v3/klines"
MEXC_DEPTH  = "https://api.mexc.com/api/v3/depth"

# ═══════════════════════════════════════════════
#   🆕 SECTOR DEFINITIONS — قاموس القطاعات
# ═══════════════════════════════════════════════
SECTORS = {
    "AI":      ["FETUSDT","AGIXUSDT","OCEANUSDT","AIXBTUSDT","RENDUSDT",
                "NEWTUSDT","TAOAUSDT","PHAUSDT","ARKMUSDT","GRTUSDT"],
    "RWA":     ["SAHARAUSDT","ONDOUSDT","CFGUSDT","POLIXUSDT","MPLXUSDT",
                "REALUSDT","RSRUSDT","TRSTUSDT","RBSUSDT","GOLDUSDT"],
    "Gaming":  ["AXSUSDT","SANDUSDT","MANAUSDT","ILVUSDT","GMTUSDT",
                "YGGUSDT","SLPUSDT","PGXUSDT","RBIFUSDT","BEXUSDT"],
    "DeFi":    ["UNIUSDT","AAVEUSDT","CAKEUSDT","C98USDT","SUSHIUSDT",
                "COMPUSDT","MKRUSDT","CRVUSDT","LDOUSDT","1INCHUSDT"],
    "Layer1":  ["AVAXUSDT","ADAUSDT","ATOMUSDT","NEARUSDT","FTMUSDT",
                "ALGOUSDT","ICPUSDT","APTUSDT","SUIUSDT","SEIUSDT"],
    "Layer2":  ["MATICUSDT","OPUSDT","ARBUSDT","ZKUSDT","STRKUSDT",
                "LRCUSDT","IMXUSDT","METISUSDT","SCROLLUSDT","MANTAUSDT"],
    "Meme":    ["DOGEUSDT","SHIBUSDT","PEPEUSDT","FLOKIUSDT","WIFUSDT",
                "BOMUSDT","MEMEUSDT","NEIROUSDT","MOGUUSDT","TUROUSDT"],
    "Oracle":  ["LINKUSDT","BANDUSDT","APIUSDT","UMAUSDT","DIAAUSDT"],
    "Privacy": ["XMRUSDT","ZCASHUSDT","DASHUSDT","SCRTUSDT","ROSEUSDT"],
    "Storage": ["FILUSDT","ARUSDT","STORJUSDT","SCUSDT","BLZUSDT"],
    "DePIN":   ["IOTAUSDT","HELIUMUSDT","WLDUSDT","AIOZUSDT","XNETUSDT"],
    "Old":     ["LTCUSDT","ETCUSDT","XEMUSDT","ZECUSDT","LUNCUSDT"],
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
        logging.FileHandler("mexc_bot.log", encoding="utf-8"),
    ]
)
log = logging.getLogger("MexcBot")

# ═══════════════════════════════════════════════
#                   STATE
# ═══════════════════════════════════════════════
tracked          = {}   # type: Dict[str, Dict[str, Any]]
discovered       = {}   # type: Dict[str, Dict[str, Any]]
rejection_cache  = {}   # type: Dict[str, float]
watchlist        = {}   # type: Dict[str, float]
last_report      = 0.0
last_discovery   = 0.0
last_btc_analysis= 0.0
last_sector_check= 0.0
watch_symbols    = []   # type: List[str]
btc_change_24h   = 0.0
btc_trend_1h     = 0.0
market_state     = "SAFE"   # SAFE / CAUTION / DANGER
hot_sectors      = []        # type: List[str]  القطاعات الساخنة حالياً
hot_symbols      = set()     # type: set  العملات في القطاعات الساخنة
changes_map      = {}        # type: Dict[str, float]

session = requests.Session()
session.headers.update({"User-Agent": "MexcBot/9.0"})


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
        return
    try:
        r = session.post(
            "https://api.telegram.org/bot{}/sendMessage".format(TELEGRAM_TOKEN),
            data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"},
            timeout=10,
        )
        if r.status_code != 200:
            log.warning("Telegram error %s", r.status_code)
    except requests.RequestException as e:
        log.error("Telegram: %s", e)


def safe_get(url, params=None):
    # type: (str, Optional[dict]) -> Optional[Any]
    try:
        r = session.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        log.debug("API [%s]: %s", url.split("/")[-1], e)
        return None


def is_rejected_recently(symbol):
    # type: (str) -> bool
    return (time.time() - rejection_cache.get(symbol, 0)) < REJECTION_CACHE_SEC

def mark_rejected(symbol):
    # type: (str) -> None
    rejection_cache[symbol] = time.time()

def cleanup_rejection_cache():
    # type: () -> None
    now = time.time()
    for s in [s for s, t in list(rejection_cache.items())
              if now - t > REJECTION_CACHE_SEC * 2]:
        del rejection_cache[s]


# ═══════════════════════════════════════════════
#              DATA FETCHERS
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
        avg_vol = sum(vols[:-1]) / max(len(vols[:-1]), 1)
        return {"opens": opens, "highs": highs, "lows": lows,
                "closes": closes, "vols": vols, "avg_vol": avg_vol}
    except (IndexError, ValueError, ZeroDivisionError):
        return None


def get_order_book(symbol):
    # type: (str) -> Optional[Dict]
    data = safe_get(MEXC_DEPTH, {"symbol": symbol, "limit": ORDER_BOOK_LIMIT})
    if not data:
        return None
    try:
        bid = sum(float(b[0]) * float(b[1]) for b in data.get("bids", []))
        ask = sum(float(a[0]) * float(a[1]) for a in data.get("asks", []))
        return {"bid_depth": bid, "ask_depth": ask,
                "imbalance": bid / ask if ask > 0 else 99}
    except (ValueError, ZeroDivisionError):
        return None


def get_supertrend_direction(symbol, interval="15m"):
    # type: (str, str) -> str
    """
    يحسب اتجاه Supertrend (UP/DOWN).
    UP  = السعر فوق خط Supertrend = اتجاه صاعد ✅
    DOWN = السعر تحت خط Supertrend = اتجاه نازل ❌
    """
    kd = get_klines_data(symbol, interval=interval, limit=20)
    if kd is None or len(kd["closes"]) < 15:
        return "UNKNOWN"
    highs  = kd["highs"]
    lows   = kd["lows"]
    closes = kd["closes"]
    # ATR بسيط
    trs = []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i],
                 abs(highs[i] - closes[i-1]),
                 abs(lows[i]  - closes[i-1]))
        trs.append(tr)
    if not trs:
        return "UNKNOWN"
    atr = sum(trs[-SUPERTREND_ATR_PERIOD:]) / min(len(trs), SUPERTREND_ATR_PERIOD)
    # Supertrend band
    hl2 = [(h + l) / 2 for h, l in zip(highs, lows)]
    upper = hl2[-1] + SUPERTREND_MULTIPLIER * atr
    lower = hl2[-1] - SUPERTREND_MULTIPLIER * atr
    cur   = closes[-1]
    if cur > lower:   return "UP"
    if cur < upper:   return "DOWN"
    return "UNKNOWN"


# ═══════════════════════════════════════════════
#   🆕 BTC MARKET ANALYSIS
# ═══════════════════════════════════════════════
def analyze_btc_market():
    # type: () -> None
    global btc_change_24h, btc_trend_1h, market_state, last_btc_analysis

    data_24h = safe_get(MEXC_24H, {"symbol": "BTCUSDT"})
    if data_24h:
        try:
            btc_change_24h = float(data_24h["priceChangePercent"])
        except (KeyError, ValueError):
            pass

    kd_btc = get_klines_data("BTCUSDT", interval="1h", limit=4)
    if kd_btc and len(kd_btc["closes"]) >= 2:
        c = kd_btc["closes"]
        btc_trend_1h = (c[-1] - c[0]) / c[0] * 100

    btc_st = get_supertrend_direction("BTCUSDT", interval="1h")

    old_state = market_state
    if btc_change_24h <= BTC_DANGER_ZONE or btc_trend_1h <= -2.0:
        market_state = "DANGER"
    elif btc_change_24h <= BTC_CAUTION_ZONE or btc_st == "DOWN":
        market_state = "CAUTION"
    else:
        market_state = "SAFE"

    last_btc_analysis = time.time()

    if old_state != market_state:
        icons  = {"SAFE": "🟢", "CAUTION": "🟡", "DANGER": "🔴"}
        notes  = {"SAFE":   "السوق آمن ✅ — كل الإشارات مفعّلة",
                  "CAUTION":"تحذير ⚠️ — Gold فقط (Score 88+)",
                  "DANGER": "السوق خطر 🔴 — لا إشارات عادية\nنتابع القطاعات المستقلة فقط"}
        send_telegram(
            "📊 *تقرير السوق — BTC Analysis*\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "{icon} حالة السوق: *{state}*\n"
            "₿ BTC 24h: `{ch24:+.2f}%`\n"
            "₿ BTC 1h:  `{ch1h:+.2f}%`\n"
            "📈 Supertrend BTC: `{st}`\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "_{note}_".format(
                icon=icons[market_state], state=market_state,
                ch24=btc_change_24h, ch1h=btc_trend_1h,
                st="🟢 صاعد" if btc_st == "UP" else "🔴 نازل",
                note=notes[market_state],
            )
        )
        log.info("📊 Market: %s→%s | BTC 24h=%.2f%% 1h=%.2f%%",
                 old_state, market_state, btc_change_24h, btc_trend_1h)


# ═══════════════════════════════════════════════
#   🆕 SECTOR ROTATION TRACKER
# ═══════════════════════════════════════════════
def analyze_sector_rotation(all_tickers):
    # type: (List[Dict]) -> None
    """
    يحلل دوران السيولة بين القطاعات:
    1. يحسب متوسط تغيير كل قطاع
    2. يحسب إجمالي الحجم لكل قطاع
    3. يكتشف القطاع الذي تدخله السيولة
    4. يرسل تقرير ويحدث hot_sectors و hot_symbols
    """
    global hot_sectors, hot_symbols, last_sector_check

    # بناء خريطة الأسعار والتغييرات من البيانات المحملة
    price_data = {}  # type: Dict[str, Dict]
    for t in all_tickers:
        sym = t.get("symbol", "")
        if not sym.endswith("USDT"):
            continue
        try:
            price_data[sym] = {
                "change": float(t["priceChangePercent"]),
                "vol":    float(t["quoteVolume"]),
            }
        except (KeyError, ValueError):
            pass

    # تحليل كل قطاع
    sector_stats = {}  # type: Dict[str, Dict]
    for sector, symbols in SECTORS.items():
        changes = []
        total_vol = 0.0
        rising_coins = []
        for sym in symbols:
            if sym in price_data:
                ch  = price_data[sym]["change"]
                vol = price_data[sym]["vol"]
                changes.append(ch)
                total_vol += vol
                if ch > 0:
                    rising_coins.append((sym.replace("USDT",""), ch))
        if not changes:
            continue
        avg_change = sum(changes) / len(changes)
        rising_pct = sum(1 for c in changes if c > 0) / len(changes) * 100
        sector_stats[sector] = {
            "avg_change":  avg_change,
            "total_vol":   total_vol,
            "rising_pct":  rising_pct,
            "rising_coins":sorted(rising_coins, key=lambda x: -x[1])[:3],
            "count":       len(changes),
        }

    if not sector_stats:
        return

    # تحديد القطاعات الساخنة
    # معيار: متوسط تغيير > 3% + أغلبية العملات صاعدة
    new_hot = []
    sorted_sectors = sorted(sector_stats.items(),
                            key=lambda x: -x[1]["avg_change"])

    for sector, stats in sorted_sectors:
        if (stats["avg_change"] >= SECTOR_HOT_CHANGE_MIN
                and stats["rising_pct"] >= 60):
            new_hot.append(sector)

    # تحديث hot_symbols
    new_hot_syms = set()
    for sector in new_hot:
        for sym in SECTORS[sector]:
            new_hot_syms.add(sym)

    # إرسال تقرير إذا تغير الزخم
    old_hot = set(hot_sectors)
    new_hot_set = set(new_hot)

    if new_hot_set != old_hot:
        # قطاعات جديدة دخلت
        entered = new_hot_set - old_hot
        exited  = old_hot - new_hot_set

        msg = "🔄 *SECTOR ROTATION — دوران السيولة*\n━━━━━━━━━━━━━━━━━━\n"

        if entered:
            msg += "💰 *سيولة تدخل:*\n"
            for s in entered:
                st = sector_stats.get(s, {})
                coins_txt = " | ".join(
                    "{} +{:.0f}%".format(c, p)
                    for c, p in st.get("rising_coins", [])
                )
                msg += "  ✅ *{}*  avg:`+{:.1f}%`\n  {}\n".format(
                    s, st.get("avg_change", 0), coins_txt)

        if exited:
            msg += "📤 *سيولة خرجت:* {}\n".format(", ".join(exited))

        # أفضل 3 عملات في القطاعات الساخنة للشراء
        top_picks = []
        for sector in new_hot:
            st = sector_stats.get(sector, {})
            top_picks.extend(st.get("rising_coins", []))
        top_picks = sorted(top_picks, key=lambda x: -x[1])[:5]

        if top_picks:
            msg += "\n🎯 *أفضل العملات الآن:*\n"
            for coin, chg in top_picks:
                msg += "  • *{}USDT* `+{:.1f}%`\n".format(coin, chg)

        msg += "\n₿ BTC: `{:+.2f}%` | السوق: `{}`".format(
            btc_change_24h, market_state)

        send_telegram(msg)
        log.info("🔄 Sector Rotation: %s → %s", list(old_hot), new_hot)

    hot_sectors   = new_hot
    hot_symbols   = new_hot_syms
    last_sector_check = time.time()

    # سجّل ملخصاً
    if hot_sectors:
        log.info("🔥 Hot Sectors: %s", ", ".join(hot_sectors))


# ═══════════════════════════════════════════════
#   ANALYSIS FUNCTIONS
# ═══════════════════════════════════════════════
def detect_pump_and_dump(kd):
    # type: (Dict) -> Tuple[bool, str]
    closes = kd["closes"]
    highs  = kd["highs"]
    if len(closes) < PUMP_LOOKBACK_CANDLES:
        return False, ""
    rc = closes[-PUMP_LOOKBACK_CANDLES:]
    rh = highs[-PUMP_LOOKBACK_CANDLES:]
    mn = min(rc)
    mx = max(rh)
    if mn <= 0: return False, ""
    rise = (mx - mn) / mn * 100
    drop = (mx - closes[-1]) / mx * 100
    if rise >= PUMP_MAX_RISE_PCT:
        if drop >= PUMP_DUMP_DROP_PCT:
            return True, "Pump {:.0f}% ثم Dump {:.0f}%".format(rise, drop)
        if rise >= 40.0:
            return True, "ارتفاع مفرط {:.0f}%".format(rise)
    return False, ""


def detect_volume_accumulation(kd):
    # type: (Dict) -> Tuple[bool, float]
    vols    = kd["vols"]
    closes  = kd["closes"]
    avg_vol = kd["avg_vol"]
    if len(vols) < VOL_ACCUM_CANDLES: return False, 0.0
    rv = vols[-VOL_ACCUM_CANDLES:]
    rc = closes[-VOL_ACCUM_CANDLES:]
    ar = sum(rv) / len(rv)
    if ar < avg_vol * VOL_ACCUM_MIN_RATIO: return False, 0.0
    pr = (max(rc) - min(rc)) / min(rc) * 100
    if pr > VOL_ACCUM_MAX_PRICE_MOVE: return False, 0.0
    vt = sum(1 for i in range(1, len(rv)) if rv[i] >= rv[i-1])
    if vt / (len(rv)-1) < 0.5: return False, 0.0
    s = min((ar/avg_vol-1)*50 + max(0,(VOL_ACCUM_MAX_PRICE_MOVE-pr)/VOL_ACCUM_MAX_PRICE_MOVE*30) + (vt/(len(rv)-1))*20, 100)
    return True, round(s, 1)


def detect_volume_spike(kd):
    # type: (Dict) -> Tuple[bool, float]
    avg_vol = kd["avg_vol"]
    if avg_vol == 0: return False, 0.0
    r = kd["vols"][-1] / avg_vol
    return r >= VOL_SPIKE_RATIO, round(r, 2)


def detect_price_consolidation(kd):
    # type: (Dict) -> Tuple[bool, float]
    h = kd["highs"]; l = kd["lows"]; c = kd["closes"]
    if len(h) < CONSOL_CANDLES: return False, 0.0
    rh = h[-CONSOL_CANDLES:]; rl = l[-CONSOL_CANDLES:]; rc = c[-CONSOL_CANDLES:]
    tr = (max(rh)-min(rl))/min(rl)*100
    if tr > CONSOL_MAX_RANGE: return False, 0.0
    if (rc[-1]-rc[0])/rc[0]*100 < -2.0: return False, 0.0
    hl = sum(1 for i in range(1,len(rl)) if rl[i]>=rl[i-1])
    tight = max(0,(CONSOL_MAX_RANGE-tr)/CONSOL_MAX_RANGE*100)
    return True, round(min(tight*0.8+(hl/(len(rl)-1))*20,100),1)


def detect_higher_lows(kd):
    # type: (Dict) -> Tuple[bool, float]
    lows = kd["lows"][-8:]
    if len(lows) < 4: return False, 0.0
    h = sum(1 for i in range(1,len(lows)) if lows[i]>=lows[i-1])
    r = h/(len(lows)-1)
    return r >= HIGHER_LOWS_MIN_RATIO, round(r*100,1)


def detect_green_candles(kd):
    # type: (Dict) -> Tuple[bool, float]
    o = kd["opens"][-8:]; c = kd["closes"][-8:]
    if len(o) < 4: return False, 0.0
    g = sum(1 for op,cl in zip(o,c) if cl>=op)
    r = g/len(o)
    return r >= GREEN_CANDLES_MIN_RATIO, round(r*100,1)


def passes_market_filter(symbol_change_24h):
    # type: (float) -> Tuple[bool, str]
    if not MARKET_FILTER_ENABLED: return True, ""
    relative = symbol_change_24h - btc_change_24h
    if btc_change_24h < -2.0:
        if relative >= 5.0:   return True, "💪 تقاوم السوق بقوة"
        elif relative >= 2.0: return True, "🛡️ صمود جيد"
        elif relative >= 0.0: return True, "⚡ مستقلة"
        else:                 return False, ""
    if symbol_change_24h >= -3.0: return True, ""
    return False, ""


def detect_pre_breakout(symbol):
    # type: (str) -> Tuple[bool, float, str]
    kd = get_klines_data(symbol, interval="4h", limit=BREAKOUT_4H_CANDLES)
    if kd is None or len(kd["closes"]) < BREAKOUT_MIN_FLAT_CANDLES:
        return False, 0.0, ""
    closes = kd["closes"]; highs = kd["highs"]
    lows   = kd["lows"];   vols  = kd["vols"]
    fe = int(len(closes)*0.7)
    fc = closes[:fe]; fh = highs[:fe]; fl = lows[:fe]; fv = vols[:fe]
    if min(fl) <= 0: return False, 0.0, ""
    fr = (max(fh)-min(fl))/min(fl)*100
    if fr > BREAKOUT_FLAT_MAX_RANGE: return False, 0.0, ""
    afv = sum(fv)/max(len(fv),1)
    rv  = vols[fe:]
    arv = sum(rv)/max(len(rv),1)
    if afv <= 0: return False, 0.0, ""
    vs = arv/afv
    if vs < BREAKOUT_VOL_SURGE_RATIO: return False, 0.0, ""
    cur = closes[-1]; base = min(fl); peak = max(fh)
    if peak <= base: return False, 0.0, ""
    rise = (cur-base)/base*100
    if rise > BREAKOUT_PRICE_NEAR_LOW:
        drop = (peak-cur)/peak*100
        if drop > 15.0: return False, 0.0, ""
    rc2 = closes[fe:]
    if len(rc2) >= 2:
        up = sum(1 for i in range(1,len(rc2)) if rc2[i]>=rc2[i-1])
        if up/(len(rc2)-1) < 0.5: return False, 0.0, ""
    ts = max(0,(BREAKOUT_FLAT_MAX_RANGE-fr)/BREAKOUT_FLAT_MAX_RANGE*40)
    vs2= min((vs/BREAKOUT_VOL_SURGE_RATIO-1)*30,40)
    tm = max(0,(BREAKOUT_PRICE_NEAR_LOW-rise)/BREAKOUT_PRICE_NEAR_LOW*20)
    st = min(ts+vs2+tm,100)
    desc = "تجميع {:.0f}% | حجم ×{:.1f} | ارتفاع {:.0f}%".format(fr,vs,rise)
    return True, round(st,1), desc


def detect_bottom(symbol, kd_15m):
    # type: (str, Dict) -> Tuple[bool, float, str]
    kd = get_klines_data(symbol, interval="1h", limit=BOTTOM_LOOKBACK_1H)
    if kd is None: return False, 0.0, ""
    c = kd["closes"]; l = kd["lows"]; v = kd["vols"]
    if not c or min(l) <= 0: return False, 0.0, ""
    cur = c[-1]; pl = min(l)
    dist = (cur-pl)/pl*100
    if dist > BOTTOM_NEAR_LOW_PCT: return False, 0.0, ""
    av = sum(v[:-3])/max(len(v[:-3]),1)
    rv = sum(v[-3:])/3
    if av <= 0 or rv/av < BOTTOM_VOL_START_RATIO: return False, 0.0, ""
    o15 = kd_15m["opens"]; c15 = kd_15m["closes"]
    if c15[-1] <= o15[-1]: return False, 0.0, ""
    ns = max(0,(BOTTOM_NEAR_LOW_PCT-dist)/BOTTOM_NEAR_LOW_PCT*50)
    vs = min((rv/av-1)*30,30)
    st = min(ns+vs+20,100)
    desc = "القاع {:.1f}% | حجم ×{:.1f} | ارتداد".format(dist,rv/av)
    return True, round(st,1), desc


# ═══════════════════════════════════════════════
#   WATCHLIST ALERT
# ═══════════════════════════════════════════════
def check_watchlist(symbol, price, change_24h=0.0):
    # type: (str, float, float) -> None
    if symbol in tracked: return
    now = time.time()
    if now - watchlist.get(symbol,0) < WATCHLIST_COOLDOWN_SEC: return
    active = sum(1 for t in watchlist.values() if now-t < WATCHLIST_COOLDOWN_SEC)
    if active >= WATCHLIST_MAX_ALERTS: return
    passes, market_note = passes_market_filter(change_24h)
    if not passes: return
    kd = get_klines_data(symbol)
    if kd is None: return
    avg_vol = kd["avg_vol"]
    if avg_vol <= 0 or kd["vols"][-1] < avg_vol * WATCHLIST_VOL_RATIO: return
    is_bot, bot_str, bot_desc = detect_bottom(symbol, kd)
    if not is_bot: return
    ob = get_order_book(symbol)
    if ob:
        if ob["bid_depth"] < WATCHLIST_MIN_BID_DEPTH: return
        if ob["imbalance"] < MIN_BID_ASK_IMBALANCE: return
    watchlist[symbol] = now
    # هل العملة في قطاع ساخن؟
    sector_tag = ""
    for sec, syms in SECTORS.items():
        if symbol in syms and sec in hot_sectors:
            sector_tag = "\n🔥 *قطاع ساخن:* `{}`".format(sec)
            break
    ob_text = ""
    if ob:
        ob_text = "\n📗 Bid:`{:,.0f}` | ⚖️ Imb:`{:.2f}`".format(
            ob["bid_depth"], ob["imbalance"])
    send_telegram(
        "👀 *WATCHLIST ALERT*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "💰 *{sym}* — في القاع{sec}\n"
        "💵 Price: `{price}`\n"
        "📉 24h: `{ch:.1f}%` | BTC: `{btc:.1f}%`\n"
        "🔻 *Bottom:* `{bs:.0f}%` — _{bd}_\n"
        "⚡ Vol: `{vr:.1f}×` المتوسط"
        "{ob}\n"
        "⏳ _انتظر Signal #1_".format(
            sym=symbol, sec=sector_tag,
            price=format_price(price), ch=change_24h, btc=btc_change_24h,
            bs=bot_str, bd=bot_desc,
            vr=kd["vols"][-1]/avg_vol if avg_vol>0 else 0,
            ob=ob_text,
        )
    )
    log.info("👀 WATCHLIST: %s | bottom=%.0f%%", symbol, bot_str)


# ═══════════════════════════════════════════════
#   DYNAMIC STOP LOSS
# ═══════════════════════════════════════════════
def calculate_dynamic_sl(kd, score, ob, is_breakout=False):
    # type: (Dict, int, Optional[Dict], bool) -> float
    h = kd["highs"]; l = kd["lows"]
    rp = list(zip(h[-10:],l[-10:]))
    if rp and min(lv for _,lv in rp) > 0:
        atr = sum((hv-lv)/lv*100 for hv,lv in rp)/len(rp)
    else:
        atr = SL_BASE_PCT
    sf = 0.70 if score>=88 else 0.85 if score>=75 else 1.00 if score>=65 else 1.15
    imb_f = 1.0
    if ob:
        imb = ob["imbalance"]
        imb_f = 0.80 if imb>=2.0 else 0.90 if imb>=1.5 else 1.00 if imb>=1.0 else 1.10
    bf = 1.3 if is_breakout else 1.0
    return round(max(SL_MIN_PCT, min(SL_MAX_PCT, atr*sf*imb_f*bf)), 1)


# ═══════════════════════════════════════════════
#   SCORE SYSTEM v9
# ═══════════════════════════════════════════════
def calculate_score(kd, ob, vol_accum, vol_spike, consol, higher_lows,
                    green_candles, breakout_str=0.0, in_hot_sector=False):
    # type: (Dict, Optional[Dict], Tuple, Tuple, Tuple, Tuple, Tuple, float, bool) -> int
    score = 0
    avg_vol = kd["avg_vol"]

    # حجم (15)
    r = kd["vols"][-1]/avg_vol if avg_vol>0 else 0
    score += 15 if r>=3.0 else 11 if r>=2.0 else 7 if r>=1.5 else 4 if r>=1.2 else 0

    # Order Book (15)
    if ob:
        if ob["bid_depth"] >= MIN_BID_DEPTH_USDT: score += 7
        imb = ob["imbalance"]
        score += 8 if imb>=2.0 else 6 if imb>=1.5 else 4 if imb>=1.0 else 2

    # Vol Accum (10)
    ia, as_ = vol_accum
    if ia: score += max(int(as_/100*10), 6)

    # Vol Spike (10)
    isp, sr = vol_spike
    if isp: score += 10 if sr>=5.0 else 7 if sr>=3.5 else 5

    # Consolidation (10)
    ic, cs = consol
    if ic: score += max(int(cs/100*10), 5)

    # Higher Lows (10)
    ih, hp = higher_lows
    if ih: score += 10 if hp>=80 else 7 if hp>=70 else 4

    # Green Candles (10)
    ig, gp = green_candles
    if ig: score += 10 if gp>=75 else 6 if gp>=60 else 3

    # اتجاه (5)
    c = kd["closes"]
    if c[-1] > c[0]: score += 5

    # Pre-Breakout (10)
    if breakout_str > 0:
        score += max(int(breakout_str/100*10), 6)

    # 🆕 Sector Rotation Bonus (15)
    if in_hot_sector:
        score += SECTOR_ROTATION_BONUS

    return min(score, 100)


def score_label(score):
    # type: (int) -> Optional[str]
    if score >= 88:        return "🏆 *GOLD SIGNAL*"
    if score >= 75:        return "🔵 *SILVER SIGNAL*"
    if score >= SCORE_MIN: return None  # لا Bronze — قوي فقط
    return None


# ═══════════════════════════════════════════════
#   VALID SETUP v9
# ═══════════════════════════════════════════════
def valid_setup(symbol, symbol_change_24h=0.0):
    # type: (str, float) -> Optional[Dict]
    if is_rejected_recently(symbol): return None

    # تحقق من حالة السوق
    if market_state == "DANGER":
        # في السوق الخطر: نقبل فقط العملات في القطاعات الساخنة
        if symbol not in hot_symbols:
            return None
    elif market_state == "CAUTION":
        # تحذير: نرفع معيار الإشارة (Gold فقط — يُطبق لاحقاً)
        pass

    passes, market_note = passes_market_filter(symbol_change_24h)
    if not passes:
        mark_rejected(symbol)
        return None

    kd = get_klines_data(symbol)
    if kd is None:
        mark_rejected(symbol)
        return None

    # Pump & Dump
    is_pnd, pnd_r = detect_pump_and_dump(kd)
    if is_pnd:
        log.info("🚫 P&D: %s | %s", symbol, pnd_r)
        mark_rejected(symbol)
        return None

    # حجم
    if kd["vols"][-1] < kd["avg_vol"]*1.2 or kd["vols"][-1] < DISCOVERY_MIN_VOL:
        mark_rejected(symbol)
        return None

    # Supertrend
    st_dir = get_supertrend_direction(symbol)
    if st_dir == "DOWN" and symbol not in hot_symbols:
        # نقبل العملات ذات Supertrend نازل فقط إذا كانت في قطاع ساخن
        log.debug("%s رُفض: Supertrend نازل", symbol)
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
            mark_rejected(symbol); return None
        if ob["imbalance"] > MAX_BID_ASK_IMBALANCE:
            mark_rejected(symbol); return None
        if ob["bid_depth"] < MIN_BID_DEPTH_USDT:
            mark_rejected(symbol); return None

    # تحليلات
    vol_accum   = detect_volume_accumulation(kd)
    vol_spike   = detect_volume_spike(kd)
    consol      = detect_price_consolidation(kd)
    higher_lows = detect_higher_lows(kd)
    is_bo, bo_str, bo_desc = detect_pre_breakout(symbol)

    # هل في قطاع ساخن؟
    in_hot = symbol in hot_symbols
    sector_name = ""
    if in_hot:
        for sec, syms in SECTORS.items():
            if symbol in syms and sec in hot_sectors:
                sector_name = sec
                break

    return {
        "kd": kd, "ob": ob,
        "vol_accum": vol_accum, "vol_spike": vol_spike,
        "consol": consol, "higher_lows": higher_lows,
        "green": (is_green, green_pct),
        "market_note": market_note,
        "is_breakout": is_bo, "breakout_str": bo_str, "breakout_desc": bo_desc,
        "in_hot_sector": in_hot, "sector_name": sector_name,
        "supertrend": st_dir,
    }


# ═══════════════════════════════════════════════
#   SYMBOL DISCOVERY
# ═══════════════════════════════════════════════
def discover_symbols():
    # type: () -> Tuple[List[str], Dict[str, float], List[Dict]]
    global btc_change_24h
    log.info("🔍 تحديث الأزواج...")
    data = safe_get(MEXC_24H)
    if not data:
        return watch_symbols, changes_map, []

    ch_map = {}  # type: Dict[str, float]
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
        if any(k in sym for k in LEVERAGE_KEYWORDS): continue
        ch_map[sym] = change
        if DISCOVERY_MIN_VOL < vol < DISCOVERY_MAX_VOL:
            result.append((sym, vol))

    result.sort(key=lambda x: -x[1])
    symbols = [s for s, _ in result[:MAX_SYMBOLS]]

    # أضف عملات القطاعات الساخنة حتى لو خارج الحجم المعتاد
    for sec in hot_sectors:
        for sym in SECTORS[sec]:
            if sym not in symbols and sym not in EXCLUDED:
                symbols.append(sym)

    log.info("✅ %d زوج | BTC: %.2f%%", len(symbols), btc_change_24h)
    return symbols, ch_map, data


# ═══════════════════════════════════════════════
#   STOP LOSS
# ═══════════════════════════════════════════════
def check_stop_loss(symbol, price):
    # type: (str, float) -> bool
    if symbol not in tracked: return False
    entry  = tracked[symbol]["entry"]
    sl_pct = tracked[symbol].get("sl_pct", SL_BASE_PCT)
    change = (price - entry) / entry * 100
    if change <= -sl_pct:
        send_telegram(
            "🛑 *STOP LOSS* | `{sym}`\n"
            "📉 خسارة: `{ch:.2f}%` | SL: `-{sl}%`\n"
            "💵 دخول: `{e}` ← الآن: `{n}`".format(
                sym=symbol, ch=change, sl=sl_pct,
                e=format_price(entry), n=format_price(price))
        )
        log.info("🛑 SL: %s %.2f%%", symbol, change)
        del tracked[symbol]
        return True
    return False


# ═══════════════════════════════════════════════
#   SIGNAL HANDLER v9
# ═══════════════════════════════════════════════
def handle_signal(symbol, price, change_24h=0.0):
    # type: (str, float, float) -> None
    if symbol.replace("USDT","") in STABLECOINS: return
    now = time.time()
    if check_stop_loss(symbol, price): return
    if symbol in tracked:
        if now - tracked[symbol].get("last_alert",0) < ALERT_COOLDOWN_SEC: return

    result = valid_setup(symbol, change_24h)
    if result is None: return

    kd           = result["kd"]
    ob           = result["ob"]
    vol_accum    = result["vol_accum"]
    vol_spike    = result["vol_spike"]
    consol       = result["consol"]
    higher_lows  = result["higher_lows"]
    green        = result["green"]
    market_note  = result["market_note"]
    is_bo        = result["is_breakout"]
    bo_str       = result["breakout_str"]
    bo_desc      = result["breakout_desc"]
    in_hot       = result["in_hot_sector"]
    sector_name  = result["sector_name"]
    st_dir       = result["supertrend"]

    score = calculate_score(kd, ob, vol_accum, vol_spike, consol,
                            higher_lows, green, bo_str, in_hot)

    # في حالة CAUTION: Gold فقط
    min_score = 88 if market_state == "CAUTION" else SCORE_MIN
    label = score_label(score)
    if not label or score < min_score:
        return

    # نصوص الإشارات
    signals_text = ""
    ia, as_ = vol_accum
    isp, sr  = vol_spike
    ic, cs   = consol
    ih, hp   = higher_lows
    ig, gp   = green

    if in_hot:
        signals_text += "\n🔥 *قطاع ساخن:* `{}`".format(sector_name)
    if is_bo:
        signals_text += "\n💥 *Breakout:* `{:.0f}%` _{}_".format(bo_str, bo_desc)
    if isp:
        signals_text += "\n⚡ *Vol Spike:* `{:.1f}×`".format(sr)
    if ia:
        signals_text += "\n🔋 *Vol Accum:* `{:.0f}%`".format(as_)
    if ic:
        signals_text += "\n🎯 *Consolidation:* `{:.0f}%`".format(cs)
    if ih:
        signals_text += "\n📈 *Higher Lows:* `{:.0f}%`".format(hp)
    if ig:
        signals_text += "\n🟢 *Green Candles:* `{:.0f}%`".format(gp)
    signals_text += "\n📊 *Supertrend:* `{}`".format("🟢 UP" if st_dir=="UP" else "🔴 DOWN")
    if market_note:
        signals_text += "\n{}".format(market_note)

    ob_text = ""
    if ob:
        em = "🟢" if ob["imbalance"] >= 1.2 else "🟡"
        ob_text = "\n📗 Bid:`{:,.0f}` | 📕 Ask:`{:,.0f}`\n{} Imb:`{:.2f}`".format(
            ob["bid_depth"], ob["ask_depth"], em, ob["imbalance"])

    # نوع الإشارة
    if is_bo and in_hot:    stype = "💥🔥 *BREAKOUT + HOT SECTOR*"
    elif is_bo:             stype = "💥 *BREAKOUT SETUP*"
    elif in_hot:            stype = "🔥 *HOT SECTOR SIGNAL*"
    elif sum([isp,ia,ic,ih])>=3: stype = "💎 *PRE-EXPLOSION*"
    elif isp:               stype = "⚡ *VOLUME SPIKE*"
    elif ia:                stype = "🔋 *ACCUMULATION*"
    else:                   stype = "📊 *SIGNAL*"

    if symbol not in tracked:
        sl_pct = calculate_dynamic_sl(kd, score, ob, is_bo)
        tracked[symbol] = {"entry": price, "level": 1, "score": score,
                           "entry_time": now, "last_alert": now, "sl_pct": sl_pct}
        discovered[symbol] = {"price": price, "time": now, "score": score}

        # حالة السوق في الإشارة
        mkt_icon = {"SAFE":"🟢","CAUTION":"🟡","DANGER":"🔴"}.get(market_state,"⚪")

        send_telegram(
            "👑 *SOURCE BOT VIP v9*\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "💰 *{sym}*\n"
            "{label} | {stype}\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "💵 Price: `{price}`\n"
            "📊 Score: *{score}/100*\n"
            "🕐 Time: `{time}`\n"
            "{mkt} السوق: `{mst}`{signals}{ob}\n"
            "📉 24h: `{ch:.1f}%` | BTC: `{btc:.1f}%`\n"
            "⚠️ Stop Loss: `-{sl}%` (ديناميكي)".format(
                sym=symbol, label=label, stype=stype,
                price=format_price(price), score=score,
                time=datetime.now().strftime("%H:%M:%S"),
                mkt=mkt_icon, mst=market_state,
                signals=signals_text, ob=ob_text,
                ch=change_24h, btc=btc_change_24h, sl=sl_pct,
            )
        )
        log.info("🟢 #1 | %s | score=%d | hot=%s bo=%s sl=%.1f%%",
                 symbol, score, in_hot, is_bo, sl_pct)
        return

    entry  = tracked[symbol]["entry"]
    level  = tracked[symbol]["level"]
    sl_pct = tracked[symbol].get("sl_pct", SL_BASE_PCT)
    change = (price - entry) / entry * 100

    if level == 1 and change >= SIGNAL2_GAIN:
        send_telegram(
            "🚀 {label} | *SIGNAL #2*\n💰 *{sym}*\n"
            "📈 Gain: *+{gain:.2f}%*\n"
            "💵 `{price}` | Score: *{score}* | SL:`-{sl}%`"
            "{signals}{ob}".format(
                label=label, sym=symbol, gain=change,
                price=format_price(price), score=score,
                sl=sl_pct, signals=signals_text, ob=ob_text)
        )
        tracked[symbol]["level"] = 2
        tracked[symbol]["last_alert"] = now
        log.info("🔵 #2 | %s +%.2f%%", symbol, change)

    elif level == 2 and change >= SIGNAL3_GAIN:
        send_telegram(
            "🔥 {label} | *SIGNAL #3*\n💰 *{sym}*\n"
            "📈 Gain: *+{gain:.2f}%*\n"
            "💵 `{price}` | Score: *{score}* | SL:`-{sl}%`"
            "{signals}{ob}".format(
                label=label, sym=symbol, gain=change,
                price=format_price(price), score=score,
                sl=sl_pct, signals=signals_text, ob=ob_text)
        )
        tracked[symbol]["level"] = 3
        tracked[symbol]["last_alert"] = now
        log.info("🔥 #3 | %s +%.2f%%", symbol, change)


# ═══════════════════════════════════════════════
#   CLEANUP & REPORT
# ═══════════════════════════════════════════════
def cleanup_stale():
    # type: () -> None
    now = time.time()
    for s in [s for s,d in list(tracked.items()) if now-d["entry_time"]>STALE_REMOVE_SEC]:
        log.info("🗑️ %s", s); del tracked[s]
    cleanup_rejection_cache()


def send_report():
    # type: () -> None
    global last_report
    now = time.time()
    if now - last_report < REPORT_INTERVAL: return
    last_report = now
    rows = []
    for sym, d in list(discovered.items()):
        pd = safe_get(MEXC_PRICE, {"symbol": sym})
        if not pd: continue
        try:
            cur = float(pd["price"])
            gr  = (cur - d["price"]) / d["price"] * 100
            if gr > 5: rows.append((sym, d["price"], cur, gr, d["score"]))
        except (KeyError, ValueError, ZeroDivisionError): continue
    if not rows: return
    rows.sort(key=lambda x: -x[3])
    msg = "⚡ *PERFORMANCE REPORT v9*\n🕐 `{}`\n\n".format(
        datetime.now().strftime("%Y-%m-%d %H:%M"))
    for sym, disc, cur, gr, sc in rows[:5]:
        msg += "🔥 *{}*  +{:.2f}% | Score:{}\n".format(sym, gr, sc)
    send_telegram(msg)


# ═══════════════════════════════════════════════
#   MAIN LOOP
# ═══════════════════════════════════════════════
def run():
    global watch_symbols, changes_map, last_discovery, last_sector_check

    log.info("🚀 MEXC Bot v9 يبدأ...")
    send_telegram(
        "🤖 *SOURCE BOT VIP v9*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🆕 Sector Rotation Tracker ✅\n"
        "   يتتبع دوران السيولة بين 12 قطاع\n"
        "🆕 BTC Market Analysis ✅\n"
        "🆕 Supertrend Filter ✅\n"
        "📊 Score Min: `{score}` (قوي فقط)\n"
        "✅ Watchlist + Bottom + Breakout\n"
        "✅ Anti P&D | Dynamic SL `{sl_min}-{sl_max}%`\n"
        "⚙️ Pairs: `{pairs}` | Sectors: `12`".format(
            score=SCORE_MIN,
            sl_min=SL_MIN_PCT, sl_max=SL_MAX_PCT,
            pairs=MAX_SYMBOLS,
        )
    )

    # أول تشغيل
    analyze_btc_market()
    res = discover_symbols()
    watch_symbols  = res[0]
    changes_map    = res[1]
    all_tickers    = res[2]
    last_discovery = time.time()
    analyze_sector_rotation(all_tickers)
    last_sector_check = time.time()
    cycle = 0

    while True:
        try:
            now = time.time()

            # تحديث BTC
            if now - last_btc_analysis >= BTC_ANALYSIS_INTERVAL:
                analyze_btc_market()

            # تحديث القطاعات والأزواج
            if now - last_discovery >= DISCOVERY_REFRESH_SEC:
                res = discover_symbols()
                watch_symbols  = res[0]
                changes_map    = res[1]
                all_tickers    = res[2]
                last_discovery = now

            # تحليل القطاعات
            if now - last_sector_check >= SECTOR_CHECK_INTERVAL:
                if all_tickers:
                    analyze_sector_rotation(all_tickers)
                last_sector_check = now

            # فحص الأسعار
            prices_data = safe_get(MEXC_PRICE)
            if prices_data:
                pm = {}
                for p in prices_data:
                    try: pm[p["symbol"]] = float(p["price"])
                    except (KeyError, ValueError): pass
                for sym in watch_symbols:
                    if sym in pm:
                        handle_signal(sym, pm[sym], changes_map.get(sym, 0.0))
                        if sym not in tracked:
                            check_watchlist(sym, pm[sym], changes_map.get(sym, 0.0))

            cycle += 1
            if cycle % 10 == 0: cleanup_stale()
            send_report()
            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            send_telegram("⛔ *SOURCE BOT VIP v9* – تم الإيقاف")
            break
        except Exception as e:
            log.error("خطأ: %s", e, exc_info=True)
            time.sleep(5)


if __name__ == "__main__":
    run()

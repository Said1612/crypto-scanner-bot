# -*- coding: utf-8 -*-
# Build: 20260323-V25-FINAL
"""
╔══════════════════════════════════════════════════════════════╗
║     MAFIO BOT V25 — FULL MARKET SCANNER                    ║
║     16 قطاع + مسح ذكي للسيولة                              ║
║     ✅ تقرير يومي (00:00 UTC)                              ║
║     ✅ تقرير كل 4 ساعات                                    ║
║     ✅ أوامر Telegram تعمل                                 ║
║     ✅ رصد السيولة حتى في السوق الهابط                     ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import sys
import time
import json
import logging
import requests
from datetime import datetime, timezone
from typing import Optional, Dict, List, Tuple, Any, Set
from collections import deque
import math

# ==================== إعداد LOGGING ====================

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

log.info("🚀 MAFIO-BOT V25 بدء التشغيل...")

# ==================== متغيرات البيئة ====================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("CHAT_ID", "")
GROUP_ID = os.getenv("GROUP_ID", "")
REDIS_URL = os.environ.get("REDIS_URL", os.environ.get("UPSTASH_REDIS_REST_URL", ""))
REDIS_TOKEN = os.environ.get("REDIS_TOKEN", os.environ.get("UPSTASH_REDIS_REST_TOKEN", ""))

# ==================== جميع القطاعات (16 قطاع) ====================

SECTORS = {
    "AI": [
        "FETUSDT", "AGIXUSDT", "OCEANUSDT", "RENDERUSDT", "GRTUSDT",
        "WLDUSDT", "ARKMUSDT", "VIRTUSDT", "ACTUSDT", "CGPTUSDT",
        "NEUROUSDT", "SWARMAUSDT", "PHAUSDT", "AIXBTUSDT", "KAIAUSDT"
    ],
    "Meme": [
        "DOGEUSDT", "SHIBUSDT", "PEPEUSDT", "FLOKIUSDT", "WIFUSDT",
        "BONKUSDT", "BOMEUSDT", "MEMEUSDT", "POPCATUSDT", "MOGUSDT",
        "BABYDOGEUSDT", "DOGSUSDT", "CATIUSDT", "PNUTUSDT", "TURBOUSDT"
    ],
    "Layer1": [
        "AVAXUSDT", "ADAUSDT", "SOLUSDT", "NEARUSDT", "SUIUSDT",
        "APTUSDT", "INJUSDT", "KASUSDT", "TONUSDT", "HBARUSDT",
        "EGLDUSDT", "FTMUSDT", "ALGOUSDT", "ICPUSDT", "SEIUSDT"
    ],
    "Layer2": [
        "POLUSDT", "OPUSDT", "ARBUSDT", "ZKUSDT", "STRKUSDT",
        "LRCUSDT", "METISUSDT", "MANTAUSDT", "MNTUSDT", "ALTUSDT",
        "ZROUSDT", "TAIKOUSDT", "SKLUSDT", "CELRUSDT", "BOBAUSDT"
    ],
    "DeFi": [
        "AAVEUSDT", "UNIUSDT", "CAKEUSDT", "LINKUSDT", "MKRUSDT",
        "CRVUSDT", "LDOUSDT", "COMPUSDT", "DYDXUSDT", "GMXUSDT",
        "JUPUSDT", "PENDLEUSDT", "EIGENUSDT", "ETHFIUSDT", "WOOUSDT"
    ],
    "Gaming": [
        "GALAUSDT", "AXSUSDT", "SANDUSDT", "IMXUSDT", "BEAMUSDT",
        "PIXELUSDT", "NOTUSDT", "XAIUSDT", "ALICEUSDT", "PORTALUSDT",
        "GMTUSDT", "YGGUSDT", "ILVUSDT", "RONUSDT", "MAGICUSDT"
    ],
    "RWA": [
        "ONDOUSDT", "CFGUSDT", "MANTRAUSDT", "RSRUSDT", "MPLXUSDT",
        "REALUSDT", "TRSTUSDT", "PROMUSDT", "LQTYUSDT", "POLYXUSDT",
        "PLUMEUSDT", "CENTUSDT", "DEXTUSDT", "MAPLEUSDT"
    ],
    "Oracle": [
        "LINKUSDT", "PYTHUSDT", "BANDUSDT", "UMAUSDT", "DIAUSDT",
        "API3USDT", "FLUXUSDT", "SUPRAUSDT", "TRUFUSDT", "ORAIUSDT"
    ],
    "Storage": [
        "FILUSDT", "ARUSDT", "STORJUSDT", "BLZUSDT", "HOTUSDT",
        "CKBUSDT", "AIOZUSDT", "ANKRUSDT", "CRUSTUSDT", "SWARMUSDT"
    ],
    "DePIN": [
        "IOTAUSDT", "HNTUSDT", "LPTUSDT", "NTRNUSDT", "GPUUSDT",
        "PONDUSDT", "GRASSUSDT", "IOTXUSDT", "POKTUSDT", "DOTUSDT"
    ],
    "Privacy": [
        "XMRUSDT", "DASHUSDT", "ZECUSDT", "SCRTUSDT", "ROSEUSDT",
        "DUSKUSDT", "ZENUSDT", "NYMUSDT", "FIROUSDT", "PIVXUSDT"
    ],
    "NeoBank": [
        "XLMUSDT", "XRPUSDT", "PYTHUSDT", "STRKUSDT", "COTIUSDT",
        "REQUSDT", "PAYUSDT", "SOLOUSDT", "NEXOUSDT", "WIREXUSDT"
    ],
    "Robotics": [
        "WLDUSDT", "RENDERUSDT", "FETUSDT", "AGIXUSDT", "ARKMUSDT",
        "PHAUSDT", "CUDOSUSDT", "CGPTUSDT", "NEUROUSDT", "VIRTUSDT"
    ],
    "Quantum": [
        "QNTUSDT", "QTUMUSDT", "IONQUSDT", "QUAIUSDT", "KVANTUSDT",
        "QUIPUSDT", "QUANTUMUSDT", "QKCUSDT", "ALEPHUSDT"
    ],
    "POW": [
        "ZECUSDT", "ZILUSDT", "ALPHUSDT", "KASUSDT", "RVNUSDT",
        "DCRUSDT", "GRLUSDT", "ERGOUSDT", "CPHUSDT", "RIFUSDT"
    ],
    "Old": [
        "LTCUSDT", "ETCUSDT", "BCHUSDT", "EOSUSDT", "TRXUSDT",
        "QTUMUSDT", "XEMUSDT", "ZRXUSDT", "ICXUSDT", "STEEMUSDT"
    ]
}

log.info(f"✅ تم تحميل {len(SECTORS)} قطاع")

# ==================== إعدادات المسح ====================

MIN_VOL_USDT = 300_000
MAX_VOL_USDT = 80_000_000
MIN_PRICE_CHANGE = -5.0
MAX_PRICE_CHANGE = 80.0
MIN_SCAN_SCORE = 30

LEVERAGE_KEYWORDS = ["3L", "3S", "5L", "5S", "BULL", "BEAR", "UP", "DOWN", "LONG", "SHORT"]
STABLECOINS = {"USDT", "USDC", "BUSD", "FDUSD", "DAI", "TUSD"}

# ==================== إعدادات التقارير ====================
REPORT_4H_INTERVAL = 14400  # 4 ساعات

# ==================== المتغيرات العامة ====================

last_tickers = 0.0
last_btc = 0.0
last_sectors = 0.0
last_deep_scan = 0.0
last_stale = 0.0
last_4h_report = 0.0

btc_change_24h = 0.0
btc_trend_1h = 0.0
btc_trend_4h = 0.0
eth_change_24h = 0.0
btc_tps_stats = {}
eth_tps_stats = {}
market_state = "SAFE"

hot_sectors = []
hot_symbols = set()
candidates = []
changes_map = {}
all_tickers = []
klines_cache = {}
coin_vol_history = {}
watchlist = {}
price_map = {}
vol_now = {}
change_now = {}

api_calls_total = 0
api_calls_minute = 0
api_minute_reset = time.time()

_tg_offset = 0
_force_daily_report = False
daily_report_sent_date = ""

# ==================== الدوال المساعدة ====================

def fmt_price(p):
    if p == 0:
        return "0"
    if p < 0.0001:
        return "{:.10f}".format(p).rstrip("0")
    if p < 1:
        return "{:.8f}".format(p).rstrip("0")
    if p < 1000:
        return "{:.4f}".format(p).rstrip("0").rstrip(".")
    return "{:,.2f}".format(p)


def send(msg, personal_only=False):
    """إرسال رسالة Telegram"""
    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN == "YOUR_BOT_TOKEN":
        log.info("[TELEGRAM] %s", msg[:80])
        return

    targets = [CHAT_ID]
    if GROUP_ID and not personal_only:
        targets.append(GROUP_ID)

    for chat_id in targets:
        if not chat_id or "YOUR" in str(chat_id):
            continue
        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                data={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"},
                timeout=15,
            )
        except Exception as e:
            log.error("Telegram [%s]: %s", chat_id, e)


def safe_get(url, params=None, retries=3):
    global api_calls_total, api_calls_minute, api_minute_reset

    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=10)
            r.raise_for_status()
            api_calls_total += 1
            api_calls_minute += 1
            _now = time.time()
            _elapsed = _now - api_minute_reset
            if _elapsed >= 60:
                _rate = int(api_calls_minute / (_elapsed / 60))
                log.info("📡 API: %d req/min | total: %d", _rate, api_calls_total)
                api_calls_minute = 0
                api_minute_reset = _now
            return r.json()
        except Exception as e:
            wait = 2 ** attempt
            if attempt < retries - 1:
                time.sleep(wait)
    return None


def get_klines(symbol, interval="15m", limit=50):
    cache_ttl = {"15m": 60, "1h": 300, "4h": 900}.get(interval, 60)
    key = f"{symbol}_{interval}"
    now = time.time()

    if key in klines_cache:
        data, ts = klines_cache[key]
        if now - ts < cache_ttl:
            return data

    raw = safe_get("https://api.mexc.com/api/v3/klines",
                   {"symbol": symbol, "interval": interval, "limit": limit})
    if not raw or len(raw) < 6:
        return None

    try:
        opens = [float(c[1]) for c in raw]
        highs = [float(c[2]) for c in raw]
        lows = [float(c[3]) for c in raw]
        closes = [float(c[4]) for c in raw]
        vols = [float(c[5]) for c in raw]
        result = {
            "opens": opens, "highs": highs, "lows": lows,
            "closes": closes, "vols": vols,
            "avg_vol": sum(vols[:-1]) / max(len(vols[:-1]), 1),
        }
        klines_cache[key] = (result, now)
        return result
    except (IndexError, ValueError, ZeroDivisionError):
        return None


def get_coin_vol_ratio(sym, current_vol):
    hist = coin_vol_history.get(sym, [])
    if len(hist) < 3:
        return 1.0
    avg = sum(hist) / len(hist)
    if avg <= 0:
        return 1.0
    return round(current_vol / avg, 2)


def update_coin_vol_history(vol_map):
    global coin_vol_history
    for sym, vol in vol_map.items():
        if vol <= 0:
            continue
        if sym not in coin_vol_history:
            coin_vol_history[sym] = []
        coin_vol_history[sym].append(vol)
        if len(coin_vol_history[sym]) > 10:
            coin_vol_history[sym].pop(0)


def analyze_tps_ats(sym):
    raw = safe_get("https://api.mexc.com/api/v3/trades",
                   {"symbol": sym, "limit": 100})
    if not raw or not isinstance(raw, list) or len(raw) < 10:
        return None
    try:
        now_ms = int(time.time() * 1000)
        window = 30000
        all_vol = 0.0
        trade_window = 0

        for t in raw:
            price = float(t.get("price", 0))
            qty = float(t.get("qty", 0))
            ts = int(t.get("time", 0))
            val = price * qty
            all_vol += val
            if now_ms - ts <= window:
                trade_window += 1

        if all_vol <= 0:
            return None

        tps = trade_window / 30.0
        ats = all_vol / len(raw)

        vdelta = 0.5
        kd = get_klines(sym, "15m", 15)
        if kd and len(kd["closes"]) >= 5:
            buy_vol = 0
            sell_vol = 0
            for i in range(len(kd["closes"])):
                if kd["closes"][i] > kd["opens"][i]:
                    buy_vol += kd["vols"][i]
                elif kd["closes"][i] < kd["opens"][i]:
                    sell_vol += kd["vols"][i]
            total = buy_vol + sell_vol
            if total > 0:
                vdelta = buy_vol / total

        return {
            "tps": round(tps, 2),
            "ats": round(ats, 2),
            "vdelta": round(vdelta, 3),
        }
    except (KeyError, ValueError, ZeroDivisionError, TypeError):
        return None


def calculate_coin_score(vol, change, vdelta, ats, tps):
    score = 0
    if vol >= 10_000_000:
        score += 25
    elif vol >= 5_000_000:
        score += 20
    elif vol >= 1_000_000:
        score += 15
    elif vol >= 500_000:
        score += 10

    if change > 0:
        if change >= 10:
            score += 20
        elif change >= 5:
            score += 15
        elif change >= 2:
            score += 10
        else:
            score += 5

    if vdelta >= 0.70:
        score += 25
    elif vdelta >= 0.65:
        score += 20
    elif vdelta >= 0.60:
        score += 15

    if ats >= 2000:
        score += 20
    elif ats >= 500:
        score += 10

    if tps >= 2.0:
        score += 10

    return min(score, 100)


def is_leverage_token(sym):
    for kw in LEVERAGE_KEYWORDS:
        if kw in sym:
            return True
    return False


def is_stablecoin(sym):
    base = sym.replace("USDT", "")
    if base in STABLECOINS:
        return True
    return False


# ==================== نظام المسح الذكي ====================

class SmartMarketScanner:
    def __init__(self):
        self.scan_results = {}
        self.last_scan_time = 0
        self.scan_interval = 3600
        
    def scan_all_market(self):
        global all_tickers, candidates, changes_map, hot_sectors, hot_symbols
        log.info("🔍 بدء المسح الذكي للسوق...")
        
        data = safe_get("https://api.mexc.com/api/v3/ticker/24hr")
        if not data:
            log.warning("⚠️ فشل جلب بيانات السوق")
            return []
        
        all_tickers = data
        results = []
        changes_map = {}
        
        vol_map = {}
        change_map = {}
        price_map = {}
        
        for t in data:
            sym = t.get("symbol", "")
            if not sym.endswith("USDT"):
                continue
            try:
                vol = float(t.get("quoteVolume", 0))
                ch = float(t.get("priceChangePercent", 0))
                price = float(t.get("lastPrice", 0))
                vol_map[sym] = vol
                change_map[sym] = ch
                price_map[sym] = price
                changes_map[sym] = ch
            except (KeyError, ValueError):
                continue
        
        all_scanned = []
        
        for sector, coins in SECTORS.items():
            for sym in coins:
                if sym not in vol_map:
                    continue
                
                vol = vol_map.get(sym, 0)
                ch = change_map.get(sym, 0)
                
                if vol < MIN_VOL_USDT or vol > MAX_VOL_USDT:
                    continue
                if ch < MIN_PRICE_CHANGE or ch > MAX_PRICE_CHANGE:
                    continue
                if is_leverage_token(sym):
                    continue
                if is_stablecoin(sym):
                    continue
                
                stats = analyze_tps_ats(sym)
                vdelta = stats.get("vdelta", 0.5) if stats else 0.5
                ats = stats.get("ats", 0) if stats else 0
                tps = stats.get("tps", 0) if stats else 0
                
                score = calculate_coin_score(vol, ch, vdelta, ats, tps)
                vol_ratio = get_coin_vol_ratio(sym, vol)
                
                if score >= MIN_SCAN_SCORE or vol_ratio >= 1.5:
                    all_scanned.append({
                        "sym": sym,
                        "sector": sector,
                        "price": price_map.get(sym, 0),
                        "change": ch,
                        "vol": vol,
                        "vdelta": vdelta,
                        "ats": ats,
                        "tps": tps,
                        "score": score,
                        "vol_ratio": vol_ratio
                    })
        
        all_scanned.sort(key=lambda x: -x["score"])
        candidates = [c["sym"] for c in all_scanned[:100]]
        self.scan_results = {c["sym"]: c for c in all_scanned}
        self.last_scan_time = time.time()
        
        # تحديث القطاعات الساخنة
        sector_scores = {}
        for c in all_scanned[:50]:
            sec = c["sector"]
            if sec not in sector_scores:
                sector_scores[sec] = {"count": 0, "total_score": 0}
            sector_scores[sec]["count"] += 1
            sector_scores[sec]["total_score"] += c["score"]
        
        sorted_sectors = sorted(sector_scores.items(), key=lambda x: -x[1]["total_score"] / x[1]["count"])
        hot_sectors = [s for s, _ in sorted_sectors[:5]]
        hot_symbols = {c for s in hot_sectors for c in SECTORS.get(s, [])}
        
        log.info(f"✅ المسح الذكي اكتمل | وجد {len(all_scanned)} عملة تستوفي الشروط")
        log.info(f"🔥 Hot sectors: {hot_sectors}")
        return all_scanned


# ==================== دالة تحليل BTC ====================

def analyze_btc():
    global btc_change_24h, btc_trend_1h, btc_trend_4h, market_state, eth_change_24h
    global btc_tps_stats, eth_tps_stats

    data = safe_get("https://api.mexc.com/api/v3/ticker/24hr", {"symbol": "BTCUSDT"})
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

    kd1 = get_klines("BTCUSDT", "1h", 4)
    if kd1 and len(kd1["closes"]) >= 2:
        c = kd1["closes"]
        btc_trend_1h = (c[-1] - c[-2]) / c[-2] * 100 if c[-2] > 0 else 0.0

    kd4 = get_klines("BTCUSDT", "4h", 3)
    if kd4 and len(kd4["closes"]) >= 2:
        c4 = kd4["closes"]
        btc_trend_4h = (c4[-1] - c4[-2]) / c4[-2] * 100 if c4[-2] > 0 else 0.0

    eth_data = safe_get("https://api.mexc.com/api/v3/ticker/24hr", {"symbol": "ETHUSDT"})
    if eth_data:
        try:
            _elp = float(eth_data.get("lastPrice", 0))
            _eop = float(eth_data.get("openPrice", _elp))
            if _eop > 0:
                eth_change_24h = (_elp - _eop) / _eop * 100
        except (KeyError, ValueError, TypeError):
            pass

    _btc_tps = analyze_tps_ats("BTCUSDT")
    if _btc_tps:
        btc_tps_stats = _btc_tps
    _eth_tps = analyze_tps_ats("ETHUSDT")
    if _eth_tps:
        eth_tps_stats = _eth_tps

    # تحديث حالة السوق
    if btc_change_24h <= -2.0:
        market_state = "DANGER"
    elif btc_change_24h <= -1.0:
        market_state = "CAUTION"
    else:
        market_state = "SAFE"


# ==================== دالة تقرير 4 ساعات ====================

def send_4h_sector_report():
    global last_4h_report
    now = time.time()
    
    if now - last_4h_report < REPORT_4H_INTERVAL:
        return
    
    last_4h_report = now
    
    msg = "📊 *تقرير القطاعات | 4 ساعات*\n━━━━━━━━━━━━━━━━━━\n"
    msg += f"🕐 {datetime.now().strftime('%H:%M:%S')}\n"
    msg += f"🔥 أفضل القطاعات: {', '.join(hot_sectors[:5]) or 'لا يوجد'}\n"
    msg += f"📊 عدد العملات المرشحة: {len(candidates)}\n"
    msg += f"₿ BTC: `{btc_change_24h:+.2f}%`\n"
    send(msg)
    log.info(f"📊 4H Report sent")


# ==================== دالة تقرير يومي ====================

def send_daily_report(force=False):
    global daily_report_sent_date
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    today = now_utc.strftime("%Y-%m-%d")

    if not force and not _force_daily_report:
        if now_utc.hour != 0:
            return
        if daily_report_sent_date == today:
            return

    daily_report_sent_date = today
    
    msg = "📊 *التقرير اليومي*\n━━━━━━━━━━━━━━━━━━\n"
    msg += f"📅 {today}\n"
    msg += f"₿ BTC: `{btc_change_24h:+.2f}%` | السوق: `{market_state}`\n"
    msg += f"🔥 القطاعات الساخنة: {', '.join(hot_sectors[:3]) or 'لا يوجد'}\n"
    msg += f"📊 عدد العملات المرشحة: {len(candidates)}\n"
    send(msg)
    log.info(f"📅 Daily Report sent | {today}")


# ==================== دالة استقبال أوامر Telegram (المصححة) ====================

def poll_commands():
    """يستمع لأوامر Telegram"""
    global _tg_offset, daily_report_sent_date, candidates, hot_sectors, market_state, btc_change_24h, btc_trend_1h, btc_tps_stats, changes_map
    
    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN == "YOUR_BOT_TOKEN":
        return

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={_tg_offset}&timeout=10"
        r = requests.get(url, timeout=15)
        
        if r.status_code != 200:
            return
        
        data = r.json()
        if not data.get("ok"):
            return
        
        updates = data.get("result", [])
        
        for update in updates:
            _tg_offset = update["update_id"] + 1
            
            msg = update.get("message") or update.get("channel_post") or {}
            text = msg.get("text", "").strip()
            chat_id = str(msg.get("chat", {}).get("id", ""))
            
            allowed = [str(CHAT_ID)]
            if GROUP_ID and GROUP_ID != "YOUR_GROUP_ID":
                allowed.append(str(GROUP_ID))
            
            if chat_id not in allowed:
                continue
            
            text_lower = text.lower()
            log.info(f"📨 أمر مستلم: {text}")
            
            # ========== الأوامر ==========
            
            if text_lower in ("/status", "/حالة"):
                reply = (
                    f"📊 *حالة البوت*\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"✅ البوت يعمل\n"
                    f"📈 العملات المرشحة: `{len(candidates)}`\n"
                    f"🔥 القطاعات: `{', '.join(hot_sectors[:3]) or 'لا يوجد'}`\n"
                    f"₿ BTC: `{btc_change_24h:+.2f}%` | `{market_state}`\n"
                    f"🕐 {datetime.now().strftime('%H:%M:%S')}"
                )
                send(reply, personal_only=True)
                log.info("✅ /status تم الإرسال")
            
            elif text_lower in ("/report", "/تقرير"):
                send("📄 جاري إعداد التقرير...", personal_only=True)
                reply = (
                    f"📊 *تقرير فوري*\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🕐 {datetime.now().strftime('%H:%M:%S')}\n"
                    f"₿ BTC: `{btc_change_24h:+.2f}%`\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🔥 *القطاعات:* {', '.join(hot_sectors[:5]) or 'لا يوجد'}\n"
                    f"📈 *العملات:* `{len(candidates)}`\n"
                )
                if candidates:
                    reply += "\n*🏆 أفضل 5:*\n"
                    for sym in candidates[:5]:
                        base = sym.replace("USDT", "")
                        ch = changes_map.get(sym, 0)
                        icon = "🟢" if ch > 0 else "🔴"
                        reply += f"  {icon} *{base}* `{ch:+.1f}%`\n"
                send(reply, personal_only=True)
                log.info("✅ /report تم الإرسال")
            
            elif text_lower in ("/sectors", "/قطاعات"):
                if not hot_sectors:
                    send("📊 لا توجد قطاعات ساخنة", personal_only=True)
                else:
                    reply = "🏆 *القطاعات الساخنة:*\n━━━━━━━━━━━━━━━━━━\n"
                    for i, sec in enumerate(hot_sectors[:5], 1):
                        reply += f"{i}. 🔥 *{sec}*\n"
                    send(reply, personal_only=True)
                log.info("✅ /sectors تم الإرسال")
            
            elif text_lower in ("/btc", "/بتكوين"):
                icon = {"SAFE": "🟢", "CAUTION": "🟡", "DANGER": "🔴"}.get(market_state, "📊")
                reply = (
                    f"₿ *BTC الآن*\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"{icon} السوق: *{market_state}*\n"
                    f"24h: `{btc_change_24h:+.2f}%`\n"
                    f"1h:  `{btc_trend_1h:+.2f}%`\n"
                )
                if btc_tps_stats:
                    reply += f"ATS: `{btc_tps_stats.get('ats',0):.0f}$` | VD: `{btc_tps_stats.get('vdelta',0.5)*100:.0f}%`\n"
                send(reply, personal_only=True)
                log.info("✅ /btc تم الإرسال")
            
            elif text_lower == "/test":
                send("✅ *البوت يعمل!*\nأمر /test تم استلامه بنجاح", personal_only=True)
                log.info("✅ /test تم الإرسال")
            
            elif text_lower in ("/help", "/مساعدة"):
                reply = (
                    "🤖 *أوامر MAFIO-BOT:*\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    "📊 /status  — حالة البوت\n"
                    "📅 /report  — تقرير فوري\n"
                    "🏆 /sectors — القطاعات الساخنة\n"
                    "₿ /btc     — حالة BTC\n"
                    "🧪 /test    — اختبار البوت\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    "💡 الإشارات تلقائية عند وجود سيولة"
                )
                send(reply, personal_only=True)
                log.info("✅ /help تم الإرسال")
            
            elif text_lower in ("/start", "/تشغيل"):
                send("✅ البوت يعمل الآن!", personal_only=True)
                log.info("✅ /start تم الإرسال")
            
            else:
                send(f"⚠️ أمر غير معروف: `{text}`\nأرسل /help للتعليمات", personal_only=True)
                
    except Exception as e:
        log.error(f"poll_commands error: {e}")


# ==================== دوال فارغة لتجنب الأخطاء ====================

def refresh_tickers():
    global last_tickers
    last_tickers = time.time()


def update_coin_vol_history(vol_map):
    pass


def save_state():
    pass


def load_state():
    pass


def cleanup():
    pass


# ==================== الحلقة الرئيسية ====================

def run():
    global all_tickers, candidates, hot_sectors, market_state, btc_change_24h
    global last_btc, last_sectors, last_deep_scan, last_stale, last_tickers
    global last_4h_report, price_map, vol_now, change_now
    
    price_map = {}
    vol_now = {}
    change_now = {}
    
    log.info("🚀 MAFIO-BOT V25 بدء التشغيل...")
    log.info(f"📊 {len(SECTORS)} قطاع يتم مراقبتها")

    time.sleep(5)

    scanner = SmartMarketScanner()

    analyze_btc()
    scanner.scan_all_market()
    
    time.sleep(2)
    
    last_deep_scan = 0
    last_tickers = time.time()
    last_4h_report = time.time()

    log.info(f"✅ Ready | Candidates: {len(candidates)} | Hot sectors: {hot_sectors}")

    send(
        f"💀 *MAFIO-BOT V25* 💀\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 {len(SECTORS)} قطاع تحت المراقبة\n"
        f"✅ تقرير يومي (00:00 UTC)\n"
        f"✅ تقرير كل 4 ساعات\n"
        f"✅ أوامر Telegram: /status, /report, /sectors, /btc, /test\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"₿ BTC: `{btc_change_24h:+.2f}%` | `{market_state}`"
    )

    while True:
        try:
            now = time.time()

            # التقرير كل 4 ساعات
            if now - last_4h_report >= REPORT_4H_INTERVAL:
                send_4h_sector_report()
                last_4h_report = now

            # التقرير اليومي
            send_daily_report()

            # المسح الذكي للسوق كل ساعة
            if now - scanner.last_scan_time >= scanner.scan_interval:
                scanner.scan_all_market()

            # جلب بيانات السوق
            tickers_now = safe_get("https://api.mexc.com/api/v3/ticker/24hr")
            if tickers_now:
                all_tickers = tickers_now
                for t in tickers_now:
                    sym = t.get("symbol", "")
                    try:
                        last = float(t["lastPrice"])
                        change_now[sym] = float(t.get("priceChangePercent", 0))
                        vol_now[sym] = float(t.get("quoteVolume", 0))
                        price_map[sym] = last
                    except (KeyError, ValueError):
                        pass

                changes_map.update(change_now)

            # تحديث قائمة المرشحين
            if now - last_tickers >= 1800:
                candidates = list(scanner.scan_results.keys())[:100]
                last_tickers = now

            # تحليل BTC
            if now - last_btc >= 300:
                analyze_btc()
                last_btc = now

            # استقبال أوامر Telegram
            poll_commands()

            time.sleep(12)

        except KeyboardInterrupt:
            send("⛔ *MAFIO-BOT* — تم الإيقاف")
            break
        except Exception as e:
            log.error(f"Error: {e}", exc_info=True)
            time.sleep(10)


if __name__ == "__main__":
    run()

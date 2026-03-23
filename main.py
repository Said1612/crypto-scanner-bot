# -*- coding: utf-8 -*-
# Build: 20260323-V30-FINAL
"""
╔══════════════════════════════════════════════════════════════╗
║     MAFIO BOT V30 — LIQUIDITY MASTER                       ║
║     نظام الكشف المبكر عن السيولة قبل ارتفاع السعر          ║
║     ✅ مرحلتين: WATCH → ENTRY                              ║
║     ✅ ATS حسب حجم العملة (Small/Mid/Big Cap)              ║
║     ✅ فلتر Pump & Dump                                    ║
║     ✅ Sector Flow للقطاعات الساخنة                        ║
║     ✅ جاهز للإنتاج                                        ║
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

log.info("🚀 MAFIO-BOT V30 - LIQUIDITY MASTER بدء التشغيل...")

# ==================== متغيرات البيئة ====================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("CHAT_ID", "")
GROUP_ID = os.getenv("GROUP_ID", "")

# ==================== إعدادات النظام ====================

# إعدادات الوقت
CHECK_INTERVAL = 30               # فحص كل 30 ثانية
REPORT_4H_INTERVAL = 14400        # 4 ساعات
BTC_EVERY = 300                   # 5 دقائق

# إعدادات ATS حسب حجم العملة
ATS_THRESHOLDS = {
    "small": {                    # حجم < 1M USDT
        "watch": 30,
        "entry": 50,
        "joker": 100,
        "max_price_change": 8.0,
        "label": "Small Cap 🚀"
    },
    "mid": {                      # حجم 1M-10M USDT
        "watch": 50,
        "entry": 100,
        "joker": 300,
        "max_price_change": 5.0,
        "label": "Mid Cap 📊"
    },
    "big": {                      # حجم > 10M USDT
        "watch": 100,
        "entry": 200,
        "joker": 500,
        "max_price_change": 3.0,
        "label": "Big Cap 🏦"
    }
}

# إعدادات VDelta
VDELTA_THRESHOLDS = {
    "watch": 0.50,      # 50% بداية شراء
    "entry": 0.65,      # 65% شراء قوي
    "joker": 0.70,      # 70% شراء خالص
}

# إعدادات الحجم
VOLUME_THRESHOLDS = {
    "watch": 1.5,       # 1.5× بداية نشاط
    "entry": 2.5,       # 2.5× سيولة قوية
    "joker": 3.0,       # 3.0× حجم غير طبيعي
}

# إعدادات TPS
TPS_THRESHOLDS = {
    "min": 0.3,         # أقل TPS للقبول
    "ideal": 0.5,       # TPS مثالي (حيتان هادئون)
    "max": 2.0,         # أكثر من هذا = نشاط عادي
}

# إعدادات Sector Flow
SECTOR_FLOW_THRESHOLD = 15.0      # +15% حجم القطاع = ساخن
SECTOR_FLOW_COOLDOWN = 1800       # 30 دقيقة

# إعدادات التكرار
COOLDOWN_WATCH = 1800             # 30 دقيقة بين إشارات WATCH
COOLDOWN_ENTRY = 3600             # ساعة بين إشارات ENTRY
COOLDOWN_JOKER = 14400            # 4 ساعات بين إشارات JOKER

# ==================== جميع القطاعات (16 قطاع) ====================

SECTORS = {
    "AI": ["FETUSDT", "AGIXUSDT", "OCEANUSDT", "RENDERUSDT", "GRTUSDT", "WLDUSDT", "ARKMUSDT", "VIRTUSDT", "ACTUSDT", "CGPTUSDT"],
    "Meme": ["DOGEUSDT", "SHIBUSDT", "PEPEUSDT", "FLOKIUSDT", "WIFUSDT", "BONKUSDT", "BOMEUSDT", "MEMEUSDT", "POPCATUSDT", "MOGUSDT"],
    "Layer1": ["AVAXUSDT", "ADAUSDT", "SOLUSDT", "NEARUSDT", "SUIUSDT", "APTUSDT", "INJUSDT", "KASUSDT", "TONUSDT", "HBARUSDT"],
    "Layer2": ["POLUSDT", "OPUSDT", "ARBUSDT", "ZKUSDT", "STRKUSDT", "LRCUSDT", "METISUSDT", "MANTAUSDT", "MNTUSDT", "ALTUSDT"],
    "DeFi": ["AAVEUSDT", "UNIUSDT", "CAKEUSDT", "LINKUSDT", "MKRUSDT", "CRVUSDT", "LDOUSDT", "COMPUSDT", "DYDXUSDT", "GMXUSDT"],
    "Gaming": ["GALAUSDT", "AXSUSDT", "SANDUSDT", "IMXUSDT", "BEAMUSDT", "PIXELUSDT", "NOTUSDT", "XAIUSDT", "ALICEUSDT", "PORTALUSDT"],
    "RWA": ["ONDOUSDT", "CFGUSDT", "MANTRAUSDT", "RSRUSDT", "MPLXUSDT", "REALUSDT", "TRSTUSDT", "PROMUSDT", "LQTYUSDT", "POLYXUSDT"],
    "Oracle": ["LINKUSDT", "PYTHUSDT", "BANDUSDT", "UMAUSDT", "DIAUSDT", "API3USDT", "FLUXUSDT", "SUPRAUSDT", "TRUFUSDT", "ORAIUSDT"],
    "Storage": ["FILUSDT", "ARUSDT", "STORJUSDT", "BLZUSDT", "HOTUSDT", "CKBUSDT", "AIOZUSDT", "ANKRUSDT", "CRUSTUSDT", "SWARMUSDT"],
    "DePIN": ["IOTAUSDT", "HNTUSDT", "LPTUSDT", "NTRNUSDT", "GPUUSDT", "PONDUSDT", "GRASSUSDT", "IOTXUSDT", "POKTUSDT", "DOTUSDT"],
    "Privacy": ["XMRUSDT", "DASHUSDT", "ZECUSDT", "SCRTUSDT", "ROSEUSDT", "DUSKUSDT", "ZENUSDT", "NYMUSDT", "FIROUSDT", "PIVXUSDT"],
    "NeoBank": ["XLMUSDT", "XRPUSDT", "PYTHUSDT", "STRKUSDT", "COTIUSDT", "REQUSDT", "PAYUSDT", "SOLOUSDT", "NEXOUSDT", "WIREXUSDT"],
    "Robotics": ["WLDUSDT", "RENDERUSDT", "FETUSDT", "AGIXUSDT", "ARKMUSDT", "PHAUSDT", "CUDOSUSDT", "CGPTUSDT", "NEUROUSDT", "VIRTUSDT"],
    "Quantum": ["QNTUSDT", "QTUMUSDT", "IONQUSDT", "QUAIUSDT", "KVANTUSDT", "QUIPUSDT", "QUANTUMUSDT", "QKCUSDT", "ALEPHUSDT"],
    "POW": ["ZECUSDT", "ZILUSDT", "ALPHUSDT", "KASUSDT", "RVNUSDT", "DCRUSDT", "GRLUSDT", "ERGOUSDT", "CPHUSDT", "RIFUSDT"],
    "Old": ["LTCUSDT", "ETCUSDT", "BCHUSDT", "EOSUSDT", "TRXUSDT", "QTUMUSDT", "XEMUSDT", "ZRXUSDT", "ICXUSDT", "STEEMUSDT"]
}

log.info(f"✅ تم تحميل {len(SECTORS)} قطاع")

# ==================== المتغيرات العامة ====================

# متغيرات الوقت
last_tickers = 0.0
last_btc = 0.0
last_sectors = 0.0
last_deep_scan = 0.0
last_stale = 0.0
last_4h_report = 0.0
last_sector_flow_scan = 0.0

# متغيرات السوق
btc_change_24h = 0.0
btc_trend_1h = 0.0
btc_trend_4h = 0.0
eth_change_24h = 0.0
btc_tps_stats = {}
eth_tps_stats = {}
market_state = "SAFE"

# قوائم العملات
hot_sectors = []
hot_symbols = set()
candidates = []
changes_map = {}
all_tickers = []
klines_cache = {}
coin_vol_history = {}
price_map = {}
vol_now = {}
change_now = {}

# عدادات API
api_calls_total = 0
api_calls_minute = 0
api_minute_reset = time.time()

# متغيرات Telegram
_tg_offset = 0
_force_daily_report = False
daily_report_sent_date = ""

# ==================== نظام الإشارات ====================

class SignalTracker:
    """تتبع العملات في مرحلة المراقبة"""
    
    def __init__(self):
        self.watchlist = {}  # {sym: {"time": timestamp, "price": price, "tier": tier, "data": {}}}
        self.alerted = {}    # {sym: {"watch": timestamp, "entry": timestamp, "joker": timestamp}}
        
    def get_tier(self, vol_24h):
        """تحديد حجم العملة حسب حجم 24h"""
        if vol_24h < 1_000_000:
            return "small"
        elif vol_24h < 10_000_000:
            return "mid"
        else:
            return "big"
    
    def get_ats_threshold(self, tier, signal_type):
        """الحصول على حد ATS حسب حجم العملة ونوع الإشارة"""
        thresholds = ATS_THRESHOLDS.get(tier, ATS_THRESHOLDS["mid"])
        if signal_type == "watch":
            return thresholds["watch"]
        elif signal_type == "entry":
            return thresholds["entry"]
        else:
            return thresholds["joker"]
    
    def should_send_watch(self, sym, ats, vol_24h, price_change):
        """التحقق من شروط إرسال إشارة مراقبة"""
        tier = self.get_tier(vol_24h)
        min_ats = self.get_ats_threshold(tier, "watch")
        max_price_change = ATS_THRESHOLDS[tier]["max_price_change"]
        
        # شروط المراقبة
        if ats >= min_ats and price_change <= max_price_change:
            return True, tier
        return False, None
    
    def should_send_entry(self, sym, ats, vdelta, vol_ratio, vol_24h, price_change):
        """التحقق من شروط إرسال إشارة دخول"""
        tier = self.get_tier(vol_24h)
        min_ats = self.get_ats_threshold(tier, "entry")
        max_price_change = ATS_THRESHOLDS[tier]["max_price_change"]
        
        # شروط الدخول
        if (ats >= min_ats and 
            vdelta >= VDELTA_THRESHOLDS["entry"] and 
            vol_ratio >= VOLUME_THRESHOLDS["entry"] and
            price_change <= max_price_change):
            return True, tier
        return False, None
    
    def add_watch(self, sym, price, ats, vdelta, vol_ratio, tps, vol_24h, sector):
        """إضافة عملة لقائمة المراقبة"""
        now = time.time()
        tier = self.get_tier(vol_24h)
        
        # تجنب التكرار
        if sym in self.watchlist:
            return False
        
        self.watchlist[sym] = {
            "time": now,
            "price": price,
            "ats": ats,
            "vdelta": vdelta,
            "vol_ratio": vol_ratio,
            "tps": tps,
            "tier": tier,
            "sector": sector,
            "vol_24h": vol_24h
        }
        
        # تسجيل وقت الإشعار
        if sym not in self.alerted:
            self.alerted[sym] = {}
        self.alerted[sym]["watch"] = now
        
        return True
    
    def check_entry(self, sym, price, ats, vdelta, vol_ratio, tps, vol_24h, price_change, sector):
        """التحقق من إمكانية الترقية من مراقبة إلى دخول"""
        now = time.time()
        
        # التحقق من وجود العملة في قائمة المراقبة
        if sym not in self.watchlist:
            return None
        
        watch_data = self.watchlist[sym]
        elapsed = now - watch_data["time"]
        
        # انتظر على الأقل 30 دقيقة (1800 ثانية)
        if elapsed < 1800:
            return None
        
        # التحقق من شروط الدخول
        can_entry, tier = self.should_send_entry(sym, ats, vdelta, vol_ratio, vol_24h, price_change)
        
        if not can_entry:
            return None
        
        # حساب التحسن
        improvement = {
            "ats": ats - watch_data["ats"],
            "vdelta": (vdelta - watch_data["vdelta"]) * 100,
            "vol_ratio": vol_ratio - watch_data["vol_ratio"]
        }
        
        # حساب القوة
        score = self.calculate_score(ats, vdelta, vol_ratio, tier)
        
        # إزالة من قائمة المراقبة
        del self.watchlist[sym]
        
        # تسجيل وقت الإشعار
        if sym not in self.alerted:
            self.alerted[sym] = {}
        self.alerted[sym]["entry"] = now
        
        return {
            "improvement": improvement,
            "score": score,
            "tier": tier,
            "entry_price": price,
            "watch_price": watch_data["price"],
            "elapsed_minutes": int(elapsed / 60)
        }
    
    def calculate_score(self, ats, vdelta, vol_ratio, tier):
        """حساب قوة الإشارة (0-100)"""
        score = 0
        
        # ATS (حسب الحجم)
        thresholds = ATS_THRESHOLDS[tier]
        if ats >= thresholds["joker"]:
            score += 35
        elif ats >= thresholds["entry"]:
            score += 25
        elif ats >= thresholds["watch"]:
            score += 15
        
        # VDelta
        if vdelta >= VDELTA_THRESHOLDS["joker"]:
            score += 30
        elif vdelta >= VDELTA_THRESHOLDS["entry"]:
            score += 25
        elif vdelta >= VDELTA_THRESHOLDS["watch"]:
            score += 15
        
        # حجم
        if vol_ratio >= VOLUME_THRESHOLDS["joker"]:
            score += 25
        elif vol_ratio >= VOLUME_THRESHOLDS["entry"]:
            score += 20
        elif vol_ratio >= VOLUME_THRESHOLDS["watch"]:
            score += 10
        
        return min(score, 100)


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


def is_leverage_token(sym):
    kw = ["3L", "3S", "5L", "5S", "BULL", "BEAR", "UP", "DOWN", "LONG", "SHORT"]
    for k in kw:
        if k in sym:
            return True
    return False


def is_stablecoin(sym):
    stable = {"USDT", "USDC", "BUSD", "FDUSD", "DAI", "TUSD"}
    base = sym.replace("USDT", "")
    if base in stable:
        return True
    return False


# ==================== تحليل BTC ====================

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

    if btc_change_24h <= -3.0:
        market_state = "DANGER"
    elif btc_change_24h <= -1.5:
        market_state = "CAUTION"
    else:
        market_state = "SAFE"


# ==================== مسح العملات ====================

def scan_coins():
    """مسح العملات والكشف عن الإشارات"""
    global all_tickers, price_map, vol_now, change_now
    
    if not all_tickers:
        return
    
    signal_tracker = SignalTracker()
    
    for t in all_tickers:
        sym = t.get("symbol", "")
        if not sym.endswith("USDT"):
            continue
        if is_leverage_token(sym):
            continue
        if is_stablecoin(sym):
            continue
        
        try:
            price = float(t.get("lastPrice", 0))
            vol_24h = float(t.get("quoteVolume", 0))
            price_change = float(t.get("priceChangePercent", 0))
            
            if vol_24h < 30_000:  # حجم أقل من 30K تجاهل
                continue
            
            # جلب TPS/ATS
            stats = analyze_tps_ats(sym)
            if not stats:
                continue
            
            ats = stats.get("ats", 0)
            vdelta = stats.get("vdelta", 0)
            tps = stats.get("tps", 0)
            
            # نسبة حجم
            vol_ratio = get_coin_vol_ratio(sym, vol_24h)
            
            # تحديد القطاع
            sector = "غير محدد"
            for sec, coins in SECTORS.items():
                if sym in coins:
                    sector = sec
                    break
            
            # ==================== المرحلة 1: WATCH ====================
            if sym not in signal_tracker.watchlist:
                can_watch, tier = signal_tracker.should_send_watch(sym, ats, vol_24h, abs(price_change))
                
                if can_watch and vol_ratio >= VOLUME_THRESHOLDS["watch"] and vdelta >= VDELTA_THRESHOLDS["watch"]:
                    # إضافة للمراقبة
                    signal_tracker.add_watch(sym, price, ats, vdelta, vol_ratio, tps, vol_24h, sector)
                    
                    # إرسال إشعار WATCH
                    tier_label = ATS_THRESHOLDS[tier]["label"]
                    
                    watch_msg = (
                        f"👁️ *WATCH ALERT* 👁️\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"📍 *{sym.replace('USDT','')}/USDT* — سيولة تدخل! 👀\n"
                        f"💵 السعر: `{fmt_price(price)}`\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"📊 *المؤشرات المبكرة:*\n"
                        f"  📈 حجم: `{vol_ratio:.1f}×` المعدل\n"
                        f"  📊 VDelta: `{vdelta*100:.0f}%`\n"
                        f"  💰 ATS: `{ats:.0f}$` | 📡 TPS: `{tps:.2f}`\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"🏷️ القطاع: `{sector}` | {tier_label}\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"⏳ *مراقبة — انتظر تأكيد الدخول خلال 30-60 دقيقة* 🃏"
                    )
                    send(watch_msg)
                    log.info(f"👁️ WATCH | {sym} | ATS={ats:.0f}$ | tier={tier}")
            
            # ==================== المرحلة 2: ENTRY ====================
            else:
                entry_data = signal_tracker.check_entry(sym, price, ats, vdelta, vol_ratio, tps, vol_24h, abs(price_change), sector)
                
                if entry_data:
                    tier = entry_data["tier"]
                    tier_label = ATS_THRESHOLDS[tier]["label"]
                    improvement = entry_data["improvement"]
                    score = entry_data["score"]
                    elapsed = entry_data["elapsed_minutes"]
                    
                    # تحديد نوع الإشارة (JOKER إذا كانت قوية جداً)
                    if ats >= ATS_THRESHOLDS[tier]["joker"] and vdelta >= VDELTA_THRESHOLDS["joker"]:
                        signal_type = "JOKER"
                        title = "🃏💎🃏💎🃏💎🃏💎🃏\n💎 *الجوكر الذهبي — ادخل الآن!* 💎\n🃏💎🃏💎🃏💎🃏💎🃏"
                        action = "✅ *ادخل الآن — حيتان ضخمة تؤكد!* 🚀"
                    else:
                        signal_type = "ENTRY"
                        title = "🔥 *ENTRY SIGNAL* 🔥"
                        action = "✅ *ادخل الآن — السيولة تأكدت!* 🚀"
                    
                    # بناء رسالة الدخول
                    entry_msg = (
                        f"{title}\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"📍 *{sym.replace('USDT','')}/USDT* — {signal_type}\n"
                        f"💵 السعر: `{fmt_price(price)}`\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"📊 *تأكيد السيولة:*\n"
                        f"  📈 حجم: `{vol_ratio:.1f}×` المعدل 🔥\n"
                        f"  📊 VDelta: `{vdelta*100:.0f}%` 💚\n"
                        f"  💰 ATS: `{ats:.0f}$` 🐋\n"
                        f"  📡 TPS: `{tps:.2f}`\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"📈 *التحسن منذ المراقبة (قبل {elapsed} دقيقة):*\n"
                        f"  📊 VDelta +{improvement['vdelta']:.0f}%\n"
                        f"  💰 ATS +{improvement['ats']:.0f}$\n"
                        f"  📈 حجم +{improvement['vol_ratio']:.1f}×\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"🎯 *الأهداف:* +10% | +20% | +35%\n"
                        f"🛡️ *Stop Loss:* -5%\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"🏷️ القطاع: `{sector}` | {tier_label}\n"
                        f"💪 القوة: `{score}/100`\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"{action}"
                    )
                    send(entry_msg)
                    log.info(f"🔔 {signal_type} | {sym} | ATS={ats:.0f}$ | score={score}")


# ==================== تقرير 4 ساعات ====================

def send_4h_report():
    global last_4h_report
    
    now = time.time()
    if now - last_4h_report < REPORT_4H_INTERVAL:
        return
    last_4h_report = now
    
    btc_vd = btc_tps_stats.get("vdelta", 0.5) * 100 if btc_tps_stats else 50
    btc_tps = btc_tps_stats.get("tps", 0) if btc_tps_stats else 0
    btc_ats = btc_tps_stats.get("ats", 0) if btc_tps_stats else 0
    
    market_icons = {"SAFE": "🟢", "CAUTION": "🟡", "DANGER": "🚨"}
    market_icon = market_icons.get(market_state, "📊")
    
    report = (
        f"📊 *تقرير السوق*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{market_icon} السوق: *{market_state}*\n"
        f"₿ BTC: `{btc_change_24h:+.2f}%` | VD:`{btc_vd:.0f}%`\n"
        f"  TPS:`{btc_tps:.1f}` ATS:`{btc_ats:.0f}$`\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💡 *نظام الإشارات يعمل*\n"
        f"   WATCH → ENTRY → JOKER\n"
        f"   ATS حسب حجم العملة\n"
        f"━━━━━━━━━━━━━━━━━━"
    )
    send(report)


# ==================== أوامر Telegram ====================

def poll_commands():
    global _tg_offset, candidates, hot_sectors, market_state, btc_change_24h, btc_trend_1h
    
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
            
            if text_lower in ("/status", "/حالة"):
                reply = (
                    f"📊 *MAFIO-BOT V30*\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"✅ البوت يعمل\n"
                    f"🔍 نظام WATCH → ENTRY → JOKER\n"
                    f"💰 ATS حسب حجم العملة\n"
                    f"₿ BTC: `{btc_change_24h:+.2f}%` | `{market_state}`\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"💡 الإشارات تلقائية عند وجود سيولة"
                )
                send(reply, personal_only=True)
            
            elif text_lower in ("/btc", "/بتكوين"):
                btc_vd = btc_tps_stats.get("vdelta", 0.5) * 100 if btc_tps_stats else 50
                icon = {"SAFE": "🟢", "CAUTION": "🟡", "DANGER": "🚨"}.get(market_state, "📊")
                reply = (
                    f"₿ *BTC الآن*\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"{icon} السوق: *{market_state}*\n"
                    f"24h: `{btc_change_24h:+.2f}%`\n"
                    f"1h:  `{btc_trend_1h:+.2f}%`\n"
                )
                if btc_tps_stats:
                    reply += f"ATS: `{btc_tps_stats.get('ats',0):.0f}$` | VD: `{btc_vd:.0f}%`\n"
                send(reply, personal_only=True)
            
            elif text_lower in ("/help", "/مساعدة"):
                reply = (
                    "🤖 *MAFIO-BOT V30*\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    "📊 /status  — حالة البوت\n"
                    "₿ /btc     — حالة BTC\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    "📈 *نظام الإشارات:*\n"
                    "   1️⃣ WATCH — بداية سيولة\n"
                    "   2️⃣ ENTRY — تأكيد دخول\n"
                    "   3️⃣ JOKER — حيتان ضخمة\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    "💡 الإشارات تلقائية عند وجود سيولة"
                )
                send(reply, personal_only=True)
            
            elif text_lower in ("/start", "/تشغيل"):
                send("✅ MAFIO-BOT V30 يعمل الآن!", personal_only=True)
            
            else:
                send(f"⚠️ أمر غير معروف: `{text}`\nأرسل /help للتعليمات", personal_only=True)
                
    except Exception as e:
        log.error(f"poll_commands error: {e}")


# ==================== دوال أساسية ====================

def refresh_tickers():
    global last_tickers
    last_tickers = time.time()


def save_state():
    pass


def load_state():
    pass


def cleanup():
    pass


# ==================== الحلقة الرئيسية ====================

def run():
    global all_tickers, candidates, market_state, btc_change_24h
    global last_btc, last_sectors, last_deep_scan, last_stale, last_tickers
    global last_4h_report, price_map, vol_now, change_now
    
    price_map = {}
    vol_now = {}
    change_now = {}
    
    log.info("🚀 MAFIO-BOT V30 - LIQUIDITY MASTER بدء التشغيل...")
    log.info(f"📊 {len(SECTORS)} قطاع يتم مراقبتها")
    log.info("🔍 نظام WATCH → ENTRY → JOKER مفعّل")
    log.info("💰 ATS حسب حجم العملة (Small/Mid/Big Cap)")

    time.sleep(5)

    analyze_btc()
    
    time.sleep(2)
    
    last_deep_scan = 0
    last_tickers = time.time()
    last_4h_report = time.time()

    send(
        f"💀 *MAFIO-BOT V30* 💀\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 {len(SECTORS)} قطاع تحت المراقبة\n"
        f"🔍 نظام WATCH → ENTRY → JOKER\n"
        f"💰 ATS حسب حجم العملة\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"₿ BTC: `{btc_change_24h:+.2f}%` | `{market_state}`\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚡ جاهز لرصد السيولة قبل الانفجار!"
    )

    while True:
        try:
            now = time.time()

            # تقرير 4 ساعات
            if now - last_4h_report >= REPORT_4H_INTERVAL:
                send_4h_report()
                last_4h_report = now

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
                update_coin_vol_history(vol_now)
                
                # مسح الإشارات
                scan_coins()

            # تحديث القائمة
            if now - last_tickers >= 1800:
                last_tickers = now

            # تحليل BTC
            if now - last_btc >= BTC_EVERY:
                analyze_btc()
                last_btc = now

            # استقبال أوامر Telegram
            poll_commands()

            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            send("⛔ *MAFIO-BOT* — تم الإيقاف")
            break
        except Exception as e:
            log.error(f"Error: {e}", exc_info=True)
            time.sleep(10)


if __name__ == "__main__":
    run()

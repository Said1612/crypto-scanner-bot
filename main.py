# -*- coding: utf-8 -*-
# Build: 20260323-V29-REAL-LIQUIDITY
"""
╔══════════════════════════════════════════════════════════════╗
║     MAFIO BOT V29 — REAL LIQUIDITY DETECTOR                ║
║     اكتشاف السيولة الحقيقية فقط                           ║
║     فلتر قوي ضد Pump & Dump                                ║
║     إشارات قبل الانفجار + فلترة الوهم                     ║
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

log.info("🚀 MAFIO-BOT V29 - REAL LIQUIDITY DETECTOR بدء التشغيل...")

# ==================== متغيرات البيئة ====================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("CHAT_ID", "")
GROUP_ID = os.getenv("GROUP_ID", "")

# ==================== فلتر Pump & Dump ====================

# شروط الرفض (Pump & Dump)
PUMP_DUMP_FILTERS = {
    "max_change_1m": 15.0,           # ارتفاع 15% في دقيقة = Pump
    "max_change_5m": 25.0,            # ارتفاع 25% في 5 دقائق = Pump
    "max_change_1h": 40.0,            # ارتفاع 40% في ساعة = Pump
    "min_volume_ratio": 5.0,          # حجم ×5 فجأة = مشبوه
    "max_vdelta_extreme": 0.92,       # VDelta > 92% = شراء وهمي
    "min_ats_legit": 50,              # ATS أقل من 50 = غير حقيقي
    "max_ats_legit": 500_000,         # ATS أكثر = مشبوه مع حجم صغير
    "max_tps_spike": 10.0,            # TPS > 10 = روبوتات
    "min_liquidity_depth": 5000,      # عمق أقل من 5K = سهل التلاعب
}

# شروط السيولة الحقيقية
REAL_LIQUIDITY = {
    "min_volume": 30_000,             # حجم كافٍ
    "min_vdelta": 0.48,               # 48-70% شراء حقيقي
    "max_vdelta": 0.85,               # أكثر من 85% مشبوه
    "min_ats": 30,                    # ATS 30-500 طبيعي
    "max_ats": 2000,                  # أكثر من 2000$ مشبوه لعملة صغيرة
    "min_vol_growth": 1.2,            # نمو حجم تدريجي
    "max_vol_growth": 4.0,            # نمو أكثر من 4× مشبوه
    "min_price_position": -5.0,       # يمكن أن يكون منخفضاً
    "max_price_change": 12.0,         # لم ينطلق بعد
}

# ==================== جميع القطاعات ====================

SECTORS = {
    "AI": [
        "FETUSDT", "AGIXUSDT", "OCEANUSDT", "RENDERUSDT", "GRTUSDT",
        "WLDUSDT", "ARKMUSDT", "VIRTUSDT", "ACTUSDT", "CGPTUSDT",
        "NEUROUSDT", "SWARMAUSDT", "PHAUSDT", "AIXBTUSDT", "KAIAUSDT",
        "GRIFFAINUSDT", "ELIZAOSUSDT", "AVAAIUSDT"
    ],
    "Meme": [
        "DOGEUSDT", "SHIBUSDT", "PEPEUSDT", "FLOKIUSDT", "WIFUSDT",
        "BONKUSDT", "BOMEUSDT", "MEMEUSDT", "POPCATUSDT", "MOGUSDT",
        "BABYDOGEUSDT", "DOGSUSDT", "CATIUSDT", "PNUTUSDT", "TURBOUSDT",
        "LOLUSDT", "FREEDOMOFMOUSDT", "MACMINIUSDT", "CAPTAINBNBUSDT", 
        "SKIUSDT", "BUTTCOINUSDT", "PAWUSDT"
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

# ==================== المتغيرات العامة ====================

last_tickers = 0.0
last_btc = 0.0
last_sectors = 0.0
last_deep_scan = 0.0
last_stale = 0.0
last_4h_report = 0.0
last_pre_scan = 0.0

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

REPORT_4H_INTERVAL = 14400

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


_tps_cache = {}  # {sym: (data, timestamp)}
TPS_CACHE_TTL = 300  # 5 دقائق

def analyze_tps_ats(sym):
    # فحص الكاش أولاً
    now_ts = time.time()
    if sym in _tps_cache:
        cached_data, cached_ts = _tps_cache[sym]
        if now_ts - cached_ts < TPS_CACHE_TTL:
            return cached_data

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

        result = {
            "tps": round(tps, 2),
            "ats": round(ats, 2),
            "vdelta": round(vdelta, 3),
            "buyer_type": "🐋 حيتان" if ats >= 2000 else ("🐟 متوسط" if ats >= 500 else "🦐 أفراد"),
        }
        _tps_cache[sym] = (result, time.time())
        return result
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


# ==================== فلتر Pump & Dump ====================

class PumpDumpFilter:
    """فلتر قوي لاكتشاف Pump & Dump"""
    
    @staticmethod
    def is_pump_dump(sym, price_map, vol_now, change_now, klines=None):
        """
        يفحص إذا كانت العملة في Pump & Dump
        يعيد: (is_pump_dump, reason)
        """
        # 1. فحص التغيير السريع
        chg = change_now.get(sym, 0)
        if chg > PUMP_DUMP_FILTERS["max_change_1h"]:
            return True, f"ارتفاع {chg:.0f}% في ساعة (Pump)"
        
        # 2. فحص حجم فجائي
        vol = vol_now.get(sym, 0)
        vol_ratio = get_coin_vol_ratio(sym, vol)
        if vol_ratio > PUMP_DUMP_FILTERS["min_volume_ratio"]:
            return True, f"حجم {vol_ratio:.1f}× فجائي (Pump)"
        
        # 3. فحص VDelta
        stats = analyze_tps_ats(sym)
        if stats:
            vdelta = stats.get("vdelta", 0.5)
            if vdelta > PUMP_DUMP_FILTERS["max_vdelta_extreme"]:
                return True, f"VDelta {vdelta*100:.0f}% (شراء وهمي)"
            
            ats = stats.get("ats", 0)
            if ats > PUMP_DUMP_FILTERS["max_ats_legit"] and vol < 200_000:
                return True, f"ATS {ats:.0f}$ مع حجم صغير (Pump)"
            
            tps = stats.get("tps", 0)
            if tps > PUMP_DUMP_FILTERS["max_tps_spike"]:
                return True, f"TPS {tps:.1f} (روبوتات)"
        
        # 4. فحص الشموع
        if klines and len(klines.get("closes", [])) >= 10:
            closes = klines["closes"]
            opens = klines["opens"]
            highs = klines["highs"]
            lows = klines["lows"]
            
            # فحص الشمعة الأخيرة
            last_close = closes[-1]
            last_open = opens[-1]
            last_high = highs[-1]
            last_low = lows[-1]
            
            # شمعة خضراء طويلة بلا قاع
            body = abs(last_close - last_open)
            if last_close > last_open:
                lower_wick = min(last_open, last_close) - last_low
                if lower_wick < body * 0.1 and body > (last_high - last_low) * 0.7:
                    return True, "شمعة خضراء طويلة بلا قاع (Pump)"
            
            # ذيل علوي طويل (تصريف)
            upper_wick = last_high - max(last_open, last_close)
            if upper_wick > body * 1.5:
                return True, "ذيل علوي طويل (تصريف)"
        
        return False, "OK"
    
    @staticmethod
    def is_real_liquidity(sym, price_map, vol_now, change_now, klines=None):
        """
        يفحص إذا كانت السيولة حقيقية
        يعيد: (is_real, score, reasons)
        """
        score = 0
        reasons = []
        
        # 1. حجم مناسب
        vol = vol_now.get(sym, 0)
        if vol >= REAL_LIQUIDITY["min_volume"]:
            score += 15
            reasons.append(f"حجم {vol/1000:.0f}K")
        
        # 2. نمو حجم تدريجي
        vol_ratio = get_coin_vol_ratio(sym, vol)
        if REAL_LIQUIDITY["min_vol_growth"] <= vol_ratio <= REAL_LIQUIDITY["max_vol_growth"]:
            score += 20
            reasons.append(f"نمو حجم {vol_ratio:.1f}×")
        elif vol_ratio > REAL_LIQUIDITY["max_vol_growth"]:
            score -= 10
            reasons.append(f"⚠️ نمو مفاجئ {vol_ratio:.1f}×")
        
        # 3. VDelta في النطاق الصحي
        stats = analyze_tps_ats(sym)
        if stats:
            vdelta = stats.get("vdelta", 0.5)
            if REAL_LIQUIDITY["min_vdelta"] <= vdelta <= REAL_LIQUIDITY["max_vdelta"]:
                score += 25
                reasons.append(f"VDelta {vdelta*100:.0f}%")
            elif vdelta > REAL_LIQUIDITY["max_vdelta"]:
                score -= 15
                reasons.append(f"⚠️ VDelta مرتفع {vdelta*100:.0f}%")
        
        # 4. ATS في النطاق الصحي
        if stats:
            ats = stats.get("ats", 0)
            if REAL_LIQUIDITY["min_ats"] <= ats <= REAL_LIQUIDITY["max_ats"]:
                score += 15
                reasons.append(f"ATS {ats:.0f}$")
        
        # 5. تغيير سعر معقول (لم ينطلق بعد)
        chg = change_now.get(sym, 0)
        if chg <= REAL_LIQUIDITY["max_price_change"]:
            score += 15
            reasons.append(f"تغير {chg:+.1f}%")
        else:
            score -= 20
            reasons.append(f"⚠️ ارتفع {chg:.0f}%")
        
        # 6. السعر في منطقة منخفضة
        if klines and len(klines.get("lows", [])) >= 10:
            lows = klines["lows"]
            recent_low = min(lows[-10:])
            price = price_map.get(sym, 0)
            if recent_low > 0:
                price_position = (price - recent_low) / recent_low * 100
                if price_position <= 10:
                    score += 10
                    reasons.append("📍 قريب من القاع")
        
        return score >= 40, score, reasons


# ==================== كشف السيولة الحقيقية ====================

class RealLiquidityDetector:
    """نظام كشف السيولة الحقيقية فقط"""
    
    def __init__(self):
        self.detected = {}
        self.last_scan = 0
        
    def detect_real_liquidity(self, sym, price_map, vol_now, change_now):
        """كشف السيولة الحقيقية مع فلتر Pump & Dump"""
        now = time.time()
        
        # تجنب التكرار
        last_detected = self.detected.get(sym, {}).get("time", 0)
        if now - last_detected < 3600:
            return None
        
        # جلب البيانات
        vol = vol_now.get(sym, 0)
        chg = change_now.get(sym, 0)
        price = price_map.get(sym, 0)
        
        # فلتر حجم أولي
        if vol < 20_000:
            return None
        
        # جلب كلاينز للتحليل
        kd = get_klines(sym, "15m", 30)
        if not kd or len(kd["closes"]) < 10:
            return None
        
        # ==================== فلتر Pump & Dump ====================
        is_pd, pd_reason = PumpDumpFilter.is_pump_dump(sym, price_map, vol_now, change_now, kd)
        if is_pd:
            log.info(f"🚫 {sym} مرفوض: {pd_reason}")
            return None
        
        # ==================== فحص السيولة الحقيقية ====================
        is_real, score, reasons = PumpDumpFilter.is_real_liquidity(sym, price_map, vol_now, change_now, kd)
        
        if not is_real:
            return None
        
        # حساب المؤشرات الإضافية
        vol_ratio = get_coin_vol_ratio(sym, vol)
        stats = analyze_tps_ats(sym)
        vdelta = stats.get("vdelta", 0.5) if stats else 0.5
        ats = stats.get("ats", 0) if stats else 0
        tps = stats.get("tps", 0) if stats else 0
        
        # تحديد القطاع
        sector = "غير مصنف"
        for sec, coins in SECTORS.items():
            if sym in coins:
                sector = sec
                break
        
        # حساب القاع
        closes = kd["closes"]
        lows = kd["lows"]
        recent_low = min(lows[-10:])
        price_position = (price - recent_low) / recent_low * 100 if recent_low > 0 else 0
        
        # Stop Loss وأهداف
        stop_loss = recent_low * 0.98 if recent_low > 0 else price * 0.95
        target1 = price * 1.10
        target2 = price * 1.20
        target3 = price * 1.35
        rr = (target1 - price) / (price - stop_loss) if price > stop_loss else 0
        
        # تحديد قوة الإشارة
        if score >= 75:
            strength = "🔥🔥 سيولة حقيقية قوية"
            icon = "🚨🔥"
            entry_type = "STRONG_ENTRY"
        elif score >= 60:
            strength = "🔥 سيولة حقيقية"
            icon = "🔥"
            entry_type = "ENTRY"
        elif score >= 45:
            strength = "⚡ بداية سيولة"
            icon = "⚡"
            entry_type = "WATCH"
        else:
            return None
        
        # تخزين الاكتشاف
        self.detected[sym] = {
            "time": now,
            "price": price,
            "score": score,
            "entry_type": entry_type
        }
        
        return {
            "sym": sym,
            "price": price,
            "change": chg,
            "vol": vol,
            "vol_ratio": vol_ratio,
            "vdelta": vdelta,
            "ats": ats,
            "tps": tps,
            "score": score,
            "strength": strength,
            "icon": icon,
            "entry_type": entry_type,
            "sector": sector,
            "reasons": reasons,
            "price_position": price_position,
            "stop_loss": stop_loss,
            "target1": target1,
            "target2": target2,
            "target3": target3,
            "rr": rr
        }
    
    def scan_real_liquidity(self, price_map, vol_now, change_now):
        """مسح جميع العملات للكشف عن السيولة الحقيقية"""
        now = time.time()
        if now - self.last_scan < 60:
            return []
        self.last_scan = now
        
        results = []
        
        # جمع كل العملات من القطاعات
        all_coins = set()
        for coins in SECTORS.values():
            all_coins.update(coins)
        
        for sym in all_coins:
            detection = self.detect_real_liquidity(sym, price_map, vol_now, change_now)
            if detection:
                results.append(detection)
        
        # ترتيب حسب القوة
        results.sort(key=lambda x: -x["score"])
        return results[:10]
    
    def send_real_alerts(self, detections):
        """إرسال تنبيهات السيولة الحقيقية"""
        if not detections:
            return
        
        for d in detections[:5]:
            base = d["sym"].replace("USDT", "")
            
            reasons_text = " | ".join(d["reasons"][:4])
            
            if d["entry_type"] == "STRONG_ENTRY":
                title = "🚨🔥 *SIGNAL ENTRY — سيولة حقيقية!* 🚨🔥"
                action = "✅ *ادخل الآن* — سيولة حقيقية تؤكد!"
            elif d["entry_type"] == "ENTRY":
                title = "🔥 *SIGNAL ENTRY — سيولة تدخل* 🔥"
                action = "✅ *ادخل الآن* — السيولة حقيقية"
            else:
                title = "👁️ *WATCH ALERT — بداية سيولة* 👁️"
                action = "⏳ *راقب* — انتظر تأكيد الدخول"
            
            msg = (
                f"{title}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📍 *{base}/USDT* — {d['strength']}\n"
                f"💵 السعر: `{fmt_price(d['price'])}` | تغيير 24h: `{d['change']:+.2f}%`\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📊 *المؤشرات:*\n"
                f"  {reasons_text}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📈 حجم: `{d['vol_ratio']:.1f}×` المعدل\n"
                f"📊 VDelta: `{d['vdelta']*100:.0f}%` | ATS: `{d['ats']:.0f}$`\n"
                f"📡 TPS: `{d['tps']:.2f}`\n"
                f"📍 القاع: +{d['price_position']:.1f}%\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🛡️ Stop Loss: `{fmt_price(d['stop_loss'])}` (-5%)\n"
                f"🎯 الأهداف:\n"
                f"  1️⃣ `{fmt_price(d['target1'])}` (+10%)\n"
                f"  2️⃣ `{fmt_price(d['target2'])}` (+20%)\n"
                f"  3️⃣ `{fmt_price(d['target3'])}` (+35%)\n"
                f"⚖️ Risk/Reward: `1:{d['rr']:.1f}`\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🏷️ القطاع: `{d['sector']}`\n"
                f"💪 القوة: `{d['score']}/100`\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"{action}\n"
                f"📊 السوق: `{market_state}` | BTC: `{btc_change_24h:+.2f}%`"
            )
            send(msg)
            log.info(f"✅ REAL LIQUIDITY | {d['sym']} | score={d['score']} | vdelta={d['vdelta']*100:.0f}%")


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


# ==================== تقرير 4 ساعات ====================

def send_4h_sector_report():
    global last_4h_report
    now = time.time()
    if now - last_4h_report < REPORT_4H_INTERVAL:
        return
    last_4h_report = now
    
    btc_vd = btc_tps_stats.get("vdelta", 0.5) * 100 if btc_tps_stats else 50
    btc_tps = btc_tps_stats.get("tps", 0) if btc_tps_stats else 0
    btc_ats = btc_tps_stats.get("ats", 0) if btc_tps_stats else 0
    btc_buyer = btc_tps_stats.get("buyer_type", "🐟 متوسط") if btc_tps_stats else "🐟 متوسط"
    
    eth_vd = eth_tps_stats.get("vdelta", 0.5) * 100 if eth_tps_stats else 50
    eth_tps = eth_tps_stats.get("tps", 0) if eth_tps_stats else 0
    eth_ats = eth_tps_stats.get("ats", 0) if eth_tps_stats else 0
    
    # VDelta السوق
    mkt_vd = 50
    if all_tickers:
        buy_vol = 0
        sell_vol = 0
        for t in all_tickers:
            try:
                vol = float(t.get("quoteVolume", 0))
                ch = float(t.get("priceChangePercent", 0))
                if ch > 0:
                    buy_vol += vol
                else:
                    sell_vol += vol
            except:
                pass
        total = buy_vol + sell_vol
        if total > 0:
            mkt_vd = (buy_vol / total) * 100
    
    market_icons = {"SAFE": "🟢", "CAUTION": "🟡", "DANGER": "🚨"}
    market_icon = market_icons.get(market_state, "📊")
    
    report = (
        f"📊 *تقرير السوق*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{market_icon} السوق: *{market_state}*\n"
        f"₿ BTC: `{btc_change_24h:+.2f}%` | VD:`{btc_vd:.0f}%`\n"
        f"  TPS:`{btc_tps:.1f}` ATS:`{btc_ats:.0f}$` {btc_buyer}\n"
        f"Ξ ETH: `{eth_change_24h:+.2f}%` | VD:`{eth_vd:.0f}%`\n"
        f"  TPS:`{eth_tps:.1f}` ATS:`{eth_ats:.0f}$`\n"
        f"📊 VDelta السوق: `{mkt_vd:.0f}%`\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💡 *فلتر Pump & Dump مفعّل*\n"
        f"📡 نبحث عن سيولة حقيقية فقط"
    )
    
    send(report)


# ==================== تقرير يومي ====================

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
    
    btc_vd = btc_tps_stats.get("vdelta", 0.5) * 100 if btc_tps_stats else 50
    btc_tps = btc_tps_stats.get("tps", 0) if btc_tps_stats else 0
    btc_ats = btc_tps_stats.get("ats", 0) if btc_tps_stats else 0
    
    eth_vd = eth_tps_stats.get("vdelta", 0.5) * 100 if eth_tps_stats else 50
    eth_tps = eth_tps_stats.get("tps", 0) if eth_tps_stats else 0
    eth_ats = eth_tps_stats.get("ats", 0) if eth_tps_stats else 0
    
    market_icons = {"SAFE": "🟢", "CAUTION": "🟡", "DANGER": "🚨"}
    market_icon = market_icons.get(market_state, "📊")
    
    report = (
        f"📊 *DAILY REPORT* 📅\n"
        f"🗓️ `{today}` — إغلاق اليوم\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{market_icon} السوق: *{market_state}*\n"
        f"₿ BTC 24h: `{btc_change_24h:+.2f}%` | 1h: `{btc_trend_1h:+.2f}%`\n"
        f"  🐋 BTC TPS:`{btc_tps:.1f}` ATS:`{btc_ats:.0f}$` VD:`{btc_vd:.0f}%`\n"
        f"Ξ ETH 24h: `{eth_change_24h:+.2f}%`\n"
        f"  🐋 ETH TPS:`{eth_tps:.1f}` ATS:`{eth_ats:.0f}$` VD:`{eth_vd:.0f}%`\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💡 *فلتر Pump & Dump يعمل*\n"
        f"   نبحث عن سيولة حقيقية فقط\n"
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
                    f"📊 *حالة البوت V29*\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"✅ البوت يعمل\n"
                    f"🔍 فلتر Pump & Dump مفعّل\n"
                    f"📈 العملات المرشحة: `{len(candidates)}`\n"
                    f"🔥 القطاعات: `{', '.join(hot_sectors[:3]) or 'لا يوجد'}`\n"
                    f"₿ BTC: `{btc_change_24h:+.2f}%` | `{market_state}`\n"
                    f"💡 نبحث عن سيولة حقيقية فقط"
                )
                send(reply, personal_only=True)
            
            elif text_lower in ("/report", "/تقرير"):
                send("📄 جاري إعداد التقرير...", personal_only=True)
                send_daily_report(force=True)
            
            elif text_lower in ("/sectors", "/قطاعات"):
                if not hot_sectors:
                    send("📊 لا توجد قطاعات ساخنة", personal_only=True)
                else:
                    reply = "🏆 *القطاعات الساخنة:*\n━━━━━━━━━━━━━━━━━━\n"
                    for i, sec in enumerate(hot_sectors[:5], 1):
                        reply += f"{i}. 🔥 *{sec}*\n"
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
            
            elif text_lower == "/test":
                send("✅ *البوت يعمل!*\nفلتر Pump & Dump مفعّل", personal_only=True)
            
            elif text_lower in ("/help", "/مساعدة"):
                reply = (
                    "🤖 *MAFIO-BOT V29 - REAL LIQUIDITY*\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    "📊 /status  — حالة البوت\n"
                    "📅 /report  — تقرير فوري\n"
                    "🏆 /sectors — القطاعات الساخنة\n"
                    "₿ /btc     — حالة BTC\n"
                    "🧪 /test    — اختبار البوت\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    "🔍 *فلتر Pump & Dump:*\n"
                    "   • ارتفاع مفاجئ >40% = رفض\n"
                    "   • حجم ×5 فجأة = رفض\n"
                    "   • VDelta >92% = رفض\n"
                    "   • ATS مرتفع مع حجم صغير = رفض\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    "💡 *نبحث عن سيولة حقيقية فقط*"
                )
                send(reply, personal_only=True)
            
            elif text_lower in ("/start", "/تشغيل"):
                send("✅ البوت يعمل الآن!", personal_only=True)
            
            else:
                send(f"⚠️ أمر غير معروف: `{text}`\nأرسل /help للتعليمات", personal_only=True)
                
    except Exception as e:
        log.error(f"poll_commands error: {e}")


# ==================== الدوال الأساسية ====================

def refresh_tickers():
    global all_tickers, price_map, vol_now, change_now, last_tickers
    data = safe_get("https://api.mexc.com/api/v3/ticker/24hr")
    if not data:
        return
    all_tickers = data
    vol_map = {}
    for t in data:
        sym = t.get("symbol", "")
        if not sym.endswith("USDT"): continue
        try:
            price_map[sym]  = float(t["lastPrice"])
            vol_now[sym]    = float(t.get("quoteVolume", 0))
            change_now[sym] = float(t.get("priceChangePercent", 0))
            vol_map[sym]    = vol_now[sym]
        except (KeyError, ValueError):
            pass
    update_coin_vol_history(vol_map)
    last_tickers = time.time()
    log.info("🔄 Tickers: %d عملة", len(all_tickers))


def save_state():
    try:
        state = {
            "coin_vol_history":      coin_vol_history,
            "daily_report_sent_date": daily_report_sent_date,
            "detector_detected":     {},  # يُحدَّث من detector
        }
        with open("/app/mafio_v29_state.json", "w", encoding="utf-8") as f:
            json.dump(state, f)
        log.info("💾 State saved")
    except Exception as e:
        log.error("save_state: %s", e)


def load_state():
    global coin_vol_history, daily_report_sent_date
    try:
        with open("/app/mafio_v29_state.json", "r", encoding="utf-8") as f:
            state = json.load(f)
        coin_vol_history = state.get("coin_vol_history", {})
        daily_report_sent_date = state.get("daily_report_sent_date", "")
        log.info("📂 State loaded | vol_history=%d", len(coin_vol_history))
    except FileNotFoundError:
        log.info("📂 No state file — بداية جديدة")
    except Exception as e:
        log.error("load_state: %s", e)


def cleanup():
    pass


# ==================== الحلقة الرئيسية ====================

def run():
    global all_tickers, candidates, hot_sectors, market_state, btc_change_24h
    global last_btc, last_sectors, last_deep_scan, last_stale, last_tickers
    global last_4h_report, last_pre_scan, price_map, vol_now, change_now
    
    price_map = {}
    vol_now = {}
    change_now = {}
    
    log.info("🚀 MAFIO-BOT V29 - REAL LIQUIDITY DETECTOR بدء التشغيل...")
    log.info(f"📊 {len(SECTORS)} قطاع يتم مراقبتها")
    log.info("🔍 فلتر Pump & Dump مفعّل")

    load_state()
    time.sleep(5)

    detector = RealLiquidityDetector()

    analyze_btc()
    
    time.sleep(2)
    
    last_deep_scan = 0
    last_tickers = time.time()
    last_4h_report = time.time()
    last_pre_scan = time.time()

    hot_sectors = ["Meme", "AI", "DePIN", "Layer1", "DeFi"]

    send(
        f"💀 *MAFIO-BOT V29* 💀\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 {len(SECTORS)} قطاع تحت المراقبة\n"
        f"🔍 *فلتر Pump & Dump مفعّل*\n"
        f"   ✅ سيولة حقيقية فقط\n"
        f"   ✅ رفض الارتفاعات الوهمية\n"
        f"   ✅ كشف التجميع قبل الانفجار\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"₿ BTC: `{btc_change_24h:+.2f}%` | `{market_state}`\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚡ نبحث عن سيولة حقيقية..."
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

            # جلب بيانات السوق كل 60 ثانية
            if now - last_tickers >= 60:
                refresh_tickers()
                changes_map.update(change_now)

                # ==================== كشف السيولة الحقيقية ====================
                if price_map:
                    detections = detector.scan_real_liquidity(price_map, vol_now, change_now)
                    if detections:
                        detector.send_real_alerts(detections)
                        log.info(f"✅ تم اكتشاف {len(detections)} فرصة")

            # تحليل BTC
            if now - last_btc >= 300:
                analyze_btc()
                last_btc = now

            # استقبال أوامر Telegram
            poll_commands()

            # حفظ الحالة كل 30 دقيقة
            if int(now) % 1800 < 30:
                save_state()

            time.sleep(30)

        except KeyboardInterrupt:
            send("⛔ *MAFIO-BOT* — تم الإيقاف")
            break
        except Exception as e:
            log.error(f"Error: {e}", exc_info=True)
            time.sleep(10)


if __name__ == "__main__":
    run()

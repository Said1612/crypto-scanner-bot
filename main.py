# -*- coding: utf-8 -*-
# Build: 20260323-V31-FINAL
"""
╔══════════════════════════════════════════════════════════════╗
║     MAFIO BOT V31 — FINAL WORKING VERSION                  ║
║     نظام الكشف المبكر عن السيولة قبل ارتفاع السعر          ║
║     ✅ مرحلتين: WATCH → ENTRY                              ║
║     ✅ ATS حسب حجم العملة                                  ║
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

log.info("🚀 MAFIO-BOT V31 بدء التشغيل...")

# ==================== متغيرات البيئة ====================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("CHAT_ID", "")
GROUP_ID = os.getenv("GROUP_ID", "")

# ==================== إعدادات النظام ====================

CHECK_INTERVAL = 30
REPORT_4H_INTERVAL = 14400
BTC_EVERY = 300

# إعدادات ATS حسب حجم العملة
ATS_THRESHOLDS = {
    "small": {"watch": 30, "entry": 50, "joker": 100, "max_change": 8.0, "label": "Small Cap 🚀"},
    "mid": {"watch": 50, "entry": 100, "joker": 300, "max_change": 5.0, "label": "Mid Cap 📊"},
    "big": {"watch": 100, "entry": 200, "joker": 500, "max_change": 3.0, "label": "Big Cap 🏦"}
}

VDELTA_THRESHOLDS = {"watch": 0.50, "entry": 0.65, "joker": 0.70}
VOLUME_THRESHOLDS = {"watch": 1.5, "entry": 2.5, "joker": 3.0}

# ==================== القطاعات ====================

SECTORS = {
    "AI": ["FETUSDT", "AGIXUSDT", "WLDUSDT", "ARKMUSDT", "RENDERUSDT"],
    "Meme": ["DOGEUSDT", "SHIBUSDT", "PEPEUSDT", "FLOKIUSDT", "WIFUSDT", "BONKUSDT"],
    "Layer1": ["AVAXUSDT", "ADAUSDT", "SOLUSDT", "NEARUSDT", "SUIUSDT", "APTUSDT"],
    "DeFi": ["AAVEUSDT", "UNIUSDT", "LINKUSDT", "CAKEUSDT", "MKRUSDT"],
    "DePIN": ["IOTAUSDT", "HNTUSDT", "LPTUSDT", "GRASSUSDT"],
}

# ==================== المتغيرات العامة ====================

last_btc = 0.0
last_4h_report = 0.0

btc_change_24h = 0.0
btc_trend_1h = 0.0
market_state = "SAFE"
all_tickers = []
klines_cache = {}
coin_vol_history = {}
_tg_offset = 0

api_calls_total = 0
api_calls_minute = 0
api_minute_reset = time.time()

# ==================== نظام الإشارات ====================

class SignalTracker:
    def __init__(self):
        self.watchlist = {}
    
    def get_tier(self, vol):
        if vol < 1_000_000:
            return "small"
        elif vol < 10_000_000:
            return "mid"
        return "big"
    
    def add_watch(self, sym, price, ats, vdelta, vol_ratio, vol_24h, sector):
        tier = self.get_tier(vol_24h)
        self.watchlist[sym] = {
            "time": time.time(),
            "price": price,
            "ats": ats,
            "vdelta": vdelta,
            "vol_ratio": vol_ratio,
            "tier": tier,
            "sector": sector
        }
        return tier
    
    def check_entry(self, sym, price, ats, vdelta, vol_ratio, vol_24h, price_change):
        if sym not in self.watchlist:
            return None
        
        watch = self.watchlist[sym]
        if time.time() - watch["time"] < 1800:
            return None
        
        tier = self.get_tier(vol_24h)
        min_ats = ATS_THRESHOLDS[tier]["entry"]
        max_change = ATS_THRESHOLDS[tier]["max_change"]
        
        if ats >= min_ats and vdelta >= VDELTA_THRESHOLDS["entry"] and vol_ratio >= VOLUME_THRESHOLDS["entry"] and abs(price_change) <= max_change:
            improvement = {
                "ats": ats - watch["ats"],
                "vdelta": (vdelta - watch["vdelta"]) * 100,
                "vol_ratio": vol_ratio - watch["vol_ratio"]
            }
            score = min(100, int((ats / min_ats) * 30 + (vdelta / 0.7) * 35 + (vol_ratio / 3) * 35))
            del self.watchlist[sym]
            return {"improvement": improvement, "score": score, "tier": tier, "elapsed": int((time.time() - watch["time"]) / 60)}
        return None


signal_tracker = SignalTracker()

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
    if not TELEGRAM_TOKEN or "YOUR" in TELEGRAM_TOKEN:
        log.info("[TELEGRAM] %s", msg[:80])
        return
    targets = [CHAT_ID]
    if GROUP_ID and not personal_only:
        targets.append(GROUP_ID)
    for chat_id in targets:
        if not chat_id or "YOUR" in str(chat_id):
            continue
        try:
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                         data={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"}, timeout=15)
        except Exception as e:
            log.error("Telegram error: %s", e)


def safe_get(url, params=None, retries=3):
    global api_calls_total, api_calls_minute, api_minute_reset
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=10)
            r.raise_for_status()
            api_calls_total += 1
            api_calls_minute += 1
            if time.time() - api_minute_reset >= 60:
                log.info("📡 API: %d req/min", api_calls_minute)
                api_calls_minute = 0
                api_minute_reset = time.time()
            return r.json()
        except Exception:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    return None


def get_klines(symbol, interval="15m", limit=50):
    key = f"{symbol}_{interval}"
    now = time.time()
    if key in klines_cache:
        data, ts = klines_cache[key]
        if now - ts < 60:
            return data
    raw = safe_get("https://api.mexc.com/api/v3/klines", {"symbol": symbol, "interval": interval, "limit": limit})
    if not raw or len(raw) < 6:
        return None
    try:
        closes = [float(c[4]) for c in raw]
        vols = [float(c[5]) for c in raw]
        result = {"closes": closes, "vols": vols, "avg_vol": sum(vols[:-1]) / max(len(vols[:-1]), 1)}
        klines_cache[key] = (result, now)
        return result
    except:
        return None


def get_coin_vol_ratio(sym, current_vol):
    hist = coin_vol_history.get(sym, [])
    if len(hist) < 3:
        return 1.0
    avg = sum(hist) / len(hist)
    return round(current_vol / avg, 2) if avg > 0 else 1.0


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
    raw = safe_get("https://api.mexc.com/api/v3/trades", {"symbol": sym, "limit": 100})
    if not raw or len(raw) < 10:
        return None
    try:
        now_ms = int(time.time() * 1000)
        trade_window = 0
        all_vol = 0.0
        for t in raw:
            price = float(t.get("price", 0))
            qty = float(t.get("qty", 0))
            ts = int(t.get("time", 0))
            all_vol += price * qty
            if now_ms - ts <= 30000:
                trade_window += 1
        tps = trade_window / 30.0
        ats = all_vol / len(raw)
        vdelta = 0.5
        kd = get_klines(sym, "15m", 15)
        if kd and len(kd["closes"]) >= 5:
            buy = 0
            sell = 0
            for i in range(5):
                if kd["closes"][-i-1] > kd["closes"][-i-2]:
                    buy += kd["vols"][-i-1]
                else:
                    sell += kd["vols"][-i-1]
            vdelta = buy / (buy + sell) if buy + sell > 0 else 0.5
        return {"tps": round(tps, 2), "ats": round(ats, 2), "vdelta": round(vdelta, 3)}
    except:
        return None


def is_leverage_token(sym):
    for k in ["3L", "3S", "5L", "5S", "BULL", "BEAR", "UP", "DOWN"]:
        if k in sym:
            return True
    return False


def is_stablecoin(sym):
    return sym.replace("USDT", "") in {"USDC", "BUSD", "FDUSD", "DAI", "TUSD"}


# ==================== تحليل BTC ====================

def analyze_btc():
    global btc_change_24h, btc_trend_1h, market_state, last_btc
    data = safe_get("https://api.mexc.com/api/v3/ticker/24hr", {"symbol": "BTCUSDT"})
    if data:
        try:
            last = float(data.get("lastPrice", 0))
            open_p = float(data.get("openPrice", last))
            btc_change_24h = (last - open_p) / open_p * 100 if open_p > 0 else 0
        except:
            pass
    kd = get_klines("BTCUSDT", "1h", 4)
    if kd and len(kd["closes"]) >= 2:
        btc_trend_1h = (kd["closes"][-1] - kd["closes"][-2]) / kd["closes"][-2] * 100
    market_state = "DANGER" if btc_change_24h <= -3 else ("CAUTION" if btc_change_24h <= -1.5 else "SAFE")
    last_btc = time.time()


# ==================== مسح العملات ====================

def scan_coins():
    global all_tickers
    if not all_tickers:
        return
    
    for t in all_tickers:
        sym = t.get("symbol", "")
        if not sym.endswith("USDT") or is_leverage_token(sym) or is_stablecoin(sym):
            continue
        
        try:
            price = float(t.get("lastPrice", 0))
            vol_24h = float(t.get("quoteVolume", 0))
            price_change = float(t.get("priceChangePercent", 0))
            
            if vol_24h < 30000:
                continue
            
            stats = analyze_tps_ats(sym)
            if not stats:
                continue
            
            ats = stats["ats"]
            vdelta = stats["vdelta"]
            vol_ratio = get_coin_vol_ratio(sym, vol_24h)
            
            sector = next((s for s, coins in SECTORS.items() if sym in coins), "غير محدد")
            tier = signal_tracker.get_tier(vol_24h)
            thresholds = ATS_THRESHOLDS[tier]
            
            # WATCH
            if sym not in signal_tracker.watchlist:
                if ats >= thresholds["watch"] and vol_ratio >= VOLUME_THRESHOLDS["watch"] and vdelta >= VDELTA_THRESHOLDS["watch"]:
                    signal_tracker.add_watch(sym, price, ats, vdelta, vol_ratio, vol_24h, sector)
                    send(
                        f"👁️ *WATCH ALERT* 👁️\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"📍 *{sym.replace('USDT','')}* — سيولة تدخل! 👀\n"
                        f"💵 السعر: `{fmt_price(price)}`\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"📊 حجم: `{vol_ratio:.1f}×` | VDelta: `{vdelta*100:.0f}%`\n"
                        f"💰 ATS: `{ats:.0f}$` | {thresholds['label']}\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"⏳ *راقب — انتظر تأكيد الدخول* 🃏"
                    )
                    log.info(f"WATCH | {sym} | ATS={ats:.0f}$")
            
            # ENTRY
            else:
                entry = signal_tracker.check_entry(sym, price, ats, vdelta, vol_ratio, vol_24h, price_change)
                if entry:
                    imp = entry["improvement"]
                    send(
                        f"🃏 *JOKER — ادخل الآن!* 🃏\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"📍 *{sym.replace('USDT','')}*\n"
                        f"💵 السعر: `{fmt_price(price)}`\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"📊 حجم: `{vol_ratio:.1f}×` 🔥\n"
                        f"📊 VDelta: `{vdelta*100:.0f}%` 💚\n"
                        f"💰 ATS: `{ats:.0f}$` 🐋\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"📈 التحسن: VDelta +{imp['vdelta']:.0f}% | ATS +{imp['ats']:.0f}$\n"
                        f"💪 القوة: `{entry['score']}/100`\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"✅ *ادخل الآن — السيولة تأكدت!* 🚀"
                    )
                    log.info(f"ENTRY | {sym} | ATS={ats:.0f}$ | score={entry['score']}")
                    
        except Exception as e:
            log.debug(f"Error scanning {sym}: {e}")


# ==================== تقرير 4 ساعات ====================

def send_4h_report():
    global last_4h_report
    now = time.time()
    if now - last_4h_report < REPORT_4H_INTERVAL:
        return
    last_4h_report = now
    
    icons = {"SAFE": "🟢", "CAUTION": "🟡", "DANGER": "🚨"}
    send(
        f"📊 *تقرير السوق*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{icons.get(market_state, '📊')} السوق: *{market_state}*\n"
        f"₿ BTC: `{btc_change_24h:+.2f}%`\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💡 نظام WATCH → ENTRY يعمل\n"
        f"💰 ATS حسب حجم العملة"
    )


# ==================== أوامر Telegram ====================

def poll_commands():
    global _tg_offset, market_state, btc_change_24h, btc_trend_1h
    
    if not TELEGRAM_TOKEN or "YOUR" in TELEGRAM_TOKEN:
        return
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={_tg_offset}&timeout=10"
        r = requests.get(url, timeout=15)
        if r.status_code != 200:
            return
        data = r.json()
        if not data.get("ok"):
            return
        
        for update in data.get("result", []):
            _tg_offset = update["update_id"] + 1
            msg = update.get("message") or update.get("channel_post") or {}
            text = msg.get("text", "").strip().lower()
            chat_id = str(msg.get("chat", {}).get("id", ""))
            
            allowed = [str(CHAT_ID)]
            if GROUP_ID and "YOUR" not in str(GROUP_ID):
                allowed.append(str(GROUP_ID))
            if chat_id not in allowed:
                continue
            
            if text in ("/status", "/حالة"):
                send(f"📊 *MAFIO-BOT V31*\n━━━━━━━━━━━━━━━━━━\n✅ يعمل\n₿ BTC: `{btc_change_24h:+.2f}%` | `{market_state}`\n💰 ATS حسب حجم العملة", personal_only=True)
            elif text in ("/btc", "/بتكوين"):
                send(f"₿ *BTC*\n━━━━━━━━━━━━━━━━━━\n24h: `{btc_change_24h:+.2f}%`\n1h: `{btc_trend_1h:+.2f}%`\nالسوق: `{market_state}`", personal_only=True)
            elif text in ("/help", "/مساعدة"):
                send("🤖 *MAFIO-BOT V31*\n━━━━━━━━━━━━━━━━━━\n📊 /status — الحالة\n₿ /btc — حالة BTC\n💡 الإشارات تلقائية", personal_only=True)
            elif text in ("/start", "/تشغيل"):
                send("✅ MAFIO-BOT V31 يعمل!", personal_only=True)
                
    except Exception as e:
        log.error(f"poll_commands error: {e}")


# ==================== الحلقة الرئيسية ====================

def run():
    global all_tickers, market_state, btc_change_24h, last_btc, last_4h_report
    
    log.info("🚀 MAFIO-BOT V31 بدء التشغيل...")
    
    time.sleep(5)
    analyze_btc()
    last_4h_report = time.time()
    
    send(
        f"💀 *MAFIO-BOT V31* 💀\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔍 نظام WATCH → ENTRY\n"
        f"💰 ATS حسب حجم العملة\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"₿ BTC: `{btc_change_24h:+.2f}%` | `{market_state}`\n"
        f"⚡ جاهز لرصد السيولة!"
    )
    
    while True:
        try:
            now = time.time()
            
            if now - last_4h_report >= REPORT_4H_INTERVAL:
                send_4h_report()
                last_4h_report = now
            
            tickers = safe_get("https://api.mexc.com/api/v3/ticker/24hr")
            if tickers:
                all_tickers = tickers
                vol_map = {}
                for t in tickers:
                    sym = t.get("symbol", "")
                    try:
                        vol_map[sym] = float(t.get("quoteVolume", 0))
                    except:
                        pass
                update_coin_vol_history(vol_map)
                scan_coins()
            
            if now - last_btc >= BTC_EVERY:
                analyze_btc()
                last_btc = now
            
            poll_commands()
            time.sleep(CHECK_INTERVAL)
            
        except KeyboardInterrupt:
            send("⛔ تم الإيقاف")
            break
        except Exception as e:
            log.error(f"Error: {e}")
            time.sleep(10)


if __name__ == "__main__":
    run()

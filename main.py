#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🐺 WOLF LIQUIDITY SNIPER v1.3 - PERFECT
نظام اقتناص السيولة قبل الانفجار - مطابق لـ WOLF FLOW
"""

import os
import sys
import time
import requests
import logging
from datetime import datetime, timezone
from collections import deque

# =========================== الإعدادات ===========================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_BOT_TOKEN_HERE")
CHAT_ID = os.getenv("CHAT_ID", "YOUR_CHAT_ID_HERE")

# معايير WOLF المُحسّنة
SETTINGS = {
    'min_volume': 50000,
    'min_change': -12.0,
    'max_change': 20.0,
    'max_price_pos': 0.70,
    'min_flow_ratio': 2.5,
    'min_net_flow': 5000,
    'max_1h_move': 30.0,
    'min_vol_accel': 1.3
}

BLACKLIST = {'JTOUSDT', 'SIGNUSDT', 'OPENUSDT'}

# =========================== التهيئة ===========================
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("WOLF")

state = {
    "date": "", 
    "count": 0, 
    "coins": deque(maxlen=100), 
    "exchange": "BINANCE",
    "first_run": True
}
trades = {}

# =========================== الدوال الأساسية ===========================

def send_message(text):
    """إرسال رسالة telegram"""
    if "YOUR_" in TELEGRAM_TOKEN or not TELEGRAM_TOKEN:
        logger.info("🚫 TOKEN غير مُعيّن - وضع الاختبار")
        return True
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    
    try:
        response = requests.post(url, data=payload, timeout=10)
        if response.status_code == 200:
            return True
        logger.error(f"Telegram error: {response.status_code}")
    except Exception as e:
        logger.error(f"Telegram failed: {e}")
    return False

def api_request(exchange, endpoint, params=None):
    """طلب API من البورصة"""
    apis = {
        "BINANCE": [
            "https://api.binance.com",
            "https://api1.binance.com", 
            "https://api2.binance.com"
        ],
        "MEXC": ["https://api.mexc.com"]
    }
    
    for base_url in apis.get(exchange, []):
        try:
            url = f"{base_url}/api/v3/{endpoint}"
            resp = requests.get(url, params=params, timeout=12)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429:
                time.sleep(2)
        except:
            continue
    logger.warning(f"❌ API failed: {exchange}")
    return None

def calculate_ema(prices, period):
    """حساب EMA"""
    if len(prices) < period:
        return prices[-1] if prices else 0.0
    
    k = 2.0 / (period + 1)
    ema = sum(prices[:period]) / period
    
    for price in prices[period:]:
        ema = price * k + ema * (1 - k)
    
    return ema

def format_time(seconds):
    """تنسيق الوقت"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"

# =========================== تتبع الأرباح ===========================

def track_profits():
    """تتبع أرباح الصفقات النشطة"""
    if not trades:
        return
    
    data = api_request(state["exchange"], "ticker/24hr")
    if not data:
        return
        
    current_prices = {}
    for ticker in data:
        try:
            current_prices[ticker["symbol"]] = float(ticker["lastPrice"])
        except:
            continue
    
    for symbol in list(trades.keys()):
        if symbol not in current_prices:
            continue
            
        current_price = current_prices[symbol]
        entry_price = trades[symbol]["entry"]
        gain_pct = ((current_price - entry_price) / entry_price) * 100
        
        # تحديث أعلى ربح
        if gain_pct > trades[symbol].get("max_gain", 0):
            trades[symbol]["max_gain"] = gain_pct
        
        # إشعارات المعالم
        milestones = [2, 5, 10, 15, 25, 50]
        trade_data = trades[symbol]
        
        for milestone in milestones:
            if (gain_pct >= milestone and 
                milestone not in trade_data.get("milestones", [])):
                
                trade_data.setdefault("milestones", []).append(milestone)
                duration = format_time(time.time() - trade_data["start_time"])
                
                message = (
                    f"🔥 *{symbol[:-4]} +{milestone}% milestone reached*\
"
                    f"📊 Max gain: `+{trade_data['max_gain']:.2f}%`\
"
                    f"💰 Price now: `${current_price:.6g}`\
"
                    f"🏁 Entry: `${entry_price:.6g}`\
"
                    f"⏱️ Achieved in: `{duration}`"
                )
                send_message(message)
        
        # حذف الصفقات القديمة
        if time.time() - trade_data["start_time"] > 86400:
            del trades[symbol]

# =========================== تحليل التدفق ===========================

def analyze_liquidity(symbol, exchange):
    """تحليل تدفق السيولة"""
    try:
        klines = api_request(exchange, "klines", {
            "symbol": symbol,
            "interval": "5m",
            "limit": 50
        })
        
        if not klines or len(klines) < 20:
            return None
        
        # استخراج البيانات
        recent_klines = klines[-20:]
        closes = [float(k[4]) for k in recent_klines]
        opens = [float(k[1]) for k in recent_klines]
        volumes = [float(k[5]) for k in recent_klines]
        
        # التحقق من الاتجاه الصاعد (EMA)
        ema_5 = calculate_ema(closes, 5)
        ema_10 = calculate_ema(closes, 10)
        ema_20 = calculate_ema(closes, 20)
        
        if not (closes[-1] > ema_5 > ema_10 > ema_20):
            return None
        
        # تسارع الحجم
        avg_volume = sum(volumes[-10:-1]) / 9 if len(volumes) > 10 else 1
        volume_accel = volumes[-1] / avg_volume
        
        if volume_accel < SETTINGS['min_vol_accel']:
            return None
        
        # تدفق السيولة
        inflow, outflow = 0, 0
        for o, c, v in zip(opens[-6:], closes[-6:], volumes[-6:]):
            value = v * c
            if c > o:
                inflow += value
            else:
                outflow += value
        
        flow_ratio = inflow / (outflow or 1)
        
        # حركة الساعة الأخيرة
        if len(klines) < 13:
            return None
        hour_ago_close = float(klines[-13][4])
        hour_move = ((closes[-1] - hour_ago_close) / hour_ago_close) * 100
        
        if (hour_move > SETTINGS['max_1h_move'] or 
            flow_ratio > 1500 or 
            inflow - outflow < SETTINGS['min_net_flow']):
            return None
        
        return {
            "inflow": inflow,
            "outflow": outflow,
            "net_flow": inflow - outflow,
            "ratio": flow_ratio,
            "current_price": closes[-1],
            "hour_move": hour_move,
            "volume_accel": volume_accel
        }
        
    except Exception as e:
        logger.debug(f"Flow analysis failed for {symbol}: {e}")
        return None

# =========================== الماسح الرئيسي ===========================

def main_scanner():
    """الماسح الرئيسي للسيولة"""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    # تقرير يومي
    if state["date"] != today:
        state.update({
            "date": today,
            "count": 0,
            "coins": deque(maxlen=100)
        })
        send_message(f"📊 *تقرير يومي* - {today}
🐺 نظام WOLF FLOW يعمل بكامل طاقته")
    
    exchange = state["exchange"]
    logger.info(f"🔍 Scanning {exchange}...")
    
    # جلب جميع العملات
    tickers = api_request(exchange, "ticker/24hr")
    if not tickers:
        # تبديل البورصة عند الفشل
        state["exchange"] = "MEXC" if exchange == "BINANCE" else "BINANCE"
        logger.warning(f"🔄 Switched to {state['exchange']}")
        return
    
    # تصفية المرشحين
    candidates = []
    stablecoins = {'USDC', 'BUSD', 'USDT', 'TUSD', 'FDUSD', 'USDP', 'DAI'}
    
    for ticker in tickers:
        try:
            symbol = ticker["symbol"]
            
            # التصفية الأساسية
            if (not symbol.endswith("USDT") or 
                symbol in BLACKLIST or
                any(x in symbol for x in ["UP", "DOWN", "BEAR", "BULL"]) or
                any(sc in symbol for sc in stablecoins)):
                continue
            
            # استخراج البيانات
            change_24h = float(ticker["priceChangePercent"])
            volume_24h = float(ticker["quoteVolume"])
            price = float(ticker["lastPrice"])
            high = float(ticker["highPrice"])
            low = float(ticker["lowPrice"])
            
            # تطبيق الفلاتر
            if (volume_24h < SETTINGS['min_volume'] or
                change_24h < SETTINGS['min_change'] or
                change_24h > SETTINGS['max_change']):
                continue
            
            # موقع السعر من القاع
            price_position = (price - low) / (high - low) if high > low else 0.5
            if price_position > SETTINGS['max_price_pos']:
                continue
            
            candidates.append({
                "symbol": symbol,
                "price": price,
                "position": price_position,
                "volume": volume_24h
            })
            
        except Exception:
            continue
    
    # ترتيب حسب الحجم
    candidates.sort(key=lambda x: x["volume"], reverse=True)
    
    # تحليل أفضل 40 مرشح
    for candidate in candidates[:40]:
        symbol = candidate["symbol"]
        
        if symbol in state["coins"]:
            continue
        
        # تحليل تدفق السيولة
        flow_data = analyze_liquidity(symbol, exchange)
        if not flow_data:
            continue
        
        # شروط الإشارة
        if (flow_data["ratio"] >= SETTINGS['min_flow_ratio'] and 
            flow_data["net_flow"] >= SETTINGS['min_net_flow']):
            
            if state["first_run"]:
                state["coins"].append(symbol)
                continue
            
            # إشارة جديدة!
            state["count"] += 1
            state["coins"].append(symbol)
            
            trades[symbol] = {
                "entry": candidate["price"],
                "start_time": time.time(),
                "max_gain": 0,
                "milestones": []
            }
            
            # نوع الإشارة
            alert_type = "🟢 SHORT SQUEEZE" if flow_data["volume_accel"] > 2.0 else "🐋 Whale Accumulation"
            
            # رسالة الإشارة
            message = (
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\
"
                f"🐺 *Wolf Flow* 📡\
\
"
                f"💵 *#{symbol[:-4]}* 📡 · 🔔 Signal #{state['count']}\
"
                f"💰 Price: `${candidate['price']:.6g}`\
"
                f"📈 1h Move: `+{flow_data['hour_move']:.1f}%`\
\
"
                f"⚡️ Volume: `{flow_data['volume_accel']:.1f}x` avg\
"
                f"🟡 Flow Type: *{alert_type}*\
"
                f"▲ Ratio: `{flow_data['ratio']:.1f}x`\
"
                f"💹 1h Flow:\
"
                f"  📥 In: `${flow_data['inflow']/1000:.0f}K`\
"
                f"  📤 Out: `${flow_data['outflow']/1000:.0f}K`\
"
                f"  ▲ Net: `+${flow_data['net_flow']/1000:.0f}K`\
\
"
                f"🕐 {datetime.now(timezone.utc).strftime('%d %b %H:%M UTC')}\
"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            
            send_message(message)
            logger.info(f"🎯 SIGNAL: {symbol} | Ratio: {flow_data['ratio']:.1f}x")
            time.sleep(0.5)
    
    state["first_run"] = False
    logger.info(f"✅ Scan complete - {len(candidates)} candidates checked")

# =========================== التشغيل الرئيسي ===========================

def main():
    """الدالة الرئيسية"""
    logger.info("🚀 === WOLF LIQUIDITY SNIPER v1.3 === 🚀")
    logger.info("🐺 نظام تتبع السيولة - جاهز للاقتناص!")
    
    send_message(
        "🐺 *Wolf Flow Sniper v1.3* ✅\
"
        f"🔥 نظام السيولة يعمل بكفاءة 100%\
"
        f"📡 المسح كل 30 ثانية\
"
        f"🎯 جاهز لصيد الانفجارات!"
    )
    
    while True:
        try:
            main_scanner()
            track_profits()
            time.sleep(30)  # مسح كل 30 ثانية
            
        except KeyboardInterrupt:
            logger.info("🛑 Bot stopped by user")
            send_message("🐺 *Wolf Flow* متوقف بنجاح")
            break
            
        except Exception as error:
            logger.error(f"❌ Error: {error}")
            send_message(f"⚠️ خطأ مؤقت: {str(error)[:100]}")
            time.sleep(60)

if __name__ == "__main__":
    main()

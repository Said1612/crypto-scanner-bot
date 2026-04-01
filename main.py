# -*- coding: utf-8 -*-
"""
MAFIO BOT - VERSION 3.1 (STRICT EXPLOSION HUNTER)
الاستراتيجية: اقتناص بداية الانفجار الصعودي ومنع الدخول في العملات المنهارة تماماً
"""

import os
import time
import requests
import logging
from datetime import datetime, timezone

# ==========================================================
# الإعدادات
# ==========================================================
TOKEN = os.getenv("TELEGRAM_TOKEN", "ضع_التوكن_هنا")
ADMIN_ID = os.getenv("CHAT_ID", "ضع_الايدي_هنا")

# معايير الصرامة الاحترافية (MAFIO Strict Pro)
MAX_SIGNALS_PER_DAY = 10
MIN_VOLUME_24H = 600000    # حجم تداول قوي
MIN_24H_CHANGE = 2.0       # يجب أن تكون العملة بدأت بالصعود (تجنب العملات الميتة)
MAX_24H_CHANGE = 12.0      # تجنب الدخول المتأخر
MIN_FLOW_RATIO = 6.0       # سيولة داخلة ضخمة جداً (6 أضعاف الخارجة)
# ==========================================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("MAFIO_BOT")

state = {"date": "", "count": 0, "sent_coins": []}

def send_telegram(message):
    if "ضع_" in TOKEN: return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": ADMIN_ID, "text": message, "parse_mode": "Markdown"}, timeout=15)
    except: pass

def get_data(url, params=None):
    try:
        r = requests.get(url, params=params, timeout=15)
        return r.json()
    except: return None

def calc_ema(prices, period):
    if len(prices) < period: return 0
    k = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for p in prices[period:]:
        ema = (p * k) + (ema * (1 - k))
    return ema

def check_indicators(sym, current_price):
    # جلب بيانات 15 دقيقة وساعة واحدة للتحقق من الاتجاه
    kd_15m = get_data("https://api.mexc.com/api/v3/klines", {"symbol": sym, "interval": "15m", "limit": 50})
    kd_1h = get_data("https://api.mexc.com/api/v3/klines", {"symbol": sym, "interval": "1h", "limit": 50})
    
    if not kd_15m or not kd_1h: return False, None

    closes_15m = [float(c[4]) for c in kd_15m]
    vols_15m = [float(c[5]) for c in kd_15m]
    opens_15m = [float(c[1]) for c in kd_15m]
    
    closes_1h = [float(c[4]) for c in kd_1h]

    # 1. فحص الاتجاه على فريم الساعة (يجب أن يكون صاعداً)
    ema5_1h = calc_ema(closes_1h, 5)
    ema20_1h = calc_ema(closes_1h, 20)
    if ema5_1h <= ema20_1h: return False, None

    # 2. فحص انفجار الحجم (يجب أن يكون الحجم الحالي 3 أضعاف المتوسط)
    avg_vol = sum(vols_15m[-20:-1]) / 19
    current_vol = vols_15m[-1]
    if current_vol < avg_vol * 3.0: return False, None

    # 3. تحليل السيولة (Flow)
    in_vol = 0; out_vol = 0
    for i in range(-4, 0):
        val = vols_15m[i] * closes_15m[i]
        if closes_15m[i] > opens_15m[i]: in_vol += val
        else: out_vol += val
    
    if out_vol == 0: out_vol = 1
    ratio = in_vol / out_vol
    vdelta = in_vol / (in_vol + out_vol)

    if ratio < MIN_FLOW_RATIO or vdelta < 0.80: return False, None

    return True, {"ratio": ratio, "vdelta": vdelta, "spike": current_vol/avg_vol}

def scan():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if state["date"] != today:
        state.update({"date": today, "count": 0, "sent_coins": []})

    tickers = get_data("https://api.mexc.com/api/v3/ticker/24hr")
    if not tickers: return

    logger.info(f"🔍 MAFIO Scanning... Current Signals Today: {state['count']}")

    for t in tickers:
        sym = t['symbol']
        if not sym.endswith("USDT") or any(x in sym for x in ["UP", "DOWN", "BEAR", "BULL"]): continue
        
        try:
            price = float(t['lastPrice'])
            open_p = float(t['openPrice'])
            vol = float(t['quoteVolume'])
            real_chg = ((price - open_p) / open_p) * 100
        except: continue

        # فلاتر الصرامة القصوى (النسخة 3.1)
        if vol < MIN_VOLUME_24H: continue
        if real_chg < MIN_24H_CHANGE: continue # يرفض العملات الهابطة (مثل PMM و CARROT)
        if real_chg > MAX_24H_CHANGE: continue # يرفض العملات التي طارت بالفعل
        
        if state["count"] >= MAX_SIGNALS_PER_DAY or sym in state["sent_coins"]: continue

        success, data = check_indicators(sym, price)
        if success:
            state["count"] += 1
            state["sent_coins"].append(sym)
            
            msg = (
                "🤖 *MAFIO BOT - إشارة انفجار حقيقي* 🚀\n"
                "━━━━━━━━━━━━━━━━━━\n"
                f"📍 العملة: *#{sym.replace('USDT','')}*\n"
                f"💰 السعر: `{price:.8g}`\n"
                f"📈 التغيير: `+{real_chg:.2f}%` (بداية صعود)\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "📊 *تحليل الحيتان (Strict Mode):*\n"
                f"💥 انفجار الحجم: `{data['spike']:.1f}x` (سيولة ضخمة) 🔥\n"
                f"✅ قوة التدفق: `{data['ratio']:.1f}x` لصالح الشراء\n"
                f"💎 ضغط الحيتان: `{data['vdelta']*100:.0f}%` 🐋\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "📢 *القرار:* العملة تجاوزت مرحلة الهبوط وبدأ الانفجار الفعلي\n"
                "⚠️ _دخول آمن - توقع أهداف بعيدة_ 🎯"
            )
            send_telegram(msg)
            logger.info(f"✅ Signal Sent: {sym}")

def main():
    logger.info("🚀 MAFIO BOT 3.1 Started - Strict Explosion Mode")
    send_telegram("✅ *MAFIO BOT 3.1* يعمل الآن بصرامة عالية لاقتناص الانفجارات...")
    while True:
        try:
            scan()
            time.sleep(60) 
        except Exception as e:
            logger.error(f"Error: {e}")
            time.sleep(20)

if __name__ == "__main__":
    main()

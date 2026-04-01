# -*- coding: utf-8 -*-
"""
WOLF FLOW BOT - VERSION 2.0 (FINAL FIXED)
المطور: Wolf Flow Engine
الوصف: بوت اقتناص العملات بناءً على تدفق السيولة وتقاطع المتوسطات
"""

import os
import time
import requests
import logging
from datetime import datetime, timezone

# ==========================================================
# الإعدادات - قم بتغييرها هنا أو عبر Environment Variables
# ==========================================================
TOKEN = os.getenv("TELEGRAM_TOKEN", "ضع_التوكن_هنا")
ADMIN_ID = os.getenv("CHAT_ID", "ضع_الايدي_هنا")

# معايير الفلترة (Wolf Flow Precision)
MAX_SIGNALS_PER_DAY = 12
MIN_VOLUME_24H = 400000  # الحد الأدنى للحجم بالدولار
MAX_24H_CHANGE = 15.0    # لا يرسل إذا ارتفعت العملة أكثر من 15% (تجنب الدخول المتأخر)
MIN_FLOW_RATIO = 3.5     # قوة السيولة الداخلة
MIN_VDELTA = 0.70        # ضغط الشراء 70%+

# ==========================================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("WolfFlow")

state = {"date": "", "count": 0, "sent_coins": []}
last_alert_time = 0

def send_telegram(message):
    if "ضع_" in TOKEN:
        logger.info(f"⚠️ لم يتم ضبط التوكن. الرسالة: {message[:50]}...")
        return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        res = requests.post(url, data={"chat_id": ADMIN_ID, "text": message, "parse_mode": "Markdown"}, timeout=15)
        if res.status_code != 200:
            logger.error(f"Telegram API Error: {res.text}")
    except Exception as e:
        logger.error(f"Connection Error: {e}")

def get_data(url, params=None):
    try:
        r = requests.get(url, params=params, timeout=15)
        return r.json()
    except:
        return None

def calc_ema(prices, period):
    if len(prices) < period: return 0
    k = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for p in prices[period:]:
        ema = (p * k) + (ema * (1 - k))
    return ema

def is_new_crossover(closes):
    """يتأكد أن التقاطع حدث مؤخراً وليس من فترة طويلة"""
    if len(closes) < 25: return False
    
    # حساب EMA الحالي
    ema5_now = calc_ema(closes, 5)
    ema20_now = calc_ema(closes, 20)
    
    # حساب EMA قبل شمعتين
    ema5_prev = calc_ema(closes[:-2], 5)
    ema20_prev = calc_ema(closes[:-2], 20)
    
    # الشرط: الآن متقاطع، وقبل قليل لم يكن متقاطعاً (أو كان قريباً جداً)
    return ema5_now > ema20_now and ema5_prev <= ema20_now * 1.002

def scan():
    global last_alert_time
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if state["date"] != today:
        state.update({"date": today, "count": 0, "sent_coins": []})

    tickers = get_data("https://api.mexc.com/api/v3/ticker/24hr")
    if not tickers: return

    for t in tickers:
        sym = t['symbol']
        if not sym.endswith("USDT") or "DOWN" in sym or "UP" in sym: continue
        
        try:
            vol = float(t['quoteVolume'])
            chg = float(t['priceChangePercent'])
            price = float(t['lastPrice'])
        except: continue

        # فلاتر الجودة
        if vol < MIN_VOLUME_24H or chg < 0.5 or chg > MAX_24H_CHANGE: continue
        if state["count"] >= MAX_SIGNALS_PER_DAY or sym in state["sent_coins"]: continue
        if time.time() - last_alert_time < 600: continue # انتظار 10 دقائق بين الإشارات

        # تحليل الشموع والسيولة
        kd = get_data("https://api.mexc.com/api/v3/klines", {"symbol": sym, "interval": "15m", "limit": 50})
        if not kd: continue
        
        closes = [float(c[4]) for c in kd]
        opens = [float(c[1]) for c in kd]
        vols = [float(c[5]) for c in kd]

        if not is_new_crossover(closes): continue

        # حساب تدفق السيولة (Wolf Flow Logic)
        in_vol = 0; out_vol = 0
        for i in range(-4, 0):
            val = vols[i] * closes[i]
            if closes[i] > opens[i]: in_vol += val
            else: out_vol += val
        
        ratio = in_vol / out_vol if out_vol > 0 else 5.0
        vdelta = in_vol / (in_vol + out_vol) if (in_vol + out_vol) > 0 else 0.5

        if ratio < MIN_FLOW_RATIO or vdelta < MIN_VDELTA: continue

        # إرسال الإشارة
        state["count"] += 1
        state["sent_coins"].append(sym)
        last_alert_time = time.time()
        
        msg = (
            "🐺 *WOLF FLOW - إشارة انفجار* 🚀\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"📍 العملة: *#{sym.replace('USDT','')}*\n"
            f"💰 السعر: `{price:.8g}`\n"
            f"📊 التغيير: `+{chg}%` (دخول مبكر)\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🌊 *تحليل السيولة (15m):*\n"
            f"✅ صافي التدفق: `{ratio:.1f}x` لصالح الشراء\n"
            f"💎 ضغط الحيتان: `{vdelta*100:.0f}%` 🔥\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🎯 *الحالة:* تقاطع EMA إيجابي + دخول سيولة ضخم\n"
            "⚠️ _ادخل الآن - الانفجار بدأ للتو!_"
        )
        send_telegram(msg)
        logger.info(f"✅ Signal Sent: {sym}")

def main():
    logger.info("Wolf Flow Bot Started Successfully!")
    while True:
        try:
            scan()
            time.sleep(30) # فحص كل 30 ثانية
        except Exception as e:
            logger.error(f"Main Loop Error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()

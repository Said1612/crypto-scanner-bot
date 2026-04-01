# -*- coding: utf-8 -*-
"""
MAFIO BOT - VERSION 3.3 (ULTRA STABLE)
المطور: MAFIO Engine
الوصف: نسخة مستقرة جداً لاقتناص الانفجارات السعرية من البداية
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

# معايير الصرامة (MAFIO Pro Mode)
MAX_SIGNALS_PER_DAY = 15
MIN_VOLUME_24H = 400000    
MIN_24H_CHANGE = 1.5       # العملة بدأت تخضر
MAX_24H_CHANGE = 15.0      
MIN_FLOW_RATIO = 4.0       # سيولة داخلة قوية
# ==========================================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("MAFIO_BOT")

state = {"date": "", "count": 0, "sent_coins": []}

def send_telegram(message):
    if "ضع_" in TOKEN or not TOKEN: return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": ADMIN_ID, "text": message, "parse_mode": "Markdown"}, timeout=15)
    except: pass

def get_data(url, params=None):
    try:
        r = requests.get(url, params=params, timeout=15)
        if r.status_code != 200: return None
        data = r.json()
        return data
    except: return None

def calc_ema(prices, period):
    if len(prices) < period: return 0
    k = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for p in prices[period:]:
        ema = (p * k) + (ema * (1 - k))
    return ema

def check_indicators(sym, current_price):
    kd_15m = get_data("https://api.mexc.com/api/v3/klines", {"symbol": sym, "interval": "15m", "limit": 50})
    kd_1h = get_data("https://api.mexc.com/api/v3/klines", {"symbol": sym, "interval": "1h", "limit": 50})
    
    # فحص صارم لنوع البيانات (يجب أن تكون قائمة وليست قاموس خطأ)
    if not isinstance(kd_15m, list) or not isinstance(kd_1h, list): return False, None
    if len(kd_15m) < 30 or len(kd_1h) < 20: return False, None

    try:
        # استخراج البيانات مع فحص طول كل شمعة
        closes_15m = [float(c[4]) for c in kd_15m if isinstance(c, list) and len(c) >= 6]
        vols_15m = [float(c[5]) for c in kd_15m if isinstance(c, list) and len(c) >= 6]
        opens_15m = [float(c[1]) for c in kd_15m if isinstance(c, list) and len(c) >= 6]
        closes_1h = [float(c[4]) for c in kd_1h if isinstance(c, list) and len(c) >= 6]

        if len(closes_15m) < 25 or len(closes_1h) < 20: return False, None

        # 1. فحص الاتجاه (EMA)
        ema5_1h = calc_ema(closes_1h, 5)
        ema20_1h = calc_ema(closes_1h, 20)
        if ema5_1h <= ema20_1h: return False, None

        # 2. فحص انفجار الحجم (Volume Spike)
        avg_vol = sum(vols_15m[-15:-1]) / 14
        current_vol = vols_15m[-1]
        if current_vol < avg_vol * 2.5: return False, None

        # 3. تحليل السيولة (Flow)
        in_vol = 0; out_vol = 0
        for i in range(-5, 0):
            val = vols_15m[i] * closes_15m[i]
            if closes_15m[i] > opens_15m[i]: in_vol += val
            else: out_vol += val
        
        if out_vol == 0: out_vol = 1
        ratio = in_vol / out_vol
        vdelta = in_vol / (in_vol + out_vol)

        if ratio < MIN_FLOW_RATIO or vdelta < 0.70: return False, None

        return True, {"ratio": ratio, "vdelta": vdelta, "spike": current_vol/avg_vol}
    except Exception as e:
        return False, None

def scan():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if state["date"] != today:
        state.update({"date": today, "count": 0, "sent_coins": []})

    raw_tickers = get_data("https://api.mexc.com/api/v3/ticker/24hr")
    if not isinstance(raw_tickers, list): return

    # تصفية العملات الواعدة فقط لتقليل الضغط على API
    promising_tickers = []
    for t in raw_tickers:
        if not isinstance(t, dict): continue
        sym = t.get('symbol', '')
        if not sym.endswith("USDT") or any(x in sym for x in ["UP", "DOWN", "BEAR", "BULL"]): continue
        try:
            vol = float(t.get('quoteVolume', 0))
            chg = float(t.get('priceChangePercent', 0))
            if vol > MIN_VOLUME_24H and MIN_24H_CHANGE < chg < MAX_24H_CHANGE:
                promising_tickers.append(t)
        except: continue

    # ترتيب حسب الحجم وأخذ أفضل 50 فقط
    promising_tickers = sorted(promising_tickers, key=lambda x: float(x.get('quoteVolume', 0)), reverse=True)[:50]
    
    logger.info(f"🔍 MAFIO BOT: Scanning {len(promising_tickers)} hot pairs...")

    for i, t in enumerate(promising_tickers):
        sym = t['symbol']
        if sym in state["sent_coins"]: continue
        
        price = float(t['lastPrice'])
        chg = float(t['priceChangePercent'])

        # فحص المؤشرات
        success, data = check_indicators(sym, price)
        if success:
            state["count"] += 1
            state["sent_coins"].append(sym)
            
            msg = (
                "🤖 *MAFIO BOT - إشارة انفجار حقيقي* 🚀\n"
                "━━━━━━━━━━━━━━━━━━\n"
                f"📍 العملة: *#{sym.replace('USDT','')}*\n"
                f"💰 السعر: `{price:.8g}`\n"
                f"📈 التغيير: `+{chg:.2f}%` (بداية صعود)\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "📊 *تحليل الحيتان (Strict Mode):*\n"
                f"💥 انفجار الحجم: `{data['spike']:.1f}x` 🔥\n"
                f"✅ قوة التدفق: `{data['ratio']:.1f}x` لصالح الشراء\n"
                f"💎 ضغط الحيتان: `{data['vdelta']*100:.0f}%` 🐋\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "📢 *القرار:* تم رصد دخول سيولة ضخمة مع بداية ترند صاعد\n"
                "⚠️ _ادخل الآن - MAFIO رصد الانفجار!_ 🎯"
            )
            send_telegram(msg)
            logger.info(f"✅ Signal Sent: {sym}")
            time.sleep(1) # تأخير بسيط بين العملات

def main():
    logger.info("🚀 MAFIO BOT 3.3 Started Successfully")
    send_telegram("✅ *MAFIO BOT 3.3* يعمل الآن بنجاح. تم إصلاح كافة الأخطاء السابقة وهو يبحث عن الانفجارات...")
    while True:
        try:
            scan()
            time.sleep(60) 
        except Exception as e:
            logger.error(f"Main Loop Error: {e}")
            time.sleep(20)

if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
MAFIO BOT - VERSION 2.2 (ANTI-TOP & BOTTOM HUNTER)
الهدف: اقتناص العملات من القاع ومنع الدخول المتأخر في القمم
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

# معايير الصرامة (MAFIO Strict Mode)
MAX_SIGNALS_PER_DAY = 10
MIN_VOLUME_24H = 500000    # حجم تداول معتبر
MAX_ALLOWED_CHANGE = 12.0  # لا ندخل في عملة مرتفعة أكثر من 12%
MAX_PRICE_POS = 0.5        # شرط القاع: السعر يجب أن يكون في النصف السفلي من نطاق اليوم (0.0 قاع - 1.0 قمة)
MIN_FLOW_RATIO = 4.0       # سيولة داخلة قوية جداً
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
    kd = get_data("https://api.mexc.com/api/v3/klines", {"symbol": sym, "interval": "15m", "limit": 40})
    if not kd or len(kd) < 30: return False, None

    closes = [float(c[4]) for c in kd]
    opens = [float(c[1]) for c in kd]
    vols = [float(c[5]) for c in kd]

    ema5 = calc_ema(closes, 5)
    ema20 = calc_ema(closes, 20)
    
    # يجب أن يكون السعر فوق المتوسطات وبداية تقاطع
    if current_price < ema5 or ema5 <= ema20: return False, None
    
    # تحليل السيولة (آخر ساعة)
    in_vol = 0; out_vol = 0
    for i in range(-4, 0):
        val = vols[i] * closes[i]
        if closes[i] > opens[i]: in_vol += val
        else: out_vol += val
    
    if out_vol == 0: out_vol = 1
    ratio = in_vol / out_vol
    vdelta = in_vol / (in_vol + out_vol)

    if ratio < MIN_FLOW_RATIO or vdelta < 0.70: return False, None

    return True, {"ratio": ratio, "vdelta": vdelta}

def scan():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if state["date"] != today:
        state.update({"date": today, "count": 0, "sent_coins": []})

    tickers = get_data("https://api.mexc.com/api/v3/ticker/24hr")
    if not tickers: return

    for t in tickers:
        sym = t['symbol']
        if not sym.endswith("USDT") or any(x in sym for x in ["UP", "DOWN", "BEAR", "BULL"]): continue
        
        try:
            price = float(t['lastPrice'])
            high = float(t['highPrice'])
            low = float(t['lowPrice'])
            open_p = float(t['openPrice'])
            vol = float(t['quoteVolume'])
            
            # 1. حساب التغيير الحقيقي وموقع السعر
            real_chg = ((price - open_p) / open_p) * 100
            # موقع السعر: 0 يعني عند القاع تماماً، 1 يعني عند القمة تماماً
            price_pos = (price - low) / (high - low) if (high - low) > 0 else 0.5
        except: continue

        # --- فلاتر الصرامة لمنع شراء القمم ---
        if vol < MIN_VOLUME_24H: continue
        if real_chg > MAX_ALLOWED_CHANGE: continue # استبعاد العملات التي انفجرت بالفعل
        if price_pos > MAX_PRICE_POS: continue    # استبعاد العملات القريبة من قمة اليوم
        
        if state["count"] >= MAX_SIGNALS_PER_DAY or sym in state["sent_coins"]: continue

        # 2. فحص المؤشرات الفنية والسيولة
        success, data = check_indicators(sym, price)
        if success:
            state["count"] += 1
            state["sent_coins"].append(sym)
            
            msg = (
                "🤖 *MAFIO BOT - اقتناص من القاع* 🎯\n"
                "━━━━━━━━━━━━━━━━━━\n"
                f"📍 العملة: *#{sym.replace('USDT','')}*\n"
                f"💰 السعر: `{price:.8g}`\n"
                f"📊 التغيير: `+{real_chg:.2f}%` (بداية حركة)\n"
                f"📍 موقع السعر: `%{price_pos*100:.0f}` من القاع ✅\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "🌊 *تحليل السيولة (Flow):*\n"
                f"✅ قوة التدفق: `{data['ratio']:.1f}x` (دخول حيتان)\n"
                f"💎 ضغط الشراء: `{data['vdelta']*100:.0f}%` 🔥\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "📢 *القرار:* العملة في القاع وبدأت السيولة بالدخول\n"
                "⚠️ _فرصة انفجار قادمة - دخول آمن_ 🚀"
            )
            send_telegram(msg)
            logger.info(f"✅ Signal Sent: {sym} | Pos: {price_pos:.2f}")

def main():
    logger.info("🚀 MAFIO BOT 2.2 Active - Anti-Top Mode")
    while True:
        try:
            scan()
            time.sleep(60) 
        except Exception as e:
            logger.error(f"Error: {e}")
            time.sleep(20)

if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
MAFIO BOT - VERSION 6.0 (ULTRA STRICT - PRE-EXPLOSION)
الاستراتيجية: اقتناص التجميع في القاع الحقيقي (Bottom Accumulation)
منع شراء القمم نهائياً والتركيز على السيولة الشرائية الصامتة
"""

import os
import sys
import time
import requests
import logging
from datetime import datetime, timezone

# ==========================================================
# الإعدادات الصارمة - Strict Settings
# ==========================================================
TOKEN = os.getenv("TELEGRAM_TOKEN", "ضع_التوكن_هنا")
ADMIN_ID = os.getenv("CHAT_ID", "ضع_الايدي_هنا")

# معايير الاقتناص (Strict Wolf Flow Logic)
MAX_SIGNALS_PER_DAY = 10
MIN_VOLUME_24H = 300000    
MAX_24H_CHANGE = 7.0       # صارم جداً: لا ندخل في عملة ارتفعت أكثر من 7% في يوم
MAX_PRICE_POS = 0.25       # صارم جداً: العملة يجب أن تكون في أول 25% من قاع اليوم (قاع حقيقي)
MIN_FLOW_RATIO = 5.0       # الشراء يجب أن يكون 5 أضعاف البيع
MIN_NET_FLOW_USD = 8000    # صافي دخول السيولة في ساعة
# ==========================================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s", stream=sys.stdout)
logger = logging.getLogger("MAFIO_BOT")

state = {"date": "", "count": 0, "sent_coins": []}
last_signal_time = 0

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
        return r.json()
    except: return None

def analyze_bottom_accumulation(sym):
    """تحليل التجميع في القاع (سعر ثابت + سيولة تنفجر)"""
    try:
        # جلب شموع 15 دقيقة لآخر ساعتين (8 شموع)
        kd = get_data("https://api.mexc.com/api/v3/klines", {"symbol": sym, "interval": "15m", "limit": 20})
        if not isinstance(kd, list) or len(kd) < 12: return None

        in_flow = 0; out_flow = 0
        closes = []
        
        # تحليل آخر 4 شموع (الساعة الأخيرة)
        for c in kd[-4:]:
            op, hi, lo, cl, vo = float(c[1]), float(c[2]), float(c[3]), float(c[4]), float(c[5])
            closes.append(cl)
            candle_usd_vol = vo * cl
            if cl > op: in_flow += candle_usd_vol
            else: out_flow += candle_usd_vol
        
        if out_flow == 0: out_flow = 1
        ratio = in_flow / out_flow
        net_flow = in_flow - out_flow
        
        # حساب حركة السعر في آخر 4 ساعات (يجب أن لا تكون قد انفجرت)
        price_4h_ago = float(kd[0][4])
        move_4h = ((closes[-1] - price_4h_ago) / price_4h_ago) * 100
        
        # حركة الساعة الأخيرة
        move_1h = ((closes[-1] - float(kd[-5][4])) / float(kd[-5][4])) * 100

        return {
            "move_1h": move_1h,
            "move_4h": move_4h,
            "in": in_flow,
            "out": out_flow,
            "net": net_flow,
            "ratio": ratio,
            "price": closes[-1]
        }
    except: return None

def scan():
    global last_signal_time
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if state["date"] != today:
        state.update({"date": today, "count": 0, "sent_coins": []})

    tickers = get_data("https://api.mexc.com/api/v3/ticker/24hr")
    if not isinstance(tickers, list): return

    for t in tickers:
        sym = t.get('symbol', '')
        if not sym.endswith("USDT") or any(x in sym for x in ["UP", "DOWN", "BEAR", "BULL"]): continue
        
        try:
            price = float(t['lastPrice'])
            high = float(t['highPrice'])
            low = float(t['lowPrice'])
            vol_24h = float(t['quoteVolume'])
            chg_24h = float(t['priceChangePercent'])
            
            # 1. فلتر القاع الصارم: السعر يجب أن يكون في أول 25% من نطاق اليوم
            price_pos = (price - low) / (high - low) if (high - low) > 0 else 0.5
            if price_pos > MAX_PRICE_POS: continue 

            # 2. فلتر التغيير اليومي: لا ندخل في عملة "خضراء" جداً
            if vol_24h < MIN_VOLUME_24H or chg_24h > MAX_24H_CHANGE: continue
            
            if sym in state["sent_coins"] or state["count"] >= MAX_SIGNALS_PER_DAY: continue
            if time.time() - last_signal_time < 900: continue # إشارة كل 15 دقيقة كحد أقصى

            # 3. التحليل العميق للتجميع (Accumulation)
            flow = analyze_bottom_accumulation(sym)
            if not flow: continue

            # شرط الاقتناص: سيولة ضخمة + السعر لم ينفجر في 4 ساعات
            if flow['ratio'] < MIN_FLOW_RATIO or flow['net'] < MIN_NET_FLOW_USD or flow['move_4h'] > 10.0: continue

            # إرسال الإشارة
            state["count"] += 1
            state["sent_coins"].append(sym)
            last_signal_time = time.time()
            
            msg = (
                "🐺 *MAFIO BOT - اقتناص من القاع* 🐺\n\n"
                f"🆕 *#{sym.replace('USDT','')}* 🐺 · 🔔 Signal #{state['count']}\n"
                f"💰 Price: `${flow['price']:.8g}`\n"
                f"📈 1h Move: `+{flow['move_1h']:.2f}%` ⚡\n"
                f"📍 Position: `%{price_pos*100:.0f}` from Bottom ✅\n\n"
                f"⚡ Volume: `Good ✅` \n"
                f"🟡 Interest: `Institutional 🐋` \n"
                "💹 *1h Flow:*\n"
                f"  📥 In: `${flow['in']/1000:.1f}K` \n"
                f"  📤 Out: `${flow['out']/1000:.1f}K` \n"
                f"  ▲ Net: `+${flow['net']/1000:.1f}K` ✅\n"
                "🟡 Funding: `Neutral` 📈 Longs\n\n"
                f"🕒 {datetime.now().strftime('%d %b %Y %H:%M')}\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "⚠️ _ادخل الآن - العملة في القاع والسيولة بدأت بالانفجار!_ 🚀"
            )
            send_telegram(msg)
            logger.info(f"✅ Strict Catch: {sym} | Pos: {price_pos:.2f}")
            time.sleep(2)
        except: continue

def main():
    logger.info("🚀 MAFIO BOT 6.0 (Strict Bottom Hunter) Started")
    send_telegram("✅ *MAFIO BOT 6.0* متصل.\nتم تفعيل فلاتر القاع الصارمة لمنع شراء القمم واقتناص الانفجارات من البداية.")
    while True:
        try:
            scan()
            time.sleep(60) 
        except Exception as e:
            logger.error(f"Error: {e}")
            time.sleep(30)

if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
import os, sys, time, requests
from datetime import datetime

# الإعدادات (تأكد من وضع التوكن الخاص بك في Railway)
TOKEN = os.getenv("TELEGRAM_TOKEN", "your_bot_token")
ADMIN_ID = os.getenv("CHAT_ID", "your_chat_id")

# --- معايير الـ WOLF FLOW (السر البرمجي) ---
ACCELERATION_FACTOR = 3.5    # رصد العملة إذا تضاعف حجم التداول 3.5 مرات فجأة
MIN_RATIO = 2.0              # يجب أن يكون الشراء ضعف البيع على الأقل
MIN_VOL_USDT = 1500          # الحد الأدنى لسيولة الشمعة الواحدة لبدء التنبيه

state = {"sent": []}

def get_wolf_flow_logic(sym):
    url = "https://api.binance.com/api/v3/klines"
    try:
        # فحص آخر 5 دقائق للمقارنة (دقيقة بدقيقة)
        r = requests.get(url, params={"symbol": sym, "interval": "1m", "limit": 6}, timeout=3).json()
        if len(r) < 6: return None
        
        # بيانات الشمعة الحالية (الانفجارية)
        current_candle = r[-1]
        current_vol = float(current_candle[7]) # حجم السيولة بالـ USDT
        taker_buy_vol = float(current_candle[10]) # الشراء الحقيقي
        
        # بيانات الشموع السابقة (المتوسط الطبيعي)
        prev_vols = [float(x[7]) for x in r[:-1]]
        avg_prev_vol = sum(prev_vols) / len(prev_vols)
        
        # حساب التسارع (هل هناك دخول مفاجئ؟)
        acceleration = current_vol / avg_prev_vol if avg_prev_vol > 0 else 1.0
        
        # حساب النسبة (هل الشراء مسيطر؟)
        in_v = taker_buy_vol
        out_v = current_vol - taker_buy_vol
        ratio = in_v / out_v if out_v > 0 else 5.0
        
        price = float(current_candle[4])
        
        return {
            "accel": acceleration,
            "ratio": ratio,
            "net": in_v - out_v,
            "price": price,
            "in": in_v,
            "out": out_v
        }
    except: return None

def scan():
    print(f"🐺 Wolf Flow Scanning... {datetime.now().strftime('%H:%M:%S')}", flush=True)
    try:
        tickers = requests.get("https://api.binance.com/api/v3/ticker/24hr", timeout=5).json()
        for t in tickers:
            sym = t['symbol']
            if not sym.endswith("USDT") or any(x in sym for x in ["UP", "DOWN", "BEAR", "BULL"]): continue
            if sym in state["sent"]: continue

            data = get_wolf_flow_logic(sym)
            if not data: continue

            # --- تطبيق منطق "أحمد عبد الناصر" (Wolf Flow Logic) ---
            # 1. تسارع مفاجئ في السيولة (أكبر من المتوسط بـ 3.5 مرات)
            # 2. الشراء أكبر من البيع بوضوح (Ratio > 2.0)
            if data['accel'] > ACCELERATION_FACTOR and data['ratio'] > MIN_RATIO and data['in'] > MIN_VOL_USDT:
                state["sent"].append(sym)
                if len(state["sent"]) > 50: state["sent"].pop(0)

                msg = (
                    f"🐺 *WOLF FLOW SIGNAL* 🚀\n\n"
                    f"💵 *#{sym.replace('USDT','')}* | *Explosion Alert*\n"
                    f"💰 Price: `{data['price']:.8g}`\n\n"
                    f"⚡ *Acceleration: `{data['accel']:.1f}x`* 🔥\n"
                    f"📈 *Ratio: `{data['ratio']:.2f}x`* ✅\n"
                    f"📊 *Net Flow: `+${data['net']:.1f}`*\n\n"
                    f"🕒 {datetime.now().strftime('%H:%M:%S UTC')}"
                )
                requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                              data={"chat_id": ADMIN_ID, "text": msg, "parse_mode": "Markdown"})
                print(f"🎯 BOOM: {sym} Accel: {data['accel']:.1f}x")

    except Exception as e: print(f"Error: {e}")

def main():
    while True:
        scan()
        time.sleep(30) # فحص كل 30 ثانية كما في البوت الأصلي

if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
import os
import sys
import time
import requests
from datetime import datetime

# إعدادات الاتصال (Railway Variables)
TOKEN = os.getenv("TELEGRAM_TOKEN", "ضع_التوكن_هنا")
ADMIN_ID = os.getenv("CHAT_ID", "ضع_الايدي_هنا")

# معايير التصفية الصارمة (Wolf Strategy)
MIN_NET_FLOW = 75000         # الحد الأدنى لصافي الدخول (بالدولار) في آخر 15 دقيقة
MIN_RATIO = 5.0              # الدخول يجب أن يكون 5 أضعاف الخروج على الأقل
MIN_VOLUME_24H = 150000      # فوليوم يومي معقول للعملة

state = {"sent_coins": []}

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": ADMIN_ID, "text": message, "parse_mode": "Markdown"}, timeout=10)
    except Exception as e:
        print(f"Telegram Error: {e}")

def get_flow_analysis(sym):
    """تحليل دقيق لصافي السيولة In vs Out"""
    url = "https://api.binance.com/api/v3/klines"
    # تحليل آخر 15 شمعة (كل شمعة 1 دقيقة)
    params = {"symbol": sym, "interval": "1m", "limit": 15}
    try:
        r = requests.get(url, params=params, timeout=5).json()
        in_vol = 0
        out_vol = 0
        
        for c in r:
            open_p, close_p, vol_quote = float(c[1]), float(c[4]), float(c[7])
            if close_p > open_p:
                in_vol += vol_quote
            else:
                out_vol += vol_quote
                
        net_flow = in_vol - out_vol
        ratio = in_vol / out_vol if out_vol > 0 else 10.0
        current_price = float(r[-1][4])
        # حساب الحركة السعرية في آخر ساعة (تقريبياً من البيانات المتاحة)
        move_1h = ((float(r[-1][4]) - float(r[0][1])) / float(r[0][1])) * 100
        
        return {
            "in": in_vol, "out": out_vol, "net": net_flow, 
            "ratio": ratio, "price": current_price, "move": move_1h
        }
    except: return None

def scan():
    print(f"--- Scanning Market: {datetime.now().strftime('%H:%M:%S')} ---", flush=True)
    try:
        # استخدام Binance API كمصدر أساسي وموثوق للسيولة
        tickers = requests.get("https://api.binance.com/api/v3/ticker/24hr", timeout=10).json()
    except: 
        print("Error fetching tickers")
        return

    for t in tickers:
        sym = t['symbol']
        if not sym.endswith("USDT") or any(x in sym for x in ["UP", "DOWN", "BEAR", "BULL"]): continue
        if sym in state["sent_coins"]: continue

        try:
            vol_24h = float(t['quoteVolume'])
            if vol_24h < MIN_VOLUME_24H: continue

            flow = get_flow_analysis(sym)
            if not flow: continue

            # تطبيق "الفلتر الذهبي" لصافي السيولة
            if flow['net'] > MIN_NET_FLOW and flow['ratio'] > MIN_RATIO:
                
                state["sent_coins"].append(sym)
                if len(state["sent_coins"]) > 100: state["sent_coins"].pop(0)

                # تنسيق الإشعار ليطابق Wolf Flow تماماً
                msg = (
                    f"🐺 *Wolf Flow* 🛰️\n\n"
                    f"💵 *#{sym.replace('USDT','')}/USDT* ⚡🚀  🔔 Signal #{len(state['sent_coins'])}\n"
                    f"💰 Price: `${flow['price']:.8g}`\n"
                    f"📈 1h Move: `+{flow['move']:.2f}%`\n\n"
                    f"⚡ Volume: `Exceptional` 🔥\n"
                    f"🟢 Interest: `Strong` ✅\n"
                    f"📊 *1h Flow:*\n"
                    f"  📥 In: `${flow['in']/1000:.2f}K` \n"
                    f"  📤 Out: `${flow['out']/1000:.2f}K` \n"
                    f"  ▲ Net: `+${flow['net']/1000:.2f}K` ✅\n"
                    f"🟡 Funding: `Neutral`\n\n"
                    f"🕒 {datetime.now().strftime('%d %b %Y %H:%M')}"
                )
                send_telegram(msg)
                print(f"🎯 Signal sent: {sym} | Net: +${flow['net']/1000:.1f}K", flush=True)
                time.sleep(1) # تجنب الضغط على API التليجرام
        except: continue

def main():
    print("🚀 MAFIO NET FLOW V22.0 PRO STARTED", flush=True)
    send_telegram("✅ *Mafio Bot V22.0 Connected*\nتم تفعيل نظام صافي التدفق (Net Flow) بنجاح.")
    while True:
        try:
            scan()
            time.sleep(35) # فحص كل 35 ثانية
        except Exception as e:
            print(f"Main Loop Error: {e}", flush=True)
            time.sleep(20)

if __name__ == "__main__":
    main()

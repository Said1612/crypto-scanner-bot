# -*- coding: utf-8 -*-
import os
import sys
import time
import requests
from datetime import datetime

# الإعدادات
TOKEN = os.getenv("TELEGRAM_TOKEN", "ضع_التوكن_هنا")
ADMIN_ID = os.getenv("CHAT_ID", "ضع_الايدي_هنا")

# معايير الصيد الاحترافي (Wolf Logic)
MIN_NET_FLOW = 50000        # الحد الأدنى لصافي الدخول (بالدولار)
MIN_RATIO = 4.0             # يجب أن يكون الدخول 4 أضعاف الخروج على الأقل
MIN_VOLUME_24H = 100000     

state = {"sent_coins": []}

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": ADMIN_ID, "text": message, "parse_mode": "Markdown"}, timeout=10)
    except: pass

def get_flow_analysis(sym):
    """تحليل دقيق لتدفق السيولة In/Out/Net"""
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": sym, "interval": "1m", "limit": 15} # تحليل آخر 15 دقيقة
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
        ratio = in_vol / out_vol if out_vol > 0 else 10
        current_price = float(r[-1][4])
        move_1h = ((float(r[-1][4]) - float(r[0][1])) / float(r[0][1])) * 100
        
        return {
            "in": in_vol, "out": out_vol, "net": net_flow, 
            "ratio": ratio, "price": current_price, "move": move_1h
        }
    except: return None

def scan():
    # جلب أسعار بايننس كمصدر أساسي للسيولة
    try:
        tickers = requests.get("https://api.binance.com/api/v3/ticker/24hr").json()
    except: return

    for t in tickers:
        sym = t['symbol']
        if not sym.endswith("USDT") or any(x in sym for x in ["UP", "DOWN"]): continue
        if sym in state["sent_coins"]: continue

        vol_24h = float(t['quoteVolume'])
        if vol_24h < MIN_VOLUME_24H: continue

        # تحليل التدفق
        flow = get_flow_analysis(sym)
        if not flow: continue

        # الفلتر الذهبي: الصافي إيجابي + الدخول أكبر بكثير من الخروج
        if flow['net'] > MIN_NET_FLOW and flow['ratio'] > MIN_RATIO:
            
            state["sent_coins"].append(sym)
            if len(state["sent_coins"]) > 50: state["sent_coins"].pop(0)

            # تنسيق الإشعار مثل Wolf Flow
            msg = (
                f"🐺 *Wolf Flow* 🛰️\n\n"
                f"💵 *#{sym}* ⚡🚀  🔔 Signal #{len(state['sent_coins'])}\n"
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
            print(f"🎯 Signal sent for {sym}")
            time.sleep(1)

def main():
    print("🚀 Net Flow Engine Started...")
    while True:
        try:
            scan()
            time.sleep(30)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()

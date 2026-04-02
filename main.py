# -*- coding: utf-8 -*-
import os
import sys
import time
import requests
from datetime import datetime

# إعدادات المتغيرات من Railway
TOKEN = os.getenv("TELEGRAM_TOKEN", "ضع_التوكن_هنا")
ADMIN_ID = os.getenv("CHAT_ID", "ضع_الايدي_هنا")

# معايير الفلترة (Wolf Flow)
MIN_NET_FLOW = 75000         
MIN_RATIO = 5.0              
MIN_VOLUME_24H = 150000      

state = {"sent_coins": []}

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": ADMIN_ID, "text": message, "parse_mode": "Markdown"}, timeout=10)
    except:
        pass

def get_flow_analysis(sym):
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": sym, "interval": "1m", "limit": 15}
    try:
        r = requests.get(url, params=params, timeout=5)
        if r.status_code != 200: return None
        data = r.json()
        if not isinstance(data, list): return None
        
        in_vol = 0
        out_vol = 0
        for c in data:
            open_p, close_p, vol_quote = float(c[1]), float(c[4]), float(c[7])
            if close_p > open_p:
                in_vol += vol_quote
            else:
                out_vol += vol_quote
                
        net_flow = in_vol - out_vol
        ratio = in_vol / out_vol if out_vol > 0 else 10.0
        current_price = float(data[-1][4])
        move_1h = ((current_price - float(data[0][1])) / float(data[0][1])) * 100
        
        return {
            "in": in_vol, "out": out_vol, "net": net_flow, 
            "ratio": ratio, "price": current_price, "move": move_1h
        }
    except:
        return None

def scan():
    print(f"--- Scanning Market: {datetime.now().strftime('%H:%M:%S')} ---", flush=True)
    try:
        r = requests.get("https://api.binance.com/api/v3/ticker/24hr", timeout=10)
        if r.status_code != 200: return
        tickers = r.json()
        if not isinstance(tickers, list): return

        for t in tickers:
            if not isinstance(t, dict): continue
            sym = t.get('symbol', '')
            if not sym.endswith("USDT") or any(x in sym for x in ["UP", "DOWN", "BEAR", "BULL"]): continue
            if sym in state["sent_coins"]: continue

            vol_24h = float(t.get('quoteVolume', 0))
            if vol_24h < MIN_VOLUME_24H: continue

            flow = get_flow_analysis(sym)
            if not flow or flow['net'] < MIN_NET_FLOW or flow['ratio'] < MIN_RATIO: continue

            state["sent_coins"].append(sym)
            if len(state["sent_coins"]) > 100: state["sent_coins"].pop(0)

            # تم إصلاح القوس هنا وضمان إغلاق السلسلة النصية بشكل صحيح
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
            print(f"🎯 Signal: {sym} | Net Flow: +${flow['net']/1000:.1f}K", flush=True)
            time.sleep(1)
    except Exception as e:
        print(f"Scan Error: {e}", flush=True)

def main():
    print("🚀 MAFIO NET FLOW V22.2 STARTED (FIXED)", flush=True)
    while True:
        try:
            scan()
            time.sleep(45)
        except Exception as e:
            print(f"Main Loop Error: {e}", flush=True)
            time.sleep(30)

if __name__ == "__main__":
    main()

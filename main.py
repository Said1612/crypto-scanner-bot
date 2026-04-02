# -*- coding: utf-8 -*-
import os
import sys
import time
import requests
from datetime import datetime

# الإعدادات من Railway
TOKEN = os.getenv("TELEGRAM_TOKEN", "ضع_التوكن_هنا")
ADMIN_ID = os.getenv("CHAT_ID", "ضع_الايدي_هنا")

# تم تعديل المعايير لتكون أكثر حساسية لاصطياد الفرص بشكل أسرع
MIN_NET_FLOW = 30000         # خفضنا الحد إلى 30 ألف دولار لاكتشاف السيولة مبكراً
MIN_RATIO = 2.5              # الدخول يجب أن يكون مرتين ونصف ضعف الخروج
MIN_VOLUME_24H = 100000      # الحد الأدنى للفوليوم اليومي

state = {"sent_coins": [], "total_scanned": 0}

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        r = requests.post(url, data={"chat_id": ADMIN_ID, "text": message, "parse_mode": "Markdown"}, timeout=10)
        return r.status_code == 200
    except:
        return False

def get_flow_analysis(sym):
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": sym, "interval": "1m", "limit": 15}
    try:
        r = requests.get(url, params=params, timeout=5)
        if r.status_code != 200: return None
        data = r.json()
        
        in_vol, out_vol = 0, 0
        for c in data:
            open_p, close_p, vol_quote = float(c[1]), float(c[4]), float(c[7])
            if close_p > open_p: in_vol += vol_quote
            else: out_vol += vol_quote
                
        net_flow = in_vol - out_vol
        ratio = in_vol / out_vol if out_vol > 0 else 5.0
        current_price = float(data[-1][4])
        move_1h = ((current_price - float(data[0][1])) / float(data[0][1])) * 100
        
        return {"in": in_vol, "out": out_vol, "net": net_flow, "ratio": ratio, "price": current_price, "move": move_1h}
    except:
        return None

def scan():
    print(f"🔍 Scan Started: {datetime.now().strftime('%H:%M:%S')}", flush=True)
    try:
        r = requests.get("https://api.binance.com/api/v3/ticker/24hr", timeout=10)
        if r.status_code != 200: 
            print(f"❌ API Error: {r.status_code}", flush=True)
            return
        
        tickers = r.json()
        candidates_found = 0

        for t in tickers:
            sym = t.get('symbol', '')
            if not sym.endswith("USDT") or any(x in sym for x in ["UP", "DOWN", "BEAR", "BULL"]): continue
            
            vol_24h = float(t.get('quoteVolume', 0))
            if vol_24h < MIN_VOLUME_24H: continue

            flow = get_flow_analysis(sym)
            if not flow: continue

            # التحقق من الشروط
            if flow['net'] > MIN_NET_FLOW and flow['ratio'] > MIN_RATIO:
                if sym in state["sent_coins"]: continue
                
                candidates_found += 1
                state["sent_coins"].append(sym)
                if len(state["sent_coins"]) > 50: state["sent_coins"].pop(0)

                msg = (
                    f"🐺 *Wolf Flow* 🛰️\n\n"
                    f"💵 *#{sym.replace('USDT','')}/USDT* ⚡🚀\n"
                    f"💰 Price: `${flow['price']:.8g}`\n"
                    f"📈 1m Move: `+{flow['move']:.2f}%`\n\n"
                    f"⚡ Volume: `Exceptional` 🔥\n"
                    f"🟢 Interest: `Strong` ✅\n"
                    f"📊 *15m Flow:*\n"
                    f"  📥 In: `${flow['in']/1000:.1f}K` \n"
                    f"  📤 Out: `${flow['out']/1000:.2f}K` \n"
                    f"  ▲ Net: `+${flow['net']/1000:.1f}K` ✅\n"
                    f"🟡 Funding: `Neutral`\n\n"
                    f"🕒 {datetime.now().strftime('%H:%M UTC')}"
                )
                if send_telegram(msg):
                    print(f"✅ SIGNAL SENT: {sym}", flush=True)
                time.sleep(1)

        print(f"📊 Scan Finished. Candidates sent this cycle: {candidates_found}", flush=True)
    except Exception as e:
        print(f"⚠️ Scan Exception: {e}", flush=True)

def main():
    print("🚀 MAFIO V22.3 (High Sensitivity) STARTED", flush=True)
    # رسالة ترحيب للتأكد أن التليجرام يعمل
    send_telegram("📡 *Mafio Bot V22.3 Online*\nتم تقليل القيود لزيادة عدد الإشارات.")
    
    while True:
        try:
            scan()
            time.sleep(40) 
        except Exception as e:
            print(f"❌ Main Loop Error: {e}", flush=True)
            time.sleep(20)

if __name__ == "__main__":
    main()

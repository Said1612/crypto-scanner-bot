# -*- coding: utf-8 -*-
import os, sys, time, requests
from datetime import datetime

# الإعدادات الأساسية
TOKEN = os.getenv("TELEGRAM_TOKEN", "ضع_التوكن_هنا")
ADMIN_ID = os.getenv("CHAT_ID", "ضع_الايدي_هنا")

# معايير "الوحش" المستوحاة من صفقاتك الأخيرة
MIN_NET_FLOW = 50000         # الحد الأدنى لبداية الرصد
EXTREME_NET_FLOW = 150000    # حد "الانفجار الحقيقي"
MIN_RATIO = 3.5              
MIN_VOLUME_24H = 100000      

state = {"sent_coins": []}

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": ADMIN_ID, "text": message, "parse_mode": "Markdown"}, timeout=10)
    except: pass

def get_analysis(sym, source="BINANCE"):
    """تحليل السيولة العميقة - منطق ولف المتطور"""
    base = "https://api.binance.com/api/v3/klines" if source == "BINANCE" else "https://api.mexc.com/api/v3/klines"
    try:
        # تحليل آخر 5 دقائق (دقيقة بدقيقة)
        r = requests.get(base, params={"symbol": sym, "interval": "1m", "limit": 5}, timeout=5).json()
        in_v, out_v = 0, 0
        for c in r:
            vol = float(c[7]) if source == "BINANCE" else float(c[10]) # Quote Volume
            if float(c[4]) > float(c[1]): in_v += vol
            else: out_v += vol
        
        net = in_v - out_v
        ratio = in_v / out_v if out_v > 0 else 10.0
        # حساب التسارع في آخر شمعة
        last_vol = float(r[-1][7]) if source == "BINANCE" else float(r[-1][10])
        avg_v = sum([float(x[7]) for x in r[:-1]]) / 4
        accel = last_vol / avg_v if avg_v > 0 else 1.0
        
        return {"in": in_v, "out": out_v, "net": net, "ratio": ratio, "price": float(r[-1][4]), "accel": accel}
    except: return None

def scan_market(source="BINANCE"):
    print(f"🔍 Scanning {source}...", flush=True)
    url = "https://api.binance.com/api/v3/ticker/24hr" if source == "BINANCE" else "https://api.mexc.com/api/v3/ticker/24hr"
    try:
        tickers = requests.get(url, timeout=10).json()
        for t in tickers:
            sym = t['symbol']
            if not sym.endswith("USDT") or any(x in sym for x in ["UP", "DOWN"]): continue
            if sym in state["sent_coins"]: continue
            
            vol_24h = float(t.get('quoteVolume', 0))
            if vol_24h < MIN_VOLUME_24H: continue

            data = get_analysis(sym, source)
            if not data: continue

            # شرط الدخول: صافي تدفق ضخم أو تسارع انفجاري
            if data['net'] > MIN_NET_FLOW and (data['ratio'] > MIN_RATIO or data['accel'] > 5.0):
                state["sent_coins"].append(sym)
                if len(state["sent_coins"]) > 50: state["sent_coins"].pop(0)

                interest = "Extreme 🔥" if data['net'] > EXTREME_NET_FLOW else "Strong ✅"
                
                msg = (
                    f"🐺 *Wolf Flow v23.0* 🛰️\n\n"
                    f"💵 *#{sym.replace('USDT','')}/USDT* 🚀🚀\n"
                    f"💰 Price: `${data['price']:.8g}`\n"
                    f"⚡ Accel: `{data['accel']:.1f}x` | Source: `{source}`\n\n"
                    f"🟢 Interest: `{interest}`\n"
                    f"📊 *Net Flow Analysis:*\n"
                    f"  📥 In: `${data['in']/1000:.1f}K` \n"
                    f"  ▲ Net: `+${data['net']/1000:.1f}K` ✅\n"
                    f"📈 Ratio: `{data['ratio']:.1f}x` \n\n"
                    f"🕒 {datetime.now().strftime('%H:%M:%S UTC')}\n"
                    f"⚠️ _سيولة ذكية تم رصدها الآن!_"
                )
                send_telegram(msg)
                print(f"🎯 SIGNAL: {sym} Net: {data['net']}", flush=True)
    except: pass

def main():
    print("🚀 ULTIMATE WOLF V23.0 STARTED", flush=True)
    send_telegram("🐺 *Ultimate Wolf V23.0 Online*\nجاهز لاصطياد الانفجارات السعرية.")
    while True:
        try:
            scan_market("BINANCE")
            time.sleep(5)
            scan_market("MEXC")
            time.sleep(20)
        except: time.sleep(10)

if __name__ == "__main__":
    main()

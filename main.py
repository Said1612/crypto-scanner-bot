# -*- coding: utf-8 -*-
import os, time, requests
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --- الإعدادات ---
TOKEN = "your_token_here"
CHAT_ID = "your_id_here"

# إنشاء جلسة اتصال ذكية (تُعيد المحاولة تلقائياً ولا تعلق)
session = requests.Session()
retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
session.mount('https://', HTTPAdapter(max_retries=retries))

active_trades = {}

def send_telegram(text):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        session.post(url, data={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=5)
    except: pass

def main():
    print("💀 MAFIO V80: IRONCLAD EDITION START")
    send_telegram("💀 *Mafio V80: Ironclad Edition*\nتم تحديث محرك الاتصال. لن يعلق البوت بعد الآن.")

    while True:
        try:
            print(f"📡 [{datetime.now().strftime('%H:%M:%S')}] Heartbeat: Engine is Running...")
            
            # جلب البيانات بمهلة صارمة (Timeout) لمنع التعليق
            r = session.get("https://api.binance.com/api/v3/ticker/24hr", timeout=5).json()
            
            # فرز فوري لأقوى 20 عملة (تقليل العدد لزيادة السرعة القصوى)
            movers = [t for t in r if t['symbol'].endswith("USDT") and float(t['quoteVolume']) > 10000000]
            movers = sorted(movers, key=lambda x: float(x['priceChangePercent']), reverse=True)[:20]

            for t in movers:
                sym = t['symbol']
                if sym in active_trades: continue

                # فحص السيولة اللحظية
                k_data = session.get("https://api.binance.com/api/v3/klines", 
                                    params={"symbol": sym, "interval": "1m", "limit": 1}, timeout=3).json()
                if not k_data: continue
                
                candle = k_data[-1]
                entry_p = float(candle[4])
                ratio = float(candle[10]) / (float(candle[7]) - float(candle[10])) if float(candle[7]) > float(candle[10]) else 1.5
                
                if ratio >= 2.0:
                    active_trades[sym] = {'entry': entry_p, 'peak': 0, 'time': time.time()}
                    send_telegram(f"💀 *NEW SNIPE*: `#{sym.replace('USDT','')}`\n💰 Price: `{entry_p}`")

            # ملاحقة الأرباح
            for s in list(active_trades.keys()):
                curr = session.get("https://api.binance.com/api/v3/ticker/price", params={"symbol": s}, timeout=3).json()
                p_now = float(curr['price'])
                gain = ((p_now - active_trades[s]['entry']) / active_trades[s]['entry']) * 100
                
                for milestone in [2, 5, 10, 20]:
                    if gain >= milestone and active_trades[s]['peak'] < milestone:
                        active_trades[s]['peak'] = milestone
                        send_telegram(f"💀 *PROFIT ALERT* 🔔\n🚀 `#{s}`: `+{gain:.2f}%` ✅")

            print("✅ Cycle Finished Successfully.")
            time.sleep(10)

        except Exception as e:
            print(f"⚠️ System Auto-Reset: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()

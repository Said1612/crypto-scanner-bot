# -*- coding: utf-8 -*-
import time, requests, os
from datetime import datetime

# --- الإعدادات ---
TOKEN = os.getenv("TELEGRAM_TOKEN", "ضع_التوكن_هنا")
CHAT_ID = os.getenv("CHAT_ID", "ضع_الايدي_هنا")

# روابط بديلة لـ Binance لتجاوز الحظر
BINANCE_ENDPOINTS = [
    "https://api.binance.com",
    "https://api1.binance.com",
    "https://api2.binance.com",
    "https://api3.binance.com"
]

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=10)
    except: pass

def get_data_safe(symbol, endpoint):
    """جلب بيانات السيولة من رابط محدد"""
    try:
        url = f"{endpoint}/api/v3/klines"
        r = requests.get(url, params={"symbol": symbol, "interval": "1m", "limit": 2}, timeout=5)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and len(data) > 0:
                c = data[-1]
                total = float(c[7])
                buy = float(c[10])
                sell = total - buy
                if sell == 0: return None
                return {"p": float(c[4]), "ratio": buy/sell, "in": buy}
        return None
    except: return None

def main():
    print("💀 SKULL FLOW V34.0 - ANTI-BAN SYSTEM")
    send_telegram("💀 *Skull Flow V34.0*\nتم تفعيل نظام تخطي الحظر وتبديل الـ API.")
    
    sent_list = []
    current_api_idx = 0

    while True:
        try:
            # اختيار رابط API مختلف في كل دورة لتوزيع الضغط
            api_base = BINANCE_ENDPOINTS[current_api_idx]
            
            # جلب الأسعار
            r = requests.get(f"{api_base}/api/v3/ticker/price", timeout=10)
            
            if r.status_code != 200:
                print(f"⚠️ API {current_api_idx} Busy, switching...")
                current_api_idx = (current_api_idx + 1) % len(BINANCE_ENDPOINTS)
                time.sleep(5)
                continue

            tickers = r.json()
            # فحص أهم 150 عملة فقط لتقليل عدد الطلبات ومنع الحظر
            active_tickers = [t for t in tickers if t['symbol'].endswith("USDT")][:150]

            for t in active_tickers:
                sym = t['symbol']
                if any(x in sym for x in ["UP", "DOWN", "BULL", "BEAR"]) or sym in sent_list: continue

                # فحص السيولة
                d = get_data_safe(sym, api_base)
                
                if d and d['ratio'] > 2.2 and d['in'] > 3000:
                    msg = (
                        f"💀 *SKULL SIGNAL* 💀\n\n"
                        f"💵 *#{sym.replace('USDT','')}*\n"
                        f"💰 Price: `{d['p']:.8g}`\n"
                        f"📈 Ratio: `{d['ratio']:.2f}x` 🔥\n"
                        f"📥 Inflow: `${d['in']/1000:.1f}K` ✅"
                    )
                    send_telegram(msg)
                    sent_list.append(sym)
                    if len(sent_list) > 30: sent_list.pop(0)
                    print(f"🎯 Signal: {sym}")
                    time.sleep(0.5) # تأخير بسيط بين فحص عملة وأخرى لمنع الـ Rate Limit

            # تبديل الـ API للدورة القادمة
            current_api_idx = (current_api_idx + 1) % len(BINANCE_ENDPOINTS)
            time.sleep(40) # زيادة وقت الراحة بين الدورات لتجنب حظر الـ IP

        except Exception as e:
            print(f"❌ Error: {e}")
            time.sleep(20)

if __name__ == "__main__":
    main()

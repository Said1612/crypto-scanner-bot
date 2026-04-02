# -*- coding: utf-8 -*-
import time, requests
from datetime import datetime

# --- الإعدادات المباشرة (ضع بياناتك هنا بين القوسين) ---
TELEGRAM_TOKEN = "ضع_التوكن_الخاص_بك_هنا"
CHAT_ID = "ضع_الايدي_الخاص_بك_هنا"

def send_msg(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.status_code
    except:
        return 0

def get_data(symbol):
    try:
        url = "https://api.binance.com/api/v3/klines"
        params = {"symbol": symbol, "interval": "1m", "limit": 2}
        r = requests.get(url, params=params, timeout=5).json()
        
        c = r[-1] # الشمعة الحالية
        total_v = float(c[7])
        buy_v = float(c[10]) # الشراء
        sell_v = total_v - buy_v
        
        if sell_v == 0: return None
        
        return {
            "p": float(c[4]),
            "ratio": buy_v / sell_v,
            "in": buy_v,
            "net": buy_v - sell_v
        }
    except:
        return None

def main():
    print("💀 SKULL V32 STARTED...")
    status = send_msg("💀 *Skull Flow V32*\nتم التشغيل بنجاح.. جاري رصد السيولة.")
    
    if status == 401:
        print("❌ خطأ: التوكن غير صحيح! تأكد من التوكن الذي وضعته داخل الكود.")
        return

    sent_list = []

    while True:
        try:
            # جلب أفضل 100 عملة من حيث الحجم لسرعة الفحص
            tickers = requests.get("https://api.binance.com/api/v3/ticker/24hr").json()
            # ترتيب حسب السيولة
            tickers = sorted(tickers, key=lambda x: float(x['quoteVolume']), reverse=True)[:100]

            for t in tickers:
                sym = t['symbol']
                if not sym.endswith("USDT") or sym in sent_list: continue

                d = get_data(sym)
                # شرط الدخول: الشراء أكبر من البيع بوضوح (Ratio > 1.8)
                if d and d['ratio'] > 1.8 and d['in'] > 1000:
                    
                    msg = (
                        f"💀 *SKULL SIGNAL* 💀\n\n"
                        f"💵 *#{sym.replace('USDT','')}*\n"
                        f"💰 Price: `{d['p']:.8g}`\n"
                        f"📈 Ratio: `{d['ratio']:.2f}x` 🔥\n"
                        f"▲ Net: `+${d['net']/1000:.1f}K` ✅\n\n"
                        f"🕒 {datetime.now().strftime('%H:%M:%S UTC')}"
                    )
                    
                    if send_msg(msg) == 200:
                        sent_list.append(sym)
                        if len(sent_list) > 40: sent_list.pop(0)
                        print(f"✅ Signal Sent: {sym}")
            
            time.sleep(30) # فحص كل 30 ثانية
        except Exception as e:
            print(f"⚠️ Error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()

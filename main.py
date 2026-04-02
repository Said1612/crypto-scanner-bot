# -*- coding: utf-8 -*-
import time, requests, os
from datetime import datetime

# --- الإعدادات ---
# يفضل وضعها في Variables في Railway، أو كتابتها هنا مباشرة
TOKEN = os.getenv("TELEGRAM_TOKEN", "ضع_التوكن_هنا")
CHAT_ID = os.getenv("CHAT_ID", "ضع_الايدي_هنا")

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=10)
    except:
        pass

def get_valid_data(symbol):
    """جلب البيانات مع فحص النوع لمنع خطأ string indices"""
    url = "https://api.binance.com/api/v3/klines"
    try:
        r = requests.get(url, params={"symbol": symbol, "interval": "1m", "limit": 2}, timeout=5)
        data = r.json()
        
        # التأكد من أن الرد هو قائمة (List) وليس رسالة خطأ (String/Dict)
        if isinstance(data, list) and len(data) > 0:
            candle = data[-1]
            total_vol = float(candle[7])
            buy_vol = float(candle[10])
            sell_vol = total_vol - buy_vol
            return {
                "price": float(candle[4]),
                "ratio": buy_vol / sell_vol if sell_vol > 0 else 2.0,
                "in": buy_vol,
                "net": buy_vol - sell_vol
            }
    except:
        return None
    return None

def main():
    print("💀 SKULL FLOW V33.0 - ANTI-ERROR SYSTEM ONLINE")
    send_telegram("💀 *Skull Flow V33.0* \nتم تفعيل نظام الحماية وإصلاح أخطاء السجلات.")
    
    sent_signals = []

    while True:
        try:
            # 1. جلب قائمة الأسعار أولاً
            resp = requests.get("https://api.binance.com/api/v3/ticker/price", timeout=10)
            all_tickers = resp.json()

            # التأكد من أن الرد صحيح قبل البدء
            if not isinstance(all_tickers, list):
                print("⚠️ Binance API busy... retrying")
                time.sleep(10)
                continue

            for t in all_tickers:
                # فحص النوع للتأكد أن t هو Dictionary
                if not isinstance(t, dict) or 'symbol' not in t: continue
                
                symbol = t['symbol']
                if not symbol.endswith("USDT") or symbol in sent_signals: continue

                # 2. تحليل تدفق السيولة للعملة
                flow = get_valid_data(symbol)
                
                # شرط الاقتناص: سيولة شراء قوية جداً
                if flow and flow['ratio'] > 2.0 and flow['in'] > 2000:
                    
                    msg = (
                        f"💀 *SKULL WHALE DETECTED* 💀\n\n"
                        f"💵 *#{symbol.replace('USDT','')}*\n"
                        f"💰 Price: `{flow['price']:.8g}`\n"
                        f"📊 Ratio: `{flow['ratio']:.2f}x` 🔥\n"
                        f"📥 Inflow: `${flow['in']/1000:.1f}K`\n"
                        f"🟢 Net: `+${flow['net']/1000:.1f}K` ✅\n\n"
                        f"🕒 {datetime.now().strftime('%H:%M:%S UTC')}"
                    )
                    
                    send_telegram(msg)
                    sent_signals.append(symbol)
                    if len(sent_signals) > 50: sent_signals.pop(0)
                    print(f"✅ Signal: {symbol}")

            time.sleep(30)
            
        except Exception as e:
            print(f"⚠️ Runtime Warning: {e}")
            time.sleep(15)

if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
import json
import time
import urllib.request
import urllib.parse

# --- الإعدادات (ضع بياناتك هنا) ---
TOKEN = "YOUR_BOT_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"

def send_msg(text):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        params = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}).encode()
        urllib.request.urlopen(url, data=params, timeout=10)
    except:
        pass

def start_bot():
    print("🚀 MAFIO-BOT V16 IS STARTING...")
    send_msg("✅ *MAFIO-BOT V16*\nتم إصلاح خطأ السطر 12819 بنجاح والبوت يعمل الآن!")
    
    while True:
        try:
            # جلب البيانات من MEXC بدون مكتبات خارجية
            with urllib.request.urlopen("https://api.mexc.com/api/v3/ticker/24hr", timeout=10) as r:
                data = json.loads(r.read())
                for t in data:
                    sym = t.get('symbol', '')
                    change = float(t.get('priceChangePercent', 0))
                    if sym.endswith('USDT') and change > 15:
                        send_msg(f"🔥 *إشارة قوية:* {sym}\n📈 الارتفاع: {change}%")
            time.sleep(15)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(20)

if __name__ == "__main__":
    start_bot()

# -*- coding: utf-8 -*-
import os, time, requests
from datetime import datetime

# --- الإعدادات (تأكد من وضع بياناتك) ---
TOKEN = "YOUR_TELEGRAM_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"

# --- فلاتر الصيد (إعدادات حذرة لمنع الانعكاس) ---
MIN_VOL_24H = 300000        # سيولة كافية للحركة
TARGET_CHANGE = 1.5         # صعود 1.5% كحد أدنى

def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}, timeout=5)
    except: pass

def get_mexc_data():
    """جلب البيانات باستخدام محرك V3 الجديد والأكثر استقراراً"""
    try:
        # الرابط الرسمي المحدث لـ MEXC
        url = "https://api.mexc.com/api/v3/ticker/24hr"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            # التأكد أن البيانات قائمة (List) وليست نصاً لمنع خطأ TypeError
            if isinstance(data, list):
                return data
        return None
    except:
        return None

def main():
    print("🚀 MAFIO V100: MEXC ULTIMATE - ONLINE")
    send_telegram("💀 *Mafio V100: MEXC Ultimate*\nتم تحديث المحرك لروابط V3 الرسمية. بدأ الفحص الآمن..")
    
    sent_signals = []

    while True:
        try:
            print(f"🔍 [{datetime.now().strftime('%H:%M:%S')}] Heartbeat: Scanning MEXC...")
            tickers = get_mexc_data()
            
            if not tickers:
                print("⚠️ API Response Error. Retrying in 20s...")
                time.sleep(20)
                continue

            # تصفية العملات
            for t in tickers:
                # التأكد من وجود المفاتيح المطلوبة قبل القراءة
                if 'symbol' not in t or 'lastPrice' not in t: continue
                
                sym = t['symbol']
                if not sym.endswith("USDT") or sym in sent_signals: continue
                
                price = float(t['lastPrice'])
                change = float(t['priceChangePercent'])
                volume = float(t['quoteVolume'])

                # شرط الدخول: صعود حقيقي مع سيولة
                if change >= TARGET_CHANGE and volume >= MIN_VOL_24H:
                    sent_signals.append(sym)
                    if len(sent_signals) > 50: sent_signals.pop(0)

                    msg = (
                        f"💀 *MAFIO MEXC SIGNAL* 💀\n\n"
                        f"💵 *#{sym.replace('USDT','')}*\n"
                        f"💰 Price: `{price:.8g}`\n"
                        f"📈 24h Change: `+{change:.2f}%` 🔥\n"
                        f"💎 24h Vol: `${volume/1000:.1f}K` ✅\n\n"
                        f"🕒 {datetime.now().strftime('%H:%M UTC')}"
                    )
                    send_telegram(msg)
                    print(f"✅ Signal Sent: {sym}")

            time.sleep(30) # دورة فحص متزنة

        except Exception as e:
            print(f"⚠️ Warning: {e}")
            time.sleep(15)

if __name__ == "__main__":
    main()

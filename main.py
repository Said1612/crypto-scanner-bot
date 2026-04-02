# -*- coding: utf-8 -*-
import websocket, json, time, requests, os
from datetime import datetime

# --- الإعدادات ---
TOKEN = os.getenv("TELEGRAM_TOKEN", "ضع_التوكن_هنا")
CHAT_ID = os.getenv("CHAT_ID", "ضع_الايدي_هنا")

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=10)
    except: pass

def on_message(ws, message):
    try:
        data = json.loads(message)
        # استخراج البيانات من البث المباشر (Individual Symbol Ticker)
        sym = data['s']
        if not sym.endswith("USDT"): return

        price = float(data['c'])
        total_vol = float(data['q']) # Volume in USDT
        
        # في الـ WebSocket لا نحصل على حجم الشراء/البيع فوراً بنفس الطريقة
        # لذا سنراقب التغير السعري المفاجئ مع الحجم الكبير
        change = float(data['P']) # 24h price change percentage

        if change > 5.0 and total_vol > 500000: # فلتر أولي للعملات النشطة جداً
            msg = (
                f"💀 *LIVE SKULL ALERT* 💀\n\n"
                f"💵 *#{sym.replace('USDT','')}*\n"
                f"💰 Price: `{price:.8g}`\n"
                f"📊 24h Change: `{change:+.2f}%` 🔥\n"
                f"💎 24h Vol: `${total_vol/1000000:.1f}M` ✅\n\n"
                f"🕒 {datetime.now().strftime('%H:%M:%S UTC')}"
            )
            # إضافة نظام منع تكرار بسيط هنا إذا لزم الأمر
            print(f"🎯 Signal Detected: {sym}")
            send_telegram(msg)
    except Exception as e:
        print(f"Error processing message: {e}")

def on_error(ws, error):
    print(f"💀 Connection Error: {error}")

def on_close(ws, close_status_code, close_msg):
    print("💀 Connection Closed. Retrying in 5s...")
    time.sleep(5)
    start_socket()

def start_socket():
    # الاتصال ببث جميع العملات (All Market Tickers) لتقليل عدد الطلبات
    socket_url = "wss://stream.binance.com:9443/ws/!ticker@arr"
    ws = websocket.WebSocketApp(socket_url,
                                on_message=on_message,
                                on_error=on_error,
                                on_close=on_close)
    ws.run_forever()

if __name__ == "__main__":
    print("💀 SKULL FLOW V35.0 - WEBSOCKET MODE ONLINE")
    send_telegram("💀 *Skull Flow V35.0*\nتم التحول لنظام البث المباشر (WebSocket) لتخطي الحظر.")
    start_socket()

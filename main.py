# -*- coding: utf-8 -*-
import subprocess
import sys
import os

# --- مرحلة التثبيت الإجباري (Force Install) ---
def install_deps():
    try:
        import websocket
        import requests
    except ImportError:
        print("💀 Installing missing libraries...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "websocket-client", "requests"])

install_deps()

# --- استيراد المكتبات بعد التأكد من تثبيتها ---
import websocket
import json
import time
import requests
from datetime import datetime

# --- الإعدادات ---
TOKEN = os.getenv("TELEGRAM_TOKEN", "your_token_here")
CHAT_ID = os.getenv("CHAT_ID", "your_id_here")

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=10)
    except: pass

def on_message(ws, message):
    try:
        data = json.loads(message)
        # هذا البث يعطي قائمة (List) بكل العملات
        for ticker in data:
            sym = ticker['s']
            if not sym.endswith("USDT"): continue
            
            # منطق الحيتان: سعر يتغير مع سيولة ضخمة
            change = float(ticker['P'])
            volume = float(ticker['q'])
            
            if change > 3.5 and volume > 1000000: # أكثر من 3.5% وسيولة مليون دولار
                msg = (
                    f"💀 *SKULL LIVE SIGNAL* 💀\n\n"
                    f"💵 *#{sym.replace('USDT','')}*\n"
                    f"💰 Price: `{float(ticker['c']):.8g}`\n"
                    f"📈 Change: `{change:+.2f}%` 🔥\n"
                    f"💎 24h Vol: `${volume/1000000:.1f}M` ✅\n\n"
                    f"🕒 {datetime.now().strftime('%H:%M:%S UTC')}"
                )
                send_telegram(msg)
                print(f"🎯 Found: {sym}")
                time.sleep(1) # تجنب التكرار اللحظي
    except Exception as e:
        print(f"Error: {e}")

def on_error(ws, error):
    print(f"💀 Socket Error: {error}")

def on_close(ws, close_status_code, close_msg):
    print("💀 Connection Closed. Restarting...")
    time.sleep(5)
    start_socket()

def start_socket():
    # الاتصال بالبث المباشر الشامل لجميع العملات
    socket_url = "wss://stream.binance.com:9443/ws/!ticker@arr"
    ws = websocket.WebSocketApp(socket_url,
                                on_message=on_message,
                                on_error=on_error,
                                on_close=on_close)
    ws.run_forever()

if __name__ == "__main__":
    print("💀 SKULL FLOW V36.0 - AUTO-INSTALLER ACTIVE")
    send_telegram("💀 *Skull Flow V36.0*\nنظام التثبيت الذاتي والبث المباشر متصل.")
    start_socket()

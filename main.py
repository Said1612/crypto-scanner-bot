# -*- coding: utf-8 -*-
import subprocess, sys, os

# التثبيت الذاتي للمكتبات لضمان التشغيل على Railway
def install_deps():
    try:
        import websocket, requests
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "websocket-client", "requests"])

install_deps()

import websocket, json, time, requests
from datetime import datetime

# --- الإعدادات (ضع بياناتك هنا أو في Railway Variables) ---
TOKEN = os.getenv("TELEGRAM_TOKEN", "your_token_here")
CHAT_ID = os.getenv("CHAT_ID", "your_id_here")

# --- منطق الاقتناص الاحترافي ---
MIN_VOLUME_1M = 50000       # الحد الأدنى لسيولة الشمعة الحالية
BUY_RATIO_THRESHOLD = 2.0   # يجب أن يكون الشراء ضعف البيع على الأقل
PRICE_CHANGE_MIN = 0.5      # الحد الأدنى للارتفاع اللحظي (%)

sent_signals = {}

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=10)
    except: pass

def on_message(ws, message):
    try:
        data = json.loads(message)
        # استخدام بث kline للحصول على تفاصيل الشراء والبيع (Taker Buy Volume)
        if data['e'] != 'kline': return
        
        k = data['k']
        if not k['x']: return # ننتظر إغلاق الشمعة أو تحديثها القوي
        
        sym = data['s']
        if not sym.endswith("USDT"): return

        # --- تحليل البيانات ---
        close_price = float(k['c'])
        total_vol = float(k['q'])       # السيولة الإجمالية بالدولار
        buy_vol = float(k['V'])         # سيولة الشراء (Taker Buy Asset Vol * Price)
        buy_vol_usdt = buy_vol * close_price
        sell_vol_usdt = total_vol - buy_vol_usdt
        
        if sell_vol_usdt == 0: return
        ratio = buy_vol_usdt / sell_vol_usdt
        change = ((float(k['c']) - float(k['o'])) / float(k['o'])) * 100

        # --- شرط الدخول الذهبي 💀 ---
        if ratio >= BUY_RATIO_THRESHOLD and total_vol >= MIN_VOLUME_1M and change >= PRICE_CHANGE_MIN:
            
            # منع تكرار نفس العملة في وقت قصير
            current_time = time.time()
            if sym in sent_signals and current_time - sent_signals[sym] < 300: return
            
            sent_signals[sym] = current_time
            
            # حساب الأهداف التقديرية (1% و 2%)
            tp1 = close_price * 1.01
            tp2 = close_price * 1.02

            msg = (
                f"💀 *SKULL PRO SIGNAL* 💀\n\n"
                f"🚀 *Symbol:* `#{sym.replace('USDT','')}`\n"
                f"💰 *Entry:* `{close_price:.8g}`\n"
                f"📊 *Buy/Sell Ratio:* `{ratio:.2f}x` 🔥\n"
                f"📈 *Momentum:* `{change:+.2f}%`\n"
                f"💎 *Volume:* `${total_vol/1000:.1f}K` ✅\n\n"
                f"🎯 *Targets:*\n"
                f"  ∟ TP1: `{tp1:.8g}` (1%)\n"
                f"  ∟ TP2: `{tp2:.8g}` (2%)\n\n"
                f"🕒 {datetime.now().strftime('%H:%M:%S UTC')}"
            )
            send_telegram(msg)
            print(f"✅ Professional Signal Sent: {sym} | Ratio: {ratio:.2f}")

    except Exception as e:
        pass

def on_error(ws, error): print(f"💀 Error: {error}")
def on_close(ws, c, m): time.sleep(5); start_socket()

def start_socket():
    # نراقب شمعة الدقيقة (1m) لجميع العملات
    # ملاحظة: لتقليل الضغط سنراقب أهم العملات أو نستخدم البث العام
    socket_url = "wss://stream.binance.com:9443/ws/!kline_1m"
    ws = websocket.WebSocketApp(socket_url, on_message=on_message, on_error=on_error, on_close=on_close)
    ws.run_forever()

if __name__ == "__main__":
    print("💀 SKULL FLOW V37.0 - PROFESSIONAL MODE ACTIVE")
    send_telegram("💀 *Skull Flow V37.0 Professional*\nتم تفعيل نظام تحليل السيولة المتقدم (Ratio Analysis).")
    start_socket()

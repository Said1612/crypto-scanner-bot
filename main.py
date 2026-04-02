# -*- coding: utf-8 -*-
import os, sys, time, requests
from datetime import datetime

# --- إدخال الإعدادات مباشرة هنا إذا فشل Railway في قراءتها ---
TOKEN = "ضع_التوكن_هنا" 
ADMIN_ID = "ضع_الايدي_هنا"

# إذا كنت تستخدم Variables في Railway، اترك هذه الأسطر كما هي:
TOKEN = os.getenv("TELEGRAM_TOKEN", TOKEN)
ADMIN_ID = os.getenv("CHAT_ID", ADMIN_ID)

# --- معايير الاقتناص اللحظي (Skull Logic) ---
MIN_RATIO = 1.5              # نسبة الشراء مقابل البيع
ACCEL_THRESHOLD = 2.5        # تسارع السيولة
MIN_VOL_THRESHOLD = 800      # الحد الأدنى للسيولة بالدولار

state = {"sent": []}

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        response = requests.post(url, data={"chat_id": ADMIN_ID, "text": message, "parse_mode": "Markdown"}, timeout=10)
        if response.status_code == 401:
            print("❌ الخطأ: توكن تليجرام غير صحيح (Unauthorized).")
        return response
    except Exception as e:
        print(f"⚠️ Error sending to Telegram: {e}")
        return None

def get_flow(sym):
    url = "https://api.binance.com/api/v3/klines"
    try:
        # فحص الشمعة الحالية والماضية للمقارنة
        r = requests.get(url, params={"symbol": sym, "interval": "1m", "limit": 5}, timeout=5).json()
        if not r or len(r) < 5: return None
        
        curr = r[-1]
        total_vol = float(curr[7])
        in_vol = float(curr[10]) # Taker Buy Volume
        out_vol = total_vol - in_vol
        
        # حساب متوسط السيولة للشموع السابقة
        prev_avg = sum([float(x[7]) for x in r[:-1]]) / 4
        accel = total_vol / prev_avg if prev_avg > 0 else 1.0
        
        ratio = in_vol / out_vol if out_vol > 0 else 2.0
        price = float(curr[4])
        
        return {
            "in": in_vol, "out": out_vol, "net": in_vol - out_vol,
            "ratio": ratio, "accel": accel, "price": price, "total": total_vol
        }
    except: return None

def scan():
    print(f"💀 Skull Scanning... {datetime.now().strftime('%H:%M:%S')}", flush=True)
    try:
        r = requests.get("https://api.binance.com/api/v3/ticker/24hr", timeout=10)
        tickers = r.json()
        
        for t in tickers:
            sym = t['symbol']
            if not sym.endswith("USDT") or any(x in sym for x in ["UP", "DOWN"]): continue
            if sym in state["sent"]: continue

            data = get_flow(sym)
            if not data: continue

            # --- منطق الجمجمة (In > Out) ---
            if data['in'] > data['out'] and data['ratio'] >= MIN_RATIO and data['total'] > MIN_VOL_THRESHOLD:
                if data['accel'] > ACCEL_THRESHOLD or data['ratio'] > 4.0:
                    
                    state["sent"].append(sym)
                    if len(state["sent"]) > 50: state["sent"].pop(0)

                    msg = (
                        f"💀 *SKULL FLOW ALERT* 💀\n\n"
                        f"💵 *#{sym.replace('USDT','')}* | 💎 *Trend Start*\n"
                        f"💰 Price: `{data['price']:.8g}`\n\n"
                        f"📊 *Analysis:*\n"
                        f"  📥 In: `${data['in']:.1f}`\n"
                        f"  ▲ Net: `+${data['net']:.1f}` ✅\n\n"
                        f"📈 Ratio: `{data['ratio']:.2f}x` \n"
                        f"⚡ Accel: `{data['accel']:.1f}x` 🔥\n"
                        f"🕒 {datetime.now().strftime('%H:%M:%S UTC')}"
                    )
                    send_telegram(msg)
                    print(f"🎯 Signal: {sym} Sent!")

    except Exception as e:
        print(f"⚠️ Scan error: {e}")

def main():
    print("💀 SKULL FLOW V31.0 STARTED")
    # اختبار التوكن عند التشغيل
    test = send_telegram("💀 *Skull Flow V31.0*\nنظام رصد السيولة متصل الآن.")
    if test and test.status_code == 401:
        print("🛑 توقف البوت: التوكن غير صحيح. يرجى التأكد من التوكن في إعدادات Railway.")
        return

    while True:
        try:
            scan()
            time.sleep(30)
        except:
            time.sleep(10)

if __name__ == "__main__":
    main()

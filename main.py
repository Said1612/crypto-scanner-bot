# -*- coding: utf-8 -*-
import os, sys, time, requests
from datetime import datetime

# الإعدادات (تأكد من ضبطها في Railway)
TOKEN = os.getenv("TELEGRAM_TOKEN", "your_token_here")
ADMIN_ID = os.getenv("CHAT_ID", "your_id_here")

# --- معايير الاقتناص اللحظي (Logic 💀) ---
ACCELERATION_FACTOR = 3.0    # رصد التضاعف المفاجئ في السيولة
MIN_RATIO = 1.6              # يجب أن يكون الشراء أكبر من البيع بـ 60% على الأقل
MIN_VOL_USDT = 1000          # الحد الأدنى لسيولة الشمعة (لتجنب العملات الميتة)

state = {"sent": []}

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": ADMIN_ID, "text": message, "parse_mode": "Markdown"}, timeout=10)
    except:
        pass

def get_market_flow(sym):
    url = "https://api.binance.com/api/v3/klines"
    try:
        # فحص آخر 5 دقائق للمقارنة اللحظية
        r = requests.get(url, params={"symbol": sym, "interval": "1m", "limit": 6}, timeout=5).json()
        if len(r) < 6: return None
        
        # الشمعة الحالية (دقيقة 0)
        curr = r[-1]
        vol_total = float(curr[7])    # إجمالي السيولة بالدولار
        vol_in = float(curr[10])     # سيولة الشراء (Taker Buy)
        vol_out = vol_total - vol_in # سيولة البيع
        
        # متوسط السيولة في الـ 5 دقائق الماضية (للفلترة)
        prev_avg = sum([float(x[7]) for x in r[:-1]]) / 5
        
        accel = vol_total / prev_avg if prev_avg > 0 else 1.0
        ratio = vol_in / vol_out if vol_out > 0 else 2.0
        price = float(curr[4])
        
        return {
            "in": vol_in,
            "out": vol_out,
            "net": vol_in - vol_out,
            "ratio": ratio,
            "accel": accel,
            "price": price,
            "total": vol_total
        }
    except:
        return None

def scan():
    print(f"💀 Scanning Market Flow... {datetime.now().strftime('%H:%M:%S')}", flush=True)
    try:
        # جلب قائمة الأسعار لفلترة العملات النشطة فقط
        tickers = requests.get("https://api.binance.com/api/v3/ticker/24hr", timeout=10).json()
        
        for t in tickers:
            sym = t['symbol']
            # فحص أزواج USDT فقط وتجاهل العملات الرافعة (UP/DOWN)
            if not sym.endswith("USDT") or any(x in sym for x in ["UP", "DOWN", "BEAR", "BULL"]): continue
            if sym in state["sent"]: continue

            # تحليل التدفق (Flow)
            data = get_market_flow(sym)
            if not data: continue

            # --- الشرط الذهبي (💀 Logic) ---
            # 1. الشراء أكبر من البيع (In > Out)
            # 2. وجود تسارع مفاجئ (Acceleration) أو نسبة شراء قوية جداً
            if data['in'] > data['out'] and data['ratio'] >= MIN_RATIO and data['total'] > MIN_VOL_USDT:
                if data['accel'] > ACCELERATION_FACTOR or data['ratio'] > 3.0:
                    
                    state["sent"].append(sym)
                    if len(state["sent"]) > 50: state["sent"].pop(0)

                    msg = (
                        f"💀 *SKULL FLOW DETECTED* 💀\n\n"
                        f"💵 *#{sym.replace('USDT','')}* | 🟢 *In > Out*\n"
                        f"💰 Price: `{data['price']:.8g}`\n\n"
                        f"📊 *Flow Analysis:*\n"
                        f"  📥 In: `${data['in']:.1f}`\n"
                        f"  ▲ Net: `+${data['net']:.1f}` ✅\n\n"
                        f"📈 Ratio: `{data['ratio']:.2f}x` 🔥\n"
                        f"⚡ Accel: `{data['accel']:.1f}x` \n"
                        f"🕒 {datetime.now().strftime('%H:%M:%S UTC')}"
                    )
                    send_telegram(msg)
                    print(f"🎯 Signal: {sym} | Ratio: {data['ratio']:.2f}", flush=True)

    except Exception as e:
        print(f"⚠️ Scan Error: {e}", flush=True)

def main():
    print("💀 SKULL FLOW V30.0 STARTED", flush=True)
    send_telegram("💀 *Skull Flow V30.0 Online*\nنظام رصد السيولة اللحظي بدأ العمل.")
    while True:
        try:
            scan()
            time.sleep(30) # فحص كل 30 ثانية كما في Wolf Flow
        except Exception as e:
            print(f"❌ Main Loop Error: {e}", flush=True)
            time.sleep(10)

if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
import os, time, requests
from datetime import datetime

# --- الإعدادات (تعديل مباشر) ---
TOKEN = "your_token_here"
ADMIN_ID = "your_id_here"

# --- الإعدادات الجديدة لتقليل الأخطاء ومنع الانعكاس ---
MIN_VOL_USDT = 2000          # رفع الحد الأدنى لسيولة الشمعة (فلترة العملات الضعيفة)
BUY_RATIO_REQUIRED = 2.5     # لن يرسل إشارة إلا إذا كان الشراء 2.5 ضعف البيع
PRICE_PUMP_MIN = 0.8         # يجب أن تكون العملة صاعدة بنسبة 0.8% على الأقل في آخر دقيقة
COOLDOWN = 600               # منع تكرار نفس العملة لمدة 10 دقائق

state = {"sent": {}}

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": ADMIN_ID, "text": message, "parse_mode": "Markdown"}, timeout=10)
    except: pass

def get_data():
    # استخدام التيكر المباشر للحصول على بيانات دقيقة
    url = "https://api.binance.com/api/v3/ticker/24hr"
    try:
        return requests.get(url, timeout=10).json()
    except: return []

def check_flow(sym):
    # فحص تفصيلي للسيولة (Taker Buy/Sell)
    url = "https://api.binance.com/api/v3/klines"
    try:
        r = requests.get(url, params={"symbol": sym, "interval": "1m", "limit": 2}, timeout=5).json()
        if not r: return None
        
        curr = r[-1]
        total_v = float(curr[7]) # إجمالي السيولة بالدولار
        buy_v = float(curr[10]) # سيولة الشراء الحقيقية
        sell_v = total_v - buy_v
        
        if sell_v == 0: return None
        
        ratio = buy_v / sell_v
        price = float(curr[4])
        change = ((float(curr[4]) - float(curr[1])) / float(curr[1])) * 100
        
        return {"ratio": ratio, "vol": total_v, "price": price, "change": change, "buy": buy_v}
    except: return None

def main():
    print("💀 SKULL FLOW REBORN - ACTIVE")
    send_telegram("💀 *Skull Flow System Reborn*\nتم استعادة النسخة المستقرة مع تشديد فلاتر الدخول.")
    
    while True:
        try:
            tickers = get_data()
            # ترتيب حسب العملات الأكثر صعوداً حالياً لسرعة الاقتناص
            top_movers = [t for t in tickers if t['symbol'].endswith("USDT") and float(t['priceChangePercent']) > 2]
            
            for t in top_movers:
                sym = t['symbol']
                now = time.time()
                
                if sym in state["sent"] and now - state["sent"][sym] < COOLDOWN: continue
                
                f = check_flow(sym)
                # --- الفلتر الجديد القوي ---
                if f and f['ratio'] >= BUY_RATIO_REQUIRED and f['vol'] >= MIN_VOL_USDT and f['change'] >= PRICE_PUMP_MIN:
                    
                    state["sent"][sym] = now
                    
                    msg = (
                        f"💀 *SKULL FLOW SIGNAL* 💀\n\n"
                        f"💵 *#{sym.replace('USDT','')}* | 🟢 *Strong Buy*\n"
                        f"💰 Price: `{f['price']:.8g}`\n\n"
                        f"📊 *Flow Analysis:*\n"
                        f"  📥 Buy Vol: `${f['buy']/1000:.1f}K` ✅\n"
                        f"  📈 Ratio: `{f['ratio']:.2f}x` 🔥\n"
                        f"  ⚡ 1m Change: `{f['change']:+.2f}%` \n\n"
                        f"🕒 {datetime.now().strftime('%H:%M:%S UTC')}"
                    )
                    send_telegram(msg)
                    print(f"🎯 Signal: {sym} | Ratio: {f['ratio']:.2f}")
            
            time.sleep(30)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()

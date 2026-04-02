# -*- coding: utf-8 -*-
import os, time, requests
from datetime import datetime

# --- الإعدادات الخاصة بـ Mafio Bot ---
TOKEN = "your_token_here"
CHAT_ID = "your_id_here"

# --- إعدادات الاستراتيجية المتقدمة (الفلترة الذكية) ---
MIN_24H_VOL = 10000000      # 10 مليون دولار كحد أدنى للسيولة اليومية (للأمان)
RATIO_THRESHOLD = 2.4       # قوة الشراء يجب أن تفوق البيع بـ 2.4 مرة
MIN_PUMP_1M = 0.6           # يجب أن يكون السعر في حالة صعود فعلي بنسبة 0.6%
COOLDOWN = 600              # تكرار العملة الواحدة كل 10 دقائق فقط

state = {"sent_signals": {}}

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=10)
    except: pass

def get_market_movers():
    """جلب العملات التي تشهد حركة غير عادية"""
    try:
        r = requests.get("https://api.binance.com/api/v3/ticker/24hr", timeout=10).json()
        # نركز فقط على العملات الصاعدة التي لديها سيولة محترمة
        return [t for t in r if t['symbol'].endswith("USDT") and float(t['priceChangePercent']) > 1.0]
    except: return []

def analyze_mafio_logic(symbol):
    """تحليل تدفق السيولة اللحظي (Mafio Strategy)"""
    try:
        url = "https://api.binance.com/api/v3/klines"
        # فحص آخر شمعة دقيقة واحدة
        params = {"symbol": symbol, "interval": "1m", "limit": 1}
        r = requests.get(url, params=params, timeout=5).json()
        if not r: return None
        
        candle = r[-1]
        close_p = float(candle[4])
        open_p = float(candle[1])
        
        total_q_vol = float(candle[7])    # إجمالي السيولة بالدولار
        taker_buy_vol = float(candle[10]) # سيولة الشراء العنيفة (Market Buys)
        sell_vol = total_q_vol - taker_buy_vol
        
        if sell_vol <= 0: return None
        
        ratio = taker_buy_vol / sell_vol
        change = ((close_p - open_p) / open_p) * 100
        
        return {
            "price": close_p,
            "ratio": ratio,
            "change": change,
            "vol": total_q_vol
        }
    except: return None

def main():
    print("💀 MAFIO BOT ONLINE - READY TO HUNT")
    send_telegram("💀 *Mafio Bot System Online*\nتم تفعيل استراتيجية اقتناص السيولة المتقدمة.")
    
    while True:
        try:
            movers = get_market_movers()
            
            for m in movers:
                sym = m['symbol']
                now = time.time()
                
                # 1. فحص الكول داون والسيولة اليومية
                if sym in state["sent_signals"] and now - state["sent_signals"][sym] < COOLDOWN: continue
                if float(m['quoteVolume']) < MIN_24H_VOL: continue

                # 2. تحليل Mafio للسيولة اللحظية
                analysis = analyze_mafio_logic(sym)
                
                # 3. الشرط القاطع للدخول (الدقة العالية)
                if analysis and analysis['ratio'] >= RATIO_THRESHOLD and analysis['change'] >= MIN_PUMP_1M:
                    
                    state["sent_signals"][sym] = now
                    
                    msg = (
                        f"💀 *MAFIO ALERT* 💀\n\n"
                        f"💵 *#{sym.replace('USDT','')}* | 🎯 *Snipe Target*\n"
                        f"💰 Price: `{analysis['price']:.8g}`\n\n"
                        f"📊 *Strategy Metrics:*\n"
                        f"  🔥 Buy Power: `{analysis['ratio']:.2f}x` \n"
                        f"  ⚡ 1m Momentum: `{analysis['change']:+.2f}%` \n"
                        f"  💎 Candle Flow: `${analysis['vol']/1000:.1f}K` ✅\n\n"
                        f"🕒 {datetime.now().strftime('%H:%M:%S UTC')}"
                    )
                    send_telegram(msg)
                    print(f"✅ Mafio Snipe: {sym}")

            time.sleep(25) # توازن مثالي لمنع حظر الـ IP
        except Exception as e:
            print(f"⚠️ Warning: {e}")
            time.sleep(15)

if __name__ == "__main__":
    main()

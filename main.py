# -*- coding: utf-8 -*-
import os, time, requests
from datetime import datetime

# --- الإعدادات ---
TOKEN = "your_token_here"
CHAT_ID = "your_id_here"

# --- فلاتر Mafio (تم تعديلها قليلاً لتكون أكثر مرونة في البداية) ---
MIN_24H_VOL = 5000000       # 5 مليون دولار (بدلاً من 10 لزيادة الفرص)
RATIO_THRESHOLD = 2.0       # نسبة الشراء (ضعف البيع)
MOMENTUM_1M = 0.4           # الحد الأدنى للصعود اللحظي
COOLDOWN = 300              # 5 دقائق بين كل إشارة لنفس العملة

state = {"sent": {}}

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=10)
    except: pass

def get_market():
    """جلب قائمة العملات"""
    try:
        # إضافة رسالة في السجلات لنعلم أن البوت يتصل بباينانس
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Connecting to Binance API...")
        r = requests.get("https://api.binance.com/api/v3/ticker/24hr", timeout=10).json()
        return [t for t in r if t['symbol'].endswith("USDT")]
    except Exception as e:
        print(f"⚠️ Connection Error: {e}")
        return []

def analyze(sym):
    """تحليل السيولة"""
    try:
        url = "https://api.binance.com/api/v3/klines"
        r = requests.get(url, params={"symbol": sym, "interval": "1m", "limit": 1}, timeout=5).json()
        if not r: return None
        
        c = r[-1]
        total_v = float(c[7])
        buy_v = float(c[10])
        sell_v = total_v - buy_v
        
        if sell_v <= 0: return None
        
        ratio = buy_v / sell_v
        change = ((float(c[4]) - float(c[1])) / float(c[1])) * 100
        
        return {"p": float(c[4]), "r": ratio, "ch": change, "v": total_v}
    except: return None

def main():
    print("💀 MAFIO BOT V41.0 - ENGINE START")
    send_telegram("💀 *Mafio Bot V41.0*\nEngine started. Monitoring market flow...")
    
    while True:
        try:
            tickers = get_market()
            total_checked = 0
            
            # ترتيب العملات حسب نسبة التغير في 24 ساعة (الأقوى أولاً)
            top_tickers = sorted(tickers, key=lambda x: float(x['priceChangePercent']), reverse=True)[:100]

            for t in top_tickers:
                sym = t['symbol']
                
                # فحص السيولة اليومية
                if float(t['quoteVolume']) < MIN_24H_VOL: continue
                
                # فحص الكول داون
                if sym in state["sent"] and time.time() - state["sent"][sym] < COOLDOWN: continue

                analysis = analyze(sym)
                total_checked += 1
                
                # طباعة كل 20 عملة في السجلات لنرى أن البوت يعمل
                if total_checked % 20 == 0:
                    print(f"--- Checking: {sym} | Ratio: {analysis['r']:.2f} if valid ---")

                if analysis and analysis['r'] >= RATIO_THRESHOLD and analysis['ch'] >= MOMENTUM_1M:
                    state["sent"][sym] = time.time()
                    
                    msg = (
                        f"💀 *MAFIO SNIPE* 💀\n\n"
                        f"💵 *#{sym.replace('USDT','')}*\n"
                        f"💰 Price: `{analysis['p']:.8g}`\n"
                        f"🔥 Ratio: `{analysis['r']:.2f}x` \n"
                        f"📈 1m: `{analysis['ch']:+.2f}%` \n"
                        f"💎 Vol: `${analysis['v']/1000:.1f}K` ✅"
                    )
                    send_telegram(msg)
                    print(f"🎯 SIGNAL SENT: {sym}")

            print(f"✅ Cycle Complete. Checked {total_checked} active symbols.")
            time.sleep(20) # راحة قصيرة لتجنب الحظر
            
        except Exception as e:
            print(f"❌ Main Loop Error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()

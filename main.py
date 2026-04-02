# -*- coding: utf-8 -*-
import os, time, requests
from datetime import datetime

# --- الإعدادات الأساسية ---
TOKEN = "your_token_here"
CHAT_ID = "your_id_here"

# --- إعدادات الاستراتيجية (معدلة للسرعة والدقة) ---
MIN_VOLUME_24H = 10000000   # 10 مليون دولار (لضمان وجود حيتان)
BUY_RATIO_LIMIT = 2.2       # نسبة الشراء
MOMENTUM_REQUIRED = 0.5     # زخم الصعود اللحظي
CHECK_LIMIT = 50            # فحص أقوى 50 عملة فقط في كل دورة (للسرعة القصوى)

sent_list = {}

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=5)
    except: pass

def main():
    print("💀 MAFIO BOT V42.0 - FAST SCAN STARTING")
    send_telegram("💀 *Mafio Bot V42.0*\nالنسخة السريعة قيد التشغيل... بدأت المراقبة.")

    while True:
        try:
            # 1. جلب العملات وفرزها فوراً حسب السيولة
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Scanning Market...")
            resp = requests.get("https://api.binance.com/api/v3/ticker/24hr", timeout=10).json()
            
            # فلترة العملات القوية فقط (USDT وصعود > 1% وسيولة عالية)
            active_symbols = [
                t for t in resp 
                if t['symbol'].endswith("USDT") and float(t['quoteVolume']) > MIN_VOLUME_24H
            ]
            # ترتيب حسب نسبة التغير واختيار القمة فقط
            active_symbols = sorted(active_symbols, key=lambda x: float(x['priceChangePercent']), reverse=True)[:CHECK_LIMIT]

            for t in active_symbols:
                sym = t['symbol']
                
                # فحص الكول داون
                if sym in sent_list and time.time() - sent_list[sym] < 600: continue

                # 2. تحليل السيولة اللحظية (السر الحقيقي)
                klines_url = "https://api.binance.com/api/v3/klines"
                k_resp = requests.get(klines_url, params={"symbol": sym, "interval": "1m", "limit": 1}, timeout=5).json()
                
                if not k_resp: continue
                candle = k_resp[-1]
                
                total_q_vol = float(candle[7])    # إجمالي السيولة بالدولار في الدقيقة
                buy_q_vol = float(candle[10])     # سيولة الشراء
                sell_q_vol = total_q_vol - buy_q_vol
                
                if sell_q_vol <= 0: continue
                ratio = buy_q_vol / sell_q_vol
                change = ((float(candle[4]) - float(candle[1])) / float(candle[1])) * 100

                # 3. شرط الاقتناص 🎯
                if ratio >= BUY_RATIO_LIMIT and change >= MOMENTUM_REQUIRED:
                    sent_list[sym] = time.time()
                    
                    msg = (
                        f"💀 *MAFIO SNIPE* 💀\n\n"
                        f"💵 *#{sym.replace('USDT','')}*\n"
                        f"💰 Price: `{float(candle[4]):.8g}`\n"
                        f"🔥 Ratio: `{ratio:.2f}x` 🔥\n"
                        f"📈 1m: `{change:+.2f}%` \n"
                        f"💎 Candle Vol: `${total_q_vol/1000:.1f}K` ✅"
                    )
                    send_telegram(msg)
                    print(f"✅ SIGNAL: {sym} | Ratio: {ratio:.2f}")

            # رسالة نبض القلب في السجل لتعرف أن البوت لم يتوقف
            print(f"✨ Cycle Complete. Sleeping 15s...")
            time.sleep(15)

        except Exception as e:
            print(f"⚠️ Error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()

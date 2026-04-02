# -*- coding: utf-8 -*-
import os, time, requests
from datetime import datetime

# --- إعدادات الحساب ---
TOKEN = "your_token_here"
CHAT_ID = "your_id_here"

# --- استراتيجية Wolf-Mafio الهجينة ---
MIN_VOLUME_24H = 5000000     # سيولة جيدة
RATIO_STRENGTH = 2.0        # قوة شراء ضعف البيع
MOMENTUM_STRENGTH = 0.3     # زخم بداية الانفجار
ALERT_LEVEL_TARGET = 3      # لا ترسل تنبيه ذهبي إلا بعد رصد القوة 3 مرات (تشابه 🔔)

# مخزن لمتابعة تكرار التنبيهات لكل عملة
market_watch = {} 

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=5)
    except: pass

def main():
    print("💀 MAFIO V60: WOLF STALKER MODE ACTIVE")
    send_telegram("💀 *Mafio V60: Wolf Stalker Mode*\nتم فك شفرة استراتيجية التنبيهات المتكررة. بدأ القنص..")

    while True:
        try:
            print(f"📡 Scanning for Accumulation... {datetime.now().strftime('%H:%M:%S')}")
            
            # جلب أقوى العملات سيولة
            r = requests.get("https://api.binance.com/api/v3/ticker/24hr", timeout=10).json()
            movers = [t for t in r if t['symbol'].endswith("USDT") and float(t['quoteVolume']) > MIN_VOLUME_24H]
            movers = sorted(movers, key=lambda x: float(x['priceChangePercent']), reverse=True)[:40]

            for t in movers:
                symbol = t['symbol']
                
                # تحليل الشمعة اللحظية
                k_data = requests.get("https://api.binance.com/api/v3/klines", 
                                     params={"symbol": symbol, "interval": "1m", "limit": 1}, timeout=5).json()
                if not k_data: continue
                
                candle = k_data[-1]
                vol_total = float(candle[7])
                vol_buy = float(candle[10])
                ratio = vol_buy / (vol_total - vol_buy) if (vol_total - vol_buy) > 0 else 2.0
                change = ((float(candle[4]) - float(candle[1])) / float(candle[1])) * 100

                # --- نظام التنبيه المتكرر (The Alert System) ---
                if ratio >= RATIO_STRENGTH and change >= MOMENTUM_STRENGTH:
                    if symbol not in market_watch:
                        market_watch[symbol] = {'count': 1, 'last_time': time.time()}
                    else:
                        market_watch[symbol]['count'] += 1
                        market_watch[symbol]['last_time'] = time.time()

                    count = market_watch[symbol]['count']
                    print(f"🔔 Signal Level {count} for {symbol}")

                    # إرسال تنبيه "ذهبي" فقط عند الوصول للمستوى المطلوب (تشابه 🔔3 فأعلى)
                    if count >= ALERT_LEVEL_TARGET:
                        msg = (
                            f"💀 *MAFIO GOLDEN SNIPE* 🔔{count}\n\n"
                            f"💵 *#{symbol.replace('USDT','')}*\n"
                            f"🏁 Entry: `${float(candle[4]):.8g}`\n"
                            f"📈 Momentum: `{change:+.2f}%`\n"
                            f"🔥 Ratio: `{ratio:.2f}x`\n"
                            f"🏆 Status: *ACCUMULATION DETECTED*"
                        )
                        send_telegram(msg)
                        market_watch[symbol]['count'] = 0 # تصفير العداد بعد الإرسال
                        print(f"✅ WINNING SIGNAL SENT: {symbol}")

            # تنظيف العملات القديمة من الذاكرة كل دورة
            current_time = time.time()
            for s in list(market_watch.keys()):
                if current_time - market_watch[s]['last_time'] > 1800: # حذف بعد 30 دقيقة خمول
                    del market_watch[s]

            time.sleep(15)

        except Exception as e:
            print(f"⚠️ Note: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()

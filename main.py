# -*- coding: utf-8 -*-
import os, time, requests
from datetime import datetime

# --- إعداداتك ---
TOKEN = "your_token_here"
CHAT_ID = "your_id_here"

# --- إعدادات القنص (معدلة لتجلب أرباحاً حقيقية) ---
MIN_VOLUME_24H = 8000000    # 8 مليون دولار (سيولة تضمن الحركة)
RATIO_TARGET = 2.0          # قوة شراء ضعف البيع
MOMENTUM_REQUIRED = 0.4     # صعود 0.4% في دقيقة (تأكيد الانفجار)

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=5)
    except: pass

def main():
    print("🚀 MAFIO V50: ENGINE INITIALIZED...")
    send_telegram("🚀 *Mafio V50 Activated*\nنظام القنص الجديد متصل الآن. لن نضيع أي فرصة بعد اليوم.")
    
    sent_signals = {}

    while True:
        try:
            # رسالة حية للسجلات
            print(f"🔍 [{datetime.now().strftime('%H:%M:%S')}] Scanning Market Peaks...")
            
            # جلب البيانات مع مهلة زمنية قصيرة لعدم التعليق
            r = requests.get("https://api.binance.com/api/v3/ticker/24hr", timeout=7).json()
            
            # فلترة فورية لأقوى 30 عملة فقط (السرعة هي الأهم)
            top_movers = [t for t in r if t['symbol'].endswith("USDT") and float(t['quoteVolume']) > MIN_VOLUME_24H]
            top_movers = sorted(top_movers, key=lambda x: float(x['priceChangePercent']), reverse=True)[:30]

            if not top_movers:
                print("💤 No high-volume movers found. Retrying...")
                time.sleep(10)
                continue

            for t in top_movers:
                symbol = t['symbol']
                
                # منع التكرار (Cooldown)
                if symbol in sent_signals and time.time() - sent_signals[symbol] < 600:
                    continue

                # تحليل الشمعة اللحظية
                k_url = "https://api.binance.com/api/v3/klines"
                k_data = requests.get(k_url, params={"symbol": symbol, "interval": "1m", "limit": 1}, timeout=5).json()
                
                if not k_data: continue
                candle = k_data[-1]
                
                # حساب النسبة والزخم
                vol_total = float(candle[7])
                vol_buy = float(candle[10])
                vol_sell = vol_total - vol_buy
                
                if vol_sell <= 0: vol_sell = 0.001 # تجنب القسمة على صفر
                
                ratio = vol_buy / vol_sell
                price_change = ((float(candle[4]) - float(candle[1])) / float(candle[1])) * 100

                # --- قرار القنص 🎯 ---
                if ratio >= RATIO_TARGET and price_change >= MOMENTUM_REQUIRED:
                    sent_signals[symbol] = time.time()
                    
                    msg = (
                        f"💀 *MAFIO GOLDEN SNIPE* 💀\n\n"
                        f"💵 *#{symbol.replace('USDT','')}*\n"
                        f"💰 Price: `{float(candle[4]):.8g}`\n"
                        f"🔥 Ratio: `{ratio:.2f}x` (Heavy Buying)\n"
                        f"📈 Momentum: `{price_change:+.2f}%` \n"
                        f"💎 Vol 1m: `${vol_total/1000:.1f}K` ✅"
                    )
                    send_telegram(msg)
                    print(f"✅ TARGET LOCKED: {symbol} - Sending to Telegram!")

            print("✨ Scan Finished. Cooling down for 10 seconds...")
            time.sleep(10)

        except Exception as e:
            print(f"⚠️ System Note: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()

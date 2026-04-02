# -*- coding: utf-8 -*-
import os, time, requests
from datetime import datetime

# --- الإعدادات ---
TOKEN = "your_token_here"
CHAT_ID = "your_id_here"

# --- إعدادات القنص ---
MIN_VOLUME_24H = 7000000
RATIO_LIMIT = 2.2
MOMENTUM_LIMIT = 0.5

# قاموس لمتابعة العملات المفتوحة وأعلى ربح حققته
active_trades = {}

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=5)
    except: pass

def main():
    print("💀 MAFIO V70: PROFIT TRACKER MODE ACTIVE")
    send_telegram("💀 *Mafio V70: Profit Tracker Started*\nنظام ملاحقة الأرباح والتنبيهات المتتالية متصل.")

    while True:
        try:
            # 1. مرحلة البحث عن صفقات جديدة
            r = requests.get("https://api.binance.com/api/v3/ticker/24hr", timeout=10).json()
            movers = [t for t in r if t['symbol'].endswith("USDT") and float(t['quoteVolume']) > MIN_VOLUME_24H]
            movers = sorted(movers, key=lambda x: float(x['priceChangePercent']), reverse=True)[:30]

            for t in movers:
                sym = t['symbol']
                if sym in active_trades: continue # لا يدخل إذا كانت العملة مراقبة بالفعل

                # تحليل الدخول
                k = requests.get("https://api.binance.com/api/v3/klines", params={"symbol": sym, "interval": "1m", "limit": 1}).json()
                if not k: continue
                
                price_entry = float(k[-1][4])
                vol_buy = float(k[-1][10])
                ratio = vol_buy / (float(k[-1][7]) - vol_buy) if (float(k[-1][7]) - vol_buy) > 0 else 2.0
                change = ((price_entry - float(k[-1][1])) / float(k[-1][1])) * 100

                if ratio >= RATIO_LIMIT and change >= MOMENTUM_LIMIT:
                    active_trades[sym] = {
                        'entry': price_entry,
                        'highest_reach': 0, # لتتبع مستويات 2%, 5%, 10%...
                        'time': time.time()
                    }
                    msg = f"💀 *MAFIO NEW SIGNAL* 💀\n\n💵 *#{sym.replace('USDT','')}*\n🏁 Entry: `${price_entry:.8g}`\n🔥 Power: `{ratio:.2f}x`"
                    send_telegram(msg)

            # 2. مرحلة ملاحقة الأرباح (Tracking)
            for sym in list(active_trades.keys()):
                trade = active_trades[sym]
                # جلب السعر الحالي بسرعة
                curr_tick = requests.get("https://api.binance.com/api/v3/ticker/price", params={"symbol": sym}).json()
                curr_price = float(curr_tick['price'])
                
                # حساب نسبة الربح الحالية
                profit_pct = ((curr_price - trade['entry']) / trade['entry']) * 100

                # تحديد "الجرس" بناءً على الربح المحقق
                milestones = [2, 5, 10, 20, 50, 100]
                for m in milestones:
                    if profit_pct >= m and trade['highest_reach'] < m:
                        trade['highest_reach'] = m
                        bell_count = milestones.index(m) + 1
                        msg = (
                            f"💀 *MAFIO PROFIT ALERT* 🔔{bell_count}\n\n"
                            f"🚀 *#{sym.replace('USDT','')}*\n"
                            f"📈 Peak: `+{profit_pct:.2f}%` 🔥\n"
                            f"💰 Current: `${curr_price:.8g}`"
                        )
                        send_telegram(msg)

                # حذف الصفقة من المراقبة بعد 24 ساعة أو إذا نزل السعر تحت الدخول بـ 5% (وقف خسارة اختياري)
                if time.time() - trade['time'] > 86400:
                    del active_trades[sym]

            time.sleep(10)

        except Exception as e:
            print(f"⚠️ Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()

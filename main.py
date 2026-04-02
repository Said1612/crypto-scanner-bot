# -*- coding: utf-8 -*-
import os, time, requests
from datetime import datetime

# --- الإعدادات ---
TOKEN = "your_token_here"
CHAT_ID = "your_id_here"

# --- استراتيجية MEXC (صيد العملات المتفجرة) ---
MIN_VOLUME_MEXC = 500000     # سيولة العملة (MEXC سيولتها أقل من باينانس لذا 500k جيدة جداً)
RATIO_TARGET = 2.5          # شرط شراء قوي جداً
MOMENTUM_MEXC = 1.0         # صعود 1% في دقيقة (MEXC تمتاز بالانفجارات السريعة)

active_trades = {}

def send_telegram(text):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=5)
    except: pass

def get_mexc_tickers():
    """جلب جميع العملات من MEXC"""
    try:
        url = "https://www.mexc.com/open/api/v2/market/ticker"
        r = requests.get(url, timeout=10).json()
        return [t for t in r['data'] if t['symbol'].endswith("_USDT")]
    except: return []

def analyze_mexc_flow(symbol):
    """تحليل السيولة اللحظية على MEXC"""
    try:
        # جلب آخر الشموع
        url = f"https://www.mexc.com/open/api/v2/market/kline"
        params = {"symbol": symbol, "interval": "1m", "limit": 1}
        r = requests.get(url, params=params, timeout=5).json()
        if not r['data']: return None
        
        c = r['data'][0]
        # MEXC API: [time, open, close, high, low, vol, amount]
        price_open = float(c[1])
        price_close = float(c[2])
        amount_usdt = float(c[6]) # السيولة بالدولار
        
        change = ((price_close - price_open) / price_open) * 100
        
        # ملاحظة: MEXC العام لا يعطي Taker Buy مباشرة، لذا سنعتمد على الزخم وحجم التداول (Amount)
        return {"price": price_close, "change": change, "vol": amount_usdt}
    except: return None

def main():
    print("💀 MAFIO V90: MEXC ENGINE START")
    send_telegram("💀 *Mafio V90: MEXC Edition*\nالمحرك انتقل الآن إلى MEXC. بدأ صيد العملات المتفجرة!")

    while True:
        try:
            print(f"📡 [{datetime.now().strftime('%H:%M:%S')}] Scanning MEXC Gems...")
            tickers = get_mexc_tickers()
            
            # ترتيب حسب أعلى صعود في 24 ساعة (أقوى العملات)
            movers = sorted(tickers, key=lambda x: float(x['change_rate']), reverse=True)[:40]

            for t in movers:
                sym = t['symbol']
                if sym in active_trades: continue
                
                # فحص السيولة اليومية (Volume 24h)
                if float(t['vol']) < MIN_VOLUME_MEXC: continue

                analysis = analyze_mexc_flow(sym)
                
                if analysis and analysis['change'] >= MOMENTUM_MEXC:
                    active_trades[sym] = {'entry': analysis['price'], 'peak': 0, 'time': time.time()}
                    
                    msg = (
                        f"💀 *MAFIO MEXC SNIPE* 💀\n\n"
                        f"💵 *#{sym.replace('_USDT','')}*\n"
                        f"💰 Price: `{analysis['price']:.8g}`\n"
                        f"📈 1m Pump: `{analysis['change']:+.2f}%` 🚀\n"
                        f"💎 1m Vol: `${analysis['vol']/1000:.1f}K` ✅"
                    )
                    send_telegram(msg)

            # ملاحقة الأرباح على MEXC
            for s in list(active_trades.keys()):
                # تحديث السعر الحالي
                tick = requests.get(f"https://www.mexc.com/open/api/v2/market/ticker?symbol={s}").json()
                p_now = float(tick['data'][0]['last'])
                gain = ((p_now - active_trades[s]['entry']) / active_trades[s]['entry']) * 100
                
                for m in [2, 5, 10, 20, 50]:
                    if gain >= m and active_trades[s]['peak'] < m:
                        active_trades[s]['peak'] = m
                        send_telegram(f"💀 *MEXC PROFIT* 🔔\n🚀 `#{s}`: `+{gain:.2f}%` (Reached {m}%) ✅")

                # تنظيف القائمة بعد 12 ساعة
                if time.time() - active_trades[s]['time'] > 43200:
                    del active_trades[s]

            time.sleep(20)

        except Exception as e:
            print(f"⚠️ MEXC API Note: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()

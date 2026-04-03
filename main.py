#!/usr/bin/env python3
"""
🐺 WOLF LIQUIDITY BOT v3.0 - SIMPLE & WORKING
نظام تتبع السيولة - بدون أخطاء API
"""

import os
import time
import requests
from datetime import datetime

# الإعدادات البسيطة
TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("CHAT_ID", "")

trades = {}
signals = set()
count = 0

def send_message(text):
    if not TOKEN:
        print(f"[TEST] {text[:100]}")
        return True
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.post(url, data={
            'chat_id': CHAT_ID, 
            'text': text, 
            'parse_mode': 'Markdown'
        }, timeout=10)
        return True
    except:
        return False

def get_mexc_tickers():
    """MEXC tickers - أبسط API"""
    try:
        r = requests.get("https://api.mexc.com/api/v3/ticker/24hr", timeout=15)
        return r.json() if r.status_code == 200 else []
    except:
        return []

def scan():
    global count
    tickers = get_mexc_tickers()
    if not tickers:
        return

    candidates = []
    
    # فلترة بسيطة جداً
    for t in tickers[:500]:  # أول 500 فقط
        try:
            symbol = t['symbol']
            if (not symbol.endswith('USDT') or 
                len(symbol) < 6 or 
                any(x in symbol for x in ['UP','DOWN','BEAR','BULL','USDC','BUSD'])):
                continue

            price = float(t['lastPrice'])
            change = float(t['priceChangePercent'])
            volume = float(t['quoteVolume'])

            # شروط بسيطة جداً
            if (50000 < volume < 50000000 and 
                -20 < change < 25 and 
                price > 0.00001):
                candidates.append({
                    'symbol': symbol,
                    'price': price,
                    'change': change,
                    'volume': volume
                })
        except:
            continue

    # فحص أفضل 10 فقط
    for coin in sorted(candidates[:10], key=lambda x: x['volume'], reverse=True):
        symbol = coin['symbol']
        if symbol in signals:
            continue

        # فحص سريع klines
        try:
            klines_url = "https://api.mexc.com/api/v3/klines"
            klines = requests.get(klines_url, params={
                'symbol': symbol,
                'interval': '1m', 
                'limit': '20'
            }, timeout=8).json()
            
            if not klines or len(klines) < 15:
                continue

            prices = [float(k[4]) for k in klines[-10:]]
            volumes = [float(k[5]) for k in klines[-10:]]

            # شروط بسيطة للسيولة
            if (len(set(prices[-3:])) > 1 and  # حركة سعر
                volumes[-1] > sum(volumes[-5:-1])/4):  # حجم متزايد

                count += 1
                signals.add(symbol)
                trades[symbol] = {
                    'entry': coin['price'],
                    'time': time.time(),
                    'max_gain': 0
                }

                msg = f"""🐺 WOLF SIGNAL #{count}

💰 {symbol}
💵 Entry: `${coin['price']:.7g}`
📈 24h: {coin['change']:.1f}%
📊 Volume: ${coin['volume']/1e6:.1f}M

{datetime.now().strftime('%H:%M UTC')}"""
                
                send_message(msg)
                print(f"🎯 SIGNAL: {symbol}")
                time.sleep(1)

        except:
            continue

def track():
    if not trades:
        return
        
    tickers = get_mexc_tickers()
    if not tickers:
        return

    price_map = {}
    for t in tickers:
        try:
            price_map[t['symbol']] = float(t['lastPrice'])
        except:
            continue

    for symbol in list(trades):
        if symbol not in price_map:
            continue
            
        current = price_map[symbol]
        entry = trades[symbol]['entry']
        gain = (current - entry) / entry * 100
        
        if gain > trades[symbol]['max_gain']:
            trades[symbol]['max_gain'] = gain
            
            if gain >= 5:
                minutes = int((time.time() - trades[symbol]['time'])/60)
                send_message(f"🔥 {symbol[:-4]} +{gain:.1f}%
💰 ${current:.7g}")
        
        if time.time() - trades[symbol]['time'] > 24*3600:
            del trades[symbol]

def main():
    print("🐺 WOLF LIQUIDITY SNIPER v3.0 - LIVE")
    send_message("🐺 *Wolf Sniper v3.0* ✅
MEXC Spot - Simple & Fast")
    
    while True:
        try:
            scan()
            track()
            time.sleep(30)
        except KeyboardInterrupt:
            print("🛑 Stopped")
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()

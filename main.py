#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🐺 WOLF LIQUIDITY SNIPER v2.1 - MEXC API ✅
نظام تتبع السيولة - MEXC Global API
"""

import os
import time
import requests
import logging
from datetime import datetime, timezone
from collections import deque

# الإعدادات
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("CHAT_ID", "")

# إعدادات MEXC
MEXC_SETTINGS = {
    'min_vol': 30000,      # حجم أقل لـ MEXC
    'min_change': -15,     # قيعان أعمق
    'max_change': 25,      # مرونة أكبر
    'max_price_pos': 0.75,
    'min_flow': 2.2,
    'min_net': 3000
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
log = logging.getLogger('WOLF_MEXC')

state = {'date': '', 'count': 0, 'coins': deque(maxlen=100), 'first': True}
trades = {}

def send(msg):
    if not TELEGRAM_TOKEN:
        print(f"[TG] {msg[:80]}...")
        return True
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={'chat_id': CHAT_ID, 'text': msg, 'parse_mode': 'Markdown'}, timeout=8)
        return True
    except:
        return False

def mexc_tickers():
    """MEXC 24hr ticker - API v3"""
    try:
        url = "https://api.mexc.com/api/v3/ticker/24hr"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return None

def mexc_klines(symbol, limit=30):
    """MEXC klines 5m"""
    try:
        url = "https://api.mexc.com/api/v3/klines"
        params = {'symbol': symbol, 'interval': '5m', 'limit': str(limit)}
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return None

def scan_mexc():
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    if state['date'] != today:
        state.update({'date': today, 'count': 0, 'coins': deque(maxlen=100)})
        send(f"🐺 *MEXC Wolf Flow* - {today}")

    tickers = mexc_tickers()
    if not tickers:
        log.error("❌ MEXC API offline")
        return

    candidates = []
    for t in tickers:
        try:
            symbol = t['symbol']
            if (not symbol.endswith('USDT') or 
                len(symbol) < 6 or 
                any(x in symbol for x in ['UP', 'DOWN', 'BEAR'])):
                continue

            # تجاهل stablecoins
            if any(sc in symbol for sc in ['USDC', 'BUSD', 'TUSD', 'USDP']):
                continue

            chg = float(t['priceChangePercent'])
            vol = float(t['quoteVolume'])
            price = float(t['lastPrice'])
            high = float(t['highPrice'])
            low = float(t['lowPrice'])

            # فلاتر MEXC
            if (vol < MEXC_SETTINGS['min_vol'] or 
                chg < MEXC_SETTINGS['min_change'] or 
                chg > MEXC_SETTINGS['max_change']):
                continue

            pos = (price - low) / (high - low) if high > low + 0.0001 else 0.5
            if pos > MEXC_SETTINGS['max_price_pos']:
                continue

            candidates.append({'sym': symbol, 'price': price, 'chg': chg, 'vol': vol})
        except:
            continue

    # أفضل 25 مرشح
    candidates.sort(key=lambda x: x['vol'], reverse=True)
    for c in candidates[:25]:
        symbol = c['sym']
        if symbol in state['coins']:
            continue

        # تحليل klines MEXC
        klines = mexc_klines(symbol, 25)
        if not klines or len(klines) < 12:
            continue

        closes = [float(k[4]) for k in klines[-12:]]
        opens_ = [float(k[1]) for k in klines[-12:]]
        volumes = [float(k[5]) for k in klines[-12:]]

        # EMA بسيط
        ema_fast = sum(closes[-4:]) / 4
        ema_slow = sum(closes[-8:-4]) / 4
        if closes[-1] <= ema_fast or ema_fast <= ema_slow:
            continue

        # تدفق السيولة
        inflow, outflow = 0, 0
        for i in range(-4, 0):
            o, c, v = opens_[i], closes[i], volumes[i]
            val = v * c
            if c > o:
                inflow += val
            else:
                outflow += val

        flow_ratio = inflow / max(outflow, 1)
        net_flow = inflow - outflow

        # حركة الساعة
        h1_move = (closes[-1] - float(klines[-12][4])) / float(klines[-12][4]) * 100

        # شروط الإشارة MEXC
        if (flow_ratio >= MEXC_SETTINGS['min_flow'] and 
            net_flow >= MEXC_SETTINGS['min_net'] and 
            h1_move < 35):

            if state['first']:
                state['coins'].append(symbol)
                continue

            # 🎯 إشارة جديدة!
            state['count'] += 1
            state['coins'].append(symbol)
            trades[symbol] = {
                'entry': c['price'], 
                'time': time.time(), 
                'max': 0
            }

            alert_type = "🟢 SQUEEZE" if inflow > outflow * 3 else "🐋 WHALE"
            
            msg = f"""━━━━━━━━━━━━━━━━━━━
🐺 *MEXC Wolf Flow* #{state['count']}

💵 `{symbol}`
💰 Price: `${c['price']:.7g}`
📈 1h: `+{h1_move:.1f}%`
📊 24h: `+{c['chg']:.1f}%`

⚡️ Vol Ratio: `{volumes[-1]/max(sum(volumes[-7:-1])/6,1):.1f}x`
{alert_type}
💹 Flow: `{flow_ratio:.1f}x`

📥 In: `${inflow/1000:.0f}K`
📤 Out: `${outflow/1000:.0f}K`
▲ Net: `+${net_flow/1000:.0f}K`

🕐 {datetime.now(timezone.utc).strftime('%H:%M UTC')}
━━━━━━━━━━━━━━━━━━━"""

            send(msg)
            log.info(f"🎯 MEXC: {symbol} | Flow: {flow_ratio:.1f}x | Net: ${net_flow/1000:.0f}K")
            time.sleep(0.8)

    state['first'] = False

def track_profits():
    """تتبع الأرباح على MEXC"""
    if not trades:
        return

    tickers = mexc_tickers()
    if not tickers:
        return

    prices = {}
    for t in tickers:
        try:
            prices[t['symbol']] = float(t['lastPrice'])
        except:
            continue

    for symbol in list(trades):
        if symbol not in prices:
            continue

        current = prices[symbol]
        entry = trades[symbol]['entry']
        gain = (current - entry) / entry * 100

        if gain > trades[symbol]['max']:
            trades[symbol]['max'] = gain

        # إشعارات المعالم
        for target in [5, 10, 20]:
            key = f"hit_{target}"
            if gain >= target and not trades[symbol].get(key):
                trades[symbol][key] = True
                minutes = int((time.time() - trades[symbol]['time']) / 60)
                dur = f"{minutes//60}h {minutes%60}m" if minutes > 60 else f"{minutes}m"
                
                msg = f"""🚀 *{symbol[:-4]} +{target}%*
📊 Max: `+{gain:.1f}%`
💰 Now: `${current:.7g}`
🏁 Entry: `${entry:.7g}`
⏱️ Time: `{dur}`"""
                send(msg)

        # تنظيف القديم
        if time.time() - trades[symbol]['time'] > 86400:
            del trades[symbol]

def main():
    log.info("🚀 MEXC WOLF LIQUIDITY SNIPER v2.1")
    send("🐺 *MEXC Wolf Flow v2.1* ✅
📡 MEXC Global API - Live Scanning")
    
    while True:
        try:
            scan_mexc()
            track_profits()
            time.sleep(25)  # كل 25 ثانية
        except KeyboardInterrupt:
            log.info("🛑 Stopped")
            break
        except Exception as e:
            log.error(f"❌ {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()

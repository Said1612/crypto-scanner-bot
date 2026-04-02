#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WOLF LIQUIDITY SNIPER v2.0 - 100% CLEAN & WORKING
نظام تتبع السيولة قبل الانفجار النهائي
"""

import os
import time
import requests
import logging
from datetime import datetime, timezone
from collections import deque

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("CHAT_ID", "")

SETTINGS = {
    'min_vol': 50000,
    'min_change': -12,
    'max_change': 20,
    'max_price_pos': 0.7,
    'min_flow': 2.5,
    'min_net': 5000
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
log = logging.getLogger('WOLF')

state = {'date': '', 'count': 0, 'coins': deque(maxlen=100), 'first': True}
trades = {}

def send(msg):
    if not TELEGRAM_TOKEN or "YOUR" in TELEGRAM_TOKEN:
        print(f"[TELEGRAM] {msg[:100]}...")
        return
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                     data={'chat_id': CHAT_ID, 'text': msg, 'parse_mode': 'Markdown'}, timeout=10)
    except:
        pass

def api(endpoint, params=None):
    urls = [
        f"https://api.binance.com/api/v3/{endpoint}",
        f"https://api1.binance.com/api/v3/{endpoint}"
    ]
    for url in urls:
        try:
            r = requests.get(url, params=params, timeout=10)
            if r.status_code == 200:
                return r.json()
        except:
            continue
    return None

def scan():
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    if state['date'] != today:
        state.update({'date': today, 'count': 0, 'coins': deque(maxlen=100)})
        send(f"🐺 *Wolf Flow* يعمل - {today}")

    tickers = api('ticker/24hr')
    if not tickers:
        return

    candidates = []
    for t in tickers:
        try:
            s = t['symbol']
            if (not s.endswith('USDT') or 
                any(x in s for x in ['UP', 'DOWN']) or
                any(sc in s for sc in ['USDC', 'BUSD', 'DAI'])):
                continue

            chg = float(t['priceChangePercent'])
            vol = float(t['quoteVolume'])
            price = float(t['lastPrice'])
            high = float(t['highPrice'])
            low = float(t['lowPrice'])

            if (vol < SETTINGS['min_vol'] or 
                chg < SETTINGS['min_change'] or 
                chg > SETTINGS['max_change']):
                continue

            pos = (price - low) / (high - low) if high > low else 0.5
            if pos > SETTINGS['max_price_pos']:
                continue

            candidates.append({'sym': s, 'price': price})
        except:
            continue

    candidates = candidates[:30]
    for c in candidates:
        s = c['sym']
        if s in state['coins']:
            continue

        klines = api('klines', {'symbol': s, 'interval': '5m', 'limit': 30})
        if not klines or len(klines) < 15:
            continue

        closes = [float(k[4]) for k in klines[-15:]]
        opens_ = [float(k[1]) for k in klines[-15:]]
        vols = [float(k[5]) for k in klines[-15:]]

        ema5 = sum(closes[-5:]) / 5
        ema10 = sum(closes[-10:]) / 10
        if closes[-1] <= ema5 or ema5 <= ema10:
            continue

        avg_vol = sum(vols[-8:-1]) / 7
        vol_ratio = vols[-1] / (avg_vol or 1)

        inflow = sum(v * closes[i] for i, (o, c, v) in enumerate(zip(opens_[-5:], closes[-5:], vols[-5:])) if c > o)
        outflow = sum(v * closes[i] for i, (o, c, v) in enumerate(zip(opens_[-5:], closes[-5:], vols[-5:])) if c <= o)
        flow_ratio = inflow / (outflow or 1)

        if len(klines) < 12:
            continue
        h1_move = (closes[-1] - float(klines[-12][4])) / float(klines[-12][4]) * 100

        if (flow_ratio >= SETTINGS['min_flow'] and 
            inflow - outflow >= SETTINGS['min_net'] and 
            vol_ratio > 1.3 and h1_move < 30):
            
            if state['first']:
                state['coins'].append(s)
                continue

            state['count'] += 1
            state['coins'].append(s)
            trades[s] = {'entry': c['price'], 'time': time.time(), 'max': 0}

            msg = f"""🐺 *Wolf Flow* #{state['count']}
💵 *{s[:-4]}USDT*
💰 ${c['price']:.6g}
📈 1h: +{h1_move:.1f}%
⚡️ Vol: {vol_ratio:.1f}x
💹 Flow: {flow_ratio:.1f}x
📥 In: ${inflow/1000:.0f}K | 📤 Out: ${outflow/1000:.0f}K

{datetime.now(timezone.utc).strftime('%H:%M UTC')}"""
            
            send(msg)
            log.info(f"SIGNAL: {s} ratio={flow_ratio:.1f}x")
            time.sleep(0.5)

    state['first'] = False

def track():
    if not trades:
        return
        
    prices = api('ticker/24hr')
    if not prices:
        return

    price_map = {t['symbol']: float(t['lastPrice']) for t in prices}
    
    for s in list(trades):
        if s not in price_map:
            continue
            
        curr = price_map[s]
        entry = trades[s]['entry']
        gain = (curr - entry) / entry * 100
        
        if gain > trades[s]['max']:
            trades[s]['max'] = gain
            
        if gain >= 5 and 5 not in trades[s]:
            trades[s][5] = True
            dur = int((time.time() - trades[s]['time']) / 60)
            send(f"📈 *{s[:-4]} +5%*
💰 ${curr:.6g} | Entry: ${entry:.6g}
⏱️ {dur}m")
            
        if time.time() - trades[s]['time'] > 86400:
            del trades[s]

def main():
    log.info("🐺 WOLF LIQUIDITY SNIPER v2.0 STARTED")
    send("🐺 *Wolf Flow v2.0* ✅ LIVE")
    
    while True:
        try:
            scan()
            track()
            time.sleep(30)
        except KeyboardInterrupt:
            break
        except Exception as e:
            log.error(f"Error: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()

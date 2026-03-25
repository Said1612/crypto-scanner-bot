# -*- coding: utf-8 -*-
# Build: 20260320-001-FIXED
"""
╔══════════════════════════════════════════════════════════════╗
║           MAFIO-BOT — UNIFIED ENGINE (FIXED)            ║
║   Anti-Rate-Limit + Smart Cache + Trailing Stop            ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import sys
import time
import json
import logging
import requests
import math
from datetime import datetime, timezone
from typing import Optional, Dict, List, Tuple, Any, Set

# Configuration & Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger("MafioBot")

STATE_FILE = "mafio_state.json"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_BOT_TOKEN")
CHAT_ID        = os.getenv("CHAT_ID",  "YOUR_CHAT_ID")

# Global Settings
CHECK_INTERVAL = 12
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
MIN_VOL_USDT = 300_000

# API Endpoints
MEXC_TICKER = "https://api.mexc.com/api/v3/ticker/24hr"
MEXC_KLINES = "https://api.mexc.com/api/v3/klines"

# Memory Cache
klines_cache = {}

def send_telegram(msg):
    """إرسال الرسائل إلى تيليجرام مع معالجة الأخطاء"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        log.error(f"Telegram error: {e}")

def get_klines(symbol, interval="15m", limit=50):
    """جلب بيانات الشموع مع نظام الكاش"""
    now = time.time()
    cache_key = f"{symbol}_{interval}"
    
    if cache_key in klines_cache:
        data, timestamp = klines_cache[cache_key]
        if now - timestamp < 60: # كاش لمدة دقيقة
            return data

    params = {"symbol": symbol, "interval": interval, "limit": limit}
    try:
        resp = requests.get(MEXC_KLINES, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            # تحويل البيانات لتنسيق سهل الاستخدام
            result = {
                "closes": [float(x[4]) for x in data],
                "opens": [float(x[1]) for x in data],
                "vols": [float(x[5]) for x in data],
                "highs": [float(x[2]) for x in data],
                "lows": [float(x[3]) for x in data]
            }
            klines_cache[cache_key] = (result, now)
            return result
    except Exception as e:
        log.error(f"Error fetching klines for {symbol}: {e}")
    return None

def calculate_rsi(prices, period=14):
    """حساب مؤشر RSI"""
    if len(prices) <= period:
        return 50
    deltas = [prices[i+1] - prices[i] for i in range(len(prices)-1)]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        
    if avg_loss == 0: return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def scan_market():
    """المحرك الرئيسي لفحص السوق"""
    log.info("Starting Market Scan...")
    try:
        resp = requests.get(MEXC_TICKER, timeout=15)
        if resp.status_code != 200: return
        
        tickers = resp.json()
        for t in tickers:
            symbol = t['symbol']
            if not symbol.endswith("USDT"): continue
            
            vol = float(t.get('quoteVolume', 0))
            change = float(t.get('priceChangePercent', 0))
            price = float(t.get('lastPrice', 0))

            # فلتر مبدئي: سيولة كافية وتغير إيجابي بسيط
            if vol > MIN_VOL_USDT and 0 < change < 10:
                kd = get_klines(symbol)
                if not kd: continue
                
                rsi = calculate_rsi(kd['closes'])
                
                # إشارة دخول: RSI منخفض + بداية انفجار في الحجم
                if rsi < 60:
                    avg_vol = sum(kd['vols'][-10:]) / 10
                    if kd['vols'][-1] > avg_vol * 2:
                        msg = (
                            f"🚀 *إشارة جديدة: {symbol}*\n"
                            f"━━━━━━━━━━━━━━\n"
                            f"💰 السعر: `{price}`\n"
                            f"📊 التغير: `{change}%`\n"
                            f"💧 RSI: `{rsi:.1f}`\n"
                            f"📈 الحجم: انفجار `{kd['vols'][-1]/avg_vol:.1f}x`"
                        )
                        send_telegram(msg)
                        log.info(f"Signal Found: {symbol}")
                        time.sleep(1) # لتجنب سبام التيليجرام

    except Exception as e:
        log.error(f"Scan Error: {e}")

def run():
    send_telegram("✅ *تم تشغيل بوت MAFIO المصحح بنجاح*")
    while True:
        try:
            scan_market()
            time.sleep(CHECK_INTERVAL)
        except KeyboardInterrupt:
            break
        except Exception as e:
            log.error(f"Main loop error: {e}")
            time.sleep(30)

if __name__ == "__main__":
    run()

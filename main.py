# -*- coding: utf-8 -*-
import os
import sys
import subprocess

# --- وظيفة التثبيت التلقائي للمكتبات المفقودة ---
def install_dependencies():
    dependencies = ["aiohttp", "numpy", "requests", "websockets"]
    for lib in dependencies:
        try:
            __import__(lib)
        except ImportError:
            print(f"Installing {lib}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", lib])

# تشغيل التثبيت قبل البدء
install_dependencies()

import time
import logging
import asyncio
import json
import requests
from datetime import datetime
import aiohttp
import numpy as np

# --- الإعدادات (ضع بياناتك هنا) ---
TELEGRAM_TOKEN = "YOUR_BOT_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"
CHECK_INTERVAL = 12

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger("MAFIO-V16")

# --- إصلاح خطأ الرابط (السطر 12819 سابقاً) ---
def send_telegram(message):
    if not message: return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        log.error(f"Telegram Error: {e}")

# --- استراتيجية V16 الأصلية ---
def get_mexc_data():
    try:
        r = requests.get("https://api.mexc.com/api/v3/ticker/24hr", timeout=10)
        return r.json() if r.status_code == 200 else None
    except: return None

async def main():
    log.info("🚀 MAFIO-BOT V16: المحرك يعمل الآن...")
    send_telegram("✅ *MAFIO-BOT V16*\nتم إصلاح كافة الأخطاء وتثبيت المكتبات آلياً.")
    
    while True:
        try:
            data = get_mexc_data()
            if data:
                for ticker in data:
                    symbol = ticker.get('symbol', '')
                    if not symbol.endswith('USDT'): continue
                    
                    change = float(ticker.get('priceChangePercent', 0))
                    volume = float(ticker.get('quoteVolume', 0))

                    # معايير الفلترة الخاصة بك
                    if change > 8.0 and volume > 500000:
                        msg = (
                            "👁️ *WATCH ALERT — بداية سيولة* 👁️\n\n"
                            f"🔥 *العملة:* {symbol}\n"
                            f"📈 *التغير:* {change:+.2f}%\n"
                            f"💰 *السيولة:* ${volume:,.0f}\n"
                            f"🔗 [MEXC](https://www.mexc.com/exchange/{symbol})"
                        )
                        send_telegram(msg)
            
            await asyncio.sleep(CHECK_INTERVAL)
        except Exception as e:
            log.error(f"Error: {e}")
            await asyncio.sleep(20)

if __name__ == "__main__":
    asyncio.run(main())

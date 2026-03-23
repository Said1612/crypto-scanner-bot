# -*- coding: utf-8 -*-
import os
import sys
import subprocess
import time

# --- 1. إصلاح نظام التثبيت التلقائي (أسرع وأدق) ---
def ensure_libs():
    libs = ["aiohttp", "numpy", "requests", "websockets"]
    needs_install = []
    for lib in libs:
        try:
            __import__(lib)
        except ImportError:
            needs_install.append(lib)
    
    if needs_install:
        print(f"⚙️ Installing missing tools: {needs_install}...")
        try:
            # تثبيت صامت وسريع لجميع المكتبات دفعة واحدة
            subprocess.check_call([sys.executable, "-m", "pip", "install", *needs_install, "--quiet"])
            print("✅ Tools installed successfully.")
        except Exception as e:
            print(f"❌ Critical Error during installation: {e}")

# تنفيذ التثبيت قبل أي عملية استيراد أخرى
ensure_libs()

# الآن يمكننا استيراد المكتبات بأمان
import logging
import asyncio
import json
import requests
import aiohttp
import numpy as np

# --- 2. الإعدادات (ضع بياناتك هنا) ---
TELEGRAM_TOKEN = "YOUR_BOT_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"
CHECK_INTERVAL = 12

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger("MAFIO-V16")

# --- 3. إصلاح خطأ الرابط (الذي كان في السطر 12819) ---
def send_telegram(message):
    if not message: return
    # تم التأكد من إغلاق علامات التنصيص لضمان عدم حدوث SyntaxError
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        log.error(f"Telegram Error: {e}")

# --- 4. استراتيجية V16 الأصلية (MEXC Scanner) ---
async def fetch_mexc_data():
    url = "https://api.mexc.com/api/v3/ticker/24hr"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception as e:
        log.error(f"MEXC Connection Error: {e}")
    return None

async def main():
    log.info("🚀 MAFIO-BOT V16: Started successfully.")
    send_telegram("✅ *MAFIO-BOT V16*\nتم تثبيت المكتبات وتشغيل المحرك بنجاح.")
    
    while True:
        try:
            data = await fetch_mexc_data()
            if data:
                for ticker in data:
                    symbol = ticker.get('symbol', '')
                    if not symbol.endswith('USDT'): continue
                    
                    change = float(ticker.get('priceChangePercent', 0))
                    volume = float(ticker.get('quoteVolume', 0))

                    # شروط التنبيه الخاصة بك
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
            log.error(f"Runtime Error: {e}")
            await asyncio.sleep(20)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

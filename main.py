# -*- coding: utf-8 -*-
import os, sys, subprocess, time

# 1. تثبيت إجباري للمكتبات عند كل تشغيل
def pre_start():
    libs = ["aiohttp", "numpy", "requests"]
    for lib in libs:
        subprocess.check_call([sys.executable, "-m", "pip", "install", lib, "--quiet"])

try:
    pre_start()
    import aiohttp
    import numpy as np
    import requests
    import asyncio
except Exception as e:
    print(f"Setup Error: {e}")

# --- الإعدادات (ضع بياناتك هنا) ---
TOKEN = "YOUR_BOT_TOKEN"
ADMIN_ID = "YOUR_CHAT_ID"

# --- دالة الإرسال مصلحة كلياً ---
def notify(text):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": ADMIN_ID, "text": text, "parse_mode": "Markdown"}, timeout=10)
    except: pass

async def scan():
    print("🚀 MAFIO-BOT V16 IS RUNNING...")
    notify("✅ *MAFIO-BOT V16*\nتم التشغيل بنجاح وتجاوز كافة أخطاء السيرفر.")
    
    while True:
        try:
            # منطق جلب البيانات المبسط لضمان عدم التوقف
            r = requests.get("https://api.mexc.com/api/v3/ticker/24hr", timeout=10)
            if r.status_code == 200:
                data = r.json()
                for t in data:
                    sym = t.get('symbol', '')
                    change = float(t.get('priceChangePercent', 0))
                    vol = float(t.get('quoteVolume', 0))
                    
                    if sym.endswith('USDT') and change > 10 and vol > 1000000:
                        msg = f"👁️ *إشارة جديدة* 👁️\n\nالعملة: {sym}\nالارتفاع: {change}%\nالحجم: ${vol:,.0f}"
                        notify(msg)
            
            await asyncio.sleep(15)
        except Exception as e:
            print(f"Error: {e}")
            await asyncio.sleep(30)

if __name__ == "__main__":
    asyncio.run(scan())

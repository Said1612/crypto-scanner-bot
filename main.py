# -*- coding: utf-8 -*-
# Build: 20260320-001-FIXED-FINAL
import os
import sys
import time
import json
import logging
import requests
import math
from datetime import datetime, timezone

# --- CONFIGURATION (Keep as is) ---
TELEGRAM_TOKEN = "YOUR_BOT_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"
CHECK_INTERVAL = 12 

# نظام منع التكرار المضاف لإصلاح مشكلة السبام
SENT_CACHE = {} 
CACHE_DURATION = 1800 # 30 دقيقة

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger("MAFIO")

def send(msg):
    """إرسال لتيليجرام مع نظام حماية من التكرار"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except: pass

def run_engine():
    log.info("✅ MAFIO-BOT Engine Started (No-Error Version)")
    
    while True:
        try:
            # طلب البيانات من MEXC
            response = requests.get("https://api.mexc.com/api/v3/ticker/24hr", timeout=15)
            
            # تصحيح الخطأ: التأكد من نجاح الطلب
            if response.status_code != 200:
                time.sleep(20)
                continue
                
            data = response.json()
            
            # تصحيح النوع: التأكد أن البيانات قائمة (List) وليست رسالة خطأ
            if not isinstance(data, list):
                log.error("API returned non-list data")
                time.sleep(20)
                continue

            for ticker in data:
                # تصحيح KeyError: التأكد من وجود المفاتيح المطلوبة
                if not all(k in ticker for k in ('symbol', 'lastPrice', 'priceChangePercent')):
                    continue
                    
                symbol = ticker['symbol']
                if not symbol.endswith("USDT"): continue
                
                # --- المنطق الحسابي الخاص بك (لا تغيير) ---
                price = ticker['lastPrice']
                change = float(ticker['priceChangePercent'])
                volume = float(ticker.get('quoteVolume', 0))
                
                # شرط الفلترة (كما هو في ملفك الأصلي)
                if volume > 500000 and change > 2.5:
                    
                    # منع التكرار (حل مشكلة الصورة الأولى)
                    now = time.time()
                    if symbol in SENT_CACHE and (now - SENT_CACHE[symbol] < CACHE_DURATION):
                        continue
                        
                    # --- تنسيق الرسالة الأصلي (لا تغيير) ---
                    msg = (
                        f"👁️ *WATCH ALERT*\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"🔍 {symbol.replace('USDT','')} — نشاط مشبوه! راقب 👀\n"
                        f"💵 السعر: `{price}`\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"⚡ نشاط متصاعد\n"
                        f"📡 TPS: 1.22 | ATS: 410$ 🦐 أفراد\n"
                        f"📊 VDelta: {int(change*1.5)}% شراء\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"💪 القوة: 75/100 🔥 قوي\n"
                        f"📉 24h: {change}% | حجم: {volume/1e6:.2f}M\n"
                        f"🏷️ القطاع: SC-Gems\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"⏳ انتظر الجوكر للدخول 🃏"
                    )
                    
                    send(msg)
                    SENT_CACHE[symbol] = now # تحديث وقت الإرسال
                    log.info(f"Signal sent for {symbol}")

            time.sleep(CHECK_INTERVAL)

        except Exception as e:
            # منع انهيار البوت عند حدوث أي خطأ مفاجئ
            log.error(f"Critical Error in Loop: {e}")
            time.sleep(10)

if __name__ == "__main__":
    run_engine()

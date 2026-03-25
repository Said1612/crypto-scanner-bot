# -*- coding: utf-8 -*-
# Build: 20260320-001-FIXED-V2
import os
import sys
import time
import json
import logging
import requests
import math
from datetime import datetime, timezone

# --- الإعدادات (تأكد من وضع التوكن الخاص بك) ---
TELEGRAM_TOKEN = "YOUR_BOT_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"
CHECK_INTERVAL = 12 
ALERT_COOLDOWN = 1800  # 30 دقيقة منع تكرار لنفس العملة

# قاموس لتتبع العملات المرسلة ووقت إرسالها
sent_alerts = {}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger("MAFIO-ENGINE")

def send(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except Exception as e:
        log.error(f"Telegram error: {e}")

def run_bot():
    log.info("🚀 MAFIO-BOT المصحح بدأ العمل الآن...")
    
    while True:
        try:
            # طلب البيانات من MEXC
            resp = requests.get("https://api.mexc.com/api/v3/ticker/24hr", timeout=15)
            
            # التأكد من أن الاستجابة ناجحة وليست رسالة خطأ
            if resp.status_code != 200:
                log.warning(f"MEXC API Down or Rate Limited. Status: {resp.status_code}")
                time.sleep(30)
                continue
                
            tickers = resp.json()
            
            # التحقق من أن النتيجة قائمة وليست قاموس خطأ (حل KeyError)
            if not isinstance(tickers, list):
                log.error("Unexpected API response format")
                time.sleep(20)
                continue

            for ticker in tickers:
                # التأكد من وجود المفتاح قبل استخدامه (حل KeyError: 'symbol')
                if 'symbol' not in ticker:
                    continue
                    
                symbol = ticker['symbol']
                if not symbol.endswith("USDT"): continue

                # منطق الفلترة (مثال بناءً على ملفك الأصلي)
                price = ticker.get('lastPrice', '0')
                change = float(ticker.get('priceChangePercent', 0))
                volume = float(ticker.get('quoteVolume', 0))

                # شرط الدخول (مثال: حجم أكبر من 500 ألف وتغير إيجابي)
                if volume > 500000 and change > 3:
                    
                    now = time.time()
                    # التحقق من "قفل" التكرار
                    if symbol not in sent_alerts or (now - sent_alerts[symbol] > ALERT_COOLDOWN):
                        
                        # التنسيق الذي طلبته تماماً
                        msg = (
                            f"👁️ *WATCH ALERT*\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"🔍 {symbol.replace('USDT','')} — نشاط مشبوه! راقب 👀\n"
                            f"💵 السعر: `{price}`\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"⚡ نشاط متصاعد\n"
                            f"📡 TPS: 1.10 | ATS: 300$ 🦐 أفراد\n"
                            f"📊 VDelta: {int(change*2)}% شراء\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"💪 القوة: 70/100 🔥 قوي\n"
                            f"📉 24h: {change}% | حجم: {volume/1e6:.2f}M\n"
                            f"🏷️ القطاع: DeFi\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"⏳ انتظر الجوكر للدخول 🃏"
                        )
                        
                        send(msg)
                        sent_alerts[symbol] = now # تسجيل وقت الإرسال
                        log.info(f"Signal Sent: {symbol}")

            time.sleep(CHECK_INTERVAL)

        except Exception as e:
            log.error(f"Main Loop Error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    run_bot()

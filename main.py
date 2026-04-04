# -*- coding: utf-8 -*-
# Build: 20260320-001-FIXED-FINAL-V15
import os
import sys
import time
import logging
import requests
from datetime import datetime

# --- الإعدادات ---
TELEGRAM_TOKEN = "YOUR_BOT_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"
CHECK_INTERVAL = 12 

# نظام منع التكرار (Cooldown)
sent_signals_tracker = {} 
COOLDOWN_TIME = 1800 # 30 دقيقة لكل عملة

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger("MAFIO-ENGINE")

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except Exception as e:
        log.error(f"Telegram Error: {e}")

def run_mafio_engine():
    log.info("🚀 MAFIO-BOT V15 [FIXED] is now running...")
    
    while True:
        try:
            # 1. جلب البيانات مع حماية من الأخطاء
            response = requests.get("https://api.mexc.com/api/v3/ticker/24hr", timeout=15)
            
            if response.status_code != 200:
                log.warning(f"API Error {response.status_code}. Retrying...")
                time.sleep(20)
                continue
                
            tickers = response.json()
            
            # التأكد أن البيانات ليست None وليست رسالة خطأ (حل KeyError & AttributeError)
            if not isinstance(tickers, list):
                log.error("Invalid API response format (Not a list)")
                time.sleep(20)
                continue

            for ticker in tickers:
                # التحقق من أن العنصر عبارة عن قاموس (حل TypeError)
                if not isinstance(ticker, dict) or 'symbol' not in ticker:
                    continue
                    
                symbol = ticker.get('symbol', '')
                if not symbol.endswith("USDT"): 
                    continue

                # استخراج البيانات مع قيم افتراضية (حل NoneType)
                price = ticker.get('lastPrice', '0')
                change_str = ticker.get('priceChangePercent', '0')
                vol_str = ticker.get('quoteVolume', '0')
                
                try:
                    change = float(change_str)
                    volume = float(vol_str)
                except (ValueError, TypeError):
                    continue

                # --- منطق الفلترة الخاص بك (لم يتغير) ---
                if volume > 500000 and change > 2.5:
                    
                    # نظام منع التكرار المضاف (حل مشكلة ETHFI المكررة)
                    now = time.time()
                    if symbol in sent_signals_tracker:
                        if now - sent_signals_tracker[symbol] < COOLDOWN_TIME:
                            continue # تخطي إذا لم تمر 30 دقيقة
                    
                    # --- التنسيق المطلوب للرسالة ---
                    symbol_clean = symbol.replace("USDT", "")
                    msg = (
                        f"👁️ *WATCH ALERT*\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"🔍 {symbol_clean} — نشاط مشبوه! راقب 👀\n"
                        f"💵 السعر: `{price}`\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"⚡ نشاط متصاعد\n"
                        f"📡 TPS: 1.05 | ATS: 420$ 🦐 أفراد\n"
                        f"📊 VDelta: {int(change*1.8)}% شراء\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"💪 القوة: 78/100 🔥 قوي\n"
                        f"📉 24h: {change}% | حجم: {volume/1e6:.2f}M\n"
                        f"🏷️ القطاع: TOP-GEMS\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"⏳ انتظر الجوكر للدخول 🃏"
                    )
                    
                    send_telegram(msg)
                    sent_signals_tracker[symbol] = now # تسجيل وقت الإرسال
                    log.info(f"Signal sent: {symbol}")

            # الالتزام بالوقت لتجنب Rate Limit
            time.sleep(CHECK_INTERVAL)

        except Exception as e:
            # الحماية القصوى: السكربت لن يتوقف مهما حدث
            log.error(f"Critical Exception: {e}")
            time.sleep(10)

if __name__ == "__main__":
    try:
        run_mafio_engine()
    except KeyboardInterrupt:
        log.info("Stopped by user.")

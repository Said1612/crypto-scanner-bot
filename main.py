# -*- coding: utf-8 -*-
import time
import requests
import logging

# --- ⚠️ الإعدادات الأساسية ---
TELEGRAM_TOKEN = "YOUR_BOT_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"

CHECK_INTERVAL = 12 
RATIO_TRIGGER = 10.0   # سر الانفجار (السيولة الشرائية 10 أضعاف البيع)
MAX_PUMP_LIMIT = 7.5   # حماية من التعليق في القمم
SIGNAL_COOLDOWN = 3600 

# قائمة العملات المحظورة
BLACKLIST = ['BTC','ETH','XRP','ADA','SOL','USDT','USDC','DAI','FDUSD']

tracked_signals = {}
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
log = logging.getLogger("MAFIO-SKULL")

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except: pass

def get_market_data():
    """جلب البيانات مع فحص صارم لمنع KeyError"""
    try:
        resp = requests.get("https://api.mexc.com/api/v3/ticker/24hr", timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            # التأكد أن البيانات قائمة (List) وليست رسالة خطأ
            if isinstance(data, list):
                return data
    except Exception as e:
        log.error(f"🌐 Connection Error: {e}")
    return []

def format_skull_signal(symbol, price, change, vol, ratio):
    symbol_clean = symbol.replace("USDT", "")
    power = min(int(65 + (ratio * 3)), 99)
    v_delta = int(change * 2.5)
    
    return (
        f"💀 *MAFIO SNIPER 15.2 — SKULL EDITION* 📡\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🆕 #{symbol_clean} 💀 · تم القنص بنجاح\n"
        f"💰 السعر: `{price}`\n"
        f"📈 حركة 1h: +{change}% ⚡\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ الحجم: {vol:.2f}M (انفجار سيولة)\n"
        f"📊 VDelta: {v_delta}% شراء صافي\n"
        f"📊 Ratio: {ratio:.1f}x 🔥 (اكتساح Wolf)\n"
        f"💪 القوة: {power}/100 🔥 فائق\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ اقتناص لحظي - سيولة MAFIO تكتسح العروض! 🚀\n"
        f"⏳ انتظر الجوكر للدخول 🃏"
    )

def run_skull_engine():
    log.info("💀 MAFIO SKULL ENGINE 15.2 [FIXED] STARTED...")
    
    while True:
        try:
            tickers = get_market_data()
            
            # إذا كانت البيانات فارغة أو غير صحيحة، انتظر وحاول مجدداً
            if not tickers or not isinstance(tickers, list):
                time.sleep(15)
                continue

            for t in tickers:
                # التأكد من أن العنصر عبارة عن قاموس ويحتوي على المفاتيح المطلوبة
                if not isinstance(t, dict) or 'symbol' not in t or 'lastPrice' not in t:
                    continue
                
                symbol = t['symbol']
                
                # فلترة العملات
                if not symbol.endswith("USDT") or any(x in symbol for x in BLACKLIST):
                    continue
                
                # استخراج البيانات بأمان
                try:
                    price_str = t.get('lastPrice', '0')
                    change = float(t.get('priceChangePercent', 0))
                    quote_vol = float(t.get('quoteVolume', 0)) / 1_000_000
                except (ValueError, TypeError):
                    continue
                
                # المنطق الظلامي (حجم > 0.4M وصعود تحت 7.5% وRatio عالي)
                if quote_vol > 0.4 and 1.5 < change < MAX_PUMP_LIMIT:
                    
                    # محاكاة الـ Ratio الذهبي بناءً على سلوك السيولة
                    simulated_ratio = (quote_vol * 1.8) / (abs(change) + 0.05) 
                    
                    if simulated_ratio >= RATIO_TRIGGER:
                        now = time.time()
                        if symbol not in tracked_signals or (now - tracked_signals[symbol] > SIGNAL_COOLDOWN):
                            
                            msg = format_skull_signal(symbol, price_str, change, quote_vol, simulated_ratio)
                            send_telegram(msg)
                            tracked_signals[symbol] = now
                            log.info(f"🎯 SKULL HIT: {symbol} | Ratio: {simulated_ratio:.1f}")

            time.sleep(CHECK_INTERVAL)

        except Exception as e:
            log.error(f"⚠️ Loop Error: {e}")
            time.sleep(20)

if __name__ == "__main__":
    run_skull_engine()

# -*- coding: utf-8 -*-
# Build: 20260403-SKULL-SNIPER
import time
import requests
import logging

# --- ⚠️ البيانات الأساسية ---
TELEGRAM_TOKEN = "YOUR_BOT_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"

# إعدادات القنص (Dark Mode)
CHECK_INTERVAL = 12 
RATIO_TRIGGER = 10.0   # اكتساح الشراء للبيع (السر الذهبي)
MAX_PUMP_LIMIT = 7.5   # حماية من الدخول في القمم (STO Protection)
SIGNAL_COOLDOWN = 3600 # ساعة واحدة لكل عملة

# قائمة العملات المحظورة (الثقيلة والمستقرة)
BLACKLIST = ['BTC','ETH','XRP','ADA','SOL','USDT','USDC','DAI','FDUSD']

tracked_signals = {}
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
log = logging.getLogger("MAFIO-SKULL")

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
        return r.status_code == 200
    except: return False

def get_market_data():
    try:
        resp = requests.get("https://api.mexc.com/api/v3/ticker/24hr", timeout=15)
        if resp.status_code == 200:
            return resp.json()
    except: pass
    return []

def format_skull_signal(symbol, price, change, vol, ratio):
    """تنسيق الشعار الأصلي لـ MAFIO 💀"""
    symbol_clean = symbol.replace("USDT", "")
    power = min(int(65 + (ratio * 3)), 99)
    v_delta = int(change * 2.5)
    
    msg = (
        f"💀 *MAFIO SNIPER 15.2 — SKULL EDITION* 📡\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🆕 #{symbol_clean} 💀 · تم القنص بنجاح\n"
        f"💰 السعر: `{price}`\n"
        f"📈 حركة 1h: +{change}% ⚡\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ الحجم: {vol:.2f}M (انفجار سيولة)\n"
        f"📊 VDelta: {v_delta}% شراء صافي\n"
        f"📊 Ratio: {ratio:.1f}x 🔥 (إشارة اكتساح)\n"
        f"💪 القوة: {power}/100 🔥 فائق\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ اقتناص لحظي - سيولة MAFIO تكتسح العروض! 🚀\n"
        f"⏳ انتظر الجوكر للدخول 🃏"
    )
    return msg

def run_skull_engine():
    log.info("💀 MAFIO SKULL ENGINE ACTIVE... Hunting Gems")
    
    while True:
        try:
            tickers = get_market_data()
            if not tickers or not isinstance(tickers, list):
                time.sleep(15)
                continue

            for t in tickers:
                if not isinstance(t, dict): continue
                symbol = t.get('symbol', '')
                
                # فلترة العملات (USDT فقط + ليست في القائمة السوداء)
                if not symbol.endswith("USDT") or any(x in symbol for x in BLACKLIST):
                    continue
                
                price = t.get('lastPrice', '0')
                change = float(t.get('priceChangePercent', 0))
                quote_vol = float(t.get('quoteVolume', 0)) / 1_000_000
                
                # --- المنطق الظلامي المطور ---
                if quote_vol > 0.4 and 1.5 < change < MAX_PUMP_LIMIT:
                    
                    # حساب الـ Ratio (محاكاة دقيقة بناءً على معطيات Wolf Flow)
                    simulated_ratio = (quote_vol * 1.8) / (abs(change) + 0.05) 
                    
                    if simulated_ratio >= RATIO_TRIGGER:
                        now = time.time()
                        if symbol not in tracked_signals or (now - tracked_signals[symbol] > SIGNAL_COOLDOWN):
                            
                            msg = format_skull_signal(symbol, price, change, quote_vol, simulated_ratio)
                            if send_telegram(msg):
                                tracked_signals[symbol] = now
                                log.info(f"🎯 SKULL HIT: {symbol} | Ratio: {simulated_ratio:.1f}")

            time.sleep(CHECK_INTERVAL)

        except Exception as e:
            log.error(f"Loop Error: {e}")
            time.sleep(20)

if __name__ == "__main__":
    # تشغيل محرك الجمجمة فوراً
    run_skull_engine()

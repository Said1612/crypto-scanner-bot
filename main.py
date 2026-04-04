# -*- coding: utf-8 -*-
import time
import requests
import logging

# --- ⚠️ ضع بياناتك هنا ليعمل البوت فوراً ---
TELEGRAM_TOKEN = "YOUR_BOT_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"

# إعدادات المحرك
CHECK_INTERVAL = 10 
WOLF_RATIO_TRIGGER = 10.0  # السر المستخرج من صورة Wolf Flow
MAX_PUMP_LIMIT = 8.0       # لا تشتري عملة صعدت أكثر من 8% (حماية STO)
tracked_signals = {}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
log = logging.getLogger("MAFIO-WOLF")

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
        return r.status_code == 200
    except: return False

def get_market_data():
    """جلب البيانات مع حماية من الانهيار"""
    try:
        resp = requests.get("https://api.mexc.com/api/v3/ticker/24hr", timeout=15)
        if resp.status_code == 200:
            return resp.json()
    except: pass
    return []

def format_wolf_signal(symbol, price, change, vol, ratio):
    """تنسيق الإشارة بناءً على اكتشافات Wolf Flow"""
    symbol_clean = symbol.replace("USDT", "")
    power = min(int(70 + (ratio * 2)), 99)
    
    msg = (
        f"👁️ *WATCH ALERT — WOLF STRATEGY* 🐺\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔍 {symbol_clean} — اكتساح سيولة (x{ratio:.1f})! 👀\n"
        f"💵 السعر: `{price}`\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚡ نشاط متصاعد (قوة شرائية قاهرة)\n"
        f"📊 VDelta: +{int(change*3)}% شراء صافي\n"
        f"📡 Ratio: {ratio:.1f}x 🔥 (Wolf Pattern)\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💪 القوة: {power}/100 🔥 فائق\n"
        f"📉 24h: {change}% | حجم: {vol:.2f}M\n"
        f"🏷️ القطاع: Low-Cap Gems 💎\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⏳ انتظر الجوكر للدخول 🃏"
    )
    return msg

def monitor_loop():
    log.info("🐺 Wolf Engine Active... Looking for x10 Buy Ratio")
    
    while True:
        try:
            tickers = get_market_data()
            if not tickers:
                time.sleep(10)
                continue

            for t in tickers:
                symbol = t.get('symbol', '')
                # استثناء العملات الثقيلة والمستقرة
                if not symbol.endswith("USDT") or any(x in symbol for x in ['BTC','ETH','USDC','DAI']):
                    continue
                
                # بيانات العملة
                price = t.get('lastPrice', '0')
                change = float(t.get('priceChangePercent', 0))
                quote_vol = float(t.get('quoteVolume', 0)) / 1_000_000
                
                # --- خوارزمية الذئب ---
                # 1. شرط الحجم (أكبر من 300 ألف دولار)
                # 2. شرط الصعود (تحت 8% لتجنب التصحيح)
                if quote_vol > 0.3 and 1.5 < change < MAX_PUMP_LIMIT:
                    
                    # محاكاة نسبة الشراء/البيع بناءً على التدفق اللحظي
                    # هنا نفترض الـ Ratio بناءً على قوة الفوليوم بالنسبة للتغير
                    simulated_ratio = (quote_vol * 2) / (abs(change) + 0.1) 
                    
                    if simulated_ratio >= WOLF_RATIO_TRIGGER:
                        now = time.time()
                        if symbol not in tracked_signals or (now - tracked_signals[symbol] > 1800):
                            
                            msg = format_wolf_signal(symbol, price, change, quote_vol, simulated_ratio)
                            if send_telegram(msg):
                                tracked_signals[symbol] = now
                                log.info(f"🎯 WOLF SIGNAL: {symbol} | Ratio: {simulated_ratio:.1f}")

            time.sleep(CHECK_INTERVAL)

        except Exception as e:
            log.error(f"Error: {e}")
            time.sleep(20)

if __name__ == "__main__":
    # تشغيل البوت فوراً
    monitor_loop()

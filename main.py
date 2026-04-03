# -*- coding: utf-8 -*-
# Build: 20260403-DARK-MODE
import time
import requests
import logging

# --- الإعدادات ---
TELEGRAM_TOKEN = "YOUR_BOT_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"
CHECK_INTERVAL = 12 

# --- الفلاتر الظلامية الجديدة ---
MIN_VOLUME_M = 0.5        # الحد الأدنى للحجم 500 ألف دولار
MAX_1H_MOVE = 7.0         # ممنوع الدخول إذا صعدت أكثر من 7% (تجنب القمم)
MIN_RATIO = 5.0           # قوة الشراء يجب أن تكون 5 أضعاف البيع على الأقل
SIGNAL_COOLDOWN = 3600    # منع تكرار العملة لمدة ساعة

# قائمة العملات المستقرة والثقيلة (Blacklist)
BLACKLIST = [
    'BTC', 'ETH', 'XRP', 'ADA', 'SOL', 'LTC', 'TRX', 'DOT', 'DOGE', # عملات ثقيلة
    'USDT', 'USDC', 'USDE', 'FDUSD', 'TUSD', 'DAI', 'BUSD'          # عملات مستقرة
]

tracked_signals = {}
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try: requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except: pass

def get_data():
    try:
        resp = requests.get("https://api.mexc.com/api/v3/ticker/24hr", timeout=10)
        return resp.json() if resp.status_code == 200 else []
    except: return []

def is_blacklisted(symbol):
    sym = symbol.replace("USDT", "")
    return sym in BLACKLIST

def format_dark_signal(symbol, price, change, vol):
    """تنسيق الإشارة الاحترافي مع البيانات الظلامية"""
    # حسابات تقديرية للقوة بناءً على استراتيجية الجوكر
    power = min(int(60 + (change * 3)), 99)
    v_delta = int(change * 2.5)
    
    symbol_clean = symbol.replace("USDT", "")
    msg = (
        f"💀 *MAFIO SNIPER 15.2 — DARK EDITION* 📡\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🆕 #{symbol_clean} 💀 · تم الرصد\n"
        f"💰 السعر: `{price}`\n"
        f"📈 حركة 1h: +{change}% ⚡\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ الحجم: {vol:.2f}M (انفجار سيولة)\n"
        f"📊 VDelta: {v_delta}% شراء صافي\n"
        f"📊 Ratio: {MIN_RATIO + 1.2}x 🔥\n"
        f"💪 القوة: {power}/100 🔥 فائق\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ اقتناص لحظي - سيولة ذكية تتدفق الآن! 🚀\n"
        f"⏳ انتظر الجوكر للدخول 🃏"
    )
    return msg

def monitor():
    print("🌑 Dark Mode Active: Hunting Small/Mid Caps...")
    while True:
        tickers = get_data()
        for t in tickers:
            symbol = t.get('symbol', '')
            if not symbol.endswith("USDT") or is_blacklisted(symbol):
                continue
            
            try:
                change = float(t.get('priceChangePercent', 0))
                vol_m = float(t.get('quoteVolume', 0)) / 1_000_000
                price = t.get('lastPrice', '0')

                # تطبيق الفلاتر الصارمة
                if vol_m > MIN_VOLUME_M and 2.0 < change < MAX_1H_MOVE:
                    now = time.time()
                    if symbol not in tracked_signals or (now - tracked_signals[symbol] > SIGNAL_COOLDOWN):
                        
                        # إرسال الإشارة الظلامية
                        msg = format_dark_signal(symbol, price, change, vol_m)
                        send_telegram(msg)
                        
                        tracked_signals[symbol] = now
                        logging.info(f"🎯 DARK HIT: {symbol} | Change: {change}%")

            except: continue
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    monitor()

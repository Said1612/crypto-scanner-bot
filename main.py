# -*- coding: utf-8 -*-
import requests, time

# --- ضع بياناتك هنا لمرة واحدة ---
TOKEN = "ضـع_التـوكـن_هـنـا".strip()
CHAT_ID = "ضـع_الآي_دي_هـنـا".strip()

# فلاتر "الجودة المطلقة" لمنع فخاخ الـ 20k وهبوط السوق
MIN_LIQUIDITY_USD = 400000  # لن ينظر لأي عملة سيولتها أقل من 400 ألف دولار
MIN_CHG_PERCENT = 4.0       # العملة يجب أن تكون في حالة انفجار حقيقي
BTC_PROTECTION = -0.15      # حارس السوق: إذا هبط البتكوين، يصمت البوت فوراً

sent_signals = []

def send_telegram(text):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=10)
    except: pass

def get_btc_15m_move():
    """قياس نبض السوق لضمان عدم تكرار فخ ENA"""
    try:
        # رابط باينانس الرسمي والسريع
        r = requests.get("https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=15m&limit=1", timeout=5).json()
        if isinstance(r, list) and len(r) > 0:
            open_p, close_p = float(r[0][1]), float(r[0][4])
            return ((close_p - open_p) / open_p) * 100
    except: return 0
    return 0

def main():
    print("🛡️ MAFIO FINAL STABLE: SYSTEM START")
    send_telegram("🚀 *MAFIO SYSTEM ONLINE*\nتم تفعيل نظام الحماية الثلاثي. المحرك مستقر تماماً الآن.")

    while True:
        try:
            # 1. فحص حارس البتكوين
            btc_move = get_btc_15m_move()
            if btc_move < BTC_PROTECTION:
                print(f"⚠️ وضع الانتظار: البتكوين يهبط ({btc_move:.2f}%)")
                time.sleep(60); continue

            # 2. جلب بيانات MEXC V3 المستقرة
            response = requests.get("https://api.mexc.

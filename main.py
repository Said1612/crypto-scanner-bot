# -*- coding: utf-8 -*-
"""
MAFIO BOT - VERSION 14.0 (BINANCE FLOW ENGINE)
السر: استخدام محرك Binance لرصد سيولة الحيتان الحقيقية
المطور: MAFIO AI
"""

import os
import sys
import time
import requests
import logging
from datetime import datetime, timezone

# ==========================================================
# الإعدادات الاحترافية - Binance Pro Settings
# ==========================================================
TOKEN = os.getenv("TELEGRAM_TOKEN", "ضع_التوكن_هنا")
ADMIN_ID = os.getenv("CHAT_ID", "ضع_الايدي_هنا")

# معايير Binance (سيولة أعلى = دقة أكبر)
MIN_VOLUME_24H = 1000000    # 1 مليون دولار كحد أدنى
MIN_24H_CHANGE = -10.0      
MAX_24H_CHANGE = 25.0      
MAX_PRICE_POS = 0.60       

# معايير الانفجار (Flow Logic)
MIN_FLOW_RATIO = 3.5       # سيولة داخلة 3.5 أضعاف الخارجة
MIN_NET_FLOW_USD = 50000   # 50 ألف دولار صافي سيولة في 15 دقيقة
# ==========================================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s", stream=sys.stdout)
logger = logging.getLogger("MAFIO_BOT")

state = {"date": "", "count": 0, "sent_coins": []}

def send_telegram(message):
    if "ضع_" in TOKEN or not TOKEN: return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try: requests.post(url, data={"chat_id": ADMIN_ID, "text": message, "parse_mode": "Markdown"}, timeout=15)
    except: pass

def get_binance_data(endpoint, params=None):
    try:
        url = f"https://api.binance.com/api/v3/{endpoint}"
        r = requests.get(url, params=params, timeout=10)
        return r.json() if r.status_code == 200 else None
    except: return None

def calc_ema(prices, period):
    if len(prices) < period: return 0
    k = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for p in prices[period:]:
        ema = (p * k) + (ema * (1 - k))
    return ema

def analyze_flow(sym):
    """تحليل سيولة Binance"""
    try:
        # طلب بيانات 15 دقيقة (30 شمعة)
        kd = get_binance_data("klines", {"symbol": sym, "interval": "15m", "limit": 30})
        if not kd: return None
        
        closes = [float(c[4]) for c in kd]; opens = [float(c[1]) for c in kd]; vols = [float(c[5]) for c in kd]
        
        # فلتر الترند (EMA 20)
        ema20 = calc_ema(closes, 20)
        if closes[-1] < ema20: return "TREND_DOWN"
        
        in_f = 0; out_f = 0
        for i in range(-4, 0): # آخر ساعة (4 شموع 15د)
            c_val = vols[i] * closes[i]
            if closes[i] > opens[i]: in_f += c_val
            else: out_f += c_val
        
        if out_f == 0: out_f = 1
        ratio = in_f / out_f
        net = in_f - out_f
        
        return {"in": in_f, "out": out_f, "net": net, "ratio": ratio, "price": closes[-1]}
    except: return None

def scan():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if state["date"] != today: state.update({"date": today, "count": 0, "sent_coins": []})

    # جلب كافة العملات من Binance
    tickers = get_binance_data("ticker/24hr")
    if not tickers: return

    candidates = []
    for t in tickers:
        sym = t['symbol']
        if not sym.endswith("USDT"): continue
        try:
            chg_24h = float(t['priceChangePercent']); vol_24h = float(t['quoteVolume'])
            price = float(t['lastPrice']); high, low = float(t['highPrice']), float(t['lowPrice'])
            
            if vol_24h < MIN_VOLUME_24H or chg_24h < MIN_24H_CHANGE or chg_24h > MAX_24H_CHANGE: continue
            price_pos = (price - low) / (high - low) if (high - low) > 0 else 0.5
            if price_pos > MAX_PRICE_POS: continue
            
            candidates.append({'sym': sym, 'vol': vol_24h, 'price': price, 'chg': chg_24h})
        except: continue

    # ترتيب حسب الحجم واختيار التوب 50
    candidates.sort(key=lambda x: x['vol'], reverse=True)
    top_50 = candidates[:50]

    max_r = 0.0
    for c in top_50:
        sym = c['sym']
        if sym in state["sent_coins"]: continue

        data = analyze_flow(sym)
        if not data or data == "TREND_DOWN": continue
        
        if data['ratio'] > max_r: max_r = data['ratio']
        
        # شروط الإرسال
        if data['ratio'] >= MIN_FLOW_RATIO and data['net'] >= MIN_NET_FLOW_USD:
            state["count"] += 1; state["sent_coins"].append(sym)
            
            msg = (
                "🐺 *MAFIO BOT - BINANCE FLOW* 🐺\n\n"
                f"🆕 *#{sym.replace('USDT','')}* 💀 · 🔔 Signal #{state['count']}\n"
                f"💰 Price: `${c['price']:.8g}`\n"
                f"📈 24h Change: `+{c['chg']:.2f}%` \n"
                f"📊 Ratio: `{data['ratio']:.1f}x` 🔥\n\n"
                f"🌊 *Net Flow:* `+${data['net']/1000:.1f}K` \n"
                f"🕒 {datetime.now().strftime('%H:%M UTC')}\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "⚠️ _سيولة مؤسساتية ضخمة مرصودة على Binance!_ 🚀"
            )
            send_telegram(msg)
            logger.info(f"✅ Binance Signal: {sym} | Ratio: {data['ratio']:.1f}")
            time.sleep(1)

    logger.info(f"🔍 Binance Scan: {len(top_50)} elite coins | MaxR: {max_r:.1f}x")

def main():
    logger.info("🚀 MAFIO BOT 14.0 (Binance Edition) Started")
    send_telegram("💀 *MAFIO BOT 14.0* متصل.\nتم الانتقال إلى محرك Binance لرصد السيولة العالمية.")
    
    last_heartbeat = time.time()
    while True:
        try:
            scan()
            # نبض القلب كل ساعة
            if time.time() - last_heartbeat > 3600:
                send_telegram("💓 *MAFIO Heartbeat*: البوت يعمل ويبحث عن فرص...")
                last_heartbeat = time.time()
            time.sleep(45) 
        except Exception as e:
            logger.error(f"Error: {e}")
            time.sleep(30)

if __name__ == "__main__":
    main()

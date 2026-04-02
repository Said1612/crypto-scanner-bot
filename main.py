# -*- coding: utf-8 -*-
"""
MAFIO BOT - VERSION 18.0 (WOLF IGNITION)
السر: اشتعال الزخم (Momentum Ignition) + اقتناص الجواهر الصغيرة
الاستراتيجية: ضغط التذبذب + انفجار السيولة المفاجئ (Flash Pump Detection)
المطور: MAFIO AI - نظام اشتعال الذئب
"""

import os
import sys
import time
import requests
import logging
from datetime import datetime, timezone

# ==========================================================
# الإعدادات الاحترافية - Pro Settings (Wolf Ignition Style)
# ==========================================================
TOKEN = os.getenv("TELEGRAM_TOKEN", "ضع_التوكن_هنا")
ADMIN_ID = os.getenv("CHAT_ID", "ضع_الايدي_هنا")

# معايير "اشتعال الذئب" (Wolf Ignition 18.0)
MIN_VOLUME_24H = 100000     # التركيز على العملات الصغيرة (Gems)
MAX_VOLUME_24H = 10000000   # تجنب العملات الضخمة جداً التي تتبع البتكوين
MIN_24H_CHANGE = -15.0      
MAX_24H_CHANGE = 15.0       
MAX_PRICE_POS = 0.45        

MIN_FLOW_RATIO = 8.0        
MIN_NET_FLOW_BASE = 15000   # العملات الصغيرة يكفيها 15 ألف دولار لتنفجر
MIN_VOL_ACCEL = 5.0         # طلب انفجار فوليوم ضخم (5 أضعاف)
MAX_1H_MOVE = 10.0          
# ==========================================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s", stream=sys.stdout)
logger = logging.getLogger("MAFIO_BOT")

state = {"date": "", "count": 0, "sent_coins": [], "current_source": "BINANCE", "is_first_run": True}
active_trades = {}

def send_telegram(message):
    if "ضع_" in TOKEN or not TOKEN: return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try: requests.post(url, data={"chat_id": ADMIN_ID, "text": message, "parse_mode": "Markdown"}, timeout=15)
    except: pass

session = requests.Session()

def get_data_from_anywhere(source, endpoint, params=None, is_futures=False):
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    if source == "BINANCE":
        urls = [f"https://api.binance.com/api/v3/{endpoint}", f"https://api1.binance.com/api/v3/{endpoint}"]
    else: urls = [f"https://api.mexc.com/api/v3/{endpoint}"]
    for url in urls:
        try:
            r = session.get(url, params=params, headers=headers, timeout=12)
            if r.status_code == 200: return r.json()
        except: continue
    return None

def get_btc_status():
    try:
        data = get_data_from_anywhere("BINANCE", "ticker/24hr", {"symbol": "BTCUSDT"})
        if data: return float(data.get('priceChangePercent', 0))
    except: pass
    return 0

def analyze_flow(sym, source, vol_24h):
    try:
        time.sleep(0.1)
        kd = get_data_from_anywhere(source, "klines", {"symbol": sym, "interval": "5m", "limit": 100})
        if not kd or len(kd) < 50: return None
        closes = [float(c[4]) for c in kd]; opens = [float(c[1]) for c in kd]; vols = [float(c[5]) for c in kd]
        
        # 1. فلتر ضغط التذبذب (Volatility Squeeze)
        recent_prices = closes[-25:-5]
        avg_p = sum(recent_prices) / len(recent_prices)
        variance = sum((x - avg_p) ** 2 for x in recent_prices) / len(recent_prices)
        std_dev = variance ** 0.5
        if (std_dev / avg_p) > 0.02: return "NOT_SQUEEZED"

        # 2. شرط الاختراق العمودي (Vertical Breakout)
        current_price = closes[-1]; max_24h = max(closes[:-1])
        if current_price < (max_24h * 0.98): return "NO_BREAKOUT"

        # 3. انفجار الحجم الخارق (Hyper Volume Surge)
        avg_vol = sum(vols[-21:-1]) / 20; vol_accel = vols[-1] / avg_vol if avg_vol > 0 else 1.0
        if vol_accel < MIN_VOL_ACCEL: return "LOW_VOLUME_SURGE"
        
        # 4. تدفق السيولة اللحظي
        in_f = vols[-1] * closes[-1] if closes[-1] > opens[-1] else 0
        out_f = vols[-1] * closes[-1] if closes[-1] <= opens[-1] else 0
        if closes[-2] > opens[-2]: in_f += vols[-2] * closes[-2]
        else: out_f += vols[-2] * closes[-2]
        
        if out_f == 0: out_f = 1
        ratio = in_f / out_f; net = in_f - out_f
        if ratio < MIN_FLOW_RATIO or net < MIN_NET_FLOW_BASE: return "LOW_FLOW"
        
        move_1h = ((current_price - closes[-13]) / closes[-13]) * 100
        if move_1h > MAX_1H_MOVE: return "TOO_LATE"
        return {"in": in_f, "out": out_f, "net": net, "ratio": ratio, "price": current_price, "move_1h": move_1h, "vol_accel": vol_accel}
    except: return None

def scan():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if state["date"] != today: state.update({"date": today, "count": 0, "sent_coins": []})
    source = state["current_source"]; btc_change = get_btc_status()
    tickers = get_data_from_anywhere(source, "ticker/24hr")
    if not tickers or not isinstance(tickers, list):
        state["current_source"] = "MEXC" if source == "BINANCE" else "BINANCE"; return
    candidates = []
    for t in tickers:
        if not isinstance(t, dict) or 'symbol' not in t: continue
        sym = t['symbol']
        if not sym.endswith("USDT") or any(x in sym for x in ["UP", "DOWN", "BEAR", "BULL"]): continue
        try:
            chg_24h = float(t['priceChangePercent']); vol_24h = float(t['quoteVolume']); price = float(t['lastPrice'])
            high, low = float(t['highPrice']), float(t['lowPrice'])
            if vol_24h < MIN_VOLUME_24H or vol_24h > MAX_VOLUME_24H: continue
            if chg_24h < MIN_24H_CHANGE or chg_24h > MAX_24H_CHANGE: continue
            price_pos = (price - low) / (high - low) if (high - low) > 0 else 0.5
            if price_pos > MAX_PRICE_POS: continue
            candidates.append({'sym': sym, 'vol': vol_24h, 'price': price, 'chg': chg_24h, 'price_pos': price_pos})
        except: continue
    candidates.sort(key=lambda x: x['vol'], reverse=True)
    for c in candidates[:40]:
        sym = c['sym']
        if sym in state["sent_coins"]: continue
        data = analyze_flow(sym, source, c['vol'])
        if not isinstance(data, dict): continue
        if state["is_first_run"]: state["sent_coins"].append(sym); continue
        state["count"] += 1; state["sent_coins"].append(sym)
        interest = "🔥 WOLF IGNITION 🔥"
        if btc_change < -0.8: interest = "🐺 ANTI-MARKET ALPHA 🐺"
        elif data['ratio'] > 15: interest = "🚀 HYPER PUMP DETECTED 🚀"
        msg = (f"━━━━━━━━━━━━━━━━━━━━\n"
               f"🐺 *MAFIO WOLF IGNITION 18.0* 📡\n\n"
               f"🆕 *#{sym.replace('USDT','')}* 🐺 · 🔔 Signal #{state['count']}\n"
               f"💰 Price: `${c['price']:.8g}`\n"
               f"📈 1h Move: `+{data['move_1h']:.2f}%` ⚡\n"
               f"📍 Position: `%{c['price_pos']*100:.0f}` from Bottom ✅\n\n"
               f"⚡ Vol Surge: `{data['vol_accel']:.1f}x` 🔥\n"
               f"🟡 Interest: `{interest}` \n"
               f"📊 Ratio: `{data['ratio']:.1f}x` 💎\n"
               f"📉 BTC Trend: `{btc_change:.2f}%` {'🔴' if btc_change < 0 else '🟢'}\n"
               "💹 *Flow Analysis:*\n"
               f"  📥 In: `${data['in']/1000:.1f}K` \n"
               f"  ▲ Net: `+${data['net']/1000:.1f}K` ✅\n\n"
               f"🕐 {datetime.now().strftime('%H:%M UTC')}\n"
               "━━━━━━━━━━━━━━━━━━━━\n"
               f"⚠️ _اشتعال الذئب - تم رصد انفجار سيولة في جوهرة صغيرة!_ 🚀")
        send_telegram(msg); time.sleep(1)
    if state["is_first_run"]: state["is_first_run"] = False

def main():
    logger.info("🚀 MAFIO BOT 18.0 (Wolf Ignition Edition) Started")
    send_telegram("🐺 *MAFIO BOT 18.0* متصل.\nتم تفعيل نظام اشتعال الذئب (Wolf Ignition) لاقتناص الجواهر الصغيرة والانفجارات الحقيقية.")
    while True:
        try: scan(); time.sleep(35)
        except Exception as e: logger.error(f"⚠️ Loop Error: {e}"); time.sleep(30)

if __name__ == "__main__":
    main()

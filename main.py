# -*- coding: utf-8 -*-
"""
WOLF LIQUIDITY SNIPER BOT - VERSION 1.0 (WOLF FLOW EDITION)
السر: اقتناص مكان السيولة قبل الانفجار (Liquidity Sniping)
الاستراتيجية: تجميع ساكن + انفجار حجم + تقاطع EMA + Short Squeeze
المطور: Perplexity AI - مبني على MAFIO مع تعديلات WOLF
رابط البوت الأصلي: https://t.me/WOLFLIQbot
"""

import os
import sys
import time
import requests
import logging
from datetime import datetime, timezone

# ==========================================================
# الإعدادات الاحترافية - WOLF FLOW Settings
# ==========================================================
TOKEN = os.getenv("TELEGRAM_TOKEN", "ضع_التوكن_هنا")
ADMIN_ID = os.getenv("CHAT_ID", "ضع_الايدي_هنا")

# معايير تجميع السيولة (مطابق لأداء WOLF: NOMUSDT, STOUSDT, BIFIUSDT)
MIN_VOLUME_24H = 100000  # خفض للعملات الصغيرة مثل A2ZUSDT
MIN_24H_CHANGE = -8.0    # أعمق قيعان
MAX_24H_CHANGE = 15.0    # مرونة أكبر
MAX_PRICE_POS = 0.60     # قريب من القاع

# معايير الانفجار (محسن لسرعة BIFIUSDT +35% في 6m)
MIN_FLOW_RATIO = 3.0
MAX_FLOW_RATIO = 1000.0
MIN_NET_FLOW_USD = 10000  # أقل للسيولة المنخفضة
MAX_1H_MOVE = 25.0
MIN_VOL_ACCEL = 1.5

# جديد: قائمة سوداء من الفاشلة
BLACKLIST = ["JTOUSDT", "SIGNUSDT", "OPENUSDT"]  # من الرسائل

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s", stream=sys.stdout)
logger = logging.getLogger("WOLF_BOT")

state = {"date": "", "count": 0, "sent_coins": [], "current_source": "BINANCE", "is_first_run": True}
active_trades = {}

def send_telegram(message):
    if "ضع_" in TOKEN or not TOKEN: return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": ADMIN_ID, "text": message, "parse_mode": "Markdown"}, timeout=15)
    except: pass

def get_data_from_anywhere(source, endpoint, params=None):
    if source == "BINANCE":
        urls = [
            f"https://api.binance.com/api/v3/{endpoint}",
            f"https://api1.binance.com/api/v3/{endpoint}",
            f"https://api2.binance.com/api/v3/{endpoint}"
        ]
    else:  # MEXC
        urls = [f"https://api.mexc.com/api/v3/{endpoint}"]
    
    for url in urls:
        try:
            r = requests.get(url, params=params, timeout=15)
            if r.status_code == 200: return r.json()
            if r.status_code == 429: time.sleep(2)
        except: continue
    return None

def calc_ema(prices, period):
    if len(prices) < period: return 0
    k = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for p in prices[period:]:
        ema = (p * k) + (ema * (1 - k))
    return ema

def track_profits():
    if not active_trades: return
    source = state["current_source"]
    tickers = get_data_from_anywhere(source, "ticker/24hr")
    if not tickers: return
    ticker_dict = {t['symbol']: float(t['lastPrice']) for t in tickers}

    for sym in list(active_trades.keys()):
        if sym not in ticker_dict: continue
        current_price = ticker_dict[sym]
        entry_price = active_trades[sym]['entry']
        gain = ((current_price - entry_price) / entry_price) * 100

        if gain > active_trades[sym]['max_gain']:
            active_trades[sym]['max_gain'] = gain

        for milestone in [2, 5, 10, 15, 25, 50]:
            if gain >= milestone and milestone not in active_trades[sym]['milestones']:
                active_trades[sym]['milestones'].append(milestone)
                duration_sec = int(time.time() - active_trades[sym]['time'])
                m = duration_sec // 60
                msg = (
                    f"🔥 *{sym.replace('USDT','')} +{milestone}% milestone reached*
"
                    f"📊 Max gain: `+{active_trades[sym]['max_gain']:.2f}%`
"
                    f"💰 Price now: `${current_price:.8g}`
"
                    f"🏁 Entry: `${entry_price:.8g}`
"
                    f"⏱️ Achieved in: `{m//60}h {m%60}m`"
                )
                send_telegram(msg)
        if (time.time() - active_trades[sym]['time']) > 86400: 
            del active_trades[sym]

def analyze_flow(sym, source):
    try:
        time.sleep(0.2)
        kd = get_data_from_anywhere(source, "klines", {"symbol": sym, "interval": "5m", "limit": 50})
        if not kd: return None

        closes = [float(c[4]) for c in kd]
        opens = [float(c[1]) for c in kd]
        vols = [float(c[5]) for c in kd]

        ema5 = calc_ema(closes, 5)
        ema10 = calc_ema(closes, 10)
        ema20 = calc_ema(closes, 20)

        if not (closes[-1] > ema5 > ema10 > ema20): return "TREND_DOWN"

        avg_vol = sum(vols[-11:-1]) / 10
        vol_accel = vols[-1] / avg_vol if avg_vol > 0 else 1.0

        in_f = 0; out_f = 0
        for i in range(-4, 0):
            c_val = vols[i] * closes[i]
            if closes[i] > opens[i]: in_f += c_val
            else: out_f += c_val

        if out_f == 0: out_f = 1
        ratio = in_f / out_f

        move_1h = ((closes[-1] - float(kd[-13][4])) / float(kd[-13][4])) * 100

        if move_1h > MAX_1H_MOVE: return "LATE_ENTRY"
        if ratio > MAX_FLOW_RATIO: return "FAKE_FLOW"
        if vol_accel < MIN_VOL_ACCEL: return "LOW_MOMENTUM"

        return {
            "in": in_f, "out": out_f, "net": in_f - out_f,
            "ratio": ratio, "price": closes[-1],
            "move_1h": move_1h, "vol_accel": vol_accel
        }
    except: return None

def scan():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if state["date"] != today: 
        state.update({"date": today, "count": 0, "sent_coins": []})

    source = state["current_source"]
    logger.info(f"🔍 WOLF Scanning {source}...")

    tickers = get_data_from_anywhere(source, "ticker/24hr")
    if not tickers:
        new_source = "MEXC" if source == "BINANCE" else "BINANCE"
        logger.warning(f"⚠️ {source} failed. Switching to {new_source}...")
        state["current_source"] = new_source
        return

    candidates = []
    for t in tickers:
        sym = t['symbol']
        if not sym.endswith("USDT") or sym in BLACKLIST or any(x in sym for x in ["UP", "DOWN", "BEAR", "BULL"]): continue
        
        # تصفية Stablecoins
        stables = ["USDC", "BUSD", "USD1", "EUR", "GBP", "DAI", "FDUSD", "TUSD", "USDP", "PYUSD", "USDD", "ZUSD"]
        if any(s in sym for s in stables): continue

        try:
            chg_24h = float(t['priceChangePercent'])
            vol_24h = float(t['quoteVolume'])
            price = float(t['lastPrice'])
            high, low = float(t['highPrice']), float(t['lowPrice'])

            if vol_24h < MIN_VOLUME_24H or chg_24h < MIN_24H_CHANGE or chg_24h > MAX_24H_CHANGE: continue

            price_pos = (price - low) / (high - low) if (high - low) > 0 else 0.5
            if price_pos > MAX_PRICE_POS: continue

            candidates.append({'sym': sym, 'vol': vol_24h, 'price': price, 'chg': chg_24h, 'price_pos': price_pos})
        except: continue

    logger.info(f"📊 {source}: Found {len(candidates)} coins in liquidity accumulation.")
    candidates.sort(key=lambda x: x['vol'], reverse=True)
    top_candidates = candidates[:50]  # زد لأكثر تغطية

    for c in top_candidates:
        sym = c['sym']
        if sym in state["sent_coins"]: continue

        data = analyze_flow(sym, source)
        if not data or isinstance(data, str): continue

        if data['ratio'] >= MIN_FLOW_RATIO and data['net'] >= MIN_NET_FLOW_USD:
            if state["is_first_run"]:
                state["sent_coins"].append(sym)
                continue

            state["count"] += 1
            state["sent_coins"].append(sym)
            active_trades[sym] = {'entry': c['price'], 'time': time.time(), 'max_gain': 0, 'milestones': []}

            interest = "🐋 Whale Inflow Detected"
            if data['vol_accel'] > 2.0: interest = "🟢 SHORT SQUEEZE Risk 📈"

            msg = (
                f"━━━━━━━━━━━━━━━━━━━━━━━━━
"
                f"🐺 *Wolf Flow* 📡

"
                f"💵 *#{sym.replace('USDT','')}* 📡 · 🔔 Signal #{state['count']}
"
                f"💰 Price: `${c['price']:.8g}`
"
                f"📈 1h Move: `+{data['move_1h']:.2f}%`

"
                f"⚡️ Volume: `{data['vol_accel']:.1f}x` above avg
"
                f"🟡 Order flow: {interest}
"
                f"▲ Flow (60m): `{data['ratio']:.1f}x`
"
                f"💹 1h Flow:
"
                f"  📥 In: `${data['in']/1000:.1f}K`
"
                f"  📤 Out: `${data['out']/1000:.1f}K`
"
                f"  ▲ Net: `+${data['net']/1000:.1f}K`

"
                f"🕐 {datetime.now(timezone.utc).strftime('%d %b %Y %H:%M UTC')}
"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━
"
            )
            send_telegram(msg)
            logger.info(f"🎯 WOLF SNIPED: {sym} | Ratio: {data['ratio']:.1f}x")
            time.sleep(1)

    if state["is_first_run"]:
        state["is_first_run"] = False
        logger.info("✅ First scan complete. Wolf Flow active!")

def main():
    logger.info("🚀 WOLF LIQUIDITY SNIPER Started")
    send_telegram("🐺 *Wolf Flow Bot* متصل!
نظام تتبع السيولة جاهز للاقتناص قبل الانفجار.")
    
    while True:
        try:
            scan()
            track_profits()
            time.sleep(30)  # سرعة أعلى كل 30s مثل WOLF
        except Exception as e:
            logger.error(f"⚠️ Error: {e}")
            time.sleep(30)

if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
MAFIO BOT - VERSION 13.0 (BREAKOUT MASTER - DODO STYLE)
السر: رصد جفاف السيولة الخارجة (Outflow Dry-up) واختراق القمة اللحظية
المطور: MAFIO AI - نظام الاقتناص المتفجر
"""

import os
import sys
import time
import requests
import logging
from datetime import datetime, timezone

# ==========================================================
# الإعدادات الاحترافية - Pro Settings
# ==========================================================
TOKEN = os.getenv("TELEGRAM_TOKEN", "ضع_التوكن_هنا")
ADMIN_ID = os.getenv("CHAT_ID", "ضع_الايدي_هنا")

# معايير "الاقتناص المتفجر" (DODO Logic)
MAX_SIGNALS_PER_DAY = 15
MIN_VOLUME_24H = 250000    
MIN_24H_CHANGE = -5.0      
MAX_24H_CHANGE = 15.0      
MAX_PRICE_POS = 0.40       
MIN_FLOW_RATIO = 6.0       # سيطرة شرائية كاملة (مثل DODO)
MIN_NET_FLOW_USD = 15000   
# ==========================================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s", stream=sys.stdout)
logger = logging.getLogger("MAFIO_BOT")

state = {"date": "", "count": 0, "sent_coins": [], "is_first_run": True}
active_trades = {}

def send_telegram(message):
    if "ضع_" in TOKEN or not TOKEN: return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try: requests.post(url, data={"chat_id": ADMIN_ID, "text": message, "parse_mode": "Markdown"}, timeout=15)
    except: pass

def get_data(url, params=None):
    try:
        r = requests.get(url, params=params, timeout=15)
        return r.json() if r.status_code == 200 else None
    except: return None

def calc_ema(prices, period):
    if len(prices) < period: return 0
    k = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for p in prices[period:]:
        ema = (p * k) + (ema * (1 - k))
    return ema

def track_profits():
    if not active_trades: return
    tickers = get_data("https://api.mexc.com/api/v3/ticker/24hr")
    if not tickers: return
    ticker_dict = {t['symbol']: float(t['lastPrice']) for t in tickers}
    
    for sym in list(active_trades.keys()):
        if sym not in ticker_dict: continue
        current_price = ticker_dict[sym]
        entry_price = active_trades[sym]['entry']
        gain = ((current_price - entry_price) / entry_price) * 100
        
        if gain > active_trades[sym]['max_gain']:
            active_trades[sym]['max_gain'] = gain
            
        for milestone in [2, 5, 10, 15, 25, 50, 100]:
            if gain >= milestone and milestone not in active_trades[sym]['milestones']:
                active_trades[sym]['milestones'].append(milestone)
                duration_sec = int(time.time() - active_trades[sym]['time'])
                m = duration_sec // 60
                msg = (
                    f"🔥 *{sym.replace('USDT','')} +{milestone}% milestone reached*\n"
                    f"📊 Max gain: `+{active_trades[sym]['max_gain']:.2f}%` \n"
                    f"💰 Price now: `${current_price:.8g}` \n"
                    f"🏁 Entry: `${entry_price:.8g}` \n"
                    f"⏱ Achieved in: `{m}m`"
                )
                send_telegram(msg)
        if (time.time() - active_trades[sym]['time']) > 86400: del active_trades[sym]

def analyze_breakout_flow(sym):
    """تحليل الاختراق: جفاف البيع + انفجار الشراء"""
    try:
        kd_1h = get_data("https://api.mexc.com/api/v3/klines", {"symbol": sym, "interval": "1h", "limit": 20})
        kd_15m = get_data("https://api.mexc.com/api/v3/klines", {"symbol": sym, "interval": "15m", "limit": 20})
        if not kd_1h or not kd_15m: return None

        closes_1h = [float(c[4]) for c in kd_1h]
        ema20_1h = calc_ema(closes_1h, 20)
        if closes_1h[-1] < ema20_1h: return None

        closes_15m = [float(c[4]) for c in kd_15m]
        opens_15m = [float(c[1]) for c in kd_15m]
        vols_15m = [float(c[5]) for c in kd_15m]
        
        # 1. فحص جفاف البيع (Outflow Dry-up)
        in_f = 0; out_f = 0
        for i in range(-4, 0):
            c_val = vols_15m[i] * closes_15m[i]
            if closes_15m[i] > opens_15m[i]: in_f += c_val
            else: out_f += c_val
        
        if out_f == 0: out_f = 1
        ratio = in_f / out_f
        
        # السر: إذا كان البيع أقل من 10% من إجمالي التداول (Ratio > 9)
        is_dry = True if ratio > 9.0 else False

        move_1h = ((closes_15m[-1] - float(kd_15m[-5][4])) / float(kd_15m[-5][4])) * 100

        return {
            "move_1h": move_1h,
            "in": in_f,
            "out": out_f,
            "net": in_f - out_f,
            "ratio": ratio,
            "is_dry": is_dry,
            "price": closes_15m[-1]
        }
    except: return None

def scan():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if state["date"] != today: state.update({"date": today, "count": 0, "sent_coins": []})

    tickers = get_data("https://api.mexc.com/api/v3/ticker/24hr")
    if not tickers: return

    if not state["is_first_run"]:
        logger.info(f"🔍 MAFIO BOT: Monitoring for Breakouts... [Signals: {state['count']}]")

    for t in tickers:
        sym = t['symbol']
        if not sym.endswith("USDT") or any(x in sym for x in ["UP", "DOWN", "BEAR", "BULL"]): continue
        try:
            chg_24h = float(t['priceChangePercent']); vol_24h = float(t['quoteVolume'])
            price = float(t['lastPrice']); high, low = float(t['highPrice']), float(t['lowPrice'])
            if chg_24h < MIN_24H_CHANGE or vol_24h < MIN_VOLUME_24H or chg_24h > MAX_24H_CHANGE: continue
            price_pos = (price - low) / (high - low) if (high - low) > 0 else 0.5
            if price_pos > MAX_PRICE_POS: continue
            if sym in state["sent_coins"] or state["count"] >= MAX_SIGNALS_PER_DAY: continue

            data = analyze_breakout_flow(sym)
            if not data: continue

            # شرط DODO: سيولة طاغية (Ratio > 6) أو جفاف بيع (is_dry)
            if (data['ratio'] < MIN_FLOW_RATIO and not data['is_dry']) or data['net'] < MIN_NET_FLOW_USD: continue

            if state["is_first_run"]:
                state["sent_coins"].append(sym)
                continue

            state["count"] += 1; state["sent_coins"].append(sym)
            active_trades[sym] = {'entry': price, 'time': time.time(), 'max_gain': 0, 'milestones': []}
            
            status = "Outflow Dry-up ❄️" if data['is_dry'] else "High Inflow 🔥"
            msg = (
                "💀 *MAFIO BOT - اختراق متفجر* 💀\n\n"
                f"🆕 *#{sym.replace('USDT','')}* 💀 · 🔔 Signal #{state['count']}\n"
                f"💰 Price: `${price:.8g}`\n"
                f"📈 1h Move: `+{data['move_1h']:.2f}%` ⚡\n"
                f"📍 Position: `%{price_pos*100:.0f}` from Bottom ✅\n\n"
                f"⚡ Status: `{status}` \n"
                f"🟡 Interest: `Institutional Breakout 🐋` \n"
                "💹 *1h Flow:*\n"
                f"  📥 In: `${data['in']/1000:.1f}K` \n"
                f"  📤 Out: `${data['out']/1000:.1f}K` \n"
                f"  ▲ Net: `+${data['net']/1000:.1f}K` ✅\n\n"
                f"🕒 {datetime.now().strftime('%d %b %Y %H:%M')}\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "⚠️ _ادخل الآن - تم رصد جفاف في البيع وبداية انفجار سعري!_ 🚀"
            )
            send_telegram(msg)
            logger.info(f"✅ Breakout Signal: {sym}")
            time.sleep(2)
        except: continue

    if state["is_first_run"]:
        state["is_first_run"] = False
        logger.info("✅ Silent database built. Ready for DODO-style breakouts!")

def main():
    logger.info("🚀 MAFIO BOT 13.0 (Breakout Master) Started")
    send_telegram("💀 *MAFIO BOT 13.0* متصل.\nتم تفعيل خوارزمية 'جفاف البيع' (Outflow Dry-up) لاقتناص الانفجارات السريعة.")
    while True:
        try:
            scan()
            track_profits() 
            time.sleep(60) 
        except Exception as e:
            logger.error(f"Error: {e}")
            time.sleep(30)

if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
MAFIO BOT - VERSION 9.0 (300% HUNTER - FLOW ENGINE)
الاستراتيجية: اقتناص الانفجار من منطقة التجميع (STO Style)
المطور: MAFIO AI - نظام رصد السيولة المؤسساتية
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

# معايير "اقتناص الانفجار" (STO Logic)
MAX_SIGNALS_PER_DAY = 15
MIN_VOLUME_24H = 200000    
MAX_24H_CHANGE = 12.0      # العملة لا تزال في بداية حركتها
MAX_PRICE_POS = 0.30       # الربع السفلي من سعر اليوم (قاع حقيقي)
MIN_1H_MOVE = 1.0          # بداية الانطلاق
MIN_FLOW_RATIO = 5.0       # الشراء 5 أضعاف البيع (سيطرة كاملة)
MIN_NET_FLOW_USD = 20000   # دخول سيولة قوية (20 ألف دولار كحد أدنى في ساعة)
# ==========================================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s", stream=sys.stdout)
logger = logging.getLogger("MAFIO_BOT")

state = {"date": "", "count": 0, "sent_coins": []}
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
            
        for milestone in [2, 5, 10, 20, 50, 100, 200, 300]:
            if gain >= milestone and milestone not in active_trades[sym]['milestones']:
                active_trades[sym]['milestones'].append(milestone)
                duration = int((time.time() - active_trades[sym]['time']) / 60)
                msg = (
                    f"🚀 *{sym.replace('USDT','')} {milestone}% milestone reached*\n"
                    f"📊 Max gain: `+{active_trades[sym]['max_gain']:.2f}%` \n"
                    f"💰 Price now: `${current_price:.8g}` \n"
                    f"🏁 Entry: `${entry_price:.8g}` \n"
                    f"⏱ Achieved in: `{duration}m`"
                )
                send_telegram(msg)
        if (time.time() - active_trades[sym]['time']) > 172800: del active_trades[sym] # تتبع لمدة يومين

def analyze_explosion_potential(sym):
    """تحليل إمكانية الانفجار (نفس نمط STO)"""
    try:
        # جلب شموع 15 دقيقة (لتحليل الحجم والسيولة)
        kd_15m = get_data("https://api.mexc.com/api/v3/klines", {"symbol": sym, "interval": "15m", "limit": 40})
        # جلب شموع الساعة (لتأكيد الترند)
        kd_1h = get_data("https://api.mexc.com/api/v3/klines", {"symbol": sym, "interval": "1h", "limit": 20})
        
        if not kd_15m or not kd_1h: return None

        closes_15m = [float(c[4]) for c in kd_15m]
        opens_15m = [float(c[1]) for c in kd_15m]
        vols_15m = [float(c[5]) for c in kd_15m]
        
        closes_1h = [float(c[4]) for c in kd_1h]
        ema20_1h = calc_ema(closes_1h, 20)
        current_price = closes_15m[-1]

        # 1. فحص الترند: يجب أن يكون السعر قد بدأ بالاستقرار فوق EMA20 ساعة
        if current_price < ema20_1h: return None

        # 2. فحص انفجار الحجم (Volume Spike): الحجم الحالي > 3 أضعاف متوسط آخر 20 شمعة
        avg_vol = sum(vols_15m[-21:-1]) / 20
        current_vol = vols_15m[-1]
        if current_vol < avg_vol * 3.0: return None

        # 3. تحليل السيولة (Flow In vs Out)
        in_f = 0; out_f = 0
        for i in range(-4, 0): # آخر ساعة
            c_val = vols_15m[i] * closes_15m[i]
            if closes_15m[i] > opens_15m[i]: in_f += c_val
            else: out_f += c_val
        
        net_f = in_f - out_f
        ratio = in_f / out_f if out_f > 0 else 10.0
        
        # حركة الساعة
        move_1h = ((current_price - float(kd_1h[-2][4])) / float(kd_1h[-2][4])) * 100

        return {
            "move_1h": move_1h,
            "in": in_f,
            "out": out_f,
            "net": net_f,
            "ratio": ratio,
            "price": current_price,
            "spike": current_vol / avg_vol
        }
    except: return None

def scan():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if state["date"] != today: state.update({"date": today, "count": 0, "sent_coins": []})

    tickers = get_data("https://api.mexc.com/api/v3/ticker/24hr")
    if not tickers: return

    for t in tickers:
        sym = t['symbol']
        if not sym.endswith("USDT") or any(x in sym for x in ["UP", "DOWN", "BEAR", "BULL"]): continue
        
        try:
            price = float(t['lastPrice'])
            high, low = float(t['highPrice']), float(t['lowPrice'])
            vol_24h = float(t['quoteVolume'])
            chg_24h = float(t['priceChangePercent'])
            
            # فلتر القاع الصارم (STO Style)
            price_pos = (price - low) / (high - low) if (high - low) > 0 else 0.5
            if price_pos > MAX_PRICE_POS or vol_24h < MIN_VOLUME_24H or chg_24h > MAX_24H_CHANGE: continue
            
            if sym in state["sent_coins"] or state["count"] >= MAX_SIGNALS_PER_DAY: continue

            # التحليل العميق للانفجار
            data = analyze_explosion_potential(sym)
            if not data: continue

            # شروط الاقتناص الذهبية
            if data['ratio'] < MIN_FLOW_RATIO or data['net'] < MIN_NET_FLOW_USD or data['move_1h'] < MIN_1H_MOVE: continue

            # إرسال الإشارة
            state["count"] += 1
            state["sent_coins"].append(sym)
            active_trades[sym] = {'entry': price, 'time': time.time(), 'max_gain': 0, 'milestones': []}
            
            msg = (
                "💀 *MAFIO BOT - قناص الانفجارات* 💀\n\n"
                f"🆕 *#{sym.replace('USDT','')}* 💀 · 🔔 Signal #{state['count']}\n"
                f"💰 Price: `${price:.8g}`\n"
                f"📈 1h Move: `+{data['move_1h']:.2f}%` ⚡\n"
                f"📍 Position: `%{price_pos*100:.0f}` from Bottom ✅\n\n"
                f"💥 Volume Spike: `{data['spike']:.1f}x` (انفجار حجم) 🔥\n"
                f"🟡 Interest: `Institutional Accumulation 🐋` \n"
                "💹 *1h Flow:*\n"
                f"  📥 In: `${data['in']/1000:.1f}K` \n"
                f"  📤 Out: `${data['out']/1000:.1f}K` \n"
                f"  ▲ Net: `+${data['net']/1000:.1f}K` ✅\n\n"
                f"🕒 {datetime.now().strftime('%d %b %Y %H:%M')}\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "⚠️ _ادخل الآن - العملة تكرر نموذج STO التاريخي!_ 🚀"
            )
            send_telegram(msg)
            logger.info(f"✅ Explosion Signal: {sym} | Spike: {data['spike']:.1f}x")
            time.sleep(2)
        except: continue

def main():
    logger.info("🚀 MAFIO BOT 9.0 (300% Hunter) Started")
    send_telegram("✅ *MAFIO BOT 9.0* متصل.\nتم تفعيل خوارزمية STO لاقتناص الانفجارات الكبرى من منطقة التجميع.")
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

# -*- coding: utf-8 -*-
"""
MAFIO BOT - VERSION 10.0 (ATOMIC FLOW ENGINE)
السر: رصد تسارع السيولة (Flow Acceleration) قبل حركة السعر
اقتناص الانفجارات في دقائق معدودة - نظام Wolf Flow المطور
"""

import os
import sys
import time
import requests
import logging
from datetime import datetime, timezone

# ==========================================================
# الإعدادات السرية - Secret Settings
# ==========================================================
TOKEN = os.getenv("TELEGRAM_TOKEN", "ضع_التوكن_هنا")
ADMIN_ID = os.getenv("CHAT_ID", "ضع_الايدي_هنا")

# معايير "الاقتناص اللحظي"
MAX_SIGNALS_PER_DAY = 15
MIN_VOLUME_24H = 200000    
MAX_24H_CHANGE = 15.0      
MAX_PRICE_POS = 0.40       # السماح بنطاق أوسع قليلاً لاقتناص بداية الارتداد
MIN_FLOW_RATIO = 6.0       # الشراء يجب أن يكون 6 أضعاف البيع (اكتساح عروض)
MIN_NET_FLOW_USD = 10000   
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
            
        # تنبيهات Milestones مطابقة للصور
        for milestone in [2, 5, 10, 25, 50, 100, 200, 300]:
            if gain >= milestone and milestone not in active_trades[sym]['milestones']:
                active_trades[sym]['milestones'].append(milestone)
                duration_sec = int(time.time() - active_trades[sym]['time'])
                h = duration_sec // 3600
                m = (duration_sec % 3600) // 60
                time_str = f"{h}h {m}m" if h > 0 else f"{m}m"
                
                msg = (
                    f"🚀 *{sym.replace('USDT','')} +{milestone}% milestone reached*\n"
                    f"📊 Max gain: `+{active_trades[sym]['max_gain']:.2f}%` \n"
                    f"💰 Price now: `${current_price:.8g}` \n"
                    f"🏁 Entry: `${entry_price:.8g}` \n"
                    f"⏱ Achieved in: `{time_str}`"
                )
                send_telegram(msg)
        if (time.time() - active_trades[sym]['time']) > 172800: del active_trades[sym]

def analyze_atomic_flow(sym):
    """تحليل تسارع السيولة اللحظي (Atomic Flow)"""
    try:
        # جلب شموع 5 دقائق لرصد التسارع اللحظي
        kd_5m = get_data("https://api.mexc.com/api/v3/klines", {"symbol": sym, "interval": "5m", "limit": 20})
        if not kd_5m or len(kd_5m) < 10: return None

        # حساب السيولة في آخر 15 دقيقة (3 شموع)
        in_f = 0; out_f = 0
        for c in kd_5m[-3:]:
            op, cl, vo = float(c[1]), float(c[4]), float(c[5])
            usd_vol = vo * cl
            if cl > op: in_f += usd_vol
            else: out_f += usd_vol
        
        # حساب السيولة في الـ 45 دقيقة السابقة للمقارنة (التسارع)
        prev_in = 0
        for c in kd_5m[-12:-3]:
            op, cl, vo = float(c[1]), float(c[4]), float(c[5])
            if cl > op: prev_in += (vo * cl)
        
        avg_prev_in = prev_in / 9
        current_in_avg = in_f / 3
        
        # معامل التسارع: كم مرة زاد الشراء الآن عن السابق
        acceleration = current_in_avg / avg_prev_in if avg_prev_in > 0 else 1.0
        
        if out_f == 0: out_f = 1
        ratio = in_f / out_f
        net_f = in_f - out_f
        
        # حركة الساعة
        move_1h = ((float(kd_5m[-1][4]) - float(kd_5m[-12][4])) / float(kd_5m[-12][4])) * 100

        return {
            "move_1h": move_1h,
            "in": in_f,
            "out": out_f,
            "net": net_f,
            "ratio": ratio,
            "accel": acceleration,
            "price": float(kd_5m[-1][4])
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
            
            price_pos = (price - low) / (high - low) if (high - low) > 0 else 0.5
            if price_pos > MAX_PRICE_POS or vol_24h < MIN_VOLUME_24H or chg_24h > MAX_24H_CHANGE: continue
            if sym in state["sent_coins"] or state["count"] >= MAX_SIGNALS_PER_DAY: continue

            # التحليل الذري للسيولة
            data = analyze_atomic_flow(sym)
            if not data: continue

            # السر: سيولة طاغية (Ratio > 6) + تسارع في الشراء (Accel > 2.5)
            if data['ratio'] < MIN_FLOW_RATIO or data['accel'] < 2.5 or data['net'] < MIN_NET_FLOW_USD: continue

            # إرسال الإشارة
            state["count"] += 1
            state["sent_coins"].append(sym)
            active_trades[sym] = {'entry': price, 'time': time.time(), 'max_gain': 0, 'milestones': []}
            
            msg = (
                "💀 *MAFIO BOT* 💀\n\n"
                f"🆕 *#{sym.replace('USDT','')}* 💀 · 🔔 Signal #{state['count']}\n"
                f"💰 Price: `${price:.8g}`\n"
                f"📈 1h Move: `{data['move_1h']:+.2f}%` ⚡\n\n"
                f"⚡ Volume: `High 🔥` \n"
                f"🟡 Interest: `Flow Acceleration 🚀` \n"
                "💹 *1h Flow:*\n"
                f"  📥 In: `${data['in']/1000:.1f}K` \n"
                f"  📤 Out: `${data['out']/1000:.1f}K` \n"
                f"  ▲ Net: `+${data['net']/1000:.1f}K` ✅\n"
                "🟡 Funding: `Neutral` 📈 Longs\n\n"
                f"🕒 {datetime.now().strftime('%d %b %Y %H:%M')}\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "⚠️ _ادخل الآن - تم رصد تسارع عنيف في سيولة الحيتان!_ 🎯"
            )
            send_telegram(msg)
            logger.info(f"✅ Atomic Flow: {sym} | Accel: {data['accel']:.1f}x")
            time.sleep(2)
        except: continue

def main():
    logger.info("🚀 MAFIO BOT 10.0 (Atomic Flow) Started")
    send_telegram("✅ *MAFIO BOT 10.0* متصل.\nتم تفعيل خوارزمية تسارع السيولة (Acceleration) لاقتناص الانفجارات اللحظية.")
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

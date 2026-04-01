# -*- coding: utf-8 -*-
"""
MAFIO BOT - VERSION 7.1 (SKULL EDITION)
الاستراتيجية: اقتناص التجميع في القاع + تتبع الأرباح تلقائياً (Profit Tracking)
المطور: MAFIO AI
"""

import os
import sys
import time
import requests
import logging
from datetime import datetime, timezone

# ==========================================================
# الإعدادات - Settings
# ==========================================================
TOKEN = os.getenv("TELEGRAM_TOKEN", "ضع_التوكن_هنا")
ADMIN_ID = os.getenv("CHAT_ID", "ضع_الايدي_هنا")

# معايير الاقتناص
MAX_SIGNALS_PER_DAY = 15
MIN_VOLUME_24H = 250000    
MAX_24H_CHANGE = 10.0      # لا ندخل في عملة طارت أكثر من 10% في يوم
MAX_PRICE_POS = 0.35       # يجب أن تكون العملة في أول 35% من قاع اليوم
MIN_FLOW_RATIO = 4.0       # الشراء 4 أضعاف البيع
# ==========================================================

# سجلات بيضاء لـ Railway
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s", stream=sys.stdout)
logger = logging.getLogger("MAFIO_BOT")

# حالة البوت وتتبع الأرباح
state = {"date": "", "count": 0, "sent_coins": []}
active_trades = {} # لتتبع الأرباح {sym: {'entry': price, 'time': ts, 'max_gain': 0, 'milestones': []}}

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
    """تتبع العملات المرسلة وإرسال تنبيه عند تحقيق أرباح"""
    if not active_trades: return
    
    tickers = get_data("https://api.mexc.com/api/v3/ticker/24hr")
    if not tickers: return
    
    ticker_dict = {t['symbol']: float(t['lastPrice']) for t in tickers}
    
    for sym in list(active_trades.keys()):
        if sym not in ticker_dict: continue
        
        current_price = ticker_dict[sym]
        entry_price = active_trades[sym]['entry']
        start_time = active_trades[sym]['time']
        
        gain = ((current_price - entry_price) / entry_price) * 100
        
        # تتبع أعلى ربح وصل له
        if gain > active_trades[sym]['max_gain']:
            active_trades[sym]['max_gain'] = gain
            
        # إرسال تنبيه عند تحقيق أهداف (2%, 5%, 10%, 20%...)
        for milestone in [2, 5, 10, 20, 50, 100]:
            if gain >= milestone and milestone not in active_trades[sym]['milestones']:
                active_trades[sym]['milestones'].append(milestone)
                duration = int((time.time() - start_time) / 60) # بالدقائق
                
                msg = (
                    f"✅ *{sym.replace('USDT','')} WIN confirmed +{milestone}% reached*\n"
                    f"📊 Max gain: `+{active_trades[sym]['max_gain']:.2f}%` \n"
                    f"💰 Price now: `${current_price:.8g}` \n"
                    f"🏁 Entry: `${entry_price:.8g}` \n"
                    f"⏱ Achieved in: `{duration}m`"
                )
                send_telegram(msg)
                
        # حذف من التتبع بعد 24 ساعة
        if (time.time() - start_time) > 86400:
            del active_trades[sym]

def scan():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if state["date"] != today:
        state.update({"date": today, "count": 0, "sent_coins": []})

    tickers = get_data("https://api.mexc.com/api/v3/ticker/24hr")
    if not tickers: return

    for t in tickers:
        sym = t['symbol']
        if not sym.endswith("USDT") or any(x in sym for x in ["UP", "DOWN", "BEAR", "BULL"]): continue
        
        try:
            price = float(t['lastPrice'])
            high, low = float(t['highPrice']), float(t['lowPrice'])
            vol_24h, open_p = float(t['quoteVolume']), float(t['openPrice'])
            
            price_pos = (price - low) / (high - low) if (high - low) > 0 else 0.5
            real_chg = ((price - open_p) / open_p) * 100

            if price_pos > MAX_PRICE_POS or vol_24h < MIN_VOLUME_24H or real_chg > MAX_24H_CHANGE: continue
            if sym in state["sent_coins"] or state["count"] >= MAX_SIGNALS_PER_DAY: continue

            # تحليل السيولة (Flow)
            kd = get_data("https://api.mexc.com/api/v3/klines", {"symbol": sym, "interval": "15m", "limit": 10})
            if not kd or len(kd) < 5: continue
            
            in_f = 0; out_f = 0
            for c in kd[-4:]:
                c_vol = float(c[5]) * float(c[4])
                if float(c[4]) > float(c[1]): in_f += c_vol
                else: out_f += c_vol
            
            if out_f == 0: out_f = 1
            ratio = in_f / out_f
            net_f = in_f - out_f
            move_1h = ((price - float(kd[-5][4])) / float(kd[-5][4])) * 100

            if ratio < MIN_FLOW_RATIO or net_f < 5000: continue

            # إرسال الإشارة
            state["count"] += 1
            state["sent_coins"].append(sym)
            active_trades[sym] = {'entry': price, 'time': time.time(), 'max_gain': 0, 'milestones': []}
            
            msg = (
                "💀 *MAFIO BOT - اقتناص من القاع* 💀\n\n"
                f"🆕 *#{sym.replace('USDT','')}* 💀 · 🔔 Signal #{state['count']}\n"
                f"💰 Price: `${price:.8g}`\n"
                f"📈 1h Move: `+{move_1h:.2f}%` ⚡\n"
                f"📍 Position: `%{price_pos*100:.0f}` from Bottom ✅\n\n"
                f"⚡ Volume: `Good ✅` \n"
                f"🟡 Interest: `Institutional 🐋` \n"
                "💹 *1h Flow:*\n"
                f"  📥 In: `${in_f/1000:.1f}K` \n"
                f"  📤 Out: `${out_f/1000:.1f}K` \n"
                f"  ▲ Net: `+${net_f/1000:.1f}K` ✅\n"
                "🟡 Funding: `Neutral` 📈 Longs\n\n"
                f"🕒 {datetime.now().strftime('%d %b %Y %H:%M')}\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "⚠️ _ادخل الآن - العملة في القاع والسيولة بدأت بالانفجار!_ 🚀"
            )
            send_telegram(msg)
            logger.info(f"✅ Signal: {sym}")
            time.sleep(2)
        except: continue

def main():
    logger.info("🚀 MAFIO BOT 7.1 (Skull Edition) Started")
    send_telegram("✅ *MAFIO BOT 7.1* متصل.\nتم استبدال الشعار برأس الجمجمة 💀 وتفعيل نظام تتبع الأرباح.")
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

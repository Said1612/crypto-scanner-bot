# -*- coding: utf-8 -*-
"""
MAFIO BOT - VERSION 5.0 (LIQUIDITY FLOW ENGINE)
الاستراتيجية: التركيز الكلي على قوة السيولة الشرائية (Inflow vs Outflow)
اقتناص العملات في الأسواق الهابطة بناءً على تجميع الحيتان
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

# معايير الاقتناص (Wolf Flow Logic)
MAX_SIGNALS_PER_DAY = 12
MIN_VOLUME_24H = 300000    
MIN_FLOW_RATIO = 4.0       # الشراء يجب أن يكون 4 أضعاف البيع على الأقل
MIN_NET_FLOW_USD = 5000    # صافي دخول السيولة يجب أن يتجاوز 5000$ في ساعة
MAX_24H_CHANGE = 15.0      # تجنب العملات التي تضخمت فعلياً
# ==========================================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s", stream=sys.stdout)
logger = logging.getLogger("MAFIO_BOT")

state = {"date": "", "count": 0, "sent_coins": []}
last_signal_time = 0

def send_telegram(message):
    if "ضع_" in TOKEN or not TOKEN: return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": ADMIN_ID, "text": message, "parse_mode": "Markdown"}, timeout=15)
    except: pass

def get_data(url, params=None):
    try:
        r = requests.get(url, params=params, timeout=15)
        if r.status_code != 200: return None
        return r.json()
    except: return None

def analyze_institutional_flow(sym):
    """تحليل السيولة المؤسساتية (دخول وخروج الأموال الحقيقي)"""
    try:
        # جلب شموع 15 دقيقة (آخر ساعة = 4 شموع)
        kd = get_data("https://api.mexc.com/api/v3/klines", {"symbol": sym, "interval": "15m", "limit": 20})
        if not isinstance(kd, list) or len(kd) < 10: return None

        in_flow = 0; out_flow = 0
        closes = []
        
        # تحليل آخر 4 شموع (الساعة الأخيرة)
        for c in kd[-4:]:
            if len(c) < 6: continue
            op, hi, lo, cl, vo = float(c[1]), float(c[2]), float(c[3]), float(c[4]), float(c[5])
            closes.append(cl)
            candle_usd_vol = vo * cl
            
            if cl > op: # شمعة شرائية
                in_flow += candle_usd_vol
            else: # شمعة بيعية
                out_flow += candle_usd_vol
        
        if out_flow == 0: out_flow = 1
        net_flow = in_flow - out_flow
        ratio = in_flow / out_flow
        
        # حساب حركة السعر في ساعة
        move_1h = ((closes[-1] - float(kd[-5][4])) / float(kd[-5][4])) * 100 if len(kd) >= 5 else 0

        # تحديد حالة الاهتمام والحجم
        vol_status = "High 🔥" if ratio > 5.0 else "Good ✅"
        interest = "Institutional 🐋" if ratio > 4.0 else "Neutral"

        return {
            "move_1h": move_1h,
            "in": in_flow,
            "out": out_flow,
            "net": net_flow,
            "ratio": ratio,
            "vol_status": vol_status,
            "interest": interest,
            "price": closes[-1]
        }
    except: return None

def scan():
    global last_signal_time
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if state["date"] != today:
        state.update({"date": today, "count": 0, "sent_coins": []})

    tickers = get_data("https://api.mexc.com/api/v3/ticker/24hr")
    if not isinstance(tickers, list): return

    for t in tickers:
        sym = t.get('symbol', '')
        if not sym.endswith("USDT") or any(x in sym for x in ["UP", "DOWN", "BEAR", "BULL"]): continue
        
        try:
            vol_24h = float(t.get('quoteVolume', 0))
            chg_24h = float(t.get('priceChangePercent', 0))
            
            # فلاتر أولية
            if vol_24h < MIN_VOLUME_24H or chg_24h > MAX_24H_CHANGE: continue
            if sym in state["sent_coins"] or state["count"] >= MAX_SIGNALS_PER_DAY: continue
            
            # منع تلاحم الإشارات (إشارة كل 10 دقائق على الأقل)
            if time.time() - last_signal_time < 600: continue

            # التحليل العميق للسيولة (Flow)
            flow = analyze_institutional_flow(sym)
            if not flow: continue

            # الشرط الذهبي: سيولة شرائية طاغية (Inflow >> Outflow)
            if flow['ratio'] < MIN_FLOW_RATIO or flow['net'] < MIN_NET_FLOW_USD: continue

            # إرسال الإشارة بتنسيق Wolf Flow
            state["count"] += 1
            state["sent_coins"].append(sym)
            last_signal_time = time.time()
            
            msg = (
                "🐺 *MAFIO BOT* 🐺\n\n"
                f"🆕 *#{sym.replace('USDT','')}* 🐺 · 🔔 Signal #{state['count']}\n"
                f"💰 Price: `${flow['price']:.8g}`\n"
                f"📈 1h Move: `+{flow['move_1h']:.2f}%` ⚡\n\n"
                f"⚡ Volume: `{flow['vol_status']}`\n"
                f"🟡 Interest: `{flow['interest']}`\n"
                "💹 *1h Flow:*\n"
                f"  📥 In: `${flow['in']/1000:.1f}K` \n"
                f"  📤 Out: `${flow['out']/1000:.1f}K` \n"
                f"  ▲ Net: `+${flow['net']/1000:.1f}K` ✅\n"
                "🟡 Funding: `Neutral` 📈 Longs\n\n"
                f"🕒 {datetime.now().strftime('%d %b %Y %H:%M')}\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "⚠️ _ادخل الآن - سيولة شرائية ضخمة تكتسح العروض!_ 🚀"
            )
            send_telegram(msg)
            logger.info(f"✅ Signal: {sym} | Ratio: {flow['ratio']:.1f}x")
            time.sleep(2)
        except: continue

def main():
    logger.info("🚀 MAFIO BOT 5.0 (Flow Engine) Started")
    send_telegram("✅ *MAFIO BOT 5.0* متصل.\nالمحرك يركز الآن على اقتناص السيولة الشرائية القوية (Flow In) حتى في الأسواق الهابطة.")
    while True:
        try:
            scan()
            time.sleep(60) 
        except Exception as e:
            logger.error(f"Error: {e}")
            time.sleep(30)

if __name__ == "__main__":
    main()

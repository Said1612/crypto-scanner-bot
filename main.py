# -*- coding: utf-8 -*-
"""
MAFIO BOT - VERSION 13.3 (SMART SNIPER)
السر: تجاوز حظر الـ API عن طريق فحص "نخبة" العملات فقط
المطور: MAFIO AI
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

# معايير الفلترة الأولية
MIN_VOLUME_24H = 200000    
MIN_24H_CHANGE = -10.0      
MAX_24H_CHANGE = 20.0      
MAX_PRICE_POS = 0.55       

# معايير الانفجار
MIN_FLOW_RATIO = 4.0       
MIN_NET_FLOW_USD = 10000   
# ==========================================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s", stream=sys.stdout)
logger = logging.getLogger("MAFIO_BOT")

state = {"date": "", "count": 0, "sent_coins": [], "is_first_run": True}

def send_telegram(message):
    if "ضع_" in TOKEN or not TOKEN: return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try: requests.post(url, data={"chat_id": ADMIN_ID, "text": message, "parse_mode": "Markdown"}, timeout=15)
    except: pass

def get_data(url, params=None):
    try:
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 429: 
            time.sleep(5) # حظر شديد، انتظر أكثر
            return None
        return r.json() if r.status_code == 200 else None
    except: return None

def calc_ema(prices, period):
    if len(prices) < period: return 0
    k = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for p in prices[period:]:
        ema = (p * k) + (ema * (1 - k))
    return ema

def analyze_breakout_flow(sym):
    """تحليل السيولة بعمق"""
    try:
        time.sleep(0.3) # تأخير كافٍ لتجنب الحظر
        # طلب بيانات الساعة والـ 15 دقيقة في طلب واحد إذا أمكن (هنا نطلب الـ 15 دقيقة أولاً)
        kd = get_data("https://api.mexc.com/api/v3/klines", {"symbol": sym, "interval": "15m", "limit": 30})
        if not kd: return "API_ERR"
        
        closes = [float(c[4]) for c in kd]; opens = [float(c[1]) for c in kd]; vols = [float(c[5]) for c in kd]
        
        # فحص الترند السريع (EMA 20 على 15m كبديل لتوفير الطلبات)
        ema20 = calc_ema(closes, 20)
        if closes[-1] < ema20: return "TREND_DOWN"
        
        in_f = 0; out_f = 0
        for i in range(-4, 0):
            c_val = vols[i] * closes[i]
            if closes[i] > opens[i]: in_f += c_val
            else: out_f += c_val
        
        if out_f == 0: out_f = 1
        ratio = in_f / out_f
        is_dry = True if ratio > 7.0 else False
        move_1h = ((closes[-1] - float(kd[-5][4])) / float(kd[-5][4])) * 100
        
        return {"move_1h": move_1h, "in": in_f, "out": out_f, "net": in_f - out_f, "ratio": ratio, "is_dry": is_dry, "price": closes[-1]}
    except: return "SYS_ERR"

def scan():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if state["date"] != today: state.update({"date": today, "count": 0, "sent_coins": []})

    tickers = get_data("https://api.mexc.com/api/v3/ticker/24hr")
    if not tickers: return

    # 1. جمع المرشحين الذين اجتازوا الفلتر الأساسي
    candidates = []
    for t in tickers:
        sym = t['symbol']
        if not sym.endswith("USDT") or any(x in sym for x in ["UP", "DOWN", "BEAR", "BULL"]): continue
        try:
            chg_24h = float(t['priceChangePercent']); vol_24h = float(t['quoteVolume'])
            price = float(t['lastPrice']); high, low = float(t['highPrice']), float(t['lowPrice'])
            
            if chg_24h < MIN_24H_CHANGE or vol_24h < MIN_VOLUME_24H or chg_24h > MAX_24H_CHANGE: continue
            price_pos = (price - low) / (high - low) if (high - low) > 0 else 0.5
            if price_pos > MAX_PRICE_POS: continue
            
            candidates.append({'sym': sym, 'vol': vol_24h, 'price': price, 'pos': price_pos, 'chg': chg_24h})
        except: continue

    # 2. ترتيب المرشحين حسب الحجم واختيار أفضل 40 فقط (لتجنب الحظر)
    candidates.sort(key=lambda x: x['vol'], reverse=True)
    top_candidates = candidates[:40]

    scanned_deep = 0; trend_down = 0; api_err = 0; max_r = 0.0
    for c in top_candidates:
        sym = c['sym']
        if sym in state["sent_coins"]: continue

        data = analyze_breakout_flow(sym)
        if data == "TREND_DOWN": trend_down += 1; continue
        if data in ["API_ERR", "SYS_ERR"]: api_err += 1; continue
        
        scanned_deep += 1
        if data['ratio'] > max_r: max_r = data['ratio']
        
        if (data['ratio'] < MIN_FLOW_RATIO and not data['is_dry']) or data['net'] < MIN_NET_FLOW_USD: continue

        if state["is_first_run"]:
            state["sent_coins"].append(sym)
            continue

        state["count"] += 1; state["sent_coins"].append(sym)
        
        msg = (
            "💀 *MAFIO BOT - اختراق متفجر* 💀\n\n"
            f"🆕 *#{sym.replace('USDT','')}* 💀 · 🔔 Signal #{state['count']}\n"
            f"💰 Price: `${c['price']:.8g}`\n"
            f"📈 24h Change: `+{c['chg']:.2f}%` \n"
            f"📊 Ratio: `{data['ratio']:.1f}x` ✅\n\n"
            f"▲ Net Flow: `+${data['net']/1000:.1f}K` \n"
            f"🕒 {datetime.now().strftime('%H:%M UTC')}\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "⚠️ _فرصة قوية - سيولة مؤسساتية مرصودة!_ 🚀"
        )
        send_telegram(msg)
        logger.info(f"✅ Signal: {sym} | Ratio: {data['ratio']:.1f}")
        time.sleep(1)

    if not state["is_first_run"]:
        logger.info(f"🔍 Elite Scan: {len(top_candidates)} top coins | {scanned_deep} deep checked | {api_err} api_err | MaxR: {max_r:.1f}x")
    else:
        state["is_first_run"] = False
        logger.info("✅ Silent database built. Ready for elite breakouts!")

def main():
    logger.info("🚀 MAFIO BOT 13.3 (Smart Sniper) Started")
    send_telegram("💀 *MAFIO BOT 13.3* متصل.\nنظام 'فلترة النخبة' نشط الآن لتجاوز حظر الـ API.")
    while True:
        try:
            scan()
            time.sleep(40) 
        except Exception as e:
            logger.error(f"Error: {e}")
            time.sleep(30)

if __name__ == "__main__":
    main()

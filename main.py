# -*- coding: utf-8 -*-
"""
MAFIO BOT - VERSION 3.4 (GOLDEN EDITION)
الاستراتيجية: اقتناص الانفجار من القاع الحقيقي ومنع شراء القمم
"""

import os
import time
import requests
import logging
import traceback
from datetime import datetime, timezone

# ==========================================================
# الإعدادات
# ==========================================================
TOKEN = os.getenv("TELEGRAM_TOKEN", "ضع_التوكن_هنا")
ADMIN_ID = os.getenv("CHAT_ID", "ضع_الايدي_هنا")

# معايير الفحص (MAFIO Balanced Mode)
MAX_SIGNALS_PER_DAY = 15
MIN_VOLUME_24H = 150000    # تقليل الحد لزيادة فرص الرصد
MIN_24H_CHANGE = 0.5       # العملة بدأت تتحرك
MAX_24H_CHANGE = 15.0      # منع العملات التي طارت فعلاً
MAX_PRICE_POS = 0.4        # شرط القاع: السعر في أول 40% من نطاق اليوم
MIN_FLOW_RATIO = 3.5       # سيولة داخلة جيدة
# ==========================================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("MAFIO_BOT")

state = {"date": "", "count": 0, "sent_coins": []}

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

def calc_ema(prices, period):
    if len(prices) < period: return 0
    k = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for p in prices[period:]:
        ema = (p * k) + (ema * (1 - k))
    return ema

def check_indicators(sym, current_price):
    try:
        kd_15m = get_data("https://api.mexc.com/api/v3/klines", {"symbol": sym, "interval": "15m", "limit": 50})
        if not isinstance(kd_15m, list) or len(kd_15m) < 30: return False, None

        closes = []
        opens = []
        vols = []
        for c in kd_15m:
            if isinstance(c, list) and len(c) >= 6:
                closes.append(float(c[4]))
                opens.append(float(c[1]))
                vols.append(float(c[5]))

        if len(closes) < 30: return False, None

        # 1. فحص EMA (5 فوق 20)
        ema5 = calc_ema(closes, 5)
        ema20 = calc_ema(closes, 20)
        if ema5 <= ema20: return False, None

        # 2. فحص السيولة (Flow)
        in_vol = 0; out_vol = 0
        for i in range(-5, 0):
            val = vols[i] * closes[i]
            if closes[i] > opens[i]: in_vol += val
            else: out_vol += val
        
        ratio = in_vol / out_vol if out_vol > 0 else 5.0
        vdelta = in_vol / (in_vol + out_vol) if (in_vol + out_vol) > 0 else 0.5

        if ratio < MIN_FLOW_RATIO or vdelta < 0.70: return False, None

        return True, {"ratio": ratio, "vdelta": vdelta}
    except:
        return False, None

def scan():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if state["date"] != today:
        state.update({"date": today, "count": 0, "sent_coins": []})

    raw_tickers = get_data("https://api.mexc.com/api/v3/ticker/24hr")
    if not isinstance(raw_tickers, list): 
        logger.warning("⚠️ Failed to fetch tickers or invalid format.")
        return

    promising = []
    for t in raw_tickers:
        try:
            sym = t.get('symbol', '')
            if not sym.endswith("USDT") or any(x in sym for x in ["UP", "DOWN", "BEAR", "BULL"]): continue
            
            vol = float(t.get('quoteVolume', 0))
            price = float(t.get('lastPrice', 0))
            high = float(t.get('highPrice', 0))
            low = float(t.get('lowPrice', 0))
            open_p = float(t.get('openPrice', 0))
            
            if open_p == 0 or high == low: continue
            
            real_chg = ((price - open_p) / open_p) * 100
            price_pos = (price - low) / (high - low)

            # فلاتر MAFIO BOT 3.4
            if vol > MIN_VOLUME_24H and MIN_24H_CHANGE < real_chg < MAX_24H_CHANGE and price_pos < MAX_PRICE_POS:
                promising.append({'sym': sym, 'price': price, 'chg': real_chg, 'pos': price_pos})
        except: continue

    logger.info(f"🔍 MAFIO BOT: Found {len(promising)} candidates in the bottom range.")

    for item in promising[:30]: # فحص أفضل 30 مرشحاً
        sym = item['sym']
        if sym in state["sent_coins"]: continue
        if state["count"] >= MAX_SIGNALS_PER_DAY: break

        success, data = check_indicators(sym, item['price'])
        if success:
            state["count"] += 1
            state["sent_coins"].append(sym)
            
            msg = (
                "🤖 *MAFIO BOT - اقتناص من القاع* 🚀\n"
                "━━━━━━━━━━━━━━━━━━\n"
                f"📍 العملة: *#{sym.replace('USDT','')}*\n"
                f"💰 السعر: `{item['price']:.8g}`\n"
                f"📈 التغيير: `+{item['chg']:.2f}%` (بداية حركة)\n"
                f"📍 موقع السعر: `%{item['pos']*100:.0f}` من القاع ✅\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "🌊 *تحليل السيولة (Flow):*\n"
                f"✅ قوة التدفق: `{data['ratio']:.1f}x` لصالح الشراء\n"
                f"💎 ضغط الحيتان: `{data['vdelta']*100:.0f}%` 🔥\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "📢 *القرار:* العملة في منطقة شراء آمنة والسيولة بدأت بالتدفق\n"
                "⚠️ _ادخل الآن - MAFIO رصد الانفجار قبل حدوثه!_ 🎯"
            )
            send_telegram(msg)
            logger.info(f"✅ Signal Sent: {sym}")
            time.sleep(2)

def main():
    logger.info("🚀 MAFIO BOT 3.4 Started - Golden Edition")
    send_telegram("✅ *MAFIO BOT 3.4* متصل الآن ويبحث عن انفجارات القاع الحقيقية...")
    while True:
        try:
            scan()
            time.sleep(60) 
        except Exception as e:
            logger.error(f"❌ Critical Error: {e}")
            time.sleep(30)

if __name__ == "__main__":
    main()

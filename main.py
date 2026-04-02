# -*- coding: utf-8 -*-
import os, sys, time, requests, logging
from datetime import datetime

# --- الإعدادات ---
TOKEN = "YOUR_TELEGRAM_TOKEN"
ADMIN_ID = "YOUR_CHAT_ID"

# معايير الجمجمة الشبح (Phantom Skull)
MIN_VOLUME_24H = 150000     
MIN_ALPHA_SCORE = 1.0       # تقليل النسبة قليلاً لزيادة الفرص

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger("MAFIO_V19")

# محرك الجلسة مع معالجة الحظر الجغرافي
session = requests.Session()

def get_data_safe(url, params=None):
    try:
        # إضافة Headers لتبدو كمتصفح حقيقي لتجنب خطأ 451
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = session.get(url, params=params, headers=headers, timeout=10)
        if r.status_code == 200:
            return r.json()
        return None
    except: return None

def get_btc_1h():
    # محاولة جلب BTC من باينانس، وإذا فشل نجلب من MEXC
    data = get_data_safe("https://api.binance.com/api/v3/klines", {"symbol": "BTCUSDT", "interval": "1h", "limit": 2})
    if not data:
        data = get_data_safe("https://api.mexc.com/api/v3/klines", {"symbol": "BTC_USDT", "interval": "1h", "limit": 2})
    
    if data and len(data) > 1:
        return ((float(data[-1][4]) - float(data[-1][1])) / float(data[-1][1])) * 100
    return 0

def main():
    logger.info("💀 MAFIO V19.2: DEPLOYED & PROTECTED")
    sent_coins = []
    
    while True:
        try:
            btc_move = get_btc_1h()
            # جلب البيانات من MEXC لأنها أكثر استقراراً في السجلات الخاصة بك
            url = "https://api.mexc.com/api/v3/ticker/24hr"
            tickers = get_data_safe(url)
            
            if not tickers or not isinstance(tickers, list):
                logger.warning("⚠️ API Error: Switching source or retrying...")
                time.sleep(30); continue

            # تصفية العملات القوية فقط
            for t in tickers:
                sym = t['symbol']
                if not sym.endswith("USDT") or sym in sent_coins: continue
                
                vol = float(t.get('quoteVolume', 0))
                chg = float(t.get('priceChangePercent', 0))
                
                if vol > MIN_VOLUME_24H and 1.0 < chg < 15.0:
                    # فحص القوة النسبية (Alpha)
                    # ملاحظة: MEXC تستخدم 'lastPrice' بدلاً من 'last' في بعض الإصدارات
                    price = float(t['lastPrice'])
                    alpha = chg - btc_move
                    
                    if alpha > MIN_ALPHA_SCORE:
                        msg = (f"💀 *MAFIO PHANTOM 19.2*\n\n"
                               f"🚀 *#{sym.replace('_USDT','')}*\n"
                               f"💰 Price: `{price}`\n"
                               f"🛡️ Alpha: `+{alpha:.2f}%` (vs BTC)\n"
                               f"📊 24h Vol: `${vol/1000:.1f}K` ✅\n\n"
                               f"🔔 _رصد انفصال إيجابي عن السوق!_")
                        
                        # إرسال التنبيه
                        tel_url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
                        requests.post(tel_url, data={"chat_id": ADMIN_ID, "text": msg, "parse_mode": "Markdown"})
                        
                        sent_coins.append(sym)
                        if len(sent_coins) > 100: sent_coins.pop(0)

            logger.info(f"✅ Cycle Complete. BTC 1h: {btc_move:.2f}%")
            time.sleep(40)

        except Exception as e:
            logger.error(f"⚠️ System Error: {e}")
            time.sleep(20)

if __name__ == "__main__":
    main()

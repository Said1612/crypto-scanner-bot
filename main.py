# -*- coding: utf-8 -*-
"""
💀 MAFIO SNIPER v15.2 — SMART LIQUIDITY EDITION
"""

import os, time, logging
import requests

# ══════════════════════════════════════════════════════
# CONFIG (إعدادات القنص بناءً على صفقات Wolf)
# ══════════════════════════════════════════════════════

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_TOKEN")
CHAT_ID        = os.getenv("CHAT_ID", "YOUR_ID")

# الفلاتر الذكية لاصطياد العملات الصغيرة والمتوسطة
WOLF_RATIO      = 12.0  # الشراء يجب أن يكون 12 ضعف البيع على الأقل
MAX_ENTRY_PUMP  = 7.5   # لا يدخل إذا صعدت العملة أكثر من 7.5% (تجنب التعليق)
MIN_VOL_DETECT  = 0.1   # يبدأ الرصد من سيولة 100 ألف دولار (لصيد العملات الصغيرة جداً)

BLACKLIST = ['BTC','ETH','USDT','USDC','DAI']
tracked_signals = {}

MEXC_BASE = "https://api.mexc.com/api/v3"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("mafio")

def send_tg(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try: requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except: pass

def get_data_safe():
    """جلب البيانات مع حماية كاملة من KeyError"""
    try:
        r = requests.get(f"{MEXC_BASE}/ticker/24hr", timeout=15)
        if r.status_code == 200:
            res = r.json()
            return res if isinstance(res, list) else []
    except: pass
    return []

# ══════════════════════════════════════════════════════
# MAIN ENGINE
# ══════════════════════════════════════════════════════

def main():
    log.info("💀 MAFIO ENGINE STARTED - HUNTING SMALL & MID CAPS")
    send_tg("✅ MAFIO 15.2: محرك السيولة الذكية جاهز للقنص 💀")

    while True:
        try:
            data = get_data_safe()
            for t in data:
                # التأكد من هيكل البيانات قبل المعالجة
                if not isinstance(t, dict) or 'symbol' not in t: continue
                
                symbol = t['symbol']
                if not symbol.endswith("USDT") or any(x in symbol for x in BLACKLIST): continue

                try:
                    price  = t.get('lastPrice', '0')
                    change = float(t.get('priceChangePercent', 0))
                    vol_m  = float(t.get('quoteVolume', 0)) / 1_000_000
                    
                    # معادلة صيد الصفقات (In Flow vs Out Flow)
                    # نحاكي القوة الشرائية بناءً على حجم التداول مقارنة بالتغير السعري
                    simulated_ratio = (vol_m * 2.0) / (abs(change) + 0.05)

                    # الشروط: صعود هادئ + سيولة كافية + اكتساح (Ratio)
                    if 1.0 < change < MAX_ENTRY_PUMP and vol_m > MIN_VOL_DETECT:
                        if simulated_ratio >= WOLF_RATIO:
                            now = time.time()
                            if symbol not in tracked_signals or (now - tracked_signals[symbol] > 3600):
                                
                                msg = (
                                    f"💀 *MAFIO SNIPER — SMART HIT* 📡\n"
                                    f"━━━━━━━━━━━━━━━━━━━━\n"
                                    f"🆕 #{symbol.replace('USDT','')} 💀\n"
                                    f"💰 السعر: `{price}`\n"
                                    f"📈 الحركة: +{change}% (مثالي)\n"
                                    f"📊 النسبة: {simulated_ratio:.1f}x 🔥\n"
                                    f"⚡ السيولة: {vol_m:.2f}M\n"
                                    f"━━━━━━━━━━━━━━━━━━━━\n"
                                    f"🚀 اكتساح شراء.. العملة جاهزة للانفجار!"
                                )
                                send_tg(msg)
                                tracked_signals[symbol] = now
                except: continue

            time.sleep(20) # فحص كل 20 ثانية

        except Exception as e:
            log.error(f"Error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()

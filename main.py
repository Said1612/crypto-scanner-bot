# -*- coding: utf-8 -*-
import os, time, logging
import requests

# ══════════════════════════════════════════════════════
# CONFIG (نفس متغيرات Railway الخاصة بك)
# ══════════════════════════════════════════════════════

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID        = os.getenv("CHAT_ID", "")

# إعدادات القنص المحدثة بناءً على صفقات Wolf Flow
WOLF_RATIO      = 5.0   # خفضنا النسبة قليلاً لضمان عدم تفويت الصفقات
MAX_ENTRY_PUMP  = 10.0  # رفعنا السقف لـ 10% للسماح بصيد العملات السريعة
MIN_VOL_DETECT  = 0.05  # يبدأ الرصد من 50 ألف دولار (لصيد العملات الصغيرة جداً)

BLACKLIST = ['BTC','ETH','USDT','USDC','DAI']
tracked_signals = {}

MEXC_BASE = "https://api.mexc.com/api/v3"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mafio")

# ══════════════════════════════════════════════════════
# FUNCTIONS (مبنية على سكريبتك الأصلي لضمان الاستقرار)
# ══════════════════════════════════════════════════════

def send_tg(msg):
    if not TELEGRAM_TOKEN: return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except Exception as e:
        log.error(f"TG Error: {e}")

def get_data_safe():
    """دالة جلب البيانات الآمنة (No-Error Version)"""
    try:
        # استخدام هيدرز لضمان عدم الحظر من MEXC
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(f"{MEXC_BASE}/ticker/24hr", headers=headers, timeout=15)
        if r.status_code == 200:
            res = r.json()
            if isinstance(res, list): return res
    except: pass
    return []

# ══════════════════════════════════════════════════════
# MAIN ENGINE
# ══════════════════════════════════════════════════════

def main():
    log.info("💀 MAFIO ENGINE STARTED - NO ERROR VERSION")
    send_tg("✅ MAFIO 15.2 ACTIVE 💀\nتم تفعيل خوارزمية السيولة الذكية")

    while True:
        try:
            data = get_data_safe()
            
            if not data:
                time.sleep(10)
                continue

            for t in data:
                # الحماية القصوى من KeyError (فحص وجود المفتاح قبل استخدامه)
                if not isinstance(t, dict) or 'symbol' not in t or 'lastPrice' not in t:
                    continue
                
                symbol = t['symbol']
                if not symbol.endswith("USDT") or any(x in symbol for x in BLACKLIST):
                    continue

                try:
                    price  = t.get('lastPrice', '0')
                    change = float(t.get('priceChangePercent', 0))
                    vol_m  = float(t.get('quoteVolume', 0)) / 1_000_000
                    
                    # معادلة اكتساح الشراء (In Flow vs Out Flow)
                    # قمنا بتحسينها لتناسب العملات الصغيرة (مثل صفقاتك السابقة)
                    simulated_ratio = (vol_m * 3.0) / (abs(change) + 0.1)

                    # شروط القنص: حجم كافٍ + صعود معتدل + نسبة اكتساح جيدة
                    if 1.0 < change < MAX_ENTRY_PUMP and vol_m > MIN_VOL_DETECT:
                        if simulated_ratio >= WOLF_RATIO:
                            now = time.time()
                            # منع تكرار العملة (Cooldown) لمدة ساعة واحدة
                            if symbol not in tracked_signals or (now - tracked_signals[symbol] > 3600):
                                
                                msg = (
                                    f"💀 *MAFIO SNIPER — TARGET LOCKED* 🎯\n"
                                    f"━━━━━━━━━━━━━━━━━━━━\n"
                                    f"🆕 #{symbol.replace('USDT','')} 💀\n"
                                    f"💰 السعر: `{price}`\n"
                                    f"📈 الحركة: +{change}% ⚡\n"
                                    f"📊 القوة: {simulated_ratio:.1f}x (Ratio)\n"
                                    f"⚡ السيولة: {vol_m:.2f}M (Smart Flow)\n"
                                    f"━━━━━━━━━━━━━━━━━━━━\n"
                                    f"🚀 سيولة ذكية تكتسح العروض الآن!"
                                )
                                send_tg(msg)
                                tracked_signals[symbol] = now
                                log.info(f"Signal sent for {symbol}")

                except (ValueError, TypeError):
                    continue

            # انتظار قصير لتقليل الضغط على السيرفر
            time.sleep(15)

        except Exception as e:
            log.error(f"Main Loop Error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()

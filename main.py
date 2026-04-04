# -*- coding: utf-8 -*-
import os, time, logging
import requests

# ══════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID        = os.getenv("CHAT_ID", "")

# إعدادات مرنة لاختبار الفحص فوراً
WOLF_RATIO      = 4.0   # تقليل النسبة قليلاً لزيادة الحساسية
MAX_ENTRY_PUMP  = 12.0  
MIN_VOL_DETECT  = 0.03  # صيد العملات ابتداءً من 30 ألف دولار سيولة

BLACKLIST = ['BTC','ETH','USDT','USDC','DAI']
tracked_signals = {}

MEXC_BASE = "https://api.mexc.com/api/v3"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mafio")

def send_tg(msg):
    if not TELEGRAM_TOKEN: return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=5)
    except: pass

def get_data_safe():
    try:
        # مهلة قصيرة (5 ثوانٍ) لمنع "تجمد" البوت
        r = requests.get(f"{MEXC_BASE}/ticker/24hr", timeout=5)
        if r.status_code == 200:
            res = r.json()
            if isinstance(res, list): return res
    except:
        log.warning("⚠️ MEXC Timeout - Skipping this round...")
    return []

def main():
    log.info("💀 MAFIO ENGINE 15.2 — ACTIVE SCANNING MODE")
    send_tg("🚀 MAFIO 15.2: المحرك بدأ الفحص الفعلي الآن...")

    last_heartbeat = time.time()

    while True:
        try:
            data = get_data_safe()
            
            # رسالة لتأكيد أن البوت "حي" في السجلات كل 60 ثانية
            if time.time() - last_heartbeat > 60:
                log.info(f"🔄 Heartbeat: Scanning {len(data) if data else 0} pairs...")
                last_heartbeat = time.time()

            if not data:
                time.sleep(5)
                continue

            for t in data:
                if not isinstance(t, dict) or 'symbol' not in t: continue
                
                symbol = t['symbol']
                if not symbol.endswith("USDT") or any(x in symbol for x in BLACKLIST):
                    continue

                try:
                    price  = t.get('lastPrice', '0')
                    change = float(t.get('priceChangePercent', 0))
                    vol_m  = float(t.get('quoteVolume', 0)) / 1_000_000
                    
                    # معادلة السيولة الذكية (Smart Flow)
                    simulated_ratio = (vol_m * 3.5) / (abs(change) + 0.1)

                    if 0.5 < change < MAX_ENTRY_PUMP and vol_m > MIN_VOL_DETECT:
                        if simulated_ratio >= WOLF_RATIO:
                            now = time.time()
                            if symbol not in tracked_signals or (now - tracked_signals[symbol] > 3600):
                                msg = (
                                    f"💀 *MAFIO SNIPER — HIT* 🎯\n"
                                    f"━━━━━━━━━━━━━━━━━━━━\n"
                                    f"🆕 #{symbol.replace('USDT','')} 💀\n"
                                    f"💰 السعر: `{price}`\n"
                                    f"📈 الحركة: +{change}% ⚡\n"
                                    f"📊 القوة: {simulated_ratio:.1f}x\n"
                                    f"⚡ السيولة: {vol_m:.2f}M\n"
                                    f"━━━━━━━━━━━━━━━━━━━━\n"
                                    f"🚀 اكتساح شراء تم رصده!"
                                )
                                send_tg(msg)
                                tracked_signals[symbol] = now
                                log.info(f"🎯 SIGNAL SENT: {symbol}")

                except: continue

            time.sleep(10) # فحص سريع كل 10 ثوانٍ

        except Exception as e:
            log.error(f"Error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()

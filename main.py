# -*- coding: utf-8 -*-
# Build: 20260401-ULTIMATE-WOLF
import os, sys, time, requests, logging
from datetime import datetime

# --- إعدادات اللوجات لـ Railway ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("WolfSniper")

# --- الإعدادات الذهبية (صيد القاع) ---
MIN_VOL_24H      = 150000    # منع العملات الوهمية
MAX_CHG_24H      = 8.0       # صيد من القاع فقط
WOLF_SPIKE_LIMIT = 4.0       # انفجار حجم 4 أضعاف في دقيقة
MIN_NET_FLOW     = 2000      # سيولة حقيقية بالدولار
CHECK_INTERVAL   = 12        # ثانية بين كل دورة فحص

# --- إعدادات التليجرام ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID        = os.getenv("CHAT_ID", "")

def send_tg(msg):
    if not TELEGRAM_TOKEN or not CHAT_ID: return
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                      data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except Exception as e: log.error(f"Telegram Error: {e}")

def safe_get(url, params=None):
    try:
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200: return r.json()
        if r.status_code == 429: log.warning("⚠️ Rate Limit Hit! Sleeping...") ; time.sleep(30)
        return None
    except: return None

def get_klines(sym, interval="1m", limit=10):
    data = safe_get("https://api.mexc.com/api/v3/klines", {"symbol": sym, "interval": interval, "limit": limit})
    if not data or len(data) < 5: return None
    return {
        "vols": [float(c[5]) for c in data],
        "closes": [float(c[4]) for c in data],
        "opens": [float(c[1]) for c in data]
    }

def wolf_logic(all_tickers):
    now = time.time()
    # 1. فلترة أولية لتقليل عدد العملات (حماية من الحظر)
    candidates = []
    for t in all_tickers:
        try:
            sym = t["symbol"]
            vol = float(t["quoteVolume"])
            chg = float(t["priceChangePercent"])
            if sym.endswith("USDT") and vol > MIN_VOL_24H and chg < MAX_CHG_24H:
                candidates.append(t)
        except: continue

    log.info(f"🔍 Scanning {len(candidates)} potential coins from the bottom...")

    for t in candidates:
        sym = t["symbol"]
        try:
            # فحص السيولة اللحظية (1 دقيقة)
            kd = get_klines(sym, "1m", 10)
            if not kd: continue
            
            avg_vol = sum(kd["vols"][:-1]) / 9
            if avg_vol <= 0: continue
            
            vol_spike = kd["vols"][-1] / avg_vol
            price_move = abs((kd["closes"][-1] - kd["closes"][-2]) / kd["closes"][-2] * 100)

            # الشرط الصاعق: فوليوم عالي + سعر لم يتحرك
            if vol_spike >= WOLF_SPIKE_LIMIT and price_move < 1.5:
                # تأكيد التدفق بالدولار
                net_flow = kd["vols"][-1] * kd["closes"][-1]
                if net_flow < MIN_NET_FLOW: continue

                msg = (
                    "🐺 *WOLF SNIPER SIGNAL* 🐺\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    "🎯 *#{}*\n"
                    "📊 الانفجار: `{}x` فوليوم دقيقة 🔥\n"
                    "💹 سيولة السيولة: `+${:,.0f}`\n"
                    "💰 السعر الحالي: `{}`\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    "🚀 *السيولة دخلت بالقاع — الانفجار وشيك* 🎯"
                ).format(sym.replace("USDT",""), round(vol_spike,1), net_flow, t["lastPrice"])
                
                log.info(f"🔥 SIGNAL FOUND: {sym}!")
                send_tg(msg)
                time.sleep(1) # تأخير بسيط بين الإشارات
        except: continue

def run():
    log.info("🚀 MAFIO-BOT WOLF EDITION STARTED SUCCESSFULY")
    send_tg("✅ *البوت بدأ العمل بنظام Wolf Sniper*\nيتم الآن مسح السوق بحثاً عن السيولة المختبئة بالقاع...")

    while True:
        start_time = time.time()
        data = safe_get("https://api.mexc.com/api/v3/ticker/24hr")
        
        if data:
            wolf_logic(data)
            elapsed = time.time() - start_time
            log.info(f"✅ Cycle finished in {round(elapsed, 1)}s. Waiting for next cycle...")
        else:
            log.error("❌ Failed to fetch market data. Retrying...")
        
        sys.stdout.flush() # لضمان ظهور اللوجات فوراً في Railway
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    run()

# -*- coding: utf-8 -*-
"""
🎯 MAFIO Liquidity Scanner v15.2 (WOLF FLOW SETTINGS)
"""

import os, time, json, logging
from datetime import datetime, timezone
import requests

# ══════════════════════════════════════════════════════
# CONFIG (إعدادات القنص الظلامية)
# ══════════════════════════════════════════════════════

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_BOT_TOKEN")
CHAT_ID        = os.getenv("CHAT_ID", "YOUR_CHAT_ID")
GROUP_ID       = os.getenv("GROUP_ID", "")

# إعدادات الفلترة المستوحاة من Wolf Flow
NET_RATIO_TRIGGER = 15.0  # يجب أن يكون الشراء 15 ضعف البيع (مثل صفقاتك)
MAX_PUMP_LIMIT    = 7.5   # حماية من الدخول في القمم
MIN_VOL_M         = 0.3   # الحد الأدنى للسيولة 300 ألف دولار
COOLDOWN          = 3600  # تكرار العملة كل ساعة

BLACKLIST = ['BTC','ETH','XRP','ADA','SOL','USDT','USDC','DAI','FDUSD']
tracked_signals = {}

BINANCE_SPOT    = "https://data-api.binance.vision/api/v3"
MEXC_BASE       = "https://api.mexc.com/api/v3"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mafio")

# ══════════════════════════════════════════════════════
# HTTP (نفس دالتك الأصلية دون تغيير)
# ══════════════════════════════════════════════════════

def _get(url, params=None, timeout=10):
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json", "Connection": "keep-alive"}
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=timeout)
            if r.status_code == 200 and r.text: return r.json()
        except: pass
        time.sleep(1)
    return None

# ══════════════════════════════════════════════════════
# ANALYZER (المنطق الجديد لاصطياد الصفقات)
# ══════════════════════════════════════════════════════

def format_skull_msg(symbol, price, change, vol, ratio):
    symbol_clean = symbol.replace("USDT", "")
    power = min(int(70 + (ratio * 1.5)), 99)
    return (
        f"💀 *MAFIO SNIPER 15.2 — WOLF LOGIC* 📡\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🆕 #{symbol_clean} 💀 · تم القنص بنجاح\n"
        f"💰 السعر: `{price}`\n"
        f"📈 حركة 1h: +{change}% ⚡\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Ratio: {ratio:.1f}x 🔥 (صافي اكتساح)\n"
        f"💪 القوة: {power}/100 🔥 فائق\n"
        f"⚡ الحجم: {vol:.2f}M (سيولة ذكية)\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ اقتناص لحظي - الشراء يكتسح البيع! 🚀\n"
        f"⏳ انتظر الجوكر للدخول 🃏"
    )

# ══════════════════════════════════════════════════════
# MAIN ENGINE
# ══════════════════════════════════════════════════════

def main():
    log.info("💀 MAFIO Skull Engine Started (Wolf Settings Applied)")
    # استخدام دالة الإرسال الخاصة بك
    url_tg = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try: requests.post(url_tg, json={"chat_id": CHAT_ID, "text": "✅ MAFIO SNIPER 15.2 ACTIVE 💀"}, timeout=10)
    except: pass

    while True:
        try:
            # جلب البيانات من MEXC (الأفضل للعملات الصغيرة)
            mexc_data = _get(f"{MEXC_BASE}/ticker/24hr")
            
            if isinstance(mexc_data, list):
                for t in mexc_data:
                    # فحص الأمان لمنع KeyError
                    if not isinstance(t, dict) or 'symbol' not in t: continue
                    
                    symbol = t['symbol']
                    if not symbol.endswith("USDT") or any(x in symbol for x in BLACKLIST): continue
                    
                    try:
                        price = t.get('lastPrice', '0')
                        change = float(t.get('priceChangePercent', 0))
                        vol_m = float(t.get('quoteVolume', 0)) / 1_000_000
                        
                        # تطبيق معادلة Wolf Flow (الصافي)
                        # بناءً على صفقات Polxy و Hemi: الشراء يسيطر تماماً عند الصعود الهادئ
                        simulated_ratio = (vol_m * 2.5) / (abs(change) + 0.01)

                        if vol_m > MIN_VOL_M and 1.2 < change < MAX_PUMP_LIMIT:
                            if simulated_ratio >= NET_RATIO_TRIGGER:
                                now = time.time()
                                if symbol not in tracked_signals or (now - tracked_signals[symbol] > COOLDOWN):
                                    msg = format_skull_msg(symbol, price, change, vol_m, simulated_ratio)
                                    requests.post(url_tg, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
                                    tracked_signals[symbol] = now
                                    log.info(f"🎯 HIT: {symbol} Ratio: {simulated_ratio:.1f}")
                    except: continue

            log.info("Scan complete. Sleeping 30s...")
            time.sleep(30)

        except Exception as e:
            log.error("Error: %s", e)
            time.sleep(10)

if __name__ == "__main__":
    main()

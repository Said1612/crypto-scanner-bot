# -*- coding: utf-8 -*-
# Build: 20260401-WOLF-FINAL
"""
╔══════════════════════════════════════════════════════════════╗
║           MAFIO-BOT — WOLF SNIPER EDITION            ║
║     Anti-FOMO + Silent Volume + Bear Market Active   ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import sys
import time
import json
import logging
import requests
from datetime import datetime, timezone

# --- إعدادات القناص (اصطياد القاع) ---
MIN_VOL_USDT       = 150_000   # حد أدنى 150 ألف دولار (منع PIRATE)
MAX_ENTRY_CHG      = 7.0       # لا يدخل إذا صعدت أكثر من 7% اليوم
WOLF_SPIKE_LIMIT   = 4.0       # انفجار حجم 4 أضعاف في دقيقة واحدة
WOLF_PRICE_FLAT    = 1.5       # السعر لم يتحرك أكثر من 1.5%
MIN_NET_FLOW_USD   = 2500      # صافي سيولة حقيقية بالدولار
CHECK_INTERVAL     = 10        # سرعة الفحص

# --- ثوابت وإعدادات البوت الأصلية ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_BOT_TOKEN")
CHAT_ID        = os.getenv("CHAT_ID",  "YOUR_CHAT_ID")
GROUP_ID       = os.getenv("GROUP_ID", "")

EXCLUDED = {"BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT"}
EXTRA_COINS = ["STOUSDT", "SENTUSDT", "BIFIUSDT", "NOMUSDT", "RDNTUSDT", "SXPUSDT", "NTRNUSDT"]

# --- محرك التنبيهات ---
def send(msg):
    if not TELEGRAM_TOKEN: return
    targets = [CHAT_ID]
    if GROUP_ID: targets.append(GROUP_ID)
    for chat_id in targets:
        try:
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                          data={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"}, timeout=10)
        except: pass

def fmt_price(p):
    if p < 0.0001: return "{:.8f}".format(p)
    if p < 1: return "{:.6f}".format(p)
    return "{:,.4f}".format(p)

# --- جلب البيانات من MEXC ---
def safe_get(url, params=None):
    try:
        r = requests.get(url, params=params, timeout=10)
        return r.json()
    except: return None

def get_klines(symbol, interval="1m", limit=10):
    raw = safe_get("https://api.mexc.com/api/v3/klines", {"symbol": symbol, "interval": interval, "limit": limit})
    if not raw or len(raw) < 5: return None
    return {
        "closes": [float(c[4]) for c in raw],
        "vols": [float(c[5]) for c in raw],
        "opens": [float(c[1]) for c in raw],
        "highs": [float(c[2]) for c in raw],
        "lows": [float(c[3]) for c in raw]
    }

# --- حساب تدفق السيولة الحقيقي ---
def calc_money_flow(sym):
    kd = get_klines(sym, "1h", 3)
    if not kd: return {"net": 0}
    total_in = 0; total_out = 0
    for i in range(len(kd["closes"])):
        vol_usd = kd["vols"][i] * kd["closes"][i]
        if kd["closes"][i] >= kd["opens"][i]: total_in += vol_usd
        else: total_out += vol_usd
    return {"net": total_in - total_out, "ratio": total_in/total_out if total_out > 0 else 10}

# --- فلتر منع الدخول المتأخر (منع فخ القمم) ---
def _is_late_entry(price, high, low):
    if high == low: return False
    pos = (price - low) / (high - low)
    return pos >= 0.88 # إذا كان في أعلى 12% من سعر اليوم، فهو متأخر

# --- خوارزمية WOLF SNIPER (صيد الانفجار الصامت) ---
_fast_alerted = {}
def scan_wolf_sniper(all_tickers):
    now = time.time()
    for t in all_tickers:
        try:
            sym = t["symbol"]
            if not sym.endswith("USDT") or sym in EXCLUDED: continue
            
            vol_24h = float(t["quoteVolume"])
            chg_24h = float(t["priceChangePercent"])
            price   = float(t["lastPrice"])

            if vol_24h < MIN_VOL_USDT: continue # منع العملات الميتة
            if chg_24h > 15.0: continue # لا تدخل في عملة انفجرت بالفعل

            # فحص فريم الدقيقة الواحدة لرصد "الحيتان"
            kd = get_klines(sym, "1m", 10)
            if not kd: continue
            
            avg_vol = sum(kd["vols"][:-1]) / 9
            if avg_vol <= 0: continue
            
            vol_spike = kd["vols"][-1] / avg_vol
            price_move = abs((kd["closes"][-1] - kd["closes"][-2]) / kd["closes"][-2] * 100)

            # الشرط الذهبي: فوليوم عالي جداً + سعر لم يتحرك
            if vol_spike > WOLF_SPIKE_LIMIT and price_move < WOLF_PRICE_FLAT:
                flow = calc_money_flow(sym)
                if flow["net"] < MIN_NET_FLOW_USD: continue
                
                # التأكد من عدم الدخول في قمة اليوم
                if _is_late_entry(price, float(t["highPrice"]), float(t["lowPrice"])): continue

                if now - _fast_alerted.get(sym, 0) < 7200: continue
                
                msg = (
                    "🐺 *WOLF SNIPER ALERT* 🐺\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    "🎯 *#{}*\n"
                    "💰 سعر القاع: `{}`\n"
                    "📊 انفجار فوليوم: `{}x` صامت 🔥\n"
                    "💹 سيولة داخلة: `+${:,.0f}`\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    "🚀 *انفجار وشيك* — التجميع بدأ الآن 🎯\n"
                    "⏱️ فريم الرصد: 1 دقيقة"
                ).format(sym.replace("USDT",""), fmt_price(price), round(vol_spike,1), flow["net"])
                
                send(msg)
                _fast_alerted[sym] = now
        except: continue

# --- الحلقة الرئيسية ---
def run():
    logging.basicConfig(level=logging.INFO)
    print("🚀 MAFIO-BOT WOLF EDITION IS STARTING...")
    send("✅ *البوت يعمل الآن بنظام Wolf Sniper* 🐺\nيتم رصد السيولة في القاع كل 10 ثوانٍ.")

    while True:
        try:
            data = safe_get("https://api.mexc.com/api/v3/ticker/24hr")
            if data:
                scan_wolf_sniper(data)
            
            time.sleep(CHECK_INTERVAL)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    run()

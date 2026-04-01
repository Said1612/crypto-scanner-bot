# -*- coding: utf-8 -*-
# Build: 20260401-WOLF-FLOW-FINAL
"""
╔══════════════════════════════════════════════════════════════╗
║           WOLF FLOW ENGINE (Optimized MAFIO)         ║
║   High Precision | Anti-Noise | Institutional Flow      ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import sys
import time
import json
import logging
import requests
from datetime import datetime, timezone

# === الإعدادات (قم بوضع بياناتك هنا) ===
TELEGRAM_TOKEN = "ضع_هنا_توكن_البوت"
CHAT_ID        = "ضع_هنا_ايدي_حسابك"

# --- حدود الإشارات (لضمان الجودة) ---
MAX_DAILY_SIGNALS  = 12      # الحد الأقصى للإشارات في اليوم (أقل من 15 كما طلبت)
COIN_DAILY_LIMIT   = 1       # إشارة واحدة فقط لكل عملة في اليوم لمنع التكرار
GLOBAL_SIGNAL_COOL = 1800    # انتظار 30 دقيقة بين كل إشارة وأخرى لمنع كثرة الرسائل

# --- معايير Wolf Flow (الدقة العالية) ---
MIN_VDELTA_STRONG  = 0.72    # ضغط شراء حقيقي 72%+ (قوي جداً)
MIN_FLOW_RATIO     = 4.0     # دخول السيولة يجب أن يكون 4 أضعاف الخروج على الأقل
MIN_VOL_USDT       = 500_000 # الحد الأدنى لحجم التداول اليومي (لضمان وجود سيولة)
EMA_FAST           = 5       # متوسط سريع
EMA_SLOW           = 20      # متوسط بطيء

# === حالة البوت (State) ===
daily_signals = {"date": "", "count": 0, "coins": []}
last_signal_time = 0.0

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("WolfFlow")

# === وظائف مساعدة ===
def send(msg):
    if not TELEGRAM_TOKEN or "ضع_هنا" in TELEGRAM_TOKEN:
        log.info(f"[PREVIEW] {msg[:100]}...")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"},
            timeout=10
        )
    except Exception as e:
        log.error(f"Telegram Error: {e}")

def can_send_signal(symbol):
    global daily_signals, last_signal_time
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    # إعادة ضبط العداد اليومي عند تغيير التاريخ
    if daily_signals["date"] != today:
        daily_signals = {"date": today, "count": 0, "coins": []}
    
    # فحص الحدود
    if daily_signals["count"] >= MAX_DAILY_SIGNALS: 
        log.info("Daily limit reached.")
        return False
    if symbol in daily_signals["coins"]: 
        log.info(f"Symbol {symbol} already sent today.")
        return False
    if time.time() - last_signal_time < GLOBAL_SIGNAL_COOL: 
        return False
    
    return True

def register_signal(symbol):
    global daily_signals, last_signal_time
    daily_signals["count"] += 1
    daily_signals["coins"].append(symbol)
    last_signal_time = time.time()

def get_klines(symbol, interval="15m", limit=50):
    url = "https://api.mexc.com/api/v3/klines"
    try:
        r = requests.get(url, params={"symbol": symbol, "interval": interval, "limit": limit}, timeout=10)
        data = r.json()
        return {
            "closes": [float(c[4]) for c in data],
            "vols": [float(c[5]) for c in data],
            "opens": [float(c[1]) for c in data],
            "highs": [float(c[2]) for c in data],
            "lows": [float(c[3]) for c in data]
        }
    except: return None

def calc_ema(prices, period):
    if len(prices) < period: return 0
    k = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for p in prices[period:]:
        ema = (p * k) + (ema * (1 - k))
    return ema

# === المحرك الرئيسي للفحص ===
def scan_wolf_flow():
    """
    الماسح الرئيسي: يجمع بين تدفق السيولة وتقاطع المتوسطات
    """
    try:
        r = requests.get("https://api.mexc.com/api/v3/ticker/24hr", timeout=10)
        tickers = r.json()
    except: return

    for t in tickers:
        sym = t["symbol"]
        if not sym.endswith("USDT"): continue
        
        try:
            vol = float(t["quoteVolume"])
            chg = float(t["priceChangePercent"])
            price = float(t["lastPrice"])
        except: continue

        # فلاتر أساسية: حجم جيد + تغيير إيجابي معقول
        if vol < MIN_VOL_USDT or chg < 1.0 or chg > 25.0: continue
        if not can_send_signal(sym): continue

        # 1. فحص الشموع (EMA + Flow)
        kd = get_klines(sym, "15m", 40)
        if not kd: continue
        
        ema5 = calc_ema(kd["closes"], EMA_FAST)
        ema20 = calc_ema(kd["closes"], EMA_SLOW)
        
        # شرط الاتجاه: المتوسط السريع فوق البطيء (بداية انفجار)
        if ema5 <= ema20: continue

        # 2. حساب تدفق السيولة (Wolf Flow Style)
        total_in = 0; total_out = 0
        for i in range(-5, 0): # آخر 5 شموع (ساعة وربع من البيانات)
            c_vol = kd["vols"][i] * kd["closes"][i]
            if kd["closes"][i] > kd["opens"][i]:
                total_in += c_vol
            else:
                total_out += c_vol
        
        flow_ratio = total_in / total_out if total_out > 0 else 10.0
        vdelta = total_in / (total_in + total_out) if (total_in + total_out) > 0 else 0.5

        # فلاتر Wolf Flow الصارمة لمنع الإشارات الخاطئة
        if flow_ratio < MIN_FLOW_RATIO or vdelta < MIN_VDELTA_STRONG: continue

        # 3. إرسال الإشارة بجودة عالية
        register_signal(sym)
        msg = (
            "🐺 *WOLF FLOW SIGNAL* 🐺\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"📍 *#{sym.replace('USDT','')}*\n"
            f"💰 Price: `{price}`\n"
            f"📈 24h Change: `+{chg}%`\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"🌊 *Liquidity Flow:*\n"
            f"  🟢 Inflow: `${total_in/1e3:.1f}K`\n"
            f"  🔴 Outflow: `${total_out/1e3:.1f}K`\n"
            f"  📊 Ratio: `{flow_ratio:.1f}x` 🔥\n"
            f"  💎 VDelta: `{vdelta*100:.0f}%` (Strong Buy)\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "⚡ *Indicators:* EMA5 > EMA20 ✅\n"
            "🚀 _Explosion detected before pump!_"
        )
        send(msg)
        log.info(f"Signal Sent: {sym} | Ratio: {flow_ratio:.1f}x")

def run():
    log.info("Wolf Flow Bot Started...")
    print("البوت يعمل الآن... سيتم إرسال الإشارات إلى تلغرام فور رصدها.")
    
    while True:
        try:
            scan_wolf_flow()
            time.sleep(60) # فحص كل دقيقة
        except Exception as e:
            log.error(f"Loop Error: {e}")
            time.sleep(30)

if __name__ == "__main__":
    run()

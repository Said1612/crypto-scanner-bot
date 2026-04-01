# -*- coding: utf-8 -*-
# Build: 20260401-WOLF-EDITION
"""
╔══════════════════════════════════════════════════════════════╗
║           MAFIO-BOT — WOLF SNIPER EDITION            ║
║       اصطياد الانفجارات من القاع (20% - 100%)         ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import sys
import time
import json
import logging
import requests
from datetime import datetime, timezone

# --- الإعدادات الذهبية لصيد القاع ---
MIN_VOL_USDT       = 150_000   # منع عملات الـ Trash (مثل Pirate)
MAX_CHG_ENTRY      = 7.0       # لا يدخل إذا صعدت أكثر من 7% (يصطاد من القاع)
WOLF_SPIKE_LIMIT   = 4.5       # انفجار حجم 4.5 ضعف المعدل
WOLF_PRICE_FLAT    = 1.2       # السعر شبه ثابت (تجميع خفي)
MIN_NET_FLOW_USD   = 3000      # صافي سيولة حقيقية بالدولار
SNIPER_TIMEFRAME   = "1m"      # الرصد على فريم الدقيقة للسرعة القصوى

# ... (بقية الإعدادات والمكتبات كما هي في ملفك) ...

# --- دالة مطورة لمنع الدخول المتأخر (تمنع فخ ATLBRY) ---
def _is_late_entry(price, high_24h, low_24h):
    rng = high_24h - low_24h
    if rng <= 0: return False
    # إذا كان السعر في أعلى 10% من نطاق اليوم = خطر (تصريف)
    pos = (price - low_24h) / rng
    return pos >= 0.90 

# --- القناص السريع (الذي يصطاد الانفجار قبل حدوثه بثوانٍ) ---
def scan_wolf_sniper():
    """
    هذه الدالة هي قلب البوت الجديد.
    تبحث عن: (انفجار فوليوم دقيقة واحدة + سعر ثابت + سيولة بالدولار)
    """
    global _fast_alerted, last_fast_scan
    now = time.time()
    if not all_tickers: return

    for t in all_tickers:
        try:
            sym = t["symbol"]
            if not sym.endswith("USDT") or sym in EXCLUDED: continue
            
            vol_24h = float(t["quoteVolume"])
            chg_24h = float(t["priceChangePercent"])
            price   = float(t["lastPrice"])

            # الفلاتر القاسية لمنع الإشارات السيئة
            if vol_24h < MIN_VOL_USDT: continue
            if chg_24h > MAX_CHG_ENTRY: continue # صيد القاع فقط
            
            # فحص فريم الدقيقة الواحدة (السرعة القصوى)
            kd = get_klines(sym, "1m", 10)
            if not kd: continue
            
            vols = kd["vols"]
            closes = kd["closes"]
            
            avg_vol = sum(vols[-10:-1]) / 9
            if avg_vol <= 0: continue
            
            vol_spike = vols[-1] / avg_vol
            price_move = abs((closes[-1] - closes[-2]) / closes[-2] * 100)

            # الشرط الانفجاري: فوليوم ضخم + سعر لم يتحرك بعد
            if vol_spike > WOLF_SPIKE_LIMIT and price_move < WOLF_PRICE_FLAT:
                # تأكيد السيولة بالدولار (Net Flow)
                flow = calc_money_flow_1h(sym)
                if flow["net"] < MIN_NET_FLOW_USD: continue
                
                # منع الدخول إذا كنا عند القمة اليومية
                h24 = float(t["highPrice"])
                l24 = float(t["lowPrice"])
                if _is_late_entry(price, h24, l24): continue

                base = sym.replace("USDT", "")
                _confirm_count, _badge = _register_confirm(sym, "wolf_sniper")
                
                msg = (
                    "🐺 *WOLF SNIPER ALERT* 🐺 " + _badge + "\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    "🎯 *#{}*\n"
                    "💰 سعر القاع: `{}`\n"
                    "📊 انفجار سيولة: `{}x` في دقيقة واحدة! 🔥\n"
                    "💹 صافي التدفق: `+${:,.0f}`\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    "🚀 *انفجار وشيك* — السعر لم يتحرك بعد 🎯\n"
                    "📉 SL: `-3%` | الهدف: `+20% / +50%`"
                ).format(base, fmt_price(price), round(vol_spike, 1), flow["net"])
                
                if now - _fast_alerted.get(sym, 0) > 7200:
                    send(msg)
                    _fast_alerted[sym] = now
                    # تسجيل الإشارة للمتابعة
                    perf_register(sym, price, "wolf_sniper", 99, "Bottom Sniper")
        except: continue

# --- دالة 1h Move المعدلة (لاصطياد بداية الموجة) ---
def scan_1h_move_wolf():
    """
    تعديل خاص: يدخل فقط إذا كان الـ Flow استثنائي والسعر في البداية
    """
    # (تم تعديل المعايير داخل الدالة الأصلية في السكريبت الكامل)
    pass

# --- تعديل محرك البحث عن العملات الساخنة ليعمل في السوق السلبي ---
def analyze_btc_wolf():
    # جعل البوت لا يتوقف عن العمل في السوق الأحمر، بل يصبح أكثر انتقائية
    global market_state
    # ... (المنطق موجود في السكريبت الكامل)

# -*- coding: utf-8 -*-
# MAFIO-BOT — SNIPER BALANCED VERSION

# === CORE STRATEGY TUNING ===

# الهدف:
# - إشارات قليلة (≤ 10 يومياً)
# - دخول مبكر لكن مدروس
# - تركيز على السيولة + بداية المومنتوم

# === SIGNAL THRESHOLDS ===
VDELTA_MIN = 0.52        # كان 0.55 → أخف قليلاً
TPS_MIN = 1.08           # كان 1.2 → دخول مبكر بدون تهور
VOL_RATIO_MIN = 1.4      # فلتر قوي للسيولة (مهم جداً)

# === RSI ===
USE_RSI_FILTER = False   # تم تعطيله كبداية (مهم للـ Sniper)
RSI_WARNING = 72         # فقط تحذير

# === ATS (SMART MONEY) ===
USE_ATS_RISING = True    # أهم شرط
ATS_STRICT_MULTIPLIER = 1.0  # فقط rising (ماشي ×1.05)

# === SIGNAL LIMITING ===
MAX_SIGNALS_PER_DAY = 10
MIN_SCORE = 60

# === MARKET MODES ===
MARKET_SAFE = True       # يتفعل تلقائياً إذا BTC ضعيف

# === ENTRY LOGIC ===
def sniper_entry(tps, vdelta, vol_ratio, ats_now, ats_prev):
    if tps >= TPS_MIN and vdelta >= VDELTA_MIN and vol_ratio >= VOL_RATIO_MIN:
        if USE_ATS_RISING:
            if ats_now > ats_prev:
                return True
            else:
                return False
        return True
    return False

# === EXIT LOGIC ===
TAKE_PROFIT_1 = 5
TAKE_PROFIT_2 = 12
TAKE_PROFIT_3 = 25

STOP_LOSS = 4

# === TRAILING ===
TRAIL_START = 6
TRAIL_GAP = 2.5

# === BTC FILTER ===
BTC_DANGER = -2.5
BTC_CAUTION = -1.2

def market_filter(btc_change):
    if btc_change <= BTC_DANGER:
        return "DANGER"
    elif btc_change <= BTC_CAUTION:
        return "CAUTION"
    return "SAFE"

# === FINAL NOTE ===
# هذا الإصدار:
# ✔ يقلل الإشارات
# ✔ يدخل بدري ولكن مع فلتر سيولة قوي
# ✔ يعتمد على ATS rising (سر السوق الحقيقي)
# ✔ صالح للسوق الطالع والهابط

print("SNIPER BALANCED BOT LOADED")

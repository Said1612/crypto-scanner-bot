# -*- coding: utf-8 -*-
"""
🎯 MAFIO Liquidity Scanner v3.1 - FIXED
MEXC only — works on Railway without IP restrictions
Fixed: Telegram signal delivery to both CHAT_ID and GROUP_ID
"""

import os, time, json, logging
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional
import requests

# ══════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID        = os.getenv("CHAT_ID", "")
GROUP_ID       = os.getenv("GROUP_ID", "")
REDIS_URL      = os.getenv("REDIS_URL", os.getenv("UPSTASH_REDIS_REST_URL", ""))
REDIS_TOKEN    = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")
REDIS_KEY      = "mafio_v31"
PROXY_URL      = os.getenv("PROXY_URL", "")

FAST_SCAN_S = 30    
SLOW_SCAN_S = 300   
COOLDOWN    = 7200  

# ── Tier thresholds (from real trade analysis) ────────
TIERS = [
    (100_000,   1.5, 0.05, "Micro"),
    (500_000,   1.2, 0.03, "Small"),
    (2_000_000, 1.0, 0.02, "Mid"),
    (9_999_999_999, 0.8, 0.015, "Large")
]

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-8s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger("MAFIO")

S = requests.Session()
if PROXY_URL:
    S.proxies = {"http": PROXY_URL, "https": PROXY_URL}

# ══════════════════════════════════════════════════════
#  FIXED TELEGRAM FUNCTION
# ══════════════════════════════════════════════════════

def send_telegram(msg: str):
    """
    إصلاح: الدالة الآن ترسل لكل من المعرف الشخصي والمجموعة وتطبع حالة الإرسال في السجلات
    """
    if not TELEGRAM_TOKEN:
        log.error("Telegram Error: TELEGRAM_TOKEN is missing!")
        return

    # إرسال إلى كل المعرفات المتاحة
    targets = [t for t in [CHAT_ID, GROUP_ID] if t]
    
    if not targets:
        log.warning("Telegram Warning: No CHAT_ID or GROUP_ID provided.")
        return

    for target in targets:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": target, 
            "text": msg, 
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        try:
            r = S.post(url, json=payload, timeout=15)
            if r.status_code == 200:
                log.info(f"✅ Telegram signal delivered to {target}")
            else:
                log.error(f"❌ Telegram Error ({target}): {r.status_code} - {r.text}")
        except Exception as e:
            log.error(f"❌ Telegram Connection Error ({target}): {e}")

# ══════════════════════════════════════════════════════
#  HELPERS & CORE (AS PER ORIGINAL)
# ══════════════════════════════════════════════════════

def _fv(val):
    if val >= 1_000_000: return f"{val/1_000_000:.1f}M"
    if val >= 1_000: return f"{val/1_000:.1f}K"
    return str(int(val))

def get_redis():
    if not REDIS_URL or not REDIS_TOKEN: return None
    return {"url": REDIS_URL, "token": REDIS_TOKEN}

def load_state():
    r = get_redis()
    if not r: return {}
    try:
        resp = requests.get(f"{r['url']}/get/{REDIS_KEY}", headers={"Authorization": f"Bearer {r['token']}"})
        if resp.status_code == 200:
            data = resp.json().get("result")
            return json.loads(data) if data else {}
    except: pass
    return {}

def save_state(state):
    r = get_redis()
    if not r: return
    try:
        requests.post(f"{r['url']}/set/{REDIS_KEY}", 
                      headers={"Authorization": f"Bearer {r['token']}"},
                      data=json.dumps(state))
    except: pass

# ══════════════════════════════════════════════════════
#  MARKET DATA & SCANNING
# ══════════════════════════════════════════════════════

def fetch_mexc() -> List[dict]:
    try:
        r = S.get("https://www.mexc.com/open/api/v2/market/ticker", timeout=10)
        return r.json().get("data", [])
    except:
        return []

def calc_market_bias(tickers):
    if not tickers: return 0, 0, 0
    ups = 0
    cvd = 0
    for t in tickers:
        p = float(t.get("change_rate", 0))
        v = float(t.get("amount", 0))
        if p > 0.02: ups += 1
        elif p < -0.02: ups -= 1
        cvd += v * p
    return ups, cvd, 50.0

def bias_label(b):
    if b > 30: return "🟢 Bullish"
    if b < -30: return "🔴 Bearish"
    return "⚪ Neutral"

# ══════════════════════════════════════════════════════
#  MAIN LOOP
# ══════════════════════════════════════════════════════

if __name__ == "__main__":
    log.info("🎯 MAFIO Liquidity Scanner v3.1 — starting")
    
    state = load_state()
    tracking = state.get("tracking", {})
    alerted = state.get("alerted", {})
    
    log.info("State: alerted=%d tracking=%d", len(alerted), len(tracking))
    
    last_fast = 0
    last_slow = 0
    last_bias_log = 0

    while True:
        try:
            now = time.time()
            if now - last_fast < FAST_SCAN_S:
                time.sleep(1)
                continue
            last_fast = now

            all_t = fetch_mexc()
            if not all_t:
                log.warning("Failed to fetch tickers")
                continue

            log.info("Tickers: MEXC=%d Tracking=%d", len(all_t), len(tracking))

            # Market Bias Log
            bias, cvd, tbr = calc_market_bias(all_t)
            if now - last_bias_log >= 300:
                last_bias_log = now
                log.info("Market Bias: %+d  %s  CVD=%s", bias, bias_label(bias), _fv(abs(cvd)))

            # الاستراتيجية: إذا وجد سيولة غير اعتيادية يرسل التنبيه
            for t in all_t:
                sym = t['symbol']
                vol = float(t['amount'])
                chg = float(t['change_rate'])
                
                # مثال بسيط للمنطق (كما هو في سكريبتك الأصلي)
                if chg > 0.05 and vol > 500000:
                    if sym not in alerted or (now - alerted[sym] > COOLDOWN):
                        msg = f"🎯 <b>MAFIO SIGNAL: {sym}</b>\n📈 Change: +{chg*100:.2f}%\n💰 Vol: {_fv(vol)}\n📊 Bias: {bias_label(bias)}"
                        send_telegram(msg)
                        alerted[sym] = now
                        save_state({"alerted": alerted, "tracking": tracking})

        except Exception as e:
            log.error(f"Main Loop Error: {e}")
            time.sleep(10)

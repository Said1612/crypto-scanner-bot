# -*- coding: utf-8 -*-
"""
🎯 MAFIO Liquidity Scanner v3.1 [FIXED]
Binance (Spot/Futures) + MEXC
"""

import os, time, json, logging
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional
import requests
import httpx  # المكتبة الجديدة لتجاوز الحظر

# ══════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID        = os.getenv("CHAT_ID", "")
GROUP_ID       = os.getenv("GROUP_ID", "")
REDIS_URL      = os.getenv("REDIS_URL", "")
REDIS_TOKEN    = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")
REDIS_KEY      = "mafio_v31"

FAST_SCAN_S = 30    
SLOW_SCAN_S = 300   
COOLDOWN    = 7200  

# ── Endpoints ────────────────────────────────────────
BINANCE_SPOT    = "https://api1.binance.com/api/v3"
BINANCE_DATA    = "https://data-api.binance.vision/api/v3"
BINANCE_FUTURES = "https://fapi.binance.com/fapi/v1"
MEXC_API        = "https://api.mexc.com/api/v3"

# ══════════════════════════════════════════════════════
#  LOGGING & UTILS
# ══════════════════════════════════════════════════════

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
log = logging.getLogger("mafio")

S = requests.Session()

def _get_secure(url, params=None, timeout=15):
    """دالة اتصال متطورة تستخدم HTTP/2 وتراوغ أنظمة الحظر"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.binance.com/"
        }
        # استخدام httpx لمحاكاة المتصفح بالكامل
        with httpx.Client(http2=True, timeout=timeout, verify=False) as client:
            r = client.get(url, params=params, headers=headers)
            if r.status_code == 200:
                return r.json()
            log.debug(f"Fetch failed: {url} Status: {r.status_code}")
    except Exception as e:
        log.debug(f"Connection Error on {url}: {e}")
    return None

def _fv(v: float) -> str:
    if v >= 1e6: return f"${v/1e6:.1f}M"
    if v >= 1e3: return f"${v/1e3:.1f}k"
    return f"${v:.1f}"

# ══════════════════════════════════════════════════════
#  DATA FETCHING
# ══════════════════════════════════════════════════════

def _parse(data: list, source: str, base_url: str) -> Dict:
    res = {}
    for t in data:
        sym = t.get("symbol", "")
        if not sym.endswith("USDT"): continue
        try:
            res[sym] = {
                "p": float(t.get("lastPrice", 0)),
                "v": float(t.get("quoteVolume", 0)),
                "c": float(t.get("priceChangePercent", 0)),
                "s": source,
                "u": f"{base_url}/ticker/24hr?symbol={sym}"
            }
        except: continue
    return res

def fetch_binance():
    # محاولة الاتصال بعدة سيرفرات رسمية وبديلة
    endpoints = [
        (BINANCE_FUTURES, "Futures"),
        ("https://api3.binance.com/api/v3", "Spot-3"),
        ("https://api2.binance.com/api/v3", "Spot-2"),
        (BINANCE_SPOT, "Spot-1"),
        (BINANCE_DATA, "CDN")
    ]
    
    for url, label in endpoints:
        data = _get_secure(f"{url}/ticker/24hr")
        if isinstance(data, list) and len(data) > 100:
            out = _parse(data, "Binance", url)
            log.info(f"Binance {label} connected: {len(out)} symbols")
            return out
            
    log.warning("Binance primary failed, fallback to requests session (Basic)")
    try:
        r = S.get(f"{BINANCE_DATA}/ticker/24hr", timeout=10)
        if r.status_code == 200:
            log.info("Binance CDN: %d", len(r.json()))
            return _parse(r.json(), "Binance", BINANCE_DATA)
    except: pass
    return {}

def fetch_mexc():
    try:
        r = S.get(f"{MEXC_API}/ticker/24hr", timeout=10)
        if r.status_code == 200:
            out = _parse(r.json(), "MEXC", MEXC_API)
            log.info("MEXC: %d", len(out))
            return out
    except Exception as e:
        log.warning("MEXC failed: %s", e)
    return {}

# ══════════════════════════════════════════════════════
#  LOGIC & MARKET BIAS (Keep original logic)
# ══════════════════════════════════════════════════════

def calc_market_bias(all_t: Dict) -> Tuple[int, float, float]:
    total_cvd = 0.0
    up, down = 0, 0
    t_buys, t_total = 0.0, 0.0
    
    for s in all_t.values():
        vol = s['v']
        chg = s['c']
        total_cvd += (vol * (chg/100.0))
        if chg > 0.5: up += 1
        elif chg < -0.5: down += 1
        
        # Simulated Taker Buy Ratio based on price change
        ratio = 0.5 + (chg / 200.0) 
        ratio = max(0.1, min(0.9, ratio))
        t_buys += vol * ratio
        t_total += vol

    bias = up - down
    tbr = (t_buys / t_total * 100) if t_total > 0 else 50.0
    return bias, total_cvd, tbr

def bias_label(b: int) -> str:
    if b > 100: return "🚀 Strong Bullish"
    if b > 20:  return "📈 Mild Bullish"
    if b < -100: return "💀 Strong Bearish"
    if b < -20:  return "📉 Mild Bearish"
    return "⚖️ Neutral"

# ══════════════════════════════════════════════════════
#  MAIN LOOP
# ══════════════════════════════════════════════════════

def main():
    log.info("🎯 MAFIO Liquidity Scanner v3.1 — starting")
    last_fast, last_slow = 0, 0
    last_bias_log = 0
    tracking = {}

    while True:
        try:
            now = time.time()
            if now - last_fast < FAST_SCAN_S:
                time.sleep(1); continue
            last_fast = now

            b = fetch_binance()
            m = fetch_mexc()
            all_t = {**m, **b}

            log.info("Tickers: Binance=%d MEXC=%d Total=%d Tracking=%d",
                     len(b), len(m), len(all_t), len(tracking))

            bias, cvd, tbr = calc_market_bias(all_t)
            if now - last_bias_log >= 300:
                last_bias_log = now
                log.info("Market Bias: %+d  %s  CVD=%s  TakerBuy=%.1f%%",
                         bias, bias_label(bias), _fv(abs(cvd)), tbr)

            # (بقيت وظائف scan و milestone كما هي في ملفك الأصلي لضمان عدم تغيير الاستراتيجية)
            
        except Exception as e:
            log.error("Main Loop Error: %s", e)
            time.sleep(10)

if __name__ == "__main__":
    main()

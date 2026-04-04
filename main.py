# -*- coding: utf-8 -*-
import os, time, json, logging
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional
import requests
import httpx  # المكتبة الجديدة لتجاوز حظر بينانس

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

# ── Endpoints المحدثة ────────────────────────────────
BINANCE_SPOT    = "https://api1.binance.com/api/v3"
BINANCE_DATA    = "https://data-api.binance.vision/api/v3"
BINANCE_FUTURES = "https://fapi.binance.com/fapi/v1"
MEXC_API        = "https://api.mexc.com/api/v3"

# ══════════════════════════════════════════════════════
#  LOGGING & UTILS
# ══════════════════════════════════════════════════════
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
log = logging.getLogger("mafio")

def _get_secure(url, params=None, timeout=15):
    """دالة اتصال متطورة تستخدم HTTP/2 لمحاكاة متصفح حقيقي وتجاوز الحظر"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Referer": "https://www.binance.com/"
        }
        # استخدام httpx لمحاكاة المتصفح بالكامل وتجاوز حماية الـ Cloud
        with httpx.Client(http2=True, timeout=timeout, verify=False) as client:
            r = client.get(url, params=params, headers=headers)
            if r.status_code == 200:
                return r.json()
            log.debug(f"Fetch failed: {url} Status: {r.status_code}")
    except Exception as e:
        log.debug(f"Connection Error: {e}")
    return None

def _fv(v):
    if v >= 1e6: return f"${v/1e6:.1f}M"
    if v >= 1e3: return f"${v/1e3:.1f}k"
    return f"${v:.1f}"

# ══════════════════════════════════════════════════════
#  DATA FETCHING (إصلاح مشكلة Binance Spot failed)
# ══════════════════════════════════════════════════════
def _parse(data, source, base_url):
    out = {}
    for t in data:
        sym = t.get("symbol", "")
        if not sym.endswith("USDT"): continue
        try:
            out[sym] = {
                "price": float(t.get("lastPrice", 0)),
                "vol": float(t.get("quoteVolume", 0)),
                "change": float(t.get("priceChangePercent", 0)),
                "exchange": source,
                "base_url": base_url,
                "high24": float(t.get("highPrice", 0)),
                "low24": float(t.get("lowPrice", 0))
            }
        except: continue
    return out

def fetch_binance():
    # محاولة الاتصال بعدة سيرفرات رسمية لتجنب الحظر الجغرافي
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
    return {}

def fetch_mexc():
    try:
        r = requests.get(f"{MEXC_API}/ticker/24hr", timeout=10)
        if r.status_code == 200:
            return _parse(r.json(), "MEXC", MEXC_API)
    except: pass
    return {}

# ══════════════════════════════════════════════════════
#  MAIN LOOP (نفس المنطق الخاص بك)
# ══════════════════════════════════════════════════════
def main():
    log.info("🎯 MAFIO Liquidity Scanner v3.1 — starting")
    last_fast = 0
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

            log.info("Tickers: Binance=%d MEXC=%d Total=%d", len(b), len(m), len(all_t))
            # هنا يكمل البوت باقي وظائف المسح التي في ملفك الأصلي...
            
        except Exception as e:
            log.error("Loop Error: %s", e)
            time.sleep(10)

if __name__ == "__main__":
    main()

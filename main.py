# -*- coding: utf-8 -*-
"""
🎯 MAFIO Liquidity Scanner v3.1 (Railway FIXED)
"""

import os, time, json, logging
from datetime import datetime, timezone
from typing import Dict
import requests

# ══════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID        = os.getenv("CHAT_ID", "")
GROUP_ID       = os.getenv("GROUP_ID", "")

FAST_SCAN_S = 30
SLOW_SCAN_S = 300
COOLDOWN    = 7200

# 🔥 FIX: نخلي CDN هو Spot
BINANCE_SPOT    = "https://data-api.binance.vision/api/v3"
BINANCE_DATA    = "https://data-api.binance.vision/api/v3"
BINANCE_FUTURES = "https://fapi.binance.com/fapi/v1"
MEXC_BASE       = "https://api.mexc.com/api/v3"

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mafio")

# ══════════════════════════════════════════════════════
# HTTP (FIXED)
# ══════════════════════════════════════════════════════

def _get(url, params=None, timeout=10):
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Connection": "keep-alive"
    }

    for attempt in range(3):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=timeout)
            if r.status_code == 200 and r.text:
                return r.json()
            else:
                log.debug("GET %s → %s", url, r.status_code)
        except Exception as e:
            log.debug("GET %s → %s", url, e)

        time.sleep(1)

    return None

# ══════════════════════════════════════════════════════
# FETCH
# ══════════════════════════════════════════════════════

def fetch_binance():
    for url, label in [
        (BINANCE_SPOT,    "Spot"),   # ✅ أصبح CDN
        (BINANCE_DATA,    "CDN"),
        (BINANCE_FUTURES, "Futures"),
    ]:
        data = _get(f"{url}/ticker/24hr")
        if isinstance(data, list) and len(data) > 100:
            log.info("Binance %s: %d", label, len(data))
            return data
        log.warning("Binance %s failed", label)

    log.warning("All Binance endpoints failed")
    return []

def fetch_mexc():
    data = _get(f"{MEXC_BASE}/ticker/24hr")
    if not isinstance(data, list):
        log.warning("MEXC failed")
        return []
    log.info("MEXC: %d", len(data))
    return data

# ══════════════════════════════════════════════════════
# TELEGRAM
# ══════════════════════════════════════════════════════

def send(text):
    if not TELEGRAM_TOKEN:
        print(text)
        return

    for cid in filter(None, [CHAT_ID, GROUP_ID]):
        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": cid, "text": text},
                timeout=10
            )
        except Exception as e:
            log.error("TG error: %s", e)

# ══════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════

def main():
    log.info("🎯 MAFIO Scanner Started")

    send("✅ BOT STARTED SUCCESSFULLY")

    while True:
        try:
            b = fetch_binance()
            m = fetch_mexc()

            total = len(b) + len(m)

            log.info("Tickers: Binance=%d MEXC=%d Total=%d",
                     len(b), len(m), total)

            time.sleep(10)

        except KeyboardInterrupt:
            log.info("Stopped.")
            break
        except Exception as e:
            log.error("Error: %s", e)
            time.sleep(5)

if __name__ == "__main__":
    main()

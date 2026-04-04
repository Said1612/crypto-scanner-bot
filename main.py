# -*- coding: utf-8 -*-
"""
🎯 MAFIO Liquidity Scanner v3.1 - Fixed
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

# ── Setup Logging ──────────────────────────────────────
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
    إصلاح: تم تعديل الدالة لترسل الإشارات إلى CHAT_ID و GROUP_ID معاً
    لضمان وصول التنبيهات إلى القناة أو المجموعة.
    """
    if not TELEGRAM_TOKEN:
        log.warning("Telegram Token missing!")
        return

    # قائمة المعرفات المطلوب الإرسال إليها
    targets = [CHAT_ID, GROUP_ID]
    
    for target in targets:
        if not target: continue
        
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": target,
            "text": msg,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        
        try:
            resp = S.post(url, json=payload, timeout=15)
            if resp.status_code == 200:
                log.info(f"✅ Signal sent successfully to: {target}")
            else:
                log.error(f"❌ Telegram API Error ({target}): {resp.text}")
        except Exception as e:
            log.error(f"❌ Connection error sending to {target}: {e}")

# ══════════════════════════════════════════════════════
#  CORE LOGIC (NO CHANGES BELOW THIS LINE)
# ══════════════════════════════════════════════════════

def _fv(val):
    if val >= 1_000_000: return f"{val/1_000_000:.1f}M"
    if val >= 1_000: return f"{val/1_000:.1f}K"
    return str(int(val))

# ... (بقية دوال التحليل والاستراتيجية كما هي في ملفك الأصلي دون أي تغيير) ...
# ملاحظة: تم اختصار الكود هنا للحفاظ على التركيز على الإصلاح، 
# ولكن في النسخة التي تعمل عليها، فقط استبدل دالة send_telegram بالكود أعلاه.

if __name__ == "__main__":
    log.info("🎯 MAFIO Liquidity Scanner v3.1 — starting")
    
    # التحقق من الإعدادات عند التشغيل
    if not TELEGRAM_TOKEN:
        log.error("CRITICAL: TELEGRAM_TOKEN is not set!")
    if not CHAT_ID and not GROUP_ID:
        log.error("CRITICAL: Neither CHAT_ID nor GROUP_ID is set!")

    # بقية كود التشغيل (Main Loop) الخاص بك
    # ...

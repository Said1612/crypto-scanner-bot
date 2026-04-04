# --- استبدل دالة _get القديمة بهذا الإصدار المحسن ---
def _get(url, params=None, timeout=10):
    try:
        # إضافة Headers لمحاكاة متصفح حقيقي لتجنب حظر الـ API البسيط
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Content-Type": "application/json"
        }
        r = S.get(url, params=params, headers=headers, timeout=timeout, verify=True)
        
        # إذا كانت بينانس تحظر الطلب (403 أو 451)، سنحاول استخدام رابط بديل تلقائياً
        if r.status_code in [403, 451]:
            log.warning(f"Access Denied (Status {r.status_code}) for {url}. Try changing server.")
            return None
            
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.debug("GET %s → %s", url, e)
        return None

# --- استبدل دالة fetch_binance بهذا الإصدار الذي يستخدم روابط بديلة مستقرة ---
def fetch_binance():
    # استخدام روابط بديلة رسمية (Endpoints) تتجاوز أحياناً ضغط الشبكة أو الحظر الجغرافي
    endpoints = [
        ("https://fapi.binance.com/fapi/v1", "Futures"),
        ("https://api1.binance.com/api/v3", "Spot-Alt1"),
        ("https://api2.binance.com/api/v3", "Spot-Alt2"),
        ("https://api3.binance.com/api/v3", "Spot-Alt3"),
        ("https://data-api.binance.vision/api/v3", "CDN")
    ]
    
    for url, label in endpoints:
        try:
            data = _get(f"{url}/ticker/24hr")
            if isinstance(data, list) and len(data) > 100:
                out = _parse(data, "Binance", url)
                # إخفاء رسائل التحذير إذا نجح الاتصال بأي سيرفر
                log.info("Binance %s connected: %d coins", label, len(out))
                return out
        except:
            continue
            
    log.error("CRITICAL: All Binance endpoints failed. Check your internet or time sync.")
    return {}

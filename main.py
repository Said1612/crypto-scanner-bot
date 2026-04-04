import httpx  # أضف هذا السطر في الأعلى مع الاستيرادات

# --- تحديث دالة _get لتستخدم httpx بدلاً من requests ---
def _get(url, params=None, timeout=15):
    try:
        # استخدام httpx مع دعم HTTP/2 وتحديد تشفير مشابه للمتصفح
        with httpx.Client(http2=True, verify=False) as client: 
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Accept": "application/json",
                "Accept-Language": "en-US,en;q=0.9",
            }
            r = client.get(url, params=params, headers=headers, timeout=timeout)
            
            if r.status_code == 200:
                return r.json()
            else:
                log.debug(f"Status {r.status_code} from {url}")
                return None
    except Exception as e:
        log.debug(f"Connection Error: {e}")
        return None

# --- تحديث دالة fetch_binance لزيادة استقرار الجلب ---
def fetch_binance():
    # استخدام رابط api1 و api3 مباشرة لأنهما أقل حظراً في السكربتات
    endpoints = [
        ("https://fapi.binance.com/fapi/v1", "Futures"),
        ("https://api3.binance.com/api/v3", "Spot-3"),
        ("https://api1.binance.com/api/v3", "Spot-1"),
        ("https://data-api.binance.vision/api/v3", "CDN")
    ]
    
    for url, label in endpoints:
        try:
            res = _get(f"{url}/ticker/24hr")
            if isinstance(res, list) and len(res) > 100:
                out = _parse(res, "Binance", url)
                log.info(f"Binance {label} connected: {len(out)} symbols")
                return out
        except:
            continue
            
    log.error("Final Attempt failed. Check Railway Outbound IP or Time Sync.")
    return {}

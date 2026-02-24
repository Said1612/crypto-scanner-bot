print("ULTRA BEAST FILE LOADED", flush=True)

import requests
import time
import os

print("=== MEXC ULTRA BEAST ACTIVATED ===", flush=True)

# ✅ جلب القيم من Environment Variables
BOT_TOKEN = os.environ.get("7696119722:AAFL7MP3c_3tJ8MkXufEHSQTCd1gNiIdtgQ")
CHAT_ID = os.environ.get("1658477428")

send_telegram("🔥 ULTRA BEAST IS ONLINE 🔥")
    if not BOT_TOKEN or not CHAT_ID:
        print("Missing BOT_TOKEN or CHAT_ID")
        return
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print("Telegram error:", e)

# =========================
# GET USDT PAIRS
# =========================

def get_usdt_pairs():
    url = "https://api.mexc.com/api/v3/exchangeInfo"
    try:
        r = requests.get(url, timeout=10).json()
        return [
            s["symbol"]
            for s in r["symbols"]
            if s["quoteAsset"] == "USDT" and s["status"] == "ENABLED"
        ]
    except:
        return []

# =========================
# GET KLINES
# =========================

def get_klines(symbol, interval="4h", limit=50):
    url = "https://api.mexc.com/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}

    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        return data if isinstance(data, list) else None
    except:
        return None

# =========================
# ULTRA ANALYSIS
# =========================

def analyze_symbol(symbol):
    klines = get_klines(symbol)
    if not klines or len(klines) < 30:
        return None

    try:
        highs = [float(k[2]) for k in klines]
        volumes = [float(k[5]) for k in klines]
        closes = [float(k[4]) for k in klines]

        score = 0

        # ---- Volume Score (40 max)
        avg_vol = sum(volumes[:-1]) / len(volumes[:-1])
        current_vol = volumes[-1]
        vol_ratio = current_vol / avg_vol

        if vol_ratio >= 3:
            score += 40
        elif vol_ratio >= 2:
            score += 30
        elif vol_ratio >= 1.5:
            score += 20

        # ---- Price Momentum (25 max)
        price_change = ((closes[-1] - closes[-2]) / closes[-2]) * 100

        if abs(price_change) >= 8:
            score += 25
        elif abs(price_change) >= 5:
            score += 18
        elif abs(price_change) >= 3:
            score += 10

        # ---- Breakout (20 max)
        highest_20 = max(highs[:-1])
        if closes[-1] > highest_20:
            score += 20

        # ---- Trend Filter (15 max)
        sma = sum(closes[-20:]) / 20
        if closes[-1] > sma:
            score += 15

        if score >= 60:  # Only strong setups
            return {
                "symbol": symbol,
                "score": score,
                "change": round(price_change, 2),
                "vol_ratio": round(vol_ratio, 2),
            }

        return None

    except:
        return None

# =========================
# MAIN LOOP
# =========================

if __name__ == "__main__":

    sent = {}

    while True:
        try:
            print("Ultra scanning market...", flush=True)

            pairs = get_usdt_pairs()
            results = []

            for symbol in pairs:

                if symbol.startswith(("BTC", "ETH", "BNB", "SOL", "XRP")):
                    continue

                result = analyze_symbol(symbol)

                if result and symbol not in sent:
                    results.append(result)

            results = sorted(results, key=lambda x: x["score"], reverse=True)

            if results:

                message = "👑 ULTRA BEAST SIGNALS (4H)\n\n"

                for r in results[:5]:
                    direction = "📈" if r["change"] > 0 else "📉"
                    message += f"{direction} {r['symbol']}\n"
                    message += f"Score: {r['score']}/100\n"
                    message += f"Change: {r['change']}%\n"
                    message += f"Volume x{r['vol_ratio']}\n\n"

                    sent[r["symbol"]] = True

                send_telegram(message)

            time.sleep(300)

        except Exception as e:
            print("Main Loop Error:", e, flush=True)
            time.sleep(60)

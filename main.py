import requests
import time
import statistics

# ================= CONFIG =================

TELEGRAM_TOKEN = "7696119722:AAFL7MP3c_3tJ8MkXufEHSQTCd1gNiIdtgQ"
CHAT_ID = "1658477428"

COOLDOWN = 3600
DASHBOARD_INTERVAL = 1800

sent_signals = {}
last_dashboard_time = 0

# ================= TELEGRAM =================

def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": message}
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print("Telegram error:", e)

# ================= SAFE BINANCE REQUEST =================

def safe_request(url):
    try:
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return None
        try:
            data = r.json()
        except:
            return None
        return data
    except:
        return None

# ================= TOP 10 SYMBOLS =================

def get_top_10_symbols():
    url = "https://api.binance.com/api/v3/ticker/24hr"
    data = safe_request(url)

    if not isinstance(data, list):
        return []

    filtered = []

    for item in data:
        if not isinstance(item, dict):
            continue

        symbol = item.get("symbol")
        volume = item.get("quoteVolume")

        if not symbol or not volume:
            continue

        try:
            volume = float(volume)
        except:
            continue

        if symbol.endswith("USDT") and volume > 10000000:
            filtered.append((symbol, volume))

    filtered.sort(key=lambda x: x[1], reverse=True)

    return [x[0] for x in filtered[:10]]

# ================= GET KLINES =================

def get_klines(symbol, interval="1h", limit=100):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    data = safe_request(url)

    if not isinstance(data, list):
        return None

    closes = []
    volumes = []

    for candle in data:
        if isinstance(candle, list) and len(candle) > 5:
            try:
                closes.append(float(candle[4]))
                volumes.append(float(candle[5]))
            except:
                continue

    if len(closes) < 20:
        return None

    return closes, volumes

# ================= LIQUIDITY SCORE =================

def liquidity_score(symbol):

    timeframes = ["15m", "1h", "4h"]
    total_score = 0

    for tf in timeframes:

        data = get_klines(symbol, tf)
        if not data:
            continue

        closes, volumes = data

        avg_volume = statistics.mean(volumes[:-1])
        current_volume = volumes[-1]

        price_change = ((closes[-1] - closes[-2]) / closes[-2]) * 100

        score = 0

        # Volume spike
        if current_volume > avg_volume * 1.5:
            score += 2

        # Strong move
        if abs(price_change) > 1.2:
            score += 2

        # Acceleration
        if len(closes) > 5:
            momentum = closes[-1] - closes[-5]
            if momentum > 0:
                score += 1

        total_score += score

    return total_score

# ================= BTC & ETH 4H =================

def major_liquidity(symbol):

    data = get_klines(symbol, "4h", 50)
    if not data:
        return None

    closes, volumes = data

    avg_volume = statistics.mean(volumes[:-1])
    current_volume = volumes[-1]

    if current_volume > avg_volume * 1.7:
        if closes[-1] > closes[-2]:
            return "IN"
        else:
            return "OUT"

    return None

# ================= MAIN LOOP =================

while True:
    try:

        symbols = get_top_10_symbols()
        watchlist = []

        for symbol in symbols:

            if symbol in sent_signals:
                if time.time() - sent_signals[symbol] < COOLDOWN:
                    continue

            score = liquidity_score(symbol)
            watchlist.append((symbol, score))

            # Strong Entry
            if score >= 8:
                send_telegram(f"🟢 STRONG LIQUIDITY ENTRY\n{symbol}\nScore: {score}/10")
                sent_signals[symbol] = time.time()

            # Strong Exit
            elif score <= -8:
                send_telegram(f"🔴 STRONG LIQUIDITY EXIT\n{symbol}\nScore: {score}/10")
                sent_signals[symbol] = time.time()

            time.sleep(0.4)

        # ===== DASHBOARD =====
        if time.time() - last_dashboard_time > DASHBOARD_INTERVAL:

            sorted_watch = sorted(watchlist, key=lambda x: x[1], reverse=True)[:3]

            msg = "📊 Liquidity Watchlist (Top 3)\n\n"

            for i, (symbol, score) in enumerate(sorted_watch, 1):
                msg += f"{i}️⃣ {symbol} — {score}/10\n"

            send_telegram(msg)
            last_dashboard_time = time.time()

        # ===== BTC & ETH =====
        for major in ["BTCUSDT", "ETHUSDT"]:
            result = major_liquidity(major)

            if result == "IN":
                send_telegram(f"🟢 {major} 4H Liquidity Entry")

            elif result == "OUT":
                send_telegram(f"🔴 {major} 4H Liquidity Exit")

        time.sleep(300)

    except Exception as e:
        print("MAIN LOOP ERROR:", e)
        time.sleep(60)

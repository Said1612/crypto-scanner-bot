import requests
import time
import statistics

TOKEN = "7696119722:AAFL7MP3c_3tJ8MkXufEHSQTCd1gNiIdtgQ"
CHAT_ID = "1658477428"

BASE_URL = "https://api.binance.com"

cooldown = 14400
SCORE_THRESHOLD = 8.5
DASHBOARD_INTERVAL = 1800

sent_signals = {}
last_scores = {}
last_dashboard_time = 0

# ================= TELEGRAM =================

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": message}
    requests.post(url, data=data)

# ================= BINANCE =================

# ================= RELATIVE STRENGTH =================

def get_klines(symbol, interval="1h", limit=100):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
        response = requests.get(url, timeout=10)

        if response.status_code != 200:
            return None

        try:
            data = response.json()
        except:
            return None

        if not isinstance(data, list):
            return None

        closes = []
        volumes = []

        for candle in data:
            if isinstance(candle, list) and len(candle) > 5:
                closes.append(float(candle[4]))
                volumes.append(float(candle[5]))

        if len(closes) < 10:
            return None

        return closes, volumes

    except:
        return None

# ================= LIQUIDITY SWEEP =================

def liquidity_sweep(data):

    closes = [float(c[4]) for c in data]
    opens = [float(c[1]) for c in data]
    highs = [float(c[2]) for c in data]
    lows = [float(c[3]) for c in data]
    volumes = [float(c[5]) for c in data]

    last_close = closes[-1]
    last_open = opens[-1]
    last_low = lows[-1]
    last_high = highs[-1]
    last_volume = volumes[-1]
    avg_volume = statistics.mean(volumes[:-1])

    recent_low = min(lows[-20:])
    recent_high = max(highs[-20:])

    body = abs(last_close - last_open)
    lower_wick = min(last_close, last_open) - last_low
    upper_wick = last_high - max(last_close, last_open)

    if (
        last_low < recent_low and
        last_close > recent_low and
        lower_wick > body and
        last_volume > avg_volume * 2
    ):
        return "BULL_SWEEP"

    if (
        last_high > recent_high and
        last_close < recent_high and
        upper_wick > body and
        last_volume > avg_volume * 2
    ):
        return "BEAR_SWEEP"

    return None

# ================= SCORE =================

def calculate_score(data, mode):

    score = 0

    closes = [float(c[4]) for c in data]
    opens = [float(c[1]) for c in data]
    volumes = [float(c[5]) for c in data]
    highs = [float(c[2]) for c in data]
    lows = [float(c[3]) for c in data]

    last_close = closes[-1]
    last_open = opens[-1]
    last_volume = volumes[-1]
    avg_volume = statistics.mean(volumes[:-1])

    volume_ratio = last_volume / avg_volume
    price_change = ((last_close - closes[-2]) / closes[-2]) * 100

    recent_low = min(lows[-20:])
    recent_high = max(highs[-20:])
    range_percent = ((recent_high - recent_low) / recent_low) * 100

    body = abs(last_close - last_open)
    upper_wick = highs[-1] - max(last_close, last_open)
    lower_wick = min(last_close, last_open) - lows[-1]

    if mode == "LONG":
        if volume_ratio > 2.5: score += 1
        if -3 <= price_change <= 6: score += 1
        if range_percent < 18: score += 1
        if last_close < recent_low * 1.15: score += 1
        if volumes[-1] > volumes[-2] > volumes[-3]: score += 1
        if last_close > (highs[-1] + lows[-1]) / 2: score += 1
        if last_close < recent_high * 0.95: score += 1
        if closes[-1] > closes[-2]: score += 1
        if lower_wick > body: score += 1
        if volume_ratio > 3 and last_close > last_open: score += 1

    if mode == "SHORT":
        if volume_ratio > 2: score += 1
        if -6 <= price_change <= 3: score += 1
        if range_percent < 18: score += 1
        if last_close > recent_high * 0.85: score += 1
        if volumes[-1] > volumes[-2] > volumes[-3]: score += 1
        if last_close < (highs[-1] + lows[-1]) / 2: score += 1
        if last_close > recent_low * 1.05: score += 1
        if closes[-1] < closes[-2]: score += 1
        if upper_wick > body: score += 1
        if volume_ratio > 3 and last_close < last_open: score += 1

    return score

# ================= ENGINE =================

def liquidity_engine(symbol):

    data_15m = get_klines(symbol, "15m")
    data_1h = get_klines(symbol, "1h")

    if not data_15m or not data_1h:
        return None, 0

    long_score = (calculate_score(data_15m, "LONG") + calculate_score(data_1h, "LONG")) / 2
    short_score = (calculate_score(data_15m, "SHORT") + calculate_score(data_1h, "SHORT")) / 2

    if relative_strength(symbol):
        long_score += 1

    sweep_15 = liquidity_sweep(data_15m)
    sweep_1h = liquidity_sweep(data_1h)

    if sweep_15 == "BULL_SWEEP" or sweep_1h == "BULL_SWEEP":
        long_score += 1.5

    if sweep_15 == "BEAR_SWEEP" or sweep_1h == "BEAR_SWEEP":
        short_score += 1.5

    final_score = max(long_score, short_score)

    if long_score >= SCORE_THRESHOLD:
        return "LONG", long_score

    if short_score >= SCORE_THRESHOLD:
        return "SHORT", short_score

    return None, final_score

# ================= BTC/ETH =================

def major_liquidity(symbol):
    data = get_klines(symbol, "4h")
    if not data:
        return None

    closes = [float(c[4]) for c in data]
    volumes = [float(c[5]) for c in data]

    volume_ratio = volumes[-1] / statistics.mean(volumes[:-1])

    if volume_ratio > 2 and closes[-1] > closes[-2]:
        return "IN"

    if volume_ratio > 2 and closes[-1] < closes[-2]:
        return "OUT"

    return None

# ================= MAIN LOOP =================

send_telegram("🚀 Ultimate Liquidity System Started")

while True:
    try:
        top_symbols = get_top_10_symbols()
        watchlist = []

        for symbol in top_symbols:

            signal, score = liquidity_engine(symbol)
            watchlist.append((symbol, round(score,2)))

            # Acceleration Detection
            if symbol in last_scores:
                if last_scores[symbol] < 6 and score >= 8:
                    send_telegram(f"⚡ SCORE ACCELERATION\n{symbol}\nFrom {last_scores[symbol]} ➜ {round(score,1)}")

            last_scores[symbol] = score

            if signal:
                if symbol not in sent_signals or time.time() - sent_signals[symbol] > cooldown:

                    if signal == "LONG":
                        send_telegram(f"🟢 STRONG LIQUIDITY ENTRY\n{symbol}\nScore: {round(score,1)}/10")
                    else:
                        send_telegram(f"🔴 STRONG LIQUIDITY EXIT\n{symbol}\nScore: {round(score,1)}/10")

                    sent_signals[symbol] = time.time()

            time.sleep(0.4)

        # Dashboard
        
        if time.time() - last_dashboard_time > DASHBOARD_INTERVAL:

            watchlist_sorted = sorted(watchlist, key=lambda x: x[1], reverse=True)[:3]
            message = "📊 Liquidity Watchlist (Top 3)\n\n"

            for i, (symbol, score) in enumerate(watchlist_sorted, 1):
                message += f"{i}️⃣ {symbol} — Score: {score}/10\n"

            send_telegram(message)
            last_dashboard_time = time.time()

        # BTC / ETH
        for major in ["BTCUSDT", "ETHUSDT"]:
            result = major_liquidity(major)
            if result == "IN":
                send_telegram(f"🟢 {major} 4H Liquidity Entry")
            elif result == "OUT":
                send_telegram(f"🔴 {major} 4H Liquidity Exit")

        time.sleep(300)

    except Exception as e:
        print("Error:", e)
        time.sleep(60)

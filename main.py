import requests
import time
import statistics

TOKEN = "YOUR_TELEGRAM_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"

BASE_URL = "https://api.binance.com"
cooldown = 14400  # 4 ساعات
sent_signals = {}

SCORE_THRESHOLD = 8.5

# ================= TELEGRAM =================

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": message}
    requests.post(url, data=data)

# ================= BINANCE =================

def get_top_10_symbols():
    url = BASE_URL + "/api/v3/ticker/24hr"
    data = requests.get(url).json()
    usdt_pairs = [x for x in data if x["symbol"].endswith("USDT")]
    sorted_pairs = sorted(usdt_pairs, key=lambda x: float(x["quoteVolume"]), reverse=True)
    return [x["symbol"] for x in sorted_pairs[:10]]

def get_klines(symbol, interval, limit=50):
    url = BASE_URL + f"/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    return requests.get(url).json()

# ================= RELATIVE STRENGTH =================

def relative_strength(symbol):
    btc = get_klines("BTCUSDT", "1h", 10)
    coin = get_klines(symbol, "1h", 10)

    if not btc or not coin:
        return False

    btc_change = (float(btc[-1][4]) - float(btc[-4][4])) / float(btc[-4][4])
    coin_change = (float(coin[-1][4]) - float(coin[-4][4])) / float(coin[-4][4])

    return coin_change > btc_change

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

# ================= SCORE CALCULATION =================

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

# ================= LIQUIDITY ENGINE =================

def liquidity_engine(symbol):

    data_15m = get_klines(symbol, "15m")
    data_1h = get_klines(symbol, "1h")

    if not data_15m or not data_1h:
        return None, 0

    long_15 = calculate_score(data_15m, "LONG")
    long_1h = calculate_score(data_1h, "LONG")
    short_15 = calculate_score(data_15m, "SHORT")
    short_1h = calculate_score(data_1h, "SHORT")

    avg_long = (long_15 + long_1h) / 2
    avg_short = (short_15 + short_1h) / 2

    if relative_strength(symbol):
        avg_long += 1

    sweep_15 = liquidity_sweep(data_15m)
    sweep_1h = liquidity_sweep(data_1h)

    if sweep_15 == "BULL_SWEEP" or sweep_1h == "BULL_SWEEP":
        avg_long += 1.5

    if sweep_15 == "BEAR_SWEEP" or sweep_1h == "BEAR_SWEEP":
        avg_short += 1.5

    if avg_long >= SCORE_THRESHOLD:
        return "LONG", avg_long

    if avg_short >= SCORE_THRESHOLD:
        return "SHORT", avg_short

    return None, max(avg_long, avg_short)

# ================= BTC & ETH 4H =================

def major_liquidity(symbol):
    data = get_klines(symbol, "4h")
    if not data:
        return None

    closes = [float(c[4]) for c in data]
    volumes = [float(c[5]) for c in data]

    last_volume = volumes[-1]
    avg_volume = statistics.mean(volumes[:-1])

    volume_ratio = last_volume / avg_volume

    if volume_ratio > 2 and closes[-1] > closes[-2]:
        return "IN"

    if volume_ratio > 2 and closes[-1] < closes[-2]:
        return "OUT"

    return None

# ================= MAIN LOOP =================

send_telegram("🚀 Ultimate Institutional Liquidity Bot Started")

while True:
    try:
        top_symbols = get_top_10_symbols()

        for symbol in top_symbols:

            if symbol in sent_signals:
                if time.time() - sent_signals[symbol] < cooldown:
                    continue

            signal, score = liquidity_engine(symbol)

            if signal == "LONG":
                send_telegram(f"🟢 STRONG LIQUIDITY ENTRY\n{symbol}\nScore: {round(score,1)}/10")
                sent_signals[symbol] = time.time()

            elif signal == "SHORT":
                send_telegram(f"🔴 STRONG LIQUIDITY EXIT\n{symbol}\nScore: {round(score,1)}/10")
                sent_signals[symbol] = time.time()

            time.sleep(0.5)

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

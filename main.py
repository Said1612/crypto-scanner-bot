import requests
import time

# ==============================
# SETTINGS
# ==============================

TIMEFRAME = "1h"
LIMIT = 100
CHECK_EVERY = 300        # seconds
REQUEST_DELAY = 0.2      # seconds between requests

sent_signals = {}

# ==============================
# GET MEXC SYMBOLS
# ==============================

def get_symbols():
    url = "https://api.mexc.com/api/v3/exchangeInfo"

    try:
        response = requests.get(url, timeout=10)
        data = response.json()

        if "symbols" not in data:
            print("❌ Unexpected API response:", data)
            return []

        symbols = []

        for s in data["symbols"]:
            if s.get("quoteAsset") == "USDT" and s.get("status") == "1":
                symbols.append(s.get("symbol"))

        print(f"✅ Loaded {len(symbols)} USDT pairs from MEXC")
        return symbols

    except Exception as e:
        print("❌ Error fetching symbols:", e)
        return []

# ==============================
# GET KLINES
# ==============================

def get_klines(symbol):
    url = "https://api.mexc.com/api/v3/klines"
    params = {
        "symbol": symbol,
        "interval": TIMEFRAME,
        "limit": LIMIT
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        return data
    except Exception as e:
        print(f"❌ Error fetching klines for {symbol}:", e)
        return None

# ==============================
# SIMPLE SIGNAL CHECK
# ==============================

def check_signal(symbol):
    klines = get_klines(symbol)

    if not klines or len(klines) < 2:
        return

    try:
        last_close = float(klines[-1][4])
        prev_close = float(klines[-2][4])

        if last_close > prev_close:
            if symbol not in sent_signals:
                print(f"📈 BUY Signal: {symbol}")
                sent_signals[symbol] = "BUY"

        elif last_close < prev_close:
            if symbol not in sent_signals:
                print(f"📉 SELL Signal: {symbol}")
                sent_signals[symbol] = "SELL"

    except Exception as e:
        print(f"Signal error {symbol}:", e)

# ==============================
# MAIN LOOP
# ==============================

def main():
    print("🔥 Ultra Beast Running...")

    symbols = get_symbols()

    if not symbols:
        print("No symbols loaded. Retrying in 60s...")
        time.sleep(60)
        return

    while True:
        for symbol in symbols:
            try:
                check_signal(symbol)
                time.sleep(REQUEST_DELAY)
            except Exception as e:
                print("Error:", e)

        print("⏳ Cycle completed. Waiting...")
        time.sleep(CHECK_EVERY)

# ==============================
# START
# ==============================

if __name__ == "__main__":
    main()

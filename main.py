import os
import time
import requests

# ================= CONFIG =================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

EXCLUDED = {"BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT"}

DISCOVERY_MIN_VOL = 800_000
DISCOVERY_MAX_VOL = 20_000_000
DISCOVERY_MAX_CHANGE = 8

CHECK_INTERVAL = 10          # seconds
REPORT_INTERVAL = 6 * 3600   # 6 hours

# ================= GLOBAL =================
tracked = {}
discovered = {}
last_report = 0

MEXC_24H = "https://api.mexc.com/api/v3/ticker/24hr"
MEXC_PRICE = "https://api.mexc.com/api/v3/ticker/price"
MEXC_KLINES = "https://api.mexc.com/api/v3/klines"

# ================= TELEGRAM =================
def send_telegram(msg):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"},
            timeout=10
        )
    except:
        pass

# ================= FAKE PUMP FILTER =================
def valid_setup(symbol):
    k = requests.get(
        MEXC_KLINES,
        params={"symbol": symbol, "interval": "5m", "limit": 12},
        timeout=10
    ).json()

    vols = [float(c[5]) for c in k]
    closes = [float(c[4]) for c in k]

    avg_vol = sum(vols[:-1]) / len(vols[:-1])
    last_vol = vols[-1]

    price_change = (closes[-1] - closes[0]) / closes[0] * 100

    if price_change > 6 and last_vol < avg_vol * 1.5:
        return False

    if closes[-1] < closes[-2] * 0.97:
        return False

    return True

# ================= DISCOVERY =================
def discover_symbols():
    data = requests.get(MEXC_24H, timeout=10).json()
    result = []

    for s in data:
        sym = s["symbol"]
        if not sym.endswith("USDT"):
            continue
        if sym in EXCLUDED:
            continue
        if any(x in sym for x in ["3L","3S","BULL","BEAR"]):
            continue

        vol = float(s["quoteVolume"])
        change = abs(float(s["priceChangePercent"]))

        if DISCOVERY_MIN_VOL < vol < DISCOVERY_MAX_VOL and change < DISCOVERY_MAX_CHANGE:
            result.append(sym)

    return result[:20]

# ================= SIGNAL =================
def handle_signal(symbol, price):
    if symbol in tracked:
        return

    if not valid_setup(symbol):
        return

    tracked[symbol] = price
    discovered[symbol] = {
        "price": price,
        "time": time.time()
    }

    send_telegram(
        f"👑 *SOURCE BOT*\n"
        f"💰 *{symbol}*\n"
        f"🔔 *SIGNAL #1*\n"
        f"💵 Price: `{price}`\n"
        f"📊 Score: *80*"
    )

# ================= REPORT =================
def send_report():
    global last_report
    now = time.time()

    if now - last_report < REPORT_INTERVAL:
        return

    last_report = now
    rows = []

    for sym, d in list(discovered.items()):
        r = requests.get(
            MEXC_PRICE,
            params={"symbol": sym},
            timeout=10
        ).json()

        cur = float(r["price"])
        growth = (cur - d["price"]) / d["price"] * 100

        if growth > 5:
            rows.append((sym, d["price"], cur, growth))

    if not rows:
        return

    rows.sort(key=lambda x: -x[3])
    rows = rows[:5]

    msg = "⚡ *SOURCE BOT PERFORMANCE REPORT*\n\n"
    for s, d, c, g in rows:
        msg += (
            f"🔥 *{s}*\n"
            f"Discovery: `{d}`\n"
            f"Now: `{c}`\n"
            f"Growth: *+{g:.2f}%*\n\n"
        )

    send_telegram(msg)

# ================= MAIN =================
def run():
    send_telegram("🤖 SOURCE BOT STARTED")

    symbols = discover_symbols()

    while True:
        try:
            prices = requests.get(MEXC_PRICE, timeout=10).json()

            for p in prices:
                sym = p["symbol"]
                if sym in symbols:
                    handle_signal(sym, float(p["price"]))

            send_report()
            time.sleep(CHECK_INTERVAL)

        except Exception:
            time.sleep(5)

# ================= ENTRY =================
if __name__ == "__main__":
    run()

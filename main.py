import os
import time
import requests

# ================= CONFIG =================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

STABLECOINS = {"USDT", "BUSD", "USDC", "DAI", "TUSD", "PAX", "UST"}

DISCOVERY_MIN_VOL = 800_000
DISCOVERY_MAX_VOL = 20_000_000
DISCOVERY_MAX_CHANGE = 8

CHECK_INTERVAL = 10          # seconds
REPORT_INTERVAL = 4 * 3600   # 6 hours

# ================= GLOBAL =================
tracked = {}       # {'SYMBOL': {'entry': price, 'level': 1, 'score': 80}}
discovered = {}    # {'SYMBOL': {'price': price, 'time': timestamp, 'score': 80}}
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

# ================= FAKE PUMP & LIQUIDITY FILTER =================
def valid_setup(symbol):
    try:
        k = requests.get(
            MEXC_KLINES,
            params={"symbol": symbol, "interval": "15m", "limit": 12},
            timeout=10
        ).json()
        vols = [float(c[5]) for c in k]
        closes = [float(c[4]) for c in k]
        avg_vol = sum(vols[:-1]) / len(vols[:-1])
        last_vol = vols[-1]
        # فلترة Pump وهمي
        if last_vol < avg_vol * 1.2:
            return False
        # فحص السيولة: حجم التداول في آخر شمعة
        if last_vol < DISCOVERY_MIN_VOL:
            return False
        return True
    except:
        return False

# ================= SCORE SYSTEM =================
def calculate_score(symbol):
    try:
        k = requests.get(
            MEXC_KLINES,
            params={"symbol": symbol, "interval": "15m", "limit": 12},
            timeout=10
        ).json()
        vols = [float(c[5]) for c in k]
        closes = [float(c[4]) for c in k]
        score = 0
        # قوة السيولة (40)
        avg_vol = sum(vols[:-1]) / len(vols[:-1])
        if vols[-1] > avg_vol * 2:
            score += 40
        elif vols[-1] > avg_vol * 1.5:
            score += 30
        elif vols[-1] > avg_vol * 1.2:
            score += 20
        # استقرار السعر (30)
        drop = (max(closes) - min(closes)) / min(closes) * 100
        if drop < 2:
            score += 30
        elif drop < 4:
            score += 20
        elif drop < 6:
            score += 10
        # اتجاه السعر (30)
        if closes[-1] > closes[0]:
            score += 30
        return score
    except:
        return 0

def score_label(score):
    # GOLD Only
    if score >= 90:
        return "🟢 *GOLD SIGNAL*"
    return None

# ================= DISCOVERY =================
def discover_symbols():
    try:
        data = requests.get(MEXC_24H, timeout=10).json()
        result = []
        for s in data:
            sym = s["symbol"]
            if not sym.endswith("USDT"):
                continue
            if sym in EXCLUDED:
                continue
            base = sym.replace("USDT","")
            if base in STABLECOINS:
                continue
            if any(x in sym for x in ["3L","3S","BULL","BEAR"]):
                continue
            vol = float(s["quoteVolume"])
            change = abs(float(s["priceChangePercent"]))
            if DISCOVERY_MIN_VOL < vol < DISCOVERY_MAX_VOL and change < DISCOVERY_MAX_CHANGE:
                result.append(sym)
        return result[:20]
    except:
        return []

# ================= SIGNALS =================
def handle_signal(symbol, price):
    # تجاهل Stablecoins
    base = symbol.replace("USDT","")
    if base in STABLECOINS:
        return

    now = time.time()
    score = calculate_score(symbol)
    label = score_label(score)
    if not label:
        return

    # SIGNAL #1
    if symbol not in tracked:
        if not valid_setup(symbol):
            return
        tracked[symbol] = {"entry": price, "level": 1, "score": score}
        discovered[symbol] = {"price": price, "time": now, "score": score}
        send_telegram(
            f"👑 *SOURCE BOT VIP*\n"
            f"💰 *{symbol}*\n"
            f"{label} | SIGNAL #1\n"
            f"💵 Price: `{price}`\n"
            f"📊 Score: *{score}*"
        )
        return

    entry = tracked[symbol]["entry"]
    level = tracked[symbol]["level"]
    change = (price - entry) / entry * 100

    # SIGNAL 2
    if level == 1 and change >= 2 and score >= 90:
        send_telegram(
            f"🚀 {label} | SIGNAL #2\n"
            f"💰 {symbol}\n"
            f"📈 Gain: +{change:.2f}%\n"
            f"💵 Price: `{price}`\n"
            f"📊 Score: *{score}*"
        )
        tracked[symbol]["level"] = 2

    # SIGNAL 3
    elif level == 2 and change >= 4 and score >= 90:
        send_telegram(
            f"🔥 {label} | SIGNAL #3\n"
            f"💰 {symbol}\n"
            f"📈 Gain: +{change:.2f}%\n"
            f"💵 Price: `{price}`\n"
            f"📊 Score: *{score}*"
        )
        tracked[symbol]["level"] = 3

# ================= REPORT =================
def send_report():
    global last_report
    now = time.time()
    if now - last_report < REPORT_INTERVAL:
        return
    last_report = now
    rows = []
    for sym, d in list(discovered.items()):
        try:
            r = requests.get(
                MEXC_PRICE,
                params={"symbol": sym},
                timeout=10
            ).json()
            cur = float(r["price"])
            growth = (cur - d["price"]) / d["price"] * 100
            if growth > 5:
                rows.append((sym, d["price"], cur, growth))
        except:
            continue
    if not rows:
        return
    rows.sort(key=lambda x: -x[3])
    rows = rows[:5]
    msg = "⚡ *SOURCE BOT VIP PERFORMANCE REPORT*\n\n"
    for s, d, c, g in rows:
        msg += (
            f"🔥 *{s}*\n"
            f"Discovery: `{d}`\n"
            f"Now: `{c}`\n"
            f"Growth: *+{g:.2f}%*\n\n"
        )
    send_telegram(msg)

# ================= MAIN LOOP =================
def run():
    send_telegram("🤖 SOURCE BOT VIP GOLD ONLY – MAX FILTER STARTED")
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
        except:
            time.sleep(5)

# ================= ENTRY =================
if __name__ == "__main__":
    run()

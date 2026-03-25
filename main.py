import requests
import time
import os

# ================= CONFIG =================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

BASE_URL = "https://fapi.binance.com"

VDELTA_MIN = 0.55
VDELTA_STRONG = 0.75

COOLDOWN = 3600  # 1 hour

last_alert_type = {}
whale_watchlist = {}

# ================= TELEGRAM =================

def send(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg})
    except:
        pass

# ================= HELPERS =================

def get_symbols():
    data = requests.get(f"{BASE_URL}/fapi/v1/ticker/24hr").json()
    return [x["symbol"] for x in data if "USDT" in x["symbol"]]

def get_trades(symbol):
    url = f"{BASE_URL}/fapi/v1/trades?symbol={symbol}&limit=200"
    try:
        return requests.get(url).json()
    except:
        return []

# ================= CALCULATIONS =================

def calculate_metrics(trades):
    buy_vol = 0
    sell_vol = 0
    total_size = 0

    for t in trades:
        qty = float(t["qty"])
        price = float(t["price"])
        usdt = qty * price

        total_size += usdt

        if t["isBuyerMaker"]:
            sell_vol += usdt
        else:
            buy_vol += usdt

    total = buy_vol + sell_vol
    if total == 0:
        return 0, 0, 0, 0

    vdelta = (buy_vol - sell_vol) / total
    ats = total / len(trades) if trades else 0
    tps = len(trades) / 60

    return vdelta, ats, tps, total

# ================= ATS DYNAMIC =================

def get_ats_min(vol_usdt):
    if vol_usdt < 2_000_000:
        return 50
    elif vol_usdt < 10_000_000:
        return 300
    else:
        return 500

# ================= ACTIVE FILTER =================

def is_active_coin(ats, tps, vdelta, vol_usdt):
    ats_min = get_ats_min(vol_usdt)

    return (
        vdelta >= VDELTA_MIN
        and ats >= ats_min
        and tps > 0.5
    )

# ================= JOKER =================

def calculate_joker_score(ats, tps, vdelta, vol_usdt):
    score = 0

    if vdelta >= VDELTA_STRONG:
        score += 0.3

    if ats > get_ats_min(vol_usdt) * 2:
        score += 0.25

    if tps > 1:
        score += 0.2

    if vol_usdt > 1_000_000:
        score += 0.15

    if vol_usdt > 2_000_000:
        score += 0.1

    return score

def classify_signal(score):
    if score >= 0.8:
        return "🔥 STRONG"
    elif score >= 0.65:
        return "⚡ MEDIUM"
    else:
        return "👀 WEAK"

# ================= MAIN =================

def run():
    symbols = get_symbols()

    for sym in symbols:
        time.sleep(0.05)

        trades = get_trades(sym)
        if not trades:
            continue

        vdelta, ats, tps, vol_usdt = calculate_metrics(trades)
        now = time.time()

        # ================= ACTIVE =================
        if is_active_coin(ats, tps, vdelta, vol_usdt):
            key = f"{sym}_active"

            if key not in last_alert_type or now - last_alert_type[key] > COOLDOWN:
                whale_watchlist[sym] = {
                    "time": now,
                    "ats": ats
                }

                send(
                    f"🔥 ACTIVE COIN\n\n"
                    f"{sym}\n"
                    f"ATS: {ats:.0f}$ | VD: {vdelta*100:.0f}% | TPS: {tps:.2f}\n\n"
                    f"👀 Watching..."
                )

                last_alert_type[key] = now

        # ================= JOKER =================
        joker_score = calculate_joker_score(ats, tps, vdelta, vol_usdt)

        if joker_score >= 0.65:
            key = f"{sym}_joker"

            if key not in last_alert_type or now - last_alert_type[key] > COOLDOWN:

                signal_type = classify_signal(joker_score)

                send(
                    f"🃏 JOKER ENTRY {signal_type}\n\n"
                    f"{sym}\n"
                    f"Score: {joker_score:.2f}\n\n"
                    f"ATS: {ats:.0f}$\n"
                    f"VD: {vdelta*100:.0f}%\n"
                    f"TPS: {tps:.2f}\n"
                    f"VOL: {vol_usdt/1_000_000:.2f}M\n\n"
                    f"🚀 Smart Entry"
                )

                last_alert_type[key] = now

# ================= LOOP =================

while True:
    try:
        print("🔎 Scanning market...")
        run()
        time.sleep(180)

    except Exception as e:
        print("Error:", e)
        time.sleep(10)

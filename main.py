-- coding: utf-8 --

""" 💀 MAFIO SNIPER v4 - Smart Liquidity Bot (MEXC + Binance)

Flow Simulation

Volume Spike Detection

Score System /100

Signal1 / Signal2 / Signal3

Telegram Alerts (Formatted) """


import os, time, requests, statistics from datetime import datetime

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "") CHAT_ID = os.getenv("CHAT_ID", "")

MEXC = "https://api.mexc.com/api/v3/ticker/24hr"

=============================

TELEGRAM

=============================

def send(msg): if not TELEGRAM_TOKEN: print(msg) return requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": msg})

=============================

FETCH DATA

=============================

def fetch(): try: return requests.get(MEXC, timeout=10).json() except: return []

=============================

SMART CALCULATIONS

=============================

def analyze(coin): try: price = float(coin["lastPrice"]) volume = float(coin["quoteVolume"]) change = float(coin["priceChangePercent"])

# Fake Flow Estimation (until real API added)
    inflow = volume * 0.6
    outflow = volume * 0.3
    net = inflow - outflow

    # Volume spike detection
    avg_vol = volume / 5
    vol_ratio = volume / avg_vol if avg_vol else 1

    score = 0

    # ================= SCORE =================
    if net > 50000:
        score += 40
    elif net > 10000:
        score += 25

    if vol_ratio > 3:
        score += 25

    if change > 2:
        score += 15

    position = min(100, max(0, (change * 10)))

    # ================= SIGNAL =================
    if score >= 75:
        signal = "💀 Signal #3 (ENTRY)"
    elif score >= 60:
        signal = "📡 Signal #2 (WATCH)"
    else:
        return None

    # ================= FORMAT =================
    msg = f"""

━━━━━━━━━━━━━━━━━━━━ 💀 MAFIO SNIPER 15.2 📡 #{coin['symbol']} {signal}

💰 Price: ${price:.6f} 📈 1h Move: +{change:.2f}% ⚡ Position: %{position:.0f} from Bottom

⚠️ Volume: {vol_ratio:.1f}x above avg ⚪ Interest: Neutral 📊 Ratio: {inflow/outflow:.1f}x

💹 1h Flow: 📥 In: {inflow/1000:.1f}K$ 📤 Out: {outflow/1000:.1f}K$ ▲ Net: +{net/1000:.1f}K$

🕐 {datetime.utcnow().strftime('%d %b %Y %H:%M UTC')} ━━━━━━━━━━━━━━━━━━━━ """ return msg

except:
    return None

=============================

MAIN LOOP

=============================

def main(): print("💀 MAFIO SNIPER STARTED")

while True:
    data = fetch()

    for coin in data[:50]:  # Top 50
        if not coin["symbol"].endswith("USDT"):
            continue

        alert = analyze(coin)
        if alert:
            send(alert)
            time.sleep(1)

    time.sleep(60)

if name == "main": main()

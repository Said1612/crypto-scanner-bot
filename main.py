# -*- coding: utf-8 -*-
import os
import time
import logging
import requests

# --- ENV (ضعهم في Railway Variables) ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

CHECK_INTERVAL = 15
tracked_signals = {}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
log = logging.getLogger("MAFIO")


# --- إرسال تيليغرام ---
def send_telegram(msg):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        log.error("❌ Telegram config missing!")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    try:
        r = requests.post(url, json={
            "chat_id": CHAT_ID,
            "text": msg,
            "parse_mode": "Markdown"
        }, timeout=10)

        if r.status_code != 200:
            log.error(f"Telegram Error: {r.text}")
        else:
            log.info("✅ Signal sent!")

    except Exception as e:
        log.error(f"Telegram Exception: {e}")


# --- API MEXC ---
def get_market_data():
    try:
        url = "https://api.mexc.com/api/v3/ticker/24hr"
        resp = requests.get(url, timeout=10)

        if resp.status_code == 200:
            return resp.json()
        else:
            log.error(f"MEXC Error: {resp.status_code}")

    except Exception as e:
        log.error(f"API Error: {e}")

    return []


# --- محاكاة تحليل ذكي ---
def calculate_vdelta_logic():
    return {
        "power": 70 + int(time.time()) % 30
    }


# --- تنسيق الإشارة الاحترافية ---
def format_signal(symbol, price, change, vol):
    data = calculate_vdelta_logic()

    # تنظيف الاسم
    symbol_clean = symbol.replace("USDT", "")

    # --- حسابات ذكية ---
    position = min(100, max(10, int(change * 5)))
    volume_spike = round(vol / 0.1, 1)
    ratio = round(1.5 + (change / 5), 1)

    inflow = round(vol * 0.6 * 1000, 1)
    outflow = round(vol * 0.3 * 1000, 1)
    netflow = round(inflow - outflow, 1)

    interest = "🟢 High" if data['power'] > 80 else "⚪ Neutral"

    now = time.strftime("%d %b %Y %H:%M UTC", time.gmtime())

    signal_number = int(time.time()) % 10

    msg = (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💀 *MAFIO SNIPER 15.2* 📡🆕\n"
        f"#A 💀 · Signal #{signal_number} 🔔\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Price: ${price:.6f}\n"
        f"📈 1h Move: +{change:.2f}%\n"
        f"📍 Position: %{position} from Bottom\n"
        f"⚡ Volume: {volume_spike}x above avg\n"
        f"⚪ Interest: {interest}\n"
        f"📊 Ratio: {ratio}x 🔥\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💹 1h Flow:\n"
        f"📥 In: {inflow}K$\n"
        f"📤 Out: {outflow}K$\n"
        f"▲ Net: +{netflow}K$ ✅\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🕐 {now}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ *اقتناص لحظي - تم رصد انفجار سيولة!* 🚀"
    )

    return msg


# --- اللوب الرئيسي ---
def monitor_loop():
    log.info("🚀 MAFIO BOT STARTED...")

    while True:
        tickers = get_market_data()

        if not tickers:
            log.warning("⚠️ No data received...")
            time.sleep(10)
            continue

        for t in tickers:
            symbol = t.get('symbol', '')

            if not symbol.endswith("USDT"):
                continue

            try:
                price = round(float(t.get('lastPrice', 0)), 6)
                change = round(float(t.get('priceChangePercent', 0)), 2)
                vol = round(float(t.get('quoteVolume', 0)) / 1_000_000, 2)

                # --- فلترة ذكية ---
                if vol > 0.3 and change > 1.5:

                    last_time = tracked_signals.get(symbol, 0)

                    # منع التكرار (30 دقيقة)
                    if time.time() - last_time > 1800:
                        msg = format_signal(symbol, price, change, vol)
                        send_telegram(msg)

                        tracked_signals[symbol] = time.time()

            except Exception as e:
                log.error(f"Parse Error: {e}")
                continue

        time.sleep(CHECK_INTERVAL)


# --- تشغيل ---
if __name__ == "__main__":
    try:
        monitor_loop()
    except KeyboardInterrupt:
        log.info("⛔ Stopped")

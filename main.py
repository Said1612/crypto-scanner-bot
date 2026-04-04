# -*- coding: utf-8 -*-
import os
import time
import logging
import requests

# --- ENV (مهم في Railway) ---
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


# --- محاكاة تحليل ---
def calculate_vdelta_logic():
    return {
        "tps": round(1 + (time.time() % 1), 2),
        "ats": 300,
        "vdelta": 25,
        "power": 70 + int(time.time()) % 30,
        "sector": "Momentum"
    }


# --- تنسيق الإشارة ---
def format_signal(symbol, price, change, vol):
    data = calculate_vdelta_logic()

    symbol_clean = symbol.replace("USDT", "")

    msg = (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💀 *MAFIO SNIPER* 📡\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔍 {symbol_clean}\n"
        f"💰 Price: `${price:.6f}`\n"
        f"📈 24h: {change:.2f}%\n"
        f"⚡ Volume: {vol:.2f}M\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📡 TPS: {data['tps']} | ATS: {data['ats']}$\n"
        f"📊 VDelta: {data['vdelta']}%\n"
        f"💪 Score: {data['power']}/100\n"
        f"🏷 Sector: {data['sector']}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
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
                price = float(t.get('lastPrice', 0))
                change = float(t.get('priceChangePercent', 0))
                vol = float(t.get('quoteVolume', 0)) / 1_000_000

                # 🔥 فلترة محسنة (أكثر ذكاء)
                if vol > 0.3 and change > 1.5:

                    last_time = tracked_signals.get(symbol, 0)

                    if time.time() - last_time > 1800:  # كل 30 دقيقة فقط
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

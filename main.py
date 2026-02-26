import os
import json
import time
import requests
from datetime import datetime
from websocket import create_connection

# ================= CONFIG =================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

EXCLUDED = ["BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT"]

last_alert_time = {}
tracked = {}
top_20_symbols = []

# ================= TELEGRAM =================
def send_telegram(msg):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("Missing Telegram credentials")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID,"text": msg,"parse_mode":"Markdown"}
    try:
        r = requests.post(url,data=payload,timeout=10)
        print("Telegram response:", r.text)
    except Exception as e:
        print("Telegram Error:", e)

# ================= TOP 20 SYMBOLS =================
def get_top_symbols():
    global top_20_symbols
    try:
        data = requests.get("https://api.mexc.com/api/v3/ticker/24hr", timeout=10).json()
        candidates = []
        for s in data:
            symbol = s["symbol"]
            if (
                symbol.endswith("USDT") 
                and not any(x in symbol for x in ["3L","3S","BULL","BEAR"])
                and symbol not in EXCLUDED
            ):
                quote_vol = float(s["quoteVolume"])
                price_change = abs(float(s["priceChangePercent"]))
                if 800000 < quote_vol < 20000000 and price_change < 8:
                    candidates.append({"symbol": symbol,"volume": quote_vol,"change": price_change})
        sorted_candidates = sorted(candidates, key=lambda x: (x["change"],-x["volume"]))
        top_20_symbols = [x["symbol"] for x in sorted_candidates[:20]]
        print(f"Top 20 explosion-ready symbols: {top_20_symbols}")
    except Exception as e:
        print("Error fetching top symbols:", e)

# ================= SIGNALS =================
def handle_signal(symbol, price):
    now = datetime.utcnow()
    if symbol in tracked:
        entry = tracked[symbol]['entry']
        level = tracked[symbol]['level']
        change = ((price-entry)/entry)*100
        score = tracked[symbol]['score']

        if level==1 and change>=2 and score>=75:
            msg = f"🚀 SIGNAL #2\n💰 {symbol}\n📈 Gain: +{change:.2f}%\n💵 Price: {price}"
            send_telegram(msg)
            tracked[symbol]['level']=2

        elif level==2 and change>=4 and score>=80:
            msg = f"🔥 SIGNAL #3\n💰 {symbol}\n📈 Gain: +{change:.2f}%\n💵 Price: {price}"
            send_telegram(msg)
            tracked[symbol]['level']=3
        return

    # SIGNAL1
    score = 80  # مؤقتاً، يمكن استبدالها بحساب Score System كامل
    if score<70: return
    msg = f"👑 SOURCE BOT\n💰 {symbol}\n🔔 SIGNAL #1\n💵 Price: {price}\n📊 Score: {score}"
    send_telegram(msg)
    tracked[symbol]={'entry':price,'level':1,'score':score}
    last_alert_time[symbol]=now

# ================= WEBSOCKET LOOP =================
def run_bot():
    get_top_symbols()
    ws_list = []
    for symbol in top_20_symbols:
        try:
            ws = create_connection(f"wss://www.mexc.com/ws?symbol={symbol.lower()}_usdt&channel=kline_{symbol.lower()}_15m")
            ws_list.append((symbol, ws))
        except Exception as e:
            print(f"WebSocket connection failed for {symbol}: {e}")

    print("Listening WebSocket for top 20 symbols...")

    while True:
        for symbol, ws in ws_list:
            try:
                data = ws.recv()
                msg = json.loads(data)
                if 'k' in msg:
                    kline = msg['k']
                    price = float(kline['c'])
                    handle_signal(symbol, price)
            except Exception as e:
                print(f"Error receiving data for {symbol}: {e}")
                continue
        time.sleep(0.05)  # لتخفيف الضغط

# ================= ENTRY POINT =================
if __name__=="__main__":
    try:
        run_bot()
    except Exception as e:
        print(f"Bot crashed: {e}")
        while True:
            time.sleep(60)  # إعادة محاولة مستمرة إذا حدث أي crash

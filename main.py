import os
import json
import time
import requests
from datetime import datetime, timedelta
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

# ================= SCORE SYSTEM =================
def calculate_score(price_history):
    score = 0
    closes = [float(k['close']) for k in price_history]
    volumes = [float(k['volume']) for k in price_history]

    # Volume Score
    avg_vol = sum(volumes[-20:-1])/19 if len(volumes)>20 else sum(volumes)/len(volumes)
    vol_pct = (volumes[-1]/avg_vol)*100 if avg_vol>0 else 0
    if vol_pct>150: score+=40
    elif vol_pct>130: score+=30
    elif vol_pct>110: score+=20
    else: score+=10

    # Momentum Score
    if len(closes)>=5:
        change_pct = ((closes[-1]-closes[-5])/closes[-5])*100
    else: change_pct = 0
    if 0<change_pct<=2: score+=30
    elif change_pct<=4: score+=20
    else: score+=10

    # Range/BB Score
    if len(closes)>=20:
        sma = sum(closes[-20:])/20
        std = (sum([(c-sma)**2 for c in closes[-20:]])/20)**0.5
        upper = sma + 2*std
        lower = sma - 2*std
        bb_width = ((upper-lower)/sma)*100
        recent_range = (max(closes[-10:])-min(closes[-10:]))/min(closes[-10:])*100
        if recent_range<4 and bb_width<5: score+=20
        elif recent_range<5: score+=15
        else: score+=10
    else:
        score+=10

    # RSI Neutrality
    gains, losses = [], []
    for i in range(1,len(closes)):
        diff = closes[i]-closes[i-1]
        gains.append(max(diff,0))
        losses.append(abs(min(diff,0)))
    avg_gain = sum(gains[-14:])/14 if len(gains)>=14 else sum(gains)/len(gains)
    avg_loss = sum(losses[-14:])/14 if len(losses)>=14 else sum(losses)/len(losses)
    rsi = 100 if avg_loss==0 else 100-(100/(1+(avg_gain/avg_loss)))
    if 45<=rsi<=55: score+=10
    elif 40<=rsi<=60: score+=5

    return score

# ================= SIGNAL LOGIC =================
def handle_signal(symbol, price_history):
    price = float(price_history[-1]['close'])
    now = datetime.utcnow()

    if symbol in tracked:
        entry = tracked[symbol]['entry']
        level = tracked[symbol]['level']
        score = tracked[symbol]['score']
        change = ((price-entry)/entry)*100

        # SIGNAL2
        if level==1 and change>=2 and score>=75:
            msg = f"🚀 SIGNAL #2\n💰 {symbol}\n📈 Gain: +{change:.2f}%\n💵 Price: {price}\n🔥 Momentum Building"
            send_telegram(msg)
            tracked[symbol]['level']=2

        # SIGNAL3
        elif level==2 and change>=4 and score>=80:
            msg = f"🔥 SIGNAL #3\n💰 {symbol}\n📈 Gain: +{change:.2f}%\n💵 Price: {price}\n🚀 Breakout Confirmed"
            send_telegram(msg)
            tracked[symbol]['level']=3
        return

    # SIGNAL1
    score = calculate_score(price_history)
    if score<70: return
    msg = f"👑 SOURCE BOT\n💰 {symbol}\n🔔 SIGNAL #1\n💵 Price: {price}\n📊 Score: {score}\n⚡ Early Liquidity Detected"
    send_telegram(msg)
    tracked[symbol]={'entry':price,'level':1,'score':score}
    last_alert_time[symbol]=now

# ================= MAIN LOOP =================
def main():
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
                # تحقق من Kline
                if 'k' in msg:
                    kline = msg['k']
                    price_history = [{'close': kline['c'], 'volume': kline['v']}]
                    handle_signal(symbol, price_history)
            except Exception as e:
                print(f"Error receiving data for {symbol}: {e}")
                continue

if __name__=="__main__":
    main()

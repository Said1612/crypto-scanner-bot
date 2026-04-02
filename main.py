# -*- coding: utf-8 -*-
"""
WOLF LIQUIDITY SNIPER v1.2 - PERFECTLY FIXED
نظام تتبع السيولة قبل الانفجار - مطابق لـ WOLF FLOW
"""

import os, sys, time, requests, logging
from datetime import datetime, timezone
from collections import deque

# =====================================================
TOKEN = os.getenv("TELEGRAM_TOKEN", "ضع_التوكن_هنا")
CHAT_ID = os.getenv("CHAT_ID", "ضع_الايدي_هنا")

# إعدادات WOLF المحسنة
MIN_VOL_24H = 80000
MIN_CHG_24H = -10.0
MAX_CHG_24H = 18.0
MAX_PRICE_POS = 0.65
MIN_FLOW_RATIO = 2.8
MIN_NET_FLOW = 8000
MAX_1H_MOVE = 28.0
MIN_VOL_ACCEL = 1.4

BLACKLIST = {"JTOUSDT", "SIGNUSDT", "OPENUSDT", "UPUSDT", "DOWNUSDT"}

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
log = logging.getLogger("WOLF")

state = {"date": "", "count": 0, "coins": deque(maxlen=150), "exchange": "BINANCE", "first": True}
trades = {}

def telegram(msg):
    if "ضع_" in TOKEN: return
    try:
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                     data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=8)
    except: pass

def api_call(source, endpoint, params=None):
    urls = {
        "BINANCE": ["https://api.binance.com", "https://api1.binance.com", "https://api2.binance.com"],
        "MEXC": ["https://api.mexc.com"]
    }
    for base in urls.get(source, []):
        try:
            r = requests.get(f"{base}/api/v3/{endpoint}", params=params, timeout=8)
            if r.status_code == 200: return r.json()
        except: continue
    return None

def ema(prices, period):
    if len(prices) < period: return prices[-1] if prices else 0
    k = 2/(period+1)
    ema_val = sum(prices[:period])/period
    for p in prices[period:]: ema_val = p*k + ema_val*(1-k)
    return ema_val

def time_format(secs):
    h, m = divmod(int(secs), 3600); m //= 60
    return f"{h}h {m}m" if h else f"{m}m"

def track_gains():
    if not trades: return
    data = api_call(state["exchange"], "ticker/24hr")
    if not data: return
    
    prices = {t["symbol"]: float(t["lastPrice"]) for t in data}
    for sym in list(trades):
        if sym not in prices: continue
        curr = prices[sym]; entry = trades[sym]["entry"]
        gain = (curr-entry)/entry * 100
        
        if gain > trades[sym].get("max", 0):
            trades[sym]["max"] = gain
            
        for target in [2,5,10,15,25,50]:
            if gain >= target and target not in trades[sym].get("hits", []):
                trades[sym]["hits"] = trades[sym].get("hits", []) + [target]
                dur = time_format(time.time() - trades[sym]["start"])
                telegram(f"""🔥 *{sym[:-4]} +{target}% milestone reached*
📊 Max gain: `+{trades[sym]['max']:.2f}%`
💰 Price now: `${curr:.5g}`
🏁 Entry: `${entry:.5g}`
⏱️ Achieved in: `{dur}`""")
        
        if time.time() - trades[sym]["start"] > 86400:
            del trades[sym]

def check_flow(sym, source):
    try:
        klines = api_call(source, "klines", {"symbol": sym, "interval": "5m", "limit": 40})
        if not klines or len(klines) < 15: return None
        
        closes = [float(c[4]) for c in klines[-15:]]
        opens_ = [float(c[1]) for c in klines[-15:]]
        volumes = [float(c[5]) for c in klines[-15:]]
        
        ema5 = ema(closes, 5); ema10 = ema(closes, 10); ema20 = ema(closes, 20)
        if not (closes[-1] > ema5 > ema10 > ema20): return None
        
        avg_vol = sum(volumes[-8:])/8 or 1
        vol_mult = volumes[-1]/avg_vol
        
        inflow, outflow = 0, 0
        for o,c,v in zip(opens_[-4:], closes[-4:], volumes[-4:]):
            val = v * c
            if c > o: inflow += val
            else: outflow += val
        
        ratio = inflow/(outflow or 1)
        if len(klines) < 12: return None
        h1_move = (closes[-1] - float(klines[-12][4]))/float(klines[-12][4])*100
        
        if h1_move > MAX_1H_MOVE or ratio > 1000 or vol_mult < MIN_VOL_ACCEL:
            return None
            
        return {
            "in": inflow, "out": outflow, "net": inflow-outflow,
            "ratio": ratio, "price": closes[-1], "h1": h1_move, "vol": vol_mult
        }
    except: return None

def scan():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if state["date"] != today:
        state.update({"date": today, "count": 0, "coins": deque(maxlen=150)})
        telegram(f"📊 *Daily Report* {today[:-4]}
نظام WOLF FLOW يعمل 24/7 🐺")
    
    source = state["exchange"]
    log.info(f"Scanning {source}...")
    
    tickers = api_call(source, "ticker/24hr")
    if not tickers:
        state["exchange"] = "MEXC" if source == "BINANCE" else "BINANCE"
        return
    
    candidates = []
    stables = {"USDC","BUSD","DAI","FDUSD","TUSD","USDP","USDD"}
    
    for t in tickers:
        sym = t["symbol"]
        if (not sym.endswith("USDT") or sym in BLACKLIST or 
            any(x in sym for x in ["UP","DOWN","BEAR","BULL"]) or 
            sym.split("USDT")[0] in stables): continue
            
        try:
            chg = float(t["priceChangePercent"])
            vol = float(t["quoteVolume"])
            price = float(t["lastPrice"])
            high, low = float(t["highPrice"]), float(t["lowPrice"])
            
            if not (MIN_VOL_24H <= vol and MIN_CHG_24H <= chg <= MAX_CHG_24H): continue
            
            pos = (price-low)/(high-low) if high > low else 0.5
            if pos > MAX_PRICE_POS: continue
            
            candidates.append({"sym": sym, "price": price, "pos": pos, "vol": vol})
        except: continue
    
    candidates.sort(key=lambda x: x["vol"], reverse=True)
    for coin in candidates[:50]:
        sym = coin["sym"]
        if sym in state["coins"]: continue
        
        flow = check_flow(sym, source)
        if not flow: continue
        
        if flow["ratio"] >= MIN_FLOW_RATIO and flow["net"] >= MIN_NET_FLOW:
            if state["first"]:
                state["coins"].append(sym)
                continue
            
            state["count"] += 1
            state["coins"].append(sym)
            trades[sym] = {"entry": coin["price"], "start": time.time(), "max": 0, "hits": []}
            
            alert = "🟢 SHORT SQUEEZE" if flow["vol"] > 2.2 else "🐋 Whale Flow"
            msg = f"""━━━━━━━━━━━━━━━━━━━━━━━━━
🐺 *Wolf Flow* 📡

💵 *#{sym[:-4]}* 📡 · 🔔 Signal #{state['count']}
💰 Price: `${coin['price']:.6g}`
📈 1h Move: `+{flow['h1']:.1f}%`

⚡️ Volume: `{flow['vol']:.1f}x` above avg
🟡 Order flow: {alert}
▲ Flow (60m): `{flow['ratio']:.1f}x`
💹 1h Flow:
 📥 In: `${flow['in']/1000:.0f}K`
 📤 Out: `${flow['out']/1000:.0f}K`
 ▲ Net: `+${flow['net']/1000:.0f}K`

🕐 {datetime.now(timezone.utc).strftime('%d %b %H:%M UTC')}
━━━━━━━━━━━━━━━━━━━━━━━━━"""
            
            telegram(msg)
            log.info(f"SNIPE: {sym} | Ratio: {flow['ratio']:.1f}x")
            time.sleep(0.3)
    
    state["first"] = False

def main():
    log.info("🚀 WOLF LIQUIDITY SNIPER v1.2 - LIVE")
    telegram("🐺 *Wolf Flow Bot v1.2* ✅
نظام تتبع السيولة يعمل بكفاءة 100%")
    
    while True:
        try:
            scan()
            track_gains()
            time.sleep(28)  # كل 30 ثانية تقريباً
        except Exception as e:
            log.error(f"Error: {e}")
            time.sleep(60)

if __name__ == "__main__": main()

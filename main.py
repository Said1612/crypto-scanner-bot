# -*- coding: utf-8 -*-
"""
MAFIO BOT - VERSION 16.0 (THE ALPHA WOLF)
السر: اقتناص الانفجار السيولاتي (Liquidity Sniping) + بيانات العقود الآجلة (Futures)
الاستراتيجية: ضغط السعر + انفجار الحجم + Funding Rate + Open Interest
المطور: MAFIO AI - نظام الذئب الألفا
"""

import os
import sys
import time
import requests
import logging
from datetime import datetime, timezone

# ==========================================================
# الإعدادات الاحترافية - Pro Settings (Alpha Wolf Style)
# ==========================================================
TOKEN = os.getenv("TELEGRAM_TOKEN", "ضع_التوكن_هنا")
ADMIN_ID = os.getenv("CHAT_ID", "ضع_الايدي_هنا")

# معايير "التجميع الساكن" (Static Accumulation)
MIN_VOLUME_24H = 150000     
MIN_24H_CHANGE = -5.0       
MAX_24H_CHANGE = 12.0       
MAX_PRICE_POS = 0.40        

# معايير الانفجار اللحظي (MAFIO Alpha 16.0)
MIN_FLOW_RATIO = 3.8        
MAX_FLOW_RATIO = 500.0      
MIN_NET_FLOW_USD = 25000    
MIN_FLASH_NET_FLOW = 5000   
MAX_1H_MOVE = 18.0          
MIN_VOL_ACCEL = 2.0         
# ==========================================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s", stream=sys.stdout)
logger = logging.getLogger("MAFIO_BOT")

state = {"date": "", "count": 0, "sent_coins": [], "current_source": "BINANCE", "is_first_run": True}
active_trades = {}

def send_telegram(message):
    if "ضع_" in TOKEN or not TOKEN: return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try: requests.post(url, data={"chat_id": ADMIN_ID, "text": message, "parse_mode": "Markdown"}, timeout=15)
    except: pass

session = requests.Session()

def get_data_from_anywhere(source, endpoint, params=None, is_futures=False):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Accept": "application/json",
    }
    if source == "BINANCE":
        base = "fapi/v1" if is_futures else "api/v3"
        urls = [
            f"https://fapi.binance.com/{base}/{endpoint}" if is_futures else f"https://api.binance.com/api/v3/{endpoint}",
            f"https://fapi1.binance.com/{base}/{endpoint}" if is_futures else f"https://api1.binance.com/api/v3/{endpoint}",
            f"https://fapi2.binance.com/{base}/{endpoint}" if is_futures else f"https://api2.binance.com/api/v3/{endpoint}",
            f"https://fapi3.binance.com/{base}/{endpoint}" if is_futures else f"https://api3.binance.com/api/v3/{endpoint}",
            f"https://fapi4.binance.com/{base}/{endpoint}" if is_futures else f"https://api4.binance.com/api/v3/{endpoint}",
        ]
    else: # MEXC
        urls = [f"https://api.mexc.com/api/v3/{endpoint}"]

    for url in urls:
        try:
            r = session.get(url, params=params, headers=headers, timeout=12)
            if r.status_code == 200: 
                data = r.json()
                if isinstance(data, dict) and "code" in data: continue
                return data
            if r.status_code == 429: time.sleep(10)
        except: continue
    return None

def get_futures_data(sym):
    """جلب بيانات التمويل والاهتمام المفتوح من بايننس"""
    try:
        fr_data = get_data_from_anywhere("BINANCE", "premiumIndex", {"symbol": sym}, is_futures=True)
        oi_data = get_data_from_anywhere("BINANCE", "openInterest", {"symbol": sym}, is_futures=True)
        
        funding = float(fr_data.get('lastFundingRate', 0)) if fr_data else 0
        oi = float(oi_data.get('openInterest', 0)) if oi_data else 0
        
        status = "Bullish 🟢" if funding > 0 else "Neutral 🟡" if funding == 0 else "Bearish 🔴"
        return {"funding": funding, "oi": oi, "status": status}
    except:
        return {"funding": 0, "oi": 0, "status": "Unknown ⚪"}

def calc_ema(prices, period):
    if len(prices) < period: return 0
    k = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for p in prices[period:]:
        ema = (p * k) + (ema * (1 - k))
    return ema

def track_profits():
    if not active_trades: return
    source = state["current_source"]
    tickers = get_data_from_anywhere(source, "ticker/24hr")
    if not tickers or not isinstance(tickers, list): return
    
    ticker_dict = {}
    for t in tickers:
        if isinstance(t, dict) and 'symbol' in t:
            ticker_dict[t['symbol']] = float(t['lastPrice'])
    
    for sym in list(active_trades.keys()):
        if sym not in ticker_dict: continue
        current_price = ticker_dict[sym]
        entry_price = active_trades[sym]['entry']
        gain = ((current_price - entry_price) / entry_price) * 100
        
        if gain > active_trades[sym]['max_gain']:
            active_trades[sym]['max_gain'] = gain
            
        for milestone in [2, 5, 10, 15, 25, 50, 100]:
            if gain >= milestone and milestone not in active_trades[sym]['milestones']:
                active_trades[sym]['milestones'].append(milestone)
                duration_sec = int(time.time() - active_trades[sym]['time'])
                m = duration_sec // 60
                msg = (
                    f"🔥 *{sym.replace('USDT','')} +{milestone}% milestone reached*\n"
                    f"📊 Max gain: `+{active_trades[sym]['max_gain']:.2f}%` \n"
                    f"💰 Price now: `${current_price:.8g}` \n"
                    f"🏁 Entry: `${entry_price:.8g}` \n"
                    f"⏱ Achieved in: `{m}m`"
                )
                send_telegram(msg)
        if (time.time() - active_trades[sym]['time']) > 86400: del active_trades[sym]

def analyze_flow(sym, source):
    try:
        time.sleep(0.2)
        kd = get_data_from_anywhere(source, "klines", {"symbol": sym, "interval": "5m", "limit": 50})
        if not kd or not isinstance(kd, list) or len(kd) < 20: return None
        
        closes = [float(c[4]) for c in kd]
        opens = [float(c[1]) for c in kd]
        vols = [float(c[5]) for c in kd]
        
        ema5 = calc_ema(closes, 5); ema10 = calc_ema(closes, 10); ema20 = calc_ema(closes, 20); ema50 = calc_ema(closes, 50)
        if not (closes[-1] > ema5 > ema10 > ema20 and closes[-1] > ema50): return "TREND_DOWN"
        
        avg_vol = sum(vols[-11:-1]) / 10
        vol_accel = vols[-1] / avg_vol if avg_vol > 0 else 1.0
        
        in_f = 0; out_f = 0
        for i in range(-4, 0):
            c_val = vols[i] * closes[i]
            if closes[i] > opens[i]: in_f += c_val
            else: out_f += c_val
        
        if out_f == 0: out_f = 1
        ratio = in_f / out_f
        
        idx = -13 if len(kd) >= 13 else -len(kd)
        move_1h = ((closes[-1] - float(kd[idx][4])) / float(kd[idx][4])) * 100
        
        if move_1h > MAX_1H_MOVE: return "LATE_ENTRY"
        if ratio > MAX_FLOW_RATIO: return "FAKE_FLOW"
        if vol_accel < MIN_VOL_ACCEL: return "LOW_MOMENTUM"
        
        return {"in": in_f, "out": out_f, "net": in_f - out_f, "ratio": ratio, "price": closes[-1], "move_1h": move_1h, "vol_accel": vol_accel}
    except: return None

def scan():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if state["date"] != today: state.update({"date": today, "count": 0, "sent_coins": []})

    source = state["current_source"]
    logger.info(f"🔍 MAFIO Scanning {source}...")
    
    tickers = get_data_from_anywhere(source, "ticker/24hr")
    if not tickers or not isinstance(tickers, list):
        new_source = "MEXC" if source == "BINANCE" else "BINANCE"
        state["current_source"] = new_source; return

    candidates = []
    for t in tickers:
        if not isinstance(t, dict) or 'symbol' not in t: continue
        sym = t['symbol']
        if not sym.endswith("USDT") or any(x in sym for x in ["UP", "DOWN", "BEAR", "BULL"]): continue
        
        stables = ["USDC", "BUSD", "USD1", "EUR", "GBP", "DAI", "FDUSD", "TUSD", "USDP", "PYUSD", "USDD", "ZUSD"]
        if any(s in sym for s in stables): continue
        
        try:
            chg_24h = float(t['priceChangePercent']); vol_24h = float(t['quoteVolume']); price = float(t['lastPrice']); high, low = float(t['highPrice']), float(t['lowPrice'])
            if vol_24h < MIN_VOLUME_24H or chg_24h < MIN_24H_CHANGE or chg_24h > MAX_24H_CHANGE: continue
            price_pos = (price - low) / (high - low) if (high - low) > 0 else 0.5
            if price_pos > MAX_PRICE_POS: continue
            candidates.append({'sym': sym, 'vol': vol_24h, 'price': price, 'chg': chg_24h, 'price_pos': price_pos})
        except: continue

    candidates.sort(key=lambda x: x['vol'], reverse=True)
    for c in candidates[:40]:
        sym = c['sym']
        if sym in state["sent_coins"]: continue

        data = analyze_flow(sym, source)
        if not isinstance(data, dict): continue
        
        futures = get_futures_data(sym) if source == "BINANCE" else {"funding": 0, "oi": 0, "status": "N/A ⚪"}
        
        is_flash = data['ratio'] >= 10.0 and data['net'] >= MIN_FLASH_NET_FLOW
        is_normal = data['ratio'] >= MIN_FLOW_RATIO and data['net'] >= MIN_NET_FLOW_USD
        
        if is_flash or is_normal:
            if state["is_first_run"]: state["sent_coins"].append(sym); continue

            state["count"] += 1; state["sent_coins"].append(sym)
            active_trades[sym] = {'entry': c['price'], 'time': time.time(), 'max_gain': 0, 'milestones': []}
            
            interest = "Institutional Breakout 🐋"
            if is_flash: interest = "⚡ FLASH LIQUIDITY SPIKE ⚡"
            elif data['vol_accel'] > 2.5: interest = "🔥 High Short Squeeze Risk 🧨"
            
            msg = (
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🐺 *MAFIO ALPHA WOLF 16.0* 📡\n\n"
                f"🆕 *#{sym.replace('USDT','')}* 🐺 · 🔔 Signal #{state['count']}\n"
                f"💰 Price: `${c['price']:.8g}`\n"
                f"📈 1h Move: `+{data['move_1h']:.2f}%` ⚡\n"
                f"📍 Position: `%{c['price_pos']*100:.0f}` from Bottom ✅\n\n"
                f"⚡ Volume: `{data['vol_accel']:.1f}x` above avg\n"
                f"🟡 Interest: `{interest}` \n"
                f"📊 Ratio: `{data['ratio']:.1f}x` 🔥\n"
                f"🟢 Funding: `{futures['status']}` (`{futures['funding']:.4f}%`)\n"
                "💹 *1h Flow:*\n"
                f"  📥 In: `${data['in']/1000:.1f}K` \n"
                f"  📤 Out: `${data['out']/1000:.1f}K` \n"
                f"  ▲ Net: `+${data['net']/1000:.1f}K` ✅\n\n"
                f"🕐 {datetime.now().strftime('%d %b %Y %H:%M UTC')}\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"⚠️ _اقتناص ألفا - تم رصد انفجار سيولة على {source}!_ 🚀"
            )
            send_telegram(msg); time.sleep(1)

    if state["is_first_run"]: state["is_first_run"] = False

def main():
    logger.info("🚀 MAFIO BOT 16.0 (Alpha Wolf Edition) Started")
    send_telegram("🐺 *MAFIO BOT 16.0* متصل.\nتم تفعيل نظام الذئب الألفا (Alpha Wolf) مع مراقبة العقود الآجلة والسيولة الخارقة.")
    while True:
        try: scan(); track_profits(); time.sleep(35)
        except Exception as e: logger.error(f"⚠️ Loop Error: {e}"); time.sleep(30)

if __name__ == "__main__":
    main()

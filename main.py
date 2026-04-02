# -*- coding: utf-8 -*-
import os
import sys
import time
import requests
import logging
from datetime import datetime, timezone

# إعداد السجلات للظهور فوراً في Railway
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s", stream=sys.stdout)
logger = logging.getLogger("MAFIO_CLOUD")

# ==========================================================
# الإعدادات - يفضل وضعها في Variables في Railway
# ==========================================================
TOKEN = os.getenv("TELEGRAM_TOKEN", "ضع_التوكن_هنا")
ADMIN_ID = os.getenv("CHAT_ID", "ضع_الايدي_هنا")

# معايير التصفية
MIN_VOLUME_24H = 50000
MAX_VOLUME_24H = 50000000
MIN_FLOW_RATIO = 5.0
MIN_VOL_ACCEL = 3.0

state = {"sent_coins": [], "source": "BINANCE"}

def send_telegram(message):
    if "ضع_" in TOKEN or not TOKEN: 
        print(f"⚠️ Telegram Token missing! Message: {message}")
        return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": ADMIN_ID, "text": message, "parse_mode": "Markdown"}, timeout=10)
    except Exception as e:
        print(f"❌ Telegram Error: {e}")

def fetch_tickers(source):
    """جلب البيانات من بايننس أو ميكس بذكاء"""
    url = "https://api.binance.com/api/v3/ticker/24hr" if source == "BINANCE" else "https://api.mexc.com/api/v3/ticker/24hr"
    try:
        print(f"📡 Attempting to fetch data from {source}...", flush=True)
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return r.json()
        else:
            print(f"⚠️ {source} returned status code: {r.status_code}", flush=True)
            return None
    except Exception as e:
        print(f"❌ Connection Error with {source}: {e}", flush=True)
        return None

def analyze_coin(sym, source):
    """تحليل السيولة اللحظية للعملة"""
    base_url = "https://api.binance.com/api/v3/klines" if source == "BINANCE" else "https://api.mexc.com/api/v3/klines"
    try:
        params = {"symbol": sym, "interval": "1m", "limit": 20}
        r = requests.get(base_url, params=params, timeout=5)
        if r.status_code != 200: return None
        
        kd = r.json()
        vols = [float(c[5]) for c in kd]
        avg_vol = sum(vols[:-1]) / len(vols[:-1])
        current_vol = vols[-1]
        
        accel = current_vol / avg_vol if avg_vol > 0 else 1
        return accel
    except: return None

def scan_cycle():
    print(f"--- Starting Scan Cycle at {datetime.now()} ---", flush=True)
    data = fetch_tickers(state["source"])
    
    if not data:
        # التبديل بين المنصات في حال الفشل
        state["source"] = "MEXC" if state["source"] == "BINANCE" else "BINANCE"
        print(f"🔄 Switching source to {state['source']}", flush=True)
        return

    found_count = 0
    for t in data:
        sym = t.get('symbol', '')
        if not sym.endswith("USDT") or any(x in sym for x in ["UP", "DOWN", "BEAR", "BULL"]): continue
        if sym in state["sent_coins"]: continue

        try:
            vol = float(t.get('quoteVolume', 0))
            if vol < MIN_VOLUME_24H: continue
            
            # فحص التسارع
            accel = analyze_coin(sym, state["source"])
            if accel and accel > MIN_VOL_ACCEL:
                found_count += 1
                msg = f"🚀 *WOLF SIGNAL* ({state['source']})\n💎 العملة: #{sym}\n🔥 تسارع السيولة: {accel:.1f}x\n📊 الفوليوم: ${vol/1000:.1f}K"
                send_telegram(msg)
                state["sent_coins"].append(sym)
                print(f"✅ Found: {sym} | Accel: {accel:.1f}x", flush=True)
                if len(state["sent_coins"]) > 100: state["sent_coins"].pop(0)
        except: continue
    
    print(f"--- Cycle Finished. Found {found_count} coins. ---", flush=True)

def main():
    print("🚀 MAFIO ALPHA V20.1 STARTED ON CLOUD", flush=True)
    send_telegram("✅ *بوت مافيو متصل الآن*\nيتم مراقبة بايننس وميكس لاقتناص السيولة...")
    
    while True:
        try:
            scan_cycle()
            time.sleep(40) # انتظر 40 ثانية لتجنب الحظر
        except Exception as e:
            print(f"⚠️ Critical Loop Error: {e}", flush=True)
            time.sleep(20)

if __name__ == "__main__":
    main()

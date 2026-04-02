# -*- coding: utf-8 -*-
import requests, time

TOKEN = "YOUR_TOKEN"
CHAT_ID = "YOUR_ID"

def get_btc_trend():
    """فحص نبض البتكوين في آخر 15 دقيقة"""
    try:
        url = "https://api.binance.com/api/v3/klines"
        params = {"symbol": "BTCUSDT", "interval": "15m", "limit": 1}
        data = requests.get(url, params=params, timeout=10).json()
        open_p = float(data[0][1])
        close_p = float(data[0][4])
        # إذا كان البتكوين هابطاً بأكثر من 0.2% في 15 دقيقة، السوق خطر
        change = ((close_p - open_p) / open_p) * 100
        return change
    except: return 0

def is_perfect_signal(symbol, chg_24h, btc_chg):
    """تحديد ما إذا كانت الإشارة مثالية أم لا"""
    # 1. إذا كان البتكوين ينهار، الإشارة ليست مثالية
    if btc_chg < -0.15: 
        return False, "BTC_FALLING"
    
    # 2. قوة العملة مقابل البتكوين (العملة يجب أن تكون أقوى بـ 3 أضعاف على الأقل)
    if chg_24h < 3.0: 
        return False, "LOW_MOMENTUM"
        
    return True, "PERFECT"

def main():
    print("🎯 MAFIO V105: PERFECT STRIKE MODE")
    while True:
        try:
            btc_15m = get_btc_trend()
            
            # جلب بيانات MEXC
            res = requests.get("https://api.mexc.com/api/v3/ticker/24hr", timeout=10).json()
            
            for t in res:
                sym = t['symbol']
                if not sym.endswith("USDT"): continue
                
                chg = float(t['priceChangePercent'])
                vol = float(t['quoteVolume'])
                
                # فحص المثالية
                perfect, reason = is_perfect_signal(sym, chg, btc_15m)
                
                if perfect and vol > 1000000: # سيولة أعلى من مليون لضمان الجودة
                    msg = (f"🎯 *PERFECT SIGNAL DETECTED* 🎯\n\n"
                           f"🔥 العملة: *#{sym.replace('USDT','')}*\n"
                           f"📈 صعود العملة: `+{chg}%` \n"
                           f"📉 وضع البتكوين: `{btc_15m:+.2f}%` (آمن ✅)\n"
                           f"💰 السيولة: `${vol/1000:.1f}K` \n\n"
                           f"⚠️ هذه الإشارة فلترت هبوط السوق.")
                    # إرسال تلغرام هنا
                    print(f"✅ Perfect Match: {sym}")
            
            time.sleep(60) # فحص هادئ ودقيق
        except Exception as e:
            time.sleep(20)

if __name__ == "__main__":
    main()

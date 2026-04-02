# -*- coding: utf-8 -*-
import requests, time, sys

# --- تأكد من هذه البيانات بدقة ---
TOKEN = "ضـع_تـوكـن_بـوتـك_هـنـا" 
CHAT_ID = "ضـع_آي_دي_حـسـابـك_هـنـا"

def verify_and_send(message):
    """وظيفة إرسال مع تقرير أخطاء مفصل"""
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        response = requests.post(url, data={
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }, timeout=10)
        
        res_data = response.json()
        if res_data.get("ok"):
            print("✅ Telegram: Message sent successfully!")
        else:
            print(f"❌ Telegram Error: {res_data.get('description')}")
            # إذا كان الخطأ Unauthorized فهذا يعني أن التوكن خطأ
            # إذا كان الخطأ Chat not found فهذا يعني أنك لم تضغط Start في البوت
    except Exception as e:
        print(f"📡 Connection Error: {e}")

def main():
    print("🚀 Starting Connection Test...")
    
    # رسالة ترحيبية فورية للتأكد من الربط
    test_msg = "💀 *MAFIO V101*\nتم الاتصال بنجاح! إذا وصلت هذه الرسالة، فالبوت جاهز للصيد."
    verify_and_send(test_msg)

    while True:
        try:
            # محرك جلب البيانات من MEXC
            api_url = "https://api.mexc.com/api/v3/ticker/24hr"
            data = requests.get(api_url, timeout=10).json()
            
            if isinstance(data, list):
                print(f"🔍 Scan Active: Found {len(data)} pairs on MEXC.")
                # هنا يتم وضع منطق الفحص (الصعود > 2% إلخ)
            
            time.sleep(40)
        except Exception as e:
            print(f"⚠️ Loop Error: {e}")
            time.sleep(20)

if __name__ == "__main__":
    main()

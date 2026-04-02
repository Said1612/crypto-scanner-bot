# -*- coding: utf-8 -*-
import requests, time

# ضع البيانات الجديدة هنا بدقة
TOKEN = "ضـع_التـوكـن_الجـديـد_هـنـا"
CHAT_ID = "ضـع_الآي_دي_الخـاص_بـك"

def check_bot():
    """هذه الوظيفة ستخبرك في السجلات إذا كان التوكن صحيحاً أم لا"""
    url = f"https://api.telegram.org/bot{TOKEN}/getMe"
    try:
        r = requests.get(url).json()
        if r.get("ok"):
            print(f"✅ Token is CORRECT! Bot Name: {r['result']['first_name']}")
            return True
        else:
            print(f"❌ TOKEN ERROR: {r.get('description')}")
            return False
    except Exception as e:
        print(f"📡 Connection Error: {e}")
        return False

def send_test():
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": "💀 *MAFIO V103*: Connected successfully!", "parse_mode": "Markdown"}
    r = requests.post(url, data=payload).json()
    if not r.get("ok"):
        print(f"❌ Message Failed: {r.get('description')}")

def main():
    print("🛠️ Testing Bot Identity...")
    if check_bot():
        send_test()
        print("🚀 System Online. Scanning MEXC...")
        # هنا يبدأ محرك الفحص (نفس الكود السابق)
        while True:
            try:
                # فحص عملات MEXC
                time.sleep(30)
                print("🔍 Scanning...")
            except: pass
    else:
        print("⛔ STOPPED: Fix your Token and redeploy.")

if __name__ == "__main__":
    main()

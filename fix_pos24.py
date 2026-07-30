#!/usr/bin/env python3
"""
fix_pos24.py — توحيد وحدة pos24 في signal_history.json

إصدارات قديمة من البوت خزّنت pos24 نسبة مئوية (53.0) بدل كسر (0.53). الإصدار
الحالي يخزّن الكسر في كل المسارات، فالخلل تاريخي لا مستمر — لكنه يُفسد كل تحليل
يقرأ العمود:

  أي سجل بصيغة النسبة يقع تلقائياً فوق 0.85، فظهر في التحليل أن "الدخول عند
  قمة النطاق يربح 82%" بينما الرقم أثر جانبي للوحدة الخاطئة، مضروباً في أن تلك
  السجلات قديمة من فترة سوق صاعد. ومعه انهار كل ما يُحسب من pos24 مثل
  conviction — فبدا منقلباً بشكل مذهل بلا أن يكون ذلك حقيقياً.

الحدّ 1.5: الكسر لا يتجاوز 1.0 إلا بهامش ضئيل (سعر لحظي أعلى من high24)،
والنسبة المئوية تبدأ من 0 إلى 100. القيم بين 1.0 و1.5 غامضة فتُترك كما هي
وتُعرض لك لتقرّر.

USAGE:
  python3 fix_pos24.py            # فحص فقط — لا يكتب شيئاً (الوضع الافتراضي)
  python3 fix_pos24.py --apply    # ينفّذ الإصلاح بعد أخذ نسخة احتياطية
"""
import json
import os
import shutil
import sys
from datetime import datetime, timezone

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "signal_history.json")
THRESHOLD = 1.5          # فوقه = نسبة مئوية بلا شك
AMBIGUOUS = (1.0, 1.5)   # نطاق لا نلمسه


def load():
    with open(DB) as f:
        raw = f.read().strip()
    if raw.startswith("["):
        return json.loads(raw)
    return [json.loads(l) for l in raw.splitlines() if l.strip()]


def main():
    apply_fix = "--apply" in sys.argv

    if not os.path.exists(DB):
        print(f"❌ لم يُعثر على {DB}")
        sys.exit(1)

    db = load()
    pct  = [r for r in db if isinstance(r.get("pos24"), (int, float)) and r["pos24"] > THRESHOLD]
    amb  = [r for r in db if isinstance(r.get("pos24"), (int, float))
            and AMBIGUOUS[0] < r["pos24"] <= AMBIGUOUS[1]]
    frac = [r for r in db if isinstance(r.get("pos24"), (int, float)) and r["pos24"] <= AMBIGUOUS[0]]
    none = [r for r in db if r.get("pos24") is None]

    print(f"\n{'='*62}")
    print(f"  🔧 توحيد وحدة pos24 — {len(db)} سجل")
    print(f"{'='*62}")
    print(f"  كسر سليم (≤ 1.0)        : {len(frac):>4}")
    print(f"  نسبة مئوية (> {THRESHOLD})     : {len(pct):>4}   ← تحتاج القسمة على 100")
    print(f"  غامضة ({AMBIGUOUS[0]}–{AMBIGUOUS[1]})        : {len(amb):>4}   ← تُترك كما هي")
    print(f"  بلا قيمة                : {len(none):>4}")

    if amb:
        print(f"\n  ⚠️  السجلات الغامضة (راجعها بنفسك):")
        for r in amb[:10]:
            print(f"      {r.get('sym','?'):<12} pos24={r['pos24']}  {r.get('date','')}")

    if not pct:
        print("\n  ✅ لا شيء لإصلاحه — كل القيم بصيغة الكسر.\n")
        return

    print(f"\n  أمثلة على ما سيُصلَح:")
    for r in pct[:8]:
        print(f"      {r.get('sym','?'):<12} {r['pos24']:>7} → {round(r['pos24']/100.0, 4)}"
              f"   ({r.get('date','')})")

    if not apply_fix:
        print(f"\n  🔍 فحص فقط — لم يُكتب شيء.")
        print(f"     للتنفيذ: python3 fix_pos24.py --apply\n")
        return

    stamp  = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup = f"{DB}.bak_{stamp}"
    shutil.copy2(DB, backup)
    print(f"\n  💾 نسخة احتياطية: {os.path.basename(backup)}")

    for r in pct:
        r["pos24"] = round(r["pos24"] / 100.0, 4)

    tmp = DB + ".tmp"
    with open(tmp, "w") as f:
        json.dump(db, f, ensure_ascii=False)
    os.replace(tmp, DB)          # ذرّي — لا يترك الملف نصف مكتوب لو تعطّل

    print(f"  ✅ أُصلح {len(pct)} سجل.")
    print(f"\n  أعد التحليل الآن — وتوقّع أن تتغيّر نتائج pos24 و conviction:")
    print(f"     python3 analyze_signals.py\n")


if __name__ == "__main__":
    main()

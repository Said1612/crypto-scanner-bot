#!/usr/bin/env python3
"""
loser_dna.py — لماذا تخسر الإشارات الخاسرة؟ (تصنيف أنماط الفشل)

حلّلنا الوحوش (explosion_dna). هذه الأداة تقلب العدسة: تأخذ كل إشارة خاسرة
وتصنّفها حسب **سبب الفشل**، فنعرف أيّ نمط هو الأكثر تكراراً — وبالتالي أين نركّز.

أنماط الفشل (يُفحَص بالترتيب، أول تطابق يفوز، فالمجموع 100%):
  1. قمة ثم وقف  — بلغت +5% ثم انعكست وضربت الوقف (فشل إدارة، لا دخول → وقف متحرّك).
  2. ازدحام مرهق — L/S >= 2.5 و OI غير متمدّد (longs محشورون بلا وقود).
  3. Ratio خرافي — Ratio >= 8 (شراء وهمي/توزيع).
  4. سوق ضعيف   — market_bias <= -10 (دخول في تاپ سيّئ).
  5. سكين هابط   — pos24 < 0.40 (قاع، دخول مبكّر جداً، واصلت الهبوط).
  6. مطاردة قمة  — pos24 > 0.80 (دخول متأخر فوق القمة).
  7. أخرى         — لا نمط واضح.

USAGE (على الـ VPS):
  python3 loser_dna.py

قراءة فقط — لا يعدّل البوت ولا أي ملف.
"""
import json
import os
from collections import Counter
from statistics import median

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "signal_history.json")
_SL = ("stoploss", "peak_then_sl")


def _closed_on_stop(r):
    return r.get("outcome") in _SL or r.get("close_reason") == "stoploss"


def load():
    with open(DB) as f:
        raw = f.read().strip()
    return json.loads(raw) if raw.startswith("[") else [json.loads(l) for l in raw.splitlines() if l.strip()]


def _classify(r):
    pos  = r.get("pos24")
    ratio = r.get("ratio") or 0
    ls   = r.get("ls_ratio")
    bias = r.get("market_bias")
    oi   = r.get("oi_delta") or 0
    peak = r.get("max_gain_pct") or 0

    if r.get("outcome") == "peak_then_sl" or peak >= 5.0:
        return "قمة ثم وقف (إدارة)"
    if ls is not None and ls >= 2.5 and oi <= 2:
        return "ازدحام مرهق"
    if ratio >= 8:
        return "Ratio خرافي (توزيع)"
    if bias is not None and bias <= -10:
        return "سوق ضعيف"
    if pos is not None and pos < 0.40:
        return "سكين هابط (قاع)"
    if pos is not None and pos > 0.80:
        return "مطاردة قمة"
    return "أخرى"


def _med(rows, key):
    vals = [r.get(key) for r in rows if isinstance(r.get(key), (int, float))]
    return median(vals) if vals else None


def main():
    if not os.path.exists(DB):
        print(f"❌ لم يُعثر على {DB}"); return
    db = load()

    losers = [r for r in db
              if r.get("outcome", "active") != "active"
              and _closed_on_stop(r)]

    print("\n" + "=" * 64)
    print("  💀 لماذا تخسر الإشارات؟ — تصنيف أنماط الفشل")
    print("=" * 64)
    if not losers:
        print("  لا خاسرين في السجل.\n"); return
    print(f"  إجمالي الخاسرين: {len(losers)}")

    cats = Counter(_classify(r) for r in losers)
    print(f"\n  {'نمط الفشل':<24} {'عدد':>5} {'نسبة':>7}")
    print("  " + "─" * 42)
    for cat, n in cats.most_common():
        bar = "█" * int(n / len(losers) * 30)
        print(f"  {cat:<24} {n:>5} {n/len(losers)*100:>6.0f}%  {bar}")

    # متوسط خسارة كل نمط (من السعر)
    print(f"\n  ── متوسط أقصى نزول لكل نمط (max_drawdown) ──")
    by_cat = {}
    for r in losers:
        by_cat.setdefault(_classify(r), []).append(r)
    for cat, rows in sorted(by_cat.items(), key=lambda x: -len(x[1])):
        dd = _med(rows, "max_drawdown_pct")
        pk = _med(rows, "max_gain_pct")
        print(f"     {cat:<24} نزول وسيط {dd if dd is not None else '—'}  ·  بلغ قمة {pk if pk is not None else '—'}%")

    print("\n" + "=" * 64)
    print("  القراءة:")
    print("  • «قمة ثم وقف» كبيرة  → المشكلة إدارة الخروج (وقف متحرّك)، لا الدخول.")
    print("  • «سكين هابط» كبيرة   → تجنّب pos<0.40 (الدخول عند القاع).")
    print("  • «سوق ضعيف» كبيرة    → market_bias يعمل، والخسائر من تاپ سيّئ.")
    print("  • «ازدحام/Ratio» كبيرة → الدرجة تعاقبها أصلاً؛ نتحقّق أنها LOW.")
    print("  النمط الأكبر = حيث نركّز التحسين القادم.")
    print("=" * 64 + "\n")


if __name__ == "__main__":
    main()

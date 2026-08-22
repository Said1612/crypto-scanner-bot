#!/usr/bin/env python3
"""
grade_vs_outcome.py — هل تتنبّأ درجة SETUP بالنتيجة فعلاً؟ (تحقّق من الميزة)

أضفنا سطر 📋 SETUP (v3.7.27/28) يصنّف كل إشارة A+/GOOD/MODERATE/LOW من جداول
النجاح. لكن التصنيف يبقى ادّعاءً حتى نقيسه على النتائج الفعلية. هذه الأداة تعيد
حساب الدرجة لكل إشارة مغلقة من الحقول المحفوظة، ثم تعرض نسبة الفوز ومتوسط القمة
لكل مستوى. لو كانت الميزة حقيقية، يجب أن تنزل نسبة الفوز: A+ > GOOD > MODERATE > LOW.

ملاحظة: ls_ratio غير محفوظ في السجل بعد، فعامل الازدحام يُتجاوَز هنا (يُعاد حسابه
بـ None). الدرجة المُعاد حسابها تعتمد على Ratio/pos24/Net/المسار/FCF — خمسة من ستة.

USAGE (على الـ VPS):
  python3 grade_vs_outcome.py

قراءة فقط — لا يعدّل البوت ولا أي ملف.
"""
import json
import os

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "signal_history.json")

_SL_CLOSED = ("stoploss", "peak_then_sl")


def _closed_on_stop(r):
    return r.get("outcome") in _SL_CLOSED or r.get("close_reason") == "stoploss"


def _is_clean_win(r):
    if r.get("outcome") == "stoploss_recovered":
        return True
    return not _closed_on_stop(r) and (r.get("max_gain_pct") or 0.0) >= 5.0


def _grade(ratio, pos24, net, scanner, ls_ratio=None, fcf=None):
    """نسخة مطابقة لـ _setup_grade في main.py (v3.7.28) — تُعيد اسم المستوى فقط."""
    pts = 0
    if ratio < 1.5:      pts += 3
    elif ratio < 2.0:    pts += 2
    elif ratio < 3.0:    pts += 1
    elif 10.0 <= ratio < 20.0: pts -= 3
    elif ratio >= 5.0:   pts -= 1

    if 0.40 <= pos24 <= 0.65: pts += 2
    elif 0.65 < pos24 <= 0.75: pts += 1
    elif pos24 < 0.40:   pts -= 1

    if scanner in ("main", "supertrend"): pts += 2
    elif scanner == "volume_explosion":   pts += 1
    elif scanner in ("moonshot", "momentum"): pts -= 1

    if 5_000 <= net <= 30_000: pts += 1
    elif net > 100_000:        pts -= 1

    if ls_ratio is not None:
        if ls_ratio >= 2.5:   pts -= 3
        elif ls_ratio >= 1.8: pts -= 1
    if fcf is not None and fcf < 0.80: pts -= 1

    capped = ls_ratio is not None and ls_ratio >= 2.5
    if pts >= 5 and not capped:   return "A+"
    if pts >= 3 and not capped:   return "GOOD"
    if pts >= 1:                  return "MODERATE"
    return "LOW"


def load():
    with open(DB) as f:
        raw = f.read().strip()
    return json.loads(raw) if raw.startswith("[") else [json.loads(l) for l in raw.splitlines() if l.strip()]


def main():
    if not os.path.exists(DB):
        print(f"❌ لم يُعثر على {DB}"); return
    db = load()

    buckets = {"A+": [], "GOOD": [], "MODERATE": [], "LOW": []}
    for r in db:
        if r.get("outcome", "active") == "active":
            continue
        ratio = r.get("ratio")
        net   = r.get("net_usd")
        pos   = r.get("pos24")
        scan  = r.get("scanner") or "main"
        if ratio is None or net is None or pos is None:
            continue
        tier = _grade(ratio, pos, net, scan, ls_ratio=None, fcf=r.get("fcf"))
        buckets[tier].append(r)

    print("\n" + "=" * 66)
    print("  📋 هل تتنبّأ درجة SETUP بالنتيجة؟ — تحقّق على السجل المغلق")
    print("=" * 66)
    print(f"  {'الدرجة':<12} {'عدد':>5} {'فوز نظيف':>10} {'متوسط القمة':>14}")
    print("  " + "─" * 48)

    prev = None
    monotonic = True
    for tier in ("A+", "GOOD", "MODERATE", "LOW"):
        rs = buckets[tier]
        n  = len(rs)
        if not n:
            print(f"  {tier:<12} {0:>5}   — لا إشارات")
            continue
        wins = sum(1 for r in rs if _is_clean_win(r))
        wr   = wins / n * 100
        peaks = [r.get("max_gain_pct") or 0.0 for r in rs]
        avg_pk = sum(peaks) / len(peaks)
        bar = "█" * int(wr / 5)
        print(f"  {tier:<12} {n:>5} {wr:>8.0f}% {avg_pk:>+12.1f}%  {bar}")
        if prev is not None and wr > prev + 3:
            monotonic = False   # درجة أدنى فازت أكثر من أعلى منها
        prev = wr

    print("\n" + "=" * 66)
    if monotonic:
        print("  ✅ الترتيب صحيح: نسبة الفوز تنزل من A+ نزولاً. الدرجة تتنبّأ فعلاً.")
    else:
        print("  ⚠️ الترتيب غير نظيف: درجة أدنى فازت أكثر من أعلى منها.")
        print("     إمّا العيّنة صغيرة بعد، أو أحد الأوزان يحتاج ضبطاً بالبيانات.")
    print("     القاعدة: نحكم على الميزة بعد ~30 إشارة مغلقة لكل درجة، لا أقل.")
    print("=" * 66 + "\n")


if __name__ == "__main__":
    main()

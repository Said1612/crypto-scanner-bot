#!/usr/bin/env python3
"""
momentum_watch.py — هل صمد عائد مسار الزخم بعد فتحه؟

عائد مسار momentum المقيس (+5.2% لكل إشارة) جاء من 23 إشارة **مُنتقاة** مرّت كل
البوابات قبل إصلاح v3.7.16-3.7.19. بعد الفتح، يمرّ عدد أكبر وأقل انتقاءً — فقد
يختلف العائد. هذه الأداة تفصل الإشارات قبل/بعد تاريخ الإصلاح لتقيس ذلك مباشرة،
بدل الاعتماد على عيّنة قديمة.

القاعدة: لا يُحكَم على مسار بنسبة نجاحه — بل بعائده المتوقّع، لأن الأرباح الكبيرة
تأتي من ذيل نادر. مسار بنسبة 26% وربح وسطي +40% يتفوّق على مسار بنسبة 60% و+5%.

USAGE (على الـ VPS):
  python3 momentum_watch.py                 # القطع الافتراضي 2026-08-01
  python3 momentum_watch.py 2026-08-01      # اختر تاريخ فتح المسار
  python3 momentum_watch.py 2026-08-01 main # راقب ماسحاً آخر

قراءة فقط — لا يعدّل البوت ولا أي ملف.
"""
import json
import os
import sys
from statistics import median

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "signal_history.json")
CUTOFF  = sys.argv[1] if len(sys.argv) > 1 else "2026-08-01"
SCANNER = sys.argv[2] if len(sys.argv) > 2 else "momentum"

_SL_CLOSED = ("stoploss", "peak_then_sl")


def _closed_on_stop(r):
    return r.get("outcome") in _SL_CLOSED or r.get("close_reason") == "stoploss"


def _is_clean_win(r):
    """بلغ +5% ولم يُغلق على وقف — نفس منطق ai_agent."""
    if r.get("outcome") == "stoploss_recovered":
        return True
    return not _closed_on_stop(r) and (r.get("max_gain_pct") or 0.0) >= 5.0


def _realized(r):
    """الربح المحقّق فعلاً عند الإغلاق من سعرَي الدخول والخروج."""
    e, x = r.get("price_entry"), r.get("price_exit")
    if not e or not x or e <= 0:
        return None
    return (x - e) / e * 100.0


def _avg(xs):
    xs = [v for v in xs if v is not None]
    return sum(xs) / len(xs) if xs else None


def _stats(rows, label):
    closed = [r for r in rows if r.get("outcome", "active") != "active"]
    if not closed:
        print(f"\n  {label}: لا إشارات مغلقة بعد.")
        return
    n     = len(closed)
    wins  = sum(1 for r in closed if _is_clean_win(r))
    peaks = [r.get("max_gain_pct") for r in closed if r.get("max_gain_pct") is not None]
    real  = [v for v in (_realized(r) for r in closed) if v is not None]
    # EV بالحمل حتى الإغلاق، وEV لو اقتُنص نصف القمة على الرابحين
    half = []
    for r in closed:
        pk, rl = r.get("max_gain_pct"), _realized(r)
        if pk and pk > 0:
            half.append(pk * 0.5)
        elif rl is not None:
            half.append(rl)
    ev_hold = _avg(real)
    ev_half = _avg(half)
    best    = max(peaks) if peaks else 0.0
    _f = lambda v: f"{v:+.1f}%" if v is not None else "—"
    print(f"\n  {label}  (n={n} مغلقة، {len(rows)-n} نشطة)")
    print(f"    فوز نظيف   : {wins}/{n} = {wins/n*100:.0f}%")
    print(f"    وسيط القمة : {_f(median(peaks) if peaks else None)}")
    print(f"    EV حمل     : {_f(ev_hold)}   ← يُحكَم عليه بهذا")
    print(f"    EV نصف قمة : {_f(ev_half)}   (بالوقف المتحرّك)")
    print(f"    أفضل       : {best:+.0f}%")
    return ev_hold


def main():
    if not os.path.exists(DB):
        print(f"❌ لم يُعثر على {DB}"); return
    with open(DB) as f:
        raw = f.read().strip()
    db = json.loads(raw) if raw.startswith("[") else [json.loads(l) for l in raw.splitlines() if l.strip()]

    mine = [r for r in db if r.get("scanner") == SCANNER]
    pre  = [r for r in mine if (r.get("date") or "") < CUTOFF]
    post = [r for r in mine if (r.get("date") or "") >= CUTOFF]

    print("\n" + "=" * 64)
    print(f"  📡 متتبّع مسار '{SCANNER}' — قبل/بعد {CUTOFF}")
    print("=" * 64)
    print(f"  إجمالي إشارات المسار: {len(mine)}  ({len(pre)} قبل · {len(post)} بعد)")

    ev_pre  = _stats(pre,  f"⏮️  قبل الإصلاح")
    ev_post = _stats(post, f"⏭️  بعد الإصلاح")

    # قائمة إشارات ما بعد الإصلاح — الشاهد الحيّ
    post_sorted = sorted(post, key=lambda r: r.get("date") or "")
    if post_sorted:
        print(f"\n  📋 إشارات ما بعد الإصلاح:")
        print(f"    {'عملة':<12} {'التاريخ':<12} {'أعلى':>7} {'نزول':>7}  النتيجة")
        print("    " + "─" * 52)
        for r in post_sorted[-25:]:
            sym = (r.get("sym", "?")).replace("USDT", "")
            dt  = (r.get("date") or "")[:10]
            pk  = r.get("max_gain_pct")
            dd  = r.get("max_drawdown_pct")
            out = r.get("outcome", "active")
            ico = ("✅" if _is_clean_win(r) else
                   "🛑" if (_closed_on_stop(r) and (pk or 0) >= 5) else
                   "⏳" if out == "active" else "❌")
            _pk = f"{pk:+.0f}%" if pk is not None else "—"
            _dd = f"{dd:.0f}%" if dd is not None else "—"
            print(f"    {sym:<12} {dt:<12} {_pk:>7} {_dd:>7}  {ico} {out}")

    print("\n" + "=" * 64)
    if ev_pre is not None and ev_post is not None:
        if ev_post >= ev_pre - 1.0:
            print(f"  ✅ العائد صمد: قبل {ev_pre:+.1f}% → بعد {ev_post:+.1f}%")
            print("     فتح المسار لم يُضعِف جودته — قرار الفتح مثبت.")
        else:
            print(f"  ⚠️ العائد تراجع: قبل {ev_pre:+.1f}% → بعد {ev_post:+.1f}%")
            print("     الحجم الأكبر خفّف الجودة — قد نحتاج شرطاً إضافياً.")
    else:
        print("  ⏳ إشارات ما بعد الإصلاح قليلة بعد — عُد بعد ~15 إشارة مغلقة.")
    print("     القاعدة: نقرّر على هذا الرقم بعد أن يتراكم، لا على مثال واحد.")
    print("=" * 64 + "\n")


if __name__ == "__main__":
    main()

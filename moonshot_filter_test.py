#!/usr/bin/env python3
"""
moonshot_filter_test.py — هل يستحق تشديد فلتر الـ Moonshot؟ (اختبار على السجل)

MANTRA مرّت كـ moonshot (spike 15.9x) ثم انهارت: FCF 0.98 (تحت 1، فوق أرضية
0.60) + صافي +50.7K على انفجار 16x = churn لا تراكم. السؤال ليس "هل نحجبها" —
بل: لو شدّدنا الفلتر، كم خاسراً كنا سنمنع مقابل كم رابحاً كنا سنقتل بالخطأ؟

القاعدة: لا يُفعَّل فلتر لأنه يمنع مثالاً واحداً. يُفعَّل إن منع خاسرين كثيرين
وقتل رابحين قليلين. هذه الأداة تحسب هذه المقايضة لكل عتبة مرشّحة.

تعيد بناء is_moonshot من الحقول المخزّنة (نفس معادلة main.py بالضبط) لأن الراية
لا تُحفَظ في السجل — لكن price_entry/spike/net_usd/pos24 كلها محفوظة.

USAGE (على الـ VPS):
  python3 moonshot_filter_test.py

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


def _is_moonshot(r):
    """نفس معادلة main.py (السطر ~3190) مُعاد بناؤها من الحقول المخزّنة."""
    price = r.get("price_entry") or 0.0
    spike = r.get("spike") or 0.0
    net   = r.get("net_usd") or 0.0
    pos   = r.get("pos24")
    if pos is None:
        return False
    low_price_moon = (price < 0.25 and spike >= 10.0 and net > 20_000 and pos < 0.50)
    return (
        (net > 500_000 and pos < 0.60) or
        (pos < 0.10 and net > 60_000) or
        low_price_moon
    )


def load():
    with open(DB) as f:
        raw = f.read().strip()
    if raw.startswith("["):
        return json.loads(raw)
    return [json.loads(l) for l in raw.splitlines() if l.strip()]


def _confusion(moons, keep_pred):
    """keep_pred(r)=True يعني الفلتر يُبقي الإشارة. نقيس ما يُحجَب."""
    blocked_losers = [r for r in moons if not keep_pred(r) and _closed_on_stop(r)]
    killed_wins    = [r for r in moons if not keep_pred(r) and _is_clean_win(r)]
    kept_losers    = [r for r in moons if keep_pred(r) and _closed_on_stop(r)]
    kept_wins      = [r for r in moons if keep_pred(r) and _is_clean_win(r)]
    return blocked_losers, killed_wins, kept_losers, kept_wins


def _syms(rs, n=6):
    out = [(r.get("sym", "?")).replace("USDT", "") for r in rs]
    return ", ".join(out[:n]) + (" …" if len(out) > n else "")


def main():
    if not os.path.exists(DB):
        print(f"❌ لم يُعثر على {DB}"); return
    db = load()

    moons = [r for r in db
             if _is_moonshot(r) and r.get("outcome", "active") != "active"]
    closed_with_fcf = [r for r in moons if r.get("fcf") is not None]

    print("\n" + "=" * 70)
    print("  🚀 اختبار تشديد فلتر الـ Moonshot على السجل التاريخي")
    print("=" * 70)
    n = len(moons)
    if not n:
        print("  لا إشارات moonshot مغلقة في السجل بعد — عُد لاحقاً.\n"); return
    wins  = [r for r in moons if _is_clean_win(r)]
    losrs = [r for r in moons if _closed_on_stop(r)]
    print(f"  إجمالي moonshots مغلقة : {n}")
    print(f"    فوز نظيف  : {len(wins)}  ({len(wins)/n*100:.0f}%)")
    print(f"    خاسرة/وقف : {len(losrs)}  ({len(losrs)/n*100:.0f}%)")
    print(f"    منها بقيمة FCF مسجّلة : {len(closed_with_fcf)}")

    # ── اختبار 1: أرضية FCF ──────────────────────────────────────────────
    # الحالية 0.60. نجرّب رفعها. الإشارات بلا FCF تُعتبر ماضية (لا نحكم عليها).
    print("\n  ── اختبار (1): رفع أرضية FCF للـ moonshot ──")
    print(f"     الحالية = 0.60.  MANTRA كانت FCF=0.98")
    print(f"     {'عتبة':>6} {'يمنع خاسرين':>13} {'يقتل رابحين':>13}   الحكم")
    print("     " + "─" * 60)
    for thr in (0.60, 0.70, 0.80, 0.90, 1.00, 1.10):
        keep = lambda r, t=thr: (r.get("fcf") is None) or (r["fcf"] > t)
        bl, kw, _, _ = _confusion(closed_with_fcf, keep)
        ratio = (len(bl) / len(kw)) if kw else (float("inf") if bl else 0.0)
        verdict = ("✅ ممتاز" if ratio >= 3 else
                   "🟡 مقبول" if ratio >= 1.5 else
                   "⛔ يقتل رابحين" if kw else "— بلا أثر")
        rtxt = "∞" if ratio == float("inf") else f"{ratio:.1f}:1"
        print(f"     ≤{thr:>4.2f}  {len(bl):>10}    {len(kw):>10}     {verdict} ({rtxt})")
    # تفصيل عند 1.0 — العتبة التي تلتقط MANTRA
    keep10 = lambda r: (r.get("fcf") is None) or (r["fcf"] > 1.0)
    bl, kw, _, _ = _confusion(closed_with_fcf, keep10)
    if bl:
        print(f"\n     عند FCF≤1.0 — خاسرون سيُمنعون: {_syms(bl)}")
    if kw:
        print(f"     ⚠️ عند FCF≤1.0 — رابحون سيُقتلون: {_syms(kw)}")

    # ── اختبار 2: churn = صافي مقابل الـ spike ────────────────────────────
    # انفجار كبير بصافي ضئيل = تقليب. net_usd/spike تقريب متاح من المخزّن.
    print("\n  ── اختبار (2): churn — صافي منخفض مقابل spike مرتفع ──")
    print(f"     نحجب فقط عند spike≥12x + صافي/spike منخفض (MANTRA: 50.7K/15.9≈3.2K)")
    print(f"     {'صافي/spike ≤':>13} {'يمنع خاسرين':>13} {'يقتل رابحين':>13}")
    print("     " + "─" * 58)
    hi_spike = [r for r in moons if (r.get("spike") or 0) >= 12.0]
    print(f"     (moonshots بـ spike≥12x: {len(hi_spike)})")
    for floor in (2_000, 4_000, 6_000, 10_000):
        def keep(r, f=floor):
            sp = r.get("spike") or 0
            nt = r.get("net_usd") or 0
            if sp < 12.0:
                return True                     # لا يخضع للفلتر
            return (nt / sp) > f
        bl, kw, _, _ = _confusion(hi_spike, keep)
        print(f"     {floor:>10}$   {len(bl):>10}    {len(kw):>10}")

    print("\n" + "=" * 70)
    print("  القراءة: اختر العتبة التي 'تمنع خاسرين' ≫ 'تقتل رابحين' (نسبة ≥ 3:1).")
    print("  لو كل العتبات تقتل رابحين بقدر ما تمنع → المشكلة ليست FCF، والفلتر خطأ.")
    print("  عندها الوسم الحالي (QUICK GRAB) هو العلاج الصحيح: نُبقيها كاقتناص، لا نحجبها.")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()

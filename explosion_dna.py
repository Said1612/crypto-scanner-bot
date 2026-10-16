#!/usr/bin/env python3
"""
explosion_dna.py — ما هو الحمض النووي للانفجار؟ (دراسة الوحوش)

لائحة الوحوش (CHIP +340%, DAM +277%, PROM +77%, ...) محفوظة في signal_history.json
بكل مقاييسها لحظة الإشارة. هذه الأداة تستخرج بصمتها المشتركة، وتجيب على السؤال
الذي يهمّ لبناء كشف ما-قبل-الانفجار:

  1. عند أي pos24 التُقطت؟  → هل مبكراً (قاع) أم متأخراً (قمة)؟
  2. هل OI كان يتمدّد؟        → المؤشّر القائد: مال آجل يتموضع قبل البامب.
  3. أي scanner اصطادها؟      → من يمسك الوحوش فعلاً؟
  4. Ratio / spike / net / FCF → البصمة الرقمية.

ثم تقارن الوحوش بالخاسرين لتُظهر ما هو **مميِّز** (لا ما هو مشترك بين الكل).

USAGE (على الـ VPS):
  python3 explosion_dna.py            # الوحوش = max_gain >= 30%
  python3 explosion_dna.py 50         # ارفع العتبة إلى +50%

قراءة فقط — لا يعدّل البوت ولا أي ملف.
"""
import json
import os
import sys
from statistics import median

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "signal_history.json")
THR = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0

_SL = ("stoploss", "peak_then_sl")


def _closed_on_stop(r):
    return r.get("outcome") in _SL or r.get("close_reason") == "stoploss"


def load():
    with open(DB) as f:
        raw = f.read().strip()
    return json.loads(raw) if raw.startswith("[") else [json.loads(l) for l in raw.splitlines() if l.strip()]


def _med(rows, key):
    vals = [r.get(key) for r in rows if isinstance(r.get(key), (int, float))]
    return median(vals) if vals else None


def _pct(rows, pred):
    rows = [r for r in rows if r is not None]
    if not rows:
        return 0.0
    return sum(1 for r in rows if pred(r)) / len(rows) * 100


def _dist(rows, key, bands, labels):
    """توزيع نسبي عبر نطاقات."""
    vals = [r.get(key) for r in rows if isinstance(r.get(key), (int, float))]
    if not vals:
        return "—"
    out = []
    for (lo, hi), lab in zip(bands, labels):
        n = sum(1 for v in vals if lo <= v < hi)
        out.append(f"{lab}:{n/len(vals)*100:.0f}%")
    return "  ".join(out)


def _scanner_mix(rows):
    from collections import Counter
    c = Counter(r.get("scanner") or "?" for r in rows)
    tot = sum(c.values())
    return "  ".join(f"{k} {v/tot*100:.0f}%" for k, v in c.most_common(6))


def _f(v, suf="", mul=1.0):
    return f"{v*mul:.2f}{suf}" if isinstance(v, (int, float)) else "—"


def main():
    if not os.path.exists(DB):
        print(f"❌ لم يُعثر على {DB}"); return
    db = load()
    closed = [r for r in db if r.get("outcome", "active") != "active"]

    monsters = [r for r in closed if (r.get("max_gain_pct") or 0) >= THR]
    losers   = [r for r in closed if _closed_on_stop(r) and (r.get("max_gain_pct") or 0) < 10]

    print("\n" + "=" * 68)
    print(f"  🧬 الحمض النووي للانفجار — الوحوش (max_gain ≥ {THR:.0f}%)")
    print("=" * 68)
    print(f"  وحوش: {len(monsters)}   ·   خاسرون (للمقارنة): {len(losers)}")
    if not monsters:
        print("  لا وحوش في السجل بعد.\n"); return

    # تقسيم حسب حجم الانفجار
    tiers = [("30–50%", 30, 50), ("50–100%", 50, 100), ("100%+", 100, 1e9)]
    print("\n  ── البصمة حسب حجم الانفجار ──")
    print(f"  {'الفئة':<10} {'عدد':>4} {'pos وسيط':>9} {'ratio':>7} {'spike':>7} {'net$ وسيط':>11} {'OI وسيط':>8}")
    print("  " + "─" * 62)
    for lab, lo, hi in tiers:
        g = [r for r in monsters if lo <= (r.get("max_gain_pct") or 0) < hi]
        if not g:
            continue
        print(f"  {lab:<10} {len(g):>4} {_f(_med(g,'pos24')):>9} "
              f"{_f(_med(g,'ratio')):>7} {_f(_med(g,'spike')):>7} "
              f"{str(int(_med(g,'net_usd') or 0)):>11} {_f(_med(g,'oi_delta'),'%'):>8}")

    # السؤال الأهم: متى التُقطت؟ (pos24)
    print("\n  ── 1) متى التُقطت؟ توزيع pos24 (قاع=مبكر، قمة=متأخر) ──")
    bands  = [(0.0, 0.40), (0.40, 0.65), (0.65, 0.85), (0.85, 2.0)]
    labels = ["قاع<0.40", "ذهبي0.40-0.65", "0.65-0.85", "قمة>0.85"]
    print(f"     الوحوش : {_dist(monsters, 'pos24', bands, labels)}")
    print(f"     الخاسرون: {_dist(losers,   'pos24', bands, labels)}")

    # 2) OI — المؤشّر القائد
    print("\n  ── 2) OI لحظة الإشارة (expanding = مال آجل يتموضع) ──")
    print(f"     الوحوش   : متمدّد(>2%) {_pct(monsters, lambda r: (r.get('oi_delta') or 0) > 2):.0f}%  "
          f"· وسيط {_f(_med(monsters,'oi_delta'),'%')}")
    print(f"     الخاسرون : متمدّد(>2%) {_pct(losers,   lambda r: (r.get('oi_delta') or 0) > 2):.0f}%  "
          f"· وسيط {_f(_med(losers,'oi_delta'),'%')}")

    # 3) أي scanner
    print("\n  ── 3) أي scanner اصطاد الوحوش؟ ──")
    print(f"     {_scanner_mix(monsters)}")

    # 4) البصمة الرقمية: وحوش مقابل خاسرين
    print("\n  ── 4) البصمة الرقمية (وسيط): وحش ضدّ خاسر ──")
    print(f"     {'المقياس':<14} {'وحش':>12} {'خاسر':>12}")
    for key, lab, mul, suf in [
        ("ratio", "Ratio", 1, "x"), ("pos24", "pos24", 1, ""),
        ("spike", "spike", 1, "x"), ("net_usd", "Net $", 1, ""),
        ("fcf", "FCF", 1, ""), ("ls_ratio", "L/S", 1, ""),
        ("move_pct", "move", 1, "%"), ("ob_spot", "orderbook", 1, ""),
    ]:
        mv, lv = _med(monsters, key), _med(losers, key)
        mv_s = str(int(mv)) if key == "net_usd" and mv else _f(mv, suf, mul)
        lv_s = str(int(lv)) if key == "net_usd" and lv else _f(lv, suf, mul)
        print(f"     {lab:<14} {mv_s:>12} {lv_s:>12}")

    print("\n" + "=" * 68)
    print("  اقرأ العمود: أي مقياس يختلف بوضوح بين الوحش والخاسر = جزء من السرّ.")
    print("  وتوزيع pos24 يقول: هل البوت يصطاد الوحوش مبكراً (قاع/ذهبي) أم متأخراً.")
    print("  إن كانت أغلب الوحوش التُقطت عند pos منخفض + OI متمدّد → تلك بصمة")
    print("  ما-قبل-الانفجار التي نبنيها في scan_quiet_buildup.")
    print("=" * 68 + "\n")


if __name__ == "__main__":
    main()

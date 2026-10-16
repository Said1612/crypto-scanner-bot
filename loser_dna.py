#!/usr/bin/env python3
"""
loser_dna.py — بصمة الدخول الفاشل فعلاً (ما ضرب الوقف دون بلوغ +WIN%)

تصحيح المالك: إشارة تبلغ +13% ثم تنعكس = رابحة (فوق 10%)، لا خاسرة. الخاسر
الحقيقي = ما ضرب الوقف **دون أن يصل أبداً إلى +WIN%** (افتراضياً 10%). هذه هي
الدخولات الفاشلة التي يجب أن نعرف بصمتها ونتجنّبها.

تفصل:
  🏆 رابح (بلغ ≥ WIN% ثم أياً كان) — ليس موضوعنا.
  💀 خاسر حقيقي (ضرب الوقف ولم يبلغ WIN% قط) — نحلّل بصمته.

ثم: أنماط فشل الدخول · البصمة الرقمية (خاسر حقيقي ضدّ رابح) · أي درجة SETUP
نالها (هل البوت يحذّر منها أصلاً؟).

USAGE:
  python3 loser_dna.py          # عتبة الربح 10%
  python3 loser_dna.py 10 30    # ربح ≥10%، الرابح للمقارنة ≥30%

قراءة فقط.
"""
import json
import os
import sys
from collections import Counter
from statistics import median

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "signal_history.json")
WIN  = float(sys.argv[1]) if len(sys.argv) > 1 else 10.0
WINREF = float(sys.argv[2]) if len(sys.argv) > 2 else 30.0
_SL = ("stoploss", "peak_then_sl")


def _stopped(r):
    return r.get("outcome") in _SL or r.get("close_reason") == "stoploss"


def load():
    with open(DB) as f:
        raw = f.read().strip()
    return json.loads(raw) if raw.startswith("[") else [json.loads(l) for l in raw.splitlines() if l.strip()]


def _classify(r):
    """نمط فشل الدخول — لِمَ لم تتحرّك أبداً؟"""
    pos  = r.get("pos24")
    ratio = r.get("ratio") or 0
    ls   = r.get("ls_ratio")
    bias = r.get("market_bias")
    oi   = r.get("oi_delta") or 0
    peak = r.get("max_gain_pct") or 0

    if peak < 2.0:
        return "ضربت فوراً (لم تتحرّك <2%)"
    if ls is not None and ls >= 2.5 and oi <= 2:
        return "ازدحام مرهق (L/S≥2.5)"
    if ratio >= 8:
        return "Ratio خرافي ≥8 (توزيع)"
    if bias is not None and bias <= -10:
        return "سوق ضعيف (bias≤-10)"
    if pos is not None and pos < 0.40:
        return "سكين هابط (pos<0.40)"
    if pos is not None and pos > 0.80:
        return "مطاردة قمة (pos>0.80)"
    return "أخرى (بلغت 2-{:.0f}% ثم وقف)".format(WIN)


def _med(rows, key):
    vals = [r.get(key) for r in rows if isinstance(r.get(key), (int, float))]
    return median(vals) if vals else None


def _f(v, suf=""):
    return f"{v:.2f}{suf}" if isinstance(v, (int, float)) else "—"


def main():
    if not os.path.exists(DB):
        print(f"❌ لم يُعثر على {DB}"); return
    db = load()
    closed = [r for r in db if r.get("outcome", "active") != "active"]

    true_losers = [r for r in closed if _stopped(r) and (r.get("max_gain_pct") or 0) < WIN]
    saved       = [r for r in closed if _stopped(r) and (r.get("max_gain_pct") or 0) >= WIN]
    winners     = [r for r in closed if (r.get("max_gain_pct") or 0) >= WINREF]

    print("\n" + "=" * 64)
    print(f"  💀 بصمة الدخول الفاشل فعلاً — ضرب الوقف دون بلوغ +{WIN:.0f}%")
    print("=" * 64)
    print(f"  ضربت الوقف إجمالاً      : {len(true_losers) + len(saved)}")
    print(f"  🏆 منها بلغت ≥{WIN:.0f}% (رابحة بتعريفك) : {len(saved)}")
    print(f"  💀 خاسر حقيقي (<{WIN:.0f}% قط)         : {len(true_losers)}")
    if not true_losers:
        print("\n  لا خاسرين حقيقيين — كل ما ضرب الوقف بلغ هدفك أولاً!\n"); return

    cats = Counter(_classify(r) for r in true_losers)
    print(f"\n  ── لماذا لم تتحرّك؟ (نمط فشل الدخول) ──")
    print(f"  {'النمط':<28} {'عدد':>5} {'نسبة':>7}")
    print("  " + "─" * 46)
    for cat, n in cats.most_common():
        bar = "█" * int(n / len(true_losers) * 28)
        print(f"  {cat:<28} {n:>5} {n/len(true_losers)*100:>6.0f}%  {bar}")

    print(f"\n  ── البصمة الرقمية (وسيط): خاسر حقيقي ضدّ رابح ≥{WINREF:.0f}% ──")
    print(f"     {'المقياس':<12} {'خاسر حقيقي':>12} {'رابح':>10}")
    for key, lab, suf in [("ratio","Ratio","x"), ("pos24","pos24",""),
                          ("spike","spike","x"), ("net_usd","Net $",""),
                          ("fcf","FCF",""), ("ls_ratio","L/S",""),
                          ("market_bias","bias",""), ("move_pct","move","%")]:
        lv, wv = _med(true_losers, key), _med(winners, key)
        lv_s = str(int(lv)) if key=="net_usd" and lv else _f(lv, suf)
        wv_s = str(int(wv)) if key=="net_usd" and wv else _f(wv, suf)
        print(f"     {lab:<12} {lv_s:>12} {wv_s:>10}")

    # أي scanner أنتج الخاسرين الحقيقيين
    sc = Counter(r.get("scanner") or "?" for r in true_losers)
    tot = sum(sc.values())
    print(f"\n  ── أي scanner أنتجها؟ ──")
    print("     " + "  ".join(f"{k} {v/tot*100:.0f}%" for k, v in sc.most_common(6)))

    print("\n" + "=" * 64)
    print(f"  النمط الأكبر = أهمّ سبب دخول فاشل. قارن البصمة: أي مقياس يختلف")
    print(f"  بوضوح عن الرابح = إشارة تحذير ندمجها أعمق في الدرجة/الفلاتر.")
    print("=" * 64 + "\n")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
analyze_signals.py — تحليل signal_history.json
يطبع تقريراً عن الإشارات الرابحة وإعداداتها الفراكتالية.

تشغيل: python analyze_signals.py
"""
import json, sys, os
from collections import defaultdict

DB_PATH = os.path.join(os.path.dirname(__file__), "signal_history.json")

def _pct(n, total):
    return f"{n/total*100:.0f}%" if total else "—"

def _avg(vals):
    v = [x for x in vals if x is not None]
    return round(sum(v) / len(v), 2) if v else None

def _med(vals):
    v = sorted(x for x in vals if x is not None)
    if not v: return None
    mid = len(v) // 2
    return v[mid] if len(v) % 2 else (v[mid-1] + v[mid]) / 2

def load():
    if not os.path.exists(DB_PATH):
        print(f"❌ لم يُعثر على {DB_PATH}")
        sys.exit(1)
    with open(DB_PATH) as f:
        raw = f.read().strip()
    if raw.startswith("["):
        return json.loads(raw)
    return [json.loads(l) for l in raw.splitlines() if l.strip()]

def main():
    db = load()
    total = len(db)
    print(f"\n{'═'*60}")
    print(f"  MAFIO SNIPER — تحليل الإشارات")
    print(f"  إجمالي السجلات: {total}")
    print(f"{'═'*60}\n")

    # ── توزيع النتائج ──────────────────────────────────────────
    by_outcome = defaultdict(list)
    for r in db:
        by_outcome[r.get("outcome", "?")].append(r)

    print("📊 توزيع النتائج:")
    for out, recs in sorted(by_outcome.items()):
        gains = [r.get("max_gain_pct") for r in recs if r.get("max_gain_pct") is not None]
        avg_g = _avg(gains)
        print(f"  {out:20s} {len(recs):4d} ({_pct(len(recs), total)})  "
              f"avg_gain={avg_g if avg_g is not None else '?'}%")
    print()

    # ── تحديد الفئات ──────────────────────────────────────────
    winners   = [r for r in db if (r.get("max_gain_pct") or 0) >= 20]
    moderate  = [r for r in db if 5 <= (r.get("max_gain_pct") or 0) < 20]
    losers    = [r for r in db if r.get("outcome") in ("stoploss", "reversal")
                 and (r.get("max_gain_pct") or 0) < 5]
    active    = [r for r in db if r.get("outcome") == "active"]

    print(f"🏆 فئات الأداء:")
    print(f"  ✅ رابحون كبار  (≥+20%)  : {len(winners)}")
    print(f"  🟡 ربح معتدل   (+5-20%) : {len(moderate)}")
    print(f"  ❌ خسائر                  : {len(losers)}")
    print(f"  ⏳ نشط                    : {len(active)}")
    print()

    # ── أفضل الإشارات ─────────────────────────────────────────
    top = sorted([r for r in db if r.get("max_gain_pct")],
                 key=lambda r: r.get("max_gain_pct", 0), reverse=True)[:20]
    print("🚀 أفضل 20 إشارة (max_gain_pct):")
    print(f"  {'عملة':<10} {'تاريخ':<18} {'نتيجة':<15} {'أعلى %':>8}  {'H':>6}  {'fScore':>7}  {'fra_tags'}")
    print(f"  {'─'*85}")
    for r in top:
        tags = []
        if r.get("fra_quad"):       tags.append("QUAD")
        if r.get("fra_tornado"):    tags.append("Tornado")
        if r.get("fra_wave3"):      tags.append("Wave3")
        if r.get("fra_compression"):tags.append("Compression")
        if r.get("fra_bearish_end"):tags.append("BearEnd")
        jy = r.get("fra_jy")
        if jy and abs(jy) > 0.04:  tags.append(f"Jy{jy:+.2f}")
        res_pct = r.get("fra_res_pct")
        if res_pct is not None:     tags.append(f"Res+{res_pct:.1f}%")

        _date = (r.get('date') or '?')[:16]
        _h    = r.get('h_value')
        _fs   = r.get('fractal_score')
        print(f"  {r.get('sym') or '?':<10} {_date:<18} "
              f"{r.get('outcome') or '?':<15} {r.get('max_gain_pct') or 0:>7.1f}%  "
              f"{_h if _h is not None else '─':>6}  "
              f"{_fs if _fs is not None else '─':>7}  "
              f"{', '.join(tags) or '─'}")
    print()

    # ── مقارنة فراكتل: رابحون vs خاسرون ───────────────────────
    def frac_stats(group, label):
        if not group:
            print(f"  {label}: لا بيانات")
            return
        hs     = [r.get("h_value") for r in group]
        fscores= [r.get("fractal_score") for r in group]
        gains  = [r.get("max_gain_pct") for r in group if r.get("max_gain_pct") is not None]
        n_quad = sum(1 for r in group if r.get("fra_quad"))
        n_torn = sum(1 for r in group if r.get("fra_tornado"))
        n_wav3 = sum(1 for r in group if r.get("fra_wave3"))
        n_comp = sum(1 for r in group if r.get("fra_compression"))
        n_bear = sum(1 for r in group if r.get("fra_bearish_end"))
        n_res1 = sum(1 for r in group if (r.get("fra_res_pct") or 999) < 1.0)
        n_res2 = sum(1 for r in group if 1.0 <= (r.get("fra_res_pct") or 999) < 2.5)
        n      = len(group)
        print(f"\n  {label} ({n} إشارة):")
        print(f"    avg gain      = {_avg(gains)}%  |  median = {_med(gains)}%")
        print(f"    H avg/med     = {_avg(hs)} / {_med(hs)}")
        print(f"    fractal_score = avg {_avg(fscores)} / med {_med(fscores)}")
        print(f"    QUAD       {n_quad:3d} ({_pct(n_quad,n)})")
        print(f"    Tornado    {n_torn:3d} ({_pct(n_torn,n)})")
        print(f"    Wave3      {n_wav3:3d} ({_pct(n_wav3,n)})")
        print(f"    Compress.  {n_comp:3d} ({_pct(n_comp,n)})")
        print(f"    BearEnd    {n_bear:3d} ({_pct(n_bear,n)})")
        print(f"    Res <1%    {n_res1:3d} ({_pct(n_res1,n)})  ← جدار مقاومة قريب جداً")
        print(f"    Res 1-2.5% {n_res2:3d} ({_pct(n_res2,n)})  ← مقاومة قريبة")

    print("📈 مقارنة الفراكتل — رابحون vs خاسرون:")
    frac_stats(winners, "✅ رابحون كبار ≥+20%")
    frac_stats(losers,  "❌ خاسرون")
    print()

    # ── أفضل العملات تاريخياً ──────────────────────────────────
    coin_stats = defaultdict(list)
    for r in db:
        coin_stats[r.get("sym","?")].append(r.get("max_gain_pct") or 0)
    coin_best = sorted(coin_stats.items(), key=lambda x: max(x[1]), reverse=True)[:15]
    print("🏅 أفضل 15 عملة (بأعلى max_gain في التاريخ):")
    for sym, gains in coin_best:
        print(f"  {sym:<12} signals={len(gains):3d}  best={max(gains):+7.1f}%  avg={_avg(gains):+6.1f}%")
    print()

    # ── توزيع h_value للرابحين ─────────────────────────────────
    h_wins  = sorted(r.get("h_value") for r in winners if r.get("h_value") is not None)
    h_loss  = sorted(r.get("h_value") for r in losers  if r.get("h_value") is not None)
    if h_wins:
        h_above55 = sum(1 for h in h_wins if h >= 0.55)
        h_below45 = sum(1 for h in h_wins if h < 0.45)
        print(f"  H≥0.55 في الرابحين: {h_above55}/{len(h_wins)} ({_pct(h_above55,len(h_wins))})")
        print(f"  H<0.45 في الرابحين: {h_below45}/{len(h_wins)} ({_pct(h_below45,len(h_wins))})")
    if h_loss:
        h_above55 = sum(1 for h in h_loss if h >= 0.55)
        h_below45 = sum(1 for h in h_loss if h < 0.45)
        print(f"  H≥0.55 في الخاسرين: {h_above55}/{len(h_loss)} ({_pct(h_above55,len(h_loss))})")
        print(f"  H<0.45 في الخاسرين: {h_below45}/{len(h_loss)} ({_pct(h_below45,len(h_loss))})")
    print()

    # ── توزيع fractal_res_pct للرابحين ────────────────────────
    res_bins = {"<1%":0, "1-2.5%":0, "2.5-5%":0, ">5% or none":0}
    for r in winners:
        rp = r.get("fra_res_pct")
        if rp is None:           res_bins[">5% or none"] += 1
        elif rp < 1.0:           res_bins["<1%"] += 1
        elif rp < 2.5:           res_bins["1-2.5%"] += 1
        elif rp < 5.0:           res_bins["2.5-5%"] += 1
        else:                    res_bins[">5% or none"] += 1
    if winners:
        print("  توزيع مسافة المقاومة في الرابحين:")
        for k, v in res_bins.items():
            print(f"    {k:<15} {v:3d} ({_pct(v,len(winners))})")
    print()

    print(f"{'═'*60}")
    print("  ملاحظة: حقول fra_* ستُملأ فقط في الإشارات الجديدة (v3.2.44+)")
    print(f"{'═'*60}\n")

if __name__ == "__main__":
    main()

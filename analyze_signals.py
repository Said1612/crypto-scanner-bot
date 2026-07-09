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
    # Optional date filter: `python3 analyze_signals.py 2026-07-01` analyzes only
    # signals on/after that UTC date — lets us isolate POST-FIX signals from the
    # older contaminated history and judge the current filters on clean data.
    since = None
    if len(sys.argv) > 1 and len(sys.argv[1]) >= 8 and sys.argv[1][:4].isdigit():
        since = sys.argv[1]
        db = [r for r in db if (r.get("date") or "") >= since]
    total = len(db)
    print(f"\n{'═'*60}")
    print(f"  MAFIO SNIPER — تحليل الإشارات")
    if since:
        print(f"  ⏱ منذ: {since} (بيانات ما بعد الإصلاح فقط)")
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

    # ── معدل النجاح حسب كل مقياس (لمعايرة الفلاتر) ────────────────
    WIN_OUT  = {"success", "partial", "stoploss_recovered"}
    LOSS_OUT = {"stoploss", "reversal", "timeout"}
    closed = [r for r in db if r.get("outcome") in WIN_OUT | LOSS_OUT]

    def _is_win(r): return r.get("outcome") in WIN_OUT

    def winrate_buckets(group, key, edges, label, fmt="{:.2f}"):
        print(f"\n  === {label} ===")
        bounds = ([(-1e18, edges[0])]
                  + [(edges[i], edges[i+1]) for i in range(len(edges)-1)]
                  + [(edges[-1], 1e18)])
        for lo, hi in bounds:
            grp = [r for r in group if r.get(key) is not None and lo <= r[key] < hi]
            if not grp:
                continue
            n = len(grp)
            w = sum(1 for r in grp if _is_win(r))
            avg = _avg([r.get("max_gain_pct") for r in grp]) or 0
            lo_s = "-inf" if lo < -1e17 else fmt.format(lo)
            hi_s = "+inf" if hi >  1e17 else fmt.format(hi)
            print(f"    [{lo_s:>8} .. {hi_s:>8})  n={n:3d}  win={w/n*100:5.1f}%  avg_peak={avg:+6.1f}%")

    def winrate_cat(group, key, label):
        print(f"\n  === {label} ===")
        vals = defaultdict(list)
        for r in group:
            vals[r.get(key)].append(r)
        for v, grp in sorted(vals.items(), key=lambda x: -len(x[1])):
            n = len(grp); w = sum(1 for r in grp if _is_win(r))
            avg = _avg([r.get("max_gain_pct") for r in grp]) or 0
            print(f"    {str(v):>18}  n={n:3d}  win={w/n*100:5.1f}%  avg_peak={avg:+6.1f}%")

    print(f"\n{'═'*60}")
    print(f"  📐 معدل النجاح حسب المقياس — closed={len(closed)}")
    if closed:
        wtot = sum(1 for r in closed if _is_win(r))
        print(f"  معدل النجاح الإجمالي: {wtot/len(closed)*100:.1f}% "
              f"({wtot} ربح / {len(closed)-wtot} خسارة)")
    print(f"{'═'*60}")
    if closed:
        winrate_cat(closed, "is_alpha", "ALPHA مقابل SPOT")
        winrate_cat(closed, "scanner",  "حسب السكانر")
        winrate_buckets(closed, "ratio",   [1.5, 2.0, 3.0, 5.0],           "حسب RATIO")
        winrate_buckets(closed, "pos24",   [0.40, 0.55, 0.65, 0.75, 0.85], "حسب POS24")
        winrate_buckets(closed, "spike",   [3.0, 5.0, 10.0, 20.0],         "حسب SPIKE")
        winrate_buckets(closed, "net_usd", [5000, 15000, 30000, 100000],   "حسب NET USD", fmt="{:.0f}")
        winrate_buckets(closed, "score",   [4.0, 5.0, 6.0, 7.0],           "حسب SCORE")
        winrate_buckets(closed, "ob_spot", [0.50, 0.60, 0.70],             "حسب ORDERBOOK")

    # ── CONVICTION SCORE (0-10) — combines the validated winning factors ─────────
    # Goal: find a threshold that separates winners from losers so we can safely
    # block the weak tier WITHOUT blocking TAC-type winners (strong flow, weak spike).
    def _conviction(r):
        s = 0.0
        ratio = r.get("ratio") or 0
        ob    = r.get("ob_spot") or 0
        net   = r.get("net_usd") or 0
        pos   = r.get("pos24")
        spike = r.get("spike") or 0
        fs    = r.get("fractal_score") or 0
        jy    = r.get("fra_jy") or 0
        # Order flow (max 4) — this is what carried TAC (ratio 2.7 + OB 72)
        s += 2 if ratio >= 3.0 else 1 if ratio >= 2.0 else 0
        s += 2 if ob >= 0.72 else 1 if ob >= 0.65 else 0
        s += 2 if net >= 100_000 else 1 if net >= 30_000 else 0
        s = min(s, 4)
        # Early entry (max 2)
        if pos is not None:
            s += 2 if pos <= 0.45 else 1 if pos <= 0.60 else 0
        # Volume event (max 2)
        s += 2 if spike >= 15 else 1 if spike >= 8 else 0
        # Fractal health (max 2)
        s += 1 if fs >= 7 else 0
        s += 1 if jy >= 0.05 else 0
        return min(round(s), 10)

    for r in closed:
        r["_conv"] = _conviction(r)

    print(f"\n{'═'*60}")
    print("  💎 معدل النجاح حسب درجة القناعة (0-10)")
    print(f"{'═'*60}")
    if closed:
        winrate_buckets(closed, "_conv", [2, 4, 6, 8], "حسب CONVICTION")
        # Where do the BIG winners land? (must not block these)
        big = sorted([r for r in closed if _is_win(r)],
                     key=lambda x: -(x.get("max_gain_pct") or 0))[:12]
        print("\n  === أين تقع أكبر الرابحات؟ (يجب ألا نحجبها) ===")
        for r in big:
            print(f"    {r.get('sym','?'):>12}  conv={r.get('_conv')}  "
                  f"gain={r.get('max_gain_pct',0):+6.1f}%  ratio={r.get('ratio')} "
                  f"ob={r.get('ob_spot')} pos={r.get('pos24')} spike={r.get('spike')}")
        # Lowest-conviction winners set the safe floor for blocking
        conv_wins = [r.get("_conv") for r in closed if _is_win(r)]
        if conv_wins:
            print(f"\n  أدنى قناعة بين الرابحات = {min(conv_wins)}  "
                  f"← الحجب يجب أن يكون تحت هذا الرقم فقط")

    # ── EXPLOSION SIGNATURE — what separates big winners from losers ─────────────
    # The user's core question: what predicts a real move? Profile the metric
    # averages of BIG winners vs losers side by side. A metric whose average
    # differs sharply between the two groups is a real signal; a similar one is noise.
    def _mean(recs, key):
        vals = [r.get(key) for r in recs if isinstance(r.get(key), (int, float))]
        return sum(vals) / len(vals) if vals else None

    def _hit(recs, key, pred):
        vals = [r for r in recs if isinstance(r.get(key), (int, float))]
        if not vals: return None
        return sum(1 for r in vals if pred(r[key])) / len(vals) * 100

    big  = [r for r in closed if (r.get("max_gain_pct") or 0) >= 20]   # +20% explosions
    mega = [r for r in closed if (r.get("max_gain_pct") or 0) >= 50]   # +50% monsters
    lose = [r for r in closed if not _is_win(r)]

    print(f"\n{'═'*60}")
    print(f"  💥 بصمة الانفجار — رابحون كبار (≥+20%: {len(big)}) مقابل خاسرون ({len(lose)})")
    print(f"{'═'*60}")
    FEATURES = [
        ("pos24",         "pos24 (موقع الدخول)"),
        ("ratio",         "ratio"),
        ("ob_spot",       "order book"),
        ("net_usd",       "net USD"),
        ("spike",         "spike"),
        ("move_pct",      "move %"),
        ("fractal_score", "fractal score"),
        ("h_value",       "Hurst H"),
        ("fra_jy",        "Jy (زخم)"),
        ("market_bias",   "market bias"),
        ("liq_ratio",     "liq/mktcap (فكرتك!)"),
        ("mkt_cap",       "market cap"),
    ]
    print(f"  {'المقياس':<22} {'رابحون ≥20%':>14} {'وحوش ≥50%':>14} {'خاسرون':>12}")
    print(f"  {'-'*62}")
    for key, label in FEATURES:
        bw, mw, lo = _mean(big, key), _mean(mega, key), _mean(lose, key)
        def _f(v):
            if v is None: return "—"
            return f"{v:,.0f}" if abs(v) >= 1000 else f"{v:.3f}"
        print(f"  {label:<22} {_f(bw):>14} {_f(mw):>14} {_f(lo):>12}")

    # pos24 SPLIT by scanner type — resolves the confounding: Alpha (accumulation)
    # and main/Spot (momentum breakout) have OPPOSITE pos dynamics, so the pooled
    # pos curve is a misleading U-shape. Split them to see the true edge per type.
    print(f"\n{'═'*60}")
    print("  📍 pos24 مفصولاً حسب النوع (يحل الالتباس)")
    print(f"{'═'*60}")
    a_closed = [r for r in closed if r.get("is_alpha")]
    s_closed = [r for r in closed if not r.get("is_alpha")]
    print(f"\n  --- ALPHA فقط (n={len(a_closed)}) — المتوقع: pos منخفض يربح ---")
    winrate_buckets(a_closed, "pos24", [0.35, 0.45, 0.55, 0.70], "Alpha pos24")
    print(f"\n  --- SPOT/FUTURES فقط (n={len(s_closed)}) — المتوقع: pos عالٍ يربح ---")
    winrate_buckets(s_closed, "pos24", [0.40, 0.55, 0.70, 0.85], "Spot pos24")

    # liq/mktcap deep-dive (the user's hypothesis)
    print(f"\n  === liq/mktcap — هل السيولة حسب القيمة السوقية تتنبأ؟ ===")
    if any(r.get("liq_ratio") is not None for r in closed):
        winrate_buckets(closed, "liq_ratio", [0.01, 0.03, 0.06, 0.10], "حسب liq/mktcap", fmt="{:.3f}")
    else:
        print("    (لا بيانات بعد — ستُملأ في الإشارات الجديدة بعد هذا التحديث)")

    print(f"\n{'═'*60}")
    print("  ملاحظة: حقول fra_* + liq_ratio تُملأ في الإشارات الجديدة فقط")
    print(f"{'═'*60}\n")

if __name__ == "__main__":
    main()

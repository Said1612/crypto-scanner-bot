#!/usr/bin/env python3
"""
missed_movers.py — لماذا لم يلتقط البوت العملات التي ارتفعت؟

يربط قائمة الرابحين الفعلية (من Binance) بسجل البوت (journalctl)، ويجيب على
السؤال الوحيد المهم: كل عملة ارتفعت اليوم — هل رآها البوت؟ ولماذا رفضها؟

يفصل بين ثلاث حالات مختلفة تماماً، لأن علاج كل واحدة مختلف:
  🔴 لم تُفحص إطلاقاً  → ثغرة تغطية (لم تدخل مجمّع المرشّحين)
  🟡 فُحصت ورُفضت      → مشكلة فلترة (ونعرف الفلتر بالاسم)
  🟢 أُطلقت إشارة       → البوت نجح

USAGE (على الـ VPS):
  python3 missed_movers.py            # ارتفاع ≥ 8% خلال 24 ساعة، سيولة ≥ $2M
  python3 missed_movers.py 12         # ارتفاع ≥ 12%
  python3 missed_movers.py 8 12       # ارتفاع ≥ 8% خلال 12 ساعة
  python3 missed_movers.py 8 24 0.5   # خفض حدّ السيولة إلى $0.5M

السيولة تُفصل عمداً: عملة بحجم $300K ترتفع +65% ليست فرصة فائتة — الدخول
والخروج منها يحرّك السعر. خلطها مع الرابحين الحقيقيين يجعل نسبة الالتقاط
تبدو كارثية بينما البوت يؤدي عمله. النسبة التي تهمّ تُحسب على القابل للتداول.

ملاحظة: يقرأ فقط — لا يعدّل البوت ولا أي ملف.
"""
import json
import re
import subprocess
import sys
from collections import Counter

try:
    import requests
except ImportError:
    print("requests غير مثبّت — pip install requests"); sys.exit(1)

MIN_GAIN = float(sys.argv[1]) if len(sys.argv) > 1 else 8.0
HOURS    = int(sys.argv[2]) if len(sys.argv) > 2 else 24
# حدّ السيولة الذي يفصل "فرصة حقيقية" عن "مضخّة رقيقة" — بالمليون دولار
MIN_VOL  = (float(sys.argv[3]) if len(sys.argv) > 3 else 2.0) * 1e6
SERVICE  = "crypto-scanner"

# REJ BTCUSDT [5m] low_move(-1.0%)   → (sym, interval, reason)
RE_REJ    = re.compile(r"REJ\s+(\S+)\s+\[([^\]]+)\]\s+([a-z_]+)")
# SIGNAL BTCUSDT        tier=Mid   spike=...
RE_SIGNAL = re.compile(r"SIGNAL\s+(\S+)")


def top_gainers(min_gain: float):
    """أعلى الرابحين على Binance spot مقابل USDT."""
    r = requests.get("https://api.binance.com/api/v3/ticker/24hr", timeout=25)
    r.raise_for_status()
    out = []
    for t in r.json():
        sym = t.get("symbol", "")
        if not sym.endswith("USDT"):
            continue
        try:
            chg = float(t.get("priceChangePercent", 0))
            vol = float(t.get("quoteVolume", 0))
        except (TypeError, ValueError):
            continue
        if chg >= min_gain:
            out.append({"sym": sym, "chg": chg, "vol": vol})
    return sorted(out, key=lambda x: x["chg"], reverse=True)


def read_log(hours: int) -> str:
    try:
        p = subprocess.run(
            ["journalctl", "-u", SERVICE, "--since", f"{hours} hours ago", "--no-pager"],
            capture_output=True, text=True, timeout=180,
        )
        return p.stdout
    except FileNotFoundError:
        print("journalctl غير متاح — شغّل هذا على الـ VPS"); sys.exit(1)
    except subprocess.TimeoutExpired:
        print("journalctl بطيء جداً — جرّب عدد ساعات أقل"); sys.exit(1)


def main():
    print(f"\n📡 جلب الرابحين (≥ +{MIN_GAIN:g}%) وقراءة سجل آخر {HOURS} ساعة...\n")
    gainers = top_gainers(MIN_GAIN)
    log     = read_log(HOURS)

    if not log.strip():
        print("⚠️  السجل فارغ — تحقّق من اسم الخدمة أو الصلاحيات (شغّل بـ root)"); return

    rejects, signals = {}, set()
    for line in log.splitlines():
        m = RE_REJ.search(line)
        if m:
            sym, _interval, reason = m.groups()
            rejects.setdefault(sym, Counter())[reason] += 1
            continue
        m = RE_SIGNAL.search(line)
        if m:
            signals.add(m.group(1))

    never, blocked, fired = [], [], []
    for g in gainers:
        sym = g["sym"]
        if sym in signals:
            fired.append(g)
        elif sym in rejects:
            g["reasons"] = rejects[sym]
            g["scans"]   = sum(rejects[sym].values())
            blocked.append(g)
        else:
            never.append(g)

    total = len(gainers)
    liq   = lambda lst: [g for g in lst if g["vol"] >= MIN_VOL]
    f_l, b_l, n_l = liq(fired), liq(blocked), liq(never)
    total_l = len(f_l) + len(b_l) + len(n_l)
    thin    = total - total_l

    print("=" * 74)
    print(f"  📊 {total} عملة ارتفعت ≥ +{MIN_GAIN:g}% خلال {HOURS} ساعة")
    print(f"     منها {total_l} قابلة للتداول (سيولة ≥ ${MIN_VOL/1e6:g}M) · {thin} مضخّة رقيقة")
    print("=" * 74)
    print(f"                        الكل    القابل للتداول")
    print(f"  🟢 أطلق إشارة       : {len(fired):>4}   {len(f_l):>10}")
    print(f"  🟡 فحصها ورفضها     : {len(blocked):>4}   {len(b_l):>10}   ← مشكلة فلترة")
    print(f"  🔴 لم يفحصها أبداً   : {len(never):>4}   {len(n_l):>10}   ← ثغرة تغطية")
    if total_l:
        print(f"\n  ⭐ نسبة الالتقاط على القابل للتداول: {len(f_l)/total_l*100:.0f}%"
              f"   (على الكل: {len(fired)/total*100:.0f}%)")
        print(f"     الرقم الأول هو المقياس — الثاني تشوّهه المضخّات الرقيقة.")

    if fired:
        print("\n🟢 التقطها البوت:")
        for g in fired:
            print(f"   {g['sym'].replace('USDT',''):<12} +{g['chg']:.1f}%   vol=${g['vol']/1e6:.1f}M")

    if blocked:
        print(f"\n🟡 فحصها ورفضها — أهم أسباب الرفض لكل عملة  (💧 = سيولة رقيقة):")
        print(f"   {'عملة':<12} {'24h':>7} {'الحجم':>9} {'فحوص':>6}  الأسباب الغالبة")
        print("   " + "─" * 68)
        for g in sorted(blocked, key=lambda x: x["chg"], reverse=True)[:25]:
            top  = " · ".join(f"{r}×{c}" for r, c in g["reasons"].most_common(3))
            mark = "  " if g["vol"] >= MIN_VOL else "💧"
            print(f" {mark}{g['sym'].replace('USDT',''):<12} {g['chg']:>6.1f}% "
                  f"{g['vol']/1e6:>8.1f}M {g['scans']:>6}  {top}")

        # أي فلتر هو المسؤول الأكبر عن تفويت الرابحين؟ يُحسب على القابل للتداول
        # فقط — الفلاتر التي تحجب المضخّات الرقيقة تؤدي عملها، لا تخطئ.
        if b_l:
            agg = Counter()
            for g in b_l:
                for reason, n in g["reasons"].items():
                    agg[reason] += n
            print(f"\n   🎯 الفلاتر التي حجبت رابحين قابلين للتداول (سيولة ≥ ${MIN_VOL/1e6:g}M):")
            for reason, n in agg.most_common(10):
                coins = [g['sym'].replace('USDT','') for g in b_l if reason in g["reasons"]]
                print(f"      {reason:<22} {n:>6} رفض   على {len(coins)}: {', '.join(coins[:5])}")
            print(f"\n      ↑ هذه هي القائمة التي تُبنى عليها القرارات — أي فلتر يتكرّر هنا")
            print(f"        على عملات سائلة متعددة هو المرشّح للمراجعة بالبيانات.")

    if never:
        print(f"\n🔴 لم يفحصها البوت إطلاقاً (لم تدخل مجمّع المرشّحين):")
        for g in sorted(never, key=lambda x: x["chg"], reverse=True)[:20]:
            print(f"   {g['sym'].replace('USDT',''):<12} +{g['chg']:>5.1f}%   vol=${g['vol']/1e6:.1f}M")
        print("      ↑ راجع حدود الحجم/التغيّر في مجمّع المرشّحين، أو BLACKLIST")

    print("\n" + "=" * 74)
    print("  الأسباب أعلاه تُحسب عبر كل عمليات المسح — عملة تُفحص مئات المرات يومياً،")
    print("  فالرقم الكبير يعني 'رُفضت كثيراً'، لا 'رُفضت مرة واحدة بشدة'.")
    print("=" * 74 + "\n")


if __name__ == "__main__":
    main()

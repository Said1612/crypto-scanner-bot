#!/usr/bin/env python3
"""
fix_history.py — إصلاح max_gain_pct للإشارات التي أُغلقت قبل الوصول للقمة الحقيقية.

المشكل: SIGNAL_TIMEOUT_H كان 8h → إشارات تُغلق قبل القمة الفعلية.
العملات تختلف في توقيت الانفجار: 1 يوم، 10 أيام، 15، 20، 25 يوم.
لا يوجد توقيت ثابت — لذلك نستخدم 30 يوماً كحد أقصى (720h).

الحل: جلب klines من Binance/MEXC لـ 30 يوم بعد كل إشارة وتحديث max_gain_pct.
30 يوم = 720 ساعة — ضمن حد Binance (1000 kline) في طلب واحد.

تشغيل: python3 fix_history.py [--dry-run] [--sym BANANAS31] [--days 30]
"""
import json, os, time, argparse, requests
from datetime import datetime, timezone

DB_PATH  = os.path.join(os.path.dirname(__file__), "signal_history.json")
BINANCE  = "https://api.binance.com/api/v3"
MEXC     = "https://api.mexc.com/api/v3"
LOOK_AHEAD_H = 720   # 30 يوماً — يغطي جميع الانفجارات المتأخرة


def load_db():
    if not os.path.exists(DB_PATH):
        print("❌ لم يُعثر على signal_history.json"); exit(1)
    with open(DB_PATH) as f:
        raw = f.read().strip()
    if raw.startswith("["):
        return json.loads(raw)
    return [json.loads(l) for l in raw.splitlines() if l.strip()]


def save_db(db):
    with open(DB_PATH, "w") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def _parse_klines(klines):
    """استخرج قائمة الـ highs من أي تنسيق klines (Binance أو MEXC)."""
    if not klines or not isinstance(klines, list):
        return []
    # تنسيق قائمة: [[openTime, open, high, ...], ...]
    if isinstance(klines[0], list):
        return [float(k[2]) for k in klines if len(k) > 2]
    # تنسيق dict: [{"o": ..., "h": ..., ...}, ...]
    if isinstance(klines[0], dict):
        for hkey in ("h", "high", "highPrice"):
            vals = [float(k[hkey]) for k in klines if hkey in k]
            if vals:
                return vals
    return []


def fetch_peak(sym, entry_ts, entry_price, exchange="Binance"):
    """جلب أعلى سعر وصله السهم خلال LOOK_AHEAD_H ساعة من entry_ts."""
    start_ms = int(entry_ts * 1000)
    end_ms   = int((entry_ts + LOOK_AHEAD_H * 3600) * 1000)
    limit    = min(LOOK_AHEAD_H, 1000)

    is_mexc  = "mexc" in (exchange or "").lower()

    # قائمة الـ endpoints المرتبة حسب الأولوية
    candidates = []
    if is_mexc:
        # MEXC spot — endpoint رسمي
        candidates.append(f"{MEXC}/klines?symbol={sym}&interval=1h&startTime={start_ms}&endTime={end_ms}&limit={limit}")
        # MEXC بدون startTime (بعض الإصدارات لا تدعمه)
        candidates.append(f"{MEXC}/klines?symbol={sym}&interval=1h&limit={limit}")
    # Binance دائماً كـ fallback (بعض MEXC coins موجودة على Binance أيضاً)
    candidates.append(f"{BINANCE}/klines?symbol={sym}&interval=1h&startTime={start_ms}&endTime={end_ms}&limit={limit}")
    if not is_mexc:
        # MEXC كـ fallback لـ Binance coins
        candidates.append(f"{MEXC}/klines?symbol={sym}&interval=1h&startTime={start_ms}&endTime={end_ms}&limit={limit}")

    for url in candidates:
        try:
            r = requests.get(url, timeout=12)
            if r.status_code == 200:
                highs = _parse_klines(r.json())
                if highs:
                    peak = max(highs)
                    gain = (peak - entry_price) / entry_price * 100
                    return round(gain, 2)
        except Exception:
            pass
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",  action="store_true", help="عرض فقط بدون تعديل")
    parser.add_argument("--sym",      type=str, default=None, help="صحح عملة محددة فقط")
    parser.add_argument("--days",     type=int, default=30,
                        help="نافذة البحث بالأيام (افتراضي: 30)")
    parser.add_argument("--min-gain", type=float, default=0.0,
                        help="صحح فقط إذا القمة الحقيقية > هذه القيمة")
    parser.add_argument("--clean",    action="store_true",
                        help="احذف السجلات التي لا بيانات لها + max_gain=0 (عملات محذوفة أو MEXC قديمة)")
    args = parser.parse_args()
    global LOOK_AHEAD_H
    LOOK_AHEAD_H = args.days * 24

    db    = load_db()
    now   = time.time()
    fixed   = 0
    deleted = 0
    total   = 0
    # نسخة نظيفة تُبنى تدريجياً عند --clean
    clean_db = []

    print(f"\n{'═'*60}")
    print(f"  fix_history.py — إصلاح max_gain_pct")
    print(f"  إجمالي السجلات: {len(db)}")
    print(f"  نافذة البحث: {LOOK_AHEAD_H}h بعد كل إشارة")
    if args.dry_run: print("  ⚠️  DRY RUN — لن يتم التعديل")
    if args.clean:   print("  🧹 --clean: حذف السجلات بلا بيانات و max_gain=0")
    print(f"{'═'*60}\n")

    for i, rec in enumerate(db):
        sym         = rec.get("sym", "?")
        entry_ts    = rec.get("timestamp")
        entry_price = rec.get("price_entry") or rec.get("price")
        old_gain    = rec.get("max_gain_pct") or 0.0
        outcome     = rec.get("outcome", "")
        exchange    = rec.get("exchange", "Binance")

        if not entry_ts or not entry_price:
            if args.clean: continue   # لا بيانات أساسية → احذف
            continue
        if args.sym and sym.replace("USDT","") != args.sym.replace("USDT",""):
            if args.clean: clean_db.append(rec)
            continue
        if outcome == "active":
            if args.clean: clean_db.append(rec)
            continue
        age_h = (now - entry_ts) / 3600
        if age_h < LOOK_AHEAD_H + 1:
            if args.clean: clean_db.append(rec)
            continue

        total += 1
        exch_tag = "M" if ("mexc" in (exchange or "").lower()) else "B"
        print(f"  [{i}][{exch_tag}] {sym:<14} old={old_gain:+.1f}%  outcome={outcome}  ", end="", flush=True)

        real_gain = fetch_peak(sym, entry_ts, entry_price, exchange=exchange)
        time.sleep(0.25)

        if real_gain is None:
            # لا بيانات: إذا max_gain=0 أيضاً → هذا السجل عديم الفائدة
            if args.clean and old_gain <= 0.0:
                print("🗑️  حُذف (لا بيانات + gain=0)")
                deleted += 1
                # لا نضيف للـ clean_db
            else:
                print("⚠️ لا بيانات — محتفظ به")
                if args.clean: clean_db.append(rec)
            continue

        # بيانات متاحة: حدّث إذا لزم
        if real_gain > old_gain + 0.5 and real_gain >= args.min_gain:
            print(f"→ FIX {real_gain:+.1f}%  (كان {old_gain:+.1f}%)")
            fixed += 1
            if not args.dry_run:
                rec["max_gain_pct"] = real_gain
                if outcome == "timeout" and real_gain >= 5.0:
                    rec["outcome"] = "win"
        else:
            print(f"ok ({real_gain:+.1f}% حقيقي)")

        if args.clean: clean_db.append(rec)

    print(f"\n{'─'*60}")
    print(f"  فحص: {total}  |  إصلاح: {fixed}  |  محذوف: {deleted}")

    if not args.dry_run:
        final_db = clean_db if args.clean else db
        if fixed > 0 or (args.clean and deleted > 0):
            save_db(final_db)
            if args.clean:
                print(f"  ✅ signal_history.json — بقي {len(final_db)} سجل (حُذف {deleted})")
            else:
                print(f"  ✅ signal_history.json محدَّث ({fixed} سجل)")
    else:
        print(f"  ℹ️  DRY RUN — شغّل بدون --dry-run للتعديل الفعلي")
    print(f"{'═'*60}\n")


if __name__ == "__main__":
    main()

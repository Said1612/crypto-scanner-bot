#!/usr/bin/env python3
"""
fix_history.py — إصلاح max_gain_pct للإشارات التي أُغلقت قبل الوصول للقمة الحقيقية.

المشكل: SIGNAL_TIMEOUT_H كان 8h → إشارات تُغلق قبل القمة الفعلية.
كذلك: إشارات stoploss تُسجَّل بـ max_gain منخفض (لحظة الضغط)
        لكن الكوين يواصل الصعود بعد الـ SL.

الحل: جلب klines من Binance/MEXC لـ 30 يوم بعد كل إشارة وتحديث max_gain_pct.
      إذا كان max_gain >= 5% نحوّل outcome من stoploss → stoploss_recovered.

تشغيل:
  python3 fix_history.py                          # فحص وإصلاح كل الإشارات
  python3 fix_history.py BANANAS31USDT            # إشارات عملة محددة (positional)
  python3 fix_history.py --sym BANANAS31USDT      # نفس الشيء بـ flag
  python3 fix_history.py --dry-run                # عرض فقط بدون تعديل
  python3 fix_history.py --days 7                 # تغيير نافذة البحث
  python3 fix_history.py --clean                  # حذف السجلات بلا بيانات
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
    if isinstance(klines[0], list):
        return [float(k[2]) for k in klines if len(k) > 2]
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

    candidates = []
    if is_mexc:
        candidates.append(f"{MEXC}/klines?symbol={sym}&interval=1h&startTime={start_ms}&endTime={end_ms}&limit={limit}")
        candidates.append(f"{MEXC}/klines?symbol={sym}&interval=1h&limit={limit}")
    candidates.append(f"{BINANCE}/klines?symbol={sym}&interval=1h&startTime={start_ms}&endTime={end_ms}&limit={limit}")
    if not is_mexc:
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
    parser = argparse.ArgumentParser(
        description="إصلاح max_gain_pct في signal_history.json",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    # قبول اسم العملة كـ positional argument أو كـ --sym
    parser.add_argument("sym_positional", nargs="?", default=None,
                        metavar="SYM", help="اسم العملة (مثال: BANANAS31USDT أو BANANAS31)")
    parser.add_argument("--sym",      type=str, default=None, help="اسم العملة (بديل)")
    parser.add_argument("--dry-run",  action="store_true", help="عرض فقط بدون تعديل")
    parser.add_argument("--days",     type=int, default=30,
                        help="نافذة البحث بالأيام (افتراضي: 30)")
    parser.add_argument("--min-gain", type=float, default=0.0,
                        help="صحح فقط إذا القمة الحقيقية > هذه القيمة")
    parser.add_argument("--clean",    action="store_true",
                        help="احذف السجلات التي لا بيانات لها + max_gain=0")
    args = parser.parse_args()

    # دعم positional أو --sym (positional له الأولوية)
    sym_filter = args.sym_positional or args.sym

    global LOOK_AHEAD_H
    LOOK_AHEAD_H = args.days * 24

    db    = load_db()
    now   = time.time()
    fixed   = 0
    sl_recovered = 0
    deleted = 0
    total   = 0
    clean_db = []

    print(f"\n{'═'*60}")
    print(f"  fix_history.py — إصلاح max_gain_pct + stoploss_recovered")
    print(f"  إجمالي السجلات: {len(db)}")
    print(f"  نافذة البحث: {LOOK_AHEAD_H}h ({args.days} يوم) بعد كل إشارة")
    if sym_filter:   print(f"  فلتر العملة: {sym_filter}")
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
            if args.clean: continue
            continue

        # فلتر العملة — يقبل BANANAS31 أو BANANAS31USDT
        if sym_filter:
            sym_clean    = sym.upper().replace("USDT", "")
            filter_clean = sym_filter.upper().replace("USDT", "")
            if sym_clean != filter_clean:
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
        print(f"  [{i}][{exch_tag}] {sym:<16} old={old_gain:+.1f}%  outcome={outcome:<18}", end="", flush=True)

        real_gain = fetch_peak(sym, entry_ts, entry_price, exchange=exchange)
        time.sleep(0.25)

        if real_gain is None:
            if args.clean and old_gain <= 0.0:
                print("🗑️  حُذف (لا بيانات + gain=0)")
                deleted += 1
            else:
                print("⚠️ لا بيانات — محتفظ به")
                if args.clean: clean_db.append(rec)
            continue

        updated = False

        # ── تحديث max_gain_pct إذا كانت القمة الحقيقية أعلى ──────────────
        if real_gain > old_gain + 0.5 and real_gain >= args.min_gain:
            if not args.dry_run:
                rec["max_gain_pct"] = real_gain
            fixed += 1
            updated = True

        # ── تحديث outcome ─────────────────────────────────────────────────
        new_outcome = outcome
        if outcome in ("timeout", "unknown") and real_gain >= 5.0:
            # timeout/unknown مع قمة حقيقية ≥ 5% → win
            new_outcome = "win"
        elif outcome == "stoploss" and real_gain >= 5.0:
            # stoploss لكن الكوين صعد في النهاية → stoploss_recovered
            new_outcome = "stoploss_recovered"
            sl_recovered += 1

        if new_outcome != outcome:
            if not args.dry_run:
                rec["outcome"] = new_outcome
            updated = True

        # ── طباعة النتيجة ─────────────────────────────────────────────────
        if updated:
            change_str = f"gain: {old_gain:+.1f}% → {real_gain:+.1f}%"
            if new_outcome != outcome:
                change_str += f"  |  outcome: {outcome} → {new_outcome}"
            print(f"→ FIX  {change_str}")
        else:
            print(f"ok  ({real_gain:+.1f}% حقيقي — لا تغيير)")

        if args.clean: clean_db.append(rec)

    print(f"\n{'─'*60}")
    print(f"  فحص: {total}  |  gain محدَّث: {fixed}  |  stoploss_recovered: {sl_recovered}  |  محذوف: {deleted}")

    if not args.dry_run:
        final_db = clean_db if args.clean else db
        if fixed > 0 or sl_recovered > 0 or (args.clean and deleted > 0):
            save_db(final_db)
            print(f"  ✅ signal_history.json محدَّث")
        else:
            print(f"  ℹ️  لا تغييرات")
    else:
        print(f"  ℹ️  DRY RUN — شغّل بدون --dry-run للتعديل الفعلي")
    print(f"{'═'*60}\n")


if __name__ == "__main__":
    main()

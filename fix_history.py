#!/usr/bin/env python3
"""
fix_history.py — إصلاح max_gain_pct للإشارات التي أُغلقت قبل الوصول للقمة الحقيقية.

المشكل: SIGNAL_TIMEOUT_H كان 8h → إشارات تُغلق قبل القمة الفعلية.
بعض العملات تنفجر بعد 3-10 أيام وليس 24 ساعة.

الحل: جلب klines من Binance/MEXC لـ 7 أيام (168h) بعد كل إشارة وتحديث max_gain_pct.

تشغيل: python3 fix_history.py [--dry-run] [--sym BANANAS31] [--days 7]
"""
import json, os, time, argparse, requests
from datetime import datetime, timezone

DB_PATH  = os.path.join(os.path.dirname(__file__), "signal_history.json")
BINANCE  = "https://api.binance.com/api/v3"
MEXC     = "https://api.mexc.com/api/v3"
LOOK_AHEAD_H = 168   # 7 أيام — يغطي الانفجارات المتأخرة


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


def fetch_peak(sym, entry_ts, entry_price, exchange="Binance"):
    """جلب أعلى سعر وصله السهم خلال LOOK_AHEAD_H ساعة من entry_ts."""
    start_ms = int(entry_ts * 1000)
    end_ms   = int((entry_ts + LOOK_AHEAD_H * 3600) * 1000)
    limit    = min(LOOK_AHEAD_H, 1000)   # Binance max 1000 per request

    urls = [
        f"{BINANCE}/klines?symbol={sym}&interval=1h&startTime={start_ms}&endTime={end_ms}&limit={limit}",
        f"{MEXC}/klines?symbol={sym}&interval=1h&startTime={start_ms}&endTime={end_ms}&limit={limit}",
    ]
    for url in urls:
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                klines = r.json()
                if klines and isinstance(klines, list):
                    highs = [float(k[2]) for k in klines if isinstance(k, list)]
                    if highs:
                        peak = max(highs)
                        gain = (peak - entry_price) / entry_price * 100
                        return round(gain, 2)
        except Exception as e:
            print(f"  ⚠️ {sym} fetch error: {e}")
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",  action="store_true", help="عرض فقط بدون تعديل")
    parser.add_argument("--sym",      type=str, default=None, help="صحح عملة محددة فقط")
    parser.add_argument("--days",     type=int, default=7,
                        help="نافذة البحث بالأيام (افتراضي: 7)")
    parser.add_argument("--min-gain", type=float, default=0.0,
                        help="صحح فقط إذا القمة الحقيقية > هذه القيمة")
    args = parser.parse_args()
    global LOOK_AHEAD_H
    LOOK_AHEAD_H = args.days * 24

    db    = load_db()
    now   = time.time()
    fixed = 0
    total = 0

    print(f"\n{'═'*60}")
    print(f"  fix_history.py — إصلاح max_gain_pct")
    print(f"  إجمالي السجلات: {len(db)}")
    print(f"  نافذة البحث: {LOOK_AHEAD_H}h بعد كل إشارة")
    if args.dry_run: print("  ⚠️  DRY RUN — لن يتم التعديل")
    print(f"{'═'*60}\n")

    for i, rec in enumerate(db):
        sym        = rec.get("sym", "?")
        entry_ts   = rec.get("timestamp")
        entry_price = rec.get("price_entry") or rec.get("price")
        old_gain   = rec.get("max_gain_pct") or 0.0
        outcome    = rec.get("outcome", "")

        # فلترة: فقط الإشارات القديمة المكتملة (أو المنتهية بـ timeout)
        if not entry_ts or not entry_price:
            continue
        if args.sym and sym.replace("USDT","") != args.sym.replace("USDT",""):
            continue
        # تجاهل الإشارات النشطة أو الحديثة (أقل من 24h)
        if outcome == "active":
            continue
        age_h = (now - entry_ts) / 3600
        if age_h < LOOK_AHEAD_H + 1:
            continue

        total += 1
        print(f"  [{i}] {sym:<14} old={old_gain:+.1f}%  outcome={outcome}  ", end="", flush=True)

        real_gain = fetch_peak(sym, entry_ts, entry_price)
        time.sleep(0.25)   # rate limit — أبطأ قليلاً لنافذة 7 أيام

        if real_gain is None:
            print("⚠️ لا بيانات")
            continue

        if real_gain > old_gain + 0.5 and real_gain >= args.min_gain:
            print(f"→ FIX {real_gain:+.1f}%  (كان {old_gain:+.1f}%)")
            fixed += 1
            if not args.dry_run:
                db[i]["max_gain_pct"] = real_gain
                # لو كان timeout وفاز → غير الـ outcome
                if outcome == "timeout" and real_gain >= 5.0:
                    db[i]["outcome"] = "win"
        else:
            print(f"ok ({real_gain:+.1f}% حقيقي)")

    print(f"\n{'─'*60}")
    print(f"  فحص: {total}  |  إصلاح: {fixed}")
    if not args.dry_run and fixed > 0:
        save_db(db)
        print(f"  ✅ signal_history.json محدَّث ({fixed} سجل)")
    elif args.dry_run:
        print(f"  ℹ️  DRY RUN — شغّل بدون --dry-run للتعديل الفعلي")
    print(f"{'═'*60}\n")


if __name__ == "__main__":
    main()

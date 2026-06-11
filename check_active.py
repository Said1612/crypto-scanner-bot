#!/usr/bin/env python3
"""
check_active.py — عرض الإشارات النشطة مع نسبة الربح/الخسارة من سعر الدخول
تشغيل: python3 check_active.py
"""
import json, os, time, requests
from datetime import datetime, timezone

DB_PATH    = os.path.join(os.path.dirname(__file__), "signal_history.json")
STATE_PATH = os.path.join(os.path.dirname(__file__), "state.json")
BINANCE    = "https://api.binance.com/api/v3"
MEXC       = "https://api.mexc.com/api/v3"

def load_db():
    if not os.path.exists(DB_PATH):
        return []
    with open(DB_PATH) as f:
        raw = f.read().strip()
    if raw.startswith("["):
        return json.loads(raw)
    return [json.loads(l) for l in raw.splitlines() if l.strip()]

def load_tracking():
    """Load tracking dict from state.json for SL/TP targets."""
    if not os.path.exists(STATE_PATH):
        return {}
    try:
        with open(STATE_PATH) as f:
            s = json.load(f)
        return s.get("tracking", {})
    except Exception:
        return {}

def get_prices(syms):
    """Fetch current prices for a list of symbols from Binance then MEXC fallback."""
    prices = {}
    # Try Binance batch
    try:
        r = requests.get(f"{BINANCE}/ticker/price", timeout=8)
        if r.status_code == 200:
            for t in r.json():
                if t["symbol"] in syms:
                    prices[t["symbol"]] = float(t["price"])
    except Exception:
        pass
    # MEXC fallback for missing
    missing = [s for s in syms if s not in prices]
    if missing:
        try:
            r = requests.get(f"{MEXC}/ticker/price", timeout=8)
            if r.status_code == 200:
                for t in r.json():
                    if t["symbol"] in missing:
                        prices[t["symbol"]] = float(t["price"])
        except Exception:
            pass
    return prices

def fmt_pct(v):
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.2f}%"

def main():
    db       = load_db()
    tracking = load_tracking()

    # Active signals — from signal_history
    active = [r for r in db if r.get("outcome") == "active"]

    # Also include tracking entries that might not be in DB yet
    track_syms = set(tracking.keys())
    db_syms    = {r.get("sym") for r in active}
    only_track = track_syms - db_syms

    print(f"\n{'═'*65}")
    print(f"  الإشارات النشطة — P&L من سعر الدخول")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'═'*65}")

    if not active and not only_track:
        print("  لا توجد إشارات نشطة حالياً")
        print(f"{'═'*65}\n")
        return

    # Collect all symbols to fetch
    all_syms = set()
    for r in active:
        if r.get("sym"):
            all_syms.add(r["sym"])
    for sym in only_track:
        all_syms.add(sym)

    print(f"  جلب الأسعار الحالية... ({len(all_syms)} عملة)")
    prices = get_prices(all_syms)

    print()
    print(f"  {'عملة':<12} {'دخول':>12} {'حالي':>12} {'P&L':>8}  {'أعلى%':>7}  {'SL':>8}  {'TP1':>8}  {'مدة'}")
    print(f"  {'─'*80}")

    rows = []
    for r in active:
        sym   = r.get("sym", "?")
        entry = r.get("price_entry")
        if not entry:
            continue
        cur   = prices.get(sym)
        pnl   = (cur - entry) / entry * 100 if cur else None
        maxg  = r.get("max_gain_pct") or 0.0
        ts    = r.get("timestamp")
        mins  = int((time.time() - ts) / 60) if ts else 0
        hours = mins // 60
        dur   = f"{hours}h{mins%60:02d}m"

        tr    = tracking.get(sym, {})
        sl    = tr.get("sl")
        tp1   = tr.get("tp1")

        sl_pct  = (sl  - entry) / entry * 100 if sl  else None
        tp1_pct = (tp1 - entry) / entry * 100 if tp1 else None

        rows.append((pnl or -999, sym, entry, cur, pnl, maxg, sl_pct, tp1_pct, dur))

    # Sort by current P&L descending
    rows.sort(key=lambda x: x[0], reverse=True)

    for _, sym, entry, cur, pnl, maxg, sl_pct, tp1_pct, dur in rows:
        pnl_s  = fmt_pct(pnl)  if pnl  is not None else "?"
        maxg_s = fmt_pct(maxg) if maxg else "─"
        sl_s   = fmt_pct(sl_pct)  if sl_pct  is not None else "─"
        tp1_s  = fmt_pct(tp1_pct) if tp1_pct is not None else "─"
        cur_s  = f"{cur:.6g}" if cur else "?"

        # Color indicator
        if pnl is not None:
            icon = "🟢" if pnl >= 5 else ("🟡" if pnl >= 0 else "🔴")
        else:
            icon = "⚪"

        print(f"  {icon} {sym:<10} {entry:>12.6g} {cur_s:>12}  "
              f"{pnl_s:>8}  {maxg_s:>7}  {sl_s:>8}  {tp1_s:>8}  {dur}")

    # Tracking-only (not yet in DB)
    if only_track:
        print(f"\n  ── من tracking فقط ──")
        for sym in sorted(only_track):
            tr    = tracking.get(sym, {})
            entry = tr.get("price_entry") or tr.get("entry")
            cur   = prices.get(sym)
            if not entry:
                continue
            pnl   = (cur - entry) / entry * 100 if cur else None
            sl    = tr.get("sl")
            tp1   = tr.get("tp1")
            sl_pct  = (sl  - entry) / entry * 100 if sl  else None
            tp1_pct = (tp1 - entry) / entry * 100 if tp1 else None
            icon = "🟢" if (pnl or 0) >= 5 else ("🟡" if (pnl or 0) >= 0 else "🔴")
            print(f"  {icon} {sym:<10} {entry:>12.6g} {cur or '?':>12}  "
                  f"{fmt_pct(pnl) if pnl else '?':>8}  ─  "
                  f"{fmt_pct(sl_pct) if sl_pct else '─':>8}  "
                  f"{fmt_pct(tp1_pct) if tp1_pct else '─':>8}")

    n_green  = sum(1 for r in rows if r[4] is not None and r[4] >= 5)
    n_yellow = sum(1 for r in rows if r[4] is not None and 0 <= r[4] < 5)
    n_red    = sum(1 for r in rows if r[4] is not None and r[4] < 0)

    print(f"\n  الملخص: 🟢 {n_green} رابح  🟡 {n_yellow} محايد  🔴 {n_red} خسارة  "
          f"(من {len(rows)} إشارة نشطة)")
    print(f"{'═'*65}\n")

if __name__ == "__main__":
    main()

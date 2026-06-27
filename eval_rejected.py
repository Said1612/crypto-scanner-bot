#!/usr/bin/env python3
"""
eval_rejected.py — replay blocked Alpha signals to judge whether the filter
was right. For each record in rejected_signals.json, fetch 1h klines from the
rejection time forward and check which came first from the entry price:
  +5% (would-be WIN  → filter was WRONG, too tight)
  -8% (would-be LOSS → filter was RIGHT, good block)

Usage:  python3 eval_rejected.py
"""
import json, os, sys, time
import requests

REJECTED_DB = os.path.join(os.path.dirname(__file__), "rejected_signals.json")
WIN_PCT  =  5.0
LOSS_PCT = -8.0
# Binance Alpha klines share the standard spot kline endpoint host.
BASES = ["https://api.binance.com/api/v3", "https://data-api.binance.vision/api/v3"]

def fetch_klines(sym, start_ms, limit=200):
    for base in BASES:
        try:
            r = requests.get(f"{base}/klines",
                             params={"symbol": sym, "interval": "1h",
                                     "startTime": start_ms, "limit": limit},
                             timeout=10)
            if r.status_code == 200:
                d = r.json()
                if isinstance(d, list) and d:
                    return d
        except Exception:
            continue
    return []

def outcome(entry, kl):
    """Return (verdict, max_gain_pct, max_dd_pct) by walking candles in order."""
    max_g, max_dd = 0.0, 0.0
    for c in kl:
        hi = float(c[2]); lo = float(c[3])
        g  = (hi - entry) / entry * 100
        dd = (lo - entry) / entry * 100
        max_g  = max(max_g, g)
        max_dd = min(max_dd, dd)
        # candle ordering: assume worst-case both touched — check loss first (conservative)
        if dd <= LOSS_PCT and g >= WIN_PCT:
            return "loss_first", max_g, max_dd   # ambiguous candle → count as loss (conservative)
        if dd <= LOSS_PCT:
            return "loss", max_g, max_dd
        if g >= WIN_PCT:
            return "win", max_g, max_dd
    return "open", max_g, max_dd

def main():
    try:
        with open(REJECTED_DB) as f:
            data = json.load(f)
    except Exception as e:
        print(f"cannot read {REJECTED_DB}: {e}")
        sys.exit(1)

    if not data:
        print("no rejected signals logged yet")
        return

    print(f"evaluating {len(data)} blocked signals "
          f"(+{WIN_PCT:.0f}% would-be-WIN = filter wrong, {LOSS_PCT:.0f}% = filter right)\n")

    by_reason = {}
    rows = []
    for rec in data:
        sym   = rec["sym"]
        entry = rec["price_entry"]
        ts    = rec["timestamp"]
        if entry <= 0:
            continue
        kl = fetch_klines(sym, ts * 1000)
        time.sleep(0.15)   # be gentle on the API
        verdict, mg, dd = outcome(entry, kl) if kl else ("nodata", 0, 0)
        reason = rec.get("reason", "?")
        by_reason.setdefault(reason, []).append(verdict)
        rows.append((sym, reason, verdict, mg, dd, rec.get("ratio"),
                     rec.get("net_intensity"), rec.get("pos24")))

    # Per-reason summary: how often did the block save us vs cost us
    print("=" * 70)
    print("PER-FILTER VERDICT (did blocking help?)")
    print("=" * 70)
    for reason, verds in sorted(by_reason.items()):
        n      = len(verds)
        wins   = sum(1 for v in verds if v == "win")           # filter was WRONG
        losses = sum(1 for v in verds if v in ("loss", "loss_first"))  # filter was RIGHT
        opens  = sum(1 for v in verds if v == "open")
        nodata = sum(1 for v in verds if v == "nodata")
        evaluable = wins + losses
        good = (losses / evaluable * 100) if evaluable else 0
        print(f"\n  {reason}  (n={n})")
        print(f"    filter RIGHT (faded -8%):   {losses:3d}")
        print(f"    filter WRONG (ran +5%):     {wins:3d}")
        print(f"    still open / nodata:        {opens}/{nodata}")
        if evaluable:
            print(f"    => block accuracy: {good:.0f}%  "
                  f"({'KEEP — good filter' if good >= 60 else 'REVIEW — too tight' if good < 45 else 'borderline'})")

    print("\n" + "=" * 70)
    print("DETAIL (each blocked coin)")
    print("=" * 70)
    for sym, reason, verdict, mg, dd, ratio, ni, pos in rows:
        flag = "❌filter-wrong" if verdict == "win" else ("✅filter-right" if verdict in ("loss","loss_first") else "·")
        print(f"  {sym:>12} {reason:<22} {verdict:<10} peak={mg:+6.1f}% dd={dd:+6.1f}% "
              f"ratio={ratio} ni={ni} pos={pos} {flag}")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
eval_rejected.py — report whether blocking each signal was RIGHT or WRONG.

Primary source: the real-time shadow outcome the bot now records on every
blocked signal (shadow_outcome: would_win / would_lose / expired). This is
reliable for Alpha BSC tokens, whose historical klines are NOT available from
the spot API — the reason the old kline-replay approach returned "nodata" for
most of them.

Fallback: for old records with no shadow_outcome (logged before the bot did
real-time tracking), replay 1h klines from Binance spot (works only for
spot-listed symbols).

Usage:  python3 eval_rejected.py
"""
import json, os, sys, time
import requests

REJECTED_DB = os.path.join(os.path.dirname(__file__), "rejected_signals.json")
WIN_PCT, LOSS_PCT = 5.0, -8.0
BASES = ["https://api.binance.com/api/v3", "https://data-api.binance.vision/api/v3"]

def fetch_klines(sym, start_ms, limit=200):
    for base in BASES:
        try:
            r = requests.get(f"{base}/klines",
                             params={"symbol": sym, "interval": "1h",
                                     "startTime": start_ms, "limit": limit}, timeout=10)
            if r.status_code == 200 and isinstance(r.json(), list) and r.json():
                return r.json()
        except Exception:
            continue
    return []

def replay(entry, kl):
    for c in kl:
        hi, lo = float(c[2]), float(c[3])
        if (lo - entry) / entry * 100 <= LOSS_PCT:
            return "would_lose"
        if (hi - entry) / entry * 100 >= WIN_PCT:
            return "would_win"
    return "expired"

def verdict(rec):
    """Return would_win / would_lose / expired / pending / nodata for one record."""
    o = rec.get("shadow_outcome")
    if o in ("would_win", "would_lose", "expired"):
        return o
    if o == "pending":
        return "pending"
    # old record with no shadow tracking → try kline replay (spot-listed only)
    entry, ts = rec.get("price_entry", 0), rec.get("timestamp", 0)
    if entry <= 0:
        return "nodata"
    kl = fetch_klines(rec.get("sym", ""), ts * 1000)
    time.sleep(0.12)
    return replay(entry, kl) if kl else "nodata"

def main():
    try:
        with open(REJECTED_DB) as f:
            data = json.load(f)
    except Exception as e:
        print(f"cannot read {REJECTED_DB}: {e}"); sys.exit(1)
    if not data:
        print("no rejected signals logged yet"); return

    has_shadow = sum(1 for r in data if r.get("shadow_outcome") in
                     ("would_win", "would_lose", "expired", "pending"))
    print(f"evaluating {len(data)} blocked signals "
          f"({has_shadow} via real-time shadow tracking)\n")

    by_reason, rows = {}, []
    for rec in data:
        v = verdict(rec)
        by_reason.setdefault(rec.get("reason", "?"), []).append(v)
        rows.append((rec.get("sym", "?"), rec.get("reason", "?"), v,
                     rec.get("shadow_peak"), rec.get("shadow_dd"),
                     rec.get("ratio"), rec.get("net_intensity"), rec.get("pos24")))

    print("=" * 68)
    print("PER-FILTER VERDICT (of resolved signals, did blocking help?)")
    print("=" * 68)
    for reason, vs in sorted(by_reason.items()):
        n = len(vs)
        win  = sum(1 for v in vs if v == "would_win")    # filter WRONG (ran +5%)
        lose = sum(1 for v in vs if v == "would_lose")   # filter RIGHT (faded -8%)
        exp  = sum(1 for v in vs if v == "expired")      # neither (drifted, ~neutral)
        pend = sum(1 for v in vs if v == "pending")
        nod  = sum(1 for v in vs if v == "nodata")
        decisive = win + lose
        print(f"\n  {reason}  (n={n})")
        print(f"    filter RIGHT (faded to -8%):  {lose}")
        print(f"    filter WRONG (ran to +5%):    {win}")
        print(f"    neutral (expired ~flat):      {exp}")
        print(f"    pending / nodata:             {pend}/{nod}")
        if decisive:
            acc = lose / decisive * 100
            tag = ("KEEP — good filter" if acc >= 60 else
                   "REVIEW — too tight" if acc < 40 else "borderline")
            print(f"    => block accuracy: {acc:.0f}%  ({tag})")
        # Counting expired as a mild win for the filter (we avoided a flat/no-edge trade):
        soft = lose + exp
        if (soft + win) > 0:
            print(f"    => incl. neutral-as-good: {soft/(soft+win)*100:.0f}%")

    print("\n" + "=" * 68)
    print("DETAIL (resolved only)")
    print("=" * 68)
    for sym, reason, v, pk, dd, ratio, ni, pos in rows:
        if v in ("pending", "nodata"):
            continue
        flag = "❌ filter-wrong" if v == "would_win" else (
               "✅ filter-right" if v == "would_lose" else "· neutral")
        pk = f"{pk:+.1f}%" if isinstance(pk, (int, float)) else "?"
        dd = f"{dd:+.1f}%" if isinstance(dd, (int, float)) else "?"
        print(f"  {sym:>13} {reason:<22} {v:<11} peak={pk:>7} dd={dd:>7} "
              f"ratio={ratio} ni={ni} pos={pos} {flag}")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
fractal_journal.py — a discipline scorecard for the fractal models learned in class.

The fractal setups are DISCRETIONARY (you draw them by hand), so the only honest
way to know if a model has a real edge is to log every call BEFORE the outcome and
measure the hit rate over many trades — not to trust a few good-looking examples.

Log each setup the moment you draw it, mark the outcome when it resolves, and read
the stats. Numbers decide, not enthusiasm.

USAGE (one line each, phone-friendly via Termius):

  # add a setup  (dir = long|short)
  python3 fractal_journal.py add PYTH 1to1 long 0.0455 0.0530 0.0430 note here
      models:  1to1  = "One to One" (fib measured move)
               adv   = "Advanced Fractal" (small fractal enlarged)

  # mark the result when it resolves  (outcome = win|loss|expired)
  #   win     = price reached the target before the stop
  #   loss    = price hit the stop first
  #   expired = drifted / you closed it flat
  python3 fractal_journal.py close 3 win

  python3 fractal_journal.py list           # show open + recent
  python3 fractal_journal.py stats          # hit rate + R:R + expectancy by model
"""
import json, os, sys
from datetime import datetime, timezone

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fractal_journal.json")
MODELS = {"1to1": "One-to-One", "adv": "Advanced-Fractal"}
OUTCOMES = {"win", "loss", "expired"}


def _load():
    try:
        with open(DB) as f:
            return json.load(f)
    except Exception:
        return []


def _save(rows):
    tmp = DB + ".tmp"
    with open(tmp, "w") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    os.replace(tmp, DB)


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")


def _rr(entry, target, stop):
    """Reward:risk ratio = |target-entry| / |entry-stop|."""
    risk = abs(entry - stop)
    return round(abs(target - entry) / risk, 2) if risk > 0 else None


def add(args):
    if len(args) < 6:
        print("need: add <coin> <model:1to1|adv> <dir:long|short> <entry> <target> <stop> [note]")
        return
    coin, model, direction = args[0].upper(), args[1].lower(), args[2].lower()
    if model not in MODELS:
        print(f"model must be one of: {', '.join(MODELS)}"); return
    if direction not in ("long", "short"):
        print("dir must be long or short"); return
    try:
        entry, target, stop = float(args[3]), float(args[4]), float(args[5])
    except ValueError:
        print("entry/target/stop must be numbers"); return
    note = " ".join(args[6:])
    rows = _load()
    new_id = (max([r["id"] for r in rows], default=0) + 1)
    rows.append({
        "id": new_id, "date": _now(), "coin": coin, "model": model,
        "dir": direction, "entry": entry, "target": target, "stop": stop,
        "rr": _rr(entry, target, stop), "status": "open",
        "outcome": None, "note": note,
    })
    _save(rows)
    print(f"✅ #{new_id} {coin} {MODELS[model]} {direction} "
          f"entry={entry} target={target} stop={stop} R:R={_rr(entry, target, stop)}")


def close(args):
    if len(args) < 2 or not args[0].isdigit() or args[1].lower() not in OUTCOMES:
        print("need: close <id> <win|loss|expired>"); return
    rid, outcome = int(args[0]), args[1].lower()
    rows = _load()
    for r in rows:
        if r["id"] == rid:
            r["status"] = "closed"; r["outcome"] = outcome; r["closed"] = _now()
            _save(rows)
            print(f"✅ #{rid} {r['coin']} → {outcome}")
            return
    print(f"no setup with id {rid}")


def _list(_args):
    rows = _load()
    if not rows:
        print("journal empty — log your first setup with 'add'"); return
    openr = [r for r in rows if r["status"] == "open"]
    print(f"\n📂 OPEN ({len(openr)}):")
    for r in openr:
        print(f"  #{r['id']:>2} {r['coin']:<8} {MODELS[r['model']]:<16} {r['dir']:<5} "
              f"entry={r['entry']} target={r['target']} stop={r['stop']} R:R={r['rr']}  {r['note']}")
    closed = [r for r in rows if r["status"] == "closed"][-10:]
    print(f"\n📕 RECENT CLOSED (last {len(closed)}):")
    for r in closed:
        ico = {"win": "✅", "loss": "❌", "expired": "·"}.get(r["outcome"], "?")
        print(f"  #{r['id']:>2} {r['coin']:<8} {MODELS[r['model']]:<16} {ico} {r['outcome']}")


def stats(_args):
    rows = [r for r in _load() if r["status"] == "closed" and r["outcome"] in OUTCOMES]
    print("\n" + "=" * 60)
    print("  📐 FRACTAL SCORECARD — النتائج تحكم، لا الإعجاب")
    print("=" * 60)
    if not rows:
        print("  لا صفقات مغلقة بعد. سجّل واغلق عدة صفقات ثم عُد."); return

    def block(label, grp):
        n = len(grp)
        wins = sum(1 for r in grp if r["outcome"] == "win")
        loss = sum(1 for r in grp if r["outcome"] == "loss")
        exp = sum(1 for r in grp if r["outcome"] == "expired")
        decisive = wins + loss
        wr = (wins / decisive * 100) if decisive else 0.0
        rrs = [r["rr"] for r in grp if r.get("rr")]
        avg_rr = round(sum(rrs) / len(rrs), 2) if rrs else 0.0
        # expectancy per trade in R units: winrate*RR - lossrate*1
        exp_r = round((wr / 100) * avg_rr - (1 - wr / 100), 2) if decisive else 0.0
        print(f"\n  {label}  (n={n})")
        print(f"    ✅ win {wins}  ❌ loss {loss}  · expired {exp}")
        if decisive:
            tag = ("حافة حقيقية ✅" if wr >= 60 else
                   "ضعيف — أعد التقييم ⚠️" if wr < 40 else "متوسط")
            print(f"    hit-rate: {wr:.0f}%  ({tag})")
            print(f"    avg R:R: {avg_rr}   expectancy: {exp_r}R / trade "
                  f"({'رابح' if exp_r > 0 else 'خاسر'} على المدى)")

    block("ALL", rows)
    for m in MODELS:
        grp = [r for r in rows if r["model"] == m]
        if grp:
            block(MODELS[m], grp)
    print("\n  ملاحظة: تحتاج n≥15-20 لكل نموذج قبل الثقة بالنسبة.\n")


CMDS = {"add": add, "close": close, "list": _list, "stats": stats}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in CMDS:
        print(__doc__)
    else:
        CMDS[sys.argv[1]](sys.argv[2:])

"""
MAFIO AI Agent v2 — Self-Learning from signal_history.json
----------------------------------------------------------
• Loads all historical outcomes at startup and retrains automatically
• Learns which features predict success (ratio, ob_spot, spike, pos24, net_usd)
• Adjusts scanner/tier weights based on actual win rates
• Saves learned weights to ai_weights.json so knowledge persists across restarts
• Re-trains after every 10 new completed signals
"""

import json, os, math, logging, time
from typing import Dict, Any

log = logging.getLogger("mafio.ai")

SIGNAL_DB   = "signal_history.json"
WEIGHTS_FILE = "ai_weights.json"

# ── Feature thresholds for scoring ──────────────────────────────────────────
_FEAT_BINS = {
    "ob_spot": [0.50, 0.55, 0.60, 0.65, 0.70, 0.80],
    "ratio":   [1.5,  2.0,  3.0,  4.0,  6.0, 10.0],
    "spike":   [1.5,  2.5,  4.0,  6.0, 10.0, 20.0],
    "pos24":   [0.10, 0.20, 0.30, 0.40, 0.55, 0.70],  # lower is better
    "net_usd": [5_000, 15_000, 40_000, 100_000, 300_000, 1_000_000],
    "score":   [4.0,  5.0,  6.0,  7.0,  8.0,  9.0],
}

# Default weights (used before enough history)
_DEFAULT_WEIGHTS = {
    "ob_spot":  1.5,
    "ratio":    1.2,
    "spike":    1.0,
    "pos24":   -1.0,   # negative: higher pos24 = worse
    "net_usd":  0.8,
    "score":    0.5,
}

_SCANNER_BASE = {
    "moonshot":        85,
    "volume_explosion":70,
    "main":            65,
    "slow_scan":       65,
    "supertrend":      62,
    "scan_supertrend": 62,
    "mid_scan":        60,
    "fast_scan":       58,
    "accum":           55,
    "quiet_accum":     50,
    "momentum":        45,
    "scalp":           50,
}

_TIER_BASE = {
    "Mid":     72,
    "Small":   68,
    "Micro":   60,
    "Large":   58,
    "Unknown": 60,
}


class MafioAgent:
    def __init__(self):
        self._weights      = dict(_DEFAULT_WEIGHTS)
        self._scanner_adj  : Dict[str, float] = {}
        self._tier_adj     : Dict[str, float] = {}
        self._trained_on   = 0    # number of records used in last training
        self._last_train   = 0.0  # timestamp
        self._new_outcomes = 0    # counter since last retrain

        # Load persisted weights first, then retrain if new data available
        self._load_weights()
        self._train()

    # ── Training ─────────────────────────────────────────────────────────────

    def _train(self):
        """Learn from completed signals in signal_history.json."""
        try:
            with open(SIGNAL_DB) as f:
                history = json.load(f)
        except Exception:
            return

        # Only use completed signals (not active)
        completed = [
            s for s in history
            if s.get("outcome", "active") != "active"
            and s.get("max_gain_pct") is not None
        ]

        if len(completed) < 10:
            log.info("AI: not enough history (%d records) — using defaults", len(completed))
            return

        if len(completed) == self._trained_on:
            return  # nothing new

        wins  = [s for s in completed if s.get("max_gain_pct", 0) >= 5]
        loses = [s for s in completed if s.get("max_gain_pct", 0) < 0]

        def _avg(lst, key):
            vals = [float(s.get(key) or 0) for s in lst if s.get(key) is not None]
            return sum(vals) / len(vals) if vals else 0.0

        # ── Feature weight adjustment ──
        for feat, default in _DEFAULT_WEIGHTS.items():
            avg_w = _avg(wins,  feat)
            avg_l = _avg(loses, feat)
            if avg_w == 0 and avg_l == 0:
                self._weights[feat] = default
                continue
            # If wins have higher value → positive predictor
            # If wins have lower value → negative predictor
            diff = avg_w - avg_l
            total = abs(avg_w) + abs(avg_l) + 1e-9
            # Normalise to ±2 range
            adj = (diff / total) * 2.0
            # Blend: 60% learned + 40% default (avoid overfitting)
            self._weights[feat] = round(default * 0.4 + adj * 0.6, 3)

        # pos24 is always negative (lower = better entry)
        if self._weights["pos24"] > 0:
            self._weights["pos24"] = -self._weights["pos24"]

        # ── Scanner win-rate adjustment ──
        sc_stats: Dict[str, list] = {}
        for s in completed:
            sc = s.get("scanner", "main")
            sc_stats.setdefault(sc, []).append(s.get("max_gain_pct", 0))
        for sc, vals in sc_stats.items():
            win_rate = sum(1 for v in vals if v >= 5) / len(vals)
            avg_gain = sum(vals) / len(vals)
            # Adjustment: ±20 points based on win rate vs 50% baseline
            self._scanner_adj[sc] = round((win_rate - 0.50) * 40 + (avg_gain / 10), 1)

        # ── Tier win-rate adjustment ──
        tier_stats: Dict[str, list] = {}
        for s in completed:
            tier = s.get("tier", "Unknown")
            tier_stats.setdefault(tier, []).append(s.get("max_gain_pct", 0))
        for tier, vals in tier_stats.items():
            win_rate = sum(1 for v in vals if v >= 5) / len(vals)
            self._tier_adj[tier] = round((win_rate - 0.50) * 30, 1)

        self._trained_on   = len(completed)
        self._last_train   = time.time()
        self._new_outcomes = 0
        self._save_weights()

        log.info(
            "AI retrained: %d completed signals | weights=%s | scanner_adj=%s",
            len(completed), self._weights, self._scanner_adj
        )

    def notify_outcome(self):
        """Call when a signal outcome is recorded — triggers retrain after 10 new outcomes."""
        self._new_outcomes += 1
        if self._new_outcomes >= 10:
            self._train()

    # ── Weights persistence ───────────────────────────────────────────────────

    def _save_weights(self):
        try:
            with open(WEIGHTS_FILE, "w") as f:
                json.dump({
                    "weights":      self._weights,
                    "scanner_adj":  self._scanner_adj,
                    "tier_adj":     self._tier_adj,
                    "trained_on":   self._trained_on,
                    "ts":           time.time(),
                }, f, indent=2)
        except Exception as e:
            log.warning("AI weights save failed: %s", e)

    def _load_weights(self):
        try:
            with open(WEIGHTS_FILE) as f:
                d = json.load(f)
            self._weights     = d.get("weights",     self._weights)
            self._scanner_adj = d.get("scanner_adj", {})
            self._tier_adj    = d.get("tier_adj",    {})
            self._trained_on  = d.get("trained_on",  0)
            log.info("AI weights loaded: trained_on=%d signals", self._trained_on)
        except Exception:
            pass  # use defaults

    # ── Prediction ────────────────────────────────────────────────────────────

    def _feature_score(self, sig: dict) -> float:
        """Convert signal features to a raw score 0-100."""
        total = 0.0
        max_possible = 0.0

        for feat, weight in self._weights.items():
            val = float(sig.get(feat) or 0)
            bins = _FEAT_BINS.get(feat, [])
            if not bins:
                continue
            # Bin index 0-6
            idx = sum(1 for b in bins if val >= b)
            if feat == "pos24":
                # Invert: lower pos24 = better
                idx = len(bins) - idx
            # Normalise to 0-1
            norm = idx / len(bins)
            total       += norm * abs(weight)
            max_possible += abs(weight)

        return (total / max_possible * 100) if max_possible > 0 else 50.0

    def predict(self, sig: dict) -> dict:
        """
        Return {prob, verdict, emoji, warnings, model}.
        prob: 0-100 — probability signal will succeed (≥+5%).
        """
        scanner = sig.get("scanner", "main")
        tier    = sig.get("tier",    "Unknown")

        # Base from scanner
        base = _SCANNER_BASE.get(scanner, 60)
        base += self._scanner_adj.get(scanner, 0)
        base += self._tier_adj.get(tier, 0)

        # Tier base
        tier_base = _TIER_BASE.get(tier, 60)
        base = base * 0.6 + tier_base * 0.4

        # Feature-based adjustment
        feat_score = self._feature_score(sig)
        # Blend: 50% base + 50% features
        raw = base * 0.50 + feat_score * 0.50

        # Clamp to 30-98
        prob = max(30, min(98, round(raw)))

        # ── Warnings ──
        warnings = []
        ob   = float(sig.get("ob_spot") or 0)
        rat  = float(sig.get("ratio")   or 0)
        spk  = float(sig.get("spike")   or 0)
        pos  = float(sig.get("pos24")   or 0)
        net  = float(sig.get("net_usd") or 0)
        scr  = float(sig.get("score")   or 0)

        if ob < 0.55:
            warnings.append(f"Weak OB ({int(ob*100)}% bids) — seller pressure")
        if pos > 0.65:
            warnings.append(f"Late entry ({int(pos*100)}% of range) — exhaustion risk")
        if net < 15_000:
            warnings.append(f"Low net flow (${net/1000:.0f}K) — limited conviction")
        if spk < 3.0:
            warnings.append(f"Weak volume ({spk:.1f}x) — no real surge")
        if scr < 6.5:
            warnings.append(f"Low score ({scr:.1f}) → weak signal")

        # ── Verdict ──
        if prob >= 85:
            verdict = "✅ Strong Entry"
            emoji   = "🟢"
        elif prob >= 70:
            verdict = "✅ Promising Entry"
            emoji   = "🟢"
        elif prob >= 55:
            verdict = "🟡 Moderate — manage risk"
            emoji   = "🟡"
        else:
            verdict = "🔴 Avoid"
            emoji   = "🔴"

        model = f"v2({self._trained_on}sig)"

        return {
            "prob":     prob,
            "verdict":  verdict,
            "emoji":    emoji,
            "warnings": warnings[:1],  # max 1 warning in signal
            "model":    model,
        }

    def summary(self) -> str:
        """Return a short summary of what the model has learned."""
        lines = [
            f"🤖 *AI Agent v2 — Model Summary*",
            f"Trained on: `{self._trained_on}` completed signals",
            "",
            "*Feature Weights (learned):*",
        ]
        for feat, w in self._weights.items():
            direction = "↑ good" if w > 0 else "↓ risk"
            lines.append(f"  `{feat:<10}` weight=`{w:+.2f}` {direction}")

        if self._scanner_adj:
            lines.append("\n*Scanner adjustments:*")
            for sc, adj in sorted(self._scanner_adj.items(), key=lambda x: -x[1]):
                lines.append(f"  `{sc:<18}` `{adj:+.1f}` pts")

        if self._tier_adj:
            lines.append("\n*Tier adjustments:*")
            for t, adj in sorted(self._tier_adj.items(), key=lambda x: -x[1]):
                lines.append(f"  `{t:<8}` `{adj:+.1f}` pts")

        return "\n".join(lines)

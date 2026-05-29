"""
MAFIO AI Agent v3 — Pattern Matching + Self-Learning
-----------------------------------------------------
v3 improvements over v2:
• Pattern Matching (k-NN): finds 3 most similar historical signals and reports
  their actual outcomes — "SAGA +19% ✅, ERA +12% ✅, DIS -6% ❌"
• Uses fractal features (FS, H) + OI in similarity calculation
• Probability based on nearest-neighbor win rate (more accurate than linear scoring)
• Blends k-NN probability with learned weights for best of both approaches
• Re-trains after every 10 new completed signals (same as v2)
"""

import json, os, math, logging, time
from typing import Dict, Any, List, Tuple

log = logging.getLogger("mafio.ai")

SIGNAL_DB    = "signal_history.json"
WEIGHTS_FILE = "ai_weights.json"

# ── Feature normalization ranges for k-NN distance ──────────────────────────
_FEAT_RANGES = {
    "score":         (0.0,  10.0),
    "fractal_score": (0.0,  10.0),
    "ob_spot":       (0.40,  1.0),
    "spike":         (1.0,  30.0),
    "pos24":         (0.0,   1.0),
    "net_usd":       (0.0, 500_000),
    "h_value":       (0.40,  0.80),
    "oi_delta":      (-10.0, 15.0),
}

# Feature weights for linear scoring (v2 baseline, updated by training)
_DEFAULT_WEIGHTS = {
    "ob_spot":  1.5,
    "ratio":    1.2,
    "spike":    1.0,
    "pos24":   -1.0,
    "net_usd":  0.8,
    "score":    0.5,
}

_FEAT_BINS = {
    "ob_spot": [0.50, 0.55, 0.60, 0.65, 0.70, 0.80],
    "ratio":   [1.5,  2.0,  3.0,  4.0,  6.0, 10.0],
    "spike":   [1.5,  2.5,  4.0,  6.0, 10.0, 20.0],
    "pos24":   [0.10, 0.20, 0.30, 0.40, 0.55, 0.70],
    "net_usd": [5_000, 15_000, 40_000, 100_000, 300_000, 1_000_000],
    "score":   [4.0,  5.0,  6.0,  7.0,  8.0,  9.0],
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
}

_TIER_BASE = {
    "Large": 68,
    "Mid":   65,
    "Small": 62,
    "Micro": 55,
}


class MafioAgent:
    def __init__(self):
        self._weights      = dict(_DEFAULT_WEIGHTS)
        self._scanner_adj  : Dict[str, float] = {}
        self._tier_adj     : Dict[str, float] = {}
        self._trained_on   = 0
        self._last_train   = 0.0
        self._new_outcomes = 0
        self._history      : List[dict] = []   # all signals for pattern matching

        self._load_weights()
        self._train()

    # ── Training ─────────────────────────────────────────────────────────────

    def _train(self):
        """Load history and retrain weights from completed signals."""
        try:
            with open(SIGNAL_DB) as f:
                self._history = json.load(f)
        except Exception:
            self._history = []
            return

        completed = [
            s for s in self._history
            if s.get("outcome", "active") != "active"
            and s.get("max_gain_pct") is not None
        ]

        if len(completed) < 10:
            log.info("AI: not enough history (%d records) — using defaults", len(completed))
            return

        if len(completed) == self._trained_on:
            return

        wins  = [s for s in completed if s.get("max_gain_pct", 0) >= 5]
        loses = [s for s in completed if s.get("max_gain_pct", 0) < 0]

        def _avg(lst, key):
            vals = [float(s.get(key) or 0) for s in lst if s.get(key) is not None]
            return sum(vals) / len(vals) if vals else 0.0

        for feat, default in _DEFAULT_WEIGHTS.items():
            avg_w = _avg(wins,  feat)
            avg_l = _avg(loses, feat)
            if avg_w == 0 and avg_l == 0:
                self._weights[feat] = default
                continue
            diff  = avg_w - avg_l
            total = abs(avg_w) + abs(avg_l) + 1e-9
            adj   = (diff / total) * 2.0
            self._weights[feat] = round(default * 0.4 + adj * 0.6, 3)

        if self._weights["pos24"] > 0:
            self._weights["pos24"] = -self._weights["pos24"]

        sc_stats: Dict[str, list] = {}
        for s in completed:
            sc = s.get("scanner", "main")
            sc_stats.setdefault(sc, []).append(s.get("max_gain_pct", 0))
        for sc, vals in sc_stats.items():
            win_rate = sum(1 for v in vals if v >= 5) / len(vals)
            avg_gain = sum(vals) / len(vals)
            self._scanner_adj[sc] = round((win_rate - 0.50) * 40 + (avg_gain / 10), 1)

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
            "AI v3 retrained: %d completed | %d total history | weights=%s",
            len(completed), len(self._history), self._weights
        )

    def notify_outcome(self):
        self._new_outcomes += 1
        if self._new_outcomes >= 10:
            self._train()

    # ── Pattern Matching (k-NN) ───────────────────────────────────────────────

    def _normalize(self, val: float, feat: str) -> float:
        mn, mx = _FEAT_RANGES.get(feat, (0.0, 1.0))
        rng = mx - mn
        return (float(val) - mn) / rng if rng > 0 else 0.5

    def _distance(self, a: dict, b: dict) -> float:
        """Euclidean distance in normalized feature space."""
        total = 0.0
        count = 0
        for feat in _FEAT_RANGES:
            av = a.get(feat)
            bv = b.get(feat)
            if av is None or bv is None:
                continue
            try:
                diff   = self._normalize(float(av), feat) - self._normalize(float(bv), feat)
                total += diff * diff
                count += 1
            except (TypeError, ValueError):
                continue
        return math.sqrt(total / count) if count > 0 else 1.0

    def _find_similar(self, sig: dict, n: int = 3) -> List[dict]:
        """Return n completed signals most similar to sig by feature distance."""
        candidates = [
            s for s in self._history
            if s.get("outcome", "active") != "active"
            and s.get("max_gain_pct") is not None
            and s.get("sym") != sig.get("sym")   # exclude same coin
        ]
        if not candidates:
            return []
        scored = sorted(candidates, key=lambda s: self._distance(sig, s))
        return scored[:n]

    def _similar_summary(self, similar: List[dict]) -> Tuple[float, str]:
        """
        Returns (win_prob_0_100, display_string) from a list of similar signals.
        win_prob is the fraction that achieved >= +5%.
        """
        if not similar:
            return 0.0, ""

        wins = sum(1 for s in similar if s.get("max_gain_pct", 0) >= 5)
        win_prob = wins / len(similar) * 100

        parts = []
        for s in similar:
            gain  = s.get("max_gain_pct", 0)
            sym   = s.get("sym", "?").replace("USDT", "")
            sign  = "+" if gain >= 0 else ""
            icon  = "✅" if gain >= 5 else ("❌" if gain < 0 else "⚠️")
            parts.append(f"{sym} {sign}{gain:.0f}% {icon}")

        return win_prob, " · ".join(parts)

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
                data = json.load(f)
            self._weights      = data.get("weights",      dict(_DEFAULT_WEIGHTS))
            self._scanner_adj  = data.get("scanner_adj",  {})
            self._tier_adj     = data.get("tier_adj",     {})
            self._trained_on   = data.get("trained_on",   0)
            log.info("AI weights loaded: trained_on=%d", self._trained_on)
        except FileNotFoundError:
            pass
        except Exception as e:
            log.warning("AI weights load failed: %s", e)

    # ── Scoring ───────────────────────────────────────────────────────────────

    def _feature_score(self, sig: dict) -> float:
        """Linear weighted score 0-100 (v2 baseline)."""
        total = 0.0
        max_p = 0.0
        for feat, weight in self._weights.items():
            val  = float(sig.get(feat) or 0)
            bins = _FEAT_BINS.get(feat, [])
            if not bins:
                continue
            idx = sum(1 for b in bins if val >= b)
            if feat == "pos24":
                idx = len(bins) - idx
            norm  = idx / len(bins)
            total += norm * abs(weight)
            max_p += abs(weight)
        return (total / max_p * 100) if max_p > 0 else 50.0

    # ── Main predict ─────────────────────────────────────────────────────────

    def predict(self, sig: dict) -> dict:
        """
        Return {prob, verdict, emoji, warnings, similar_str, model}.
        prob: 0-100 — estimated probability signal reaches +5%.
        similar_str: display string of 3 most similar past trades.
        """
        scanner = sig.get("scanner", "main")
        tier    = sig.get("tier",    "Unknown")

        # ── v2 baseline (linear) ──────────────────────────────────────────
        base       = _SCANNER_BASE.get(scanner, 60)
        base      += self._scanner_adj.get(scanner, 0)
        base      += self._tier_adj.get(tier, 0)
        tier_base  = _TIER_BASE.get(tier, 60)
        base       = base * 0.6 + tier_base * 0.4
        feat_score = self._feature_score(sig)
        linear_prob = base * 0.50 + feat_score * 0.50

        # ── v3 pattern matching (k-NN) ────────────────────────────────────
        similar     = self._find_similar(sig, n=3)
        knn_prob, similar_str = self._similar_summary(similar)

        # Blend: if enough similar signals, weight k-NN more heavily
        if len(similar) >= 3:
            prob = round(linear_prob * 0.35 + knn_prob * 0.65)
        elif len(similar) >= 1:
            prob = round(linear_prob * 0.60 + knn_prob * 0.40)
        else:
            prob = round(linear_prob)

        prob = max(30, min(98, prob))

        # ── Warnings ──────────────────────────────────────────────────────
        warnings = []
        ob  = float(sig.get("ob_spot")       or 0)
        rat = float(sig.get("ratio")         or 0)
        spk = float(sig.get("spike")         or 0)
        pos = float(sig.get("pos24")         or 0)
        net = float(sig.get("net_usd")       or 0)
        scr = float(sig.get("score")         or 0)
        fs  = float(sig.get("fractal_score") or 0)
        h   = float(sig.get("h_value")       or 0)

        if pos > 0.65:
            warnings.append(f"Late entry ({int(pos*100)}% of range) — exhaustion risk")
        elif ob < 0.55:
            warnings.append(f"Weak OB ({int(ob*100)}% bids) — seller pressure")
        elif net < 15_000:
            warnings.append(f"Low net flow (${net/1000:.0f}K) — limited conviction")
        elif h > 0 and h < 0.53:
            warnings.append(f"Random market (H={h:.2f}) — no trending edge")
        elif fs > 0 and fs < 6.0:
            warnings.append(f"Moderate fractal structure (FS={fs:.0f})")

        # ── Exceptional setup highlights ──────────────────────────────────
        highlights = []
        if spk >= 50:
            highlights.append(f"explosive volume ({spk:.0f}x above avg)")
        elif spk >= 10:
            highlights.append(f"strong volume surge ({spk:.0f}x)")
        if ob >= 0.72:
            highlights.append(f"healthy OB ({int(ob*100)}% bids)")
        if rat >= 5.0:
            highlights.append(f"high buy ratio ({rat:.1f}x)")
        if fs >= 8.0:
            highlights.append(f"strong fractal (FS={fs:.0f})")
        brain_str = ", ".join(highlights[:2]) if highlights else ""

        # ── Verdict ───────────────────────────────────────────────────────
        if prob >= 75:
            verdict, emoji = "✅ Strong Entry",     "🟢"
        elif prob >= 58:
            verdict, emoji = "🟡 Moderate — manage risk", "🟡"
        else:
            verdict, emoji = "🔴 Avoid",             "🔴"

        model = f"v3({self._trained_on}sig)"

        return {
            "prob":        prob,
            "verdict":     verdict,
            "emoji":       emoji,
            "warnings":    warnings[:1],
            "brain_str":   brain_str,
            "similar_str": similar_str,
            "model":       model,
        }

    def summary(self) -> str:
        lines = [
            f"🤖 *AI Agent v3 — Pattern Matching*",
            f"History: `{len(self._history)}` signals · Trained: `{self._trained_on}` completed",
            "",
            "*Feature Weights (learned):*",
        ]
        for feat, w in self._weights.items():
            direction = "↑ good" if w > 0 else "↓ risk"
            lines.append(f"  `{feat:<12}` weight=`{w:+.2f}` {direction}")

        if self._scanner_adj:
            lines.append("\n*Scanner win-rate adjustments:*")
            for sc, adj in sorted(self._scanner_adj.items(), key=lambda x: -x[1]):
                lines.append(f"  `{sc:<18}` `{adj:+.1f}` pts")

        if self._tier_adj:
            lines.append("\n*Tier adjustments:*")
            for t, adj in sorted(self._tier_adj.items(), key=lambda x: -x[1]):
                lines.append(f"  `{t:<8}` `{adj:+.1f}` pts")

        return "\n".join(lines)

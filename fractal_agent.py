"""
MAFIO Fractal Agent v1 — Bill Williams Fractal Analysis
-------------------------------------------------------
• Detects bullish/bearish fractals (5-candle pattern — Bill Williams standard)
• Maps fractal support/resistance levels from kline data
• Analyzes fractal trend: Higher Lows (bullish) / Lower Highs (bearish)
• Detects fractal breakouts: price clears a former resistance level
• Scores 0-100 based on fractal confluence
• Self-learning: adjusts feature weights from real signal outcomes
• Persists knowledge to fractal_weights.json — survives bot restarts/updates
"""

import json, os, time, logging
from typing import Dict, List, Optional, Tuple

log = logging.getLogger("mafio.fractal")

FRACTAL_WEIGHTS_FILE = "fractal_weights.json"

# Default feature weights (tuned manually, overwritten by learning)
_DEFAULT_WEIGHTS: Dict[str, float] = {
    "above_support":    2.0,   # price is above a fractal support level
    "near_support":     1.5,   # price is within 2% of fractal support (tight dip buy)
    "fractal_break":    2.5,   # price cleared a former fractal resistance → now air above
    "higher_lows":      1.8,   # series of rising fractal lows = uptrend structure
    "lower_highs":     -1.5,   # series of falling fractal highs = downtrend pressure
    "near_resistance": -2.0,   # fractal resistance within 5% above price = ceiling risk
    "count_bonus":      0.5,   # more confirmed fractals = stronger structure reading
}


class FractalAgent:
    def __init__(self):
        self._weights    = dict(_DEFAULT_WEIGHTS)
        self._trained_on = 0
        self._history: List[dict] = []   # fractal snapshots → learns from outcomes
        self._load_weights()

    # ── Fractal Detection ─────────────────────────────────────────────────────

    @staticmethod
    def _detect_fractals(klines: list) -> Tuple[List[float], List[float]]:
        """
        Bill Williams 5-candle fractal detection.
        klines format: [ts, open, high, low, close, volume, ...]
        Returns (bullish_lows, bearish_highs) in chronological order.
        """
        bulls: List[float] = []   # bullish fractal lows  → support
        bears: List[float] = []   # bearish fractal highs → resistance

        n = len(klines)
        for i in range(2, n - 2):
            try:
                hi = [float(klines[j][2]) for j in range(i - 2, i + 3)]
                lo = [float(klines[j][3]) for j in range(i - 2, i + 3)]
            except (IndexError, ValueError):
                continue

            # Bearish fractal: middle candle has the highest high of the 5
            if hi[2] > hi[0] and hi[2] > hi[1] and hi[2] > hi[3] and hi[2] > hi[4]:
                bears.append(hi[2])

            # Bullish fractal: middle candle has the lowest low of the 5
            if lo[2] < lo[0] and lo[2] < lo[1] and lo[2] < lo[3] and lo[2] < lo[4]:
                bulls.append(lo[2])

        return bulls, bears

    @staticmethod
    def _fractal_trend(levels: List[float], n: int = 3) -> str:
        """
        Determine trend direction from the last n fractal levels.
        Returns: 'bullish' / 'bearish' / 'neutral'
        """
        if len(levels) < 2:
            return "neutral"
        recent = levels[-n:] if len(levels) >= n else levels
        if all(recent[i] > recent[i - 1] for i in range(1, len(recent))):
            return "bullish"
        if all(recent[i] < recent[i - 1] for i in range(1, len(recent))):
            return "bearish"
        return "neutral"

    # ── Main Analysis ─────────────────────────────────────────────────────────

    def analyze(self, klines: list, price: float) -> dict:
        """
        Full fractal analysis for a given price.
        Returns: {score, verdict, detail, warning, support, resistance,
                  bull_trend, bear_trend, bulls_count, bears_count, _features}
        """
        if not klines or len(klines) < 10:
            return self._empty_result()

        bulls, bears = self._detect_fractals(klines)

        if not bulls and not bears:
            return self._empty_result()

        # ── Nearest levels relative to current price ──
        supports    = [b for b in bulls if b <= price * 1.02]   # at or slightly above price
        resistances = [b for b in bears if b >= price * 0.98]   # at or slightly below price

        nearest_sup = max(supports)    if supports    else None
        nearest_res = min(resistances) if resistances else None

        # ── Distances (%) ──
        sup_dist = ((price - nearest_sup) / price * 100) if nearest_sup else None
        res_dist = ((nearest_res - price) / price * 100) if nearest_res else None

        # ── Feature flags ──
        above_support   = nearest_sup is not None and sup_dist is not None and sup_dist <= 8.0
        near_support    = nearest_sup is not None and sup_dist is not None and sup_dist <= 2.0
        near_resistance = nearest_res is not None and res_dist is not None and res_dist <= 5.0

        # Fractal breakout: price cleared the last major resistance (clear sky above)
        fractal_break = False
        if len(bears) >= 2 and (nearest_res is None or (res_dist is not None and res_dist > 5.0)):
            fractal_break = price > bears[-2]

        # Trend structure
        bull_trend  = self._fractal_trend(bulls)
        bear_trend  = self._fractal_trend(bears)
        higher_lows = bull_trend == "bullish"
        lower_highs = bear_trend == "bearish"

        count_bonus = min(len(bulls) + len(bears), 10)

        # ── Score (base 50, range 10-100) ──
        w = self._weights
        raw = 50.0
        raw += w["above_support"]   * (1 if above_support   else 0)
        raw += w["near_support"]    * (1 if near_support    else 0)
        raw += w["fractal_break"]   * (1 if fractal_break   else 0)
        raw += w["higher_lows"]     * (1 if higher_lows     else 0)
        raw += w["lower_highs"]     * (1 if lower_highs     else 0)
        raw += w["near_resistance"] * (1 if near_resistance else 0)
        raw += w["count_bonus"]     * (count_bonus / 10.0)

        score = max(10, min(100, round(raw)))

        # ── Verdict ──
        if score >= 75:
            verdict = "✅ فراكتل قوي"
        elif score >= 55:
            verdict = "🟡 فراكتل معتدل"
        else:
            verdict = "🔴 فراكتل ضعيف"

        # ── Detail text ──
        parts = []
        if near_support and nearest_sup:
            parts.append(f"دعم فراكتلي ${nearest_sup:.4g} ({sup_dist:.1f}%↓)")
        elif above_support and nearest_sup:
            parts.append(f"فوق دعم ${nearest_sup:.4g}")
        if fractal_break:
            parts.append("كسر مقاومة فراكتلية ✅")
        if higher_lows:
            parts.append("Higher Lows ↗")
        if lower_highs:
            parts.append("Lower Highs ↘ ⚠️")
        detail = " · ".join(parts) if parts else "بنية فراكتلية محايدة"

        warning = None
        if near_resistance and nearest_res:
            warning = f"مقاومة فراكتلية ${nearest_res:.4g} (+{res_dist:.1f}%) ⚠️"

        features = {
            "above_support":   above_support,
            "near_support":    near_support,
            "fractal_break":   fractal_break,
            "higher_lows":     higher_lows,
            "lower_highs":     lower_highs,
            "near_resistance": near_resistance,
            "count_bonus":     count_bonus,
        }

        return {
            "score":       score,
            "verdict":     verdict,
            "detail":      detail,
            "warning":     warning,
            "support":     round(nearest_sup, 8)  if nearest_sup  else None,
            "resistance":  round(nearest_res, 8)  if nearest_res  else None,
            "bull_trend":  bull_trend,
            "bear_trend":  bear_trend,
            "bulls_count": len(bulls),
            "bears_count": len(bears),
            "_features":   features,
        }

    def _empty_result(self) -> dict:
        return {
            "score": 50, "verdict": "⚪ لا بيانات فراكتلية",
            "detail": "", "warning": None,
            "support": None, "resistance": None,
            "bull_trend": "neutral", "bear_trend": "neutral",
            "bulls_count": 0, "bears_count": 0,
            "_features": {},
        }

    # ── Self-Learning ─────────────────────────────────────────────────────────

    def record_signal(self, sym: str, features: dict):
        """Store fractal snapshot at signal entry — outcome filled later."""
        self._history.append({
            "sym":      sym,
            "ts":       time.time(),
            "features": features,
            "outcome":  None,
        })
        if len(self._history) > 500:
            self._history = self._history[-500:]
        self._save_weights()

    def record_outcome(self, sym: str, max_gain: float):
        """
        Called when a signal closes (SL / success / timeout).
        Retrains every 10 new completed outcomes once ≥20 exist.
        """
        for rec in reversed(self._history):
            if rec["sym"] == sym and rec["outcome"] is None:
                rec["outcome"] = max_gain
                break

        completed = [r for r in self._history if r["outcome"] is not None]
        if len(completed) >= 20 and len(completed) % 10 == 0:
            self._train()

    def _train(self):
        """Adjust feature weights from historical fractal outcomes."""
        completed = [r for r in self._history if r["outcome"] is not None]
        if len(completed) < 20:
            return

        wins  = [r for r in completed if r["outcome"] >= 5.0]
        loses = [r for r in completed if r["outcome"] < 0]

        if not wins or not loses:
            return

        for feat, default in _DEFAULT_WEIGHTS.items():
            w_rate = sum(1 for r in wins  if r["features"].get(feat)) / len(wins)
            l_rate = sum(1 for r in loses if r["features"].get(feat)) / len(loses)
            diff   = w_rate - l_rate
            # Blend 60% learned + 40% default to avoid overfitting
            adj = default * 0.4 + diff * abs(default) * 2.0 * 0.6
            self._weights[feat] = round(adj, 3)

        # Keep penalty features always negative
        if self._weights["near_resistance"] > 0:
            self._weights["near_resistance"] = -self._weights["near_resistance"]
        if self._weights["lower_highs"] > 0:
            self._weights["lower_highs"] = -self._weights["lower_highs"]

        self._trained_on = len(completed)
        self._save_weights()
        log.info("FractalAgent retrained on %d signals | weights=%s",
                 len(completed), self._weights)

    # ── Persistence ───────────────────────────────────────────────────────────

    def _save_weights(self):
        try:
            with open(FRACTAL_WEIGHTS_FILE, "w") as f:
                json.dump({
                    "weights":    self._weights,
                    "trained_on": self._trained_on,
                    "history":    self._history[-200:],
                    "ts":         time.time(),
                }, f, indent=2)
        except Exception as e:
            log.warning("FractalAgent save failed: %s", e)

    def _load_weights(self):
        try:
            with open(FRACTAL_WEIGHTS_FILE) as f:
                d = json.load(f)
            self._weights    = d.get("weights",    self._weights)
            self._trained_on = d.get("trained_on", 0)
            self._history    = d.get("history",    [])
            log.info("FractalAgent loaded: trained_on=%d signals", self._trained_on)
        except Exception:
            pass

    def summary(self) -> str:
        """Human-readable model summary for /fractal_summary command."""
        lines = [
            "📐 *Fractal Agent v1 — ملخص النموذج*",
            f"مُدرَّب على: `{self._trained_on}` إشارة مكتملة",
            f"سجل التاريخ: `{len(self._history)}` نقطة",
            "",
            "*أوزان الميزات المتعلَّمة:*",
        ]
        for feat, w in self._weights.items():
            icon = "↑ إيجابي" if w > 0 else "↓ سلبي"
            lines.append(f"  `{feat:<20}` `{w:+.3f}` {icon}")
        return "\n".join(lines)

"""
MAFIO Fractal Agent v2 — Advanced Fractal Analysis
---------------------------------------------------
Based on fractal analysis course principles:

QUAD FRACTAL (Binary Fractions / الكسور الثنائية):
  - Every wave (up or down) consists of 4 sub-fractals (F1 → F4)
  - F2 copies and MAGNIFIES F1 | F4 copies and MAGNIFIES F3
  - Second main fractal (F3+F4) MUST surpass peak of first main (F1+F2)
  - If F4 doesn't surpass F2 → not a valid continuation

TORNADO / RUNAWAY:
  - After initial impulse (F1), correction (F2) stays below F1's peak
  - Bounded correction → strong runaway continuation expected

END OF BEARISH FRACTAL (نهاية الفراكتل الهابط):
  - Series of lower lows ends → last low = certain buy (new bullish fractal begins)
  - "نهاية الفراكتل الهابط بداية لفراكتل صاعد" — highest-confidence buy signal

CONTAINMENT (احتضان):
  - Each fractal contains smaller fractals inside it
  - Larger TF fractal gives direction | Smaller TF gives entry

PRICE vs TIME FRACTALS:
  - Price fractal: moves on Y-axis (magnitude)
  - Time fractal: moves on X-axis (duration)
  - Must alternate — impossible to have all price or all time fractals

Self-learning:
  - Records fractal conditions at signal entry
  - Adjusts feature weights from real signal outcomes
  - Persists knowledge to fractal_weights.json across restarts/updates
"""

import json, os, time, logging
from typing import Dict, List, Optional, Tuple

log = logging.getLogger("mafio.fractal")

FRACTAL_WEIGHTS_FILE = "fractal_weights.json"

# Feature weights — tuned from course principles, overwritten by learning
_DEFAULT_WEIGHTS: Dict[str, float] = {
    # ── Primary signals (from course) ──────────────────────────────────
    "bearish_end":       3.5,   # end of bearish fractal = certain buy (strongest signal)
    "tornado_setup":     3.0,   # correction bounded → runaway continuation expected
    "quad_valid":        2.5,   # valid QUAD structure: F4 surpassed F2's peak
    "wave3_entry":       2.0,   # price entering what appears to be 3rd wave (strongest)
    # ── Structural signals ───────────────────────────────────────────────
    "above_support":     2.0,   # price above fractal support level
    "near_support":      1.5,   # price within 2% of fractal support (tight dip)
    "fractal_break":     2.5,   # price cleared former fractal resistance (air above)
    "higher_lows":       1.8,   # series of rising fractal lows = uptrend structure
    "magnification":     1.5,   # each fractal copy is larger = healthy trend strength
    # ── Risk signals ────────────────────────────────────────────────────
    "lower_highs":      -1.5,   # series of falling fractal highs = downtrend pressure
    "near_resistance":  -2.0,   # fractal resistance within 5% above price = ceiling
    "miniaturization":  -1.5,   # each fractal copy is smaller = weakening trend
    "count_bonus":       0.5,   # more confirmed fractals = stronger structure reading
}


class FractalAgent:
    def __init__(self):
        self._weights    = dict(_DEFAULT_WEIGHTS)
        self._trained_on = 0
        self._history: List[dict] = []
        self._load_weights()

    # ── Bill Williams 5-Candle Fractal Detection ──────────────────────────────

    @staticmethod
    def _detect_fractals(klines: list) -> Tuple[List[float], List[float]]:
        """
        Bill Williams 5-candle fractal detection.
        klines: [ts, open, high, low, close, volume, ...]
        Returns (bullish_lows, bearish_highs) in chronological order.
        """
        bulls: List[float] = []
        bears: List[float] = []
        n = len(klines)
        for i in range(2, n - 2):
            try:
                hi = [float(klines[j][2]) for j in range(i - 2, i + 3)]
                lo = [float(klines[j][3]) for j in range(i - 2, i + 3)]
            except (IndexError, ValueError):
                continue
            if hi[2] > hi[0] and hi[2] > hi[1] and hi[2] > hi[3] and hi[2] > hi[4]:
                bears.append(hi[2])
            if lo[2] < lo[0] and lo[2] < lo[1] and lo[2] < lo[3] and lo[2] < lo[4]:
                bulls.append(lo[2])
        return bulls, bears

    # ── Swing Point Analysis (higher resolution than 5-candle) ───────────────

    @staticmethod
    def _swing_points(klines: list, lookback: int = 3) -> Tuple[List[float], List[float]]:
        """
        Detect swing highs and lows using a lookback window.
        More sensitive than 5-candle fractals — catches wave structure.
        Returns (swing_lows, swing_highs) in chronological order.
        """
        swing_lows:  List[float] = []
        swing_highs: List[float] = []
        n = len(klines)
        for i in range(lookback, n - lookback):
            try:
                hi_c = float(klines[i][2])
                lo_c = float(klines[i][3])
                hi_win = [float(klines[j][2]) for j in range(i - lookback, i + lookback + 1)]
                lo_win = [float(klines[j][3]) for j in range(i - lookback, i + lookback + 1)]
            except (IndexError, ValueError):
                continue
            if hi_c >= max(hi_win):
                swing_highs.append(hi_c)
            if lo_c <= min(lo_win):
                swing_lows.append(lo_c)
        return swing_lows, swing_highs

    # ── Trend Direction ───────────────────────────────────────────────────────

    @staticmethod
    def _trend(levels: List[float], n: int = 3) -> str:
        """'bullish' if last n levels are rising, 'bearish' if falling, else 'neutral'."""
        if len(levels) < 2:
            return "neutral"
        recent = levels[-n:] if len(levels) >= n else levels
        if all(recent[i] > recent[i - 1] for i in range(1, len(recent))):
            return "bullish"
        if all(recent[i] < recent[i - 1] for i in range(1, len(recent))):
            return "bearish"
        return "neutral"

    # ── QUAD Fractal Validation ───────────────────────────────────────────────

    @staticmethod
    def _quad_fractal(swing_lows: List[float], swing_highs: List[float]) -> dict:
        """
        Check QUAD fractal validity:
        - F2 (2nd swing high) must be > F1 (1st swing high) → magnification
        - F4 (4th swing high) must surpass F2 → valid 2nd main fractal
        - If F4 ≤ F2 → trend weakening / invalid continuation

        Returns {valid, magnification, f1, f2, f3, f4}
        """
        result = {"valid": False, "magnification": False,
                  "miniaturization": False, "f2": None, "f4": None}

        if len(swing_highs) < 2:
            return result

        # Use last 4 swing highs as F1-F4 approximation
        recent_highs = swing_highs[-4:] if len(swing_highs) >= 4 else swing_highs

        if len(recent_highs) >= 2:
            f1, f2 = recent_highs[-2], recent_highs[-1]
            result["f2"] = f2
            result["magnification"]   = f2 > f1        # F2 copies and MAGNIFIES F1
            result["miniaturization"] = f2 < f1 * 0.9  # F2 is significantly smaller

        if len(recent_highs) >= 4:
            f2_ref, f4 = recent_highs[-3], recent_highs[-1]
            result["f4"]   = f4
            result["valid"] = f4 > f2_ref   # F4 must surpass F2 for valid QUAD

        return result

    # ── Tornado / Runaway Detection ───────────────────────────────────────────

    @staticmethod
    def _tornado(swing_lows: List[float], swing_highs: List[float], price: float) -> bool:
        """
        Tornado/Runaway: after impulse, correction stays below impulse peak.
        Condition: last swing high (impulse) > correction high, and price now rising.
        Bounded correction → strong runaway continuation expected.
        """
        if len(swing_highs) < 2 or len(swing_lows) < 1:
            return False
        last_impulse  = swing_highs[-2]   # the impulse that started
        last_high     = swing_highs[-1]   # the correction high
        last_low      = swing_lows[-1]    # correction bottom

        # Tornado: correction high stays below impulse high (correction is bounded)
        correction_bounded = last_high < last_impulse * 0.98
        # Price is now above the correction low (starting to run again)
        price_recovering   = price > last_low * 1.005
        return correction_bounded and price_recovering

    # ── End of Bearish Fractal Detection ─────────────────────────────────────

    @staticmethod
    def _bearish_end(swing_lows: List[float], price: float) -> bool:
        """
        Detects end of bearish fractal: series of lower lows STOPS.
        'نهاية الفراكتل الهابط بداية لفراكتل صاعد' — strongest buy signal.

        Condition:
        - At least 3 swing lows in a bearish sequence (each lower than previous)
        - But the LAST low is NOT lower than the one before it (series ended)
        - AND current price is ABOVE the last low (confirmation)
        """
        if len(swing_lows) < 3:
            return False
        recent = swing_lows[-4:]
        # Was there a bearish sequence? (at least 2 of the lows were declining)
        bearish_seq = sum(1 for i in range(1, len(recent) - 1) if recent[i] < recent[i - 1])
        if bearish_seq < 1:
            return False
        # The LAST two lows: did the last one stop declining?
        last_low      = recent[-1]
        prev_low      = recent[-2]
        seq_ended     = last_low >= prev_low * 0.998   # last low not lower (within 0.2%)
        price_above   = price > last_low * 1.002       # price confirmed above last low
        return seq_ended and price_above

    # ── Wave 3 Entry Detection ────────────────────────────────────────────────

    @staticmethod
    def _wave3_entry(swing_lows: List[float], swing_highs: List[float], price: float) -> bool:
        """
        Detect if price is entering what appears to be the 3rd wave.
        (Strongest wave in QUAD structure — best entry point)

        Pattern:
        - F1 impulse completed
        - F2 correction completed (didn't exceed F1 low)
        - F3 starting (price back above F1 high or approaching it)
        """
        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return False
        f1_high = swing_highs[-2]   # first impulse high
        f2_low  = swing_lows[-1]    # correction low
        f1_low  = swing_lows[-2] if len(swing_lows) >= 2 else 0

        # F2 correction: low stayed above F1's starting low (valid correction)
        valid_correction = f2_low > f1_low * 0.97
        # Price is now moving above F1's high (wave 3 breakout)
        wave3_start = price >= f1_high * 0.98
        return valid_correction and wave3_start

    # ── Main Analysis ─────────────────────────────────────────────────────────

    def analyze(self, klines: list, price: float) -> dict:
        """
        Full fractal analysis. Returns:
        {score, verdict, detail, warning, support, resistance,
         bull_trend, bear_trend, bulls_count, bears_count, _features}
        """
        if not klines or len(klines) < 10:
            return self._empty_result()

        # ── Detection ──
        bulls, bears         = self._detect_fractals(klines)
        swing_lows, swing_highs = self._swing_points(klines, lookback=3)

        if not bulls and not bears and not swing_highs:
            return self._empty_result()

        # ── Fractal support/resistance levels ──
        supports    = [b for b in bulls if b <= price * 1.02]
        resistances = [b for b in bears if b >= price * 0.98]
        nearest_sup = max(supports)    if supports    else None
        nearest_res = min(resistances) if resistances else None
        sup_dist    = ((price - nearest_sup)  / price * 100) if nearest_sup  else None
        res_dist    = ((nearest_res - price)  / price * 100) if nearest_res  else None

        # ── Structural features ──
        above_support   = nearest_sup is not None and sup_dist is not None and sup_dist <= 8.0
        near_support    = nearest_sup is not None and sup_dist is not None and sup_dist <= 2.0
        near_resistance = nearest_res is not None and res_dist is not None and res_dist <= 5.0

        fractal_break = False
        if len(bears) >= 2 and (nearest_res is None or (res_dist is not None and res_dist > 5.0)):
            fractal_break = price > bears[-2]

        bull_trend  = self._trend(bulls)
        bear_trend  = self._trend(bears)
        higher_lows = bull_trend == "bullish"
        lower_highs = bear_trend == "bearish"
        count_bonus = min(len(bulls) + len(bears), 10)

        # ── Advanced QUAD / wave features (from course) ──
        quad        = self._quad_fractal(swing_lows, swing_highs)
        bearish_end = self._bearish_end(swing_lows, price)
        tornado     = self._tornado(swing_lows, swing_highs, price)
        wave3       = self._wave3_entry(swing_lows, swing_highs, price)

        # ── Score ──
        w   = self._weights
        raw = 50.0
        raw += w["bearish_end"]     * (1 if bearish_end            else 0)
        raw += w["tornado_setup"]   * (1 if tornado                else 0)
        raw += w["quad_valid"]      * (1 if quad["valid"]          else 0)
        raw += w["wave3_entry"]     * (1 if wave3                  else 0)
        raw += w["above_support"]   * (1 if above_support          else 0)
        raw += w["near_support"]    * (1 if near_support           else 0)
        raw += w["fractal_break"]   * (1 if fractal_break          else 0)
        raw += w["higher_lows"]     * (1 if higher_lows            else 0)
        raw += w["magnification"]   * (1 if quad["magnification"]  else 0)
        raw += w["lower_highs"]     * (1 if lower_highs            else 0)
        raw += w["near_resistance"] * (1 if near_resistance        else 0)
        raw += w["miniaturization"] * (1 if quad["miniaturization"] else 0)
        raw += w["count_bonus"]     * (count_bonus / 10.0)

        score = max(10, min(100, round(raw)))

        # ── Verdict ──
        if score >= 80:
            verdict = "✅✅ فراكتل قوي جداً"
        elif score >= 65:
            verdict = "✅ فراكتل قوي"
        elif score >= 50:
            verdict = "🟡 فراكتل معتدل"
        else:
            verdict = "🔴 فراكتل ضعيف"

        # ── Detail text ──
        parts = []
        if bearish_end:
            parts.append("🔄 نهاية فراكتل هابط — بداية صاعد")
        if tornado:
            parts.append("🌪️ Tornado Setup — استمرار متوقع")
        if wave3:
            parts.append("〽️ دخول موجة 3")
        if quad["valid"]:
            parts.append("✅ QUAD صحيح (F4>F2)")
        if fractal_break:
            parts.append("كسر مقاومة فراكتلية ✅")
        if near_support and nearest_sup:
            parts.append(f"دعم فراكتلي ${nearest_sup:.4g} ({sup_dist:.1f}%↓)")
        elif above_support and nearest_sup:
            parts.append(f"فوق دعم ${nearest_sup:.4g}")
        if higher_lows:
            parts.append("Higher Lows ↗")
        if quad["magnification"]:
            parts.append("تكبير الموجات ✅")
        if quad["miniaturization"]:
            parts.append("تصغير الموجات ⚠️")
        if lower_highs:
            parts.append("Lower Highs ↘ ⚠️")

        detail = " · ".join(parts) if parts else "بنية فراكتلية محايدة"

        warning = None
        if near_resistance and nearest_res:
            warning = f"مقاومة فراكتلية ${nearest_res:.4g} (+{res_dist:.1f}%) ⚠️"

        features = {
            "bearish_end":     bearish_end,
            "tornado_setup":   tornado,
            "quad_valid":      quad["valid"],
            "wave3_entry":     wave3,
            "above_support":   above_support,
            "near_support":    near_support,
            "fractal_break":   fractal_break,
            "higher_lows":     higher_lows,
            "magnification":   quad["magnification"],
            "lower_highs":     lower_highs,
            "near_resistance": near_resistance,
            "miniaturization": quad["miniaturization"],
            "count_bonus":     count_bonus,
        }

        return {
            "score":        score,
            "verdict":      verdict,
            "detail":       detail,
            "warning":      warning,
            "support":      round(nearest_sup, 8) if nearest_sup else None,
            "resistance":   round(nearest_res, 8) if nearest_res else None,
            "bull_trend":   bull_trend,
            "bear_trend":   bear_trend,
            "bulls_count":  len(bulls),
            "bears_count":  len(bears),
            "bearish_end":  bearish_end,
            "tornado":      tornado,
            "quad_valid":   quad["valid"],
            "_features":    features,
        }

    def _empty_result(self) -> dict:
        return {
            "score": 50, "verdict": "⚪ لا بيانات فراكتلية",
            "detail": "", "warning": None,
            "support": None, "resistance": None,
            "bull_trend": "neutral", "bear_trend": "neutral",
            "bulls_count": 0, "bears_count": 0,
            "bearish_end": False, "tornado": False, "quad_valid": False,
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
        """Called when signal closes. Retrains every 10 new outcomes once ≥20 exist."""
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
            adj    = default * 0.4 + diff * abs(default) * 2.0 * 0.6
            self._weights[feat] = round(adj, 3)

        # Keep penalty features always negative
        for neg_feat in ("near_resistance", "lower_highs", "miniaturization"):
            if self._weights[neg_feat] > 0:
                self._weights[neg_feat] = -self._weights[neg_feat]

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
            "📐 *Fractal Agent v2 — ملخص النموذج*",
            f"مُدرَّب على: `{self._trained_on}` إشارة مكتملة",
            f"سجل التاريخ: `{len(self._history)}` نقطة",
            "",
            "*أوزان الميزات المتعلَّمة:*",
        ]
        for feat, w in self._weights.items():
            icon = "↑ إيجابي" if w > 0 else "↓ سلبي"
            lines.append(f"  `{feat:<20}` `{w:+.3f}` {icon}")
        lines += [
            "",
            "*المفاهيم المُدمَجة:*",
            "  • QUAD Fractal — الكسور الثنائية (F1→F4)",
            "  • Tornado/Runaway — تصحيح محدود → استمرار",
            "  • نهاية الفراكتل الهابط — أقوى إشارة شراء",
            "  • Higher/Lower Lows — اتجاه البنية الفراكتلية",
        ]
        return "\n".join(lines)

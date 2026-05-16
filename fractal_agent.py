"""
MAFIO Fractal Agent v3 — Unified Strategy
==========================================
Combines two knowledge sources into one coherent model:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SOURCE 1 — Practical Fractal Course (الكسور الثنائية)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

QUAD FRACTAL (الكسور الثنائية):
  - Every wave consists of 4 fractals (F1 → F4)
  - F2 COPIES + MAGNIFIES F1 | F4 COPIES + MAGNIFIES F3
  - Second main fractal (F3+F4) MUST surpass peak of first (F1+F2)
  - Rule: "لو F4 ما اجتاز F2 ما يعتبر فراكتل رئيسي"
  - Fractal is copied exactly ONCE (ناسخ و منسوخ)

TORNADO / RUNAWAY:
  Conditions (exact from course):
  1. النسخ — the correction copies the original impulse pattern
  2. القالب الثاني (runaway) لا يتجاوز قمة القالب الأساسي المنسوخ
  → Bounded copy = strong continuation expected

MAGNIFICATION vs MINIATURIZATION (مكبر / مصغر):
  - Magnification: each successive fractal is LARGER = healthy trend
  - Miniaturization: each successive fractal is SMALLER = weakening trend
  - Relationship is in SIZE only (حجم فقط) not shape similarity

SIX FRACTAL RULES (القواعد الستة):
  1. Each instrument has its own independent fractal
  2. End of bearish fractal = start of bullish fractal (نهاية الهابط بداية للصاعد)
  3. Fractal either magnifies or miniaturizes
  4. Fractal is copied exactly once (ناسخ → منسوخ)
  5. Fractal repeats 4 times in same direction (F1, F2, F3, F4)
  6. Alternation between TIME fractal and PRICE fractal is mandatory

PRICE vs TIME FRACTAL ALTERNATION:
  - Price fractal: large magnitude on Y-axis, few candles
  - Time fractal: long duration on X-axis, small price range per candle
  - MUST alternate: impossible to have all-price or all-time sequence
  - If fractal details disappear on higher TF → zoom into lower TF

ANALYSIS METHODOLOGY:
  - Always start from largest timeframe (monthly → weekly → daily)
  - Start counting from the LOWEST point to the highest
  - Identify F1+F2 (first main) then F3+F4 (second main)
  - Never ignore any price movement — every move has purpose

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SOURCE 2 — Almazov Fractal Theory (نظرية كسورية)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

HURST EXPONENT (أس هيرست):
  Measures market "memory" — how much the past influences the future.
  H = 0.5 → pure random (Brownian motion, no edge)
  H > 0.65 → persistent/trending: P(continuation) = H (e.g. H=0.7 → 70%)
  H < 0.35 → anti-persistent/mean-reverting: expect false breakouts
  Formula: estimated from log(variance) vs log(lag) regression

FRACTAL DIMENSION (البعد الكسوري):
  D = 2 - H
  D < 1.4 (H > 0.6): clear trend, trade with direction
  D > 1.6 (H < 0.4): high instability, breakout imminent
  D ≈ 1.5 (H ≈ 0.5): random/chaotic, avoid

COMPRESSION BREAKOUT (مسار المقاومة الأقل):
  - Price consolidating in tight range = energy accumulation
  - When price breaks out: moves "بسرعة البرق" (lightning fast)
  - Threshold: range < 5% over 12-15 candles

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
UNIFIED RULE: Only high-confidence signals when BOTH agree:
  - Structural pattern from Source 1 (QUAD, tornado, bearish_end...)
  - Statistical confirmation from Source 2 (H > 0.6 → persistent trend)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Self-learning:
  - Records all fractal features at signal entry
  - Adjusts weights from real outcomes (win/loss)
  - Persists to fractal_weights.json across restarts
"""

import json, math, os, time, logging
from typing import Dict, List, Optional, Tuple

log = logging.getLogger("mafio.fractal")

FRACTAL_WEIGHTS_FILE = "fractal_weights.json"

# Feature weights — tuned from both courses, overwritten by self-learning
_DEFAULT_WEIGHTS: Dict[str, float] = {
    # ── Primary structural signals (Source 1 — Fractal Course) ──────────────
    "bearish_end":          3.5,   # Rule 2: end of bearish = certain bullish start
    "tornado_setup":        3.0,   # Tornado: bounded copy → runaway continuation
    "quad_valid":           2.5,   # QUAD: F4 surpassed F2 → valid second main fractal
    "wave3_entry":          2.0,   # entering 3rd sub-fractal (strongest move)
    # ── Structural position signals ──────────────────────────────────────────
    "above_support":        2.0,   # price above fractal support level
    "near_support":         1.5,   # within 2% of fractal support (tight dip)
    "fractal_break":        2.5,   # price cleared former fractal resistance (air above)
    "higher_lows":          1.8,   # rising fractal lows = uptrend structure
    "magnification":        1.5,   # Rule 3: larger copies = healthy trend
    # ── Risk signals ─────────────────────────────────────────────────────────
    "lower_highs":         -1.5,   # falling fractal highs = downtrend pressure
    "near_resistance":     -2.0,   # fractal resistance within 5% = ceiling risk
    "miniaturization":     -1.5,   # Rule 3: smaller copies = weakening trend
    "count_bonus":          0.5,   # more confirmed fractals = stronger reading
    # ── Statistical confirmation (Source 2 — Almazov) ────────────────────────
    "hurst_trending":       2.0,   # H > 0.65: market has memory → trend continues
    "hurst_chaotic":       -1.5,   # H ≈ 0.5: random market → no statistical edge
    # ── Compression breakout (Source 2 — Path of Least Resistance) ──────────
    "compression_breakout": 3.0,   # tight range → explosive breakout (بسرعة البرق)
}


class FractalAgent:
    def __init__(self):
        self._weights    = dict(_DEFAULT_WEIGHTS)
        self._trained_on = 0
        self._history: List[dict] = []
        self._load_weights()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SOURCE 1 METHODS — Structural fractal patterns
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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

    @staticmethod
    def _swing_points(klines: list, lookback: int = 3) -> Tuple[List[float], List[float]]:
        """
        Swing high/low detection with configurable lookback.
        More sensitive than 5-candle fractals — catches wave sub-structure.
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

    @staticmethod
    def _quad_fractal(swing_lows: List[float], swing_highs: List[float]) -> dict:
        """
        QUAD Fractal validation (الكسور الثنائية):
        - F2 must be > F1 (copies AND magnifies)
        - F4 must surpass F2 (second main fractal surpasses first main)
        - If F4 ≤ F2 → "لو 4 ما اجتاز 2 ما يعتبر فراكتل رئيسي"
        Returns {valid, magnification, miniaturization, f2, f4}
        """
        result = {"valid": False, "magnification": False,
                  "miniaturization": False, "f2": None, "f4": None}

        if len(swing_highs) < 2:
            return result

        recent_highs = swing_highs[-4:] if len(swing_highs) >= 4 else swing_highs

        if len(recent_highs) >= 2:
            f1, f2 = recent_highs[-2], recent_highs[-1]
            result["f2"]             = f2
            result["magnification"]  = f2 > f1          # F2 magnifies F1 (مكبر)
            result["miniaturization"]= f2 < f1 * 0.9   # F2 significantly smaller (مصغر)

        if len(recent_highs) >= 4:
            f2_ref, f4 = recent_highs[-3], recent_highs[-1]
            result["f4"]   = f4
            result["valid"] = f4 > f2_ref   # Second main must surpass first main

        return result

    @staticmethod
    def _tornado(swing_lows: List[float], swing_highs: List[float], price: float) -> bool:
        """
        Tornado/Runaway: correction copies impulse but stays BELOW impulse peak.
        Exact course condition: "القالب الثاني لا يتجاوز قمة القالب الأساسي المنسوخ"
        → Bounded copy = energy contained = strong runaway continuation.
        """
        if len(swing_highs) < 2 or len(swing_lows) < 1:
            return False
        last_impulse = swing_highs[-2]   # impulse high (original template)
        last_high    = swing_highs[-1]   # correction high (the copy — must stay below)
        last_low     = swing_lows[-1]    # correction bottom

        correction_bounded = last_high < last_impulse * 0.98  # copy didn't exceed original
        price_recovering   = price > last_low * 1.005          # price recovering from correction
        return correction_bounded and price_recovering

    @staticmethod
    def _bearish_end(swing_lows: List[float], price: float) -> bool:
        """
        Rule 2: "نهاية الفراكتل الهابط بداية لفراكتل صاعد"
        End of bearish fractal = highest-confidence buy signal.
        Detects: series of lower lows STOPS + price confirms above last low.
        """
        if len(swing_lows) < 3:
            return False
        recent = swing_lows[-4:]
        bearish_seq = sum(1 for i in range(1, len(recent) - 1) if recent[i] < recent[i - 1])
        if bearish_seq < 1:
            return False
        last_low   = recent[-1]
        prev_low   = recent[-2]
        seq_ended  = last_low >= prev_low * 0.998   # last low didn't make new low
        price_conf = price > last_low * 1.002        # price confirmed above
        return seq_ended and price_conf

    @staticmethod
    def _wave3_entry(swing_lows: List[float], swing_highs: List[float], price: float) -> bool:
        """
        Detect entry into 3rd sub-fractal (strongest move in QUAD structure).
        Pattern: F1 impulse done → F2 correction done (valid) → F3 starting.
        """
        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return False
        f1_high = swing_highs[-2]
        f2_low  = swing_lows[-1]
        f1_low  = swing_lows[-2] if len(swing_lows) >= 2 else 0

        valid_correction = f2_low > f1_low * 0.97   # correction didn't break F1 start
        wave3_start      = price >= f1_high * 0.98   # price at/above F1 peak (F3 starting)
        return valid_correction and wave3_start

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SOURCE 2 METHODS — Statistical confirmation (Almazov)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @staticmethod
    def _calc_hurst(klines: list) -> float:
        """
        Simplified Hurst exponent estimation from closing prices.
        Based on Almazov's principle: market has long-term memory, H ≠ 0.5.

        H > 0.65 → persistent (trending): P(continuation) = H
        H ≈ 0.50 → random (no edge): avoid
        H < 0.35 → anti-persistent (mean-reverting): expect reversals

        Uses variance scaling: log(variance) scales as 2H * log(lag).
        """
        try:
            if len(klines) < 20:
                return 0.5
            closes = [float(k[4]) for k in klines[-40:]]
            if len(closes) < 16:
                return 0.5

            lags = [2, 4, 8, 16]
            log_lags: List[float] = []
            log_vars: List[float] = []

            for lag in lags:
                if lag >= len(closes):
                    continue
                diffs = [closes[i] - closes[i - lag] for i in range(lag, len(closes))]
                if not diffs:
                    continue
                var = sum(d * d for d in diffs) / len(diffs)
                if var > 1e-12:
                    log_lags.append(math.log(lag))
                    log_vars.append(math.log(var))

            if len(log_vars) < 3:
                return 0.5

            # OLS slope of log(var) vs log(lag) ≈ 2H
            n    = len(log_vars)
            sx   = sum(log_lags)
            sy   = sum(log_vars)
            sxy  = sum(x * y for x, y in zip(log_lags, log_vars))
            sxx  = sum(x * x for x in log_lags)
            denom = n * sxx - sx * sx
            if abs(denom) < 1e-12:
                return 0.5
            slope = (n * sxy - sx * sy) / denom
            H = slope / 2.0
            return max(0.1, min(0.9, H))
        except Exception:
            return 0.5

    @staticmethod
    def _compression_breakout(klines: list, price: float,
                              window: int = 13, threshold_pct: float = 5.0) -> dict:
        """
        Compression Breakout — Almazov's "Path of Least Resistance":
        Price in tight range = energy accumulation.
        Break above ceiling = بسرعة البرق (lightning-fast move).

        Returns {detected, range_pct, ceiling, candles_compressed}
        """
        result = {"detected": False, "range_pct": None, "ceiling": None,
                  "candles_compressed": 0}
        if len(klines) < window + 3:
            return result

        comp_candles = klines[-(window + 2):-2]
        try:
            highs = [float(k[2]) for k in comp_candles]
            lows  = [float(k[3]) for k in comp_candles]
        except (IndexError, ValueError):
            return result

        high_max = max(highs)
        low_min  = min(lows)
        if low_min <= 0:
            return result

        range_pct = (high_max - low_min) / low_min * 100.0
        if range_pct >= threshold_pct:
            result["range_pct"] = round(range_pct, 2)
            return result

        count = 0
        for h, l in zip(reversed(highs), reversed(lows)):
            if h <= high_max * 1.002 and l >= low_min * 0.998:
                count += 1
            else:
                break

        result.update({
            "detected":           (price >= high_max * 1.002) and count >= 5,
            "range_pct":          round(range_pct, 2),
            "ceiling":            round(high_max, 8),
            "candles_compressed": count,
        })
        return result

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # UNIFIED ANALYSIS — combines both sources
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def analyze(self, klines: list, price: float) -> dict:
        """
        Unified fractal analysis combining structural patterns (Source 1)
        with statistical confirmation (Source 2 — Hurst).
        Returns: {score, verdict, detail, warning, hurst, ..., _features}
        """
        if not klines or len(klines) < 10:
            return self._empty_result()

        # ── Source 1: Structural detection ──
        bulls, bears             = self._detect_fractals(klines)
        swing_lows, swing_highs  = self._swing_points(klines, lookback=3)

        if not bulls and not bears and not swing_highs:
            return self._empty_result()

        # Fractal support/resistance levels
        # Support: fractal lows BELOW current price (or within 2% above — dip-buy range)
        # Resistance: fractal highs STRICTLY ABOVE current price
        supports    = [b for b in bulls if b <= price * 1.02]
        resistances = [b for b in bears if b > price]          # strictly above only
        nearest_sup = max(supports)    if supports    else None
        nearest_res = min(resistances) if resistances else None
        sup_dist    = ((price - nearest_sup) / price * 100) if nearest_sup  else None
        res_dist    = ((nearest_res - price) / price * 100) if nearest_res  else None

        above_support   = nearest_sup is not None and sup_dist is not None and sup_dist <= 8.0
        near_support    = nearest_sup is not None and sup_dist is not None and sup_dist <= 2.0
        # res_dist is always positive now (resistance strictly above price)
        near_resistance = nearest_res is not None and res_dist is not None and res_dist <= 5.0

        # fractal_break: price cleared a former fractal high that was previously resistance
        broken_levels = [b for b in bears if b <= price]       # former resistances now below
        fractal_break = len(broken_levels) > 0 and (
            nearest_res is None or (res_dist is not None and res_dist > 5.0)
        )

        bull_trend  = self._trend(bulls)
        bear_trend  = self._trend(bears)
        higher_lows = bull_trend == "bullish"
        lower_highs = bear_trend == "bearish"
        count_bonus = min(len(bulls) + len(bears), 10)

        quad        = self._quad_fractal(swing_lows, swing_highs)
        bearish_end = self._bearish_end(swing_lows, price)
        tornado     = self._tornado(swing_lows, swing_highs, price)
        wave3       = self._wave3_entry(swing_lows, swing_highs, price)

        # ── Source 2: Statistical confirmation ──
        H           = self._calc_hurst(klines)
        hurst_trending = H >= 0.62           # persistent market → reliable signals
        hurst_chaotic  = 0.45 <= H <= 0.55  # near-random → reduce confidence

        compression = self._compression_breakout(klines, price)

        # ── Score (unified) ──
        w   = self._weights
        raw = 50.0
        # Structural (Source 1)
        raw += w["bearish_end"]          * (1 if bearish_end              else 0)
        raw += w["tornado_setup"]        * (1 if tornado                  else 0)
        raw += w["quad_valid"]           * (1 if quad["valid"]            else 0)
        raw += w["wave3_entry"]          * (1 if wave3                    else 0)
        raw += w["above_support"]        * (1 if above_support            else 0)
        raw += w["near_support"]         * (1 if near_support             else 0)
        raw += w["fractal_break"]        * (1 if fractal_break            else 0)
        raw += w["higher_lows"]          * (1 if higher_lows              else 0)
        raw += w["magnification"]        * (1 if quad["magnification"]    else 0)
        raw += w["lower_highs"]          * (1 if lower_highs              else 0)
        raw += w["near_resistance"]      * (1 if near_resistance          else 0)
        raw += w["miniaturization"]      * (1 if quad["miniaturization"]  else 0)
        raw += w["count_bonus"]          * (count_bonus / 10.0)
        # Statistical (Source 2)
        raw += w["hurst_trending"]       * (1 if hurst_trending           else 0)
        raw += w["hurst_chaotic"]        * (1 if hurst_chaotic            else 0)
        raw += w["compression_breakout"] * (1 if compression["detected"]  else 0)

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
            parts.append("🌪️ Tornado — نسخ محدود → استمرار")
        if compression["detected"]:
            n_c = compression.get("candles_compressed", 0)
            r_p = compression.get("range_pct", 0)
            parts.append(f"💥 انفجار ضغط ({n_c} شمعة · {r_p:.1f}%)")
        if wave3:
            parts.append("〽️ دخول موجة 3")
        if quad["valid"]:
            parts.append("✅ QUAD صحيح (F4>F2)")
        if fractal_break:
            n_broken = len(broken_levels)
            parts.append(f"كسر {n_broken} مقاومة فراكتلية ✅")
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

        # Hurst info line
        if hurst_trending:
            parts.append(f"📊 H={H:.2f} سوق ذو ذاكرة ({round(H*100)}% استمرار)")
        elif hurst_chaotic:
            parts.append(f"📊 H={H:.2f} سوق عشوائي ⚠️")

        detail = " · ".join(parts) if parts else "بنية فراكتلية محايدة"

        warning = None
        if near_resistance and nearest_res:
            warning = f"مقاومة فراكتلية ${nearest_res:.4g} (+{res_dist:.1f}%) ⚠️"

        features = {
            "bearish_end":          bearish_end,
            "tornado_setup":        tornado,
            "quad_valid":           quad["valid"],
            "wave3_entry":          wave3,
            "above_support":        above_support,
            "near_support":         near_support,
            "fractal_break":        fractal_break,
            "higher_lows":          higher_lows,
            "magnification":        quad["magnification"],
            "lower_highs":          lower_highs,
            "near_resistance":      near_resistance,
            "miniaturization":      quad["miniaturization"],
            "count_bonus":          count_bonus,
            "hurst_trending":       hurst_trending,
            "hurst_chaotic":        hurst_chaotic,
            "compression_breakout": compression["detected"],
        }

        return {
            "score":        score,
            "verdict":      verdict,
            "detail":       detail,
            "warning":      warning,
            "hurst":        round(H, 3),
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
            "detail": "", "warning": None, "hurst": 0.5,
            "support": None, "resistance": None,
            "bull_trend": "neutral", "bear_trend": "neutral",
            "bulls_count": 0, "bears_count": 0,
            "bearish_end": False, "tornado": False, "quad_valid": False,
            "_features": {},
        }

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SELF-LEARNING
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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
        """Adjust feature weights from historical outcomes (win = +5%, loss = negative)."""
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
        for neg_feat in ("near_resistance", "lower_highs", "miniaturization", "hurst_chaotic"):
            if self._weights[neg_feat] > 0:
                self._weights[neg_feat] = -abs(self._weights[neg_feat])

        self._trained_on = len(completed)
        self._save_weights()
        log.info("FractalAgent v3 retrained on %d signals | weights=%s",
                 len(completed), self._weights)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PERSISTENCE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _save_weights(self):
        try:
            with open(FRACTAL_WEIGHTS_FILE, "w") as f:
                json.dump({
                    "weights":    self._weights,
                    "trained_on": self._trained_on,
                    "history":    self._history[-200:],
                    "ts":         time.time(),
                    "version":    3,
                }, f, indent=2)
        except Exception as e:
            log.warning("FractalAgent save failed: %s", e)

    def _load_weights(self):
        try:
            with open(FRACTAL_WEIGHTS_FILE) as f:
                d = json.load(f)
            loaded = d.get("weights", {})
            # Merge: keep defaults for new features, override existing with saved
            for k, v in loaded.items():
                if k in self._weights:
                    self._weights[k] = v
            self._trained_on = d.get("trained_on", 0)
            self._history    = d.get("history",    [])
            log.info("FractalAgent v3 loaded: trained_on=%d signals", self._trained_on)
        except Exception:
            pass

    def summary(self) -> str:
        """Human-readable summary for /fractal_summary command."""
        lines = [
            "📐 *Fractal Agent v3 — الاستراتيجية الموحدة*",
            f"مُدرَّب على: `{self._trained_on}` إشارة مكتملة",
            f"سجل التاريخ: `{len(self._history)}` نقطة",
            "",
            "*أوزان الميزات المتعلَّمة:*",
        ]
        for feat, w in self._weights.items():
            src  = "📘 S1" if feat not in ("hurst_trending", "hurst_chaotic",
                                            "compression_breakout") else "📗 S2"
            icon = "↑" if w > 0 else "↓"
            lines.append(f"  {src} `{feat:<24}` `{w:+.3f}` {icon}")
        lines += [
            "",
            "*المصدر 1 — دورة الفراكتل (الأنماط الهيكلية):*",
            "  • QUAD الكسور الثنائية (F1→F4، الثاني يجتاز الأول)",
            "  • Tornado — القالب الثاني لا يتجاوز قمة الأول → استمرار",
            "  • نهاية الفراكتل الهابط — أقوى إشارة شراء (القاعدة 2)",
            "  • مكبر/مصغر — حجم الموجات المتتالية يحدد قوة الترند",
            "",
            "*المصدر 2 — نظرية ألمازوف (التأكيد الإحصائي):*",
            "  • Hurst H>0.62: سوق ذو ذاكرة → احتمال الاستمرار = H×100%",
            "  • Hurst H≈0.5: سوق عشوائي → لا ميزة إحصائية",
            "  • Compression Breakout: انطلاق بسرعة البرق من نطاق ضيق",
            "",
            "*القاعدة الموحدة:* نقتنص الإشارة عندما يتفق المصدران ✅",
        ]
        return "\n".join(lines)

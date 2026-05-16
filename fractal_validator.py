"""
FractalValidationAgent — Multi-Source Fractal Confluence Engine
==============================================================
Based on Almazov Fractal Framework JSON Matrix (5-book synthesis).

WHAT THIS MODULE ADDS (beyond fractal_agent.py):

1. FALSE BREAKOUT FILTER (1.618 Fibonacci)
   Rule from JSON: "Short-term divergence risk at 161.8% expansion"
   → When price reaches 1.618x the last swing range, flag as exhaustion zone.
   → "Immediately slash AI Agent Score" — applied as FCF multiplier 0.50

2. BASE MODEL 1.5 — WAVE STRUCTURE DETECTION
   Rule: Impulse alternates between 3-wave and 5-wave depending on cycle maturity.
   → 5-wave impulse = trending phase (primary trend) → boost
   → 3-wave structure = correction phase (inverted wave) → caution
   → Mismatch between macro/micro wave count = divergence → reduce FCF

3. SCALE NOISE DETECTOR (Scale Shifting Rule)
   Rule: "If current TF shows excessive noise, shift Scale Level Up"
   → Measures wick/body ratio as noise proxy
   → High noise → lower confidence → FCF penalty

4. MULTI-TIMEFRAME CONFLUENCE (Macro → Micro Protocol)
   Rule: "Initiate from Macro Scales (1D/4H) then drill to Micro (15M/5M)"
   → Compares structure of last 20% candles (micro) vs all candles (macro)
   → Agreement → FCF boost | Divergence → FCF penalty

5. REVERSAL EXTREME DETECTION
   Rule: "Cycle Bottom = Absolute Deep Cliff Support | Cycle Top = Peak Exhaustion"
   → Detect if price is near cycle extremes using percentile position
   → Near bottom + upward move = strong buy context

OUTPUT: Fractal Confluence Factor (FCF)
  FCF > 1.0 → boost signal score (strong fractal alignment)
  FCF = 1.0 → neutral
  FCF < 1.0 → reduce signal score (fractal warning)
  FCF range: 0.40 → 1.40

INTEGRATION: main.py applies FCF to signal score before build_signal().
"""

import math
import logging
from typing import List, Tuple, Optional

log = logging.getLogger("mafio.fractal_validator")

# Fibonacci levels used for extension/retracement analysis
_FIBO_EXTS = [1.272, 1.414, 1.618, 2.0, 2.618]
_FIBO_RETS = [0.236, 0.382, 0.500, 0.618, 0.786]

# FCF multipliers for each condition
_FCF_1618_BREACH      =  0.50   # price AT 1.618 extension → exhaust zone → slash
_FCF_1618_APPROACH    =  0.75   # price within 3% of 1.618 → warning
_FCF_5WAVE_ALIGN      =  1.15   # both TFs show 5-wave impulse → boost
_FCF_3WAVE_CORRECTION = -0.10   # current structure is 3-wave correction → penalty (additive)
_FCF_MTF_AGREE        =  1.12   # macro/micro trends agree → boost
_FCF_MTF_DIVERGE      =  0.85   # macro/micro diverge → reduce
_FCF_NOISE_HIGH       =  0.88   # excessive noise on fast TF → reduce
_FCF_CYCLE_BOTTOM     =  1.10   # price near cycle bottom (Deep Cliff Support) → boost
_FCF_EXT_FRACTAL      =  1.18   # external fractality = breakout imminent (PDF 3)


class FractalValidationAgent:
    """
    Calculates a Fractal Confluence Factor (FCF) to adjust signal scores.
    Uses only the klines already fetched — zero additional API calls.
    """

    # ─────────────────────────────────────────────────────
    # CORE PUBLIC METHOD
    # ─────────────────────────────────────────────────────

    def evaluate_fractal_confluence(self, klines: list, price: float) -> dict:
        """
        Main evaluation function.
        klines: candles already fetched by _check() (any interval)
        price:  current price

        Returns:
          fcf          : float multiplier to apply to signal score
          detail       : human-readable Arabic/English description
          false_breakout: True if price near 1.618 extension
          wave_macro   : 'impulse_5' | 'correction_3' | 'unknown'
          wave_micro   : same for last 20% of candles
          noise        : 0.0–1.0 noise score
        """
        if not klines or len(klines) < 15:
            return self._neutral("insufficient data")

        n = len(klines)
        # Macro view: all candles | Micro view: last ~20% (recent action)
        micro_start = max(n - max(20, n // 5), 0)
        macro_klines = klines
        micro_klines = klines[micro_start:]

        # ── 1. Swing reference from macro ──────────────────
        macro_lows, macro_highs = self._swing_points(macro_klines, lookback=2)
        # Fallback: use overall range when swing detection finds too few points
        if len(macro_lows) < 2 or len(macro_highs) < 2:
            try:
                swing_low  = min(float(k[3]) for k in macro_klines)
                swing_high = max(float(k[2]) for k in macro_klines)
            except (ValueError, IndexError):
                return self._neutral("corrupted data")
        else:
            swing_low  = min(macro_lows[-3:])  if len(macro_lows)  >= 3 else min(macro_lows)
            swing_high = max(macro_highs[-3:]) if len(macro_highs) >= 3 else max(macro_highs)

        # ── 2. Fibonacci 1.618 False Breakout Filter ───────
        fb_result = self._fib_false_breakout(swing_low, swing_high, price)

        # ── 3. Wave Structure (macro vs micro) ─────────────
        wave_macro = self._wave_structure(macro_klines)
        wave_micro = self._wave_structure(micro_klines)

        # ── 4. Noise Detection ─────────────────────────────
        noise = self._noise_ratio(micro_klines)

        # ── 5. MTF Trend Direction Alignment ───────────────
        macro_trend = self._trend_direction(macro_klines)
        micro_trend = self._trend_direction(micro_klines)
        mtf_agree   = (macro_trend == micro_trend) and macro_trend != "neutral"

        # ── 6. Cycle Position (Deep Cliff Support / Peak Exhaustion) ──
        cycle_pos = self._cycle_position(macro_klines, price)

        # ══ FCF CALCULATION ═════════════════════════════════
        fcf  = 1.0
        tags = []

        # Rule 1: 1.618 False Breakout — HIGHEST PRIORITY
        if fb_result["breach"]:
            fcf *= _FCF_1618_BREACH
            tags.append("🚨 1.618 Fib Exhaust — False Breakout Risk")
        elif fb_result["approach"]:
            fcf *= _FCF_1618_APPROACH
            tags.append(f"⚠️ Approaching 1.618 ({fb_result['proximity_pct']:.1f}% away)")

        # Rule 2: Wave Structure
        if wave_macro == "impulse_5" and wave_micro == "impulse_5":
            fcf *= _FCF_5WAVE_ALIGN
            tags.append("✅ 5-Wave Impulse (macro+micro aligned)")
        elif wave_micro == "correction_3":
            fcf += _FCF_3WAVE_CORRECTION   # additive penalty
            tags.append("〽️ 3-Wave Correction — Caution")

        # Rule 3: MTF Trend Alignment
        if mtf_agree:
            fcf *= _FCF_MTF_AGREE
            tags.append(f"📈 MTF Aligned ({macro_trend})")
        elif macro_trend != "neutral" and micro_trend != "neutral":
            fcf *= _FCF_MTF_DIVERGE
            tags.append(f"⚡ MTF Divergence (macro={macro_trend} · micro={micro_trend})")

        # Rule 4: Noise
        if noise > 0.68:
            fcf *= _FCF_NOISE_HIGH
            tags.append(f"📊 High Noise ({noise:.0%})")

        # Rule 5: Cycle Bottom support
        if cycle_pos == "bottom" and micro_trend == "bullish":
            fcf *= _FCF_CYCLE_BOTTOM
            tags.append("🔵 Cycle Bottom — Deep Cliff Support")
        elif cycle_pos == "top" and fb_result["breach"]:
            fcf *= 0.80   # top + 1.618 = double exhaustion warning
            tags.append("🔴 Cycle Top + 1.618 = Double Exhaustion")

        # Rule 6: External Fractality — breakout imminent (Nigmatullin & Chen 2023)
        ext_fractal = self._external_fractality(macro_klines)
        if ext_fractal and micro_trend == "bullish" and not fb_result["breach"]:
            fcf *= _FCF_EXT_FRACTAL
            tags.append("⚡ External Fractality — Breakout Imminent")

        # ── Clamp ──────────────────────────────────────────
        fcf = max(0.40, min(1.40, round(fcf, 3)))

        detail = " · ".join(tags) if tags else "✅ No fractal risks"

        return {
            "fcf":            fcf,
            "detail":         detail,
            "false_breakout": fb_result["breach"],
            "fib_1618":       round(fb_result["level_1618"], 8) if fb_result.get("level_1618") else None,
            "wave_macro":     wave_macro,
            "wave_micro":     wave_micro,
            "mtf_agree":      mtf_agree,
            "noise":          round(noise, 3),
            "cycle_pos":      cycle_pos,
            "macro_trend":    macro_trend,
            "micro_trend":    micro_trend,
        }

    # ─────────────────────────────────────────────────────
    # FIBONACCI 1.618 FALSE BREAKOUT FILTER
    # ─────────────────────────────────────────────────────

    @staticmethod
    def _fib_false_breakout(swing_low: float, swing_high: float, price: float) -> dict:
        """
        Checks if price has reached or is approaching the 1.618 Fibonacci extension.
        JSON rule: "Short-term divergence risk at 161.8% expansion"
        Extension is measured from swing_low, through swing_high, projected upward.
        """
        if swing_high <= swing_low or swing_low <= 0:
            return {"breach": False, "approach": False, "proximity_pct": 999.0}

        diff       = swing_high - swing_low
        level_1618 = swing_low + diff * 1.618   # 1.618 extension from low through high

        proximity_pct = abs(price - level_1618) / level_1618 * 100.0

        return {
            "breach":        price >= level_1618 * 0.99,   # AT or above 1.618
            "approach":      proximity_pct <= 3.0,          # within 3% of 1.618
            "proximity_pct": round(proximity_pct, 2),
            "level_1618":    level_1618,
        }

    # ─────────────────────────────────────────────────────
    # WAVE STRUCTURE DETECTION (Base Model 1.5)
    # ─────────────────────────────────────────────────────

    @staticmethod
    def _wave_structure(klines: list) -> str:
        """
        Classify price action as impulse (5-wave) or correction (3-wave).
        Base Model 1.5: impulse alternates 3-wave / 5-wave based on cycle maturity.

        Method: count alternating swing extremes.
          ≥ 8 alternating points → 5-wave impulse (complex, trending)
          4–6 alternating points → 3-wave correction
          < 4                    → unknown (insufficient data)
        """
        if len(klines) < 10:
            return "unknown"

        swing_highs: List[float] = []
        swing_lows:  List[float] = []
        for i in range(2, len(klines) - 2):
            try:
                hi = [float(klines[j][2]) for j in range(i - 2, i + 3)]
                lo = [float(klines[j][3]) for j in range(i - 2, i + 3)]
            except (IndexError, ValueError):
                continue
            if hi[2] >= max(hi):
                swing_highs.append(hi[2])
            if lo[2] <= min(lo):
                swing_lows.append(lo[2])

        total = len(swing_highs) + len(swing_lows)

        if total >= 8:
            return "impulse_5"
        elif 4 <= total <= 7:
            return "correction_3"
        return "unknown"

    # ─────────────────────────────────────────────────────
    # SWING POINTS
    # ─────────────────────────────────────────────────────

    @staticmethod
    def _swing_points(klines: list, lookback: int = 2) -> Tuple[List[float], List[float]]:
        """Detect swing highs and lows with given lookback."""
        lows:  List[float] = []
        highs: List[float] = []
        n = len(klines)
        for i in range(lookback, n - lookback):
            try:
                hi_w = [float(klines[j][2]) for j in range(i - lookback, i + lookback + 1)]
                lo_w = [float(klines[j][3]) for j in range(i - lookback, i + lookback + 1)]
                hi_c = float(klines[i][2])
                lo_c = float(klines[i][3])
            except (IndexError, ValueError):
                continue
            if hi_c >= max(hi_w):
                highs.append(hi_c)
            if lo_c <= min(lo_w):
                lows.append(lo_c)
        return lows, highs

    # ─────────────────────────────────────────────────────
    # NOISE RATIO (Scale Shifting Rule proxy)
    # ─────────────────────────────────────────────────────

    @staticmethod
    def _noise_ratio(klines: list) -> float:
        """
        Measure candle noise as wick_size / total_range.
        High ratio → market is choppy → scale shift recommended.
        Returns 0.0 (clean trend candles) to 1.0 (all wick, no body).
        """
        ratios = []
        for k in klines[-20:]:
            try:
                o, h, l, c = float(k[1]), float(k[2]), float(k[3]), float(k[4])
                total = h - l
                if total < 1e-12:
                    continue
                body = abs(c - o)
                wick = total - body
                ratios.append(wick / total)
            except (IndexError, ValueError):
                continue
        return sum(ratios) / len(ratios) if ratios else 0.5

    # ─────────────────────────────────────────────────────
    # TREND DIRECTION (MTF alignment)
    # ─────────────────────────────────────────────────────

    @staticmethod
    def _trend_direction(klines: list) -> str:
        """
        Simple trend: compare first-half average close vs second-half average close.
        Returns 'bullish' | 'bearish' | 'neutral'
        """
        if len(klines) < 6:
            return "neutral"
        try:
            closes = [float(k[4]) for k in klines]
            mid    = len(closes) // 2
            first  = sum(closes[:mid])  / mid
            second = sum(closes[mid:])  / (len(closes) - mid)
            diff   = (second - first) / first if first > 0 else 0
            if diff >  0.005:
                return "bullish"
            if diff < -0.005:
                return "bearish"
            return "neutral"
        except (ValueError, ZeroDivisionError):
            return "neutral"

    # ─────────────────────────────────────────────────────
    # CYCLE POSITION (Deep Cliff Support / Peak Exhaustion)
    # ─────────────────────────────────────────────────────

    @staticmethod
    def _cycle_position(klines: list, price: float) -> str:
        """
        Determine if price is near cycle bottom (Deep Cliff Support) or top (Peak Exhaustion).
        Uses percentile position within the candle range.
        Returns: 'bottom' | 'top' | 'mid'
        """
        if len(klines) < 10:
            return "mid"
        try:
            all_lows  = [float(k[3]) for k in klines]
            all_highs = [float(k[2]) for k in klines]
            low_min   = min(all_lows)
            high_max  = max(all_highs)
            rng       = high_max - low_min
            if rng < 1e-12:
                return "mid"
            pct = (price - low_min) / rng   # 0.0 = at bottom, 1.0 = at top
            if pct <= 0.18:
                return "bottom"
            if pct >= 0.82:
                return "top"
            return "mid"
        except (ValueError, ZeroDivisionError):
            return "mid"

    # ─────────────────────────────────────────────────────
    # EXTERNAL FRACTALITY (Nigmatullin & Chen 2023)
    # ─────────────────────────────────────────────────────

    @staticmethod
    def _external_fractality(klines: list) -> bool:
        """
        External Fractality Detection — Nigmatullin & Chen, Mathematics 2023.
        When the fractal scale (xi) exceeds the log-price range (Rg),
        the market is in an "anomalous" state → breakout/structural change imminent.

        Approximation: compare recent log-range (last 20%) scaled by N/n
        against total log-range. If scaled recent > total → external fractality.

        This is a novel signal not present in classical technical analysis.
        """
        try:
            closes = [float(k[4]) for k in klines if float(k[4]) > 0]
            if len(closes) < 15:
                return False
            import math as _math
            log_p = [_math.log(c) for c in closes]
            Rg    = max(log_p) - min(log_p)          # total log-range
            if Rg < 1e-8:
                return False
            # Recent = last 20% of candles
            n_recent  = max(5, len(log_p) // 5)
            recent_lp = log_p[-n_recent:]
            recent_rg = max(recent_lp) - min(recent_lp)
            # Scale factor: ratio of window sizes → approx xi exponent
            scale     = _math.log(len(log_p) / n_recent) if n_recent < len(log_p) else 0
            ln_xi_approx = scale + recent_rg
            return ln_xi_approx > Rg                 # external fractality condition
        except Exception:
            return False

    # ─────────────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────────────

    @staticmethod
    def _neutral(reason: str = "") -> dict:
        return {
            "fcf":            1.0,
            "detail":         reason or "neutral",
            "false_breakout": False,
            "fib_1618":       None,
            "wave_macro":     "unknown",
            "wave_micro":     "unknown",
            "mtf_agree":      False,
            "noise":          0.5,
            "cycle_pos":      "mid",
            "macro_trend":    "neutral",
            "micro_trend":    "neutral",
        }

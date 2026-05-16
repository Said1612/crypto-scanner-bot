"""
chaos_quant.py — Fractal Chaos Confluence Engine
=================================================
Sources:
  • Edgar Peters "Fractal Market Analysis" — Hurst regimes + DFA
  • Young Ho Seo "Fractal Wave Process 1.5" — Symmetry Box (1.272–1.618)
  • Mandelbrot "The Misbehavior of Markets" — Noah Effect (heavy tails)

WHAT THIS MODULE ADDS (not in fractal_agent / fractal_validator):

1. DFA HURST (Detrended Fluctuation Analysis)
   More robust than R/S for heavy-tailed crypto distributions.
   Combines with R/S for a blended H with confidence score.

2. MULTI-WINDOW HURST CONFIDENCE
   Estimate H at different sliding windows [10, 20, 50].
   Narrow spread across windows = high confidence in regime.

3. EDGAR PETERS REGIME FILTER
   H < 0.48 → Anti-persistent (Pink Noise) → -35% score breakouts, tag FAKE OUT RISK
   H 0.48-0.55 → Brownian → -10% mild penalty
   H > 0.55 → Persistent (Black Noise / Joseph Effect) → proceed to symmetry
   H > 0.65 → Strong persistent → +10% boost

4. YOUNG HO SEO SYMMETRY BOX
   Projects 1.272 and 1.618 Fibonacci extensions from last swing.
   Price BETWEEN 1.272 and 1.618 + H > 0.55 → FRACTAL SYMMETRY COMPLETION (+25%)
   (Below 1.272: no signal yet | Above 1.618: exhaustion, handled by fractal_validator)

5. NOAH EFFECT (Mandelbrot Heavy Tails)
   Total wick range / total candle range > 0.45 → heavy-tail warning.
   Signals that SL/TP should be expanded (institutional risk note).

INTEGRATION: main.py calls integrate_with_mafio_core() after FCF calculation.
Score is adjusted in-place before build_signal().
"""

import math
import logging
from typing import Dict, List, Optional, Tuple

log = logging.getLogger("mafio.chaos_quant")


# ══════════════════════════════════════════════════════════════
#  HURST — DFA + R/S COMBINED
# ══════════════════════════════════════════════════════════════

def _rs_hurst(prices: List[float]) -> float:
    """Classic R/S Rescaled Range analysis."""
    try:
        rets = [math.log(prices[i] / prices[i - 1])
                for i in range(1, len(prices)) if prices[i - 1] > 0]
        n = len(rets)
        if n < 10:
            return 0.5
        mean_r  = sum(rets) / n
        dev     = [r - mean_r for r in rets]
        cumdev: List[float] = []
        s = 0.0
        for d in dev:
            s += d
            cumdev.append(s)
        R   = max(cumdev) - min(cumdev)
        var = sum(d * d for d in dev) / n
        S   = math.sqrt(var) if var > 1e-16 else 1e-10
        return max(0.1, min(0.9, math.log(R / S) / math.log(n)))
    except Exception:
        return 0.5


def _dfa_hurst(prices: List[float], min_w: int = 8) -> float:
    """
    Detrended Fluctuation Analysis — Edgar Peters / Stanley framework.
    More robust than R/S for autocorrelated and heavy-tailed series.

    Steps:
      1. Integrate demeaned price series → Y(i)
      2. Divide into windows of size w, linearly detrend each segment
      3. Compute RMS fluctuation F(w) for each window size
      4. Slope of log(F) vs log(w) = H
    """
    try:
        n = len(prices)
        if n < 20:
            return 0.5
        mean_p = sum(prices) / n
        # Integrated demeaned series
        Y: List[float] = []
        s = 0.0
        for p in prices:
            s += p - mean_p
            Y.append(s)

        max_w = max(min_w + 1, n // 4)
        log_wins:   List[float] = []
        log_flucts: List[float] = []

        w = min_w
        while w <= max_w:
            segs = n // w
            if segs < 4:
                break
            f_sq = 0.0
            for seg in range(segs):
                seg_Y = Y[seg * w:(seg + 1) * w]
                xs    = list(range(w))
                # OLS linear fit on segment
                sx  = sum(xs)
                sy  = sum(seg_Y)
                sxy = sum(x * y for x, y in zip(xs, seg_Y))
                sxx = sum(x * x for x in xs)
                den = w * sxx - sx * sx
                if abs(den) > 1e-12:
                    slope = (w * sxy - sx * sy) / den
                    intercept = (sy - slope * sx) / w
                    trend = [slope * x + intercept for x in xs]
                else:
                    trend = [sy / w] * w
                res = [yv - tv for yv, tv in zip(seg_Y, trend)]
                f_sq += sum(r * r for r in res) / w
            F = math.sqrt(f_sq / segs)
            if F > 1e-12:
                log_wins.append(math.log(w))
                log_flucts.append(math.log(F))
            # Geometric step for log-uniform coverage
            w = max(w + 4, int(w * 1.5))

        if len(log_wins) < 3:
            return 0.5

        # OLS slope = H
        m   = len(log_wins)
        sx  = sum(log_wins)
        sy  = sum(log_flucts)
        sxy = sum(x * y for x, y in zip(log_wins, log_flucts))
        sxx = sum(x * x for x in log_wins)
        den = m * sxx - sx * sx
        if abs(den) < 1e-12:
            return 0.5
        H = (m * sxy - sx * sy) / den
        return max(0.1, min(0.9, H))
    except Exception:
        return 0.5


def calculate_hurst_exponent(price_array: List[float],
                             windows: List[int] = None) -> dict:
    """
    Combined Hurst estimate using R/S + DFA with confidence scoring.

    Returns:
      H          : blended estimate (0.1–0.9)
      H_rs       : R/S estimate
      H_dfa      : DFA estimate
      regime     : 'persistent' | 'weak_persistent' | 'random' | 'anti_persistent'
      confidence : 'high' | 'medium' | 'low'  (based on R/S vs DFA agreement)
    """
    if not price_array or len(price_array) < 20:
        return {"H": 0.5, "H_rs": 0.5, "H_dfa": 0.5,
                "regime": "random", "confidence": "low"}

    h_rs  = _rs_hurst(price_array)
    h_dfa = _dfa_hurst(price_array)
    H     = (h_rs + h_dfa) / 2.0

    spread     = abs(h_rs - h_dfa)
    confidence = "high" if spread < 0.08 else "medium" if spread < 0.15 else "low"

    if H >= 0.62:
        regime = "persistent"       # Black noise / Joseph Effect
    elif H >= 0.52:
        regime = "weak_persistent"
    elif H >= 0.48:
        regime = "random"           # Standard Brownian motion
    else:
        regime = "anti_persistent"  # Pink noise / mean-reverting

    return {
        "H":          round(H, 3),
        "H_rs":       round(h_rs, 3),
        "H_dfa":      round(h_dfa, 3),
        "regime":     regime,
        "confidence": confidence,
        "spread":     round(spread, 3),
    }


# ══════════════════════════════════════════════════════════════
#  EDGAR PETERS REGIME FILTER
# ══════════════════════════════════════════════════════════════

def apply_regime_filter(score: float, H: float,
                        is_breakout: bool = False) -> Tuple[float, str]:
    """
    Adjust signal score based on Hurst market regime (Edgar Peters).

    H < 0.48  → Anti-persistent: breakouts likely to fail
                 Breakout signals: -35% | Other: -20%
                 Tag: "⚠️ HIGH FAKE OUT RISK"
    H 0.48-0.55 → Borderline random: mild penalty -10%
    H > 0.55  → Persistent: no penalty
    H > 0.65  → Strong persistent: +10% boost
    """
    tag = ""
    if H < 0.48:
        pct  = 0.35 if is_breakout else 0.20
        score = score * (1.0 - pct)
        tag   = "⚠️ HIGH FAKE OUT RISK"
    elif H < 0.55:
        score = score * 0.90
    elif H > 0.65:
        score = min(10.0, score * 1.10)
    return round(score, 1), tag


# ══════════════════════════════════════════════════════════════
#  YOUNG HO SEO — SYMMETRY BOX (1.272 – 1.618)
# ══════════════════════════════════════════════════════════════

def evaluate_symmetry_box(swing_low: float, swing_high: float,
                          price: float) -> dict:
    """
    Young Ho Seo "Fractal Wave Process 1.5" Symmetry Box.

    From the last completed swing (low → high), project:
      • 1.272 extension = swing_low + 1.272 × (high - low)
      • 1.618 extension = swing_low + 1.618 × (high - low)

    Price INSIDE [1.272, 1.618]: structural symmetry completion zone.
    Combined with H > 0.55 → HIGHEST-CONFIDENCE ENTRY (not exhaustion).
    Price ABOVE 1.618: exhaustion — handled separately by fractal_validator.

    Returns:
      in_box     : price in [1.272, 1.618] zone
      near_box   : price within 2% below 1.272 (approaching)
      ext_1272   : 1.272 Fibonacci extension price level
      ext_1618   : 1.618 Fibonacci extension price level
    """
    if swing_high <= swing_low or swing_low <= 0:
        return {"in_box": False, "near_box": False,
                "ext_1272": None, "ext_1618": None}

    diff     = swing_high - swing_low
    ext_1272 = swing_low + diff * 1.272
    ext_1618 = swing_low + diff * 1.618

    in_box   = ext_1272 <= price <= ext_1618
    near_box = (ext_1272 * 0.98) <= price < ext_1272

    return {
        "in_box":        in_box,
        "near_box":      near_box,
        "ext_1272":      round(ext_1272, 8),
        "ext_1618":      round(ext_1618, 8),
        "proximity_pct": round(abs(price - ext_1272) / ext_1272 * 100, 2)
                         if not in_box else 0.0,
    }


# ══════════════════════════════════════════════════════════════
#  NOAH EFFECT — Heavy Tails (Mandelbrot)
# ══════════════════════════════════════════════════════════════

def _noah_effect(klines: list) -> Tuple[bool, float]:
    """
    Mandelbrot's Noah Effect: heavy-tailed (Pareto-Levy) distributions.
    Detected via wick density: total wick / total range across recent candles.

    > 0.45 → heavy tails active → SL/TP should be wider than Gaussian assumes.
    Returns (detected, wick_density)
    """
    try:
        wick_sum = 0.0
        rng_sum  = 0.0
        for k in klines[-20:]:
            h, l, o, c = float(k[2]), float(k[3]), float(k[1]), float(k[4])
            rng = h - l
            if rng > 0:
                body     = abs(c - o)
                wick_sum += rng - body
                rng_sum  += rng
        density = wick_sum / rng_sum if rng_sum > 0 else 0.0
        return density > 0.45, round(density, 3)
    except Exception:
        return False, 0.0


# ══════════════════════════════════════════════════════════════
#  MAIN INTEGRATION FUNCTION
# ══════════════════════════════════════════════════════════════

def integrate_with_mafio_core(klines: list, price: float,
                              current_score: float,
                              is_moonshot: bool = False) -> dict:
    """
    Full Chaos-Quant integration for MaFiO Sniper.

    Integration flow (from JSON blueprint):
      Step 1: Calculate Hurst regime (R/S + DFA blended)
      Step 2: Apply Edgar Peters regime filter to score
      Step 3: If persistent (H > 0.55), check Young Ho Seo Symmetry Box
      Step 4: Check Noah Effect (heavy-tail wick density warning)

    Returns:
      score        : adjusted signal score
      tags         : list of display tags for signal message
      H            : blended Hurst estimate
      regime       : market regime string
      symmetry_box : True if fractal symmetry confirmed
      noah_effect  : True if heavy tails detected
    """
    tags: List[str] = []

    if not klines or len(klines) < 15:
        return {"score": current_score, "tags": tags, "H": 0.5,
                "regime": "unknown", "symmetry_box": False, "noah_effect": False}

    try:
        closes = [float(k[4]) for k in klines]
    except (IndexError, ValueError):
        return {"score": current_score, "tags": tags, "H": 0.5,
                "regime": "unknown", "symmetry_box": False, "noah_effect": False}

    score = current_score

    # ── Step 1: Hurst Regime ─────────────────────────────────
    hr     = calculate_hurst_exponent(closes)
    H      = hr["H"]
    regime = hr["regime"]

    # ── Step 2: Edgar Peters Regime Filter ──────────────────
    score, regime_tag = apply_regime_filter(score, H, is_breakout=is_moonshot)
    if regime_tag:
        tags.append(regime_tag)

    # ── Step 3: Symmetry Box (only when market is persistent) ──
    sym_confirmed = False
    if H > 0.55:
        highs  = [float(k[2]) for k in klines]
        lows   = [float(k[3]) for k in klines]
        s_low  = min(lows[-40:]  if len(lows)  >= 40 else lows)
        s_high = max(highs[-40:] if len(highs) >= 40 else highs)
        sym    = evaluate_symmetry_box(s_low, s_high, price)

        if sym["in_box"]:
            score         = min(10.0, score * 1.25)
            sym_confirmed = True
            tags.append("💥 FRACTAL SYMMETRY COMPLETION")
        elif sym["near_box"] and sym.get("proximity_pct", 99) < 2.0:
            tags.append(f"📐 Approaching Symmetry Box ({sym['proximity_pct']:.1f}% away)")

    # ── Step 4: Noah Effect ──────────────────────────────────
    noah, wick_density = _noah_effect(klines)
    if noah:
        tags.append(f"🌊 Noah Effect ({wick_density:.0%} wicks — wide SL/TP advised)")

    return {
        "score":        round(score, 1),
        "tags":         tags,
        "H":            H,
        "H_rs":         hr.get("H_rs", H),
        "H_dfa":        hr.get("H_dfa", H),
        "regime":       regime,
        "confidence":   hr.get("confidence", "medium"),
        "symmetry_box": sym_confirmed,
        "noah_effect":  noah,
    }

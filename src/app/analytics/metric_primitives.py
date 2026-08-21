"""Metric primitive helpers — Phase 5B backend (pure, no UI).

Spec per docs/PHASE5_PLAN.md §3 Layer 1:
  Metric {value, delta vs benchmark, percentile, rank, trend sparkline, confidence, sample n}
  Rendering helpers: percentile bar already exists at styles.css (~1286) but add helpers for Benchmark line.

No UI yet — pure helpers that return dicts / HTML snippets / CSS values.
Used by frontend later for hero cards (xG/90 + +0.31 vs avg, 89th % bar, benchmark line).

References:
- percentiles.to_float / per90 helpers kept consistent with analytics/percentiles.py
- Benchmark line: vertical marker at benchmark value within the metric's domain.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Iterable

from .percentiles import percentile_rank, to_float


@dataclass
class Metric:
    """Canonical metric primitive for tactical intelligence cards.

    Attributes:
        value: The primary measured value (e.g. 2.14 xG/90).
        benchmark: Comparison baseline (e.g. league avg 1.83). None → no delta.
        delta: value - benchmark (computed if benchmark present).
        delta_pct: delta / benchmark * 100 (None when benchmark==0)
        percentile: 0..100 vs peer population (None if no peers)
        rank: 1-indexed rank within peers (1 = best) (None if no peers)
        total: population size for rank denominator (None if no peers)
        trend: sparkline values (last N, e.g. last 5 matches). None → no sparkline.
        confidence: (low, high) 95% interval around value (None if n too small)
        n: sample size (matches/minutes) underlying the value
        label: Human label for the metric (e.g. "xG/90")
        higher_is_better: Whether larger value is better (affects percentile/rank direction)
        unit: Optional unit string ("%", "xG", "km" etc.)
        honest_note: Provenance string for fallback cases.
    """
    value: float
    benchmark: float | None = None
    delta: float | None = field(default=None)
    delta_pct: float | None = field(default=None)
    percentile: float | None = field(default=None)
    rank: int | None = field(default=None)
    total: int | None = field(default=None)
    trend: list[float] | None = field(default=None)
    confidence: tuple[float, float] | None = field(default=None)
    n: int | None = field(default=None)
    label: str | None = field(default=None)
    higher_is_better: bool = field(default=True)
    unit: str | None = field(default=None)
    honest_note: str | None = field(default=None)

    def __post_init__(self) -> None:
        # Auto-compute delta if benchmark present and delta not already set
        if self.benchmark is not None and self.delta is None:
            self.delta = round(float(self.value) - float(self.benchmark), 4)
            if self.benchmark != 0:
                try:
                    self.delta_pct = round((self.delta / float(self.benchmark)) * 100.0, 2)
                except Exception:
                    self.delta_pct = None
            else:
                self.delta_pct = None


# ── Delta helpers ────────────────────────────────────────────────────────

def calculate_delta(value: float, benchmark: float | None) -> tuple[float | None, float | None]:
    """Return (delta, delta_pct) where delta = value - benchmark."""
    if benchmark is None:
        return None, None
    try:
        v = float(value)
        b = float(benchmark)
    except Exception:
        return None, None
    delta = round(v - b, 4)
    if b == 0:
        return delta, None
    delta_pct = round((delta / b) * 100.0, 2)
    return delta, delta_pct


def format_delta(delta: float | None, *, precision: int = 2, show_plus: bool = True) -> str:
    """Format delta as '+0.31' / '−0.12' / '—' when None."""
    if delta is None:
        return "—"
    try:
        d = float(delta)
    except Exception:
        return "—"
    sign = "+" if d > 0 and show_plus else ""
    # Use minus sign proper for negative
    if d == 0:
        return f"{0:.{precision}f}"
    return f"{sign}{d:.{precision}f}"


def delta_vs_benchmark_text(value: float, benchmark: float | None, *, unit: str = "") -> str:
    """Human text: '+0.31 vs avg' or '— vs avg' when no benchmark."""
    delta, delta_pct = calculate_delta(value, benchmark)
    if delta is None:
        return "— vs benchmark"
    # Example: "+0.31 vs avg (17.0%)" when useful
    base = format_delta(delta)
    if unit:
        base = f"{base} {unit}".strip()
    if delta_pct is not None and abs(delta_pct) >= 1:
        return f"{base} vs avg ({format_delta(delta_pct, precision=1)}%)"
    return f"{base} vs avg"


# ── Percentile / rank helpers (wraps percentiles.percentile_rank) ─────────

def calculate_percentile(
    value: float,
    population: Iterable[float] | None,
    *,
    higher_is_better: bool = True,
) -> float | None:
    """Percentile 0..100 for value against population. None when population empty/None."""
    if population is None:
        return None
    vals = [to_float(v) for v in population]
    # Filter NaN? to_float already handles
    if not vals:
        return None
    try:
        pct = percentile_rank(float(value), vals)
    except Exception:
        return None
    if not higher_is_better:
        # Invert so higher percentile always means better
        pct = round(100.0 - pct, 2)
    return pct


def calculate_rank(
    value: float,
    population: Iterable[float] | None,
    *,
    higher_is_better: bool = True,
) -> tuple[int | None, int | None]:
    """Return (rank, total) 1-indexed. 1 = best. None when no population."""
    if population is None:
        return None, None
    vals = [to_float(v) for v in population]
    if not vals:
        return None, None
    try:
        v = float(value)
    except Exception:
        return None, None
    # Rank: count of peers strictly better +1; ties share average rank but simple rank counts peers > value
    if higher_is_better:
        better = sum(1 for x in vals if x > v)
    else:
        better = sum(1 for x in vals if x < v)
    rank = better + 1
    total = len(vals)
    # Clamp rank to total
    rank = max(1, min(rank, total))
    return rank, total


def percentile_tier(percentile: float | None) -> str:
    """Map percentile to CSS tier class (matches .pct-fill.tier-*)."""
    if percentile is None:
        return "tier-avg"
    if percentile >= 80:
        return "tier-elite"
    if percentile >= 60:
        return "tier-good"
    if percentile >= 40:
        return "tier-avg"
    return "tier-low"


# ── Sparkline helpers ────────────────────────────────────────────────────

def sparkline_path(
    values: list[float] | None,
    *,
    width: int = 60,
    height: int = 16,
    pad: int = 2,
) -> str | None:
    """Return SVG path `d` attribute for a sparkline.

    Normalises values to height; empty/None → None.
    """
    if not values or len(values) < 2:
        return None
    try:
        vals = [float(v) for v in values]
    except Exception:
        return None
    v_min = min(vals)
    v_max = max(vals)
    span = v_max - v_min
    if span == 0:
        span = 1.0
        v_min -= 0.5
    n = len(vals)
    step_x = (width - 2 * pad) / max(n - 1, 1)
    points = []
    for i, v in enumerate(vals):
        x = pad + i * step_x
        # y inverted (0 top)
        y = pad + (height - 2 * pad) * (1 - (v - v_min) / span)
        points.append((x, y))
    # Build path string
    d = f"M {points[0][0]:.2f} {points[0][1]:.2f}"
    for x, y in points[1:]:
        d += f" L {x:.2f} {y:.2f}"
    return d


def sparkline_svg(
    values: list[float] | None,
    *,
    width: int = 60,
    height: int = 16,
    stroke: str = "var(--accent)",
    stroke_width: float = 1.5,
    fill: str = "none",
) -> str | None:
    """Return full <svg> string for sparkline, or None when insufficient data."""
    d = sparkline_path(values, width=width, height=height)
    if d is None:
        return None
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" aria-hidden="true">'
        f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}" '
        f'stroke-linecap="round" stroke-linejoin="round" />'
        f"</svg>"
    )


# ── Confidence / sample helpers ──────────────────────────────────────────

def wilson_interval(
    successes: int,
    n: int,
    *,
    z: float = 1.96,
) -> tuple[float, float] | None:
    """Wilson score interval for a proportion (e.g. shot conversion)."""
    if n <= 0:
        return None
    try:
        p = successes / n
    except Exception:
        return None
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    low = (centre - margin) / denom
    high = (centre + margin) / denom
    return (max(0.0, round(low, 4)), min(1.0, round(high, 4)))


def normal_ci(
    values: Iterable[float] | None,
    *,
    confidence_z: float = 1.96,
) -> tuple[float, float] | None:
    """Normal approx 95% CI around mean of values. None when n<2."""
    if values is None:
        return None
    vals = [to_float(v) for v in values]
    vals = [v for v in vals if not math.isnan(v)]
    n = len(vals)
    if n < 2:
        return None
    mean = sum(vals) / n
    var = sum((v - mean) ** 2 for v in vals) / n
    se = math.sqrt(var) / math.sqrt(n)
    if se == 0:
        return (round(mean, 4), round(mean, 4))
    low = mean - confidence_z * se
    high = mean + confidence_z * se
    return (round(low, 4), round(high, 4))


def confidence_level(n: int | None) -> str:
    """Qualitative confidence label based on sample size."""
    if n is None:
        return "unknown"
    if n >= 30:
        return "high"
    if n >= 10:
        return "medium"
    if n >= 3:
        return "low"
    return "very-low"


# ── Benchmark line helpers (for .pct-track overlay) ───────────────────────

def benchmark_line_position(
    benchmark: float,
    domain_min: float = 0.0,
    domain_max: float = 100.0,
) -> float | None:
    """Return benchmark position as 0..100 % within domain.

    Example: benchmark=1.83, domain 0..3.0 → 61%. Clamped to 0..100.
    None when domain invalid or benchmark None.
    """
    if benchmark is None:
        return None
    try:
        b = float(benchmark)
        dmin = float(domain_min)
        dmax = float(domain_max)
    except Exception:
        return None
    if dmax == dmin:
        return 50.0
    pct = (b - dmin) / (dmax - dmin) * 100.0
    return max(0.0, min(100.0, round(pct, 2)))


def benchmark_line_style(
    benchmark: float | None,
    domain_min: float = 0.0,
    domain_max: float = 100.0,
) -> str | None:
    """CSS style string for benchmark vertical line: 'left:42.00%' etc."""
    pos = benchmark_line_position(benchmark, domain_min, domain_max) if benchmark is not None else None  # type: ignore
    if pos is None:
        return None
    return f"left:{pos:.2f}%"


def benchmark_line_html(
    benchmark: float | None,
    domain_min: float = 0.0,
    domain_max: float = 100.0,
    *,
    label: str = "avg",
    color: str = "var(--muted)",
) -> str | None:
    """Return HTML snippet for benchmark line overlay inside .pct-track container.

    Usage in template:
      <div class="pct-track" style="position:relative">
        <div class="pct-fill ..." style="width:..."></div>
        {benchmark_html}
      </div>
    """
    pos = benchmark_line_position(benchmark, domain_min, domain_max) if benchmark is not None else None  # type: ignore
    if pos is None:
        return None
    # Vertical line; uses absolute positioning inside relative pct-track
    return (
        f'<div class="benchmark-line" '
        f'style="position:absolute;top:0;bottom:0;width:2px;'
        f'background:{color};left:{pos:.2f}%;transform:translateX(-1px);" '
        f'title="Benchmark {benchmark:.2f} ({label})" aria-label="Benchmark {label} {benchmark:.2f}"></div>'
    )


# ── Percentile bar helpers (already CSS at styles.css ~1286) ─────────────

def percentile_bar_style(percentile: float | None) -> str:
    """CSS width style for .pct-fill: 'width:89.00%'."""
    if percentile is None:
        return "width:0%"
    try:
        p = float(percentile)
    except Exception:
        return "width:0%"
    p = max(0.0, min(100.0, p))
    return f"width:{max(4.0, p):.2f}%"


def percentile_bar_html(
    percentile: float | None,
    value: float | None = None,
    *,
    benchmark: float | None = None,
    domain_min: float = 0.0,
    domain_max: float = 100.0,
) -> str:
    """Return HTML for percentile bar with optional benchmark overlay."""
    tier = percentile_tier(percentile)
    style = percentile_bar_style(percentile)
    bench_html = ""
    if benchmark is not None:
        bh = benchmark_line_html(benchmark, domain_min, domain_max)
        if bh:
            bench_html = bh
    pct_text = f"{percentile:.0f}%" if percentile is not None else "—"
    val_text = f"{value:.2f}" if value is not None else ""
    return (
        f'<div class="pct-bar-cell">'
        f'<div class="pct-track" style="position:relative">'
        f'<div class="pct-fill {tier}" style="{style}"></div>'
        f"{bench_html}"
        f"</div>"
        f'<span class="pct-val">{pct_text}</span>'
        f'<span class="pct-raw">{val_text}</span>'
        f"</div>"
    )


# ── Factory & serialization ──────────────────────────────────────────────

def create_metric(
    value: float,
    *,
    benchmark: float | None = None,
    population: Iterable[float] | None = None,
    trend: list[float] | None = None,
    n: int | None = None,
    label: str | None = None,
    higher_is_better: bool = True,
    unit: str | None = None,
    confidence: tuple[float, float] | None = None,
    honest_note: str | None = None,
) -> Metric:
    """Factory that computes delta, percentile, rank, confidence from inputs."""
    try:
        v = float(value)
    except Exception:
        v = 0.0
    delta, delta_pct = calculate_delta(v, benchmark)
    percentile = calculate_percentile(v, population, higher_is_better=higher_is_better) if population is not None else None
    rank, total = calculate_rank(v, population, higher_is_better=higher_is_better) if population is not None else (None, None)
    # Derive n from trend if not provided
    if n is None and trend is not None:
        n = len(trend)
    # Confidence: prefer provided, else derive via normal_ci on trend if available
    if confidence is None and trend is not None and len(trend) >= 2:
        confidence = normal_ci(trend)
    return Metric(
        value=round(v, 4),
        benchmark=benchmark if benchmark is None else round(float(benchmark), 4),
        delta=delta,
        delta_pct=delta_pct,
        percentile=percentile,
        rank=rank,
        total=total,
        trend=list(trend) if trend is not None else None,
        confidence=confidence,
        n=n,
        label=label,
        higher_is_better=higher_is_better,
        unit=unit,
        honest_note=honest_note,
    )


def metric_to_dict(metric: Metric) -> dict:
    """Serialise Metric to JSON-friendly dict (for API responses)."""
    d = asdict(metric)
    # Ensure floats are round-tripped nicely
    for k in ("value", "benchmark", "delta", "delta_pct", "percentile"):
        if d.get(k) is not None:
            try:
                d[k] = round(float(d[k]), 4)
            except Exception:
                pass
    # Add rendered helpers
    d["delta_text"] = format_delta(d.get("delta"))
    d["delta_vs_benchmark"] = delta_vs_benchmark_text(metric.value, metric.benchmark, unit=metric.unit or "")
    d["benchmark_line_style"] = benchmark_line_style(metric.benchmark, 0, 100) if metric.benchmark is not None else None
    d["percentile_tier"] = percentile_tier(metric.percentile)
    d["percentile_bar_style"] = percentile_bar_style(metric.percentile)
    d["confidence_label"] = confidence_level(metric.n)
    if metric.trend is not None:
        d["sparkline_path"] = sparkline_path(metric.trend)
        d["sparkline_svg"] = sparkline_svg(metric.trend)
    return d


def metric_delta_calc(value: float, benchmark: float | None) -> dict:
    """Small helper used in tests: returns delta dict for quick assertions."""
    delta, delta_pct = calculate_delta(value, benchmark)
    return {
        "value": value,
        "benchmark": benchmark,
        "delta": delta,
        "delta_pct": delta_pct,
        "delta_text": format_delta(delta),
        "higher": (delta or 0) > 0,
        "lower": (delta or 0) < 0,
    }

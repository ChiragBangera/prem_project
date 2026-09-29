// Chart primitives: scales, ticks, path builders, a responsive SVG frame and colour ramps.
// Everything is plain SVG so colours come from CSS tokens and both themes work without JS.
import { html, useEffect, useRef, useState } from "../lib/html.js";

// ------------------------------------------------------------------ scales

export function scaleLinear(domain, range) {
  const [d0, d1] = domain;
  const [r0, r1] = range;
  const k = (r1 - r0) / (d1 - d0 || 1);
  const f = (v) => r0 + (v - d0) * k;
  f.invert = (r) => d0 + (r - r0) / k;
  f.domain = domain;
  f.range = range;
  return f;
}

export function scaleBand(keys, range, padding = 0.25) {
  const [r0, r1] = range;
  const n = keys.length || 1;
  const step = (r1 - r0) / n;
  const bw = step * (1 - padding);
  const index = new Map(keys.map((k, i) => [k, i]));
  const f = (k) => r0 + (index.get(k) ?? 0) * step + (step - bw) / 2;
  f.bandwidth = bw;
  f.step = step;
  f.center = (k) => f(k) + bw / 2;
  return f;
}

export function niceStep(span, count) {
  const raw = span / Math.max(1, count);
  const pow = Math.pow(10, Math.floor(Math.log10(raw || 1)));
  const err = raw / pow;
  const mult = err >= 7.5 ? 10 : err >= 3.5 ? 5 : err >= 1.5 ? 2 : 1;
  return mult * pow;
}

export function niceTicks(min, max, count = 5) {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [0, 1];
  if (min === max) { min -= 1; max += 1; }
  const step = niceStep(max - min, count);
  const start = Math.ceil(min / step - 1e-9) * step;
  const out = [];
  for (let v = start; v <= max + step * 1e-9; v += step) out.push(Math.abs(v) < step * 1e-9 ? 0 : +v.toFixed(10));
  return out;
}

/** Expand [min,max] outward to the nearest nice tick values. */
export function niceExtent(min, max, count = 5) {
  if (min === max) { min -= 1; max += 1; }
  const step = niceStep(max - min, count);
  return [Math.floor(min / step + 1e-9) * step, Math.ceil(max / step - 1e-9) * step];
}

export const extent = (values, pad = 0) => {
  let lo = Infinity, hi = -Infinity;
  for (const v of values) if (Number.isFinite(v)) { if (v < lo) lo = v; if (v > hi) hi = v; }
  if (!Number.isFinite(lo)) return [0, 1];
  const span = hi - lo || 1;
  return [lo - span * pad, hi + span * pad];
};

export const tickFormat = (step) => (v) => {
  const d = step >= 1 ? 0 : step >= 0.1 ? 1 : step >= 0.01 ? 2 : 3;
  return v < 0 ? "−" + Math.abs(v).toFixed(d) : v.toFixed(d);
};

// ------------------------------------------------------------------ paths

export function linePath(xs, ys, x, y, { gaps = true } = {}) {
  let d = "";
  let pen = false;
  for (let i = 0; i < xs.length; i++) {
    const yv = ys[i];
    if (yv == null || !Number.isFinite(yv)) { pen = false; if (!gaps) continue; continue; }
    d += `${pen ? "L" : "M"}${x(xs[i]).toFixed(1)},${y(yv).toFixed(1)}`;
    pen = true;
  }
  return d;
}

export function stepPath(xs, ys, x, y) {
  let d = "";
  for (let i = 0; i < xs.length; i++) {
    const px = x(xs[i]).toFixed(1), py = y(ys[i]).toFixed(1);
    d += i === 0 ? `M${px},${py}` : `H${px}V${py}`;
  }
  return d;
}

export function areaPath(xs, ys, x, y, base) {
  if (!xs.length) return "";
  let d = `M${x(xs[0]).toFixed(1)},${y(base).toFixed(1)}`;
  xs.forEach((v, i) => { d += `L${x(v).toFixed(1)},${y(ys[i]).toFixed(1)}`; });
  return d + `L${x(xs[xs.length - 1]).toFixed(1)},${y(base).toFixed(1)}Z`;
}

// ------------------------------------------------------------------ colour ramps (CSS colour-mix on theme tokens)

/** t in [0,1] -> a sequential blue from the theme ramp. */
export function seqColor(t) {
  const x = Math.max(0, Math.min(1, t)) * 6;
  const lo = Math.min(5, Math.floor(x));
  const frac = Math.round((x - lo) * 100);
  return `color-mix(in oklab, var(--seq-${lo + 1}00), var(--seq-${lo + 2}00) ${frac}%)`;
}

/** v in [-1,1] -> diverging: orange (below) - neutral - blue (above). */
export function divColor(v) {
  const a = Math.max(-1, Math.min(1, v));
  return a >= 0
    ? `color-mix(in oklab, var(--mid), var(--pos) ${Math.round(a * 100)}%)`
    : `color-mix(in oklab, var(--mid), var(--neg) ${Math.round(-a * 100)}%)`;
}

/** Ink colour that stays legible on a ramp cell at t in [0,1] (dark ramp end = light text). */
export const heatInk = (t) => (t > 0.5 ? "#fff" : "var(--ink)");

// ------------------------------------------------------------------ frame

export function useWidth(ref, initial = 640) {
  const [w, setW] = useState(initial);
  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const measure = () => setW((prev) => { const next = Math.max(160, Math.floor(el.clientWidth)); return Math.abs(prev - next) > 1 ? next : prev; });
    measure();
    if (typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return w;
}

/**
 * Responsive SVG frame. `children` is a render function receiving inner geometry.
 * The <svg> is the accessible image; a data-table alternative is provided by pages where it matters.
 */
export function Frame({ height = 280, margin, label, children, class: klass, style, onLeave, after }) {
  const ref = useRef(null);
  const w = useWidth(ref);
  const m = { top: 10, right: 16, bottom: 28, left: 40, ...(margin || {}) };
  const iw = Math.max(20, w - m.left - m.right);
  const ih = Math.max(20, height - m.top - m.bottom);
  return html`<div class=${"chart " + (klass || "")} ref=${ref} style=${style}>
    <svg width=${w} height=${height} viewBox=${`0 0 ${w} ${height}`} role="img" aria-label=${label} onMouseLeave=${onLeave}>
      <g transform=${`translate(${m.left},${m.top})`}>${children({ w, height, iw, ih, m })}</g>
    </svg>
    ${after || null}
  </div>`;
}

// ------------------------------------------------------------------ axes

export function AxisY({ scale, ticks, iw, format = (v) => String(v), grid = true, zero }) {
  return html`<g>
    ${ticks.map((t) => html`<g key=${t} transform=${`translate(0,${scale(t).toFixed(1)})`}>
      ${grid ? html`<line class=${zero && t === 0 ? "axis-line" : "grid-line"} x1="0" x2=${iw} />` : null}
      <text class="tick-label" x="-8" dy="0.32em" text-anchor="end">${format(t)}</text>
    </g>`)}
  </g>`;
}

export function AxisX({ scale, ticks, ih, format = (v) => String(v), grid = false, anchor = "middle", dy = 20 }) {
  return html`<g transform=${`translate(0,${ih})`}>
    <line class="axis-line" x1=${scale.range[0]} x2=${scale.range[1]} />
    ${ticks.map((t) => html`<g key=${t} transform=${`translate(${scale(t).toFixed(1)},0)`}>
      ${grid ? html`<line class="grid-line" y1=${-ih} y2="0" />` : html`<line class="axis-line" y1="0" y2="4" />`}
      <text class="tick-label" y=${dy} text-anchor=${anchor}>${format(t)}</text>
    </g>`)}
  </g>`;
}

/** Nearest index in a sorted numeric array. */
export function nearest(values, target) {
  let lo = 0, hi = values.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    values[mid] < target ? (lo = mid) : (hi = mid);
  }
  return Math.abs(values[lo] - target) <= Math.abs(values[hi] - target) ? lo : hi;
}

export function svgPoint(event, el) {
  const rect = el.getBoundingClientRect();
  return { x: event.clientX - rect.left, y: event.clientY - rect.top };
}

/** Legend that doubles as a series toggle when `onToggle` is given. */
export function Legend({ items, hidden = [], onToggle }) {
  return html`<div class="legend" role=${onToggle ? "group" : undefined}>
    ${items.map((it) => {
      const swatch = html`<span class=${"swatch " + (it.shape || "")} style=${{ background: it.color }}></span>`;
      return onToggle
        ? html`<button type="button" key=${it.key} class="item" aria-pressed=${String(!hidden.includes(it.key))} onClick=${() => onToggle(it.key)}>${swatch}${it.label}</button>`
        : html`<span key=${it.key} class="item">${swatch}${it.label}</span>`;
    })}
  </div>`;
}

/** Table alternative to a chart, tucked away until asked for. Every drawn number is reachable without hovering. */
export function ChartTable({ label = "View the data", columns, rows }) {
  return html`<details class="chart-table-toggle">
    <summary>${label}</summary>
    <div class="chart-table"><table class="data dense">
      <thead><tr>${columns.map((c) => html`<th key=${c.key} class=${c.num ? "num" : ""}>${c.label}</th>`)}</tr></thead>
      <tbody>${rows.map((r, i) => html`<tr key=${i}>${columns.map((c) => html`<td key=${c.key} class=${c.num ? "num" : ""}>${c.render ? c.render(r) : r[c.key]}</td>`)}</tr>`)}</tbody>
    </table></div>
  </details>`;
}

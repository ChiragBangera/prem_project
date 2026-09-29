// Line charts: multi-series with crosshair, sparklines and the league rank-trajectory chart.
import { html, useState } from "../lib/html.js";
import { tooltip } from "../lib/tooltip.js";
import { nf, ordinal } from "../lib/format.js";
import { Frame, AxisX, AxisY, ChartTable, areaPath, extent, linePath, nearest, niceExtent, niceTicks, scaleLinear, tickFormat } from "./core.js";

export const SERIES_COLORS = ["var(--c1)", "var(--c2)", "var(--c3)", "var(--c4)", "var(--c5)", "var(--c6)", "var(--c7)", "var(--c8)"];

/** Spread end labels apart so they never overlap. */
function spread(items, minGap, lo, hi) {
  const sorted = [...items].sort((a, b) => a.y - b.y);
  for (let i = 1; i < sorted.length; i++) if (sorted[i].y - sorted[i - 1].y < minGap) sorted[i].y = sorted[i - 1].y + minGap;
  const over = sorted.length ? sorted[sorted.length - 1].y - hi : 0;
  if (over > 0) sorted.forEach((s) => { s.y -= over; });
  sorted.forEach((s) => { s.y = Math.max(lo, s.y); });
  return sorted;
}

export function LineChart({
  x, series, height = 260, yFormat, xFormat, yDomain, xDomain, xTicks, zeroLine = false, invertY = false, endLabels = true,
  tooltipTitle, tooltipFormat, label = "Line chart", yLabel, xLabel, markers, dataTable = true,
}) {
  const [hover, setHover] = useState(null);
  const all = series.flatMap((s) => s.values).filter((v) => v != null && Number.isFinite(v));
  const [dy0, dy1] = yDomain || niceExtent(...extent(all, 0.06));
  const [dx0, dx1] = xDomain || [x[0], x[x.length - 1]];
  const margin = { top: 12, right: endLabels ? 58 : 16, bottom: xLabel ? 44 : 30, left: yLabel ? 58 : 46 };

  const tableCols = [{ key: "x", label: xLabel || "Point", render: (r) => (tooltipTitle ? tooltipTitle(r.i) : xFormat ? xFormat(r.x) : r.x) }, ...series.map((sr, k) => ({ key: sr.key || k, label: sr.label, num: true, render: (r) => (r.v[k] == null ? "–" : tooltipFormat ? tooltipFormat(r.v[k], sr) : nf(r.v[k], 2)) }))];
  const tableRows = x.map((xv, i) => ({ i, x: xv, v: series.map((sr) => sr.values[i]) }));
  return html`<${Frame} height=${height} label=${label} margin=${margin} onLeave=${() => { setHover(null); tooltip.hide(); }} after=${dataTable ? html`<${ChartTable} columns=${tableCols} rows=${tableRows} />` : null}>
    ${({ iw, ih }) => {
      const sx = scaleLinear([dx0, dx1], [0, iw]);
      const sy = scaleLinear([dy0, dy1], invertY ? [0, ih] : [ih, 0]);
      const yt = niceTicks(dy0, dy1, Math.max(3, Math.floor(ih / 52)));
      const xt = xTicks || niceTicks(dx0, dx1, Math.max(3, Math.floor(iw / 80)));
      const fy = yFormat || tickFormat(yt[1] - yt[0] || 1);
      const move = (e) => {
        const rect = e.currentTarget.getBoundingClientRect();
        const i = nearest(x, sx.invert(e.clientX - rect.left));
        setHover(i);
        const rows = series.filter((s) => s.values[i] != null).map((s) => ({ label: s.label, value: tooltipFormat ? tooltipFormat(s.values[i], s) : nf(s.values[i], 2), color: s.color }));
        tooltip.move(e, html`<div>${tooltipTitle ? html`<div class="tt-title">${tooltipTitle(i)}</div>` : null}${rows.map((r) => html`<div class="tt-row" key=${r.label}><span class="k"><i class="key" style=${{ background: r.color }}></i>${r.label}</span><span class="v">${r.value}</span></div>`)}</div>`);
      };
      const ends = endLabels
        ? spread(series.map((s, k) => {
            let last = s.values.length - 1;
            while (last >= 0 && (s.values[last] == null || !Number.isFinite(s.values[last]))) last -= 1;
            return last < 0 ? null : { s, k, y: sy(s.values[last]), v: s.values[last] };
          }).filter(Boolean), 14, 6, ih - 6)
        : [];
      return html`<g>
        <${AxisY} scale=${sy} ticks=${yt} iw=${iw} format=${fy} zero=${zeroLine} />
        <${AxisX} scale=${sx} ticks=${xt} ih=${ih} format=${xFormat || ((v) => String(v))} />
        ${series.map((s, k) => {
          const color = s.color || SERIES_COLORS[k % SERIES_COLORS.length];
          return html`<g key=${s.key || k}>
            ${s.area ? html`<path d=${areaPath(x, s.values.map((v) => v ?? 0), sx, sy, Math.max(dy0, 0))} style=${{ fill: color, opacity: 0.1 }} />` : null}
            <path d=${linePath(x, s.values, sx, sy)} fill="none" style=${{ stroke: color }} stroke-width=${s.width || 2} stroke-linejoin="round" stroke-linecap="round" stroke-dasharray=${s.dashed ? "5 4" : undefined} opacity=${s.dim ? 0.45 : 1} />
          </g>`;
        })}
        ${(markers || []).map((m, i) => html`<circle key=${"m" + i} cx=${sx(m.x)} cy=${sy(m.y)} r=${m.r || 3.5} style=${{ fill: m.color || "var(--c1)" }} class="mark-ring" />`)}
        ${endLabels ? ends.map((e) => html`<g key=${"e" + e.k} transform=${`translate(${iw + 6},${e.y})`}>
          <rect x="0" y="-5" width="10" height="3" rx="1.5" style=${{ fill: e.s.color || SERIES_COLORS[e.k % SERIES_COLORS.length] }} />
          <text x="14" dy="0.34em" class="end-label">${e.s.endLabel || nf(e.v, 1)}</text>
        </g>`) : null}
        ${hover != null ? html`<g pointer-events="none">
          <line class="crosshair" x1=${sx(x[hover])} x2=${sx(x[hover])} y1="0" y2=${ih} />
          ${series.map((s, k) => (s.values[hover] == null ? null : html`<circle key=${k} cx=${sx(x[hover])} cy=${sy(s.values[hover])} r="4" class="mark-ring" style=${{ fill: s.color || SERIES_COLORS[k % SERIES_COLORS.length] }} />`))}
        </g>` : null}
        <rect class="hit" x="0" y="0" width=${iw} height=${ih} onMouseMove=${move} />
        ${xLabel ? html`<text class="axis-title" x=${iw / 2} y=${ih + 40} text-anchor="middle">${xLabel}</text>` : null}
        ${yLabel ? html`<text class="axis-title" transform=${`translate(${-42},${ih / 2}) rotate(-90)`} text-anchor="middle">${yLabel}</text>` : null}
      </g>`;
    }}
  </${Frame}>`;
}

/** Inline trend. Auto-scaled; the last value is marked. Blank (null) values leave gaps. */
export function Sparkline({ values, width = 88, height = 26, color = "var(--c1)", domain, baseline, area = false, label }) {
  const clean = (values || []).map((v) => (v == null || !Number.isFinite(v) ? null : v));
  const known = clean.filter((v) => v != null);
  if (known.length < 2) return html`<span class="muted">–</span>`;
  const [lo, hi] = domain || extent([...known, ...(baseline != null ? [baseline] : [])], 0.12);
  const pad = 3;
  const xs = clean.map((_, i) => i);
  const sx = scaleLinear([0, clean.length - 1], [pad, width - pad]);
  const sy = scaleLinear([lo, hi], [height - pad, pad]);
  const last = clean.length - 1 - [...clean].reverse().findIndex((v) => v != null);
  return html`<svg class="spark" width=${width} height=${height} viewBox=${`0 0 ${width} ${height}`} role="img" aria-label=${label || "Trend"}>
    ${baseline != null ? html`<line x1=${pad} x2=${width - pad} y1=${sy(baseline)} y2=${sy(baseline)} class="spark-base" />` : null}
    ${area ? html`<path d=${areaPath(xs, clean.map((v) => v ?? lo), sx, sy, baseline ?? lo)} style=${{ fill: color, opacity: 0.12 }} />` : null}
    <path d=${linePath(xs, clean, sx, sy)} fill="none" style=${{ stroke: color }} stroke-width="1.7" stroke-linejoin="round" stroke-linecap="round" />
    <circle cx=${sx(last)} cy=${sy(clean[last])} r="2.6" style=${{ fill: color }} />
  </svg>`;
}

/** Table position by matchweek. Everything is faint except the teams being followed (palette order = follow order). */
export function RankChart({ series, rounds, highlight = [], height = 380, nTeams = 20, zones, onPick, colorOf: colorFor, shortOf = (t) => t.slice(0, 3).toUpperCase() }) {
  const [hover, setHover] = useState(null);
  const teams = Object.keys(series);
  const weeks = Array.from({ length: rounds }, (_, i) => i + 1);
  const colorOf = (t) => { const i = highlight.indexOf(t); return i < 0 ? "var(--ink)" : colorFor ? colorFor(t) : SERIES_COLORS[i % SERIES_COLORS.length]; };
  return html`<${Frame} height=${height} label="Table position by matchweek" margin=${{ top: 10, right: 50, bottom: 30, left: 34 }} onLeave=${() => { setHover(null); tooltip.hide(); }}>
    ${({ iw, ih }) => {
      const sx = scaleLinear([1, Math.max(2, rounds)], [0, iw]);
      const sy = scaleLinear([1, nTeams], [8, ih - 8]);
      const move = (e) => {
        const rect = e.currentTarget.getBoundingClientRect();
        const mx = e.clientX - rect.left, my = e.clientY - rect.top;
        const w = Math.max(1, Math.min(rounds, Math.round(sx.invert(mx))));
        let best = null, bd = Infinity;
        for (const t of teams) { const d = Math.abs(sy(series[t][w - 1]) - my); if (d < bd) { bd = d; best = t; } }
        setHover(best);
        best && tooltip.move(e, html`<div><div class="tt-title">${best}</div><div class="tt-row"><span class="k">Matchweek ${w}</span><span class="v">${ordinal(series[best][w - 1])}</span></div></div>`);
      };
      const lit = new Set([...highlight, ...(hover ? [hover] : [])]);
      const order = [...teams].sort((a, b) => lit.has(a) - lit.has(b) || (a === hover) - (b === hover));
      return html`<g>
        ${zones?.ucl ? html`<rect x="0" y=${sy(1) - 8} width=${iw} height=${sy(zones.ucl) - sy(1) + 16} class="zone-band ucl" />` : null}
        ${zones?.rel ? html`<rect x="0" y=${sy(nTeams - zones.rel + 1) - 8} width=${iw} height=${sy(nTeams) - sy(nTeams - zones.rel + 1) + 16} class="zone-band rel" />` : null}
        ${[1, 4, 8, 12, 16, 20].filter((r) => r <= nTeams).map((r) => html`<g key=${r} transform=${`translate(0,${sy(r)})`}><line class="grid-line" x1="0" x2=${iw} /><text class="tick-label" x="-8" dy="0.32em" text-anchor="end">${r}</text></g>`)}
        <${AxisX} scale=${sx} ticks=${weeks.filter((w) => w === 1 || w % 5 === 0 || w === rounds)} ih=${ih} format=${(v) => String(v)} />
        ${order.map((t) => html`<path key=${t} d=${linePath(weeks, series[t], sx, sy)} fill="none" class=${"rank-line" + (lit.has(t) ? " on" : "")} style=${lit.has(t) ? { stroke: colorOf(t) } : null} />`)}
        ${[...lit].filter((t) => series[t]).map((t) => html`<g key=${"l" + t} transform=${`translate(${iw + 6},${sy(series[t][rounds - 1])})`}><text dy="0.34em" class="end-label strong">${shortOf(t)}</text></g>`)}
        <rect class="hit" x="0" y="0" width=${iw} height=${ih} onMouseMove=${move} onClick=${() => hover && onPick && onPick(hover)} style=${{ cursor: onPick ? "pointer" : "default" }} />
      </g>`;
    }}
  </${Frame}>`;
}

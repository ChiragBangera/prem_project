// Probability grids: scoreline matrix, finishing-position strip, and the calibration (reliability) chart.
import { html } from "../lib/html.js";
import { tooltip } from "../lib/tooltip.js";
import { nf, ordinal, pct } from "../lib/format.js";
import { seqColor, Frame, AxisX, AxisY, niceTicks, scaleLinear } from "./core.js";

/** rows = home goals, columns = away goals. Cells shade by probability; the likeliest scoreline is ringed. */
export function ScorelineMatrix({ matrix, homeName, awayName, size = 7 }) {
  const n = Math.min(size, matrix.length);
  let best = { p: -1, i: 0, j: 0 };
  let max = 0;
  for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) { const p = matrix[i][j]; max = Math.max(max, p); if (p > best.p) best = { p, i, j }; }
  return html`<div class="matrix" role="table" aria-label=${`Scoreline probabilities: ${homeName} goals down, ${awayName} goals across`}>
    <div class="matrix-corner"><span class="xsmall muted">${homeName} ↓ / ${awayName} →</span></div>
    ${Array.from({ length: n }, (_, j) => html`<div class="matrix-h" key=${"c" + j}>${j}</div>`)}
    ${Array.from({ length: n }, (_, i) => [
      html`<div class="matrix-h" key=${"r" + i}>${i}</div>`,
      ...Array.from({ length: n }, (_, j) => {
        const p = matrix[i][j];
        const t = max ? p / max : 0;
        return html`<div class=${"matrix-cell" + (i === best.i && j === best.j ? " best" : "")} key=${i + "-" + j} style=${{ background: t < 0.03 ? "var(--surface-2)" : seqColor(t * 0.62) }}
          onMouseMove=${(e) => tooltip.move(e, html`<div><div class="tt-title">${homeName} ${i}–${j} ${awayName}</div><div class="tt-row"><span class="k">Probability</span><span class="v">${pct(p, 1)}</span></div></div>`)} onMouseLeave=${tooltip.hide}>${p >= 0.012 ? Math.round(p * 100) : ""}</div>`;
      }),
    ])}
  </div>`;
}

/** Twenty cells, one per finishing position. Darker = likelier. */
export function PositionStrip({ dist, team }) {
  const max = Math.max(...dist, 0.0001);
  return html`<div class="posstrip" role="img" aria-label=${`Finishing position probabilities for ${team}`}>
    ${dist.map((p, i) => html`<i key=${i} style=${{ background: p < 0.004 ? "transparent" : seqColor((p / max) * 0.85) }}
      onMouseMove=${(e) => tooltip.move(e, html`<div><div class="tt-title">${team}</div><div class="tt-row"><span class="k">Finish ${ordinal(i + 1)}</span><span class="v">${pct(p, p < 0.1 ? 1 : 0)}</span></div></div>`)} onMouseLeave=${tooltip.hide}></i>`)}
  </div>`;
}

/** Predicted probability against how often it happened. Points on the diagonal are honest forecasts. */
export function Reliability({ bins, height = 320 }) {
  const maxN = Math.max(...bins.map((b) => b.n), 1);
  return html`<${Frame} height=${height} label="Forecast reliability: predicted probability against observed frequency" margin=${{ top: 12, right: 16, bottom: 46, left: 52 }}>
    ${({ iw, ih }) => {
      const sx = scaleLinear([0, 1], [0, iw]), sy = scaleLinear([0, 1], [ih, 0]);
      const t = niceTicks(0, 1, 5);
      const ordered = [...bins].sort((a, b) => a.predicted - b.predicted);
      return html`<g>
        <${AxisY} scale=${sy} ticks=${t} iw=${iw} format=${(v) => pct(v)} />
        <${AxisX} scale=${sx} ticks=${t} ih=${ih} format=${(v) => pct(v)} grid=${true} />
        <line class="ref-line" x1=${sx(0)} y1=${sy(0)} x2=${sx(1)} y2=${sy(1)} />
        <text class="corner-labels" x=${sx(0.72)} y=${sy(0.66)} transform=${`rotate(-45 ${sx(0.72)} ${sy(0.66)})`} style=${{ fontSize: "11px", fill: "var(--ink-3)" }}>perfectly calibrated</text>
        <path d=${ordered.map((b, i) => `${i ? "L" : "M"}${sx(b.predicted).toFixed(1)},${sy(b.observed).toFixed(1)}`).join("")} fill="none" style=${{ stroke: "var(--c1)" }} stroke-width="1.6" opacity="0.6" />
        ${ordered.map((b, i) => html`<circle key=${i} cx=${sx(b.predicted)} cy=${sy(b.observed)} r=${4 + 8 * Math.sqrt(b.n / maxN)} class="mark-ring" style=${{ fill: "var(--c1)", opacity: 0.85 }}
          onMouseMove=${(e) => tooltip.move(e, html`<div><div class="tt-title">${b.n} forecasts near ${pct(b.predicted)}</div><div class="tt-row"><span class="k">Predicted</span><span class="v">${pct(b.predicted, 1)}</span></div><div class="tt-row"><span class="k">Happened</span><span class="v">${pct(b.observed, 1)}</span></div></div>`)} onMouseLeave=${tooltip.hide} />`)}
        <text class="axis-title" x=${iw / 2} y=${ih + 40} text-anchor="middle">Probability the model gave</text>
        <text class="axis-title" transform=${`translate(${-40},${ih / 2}) rotate(-90)`} text-anchor="middle">How often it happened</text>
      </g>`;
    }}
  </${Frame}>`;
}

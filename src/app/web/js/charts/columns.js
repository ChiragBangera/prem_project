// Grouped columns along an ordered axis: two values per category (created vs allowed), a league-average tick on each.
import { html } from "../lib/html.js";
import { tooltip } from "../lib/tooltip.js";
import { nf, signed } from "../lib/format.js";
import { AxisY, Frame, niceTicks, scaleBand, scaleLinear } from "./core.js";

/** Break a label over at most two lines so ordered categories stay readable on a phone. */
function wrap(text, width = 9) {
  const words = String(text).split(" ");
  const lines = [];
  for (const w of words) {
    const last = lines[lines.length - 1];
    if (last && (last + " " + w).length <= width) lines[lines.length - 1] = last + " " + w;
    else lines.push(w);
  }
  return lines.slice(0, 2);
}

/**
 * rows: [{ key, label, a, b, aAvg?, bAvg?, dim?, tip }]  (a = created, b = allowed)
 * The number under each label is the net (a - b); blue above zero, orange below, same rule as the rest of the app.
 */
export function ColumnPairs({ rows, height = 300, label, digits = 2 }) {
  const max = Math.max(1e-9, ...rows.flatMap((r) => [r.a, r.b, r.aAvg || 0, r.bAvg || 0]));
  const keys = rows.map((r) => r.key);
  return html`<${Frame} height=${height} label=${label} margin=${{ top: 22, right: 10, bottom: 66, left: 44 }} onLeave=${tooltip.hide}>
    ${({ iw, ih }) => {
      const ticks = niceTicks(0, max * 1.1, 4);
      const sy = scaleLinear([0, ticks[ticks.length - 1]], [ih, 0]);
      const sx = scaleBand(keys, [0, iw], 0.26);
      const bw = Math.max(6, sx.bandwidth / 2 - 1.5);
      return html`<g>
        <${AxisY} scale=${sy} ticks=${ticks} iw=${iw} format=${(v) => nf(v, max < 1 ? 2 : 1)} zero />
        ${rows.map((r) => {
          const x0 = sx(r.key) + (sx.bandwidth - 2 * bw - 3) / 2;
          const net = r.a - r.b;
          const lines = wrap(r.label, Math.max(6, Math.floor(sx.step / 8)));
          const bar = (v, x, color) => html`<rect x=${x} y=${sy(v)} width=${bw} height=${Math.max(0, ih - sy(v))} rx="3" style=${{ fill: color }} />`;
          const avg = (v, x) => (v == null ? null : html`<line class="avg-line" x1=${x - 2} x2=${x + bw + 2} y1=${sy(v)} y2=${sy(v)} />`);
          return html`<g key=${r.key} opacity=${r.dim ? 0.45 : 1}>
            <rect class="hit" x=${sx.center(r.key) - sx.step / 2} y="0" width=${sx.step} height=${ih + 60} fill="transparent"
              onMouseMove=${(e) => tooltip.move(e, r.tip)} onMouseLeave=${tooltip.hide} />
            ${bar(r.a, x0, "var(--c1)")}${bar(r.b, x0 + bw + 3, "var(--c2)")}
            ${avg(r.aAvg, x0)}${avg(r.bAvg, x0 + bw + 3)}
            <text class="col-val" x=${x0 + bw / 2} y=${sy(r.a) - 5} text-anchor="middle">${nf(r.a, digits)}</text>
            <text class="col-val" x=${x0 + bw + 3 + bw / 2} y=${sy(r.b) - 5} text-anchor="middle">${nf(r.b, digits)}</text>
            ${lines.map((t, i) => html`<text key=${i} class="tick-label" x=${sx.center(r.key)} y=${ih + 16 + i * 12} text-anchor="middle">${t}</text>`)}
            <text class="col-net" x=${sx.center(r.key)} y=${ih + 20 + lines.length * 12 + 6} text-anchor="middle" style=${{ fill: net >= 0 ? "var(--c1)" : "var(--c2)" }}>${signed(net, digits)}</text>
          </g>`;
        })}
      </g>`;
    }}
  </${Frame}>`;
}

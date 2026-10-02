// Probability distribution of goals given a set of chances, with the actual tally marked.
import { html } from "../lib/html.js";
import { tooltip } from "../lib/tooltip.js";
import { pct } from "../lib/format.js";
import { Frame, AxisY, niceTicks, scaleBand, scaleLinear } from "./core.js";

export function GoalsDistribution({ pmf, actual, expected, height = 230, unit = "goals" }) {
  const mean = pmf.reduce((s, p, k) => s + p * k, 0);
  const sd = Math.sqrt(pmf.reduce((s, p, k) => s + p * (k - mean) ** 2, 0));
  const lo = Math.max(0, Math.floor(Math.min(mean - 3.4 * sd, actual - 1)));
  const hi = Math.min(pmf.length - 1, Math.ceil(Math.max(mean + 3.4 * sd, actual + 1)));
  const ks = Array.from({ length: hi - lo + 1 }, (_, i) => lo + i);
  const top = Math.max(...ks.map((k) => pmf[k] || 0));
  return html`<${Frame} height=${height} label=${`Chance of each possible goal tally; actual ${actual}`} margin=${{ top: 22, right: 12, bottom: 44, left: 44 }}>
    ${({ iw, ih }) => {
      const sx = scaleBand(ks, [0, iw], 0.18);
      const sy = scaleLinear([0, top * 1.12], [ih, 0]);
      const yt = niceTicks(0, top * 1.12, 4);
      const step = Math.max(1, Math.ceil(ks.length / 12));
      return html`<g>
        <${AxisY} scale=${sy} ticks=${yt} iw=${iw} format=${(v) => pct(v)} />
        <line class="axis-line" x1="0" x2=${iw} y1=${ih} y2=${ih} />
        ${ks.map((k) => {
          const on = k === actual;
          const tail = (k >= actual && actual >= mean) || (k <= actual && actual < mean);
          return html`<g key=${k} onMouseMove=${(e) => tooltip.move(e, html`<div><div class="tt-title">${k} ${unit}</div><div class="tt-row"><span class="k">Chance of exactly ${k}</span><span class="v">${pct(pmf[k] || 0, 1)}</span></div></div>`)} onMouseLeave=${tooltip.hide}>
            <rect x=${sx(k)} y=${sy(pmf[k] || 0)} width=${sx.bandwidth} height=${Math.max(0, ih - sy(pmf[k] || 0))} rx="2"
              style=${{ fill: on ? "var(--ink)" : tail ? "var(--c1)" : "var(--surface-3)", opacity: on ? 1 : tail ? 0.55 : 1 }} />
            ${(k - lo) % step === 0 ? html`<text class="tick-label" x=${sx.center(k)} y=${ih + 16} text-anchor="middle">${k}</text>` : null}
          </g>`;
        })}
        <line class="ref-line" x1=${sx(Math.round(mean)) + sx.bandwidth / 2 + (mean - Math.round(mean)) * sx.step} x2=${sx(Math.round(mean)) + sx.bandwidth / 2 + (mean - Math.round(mean)) * sx.step} y1="-6" y2=${ih} />
        <text class="end-label" x=${sx(Math.round(mean)) + sx.bandwidth / 2 + (mean - Math.round(mean)) * sx.step} y="-9" text-anchor=${mean > (lo + hi) / 2 ? "end" : "start"} dx=${mean > (lo + hi) / 2 ? -4 : 4}>expected ${expected != null ? expected.toFixed(1) : mean.toFixed(1)}</text>
        <text class="axis-title" x=${iw / 2} y=${ih + 38} text-anchor="middle">Possible ${unit} from these chances</text>
      </g>`;
    }}
  </${Frame}>`;
}

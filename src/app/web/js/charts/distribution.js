// A small histogram: where everyone in the list sits on one metric, with the median marked and the part the current ranking keeps picked out.
import { html } from "../lib/html.js";
import { tooltip } from "../lib/tooltip.js";
import { Frame, scaleLinear } from "./core.js";

/**
 * hist: from lib/filters.js histogram(). format(v): how a value reads. keep: { from, to } value range to highlight (either may be null).
 * label: for the screen reader.
 */
export function Distribution({ hist, format, keep, height = 92, label = "Distribution", unit = "players" }) {
  if (!hist) return null;
  const top = Math.max(...hist.counts, 1);
  return html`<${Frame} height=${height} label=${label} margin=${{ top: 6, right: 6, bottom: 22, left: 6 }} onLeave=${tooltip.hide}>
    ${({ iw, ih }) => {
      const sx = scaleLinear([hist.lo, hist.hi], [0, iw]);
      const sy = scaleLinear([0, top], [ih, 0]);
      const bw = Math.max(2, iw / hist.counts.length - 1.5);
      const kept = (a, b) => keep && (keep.from == null || b > keep.from) && (keep.to == null || a < keep.to);
      return html`<g>
        <line class="axis-line" x1="0" x2=${iw} y1=${ih} y2=${ih} />
        ${hist.counts.map((c, i) => {
          const a = hist.lo + i * hist.width, b = a + hist.width;
          const on = kept(a, b);
          return html`<rect key=${i} x=${sx(a) + 0.75} y=${sy(c)} width=${bw} height=${Math.max(c ? 1.5 : 0, ih - sy(c))} rx="1.5" style=${{ fill: on ? "var(--accent)" : "var(--surface-3)", stroke: on ? "none" : "var(--line-2)", strokeWidth: 0.6 }}
            onMouseMove=${(e) => tooltip.move(e, html`<div><div class="tt-title">${format(a)} to ${format(b)}</div><div class="tt-row"><span class="k">${unit}</span><span class="v">${c}</span></div></div>`)} onMouseLeave=${tooltip.hide} />`;
        })}
        <line class="ref-line" x1=${sx(hist.median)} x2=${sx(hist.median)} y1="0" y2=${ih} />
        <text class="tick-label" x=${Math.min(iw - 2, Math.max(2, sx(hist.median)))} y=${ih + 15} text-anchor="middle">median ${format(hist.median)}</text>
        <text class="tick-label" x="0" y=${ih + 15} text-anchor="start">${format(hist.lo)}</text>
        <text class="tick-label" x=${iw} y=${ih + 15} text-anchor="end">${format(hist.hi)}</text>
      </g>`;
    }}
  </${Frame}>`;
}

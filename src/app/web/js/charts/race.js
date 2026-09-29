// Cumulative expected goals through a match: who was creating the better chances, and when the goals landed.
import { html, useState } from "../lib/html.js";
import { tooltip } from "../lib/tooltip.js";
import { nf } from "../lib/format.js";
import { Frame, AxisX, AxisY, niceTicks, scaleLinear, stepPath } from "./core.js";

const valueAt = (points, minute) => {
  let v = 0;
  for (const p of points) { if (p.minute <= minute) v = p.xg; else break; }
  return v;
};

export function XgRace({ home, away, homeName, awayName, homeShort, awayShort, height = 300 }) {
  const [hover, setHover] = useState(null);
  const end = Math.max(90, ...home.map((p) => p.minute), ...away.map((p) => p.minute));
  const top = Math.max(0.5, ...home.map((p) => p.xg), ...away.map((p) => p.xg));
  const goals = [...home.filter((p) => p.goal).map((p) => ({ ...p, side: "h" })), ...away.filter((p) => p.goal).map((p) => ({ ...p, side: "a" }))];
  const colors = { h: "var(--c1)", a: "var(--c2)" };
  return html`<${Frame} height=${height} label=${`Cumulative xG: ${homeName} ${nf(home[home.length - 1]?.xg, 2)}, ${awayName} ${nf(away[away.length - 1]?.xg, 2)}`} margin=${{ top: 16, right: 60, bottom: 34, left: 40 }} onLeave=${() => { setHover(null); tooltip.hide(); }}>
    ${({ iw, ih }) => {
      const sx = scaleLinear([0, end], [0, iw]);
      const sy = scaleLinear([0, top * 1.12], [ih, 0]);
      const yt = niceTicks(0, top * 1.1, 4);
      const path = (pts) => {
        const xs = [...pts.map((p) => p.minute), end], ys = [...pts.map((p) => p.xg), pts[pts.length - 1]?.xg ?? 0];
        return stepPath(xs, ys, sx, sy);
      };
      const at = hover;
      return html`<g>
        <${AxisY} scale=${sy} ticks=${yt} iw=${iw} format=${(v) => nf(v, 1)} />
        <${AxisX} scale=${sx} ticks=${[0, 15, 30, 45, 60, 75, 90].filter((m) => m <= end)} ih=${ih} format=${(v) => v + "′"} />
        <line class="ref-line" x1=${sx(45)} x2=${sx(45)} y1="0" y2=${ih} />
        <path d=${path(home)} fill="none" style=${{ stroke: colors.h }} stroke-width="2.4" stroke-linejoin="round" />
        <path d=${path(away)} fill="none" style=${{ stroke: colors.a }} stroke-width="2.4" stroke-linejoin="round" />
        ${goals.map((g, i) => html`<g key=${i} transform=${`translate(${sx(g.minute)},${sy(g.xg)})`}
            onMouseMove=${(e) => tooltip.move(e, html`<div><div class="tt-title">Goal ${g.minute}′: ${g.goal.player}</div><div class="tt-row"><span class="k">${g.side === "h" ? homeName : awayName}</span><span class="v">${nf(g.goal.xg, 2)} xG</span></div></div>`)} onMouseLeave=${tooltip.hide}>
          <circle r="7" style=${{ fill: colors[g.side], stroke: "var(--ink)", strokeWidth: 2 }} />
        </g>`)}
        ${[[home, homeShort, "h"], [away, awayShort, "a"]].map(([pts, name, side]) => html`<g key=${side} transform=${`translate(${iw + 8},${sy(pts[pts.length - 1]?.xg ?? 0)})`}><text dy="0.34em" class="end-label strong">${name} ${nf(pts[pts.length - 1]?.xg, 2)}</text></g>`)}
        ${at != null ? html`<g pointer-events="none"><line class="crosshair" x1=${sx(at)} x2=${sx(at)} y1="0" y2=${ih} />
          <circle cx=${sx(at)} cy=${sy(valueAt(home, at))} r="4" class="mark-ring" style=${{ fill: colors.h }} /><circle cx=${sx(at)} cy=${sy(valueAt(away, at))} r="4" class="mark-ring" style=${{ fill: colors.a }} /></g>` : null}
        <rect class="hit" x="0" y="0" width=${iw} height=${ih} onMouseMove=${(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const m = Math.max(0, Math.min(end, Math.round(sx.invert(e.clientX - rect.left))));
          setHover(m);
          tooltip.move(e, html`<div><div class="tt-title">${m}′</div>
            <div class="tt-row"><span class="k"><i class="key" style=${{ background: colors.h }}></i>${homeName}</span><span class="v">${nf(valueAt(home, m), 2)}</span></div>
            <div class="tt-row"><span class="k"><i class="key" style=${{ background: colors.a }}></i>${awayName}</span><span class="v">${nf(valueAt(away, m), 2)}</span></div></div>`);
        }} />
      </g>`;
    }}
  </${Frame}>`;
}

// The percentile "pizza": a player's standing among his role peers on sixteen measures at once, one slice each. A slice reaching the rim is
// the best of his role; the dashed ring is the typical player. Slices are grouped (attacking, creating, on the ball, defending) and each
// group keeps one colour, so the shape of a player (all attack, no defending, say) reads before any number does.
import { html, useState } from "../lib/html.js";
import { tooltip } from "../lib/tooltip.js";

export const PIZZA_GROUPS = [
  { id: "attack", label: "Attacking", color: "var(--c1)", keys: ["npxg90", "shots90", "npg90", "touchbox90"] },
  { id: "create", label: "Creating", color: "var(--c2)", keys: ["xa90", "kp90", "bigcreated90", "passbox90"] },
  { id: "ball", label: "On the ball", color: "var(--c3)", keys: ["prog_passes90", "carryprog90", "takeonswon90", "pass_acc"] },
  { id: "defend", label: "Defending", color: "var(--c4)", keys: ["tklint90", "recoveries90", "aerialwon90", "def_duel_win"] },
];

/** The slices that can be drawn for a player: the template's measures he is ranked on, in template order. `blocks` is the profile's metric blocks. */
export function pizzaSlices(blocks) {
  const byKey = new Map();
  for (const b of blocks || []) for (const it of b.items || []) byKey.set(it.key, it);
  const out = [];
  for (const g of PIZZA_GROUPS) for (const key of g.keys) {
    const it = byKey.get(key);
    if (it && it.pct != null) out.push({ ...it, group: g.id, color: g.color, groupLabel: g.label });
  }
  return out;
}

const polar = (r, a) => [r * Math.sin(a), -r * Math.cos(a)];
function wedge(r0, r1, a0, a1) {
  const [x0, y0] = polar(r1, a0), [x1, y1] = polar(r1, a1), [x2, y2] = polar(r0, a1), [x3, y3] = polar(r0, a0);
  const large = a1 - a0 > Math.PI ? 1 : 0;
  return `M${x0.toFixed(2)} ${y0.toFixed(2)}A${r1} ${r1} 0 ${large} 1 ${x1.toFixed(2)} ${y1.toFixed(2)}L${x2.toFixed(2)} ${y2.toFixed(2)}A${r0} ${r0} 0 ${large} 0 ${x3.toFixed(2)} ${y3.toFixed(2)}Z`;
}

export function Pizza({ slices, valueOf = (s) => String(s.value), peers = "role peers", poolN }) {
  const [on, setOn] = useState(null);
  const n = slices.length;
  const R = 118, R0 = 20, step = (2 * Math.PI) / n, pad = 0.022;
  const reach = (pct) => R0 + ((R - R0) * Math.max(2, pct)) / 100;
  const groups = PIZZA_GROUPS.filter((g) => slices.some((s) => s.group === g.id));
  return html`<div class="pizza">
    <svg viewBox="-200 -160 400 320" role="img" aria-label=${`Percentile profile among ${peers}: ${slices.map((s) => `${s.label} ${Math.round(s.pct)}`).join(", ")}`}>
      ${[25, 50, 75, 100].map((p) => html`<circle key=${p} class=${"pz-ring" + (p === 50 ? " mid" : "")} r=${reach(p)} />`)}
      ${slices.map((s, i) => {
        const a0 = i * step + pad, a1 = (i + 1) * step - pad, mid = (a0 + a1) / 2;
        const r = reach(s.pct);
        // a slice too short to hold its number carries it just past its end, in ink, instead of squeezed into the hub
        const short = r - R0 < 24;
        const [lx, ly] = polar(R + 12, mid), [vx, vy] = polar(short ? r + 10 : r - 11, mid);
        const side = Math.abs(Math.sin(mid)) < 0.1 ? "middle" : Math.sin(mid) > 0 ? "start" : "end";
        return html`<g key=${s.key} class=${"pz-slice" + (on === s.key ? " on" : on ? " dim" : "")}
          onMouseMove=${(e) => { setOn(s.key); tooltip.move(e, html`<div><div class="tt-title">${s.label}</div><div class="tt-sub">${s.groupLabel} · among ${peers}</div>
            <div class="tt-row"><span class="k">Value</span><span class="v">${valueOf(s)}</span></div>
            <div class="tt-row"><span class="k">Better than</span><span class="v">${Math.round(s.pct)} of every 100</span></div>
            ${s.rank ? html`<div class="tt-row"><span class="k">Rank</span><span class="v">${s.rank}${(s.pool_n || poolN) ? ` of ${s.pool_n || poolN}` : ""}</span></div>` : null}</div>`); }}
          onMouseLeave=${() => { setOn(null); tooltip.hide(); }}>
          <path class="pz-track" d=${wedge(R0, R, a0, a1)} />
          <path d=${wedge(R0, r, a0, a1)} style=${{ fill: s.color }} />
          <text class=${"pz-val" + (short ? " out" : "")} x=${vx} y=${vy} dy="0.35em" text-anchor="middle">${Math.round(s.pct)}</text>
          <text class="pz-label" x=${lx} y=${ly} dy=${Math.cos(mid) > 0.5 ? "0" : Math.cos(mid) < -0.5 ? "0.7em" : "0.35em"} text-anchor=${side}>${s.short || s.label}</text>
        </g>`;
      })}
    </svg>
    <div class="legend pz-legend">${groups.map((g) => html`<span class="item" key=${g.id}><span class="swatch box" style=${{ background: g.color }}></span>${g.label}</span>`)}<span class="item"><span class="pz-mid-key"></span>Typical ${peers.replace(/s$/, "")}</span></div>
  </div>`;
}

/**
 * Several players on one radar: each axis a measure, each player a shape made of his percentiles among his own role. Read the shapes, not the
 * area: where one reaches further he stands higher among his peers on that measure. `axes`: [{ key, label, pct: [per player] }].
 */
export function Radar({ axes, players, colors, valueOf }) {
  const [on, setOn] = useState(null);
  const n = axes.length, R = 112, step = (2 * Math.PI) / n;
  const point = (pct, i) => polar((R * Math.max(0, pct ?? 0)) / 100, i * step);
  const shape = (pi) => axes.map((a, i) => point(a.pct[pi], i).map((v) => v.toFixed(1)).join(" ")).join("L");
  return html`<div class="pizza radar">
    <svg viewBox="-205 -150 410 300" role="img" aria-label=${`Percentile shapes of ${players.map((p) => p.name).join(", ")} on ${n} measures`}>
      ${[25, 50, 75, 100].map((p) => html`<path key=${p} class=${"pz-ring" + (p === 50 ? " mid" : "")} d=${"M" + axes.map((_, i) => polar((R * p) / 100, i * step).map((v) => v.toFixed(1)).join(" ")).join("L") + "Z"} />`)}
      ${axes.map((a, i) => {
        const [x, y] = polar(R, i * step), [lx, ly] = polar(R + 12, i * step), ang = i * step;
        const side = Math.abs(Math.sin(ang)) < 0.1 ? "middle" : Math.sin(ang) > 0 ? "start" : "end";
        return html`<g key=${a.key} class=${"rd-axis" + (on === a.key ? " on" : "")} onMouseMove=${(e) => { setOn(a.key); tooltip.move(e, html`<div><div class="tt-title">${a.label}</div>
            ${players.map((p, pi) => html`<div class="tt-row" key=${p.id}><span class="k"><i class="key" style=${{ background: colors[pi] }}></i>${p.name}</span><span class="v">${valueOf ? valueOf(a, pi) : ""}${a.pct[pi] == null ? "" : ` · ${Math.round(a.pct[pi])}`}</span></div>`)}
            <div class="tt-sub">Value, then how many of every 100 role peers he beats</div></div>`); }} onMouseLeave=${() => { setOn(null); tooltip.hide(); }}>
          <line class="pz-ring" x1="0" y1="0" x2=${x} y2=${y} />
          <line class="rd-hit" x1="0" y1="0" x2=${lx} y2=${ly} />
          <text class="pz-label" x=${lx} y=${ly} dy=${Math.cos(ang) > 0.5 ? "0" : Math.cos(ang) < -0.5 ? "0.7em" : "0.35em"} text-anchor=${side}>${a.short || a.label}</text>
        </g>`;
      })}
      ${players.map((p, pi) => html`<path key=${p.id} class="rd-shape" d=${"M" + shape(pi) + "Z"} style=${{ fill: colors[pi], stroke: colors[pi] }} />`)}
      ${players.map((p, pi) => axes.map((a, i) => { const [x, y] = point(a.pct[pi], i); return a.pct[pi] == null ? null : html`<circle key=${p.id + a.key} class="rd-dot" cx=${x} cy=${y} r=${on === a.key ? 4.5 : 3} style=${{ fill: colors[pi] }} />`; }))}
    </svg>
    <div class="legend pz-legend">${players.map((p, pi) => html`<span class="item" key=${p.id}><span class="swatch dot" style=${{ background: colors[pi] }}></span>${p.name}</span>`)}<span class="item"><span class="pz-mid-key"></span>Typical player of his role</span></div>
  </div>`;
}

// Pitch maps drawn from stored event data: where a team or player touched the ball, passed, defended, carried it.
//
// Every map is one horizontal pitch (105 x 68 metres) with the team attacking from left to right and its left wing at the top, so any two maps
// can be laid side by side and read the same way. The API sends positions as tenths of the pitch (0-1000 along and across); this module only draws.
import { html, useMemo } from "../lib/html.js";
import { tooltip } from "../lib/tooltip.js";
import { nf } from "../lib/format.js";
import { seqColor } from "./core.js";

export const L = 105, W = 68;
export const NX = 24, NY = 16;
const px = (x) => (x / 1000) * L;
const py = (y) => (y / 1000) * W;

let uid = 0;
const nextId = () => `pm${++uid}`;

// pass flags (bit set), as the API sends them
export const PF = { PROG: 1, KEY: 2, BOX: 4, F3: 8, LONG: 16, CROSS: 32, THROUGH: 64, ASSIST: 128, RESTART: 256 };
// defensive point kinds
export const DK = { TACKLE: 1, INTERCEPT: 2, CLEAR: 3, BLOCK_PASS: 4, BLOCK_SHOT: 5, RECOVER: 6, BEATEN: 7, AERIAL: 8 };
export const DEF_KINDS = [
  { id: DK.TACKLE, label: "Tackles", color: "var(--c1)", shape: "circle" },
  { id: DK.INTERCEPT, label: "Interceptions", color: "var(--c3)", shape: "diamond" },
  { id: DK.CLEAR, label: "Clearances", color: "var(--c4)", shape: "square" },
  { id: DK.BLOCK_PASS, label: "Blocked passes", color: "var(--c7)", shape: "tri" },
  { id: DK.BLOCK_SHOT, label: "Blocked shots", color: "var(--c8)", shape: "tri" },
  { id: DK.RECOVER, label: "Recoveries", color: "var(--c5)", shape: "plus" },
  { id: DK.BEATEN, label: "Challenges lost", color: "var(--ink-3)", shape: "cross" },
  { id: DK.AERIAL, label: "Aerial duels (defending)", color: "var(--c2)", shape: "circle" },
];
export const GK_KINDS = [
  { id: 1, label: "Saves", color: "var(--c1)", shape: "circle" }, { id: 2, label: "Claims", color: "var(--c3)", shape: "diamond" },
  { id: 3, label: "Punches", color: "var(--c4)", shape: "square" }, { id: 4, label: "Sweeper actions", color: "var(--c5)", shape: "tri" },
  { id: 5, label: "Pickups", color: "var(--c7)", shape: "plus" }, { id: 6, label: "Smothers", color: "var(--c2)", shape: "circle" },
];

/** The pitch itself: turf, lines, boxes, arcs, spots and the two goals. Children are drawn on top, in metre coordinates. */
export function Pitch({ children, label, maxWidth = 860, caption = true }) {
  return html`<figure class="pitchmap" style=${{ maxWidth: maxWidth + "px" }}>
    <svg viewBox="-3 -3 111 ${caption ? 78 : 74}" role="img" aria-label=${label}>
      <g class="pitch">
        <rect class="turf" x="0" y="0" width=${L} height=${W} />
        ${children}
        <rect class="mark" x="0" y="0" width=${L} height=${W} />
        <line class="mark" x1=${L / 2} y1="0" x2=${L / 2} y2=${W} />
        <circle class="mark" cx=${L / 2} cy=${W / 2} r="9.15" /><circle class="spot" cx=${L / 2} cy=${W / 2} r="0.45" />
        <rect class="mark" x="0" y="13.84" width="16.5" height="40.32" /><rect class="mark" x="0" y="24.84" width="5.5" height="18.32" />
        <rect class="mark" x=${L - 16.5} y="13.84" width="16.5" height="40.32" /><rect class="mark" x=${L - 5.5} y="24.84" width="5.5" height="18.32" />
        <circle class="spot" cx="11" cy=${W / 2} r="0.45" /><circle class="spot" cx=${L - 11} cy=${W / 2} r="0.45" />
        <path class="mark" d=${`M16.5 ${W / 2 - 7.31} A9.15 9.15 0 0 1 16.5 ${W / 2 + 7.31}`} /><path class="mark" d=${`M${L - 16.5} ${W / 2 - 7.31} A9.15 9.15 0 0 0 ${L - 16.5} ${W / 2 + 7.31}`} />
        <rect class="mark goal" x="-1.8" y="30.34" width="1.8" height="7.32" /><rect class="mark goal" x=${L} y="30.34" width="1.8" height="7.32" />
      </g>
      ${caption ? html`<g class="pm-dir" pointer-events="none"><line x1="40" y1="73" x2="65" y2="73" /><path d="M63 71.6 65 73 63 74.4" fill="none" /></g>` : null}
    </svg>
    ${caption ? html`<figcaption class="xsmall muted">Attacking left to right · left wing at the top</figcaption>` : null}
  </figure>`;
}

// ------------------------------------------------------------------ heat

/** A grid of counts (NX by NY, row-major) as a smooth heat layer. */
export function HeatLayer({ grid, color, gamma = 0.7, blur = 1.5, unit = "events", total }) {
  const id = useMemo(nextId, []);
  const max = Math.max(1, ...grid);
  const sum = total ?? grid.reduce((a, b) => a + b, 0);
  const cw = L / NX, ch = W / NY;
  return html`<g>
    <defs>
      <filter id=${id + "f"} x="-6%" y="-6%" width="112%" height="112%"><feGaussianBlur stdDeviation=${blur} /></filter>
      <clipPath id=${id + "c"}><rect x="0" y="0" width=${L} height=${W} /></clipPath>
    </defs>
    <g clip-path=${`url(#${id}c)`}><g filter=${`url(#${id}f)`}>
      ${grid.map((c, i) => {
        if (!c) return null;
        const t = Math.pow(c / max, gamma);
        // the theme's sequential blue by default (darker = more in light mode, brighter = more in dark mode); a single hue when one is asked for
        const style = color ? { fill: color, fillOpacity: Math.min(0.95, 0.1 + 0.85 * t) } : { fill: seqColor(0.08 + 0.92 * t), fillOpacity: Math.min(0.95, 0.18 + 0.78 * t) };
        return html`<rect key=${i} x=${(i % NX) * cw} y=${Math.floor(i / NX) * ch} width=${cw + 0.2} height=${ch + 0.2} style=${style} />`;
      })}
    </g></g>
    <g>${grid.map((c, i) => html`<rect key=${"h" + i} class="hit" x=${(i % NX) * cw} y=${Math.floor(i / NX) * ch} width=${cw} height=${ch}
      onMouseMove=${(e) => tooltip.move(e, html`<div><div class="tt-title">${c} ${unit}</div><div class="tt-sub">${sum ? nf((100 * c) / sum, 1) : "0"}% of all</div></div>`)} onMouseLeave=${tooltip.hide} />`)}</g>
  </g>`;
}

// ------------------------------------------------------------------ lines (passes, carries)

const arrowId = (id, key) => `${id}-${key}`;

/** How strongly to draw each of n lines: a few are drawn at full strength; thousands are drawn fainter and thinner, so where they overlap the picture reads as density, not a solid wall. */
const fadeFor = (n) => Math.min(1, Math.max(0.5, Math.sqrt(160 / Math.max(n, 1))));
const thick = (width, fade) => width * (0.85 + 0.35 * fade);       // stroke width by how many lines share the pitch
const headSize = (fade) => 1.8 * (0.7 + 0.3 * fade);

/**
 * Passes as arrows. lines: [[x0, y0, x1, y1, ok, flags, minute, match]]. Completed ones in `color`; incomplete ones dashed in `failColor`
 * and ending in a cross, where the ball was lost, drawn clearly enough to read (they are what the map is for: who loses the ball, and where).
 * `emphasis` (optional): flags whose lines are drawn heavier (key passes, say) within a lighter wash of the others.
 */
export function PassLayer({ lines, color = "var(--c1)", failColor = "var(--neg)", show = "both", emphasis = 0, width = 0.5 }) {
  const id = useMemo(nextId, []);
  const ok = show === "bad" ? [] : lines.filter((l) => l[4]);               // show: "ok" completed passes, "bad" passes that were not completed, "both"
  const bad = show === "ok" ? [] : lines.filter((l) => !l[4]);
  const strong = (l) => emphasis && l[5] & emphasis;
  const fade = fadeFor(ok.length + bad.length);
  const head = headSize(fade);
  const arrow = (key, fill) => html`<marker id=${arrowId(id, key)} viewBox="0 0 6 6" refX="5" refY="3" markerWidth=${head} markerHeight=${head} markerUnits="userSpaceOnUse" orient="auto-start-reverse"><path d="M0 0 6 3 0 6z" style=${{ fill }} /></marker>`;
  return html`<g>
    <defs>${arrow("ok", color)}${arrow("bad", failColor)}</defs>
    ${bad.map((l, i) => html`<line class="pass-lost" key=${"b" + i} x1=${px(l[0])} y1=${py(l[1])} x2=${px(l[2])} y2=${py(l[3])} style=${{ stroke: failColor, strokeOpacity: 0.78 + 0.2 * fade, strokeWidth: thick(width, fade) * 1.1, strokeDasharray: "1.1 0.7" }} />`)}
    ${bad.map((l, i) => { const x = px(l[2]), y = py(l[3]), r = 0.9 + 0.4 * fade; return html`<path class="pass-lost-end" key=${"x" + i} d=${`M${x - r} ${y - r}L${x + r} ${y + r}M${x - r} ${y + r}L${x + r} ${y - r}`} style=${{ stroke: failColor, strokeOpacity: 0.85 + 0.15 * fade, strokeWidth: thick(width, fade) * 1.5, fill: "none", strokeLinecap: "round" }} />`; })}
    ${ok.map((l, i) => html`<line key=${"o" + i} x1=${px(l[0])} y1=${py(l[1])} x2=${px(l[2])} y2=${py(l[3])} marker-end=${`url(#${arrowId(id, "ok")})`} style=${{ stroke: color, strokeOpacity: strong(l) ? 0.95 : (emphasis ? 0.3 : 0.85) * (0.6 + 0.4 * fade), strokeWidth: thick(strong(l) ? width * 1.9 : width, fade) }} />`)}
  </g>`;
}

export function CarryLayer({ carries, color = "var(--c3)", progColor = "var(--c2)", width = 0.5 }) {
  const id = useMemo(nextId, []);
  const fade = fadeFor(carries.length);
  const head = headSize(fade);
  const arrow = (key, fill) => html`<marker id=${arrowId(id, key)} viewBox="0 0 6 6" refX="5" refY="3" markerWidth=${head} markerHeight=${head} markerUnits="userSpaceOnUse" orient="auto-start-reverse"><path d="M0 0 6 3 0 6z" style=${{ fill }} /></marker>`;
  return html`<g>
    <defs>${arrow("c", color)}${arrow("p", progColor)}</defs>
    ${carries.map((c, i) => html`<line key=${i} x1=${px(c[0])} y1=${py(c[1])} x2=${px(c[2])} y2=${py(c[3])} marker-end=${`url(#${arrowId(id, c[4] ? "p" : "c")})`} style=${{ stroke: c[4] ? progColor : color, strokeOpacity: (c[4] ? 0.95 : 0.8) * (0.6 + 0.4 * fade), strokeWidth: thick(c[4] ? width * 1.4 : width, fade) }} />`)}
  </g>`;
}

// ------------------------------------------------------------------ points

function Mark({ shape, x, y, r, color, filled, ...rest }) {
  const style = { fill: filled ? color : "transparent", stroke: color, strokeWidth: filled ? 0.4 : 0.7, fillOpacity: filled ? 0.9 : 0, strokeOpacity: 1 };
  switch (shape) {
    case "square": return html`<rect x=${x - r} y=${y - r} width=${2 * r} height=${2 * r} style=${style} ...${rest} />`;
    case "diamond": return html`<path d=${`M${x} ${y - r * 1.25}L${x + r * 1.25} ${y}L${x} ${y + r * 1.25}L${x - r * 1.25} ${y}Z`} style=${style} ...${rest} />`;
    case "tri": return html`<path d=${`M${x} ${y - r * 1.2}L${x + r * 1.1} ${y + r * 0.9}L${x - r * 1.1} ${y + r * 0.9}Z`} style=${style} ...${rest} />`;
    case "plus": return html`<path d=${`M${x - r} ${y}H${x + r}M${x} ${y - r}V${y + r}`} style=${{ ...style, fill: "none", strokeWidth: 0.85 }} ...${rest} />`;
    case "cross": return html`<path d=${`M${x - r} ${y - r}L${x + r} ${y + r}M${x + r} ${y - r}L${x - r} ${y + r}`} style=${{ ...style, fill: "none", strokeWidth: 0.8 }} ...${rest} />`;
    default: return html`<circle cx=${x} cy=${y} r=${r} style=${style} ...${rest} />`;
  }
}

/** Points: [[x, y, kind, ok, minute, match]] drawn by kind. `kinds` lists the kinds (with colour and shape) that are switched on. */
export function PointLayer({ points, kinds, matches, r = 0.95 }) {
  const by = Object.fromEntries(kinds.map((k) => [k.id, k]));
  const tip = (p, k) => (e) => tooltip.move(e, html`<div><div class="tt-title">${k.label}${p[3] ? "" : " (unsuccessful)"}</div>
    <div class="tt-sub">${p[4]}′${matches?.[p[5]] ? ` · ${matches[p[5]].home ? "vs" : "at"} ${matches[p[5]].opp}` : ""}</div></div>`);
  return html`<g>${points.map((p, i) => {
    const k = by[p[2]];
    return k ? html`<${Mark} key=${i} shape=${k.shape} x=${px(p[0])} y=${py(p[1])} r=${r} color=${k.color} filled=${Boolean(p[3])} onMouseMove=${tip(p, k)} onMouseLeave=${tooltip.hide} />` : null;
  })}</g>`;
}

/** Take-ons: [[x, y, ok, minute, match]]. Won ones filled. */
export function TakeOnLayer({ points, matches, color = "var(--c2)" }) {
  return html`<g>${points.map((p, i) => html`<${Mark} key=${i} shape="circle" x=${px(p[0])} y=${py(p[1])} r=${1.2} color=${color} filled=${Boolean(p[2])}
    onMouseMove=${(e) => tooltip.move(e, html`<div><div class="tt-title">Take-on ${p[2] ? "won" : "lost"}</div><div class="tt-sub">${p[3]}′${matches?.[p[4]] ? ` · ${matches[p[4]].home ? "vs" : "at"} ${matches[p[4]].opp}` : ""}</div></div>`)} onMouseLeave=${tooltip.hide} />`)}</g>`;
}

// ------------------------------------------------------------------ pass network

/**
 * Where to write each player's name so that no two names, and no name and another player's dot, overlap: above his dot, else below, else beside it.
 * The busiest players are placed first. A name that fits nowhere is left out (the hover tip still has it).
 */
function placeNames(nodes, radius, nameOf) {
  const CHAR = 1.55, HEIGHT = 3.1, GAP = 0.6;
  const hit = (a, b) => a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
  const dots = nodes.map((n) => ({ id: n.id, x: px(n.x) - radius(n), y: py(n.y) - radius(n), w: 2 * radius(n), h: 2 * radius(n) }));
  const placed = [];
  const out = new Map();
  for (const n of [...nodes].sort((a, b) => b.touches - a.touches)) {
    const w = nameOf(n).length * CHAR, r = radius(n), cx = px(n.x), cy = py(n.y);
    const options = [
      { box: { x: cx - w / 2, y: cy - r - GAP - HEIGHT, w, h: HEIGHT }, tx: cx, ty: cy - r - GAP - 0.5, anchor: "middle" },
      { box: { x: cx - w / 2, y: cy + r + GAP, w, h: HEIGHT }, tx: cx, ty: cy + r + GAP + HEIGHT - 0.5, anchor: "middle" },
      { box: { x: cx + r + GAP, y: cy - HEIGHT / 2, w, h: HEIGHT }, tx: cx + r + GAP, ty: cy + 1, anchor: "start" },
      { box: { x: cx - r - GAP - w, y: cy - HEIGHT / 2, w, h: HEIGHT }, tx: cx - r - GAP, ty: cy + 1, anchor: "end" },
    ];
    const free = options.find(({ box }) => box.x > -3 && box.x + box.w < 108 && box.y > -3 && box.y + box.h < 71
      && !placed.some((q) => hit(box, q)) && !dots.some((d) => d.id !== n.id && hit(box, d)));
    if (free) { placed.push(free.box); out.set(n.id, free); }
  }
  return out;
}

/** Nodes at the average position of each player's touches, sized by touches; links thicker for more passes between the pair. */
export function NetworkLayer({ network, color = "var(--c1)", limit = 0 }) {
  if (!network?.nodes?.length) return null;
  const nodes = limit > 0 ? [...network.nodes].sort((a, b) => b.touches - a.touches).slice(0, limit) : network.nodes;
  const kept = new Set(nodes.map((n) => n.id));
  const edges = network.edges.filter((e) => kept.has(e.a) && kept.has(e.b));
  network = { ...network, nodes, edges };
  const byId = Object.fromEntries(network.nodes.map((n) => [n.id, n]));
  const maxN = Math.max(1, ...network.edges.map((e) => e.n));
  const maxT = Math.max(1, ...network.nodes.map((n) => n.touches));
  const last = (name) => String(name || "").split(" ").slice(-1)[0];
  const radius = (n) => 1.5 + 2.0 * Math.sqrt(n.touches / maxT);
  const names = placeNames(network.nodes, radius, (n) => last(n.name));
  return html`<g>
    ${network.edges.map((e, i) => {
      const a = byId[e.a], b = byId[e.b];
      if (!a || !b) return null;
      return html`<line key=${i} x1=${px(a.x)} y1=${py(a.y)} x2=${px(b.x)} y2=${py(b.y)} style=${{ stroke: color, strokeOpacity: 0.4 + 0.5 * (e.n / maxN), strokeWidth: 0.5 + 2.1 * (e.n / maxN) }}
        onMouseMove=${(ev) => tooltip.move(ev, html`<div><div class="tt-title">${last(a.name)} ↔ ${last(b.name)}</div><div class="tt-sub">${e.n} passes between them (either way)</div></div>`)} onMouseLeave=${tooltip.hide} />`;
    })}
    ${network.nodes.map((n) => html`<g key=${n.id} onMouseMove=${(ev) => tooltip.move(ev, html`<div><div class="tt-title">${n.name}</div><div class="tt-sub">${n.touches} touches in ${network.matches} matches</div></div>`)} onMouseLeave=${tooltip.hide}>
      <circle cx=${px(n.x)} cy=${py(n.y)} r=${radius(n)} style=${{ fill: color, fillOpacity: 0.9, stroke: "var(--surface)", strokeWidth: 0.5 }} />
    </g>`)}
    ${network.nodes.map((n) => {
      const at = names.get(n.id);
      return at ? html`<text key=${"t" + n.id} class="pm-label" x=${at.tx} y=${at.ty} text-anchor=${at.anchor} pointer-events="none">${last(n.name)}</text>` : null;
    })}
  </g>`;
}

// ------------------------------------------------------------------ shots on a full pitch

const SHOT_RADIUS = (xg) => 0.7 + Math.sqrt(Math.max(0, xg)) * 2.0;

/**
 * Shots on the full pitch. Own shots attack the right-hand goal; the shots a team faced are mirrored onto the left-hand goal (their goal).
 * Each shot: [x, y, xg, result, minute, player, situation, type, match] with x, y as fractions 0-1 (1 = the goal attacked).
 */
export function ShotLayer({ shots, mirror = false, color = "var(--c1)", onPick, extra }) {
  const ordered = [...shots].sort((a, b) => (a[3] === "Goal") - (b[3] === "Goal") || b[2] - a[2]);
  return html`<g>${ordered.map((s, i) => {
    const goal = s[3] === "Goal";
    const cx = (mirror ? 1 - s[0] : s[0]) * L, cy = (mirror ? 1 - s[1] : s[1]) * W;
    return html`<circle key=${i} cx=${cx} cy=${cy} r=${SHOT_RADIUS(s[2])} style=${goal ? { fill: color, stroke: "var(--ink)", strokeWidth: 0.4, fillOpacity: 0.95 } : { fill: color, stroke: color, strokeWidth: 0.55, fillOpacity: 0.3, strokeOpacity: 0.9 }} class="shot"
      onMouseMove=${(e) => tooltip.move(e, html`<div><div class="tt-title">${goal ? "Goal" : s[3] === "SavedShot" ? "Saved" : s[3] === "BlockedShot" ? "Blocked" : s[3] === "ShotOnPost" ? "Hit the post" : "Off target"} · ${nf(s[2], 2)} xG</div>
        <div class="tt-sub">${s[5]} · ${s[4]}′${extra ? ` · ${extra(s)}` : ""}</div>
        <div class="tt-row"><span class="k">Situation</span><span class="v">${s[6]}</span></div><div class="tt-row"><span class="k">Body part</span><span class="v">${String(s[7] || "").replace(/([a-z])([A-Z])/g, "$1 $2")}</span></div></div>`)} onMouseLeave=${tooltip.hide}
      onClick=${() => onPick && onPick(s)} />`;
  })}</g>`;
}

// ------------------------------------------------------------------ zones

/** Share of touches by third and by lane, as two small bar groups. */
export function ZoneBars({ zones }) {
  if (!zones) return null;
  const row = (label, parts, names) => {
    const total = parts.reduce((a, b) => a + b, 0) || 1;
    return html`<div class="zone-bars-row"><span class="zb-label">${label}</span>
      <span class="zb-track" role="img" aria-label=${names.map((n, i) => `${n} ${nf((100 * parts[i]) / total, 0)}%`).join(", ")}>${parts.map((v, i) => html`<i key=${i} style=${{ flex: `${v} 1 0`, background: `color-mix(in oklab, var(--c1) ${35 + 25 * i}%, var(--surface-3))` }}
        onMouseMove=${(e) => tooltip.move(e, html`<div><div class="tt-title">${names[i]}</div><div class="tt-row"><span class="k">Touches</span><span class="v">${v.toLocaleString("en-GB")} (${nf((100 * v) / total, 0)}%)</span></div></div>`)} onMouseLeave=${tooltip.hide}>${(100 * v) / total >= 12 ? `${nf((100 * v) / total, 0)}%` : ""}</i>`)}</span></div>`;
  };
  return html`<div class="zone-bars">
    ${row("By third", zones.thirds, ["Own third", "Middle third", "Final third"])}
    ${row("By lane", zones.lanes, ["Left", "Centre", "Right"])}
  </div>`;
}

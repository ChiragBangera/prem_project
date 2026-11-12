// (Each layer sits in its own group: mixed in one parent, a redraw for another move could leave the lines above the numbers.)
// One move drawn on a pitch: each action numbered in order at the spot it happened, passes as arrows, carries as dotted runs, the shot or the
// place it was lost at the end. And the map of where a side's moves were taken off it. Positions are tenths of the pitch, attacking left to right.
import { html, useMemo } from "../lib/html.js";
import { tooltip } from "../lib/tooltip.js";
import { SK, MOVE_BROKEN, minuteLabel } from "../lib/matchcentre.js";
import { L, W, Pitch } from "./pitchmaps.js";

const px = (x) => (x / 1000) * L;
const py = (y) => (y / 1000) * W;
let uid = 0;

const lastName = (names, id) => { const parts = String(names?.[id] || "").trim().split(/\s+/); return parts[parts.length - 1] || ""; };

/** Where each name can go without sitting on another name or on a number: below, above, right, left of its badge; dropped if nowhere fits. */
function placeNames(badges, names) {
  const boxes = badges.map((b) => ({ x0: b.x - 1.9, x1: b.x + 1.9, y0: b.y - 1.9, y1: b.y + 1.9 }));
  const hit = (a) => boxes.some((b) => a.x0 < b.x1 && a.x1 > b.x0 && a.y0 < b.y1 && a.y1 > b.y0);
  const out = [];
  const seen = new Map();   // a player who acts twice in the same place is named once
  badges.forEach((b) => {
    const name = lastName(names, b.p);
    if (!name) return;
    const before = seen.get(b.p);
    if (before && Math.hypot(before.x - b.x, before.y - b.y) < 9) return;
    const w = name.length * 1.28 + 0.6, h = 2.8;
    const spots = [[b.x, b.y + 4.3, "middle"], [b.x, b.y - 2.5, "middle"], [b.x + 2.5, b.y + 0.9, "start"], [b.x - 2.5, b.y + 0.9, "end"]];
    for (const [x, y, anchor] of spots) {
      const x0 = anchor === "middle" ? x - w / 2 : anchor === "start" ? x : x - w;
      const box = { x0, x1: x0 + w, y0: y - h + 0.5, y1: y + 0.5 };
      if (box.x0 < 0 || box.x1 > L || box.y0 < 0 || box.y1 > W || hit(box)) continue;
      boxes.push(box);
      seen.set(b.p, b);
      out.push({ x, y, anchor, name, key: b.n });
      return;
    }
  });
  return out;
}

/**
 * The move. `lines` are its numbered actions (lib `moveLines`); `active` is the action under the pointer in the list beside it.
 * `shot` is the shot it ended in, if any.
 */
export function MovePitch({ move, lines, names, color = "var(--c1)", shot, active, label }) {
  const id = useMemo(() => `mv${++uid}`, []);
  const number = new Map(lines.filter((l) => l.n != null).map((l) => [l.step, l.n]));
  const badges = [];
  const marks = [];
  move.steps.forEach((s, i) => {
    const [kind, p, x, y, ex, ey, ok] = s;
    if (x < 0) return;
    const on = active === i;
    const X = px(x), Y = py(y);
    if (kind === SK.CARRY) {
      marks.push(html`<line key=${"c" + i} class="mv-carry" x1=${X} y1=${Y} x2=${px(ex)} y2=${py(ey)} style=${{ stroke: color }} />`);
      return;
    }
    if (kind === SK.PASS && ex >= 0) {
      marks.push(ok
        ? html`<line key=${"p" + i} class=${"mv-pass" + (on ? " on" : "")} x1=${X} y1=${Y} x2=${px(ex)} y2=${py(ey)} marker-end=${`url(#${id}-a)`} style=${{ stroke: color }} />`
        : html`<g key=${"p" + i} class=${"mv-miss" + (on ? " on" : "")}><line x1=${X} y1=${Y} x2=${px(ex)} y2=${py(ey)} />
            <path d=${`M${px(ex) - 1.1} ${py(ey) - 1.1}l2.2 2.2m0 -2.2l-2.2 2.2`} /></g>`);
    }
    if (kind === SK.SHOT) {
      const goal = shot?.result === "Goal" || move.end === "goal";
      const ty = shot?.gy != null ? Math.min(W / 2 + 7, Math.max(W / 2 - 7, py(1000 - shot.gy))) : W / 2;   // toward where it was aimed, kept near the goal
      marks.push(html`<line key=${"s" + i} class=${"mv-shot" + (goal ? " goal" : "")} x1=${X} y1=${Y} x2=${L} y2=${ty} style=${{ stroke: color }} />`);
    }
    // actions on the same spot would hide each other's numbers: a later one steps aside, the nearest free place around the spot
    let bx = X, by = Y;
    const free = (x, y) => x > 1.5 && x < L - 1.5 && y > 1.5 && y < W - 1.5 && badges.every((b) => Math.hypot(b.x - x, b.y - y) >= 3.5);
    if (!free(bx, by)) {
      search: for (const r of [3.7, 7.4, 11.1]) for (let a = 0; a < 12; a++) {
        const t = (a * Math.PI) / 6 + Math.PI / 2, x = X + r * Math.cos(t), y = Y + r * Math.sin(t);
        if (free(x, y)) { bx = x; by = y; break search; }
      }
    }
    badges.push({ x: bx, y: by, ax: X, ay: Y, p, n: number.get(i), kind, ok, on });
  });
  const labels = badges.length <= 14 ? placeNames(badges, names) : [];
  const at = move.end === "lost" && move.at ? { x: px(move.at[0]), y: py(move.at[1]) } : null;
  const breaker = at && move.by ? lastName(names, move.by) : "";
  const start = move.sat && move.sp ? { x: px(move.sat[0]), y: py(move.sat[1]) } : null;
  const drawing = html`<defs><marker id=${`${id}-a`} viewBox="0 0 6 6" refX="5.4" refY="3" markerWidth="1.9" markerHeight="1.9" markerUnits="userSpaceOnUse" orient="auto"><path d="M0 0 6 3 0 6z" style=${{ fill: color }} /></marker></defs>
    <g class="movepitch">
      ${start ? html`<g class="mv-start"><path d=${`M${start.x} ${start.y - 1.7}l1.7 1.7l-1.7 1.7l-1.7 -1.7z`} /><title>${`Won here by ${lastName(names, move.sp)}`}</title></g>` : null}
      <g>${marks}</g>
      ${at ? html`<g class="mv-break"><circle cx=${at.x} cy=${at.y} r="2.3" /><path d=${`M${at.x - 1.2} ${at.y - 1.2}l2.4 2.4m0 -2.4l-2.4 2.4`} />
        ${breaker ? html`<text x=${Math.min(L - 1, Math.max(1, at.x))} y=${at.y > W - 6 ? at.y - 3.4 : at.y + 5.2} text-anchor=${at.x > L - 12 ? "end" : at.x < 12 ? "start" : "middle"}>${breaker}</text>` : null}</g>` : null}
      <g>${badges.filter((b) => b.x !== b.ax || b.y !== b.ay).map((b) => html`<line key=${"t" + b.n} class="mv-tether" x1=${b.ax} y1=${b.ay} x2=${b.x} y2=${b.y} />`)}</g>
      <g>${badges.map((b) => html`<g key=${"b" + b.n} class=${"mv-badge" + (b.on ? " on" : "") + (b.ok || b.kind === SK.SHOT ? "" : " miss")}>
        <circle cx=${b.x} cy=${b.y} r=${b.on ? 2.3 : 1.85} style=${{ fill: b.ok || b.kind === SK.SHOT ? color : undefined, stroke: b.ok || b.kind === SK.SHOT ? undefined : color }} />
        <text x=${b.x} y=${b.y + 0.85} text-anchor="middle">${b.n}</text></g>`)}</g>
      <g>${labels.map((t) => html`<text key=${"n" + t.key} class="mv-name" x=${t.x} y=${t.y} text-anchor=${t.anchor}>${t.name}</text>`)}</g>
    </g>`;
  return html`<${Pitch} label=${label} maxWidth=${0} over=${drawing} />`;
}

/** Where a side's moves were taken off it: one cross per move, in its own direction of attack. `rows` from lib `moveBreaks`. */
export function BreakLayer({ rows, names, color = "var(--c1)" }) {
  const tip = (r) => (e) => tooltip.move(e, html`<div><div class="tt-title">${r[3] ? `Lost by ${names?.[r[3]] || "–"}` : "Lost"}</div>
    <div class="tt-sub">${r[4] ? `${MOVE_BROKEN[r[2]] || "taken by"} ${names?.[r[4]] || "–"} · ` : ""}${minuteLabel(r[5], r[6])}</div></div>`);
  return html`<g class="mv-breaks">${rows.map((r, i) => { const x = px(r[0]), y = py(r[1]);
    return html`<g key=${i} onMouseMove=${tip(r)} onMouseLeave=${tooltip.hide}><circle cx=${x} cy=${y} r="1.9" fill="transparent" />
      <path d=${`M${x - 0.95} ${y - 0.95}l1.9 1.9m0 -1.9l-1.9 1.9`} style=${{ stroke: color }} /></g>`; })}</g>`;
}

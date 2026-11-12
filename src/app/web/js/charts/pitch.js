// Football pitch drawings (metres): the shot map every level shares, and the zone map of the attacking half.
import { html } from "../lib/html.js";
import { tooltip } from "../lib/tooltip.js";
import { dateShort, nf } from "../lib/format.js";
import { bodyWord, resultWord, shotLook, shotRadius, situationWord } from "../lib/shots.js";
import { PitchMarks, Stripes } from "./pitchmaps.js";

const L = 105, W = 68;

/** Vertical attacking half, goal at the top. Coordinates: x across (0..68), y down from the goal line. */
function HalfMarks({ children }) {
  return html`<g class="pitch">
    <rect class="turf" x="0" y="0" width=${W} height="52.5" />
    <${Stripes} vertical length=${52.5} width=${W} bands=${6} />
    ${children || null}
    <rect class="mark" x="0" y="0" width=${W} height="52.5" />
    <rect class="mark" x="13.84" y="0" width="40.32" height="16.5" />
    <rect class="mark" x="24.84" y="0" width="18.32" height="5.5" />
    <circle class="spot" cx="34" cy="11" r="0.45" />
    <path class="mark" d="M26.69 16.5 A9.15 9.15 0 0 0 41.31 16.5" />
    <path class="mark" d=${`M${34 - 9.15} 52.5 A9.15 9.15 0 0 1 ${34 + 9.15} 52.5`} />
    <rect class="mark goal" x="30.34" y="-1.8" width="7.32" height="1.8" />
  </g>`;
}

/** What one shot was, for a tooltip: taker, result and xG, when, and how it came about. */
export function shotTip(s) {
  const where = s.opponent ? `${s.home === false ? "at" : "v"} ${s.opponent}` : "";
  return html`<div>
    ${s.player ? html`<div class="tt-sub" style=${{ fontWeight: 650, color: "var(--ink)" }}>${s.player}</div>` : null}
    <div class="tt-title">${resultWord(s.result)}${s.xg != null ? ` · ${nf(s.xg, 2)} xG` : ""}</div>
    <div class="tt-sub">${s.minute}′${where ? ` · ${where}` : ""}${s.date ? ` · ${dateShort(s.date)}` : ""}</div>
    ${s.xg == null ? html`<div class="tt-sub">No xG for this shot</div>` : null}
    ${s.situation ? html`<div class="tt-row"><span class="k">Situation</span><span class="v">${situationWord(s.situation)}</span></div>` : null}
    ${s.type ? html`<div class="tt-row"><span class="k">Body part</span><span class="v">${bodyWord(s.type)}</span></div>` : null}
    ${s.assisted_by ? html`<div class="tt-row"><span class="k">Assisted by</span><span class="v">${s.assisted_by}</span></div>` : null}
  </div>`;
}

/**
 * Shots on a pitch, drawn one way everywhere: size is xG, a solid circle with a dark rim is a goal, half filled is a save, faint is off target or
 * blocked, and a dashed outline is a shot with no xG. `sides`: [{ color, mirror }] by the shot's `side`; `layout`: "full" (side 0 attacks the
 * right-hand goal, a mirrored side the left) or "half" (the attacking half, goal at the top). `hot` and `sel` are shot ids to ring.
 */
export function ShotPitch({ shots, sides = [{ color: "var(--c1)" }], layout = "full", hot = null, sel = null, onHot, onPick, label, maxWidth }) {
  const half = layout === "half";
  const at = (s) => {
    const mirror = Boolean(sides[s.side ?? 0]?.mirror);
    if (half) return [s.y * W, Math.max(0, (1 - s.x) * L)];
    return [(mirror ? 1 - s.x : s.x) * L, (mirror ? 1 - s.y : s.y) * W];
  };
  // small on top of big, goals on top of the rest, so nothing is hidden under a bigger circle
  const ordered = [...shots].sort((a, b) => (a.result === "Goal") - (b.result === "Goal") || (b.xg ?? 0) - (a.xg ?? 0));
  const dots = ordered.map((s) => {
    const [cx, cy] = at(s);
    if (half && cy > 55) return null;
    return html`<circle key=${s.id} cx=${cx} cy=${cy} r=${shotRadius(s.xg)} class=${"shot " + shotLook(s)} style=${{ "--col": sides[s.side ?? 0]?.color || "var(--c1)" }}
      onMouseMove=${(e) => { tooltip.move(e, shotTip(s)); if (onHot && hot !== s.id) onHot(s.id); }} onMouseLeave=${() => { tooltip.hide(); onHot && onHot(null); }}
      onClick=${() => onPick && onPick(s)} />`;
  });
  const ring = (id, klass) => {
    const s = id == null ? null : shots.find((x) => x.id === id);
    if (!s) return null;
    const [cx, cy] = at(s);
    return half && cy > 55 ? null : html`<circle key=${klass} class=${"shot-ring " + klass} cx=${cx} cy=${cy} r=${shotRadius(s.xg) + 1.1} pointer-events="none" />`;
  };
  const text = label || `Shot map: ${shots.length} shots, ${shots.filter((s) => s.result === "Goal").length} goals`;
  return html`<div class=${"shotmap" + (half ? "" : " wide") + (onPick ? " pick" : "")} style=${maxWidth ? { maxWidth: maxWidth + "px" } : undefined}>
    ${half ? html`<svg viewBox="-2 -4 72 60" role="img" aria-label=${text}><${HalfMarks} /><g>${dots}</g><g>${ring(hot, "hot")}${ring(sel, "sel")}</g></svg>`
      : html`<svg viewBox="-2 -2 109 72" role="img" aria-label=${text}>
        <g class="pitch"><rect class="turf" x="0" y="0" width=${L} height=${W} /><${Stripes} /><${PitchMarks} /></g>
        <g>${dots}</g><g>${ring(hot, "hot")}${ring(sel, "sel")}</g>
      </svg>`}
  </div>`;
}

/** The key to a shot map. `noXg`: say what a dashed outline is (only where some shot has no xG). */
export function ShotLegend({ color = "var(--ink-2)", noXg = false, size = true }) {
  const dot = (look) => html`<svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><circle cx="7" cy="7" r="5.2" class=${"shot " + look} style=${{ "--col": color }} /></svg>`;
  return html`<div class="legend">
    <span class="item">${dot("goal")}Goal</span>
    <span class="item">${dot("on")}Saved</span>
    <span class="item">${dot("off")}Off target or blocked</span>
    ${noXg ? html`<span class="item">${dot("off noxg")}No xG for this shot</span>` : null}
    ${size ? html`<span class="item">Bigger circle = better chance (xG)</span>` : null}
  </div>`;
}

// Zone outlines on the attacking half (metres, goal at the top). Each is a hole-punched path so the zones do not overlap.
const ZONE_PATH = {
  outside: "M0 0H68V52.5H0Z M13.84 0V16.5H54.16V0Z",
  penalty: "M13.84 0H54.16V16.5H13.84Z M24.84 0V5.5H43.16V0Z",
  six: "M24.84 0H43.16V5.5H24.84Z",
};
const ZONE_TEXT = { outside: { x: 34, y: 33 }, penalty: { x: 34, y: 10.4 }, six: { x: 34, y: 3.7 } };

/**
 * The attacking half shaded by zone. zones: [{ key: "outside"|"penalty"|"six", value, name, tip }];
 * darker = a bigger value relative to `max`, so two pitches drawn with the same max compare directly.
 */
export function ZonePitch({ zones, color = "var(--c1)", max, label, maxWidth = 320 }) {
  const top = max || Math.max(1e-9, ...zones.map((z) => z.value));
  const shade = (v) => 0.1 + 0.7 * Math.min(1, Math.max(0, v) / top);
  return html`<div class="shotmap zone-pitch" style=${{ maxWidth: maxWidth + "px" }}>
    <svg viewBox="-2 -4 72 60" role="img" aria-label=${label}>
      <${HalfMarks}>
        ${zones.map((z) => html`<path key=${z.key} d=${ZONE_PATH[z.key]} fill-rule="evenodd" class="zone" style=${{ fill: color, fillOpacity: shade(z.value) }}
          onMouseMove=${(e) => tooltip.move(e, z.tip)} onMouseLeave=${tooltip.hide} />`)}
      </${HalfMarks}>
      ${zones.map((z) => html`<g key=${"t" + z.key} pointer-events="none">
        <text class="zone-val" x=${ZONE_TEXT[z.key].x} y=${ZONE_TEXT[z.key].y} text-anchor="middle" font-size=${z.key === "six" ? 2.9 : 3.8}>${nf(z.value, 2)}</text>
        ${z.key === "six" ? null : html`<text class="zone-name" x=${ZONE_TEXT[z.key].x} y=${ZONE_TEXT[z.key].y + 3.3} text-anchor="middle" font-size="2.1">${z.name}</text>`}
      </g>`)}
    </svg>
  </div>`;
}

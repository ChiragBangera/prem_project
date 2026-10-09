// Football pitch drawings (metres) and the two shot maps built on them.
import { html } from "../lib/html.js";
import { tooltip } from "../lib/tooltip.js";
import { nf } from "../lib/format.js";

const L = 105, W = 68;

/** Vertical attacking half, goal at the top. Coordinates: x across (0..68), y down from the goal line. */
function HalfMarks({ children }) {
  return html`<g class="pitch">
    <rect class="turf" x="0" y="0" width=${W} height="52.5" />
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

// Stroke widths are screen pixels (non-scaling), so marks stay crisp however the pitch is scaled.
function shotStyle(s, color) {
  const goal = s.result === "Goal";
  return goal
    ? { fill: color, stroke: "var(--ink)", strokeWidth: 1.6, fillOpacity: 0.95 }
    : { fill: color, stroke: color, strokeWidth: 1.4, fillOpacity: 0.2 };
}

const radius = (xg) => (xg == null ? 1.5 : 0.7 + Math.sqrt(Math.max(0, xg)) * 2.1);   // no xG (a live read): one size for every shot

const RESULT_WORD = { Goal: "Goal", SavedShot: "Saved", BlockedShot: "Blocked", MissedShots: "Off target", ShotOnPost: "Hit the post", OwnGoal: "Own goal" };

export function shotTip(s) {
  return html`<div>
    <div class="tt-title">${RESULT_WORD[s.result] || s.result}${s.xg != null ? ` · ${nf(s.xg, 2)} xG` : ""}</div>
    <div class="tt-sub">${s.minute}'${s.opponent ? ` vs ${s.opponent}` : ""}${s.date ? ` · ${s.date}` : ""}</div>
    ${s.situation ? html`<div class="tt-row"><span class="k">Situation</span><span class="v">${s.situation}</span></div>` : null}
    ${s.type ? html`<div class="tt-row"><span class="k">Body part</span><span class="v">${(s.type || "").replace(/([a-z])([A-Z])/g, "$1 $2")}</span></div>` : null}
    ${s.assisted_by ? html`<div class="tt-row"><span class="k">Assisted by</span><span class="v">${s.assisted_by}</span></div>` : null}
  </div>`;
}

/** One player's or team's shots on the attacking half. Radius = chance quality, filled = scored. */
export function ShotMap({ shots, color = "var(--c1)", maxWidth = 460 }) {
  const ordered = [...shots].sort((a, b) => (a.result === "Goal") - (b.result === "Goal") || b.xg - a.xg);
  return html`<div class="shotmap" style=${{ maxWidth: maxWidth + "px" }}>
    <svg viewBox="-2 -4 72 60" role="img" aria-label=${`Shot map: ${shots.length} shots, ${shots.filter((s) => s.result === "Goal").length} goals`}>
      <${HalfMarks} />
      ${ordered.map((s) => {
        const cx = s.y * W, cy = Math.max(0, (1 - s.x) * L);
        if (cy > 55) return null;
        return html`<circle key=${s.id} cx=${cx} cy=${cy} r=${radius(s.xg)} style=${shotStyle(s, color)} class="shot"
          onMouseMove=${(e) => tooltip.move(e, shotTip(s))} onMouseLeave=${tooltip.hide} />`;
      })}
    </svg>
  </div>`;
}

export function ShotLegend({ color = "var(--c1)" }) {
  return html`<div class="legend">
    <span class="item"><svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><circle cx="7" cy="7" r="5.5" style=${{ fill: color, stroke: "var(--ink)", strokeWidth: 1.3 }} /></svg>Goal</span>
    <span class="item"><svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><circle cx="7" cy="7" r="5.5" style=${{ fill: color, fillOpacity: 0.22, stroke: color, strokeWidth: 1.4 }} /></svg>No goal</span>
    <span class="item">Bigger circle = better chance (xG)</span>
  </div>`;
}

/** Full pitch, both teams. The home side attacks right, the away side is mirrored to attack left. */
export function MatchPitch({ home, away, homeColor = "var(--c1)", awayColor = "var(--c2)", onPick }) {
  const draw = (list, color, mirror) => [...list].sort((a, b) => (a.result === "Goal") - (b.result === "Goal") || (b.xg ?? 0) - (a.xg ?? 0)).map((s) => {
    const cx = (mirror ? 1 - s.x : s.x) * L, cy = (mirror ? 1 - s.y : s.y) * W;
    return html`<circle key=${s.id} cx=${cx} cy=${cy} r=${radius(s.xg)} style=${shotStyle(s, color)} class="shot"
      onMouseMove=${(e) => tooltip.move(e, html`<div><div class="tt-sub" style=${{ fontWeight: 650, color: "var(--ink)" }}>${s.player}</div>${shotTip({ ...s, opponent: null, date: null })}</div>`)} onMouseLeave=${tooltip.hide}
      onClick=${() => onPick && onPick(s)} />`;
  });
  return html`<div class="shotmap wide">
    <svg viewBox="-2 -2 109 72" role="img" aria-label="Shot map for both teams">
      <g class="pitch">
        <rect class="turf" x="0" y="0" width=${L} height=${W} />
        <rect class="mark" x="0" y="0" width=${L} height=${W} />
        <line class="mark" x1=${L / 2} y1="0" x2=${L / 2} y2=${W} />
        <circle class="mark" cx=${L / 2} cy=${W / 2} r="9.15" />
        <circle class="spot" cx=${L / 2} cy=${W / 2} r="0.45" />
        <rect class="mark" x="0" y="13.84" width="16.5" height="40.32" /><rect class="mark" x="0" y="24.84" width="5.5" height="18.32" />
        <rect class="mark" x=${L - 16.5} y="13.84" width="16.5" height="40.32" /><rect class="mark" x=${L - 5.5} y="24.84" width="5.5" height="18.32" />
        <circle class="spot" cx="11" cy=${W / 2} r="0.45" /><circle class="spot" cx=${L - 11} cy=${W / 2} r="0.45" />
        <path class="mark" d=${`M16.5 ${W / 2 - 7.31} A9.15 9.15 0 0 1 16.5 ${W / 2 + 7.31}`} /><path class="mark" d=${`M${L - 16.5} ${W / 2 - 7.31} A9.15 9.15 0 0 0 ${L - 16.5} ${W / 2 + 7.31}`} />
        <rect class="mark goal" x="-1.8" y="30.34" width="1.8" height="7.32" /><rect class="mark goal" x=${L} y="30.34" width="1.8" height="7.32" />
      </g>
      ${draw(away, awayColor, true)}
      ${draw(home, homeColor, false)}
    </svg>
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

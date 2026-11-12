// Moves (spells of possession) summed over a set of matches: how a team's end and where it loses the ball, and for one player where he
// lost it and where he took it off the other side. The same moves the Match page lists on its Moves tab (the API's `moves` block).
import { html } from "../lib/html.js";
import { tooltip } from "../lib/tooltip.js";
import { plural } from "../lib/format.js";
import { BarList, OutcomeBars, StackedBar } from "../charts/bars.js";
import { HeatLayer, L, Pitch, W } from "../charts/pitchmaps.js";
import { Card, EmptyState, playerHref } from "./common.js";

const whole = (v) => Math.round(v).toLocaleString("en-GB");
const share = (n, of) => (of > 0 ? `${Math.round((100 * n) / of)}%` : "");

const ENDS = [
  { key: "shot", label: "Ended in a shot", color: "var(--c1)" },
  { key: "kept", label: "Won a throw-in, corner or free kick", color: "var(--c3)" },
  { key: "lost", label: "Lost in play", color: "var(--c2)" },
  { key: "gave", label: "Out of play or a free kick to them", color: "var(--c5)" },
  { key: "other", label: "Ended by the whistle", color: "var(--ink-3)" },
];

/** The players of a ranked list: name (a link when Understat knows him; `links`: WhoScored id -> Understat id), a bar, the count, a short note. */
function People({ rows, note, links }) {
  if (!rows.length) return html`<p class="small muted">Nothing recorded.</p>`;
  const max = Math.max(1, ...rows.map((r) => r.n));
  return html`<div class="people">${rows.map((r) => html`<div class="people-row" key=${r.id}>
    <span class="people-name">${links?.[r.id] ? html`<a class="link-quiet" href=${playerHref(links[r.id])}>${r.name}</a>` : r.name}</span>
    <span class="track"><i style=${{ width: (r.n / max) * 100 + "%" }}></i></span>
    <b class="num">${r.n}</b>
    <span class="people-note xsmall muted">${note(r) || ""}</span>
  </div>`)}</div>`;
}

/** Team page → Style & maps: how the team's moves end, by where and how they began, where the ball is lost, who loses it, who wins it. */
export function TeamMoves({ moves, team, links }) {
  if (!moves || !moves.n) return null;
  const m = moves;
  const segments = ENDS.filter((e) => m.ends[e.key] > 0).map((e) => ({ ...e, value: m.ends[e.key] }));
  const rows = (list) => list.map((z) => ({ key: z.key, label: z.label, n: z.n, shot: z.shot, text: `${z.label}: ${z.shot} of ${z.n} moves came to a shot` }));
  const lostTotal = m.ends.lost;
  return html`<${Card} title="How their moves end"
    sub=${`A move is one spell of possession, as on a match's Moves tab. ${whole(m.n)} moves in ${plural(m.matches, "match", "matches")} (${whole(m.n / m.matches)} a match, ${(m.passes / m.n).toFixed(1)} passes each).`}>
    <${StackedBar} segments=${segments} format=${whole} />
    <div class="grid cols-2 moves-grid">
      <div class="stack" style=${{ "--gap": "18px" }}>
        <section>
          <h3 class="mini-title">By where the move began</h3>
          <${OutcomeBars} rows=${rows(m.zones)} solid="came to a shot" hatched="did not" />
        </section>
        <section>
          <h3 class="mini-title">By how it began</h3>
          <${OutcomeBars} rows=${rows(m.starts)} solid="came to a shot" hatched="did not" />
        </section>
        <p class="xsmall muted" style=${{ margin: 0 }}>“Came to a shot” counts the move itself, or the corner, free kick or penalty it won, when that was the side's next move and ended in a shot. That is why it is a little more than “ended in a shot” above (${whole(m.shot)} against ${whole(m.ends.shot)}).</p>
      </div>
      <div class="stack" style=${{ "--gap": "10px" }}>
        <h3 class="mini-title">Where ${team} lose the ball in play <span class="muted">${whole(lostTotal)} times</span></h3>
        <${Pitch} label=${`Where ${team} lost the ball in play`} maxWidth=${560}>
          <${HeatLayer} grid=${m.lost_grid} color="var(--c2)" unit="moves lost" total=${lostTotal} />
        </${Pitch}>
      </div>
    </div>
    <div class="grid cols-2 moves-grid">
      <section>
        <h3 class="mini-title">Who lost it most</h3>
        <${People} rows=${m.losers} links=${links} note=${(r) => (r.own_half ? `${r.own_half} in own half` : "")} />
        <p class="xsmall muted">The player on the ball when a move was lost in play. Players who see more of the ball lose it more: read it beside their touches, not alone.</p>
      </section>
      <section>
        <h3 class="mini-title">Who took it off the opponents most</h3>
        <${People} rows=${m.winners} links=${links} note=${(r) => (r.high ? `${r.high} high up` : "")} />
        <p class="xsmall muted">The player whose action ended an opponents' move: a tackle, a pass cut out, a loose ball, a clearance, a keeper's claim. “High up” is in the opponents' own third.</p>
      </section>
    </div>
  </${Card}>`;
}

const HOW = {
  tackle: ["Tackled", "var(--c2)"], took: ["Taken off him", "var(--c2)"], touch: ["An opponent got a touch", "var(--c2)"],
  interception: ["Pass cut out", "var(--c1)"], blocked_pass: ["Pass blocked", "var(--c1)"], pass: ["His pass found no team-mate", "var(--c1)"],
  recovery: ["Loose ball picked up by them", "var(--c5)"], clearance: ["Cleared away", "var(--c5)"], keeper: ["Gathered by the keeper", "var(--c5)"],
};
const WON = { tackle: "Tackle", took: "Took it", touch: "Got a touch", interception: "Cut a pass out", blocked_pass: "Blocked a pass", recovery: "Picked up a loose ball", clearance: "Clearance", keeper: "Keeper's claim" };
const GROUPS = [["var(--c2)", "Tackled or robbed"], ["var(--c1)", "A pass that did not arrive"], ["var(--c5)", "Loose ball, cleared, or the keeper's"]];

function Dots({ points, colorOf, labelOf, matches }) {
  return html`<g>${points.map((p, i) => html`<circle key=${i} cx=${(p[0] / 1000) * L} cy=${(p[1] / 1000) * W} r="1.15" style=${{ fill: colorOf(p), fillOpacity: 0.78, stroke: "var(--pitch-fill)", strokeWidth: 0.25 }}
    onMouseMove=${(e) => tooltip.move(e, html`<div><div class="tt-title">${labelOf(p)}</div>${matches?.[p[3]]?.opp ? html`<div class="tt-sub">${matches[p[3]].home ? "vs" : "at"} ${matches[p[3]].opp}</div>` : null}</div>`)} onMouseLeave=${tooltip.hide} />`)}</g>`;
}

/** Player page → Maps: the moves he was part of, where he lost the ball (and how), and where he took it off the other side. */
export function PlayerMoves({ moves, matches, name }) {
  if (!moves) return null;
  const m = moves;
  const who = name || "He";
  if (!m.n && !m.lost_n && !m.won_n) return html`<${Card} title="Moves he was part of"><${EmptyState} icon="info" title="No moves recorded" text="He has no part in a move in the stored matches." /></${Card}>`;
  const zones = m.lost_zone.filter((z) => z.n > 0).map((z) => `${z.n} in ${z.label === "Own third" ? "his own third" : `the ${z.label.toLowerCase()}`}`);
  return html`<${Card} title="Moves he was part of"
    sub=${`A move is one spell of possession, as on a match's Moves tab. ${who} had a part in ${whole(m.n)} of his side's moves in ${plural(m.matches, "match", "matches")}; ${whole(m.shot)} of them came to a shot${m.n ? ` (${share(m.shot, m.n)})` : ""}.`}>
    <div class="grid cols-2 moves-grid">
      <section class="stack" style=${{ "--gap": "10px" }}>
        <h3 class="mini-title">Where he lost the ball <span class="muted">${whole(m.lost_n)} times${zones.length ? `: ${zones.join(", ")}` : ""}</span></h3>
        <${Pitch} label=${`Where ${who} lost the ball`} maxWidth=${560}>
          <${Dots} points=${m.lost} matches=${matches} colorOf=${(p) => (HOW[p[2]] || HOW.took)[1]} labelOf=${(p) => (HOW[p[2]] || [p[2]])[0]} />
        </${Pitch}>
        <div class="legend">${GROUPS.map(([color, label]) => html`<span class="item" key=${label}><span class="swatch" style=${{ background: color }}></span>${label}</span>`)}</div>
        ${m.lost_how.length ? html`<${BarList} format=${whole} rows=${m.lost_how.map((h) => ({ key: h.key, label: h.label, value: h.n, color: (HOW[h.key] || HOW.took)[1] }))} />` : null}
        <p class="xsmall muted" style=${{ margin: 0 }}>He was the player on the ball when the move was lost in play. Someone who takes risks near goal loses it more there; that is not a fault by itself.</p>
      </section>
      <section class="stack" style=${{ "--gap": "10px" }}>
        <h3 class="mini-title">Where he took it off the other side <span class="muted">${whole(m.won_n)} times</span></h3>
        <${Pitch} label=${`Where ${who} ended an opponents' move`} maxWidth=${560}>
          <${Dots} points=${m.won} matches=${matches} colorOf=${() => "var(--c3)"} labelOf=${(p) => WON[p[2]] || p[2]} />
        </${Pitch}>
        <p class="xsmall muted" style=${{ margin: 0 }}>Each dot is an opponents' move that his action ended, drawn in his own side's direction of play: further right is higher up the pitch.</p>
      </section>
    </div>
  </${Card}>`;
}

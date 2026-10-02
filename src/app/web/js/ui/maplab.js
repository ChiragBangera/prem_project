// The map lab: one pitch, a layer to choose (touches, passes, defending, carries ...), and a plain reading of what is drawn.
// Used for a team (all its matches) and for a single player. The data comes from /api/maps/team or /api/maps/player/:id.
import { html, useMemo, useState } from "../lib/html.js";
import { nf, plural } from "../lib/format.js";
import { Button, Notice, Segmented } from "./common.js";
import {
  CarryLayer,
  DEF_KINDS,
  GK_KINDS,
  HeatLayer,
  NetworkLayer,
  PassLayer,
  Pitch,
  PointLayer,
  ShotLayer,
  TakeOnLayer,
  ZoneBars,
} from "../charts/pitchmaps.js";

const PASS_FILTERS = [
  { id: "all", label: "All open play", key: "all_passes", what: "Every open-play pass (throw-ins, goal kicks and corners excluded). Faint dashed lines are passes that did not find a team-mate." },
  { id: "prog", label: "Progressive", key: "prog", what: "Completed passes that move the ball at least 10 metres toward goal and end in the attacking 60% of the pitch." },
  { id: "key", label: "Key passes", key: "key", what: "Passes that led directly to a shot." },
  { id: "box", label: "Into the box", key: "box", what: "Passes that start outside the penalty area and end inside it." },
  { id: "f3", label: "Into the final third", key: "f3", what: "Passes that start before the final third and end in it." },
  { id: "long", label: "Long balls", key: "long", what: "Passes the data marks as long balls." },
  { id: "cross", label: "Crosses", key: "cross", what: "Crosses from wide areas into the box." },
  { id: "through", label: "Through balls", key: "through", what: "Passes played into space behind the defence." },
];

const LAYERS = [
  { id: "touches", label: "Touches", team: true, player: true },
  { id: "passes", label: "Passes", team: true, player: true },
  { id: "network", label: "Pass network", team: true, player: false },
  { id: "defending", label: "Defending", team: true, player: true },
  { id: "carries", label: "Carries", team: true, player: true },
  { id: "takeons", label: "Take-ons", team: true, player: true },
  { id: "shots", label: "Shots", team: true, player: false },
  { id: "keeper", label: "Goalkeeper", team: true, player: true },
];

const pctOf = (a, b) => (b ? nf((100 * a) / b, 0) + "%" : "–");

function Legend({ items }) {
  return html`<div class="legend">${items.map((it) => html`<span class="item" key=${it.label}><span class=${"swatch " + (it.shape || "box")} style=${{ background: it.color }}></span>${it.label}</span>`)}</div>`;
}

function Fact({ label, value, hint }) {
  return html`<div class="mapfact" title=${hint}><span class="label">${label}</span><b class="figure">${value}</b></div>`;
}

export function MapLab({ data, kind, shots, onMore, shotsLoading }) {
  const isTeam = kind === "team";
  const layers = LAYERS.filter((l) => (isTeam ? l.team : l.player));
  const [layer, setLayer] = useState("touches");
  const [pass, setPass] = useState("prog");
  const [failed, setFailed] = useState(true);
  const [off, setOff] = useState(() => new Set());
  const [progOnly, setProgOnly] = useState(false);
  const [defMode, setDefMode] = useState(isTeam ? "heat" : "points");   // a whole team makes thousands of actions: a heat map first, each action on request
  const [shotSide, setShotSide] = useState("both");
  const [everyone, setEveryone] = useState(false);

  const matches = data.matches || [];
  const c = data.counts || {};
  const zoneTotal = data.zones ? data.zones.thirds.reduce((a, b) => a + b, 0) : 0;
  const hasKeeper = (data.gk || []).length > 0;
  const hasShots = isTeam && shots && (shots.for.length || shots.against.length);
  const available = layers.filter((l) => (l.id === "keeper" ? hasKeeper : l.id === "shots" ? shots !== undefined : l.id === "network" ? Boolean(data.network?.nodes?.length) : true));
  const active = available.some((l) => l.id === layer) ? layer : available[0]?.id;

  const toggleKind = (id) => setOff((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const passInfo = PASS_FILTERS.find((f) => f.id === pass) || PASS_FILTERS[0];
  const passLines = data.lines?.[passInfo.key] ?? data[passInfo.key] ?? [];
  const pitch = useMemo(() => {
    switch (active) {
      case "touches": return { label: "Touch heat map", node: html`<${HeatLayer} grid=${data.grids.touches} unit="touches" total=${c.touches} />` };
      case "passes": return { label: `Passes: ${passInfo.label}`, node: html`<${PassLayer} lines=${passLines} showFailed=${failed && pass === "all"} emphasis=${0} />` };
      case "network": return { label: "Pass network", node: html`<${NetworkLayer} network=${data.network} limit=${everyone ? 0 : 12} />` };
      case "defending": return {
        label: "Defensive actions",
        node: defMode === "heat" ? html`<${HeatLayer} grid=${data.grids.def} color="var(--c2)" unit="defensive actions" total=${c.def} />`
          : html`<${PointLayer} points=${(data.def || []).filter((p) => !off.has(p[2]))} kinds=${DEF_KINDS} matches=${matches} r=${(data.def || []).length > 600 ? 0.72 : 0.95} />`,
      };
      case "carries": return { label: "Carries", node: html`<${CarryLayer} carries=${(data.carries || []).filter((p) => !progOnly || p[4])} />` };
      case "takeons": return { label: "Take-ons", node: html`<${TakeOnLayer} points=${data.takeons || []} matches=${matches} />` };
      case "keeper": return { label: "Goalkeeper actions", node: html`<${PointLayer} points=${(data.gk || []).filter((p) => !off.has("g" + p[2]))} kinds=${GK_KINDS} matches=${matches} r=${1.1} />` };
      case "shots": return {
        label: "Shots for and against",
        node: html`<g>${shotSide !== "for" ? html`<${ShotLayer} shots=${shots.against} mirror color="var(--c2)" />` : null}${shotSide !== "against" ? html`<${ShotLayer} shots=${shots.for} color="var(--c1)" />` : null}</g>`,
      };
      default: return { label: "", node: null };
    }
  }, [active, data, pass, failed, off, defMode, progOnly, shotSide, shots, everyone]);

  // the facts beside the pitch
  const facts = useMemo(() => {
    switch (active) {
      case "touches": return [["Touches", (c.touches || 0).toLocaleString("en-GB")], ["Final third", pctOf(data.zones?.thirds[2], zoneTotal)], ["Own third", pctOf(data.zones?.thirds[0], zoneTotal)]];
      case "passes": return [["Open-play passes", (c.passes || 0).toLocaleString("en-GB")], ["Completed", pctOf(c.pass_ok, c.passes)], ["Drawn", plural(passLines.length, "pass", "passes")]];
      case "network": return [["Players drawn", String(everyone ? data.network?.nodes?.length || 0 : Math.min(12, data.network?.nodes?.length || 0))], ["Strongest link", data.network?.edges?.[0] ? `${data.network.edges[0].n} passes` : "–"], ["Matches", String(data.network?.matches || data.n || 0)]];
      case "defending": return [["Defensive actions", (c.def || 0).toLocaleString("en-GB")], ["Per match", data.n ? nf((c.def || 0) / data.n, 1) : "–"], ["Recoveries", String((data.def || []).filter((p) => p[2] === 6).length)]];
      case "carries": return [["Carries", String((data.carries || []).length)], ["Progressive", String((data.carries || []).filter((p) => p[4]).length)], ["Per match", data.n ? nf((data.carries || []).length / data.n, 1) : "–"]];
      case "takeons": return [["Take-ons", String((data.takeons || []).length)], ["Won", pctOf((data.takeons || []).filter((p) => p[2]).length, (data.takeons || []).length)], ["Per match", data.n ? nf((data.takeons || []).length / data.n, 1) : "–"]];
      case "keeper": return [["Actions", String((data.gk || []).length)], ["Saves", String((data.gk || []).filter((p) => p[2] === 1).length)], ["Claims", String((data.gk || []).filter((p) => p[2] === 2).length)]];
      case "shots": return [["Shots for", String(shots?.for.length || 0)], ["xG for", nf((shots?.for || []).reduce((a, s) => a + s[2], 0), 1)], ["Shots against", String(shots?.against.length || 0)]];
      default: return [];
    }
  }, [active, data, shots, passLines.length, everyone]);

  const legend = (() => {
    if (active === "touches") return [{ label: "More touches", color: "var(--c1)" }];
    if (active === "passes") return [{ label: "Completed", color: "var(--c1)", shape: "box" }, ...(pass === "all" && failed ? [{ label: "Not completed", color: "var(--ink-3)", shape: "box" }] : [])];
    if (active === "network") return [{ label: "Player (size: touches)", color: "var(--c1)", shape: "dot" }, { label: "Line width: passes between the pair", color: "var(--accent-line)", shape: "box" }];
    if (active === "carries") return [{ label: "Carry", color: "var(--c3)" }, { label: "Progressive carry", color: "var(--c2)" }];
    if (active === "takeons") return [{ label: "Won", color: "var(--c2)", shape: "dot" }, { label: "Lost (hollow)", color: "var(--ink-3)", shape: "dot" }];
    if (active === "shots") return [{ label: "Shots for (right goal)", color: "var(--c1)", shape: "dot" }, { label: "Shots against (left goal, their goal)", color: "var(--c2)", shape: "dot" }, { label: "Bigger circle = better chance", color: "var(--ink-3)", shape: "box" }];
    return [];
  })();

  const reading = {
    touches: "Darker means more touches there. Where a team or player has the ball tells you the shape of their game: how high up the pitch, and down which side.",
    passes: passInfo.what,
    network: "Each player sits at the average position of his touches. A thicker line means more passes between two players (either direction). The data has no receiver, so a pass is credited to the next team-mate to touch the ball within a few seconds: an estimate.",
    defending: "Where the defending happens. High on the pitch means pressing and winning the ball early; deep means defending the box. Filled shapes succeeded, hollow ones did not.",
    carries: "Estimated from the gaps between a player's touches: when the ball ends up at least 3 metres from where it last was within ten seconds, he carried it (a standard method, not a measured one). Orange carries advance the ball 10 metres or more toward goal.",
    takeons: "Attempts to dribble past an opponent. Filled circles got past him.",
    keeper: "Saves, claims, punches, sweeper actions and pickups by the goalkeeper. Sweeper actions far from goal mark a keeper who plays off his line.",
    shots: "Every shot, sized by the quality of the chance (xG). A dark rim marks a goal. Shots the team took attack the right-hand goal; shots it faced are mirrored onto the left-hand goal.",
  }[active];

  if (!data.available && active !== "shots") {
    return html`<${Notice} icon="info">No event data is stored for this selection, so there is nothing to draw. Event maps need the optional event data: see the Data page for how it is fetched (it then updates by itself).</${Notice}>`;
  }
  return html`<div class="maplab">
    <div class="maplab-tabs"><${Segmented} label="Map layer" value=${active} onChange=${setLayer} options=${available.map((l) => ({ value: l.id, label: l.label }))} /></div>
    <div class="maplab-sub">
      ${active === "passes" ? html`<div class="chipgroup">${PASS_FILTERS.map((f) => html`<button type="button" key=${f.id} class="chip" aria-pressed=${String(pass === f.id)} onClick=${() => setPass(f.id)}>${f.label}</button>`)}</div>
        ${pass === "all" ? html`<label class="switch"><input type="checkbox" checked=${failed} onChange=${(e) => setFailed(e.target.checked)} /><span>Show passes that were not completed</span></label>` : null}` : null}
      ${active === "defending" ? html`<${Segmented} small label="Style" value=${defMode} onChange=${setDefMode} options=${[{ value: "points", label: "Each action" }, { value: "heat", label: "Heat map" }]} />
        ${defMode === "points" ? html`<div class="chipgroup">${DEF_KINDS.map((k) => html`<button type="button" key=${k.id} class="chip" aria-pressed=${String(!off.has(k.id))} onClick=${() => toggleKind(k.id)}><i class="dot" style=${{ background: k.color }}></i>${k.label}</button>`)}</div>` : null}` : null}
      ${active === "network" ? html`<label class="switch"><input type="checkbox" checked=${everyone} onChange=${(e) => setEveryone(e.target.checked)} /><span>Include squad players who played less (default: the 12 most involved)</span></label>` : null}
      ${active === "carries" ? html`<label class="switch"><input type="checkbox" checked=${progOnly} onChange=${(e) => setProgOnly(e.target.checked)} /><span>Progressive carries only</span></label>` : null}
      ${active === "keeper" ? html`<div class="chipgroup">${GK_KINDS.map((k) => html`<button type="button" key=${k.id} class="chip" aria-pressed=${String(!off.has("g" + k.id))} onClick=${() => toggleKind("g" + k.id)}><i class="dot" style=${{ background: k.color }}></i>${k.label}</button>`)}</div>` : null}
      ${active === "shots" ? html`<${Segmented} small label="Which shots" value=${shotSide} onChange=${setShotSide} options=${[{ value: "both", label: "For and against" }, { value: "for", label: "Shots for" }, { value: "against", label: "Shots against" }]} />` : null}
    </div>
    <div class="maplab-body">
      <div class="maplab-pitch">
        ${active === "shots" && shotsLoading ? html`<div class="well muted">Loading shots…</div>`
          : active === "shots" && !hasShots ? html`<div class="well muted">No shot data for this selection: it comes from the Understat match pages, which are downloaded in the background.</div>`
          : html`<${Pitch} label=${pitch.label}>${pitch.node}</${Pitch}>`}
      </div>
      <aside class="maplab-side">
        <div class="mapfacts">${facts.map(([label, value]) => html`<${Fact} key=${label} label=${label} value=${value} />`)}</div>
        ${legend.length ? html`<${Legend} items=${legend} />` : null}
        <p class="xsmall muted maplab-read">${reading}</p>
        ${active === "touches" ? html`<${ZoneBars} zones=${data.zones} />` : null}
        ${(data.matches || []).length ? html`<p class="xsmall muted">Based on ${plural(data.n || matches.length, "match", "matches")}${isTeam && data.formations && Object.keys(data.formations).length ? `. Formations used: ${Object.entries(data.formations).sort((a, b) => b[1] - a[1]).slice(0, 3).map(([f]) => f).join(", ")}` : ""}.</p>` : null}
        ${onMore ? html`<${Button} size="sm" kind="quiet" onClick=${onMore}>More about these maps</${Button}>` : null}
      </aside>
    </div>
  </div>`;
}

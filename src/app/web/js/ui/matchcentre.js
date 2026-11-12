// The Match page's event-data sections: the numbers of the match or of one half, momentum, where each side played and passed, how it
// defended, and the line-ups. Everything is worked out in the browser from /api/match/:id/centre (lib/matchcentre.js), so a half or a view is
// picked without waiting. A match read at half time has the same sections from what has been played so far.
import { html, useMemo, useState } from "../lib/html.js";
import { nf } from "../lib/format.js";
import { Card, Notice, Segmented, playerHref } from "./common.js";
import { DataTable } from "./table.js";
import { OutcomeBars } from "../charts/bars.js";
import { Tug } from "./matchlive.js";
import { BlockBars, Channels, FormationPitch, GoalMouth, Momentum } from "../charts/matchcharts.js";
import { CarryLayer, DEF_KINDS, HeatLayer, NetworkLayer, PassLayer, Pitch, PointLayer } from "../charts/pitchmaps.js";
import { DK, PF, blocks, channels, grid, leaders, minuteLabel, network, pick, pickShots, playerOutcomes, playerRows, teamStats } from "../lib/matchcentre.js";

const COLOR = ["var(--c1)", "var(--c2)"];
const pctf = (v) => `${nf(v, 0)}%`;
const whole = (v) => nf(v, 0);

/** Whole match, first half or second half. A half that has not been played is not offered. */
export function PeriodPicker({ c, value, onChange }) {
  const second = c.clock?.second_from != null;
  return html`<${Segmented} small label="Part of the match" value=${second ? value : value === "2" ? "all" : value} onChange=${onChange}
    options=${[{ value: "all", label: second ? "Whole match" : "So far" }, { value: "1", label: "First half" }, ...(second ? [{ value: "2", label: "Second half" }] : [])]} />`;
}

/** Why a match has no event sections, said once where they would be. */
export function NoEvents({ reason }) {
  return html`<${Notice} icon="info">${reason === "not_read"
    ? "This match has not been read from WhoScored yet, so there is nothing to draw. Its event data arrives with the half-time or full-time read."
    : "No event data is stored for this match, so momentum, passing, defending and the line-ups cannot be drawn. Event data is optional: switch it on for this league on the Data page and matches fill in by themselves."}</${Notice}>`;
}

// ------------------------------------------------------------------ overview

export function MomentumCard({ c, f }) {
  return html`<${Card} class="momentum-card" title="Momentum" sub="Who was on top, minute by minute: touches in the final third (one in the box counts three, a shot six), averaged over five minutes. Taller means more pressure."
    info="A count, not a model. For each minute, each side's touches in the opposition's final third are added up, with a touch inside the penalty area counting three and a shot six, then averaged over five minutes. The home side grows upward and the away side downward; the paler bar is the side that had less of it that minute. Goals, cards and substitutions sit on the same clock.">
    <${Momentum} c=${c} f=${f} />
  </${Card}>`;
}

const GROUPS = [
  { title: "Attack", rows: [["xg", "Expected goals", (v) => nf(v, 2)], ["shots", "Shots"], ["on_target", "On target"], ["big_chances", "Big chances"], ["box_touches", "Touches in the box"], ["box_entries", "Entries into the box"], ["f3_entries", "Entries into the final third"]] },
  { title: "On the ball", rows: [["possession", "Possession", pctf], ["tilt", "Field tilt", pctf], ["passes", "Passes"], ["pass_acc", "Pass accuracy", pctf], ["prog_passes", "Progressive passes"], ["prog_carries", "Progressive carries"], ["long_share", "Long-ball share", pctf, "none"]] },
  { title: "Without it", rows: [["tackles_won", "Tackles won"], ["interceptions", "Interceptions"], ["recoveries", "Ball recoveries"], ["high_regains", "Regains high up"], ["ppda", "Passes allowed per pressing action", (v) => nf(v, 1), "low"], ["aerial_pct", "Aerial duels won", pctf], ["fouls", "Fouls", whole, "low"]] },
];
const GROUP_HELP = "Possession is each side's share of the passes. Field tilt is its share of the touches in either final third: who had the ball where it matters. Entries are completed passes and carries that take the ball in. A progressive pass moves the ball at least ten metres toward goal into the attacking 60% of the pitch. Passes allowed per pressing action (PPDA) divides the opposition's passes in its own 60% by this side's tackles, interceptions, challenges and fouls there: lower means a harder press. Regains high up are ball recoveries in the attacking 40%.";

/** The match in numbers, home against away, for the period picked. */
export function NumbersCard({ c, period, onPeriod, hasXg }) {
  const stats = useMemo(() => teamStats(c, period), [c, period]);
  return html`<${Card} title="The match in numbers" info=${GROUP_HELP} actions=${html`<${PeriodPicker} c=${c} value=${period} onChange=${onPeriod} />`}>
    <div class="numgroups">${GROUPS.map((g) => html`<div class="numgroup" key=${g.title}>
      <h3 class="numgroup-title">${g.title}</h3>
      <div class="stack" style=${{ "--gap": "11px" }}>${g.rows.map(([key, label, format = whole, better]) => {
        const a = stats[0][key], b = stats[1][key];
        if (key === "xg" && (!hasXg || a == null || b == null)) return null;
        if (a == null || b == null) return html`<div class="tug none" key=${key}><b class="num">–</b><div class="tug-mid"><span class="tug-label">${label}</span><span class="tug-bars"></span></div><b class="num">–</b></div>`;
        return html`<${Tug} key=${key} label=${label} home=${a} away=${b} format=${format} inverse=${better === "low"} neutral=${better === "none"} />`;
      })}</div>
    </div>`)}</div>
  </${Card}>`;
}

/** Who led the match at what, both sides together. */
export function LeadersCard({ c, period, hrefOf }) {
  const boards = useMemo(() => leaders(c, period), [c, period]);
  return html`<${Card} title="Who led the match" sub="The top three at each thing, both sides together.">
    <div class="leaders">${boards.map((b) => html`<div class="leader" key=${b.key}>
      <div class="leader-label">${b.label}</div>
      ${b.top.map((p, i) => html`<div class=${"leader-row" + (i === 0 ? " first" : "")} key=${p.id}>
        <i class="side-dot" style=${{ background: COLOR[p.tm] }}></i>
        ${hrefOf(p.id) ? html`<a class="link truncate" href=${hrefOf(p.id)}>${p.name}</a>` : html`<span class="truncate">${p.name}</span>`}
        <b class="num">${p.value}</b>
      </div>`)}
    </div>`)}</div>
  </${Card}>`;
}

/** Possession and field tilt quarter-hour by quarter-hour. */
export function ControlCard({ c, f }) {
  const [measure, setMeasure] = useState("tilt");
  const rows = useMemo(() => blocks(c), [c]);
  return html`<${Card} title="Control, quarter-hour by quarter-hour" sub=${measure === "tilt" ? "Field tilt: each side's share of the touches in either final third." : "Possession: each side's share of the passes."}
    actions=${html`<${Segmented} small label="Measure" value=${measure} onChange=${setMeasure} options=${[{ value: "tilt", label: "Field tilt" }, { value: "possession", label: "Possession" }]} />`}>
    <div class="row between xsmall" style=${{ marginBottom: "8px" }}><b style=${{ color: "var(--ink)" }}>${f.home}</b><b style=${{ color: "var(--ink)" }}>${f.away}</b></div>
    <${BlockBars} rows=${rows} measure=${measure} f=${f} />
  </${Card}>`;
}

// ------------------------------------------------------------------ shots

export function GoalMouthCard({ c, f, period, hasXg }) {
  const side = (tm) => pickShots(c.shots, { period, tm });
  const line = (tm) => { const s = side(tm); return `${s.filter((x) => x.result === "Goal" || x.result === "SavedShot").length} of ${s.length} on target`; };
  return html`<${Card} title="Where the shots went" sub=${`Each goal as the shooter saw it. Filled: scored. Ringed: saved. Faint: off target or against the frame.${hasXg ? " Bigger means a better chance." : ""} Blocked shots never got there, so they are left out.`}>
    <div class="goalmouths">${[0, 1].map((tm) => html`<div class="goalmouth-side" key=${tm}>
      <div class="row between"><b><i class="side-dot" style=${{ background: COLOR[tm] }}></i>${tm === 0 ? f.home : f.away}</b><span class="muted small num">${line(tm)}</span></div>
      <${GoalMouth} shots=${side(tm)} names=${c.names} color=${COLOR[tm]} label=${`${tm === 0 ? f.home : f.away}: where the shots went in the goal`} />
    </div>`)}</div>
  </${Card}>`;
}

// ------------------------------------------------------------------ passing and territory

const PASS_VIEWS = [
  { id: "network", label: "Pass network", what: "The eleven who started, up to the first substitution or red card: each player at the average position of his touches, sized by how many he had; a thicker line means more passes between the pair. The data names no receiver, so a pass is credited to the next team-mate to touch the ball within eight seconds: an estimate." },
  { id: "touches", label: "Touches", what: "Where each side had the ball. Stronger colour means more touches there." },
  { id: "prog", label: "Progressive passes", flag: PF.PROG, what: "Completed passes that move the ball at least ten metres toward goal and end in the attacking 60% of the pitch." },
  { id: "f3", label: "Into the final third", flag: PF.F3, what: "Passes from before the final third into it. Dashed lines ending in a cross did not arrive." },
  { id: "box", label: "Into the box", flag: PF.BOX, what: "Passes from outside the penalty area into it. Dashed lines ending in a cross did not arrive." },
  { id: "key", label: "Chances created", flag: PF.KEY, what: "Passes that led straight to a shot." },
  { id: "cross", label: "Crosses", flag: PF.CROSS, what: "Crosses from wide. Dashed lines ending in a cross did not find a team-mate." },
  { id: "carries", label: "Carries", what: "Estimated from the gaps between touches: when the ball ends up at least three metres from where it last was within ten seconds, the player carried it. The brighter ones advance it ten metres or more toward goal." },
];

const asLine = (r) => [r[3], r[4], r[5], r[6], r[7], r[8], r[2], 0];

function PassPitch({ c, tm, view, period, name }) {
  const info = PASS_VIEWS.find((v) => v.id === view) || PASS_VIEWS[0];
  const { node, facts } = useMemo(() => {
    const stats = teamStats(c, period)[tm];
    if (view === "network") {
      const net = network(c, tm, { period, starters: true });
      const top = net.edges[0];
      const last = (id) => String(c.names?.[id] || "").split(" ").slice(-1)[0];
      return { node: html`<${NetworkLayer} network=${net} color=${COLOR[tm]} />`,
        facts: [["Passes between them", net.passes], ["Busiest pair", top ? `${last(top.a)} ↔ ${last(top.b)} (${top.n})` : "–"], ["Until", net.until != null ? `${net.until}′` : "the end"]] };
    }
    if (view === "touches") {
      const rows = pick(c.touches, { period, tm });
      return { node: html`<${HeatLayer} grid=${grid(rows)} color=${COLOR[tm]} unit="touches" total=${rows.length} />`,
        facts: [["Touches", stats.touches], ["In the final third", stats.f3_touches], ["In the box", stats.box_touches]] };
    }
    if (view === "carries") {
      const rows = pick(c.carries, { period, tm }).map((r) => [r[3], r[4], r[5], r[6], r[7], r[2], 0]);
      return { node: html`<${CarryLayer} carries=${rows} color="var(--pitch-ink)" progColor=${COLOR[tm]} width=${0.45} />`,
        facts: [["Carries", rows.length], ["Progressive", stats.prog_carries], ["Into the box", pick(c.carries, { period, tm }).filter((r) => r[5] >= 833 && r[6] >= 211 && r[6] <= 789 && !(r[3] >= 833 && r[4] >= 211 && r[4] <= 789)).length]] };
    }
    const rows = pick(c.passes, { period, tm }).filter((r) => r[8] & info.flag && (view === "key" || view === "cross" || !(r[8] & PF.RESTART)));
    const ok = rows.filter((r) => r[7]).length;
    return { node: html`<${PassLayer} lines=${rows.map(asLine)} color=${COLOR[tm]} failColor="var(--pitch-ink)" show=${view === "prog" ? "ok" : "both"} width=${0.55} />`,
      facts: [[info.label, rows.length], ["Completed", view === "prog" ? ok : `${ok} (${rows.length ? nf((100 * ok) / rows.length, 0) : 0}%)`], ["Pass accuracy overall", stats.pass_acc == null ? "–" : pctf(stats.pass_acc)]] };
  }, [c, tm, view, period]);
  return html`<div class="duo-side">
    <div class="duo-head"><b><i class="side-dot" style=${{ background: COLOR[tm] }}></i>${name}</b><span class="muted small">${c.teams?.[tm]?.formation ? String(c.teams[tm].formation).split("").join("-") : ""}</span></div>
    <${Pitch} label=${`${name}: ${info.label}`} maxWidth=${0} caption=${false}>${node}</${Pitch}>
    <div class="duo-facts">${facts.map(([k, v]) => html`<div key=${k}><span>${k}</span><b class="num">${v}</b></div>`)}</div>
  </div>`;
}

export function PassingSection({ c, f, period, onPeriod }) {
  const [view, setView] = useState("network");
  const info = PASS_VIEWS.find((v) => v.id === view) || PASS_VIEWS[0];
  const ch = [0, 1].map((tm) => channels(c, tm, period));
  return html`<div class="stack" style=${{ "--gap": "16px" }}>
    <${Card} title="Passing and territory" sub="Both sides drawn the same way round: attacking left to right, with their own left wing at the top."
      actions=${html`<${PeriodPicker} c=${c} value=${period} onChange=${onPeriod} />`}>
      <div class="chipgroup" role="group" aria-label="What to draw">${PASS_VIEWS.map((v) => html`<button type="button" key=${v.id} class="chip" aria-pressed=${String(view === v.id)} onClick=${() => setView(v.id)}>${v.label}</button>`)}</div>
      <p class="small muted duo-what">${info.what}</p>
      <div class="duo">
        <${PassPitch} c=${c} tm=${0} view=${view} period=${period} name=${f.home} />
        <${PassPitch} c=${c} tm=${1} view=${view} period=${period} name=${f.away} />
      </div>
    </${Card}>
    <div class="mrow m-n2">
      <${Card} title="Which side they attacked down" sub="Each side's touches in the final third, split across its left, centre and right.">
        <div class="duo tight">${[0, 1].map((tm) => html`<div class="duo-side" key=${tm}>
          <div class="duo-head"><b><i class="side-dot" style=${{ background: COLOR[tm] }}></i>${tm === 0 ? f.home : f.away}</b><span class="muted small num">${ch[tm].total} touches</span></div>
          <${Channels} shares=${ch[tm].shares} counts=${ch[tm].counts} color=${COLOR[tm]} label=${`${tm === 0 ? f.home : f.away}: attacks by side`} />
        </div>`)}</div>
      </${Card}>
      <${ControlCard} c=${c} f=${f} />
    </div>
  </div>`;
}

// ------------------------------------------------------------------ defending

const DEF_SHOWN = [DK.TACKLE, DK.INTERCEPT, DK.RECOVER, DK.CLEAR, DK.BLOCK_PASS, DK.BLOCK_SHOT];

export function DefendingSection({ c, f, period, onPeriod }) {
  const [mode, setMode] = useState("points");
  const [off, setOff] = useState(() => new Set());
  const stats = useMemo(() => teamStats(c, period), [c, period]);
  const kinds = DEF_KINDS.filter((k) => DEF_SHOWN.includes(k.id));
  const toggle = (id) => setOff((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const side = (tm) => {
    const rows = pick(c.def, { period, tm }).filter((r) => DEF_SHOWN.includes(r[5]) && !off.has(r[5]));
    const name = tm === 0 ? f.home : f.away;
    const s = stats[tm];
    const line = s.def_height;
    return html`<div class="duo-side" key=${tm}>
      <div class="duo-head"><b><i class="side-dot" style=${{ background: COLOR[tm] }}></i>${name}</b><span class="muted small num">${rows.length} actions</span></div>
      <${Pitch} label=${`${name}: defensive actions`} maxWidth=${0} caption=${false}
        over=${line != null ? html`<g class="def-line" pointer-events="none"><line x1=${line} x2=${line} y1="0" y2="68" /><text x=${line + 1.2} y="3.6">${nf(line, 0)} m</text></g>` : null}>
        ${mode === "heat" ? html`<${HeatLayer} grid=${grid(rows)} color=${COLOR[tm]} unit="defensive actions" total=${rows.length} />`
          : html`<${PointLayer} points=${rows.map((r) => [r[3], r[4], r[5], r[6], r[2], 0])} kinds=${kinds.map((k) => ({ ...k, color: k.id === DK.RECOVER ? "var(--pitch-ink)" : k.color }))} r=${1.05} />`}
      </${Pitch}>
      <div class="duo-facts">
        <div><span>Average height of the engagement</span><b class="num">${line == null ? "–" : `${nf(line, 0)} m`}</b></div>
        <div><span>Passes allowed per pressing action</span><b class="num">${s.ppda == null ? "–" : nf(s.ppda, 1)}</b></div>
        <div><span>Regains high up</span><b class="num">${s.high_regains}</b></div>
      </div>
    </div>`;
  };
  return html`<${Card} title="Defending" sub="Where each side won the ball back and broke play up, drawn in its own direction of attack: far to the right is pressing high, far to the left is defending its own box. The line is the average height of its tackles, interceptions and challenges."
    actions=${html`<${PeriodPicker} c=${c} value=${period} onChange=${onPeriod} />`}>
    <div class="row wrap" style=${{ gap: "10px 16px", marginBottom: "12px" }}>
      <${Segmented} small label="Style" value=${mode} onChange=${setMode} options=${[{ value: "points", label: "Each action" }, { value: "heat", label: "Heat map" }]} />
      <div class="chipgroup">${kinds.map((k) => html`<button type="button" key=${k.id} class="chip" aria-pressed=${String(!off.has(k.id))} onClick=${() => toggle(k.id)}><i class="dot" style=${{ background: k.id === DK.RECOVER ? "var(--ink-2)" : k.color }}></i>${k.label}</button>`)}</div>
    </div>
    <div class="duo">${side(0)}${side(1)}</div>
    <p class="xsmall muted" style=${{ marginTop: "10px" }}>Filled marks succeeded, hollow ones did not. Passes allowed per pressing action (PPDA): lower means a harder press.</p>
  </${Card}>`;
}

// ------------------------------------------------------------------ line-ups

function Bench({ c, team, tm, hrefOf }) {
  const subs = (c.timeline || []).filter((t) => t.kind === "sub" && t.tm === tm);
  const came = new Map(subs.map((t) => [t.p, t]));
  const bench = team.players.filter((p) => !p.start);
  const used = bench.filter((p) => came.has(p.id)).sort((a, b) => came.get(a.id).em - came.get(b.id).em);
  const unused = bench.filter((p) => !came.has(p.id));
  const name = (p) => (hrefOf(p.id) ? html`<a class="link" href=${hrefOf(p.id)}>${p.name}</a>` : p.name);
  return html`<div class="bench">
    <div class="duo-head"><b><i class="side-dot" style=${{ background: COLOR[tm] }}></i>${team.name}</b><span class="muted small">${team.formation ? String(team.formation).split("").join("-") : ""}${team.manager ? ` · ${team.manager}` : ""}</span></div>
    ${used.length ? html`<ul class="bench-list">${used.map((p) => { const t = came.get(p.id); return html`<li key=${p.id}><span class="num bench-min">${minuteLabel(t.pe, t.mi)}</span><span class="bench-on">${name(p)}</span><span class="muted small">for ${c.names?.[t.other] || "–"}</span></li>`; })}</ul>`
      : html`<p class="small muted">No substitutions${c.final ? "" : " yet"}.</p>`}
    ${unused.length ? html`<p class="xsmall muted">Not used: ${unused.map((p) => p.name).join(", ")}</p>` : null}
  </div>`;
}

export function LineupsSection({ c, f, hrefOf }) {
  const formations = c.teams.map((t) => (t.formations || []).filter((x) => x.name));
  const changed = formations.some((list) => new Set(list.map((x) => x.name)).size > 1);
  return html`<div class="mrow m-7-5">
    <${Card} title="Line-ups" sub=${`As they set out: ${f.home} on the left attacking right, ${f.away} on the right. A ball marks a scorer, a card a booking, a small arrow a player taken off.`}>
      <${FormationPitch} c=${c} f=${f} hrefOf=${hrefOf} />
      ${changed ? html`<p class="xsmall muted" style=${{ marginTop: "8px" }}>Shapes used: ${c.teams.map((t, i) => `${t.name} ${[...new Set(formations[i].map((x) => String(x.name).split("").join("-")))].join(", then ")}`).join(" · ")}.</p>` : null}
    </${Card}>
    <${Card} title="From the bench" sub=${[c.info?.venue, c.info?.attendance ? `${Number(c.info.attendance).toLocaleString("en-GB")} there` : null, c.info?.referee ? `referee ${c.info.referee}` : null].filter(Boolean).join(" · ") || undefined}>
      <div class="stack" style=${{ "--gap": "18px" }}><${Bench} c=${c} team=${c.teams[0]} tm=${0} hrefOf=${hrefOf} /><${Bench} c=${c} team=${c.teams[1]} tm=${1} hrefOf=${hrefOf} /></div>
    </${Card}>
  </div>`;
}

// ------------------------------------------------------------------ every player, from the events

const OUTCOME_KINDS = [["prog_passes", "progressive pass", "progressive passes"], ["prog_carries", "progressive carry", "progressive carries"], ["takeons_won", "take-on won", "take-ons won"], ["crosses", "cross", "crosses"]];

/** Who drove the ball forward most, and how much of it came to a shot: the busiest players of both sides, one split bar each. */
export function OutcomesCard({ c, f, period, hrefOf, top = 12 }) {
  const all = useMemo(() => playerOutcomes(c, period), [c, period]);
  if (!all.some((r) => r.n >= 3)) return null;
  const rows = all.slice(0, top).map((r) => {
    const parts = OUTCOME_KINDS.filter(([k]) => r.kinds[k]).map(([k, one, many]) => `${r.kinds[k].n} ${r.kinds[k].n === 1 ? one : many}`).join(", ");
    const href = hrefOf(r.id);
    return { key: r.id, n: r.n, shot: r.shot, text: r.name, color: COLOR[r.tm], label: html`<span class="row" style=${{ gap: "8px" }} title=${parts}><i class="side-dot" style=${{ background: COLOR[r.tm] }} title=${r.tm === 0 ? f.home : f.away}></i>${href ? html`<a class="link" href=${href}>${r.name}</a>` : r.name}</span>` };
  });
  const totals = [0, 1].map((tm) => all.filter((r) => r.tm === tm).reduce((a, r) => ({ n: a.n + r.n, shot: a.shot + r.shot }), { n: 0, shot: 0 }));
  const line = (tm, name) => (totals[tm].n ? `${name}: ${totals[tm].shot} of ${totals[tm].n} (${Math.round((100 * totals[tm].shot) / totals[tm].n)}%)` : `${name}: none`);
  return html`<${Card} title="Busy, and what came of it" sub=${`Progressive passes and carries, take-ons won and crosses by each player. The solid part was in a move that came to a shot. ${line(0, f.home)} · ${line(1, f.away)}.`}>
    <${OutcomeBars} rows=${rows} minN=${3} solid="came to a shot (bar in the side's colour)" />
    <p class="xsmall muted" style=${{ margin: "12px 0 0" }}>The ${rows.length} busiest players of both sides. One match is a small sample, and a move can die at someone else's feet: read it as what happened, not as a verdict. Carries are estimated from the order of events. Point at a name for the breakdown.</p>
  </${Card}>`;
}

export function EventPlayers({ c, f, period, hrefOf }) {
  const rows = useMemo(() => playerRows(c, period).filter((r) => r.touches > 0), [c, period]);
  const cols = [
    { key: "name", label: "Player", sticky: true, firstDir: "asc", className: "strong", render: (r) => html`<span class="row" style=${{ gap: "8px" }}><i class="side-dot" style=${{ background: COLOR[r.tm] }} title=${r.tm === 0 ? f.home : f.away}></i>${hrefOf(r.id) ? html`<a class="link" href=${hrefOf(r.id)}>${r.name}</a>` : r.name}</span>` },
    { key: "touches", label: "Touches", num: true }, { key: "passes", label: "Passes", num: true },
    { key: "pass_acc", label: "Pass %", num: true, render: (r) => (r.pass_acc == null ? "–" : pctf(r.pass_acc)) },
    { key: "prog_passes", label: "Prog. passes", num: true }, { key: "key_passes", label: "Chances created", num: true }, { key: "prog_carries", label: "Prog. carries", num: true },
    { key: "takeons_won", label: "Take-ons won", num: true }, { key: "box_touches", label: "Box touches", num: true }, { key: "shots", label: "Shots", num: true },
    { key: "tackles_won", label: "Tackles won", num: true }, { key: "interceptions", label: "Interceptions", num: true }, { key: "recoveries", label: "Recoveries", num: true },
    { key: "aerials_won", label: "Aerials won", num: true }, { key: "fouls", label: "Fouls", num: true },
  ];
  return html`<div class="stack"><${OutcomesCard} c=${c} f=${f} period=${period} hrefOf=${hrefOf} />
  <${Card} flush title="Every player, from the event data" sub="Both sides in one table. Click a heading to sort.">
    <${DataTable} columns=${cols} rows=${rows} rowKey=${(r) => r.id} initialSort=${{ key: "touches", dir: "desc" }} dense caption="Every player, from the event data" />
  </${Card}></div>`;
}

/** Player page links for the players the app knows (WhoScored id -> the app's player). */
export const linker = (c, scope) => (pid) => (c.links?.[pid] ? playerHref(c.links[pid], { league: scope.league, season: scope.season }) : undefined);

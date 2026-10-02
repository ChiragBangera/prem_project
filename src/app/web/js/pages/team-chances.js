// Team chances: one chart area with toggles. Choose what to break the chances down by (situation, zone, timing ...), then how to draw it
// (bars, columns, mix, versus the league, pitch). Below it, every shot on a pitch. Each view is explained and set against the league.
import { html, useState } from "../lib/html.js";
import { useApi } from "../lib/api.js";
import { setQuery, useLocation } from "../lib/router.js";
import { nf, ordinal, plural } from "../lib/format.js";
import { Tip, tooltip } from "../lib/tooltip.js";
import { Async, Badge, Button, Card, Delta, EmptyState, Notice, Segmented, Switch } from "../ui/common.js";
import { DataTable } from "../ui/table.js";
import { StackedBar } from "../charts/bars.js";
import { ColumnPairs } from "../charts/columns.js";
import { ZonePitch } from "../charts/pitch.js";
import { SERIES_COLORS } from "../charts/lines.js";
import { Pitch, ShotLayer } from "../charts/pitchmaps.js";

const NUMBERS_INFO = {
  what: "The raw counts behind the chart: shots, goals and xG for and against, plus xG per shot (how good the average shot was) and goals minus xG (finishing).",
  good: "A high xG per shot for the team and a low one against; goals above xG means finishing better than the chances suggest.",
  bad: "Goals far above xG is usually luck that fades; far below often corrects itself. Rows with few shots are dimmed as small samples.",
};
const TONE_COLOR = { positive: "var(--good, var(--c1))", negative: "var(--crit)", warning: "var(--warn)", neutral: "var(--ink-3)", info: "var(--ink-3)" };
const VIEW_LABEL = { bars: "Bars", edge: "Versus the league", columns: "Columns", mix: "Mix", pitch: "On the pitch", outcome: "Outcomes" };
const VIEW_HINT = {
  bars: "Created and allowed side by side, with the league average and rank.",
  edge: "How far above or below the league average each row is, for creating and for preventing.",
  columns: "Created and allowed in order, with the net underneath.",
  mix: "What share of the xG each row accounts for.",
  pitch: "The pitch shaded by where the xG comes from and goes.",
  outcome: "How the shots ended: goals, saves, blocks, misses.",
};

const unitWord = (group) => (group.unit === "90" ? "per 90" : "per game");
const rank = (stat) => (stat ? `${ordinal(stat.rank)} of ${stat.of}` : null);

/** The views that make sense for a breakdown, the one it was designed for first. */
function viewsFor(group) {
  const base = ["bars", "edge", "columns", "mix"];
  if (group.viz === "pitch") return ["pitch", ...base];
  if (group.viz === "outcome") return ["outcome", "bars", "edge"];
  const first = { bars: "bars", columns: "columns" }[group.viz] || "bars";
  return [first, ...base.filter((v) => v !== first)];
}

/** 1st..N: top third green, bottom third red. `kind` says which way "good" runs in the tooltip. */
function RankChip({ stat, kind, unit }) {
  if (!stat) return null;
  const third = Math.ceil(stat.of / 3);
  const tone = stat.rank <= third ? "good" : stat.rank > stat.of - third ? "crit" : "outline";
  const meaning = kind === "created" ? "1st creates the most" : "1st allows the fewest";
  return html`<${Badge} tone=${tone} title=${`${kind === "created" ? "Chances created" : "Chances allowed"}: ${ordinal(stat.rank)} of ${stat.of} teams (${meaning}). League average ${nf(stat.avg, 2)} xG ${unit}.`}>${ordinal(stat.rank)}</${Badge}>`;
}

/** The tooltip every visual shares for one row: values, quality per shot, and where it ranks. */
function rowTip(group, r, c) {
  const unit = unitWord(group);
  const rows = [
    { label: `Created (xG ${unit})`, value: `${nf(r.per_for, 2)}${c.per_for ? ` · ${rank(c.per_for)}` : ""}`, color: "var(--c1)" },
    { label: `Allowed (xG ${unit})`, value: `${nf(r.per_against, 2)}${c.per_against ? ` · ${rank(c.per_against)}` : ""}`, color: "var(--c2)" },
    { label: "Shots for / against", value: `${r.shots} / ${r.a_shots}` },
    { label: "xG per shot for / against", value: `${r.shots ? nf(r.xg_shot, 2) : "–"} / ${r.a_shots ? nf(r.a_xg_shot, 2) : "–"}` },
  ];
  if (c.per_for) rows.push({ label: "League average (created)", value: nf(c.per_for.avg, 2) });
  if (c.per_against) rows.push({ label: "League average (allowed)", value: nf(c.per_against.avg, 2) });
  return html`<${Tip} title=${r.label} sub=${r.small ? "Small sample: read with care" : r.hint} rows=${rows} />`;
}

// ------------------------------------------------------------------ the views

function AvgTick({ stat, max, unit }) {
  if (!stat) return null;
  return html`<b class="avg-tick" style=${{ left: Math.min(100, (stat.avg / max) * 100) + "%" }} title=${`League average: ${nf(stat.avg, 2)} xG ${unit}`}></b>`;
}

function Key({ group, hasLeague }) {
  return html`<div class="cbars-key">
    <span class="item"><i class="swatch box" style=${{ background: "var(--c1)" }}></i>Created</span>
    <span class="item"><i class="swatch box" style=${{ background: "var(--c2)" }}></i>Allowed</span>
    ${hasLeague ? html`<span class="item"><i class="avg-swatch"></i>League average</span>` : null}
    <span class="muted xsmall">xG ${unitWord(group)}</span>
  </div>`;
}

function Swatches({ items }) {
  return html`<div class="legend">${items.map((i) => html`<span class="item" key=${i.key}><span class="swatch box" style=${{ background: i.color }}></span>${i.label}</span>`)}</div>`;
}

function BarsView({ group, cmp }) {
  const unit = unitWord(group);
  const max = Math.max(1e-9, ...group.rows.flatMap((r) => [r.per_for, r.per_against, cmp[r.name]?.per_for?.avg || 0, cmp[r.name]?.per_against?.avg || 0]));
  return html`<div class="cbars">
    <${Key} group=${group} hasLeague=${Object.keys(cmp).length > 0} />
    ${group.rows.map((r) => {
      const c = cmp[r.name] || {};
      return html`<div class=${"cbar-row" + (r.small ? " dim" : "")} key=${r.name} title=${r.small ? "Small sample: too few shots or minutes to read much into this row." : undefined}>
        <div class="cbar-label"><b>${r.label}</b>${r.small ? html` <${Badge} tone="warn">Small sample</${Badge}>` : null}<span class="muted xsmall">${r.hint}${r.time ? ` ${nf(r.time, 0)} min.` : ""}</span></div>
        <div class="cbar-bars">
          <div class="cbar"><span class="track"><i style=${{ width: Math.min(100, (r.per_for / max) * 100) + "%", background: "var(--c1)" }}></i><${AvgTick} stat=${c.per_for} max=${max} unit=${unit} /></span><span class="val num">${nf(r.per_for, 2)}</span><${RankChip} stat=${c.per_for} kind="created" unit=${unit} /></div>
          <div class="cbar"><span class="track"><i style=${{ width: Math.min(100, (r.per_against / max) * 100) + "%", background: "var(--c2)" }}></i><${AvgTick} stat=${c.per_against} max=${max} unit=${unit} /></span><span class="val num">${nf(r.per_against, 2)}</span><${RankChip} stat=${c.per_against} kind="allowed" unit=${unit} /></div>
        </div>
        <div class="cbar-net" title="Created minus allowed"><${Delta} value=${r.per_net} digits=${2} /><span class="muted xsmall">net</span></div>
      </div>`;
    })}
  </div>`;
}

/** Creating and preventing, each as a distance from the league average: the quickest way to see where a team is better or worse than the rest. */
function EdgeView({ group, cmp }) {
  const unit = unitWord(group);
  const rows = group.rows.map((r) => {
    const c = cmp[r.name] || {};
    const known = c.per_for && c.per_against;
    return { r, c, create: known ? r.per_for - c.per_for.avg : null, prevent: known ? c.per_against.avg - r.per_against : null };
  });
  if (!rows.some((x) => x.create != null)) return html`<${Notice} icon="clock">Comparing with the other teams of the league: this view needs every team's numbers, which load in the background.</${Notice}>`;
  const max = Math.max(1e-9, ...rows.flatMap((x) => [Math.abs(x.create || 0), Math.abs(x.prevent || 0)]));
  const bar = (v) => (v == null ? null : html`<span class="edge-track"><i class="axis"></i><i class=${"fill " + (v >= 0 ? "pos" : "neg")} style=${v >= 0 ? { left: "50%", width: Math.min(50, (v / max) * 50) + "%" } : { right: "50%", width: Math.min(50, (-v / max) * 50) + "%" }}></i></span>`);
  return html`<div class="edge">
    <div class="edge-key"><span>← worse than the league average</span><span>better →</span></div>
    ${rows.map((x) => html`<div class=${"edge-row" + (x.r.small ? " dim" : "")} key=${x.r.name} onMouseMove=${(e) => tooltip.move(e, rowTip(group, x.r, x.c))} onMouseLeave=${tooltip.hide}>
      <div class="edge-label"><b>${x.r.label}</b>${x.r.small ? html` <${Badge} tone="warn">Small sample</${Badge}>` : null}</div>
      <div class="edge-lines">
        <div class="edge-line"><span class="edge-name">Creating</span>${bar(x.create)}<span class="num edge-val"><${Delta} value=${x.create} digits=${2} /></span></div>
        <div class="edge-line"><span class="edge-name">Preventing</span>${bar(x.prevent)}<span class="num edge-val"><${Delta} value=${x.prevent} digits=${2} /></span></div>
      </div>
    </div>`)}
    <p class="xsmall muted" style=${{ marginTop: "10px" }}>Creating is xG ${unit} created minus the league average. Preventing is the league average minus xG ${unit} allowed, so a positive number is good on both lines.</p>
  </div>`;
}

function MixView({ group }) {
  const seg = (get) => group.rows.map((r, i) => ({ key: r.name, label: r.label, value: get(r), color: SERIES_COLORS[(i + 2) % SERIES_COLORS.length] })).filter((s) => s.value > 0); // past blue and orange, which mean created and allowed
  const all = group.rows.map((r, i) => ({ key: r.name, label: r.label, color: SERIES_COLORS[(i + 2) % SERIES_COLORS.length] }));
  return html`<div class="stack" style=${{ "--gap": "12px" }}>
    <div><div class="mix-title">Where the xG comes from <span class="muted xsmall">${nf(group.totals.xg, 1)} xG created</span></div><${StackedBar} segments=${seg((r) => r.xg)} unit=" xG" legend=${false} height=${26} /></div>
    <div><div class="mix-title">Where the xG is conceded <span class="muted xsmall">${nf(group.totals.a_xg, 1)} xG allowed</span></div><${StackedBar} segments=${seg((r) => r.a_xg)} unit=" xG" legend=${false} height=${26} /></div>
    <${Swatches} items=${all} />
  </div>`;
}

const ZONE_KEY = { shotOboxTotal: "outside", shotPenaltyArea: "penalty", shotSixYardBox: "six" };

function ZoneView({ group, cmp }) {
  const unit = unitWord(group);
  const byName = Object.fromEntries(group.rows.map((r) => [r.name, r]));
  const max = Math.max(1e-9, ...group.rows.flatMap((r) => [r.per_for, r.per_against]));
  const zones = (get) => Object.entries(ZONE_KEY).filter(([name]) => byName[name]).map(([name, key]) => {
    const r = byName[name];
    return { key, value: r[get], name: r.label, tip: rowTip(group, r, cmp[name] || {}) };
  });
  const order = ["shotSixYardBox", "shotPenaltyArea", "shotOboxTotal"].filter((n) => byName[n]);
  return html`<div class="stack" style=${{ "--gap": "14px" }}>
    <div class="zone-pair">
      <figure><figcaption><b>Created</b> <span class="muted xsmall">xG ${unit}, at the opponent's goal</span></figcaption><${ZonePitch} zones=${zones("per_for")} color="var(--c1)" max=${max} label="Chances created by shot zone" /></figure>
      <figure><figcaption><b>Allowed</b> <span class="muted xsmall">xG ${unit}, at their own goal</span></figcaption><${ZonePitch} zones=${zones("per_against")} color="var(--c2)" max=${max} label="Chances allowed by shot zone" /></figure>
    </div>
    <div class="zone-read">
      <div class="zr-head"><span></span><span>Created</span><span>Allowed</span><span title="Average quality of a shot taken / faced">xG a shot</span></div>
      ${order.map((n) => {
        const r = byName[n], c = cmp[n] || {};
        return html`<div class="zr-row" key=${n}>
          <span><b>${r.label}</b></span>
          <span class="num">${nf(r.per_for, 2)} <${RankChip} stat=${c.per_for} kind="created" unit=${unit} /></span>
          <span class="num">${nf(r.per_against, 2)} <${RankChip} stat=${c.per_against} kind="allowed" unit=${unit} /></span>
          <span class="num muted">${r.shots ? nf(r.xg_shot, 2) : "–"} / ${r.a_shots ? nf(r.a_xg_shot, 2) : "–"}</span>
        </div>`;
      })}
    </div>
  </div>`;
}

function ColumnsView({ group, cmp }) {
  const rows = group.rows.map((r) => {
    const c = cmp[r.name] || {};
    return { key: r.name, label: r.label, a: r.per_for, b: r.per_against, aAvg: c.per_for?.avg, bAvg: c.per_against?.avg, dim: r.small, tip: rowTip(group, r, c) };
  });
  return html`<div class="stack" style=${{ "--gap": "6px" }}>
    <${Key} group=${group} hasLeague=${rows.some((r) => r.aAvg != null)} />
    <${ColumnPairs} rows=${rows} label=${`Chances created and allowed by ${group.label.toLowerCase()}`} />
  </div>`;
}

const OUTCOMES = [
  { name: "Goal", color: "var(--c1)" }, { name: "SavedShot", color: "var(--c3)" }, { name: "ShotOnPost", color: "var(--c5)" },
  { name: "BlockedShot", color: "var(--c4)" }, { name: "MissedShots", color: "var(--c8)" },
];

function OutcomeView({ group }) {
  const by = Object.fromEntries(group.rows.map((r) => [r.name, r]));
  const side = (key) => {
    const n = (name) => by[name]?.[key] || 0;
    const total = OUTCOMES.reduce((s, o) => s + n(o.name), 0) || 1;
    const onTarget = n("Goal") + n("SavedShot");
    return { total, onTarget: onTarget / total, conversion: onTarget ? n("Goal") / onTarget : 0, blocked: n("BlockedShot") / total, off: n("MissedShots") / total };
  };
  const made = side("shots"), faced = side("a_shots");
  const seg = (key) => OUTCOMES.filter((o) => by[o.name]).map((o) => ({ key: o.name, label: by[o.name].label, value: by[o.name][key], color: o.color }));
  const pctText = (v) => `${(100 * v).toFixed(0)}%`;
  const tiles = [
    { label: "On target", hint: "Goals plus saves, out of all shots", a: made.onTarget, b: faced.onTarget },
    { label: "Goals per shot on target", hint: "How often an on-target shot beat the keeper", a: made.conversion, b: faced.conversion },
    { label: "Blocked", hint: "Shots stopped by a defender", a: made.blocked, b: faced.blocked },
    { label: "Off target", hint: "Shots that missed the goal", a: made.off, b: faced.off },
  ];
  return html`<div class="stack" style=${{ "--gap": "16px" }}>
    <div><div class="mix-title">Shots the team took <span class="muted xsmall">${made.total} shots</span></div><${StackedBar} segments=${seg("shots")} unit=" shots" format=${(v) => nf(v, 0)} legend=${false} height=${26} /></div>
    <div><div class="mix-title">Shots the team faced <span class="muted xsmall">${faced.total} shots</span></div><${StackedBar} segments=${seg("a_shots")} unit=" shots" format=${(v) => nf(v, 0)} legend=${false} height=${26} /></div>
    <${Swatches} items=${OUTCOMES.filter((o) => by[o.name]).map((o) => ({ key: o.name, label: by[o.name].label, color: o.color }))} />
    <div class="tiles four">
      ${tiles.map((t) => html`<div class="tile" key=${t.label} title=${t.hint}>
        <span class="label">${t.label}</span>
        <span class="value" style=${{ color: "var(--c1)" }}>${pctText(t.a)}</span>
        <span class="delta">faced: <b>${pctText(t.b)}</b></span>
      </div>`)}
    </div>
  </div>`;
}

function Visual({ group, lg, view }) {
  const cmp = lg?.available ? lg.comparison?.[group.key] || {} : {};
  if (view === "pitch") return html`<${ZoneView} group=${group} cmp=${cmp} />`;
  if (view === "columns") return html`<${ColumnsView} group=${group} cmp=${cmp} />`;
  if (view === "outcome") return html`<${OutcomeView} group=${group} />`;
  if (view === "mix") return html`<${MixView} group=${group} />`;
  if (view === "edge") return html`<${EdgeView} group=${group} cmp=${cmp} />`;
  return html`<${BarsView} group=${group} cmp=${cmp} />`;
}

// ------------------------------------------------------------------ side panel and numbers

function Takeaways({ items, comparing }) {
  if (!items.length) return html`<p class="muted small">${comparing ? "Comparing with the league…" : "Nothing here is far from the league norm, which is a finding too."}</p>`;
  return html`<ul class="takeaways">
    ${items.map((i) => html`<li key=${i.id}>
      <i class="dot" style=${{ background: TONE_COLOR[i.tone] || TONE_COLOR.neutral }} aria-hidden="true"></i>
      <div><span class="tk-head">${i.headline}</span>
        ${i.evidence?.length ? html`<span class="tk-ev">${i.evidence.slice(0, 3).map((e) => `${e.label} ${e.value}`).join(" · ")}${i.confidence === "low" ? " · small sample" : ""}</span>` : null}</div>
    </li>`)}
  </ul>`;
}

function SidePanel({ group, insights, comparing }) {
  const g = group.guide;
  return html`<aside class="side-stack">
    <${Card} title="What stands out" class="side-card"><${Takeaways} items=${insights} comparing=${comparing} /></${Card}>
    <${Card} title="Reading it" class="side-card">
      <dl class="read-list">
        <div class="good"><dt>Good looks like</dt><dd>${g.good}</dd></div>
        <div class="bad"><dt>Watch for</dt><dd>${g.bad}</dd></div>
      </dl>
    </${Card}>
  </aside>`;
}

function Numbers({ group }) {
  const rate = unitWord(group);
  const cols = [
    { key: "label", label: group.label, firstDir: "asc", className: "strong", value: (r) => r.label },
    { key: "shots", label: "Shots", num: true },
    { key: "goals", label: "Goals", num: true },
    { key: "xg", label: "xG", num: true, title: "Expected goals created: the value of the shots taken" },
    { key: "xg_shot", label: "xG/shot", num: true, render: (r) => (r.shots ? nf(r.xg_shot, 3) : "–"), title: "Average quality of each shot. Higher means better chances, not just more shots." },
    { key: "g_xg", label: "G – xG", num: true, render: (r) => html`<${Delta} value=${r.g_xg} digits=${1} />`, title: "Goals minus xG: finishing above (blue) or below (orange) what the chances were worth" },
    { key: "a_shots", label: "Shots against", num: true },
    { key: "a_goals", label: "Goals against", num: true },
    { key: "a_xg", label: "xG against", num: true, title: "Expected goals allowed: the value of the shots the team conceded" },
    { key: "a_xg_shot", label: "xG/shot against", num: true, render: (r) => (r.a_shots ? nf(r.a_xg_shot, 3) : "–"), title: "Average quality of each shot conceded. Lower is better." },
    { key: "per_net", label: `Net ${rate}`, num: true, render: (r) => html`<${Delta} value=${r.per_net} digits=${2} />`, title: `xG created minus xG allowed, ${rate}` },
  ];
  return html`<${Card} flush title="Chance numbers, row by row" info=${NUMBERS_INFO} sub="Every count behind the chart. Click a header to sort.">
    <${DataTable} columns=${cols} rows=${group.rows} rowKey=${(r) => r.name} dense caption=${`Chances by ${group.label.toLowerCase()}`} rowClass=${(r) => (r.small ? "row-muted" : "")} />
  </${Card}>`;
}

// ------------------------------------------------------------------ every shot

const SITUATIONS = [
  { value: "all", label: "All shots", test: () => true },
  { value: "open", label: "Open play", test: (s) => s[6] === "OpenPlay" },
  { value: "corner", label: "Corners", test: (s) => s[6] === "FromCorner" },
  { value: "set", label: "Free kicks and set pieces", test: (s) => s[6] === "SetPiece" || s[6] === "DirectFreekick" },
  { value: "pen", label: "Penalties", test: (s) => s[6] === "Penalty" },
];

function totalsOf(list) {
  const xg = list.reduce((a, s) => a + s[2], 0);
  return { n: list.length, goals: list.filter((s) => s[3] === "Goal").length, xg, per: list.length ? xg / list.length : null };
}

function ShotMapCard({ team, scope }) {
  const [side, setSide] = useState("both");
  const [sit, setSit] = useState("all");
  const [goalsOnly, setGoalsOnly] = useState(false);
  const q = useApi("/api/team/shots", { team, league: scope.league, season: scope.season });
  const test = SITUATIONS.find((s) => s.value === sit).test;
  return html`<${Card} title="Every shot" sub="Where the team's shots came from, and where the shots it faced were taken. Circle size is the quality of the chance (xG); a dark rim is a goal."
    actions=${html`<${Segmented} small label="Which shots" value=${side} onChange=${setSide} options=${[{ value: "both", label: "For and against" }, { value: "for", label: "Shots for" }, { value: "against", label: "Shots against" }]} />`}>
    <${Async} q=${q}>${(d) => {
      const filt = (list) => list.filter((s) => test(s) && (!goalsOnly || s[3] === "Goal"));
      const mine = filt(d.for), theirs = filt(d.against);
      const a = totalsOf(mine), b = totalsOf(theirs);
      const [have, total] = d.coverage || [0, 0];
      return html`<div class="stack" style=${{ "--gap": "12px" }}>
        ${total && have < total ? html`<${Notice} icon="clock">Shots are stored for ${have} of ${total} matches so far; the rest arrive as match pages are downloaded.</${Notice}>` : null}
        <div class="row wrap" style=${{ gap: "12px" }}>
          <div class="chipgroup">${SITUATIONS.map((s) => html`<button type="button" key=${s.value} class="chip" aria-pressed=${String(sit === s.value)} onClick=${() => setSit(s.value)}>${s.label}</button>`)}</div>
          <${Switch} checked=${goalsOnly} onChange=${setGoalsOnly}>Goals only</${Switch}>
        </div>
        ${mine.length + theirs.length ? html`<${Pitch} label="Shots for and against" maxWidth=${940}>
            <g>${side !== "for" ? html`<${ShotLayer} shots=${theirs} mirror color="var(--c2)" />` : null}${side !== "against" ? html`<${ShotLayer} shots=${mine} color="var(--c1)" />` : null}</g>
          </${Pitch}>` : html`<${EmptyState} compact icon="scatter" title="No shots to draw" text="Nothing matches this filter, or the match pages are not downloaded yet." />`}
        <div class="legend"><span class="item"><span class="swatch dot" style=${{ background: "var(--c1)" }}></span>Shots for (right-hand goal): ${plural(a.n, "shot")}, ${a.goals} ${a.goals === 1 ? "goal" : "goals"}, ${nf(a.xg, 1)} xG${a.per != null ? `, ${nf(a.per, 2)} per shot` : ""}</span>
          <span class="item"><span class="swatch dot" style=${{ background: "var(--c2)" }}></span>Shots against (left-hand goal, their own): ${plural(b.n, "shot")}, ${b.goals} ${b.goals === 1 ? "goal" : "goals"}, ${nf(b.xg, 1)} xG${b.per != null ? `, ${nf(b.per, 2)} per shot` : ""}</span></div>
      </div>`;
    }}</${Async}>
  </${Card}>`;
}

// ------------------------------------------------------------------ page

function ChancesView({ d, lq, scope, team }) {
  const { query } = useLocation();
  const [showNumbers, setShowNumbers] = useState(false);
  const groups = d.breakdowns;
  const group = groups.find((g) => g.key === query.by) || groups[0];
  const views = group ? viewsFor(group) : [];
  const view = views.includes(query.chart) ? query.chart : views[0];
  const lg = lq.data;
  const comparing = lq.loading && !lg;
  const insights = (lg?.available ? lg.insights?.[group?.key] : null) || d.insights?.[group?.key] || [];
  const status = comparing
    ? "Comparing with the rest of the league…"
    : lg?.available ? `Compared with the other ${lg.of - 1} teams in the league.` : lg ? lg.reason : lq.error ? "League comparison is not available right now." : "";

  if (!groups.length) return html`<${Card} title="Chances"><p class="muted">Understat has no chance breakdown for this team yet.</p></${Card}>`;
  const g = group.guide;
  return html`<div class="stack" style=${{ "--gap": "16px" }}>
    <${Card} class="chances-card" title="Chances created and allowed" sub=${`${group.blurb}${status ? ` ${status}` : ""}`}>
      <div class="chart-toggles">
        <div class="toggle-row"><span class="fb-label">Break down by</span>
          <div class="chipgroup" role="group" aria-label="Break the chances down by">${groups.map((x) => html`<button type="button" class="chip" key=${x.key} aria-pressed=${String(x.key === group.key)} onClick=${() => setQuery({ by: x.key === groups[0].key ? null : x.key, chart: null })} title=${x.blurb}>${x.label}</button>`)}</div></div>
        <div class="toggle-row"><span class="fb-label">Draw it as</span>
          <${Segmented} small label="Chart type" value=${view} onChange=${(v) => setQuery({ chart: v === views[0] ? null : v })} options=${views.map((v) => ({ value: v, label: VIEW_LABEL[v], title: VIEW_HINT[v] }))} />
          <span class="xsmall muted">${VIEW_HINT[view]}</span></div>
      </div>
      <div class="chances-grid">
        <div class="stack" style=${{ "--gap": "10px", minWidth: 0 }}>
          <${Visual} group=${group} lg=${lg} view=${view} />
          ${group.note ? html`<p class="xsmall muted">${group.note}</p>` : null}
          <p class="chart-caption" style=${{ margin: 0 }}>${g.read}</p>
        </div>
        <${SidePanel} group=${group} insights=${insights} comparing=${comparing} />
      </div>
      <div class="row" style=${{ gap: "10px", marginTop: "12px" }}>
        <${Button} kind="quiet" size="sm" icon=${showNumbers ? "chevronDown" : "chevronRight"} onClick=${() => setShowNumbers(!showNumbers)}>${showNumbers ? "Hide the numbers" : "Show the numbers"}</${Button}>
      </div>
    </${Card}>
    ${showNumbers ? html`<${Numbers} group=${group} />` : null}
    <${ShotMapCard} team=${team} scope=${scope} />
  </div>`;
}

export default function Chances({ team, scope }) {
  const params = { team, league: scope.league, season: scope.season };
  const q = useApi("/api/team/chances", params);
  const lq = useApi("/api/team/chances/league", params, { staleMs: 600000 }); // slower (every team's page): the tab does not wait for it
  return html`<${Async} q=${q}>${(d) => html`<${ChancesView} d=${d} lq=${lq} scope=${scope} team=${team} />`}</${Async}>`;
}

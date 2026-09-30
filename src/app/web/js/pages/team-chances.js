// Team chances: the chances a side creates and allows, broken down seven ways, each one explained and set against the league.
import { html, useState } from "../lib/html.js";
import { useApi } from "../lib/api.js";
import { setQuery, useLocation } from "../lib/router.js";
import { nf, ordinal, signed } from "../lib/format.js";
import { Async, Badge, Card, Delta, Insights } from "../ui/common.js";
import { DataTable } from "../ui/table.js";
import { StackedBar } from "../charts/bars.js";
import { SERIES_COLORS } from "../charts/lines.js";

const GUIDE_KEY = "prem-lab.chances-guide-open";
const readOpen = () => { try { return localStorage.getItem(GUIDE_KEY) !== "0"; } catch (_) { return true; } };
const saveOpen = (v) => { try { localStorage.setItem(GUIDE_KEY, v ? "1" : "0"); } catch (_) { /* private mode: it just will not be remembered */ } };

const BARS_INFO = {
  what: "For each row, the blue bar is the xG the team created and the orange bar is the xG it allowed, on the same scale. The small tick marks the league average, and the chip is the team's rank among the league (1st is best).",
  good: "Blue longer than orange, blue past its tick, orange short of its tick, and a green 1st–6th chip.",
  bad: "Orange longer than blue, a red chip near the bottom, or a big row where the team is below the league tick.",
};
const NUMBERS_INFO = {
  what: "The raw counts behind the bars: shots, goals and xG for and against, plus xG per shot (how good the average shot was) and goals minus xG (finishing).",
  good: "A high xG per shot for the team and a low one against; goals above xG means finishing better than the chances suggest.",
  bad: "Goals far above xG is usually luck that fades; far below often corrects itself. Rows with few shots are dimmed as small samples.",
};

/** 1st..N: top third green, bottom third red. `kind` says which way "good" runs in the tooltip. */
function RankChip({ stat, kind, unit }) {
  if (!stat) return null;
  const third = Math.ceil(stat.of / 3);
  const tone = stat.rank <= third ? "good" : stat.rank > stat.of - third ? "crit" : "outline";
  const meaning = kind === "created" ? "1st creates the most" : "1st allows the fewest";
  return html`<${Badge} tone=${tone} title=${`${kind === "created" ? "Chances created" : "Chances allowed"}: ${ordinal(stat.rank)} of ${stat.of} teams (${meaning}). League average ${nf(stat.avg, 2)} xG ${unit}.`}>${ordinal(stat.rank)}</${Badge}>`;
}

function AvgTick({ stat, max, unit }) {
  if (!stat) return null;
  return html`<b class="avg-tick" style=${{ left: Math.min(100, (stat.avg / max) * 100) + "%" }} title=${`League average: ${nf(stat.avg, 2)} xG ${unit}`}></b>`;
}

function ChanceBars({ group, lg }) {
  const unit = group.unit === "90" ? "per 90" : "per game";
  const cmp = lg?.available ? lg.comparison?.[group.key] || {} : {};
  const max = Math.max(1e-9, ...group.rows.flatMap((r) => [r.per_for, r.per_against, cmp[r.name]?.per_for?.avg || 0, cmp[r.name]?.per_against?.avg || 0]));
  const hasLeague = Object.keys(cmp).length > 0;
  return html`<div class="cbars">
    <div class="cbars-key">
      <span class="item"><i class="swatch box" style=${{ background: "var(--c1)" }}></i>Created</span>
      <span class="item"><i class="swatch box" style=${{ background: "var(--c2)" }}></i>Allowed</span>
      ${hasLeague ? html`<span class="item"><i class="avg-swatch"></i>League average</span>` : null}
      <span class="muted xsmall">xG ${unit}</span>
    </div>
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

function MixBars({ group }) {
  const seg = (get) => group.rows.map((r, i) => ({ key: r.name, label: r.label, value: get(r), color: SERIES_COLORS[(i + 2) % SERIES_COLORS.length] })).filter((s) => s.value > 0); // start past blue and orange, which mean created and allowed below
  return html`<div class="stack" style=${{ "--gap": "10px" }}>
    <div><div class="mix-title">Where the xG comes from <span class="muted xsmall">${nf(group.totals.xg, 1)} xG created</span></div><${StackedBar} segments=${seg((r) => r.xg)} unit=" xG" legend=${false} /></div>
    <div><div class="mix-title">Where the xG is conceded <span class="muted xsmall">${nf(group.totals.a_xg, 1)} xG allowed</span></div><${StackedBar} segments=${seg((r) => r.a_xg)} unit=" xG" /></div>
  </div>`;
}

function Guide({ group }) {
  const [open, setOpen] = useState(readOpen);
  const toggle = () => { saveOpen(!open); setOpen(!open); };
  const g = group.guide;
  return html`<section class="card guide-card">
    <button type="button" class="guide-head" aria-expanded=${String(open)} onClick=${toggle}>
      <span class="card-title">How to read this: ${group.label}</span><span class="muted small">${open ? "Hide" : "Show"}</span>
    </button>
    ${open ? html`<dl class="guide-grid">
      <div><dt>What it is</dt><dd>${g.what}</dd></div>
      <div><dt>How to read the chart</dt><dd>${g.read}</dd></div>
      <div class="good"><dt>What good looks like</dt><dd>${g.good}</dd></div>
      <div class="bad"><dt>What to watch for</dt><dd>${g.bad}</dd></div>
    </dl>` : null}
  </section>`;
}

function Numbers({ group }) {
  const rate = group.unit === "90" ? "per 90" : "per game";
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
  return html`<${Card} flush title="Chance numbers, row by row" info=${NUMBERS_INFO} sub="Every count behind the bars. Click a header to sort.">
    <${DataTable} columns=${cols} rows=${group.rows} rowKey=${(r) => r.name} dense caption=${`Chances by ${group.label.toLowerCase()}`} rowClass=${(r) => (r.small ? "row-muted" : "")} />
  </${Card}>`;
}

function ChancesView({ d, lq, scope }) {
  const { query } = useLocation();
  const groups = d.breakdowns;
  const group = groups.find((g) => g.key === query.by) || groups[0];
  const lg = lq.data;
  const insights = (lg?.available ? lg.insights?.[group.key] : null) || d.insights?.[group.key] || [];
  const status = lq.loading && !lg
    ? "Comparing with the rest of the league…"
    : lg?.available ? `Compared with the other ${lg.of - 1} teams in the league.` : lg ? lg.reason : lq.error ? "League comparison is not available right now." : "";

  if (!groups.length) return html`<${Card} title="Chances"><p class="muted">Understat has no chance breakdown for this team yet.</p></${Card}>`;
  return html`<div class="stack" style=${{ "--gap": "16px" }}>
    <${Card} title="Break the chances down by" sub=${group.blurb}>
      <div class="season-chips" role="group" aria-label="Break the chances down by">
        ${groups.map((g) => html`<button type="button" class="chip" key=${g.key} aria-pressed=${String(g.key === group.key)} onClick=${() => setQuery({ by: g.key === groups[0].key ? null : g.key })} title=${g.blurb}>${g.label}</button>`)}
      </div>
      ${status ? html`<p class="xsmall muted" style=${{ marginTop: "10px" }}>${status}</p>` : null}
    </${Card}>

    <${Guide} group=${group} />
    ${insights.length ? html`<${Insights} items=${insights} scope=${scope} />` : null}

    <${Card} title=${`Chances created and allowed, by ${group.label.toLowerCase()}`} info=${BARS_INFO} sub=${`All values are xG ${group.unit === "90" ? "per 90 minutes" : "per game"}. Blue is created, orange is allowed.`}>
      <div class="stack" style=${{ "--gap": "20px" }}>
        <${MixBars} group=${group} />
        <${ChanceBars} group=${group} lg=${lg} />
        ${group.note ? html`<p class="xsmall muted">${group.note}</p>` : null}
      </div>
    </${Card}>

    <${Numbers} group=${group} />
  </div>`;
}

export default function Chances({ team, scope }) {
  const params = { team, league: scope.league, season: scope.season };
  const q = useApi("/api/team/chances", params);
  const lq = useApi("/api/team/chances/league", params, { staleMs: 600000 }); // slower (every team's page): the tab does not wait for it
  return html`<${Async} q=${q}>${(d) => html`<${ChancesView} d=${d} lq=${lq} scope=${scope} />`}</${Async}>`;
}

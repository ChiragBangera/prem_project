// Team matches: the season match by match, with the chances behind each result and (where event data exists) how the team played.
import { html, useMemo } from "../lib/html.js";
import { useApi } from "../lib/api.js";
import { navigate } from "../lib/router.js";
import { dateShort, formation, nf, plural, signed } from "../lib/format.js";
import { Tip } from "../lib/tooltip.js";
import { Async, Card, Crest, Notice } from "../ui/common.js";
import { DataTable } from "../ui/table.js";
import { Scatter } from "../charts/scatter.js";

const RESULT_COLOR = { w: "var(--good)", d: "var(--ink-3)", l: "var(--crit)" };
const RESULT_WORD = { w: "Won", d: "Drew", l: "Lost" };

export function ResultChip({ m }) {
  return html`<span class=${"rchip " + m.result} title=${RESULT_WORD[m.result]}><b>${m.result.toUpperCase()}</b> ${m.gf}–${m.ga}</span>`;
}

const dash = (v, fmt = (x) => x) => (v == null ? html`<span class="muted">–</span>` : fmt(v));

function columns() {
  return [
    { key: "n", label: "MW", num: true, width: "52px", firstDir: "desc", title: "The team's nth league match (a postponed game shifts later weeks).", render: (m) => m.n },
    { key: "date", label: "Date", firstDir: "desc", render: (m) => dateShort(m.date) },
    { key: "opponent", label: "Opponent", sticky: true, firstDir: "asc", width: "220px", render: (m) => html`<span class="cell-team"><${Crest} team=${m.opponent} short=${m.opponent_short} size=${22} /><span class="muted xsmall">${m.venue === "h" ? "vs" : "at"}</span><span>${m.opponent}</span></span>` },
    { key: "result", label: "Result", sortable: false, render: (m) => html`<${ResultChip} m=${m} />` },
    { key: "xg", label: "xG", num: true, render: (m) => nf(m.xg, 2), title: "Expected goals created: the value of the shots taken." },
    { key: "xga", label: "xGA", num: true, render: (m) => nf(m.xga, 2), title: "Expected goals allowed." },
    { key: "luck", label: "Pts − xPts", num: true, title: "Points won minus the points the chances were worth. Blue: more than deserved.", render: (m) => html`<span class=${"delta-val " + (m.luck > 0.5 ? "pos" : m.luck < -0.5 ? "neg" : "")}>${signed(m.luck, 1)}</span>` },
    { key: "poss", label: "Poss", num: true, title: "Share of the match's passes: the team's possession.", render: (m) => dash(m.poss, (v) => `${v}%`) },
    { key: "passes", label: "Passes", num: true, render: (m) => dash(m.passes) },
    { key: "pass_acc", label: "Pass %", num: true, render: (m) => dash(m.pass_acc, (v) => `${v}%`) },
    { key: "prog", label: "Prog", num: true, title: "Progressive passes: completed passes that move the ball 10+ metres toward goal into the attacking 60%.", render: (m) => dash(m.prog) },
    { key: "tilt", label: "Tilt", num: true, title: "Field tilt: the team's share of both sides' touches in the final third.", render: (m) => dash(m.tilt, (v) => `${v}%`) },
    { key: "ppda", label: "PPDA", num: true, title: "Opponent passes allowed per defensive action. Lower means a more intense press.", render: (m) => dash(m.ppda, (v) => nf(v, 1)) },
    { key: "tackles", label: "Tkl", num: true, render: (m) => dash(m.tackles) },
    { key: "recoveries", label: "Rec", num: true, render: (m) => dash(m.recoveries) },
    { key: "formation", label: "Shape", render: (m) => dash(formation(m.formation)) },
  ];
}

function PossessionChart({ matches }) {
  const rated = matches.filter((m) => m.poss != null);
  if (rated.length < 6) return null;
  const points = rated.map((m) => ({ id: m.n, x: m.poss, y: m.xg - m.xga, label: m.opponent_short, showLabel: true, priority: Math.abs(m.xg - m.xga), r: 6.5, color: RESULT_COLOR[m.result], data: m }));
  const dominant = rated.filter((m) => m.poss >= 55), other = rated.filter((m) => m.poss < 55);
  const record = (list) => `${list.filter((m) => m.result === "w").length}W ${list.filter((m) => m.result === "d").length}D ${list.filter((m) => m.result === "l").length}L`;
  const sub = `${dominant.length ? `With 55%+ of the ball (${plural(dominant.length, "match", "matches")}): ${record(dominant)}.` : "Never reached 55% possession."} ${other.length ? `Without it (${plural(other.length, "match", "matches")}): ${record(other)}.` : ""}`;
  return html`<${Card} title="Does having the ball help?" sub=${sub}>
    <${Scatter} points=${points} height=${340} xLabel="Possession (share of passes) →" yLabel="Chance difference in the match (xG − xGA) →" refY=${0} zeroY=${0}
      xFormat=${(v) => `${v}%`} yFormat=${(v) => signed(v, 1)} hoverPad=${18} label="Possession against chance difference, one dot per match"
      onSelect=${(p) => p.data.match_id && navigate(`/match/${p.data.match_id}`)}
      renderTip=${(p) => html`<${Tip} title=${`${p.data.venue === "h" ? "vs" : "at"} ${p.data.opponent}`} sub=${`${dateShort(p.data.date)} · ${RESULT_WORD[p.data.result]} ${p.data.gf}–${p.data.ga}`} rows=${[
        { label: "Possession", value: `${p.data.poss}%` }, { label: "xG – xGA", value: `${nf(p.data.xg, 2)} – ${nf(p.data.xga, 2)}` }, { label: "Chance difference", value: signed(p.data.xg - p.data.xga, 2) },
      ]} />`} />
    <div class="legend" style=${{ marginTop: "8px" }}>${["w", "d", "l"].map((r) => html`<span class="item" key=${r}><span class="swatch dot" style=${{ background: RESULT_COLOR[r] }}></span>${RESULT_WORD[r]}</span>`)}<span class="item muted">Above the line: created more than allowed</span></div>
  </${Card}>`;
}

function MatchesView({ d }) {
  const cols = useMemo(columns, []);
  const have = d.matches.filter((m) => m.poss != null).length;
  return html`<div class="stack" style=${{ "--gap": "16px" }}>
    ${have === 0 ? html`<${Notice} icon="info">No event data is stored for this team's matches yet, so possession, passing and pressing columns are blank (never zero). They fill in by themselves as event data is fetched: see the Data page.</${Notice}>`
      : have < d.matches.length ? html`<${Notice} icon="clock">Event data covers ${have} of ${d.matches.length} matches; the others show a dash in the style columns.</${Notice}>` : null}
    <${Card} flush title="Match by match" sub="Click a match for its report. Click a heading to sort.">
      <${DataTable} columns=${cols} rows=${d.matches} rowKey=${(m) => m.n} initialSort=${{ key: "n", dir: "desc" }} dense tight caption="Team matches"
        onRowClick=${(m) => m.match_id && navigate(`/match/${m.match_id}`)} maxHeight="min(70vh, 760px)" />
    </${Card}>
    <${PossessionChart} matches=${d.matches} />
  </div>`;
}

export default function TeamMatches({ team, scope }) {
  const q = useApi("/api/team/matches", { team, league: scope.league, season: scope.season });
  return html`<${Async} q=${q}>${(d) => html`<${MatchesView} d=${d} />`}</${Async}>`;
}

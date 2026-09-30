// Team history: one team, several of its seasons, laid over each other by matchweek.
import { html, useState } from "../lib/html.js";
import { useApi } from "../lib/api.js";
import { useMeta, setSeason } from "../lib/scope.js";
import { setQuery, useLocation } from "../lib/router.js";
import { nf, ordinal, plural, signed } from "../lib/format.js";
import { useStableSlots } from "../lib/slots.js";
import { Async, Badge, Button, Card, Delta, EmptyState, Notice, Segmented } from "../ui/common.js";
import { DataTable } from "../ui/table.js";
import { LineChart, SERIES_COLORS } from "../charts/lines.js";

const DEFAULT_SEASONS = 5;
const MAX_SEASONS = 8; // one colour each
const XG_VIEWS = [
  { value: "xgd_cum", label: "Running total", title: "Cumulative xG for minus xG against, match by match" },
  { value: "xgd_roll", label: "Last 5 matches", title: "Average xG difference over the last five matches" },
];

const short = (label) => label.slice(2); // "2025/26" -> "25/26" (the chart's end labels are narrow)
const csv = (v) => (v ? v.split(",").map(Number).filter(Number.isFinite) : []);

function SeasonPicker({ options, selected, viewing, colorOf, onChange }) {
  const set = new Set(selected);
  const full = selected.length >= MAX_SEASONS;
  const toggle = (s) => onChange(set.has(s) ? selected.filter((x) => x !== s) : [...selected, s]);
  const newest = options.map((o) => o.season);
  return html`<${Card} title="Seasons to compare" sub=${`Pick up to ${MAX_SEASONS}. Each season keeps its colour in every chart below.`}
    actions=${html`<div class="row wrap" style=${{ gap: "6px" }}>
      <${Button} kind="quiet" size="sm" onClick=${() => onChange(newest.slice(0, DEFAULT_SEASONS))}>Last 5</${Button}>
      <${Button} kind="quiet" size="sm" onClick=${() => onChange(newest.slice(0, MAX_SEASONS))}>Last 8</${Button}>
      <${Button} kind="quiet" size="sm" onClick=${() => onChange([viewing])} title="Keep only the season you opened this team from">Just this season</${Button}>
    </div>`}>
    <div class="season-chips" role="group" aria-label="Seasons to compare">
      ${options.map((o) => {
        const on = set.has(o.season);
        return html`<button type="button" class="chip" key=${o.season} aria-pressed=${String(on)} disabled=${!on && full} onClick=${() => toggle(o.season)}
          title=${!on && full ? `Up to ${MAX_SEASONS} seasons at a time` : o.season === viewing ? "The season you opened this team from" : undefined}>
          ${on ? html`<i class="dot" style=${{ background: colorOf(o.season) }}></i>` : null}${o.label}${o.season === viewing ? html`<span class="chip-note">viewing</span>` : null}
        </button>`;
      })}
    </div>
  </${Card}>`;
}

function SeasonTable({ seasons, viewing, colorOf, league }) {
  const open = (r) => {
    if (!r.available) return;
    setSeason(String(r.season));
    setQuery({ tab: null, seasons: null });
    window.scrollTo({ top: 0 });
  };
  const blank = (r, node) => (r.available ? node : html`<span class="muted">–</span>`);
  const cols = [
    { key: "label", label: "Season", sortable: false, className: "strong", render: (r) => html`<span class="season-cell">
      <i class="dot" style=${{ background: colorOf(r.season) }}></i>${r.label}${r.season === viewing ? html` <${Badge} tone="accent" title="The season you opened this team from">Viewing</${Badge}>` : null}</span>` },
    { key: "finish", label: "Finish", num: true, sortable: false, title: "Final league position. In a season still being played, position so far.", render: (r) => (r.available
      ? html`<b>${ordinal(r.final_rank)}</b><span class="muted small"> of ${r.n_teams}${r.complete ? "" : " so far"}</span>`
      : html`<span class="muted">${r.reason}</span>`) },
    { key: "played", label: "P", num: true, sortable: false, title: "Matches played", render: (r) => blank(r, r.played) },
    { key: "pts", label: "Pts", num: true, sortable: false, render: (r) => blank(r, html`<b>${r.pts}</b>`) },
    { key: "xpts", label: "xPts", num: true, sortable: false, title: "Expected points: what the chances created and allowed were worth", render: (r) => blank(r, nf(r.xpts, 1)) },
    { key: "gap", label: "Pts – xPts", num: true, sortable: false, title: "Blue: more points than the chances earned (often luck). Orange: fewer.", render: (r) => blank(r, html`<${Delta} value=${r.pts - r.xpts} digits=${1} />`) },
    { key: "gd", label: "GD", num: true, sortable: false, title: "Goal difference", render: (r) => blank(r, signed(r.gd, 0)) },
    { key: "xgd", label: "xGD", num: true, sortable: false, title: "Expected goal difference: chances created minus chances allowed", render: (r) => blank(r, html`<${Delta} value=${r.xgd} digits=${1} />`) },
  ];
  return html`<${Card} flush title="Seasons side by side" sub="Where the team finished each year, and whether the results matched the chances.">
    <${DataTable} columns=${cols} rows=${seasons} rowKey=${(r) => r.season} dense caption=${`${league} seasons compared`}
      onRowClick=${open} rowClass=${(r) => (r.available ? "" : "row-muted")} />
    <div class="card-foot"><span>Click a season to open the whole team page for that year.</span></div>
  </${Card}>`;
}

/** Axis ticks for the position chart: 1st always, then a step that suits how far down the lines reach. */
function rankTicks(lowest) {
  const step = lowest <= 6 ? 1 : lowest <= 12 ? 2 : 5;
  const ticks = [1];
  for (let v = step === 5 ? 5 : 1 + step; v <= lowest; v += step) ticks.push(v);
  return ticks;
}

function Charts({ d, viewing, colorOf }) {
  const [xg, setXg] = useState("xgd_cum");
  const [fit, setFit] = useState("fit");
  const ok = d.seasons.filter((s) => s.available);
  const rounds = d.rounds_max;
  if (rounds < 2) return html`<${EmptyState} compact icon="calendar" title="Not enough matches yet" text="A season needs at least two matches played before it can be drawn as a line." />`;
  const x = Array.from({ length: rounds }, (_, i) => i + 1);
  // A season still being played is shorter than the rest: end it with a dot instead of a label parked at the far right.
  const short_ = (s) => s.played < rounds;
  const line = (get) => ok.map((s) => ({ key: String(s.season), label: s.label, values: get(s), color: colorOf(s.season), width: s.season === viewing ? 3 : 1.75, endLabel: short(s.label), noEnd: short_(s) }));
  const dots = (get) => ok.filter(short_).flatMap((s) => { const v = get(s); const i = v.length - 1; return i >= 0 && v[i] != null ? [{ x: i + 1, y: v[i], color: colorOf(s.season), r: 4 }] : []; });
  const maxPts = Math.max(1, ...ok.flatMap((s) => s.points));
  const n = d.n_teams_max;
  const lowest = fit === "fit" ? Math.min(n, Math.max(4, ...ok.flatMap((s) => s.rank.filter((v) => v != null)))) : n;
  const ticks = fit === "fit" ? rankTicks(lowest) : [...new Set([1, 5, 10, 15, n].filter((v) => v <= n))];
  const week = (i) => `Matchweek ${x[i]}`;
  // matchweeks are whole numbers: label each one while there are few, otherwise let the chart pick a step
  const common = { x, height: 300, xLabel: "Matchweek", tooltipTitle: week, xTicks: rounds <= 12 ? x : undefined };
  return html`<div class="stack" style=${{ "--gap": "16px" }}>
    <${Card} title="Points by matchweek" sub="Running total of league points. Steeper means a faster start.">
      <${LineChart} ...${common} series=${line((s) => s.points)} markers=${dots((s) => s.points)} yDomain=${[0, Math.ceil(maxPts / 10) * 10]} yFormat=${(v) => String(Math.round(v))} tooltipFormat=${(v) => `${Math.round(v)} pts`} label="Points by matchweek for each season" />
    </${Card}>
    <${Card} title="League position by matchweek" sub="Table position after each round. Higher on the chart is better: 1st is at the top."
      actions=${html`<${Segmented} small label="Position scale" options=${[{ value: "fit", label: "Zoom to fit", title: "Only as far down as the lines reach" }, { value: "full", label: "Whole table", title: "1st to last place" }]} value=${fit} onChange=${setFit} />`}>
      <${LineChart} ...${common} series=${line((s) => s.rank)} markers=${dots((s) => s.rank)} invertY yDomain=${[0.6, lowest + 0.4]} yTicks=${ticks} yFormat=${ordinal} tooltipFormat=${(v) => ordinal(v)} label="League position by matchweek for each season" />
    </${Card}>
    <${Card} title="Chances trend by matchweek" sub=${xg === "xgd_cum" ? "Chances created minus chances allowed (xG difference), added up over the season." : "Chances created minus chances allowed, averaged over the last five matches."}
      actions=${html`<${Segmented} small label="xG measure" options=${XG_VIEWS} value=${xg} onChange=${setXg} />`}>
      <${LineChart} ...${common} series=${line((s) => s[xg])} markers=${dots((s) => s[xg])} zeroLine yFormat=${(v) => signed(v, xg === "xgd_cum" ? 0 : 1)} tooltipFormat=${(v) => signed(v, 2)} label="Expected goal difference by matchweek for each season" />
    </${Card}>
  </div>`;
}

function HistoryView({ d, viewing, colorOf }) {
  const missing = d.seasons.filter((s) => !s.available);
  return html`<div class="stack" style=${{ "--gap": "16px" }}>
    ${missing.length ? html`<${Notice} icon="info">${d.team} ${missing.every((s) => s.missing) ? "were not in" : "could not be loaded for"} ${missing.map((s) => s.label).join(", ")}. ${plural(missing.length, "season")} left off the charts. Pick other seasons above to compare more.</${Notice}>` : null}
    ${d.meta.stale ? html`<${Notice} tone="warn" icon="alert">Some seasons are showing saved data that could not be refreshed just now.</${Notice}>` : null}
    <${SeasonTable} seasons=${d.seasons} viewing=${viewing} colorOf=${colorOf} league=${d.scope.league_name} />
    <${Charts} d=${d} viewing=${viewing} colorOf=${colorOf} />
  </div>`;
}

export default function History({ team, league, viewing }) {
  const { meta } = useMeta();
  const { query } = useLocation();
  const options = (meta?.seasons || []).map((s) => ({ season: s.season, label: s.label }));
  const fallback = options.filter((o) => o.season <= viewing).slice(0, DEFAULT_SEASONS).map((o) => o.season);
  const chosen = csv(query.seasons).filter((s) => options.some((o) => o.season === s)).slice(0, MAX_SEASONS);
  const selected = [...new Set(query.seasons === "none" ? [] : chosen.length ? chosen : fallback)].sort((a, b) => b - a);
  const colorOf = (() => { const slotOf = useStableSlots(selected.map(String)); return (s) => SERIES_COLORS[slotOf(String(s))]; })();
  const onChange = (list) => setQuery({ seasons: list.length ? [...list].sort((a, b) => b - a).join(",") : "none" });
  const q = useApi("/api/team/history", { team, league, seasons: selected }, { enabled: selected.length > 0 });

  return html`<div class="stack" style=${{ "--gap": "16px" }}>
    <${SeasonPicker} options=${options} selected=${selected} viewing=${viewing} colorOf=${colorOf} onChange=${onChange} />
    ${selected.length
      ? html`<${Async} q=${q}>${(d) => html`<${HistoryView} d=${d} viewing=${viewing} colorOf=${colorOf} />`}</${Async}>`
      : html`<${EmptyState} icon="calendar" title="Pick a season" text="Choose at least one season above to see how it unfolded." />`}
  </div>`;
}

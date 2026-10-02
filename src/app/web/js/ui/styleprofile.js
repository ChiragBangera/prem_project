// A team's style profile: where it sits among the teams of its own league and season on a chosen set of measures, grouped by what they describe.
// Bars show the percentile (higher is better, whichever way the metric reads). Measures about style rather than quality (possession, direct play ...)
// are drawn as a position on a track, because "more" is not "better" there.
import { html, useMemo } from "../lib/html.js";
import { Tip, tooltip } from "../lib/tooltip.js";
import { seqColor } from "../charts/core.js";
import { blank, fmtMetric, fmtPct } from "../lib/metricfmt.js";
import { quantile } from "../lib/filters.js";
import { ordinal } from "../lib/format.js";

export const STYLE_GROUPS = [
  { title: "Results", keys: ["ppg", "xpts_pg", "gf_pg", "ga_pg", "pts_xpts"] },
  { title: "Creating chances", keys: ["xg_pg", "npxg_pg", "xg_shot", "big_pg", "deep_pg"] },
  { title: "Preventing chances", keys: ["xga_pg", "shots_against_pg", "xg_shot_against", "big_against_pg"] },
  { title: "Possession and passing", keys: ["poss", "pass_acc", "fwd_pct", "long_pct", "prog_pg", "tilt"] },
  { title: "Pressing and defending", keys: ["ppda", "def_height", "recatt_pg", "tklint_pg"] },
  { title: "Set pieces and discipline", keys: ["spxg_pg", "spxga_pg", "corners_pg", "fouls_pg"] },
];

function Row({ k, row, ctx, peers }) {
  const i = ctx.idx[k];
  const def = ctx.metrics[k];
  const v = row.v[i];
  const p = row.p[i];
  const neutral = def.hib === null;
  const sorted = peers.map((r) => r.v[i]).filter((x) => !blank(x)).sort((a, b) => a - b);
  const median = sorted.length ? quantile(sorted, 0.5) : null;
  const better = (a, b) => (def.hib === false ? a < b : a > b);
  const rank = neutral || !sorted.length ? null : sorted.filter((x) => better(x, v)).length + 1;
  const tip = (e) => tooltip.move(e, html`<${Tip} title=${def.label} sub=${def.what} rows=${[
    { label: "This team", value: fmtMetric(def, v) },
    { label: "League median", value: fmtMetric(def, median) },
    ...(rank ? [{ label: "Rank in the league", value: `${ordinal(rank)} of ${sorted.length}` }] : []),
    ...(!neutral && p != null ? [{ label: "Percentile", value: fmtPct(p) }] : []),
    ...(neutral ? [{ label: "Reading", value: "style, not quality" }] : []),
  ]} />`);
  return html`<div class="sp-row" onMouseMove=${tip} onMouseLeave=${tooltip.hide}>
    <span class="sp-label">${def.short}<span class="sp-name">${def.label}</span></span>
    <span class=${"sp-track" + (neutral ? " style" : "")} aria-hidden="true">
      ${neutral
        ? html`<i class="sp-dot" style=${{ left: `${p ?? 50}%` }}></i>`
        : html`<i class="sp-fill" style=${{ width: `${Math.max(1.5, p ?? 0)}%`, background: seqColor(0.3 + 0.62 * ((p ?? 0) / 100)) }}></i>`}
      <i class="sp-median"></i>
    </span>
    <span class="sp-value num">${fmtMetric(def, v)}</span>
    <span class="sp-pct num" title=${neutral ? "Position among the league's teams" : "Percentile"}>${p == null ? "–" : neutral ? `${fmtPct(p)}` : fmtPct(p)}</span>
  </div>`;
}

/** rows: every team row of the dataset (so ranks and medians can be worked out); row: this team's. */
export function StyleProfile({ row, rows, ctx, groups = STYLE_GROUPS }) {
  const peers = useMemo(() => rows.filter((r) => r.league === row.league && r.season === row.season), [rows, row]);
  const shown = groups.map((g) => ({ ...g, keys: g.keys.filter((k) => ctx.idx[k] !== undefined && !blank(row.v[ctx.idx[k]])) })).filter((g) => g.keys.length);
  if (!shown.length) return null;
  return html`<div class="sprofile">
    ${shown.map((g) => html`<section key=${g.title} class="sp-group">
      <h3 class="sp-title">${g.title}</h3>
      ${g.keys.map((k) => html`<${Row} key=${k} k=${k} row=${row} ctx=${ctx} peers=${peers} />`)}
    </section>`)}
  </div>`;
}

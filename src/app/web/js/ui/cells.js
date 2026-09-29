// Table cells shared by the scouting table and the shortlist.
import { html } from "../lib/html.js";
import { cls } from "../lib/format.js";
import { tooltip, Tip } from "../lib/tooltip.js";
import { seqColor } from "../charts/core.js";
import { playerHref, metricValue, POS_LABEL } from "./common.js";

const tip = (e, def, row, value, p) => tooltip.move(e, html`<${Tip} title=${def.label} sub=${`${row.name} · ${POS_LABEL[row.group]}s with enough minutes`} rows=${[
  { label: "Per-90 value", value: metricValue(def, value) },
  { label: "Percentile among peers", value: Math.round(p) },
  { label: "Rank", value: row.rank?.[def.key] ? `${row.rank[def.key]} of ${row.pool_n}` : "–" },
]} />`);
const hideTip = () => tooltip.hide();

/** A rate with its percentile drawn as a thin bar underneath. Faded when the sample is small. */
export function PctCell({ row, metric, def }) {
  const value = row[metric];
  const p = row.pct?.[metric];
  return html`<span class=${cls("pctcell", !row.in_pool && "dim")} onMouseMove=${(e) => p != null && tip(e, def, row, value, p)} onMouseLeave=${hideTip}>
    <span class="v">${metricValue(def, value)}</span>
    <span class="b" aria-hidden="true"><i style=${{ width: (p ?? 0) + "%", background: seqColor(0.3 + 0.62 * ((p ?? 0) / 100)) }}></i></span>
  </span>`;
}

export function ScoreCell({ row }) {
  if (row.output == null) return html`<span class="muted">–</span>`;
  return html`<span class=${cls("scorecell", !row.in_pool && "dim")}><b class="num">${Math.round(row.output)}</b><span class="bar-inline" aria-hidden="true"><i style=${{ width: row.output + "%" }}></i></span></span>`;
}

export function PlayerCell({ row, season }) {
  const sub = [row.team, POS_LABEL[row.group], row.age != null ? `${row.age}` : null].filter(Boolean).join(" · ");
  return html`<a class="cell-player" href=${playerHref(row.id, { league: row.league, season: row.seasons?.length === 1 ? row.seasons[0] : season })}>
    <span class="name">${row.name}${!row.in_pool ? html` <span class="badge outline" title="Fewer minutes than the role pool uses for rankings">Small sample</span>` : null}</span>
    <span class="sub">${sub}</span>
  </a>`;
}

export function TagCell({ row }) {
  const [first, ...rest] = row.tags || [];
  if (!first) return html`<span class="muted">–</span>`;
  return html`<span class="tagrow"><span class="tag" title=${first.why}>${first.label}</span>${rest.length ? html`<span class="muted xsmall" title=${rest.map((t) => t.label).join(", ")}>+${rest.length}</span>` : null}</span>`;
}

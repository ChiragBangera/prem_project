// Table cells shared by Scout, Teams, the team page and the shortlist.
import { html } from "../lib/html.js";
import { cls, nf } from "../lib/format.js";
import { tooltip, Tip } from "../lib/tooltip.js";
import { seqColor } from "../charts/core.js";
import { blank, fmtMetric, fmtPct } from "../lib/metricfmt.js";
import { Crest, Star, playerHref, teamHref, POS_LABEL } from "./common.js";

const hideTip = () => tooltip.hide();

/** Is the sample behind this row's number thin? Event metrics have their own minutes. */
export function thinSample(row, def) {
  if (row.ev_in_pool === undefined && row.in_pool === undefined) return false;
  return def?.needs === "events" ? row.ev_in_pool === false : row.in_pool === false;
}

/** A value with its percentile drawn as a thin bar beneath it. Faded when the sample is small, plain when the metric is about style rather than quality. */
export function MetricCell({ row, ctx, k }) {
  const i = ctx.idx[k];
  const def = ctx.metrics[k];
  const v = row.v[i];
  if (blank(v)) return html`<span class="muted">–</span>`;
  const p = row.p[i];
  const neutral = def?.hib === null;
  const thin = thinSample(row, def);
  const role = ctx.roles?.plural?.[row.group];
  const poolN = ctx.groupSizes?.[row.group];
  const move = (e) => tooltip.move(e, html`<${Tip} title=${def?.label || k} sub=${`${row.name ?? row.team}${role ? ` · ${role} pool` : ""}`} rows=${[
    { label: "Value", value: fmtMetric(def, v) },
    ...(p != null ? [{ label: row.group ? `Percentile among ${role?.toLowerCase() || "peers"}${poolN ? ` (${poolN})` : ""}` : "Percentile in the league", value: fmtPct(p) }] : []),
    ...(neutral ? [{ label: "Reading", value: "style, not quality" }] : []),
    ...(thin ? [{ label: "Sample", value: "small: read with care" }] : []),
  ]} />`);
  return html`<span class=${cls("mcell", thin && "dim")} onMouseMove=${move} onMouseLeave=${hideTip}>
    <span class=${cls("v", def?.signed && (v > 0 ? "pos" : v < 0 ? "neg" : ""))}>${fmtMetric(def, v)}</span>
    ${p != null ? html`<span class=${cls("b", neutral && "neutral")} aria-hidden="true"><i style=${{ width: Math.max(2, p) + "%", background: neutral ? "var(--ink-3)" : seqColor(0.3 + 0.62 * (p / 100)) }}></i></span>` : html`<span class="b" aria-hidden="true"></span>`}
  </span>`;
}

/** The player's name, club, position and age, with the compare tick and the shortlist star in front of it. */
export function PlayerCell({ row, season, picked, onPick, ctx }) {
  const unsure = row.age != null && row.dob_basis === "name";
  const age = row.age == null ? null : unsure
    ? html`<span class="age-unsure" title="Birthdate found on Wikidata by name only. The club could not be confirmed, so this could be a namesake.">${row.age}?</span>`
    : html`<span title=${row.dob ? `Born ${row.dob}` : undefined}>${row.age}</span>`;
  const position = ctx?.positions?.labels?.[row.pos2] || POS_LABEL[row.group];
  const sub = [row.team, position].filter(Boolean).join(" · ");
  return html`<div class="pcell">
    ${onPick ? html`<input type="checkbox" class="pick" aria-label=${`Select ${row.name} to compare`} checked=${picked} onClick=${(e) => e.stopPropagation()} onChange=${(e) => onPick(row.id, e.target.checked)} />` : null}
    <${Star} player=${row} />
    <a class="cell-player" href=${playerHref(row.id, { league: row.league, season: row.seasons?.length === 1 ? row.seasons[0] : season })}>
      <span class="name">${row.name}${row.in_pool === false ? html` <span class="badge outline" title="Fewer minutes than the role pool uses for rankings">Small sample</span>` : null}</span>
      <span class="sub">${sub}${age ? html` · ${age}` : null}</span>
    </a>
  </div>`;
}

/** The team's crest and name. `rank` shows the league position in front when given. */
export function TeamCell({ row, rank, sub }) {
  return html`<div class="pcell">
    ${rank != null ? html`<span class="rank">${rank}</span>` : null}
    <a class="cell-team" href=${teamHref(row.team)}><${Crest} team=${row.team} short=${row.short} size=${24} /><span class="stack" style=${{ "--gap": 0 }}><span class="name">${row.team}</span>${sub ? html`<span class="xsmall muted">${sub}</span>` : null}</span></a>
  </div>`;
}

/** Profile tags. Clicking one filters the list to players with it (when `onTag` is given). */
export function TagCell({ row, onTag, active = [], max = 2 }) {
  const tags = row.tags || [];
  if (!tags.length) return html`<span class="muted">–</span>`;
  const shown = tags.slice(0, max), rest = tags.slice(max);
  return html`<span class="tagrow">${shown.map((t) => (onTag
    ? html`<button type="button" key=${t.key} class=${cls("tag", "tag-btn", active.includes(t.key) && "on")} title=${`${t.why}. Click to filter by this profile.`} onClick=${(e) => { e.stopPropagation(); onTag(t.key); }}>${t.label}</button>`
    : html`<span class="tag" key=${t.key} title=${t.why}>${t.label}</span>`))}${rest.length ? html`<span class="muted xsmall" title=${rest.map((t) => t.label).join(", ")}>+${rest.length}</span>` : null}</span>`;
}

export function ScoreCell({ row, k = "output" }) {
  const v = k === "output" ? row.output : row[k];
  if (blank(v)) return html`<span class="muted">–</span>`;
  return html`<span class=${cls("scorecell", row.in_pool === false && "dim")}><b class="num">${Math.round(v)}</b><span class="bar-inline" aria-hidden="true"><i style=${{ width: v + "%" }}></i></span></span>`;
}

/** A form guide: the last results as W/D/L squares. */
export function FormCell({ items = [] }) {
  return html`<span class="form" role="img" aria-label=${"Last results: " + items.join(" ").toUpperCase()}>${items.map((r, i) => html`<i class=${r} key=${i}>${r.toUpperCase()}</i>`)}</span>`;
}

export const num = (v, d = 1) => (blank(v) ? "–" : nf(v, d));

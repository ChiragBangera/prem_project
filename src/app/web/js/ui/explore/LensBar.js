// Lenses: quick filters with the reasoning on show. A lens adds its rules to the filters and does nothing else: your roles, columns and
// sorting stay as they are. Hover (or tap) a lens to read what it filters on; two buttons then offer its metrics as columns or a sort.
import { html, useMemo, useState } from "../../lib/html.js";
import { Icon } from "../../lib/icons.js";
import { cls } from "../../lib/format.js";
import { describeRule, lensCount } from "../../lib/filters.js";
import { fmtMetric } from "../../lib/metricfmt.js";
import { Button } from "../common.js";
import { useMedia } from "../../lib/media.js";

const NEEDS = {
  base: "Uses season totals that exist for every player and team.",
  shots: "Uses the shot data in Understat's match pages, which the app downloads in the background.",
  events: "Uses event data (passes, duels, tackles, carries).",
};

function LensPanel({ lens, ctx, count, total, active, onToggle, onShowColumns, onSortBy, onClose, eventCover, noun }) {
  const first = lens.sort;
  return html`<aside class="lens-panel" aria-live="polite">
    <div class="row between wrap" style=${{ gap: "8px" }}>
      <div class="row" style=${{ gap: "10px" }}><b class="lens-title">${lens.label}</b><span class=${cls("badge", active ? "accent" : "outline")}>${active ? "On" : "Off"}</span></div>
      <div class="row" style=${{ gap: "8px" }}><span class="small muted"><b class="num">${count.toLocaleString("en-GB")}</b> of ${total.toLocaleString("en-GB")} ${noun} match${active ? "" : " if you switch it on"}</span>
        <button type="button" class="x-btn" aria-label="Close the explanation" onClick=${onClose}><${Icon} name="x" size="sm" /></button></div>
    </div>
    <p class="small lens-explain">${lens.explain}</p>
    <div class="lens-cols">
      <div class="stack" style=${{ "--gap": "4px" }}>
        <span class="eyebrow">It keeps ${noun} where</span>
        <ul class="plain lens-rules">${lens.rules.map((r, i) => html`<li key=${i}>${describeRule(r, ctx, fmtMetric, true)}</li>`)}
          ${lens.roles?.length ? html`<li>${lens.roles.map((r) => ctx.roles.plural[r].toLowerCase()).join(" and ")} only</li>` : null}</ul>
      </div>
      <div class="stack" style=${{ "--gap": "4px" }}>
        <span class="eyebrow">Metrics it looks at</span>
        <div class="chipgroup">${lens.show.map((k) => html`<span key=${k} class="tag" title=${ctx.metrics[k]?.what}>${ctx.metrics[k]?.short || k}</span>`)}</div>
      </div>
    </div>
    <p class="xsmall muted">${NEEDS[lens.needs] || ""}${lens.needs === "events" ? ` ${eventCover}` : ""} A lens only adds these rules: your other filters, columns and sorting stay as they are.</p>
    <div class="row wrap" style=${{ gap: "8px" }}>
      <${Button} size="sm" kind=${active ? "" : "primary"} onClick=${onToggle}>${active ? "Switch off" : "Switch on"}</${Button}>
      <${Button} size="sm" icon="grid" onClick=${() => onShowColumns(lens.show)} title="Replace the table columns with the metrics this lens looks at">Show these metrics as columns</${Button}>
      ${first ? html`<${Button} size="sm" icon="trendDown" onClick=${() => onSortBy(first)} title="Sort the list by this lens's main metric">Sort by ${ctx.metrics[first]?.short || first}</${Button}>` : null}
    </div>
  </aside>`;
}

export function LensBar({ model, allRows, noun, onShowColumns, onSortBy }) {
  const { ctx, filters, setFilters } = model;
  // The panel follows the lens last pointed at, and stays put when the pointer leaves (it would otherwise jump the page up and down).
  const [focus, setFocus] = useState(null);
  const [more, setMore] = useState(false);
  const narrow = useMedia("(max-width: 720px)");
  const key = JSON.stringify(filters);
  const counts = useMemo(() => Object.fromEntries(ctx.lensList.map((l) => [l.key, lensCount(allRows, filters, ctx, l.key)])), [allRows, key, ctx]);
  const lens = focus ? ctx.lenses[focus] : null;
  const on = (k) => filters.lenses.includes(k);
  const toggle = (k) => {
    setFilters((s) => ({ ...s, lenses: on(k) ? s.lenses.filter((x) => x !== k) : [...s.lenses, k] }));
    setFocus(k);
  };
  const eventCover = ctx.coverage.event_players != null
    ? `Event data is stored for ${ctx.coverage.event_players} of ${allRows.length} ${noun} here${ctx.coverage.event_players === 0 ? ", so this lens finds nobody yet" : ""}.`
    : ctx.coverage.event_teams != null ? `Event data is stored for ${ctx.coverage.event_teams} of ${allRows.length} ${noun} here${ctx.coverage.event_teams === 0 ? ", so this lens finds nobody yet" : ""}.` : "";
  if (!ctx.lensList.length) return null;
  return html`<div class="lensbar">
    <div class="fb-row lens-row" role="group" aria-label="Lenses: quick filters">
      <span class="fb-label" title="A lens is a saved question. It only adds filters; it never changes your columns or sorting.">Lenses</span>
      ${(narrow && !more ? ctx.lensList.filter((l, i) => i < 6 || on(l.key)) : ctx.lensList).map((l) => {
        const dim = counts[l.key] === 0 && !on(l.key);
        return html`<button type="button" key=${l.key} class=${cls("chip", "lens", dim && "dim")} aria-pressed=${String(on(l.key))}
          onClick=${() => toggle(l.key)} onMouseEnter=${() => setFocus(l.key)} onFocus=${() => setFocus(l.key)}
          title=${l.blurb}>${l.label}<span class="muted num">${counts[l.key].toLocaleString("en-GB")}</span></button>`;
      })}
      ${narrow ? html`<button type="button" class="chip" onClick=${() => setMore(!more)}>${more ? "Fewer lenses" : `All ${ctx.lensList.length} lenses`}</button>` : null}
      <span class="xsmall muted lens-hint"><${Icon} name="info" size="sm" /> ${narrow ? "Tap a lens to read what it does" : "Point at a lens to read what it does"}</span>
    </div>
    ${lens ? html`<${LensPanel} lens=${lens} ctx=${ctx} count=${counts[lens.key]} total=${allRows.length} active=${on(lens.key)} noun=${noun} eventCover=${eventCover}
      onToggle=${() => toggle(lens.key)} onShowColumns=${onShowColumns} onSortBy=${onSortBy} onClose=${() => setFocus(null)} />` : null}
  </div>`;
}

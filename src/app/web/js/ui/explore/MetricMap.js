// The map: every row in the list as a dot, placed by any two metrics. Honours the same filters, sorting and Top-N as the table.
import { html, useMemo, useState } from "../../lib/html.js";
import { Tip } from "../../lib/tooltip.js";
import { Legend } from "../../charts/core.js";
import { Scatter } from "../../charts/scatter.js";
import { SERIES_COLORS } from "../../charts/lines.js";
import { shortlistStore, useStore } from "../../lib/store.js";
import { blank, fmtMetric, fmtPct } from "../../lib/metricfmt.js";
import { quantile } from "../../lib/filters.js";
import { niceExtent } from "../../charts/core.js";
import { Segmented, Switch } from "../common.js";
import { MetricSelect } from "./MetricSelect.js";

const ROLE_COLOR = { ATT: "var(--c2)", MID: "var(--c1)", DEF: "var(--c3)", GK: "var(--c4)" };

/**
 * The range a map axis covers. A rate on a few minutes can be absurdly large, and one such dot would squash everyone else into a corner.
 * So the axis spans everyone with enough minutes (all of them, extremes included: the best players are the point of the map). Anyone beyond
 * it is a small-sample dot, drawn on the edge with a dashed outline. When too few players have enough minutes to set a range, the middle 96%
 * of everyone is used instead.
 */
function axisDomain(regularValues, allValues) {
  const base = regularValues.length >= 12 ? regularValues : allValues;
  const sorted = [...base].sort((a, b) => a - b);
  if (sorted.length < 5) return null;
  const trim = regularValues.length >= 12 ? 0 : 0.02;
  const lo = quantile(sorted, trim), hi = quantile(sorted, 1 - trim);
  if (!(hi > lo)) return null;
  const pad = (hi - lo) * 0.06;
  const floor = sorted[0] >= 0 ? 0 : -Infinity;
  const [a, b] = niceExtent(Math.max(floor, lo - pad), hi + pad);
  return [Math.max(floor, a), b];
}

/** "Better" runs up and right when the metric says so; for a metric where fewer is better the axis is flipped (and labelled). */
function axisFor(def, flip) {
  const invert = flip && def?.hib === false;
  const cue = def?.hib === false ? (flip ? "fewer is better →" : "") : def?.hib === true ? "more is better →" : "";
  return { invert, label: `${def?.label || ""}${cue ? ` (${cue})` : ""}` };
}

export function MetricMap({ model, level, scope, onOpen, noun, labelCount = 12 }) {
  const { ctx, view, shown, setView } = model;
  const marked = useStore(shortlistStore, (s) => new Set(s.items.map((i) => Number(i.id))));
  const [flip, setFlip] = useState(true);
  const [everyone, setEveryone] = useState(false);
  const [full, setFull] = useState(false);
  const xKey = view.mx, yKey = view.my;
  const xd = ctx.metrics[xKey], yd = ctx.metrics[yKey];
  const xi = ctx.idx[xKey], yi = ctx.idx[yKey];
  const mi = ctx.idx.minutes;

  const pts = useMemo(() => shown.filter((r) => !blank(r.v[xi]) && !blank(r.v[yi])), [shown, xi, yi]);
  const missing = shown.length - pts.length;
  const medians = useMemo(() => {
    const m = (i) => quantile(pts.map((r) => r.v[i]).sort((a, b) => a - b), 0.5);
    return pts.length >= 5 ? { x: m(xi), y: m(yi) } : { x: null, y: null };
  }, [pts, xi, yi]);

  const colorBy = level === "player" ? view.mc : view.mc === "role" ? "league" : view.mc;
  const leagues = useMemo(() => [...new Set(shown.map((r) => r.league))], [shown]);
  const colorOf = (r) => (colorBy === "role" ? ROLE_COLOR[r.group] : colorBy === "league" ? SERIES_COLORS[leagues.indexOf(r.league) % SERIES_COLORS.length] : "var(--c1)");
  const sizeBy = level === "player" && view.ms === "minutes" && mi !== undefined;
  const labelled = new Set(everyone ? pts.map((r) => r.id ?? r.key) : pts.slice(0, labelCount).map((r) => r.id ?? r.key));
  const idOf = (r) => r.id ?? r.key;
  const nameOf = (r) => (level === "player" ? r.name.split(" ").slice(-1)[0] : r.short || r.team);

  // the axes follow the regulars: players on very few minutes can be extreme, and are drawn on the edge (outlined) rather than stretching the map
  const regulars = useMemo(() => pts.filter((x) => x.in_pool !== false), [pts]);
  const xDom = useMemo(() => (full ? null : axisDomain(regulars.map((r) => r.v[xi]), pts.map((r) => r.v[xi]))), [full, regulars, pts, xi]);
  const yDom = useMemo(() => (full ? null : axisDomain(regulars.map((r) => r.v[yi]), pts.map((r) => r.v[yi]))), [full, regulars, pts, yi]);
  const clampTo = (v, dom) => (dom ? Math.min(dom[1], Math.max(dom[0], v)) : v);
  const beyond = pts.filter((r) => (xDom && (r.v[xi] < xDom[0] || r.v[xi] > xDom[1])) || (yDom && (r.v[yi] < yDom[0] || r.v[yi] > yDom[1]))).length;
  const points = pts.map((r, rank) => ({
    clamped: Boolean((xDom && (r.v[xi] < xDom[0] || r.v[xi] > xDom[1])) || (yDom && (r.v[yi] < yDom[0] || r.v[yi] > yDom[1]))),
    id: idOf(r), x: clampTo(r.v[xi], xDom), y: clampTo(r.v[yi], yDom), label: nameOf(r), showLabel: labelled.has(idOf(r)) || marked.has(Number(r.id)), priority: (marked.has(Number(r.id)) ? 1000 : 0) + (pts.length - rank),
    r: sizeBy ? 3 + Math.sqrt(Math.max(0, r.v[mi] || 0) / 2700) * 3.5 : level === "team" ? 6 : 4.5, color: colorOf(r), ring: marked.has(Number(r.id)), dim: level === "player" && r.in_pool === false, highlight: false, data: r,
  }));
  const ax = axisFor(xd, flip), ay = axisFor(yd, flip);
  const f = (def, v) => fmtMetric(def, v);
  const legendItems = colorBy === "role"
    ? ["ATT", "MID", "DEF", "GK"].filter((g) => pts.some((r) => r.group === g)).map((g) => ({ key: g, label: ctx.roles.plural[g], color: ROLE_COLOR[g], shape: "dot" }))
    : colorBy === "league" && leagues.length > 1 ? leagues.map((l, i) => ({ key: l, label: l, color: SERIES_COLORS[i % SERIES_COLORS.length], shape: "dot" })) : [];

  return html`<div class="stack metric-map" style=${{ "--gap": "12px" }}>
    <div class="row wrap map-controls">
      <label class="rb-field"><span class="rb-label">Across</span><${MetricSelect} ctx=${ctx} compact value=${xKey} label="Horizontal metric" onChange=${(k) => setView({ mx: k })} /></label>
      <button type="button" class="btn sm icon-only" title="Swap the two axes" aria-label="Swap the axes" onClick=${() => setView({ mx: yKey, my: xKey })}>⇄</button>
      <label class="rb-field"><span class="rb-label">Up</span><${MetricSelect} ctx=${ctx} compact value=${yKey} label="Vertical metric" onChange=${(k) => setView({ my: k })} /></label>
      ${level === "player" ? html`<${Segmented} small label="Colour dots by" value=${colorBy} onChange=${(v) => setView({ mc: v })} options=${[{ value: "role", label: "Role" }, { value: "league", label: "League" }, { value: "none", label: "One colour" }]} />
        <${Segmented} small label="Dot size" value=${view.ms} onChange=${(v) => setView({ ms: v })} options=${[{ value: "minutes", label: "Size: minutes" }, { value: "none", label: "Same size" }]} />`
        : html`<${Segmented} small label="Colour dots by" value=${colorBy} onChange=${(v) => setView({ mc: v })} options=${[{ value: "league", label: "League" }, { value: "none", label: "One colour" }]} />`}
    </div>
    <div class="row wrap map-controls" style=${{ gap: "16px" }}>
      <${Switch} checked=${flip} onChange=${setFlip}>Put “better” up and to the right</${Switch}>
      <${Switch} checked=${everyone} onChange=${setEveryone}>Label every dot${pts.length > 120 ? " (crowded)" : ""}</${Switch}>
      <${Switch} checked=${full} onChange=${setFull}>Show the full range</${Switch}>
      <span class="xsmall muted">${view.top > 0 ? `Showing the top ${shown.length} by the current sort. ` : ""}${missing ? `${missing.toLocaleString("en-GB")} ${noun} have no value for one of these metrics and are not drawn. ` : ""}Dotted lines are the medians of what is drawn.${beyond ? ` ${beyond} dot${beyond === 1 ? " is" : "s are"} beyond the edge (dashed outline): the axis fits everyone with enough minutes, so a few extreme values from players with very few minutes do not squash the rest.` : ""}${level === "player" ? " Ringed: on your shortlist. Faded: small sample." : ""}</span>
    </div>
    ${legendItems.length ? html`<${Legend} items=${legendItems} />` : null}
    ${pts.length ? html`<${Scatter} points=${points} height=${540} xLabel=${ax.label} yLabel=${ay.label} invertX=${ax.invert} invertY=${ay.invert}
        refX=${medians.x} refY=${medians.y} xDomain=${xDom || undefined} yDomain=${yDom || undefined} hoverPad=${16} label=${`${noun} plotted on ${xd?.label} and ${yd?.label}`}
        onSelect=${(p) => onOpen(p.data)}
        renderTip=${(p) => html`<${Tip} title=${p.data.name ?? p.data.team} sub=${level === "player" ? `${p.data.team} · ${ctx.positions.labels[p.data.pos2] || ctx.roles.labels[p.data.group]}` : `${p.data.league} ${p.data.season}/${String(p.data.season + 1).slice(-2)}`} rows=${[
          { label: xd?.label, value: `${f(xd, p.data.v[xi])}${p.data.p[xi] != null ? ` · ${fmtPct(p.data.p[xi])}th pct` : ""}` },
          { label: yd?.label, value: `${f(yd, p.data.v[yi])}${p.data.p[yi] != null ? ` · ${fmtPct(p.data.p[yi])}th pct` : ""}` },
          ...(level === "player" && mi !== undefined ? [{ label: "Minutes", value: Math.round(p.data.v[mi]).toLocaleString("en-GB") }] : []),
        ]} />`} />`
      : html`<div class="well muted">Nothing to draw: no ${noun} in this list have a value for both ${xd?.label} and ${yd?.label}. Pick other metrics, or widen the filters.</div>`}
  </div>`;
}

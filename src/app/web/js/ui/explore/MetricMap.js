// The map: every row in the list as a dot, placed by any two metrics. Honours the same filters, sorting and Top-N as the table.
import { html, useMemo, useState } from "../../lib/html.js";
import { Tip } from "../../lib/tooltip.js";
import { Legend } from "../../charts/core.js";
import { Scatter } from "../../charts/scatter.js";
import { SERIES_COLORS } from "../../charts/lines.js";
import { shortlistStore, useStore } from "../../lib/store.js";
import { blank, fmtMetric, fmtPct } from "../../lib/metricfmt.js";
import { quantile } from "../../lib/filters.js";
import { fitLine, offTheLine } from "../../lib/stats.js";
import { niceExtent } from "../../charts/core.js";
import { Segmented, Switch } from "../common.js";
import { MetricSelect } from "./MetricSelect.js";

const ROLE_COLOR = { ATT: "var(--c2)", MID: "var(--c1)", DEF: "var(--c3)", GK: "var(--c4)" };

/**
 * Ready-made maps, each a question. ``line`` draws the trend and names whoever stands furthest from it, which is how volume is told
 * from what came of it: far below the line at the right of the map is a lot of activity with little to show.
 */
export const MAP_QUESTIONS = {
  player: [
    { key: "chances", label: "Who makes and takes chances?", mx: "xa90", my: "npxg90", say: "Across: chances made for others. Up: chances of his own." },
    { key: "busy", label: "Busy, or productive?", mx: "progact90", my: "progact_shot90", line: true,
      say: "Across: how often he moves the ball well forward. Up: how often that move then came to a shot. Below the line is forward movement that led to less than usual for that volume.",
      low: "Busy, less came of it", high: "More came of it" },
    { key: "runs", label: "Do his runs lead anywhere?", mx: "carryprog90", my: "carryprog_shot_pct", line: true,
      say: "Across: driving runs per 90 (an estimate). Up: the share after which the move came to a shot.", low: "Runs, few shots after", high: "Runs that end in shots" },
    { key: "dribbles", label: "Dribbles with a point?", mx: "takeonswon90", my: "takeon_shot_pct", line: true,
      say: "Across: opponents beaten per 90. Up: the share after which the move came to a shot.", low: "Beats his man, little follows", high: "Beats his man, shot follows" },
    { key: "safe", label: "Safe passer, or a forward one?", mx: "pass_acc", my: "progpass_share",
      say: "Across: pass accuracy. Up: the share of his completed passes that were progressive. High accuracy with a low share is safe passing: sideways and back." },
  ],
  team: [
    { key: "chances", label: "Who creates, who concedes?", mx: "xg_pg", my: "xga_pg", say: "Across: chances made. Up: chances allowed." },
    { key: "territory", label: "Territory, or chances?", mx: "prog_pg", my: "progact_shot_pct", line: true,
      say: "Across: progressive passes per game. Up: the share of progressive actions after which the move came to a shot.", low: "Moves forward, few shots", high: "Progress that ends in shots" },
  ],
};

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
  const questions = (MAP_QUESTIONS[level] || []).filter((q) => ctx.idx[q.mx] !== undefined && ctx.idx[q.my] !== undefined);
  const question = questions.find((q) => q.mx === xKey && q.my === yKey);
  const [lineOn, setLineOn] = useState(null);                 // null: follow the question
  const showLine = lineOn ?? Boolean(question?.line);
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
  const idOf = (r) => r.id ?? r.key;
  // The trend is fitted to the regulars only (a rate on a few minutes would bend it), and one line per role: a defender moves the ball
  // forward far from goal, so measuring him against forwards would only say that he is a defender. Each line spans its own role's dots.
  const lineGroups = useMemo(() => {
    if (!showLine) return [];
    const regular = pts.filter((r) => r.in_pool !== false);
    const groups = level === "player" ? ["ATT", "MID", "DEF", "GK"].map((g) => ({ key: g, rows: regular.filter((r) => r.group === g) })) : [{ key: "all", rows: regular }];
    return groups.map(({ key, rows }) => {
      const xy = rows.map((r) => ({ id: idOf(r), x: r.v[xi], y: r.v[yi] }));
      const fit = fitLine(xy);
      if (!fit) return null;
      const xsSorted = xy.map((p) => p.x).sort((p, q) => p - q);
      return { key, fit, xy, from: xsSorted[0], to: xsSorted[xsSorted.length - 1], mid: quantile(xsSorted, 0.5) };
    }).filter(Boolean);
  }, [showLine, pts, xi, yi, level]);
  const line = lineGroups.length > 0;
  const off = useMemo(() => {
    const all = lineGroups.map((g) => offTheLine(g.xy, g.fit, { count: 6, fromX: g.mid }));
    const pick = (side, dir) => all.flatMap((o) => o[side]).sort((p, q) => dir * (p.gap - q.gap)).slice(0, 6);
    return { below: pick("below", 1), above: pick("above", -1) };
  }, [lineGroups]);
  const offIds = new Set([...off.below, ...off.above].map((p) => p.id));
  // Who is named: the dots that stand furthest from the middle of *this* map (each axis measured in its own spread), among the regulars.
  // The first rows of the table are not it: they follow the table's sort, and mostly sit in the crowd near the origin.
  const standout = useMemo(() => {
    const reg = pts.filter((r) => r.in_pool !== false);
    if (reg.length < 3) return new Map(pts.map((r, i) => [idOf(r), pts.length - i]));
    const spread = (i) => {
      const v = reg.map((r) => r.v[i]).sort((a, b) => a - b);
      return { mid: quantile(v, 0.5), width: (quantile(v, 0.9) - quantile(v, 0.1)) || (v[v.length - 1] - v[0]) || 1 };
    };
    const sx = spread(xi), sy = spread(yi);
    return new Map(reg.map((r) => [idOf(r), Math.hypot((r.v[xi] - sx.mid) / sx.width, (r.v[yi] - sy.mid) / sy.width)]));
  }, [pts, xi, yi]);
  const named = useMemo(() => [...standout].sort((a, b) => b[1] - a[1]).slice(0, labelCount).map(([id]) => id), [standout, labelCount]);
  const labelled = new Set(everyone ? pts.map(idOf) : line ? offIds : named);
  const byId = new Map(pts.map((r) => [idOf(r), r]));
  const fullName = (r) => (level === "player" ? r.name : r.short || r.team);
  const nameOf = (r) => (level === "player" ? r.name.split(" ").slice(-1)[0] : r.short || r.team);

  // the axes follow the regulars: players on very few minutes can be extreme, and are drawn on the edge (outlined) rather than stretching the map
  const regulars = useMemo(() => pts.filter((x) => x.in_pool !== false), [pts]);
  const xDom = useMemo(() => (full ? null : axisDomain(regulars.map((r) => r.v[xi]), pts.map((r) => r.v[xi]))), [full, regulars, pts, xi]);
  const yDom = useMemo(() => (full ? null : axisDomain(regulars.map((r) => r.v[yi]), pts.map((r) => r.v[yi]))), [full, regulars, pts, yi]);
  const clampTo = (v, dom) => (dom ? Math.min(dom[1], Math.max(dom[0], v)) : v);
  const outside = (r) => Boolean((xDom && (r.v[xi] < xDom[0] || r.v[xi] > xDom[1])) || (yDom && (r.v[yi] < yDom[0] || r.v[yi] > yDom[1])));
  const beyond = pts.filter(outside).length;
  // A dot beyond the edge is not drawn: pinned to the border they piled up there, each at a place that is not its value. The note says
  // how many, and "Show the full range" brings them back at their true positions. One on the shortlist is kept (pinned, dashed).
  const points = pts.filter((r) => !outside(r) || marked.has(Number(r.id))).map((r) => ({
    clamped: outside(r),
    id: idOf(r), x: clampTo(r.v[xi], xDom), y: clampTo(r.v[yi], yDom), label: nameOf(r), showLabel: labelled.has(idOf(r)) || marked.has(Number(r.id)), priority: (marked.has(Number(r.id)) ? 1000 : 0) + (standout.get(idOf(r)) ?? 0),
    r: sizeBy ? 3 + Math.sqrt(Math.max(0, r.v[mi] || 0) / 2700) * 3.5 : level === "team" ? 6 : 4.5, color: colorOf(r), ring: marked.has(Number(r.id)), dim: level === "player" && r.in_pool === false, highlight: false, data: r,
  }));
  const ax = axisFor(xd, flip), ay = axisFor(yd, flip);
  const f = (def, v) => fmtMetric(def, v);
  const legendItems = colorBy === "role"
    ? ["ATT", "MID", "DEF", "GK"].filter((g) => pts.some((r) => r.group === g)).map((g) => ({ key: g, label: ctx.roles.plural[g], color: ROLE_COLOR[g], shape: "dot" }))
    : colorBy === "league" && leagues.length > 1 ? leagues.map((l, i) => ({ key: l, label: l, color: SERIES_COLORS[i % SERIES_COLORS.length], shape: "dot" })) : [];

  return html`<div class="stack metric-map" style=${{ "--gap": "12px" }}>
    ${questions.length ? html`<div class="map-questions">
      <span class="rb-label">Start from a question</span>
      <div class="chipgroup">${questions.map((q) => html`<button type="button" key=${q.key} class="chip" aria-pressed=${String(question?.key === q.key)}
        onClick=${() => { setLineOn(null); setView({ mx: q.mx, my: q.my }); }}>${q.label}</button>`)}</div>
      ${question ? html`<p class="small muted map-say">${question.say}</p>` : null}
    </div>` : null}
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
      <${Switch} checked=${showLine} onChange=${setLineOn}>Draw the trend and name who is furthest from it</${Switch}>
      <span class="xsmall muted">${view.top > 0 ? `Showing the top ${shown.length} by the current sort. ` : ""}${missing ? `${missing.toLocaleString("en-GB")} ${noun} have no value for one of these metrics and are not drawn. ` : ""}Dotted lines are the medians of what is drawn.${beyond ? ` ${beyond} ${beyond === 1 ? "more lies" : "more lie"} beyond the edge and ${beyond === 1 ? "is" : "are"} left out: the axis fits everyone with enough minutes, so a few extreme values from very few minutes do not squash the rest. “Show the full range” draws ${beyond === 1 ? "it" : "them"}.` : ""}${everyone ? "" : " Named: the dots furthest from the middle; hover any other for its name."}${level === "player" ? " Ringed: on your shortlist. Faded: small sample." : ""}</span>
    </div>
    ${legendItems.length ? html`<${Legend} items=${legendItems} />` : null}
    ${pts.length ? html`<${Scatter} points=${points} height=${540} xLabel=${ax.label} yLabel=${ay.label} invertX=${ax.invert} invertY=${ay.invert}
        trend=${lineGroups.map((g) => ({ ...g.fit, from: g.from, to: g.to, color: level === "player" && colorBy === "role" ? ROLE_COLOR[g.key] : undefined }))} refX=${medians.x} refY=${medians.y} xDomain=${xDom || undefined} yDomain=${yDom || undefined} hoverPad=${16} label=${`${noun} plotted on ${xd?.label} and ${yd?.label}`}
        onSelect=${(p) => onOpen(p.data)}
        renderTip=${(p) => html`<${Tip} title=${p.data.name ?? p.data.team} sub=${level === "player" ? `${p.data.team} · ${ctx.positions.labels[p.data.pos2] || ctx.roles.labels[p.data.group]}` : `${p.data.league} ${p.data.season}/${String(p.data.season + 1).slice(-2)}`} rows=${[
          { label: xd?.label, value: `${f(xd, p.data.v[xi])}${p.data.p[xi] != null ? ` · ${fmtPct(p.data.p[xi])}th pct` : ""}` },
          { label: yd?.label, value: `${f(yd, p.data.v[yi])}${p.data.p[yi] != null ? ` · ${fmtPct(p.data.p[yi])}th pct` : ""}` },
          ...(level === "player" && mi !== undefined ? [{ label: "Minutes", value: Math.round(p.data.v[mi]).toLocaleString("en-GB") }] : []),
        ]} />`} />`
      : null}
    ${pts.length && showLine ? (line ? html`<div class="map-off">
        ${[["below", question?.low || "Furthest below the line"], ["above", question?.high || "Furthest above the line"]].map(([side, title]) => html`<div key=${side} class=${"map-off-col " + side}>
          <h4>${title}</h4>
          ${off[side].length ? html`<ol>${off[side].map((p) => { const r = byId.get(p.id); return html`<li key=${p.id}>
            <button type="button" class="linklike" onClick=${() => onOpen(r)}>${fullName(r)}</button>
            <span class="muted xsmall">${level === "player" ? `${ctx.roles.labels[r.group] || r.group} · ${r.team} · ` : ""}${f(xd, r.v[xi])} across, ${f(yd, r.v[yi])} up</span></li>`; })}</ol>`
            : html`<p class="small muted">Nobody stands clearly ${side} it.</p>`}
        </div>`)}
        <p class="xsmall muted map-off-note">${level === "player" ? "Each line is one role: the" : "The line is the"} usual ${yd?.label?.toLowerCase()} for a given ${xd?.label?.toLowerCase()}, fitted to ${noun} with enough minutes${level === "player" ? ", and each player is measured against his own role's line" : ""}. Only the busier half ${level === "player" ? "of each role " : ""}is named: a gap at low volume is noise. It describes actions, not worth.</p>
      </div>` : html`<p class="small muted">Too few ${noun} with enough minutes to draw a trend.</p>`) : null}
    ${pts.length ? null
      : html`<div class="well muted">Nothing to draw: no ${noun} in this list have a value for both ${xd?.label} and ${yd?.label}. Pick other metrics, or widen the filters.</div>`}
  </div>`;
}

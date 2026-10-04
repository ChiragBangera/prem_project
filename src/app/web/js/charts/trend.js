// The match-by-match chart: one mark per match, shaded by how strong the opponent was, the season-to-date and recent-form lines over the marks, and,
// behind everything, what is typical for his role. It draws the trend payload and computes no metric.
import { html, useEffect, useRef, useState } from "../lib/html.js";
import { tooltip } from "../lib/tooltip.js";
import { fmtMetric } from "../lib/metricfmt.js";
import { dateShort, isNum } from "../lib/format.js";
import { Frame, linePath, niceExtent, niceTicks, scaleLinear, seqColor, tickFormat } from "./core.js";
import { axisRange, changes, deltaText, isZeroBased, metricBounds, opponentLine, reliability, resultText, strength } from "../lib/trend.js";

/** The narrowest a match is drawn, in pixels: a long season scrolls sideways rather than squeezing the opponents' names together. */
export const SLOT = 22;
/** The value axis is its own column, so it stays put while the matches scroll beneath it. */
export const AXIS = 50;
const MARGIN = { top: 14, right: 48, bottom: 56, left: 6 };

/** The mark's colour: how strong the opponent was (darker is stronger), or home against away. */
export function markColor(m, colorBy) {
  if (colorBy === "venue") return m.home ? "var(--c1)" : "color-mix(in oklab, var(--c1) 42%, var(--surface-3))";
  const s = strength(m.opp_ctx);
  return s == null ? "var(--ink-3)" : seqColor(0.28 + 0.62 * s);
}

/** Colours the legend shows for the three thirds of the table. */
export const tierColor = { top: seqColor(0.9), mid: seqColor(0.6), bottom: seqColor(0.28) };

export const LINE = { season: "var(--ink)", form: "var(--c2)" };

function axisFormat(def, ticks) {
  if (def?.unit === "share") return (v) => `${Math.round(v * 100)}%`;
  return tickFormat(ticks.length > 1 ? ticks[1] - ticks[0] : 1);
}

const lastValue = (xs) => { for (let i = xs.length - 1; i >= 0; i--) if (isNum(xs[i])) return { i, v: xs[i] }; return null; };

/**
 * matches / series: the trend payload (`series` is the one metric drawn). def: its catalog entry. band: { p25, p50, p75 } of his role's season values.
 * show: { season, form, band } toggles. onOpen(match): a click on a match.
 */
export function MatchTrendChart({ matches, series, def, band, colorBy = "opp", show, height = 340, form = 5, onOpen, label }) {
  const n = matches.length;
  const [hover, setHover] = useState(null);
  const geom = useRef(null);
  const zero = isZeroBased(def);
  const moves = changes(series.c, series.m);
  const fmt = (v) => fmtMetric(def, v);

  const lineVals = [...(show.season ? series.c.filter(isNum) : []), ...(show.form ? series.r.filter(isNum) : []), ...(show.band && band ? [band.p25, band.p75] : [])];
  let y0, y1, clipHigh = false, clipLow = false;
  if (zero) {                                       // bars rise from zero, and a few freak matches must not flatten the rest of the season
    const range = axisRange(series.m, { lo: Math.min(0, ...lineVals), hi: Math.max(0, ...lineVals) });
    [y0, y1] = range.lo === 0 ? [0, niceExtent(0, (range.hi || 1) * 1.06)[1]] : niceExtent(range.lo - (range.hi - range.lo) * 0.04, range.hi * 1.06);
    clipHigh = range.clipHigh; clipLow = range.clipLow;
  } else {                                          // shares, ratings and distances: dots on an axis that fits them
    const all = [...series.m.filter(isNum), ...lineVals];
    const lo = all.length ? Math.min(...all) : 0, hi = all.length ? Math.max(...all) : 1;
    const bounds = metricBounds(def);                // padding must not invent values the metric cannot take: a save percentage never reaches 120%
    [y0, y1] = niceExtent(lo - (hi - lo || 1) * 0.1, hi + (hi - lo || 1) * 0.06);
    y0 = Math.max(bounds.lo, y0);
    y1 = Math.min(bounds.hi, y1);
  }

  const ih = height - MARGIN.top - MARGIN.bottom;
  const yScale = scaleLinear([y0, y1], [ih, 0]);
  const ticks = niceTicks(y0, y1, Math.max(3, Math.floor(ih / 52)));
  const tickText = axisFormat(def, ticks);

  const tipFor = (i) => {
    const m = matches[i];
    const v = series.m[i];
    const head = html`<div class="tt-title">${m.home ? "Home v" : "Away at"} ${m.opp}</div><div class="tt-sub">${[`Matchweek ${m.round}`, dateShort(m.date), resultText(m)].filter(Boolean).join(" · ")}</div>`;
    if (!m.page) return html`<div style=${{ maxWidth: "260px" }}>${head}<div class="tt-sub">No match data is stored for this game yet, so it is left out of every line. The Data page shows what is missing.</div></div>`;
    const opp = html`<div class="tt-sub tt-gap">${opponentLine(m.opp_ctx)}</div>`;
    if (!m.played) return html`<div style=${{ maxWidth: "260px" }}>${head}<div class="tt-sub">He did not play.</div>${opp}</div>`;
    const rel = reliability(def, series.n?.[i], m.minutes);
    const row = (k, val, swatch) => html`<div class="tt-row"><span class="k">${swatch ? html`<i class="key" style=${{ background: swatch }}></i>` : null}${k}</span><span class="v">${val}</span></div>`;
    const missing = def.needs === "events" ? "No event data is stored for this match." : "Not available for this match.";
    return html`<div style=${{ maxWidth: "280px" }}>${head}
      ${row(def.short || def.label, isNum(v) ? fmt(v) : "–")}
      ${show.season && isNum(series.c[i]) ? row("Season so far", fmt(series.c[i]), LINE.season) : null}
      ${show.form && isNum(series.r[i]) ? row(`Last ${form} appearances`, fmt(series.r[i]), LINE.form) : null}
      ${isNum(moves[i]) ? row("Moved his season figure", deltaText(def, moves[i])) : null}
      ${row("Minutes", `${m.minutes}${m.started ? ", started" : ", from the bench"}`)}
      ${!isNum(v) ? html`<div class="tt-sub tt-gap">${missing}</div>` : null}
      ${rel.note ? html`<div class="tt-sub tt-gap tt-warn">${rel.note}</div>` : null}
      ${opp}
      ${m.match_id ? html`<div class="tt-sub tt-gap">Click for the match report.</div>` : null}
    </div>`;
  };

  const root = useRef(null), scroll = useRef(null);
  useEffect(() => {                                                 // a long season opens on its latest matches: that is where the form is
    const area = scroll.current;
    if (area && area.scrollWidth > area.clientWidth) area.scrollLeft = area.scrollWidth;
  }, [matches]);
  const showAtSlot = (i) => {                                       // keyboard: the slot scrolls into view and the tooltip hangs off it instead of following the pointer
    const g = geom.current, area = scroll.current;
    if (!g || !area || !root.current) return;
    const x = MARGIN.left + (i + 0.5) * g.step;
    if (x < area.scrollLeft + 40 || x > area.scrollLeft + area.clientWidth - 40) area.scrollLeft = Math.max(0, x - area.clientWidth / 2);
    const box = root.current.getBoundingClientRect();               // after any scrolling: the inner box moves with the content
    tooltip.at(box.left + x, box.top + MARGIN.top + g.ih * 0.35, tipFor(i));
  };
  const onKey = (e) => {
    const move = { ArrowRight: 1, ArrowLeft: -1, Home: -Infinity, End: Infinity }[e.key];
    if (move !== undefined) {
      e.preventDefault();
      const next = Math.max(0, Math.min(n - 1, hover == null ? (move > 0 ? 0 : n - 1) : move === Infinity ? n - 1 : move === -Infinity ? 0 : hover + move));
      setHover(next);
      showAtSlot(next);
    } else if (e.key === "Enter" && hover != null && matches[hover].match_id) onOpen?.(matches[hover]);
    else if (e.key === "Escape") { setHover(null); tooltip.hide(); }
  };

  return html`<div class="trend-chart">
    <div class="trend-axis" style=${{ width: AXIS + "px", height: height + "px" }} aria-hidden="true">
      ${ticks.map((t) => html`<span key=${t} class=${zero && t === 0 ? "zero" : ""} style=${{ top: MARGIN.top + yScale(t) + "px" }}>${tickText(t)}</span>`)}
    </div>
    <div class="trend-scroll" ref=${scroll} tabindex="0" role="group" aria-label=${`${label}. Use the left and right arrow keys to move between matches, Enter to open a match report.`}
        onKeyDown=${onKey} onBlur=${() => { setHover(null); tooltip.hide(); }}>
      <div class="trend-inner" ref=${root} style=${{ minWidth: n * SLOT + MARGIN.left + MARGIN.right + "px" }}>
        <${Frame} height=${height} label=${label} margin=${MARGIN} onLeave=${() => { setHover(null); tooltip.hide(); }}>
        ${({ iw }) => {
          const step = iw / n;
          geom.current = { iw, ih, step };
          const cx = (i) => (i + 0.5) * step;
          const y = yScale;
          const base = zero ? y(0) : ih;
          const bw = Math.min(26, Math.max(4, step * 0.64));
          const idx = matches.map((_, i) => i);
          const season = lastValue(series.c), recent = lastValue(series.r);
          const ends = [show.season && season && { ...season, color: LINE.season, y: y(season.v) }, show.form && recent && { ...recent, color: LINE.form, y: y(recent.v) }].filter(Boolean);
          if (ends.length === 2 && Math.abs(ends[0].y - ends[1].y) < 13) { const upper = ends[0].y <= ends[1].y ? 0 : 1; ends[upper].y -= 7; ends[1 - upper].y += 7; }
          return html`<g>
            ${show.band && band ? html`<g class="role-band" aria-hidden="true">
              <rect x="0" width=${iw} y=${y(band.p75)} height=${Math.max(1, y(band.p25) - y(band.p75))} />
              ${isNum(band.p50) ? html`<line class="ref-line" x1="0" x2=${iw} y1=${y(band.p50)} y2=${y(band.p50)} />` : null}
            </g>` : null}
            ${ticks.map((t) => html`<line key=${t} class=${zero && t === 0 ? "axis-line" : "grid-line"} x1="0" x2=${iw} y1=${y(t)} y2=${y(t)} />`)}
            ${hover != null ? html`<rect class="strip-col" x=${hover * step} y="0" width=${step} height=${ih} />` : null}
            ${matches.map((m, i) => {
              const v = series.m[i];
              const x = cx(i);
              if (!m.page) return html`<circle key=${i} class="mark-nodata" cx=${x} cy=${ih - 5} r="3.5" />`;
              if (!m.played) return html`<line key=${i} class="mark-gone" x1=${x - 5} x2=${x + 5} y1=${ih - 4} y2=${ih - 4} />`;
              if (!isNum(v)) return html`<circle key=${i} class="mark-blank" cx=${x} cy=${ih - 5} r="3.5" />`;
              const rel = reliability(def, series.n?.[i], m.minutes);
              const fill = markColor(m, colorBy);
              if (zero) {
                const high = clipHigh && v > y1, low = clipLow && v < y0;
                const yv = high ? y(y1) : low ? y(y0) : y(v);
                const top = Math.min(yv, base);
                return html`<g key=${i}>
                  <rect class=${"mark" + (hover === i ? " on" : "")} x=${x - bw / 2} y=${top} width=${bw} height=${Math.max(1.5, Math.abs(yv - base))} rx="2" style=${{ fill, opacity: rel.alpha }} />
                  ${high || low ? html`<g class="clip" aria-hidden="true"><path d=${`M${x - bw / 2 - 1},${yv + (high ? 7 : -7)}l${bw + 2},${high ? -5 : 5}`} /><text x=${x} y=${high ? -4 : ih + 12} text-anchor="middle">${fmt(v)}</text></g>` : null}
                </g>`;
              }
              return html`<circle key=${i} class=${"mark dot" + (hover === i ? " on" : "")} cx=${x} cy=${y(v)} r=${Math.min(6, Math.max(3.5, bw / 2.2))} style=${{ fill, opacity: rel.alpha }} />`;
            })}
            ${show.season ? html`<path class="trend-line" d=${linePath(idx, series.c, cx, y)} style=${{ stroke: LINE.season }} />` : null}
            ${show.form ? html`<g>
              <path class="trend-line form" d=${linePath(idx, series.r, cx, y)} style=${{ stroke: LINE.form }} />
              ${matches.map((m, i) => (m.played && isNum(series.r[i]) ? html`<circle key=${i} class="mark-ring" cx=${cx(i)} cy=${y(series.r[i])} r="3" style=${{ fill: LINE.form }} />` : null))}
            </g>` : null}
            ${ends.map((e) => html`<text key=${e.color} class="end-label strong" x=${iw + 6} y=${e.y} dy="0.34em" style=${{ fill: e.color === LINE.season ? "var(--ink)" : "var(--c2)" }}>${fmt(e.v)}</text>`)}
            ${matches.map((m, i) => html`<g key=${"x" + i} class=${"slot-label" + (m.played ? "" : " out")} transform=${`translate(${cx(i)},${ih})`}>
              <text class="opp" y="15" text-anchor="middle">${m.opp_short || ""}</text>
              <text class="ha" y="27" text-anchor="middle">${m.home ? "H" : "A"}</text>
              ${m.result ? html`<circle class=${"res " + m.result} cx="0" cy="38" r="3.4" />` : null}
            </g>`)}
            ${matches.map((m, i) => html`<rect key=${"h" + i} class=${"hit" + (m.match_id ? " go" : "")} x=${i * step} y="0" width=${step} height=${ih + 44}
              onMouseMove=${(e) => { setHover(i); tooltip.move(e, tipFor(i)); }} onClick=${() => m.match_id && onOpen?.(m)} />`)}
          </g>`;
        }}
        </${Frame}>
      </div>
    </div>
  </div>`;
}

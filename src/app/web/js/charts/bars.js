// Bar-style visuals built from HTML/CSS so text stays crisp and layouts reflow.
import { html } from "../lib/html.js";
import { nf, ordinal, signed } from "../lib/format.js";
import { tooltip } from "../lib/tooltip.js";
import { seqColor } from "./core.js";
import { SERIES_COLORS } from "./lines.js";

/**
 * Horizontal bars around a zero line. Positive = above expectation (blue), negative = below (orange).
 * rows: [{ key, label(node), value, note? }]
 */
export function DivergingBars({ rows, format = (v) => signed(v, 1), max, leftLabel = "Below expectation", rightLabel = "Above expectation", tip }) {
  const m = max || Math.max(1e-9, ...rows.map((r) => Math.abs(r.value)));
  return html`<div class="divbars" role="list">
    <div class="divbars-head" aria-hidden="true"><span></span><span class="mid"><span>← ${leftLabel}</span><span>${rightLabel} →</span></span><span></span></div>
    ${rows.map((r) => {
      const w = Math.min(50, (Math.abs(r.value) / m) * 50);
      const on = (e) => tip && tooltip.move(e, tip(r));
      return html`<div class="divbar" role="listitem" key=${r.key} onMouseMove=${on} onMouseLeave=${tooltip.hide}>
        <div class="who">${r.label}</div>
        <div class="track"><i class="axis"></i><i class=${"fill " + (r.value >= 0 ? "pos" : "neg")} style=${r.value >= 0 ? { left: "50%", width: w + "%" } : { right: "50%", width: w + "%" }}></i></div>
        <div class="val num"><span class=${"delta-val " + (r.value > 0.05 ? "pos" : r.value < -0.05 ? "neg" : "")}>${format(r.value)}</span></div>
      </div>`;
    })}
  </div>`;
}

/** Role-peer percentile rows: filled bar, median tick, percentile and raw value. `axis` adds the scale (lowest, typical, best) above the bars. */
export function PercentileBars({ items, onHover, axis }) {
  return html`<div class="pbars" role="list">
    ${axis ? html`<div class="pbar pbar-axis" aria-hidden="true"><span></span><span class="scale-cap"><em>lowest</em><em>typical</em><em>best</em></span><span></span><span></span></div>` : null}
    ${items.map((it) => html`<div class="pbar" role="listitem" key=${it.key} onMouseMove=${(e) => it.tip && tooltip.move(e, it.tip)} onMouseLeave=${tooltip.hide}>
      <span class="lab">${it.label}</span>
      <span class="track" aria-hidden="true"><i class="fill" style=${{ width: Math.max(1.5, it.pct ?? 0) + "%", background: seqColor(0.3 + 0.62 * ((it.pct ?? 0) / 100)) }}></i><i class="median"></i></span>
      <span class="pctn" title="Percentile among role peers">${it.pct == null ? "–" : Math.round(it.pct)}</span>
      <span class="raw">${it.raw}</span>
    </div>`)}
  </div>`;
}

/** Parts of a whole. Segments are separated by a 2px gap; large ones carry their label. */
export function StackedBar({ segments, format = (v) => nf(v, 1), unit = "", height = 26, legend = true }) {
  const total = segments.reduce((s, x) => s + Math.max(0, x.value), 0) || 1;
  return html`<div class="stackbar-wrap">
    <div class="stackbar" style=${{ height: height + "px" }} role="img" aria-label=${segments.map((s) => `${s.label} ${format(s.value)}${unit}`).join(", ")}>
      ${segments.map((s, i) => {
        const p = (Math.max(0, s.value) / total) * 100;
        return html`<i key=${s.key || i} style=${{ flex: `${p} 1 0`, background: s.color || SERIES_COLORS[i % SERIES_COLORS.length] }}
          onMouseMove=${(e) => tooltip.move(e, html`<div><div class="tt-title">${s.label}</div><div class="tt-row"><span class="k">${format(s.value)}${unit}</span><span class="v">${p.toFixed(0)}%</span></div></div>`)} onMouseLeave=${tooltip.hide}>${p >= 12 ? html`<span>${p.toFixed(0)}%</span>` : null}</i>`;
      })}
    </div>
    ${legend ? html`<div class="legend">${segments.map((s, i) => html`<span class="item" key=${s.key || i}><span class="swatch box" style=${{ background: s.color || SERIES_COLORS[i % SERIES_COLORS.length] }}></span>${s.label} <b class="num">${format(s.value)}${unit}</b></span>`)}</div>` : null}
  </div>`;
}

/** Simple magnitude bars with the value at the end. rows: [{ key, label, value, right? }] */
export function BarList({ rows, max, color = "var(--c1)", format = (v) => nf(v, 1) }) {
  const m = max || Math.max(1e-9, ...rows.map((r) => r.value));
  return html`<div class="barlist">
    ${rows.map((r) => html`<div class="barrow" key=${r.key}>
      <span class="lab">${r.label}</span>
      <span class="track"><i style=${{ width: Math.min(100, (r.value / m) * 100) + "%", background: r.color || color }}></i></span>
      <span class="val num">${r.right != null ? r.right : format(r.value)}</span>
    </div>`)}
  </div>`;
}

/**
 * Percentile dot plot for comparing 2-4 subjects across metrics.
 * metrics: [{ key, label, values:[raw...], pct:[percentile...], best: index, format }]
 */
export function PercentileDots({ metrics, subjects, colors }) {
  const colorAt = (i) => (colors ? colors[i] : SERIES_COLORS[i % SERIES_COLORS.length]);
  return html`<div class="pdots" role="list">
    <div class="pdots-head" aria-hidden="true"><span></span><span class="axis-cap"><em>0</em><em>25</em><em>50</em><em>75</em><em>100</em></span><span></span></div>
    ${metrics.map((m, mi) => {
      const known = m.pct.filter((v) => v != null);
      const lo = Math.min(...known), hi = Math.max(...known);
      const head = m.group && m.group !== metrics[mi - 1]?.group ? html`<div class="pdot-group" key=${"g" + m.group}>${m.group}</div>` : null;
      return html`${head}<div class="pdot-row" role="listitem" key=${m.key} title=${m.title || undefined}>
        <span class="lab">${m.label}</span>
        <span class="track" aria-hidden="true">
          ${known.length > 1 ? html`<i class="span" style=${{ left: lo + "%", width: hi - lo + "%" }}></i>` : null}
          ${m.pct.map((p, i) => (p == null ? null : html`<i key=${i} class=${"dot" + (i === m.best ? " best" : "")} style=${{ left: p + "%", background: colorAt(i) }}
            onMouseMove=${(e) => tooltip.move(e, html`<div><div class="tt-title">${subjects[i].name}</div><div class="tt-row"><span class="k">${m.label}</span><span class="v">${m.format(m.values[i])}</span></div><div class="tt-row"><span class="k">Percentile</span><span class="v">${Math.round(p)}</span></div></div>`)} onMouseLeave=${tooltip.hide}></i>`))}
        </span>
        <span class="vals num">${m.values.map((v, i) => html`<b key=${i} class=${i === m.best ? "best" : ""} style=${{ "--dot": colorAt(i) }}>${m.format(v)}</b>`)}</span>
      </div>`;
    })}
  </div>`;
}

/**
 * Volume against what came of it. One row per kind of action: the bar's length is how many there were (against the longest row), its solid
 * part the ones in a move that came to a shot, its hatched part the ones that did not. ``rows``: ``{ key, label, n, shot, pct?, note?, color?, text? }``;
 * ``pct`` is where that share stands among peers. A row with fewer than ``minN`` actions is drawn faded: a share of three is not a share.
 */
export function OutcomeBars({ rows, minN = 5, peers = "", solid = "came to a shot", hatched = "did not" }) {
  const max = Math.max(1, ...rows.map((r) => r.n));
  return html`<div class="outcome-bars">
    <div class="ob-legend xsmall muted"><span class="ob-key solid"></span>${solid}<span class="ob-key hatch"></span>${hatched}${rows.some((r) => r.lost != null) ? html`<span class="ob-key lost"></span>the ball was lost within three actions` : null}</div>
    ${rows.map((r) => {
      const share = r.n > 0 ? r.shot / r.n : null;
      return html`<div key=${r.key || r.label} class=${"ob-row" + (r.n < minN ? " faint" : "")} title=${r.n < minN ? "Too few to read a share from" : undefined} style=${r.color ? { "--ob": r.color } : null}>
        <span class="ob-label">${r.label}${r.note ? html`<span class="muted xsmall"> ${r.note}</span>` : null}</span>
        <span class="ob-track" role="img" aria-label=${`${r.text || r.label}: ${r.shot} of ${r.n} ${solid}`}>
          <span class="ob-fill" style=${{ width: `${(r.n / max) * 100}%` }}>
            <span class="ob-solid" style=${{ width: `${(share || 0) * 100}%` }}></span>
            ${r.lost ? html`<span class="ob-lost" style=${{ width: `${Math.min(1 - (share || 0), r.lost / r.n) * 100}%` }}></span>` : null}
          </span>
        </span>
        <span class="ob-num num"><b>${r.shot}</b> of ${r.n}${share != null ? html` <span class="muted">· ${Math.round(share * 100)}%</span>` : null}${r.lost != null && r.n > 0 ? html`<span class="ob-lostnum muted xsmall" title="After this many, his side lost the ball within three actions"> · ${r.lost} lost soon</span>` : null}</span>
        ${r.pct != null ? html`<span class="ob-pct xsmall" title=${`That share is higher than ${Math.round(r.pct)}% of ${peers || "peers"}`}>${ordinal(Math.round(r.pct))} pct</span>` : html`<span class="ob-pct"></span>`}
      </div>`;
    })}
  </div>`;
}

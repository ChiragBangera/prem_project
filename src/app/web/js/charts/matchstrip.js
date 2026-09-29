// One column per match: bar = chances created minus chances allowed, marker = what actually happened.
import { html, useState } from "../lib/html.js";
import { tooltip } from "../lib/tooltip.js";
import { nf, signed, dateShort } from "../lib/format.js";
import { Frame, AxisY, niceExtent, niceTicks, scaleBand, scaleLinear, tickFormat } from "./core.js";

const WORD = { w: "Won", d: "Drew", l: "Lost" };

function Marker({ result, x, y, active }) {
  const r = 5.2;
  if (result === "w") return html`<circle cx=${x} cy=${y} r=${r} class=${"res w" + (active ? " on" : "")} />`;
  if (result === "d") return html`<circle cx=${x} cy=${y} r=${r - 0.8} class=${"res d" + (active ? " on" : "")} />`;
  return html`<rect x=${x - r + 0.6} y=${y - r + 0.6} width=${(r - 0.6) * 2} height=${(r - 0.6) * 2} rx="1.5" class=${"res l" + (active ? " on" : "")} />`;
}

export function MatchStrip({ matches, height = 230, onOpen }) {
  const [hover, setHover] = useState(null);
  const diffs = matches.map((m) => m.xg - m.xga);
  const [lo, hi] = niceExtent(Math.min(-0.5, ...diffs) * 1.05, Math.max(0.5, ...diffs) * 1.05, 4);
  return html`<${Frame} height=${height} label="Chance difference and result in every match" margin=${{ top: 26, right: 12, bottom: 26, left: 40 }} onLeave=${() => { setHover(null); tooltip.hide(); }}>
    ${({ iw, ih }) => {
      const keys = matches.map((_, i) => i);
      const sx = scaleBand(keys, [0, iw], 0.28);
      const sy = scaleLinear([lo, hi], [ih, 0]);
      const yt = niceTicks(lo, hi, 4);
      const fy = tickFormat(yt[1] - yt[0] || 1);
      return html`<g>
        <${AxisY} scale=${sy} ticks=${yt} iw=${iw} format=${(v) => (v > 0 ? "+" + fy(v) : fy(v))} zero=${true} />
        ${matches.map((m, i) => {
          const d = diffs[i], x = sx(i), w = sx.bandwidth, on = hover === i;
          const y0 = sy(0), y1 = sy(d);
          return html`<g key=${i}>
            <rect class="strip-col" x=${x - 1.5} y=${-24} width=${w + 3} height=${ih + 24} style=${{ opacity: on ? 1 : 0 }} />
            <rect x=${x} y=${Math.min(y0, y1)} width=${w} height=${Math.max(1, Math.abs(y1 - y0))} rx="2" style=${{ fill: d >= 0 ? "var(--pos)" : "var(--neg)", opacity: on ? 1 : 0.9 }} />
            <${Marker} result=${m.result} x=${x + w / 2} y=${-12} active=${on} />
            ${i === 0 || (i + 1) % 5 === 0 ? html`<text class="tick-label" x=${x + w / 2} y=${ih + 18} text-anchor="middle">${m.n}</text>` : null}
          </g>`;
        })}
        <rect class="hit" x="0" y="-24" width=${iw} height=${ih + 24}
          onMouseMove=${(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            const i = Math.max(0, Math.min(matches.length - 1, Math.floor(((e.clientX - rect.left) / iw) * matches.length)));
            const m = matches[i];
            setHover(i);
            tooltip.move(e, html`<div>
              <div class="tt-title">${m.venue === "h" ? "vs" : "at"} ${m.opponent}</div>
              <div class="tt-sub">Matchweek ${m.n} · ${dateShort(m.date)}</div>
              <div class="tt-row"><span class="k">${WORD[m.result]}</span><span class="v">${m.gf}–${m.ga}</span></div>
              <div class="tt-row"><span class="k">xG</span><span class="v">${nf(m.xg, 2)}–${nf(m.xga, 2)}</span></div>
              <div class="tt-row"><span class="k">Chance difference</span><span class="v">${signed(m.xg - m.xga, 2)}</span></div>
              <div class="tt-row"><span class="k">Points vs expected</span><span class="v">${m.pts} vs ${nf(m.xpts, 1)}</span></div>
            </div>`);
          }}
          onClick=${() => hover != null && onOpen && onOpen(matches[hover])} style=${{ cursor: onOpen ? "pointer" : "default" }} />
      </g>`;
    }}
  </${Frame}>`;
}

export function StripLegend() {
  return html`<div class="legend">
    <span class="item"><span class="swatch box" style=${{ background: "var(--pos)" }}></span>Created more chances than allowed</span>
    <span class="item"><span class="swatch box" style=${{ background: "var(--neg)" }}></span>Allowed more than created</span>
    <span class="item"><svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><circle cx="6" cy="6" r="5" class="res w" /></svg>Won</span>
    <span class="item"><svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><circle cx="6" cy="6" r="4.2" class="res d" /></svg>Drew</span>
    <span class="item"><svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><rect x="1.5" y="1.5" width="9" height="9" rx="1.5" class="res l" /></svg>Lost</span>
  </div>`;
}

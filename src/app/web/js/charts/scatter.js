// Scatter plot with hover, click-through, reference lines, corner captions and collision-aware labels.
import { html, useRef, useState } from "../lib/html.js";
import { tooltip } from "../lib/tooltip.js";
import { Frame, AxisX, AxisY, extent, niceExtent, niceTicks, scaleLinear, tickFormat } from "./core.js";

const CHAR_W = 6.4;

/** Greedy label placement: highest priority first. A label goes beside its own dot (eight places are tried) where it covers neither a
 *  label already placed nor any other dot (`obstacles`: every dot drawn, as `{ id, x, y, r }`); one that fits nowhere is left out, since a
 *  name sitting on a neighbour's dot reads as the neighbour's name. */
export function placeLabels(items, bounds, size = 12, obstacles = []) {
  const placed = [];
  const boxes = [];
  const overlaps = (a, b) => a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
  const covers = (box, o) => {
    const cx = Math.max(box.x, Math.min(o.x, box.x + box.w)), cy = Math.max(box.y, Math.min(o.y, box.y + box.h));
    return (o.x - cx) ** 2 + (o.y - cy) ** 2 < (o.r + 1) ** 2;
  };
  for (const it of items) {
    const w = it.text.length * CHAR_W + 6, h = size + 4, g = it.r + 4, d = it.r * 0.7 + 3;
    const tries = [
      { x: it.x + g, y: it.y - h / 2, anchor: "start" },
      { x: it.x - g - w, y: it.y - h / 2, anchor: "end" },
      { x: it.x - w / 2, y: it.y - g - h, anchor: "middle" },
      { x: it.x - w / 2, y: it.y + g, anchor: "middle" },
      { x: it.x + d, y: it.y - d - h, anchor: "start" },
      { x: it.x + d, y: it.y + d, anchor: "start" },
      { x: it.x - d - w, y: it.y - d - h, anchor: "end" },
      { x: it.x - d - w, y: it.y + d, anchor: "end" },
    ];
    for (const t of tries) {
      const box = { x: t.x, y: t.y, w, h };
      if (box.x < -4 || box.x + w > bounds.w + 4 || box.y < -4 || box.y + h > bounds.h + 4) continue;
      if (boxes.some((b) => overlaps(box, b))) continue;
      if (obstacles.some((o) => o.id !== it.id && covers(box, o))) continue;
      boxes.push(box);
      placed.push({ ...it, tx: t.anchor === "start" ? t.x + 1 : t.anchor === "end" ? t.x + w - 1 : t.x + w / 2, ty: t.y + h / 2, anchor: t.anchor });
      break;
    }
  }
  return placed;
}

/** Nudge overlapping pill markers apart (smallest overlap axis first) so every label stays readable. */
export function dodge(items, bounds, iterations = 80) {
  const P = items.map((p) => ({ ...p, x: p.px, y: p.py }));
  for (let it = 0; it < iterations; it++) {
    let moved = false;
    for (let i = 0; i < P.length; i++) {
      for (let j = i + 1; j < P.length; j++) {
        const a = P[i], b = P[j];
        const dx = b.x - a.x, dy = b.y - a.y;
        const ox = (a.bw + b.bw) / 2 + 2 - Math.abs(dx);
        const oy = (a.bh + b.bh) / 2 + 2 - Math.abs(dy);
        if (ox > 0 && oy > 0) {
          if (oy <= ox) { const sft = (dy >= 0 ? 1 : -1) * (oy / 2 + 0.25); a.y -= sft; b.y += sft; }
          else { const sft = (dx >= 0 ? 1 : -1) * (ox / 2 + 0.25); a.x -= sft; b.x += sft; }
          moved = true;
        }
      }
    }
    P.forEach((p) => { p.x = Math.max(p.bw / 2, Math.min(bounds.w - p.bw / 2, p.x)); p.y = Math.max(p.bh / 2, Math.min(bounds.h - p.bh / 2, p.y)); });
    if (!moved) break;
  }
  return P;
}

/** ``trend`` (on the chart) is a list of lines ``{ a, b, color?, from?, to? }``. This is the part of the line ``y = a + b·x`` that lies inside the plot, as ``[x, y, x, y]`` (null when none of it does). */
export const clipLine = ({ a, b }, [x0, x1], [y0, y1]) => {
  let lo = x0, hi = x1;
  if (b !== 0) {
    const atY0 = (y0 - a) / b, atY1 = (y1 - a) / b;
    lo = Math.max(lo, Math.min(atY0, atY1));
    hi = Math.min(hi, Math.max(atY0, atY1));
  } else if (a < y0 || a > y1) return null;
  return hi > lo ? [lo, a + b * lo, hi, a + b * hi] : null;
};

export function Scatter({
  points, xLabel, yLabel, xFormat, yFormat, invertX = false, invertY = false, xDomain, yDomain,
  refX, refY, corners, height = 380, onSelect, renderTip, mark = "dot", selectedId, hoverPad = 30, label = "Scatter plot", zeroX, zeroY, trend,
}) {
  const [hover, setHover] = useState(null);
  const svgRef = useRef(null);

  const xs = points.map((p) => p.x), ys = points.map((p) => p.y);
  // metrics that cannot go negative should not draw negative space
  const floorAt0 = (vals, [lo, hi]) => (Math.min(...vals) >= 0 && lo < 0 ? [0, hi] : [lo, hi]);
  const [x0, x1] = xDomain || floorAt0(xs, niceExtent(...extent([...xs, ...(refX != null ? [refX] : [])], 0.04)));
  const [y0, y1] = yDomain || floorAt0(ys, niceExtent(...extent([...ys, ...(refY != null ? [refY] : [])], 0.06)));

  return html`<${Frame} height=${height} label=${label} margin=${{ top: 14, right: 18, bottom: 46, left: 58 }} onLeave=${() => { setHover(null); tooltip.hide(); }}>
    ${({ iw, ih }) => {
      const sx = scaleLinear([x0, x1], invertX ? [iw, 0] : [0, iw]);
      const sy = scaleLinear([y0, y1], invertY ? [0, ih] : [ih, 0]);
      const xt = niceTicks(x0, x1, Math.max(3, Math.floor(iw / 90)));
      const yt = niceTicks(y0, y1, Math.max(3, Math.floor(ih / 60)));
      const fx = xFormat || tickFormat(xt[1] - xt[0] || 1);
      const fy = yFormat || tickFormat(yt[1] - yt[0] || 1);

      const base = points.map((p) => ({ ...p, px: sx(p.x), py: sy(p.y), pr: p.r || 4.5, bw: mark === "pill" ? Math.max(26, (p.label || "").length * 6.9 + 10) : 0, bh: 20 }));
      const pts = mark === "pill" ? dodge(base, { w: iw, h: ih }).map((p) => ({ ...p, tx: p.px, ty: p.py, px: p.x, py: p.y })) : base;
      const labelled = pts.filter((p) => p.label && (mark === "pill" || p.showLabel !== false)).sort((a, b) => (b.priority || 0) - (a.priority || 0));
      const labelItems = mark === "pill" ? [] : placeLabels(labelled.map((p) => ({ id: p.id, x: p.px, y: p.py, r: p.pr, text: p.label, color: p.labelColor })), { w: iw, h: ih }, 12, pts.map((p) => ({ id: p.id, x: p.px, y: p.py, r: p.pr })));
      const cornerBox = (side, text) => {
        const w = text.length * 7.6 + 6, h = 16;
        const x = side.endsWith("l") ? 6 : iw - 6 - w, y = side.startsWith("t") ? 2 : ih - 8 - h + 2;
        return { x, y, w, h };
      };
      const cornerFree = (side, text) => {
        if (mark !== "pill") return true;
        const b = cornerBox(side, text);
        return !pts.some((p) => p.px - p.bw / 2 < b.x + b.w + 4 && p.px + p.bw / 2 > b.x - 4 && p.py - p.bh / 2 < b.y + b.h + 4 && p.py + p.bh / 2 > b.y - 4);
      };

      const move = (e) => {
        const rect = e.currentTarget.getBoundingClientRect();
        const mx = e.clientX - rect.left, my = e.clientY - rect.top;
        let best = null, bd = hoverPad * hoverPad;
        for (const p of pts) {
          const d = (p.px - mx) ** 2 + (p.py - my) ** 2;
          if (d < bd) { bd = d; best = p; }
        }
        setHover(best ? best.id : null);
        best && renderTip ? tooltip.move(e, renderTip(best)) : tooltip.hide();
      };
      const active = hover ?? null;
      const trendSegs = (trend || []).map((t) => ({ color: t.color, seg: clipLine(t, [t.from ?? x0, t.to ?? x1], [y0, y1]) })).filter((t) => t.seg);
      const drawOrder = [...pts].sort((a, b) => (a.id === active) - (b.id === active) || (a.id === selectedId) - (b.id === selectedId) || (a.z || 0) - (b.z || 0));

      return html`<g>
        <${AxisY} scale=${sy} ticks=${yt} iw=${iw} format=${fy} />
        <${AxisX} scale=${sx} ticks=${xt} ih=${ih} format=${fx} grid=${true} />
        ${zeroX != null ? html`<line class="axis-line" x1=${sx(zeroX)} x2=${sx(zeroX)} y1="0" y2=${ih} />` : null}
        ${zeroY != null ? html`<line class="axis-line" x1="0" x2=${iw} y1=${sy(zeroY)} y2=${sy(zeroY)} />` : null}
        ${refX != null ? html`<line class="ref-line" x1=${sx(refX)} x2=${sx(refX)} y1="0" y2=${ih} />` : null}
        ${refY != null ? html`<line class="ref-line" x1="0" x2=${iw} y1=${sy(refY)} y2=${sy(refY)} />` : null}
        ${trendSegs.map((t, i) => html`<line key=${"t" + i} class="trend-line" style=${t.color ? { stroke: t.color } : null} x1=${sx(t.seg[0])} y1=${sy(t.seg[1])} x2=${sx(t.seg[2])} y2=${sy(t.seg[3])} />`)}
        ${corners ? html`<g class="corner-labels">
          ${corners.tl && cornerFree("tl", corners.tl) ? html`<text x="6" y="14" text-anchor="start">${corners.tl}</text>` : null}
          ${corners.tr && cornerFree("tr", corners.tr) ? html`<text x=${iw - 6} y="14" text-anchor="end">${corners.tr}</text>` : null}
          ${corners.bl && cornerFree("bl", corners.bl) ? html`<text x="6" y=${ih - 8} text-anchor="start">${corners.bl}</text>` : null}
          ${corners.br && cornerFree("br", corners.br) ? html`<text x=${iw - 6} y=${ih - 8} text-anchor="end">${corners.br}</text>` : null}
        </g>` : null}
        <text class="axis-title" x=${iw / 2} y=${ih + 40} text-anchor="middle">${xLabel}</text>
        <text class="axis-title" transform=${`translate(${-44},${ih / 2}) rotate(-90)`} text-anchor="middle">${yLabel}</text>
        ${drawOrder.map((p) => {
          const on = p.id === active, sel = p.id === selectedId;
          if (mark === "pill") {
            const w = p.bw;
            const off = Math.hypot(p.tx - p.px, p.ty - p.py) > 5;
            return html`<g key=${p.id} class=${"pill-mark" + (on || sel || p.highlight ? " on" : "")} style=${{ cursor: onSelect ? "pointer" : "default", "--pill": p.color || undefined }}>
              ${off ? html`<line class="leader" x1=${p.tx} y1=${p.ty} x2=${p.px} y2=${p.py} /><circle class="anchor" cx=${p.tx} cy=${p.ty} r="2.2" />` : null}
              <g transform=${`translate(${p.px},${p.py})`}><rect x=${-w / 2} y="-10" width=${w} height="20" rx="6" /><text y="0.35em" text-anchor="middle">${p.label}</text></g>
            </g>`;
          }
          return html`<g key=${p.id} transform=${`translate(${p.px},${p.py})`} style=${{ cursor: onSelect ? "pointer" : "default" }}>
            <circle r=${p.pr + (on ? 2 : 0)} class=${"dot-mark" + (p.highlight ? " hi" : "") + (sel ? " sel" : "") + (p.clamped ? " clamped" : "")} style=${{ fill: p.color || "var(--c1)", opacity: p.dim ? 0.28 : on || sel || p.highlight ? 1 : 0.68 }} />
            ${p.ring ? html`<circle r=${p.pr + 3.5} class="ring-mark" />` : null}
          </g>`;
        })}
        ${labelItems.map((l) => html`<text key=${"l" + l.id} class="pt-label" x=${l.tx} y=${l.ty} dy="0.35em" text-anchor=${l.anchor}>${l.text}</text>`)}
        <rect class="hit" x="0" y="0" width=${iw} height=${ih} ref=${svgRef} onMouseMove=${move} onClick=${() => { const p = pts.find((q) => q.id === active); if (p && onSelect) onSelect(p); }} style=${{ cursor: active != null && onSelect ? "pointer" : "default" }} />
      </g>`;
    }}
  </${Frame}>`;
}

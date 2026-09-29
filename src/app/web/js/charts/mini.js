// Tiny bar series for season-by-season comparisons.
import { html } from "../lib/html.js";
import { tooltip } from "../lib/tooltip.js";

export function MiniBars({ labels, values, format = (v) => String(v), height = 74, color = "var(--c1)", highlight }) {
  const known = values.filter((v) => v != null && Number.isFinite(v));
  const max = Math.max(1e-9, ...known);
  const barW = 100 / values.length;
  return html`<div class="minibars" role="img" aria-label=${labels.map((l, i) => `${l}: ${values[i] == null ? "n/a" : format(values[i])}`).join(", ")}>
    <div class="bars" style=${{ height: height + "px" }}>
      ${values.map((v, i) => html`<div class="col" key=${i} style=${{ width: barW + "%" }}
        onMouseMove=${(e) => tooltip.move(e, html`<div><div class="tt-title">${labels[i]}</div><div class="tt-row"><span class="k">${v == null ? "no data" : format(v)}</span></div></div>`)} onMouseLeave=${tooltip.hide}>
        <span class="val num">${v == null ? "" : format(v)}</span>
        <i style=${{ height: v == null ? "0" : Math.max(2, (v / max) * 100) + "%", background: highlight === i ? color : `color-mix(in oklab, ${color} 55%, var(--surface-3))` }}></i>
      </div>`)}
    </div>
    <div class="labels">${labels.map((l, i) => html`<span key=${i} style=${{ width: barW + "%" }}>${l}</span>`)}</div>
  </div>`;
}

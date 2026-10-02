// A native select listing every metric under its group heading: the one way to choose "which metric" anywhere in the app.
import { html } from "../../lib/html.js";
import { cls } from "../../lib/format.js";

/**
 * ctx: the explorer context (metrics, order, groups). extra: leading options that are not metrics ([{ value, label }]).
 * only: optional predicate (key) => boolean to limit the list.
 */
export function MetricSelect({ ctx, value, onChange, label, extra = [], only, compact, id, title }) {
  const byGroup = ctx.groups.map((g) => ({ g, keys: ctx.order.filter((k) => ctx.metrics[k]?.group === g.key && (!only || only(k))) })).filter((x) => x.keys.length);
  return html`<select class=${cls("select", compact && "compact")} id=${id} aria-label=${label} title=${title} onChange=${(e) => onChange(e.target.value)}>
    ${extra.map((o) => html`<option key=${o.value} value=${o.value} selected=${o.value === value}>${o.label}</option>`)}
    ${byGroup.map(({ g, keys }) => html`<optgroup key=${g.key} label=${g.label}>
      ${keys.map((k) => html`<option key=${k} value=${k} selected=${k === value}>${ctx.metrics[k].label}</option>`)}
    </optgroup>`)}
  </select>`;
}

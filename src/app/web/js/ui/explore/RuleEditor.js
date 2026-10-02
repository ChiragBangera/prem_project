// Add or edit one metric filter: "key passes per 90 at least 2.0", or "top 20% of role peers for xG". Shows how many rows it would leave, live.
import { html, useMemo, useState } from "../../lib/html.js";
import { fold } from "../../lib/format.js";
import { applyFilters, quantile } from "../../lib/filters.js";
import { fmtMetric, blank } from "../../lib/metricfmt.js";
import { Button, Segmented } from "../common.js";

const OPS = [{ value: ">=", label: "At least" }, { value: "<=", label: "At most" }];

/** What the user types vs what the rule stores: a share is typed as a percentage, stored as a fraction. */
const toStored = (def, on, typed) => (on === "value" && def?.unit === "share" ? typed / 100 : typed);
const toTyped = (def, on, stored) => (on === "value" && def?.unit === "share" ? Math.round(stored * 1000) / 10 : stored);

function stepFor(def, on) {
  if (on === "pct") return 5;
  if (def?.unit === "share") return 1;
  const d = def?.decimals ?? 2;
  return d >= 3 ? 0.001 : d === 2 ? 0.01 : d === 1 ? 0.1 : 1;
}

export function RuleEditor({ ctx, rows, state, editing, onSubmit, onCancel, level }) {
  const start = editing?.rule || null;
  const [metric, setMetric] = useState(start?.metric || null);
  const [search, setSearch] = useState("");
  const [on, setOn] = useState(start?.on || "value");
  const [op, setOp] = useState(start?.op || ">=");
  const def = metric ? ctx.metrics[metric] : null;
  const [typed, setTyped] = useState(start ? toTyped(ctx.metrics[start.metric], start.on, start.value) : "");

  const hasPct = useMemo(() => (metric ? rows.some((r) => !blank(r.p[ctx.idx[metric]])) : false), [metric, rows, ctx]);
  const values = useMemo(() => {
    if (!metric) return [];
    const i = ctx.idx[metric];
    return rows.map((r) => r.v[i]).filter((v) => !blank(v)).sort((a, b) => a - b);
  }, [metric, rows, ctx]);

  const list = useMemo(() => {
    const needle = fold(search);
    const groupLabel = Object.fromEntries(ctx.groups.map((g) => [g.key, g.label]));
    const keys = ctx.order.filter((k) => {
      const m = ctx.metrics[k];
      if (!m) return false;
      if (!needle) return true;
      return fold(`${m.label} ${m.short} ${k} ${groupLabel[m.group] || ""}`).includes(needle);
    });
    const byGroup = ctx.groups.map((g) => ({ group: g, items: keys.filter((k) => ctx.metrics[k].group === g.key) })).filter((g) => g.items.length);
    return byGroup;
  }, [search, ctx]);

  const candidate = metric && typed !== "" && Number.isFinite(Number(typed)) ? { metric, op, on, value: toStored(def, on, Number(typed)) } : null;
  const matching = useMemo(() => {
    if (!candidate) return null;
    const others = state.rules.filter((_, i) => i !== (editing?.index ?? -1));
    return applyFilters(rows, { ...state, rules: [...others, candidate] }, ctx).length;
  }, [candidate?.metric, candidate?.op, candidate?.on, candidate?.value, state, rows, ctx]);

  const choose = (k) => {
    setMetric(k);
    setSearch("");
    setTyped("");
    const m = ctx.metrics[k];
    // a ranking metric defaults to its value; the percentile switch is one click away
    setOn("value");
    setOp(m?.hib === false ? "<=" : ">=");
  };
  const pickOn = (v) => { setOn(v); setTyped(""); };
  const hint = (() => {
    if (!values.length) return "No values in this list yet.";
    if (on === "pct") return level === "team" ? "Percentile among the teams of the same league and season. 80 means better than 80% of them (top 20%)." : "Percentile among players of the same role. 80 means better than 80% of them (top 20%). It reads higher-is-better for every metric, fewer fouls included.";
    return `In this list: lowest ${fmtMetric(def, values[0])} · median ${fmtMetric(def, quantile(values, 0.5))} · highest ${fmtMetric(def, values[values.length - 1])}`;
  })();

  return html`<form class="stack rule-editor" style=${{ "--gap": "12px" }} onSubmit=${(e) => { e.preventDefault(); if (candidate) onSubmit(candidate, editing?.index ?? -1); }}>
    ${!def ? html`<div class="stack" style=${{ "--gap": "8px" }}>
      <label class="field"><span class="label">Which metric?</span><input class="input" autofocus placeholder=${`Search ${ctx.order.length} metrics (xG, tackles, passes, age …)`} value=${search} onInput=${(e) => setSearch(e.target.value)} aria-label="Search metrics" /></label>
      <div class="metric-list" role="listbox" aria-label="Metrics">
        ${list.map(({ group, items }) => html`<div key=${group.key} class="metric-group">
          <div class="eyebrow">${group.label}</div>
          ${items.map((k) => html`<button type="button" key=${k} class="menu-item" role="option" onClick=${() => choose(k)} title=${ctx.metrics[k].what}><span class="truncate">${ctx.metrics[k].label}</span></button>`)}
        </div>`)}
        ${!list.length ? html`<p class="xsmall muted" style=${{ padding: "8px" }}>No metric matches “${search}”.</p>` : null}
      </div>
    </div>` : html`<div class="stack" style=${{ "--gap": "12px" }}>
      <div class="row between"><div class="stack" style=${{ "--gap": "1px" }}><b>${def.label}</b><span class="xsmall muted">${def.what}</span></div>
        ${editing?.index >= 0 ? null : html`<${Button} kind="quiet" size="sm" onClick=${() => setMetric(null)}>Change</${Button}>`}</div>
      <div class="row wrap" style=${{ gap: "8px" }}>
        <${Segmented} small label="Compare" value=${on} onChange=${pickOn} options=${[{ value: "value", label: "Value" }, ...(hasPct ? [{ value: "pct", label: "Percentile" }] : [])]} />
        <${Segmented} small label="Direction" value=${op} onChange=${setOp} options=${OPS} />
        <label class="field" style=${{ flex: "1 1 90px" }}><span class="sr-only">Limit</span>
          <input class="input" type="number" step=${stepFor(def, on)} min=${on === "pct" ? 0 : undefined} max=${on === "pct" ? 100 : undefined} value=${typed} placeholder=${on === "pct" ? "e.g. 80" : def.unit === "share" ? "e.g. 70 (%)" : "limit"} onInput=${(e) => setTyped(e.target.value)} aria-label="Limit" /></label>
      </div>
      ${on === "pct" ? html`<div class="chipgroup">${[50, 75, 90].map((n) => html`<button type="button" key=${n} class="chip" onClick=${() => { setOp(">="); setTyped(n); }}>Top ${100 - n}%</button>`)}</div>` : null}
      <p class="xsmall muted">${hint}</p>
      <div class="row between"><span class="small">${matching == null ? "" : html`<b class="num">${matching.toLocaleString("en-GB")}</b> of ${rows.length.toLocaleString("en-GB")} would match`}</span>
        <div class="row" style=${{ gap: "8px" }}><${Button} kind="quiet" onClick=${onCancel}>Cancel</${Button}><${Button} kind="primary" type="submit" disabled=${!candidate}>${editing?.index >= 0 ? "Update filter" : "Add filter"}</${Button}></div></div>
    </div>`}
  </form>`;
}

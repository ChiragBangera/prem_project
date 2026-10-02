// Choose the table's columns: start from a themed set (Attacking, Defending ...) or tick any metrics. Every metric the app computes is here.
import { html, useMemo, useState } from "../../lib/html.js";
import { Icon } from "../../lib/icons.js";
import { cls, fold } from "../../lib/format.js";
import { Popover } from "../common.js";

function GroupBlock({ group, keys, ctx, selected, onToggle, onAll, onNone, open, onOpen, empty }) {
  const picked = keys.filter((k) => selected.has(k)).length;
  return html`<div class="cp-group">
    <button type="button" class="cp-head" aria-expanded=${String(open)} onClick=${onOpen}>
      <${Icon} name=${open ? "chevronDown" : "chevronRight"} size="sm" />
      <span class="cp-title">${group.label}</span>
      <span class="muted xsmall">${picked ? `${picked} of ${keys.length}` : keys.length}</span>
    </button>
    ${open ? html`<div class="cp-body">
      <p class="xsmall muted cp-blurb">${group.blurb}</p>
      <div class="row" style=${{ gap: "10px", marginBottom: "4px" }}><button type="button" class="linklike" onClick=${onAll}>Add all</button><button type="button" class="linklike" onClick=${onNone}>Remove all</button></div>
      ${keys.map((k) => {
        const m = ctx.metrics[k];
        const on = selected.has(k);
        return html`<button type="button" key=${k} class=${cls("menu-item", empty(m) && "dim")} role="checkbox" aria-checked=${String(on)} onClick=${() => onToggle(k)} title=${`${m.what}${empty(m) ? " (no data for this selection yet)" : ""}`}>
          <span class="check">${on ? html`<${Icon} name="check" size="sm" />` : null}</span>
          <span class="truncate">${m.label}</span>
          <span class="muted xsmall" style=${{ marginLeft: "auto" }}>${m.kind === "raw" ? "raw" : ""}</span>
        </button>`;
      })}
    </div>` : null}
  </div>`;
}

export function ColumnPicker({ model }) {
  const { ctx, columns, setView, setColumns } = model;
  const [search, setSearch] = useState("");
  const [openGroups, setOpen] = useState(() => new Set());
  const selected = new Set(columns.keys);
  const needle = fold(search);
  const emptyIn = (m) => m.needs === "events" && (ctx.coverage.event_players ?? ctx.coverage.event_teams) === 0;

  const groups = useMemo(() => ctx.groups.map((g) => ({ group: g, keys: ctx.order.filter((k) => ctx.metrics[k]?.group === g.key && (!needle || fold(`${ctx.metrics[k].label} ${ctx.metrics[k].short} ${k} ${g.label}`).includes(needle))) })).filter((g) => g.keys.length), [ctx, needle]);
  const toggleKey = (k) => setColumns(selected.has(k) ? columns.keys.filter((x) => x !== k) : [...columns.keys, k]);
  const toggleGroup = (g) => setOpen((s) => { const n = new Set(s); n.has(g) ? n.delete(g) : n.add(g); return n; });

  return html`<${Popover} label="Columns" summary=${columns.name} icon="grid" active=${columns.custom} width=${440} align="right" title="Choose which metrics the table shows">
    <div class="stack column-picker" style=${{ "--gap": "12px" }}>
      <div class="stack" style=${{ "--gap": "6px" }}>
        <span class="eyebrow">Start from a set</span>
        <div class="chipgroup">${ctx.views.map((v) => html`<button type="button" key=${v.key} class="chip" aria-pressed=${String(columns.preset === v.key)} title=${v.blurb} onClick=${() => setView({ cols: v.key === "overview" ? null : v.key })}>${v.label}</button>`)}
          ${columns.custom ? html`<span class="chip on" aria-pressed="true">Custom <b>${columns.keys.length}</b></span>` : null}</div>
      </div>
      <div class="stack" style=${{ "--gap": "6px" }}>
        <div class="row between"><span class="eyebrow">Or tick any of the ${ctx.order.length} metrics</span>
          ${columns.keys.length ? html`<button type="button" class="linklike" onClick=${() => setColumns([])}>Clear all</button>` : null}</div>
        <input class="input" placeholder="Search metrics (xG, tackles, passes, age …)" value=${search} onInput=${(e) => setSearch(e.target.value)} aria-label="Search metrics" />
      </div>
      <div class="cp-list">
        ${groups.map(({ group, keys }) => html`<${GroupBlock} key=${group.key} group=${group} keys=${keys} ctx=${ctx} selected=${selected} open=${Boolean(needle) || openGroups.has(group.key)} empty=${emptyIn}
          onOpen=${() => toggleGroup(group.key)} onToggle=${toggleKey}
          onAll=${() => setColumns([...new Set([...columns.keys, ...keys])])} onNone=${() => setColumns(columns.keys.filter((k) => !keys.includes(k)))} />`)}
        ${!groups.length ? html`<p class="xsmall muted" style=${{ padding: "8px" }}>No metric matches “${search}”.</p>` : null}
      </div>
      <p class="xsmall muted">Columns are grouped under their kind, so a mix of shooting, creating and defending metrics keeps each under its own heading. Your choice is kept in the address, so the view can be shared, and remembered here for next time.</p>
    </div>
  </${Popover}>`;
}

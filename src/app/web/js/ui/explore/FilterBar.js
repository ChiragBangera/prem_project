// The filter bar: independent controls that each narrow the list, a strip showing exactly what is active, and a count that always matches the table.
// Nothing here starts selected. "All" is the state of a control the user has not touched.
import { html, useEffect, useMemo, useState } from "../../lib/html.js";
import { Icon } from "../../lib/icons.js";
import { cls, debounce, fold, formation } from "../../lib/format.js";
import { predicateFor, ROLE_ORDER } from "../../lib/filters.js";
import { Button, Popover, RangeSlider, SearchBox, Select, Switch } from "../common.js";
import { RuleEditor } from "./RuleEditor.js";
import { LensBar } from "./LensBar.js";

/** Counts per value of one facet, with that facet's own filter ignored (so a chip shows what clicking it would add). */
function facet(rows, state, ctx, own, values) {
  const cleared = { ...state, [own]: Array.isArray(state[own]) ? [] : own === "minutes" ? 0 : "" };
  const pass = predicateFor(cleared, ctx);
  const counts = new Map();
  for (const r of rows) {
    if (!pass(r)) continue;
    for (const v of values(r)) if (v != null) counts.set(v, (counts.get(v) || 0) + 1);
  }
  return counts;
}

const toggle = (list, v) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);

function Check({ on, label, hint, sub, onClick, disabled }) {
  return html`<button type="button" class="menu-item" role="checkbox" aria-checked=${String(on)} disabled=${disabled} onClick=${onClick}>
    <span class="check">${on ? html`<${Icon} name="check" size="sm" />` : null}</span>
    <span class="stack" style=${{ "--gap": 0, minWidth: 0 }}><span class="truncate">${label}</span>${sub ? html`<span class="xsmall muted">${sub}</span>` : null}</span>
    ${hint != null ? html`<span class="muted xsmall" style=${{ marginLeft: "auto" }}>${hint}</span>` : null}
  </button>`;
}

function ClubList({ options, value, onChange }) {
  const [q, setQ] = useState("");
  const shown = options.filter((o) => fold(o.label).includes(fold(q)));
  return html`<div class="stack" style=${{ "--gap": "8px" }}>
    <input class="input" placeholder="Filter clubs" value=${q} onInput=${(e) => setQ(e.target.value)} aria-label="Filter the club list" />
    <div class="checklist">
      ${shown.map((o) => html`<${Check} key=${o.value} on=${value.includes(o.value)} label=${o.label} hint=${o.count} onClick=${() => onChange(toggle(value, o.value))} />`)}
      ${!shown.length ? html`<p class="xsmall muted" style=${{ padding: "6px" }}>No club matches “${q}”.</p>` : null}
    </div>
    ${value.length ? html`<button type="button" class="menu-item" onClick=${() => onChange([])}>Clear clubs</button>` : null}
  </div>`;
}

function PositionPanel({ ctx, counts, value, onChange, unknown }) {
  const order = ctx.positions.order;
  const byRole = ROLE_ORDER.map((role) => ({ role, items: order.filter((p) => ctx.positions.group[p] === role) })).filter((g) => g.items.length);
  return html`<div class="stack" style=${{ "--gap": "12px" }}>
    ${byRole.map((g) => html`<div key=${g.role} class="stack" style=${{ "--gap": "6px" }}>
      <span class="eyebrow">${ctx.roles.plural[g.role]}</span>
      <div class="chipgroup">${g.items.map((p) => html`<button type="button" key=${p} class="chip" aria-pressed=${String(value.includes(p))} onClick=${() => onChange(toggle(value, p))}>${ctx.positions.labels[p]} <span class="muted">${counts.get(p) || 0}</span></button>`)}</div>
    </div>`)}
    <p class="xsmall muted">The position a player mostly lined up in, from match line-ups.${unknown ? ` ${unknown} players have none yet (it arrives as match pages are downloaded) and cannot match a position.` : ""}</p>
  </div>`;
}

function ProfilePanel({ ctx, counts, value, onChange }) {
  const groups = ROLE_ORDER.map((role) => ({ role, tags: ctx.tagList.filter((t) => t.group === role) })).filter((g) => g.tags.length);
  return html`<div class="stack" style=${{ "--gap": "10px", maxHeight: "420px", overflow: "auto", paddingRight: "4px" }}>
    ${groups.map((g) => html`<div key=${g.role} class="stack" style=${{ "--gap": "2px" }}>
      <span class="eyebrow" style=${{ padding: "4px 8px" }}>${ctx.roles.plural[g.role]}</span>
      ${g.tags.map((t) => html`<${Check} key=${t.key} on=${value.includes(t.key)} label=${t.label} sub=${t.blurb} hint=${counts.get(t.key) || 0} disabled=${!counts.get(t.key) && !value.includes(t.key)} onClick=${() => onChange(toggle(value, t.key))} />`)}
    </div>`)}
    <p class="xsmall muted">Profiles are labels earned by simple rules on percentiles (for example “top 15% of defenders for build-up”). They are shown on each row, and the Data dictionary lists every rule. Players under 270 minutes are not labelled.</p>
  </div>`;
}

const MINUTE_STEPS = [0, 90, 450, 900, 1800];

function MinutesPanel({ value, onChange, poolMinutes }) {
  return html`<div class="stack" style=${{ "--gap": "12px" }}>
    <div class="chipgroup">${MINUTE_STEPS.map((m) => html`<button type="button" key=${m} class="chip" aria-pressed=${String(value === m)} onClick=${() => onChange(m)}>${m === 0 ? "Any" : `${m}+`}</button>`)}</div>
    <label class="field"><span class="label">Or at least this many minutes</span><input class="input" type="number" min="0" step="30" value=${value || ""} placeholder="0" onChange=${(e) => onChange(Math.max(0, Number(e.target.value) || 0))} /></label>
    <p class="xsmall muted">Per-90 numbers swing wildly on few minutes. Everyone is listed by default; use this to set aside cameos. ${poolMinutes ? `Rankings use players with ${poolMinutes}+ minutes as the peer group, and small samples are pulled toward the average.` : ""}</p>
  </div>`;
}

function AgePanel({ state, onChange, ageRef, unknownCount }) {
  const value = state.age || [15, 45];
  return html`<div class="stack" style=${{ "--gap": "12px" }}>
    <${RangeSlider} label="Age range" min=${15} max=${45} value=${value} format=${(v) => v} onChange=${(v) => onChange({ age: v[0] === 15 && v[1] === 45 ? null : v })} />
    <${Switch} checked=${state.ageUnknown} onChange=${(v) => onChange({ ageUnknown: v })}>Also show players whose age is unknown${unknownCount ? ` (${unknownCount})` : ""}</${Switch}>
    <p class="xsmall muted">${ageRef ? `Ages are as of ${new Date(ageRef).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" })}. ` : ""}Exact birthdates come from club squad lists. Where a list leaves a player out, Wikidata is used when it matches the name and club; a “?” means only the name matched, so the age is not trusted by this filter. With no safe match the age stays blank rather than guessed.</p>
  </div>`;
}

function FormationList({ counts, value, onChange }) {
  const items = [...counts.entries()].sort((a, b) => b[1] - a[1]);
  return html`<div class="checklist">${items.map(([f, n]) => html`<${Check} key=${f} on=${value.includes(f)} label=${formation(f) || f} hint=${n} onClick=${() => onChange(toggle(value, f))} />`)}
    ${!items.length ? html`<p class="xsmall muted" style=${{ padding: "6px" }}>Formations come from event data, which is not stored for this selection.</p>` : null}</div>`;
}

/**
 * config: { level, noun, controls: ["roles","positions","tags","clubs","minutes","age","part","formations","rule"], ageRef, poolMinutes }
 * model: from useExplorer(). allRows: the dataset's rows before filtering.
 */
export function FilterBar({ model, allRows, config, onShowColumns, onSortBy, onOpenLens }) {
  const { ctx, filters, patchFilters, setFilters, clearFilters, chips, filtered } = model;
  const has = (c) => config.controls.includes(c);
  const [text, setText] = useState(filters.q);
  const push = useMemo(() => debounce((v) => patchFilters({ q: v }), 220), [patchFilters]);
  useEffect(() => setText(filters.q), [filters.q]);
  const [editing, setEditing] = useState(null);

  const key = JSON.stringify(filters);
  const roleCounts = useMemo(() => facet(allRows, filters, ctx, "roles", (r) => [r.group]), [allRows, key, ctx]);
  const posCounts = useMemo(() => (has("positions") ? facet(allRows, filters, ctx, "positions", (r) => [r.pos2]) : new Map()), [allRows, key, ctx]);
  const tagCounts = useMemo(() => (has("tags") ? facet(allRows, filters, ctx, "tags", (r) => (r.tags || []).map((t) => t.key)) : new Map()), [allRows, key, ctx]);
  const clubCounts = useMemo(() => (has("clubs") ? facet(allRows, filters, ctx, "clubs", (r) => r.teams || [r.team]) : new Map()), [allRows, key, ctx]);
  const formCounts = useMemo(() => (has("formations") ? facet(allRows, filters, ctx, "formations", (r) => [r.formation]) : new Map()), [allRows, key, ctx]);
  const unknownPos = useMemo(() => (has("positions") ? allRows.filter((r) => !r.pos2).length : 0), [allRows]);
  const unknownAge = useMemo(() => (has("age") ? allRows.filter((r) => r.age == null || r.dob_basis === "name").length : 0), [allRows]);
  const clubOptions = useMemo(() => [...clubCounts.entries()].map(([value, count]) => ({ value, label: value, count })).sort((a, b) => a.label.localeCompare(b.label)), [clubCounts]);
  const allClubs = useMemo(() => (has("clubs") ? [...new Set(allRows.flatMap((r) => r.teams || [r.team]))].sort() : []), [allRows]);
  const clubList = allClubs.map((c) => ({ value: c, label: c, count: clubCounts.get(c) || 0 }));

  const n = filtered.length, total = allRows.length;
  return html`<section class="card filterbar" aria-label="Filters">
    <div class="fb-row fb-top">
      <${SearchBox} value=${text} onInput=${(v) => { setText(v); push(v); }} placeholder=${config.searchPlaceholder || "Search by name or club"} width="260px" />
      <span class="spacer"></span>
      <span class="fb-count" aria-live="polite"><b class="num">${n.toLocaleString("en-GB")}</b> of ${total.toLocaleString("en-GB")} ${config.noun}${model.isFiltered ? "" : " (no filters)"}</span>
      ${model.isFiltered ? html`<${Button} kind="quiet" size="sm" icon="x" onClick=${clearFilters}>Clear all</${Button}>` : null}
    </div>

    ${has("roles") ? html`<div class="fb-row">
      <span class="fb-label">Role</span>
      <div class="chipgroup" role="group" aria-label="Role">
        <button type="button" class="chip" aria-pressed=${String(!filters.roles.length)} onClick=${() => patchFilters({ roles: [] })}>All</button>
        ${ROLE_ORDER.map((r) => html`<button type="button" key=${r} class="chip" aria-pressed=${String(filters.roles.includes(r))} onClick=${() => patchFilters({ roles: toggle(filters.roles, r) })}>${ctx.roles.plural[r]} <span class="muted">${roleCounts.get(r) || 0}</span></button>`)}
      </div>
    </div>` : null}

    <div class="fb-row">
      <span class="fb-label">Filter</span>
      ${has("positions") ? html`<${Popover} label="Position" summary=${filters.positions.length ? String(filters.positions.length) : ""} active=${filters.positions.length > 0} width=${340}>
        <${PositionPanel} ctx=${ctx} counts=${posCounts} value=${filters.positions} onChange=${(v) => patchFilters({ positions: v })} unknown=${unknownPos} />
      </${Popover}>` : null}
      ${has("tags") ? html`<${Popover} label="Profile" summary=${filters.tags.length ? String(filters.tags.length) : ""} active=${filters.tags.length > 0} width=${380}>
        <${ProfilePanel} ctx=${ctx} counts=${tagCounts} value=${filters.tags} onChange=${(v) => patchFilters({ tags: v })} />
      </${Popover}>` : null}
      ${has("clubs") ? html`<${Popover} label="Club" summary=${filters.clubs.length ? String(filters.clubs.length) : ""} active=${filters.clubs.length > 0} width=${300}>
        <${ClubList} options=${clubList} value=${filters.clubs} onChange=${(v) => patchFilters({ clubs: v })} />
      </${Popover}>` : null}
      ${has("formations") ? html`<${Popover} label="Formation" summary=${filters.formations.length ? String(filters.formations.length) : ""} active=${filters.formations.length > 0} width=${240}>
        <${FormationList} counts=${formCounts} value=${filters.formations} onChange=${(v) => patchFilters({ formations: v })} />
      </${Popover}>` : null}
      ${has("minutes") ? html`<${Popover} label="Minutes" summary=${filters.minutes ? `${filters.minutes}+` : "Any"} active=${filters.minutes > 0} width=${300}>
        <${MinutesPanel} value=${filters.minutes} onChange=${(v) => patchFilters({ minutes: v })} poolMinutes=${config.poolMinutes} />
      </${Popover}>` : null}
      ${has("age") ? html`<${Popover} label="Age" summary=${filters.age ? `${filters.age[0]}–${filters.age[1]}` : "Any"} active=${Boolean(filters.age)} width=${320}>
        <${AgePanel} state=${filters} onChange=${patchFilters} ageRef=${config.ageRef} unknownCount=${unknownAge} />
      </${Popover}>` : null}
      ${has("part") ? html`<${Popover} label="Playing time" summary=${filters.part ? (filters.part === "starter" ? "Starters" : "Rotation") : "Any"} active=${Boolean(filters.part)} width=${300}>
        <div class="stack" style=${{ "--gap": "10px" }}>
          <${Select} value=${filters.part} label="Role in the team" options=${[{ value: "", label: "Anyone" }, { value: "starter", label: "Regular starters (60%+ of team minutes)" }, { value: "rotation", label: "Rotation and bench (under 60%)" }]} onChange=${(v) => patchFilters({ part: v })} />
          <p class="xsmall muted">Minutes as a share of everything his club played. Useful for finding players who are good but not yet playing.</p>
        </div>
      </${Popover}>` : null}
      ${has("rule") ? html`<${Popover} label="Metric filter" icon="plus" active=${editing != null} width=${400} open=${editing != null} onOpenChange=${(o) => setEditing(o ? { index: -1, rule: null } : null)} title=${`Keep only ${config.noun} whose value (or percentile) on any metric is above or below a limit`}>
        <${RuleEditor} ctx=${ctx} rows=${allRows} state=${filters} editing=${editing} level=${config.level}
          onSubmit=${(rule, index) => { setFilters((s) => ({ ...s, rules: index >= 0 ? s.rules.map((r, i) => (i === index ? rule : r)) : [...s.rules, rule] })); setEditing(null); }}
          onCancel=${() => setEditing(null)} />
      </${Popover}>` : null}
    </div>

    <${LensBar} model=${model} allRows=${allRows} noun=${config.noun} onShowColumns=${onShowColumns} onSortBy=${onSortBy} />

    <div class="active-strip" aria-label="Active filters">
      ${chips.length
        ? chips.map((c) => html`<span key=${c.id} class=${cls("fchip", c.kind)} title=${c.title}>
            ${c.kind === "rule" ? html`<button type="button" class="edit" onClick=${() => setEditing({ index: c.index, rule: c.rule })} aria-label=${`Edit filter ${c.text}`}>${c.text}</button>` : html`<span>${c.text}</span>`}
            <button type="button" class="x" aria-label=${`Remove filter ${c.text}`} onClick=${() => setFilters(c.next)}><${Icon} name="x" /></button>
          </span>`)
        : html`<span class="xsmall muted">No filters: every ${config.level === "team" ? "team" : "player"} in this selection is listed. Pick ${config.level === "team" ? "a formation, a lens" : "a role, a profile, a lens"} or add a metric filter to narrow it down.</span>`}
    </div>
  </section>`;
}

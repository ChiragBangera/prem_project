// The filter rail of the explorer desk: every way to narrow the list, always in view beside the table. Nothing here starts selected.
// Age and minutes are drawn as a histogram of the rows being cut, so the cut is seen before it is made. Each table picks the parts it needs.
import { html, useEffect, useMemo, useState } from "../../lib/html.js";
import { Icon } from "../../lib/icons.js";
import { cls, debounce, fold, formation } from "../../lib/format.js";
import { navigate, setQuery } from "../../lib/router.js";
import { ui, useStore } from "../../lib/store.js";
import { ROLE_ORDER, customCols, describeRule, lensCount, predicateFor, quantile, stateToQuery, sureAge } from "../../lib/filters.js";
import { blank, fmtMetric } from "../../lib/metricfmt.js";
import { Button, SearchBox, Switch } from "../common.js";
import { MetricSelect } from "./MetricSelect.js";

const AGE = [15, 45];
const toggle = (list, v) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);

/** Which parts of the rail each kind of table shows, in order. */
export const RAIL_PARTS = {
  player: ["role", "age", "minutes", "rules", "ready", "profile", "club", "kept"],
  squad: ["role", "age", "minutes", "rules", "ready", "profile"],
  match: ["side", "role", "minutes", "rules"],
  team: ["formation", "rules", "ready", "kept"],
};

/** Counts per value of one facet, with that facet's own filter ignored (so a chip shows what clicking it would add). */
export function facet(rows, state, ctx, own, values) {
  const cleared = { ...state, [own]: Array.isArray(state[own]) ? [] : own === "minutes" ? 0 : "" };
  const pass = predicateFor(cleared, ctx);
  const counts = new Map();
  for (const r of rows) {
    if (!pass(r)) continue;
    for (const v of values(r)) if (v != null) counts.set(v, (counts.get(v) || 0) + 1);
  }
  return counts;
}

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

function ProfilePanel({ ctx, counts, value, onChange }) {
  const groups = ROLE_ORDER.map((role) => ({ role, tags: ctx.tagList.filter((t) => t.group === role) })).filter((g) => g.tags.length);
  return html`<div class="stack" style=${{ "--gap": "10px", maxHeight: "420px", overflow: "auto", paddingRight: "4px" }}>
    ${groups.map((g) => html`<div key=${g.role} class="stack" style=${{ "--gap": "2px" }}>
      <span class="eyebrow" style=${{ padding: "4px 8px" }}>${ctx.roles.plural[g.role]}</span>
      ${g.tags.map((t) => html`<${Check} key=${t.key} on=${value.includes(t.key)} label=${t.label} sub=${t.blurb} hint=${counts.get(t.key) || 0} disabled=${!counts.get(t.key) && !value.includes(t.key)} onClick=${() => onChange(toggle(value, t.key))} />`)}
    </div>`)}
    <p class="xsmall muted">Profiles are labels earned by simple rules on percentiles (for example “top 15% of defenders for build-up”). The Data dictionary lists every rule. Players under 270 minutes are not labelled.</p>
  </div>`;
}

/** Counts of `values` in equal bins between lo and hi, as bars; the bars inside [from, to] are lit. */
export function HistBars({ values, lo, hi, bins = 26, from = -Infinity, to = Infinity, label }) {
  const counts = new Array(bins).fill(0);
  const width = (hi - lo) / bins || 1;
  for (const v of values) counts[Math.max(0, Math.min(bins - 1, Math.floor((v - lo) / width)))] += 1;
  const top = Math.max(1, ...counts);
  return html`<div class="dk-hist" role="img" aria-label=${label}>${counts.map((n, i) => {
    const mid = lo + (i + 0.5) * width;
    return html`<i key=${i} class=${mid >= from && mid <= to ? "in" : ""} style=${{ height: (100 * n) / top + "%" }}></i>`;
  })}</div>`;
}

/** One or two handles on a track. The value follows the handle while it moves and is handed over when it is let go. */
function Handles({ min, max, step = 1, value, onCommit, onLive, label }) {
  const [live, setLive] = useState(value);
  useEffect(() => setLive(value), [value.join()]);
  const set = (i, v) => { const next = [...live]; next[i] = Number(v); setLive(next); onLive && onLive(next); };
  const done = () => onCommit([...live].sort((a, b) => a - b));
  return html`<div class="dk-handles">${live.map((v, i) => html`<input key=${i} type="range" min=${min} max=${max} step=${step} value=${v} aria-label=${live.length > 1 ? `${label}, ${i ? "upper" : "lower"} limit` : label}
    onInput=${(e) => set(i, e.target.value)} onChange=${done} />`)}</div>`;
}

function Facet({ title, state, children, action }) {
  return html`<section class="dk-facet"><header><b>${title}</b>${state != null ? html`<span>${state}</span>` : null}${action || null}</header>${children}</section>`;
}

/** A section that stays shut until asked for, with what is chosen in it beside its name. */
function Fold({ title, state, children, open: start = false }) {
  const [open, setOpen] = useState(start);
  return html`<section class="dk-facet dk-fold">
    <button type="button" class="dk-foldhead" aria-expanded=${String(open)} onClick=${() => setOpen(!open)}><${Icon} name=${open ? "chevronDown" : "chevronRight"} size="sm" /><b>${title}</b>${state ? html`<span>${state}</span>` : null}</button>
    ${open ? children : null}
  </section>`;
}

/** One measure rule: its name, what it keeps in words, and a handle to move the limit. */
function RuleCard({ rule, index, model, allRows, peerWord }) {
  const { ctx, setFilters } = model;
  const def = ctx.metrics[rule.metric];
  const i = ctx.idx[rule.metric];
  const values = useMemo(() => allRows.map((r) => r.v[i]).filter((v) => !blank(v)).sort((a, b) => a - b), [allRows, i]);
  const put = (next) => setFilters((s) => ({ ...s, rules: s.rules.map((r, j) => (j === index ? next : r)) }));
  const drop = () => setFilters((s) => ({ ...s, rules: s.rules.filter((_, j) => j !== index) }));
  const share = def?.unit === "share";
  const [live, setLive] = useState(null);
  const shown = live ?? rule;
  const byRank = rule.on === "pct";
  const swap = () => put(byRank
    ? { ...rule, on: "value", value: Number((values.length ? quantile(values, rule.value / 100) : 0).toFixed(share ? 3 : def?.decimals ?? 2)) }
    : { ...rule, on: "pct", value: rule.op === ">=" ? 75 : 25 });
  return html`<div class="dk-rule">
    <div class="dk-rule-top"><b title=${def?.what}>${def?.label || rule.metric}</b><button type="button" aria-label=${`Remove the ${def?.label || rule.metric} rule`} onClick=${drop}><${Icon} name="x" size="sm" /></button></div>
    ${byRank
      ? html`<input type="range" min="1" max="99" value=${shown.value} aria-label=${`${def?.label}: rank within the ${peerWord}`}
          onInput=${(e) => setLive({ ...rule, value: Number(e.target.value) })} onChange=${(e) => { setLive(null); put({ ...rule, value: Number(e.target.value) }); }} />`
      : html`<input class="input dk-num" type="number" step=${share ? 1 : 10 ** -(def?.decimals ?? 2)} value=${share ? Math.round(rule.value * 1000) / 10 : rule.value} aria-label=${`${def?.label}: limit`}
          onChange=${(e) => { const n = Number(e.target.value); if (Number.isFinite(n)) put({ ...rule, value: share ? n / 100 : n }); }} />`}
    <div class="dk-rule-say">${byRank ? describeRule(shown, ctx, fmtMetric, true).replace(/^[^:]+:\s*/, "").replace(/^./, (c) => c.toUpperCase()) : `${rule.op === ">=" ? "At least" : "At most"} ${fmtMetric(def, rule.value)}`}</div>
    <div class="dk-rule-acts">
      <button type="button" class="linklike" onClick=${() => put({ ...rule, op: rule.op === ">=" ? "<=" : ">=", value: byRank ? 100 - rule.value : rule.value })}>${rule.op === ">=" ? "Switch to at most" : "Switch to at least"}</button>
      <button type="button" class="linklike" onClick=${swap}>${byRank ? "Use the number itself" : `Use rank in the ${peerWord}`}</button>
    </div>
  </div>`;
}

/** A ready-made search (a lens): what it keeps is spelled out, and its rules can be taken over and edited one by one. */
function ReadyMade({ model, allRows, noun }) {
  const { ctx, filters, setFilters, write } = model;
  const key = JSON.stringify(filters);
  const counts = useMemo(() => Object.fromEntries(ctx.lensList.map((l) => [l.key, lensCount(allRows, filters, ctx, l.key)])), [allRows, key, ctx]);
  const [all, setAll] = useState(false);
  const on = (k) => filters.lenses.includes(k);
  const flip = (lens) => {
    if (on(lens.key)) { setFilters((s) => ({ ...s, lenses: s.lenses.filter((x) => x !== lens.key) })); return; }
    // switching one on also shows the measures it looks at and ranks by its main one: the list then reads as the answer to its question
    const cols = lens.show.filter((k) => ctx.idx[k] !== undefined);
    const hib = ctx.metrics[lens.sort]?.hib;
    (write || setQuery)({ ...stateToQuery({ ...filters, lenses: [...filters.lenses, lens.key] }), ...(cols.length ? { cols: customCols(cols) } : {}), ...(lens.sort && ctx.idx[lens.sort] !== undefined ? { sort: lens.sort, dir: hib === false ? "asc" : null } : {}) });
  };
  const takeOver = (lens) => setFilters((s) => ({ ...s, lenses: s.lenses.filter((x) => x !== lens.key), rules: [...s.rules, ...lens.rules],
    roles: lens.roles?.length && !s.roles.length ? [...lens.roles] : s.roles }));
  const list = all ? ctx.lensList : ctx.lensList.filter((l, i) => i < 8 || on(l.key));
  if (!ctx.lensList.length) return null;
  return html`<${Facet} title="Ready-made searches">
    <div class="dk-ready">${list.map((l) => html`<div key=${l.key} class=${cls("dk-ready-item", on(l.key) && "on")}>
      <button type="button" class="dk-ready-btn lens" aria-pressed=${String(on(l.key))} title=${l.blurb} onClick=${() => flip(l)}><span>${l.label}</span><span class="n">${counts[l.key].toLocaleString("en-GB")}</span></button>
      ${on(l.key) ? html`<div class="dk-ready-why">
        <p>${l.explain || l.blurb}</p>
        <ul class="plain">${l.rules.map((r, i) => html`<li key=${i}>${describeRule(r, ctx, fmtMetric, true)}</li>`)}${l.roles?.length ? html`<li>${l.roles.map((r) => ctx.roles.plural[r].toLowerCase()).join(" and ")} only</li>` : null}</ul>
        <div class="dk-rule-acts"><button type="button" class="linklike" onClick=${() => takeOver(l)} title="Turn these into your own rules above, where each limit can be moved">Edit these rules</button>
          <button type="button" class="linklike" onClick=${() => flip(l)}>Switch off</button></div>
      </div>` : null}
    </div>`)}</div>
    ${ctx.lensList.length > 8 ? html`<button type="button" class="linklike" onClick=${() => setAll(!all)}>${all ? "Show fewer" : `Show all ${ctx.lensList.length}`}</button>` : null}
    <p class="dk-note">Each one filters the ${noun}, shows the measures it looks at and ranks by its main one.</p>
  </${Facet}>`;
}

/** Searches the user has kept: a name and the address it stands for, stored on this computer. */
function Kept({ level, path, query }) {
  const kept = useStore(ui, (s) => s.keptSearches)?.[level] || [];
  const [name, setName] = useState("");
  const save = (e) => {
    e.preventDefault();
    const n = name.trim();
    if (!n) return;
    ui.set((s) => ({ keptSearches: { ...(s.keptSearches || {}), [level]: [...kept.filter((k) => k.name !== n), { name: n, query }] } }));
    setName("");
  };
  const drop = (n) => ui.set((s) => ({ keptSearches: { ...(s.keptSearches || {}), [level]: kept.filter((k) => k.name !== n) } }));
  return html`<${Facet} title="Your searches">
    ${kept.length ? html`<div class="dk-ready">${kept.map((k) => html`<div key=${k.name} class="dk-ready-item"><div class="dk-kept">
      <button type="button" class="dk-ready-btn" onClick=${() => navigate(path, k.query)}><span>${k.name}</span></button>
      <button type="button" class="dk-x" aria-label=${`Delete the search ${k.name}`} onClick=${() => drop(k.name)}><${Icon} name="x" size="sm" /></button></div></div>`)}</div>` : null}
    <form class="dk-keep" onSubmit=${save}><input class="input" placeholder="Name this search to keep it" value=${name} onInput=${(e) => setName(e.target.value)} aria-label="Name for this search" /><${Button} size="sm" type="submit" disabled=${!name.trim()}>Keep</${Button}></form>
  </${Facet}>`;
}

const SEASON_MINUTES = { steps: [0, 270, 450, 900], step: 30, part: [["", "Anyone"], ["starter", "Regular starters", "60% or more of his club's minutes"], ["rotation", "Rotation and bench", "Under 60% of his club's minutes"]] };
const MATCH_MINUTES = { steps: [0, 30, 45, 60, 90], step: 1, part: [["", "Anyone"], ["starter", "Started"], ["rotation", "Came on"]] };

/**
 * model: from useExplorer(). allRows: the rows before filtering. config: { level, kind (a key of RAIL_PARTS), noun, searchPlaceholder, sides }.
 * `sides` names the two teams of a match ({ value: team, label }). head: what sits at the top of the rail (the page's name and what is
 * loaded). path and query: where "Your searches" lead back to.
 */
export function Rail({ model, allRows, config, head, path, query }) {
  const { ctx, filters, patchFilters, setFilters } = model;
  const parts = new Set(RAIL_PARTS[config.kind || config.level] || RAIL_PARTS.player);
  const team = config.level === "team";
  const match = config.kind === "match";
  const peerWord = team ? "league" : "role";
  const [text, setText] = useState(filters.q);
  const push = useMemo(() => debounce((v) => patchFilters({ q: v }), 220), [patchFilters]);
  useEffect(() => setText(filters.q), [filters.q]);
  const key = JSON.stringify(filters);

  const roleCounts = useMemo(() => facet(allRows, filters, ctx, "roles", (r) => [r.group]), [allRows, key, ctx]);
  const posCounts = useMemo(() => facet(allRows, filters, ctx, "positions", (r) => [r.pos2]), [allRows, key, ctx]);
  const tagCounts = useMemo(() => (parts.has("profile") ? facet(allRows, filters, ctx, "tags", (r) => (r.tags || []).map((t) => t.key)) : new Map()), [allRows, key, ctx]);
  const clubCounts = useMemo(() => facet(allRows, filters, ctx, "clubs", (r) => r.teams || [r.team]), [allRows, key, ctx]);
  const formCounts = useMemo(() => (parts.has("formation") ? facet(allRows, filters, ctx, "formations", (r) => [r.formation]) : new Map()), [allRows, key, ctx]);
  const allClubs = useMemo(() => [...new Set(allRows.flatMap((r) => r.teams || [r.team]))].sort(), [allRows]);
  // the histograms count the rows every other filter leaves, so a handle is moved against the list it will cut
  const ages = useMemo(() => { const pass = predicateFor({ ...filters, age: null }, ctx); return allRows.filter(pass).map(sureAge).filter((a) => a != null); }, [allRows, key, ctx]);
  const mIdx = ctx.idx.minutes;
  const minutes = useMemo(() => { const pass = predicateFor({ ...filters, minutes: 0 }, ctx); return mIdx === undefined ? [] : allRows.filter(pass).map((r) => r.v[mIdx]).filter((v) => !blank(v)); }, [allRows, key, ctx]);
  const maxMin = useMemo(() => (mIdx === undefined ? 0 : Math.max(90, ...allRows.map((r) => r.v[mIdx] || 0))), [allRows, mIdx]);
  const unknownAge = useMemo(() => allRows.filter((r) => sureAge(r) == null).length, [allRows]);
  const anyAge = unknownAge < allRows.length;
  const [ageLive, setAgeLive] = useState(null), [minLive, setMinLive] = useState(null);
  useEffect(() => { setAgeLive(null); setMinLive(null); }, [key]);
  const age = ageLive || filters.age || AGE, minNow = minLive ?? filters.minutes;
  const mins = match ? MATCH_MINUTES : SEASON_MINUTES;

  const roles = filters.roles.length ? ROLE_ORDER.filter((r) => filters.roles.includes(r)) : ROLE_ORDER;
  const positions = ctx.positions.order.filter((p) => roles.includes(ctx.positions.group[p]) && (!match || posCounts.has(p) || filters.positions.includes(p)));
  const used = new Set(filters.rules.map((r) => r.metric));
  const formations = [...formCounts.entries()].sort((a, b) => b[1] - a[1] || String(a[0]).localeCompare(String(b[0])));

  return html`<aside class="dk-rail" aria-label="Filters">
    ${head || null}
    <${SearchBox} value=${text} onInput=${(v) => { setText(v); push(v); }} placeholder=${config.searchPlaceholder || "Search by name or club"} />

    ${parts.has("side") && config.sides?.length ? html`<${Facet} title="Team">
      <div class="dk-chips" role="group" aria-label="Team">
        <button type="button" class="chip" aria-pressed=${String(!filters.clubs.length)} onClick=${() => patchFilters({ clubs: [] })}>Both</button>
        ${config.sides.map((s) => html`<button type="button" key=${s.value} class="chip" aria-pressed=${String(filters.clubs.length === 1 && filters.clubs[0] === s.value)}
          onClick=${() => patchFilters({ clubs: filters.clubs.length === 1 && filters.clubs[0] === s.value ? [] : [s.value] })}>${s.dot ? html`<i class="dk-dot" style=${{ background: s.dot }}></i>` : null}${s.label} <span class="muted">${clubCounts.get(s.value) || 0}</span></button>`)}
      </div>
    </${Facet}>` : null}

    ${parts.has("formation") ? html`<${Facet} title="Usual formation" state=${filters.formations.length ? `${filters.formations.length} chosen` : "Any"}>
      ${formations.length ? html`<div class="dk-chips" role="group" aria-label="Formation">${formations.map(([f, n]) => html`<button type="button" key=${f} class="chip" aria-pressed=${String(filters.formations.includes(f))}
        onClick=${() => patchFilters({ formations: toggle(filters.formations, f) })}>${formation(f) || f} <span class="muted">${n}</span></button>`)}</div>
        <p class="dk-note">The shape a team started most of its matches in, from the line-ups.</p>`
        : html`<p class="dk-note">Formations come from event data, which is not stored for this selection.</p>`}
    </${Facet}>` : null}

    ${parts.has("role") ? html`<${Facet} title="Role">
      <div class="dk-chips" role="group" aria-label="Role">
        <button type="button" class="chip" aria-pressed=${String(!filters.roles.length)} onClick=${() => patchFilters({ roles: [], positions: [] })}>All</button>
        ${ROLE_ORDER.map((r) => html`<button type="button" key=${r} class="chip" aria-pressed=${String(filters.roles.includes(r))} onClick=${() => patchFilters({ roles: toggle(filters.roles, r) })}>${ctx.roles.plural[r]} <span class="muted">${roleCounts.get(r) || 0}</span></button>`)}
      </div>
      ${filters.roles.length || filters.positions.length ? html`<div class="dk-chips dk-sub" role="group" aria-label="Position">${positions.map((p) => html`<button type="button" key=${p} class="chip" aria-pressed=${String(filters.positions.includes(p))}
        onClick=${() => patchFilters({ positions: toggle(filters.positions, p) })}>${ctx.positions.labels[p]} <span class="muted">${posCounts.get(p) || 0}</span></button>`)}</div>` : html`<p class="dk-note">Pick a role to choose positions within it.</p>`}
    </${Facet}>` : null}

    ${parts.has("age") && anyAge ? html`<${Facet} title="Age" state=${age[0] === AGE[0] && age[1] === AGE[1] ? "Any" : `${age[0]} to ${age[1]}`}>
      <${HistBars} values=${ages} lo=${AGE[0]} hi=${AGE[1] + 1} bins=${31} from=${age[0]} to=${age[1] + 0.99} label="How many players there are at each age" />
      <${Handles} min=${AGE[0]} max=${AGE[1]} value=${age} label="Age" onLive=${setAgeLive} onCommit=${(v) => patchFilters({ age: v[0] === AGE[0] && v[1] === AGE[1] ? null : v })} />
      <div class="dk-scale"><span>15</span><span>25</span><span>35</span><span>45</span></div>
      ${filters.age ? html`<${Switch} checked=${filters.ageUnknown} onChange=${(v) => patchFilters({ ageUnknown: v })}>Keep players of unknown age${unknownAge ? ` (${unknownAge})` : ""}</${Switch}>` : null}
    </${Facet}>` : null}

    ${parts.has("minutes") && mIdx !== undefined ? html`<${Facet} title=${match ? "Minutes in this match" : "Minutes played"} state=${minNow ? `${minNow} or more` : "Any"}>
      <${HistBars} values=${minutes} lo=${0} hi=${maxMin + 1} bins=${30} from=${minNow} label="How many players have played how many minutes" />
      <${Handles} min=${0} max=${maxMin} step=${mins.step} value=${[minNow]} label="Fewest minutes played" onLive=${(v) => setMinLive(v[0])} onCommit=${(v) => patchFilters({ minutes: v[0] })} />
      <div class="dk-chips dk-sub">${mins.steps.filter((m) => m <= maxMin).map((m) => html`<button type="button" key=${m} class="chip" aria-pressed=${String(filters.minutes === m)} onClick=${() => patchFilters({ minutes: m })}>${m === 0 ? "Any" : `${m}+`}</button>`)}</div>
      <div class="dk-chips dk-sub" role="group" aria-label=${match ? "Started or came on" : "Role in the team"}>${mins.part.map(([v, w, why]) => html`<button type="button" key=${v} class="chip" aria-pressed=${String(filters.part === v)}
        title=${why} onClick=${() => patchFilters({ part: v })}>${w}</button>`)}</div>
      ${match ? html`<p class="dk-note">A rate from a few minutes can top any list, so players under 30 minutes are not ranked against the season.</p>` : null}
    </${Facet}>` : null}

    ${parts.has("rules") ? html`<${Facet} title=${team ? "What they are good at" : match ? "What he did in this match" : "What he is good at"} state=${filters.rules.length ? `${filters.rules.length} ${filters.rules.length === 1 ? "rule" : "rules"}` : null}>
      ${filters.rules.map((r, i) => html`<${RuleCard} key=${`${r.metric}:${i}`} rule=${r} index=${i} model=${model} allRows=${allRows} peerWord=${peerWord} />`)}
      <${MetricSelect} ctx=${ctx} value="" label="Add a rule on a measure" extra=${[{ value: "", label: filters.rules.length ? "Add another measure…" : "Add a measure…" }]} only=${(k) => !used.has(k)}
        onChange=${(k) => { if (k) setFilters((s) => ({ ...s, rules: [...s.rules, { metric: k, op: ctx.metrics[k]?.hib === false ? "<=" : ">=", on: ctx.metrics[k]?.hib === false ? "value" : "pct", value: ctx.metrics[k]?.hib === false ? 0 : 75 }] })); }} />
      <p class="dk-note">${team ? "A rule ranks each team against the others in its league, or uses the number itself." : match ? "A rule ranks his number in this match against the season's players in his role, or uses the number itself." : "A rule ranks each player against others in his own role, or uses the number itself."} Any column heading adds one too.</p>
    </${Facet}>` : null}

    ${parts.has("ready") ? html`<${ReadyMade} model=${model} allRows=${allRows} noun=${config.noun} />` : null}

    ${parts.has("profile") && ctx.tagList.length ? html`<${Fold} title="Profile" state=${filters.tags.length ? `${filters.tags.length} chosen` : ""} open=${filters.tags.length > 0}>
      <${ProfilePanel} ctx=${ctx} counts=${tagCounts} value=${filters.tags} onChange=${(v) => patchFilters({ tags: v })} /></${Fold}>` : null}
    ${parts.has("club") ? html`<${Fold} title="Club" state=${filters.clubs.length ? `${filters.clubs.length} chosen` : ""} open=${filters.clubs.length > 0}>
      <${ClubList} options=${allClubs.map((c) => ({ value: c, label: c, count: clubCounts.get(c) || 0 }))} value=${filters.clubs} onChange=${(v) => patchFilters({ clubs: v })} /></${Fold}>` : null}

    ${parts.has("kept") ? html`<${Kept} level=${config.level} path=${path} query=${query} />` : null}
  </aside>`;
}

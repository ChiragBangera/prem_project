// Scout: find players by what they do. Filters and lenses on top, one dense table (or a map) below.
import { html, useEffect, useMemo, useState } from "../lib/html.js";
import { useApi } from "../lib/api.js";
import { useScope, useMeta, leagueName } from "../lib/scope.js";
import { navigate, setQuery, useLocation, href } from "../lib/router.js";
import { fold, nf, plural, signed, debounce, cls, seasonLabel } from "../lib/format.js";
import { Tip } from "../lib/tooltip.js";
import { Icon } from "../lib/icons.js";
import { shortlistStore, useStore } from "../lib/store.js";
import { PctCell, PlayerCell, ScoreCell, TagCell } from "../ui/cells.js";
import { Async, Button, ChecklistChip, DataNotices, EmptyState, Field, Insights, Notice, PageHead, Popover, RangeSlider, SearchBox, Segmented, Select, Star, Switch, playerHref, useDocumentTitle, metricValue, POS_LABEL } from "../ui/common.js";
import { CsvButton, DataTable } from "../ui/table.js";
import { Scatter } from "../charts/scatter.js";
import { seqColor } from "../charts/core.js";
import { SERIES_COLORS } from "../charts/lines.js";
import { Legend } from "../charts/core.js";

const GROUPS = [
  { value: "ATT", label: "Attackers" }, { value: "MID", label: "Midfielders" },
  { value: "DEF", label: "Defenders" }, { value: "GK", label: "Goalkeepers" },
];
const DEFAULT_GROUPS = ["ATT", "MID", "DEF"];
const MIXED = ["contrib90", "npxg90", "xa90", "xgchain90", "xgbuildup90", "shots90"];
const MAP_METRICS = ["npxg90", "xa90", "contrib90", "shots90", "kp90", "xgps", "xgchain90", "xgbuildup90", "goals90", "g_xg", "output", "minutes"];
const GROUP_COLOR = { ATT: "var(--c2)", MID: "var(--c1)", DEF: "var(--c3)", GK: "var(--c4)" };

/** Lenses: each is a saved question. They only set filters and a sort, so the result is always inspectable. */
const PRESETS = [
  { key: "best", label: "Best overall", hint: "Highest role score among regulars", patch: { groups: null, sort: "output", dir: "desc", luck: null, part: null, age: null } },
  { key: "goals", label: "Goal threats", hint: "Attackers ranked by non-penalty xG per 90", patch: { groups: "ATT", sort: "npxg90", dir: "desc", luck: null, part: null, age: null } },
  { key: "create", label: "Creators", hint: "Attackers and midfielders ranked by xA per 90", patch: { groups: "ATT,MID", sort: "xa90", dir: "desc", luck: null, part: null, age: null } },
  { key: "progress", label: "Ball progressors", hint: "Midfielders and defenders by xGBuildup per 90", patch: { groups: "MID,DEF", sort: "xgbuildup90", dir: "desc", luck: null, part: null, age: null } },
  { key: "unlucky", label: "Unlucky finishers", hint: "Scoring well below their xG: goals may follow", patch: { groups: "ATT,MID", luck: "under", sort: "g_xg_z", dir: "asc", part: null, age: null } },
  { key: "hot", label: "Running hot", hint: "Scoring well above xG: expect a slowdown", patch: { groups: "ATT,MID", luck: "over", sort: "g_xg_z", dir: "desc", part: null, age: null } },
  { key: "gems", label: "Hidden gems", hint: "Strong role score but not yet regular starters", patch: { groups: null, part: "rotation", sort: "output", dir: "desc", luck: null, age: null } },
  { key: "young", label: "Young and good", hint: "Aged 23 or under, ranked by role score", patch: { groups: null, age: "16-23", unk: "0", sort: "output", dir: "desc", luck: null, part: null } },
];

const csvList = (v) => (v ? v.split(",").filter(Boolean) : []);

function readFilters(query, scope) {
  const [ageLo, ageHi] = (query.age || "").split("-").map(Number);
  return {
    groups: query.groups !== undefined ? csvList(query.groups) : DEFAULT_GROUPS,
    leagues: csvList(query.leagues),
    seasons: csvList(query.seasons),
    minutes: query.min ? Number(query.min) : 450,
    age: Number.isFinite(ageLo) && Number.isFinite(ageHi) && query.age ? [ageLo, ageHi] : [16, 40],
    ageOn: Boolean(query.age),
    unknownAge: query.unk !== "0",
    q: query.q || "",
    teams: (query.team || "").split("|").filter(Boolean),
    part: query.part || "",
    luck: query.luck || "",
    small: query.small !== "0", // hide players below the role-pool minutes by default? no: this hides tiny samples
    sort: query.sort || "output",
    dir: query.dir || "desc",
    view: query.view === "map" ? "map" : "table",
    mx: query.mx || "xa90",
    my: query.my || "npxg90",
    cmp: (query.cmp || "").split(",").filter(Boolean).map(Number),
    preset: query.preset || "",
  };
}

function applyFilters(rows, f) {
  const needle = fold(f.q);
  const teams = new Set(f.teams);
  return rows.filter((r) => {
    if (f.groups.length && !f.groups.includes(r.group)) return false;
    if (r.minutes < f.minutes) return false;
    if (f.small && !r.in_pool && f.minutes >= 90 && r.minutes < 270) return false;
    if (needle && !fold(`${r.name} ${r.team}`).includes(needle)) return false;
    if (teams.size && !r.teams.some((t) => teams.has(t))) return false;
    if (f.ageOn) {
      if (r.age == null) { if (!f.unknownAge) return false; }
      else if (r.age < f.age[0] || r.age > f.age[1]) return false;
    }
    if (f.part === "starter" && r.minutes_share < 0.6) return false;
    if (f.part === "rotation" && r.minutes_share >= 0.6) return false;
    if (f.luck === "over" && !(r.g_xg_z >= 1.2)) return false;
    if (f.luck === "under" && !(r.g_xg_z <= -1.2)) return false;
    return true;
  });
}

function metricKeys(groups, catalog) {
  if (groups.length === 1 && groups[0] !== "GK" && catalog.profiles[groups[0]]) return catalog.profiles[groups[0]].filter((k) => k !== "yellow90").slice(0, 6);
  return MIXED;
}

// ------------------------------------------------------------------ filter bar

function FilterBar({ f, set, meta, rowsAll, scope }) {
  const teamOptions = useMemo(() => [...new Set(rowsAll.flatMap((r) => r.teams))].sort().map((t) => ({ value: t, label: t })), [rowsAll]);
  const [text, setText] = useState(f.q);
  const push = useMemo(() => debounce((v) => set({ q: v || null }), 220), []);
  useEffect(() => setText(f.q), [f.q]);
  const extra = [f.teams.length, f.leagues.length, f.seasons.length, f.part, f.luck].filter(Boolean).length;
  const toggleIn = (list, v) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);
  return html`<div class="filterbar">
    <div class="filter-row">
      <${SearchBox} value=${text} onInput=${(v) => { setText(v); push(v); }} placeholder="Search player or team" width="230px" />
      <div class="chipgroup" role="group" aria-label="Role">
        ${GROUPS.map((g) => html`<button type="button" class="chip" key=${g.value} aria-pressed=${String(f.groups.includes(g.value))}
          onClick=${() => set({ groups: toggleIn(f.groups, g.value).join(","), preset: null })}>${g.label}</button>`)}
      </div>
      <span class="spacer"></span>
      <${Popover} label="Minutes" summary=${`≥ ${f.minutes}`} active=${f.minutes !== 450} width=${280} align="right">
        <${RangeSlider} label="Minimum minutes" min=${90} max=${2700} step=${90} value=${[f.minutes, 2700]} format=${(v) => v} onChange=${([lo]) => set({ min: lo === 450 ? null : lo })} />
        <p class="xsmall muted">Per-90 rates swing wildly under about 450 minutes. Below that, players are marked small sample and cannot top a ranking on a cameo.</p>
      </${Popover}>
      <${Popover} label="Age" summary=${f.ageOn ? `${f.age[0]}–${f.age[1]}` : "Any"} active=${f.ageOn} width=${290} align="right">
        <${RangeSlider} label="Age range" min=${16} max=${40} value=${f.age} format=${(v) => v} onChange=${(v) => set({ age: v[0] === 16 && v[1] === 40 ? null : `${v[0]}-${v[1]}`, preset: null })} />
        <${Switch} checked=${f.unknownAge} onChange=${(v) => set({ unk: v ? null : "0" })}>Include players whose age is unknown</${Switch}>
        <p class="xsmall muted">Ages come from Wikidata, matched by name and club. Where there is no unambiguous match the age stays blank.</p>
      </${Popover}>
      <${Popover} label="More" summary=${extra ? `${extra} on` : ""} active=${extra > 0} width=${340} align="right">
        <${Field} label="Leagues">
          <div class="chipgroup">${meta.leagues.map((l) => html`<button type="button" class="chip" key=${l.code} aria-pressed=${String((f.leagues.length ? f.leagues : [scope.league]).includes(l.code))}
            onClick=${() => { const cur = f.leagues.length ? f.leagues : [scope.league]; const next = toggleIn(cur, l.code); set({ leagues: next.length && !(next.length === 1 && next[0] === scope.league) ? next.join(",") : null }); }}>${l.short || l.code}</button>`)}</div>
        </${Field}>
        <${Field} label="Seasons" hint="Several seasons are pooled into one profile.">
          <div class="chipgroup">${meta.seasons.slice(0, 8).map((s) => html`<button type="button" class="chip" key=${s.season} aria-pressed=${String(f.seasons.includes(String(s.season)))}
            onClick=${() => set({ seasons: toggleIn(f.seasons, String(s.season)).join(",") || null })}>${s.label}</button>`)}</div>
        </${Field}>
        <${Field} label="Club"><${ChecklistChipInline} options=${teamOptions} value=${f.teams} onChange=${(v) => set({ team: v.join("|") || null })} /></${Field}>
        <${Field} label="Role in the team">
          <${Select} value=${f.part} label="Role in the team" options=${[{ value: "", label: "Anyone" }, { value: "starter", label: "Regular starters (60%+ of team minutes)" }, { value: "rotation", label: "Rotation and bench (under 60%)" }]} onChange=${(v) => set({ part: v || null, preset: null })} />
        </${Field}>
        <${Field} label="Finishing against xG" hint="How surprising goals minus xG is, from the exact distribution over their shots.">
          <${Select} value=${f.luck} label="Finishing against xG" options=${[{ value: "", label: "Any" }, { value: "over", label: "Well above xG (running hot)" }, { value: "under", label: "Well below xG (unlucky)" }]} onChange=${(v) => set({ luck: v || null, preset: null })} />
        </${Field}>
      </${Popover}>
    </div>
    <div class="filter-row presets" role="group" aria-label="Lenses">
      <span class="eyebrow">Lenses</span>
      ${PRESETS.map((p) => html`<button type="button" class="chip" key=${p.key} title=${p.hint} aria-pressed=${String(f.preset === p.key)} onClick=${() => set({ ...p.patch, preset: p.key })}>${p.label}</button>`)}
    </div>
  </div>`;
}

/** Long checklist rendered inline (inside another popover). */
function ChecklistChipInline({ options, value, onChange }) {
  const [q, setQ] = useState("");
  const shown = options.filter((o) => fold(o.label).includes(fold(q)));
  const selected = new Set(value);
  return html`<div class="stack" style=${{ "--gap": "6px" }}>
    <input class="input" placeholder="Filter clubs" value=${q} onInput=${(e) => setQ(e.target.value)} aria-label="Filter clubs" />
    <div class="checklist">
      ${shown.map((o) => html`<button type="button" class="menu-item" role="checkbox" key=${o.value} aria-checked=${String(selected.has(o.value))} onClick=${() => { const next = new Set(selected); next.has(o.value) ? next.delete(o.value) : next.add(o.value); onChange([...next]); }}>
        <span class="check">${selected.has(o.value) ? html`<${Icon} name="check" size="sm" />` : null}</span><span class="truncate">${o.label}</span></button>`)}
    </div>
  </div>`;
}

// ------------------------------------------------------------------ table + map

function ResultsTable({ rows, f, set, catalog, scope, shortlist }) {
  const keys = metricKeys(f.groups, catalog);
  const cmp = new Set(f.cmp);
  const columns = useMemo(() => [
    { key: "pick", label: "", sortable: false, csv: false, width: "34px", render: (r) => html`<input type="checkbox" aria-label=${`Select ${r.name} to compare`} checked=${cmp.has(r.id)}
      onClick=${(e) => e.stopPropagation()} onChange=${(e) => { const next = e.target.checked ? [...f.cmp, r.id].slice(-4) : f.cmp.filter((x) => x !== r.id); set({ cmp: next.join(",") || null }); }} />` },
    { key: "star", label: "", sortable: false, csv: false, width: "34px", render: (r) => html`<${Star} player=${r} />` },
    { key: "name", label: "Player", sticky: true, firstDir: "asc", render: (r) => html`<${PlayerCell} row=${r} season=${scope.season} />`, value: (r) => r.name },
    { key: "output", label: "Role score", num: true, render: (r) => html`<${ScoreCell} row=${r} />`, title: "Average percentile across the metrics that matter for this role, ranked against peers with enough minutes. Small samples are pulled toward the average." },
    { key: "minutes", label: "Min", num: true, render: (r) => html`<span class=${!r.in_pool ? "muted" : ""}>${r.minutes}</span>`, title: "League minutes played." },
    ...keys.map((k) => {
      const def = catalog.metrics[k];
      return { key: k, label: def.short, num: true, title: `${def.what} ${def.read}`, value: (r) => r[k], csvLabel: def.label, render: (r) => html`<${PctCell} row=${r} metric=${k} def=${def} />` };
    }),
    { key: "g_xg_z", label: "G − xG", num: true, title: "Goals minus expected goals; the small number is how surprising that is (z). Beyond ±2 is rare.", value: (r) => r.g_xg_z,
      render: (r) => html`<span class="luckcell"><span class=${"delta-val " + (r.g_xg > 0.5 ? "pos" : r.g_xg < -0.5 ? "neg" : "")}>${signed(r.g_xg, 1)}</span><span class="muted xsmall">z ${signed(r.g_xg_z, 1)}</span></span>` },
    { key: "tags", label: "Profile", sortable: false, csv: false, render: (r) => html`<${TagCell} row=${r} />` },
  ], [keys.join(), f.cmp.join(), catalog]);

  return html`<${DataTable} columns=${columns} rows=${rows} rowKey=${(r) => r.id} pageSize=${50} tight
    sort=${{ key: f.sort, dir: f.dir }} onSort=${(s) => set({ sort: s.key === "output" && s.dir === "desc" ? null : s.key, dir: s.dir === "desc" && s.key === "output" ? null : s.dir, preset: null })}
    onRowClick=${(r) => navigate(`/player/${r.id}`, { league: r.league, season: r.seasons?.length === 1 ? r.seasons[0] : scope.season })} caption="Players" />`;
}

function ScoutMap({ rows, f, set, catalog, scope }) {
  const shortlist = useStore(shortlistStore, (s) => s.items);
  const marked = new Set(shortlist.map((i) => Number(i.id)));
  const label = (k) => (k === "output" ? "Role score" : catalog.metrics[k]?.short || k);
  const opts = MAP_METRICS.map((k) => ({ value: k, label: label(k) }));
  const multi = new Set(rows.map((r) => r.group)).size > 1;
  const top = new Set([...rows].sort((a, b) => (b.output ?? 0) - (a.output ?? 0)).slice(0, 12).map((r) => r.id));
  const points = rows.filter((r) => Number.isFinite(r[f.mx]) && Number.isFinite(r[f.my])).map((r) => ({
    id: r.id, x: r[f.mx], y: r[f.my], label: r.name.split(" ").slice(-1)[0], showLabel: top.has(r.id) || marked.has(r.id), priority: (marked.has(r.id) ? 1000 : 0) + (r.output ?? 0),
    r: 3 + Math.sqrt(r.minutes / 2700) * 3.5, color: multi ? GROUP_COLOR[r.group] : "var(--c1)", ring: marked.has(r.id), dim: !r.in_pool, data: r,
  }));
  const fmt = (k, v) => (k === "output" ? String(Math.round(v)) : metricValue(catalog.metrics[k], v));
  return html`<div class="stack" style=${{ "--gap": "12px" }}>
    <div class="row wrap" style=${{ gap: "12px" }}>
      <${Field} label="Horizontal"><${Select} value=${f.mx} options=${opts} label="Horizontal metric" onChange=${(v) => set({ mx: v === "xa90" ? null : v })} /></${Field}>
      <${Field} label="Vertical"><${Select} value=${f.my} options=${opts} label="Vertical metric" onChange=${(v) => set({ my: v === "npxg90" ? null : v })} /></${Field}>
      <span class="xsmall muted" style=${{ alignSelf: "end", paddingBottom: "9px" }}>Dot size: minutes played. Ringed: on your shortlist. Faded: small sample.</span>
    </div>
    ${multi ? html`<${Legend} items=${GROUPS.filter((g) => rows.some((r) => r.group === g.value)).map((g) => ({ key: g.value, label: g.label, color: GROUP_COLOR[g.value], shape: "dot" }))} />` : null}
    <${Scatter} points=${points} height=${520} xLabel=${label(f.mx)} yLabel=${label(f.my)} hoverPad=${16} label="Players plotted on two metrics"
      onSelect=${(p) => navigate(`/player/${p.id}`, { league: p.data.league, season: p.data.seasons?.length === 1 ? p.data.seasons[0] : scope.season })}
      renderTip=${(p) => html`<${Tip} title=${p.data.name} sub=${`${p.data.team} · ${POS_LABEL[p.data.group]}`} rows=${[
        { label: label(f.mx), value: fmt(f.mx, p.data[f.mx]) }, { label: label(f.my), value: fmt(f.my, p.data[f.my]) },
        { label: "Role score", value: p.data.output == null ? "–" : Math.round(p.data.output) }, { label: "Minutes", value: p.data.minutes },
      ]} />`} />
  </div>`;
}

function CompareTray({ ids, rows, set }) {
  if (!ids.length) return null;
  const chosen = ids.map((id) => rows.find((r) => r.id === id)).filter(Boolean);
  return html`<div class="tray" role="region" aria-label="Comparison selection">
    <div class="tray-list">${chosen.map((r) => html`<span class="chip on" key=${r.id}>${r.name}<button type="button" aria-label=${`Remove ${r.name}`} onClick=${() => set({ cmp: ids.filter((x) => x !== r.id).join(",") || null })}><${Icon} name="x" /></button></span>`)}</div>
    <div class="row" style=${{ gap: "8px" }}>
      <${Button} kind="quiet" size="sm" onClick=${() => set({ cmp: null })}>Clear</${Button}>
      <${Button} kind="primary" size="sm" icon="compare" disabled=${ids.length < 2} onClick=${() => navigate("/compare", { ids: ids.join(",") })}>${ids.length < 2 ? "Pick one more" : `Compare ${ids.length}`}</${Button}>
    </div>
  </div>`;
}

// ------------------------------------------------------------------ page

function ScoutView({ d, f, set, scope, meta, catalog }) {
  const rowsAll = d.rows;
  const rows = useMemo(() => applyFilters(rowsAll, f), [rowsAll, f.groups.join(), f.minutes, f.age.join(), f.ageOn, f.unknownAge, f.q, f.teams.join(), f.part, f.luck, f.small]);
  const sorted = useMemo(() => {
    const get = (r) => (f.sort === "name" ? r.name : r[f.sort]);
    const dir = f.dir === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => {
      const x = get(a), y = get(b);
      if (x == null && y == null) return 0;
      if (x == null) return 1;
      if (y == null) return -1;
      return (typeof x === "string" ? x.localeCompare(y) : x - y) * dir;
    });
  }, [rows, f.sort, f.dir]);
  const cov = d.coverage, enr = d.enrichment;
  const agesPct = cov.players ? cov.ages_known / cov.players : 1;
  const preset = PRESETS.find((p) => p.key === f.preset);
  const csvCols = useMemo(() => [
    { label: "Player", value: (r) => r.name }, { label: "Team", value: (r) => r.team }, { label: "League", value: (r) => r.league }, { label: "Role", value: (r) => r.group },
    { label: "Age", value: (r) => r.age }, { label: "Minutes", value: (r) => r.minutes }, { label: "Role score", value: (r) => r.output },
    ...MAP_METRICS.filter((k) => catalog.metrics[k]).map((k) => ({ label: catalog.metrics[k].label, value: (r) => r[k] })),
  ], [catalog]);

  return html`
    <${PageHead} eyebrow=${`${d.scope.leagues.map((l) => leagueName(meta, l)).join(" + ")} · ${d.scope.labels.join(", ")}`} title="Scout"
      sub=${`${plural(d.scope.n, "player")} with at least 90 minutes. Rankings compare each player only with peers in the same role who have played enough (${d.scope.pool_minutes}+ minutes), and pull small samples toward the average.`}
      actions=${html`<${CsvButton} columns=${csvCols} rows=${sorted} filename="prem-lab-scout.csv" />`} />
    <${DataNotices} scope=${{ note: d.scope.notes?.[0] }} meta=${d.meta} />
    ${agesPct < 0.6 ? html`<${Notice} icon="clock">Ages are known for ${cov.ages_known} of ${cov.players} players${enr.ages.running ? ` (loading ${enr.ages.done} of ${enr.ages.total} from Wikidata now)` : ""}. Age filters only apply to players with a known age; ${d.coverage.inferred_roles ? `${d.coverage.inferred_roles} roles are inferred from minutes and sharpen as position data arrives.` : ""}</${Notice}>` : null}
    ${f.view === "table" && !f.q && !f.preset ? html`<${Insights} items=${d.highlights} scope=${scope} limit=${3} compact expandable />` : null}

    <${FilterBar} f=${f} set=${set} meta=${meta} rowsAll=${rowsAll} scope=${scope} />

    <div class="card">
      <div class="results-bar">
        <div class="stack" style=${{ "--gap": "2px" }}>
          <b>${plural(sorted.length, "player")}</b>
          <span class="muted small">${f.view === "map" ? "Each dot is a player. Hover for detail, click to open the profile." : preset ? preset.hint : `Sorted by ${f.sort === "output" ? "role score" : catalog.metrics[f.sort]?.label || f.sort}, ${f.dir === "asc" ? "lowest first" : "highest first"}. Click any header to re-sort.`}</span>
        </div>
        <div class="row wrap" style=${{ gap: "8px" }}>
          ${f.preset || f.q || f.teams.length || f.ageOn || f.part || f.luck || f.minutes !== 450 || f.groups.join() !== DEFAULT_GROUPS.join() ? html`<${Button} kind="quiet" size="sm" icon="x" onClick=${() => set({ groups: null, leagues: null, seasons: null, min: null, age: null, unk: null, q: null, team: null, part: null, luck: null, sort: null, dir: null, preset: null })}>Reset</${Button}>` : null}
          <${Segmented} small label="View" options=${[{ value: "table", label: "Table" }, { value: "map", label: "Map" }]} value=${f.view} onChange=${(v) => set({ view: v === "table" ? null : v })} />
        </div>
      </div>
      ${sorted.length
        ? f.view === "map"
          ? html`<div class="card-body"><${ScoutMap} rows=${sorted} f=${f} set=${set} catalog=${catalog} scope=${scope} /></div>`
          : html`<${ResultsTable} rows=${sorted} f=${f} set=${set} catalog=${catalog} scope=${scope} />`
        : html`<${EmptyState} title="No players match" text="Try a lower minutes threshold, more roles, or reset the filters." action=${html`<${Button} onClick=${() => set({ groups: null, min: null, age: null, unk: null, q: null, team: null, part: null, luck: null, preset: null })}>Reset filters</${Button}>`} />`}
    </div>
    <${CompareTray} ids=${f.cmp} rows=${rowsAll} set=${set} />
  `;
}

export default function Scout() {
  const scope = useScope();
  const meta = useMeta();
  const { query } = useLocation();
  const f = readFilters(query, scope);
  const set = (patch) => setQuery(patch);
  const leagues = f.leagues.length ? f.leagues : [scope.league];
  const seasons = f.seasons.length ? f.seasons : [scope.season];
  const q = useApi("/api/players", { leagues, seasons, min_minutes: 90 }, { pollMs: 0 });
  const running = q.data?.enrichment && (q.data.enrichment.ages.running || q.data.enrichment.roles.running);
  useEffect(() => {
    if (!running) return undefined;
    const t = setInterval(() => q.reload(), 6000);
    return () => clearInterval(t);
  }, [running]);
  useDocumentTitle("Scout");
  return html`<${Async} q=${q}>${(d) => html`<${ScoutView} d=${d} f=${f} set=${set} scope=${scope} meta=${meta.meta} catalog=${meta.catalog} />`}</${Async}>`;
}

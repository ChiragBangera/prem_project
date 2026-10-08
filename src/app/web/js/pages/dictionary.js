// Data dictionary: every number in the app. Raw means the figure as a source publishes it; derived means computed here from raw figures.
// Each entry gives the recipe, how to read it, caveats, where it is used, and what typical values look like in the league and season on screen.
import { html, useMemo, useState } from "../lib/html.js";
import { useApi } from "../lib/api.js";
import { useScope } from "../lib/scope.js";
import { setQuery, useLocation } from "../lib/router.js";
import { fold, plural } from "../lib/format.js";
import { fmtMetric } from "../lib/metricfmt.js";
import { Async, Badge, Button, Card, EmptyState, PageHead, SearchBox, Segmented, Select, Tabs, useDocumentTitle } from "../ui/common.js";

const TABS = [
  { value: "metrics", label: "Metrics" }, { value: "raw", label: "Raw data" }, { value: "events", label: "Events and qualifiers" },
  { value: "profiles", label: "Profiles and lenses" }, { value: "concepts", label: "How to read the numbers" },
];
const SOURCE_NAME = { understat: "Understat", whoscored: "WhoScored events", both: "Understat + events", espn: "ESPN squad lists", derived: "Derived" };
const NEEDS_TEXT = { base: "Needs only season totals, which exist for everything loaded.", shots: "Needs Understat match pages, downloaded in the background.", events: "Needs event data (passes, duels, tackles, carries)." };

function Typical({ m, stats, roles }) {
  if (!stats) return null;
  const rows = m.level === "team"
    ? (stats.teams?.[m.key] ? [["Teams", stats.teams[m.key]]] : [])
    : Object.entries(stats.players?.[m.key] || {}).map(([g, q]) => [`${roles[g] || g}s`, q]);
  if (!rows.length) return null;
  return html`<div class="dict-typical"><span class="eyebrow">Typical values here</span>
    ${rows.map(([who, q]) => html`<span key=${who} class="xsmall">${who} (${q[0]}): middle 80% from <b class="num">${fmtMetric(m, q[1])}</b> to <b class="num">${fmtMetric(m, q[5])}</b>, median <b class="num">${fmtMetric(m, q[3])}</b></span>`)}</div>`;
}

function Entry({ m, stats, roles, focused }) {
  return html`<article class=${"dict-entry" + (focused ? " focus" : "")} id=${"m-" + m.key}>
    <header class="dict-head">
      <div class="stack" style=${{ "--gap": "2px", minWidth: 0 }}><h2>${m.label}</h2><span class="xsmall muted">${m.group_label} · ${m.level === "team" ? "teams" : "players"} · <code>${m.key}</code></span></div>
      <div class="row wrap" style=${{ gap: "6px" }}><${Badge} tone=${m.kind === "raw" ? "good" : "accent"} title=${m.kind === "raw" ? "The figure exactly as the source publishes it" : "Computed in this app from raw figures"}>${m.kind}</${Badge}><${Badge}>${SOURCE_NAME[m.source] || m.source}</${Badge}></div>
    </header>
    <p>${m.what}</p>
    ${m.read ? html`<p class="secondary"><b>Reading it: </b>${m.read}</p>` : null}
    <div class="dict-formula"><span class="eyebrow">${m.kind === "raw" ? "Where it comes from" : "How it is made"}</span><code>${m.formula}</code>
      ${m.inputs?.length ? html`<span class="xsmall muted">from ${m.inputs.map((i, k) => html`<code key=${i}>${i}</code>${k < m.inputs.length - 1 ? " " : ""}`)}</span>` : null}</div>
    ${m.caveat ? html`<p class="xsmall dict-caveat"><b>Caveat: </b>${m.caveat}</p>` : null}
    <p class="xsmall muted">${NEEDS_TEXT[m.needs] || ""} ${m.hib === null ? "A style measure: higher means more of it, not better." : m.hib ? "Higher is better." : "Lower is better (its percentile is inverted so that higher is always better)."}</p>
    <${Typical} m=${m} stats=${stats} roles=${roles} />
    ${[...(m.used?.lenses || []), ...(m.used?.views || []), ...(m.used?.scores || [])].length ? html`<p class="xsmall muted">Used in: ${[...(m.used.lenses || []).map((x) => `lens ${x}`), ...(m.used.views || []).map((x) => `columns ${x}`), ...(m.used.scores || []).map((x) => `score ${x}`)].join(" · ")}</p>` : null}
  </article>`;
}

function Metrics({ d, stats, query }) {
  const [shown, setShown] = useState(30);
  const level = query.lv || "all", kind = query.kind || "all", source = query.src || "all", q = query.q || "";
  const sources = useMemo(() => [...new Set(d.metrics.map((m) => m.source))], [d]);
  const needle = fold(q);
  const list = useMemo(() => d.metrics.filter((m) => (level === "all" || m.level === level) && (kind === "all" || m.kind === kind) && (source === "all" || m.source === source)
    && (!needle || fold(`${m.label} ${m.short} ${m.key} ${m.what} ${m.group_label} ${m.formula}`).includes(needle))), [d, level, kind, source, needle]);
  const focus = query.m ? d.metrics.find((m) => m.key === query.m) : null;
  const ordered = focus ? [focus, ...list.filter((m) => m.key !== focus.key)] : list;
  return html`<div class="stack" style=${{ "--gap": "14px" }}>
    <div class="row wrap" style=${{ gap: "10px" }}>
      <${SearchBox} value=${q} onInput=${(v) => { setShown(30); setQuery({ q: v || null, m: null }); }} placeholder=${`Search ${d.metrics.length} metrics`} width="280px" />
      <${Segmented} small label="Level" value=${level} onChange=${(v) => setQuery({ lv: v === "all" ? null : v, m: null })} options=${[{ value: "all", label: "Players and teams" }, { value: "player", label: "Players" }, { value: "team", label: "Teams" }]} />
      <${Segmented} small label="Kind" value=${kind} onChange=${(v) => setQuery({ kind: v === "all" ? null : v, m: null })} options=${[{ value: "all", label: "Raw and derived" }, { value: "raw", label: "Raw" }, { value: "derived", label: "Derived" }]} />
      <${Select} compact label="Source" value=${source} onChange=${(v) => setQuery({ src: v === "all" ? null : v, m: null })} options=${[{ value: "all", label: "Any source" }, ...sources.map((s) => ({ value: s, label: SOURCE_NAME[s] || s }))]} />
      <span class="xsmall muted">${plural(list.length, "metric")}</span>
    </div>
    <p class="small muted">A <b>raw</b> metric is the figure as its source publishes it. A <b>derived</b> one is computed here from raw figures: the formula and its inputs are given, so any number on any page can be traced to where it came from.</p>
    ${ordered.length ? html`<div class="dict-list">${ordered.slice(0, shown).map((m) => html`<${Entry} key=${m.level + m.key} m=${m} stats=${stats} roles=${d.roles} focused=${focus?.key === m.key} />`)}</div>
      ${ordered.length > shown ? html`<div class="row" style=${{ justifyContent: "center" }}><${Button} onClick=${() => setShown(shown + 40)}>Show ${Math.min(40, ordered.length - shown)} more</${Button}></div>` : null}`
      : html`<${EmptyState} title="No metric matches" text="Try fewer filters or a different word." />`}
  </div>`;
}

function Raw({ d }) {
  return html`<div class="stack" style=${{ "--gap": "16px" }}>${d.sources.map((s) => html`<${Card} key=${s.key} title=${s.name} sub=${s.kind}>
    <div class="stack" style=${{ "--gap": "10px" }}>
      <p>${s.what}</p><p class="small secondary"><b>How it is read: </b>${s.how}</p><p class="small secondary"><b>Limits: </b>${s.limits}</p>
      ${s.parts.map((p) => html`<div key=${p.name} class="stack" style=${{ "--gap": "4px" }}><span class="eyebrow">${p.name}</span>
        <dl class="gloss">${p.fields.map((f) => html`<div key=${f.name}><dt><code>${f.name}</code></dt><dd>${f.meaning}</dd></div>`)}</dl></div>`)}
    </div></${Card}>`)}
    <${Card} title="Event counters" sub="What each stored per-match counter counts. Every event metric is built from these sums, so a new metric never needs a new download.">
      <dl class="gloss">${d.counters.map((c) => html`<div key=${c.key}><dt><code>${c.key}</code>${c.team_only ? " (team)" : ""}</dt><dd>${c.meaning}</dd></div>`)}</dl></${Card}></div>`;
}

function Events({ d }) {
  return html`<div class="grid cols-2 top">
    <${Card} title="Event types" sub="What WhoScored records for every action in a match."><dl class="gloss one">${d.events.map((e) => html`<div key=${e.name}><dt><code>${e.name}</code> <span class="muted xsmall">#${e.id}</span></dt><dd>${e.meaning}</dd></div>`)}</dl></${Card}>
    <${Card} title="Qualifiers" sub="The extra flags attached to an event (how a pass was played, how a shot was taken)."><dl class="gloss one">${d.qualifiers.map((e) => html`<div key=${e.name}><dt><code>${e.name}</code></dt><dd>${e.meaning}</dd></div>`)}</dl></${Card}>
  </div>`;
}

function Profiles({ d }) {
  return html`<div class="stack" style=${{ "--gap": "16px" }}>
    <${Card} title="Profile tags" sub="Labels earned by simple, readable rules on percentiles within a role. They describe a player; they are not a black-box classification.">
      <dl class="gloss">${d.tags.map((t) => html`<div key=${t.key}><dt>${t.label} <span class="muted xsmall">${d.roles[t.group]}</span></dt><dd>${t.blurb} <span class="muted">Earned with: ${t.explain}.</span></dd></div>`)}</dl></${Card}>
    <${Card} title="Lenses" sub="Quick filters in Scout and Teams. Each only adds the rules below to your filters.">
      <dl class="gloss">${d.lenses.map((l) => html`<div key=${l.level + l.key}><dt>${l.label} <span class="muted xsmall">${l.level === "team" ? "teams" : "players"}</span></dt><dd>${l.explain}</dd></div>`)}</dl></${Card}>
  </div>`;
}

function Concepts({ d }) {
  return html`<div class="stack" style=${{ "--gap": "16px" }}>${d.concepts.map((g) => html`<${Card} key=${g.group} title=${g.group}>
    <dl class="gloss">${g.entries.map((e) => html`<div key=${e.key}><dt>${e.term}</dt><dd><b>${e.short}</b> ${e.long}</dd></div>`)}</dl></${Card}>`)}</div>`;
}

export default function Dictionary() {
  const { league, season } = useScope();
  const { query } = useLocation();
  const tab = TABS.some((t) => t.value === query.tab) ? query.tab : query.m ? "metrics" : "metrics";
  const q = useApi("/api/dictionary", null, { staleMs: 3600000 });
  const st = useApi("/api/dictionary/stats", { league, season }, { staleMs: 600000 });
  useDocumentTitle("Data dictionary");
  return html`<div class="stack" style=${{ "--gap": "20px" }}>
    <${PageHead} eyebrow="Reference" title="Data dictionary" sub="Every number in the app: where it comes from, how it is computed, how to read it and what typical values look like. Use it to check any chart before drawing a conclusion from it." />
    <${Tabs} tabs=${TABS} value=${tab} onChange=${(v) => setQuery({ tab: v === "metrics" ? null : v }, { replace: false })} label="Dictionary sections" />
    <${Async} q=${q}>${(d) => (tab === "metrics" ? html`<${Metrics} d=${d} stats=${st.data} query=${query} />` : tab === "raw" ? html`<${Raw} d=${d} />` : tab === "events" ? html`<${Events} d=${d} />` : tab === "profiles" ? html`<${Profiles} d=${d} />` : html`<${Concepts} d=${d} />`)}</${Async}>
  </div>`;
}

// Data: what is stored on this computer, how it keeps itself up to date, what failed and when it will try again.
import { html, useState } from "../lib/html.js";
import { api, invalidate, useApi } from "../lib/api.js";
import { useMeta, leagueName } from "../lib/scope.js";
import { bytes, cls, plural, relTime } from "../lib/format.js";
import { Icon } from "../lib/icons.js";
import { Async, Badge, Button, Card, Notice, PageHead, Select, Switch, useDocumentTitle } from "../ui/common.js";
import { DataTable } from "../ui/table.js";
import { Birthdates, CheckCard, Enrichment, EventData, Progress, SyncCard } from "./data-tools.js";

const nowSec = () => Date.now() / 1000;

/** "in 12 min", "in 3 h", "now": for something that will happen. */
function until(ts) {
  const s = ts - nowSec();
  if (s <= 5) return "any moment now";
  if (s < 90) return "in under a minute";
  const m = s / 60;
  if (m < 90) return `in ${Math.round(m)} min`;
  return `in ${Math.round(m / 60)} h`;
}

const STATE_TONE = { ok: "good", stale: "warn", failed: "crit", waiting: "warn", "not available": "outline" };

// ------------------------------------------------------------------ automatic updates

function AutoCard({ auto, mode, reload }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const prefs = auto.prefs, ev = auto.events, last = auto.last;
  const offline = mode.demo || mode.offline;
  const save = async (patch) => {
    setBusy(true); setError(null);
    try { await api.put("/api/data/auto", patch); invalidate("/api/data"); reload(); } catch (e) { setError(e); } finally { setBusy(false); }
  };
  const runNow = async () => {
    setBusy(true); setError(null);
    try { await api.post("/api/data/auto/run"); invalidate("/api/data"); setTimeout(reload, 800); } catch (e) { setError(e); } finally { setBusy(false); }
  };
  const fetched = last ? Object.values(last.leagues || {}).reduce((n, v) => n + (v.fetched || 0), 0) : 0;
  const status = !auto.auto
    ? (offline ? "Automatic updates are off in demo and offline mode." : "Automatic updates are switched off for this run (PREM_AUTO=0).")
    : !prefs.enabled ? "Paused: nothing is fetched until you switch it back on."
      : auto.running ? "Updating right now…"
        : `${auto.next_at ? `Next check ${until(auto.next_at)}.` : last?.finished ? "The next check happens shortly after the app starts." : "The first check happens shortly after the app starts."}${last?.finished ? ` Last cycle finished ${relTime(nowSec() - last.finished)}: ${plural(fetched, "match page")} fetched${last.errors?.length ? `, ${plural(last.errors.length, "problem")}` : ", no problems"}${last.backlog ? `, ${last.backlog} still to fetch (carried on next cycle)` : ""}.` : ""}`;
  const eventsOn = Boolean(ev.enabled);
  const evLeagues = prefs.events.leagues;
  return html`<${Card} title="Automatic updates" sub="While the app is open it looks for newly finished matches and fetches only those. A match page is fetched once and kept for good; finished seasons are never fetched again."
    actions=${html`<${Button} icon="refresh" disabled=${busy || !auto.auto || !prefs.enabled || auto.running} onClick=${runNow} title="Run a cycle now instead of waiting for the next one">Update now</${Button}>`}>
    <div class="stack" style=${{ "--gap": "16px" }}>
      <div class="row between wrap" style=${{ gap: "12px" }}>
        <${Switch} checked=${Boolean(auto.auto && prefs.enabled)} onChange=${(v) => save({ enabled: v })}>Keep league data and match pages up to date by itself</${Switch}>
        <span class=${cls("badge", auto.running ? "accent" : auto.auto && prefs.enabled ? "good" : "outline")}>${auto.running ? "Running" : auto.auto && prefs.enabled ? "On" : "Off"}</span>
      </div>
      <p class="small secondary">${status}</p>
      ${error ? html`<${Notice} tone="crit" icon="alert">${error.message}</${Notice}>` : null}
      <div class="auto-prefs">
        <div class="stack" style=${{ "--gap": "6px" }}>
          <span class="label">Seasons kept complete</span>
          <${Select} compact label="Seasons kept complete" value=${String(prefs.seasons_back)} options=${[0, 1, 2, 3, 4].map((n) => ({ value: String(n), label: n === 0 ? "This season only" : n === 1 ? "This and the previous season" : `This and the previous ${n} seasons` }))} onChange=${(v) => save({ seasons_back: Number(v) })} />
          <span class="xsmall muted">League tables, team and player totals and each match page (scorers, shots, positions). Older seasons are fetched only when you ask for them below.</span>
        </div>
        <div class="stack" style=${{ "--gap": "8px" }}>
          <span class="label">Event data (passes, duels, carries, maps)</span>
          <${Switch} checked=${eventsOn} onChange=${(v) => save({ events: { enabled: v } })}>Fetch event data for finished matches</${Switch}>
          <span class="xsmall muted">${prefs.events.enabled === null ? "On because event data is already stored here. " : ""}Slow by design (about 15 seconds a match), so it runs in a separate process, a few dozen matches at a time, and carries on from where it stopped.</span>
          ${ev.process ? html`<span class="small"><b>Fetching now:</b> ${ev.process}</span>` : null}
        </div>
      </div>
      ${eventsOn || prefs.events.enabled === null ? html`<div class="auto-prefs">
        <div class="stack" style=${{ "--gap": "6px" }}><span class="label">Event leagues</span>
          <div class="chipgroup">${["EPL", "La_liga", "Bundesliga", "Serie_A", "Ligue_1"].map((l) => html`<button type="button" key=${l} class="chip" aria-pressed=${String(evLeagues.includes(l))} onClick=${() => { const next = evLeagues.includes(l) ? evLeagues.filter((x) => x !== l) : [...evLeagues, l]; if (next.length) save({ events: { leagues: next } }); }}>${leagueNames[l]}</button>`)}</div></div>
        <div class="stack" style=${{ "--gap": "6px" }}><span class="label">Event seasons</span>
          <${Select} compact label="Event seasons" value=${String(prefs.events.seasons_back)} options=${[0, 1, 2, 3].map((n) => ({ value: String(n), label: n === 0 ? "This season only" : `This and the previous ${n === 1 ? "season" : `${n} seasons`}` }))} onChange=${(v) => save({ events: { seasons_back: Number(v) } })} /></div>
      </div>` : null}
      ${!ev.capability.available ? html`<${Notice} tone="warn" icon="alert"><b>Event data cannot be fetched on this computer.</b> ${ev.capability.reason} ${ev.capability.hint || ""}</${Notice}>` : html`<p class="xsmall muted">Event fetching uses the browser found at <code>${ev.capability.browser}</code>. It reads WhoScored's public pages for personal use only, which that site's terms may not allow, so it only runs while the switch above is on.</p>`}
    </div>
  </${Card}>`;
}

const leagueNames = { EPL: "Premier League", La_liga: "La Liga", Bundesliga: "Bundesliga", Serie_A: "Serie A", Ligue_1: "Ligue 1" };

/** The demo world has no Understat or WhoScored to ask and no updater: it makes its own data, and says so instead of showing controls that do nothing. */
function DemoUpdates({ status }) {
  const working = (status.events || []).some((e) => e.status?.running);
  return html`<${Card} title="Automatic updates" sub="In the real app a background updater keeps everything current without anyone pressing a button.">
    <p class="small secondary">Demo mode: the demo world makes its own league data, match pages and event data${status.mode.demo_events ? ` in the background${working ? " (it is working on that right now: see the progress below)" : ""}` : "; event data is switched off for this run (PREM_DEMO_EVENTS=0)"}, so there is nothing to fetch and no updater to run. Start the app without <code>--demo</code> to keep real data up to date by itself.</p>
  </${Card}>`;
}

function CycleCard({ auto }) {
  const last = auto.last;
  if (!last) return html`<${Card} title="Last cycle"><p class="muted small">No cycle has finished yet. The first one starts shortly after the app does, and its result is kept here across restarts.</p></${Card}>`;
  const rows = Object.entries(last.leagues || {}).map(([key, v]) => ({ key, ...v }));
  const cols = [
    { key: "key", label: "League season", sortable: false, className: "strong", render: (r) => { const [l, s] = r.key.split(":"); return `${leagueNames[l] || l} ${s}/${String(Number(s) + 1).slice(-2)}`; } },
    { key: "state", label: "State", sortable: false, render: (r) => html`<${Badge} tone=${STATE_TONE[r.state] || ""}>${r.state}</${Badge}>` },
    { key: "fetched", label: "Pages fetched", num: true, sortable: false, render: (r) => r.fetched ?? "–" },
    { key: "remaining", label: "Still to fetch", num: true, sortable: false, render: (r) => r.remaining ?? "–" },
  ];
  return html`<${Card} flush title="Last cycle" sub=${`Finished ${relTime(nowSec() - last.finished)}${last.adopted ? ` · adopted ${last.adopted} event pages from the download cache` : ""}${last.rebuilt ? ` · rebuilt derived data for ${last.rebuilt} matches` : ""}`}>
    <${DataTable} columns=${cols} rows=${rows} rowKey=${(r) => r.key} dense caption="Last update cycle" />
    ${last.errors?.length ? html`<div class="card-foot"><ul class="plain">${last.errors.map((e, i) => html`<li key=${i}>${e}</li>`)}</ul></div>` : null}
  </${Card}>`;
}

/** "events:La_liga:2026" -> "Event data: La Liga 2026/27"; "EPL:2025" -> "Premier League 2025/26". */
function failureName(key) {
  const [first, ...rest] = key.split(":");
  const events = first === "events";
  const [league, season] = events ? rest : [first, rest[0]];
  const name = `${leagueNames[league] || league} ${season}/${String(Number(season) + 1).slice(-2)}`;
  return Number.isFinite(Number(season)) ? (events ? `Event data: ${name}` : name) : key;
}

function Failures({ auto }) {
  const rows = Object.entries(auto.failures || {});
  if (!rows.length) return html`<${Card} title="Needs attention"><p class="small muted"><${Icon} name="check" size="sm" /> Nothing is failing. When a request fails it is kept (never lost), tried again after a growing delay (5 minutes, then 10, 20 … up to 6 hours), and shown here.</p></${Card}>`;
  return html`<${Card} title="Needs attention" sub="These are retried by themselves, with a growing delay, and never stop anything else.">
    <div class="stack" style=${{ "--gap": "12px" }}>${rows.map(([key, f]) => html`<div key=${key} class="stack" style=${{ "--gap": "2px" }}>
      <div class="row between"><b>${failureName(key)}</b><span class="xsmall muted">${plural(f.n, "failure")} · next try ${until(f.next_try)}</span></div>
      <span class="small" style=${{ color: "var(--crit-ink)" }}>${f.error}</span></div>`)}</div>
  </${Card}>`;
}

function Activity({ auto }) {
  const log = [...(auto.log || [])].reverse().slice(0, 14);
  return html`<${Card} title="Recent activity" sub="What the updater did and when.">
    ${log.length ? html`<div class="stack" style=${{ "--gap": "8px" }}>${log.map((e, i) => html`<div key=${i} class="row top" style=${{ gap: "10px" }}>
      <span class=${"tone " + (e.level === "warn" ? "warning" : e.level === "error" ? "negative" : "neutral")} style=${{ width: "22px", height: "22px", borderRadius: "7px", flex: "none" }}><${Icon} name=${e.level === "warn" || e.level === "error" ? "alert" : "check"} size="sm" /></span>
      <div class="stack" style=${{ "--gap": 0, minWidth: 0 }}><span class="small">${e.msg}</span><span class="xsmall muted">${relTime(nowSec() - e.t)}</span></div></div>`)}</div>`
      : html`<p class="small muted">Nothing yet this session.</p>`}
  </${Card}>`;
}

// ------------------------------------------------------------------ what is stored

function Coverage({ status, meta }) {
  const order = meta.meta.leagues.map((l) => l.code);
  const rows = [...status.matrix].sort((a, b) => order.indexOf(a.league) - order.indexOf(b.league) || b.season - a.season);
  const now = nowSec();
  const cols = [
    { key: "league", label: "League", sortable: false, className: "strong", render: (r) => leagueName(meta.meta, r.league) },
    { key: "season", label: "Season", sortable: false, render: (r) => r.label },
    { key: "state", label: "", sortable: false, render: (r) => (r.league_state ? html`<${Badge} tone=${r.league_state === "final" ? "good" : ""}>${r.league_state === "final" ? "Final" : "Live"}</${Badge}>` : html`<${Badge} tone="warn">Not fetched</${Badge}>`) },
    { key: "played", label: "Played", num: true, sortable: false, title: "Matches played so far, of the fixtures in the season.", render: (r) => (r.played == null ? html`<span class="muted">–</span>` : html`<span class="num">${r.played}<span class="muted"> / ${r.fixtures}</span></span>`) },
    { key: "pages", label: "Match pages (scorers, shots, positions)", sortable: false, width: "230px", render: (r) => (r.pages ? html`<div class="cov"><${Progress} done=${r.pages[0]} total=${r.pages[1] || 1} tone=${r.pages[0] >= r.pages[1] && r.pages[1] ? "done" : ""} /><span class="xsmall muted num">${r.pages[0]} of ${r.pages[1]}</span></div>` : html`<span class="muted">–</span>`) },
    { key: "events", label: "Event data (maps, passing, duels)", sortable: false, width: "230px", render: (r) => (r.played == null ? (r.events ? html`<span class="xsmall muted num">${r.events} stored</span>` : html`<span class="muted">–</span>`) : html`<div class="cov"><${Progress} done=${r.events} total=${r.played || 1} tone=${r.events >= r.played && r.played ? "done" : ""} /><span class="xsmall muted num">${r.events} of ${r.played}</span></div>`) },
    { key: "squads", label: "Squad lists", sortable: false, render: (r) => (r.squads ? html`<span class="small num">${r.squads.clubs} clubs, ${r.squads.players} players${r.squads.sparse ? " (sparse)" : ""}</span>` : html`<span class="muted">–</span>`) },
    { key: "fetched", label: "Updated", sortable: false, render: (r) => (r.fetched_at == null ? html`<span class="muted">–</span>` : relTime(now - r.fetched_at)) },
  ];
  return html`<${Card} flush title="What is on this computer" sub="Every league season stored, and how complete each layer is. Match pages and event data fill in by themselves; a finished season only ever needs fetching once.">
    ${rows.length ? html`<${DataTable} columns=${cols} rows=${rows} rowKey=${(r) => r.league + r.season} dense caption="Coverage of stored data" maxHeight="520px" />` : html`<div class="card-body muted">Nothing stored yet.</div>`}
  </${Card}>`;
}

const KIND = {
  league: "League seasons (Understat)", match: "Match pages: shots, scorers (Understat)", team: "Team pages (Understat)", player: "Player pages (Understat)", fav: "Favourite positions", dob: "Birthdates (Wikidata)",
  roster: "Squad lists (ESPN)", ws_raw: "Event data, raw (WhoScored)", ws_silver: "Event data, parsed", ws_gold: "Event counters", events: "Event data (older format)", kv: "Your data and settings",
};
const LAYERS = [
  { title: "Raw", keys: ["league", "match", "team", "player", "roster", "dob", "fav", "ws_raw"], text: "Every response exactly as the source served it. Never edited, never fetched twice. This is what makes the rest rebuildable." },
  { title: "Parsed", keys: ["ws_silver"], text: "Event matches turned into compact tables of every action (type, player, pitch position, qualifiers). Maps and new measures read these." },
  { title: "Counters", keys: ["ws_gold"], text: "Per-match totals for every player and team. Season numbers are sums of these, and every metric is a formula over them." },
];

function Storage({ status, reload }) {
  const kinds = status.store.kinds;
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const reclaim = async () => {
    setBusy(true);
    try { setResult(await api.post("/api/data/reclaim")); invalidate("/api/data"); reload(); } catch (_) { setResult({ error: true }); } finally { setBusy(false); }
  };
  const layerOf = (keys) => keys.reduce((a, k) => ({ count: a.count + (kinds[k]?.count || 0), bytes: a.bytes + (kinds[k]?.bytes || 0) }), { count: 0, bytes: 0 });
  return html`<${Card} title="How it is stored" sub=${status.store.path}>
    <div class="stack" style=${{ "--gap": "14px" }}>
      <div class="layers">${LAYERS.map((l, i) => {
        const t = layerOf(l.keys);
        return html`<div class="layer" key=${l.title}><span class="eyebrow">${i + 1}. ${l.title}</span><b class="figure">${bytes(t.bytes)}</b><span class="xsmall muted">${t.count.toLocaleString("en-GB")} items</span><p class="xsmall">${l.text}</p></div>`;
      })}</div>
      <p class="xsmall muted">A new definition, metric or chart only ever re-reads what is already here: when the code that parses or counts changes, the layers above rebuild from the one below, offline.</p>
      <dl class="kv">${Object.entries(kinds).map(([k, v]) => html`<dt key=${k + "d"}>${KIND[k] || k}</dt><dd key=${k}>${v.count.toLocaleString("en-GB")} · ${bytes(v.bytes)}</dd>`)}</dl>
      ${status.reclaimable_bytes > 0 ? html`<div class="well stack" style=${{ "--gap": "8px" }}>
        <span class="small"><b>${bytes(status.reclaimable_bytes)}</b> of event pages are held twice: in the event fetcher's download cache and in the store.</span>
        <div class="row" style=${{ gap: "10px" }}><${Button} size="sm" icon="trash" disabled=${busy} onClick=${reclaim}>Free that space</${Button}>
          ${result && !result.error ? html`<span class="xsmall muted">Removed ${result.deleted} files (${bytes(result.bytes ?? 0)}).</span>` : result ? html`<span class="xsmall" style=${{ color: "var(--crit-ink)" }}>That did not work.</span>` : null}</div>
        <span class="xsmall muted">Only copies the store already holds are removed, so nothing is lost and nothing needs fetching again.</span></div>` : null}
      <p class="xsmall muted">Your shortlist and notes live in the same file and survive cache clears. <code>prem clear --yes</code> clears the fetched league data; raw event pages are kept unless you add <code>--events</code>.</p>
    </div>
  </${Card}>`;
}

function HowItWorks() {
  const items = [
    ["Start", "The first time a page needs a league season, it is fetched from Understat and stored. After that it loads from this computer."],
    ["Stay current", "The updater checks every 15 minutes while the app is open. A finished season is never asked for again; a live one refreshes around match days; each finished match adds one match page (and, if switched on, one event file)."],
    ["Never lose a response", "Responses are stored exactly as received, before any interpretation. Parsed tables and counters are derived from them, so a bug fix or a new metric rebuilds from disk and never costs a request."],
    ["Fail safely", "A failed request keeps what is stored, backs off (5 min, 10, 20 … 6 h) and tries again by itself. One failing league never stops another. A season that does not exist yet is not treated as an error."],
    ["Say what is missing", "A number with no data behind it is blank, never zero. Pages say how many matches or players a figure rests on, and this page shows what has arrived."],
    ["Work offline", "With PREM_OFFLINE=1 nothing touches the network and everything stored is served."],
  ];
  return html`<${Card} title="How the data layer works">
    <dl class="gloss">${items.map(([t, d]) => html`<div key=${t}><dt>${t}</dt><dd>${d}</dd></div>`)}</dl>
  </${Card}>`;
}

function DataView({ status, meta, reload }) {
  const auto = status.auto;
  const cache = status.leagues;
  const stored = Object.values(status.store.kinds).reduce((n, k) => n + k.count, 0);
  const eventMatches = (status.events || []).reduce((n, e) => n + e.matches, 0);
  return html`
    <${PageHead} eyebrow="System" title="Data" sub=${status.mode.demo ? "You are looking at a synthetic demo world." : "Everything you see is served from this computer. The app keeps it up to date by itself and shows here what it holds, what it did and what failed."}
      actions=${html`<${Button} icon="refresh" onClick=${reload}>Refresh</${Button}>`} />
    <div class="tiles">
      <div class="tile"><span class="label">Source</span><span class="value figure" style=${{ fontSize: "24px" }}>${status.mode.demo ? "Demo world" : status.mode.offline ? "Offline cache" : "Understat"}</span><span class="delta">${status.mode.demo ? "synthetic players and results" : "read at a polite pace, stored locally"}</span></div>
      <div class="tile"><span class="label">On disk</span><span class="value figure">${bytes(status.store.total_bytes)}</span><span class="delta">${stored.toLocaleString("en-GB")} stored items</span></div>
      <div class="tile"><span class="label">League seasons</span><span class="value figure">${cache.length}</span><span class="delta">${cache.filter((c) => c.complete).length} final, ${cache.filter((c) => !c.complete).length} live</span></div>
      <div class="tile"><span class="label">Event matches</span><span class="value figure">${eventMatches.toLocaleString("en-GB")}</span><span class="delta">${eventMatches ? "maps and event metrics available" : "none stored yet"}</span></div>
    </div>
    ${status.mode.demo ? html`<${DemoUpdates} status=${status} />` : html`<${AutoCard} auto=${auto} mode=${status.mode} reload=${reload} />
    <div class="grid cols-2 top">
      <div class="stack"><${CycleCard} auto=${auto} /><${Failures} auto=${auto} /></div>
      <${Activity} auto=${auto} />
    </div>`}
    <${Coverage} status=${status} meta=${meta} />
    <div class="grid cols-2 top">
      <${EventData} status=${status} meta=${meta} />
      <${Storage} status=${status} reload=${reload} />
    </div>
    <${HowItWorks} />
    <h2 class="section-h">Tools</h2>
    <div class="grid cols-2 top">
      <div class="stack"><${SyncCard} status=${status} meta=${meta} onStarted=${reload} /><${CheckCard} status=${status} /></div>
      <div class="stack"><${Enrichment} status=${status} /><${Birthdates} status=${status} meta=${meta} /></div>
    </div>`;
}

export default function DataPage() {
  const meta = useMeta();
  const q = useApi("/api/data/status", null, { pollMs: 4000, staleMs: 1000 });
  useDocumentTitle("Data");
  return html`<${Async} q=${q}>${(d) => html`<${DataView} status=${d} meta=${meta} reload=${q.reload} />`}</${Async}>`;
}

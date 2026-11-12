// Data: what is stored on this computer, how it keeps itself up to date, what failed and when it will try again.
import { html, useState } from "../lib/html.js";
import { api, invalidate, useApi } from "../lib/api.js";
import { useMeta, leagueName } from "../lib/scope.js";
import { bytes, cls, plural, relTime } from "../lib/format.js";
import { Icon } from "../lib/icons.js";
import { Async, Badge, Button, Card, Notice, PageHead, Select, Switch, toggleFavourite, useDocumentTitle } from "../ui/common.js";
import { favouritesStore, useStore } from "../lib/store.js";
import { DataTable } from "../ui/table.js";
import { Birthdates, CheckCard, Enrichment, EventData, Progress, SyncCard } from "./data-tools.js";
import { EventReview, FetchControls, FetchPlan } from "./data-events.js";

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

/** "16:52", or "Sat 16:52" when it is not today: a moment in the reader's own time zone. */
function clockTime(ts) {
  const d = new Date(ts * 1000);
  const time = d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  return d.toDateString() === new Date().toDateString() ? time : `${d.toLocaleDateString("en-GB", { weekday: "short" })} ${time}`;
}

/** What the updater waits for: "Next: full time of Arsenal v Chelsea (Premier League), at 16:52 (in 3 h)." */
function nextLine(auto) {
  if (!auto.next_at) return null;
  return `Next: ${auto.next_reason || "the next check"}, at ${clockTime(auto.next_at)} (${until(auto.next_at)}).`;
}

/** "3 match pages fetched, no problems": what the last cycle did. A league left alone because it failed a moment ago is not "no problems". */
function cycleLine(last) {
  const states = Object.values(last.leagues || {});
  const fetched = states.reduce((n, v) => n + (v.fetched || 0), 0);
  const waiting = states.filter((v) => v.state === "waiting").length;
  const tail = last.errors?.length ? plural(last.errors.length, "problem") : waiting ? `${plural(waiting, "league season")} left alone until the source that failed is tried again` : "no problems";
  return `${plural(fetched, "match page")} fetched, ${tail}`;
}

const STATE_TONE = { ok: "good", stale: "warn", failed: "crit", waiting: "warn", "not available": "outline" };

// ------------------------------------------------------------------ the three questions

const dayMonth = (ts) => new Date(ts * 1000).toLocaleDateString("en-GB", { day: "numeric", month: "short" });

/** The page used to open on four counts and a wall of settings, and said "0 problems" while nothing had arrived for a month. It now opens
 *  on the three things a person comes here to learn: is the data current, what is the updater doing, and is anything waiting for them. */
/** Right after an update that changed how matches are counted, every stored match is worked through again once. Until that is done the
 *  event numbers on other pages can be slow or missing: say so, with how far it is. */
function BootNotice({ boot }) {
  if (!boot || !["importing", "rebuilding"].includes(boot.stage)) return null;
  const far = boot.total ? ` ${Math.min(boot.done || 0, boot.total).toLocaleString("en-GB")} of ${boot.total.toLocaleString("en-GB")} done.` : "";
  return html`<${Notice} tone="warn" icon="clock"><b>Re-working the stored matches.</b> A newer version counts some things differently, so each stored match is gone through once. Nothing is downloaded.${far} Pages that use event data can be slow or incomplete until it finishes; this page refreshes by itself.</${Notice}>`;
}

function StatusHead({ status }) {
  const auto = status.auto, last = auto.last;
  const failures = Object.entries(auto.failures || {});
  const tables = failures.filter(([k]) => !k.startsWith("events:"));
  const fetcher = failures.filter(([k]) => k.startsWith("events:"));
  const live = status.matrix.filter((r) => r.league_state === "live" && r.fetched_at != null);
  const oldest = live.length ? Math.min(...live.map((r) => r.fetched_at)) : null;
  const age = oldest == null ? null : nowSec() - oldest;
  const offline = status.mode.offline;
  // a live table is read at least twice a day; two days without one means something is in the way
  const behind = tables.length > 0 || (age != null && age > 2 * 86400);
  const current = oldest == null ? { tone: "outline", word: "Nothing stored yet", text: "Open any league and its season is fetched and kept." }
    : behind ? { tone: "warn", word: "Behind", text: `League tables were last read ${relTime(age)} (${dayMonth(oldest)}).` }
      : { tone: "good", word: "Up to date", text: `League tables were read ${relTime(age)}.` };
  const why = tables.length ? tables[0][1].error : null;
  const nextTry = tables.length ? Math.min(...tables.map(([, f]) => f.next_try)) : null;
  const doing = offline ? "Nothing: offline mode serves what is stored and never asks the network."
    : !auto.auto ? "Nothing: automatic updates are switched off for this run."
      : !auto.prefs.enabled ? "Paused: nothing is fetched until you switch it back on below."
        : auto.running ? "Updating right now."
          : auto.events.process ? `Fetching event data: ${auto.events.process}.`
            : nextLine(auto) || "Waiting for its first check, shortly after the app starts.";
  const needs = [];
  if (!auto.events.capability.available && auto.events.enabled) needs.push({ key: "cap", title: "Event data cannot be fetched on this computer", text: `${auto.events.capability.reason} ${auto.events.capability.hint || ""}` });
  // one line per reason, not per league: the same missing piece stops every league
  const seen = new Set();
  for (const [key, f] of fetcher) {
    if (seen.has(f.error)) continue;
    seen.add(f.error);
    const same = fetcher.filter(([, g]) => g.error === f.error).map(([k]) => failureName(k).replace("Event data: ", ""));
    needs.push({ key, title: `The event fetcher stopped (${same.join(", ")})`, text: f.error });
  }
  const parked = (auto.plan || []).reduce((n, r) => n + (r.events_parked || 0), 0);
  if (parked) needs.push({ key: "parked", title: `${plural(parked, "match", "matches")} could not be read`, text: "They are listed under Event matches to review below: read each again or leave it out." });
  return html`<${Card} class="status3-card" pad=${false}>
    <div class="status3">
      <div class="stack" style=${{ "--gap": "6px" }}>
        <span class="label">Is it up to date?</span>
        <div class="row" style=${{ gap: "8px" }}><${Badge} tone=${current.tone}>${current.word}</${Badge}></div>
        <p class="small">${current.text}</p>
        ${why ? html`<p class="small secondary">${why} ${nextTry ? `Nothing for you to do: the app asks again ${until(nextTry)}${tables.length > 1 ? `, for all ${tables.length} league seasons` : ""}.` : ""}</p>` : null}
      </div>
      <div class="stack" style=${{ "--gap": "6px" }}>
        <span class="label">What is it doing?</span>
        <p class="small">${doing}</p>
        ${last?.finished && !offline ? html`<p class="small secondary">Last cycle ${relTime(nowSec() - last.finished)}: ${cycleLine(last)}.</p>` : null}
      </div>
      <div class="stack" style=${{ "--gap": "6px" }}>
        <span class="label">What needs you?</span>
        ${needs.length ? needs.map((n) => html`<div key=${n.key} class="stack" style=${{ "--gap": "2px" }}><b class="small">${n.title}</b><span class="small secondary">${n.text}</span></div>`)
          : html`<p class="small"><${Icon} name="check" size="sm" /> Nothing. Failed requests are kept and tried again by themselves.</p>`}
      </div>
    </div>
  </${Card}>`;
}

// ------------------------------------------------------------------ automatic updates

const PAGE_SECONDS = 1.5, EVENT_SECONDS = 30, EVENT_RUN = 20;   // the updater's pace: a match page, a match of event data (read and pause), matches per run

/** "about 40 seconds", "about 8 minutes". */
function roughly(seconds) {
  if (seconds < 50) return `about ${Math.max(5, Math.round(seconds / 5) * 5)} seconds`;
  const m = Math.round(seconds / 60);
  return m < 90 ? `about ${plural(m, "minute")}` : `about ${Math.round(m / 60)} hours`;
}

/** What pressing "Update now" does, worked out from what the Data page already knows (what is left, today's limits, what is failing):
 *  the button used to start "a cycle" and say nothing about what that meant or how long it took. */
function updatePreview(auto) {
  const plan = auto.plan || [], budget = auto.budget || {}, ev = auto.events;
  const failures = Object.entries(auto.failures || {});
  const tablesDown = failures.filter(([k]) => !k.startsWith("events:"));
  const live = (auto.tracked || []).length;
  const steps = [];
  let seconds = 0;
  if (tablesDown.length) {
    steps.push(`ask ${tablesDown[0][1].error.startsWith("Understat") ? "Understat" : "the source"} once more for the league tables it could not give (${tablesDown[0][1].error.split(" (")[0].replace(/\.$/, "")}); if it answers, the tables and match pages follow`);
    seconds += 5;
  } else {
    const left = plan.reduce((n, r) => n + (r.pages_left || 0), 0);
    const pages = Math.min(left, budget.understat?.left ?? left);
    steps.push(`read the league tables that are due${live ? ` (${plural(live, "league season")} kept)` : ""}`);
    if (left) steps.push(pages ? `fetch ${pages === left ? "the" : `${pages} of the`} ${plural(left, "match page")} still missing` : `leave ${plural(left, "match page")} for tomorrow (today's limit of ${budget.understat?.limit} is used)`);
    seconds += 5 + pages * PAGE_SECONDS;
  }
  if (ev.enabled) {
    const left = plan.reduce((n, r) => n + (r.events_left || 0), 0);
    const allowed = Math.min(left, EVENT_RUN, budget.whoscored?.left ?? EVENT_RUN);
    if (!ev.capability.available) steps.push("skip event data (it cannot be fetched on this computer: see above)");
    else if (ev.control?.paused) steps.push("leave event data alone (it is paused)");
    else if (ev.process) steps.push(`let the event fetcher carry on (${ev.process})`);
    else if (!left) steps.push("find no event data missing");
    else if (!allowed) steps.push(`leave ${plural(left, "match", "matches")} of event data for tomorrow (today's limit is used)`);
    else { steps.push(`start the event fetcher on ${allowed === left ? "the" : `${allowed} of the`} ${plural(left, "match", "matches")} without event data (in its own process; the page stays usable)`); seconds += allowed * EVENT_SECONDS; }
  }
  return { steps, time: roughly(seconds) };
}

function AutoCard({ auto, mode, reload }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [asked, setAsked] = useState(null);   // how many waiting requests the last press of "Update now" set going again
  const prefs = auto.prefs, ev = auto.events, last = auto.last;
  const offline = mode.demo || mode.offline;
  const save = async (patch) => {
    setBusy(true); setError(null);
    try { await api.put("/api/data/auto", patch); invalidate("/api/data"); reload(); } catch (e) { setError(e); } finally { setBusy(false); }
  };
  const runNow = async () => {
    setBusy(true); setError(null);
    try { const r = await api.post("/api/data/auto/run"); setAsked(r?.retrying ?? 0); invalidate("/api/data"); setTimeout(reload, 800); } catch (e) { setError(e); } finally { setBusy(false); }
  };
  const canRun = Boolean(auto.auto && prefs.enabled && !auto.running);
  const preview = canRun ? updatePreview(auto) : null;
  const status = !auto.auto
    ? (offline ? "Automatic updates are off in demo and offline mode." : "Automatic updates are switched off for this run (PREM_AUTO=0).")
    : !prefs.enabled ? "Paused: nothing is fetched until you switch it back on."
      : auto.running ? "Updating right now…"
        : `${auto.next_at ? nextLine(auto) : last?.finished ? "The next check happens shortly after the app starts." : "The first check happens shortly after the app starts."}${last?.finished ? ` Last cycle finished ${relTime(nowSec() - last.finished)}: ${cycleLine(last)}${last.backlog ? `, ${last.backlog} still to fetch (carried on next cycle)` : ""}.` : ""}`;
  const eventsOn = Boolean(ev.enabled);
  const evLeagues = prefs.events.leagues;
  return html`<${Card} title="Automatic updates" sub="While the app is open it follows the fixture list and wakes up only when a match can have changed something: shortly after each full time (and at half time for the matches you follow), and while a result or its xG is still coming. A match page is fetched once and kept for good; finished seasons are never fetched again."
    actions=${html`<${Button} icon="refresh" disabled=${busy || !auto.auto || !prefs.enabled || auto.running} onClick=${runNow} title=${preview ? `Now, instead of at the next check: ${preview.steps.join("; ")}. Takes ${preview.time}.` : "Look for new data now instead of waiting for the next check"}>Update now</${Button}>`}>
    <div class="stack" style=${{ "--gap": "16px" }}>
      <div class="row between wrap" style=${{ gap: "12px" }}>
        <${Switch} checked=${Boolean(auto.auto && prefs.enabled)} onChange=${(v) => save({ enabled: v })}>Keep league data and match pages up to date by itself</${Switch}>
        <span class=${cls("badge", auto.running ? "accent" : auto.auto && prefs.enabled ? "good" : "outline")}>${auto.running ? "Running" : auto.auto && prefs.enabled ? "On" : "Off"}</span>
      </div>
      <p class="small secondary">${status}</p>
      ${canRun ? html`<div class="well small update-preview"><b>Update now will:</b>
        <ol>${preview.steps.map((t, i) => html`<li key=${i}>${t}</li>`)}</ol>
        <span class="muted">Takes ${preview.time}. Nothing already stored is fetched again.${asked != null ? ` Asked just now${asked ? `: ${plural(asked, "waiting request")} tried again at once` : ""}.` : ""}</span></div>` : null}
      ${error ? html`<${Notice} tone="crit" icon="alert">${error.message}</${Notice}>` : null}
      <div class="auto-prefs">
        <div class="stack" style=${{ "--gap": "6px" }}>
          <span class="label">Seasons kept complete</span>
          <${Select} compact label="Seasons kept complete" value=${String(prefs.seasons_back)} options=${[0, 1, 2, 3, 4].map((n) => ({ value: String(n), label: n === 0 ? "This season only" : n === 1 ? "This and the previous season" : `This and the previous ${n} seasons` }))} onChange=${(v) => save({ seasons_back: Number(v) })} />
          <span class="xsmall muted">League tables, team and player totals and each match page (scorers, shots, positions). Older seasons are fetched only when you ask for them below.</span>
        </div>
        <div class="stack" style=${{ "--gap": "8px" }}>
          <span class="label">Event data (passes, duels, carries, maps)</span>
          <${Switch} checked=${eventsOn} onChange=${(v) => save({ events: { enabled: v } })}>Fetch event data: every match at full time, and older ones bit by bit</${Switch}>
          <span class="xsmall muted">${prefs.events.enabled === null ? "On because event data is already stored here. " : ""}Slow by design (about 15 seconds a match), so it runs in a separate process, a few dozen matches at a time, and carries on from where it stopped.</span>
          ${ev.process ? html`<span class="small"><b>Fetching now:</b> ${ev.process}</span>` : null}
        </div>
      </div>
      ${eventsOn || prefs.events.enabled === null ? html`<div class="auto-prefs">
        <div class="stack" style=${{ "--gap": "6px" }}><span class="label">Event leagues</span>
          <div class="chipgroup">${["EPL", "La_liga", "Bundesliga", "Serie_A", "Ligue_1"].map((l) => html`<button type="button" key=${l} class="chip" aria-pressed=${String(evLeagues.includes(l))} onClick=${() => { const next = evLeagues.includes(l) ? evLeagues.filter((x) => x !== l) : [...evLeagues, l]; if (next.length) save({ events: { leagues: next } }); }}>${leagueNames[l]}</button>`)}</div></div>
        <div class="stack" style=${{ "--gap": "6px" }}><span class="label">Event seasons</span>
          <${Select} compact label="Event seasons" value=${String(prefs.events.seasons_back)} options=${[0, 1, 2, 3].map((n) => ({ value: String(n), label: n === 0 ? "This season only" : `This and the previous ${n === 1 ? "season" : `${n} seasons`}` }))} onChange=${(v) => save({ events: { seasons_back: Number(v) } })} /></div>
      </div>
      <${Favourites} />` : null}
      ${!ev.capability.available ? html`<${Notice} tone="warn" icon="alert"><b>Event data cannot be fetched on this computer.</b> ${ev.capability.reason} ${ev.capability.hint || ""}</${Notice}>` : html`<p class="xsmall muted">Event fetching uses the browser found at <code>${ev.capability.browser}</code>. It reads WhoScored's public pages for personal use only, which that site's terms may not allow, so it only runs while the switch above is on.</p>`}
    </div>
  </${Card}>`;
}

/** The favourite teams, each removable here; a team page's star adds one. */
function Favourites() {
  const teams = useStore(favouritesStore, (s) => s.teams);
  return html`<div class="stack" style=${{ "--gap": "6px" }}>
    <span class="label">Followed at half time</span>
    ${teams.length ? html`<div class="chipgroup">${teams.map((t) => html`<button type="button" key=${t.league + t.team} class="chip" aria-pressed="true"
      title=${`Remove ${t.team} from your favourites`} onClick=${() => toggleFavourite(t.league, t.team)}>${t.team} ×</button>`)}</div>` : null}
    <span class="xsmall muted">${teams.length ? "Your favourite teams, " : "No favourite teams yet: add one with the button on its team page. Followed are your favourite teams "}and any match you open while it is being played: their event data is read during the half-time break as well as at full time. Favourites are kept in the app's database, like the shortlist: restarts, updates and clearing the cache keep them.</span>
  </div>`;
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
  // the table above already names each league season: under it the reason is said once ("Premier League 2026/27: reason" -> "reason")
  const tally = new Map();
  for (const e of last.errors || []) { const why = e.includes(": ") ? e.slice(e.indexOf(": ") + 2) : e; tally.set(why, (tally.get(why) || 0) + 1); }
  const reasons = [...tally];
  const cols = [
    { key: "key", label: "League season", sortable: false, className: "strong", render: (r) => { const [l, s] = r.key.split(":"); return `${leagueNames[l] || l} ${s}/${String(Number(s) + 1).slice(-2)}`; } },
    { key: "state", label: "State", sortable: false, render: (r) => html`<${Badge} tone=${STATE_TONE[r.state] || ""}>${r.state}</${Badge}>` },
    { key: "fetched", label: "Pages fetched", num: true, sortable: false, render: (r) => r.fetched ?? "–" },
    { key: "remaining", label: "Still to fetch", num: true, sortable: false, render: (r) => r.remaining ?? "–" },
  ];
  return html`<${Card} flush title="Last cycle" sub=${`Finished ${relTime(nowSec() - last.finished)}${last.adopted ? ` · adopted ${last.adopted} event pages from the download cache` : ""}${last.rebuilt ? ` · rebuilt derived data for ${last.rebuilt} matches` : ""}`}>
    <${DataTable} columns=${cols} rows=${rows} rowKey=${(r) => r.key} dense caption="Last update cycle" />
    ${last.errors?.length ? html`<div class="card-foot"><ul class="plain">${reasons.map(([why, n]) => html`<li key=${why}>${why}${n > 1 ? ` (${n} league seasons)` : ""}</li>`)}</ul></div>` : null}
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
  // one source that is down fails every league the same way: say the reason once, with the leagues it holds up
  const groups = [];
  for (const [key, f] of rows) {
    const g = groups.find((x) => x.error === f.error);
    if (g) { g.names.push(failureName(key)); g.n = Math.max(g.n, f.n); g.next_try = Math.min(g.next_try, f.next_try); }
    else groups.push({ error: f.error, names: [failureName(key)], n: f.n, next_try: f.next_try });
  }
  return html`<${Card} title="Needs attention" sub="These are retried by themselves, with a growing delay, and never stop anything else.">
    <div class="stack" style=${{ "--gap": "12px" }}>${groups.map((g) => html`<div key=${g.error} class="stack" style=${{ "--gap": "2px" }}>
      <div class="row between top"><b>${g.names.join(", ")}</b><span class="xsmall muted" style=${{ flex: "none" }}>${plural(g.n, "failure")} · next try ${until(g.next_try)}</span></div>
      <span class="small" style=${{ color: "var(--crit-ink)" }}>${g.error}</span></div>`)}</div>
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
    ["Stay current", "The updater works out from the fixture list when something can have changed, and wakes then. A finished season is never asked for again; a live one refreshes around match days; each finished match adds one match page (and, if switched on, one event file)."],
    ["Never lose a response", "Responses are stored exactly as received, before any interpretation. Parsed tables and counters are derived from them, so a bug fix or a new metric rebuilds from disk and never costs a request."],
    ["Fail safely", "A failed request keeps what is stored, backs off (5 min, 10, 20 … 6 h) and tries again by itself. One failing league never stops another. A season that does not exist yet is not treated as an error."],
    ["Say what is missing", "A number with no data behind it is blank, never zero. Pages say how many matches or players a figure rests on, and this page shows what has arrived."],
    ["Work offline", "With PREM_OFFLINE=1 nothing touches the network and everything stored is served."],
  ];
  // reference, read once: closed until asked for, so it does not add a screen to a page people open to check on things
  return html`<details class="card fold"><summary><span class="card-title">How the data layer works</span><span class="muted small">six rules it keeps</span></summary>
    <div class="card-body"><dl class="gloss">${items.map(([t, d]) => html`<div key=${t}><dt>${t}</dt><dd>${d}</dd></div>`)}</dl></div>
  </details>`;
}

function DataView({ status, meta, reload }) {
  const auto = status.auto;
  const cache = status.leagues;
  const stored = Object.values(status.store.kinds).reduce((n, k) => n + k.count, 0);
  const eventMatches = (status.events || []).reduce((n, e) => n + e.matches, 0);
  return html`
    <${PageHead} eyebrow="System" title="Data" sub=${status.mode.demo ? "You are looking at a synthetic demo world." : "Everything you see is served from this computer. The app keeps it up to date by itself and shows here what it holds, what it did and what failed."}
      actions=${html`<${Button} icon="refresh" onClick=${reload}>Refresh</${Button}>`} />
    <${BootNotice} boot=${status.boot} />
    ${status.mode.demo ? null : html`<${StatusHead} status=${status} />`}
    <div class="tiles">
      <div class="tile"><span class="label">Source</span><span class="value figure" style=${{ fontSize: "24px" }}>${status.mode.demo ? "Demo world" : status.mode.offline ? "Offline cache" : "Understat"}</span><span class="delta">${status.mode.demo ? "synthetic players and results" : "read at a polite pace, stored locally"}</span></div>
      <div class="tile"><span class="label">On disk</span><span class="value figure">${bytes(status.store.total_bytes)}</span><span class="delta">${stored.toLocaleString("en-GB")} stored items</span></div>
      <div class="tile"><span class="label">League seasons</span><span class="value figure">${cache.length}</span><span class="delta">${cache.filter((c) => c.complete).length} final, ${cache.filter((c) => !c.complete).length} live</span></div>
      <div class="tile"><span class="label">Event matches</span><span class="value figure">${eventMatches.toLocaleString("en-GB")}</span><span class="delta">${eventMatches ? "maps and event metrics available" : "none stored yet"}</span></div>
    </div>
    <span class="wide-page" hidden></span>
    ${status.mode.demo ? html`<${DemoUpdates} status=${status} />` : html`<div class=${"mrow " + (auto.auto ? "m-n2" : "")}><${AutoCard} auto=${auto} mode=${status.mode} reload=${reload} />
      ${auto.auto ? html`<${FetchControls} auto=${auto} reload=${reload} />` : null}</div>
    <div class=${"mrow " + (auto.plan?.length ? "m-7-5" : "")}><${FetchPlan} auto=${auto} /><${CycleCard} auto=${auto} /></div>
    <div class="mrow m-n2"><${Activity} auto=${auto} /><${Failures} auto=${auto} /></div>`}
    <${Coverage} status=${status} meta=${meta} />
    <div class="grid cols-2 top">
      <${EventData} status=${status} meta=${meta} />
      <${Storage} status=${status} reload=${reload} />
    </div>
    <${EventReview} status=${status} meta=${meta} reload=${reload} />
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

// Steering what the updater fetches: today's limits and what is left of them, the plan for every league season, pause and stop for the
// event fetcher, and the review of what it could not place or read (linked by hand, retried or skipped here).
import { html, useState } from "../lib/html.js";
import { api, invalidate, useApi } from "../lib/api.js";
import { leagueName } from "../lib/scope.js";
import { cls, plural, seasonLabel } from "../lib/format.js";
import { Async, Badge, Button, Card, Notice, Select } from "../ui/common.js";
import { DataTable } from "../ui/table.js";
import { Progress } from "./data-tools.js";

const UNDERSTAT_LIMITS = [100, 300, 600, 1000, 2000];
const WHOSCORED_LIMITS = [10, 20, 40, 80, 150];
const nowSec = () => Date.now() / 1000;

/** "about 3 days", "under a day", "–". */
const daysText = (n) => (n == null ? "–" : n <= 1 ? "under a day" : `about ${n} days`);

function useAction(reload) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const run = async (fn) => {
    setBusy(true); setError(null);
    try { await fn(); invalidate("/api/data"); invalidate("/api/events"); reload?.(); } catch (e) { setError(e); } finally { setBusy(false); }
  };
  return { busy, error, run };
}

function Usage({ label, used, limit }) {
  return html`<div class="stack" style=${{ "--gap": "4px" }}>
    <div class="row between xsmall"><span>${label}</span><span class="num muted">${used} of ${limit} today</span></div>
    <${Progress} done=${used} total=${Math.max(limit, 1)} tone=${used >= limit ? "warn" : undefined} />
  </div>`;
}

/** What the event fetcher is doing, in a few words. */
function fetcherState(auto) {
  const ev = auto.events, budget = auto.budget;
  if (ev.control?.paused) return { text: "Paused: nothing is fetched until you resume.", tone: "warn" };
  if (ev.process) return { text: ev.process_kind === "matchday" ? `Reading ${ev.process} matches that have just reached half time or full time.` : `Fetching ${ev.process} now.`, tone: "accent" };
  if (ev.retry?.length) return { text: `${plural(ev.retry.length, "match", "matches")} you asked for will be read next.`, tone: "accent" };
  if (budget.whoscored.left <= 0) return { text: "Today's catching-up limit is reached: it carries on tomorrow. Matches played today are still read at full time.", tone: "outline" };
  if (ev.rest_until > nowSec()) return { text: `Resting between runs until ${new Date(ev.rest_until * 1000).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}.`, tone: "outline" };
  return { text: "Waiting for the next check.", tone: "outline" };
}

export function FetchControls({ auto, reload }) {
  const { busy, error, run } = useAction(reload);
  const limits = auto.prefs.limits, budget = auto.budget;
  const setLimit = (source, value) => run(() => api.put("/api/data/auto", { limits: { [source]: Number(value) } }));
  const eventsOn = Boolean(auto.events.enabled);
  const state = fetcherState(auto);
  const options = (list, current) => [...new Set([...list, current])].sort((a, b) => a - b).map((n) => ({ value: String(n), label: n.toLocaleString("en-GB") }));
  const md = budget.matchday;
  const today = auto.today || { matches: 0, favourites: 0 };
  return html`<${Card} title="Fetching: limits and pace"
    sub="The sources are public websites, so the updater reads like a patient person, not a crawler: one page at a time, with pauses. Each number below counts pages read by the updater since midnight; pages you open yourself load at once and are never held back.">
    <div class="stack" style=${{ "--gap": "16px" }}>
      <div class="fetch-limits">
        <div class="stack" style=${{ "--gap": "8px" }}>
          <${Usage} label="Understat match pages" used=${budget.understat.used} limit=${budget.understat.limit} />
          <label class="row" style=${{ gap: "8px" }}><span class="xsmall muted">At most</span>
            <${Select} compact label="Understat match pages per day" value=${String(limits.understat)} options=${options(UNDERSTAT_LIMITS, limits.understat)} onChange=${(v) => setLimit("understat", v)} />
            <span class="xsmall muted">a day, one every 1.5 s</span></label>
          <span class="xsmall muted">One page per finished match: its scorers, shots and positions. League tables are not counted. A matchday across five leagues needs about 20 to 60 (a page is read after the match, and once more when its numbers have settled), so the limit only matters while a new install fills earlier seasons.</span>
        </div>
        <div class="stack" style=${{ "--gap": "8px" }}>
          <${Usage} label="Event data, catching up (WhoScored)" used=${budget.whoscored.used} limit=${budget.whoscored.limit} />
          <label class="row" style=${{ gap: "8px" }}><span class="xsmall muted">At most</span>
            <${Select} compact label="Event matches caught up per day" value=${String(limits.whoscored)} options=${options(WHOSCORED_LIMITS, limits.whoscored)} onChange=${(v) => setLimit("whoscored", v)} />
            <span class="xsmall muted">matches a day, 20 a run, 10–20 s apart</span></label>
          <span class="xsmall muted">Older finished matches whose event data is missing. One match is one page read in the browser (about 15 s). It waits while matches are being played.</span>
        </div>
        ${md ? html`<div class="stack" style=${{ "--gap": "8px" }}>
          <${Usage} label="Event data on matchday (WhoScored)" used=${md.used} limit=${md.limit} />
          <span class="xsmall muted">Set by the fixture list, not by you: four reads for each of today's ${plural(today.matches, "match", "matches")} in your event leagues${today.favourites ? `, six more for each of the ${plural(today.favourites, "one", "ones")} a favourite team plays (half-time reads every three minutes until the break)` : ""}, and ten to spare. Each match is read at its 90th minute and every three minutes until WhoScored says full time; the ones you follow from the 45th minute too, every three minutes until half time. These go first, and do not use the catching-up limit.</span>
        </div>` : null}
      </div>
      ${eventsOn ? html`<div class="row between wrap fetch-state" style=${{ gap: "10px" }}>
        <span class="row" style=${{ gap: "8px" }}><${Badge} tone=${state.tone}>${auto.events.control?.paused ? "Paused" : auto.events.process ? "Running" : "Idle"}</${Badge}><span class="small">${state.text}</span></span>
        <span class="row" style=${{ gap: "8px" }}>
          ${auto.events.control?.paused
            ? html`<${Button} size="sm" icon="play" disabled=${busy} onClick=${() => run(() => api.post("/api/events/pause", { paused: false }))}>Resume</${Button}>`
            : html`<${Button} size="sm" icon="pause" disabled=${busy} onClick=${() => run(() => api.post("/api/events/pause", { paused: true }))} title="Stop now and start nothing until you resume">Pause</${Button}>`}
          ${auto.events.process ? html`<${Button} size="sm" kind="quiet" disabled=${busy} onClick=${() => run(() => api.post("/api/events/stop"))} title="End this run at its next match; the next one starts as usual">Stop this run</${Button}>` : null}
        </span>
      </div>
      <p class="xsmall muted">Stopping is always safe: the fetcher finishes the match in hand, keeps everything it read, and carries on from there next time.</p>` : null}
      ${error ? html`<${Notice} tone="crit" icon="alert">${error.message}</${Notice}>` : null}
    </div>
  </${Card}>`;
}

export function FetchPlan({ auto }) {
  const rows = auto.plan || [];
  if (!rows.length) return null;
  const events = rows.some((r) => r.events_played != null);
  const cols = [
    { key: "label", label: "League season", sortable: false, className: "strong" },
    { key: "pages_left", label: "Match pages left", num: true, sortable: false, render: (r) => r.pages_left || "–" },
    { key: "pages_days", label: "At your limit", sortable: false, render: (r) => (r.pages_left ? daysText(r.pages_days) : html`<span class="muted">complete</span>`) },
    ...(events ? [
      { key: "events_stored", label: "Event matches", num: true, sortable: false, render: (r) => (r.events_played == null ? html`<span class="muted">not fetched</span>` : `${r.events_stored} of ${r.events_played}`) },
      { key: "events_parked", label: "Waiting for you", num: true, sortable: false, render: (r) => r.events_parked || "–" },
      { key: "events_days", label: "At your limit", sortable: false, render: (r) => (r.events_played == null ? "" : r.events_left ? daysText(r.events_days) : html`<span class="muted">complete</span>`) },
    ] : []),
  ];
  return html`<${Card} flush title="Fetch plan" sub="What is still to come for every league season the updater keeps, and roughly how long it takes at today's limits. Matches waiting for you are in Needs your eye below.">
    <${DataTable} columns=${cols} rows=${rows} rowKey=${(r) => r.league + r.season} dense caption="Fetch plan" />
  </${Card}>`;
}

// ------------------------------------------------------------------ the review: what the matching could not place, and what could not be read

function CandidateLink({ item, kind, review, onLink, busy }) {
  const options = item.candidates.map((c) => ({
    value: String(c.id),
    label: kind === "players" ? `${c.name} · ${c.team}${c.same_club ? "" : " (other club)"} · ${c.minutes} min` : `${c.home} v ${c.away} ${c.hg ?? "?"}–${c.ag ?? "?"} · ${c.date}${c.days ? ` (${c.days} day${c.days > 1 ? "s" : ""} off)` : ""}`,
  }));
  const [pick, setPick] = useState(options[0]?.value || "");
  return html`<div class="row wrap" style=${{ gap: "8px" }}>
    ${options.length ? html`<${Select} compact label=${`Understat ${kind === "players" ? "player" : "match"} for ${kind === "players" ? item.name : `${item.home} v ${item.away}`}`} value=${pick} options=${options} onChange=${setPick} />
      <${Button} size="sm" disabled=${busy || !pick} onClick=${() => onLink(kind, item[kind === "players" ? "ws" : "game"], Number(pick))}>Link</${Button}>`
      : html`<span class="xsmall muted">No likely candidate${kind === "players" ? " at his club" : " within three days"}.</span>`}
    ${kind === "players" ? html`<${Button} size="sm" kind="quiet" disabled=${busy} onClick=${() => onLink("players", item.ws, 0)} title="He is not in Understat's data: stop listing him here">Not in Understat</${Button}>` : null}
  </div>`;
}

function Review({ league, season, reloadAll }) {
  const q = useApi("/api/events/review", { league, season }, { staleMs: 0 });
  const { busy, error, run } = useAction(() => { q.reload(); reloadAll?.(); });
  const link = (kind, ws, us) => run(() => api.put("/api/events/link", { league, season, kind, ws, us }));
  const retry = (game) => run(() => api.post("/api/events/retry", { league, season, game }));
  const skip = (game, value) => run(() => api.post("/api/events/skip", { league, season, game, skip: value }));
  return html`<${Async} q=${q}>${(r) => {
    const nothing = !r.players.length && !r.matches.length && !r.failed.length && !r.manual.length;
    if (nothing) return html`<p class="small muted">Nothing needs you here: every stored match and every player with 90+ minutes is matched, and nothing failed.</p>`;
    return html`<div class="stack review" style=${{ "--gap": "18px" }}>
      ${error ? html`<${Notice} tone="crit" icon="alert">${error.message}</${Notice}>` : null}
      ${r.players.length ? html`<section class="stack" style=${{ "--gap": "8px" }}>
        <h3 class="h4">Players not matched (${r.players.length})</h3>
        <p class="xsmall muted">The automatic matching only links a name it is sure of, at the same club. These it was not sure of. Pick the Understat player he is, or say he is not in Understat. Your choice always wins, and can be undone below.</p>
        ${r.players.map((p) => html`<div key=${p.ws} class="review-row">
          <div><b>${p.name}</b> <span class="xsmall muted">· ${p.clubs.join(" / ")} · ${p.minutes} min in the event data</span></div>
          <${CandidateLink} item=${p} kind="players" review=${r} onLink=${link} busy=${busy} />
        </div>`)}
      </section>` : null}
      ${r.matches.length ? html`<section class="stack" style=${{ "--gap": "8px" }}>
        <h3 class="h4">Matches not matched (${r.matches.length})</h3>
        <p class="xsmall muted">A match is linked when both sources agree on the date, the clubs (home and away) and the score. Here they do not, so one of them has it differently. If it is the same match, link it.</p>
        ${r.matches.map((m) => html`<div key=${m.game} class="review-row">
          <div><b>${m.home} v ${m.away}</b> <span class="xsmall muted">· ${m.score ? m.score.join("–") : "?"} · ${m.date} (WhoScored)</span></div>
          <${CandidateLink} item=${m} kind="matches" review=${r} onLink=${link} busy=${busy} />
        </div>`)}
      </section>` : null}
      ${r.failed.length ? html`<section class="stack" style=${{ "--gap": "8px" }}>
        <h3 class="h4">Matches that could not be read (${r.failed.length})</h3>
        <p class="xsmall muted">Each is tried again by itself up to three times, half a day apart; after that it waits for you. Retry reads it next, ahead of everything else.</p>
        ${r.failed.map((f) => html`<div key=${f.game} class="review-row">
          <div><b>${f.label || f.game}</b> <span class="xsmall muted">· ${f.date || ""} · ${plural(f.attempts, "attempt")}${f.skip ? " · skipped" : f.waiting ? " · waiting for you" : ""}</span>
            <div class="xsmall muted">${f.error}</div></div>
          <div class="row" style=${{ gap: "8px" }}>
            <${Button} size="sm" disabled=${busy} onClick=${() => retry(f.game)}>Retry now</${Button}>
            ${f.skip ? html`<${Button} size="sm" kind="quiet" disabled=${busy} onClick=${() => skip(f.game, false)}>Unskip</${Button}>`
              : html`<${Button} size="sm" kind="quiet" disabled=${busy} onClick=${() => skip(f.game, true)} title="Never try this match again">Skip</${Button}>`}
          </div>
        </div>`)}
      </section>` : null}
      ${r.manual.length ? html`<section class="stack" style=${{ "--gap": "8px" }}>
        <h3 class="h4">Your links (${r.manual.length})</h3>
        ${r.manual.map((m) => html`<div key=${m.kind + m.ws} class="review-row">
          <div><b>${m.ws_name}</b> <span class="xsmall muted">→ ${m.us ? m.us_name : "not in Understat (left out)"}</span></div>
          <${Button} size="sm" kind="quiet" disabled=${busy} onClick=${() => link(m.kind, m.ws, null)}>Undo</${Button}>
        </div>`)}
      </section>` : null}
    </div>`;
  }}</${Async}>`;
}

export function EventReview({ status, meta, reload }) {
  const items = (status.events || []).filter((e) => e.matches > 0);
  const needs = (e) => (e.unlinked_n || 0) + (e.matches_unlinked || 0) + (e.failed_n || 0);
  const ordered = [...items].sort((a, b) => needs(b) - needs(a) || b.season - a.season);
  const [pick, setPick] = useState(ordered[0] ? `${ordered[0].league}:${ordered[0].season}` : "");
  if (!items.length) return null;
  const [league, season] = pick.split(":");
  const options = ordered.map((e) => ({ value: `${e.league}:${e.season}`, label: `${leagueName(meta.meta, e.league)} ${seasonLabel(e.season)}${needs(e) ? ` · ${needs(e)} to look at` : ""}` }));
  return html`<${Card} title="Event data: needs your eye" sub="What the automatic matching could not place with certainty, and the matches that could not be read. Fix them here; everything is reversible."
    actions=${html`<${Select} compact label="League season" value=${pick} options=${options} onChange=${setPick} />`}>
    <div class=${cls("stack")}><${Review} key=${pick} league=${league} season=${Number(season)} reloadAll=${reload} /></div>
  </${Card}>`;
}

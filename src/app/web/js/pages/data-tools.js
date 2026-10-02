// Data page tools: fetch on demand, check the connection, background enrichment (squad lists, ages, positions), birthdates and event-data coverage.
import { html, useEffect, useState } from "../lib/html.js";
import { api, invalidate } from "../lib/api.js";
import { leagueName } from "../lib/scope.js";
import { plural, relTime, seasonLabel } from "../lib/format.js";
import { Icon } from "../lib/icons.js";
import { Badge, Button, Card, Field, Notice, Switch } from "../ui/common.js";

export function Progress({ done, total, failed = 0, tone }) {
  const p = total ? Math.min(1, (done + failed) / total) : 0;
  return html`<div class=${"progress" + (tone ? " " + tone : "")} role="progressbar" aria-valuenow=${Math.round(p * 100)} aria-valuemin="0" aria-valuemax="100"><i style=${{ width: p * 100 + "%" }}></i></div>`;
}

export function SyncCard({ status, meta, onStarted }) {
  const leagues = meta.meta.leagues, seasons = meta.meta.seasons;
  const [picked, setPicked] = useState(["EPL"]);
  const [years, setYears] = useState([meta.meta.current_season]);
  const [force, setForce] = useState(false);
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);
  const blocked = status.mode.demo || status.mode.offline;
  const toggle = (list, set, v) => set(list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);

  useEffect(() => {
    if (!job || job.state !== "running") return undefined;
    const t = setInterval(async () => {
      try {
        const next = await api.get(`/api/data/jobs/${job.id}`);
        setJob(next);
        if (next.state !== "running") { invalidate(); onStarted(); }
      } catch (e) { setError(e); }
    }, 900);
    return () => clearInterval(t);
  }, [job?.id, job?.state]);

  const start = async () => {
    setError(null);
    try { setJob(await api.post("/api/data/sync", { leagues: picked, seasons: years, force })); } catch (e) { setError(e); }
  };
  return html`<${Card} title="Fetch league seasons now" sub="The updater already keeps the current and the previous season fresh. Use this to load older seasons or other leagues, or to refresh something straight away. It reads at a polite pace and keeps going if you leave the page.">
    ${blocked ? html`<${Notice} tone="warn" icon="alert">${status.mode.demo ? "Demo mode: everything is synthetic and there is nothing to fetch. Start the app without --demo to load real data." : "Offline mode is on: fetching is disabled."}</${Notice}>` : null}
    <div class="stack" style=${{ "--gap": "16px", marginTop: blocked ? "14px" : 0 }}>
      <${Field} label="Leagues"><div class="chipgroup">${leagues.map((l) => html`<button type="button" class="chip" key=${l.code} aria-pressed=${String(picked.includes(l.code))} onClick=${() => toggle(picked, setPicked, l.code)}>${l.name}</button>`)}</div></${Field}>
      <${Field} label="Seasons" hint="Finished seasons never change, so they are fetched once and kept."><div class="chipgroup">${seasons.map((s) => html`<button type="button" class="chip" key=${s.season} aria-pressed=${String(years.includes(s.season))} onClick=${() => toggle(years, setYears, s.season)}>${s.label}</button>`)}</div></${Field}>
      <${Switch} checked=${force} onChange=${setForce}>Fetch finished seasons again</${Switch}>
      <div class="row" style=${{ gap: "12px" }}>
        <${Button} kind="primary" icon="download" disabled=${blocked || !picked.length || !years.length || job?.state === "running"} onClick=${start}>${job?.state === "running" ? "Fetching…" : `Fetch ${plural(picked.length * years.length, "league season")}`}</${Button}>
        ${error ? html`<span class="small" style=${{ color: "var(--crit-ink)" }}>${error.message}</span>` : null}
      </div>
      ${job ? html`<div class="jobbox">
        <div class="row between"><b>${job.label}</b><${Badge} tone=${job.state === "running" ? "accent" : job.failed ? "warn" : "good"}>${job.state}</${Badge}></div>
        <${Progress} done=${job.done} total=${job.total} failed=${job.failed} />
        <div class="xsmall muted">${job.done} of ${job.total} done${job.failed ? `, ${job.failed} failed` : ""} · ${job.elapsed}s</div>
        <pre class="joblog">${job.log.join("\n") || "Waiting for the first response…"}</pre>
      </div>` : null}
    </div>
  </${Card}>`;
}

export function CheckCard({ status }) {
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const run = async () => {
    setRunning(true); setError(null);
    try { setResult(await api.post("/api/data/check")); } catch (e) { setError(e); } finally { setRunning(false); }
  };
  return html`<${Card} title="Connection check" sub=${status.mode.demo ? "Runs the same steps against the demo world." : "Reads a league, a match and a player from Understat, a squad list from ESPN and a birthdate from Wikidata, without saving anything. Run it when a page shows an error."}
    actions=${html`<${Button} size="sm" icon="refresh" disabled=${running || status.mode.offline} onClick=${run}>${running ? "Checking…" : result ? "Run again" : "Run check"}</${Button}>`}>
    ${error ? html`<${Notice} tone="crit" icon="alert">${error.message}</${Notice}>` : null}
    ${result ? html`<div class="stack" style=${{ "--gap": "10px" }}>
      ${result.steps.map((st) => html`<div class="checkstep" key=${st.name}>
        <span class=${"tone " + (st.ok ? "positive" : "negative")}><${Icon} name=${st.ok ? "check" : "alert"} size="sm" /></span>
        <div class="stack" style=${{ "--gap": "2px", minWidth: 0 }}><b>${st.name}</b><span class=${st.ok ? "secondary small" : "small"} style=${st.ok ? null : { color: "var(--crit-ink)" }}>${st.detail}</span>${st.hint && !st.ok ? html`<span class="xsmall muted">${st.hint}</span>` : null}</div>
        <span class="xsmall muted num">${st.ms} ms</span>
      </div>`)}
      <p class="small" style=${{ marginTop: "4px" }}><b>${result.ok ? "Everything can be read." : "Something is wrong: fix the first failing step."}</b></p>
    </div>` : html`<p class="muted small">${status.mode.offline ? "Offline mode is on, so there is nothing to check." : "Not run yet."}</p>`}
  </${Card}>`;
}

export function Enrichment({ status }) {
  const idle = { kind: "rosters", total: 0, done: 0, failed: 0, running: false, last_error: null };
  const rows = [
    { key: "rosters", label: "Squad lists", source: "ESPN", p: status.enrichment.rosters || idle, note: "Exact birthdates, goalkeepers included. One league season is about 20 requests; finished seasons are fetched once and kept." },
    { key: "ages", label: "Other player ages", source: "Wikidata", p: status.enrichment.ages, note: "Only for players a squad list leaves out. Matched by name and club, and left blank when not sure." },
    { key: "roles", label: "Favourite positions", source: "Understat player pages", p: status.enrichment.roles, note: "Sharpens the role of players who play in several positions." },
  ];
  return html`<${Card} title="Background enrichment" sub="Optional details that fill in quietly after a page has loaded.">
    <div class="stack" style=${{ "--gap": "16px" }}>
      ${rows.map((r) => html`<div key=${r.key} class="stack" style=${{ "--gap": "6px" }}>
        <div class="row between"><b>${r.label}</b><span class="muted small">${r.source}</span></div>
        <${Progress} done=${r.p.done} total=${r.p.total || 1} failed=${r.p.failed} />
        <div class="row between xsmall muted"><span>${r.p.running ? `Running: ${r.p.done} of ${r.p.total}` : r.p.total ? `Last run: ${r.p.done} of ${r.p.total}${r.p.failed ? `, ${r.p.failed} failed` : ""}` : "Nothing waiting"}</span>${r.p.last_error ? html`<span style=${{ color: "var(--warn-ink)" }}>${r.p.last_error}</span>` : null}</div>
        <div class="xsmall muted">${r.note}</div>
      </div>`)}
      <div class="small"><b class="num">${status.enrichment.favorites_known}</b> players have a known favourite position.</div>
    </div>
  </${Card}>`;
}

/** Exact birthdates from club squad lists: what is stored, how well it matched Understat's players, and who is still unknown. */
export function Birthdates({ status, meta }) {
  const items = status.birthdates || [];
  const now = Date.now() / 1000;
  return html`<${Card} title="Player ages" sub="Understat has no birthdates. Each club's squad list (ESPN) does, so ages are exact. Fetched in the background, then kept on this computer.">
    ${items.length ? html`<div class="stack" style=${{ "--gap": "18px" }}>
      ${items.map((e) => {
        const share = e.regulars ? e.regulars_linked / e.regulars : null;
        return html`<div key=${e.league + e.season} class="stack" style=${{ "--gap": "6px" }}>
          <div class="row between"><b>${leagueName(meta.meta, e.league)} ${seasonLabel(e.season)}</b><${Badge} tone=${e.pending.length || e.sparse ? "warn" : "good"}>${e.sparse ? "Sparse" : e.pending.length ? "Partial" : e.final ? "Final" : "Live"}</${Badge}></div>
          ${share != null ? html`<${Progress} done=${e.regulars_linked} total=${e.regulars} />` : null}
          <div class="row between xsmall muted">
            <span>${plural(e.clubs, "club")} · ${plural(e.players, "player")} listed${e.linked != null ? ` · ${e.linked} matched to Understat` : ""}</span>
            <span>${relTime(now - e.fetched)}</span>
          </div>
          ${share != null ? html`<div class="xsmall muted"><b class="num">${e.regulars_linked}</b> of ${e.regulars} players with 450+ minutes have an exact birthdate (${Math.round(share * 100)}%). The rest stay blank unless Wikidata is sure of them.</div>` : null}
          ${e.sparse ? html`<div class="xsmall muted">ESPN lists only about ${e.median_squad} ${e.median_squad === 1 ? "player" : "players"} a club for this season, so most ages here come from Wikidata. It is asked again after a week.</div>` : null}
          ${e.pending.length ? html`<div class="xsmall muted">Not read yet, retried automatically: ${e.pending.join(", ")}.</div>` : null}
          ${e.compared ? html`<div class="xsmall muted">Cross-check: Wikidata, sure of the club, was also found for <b class="num">${e.compared}</b> of them and gives another date for <b class="num">${e.disagree}</b>${e.blank ? ` (${e.blank} by more than a year, so ${e.blank === 1 ? "that age is" : "those ages are"} left blank)` : ""}.</div>` : null}
          ${e.disagree ? html`<details class="xsmall"><summary class="muted">Where the two sources differ</summary>
            <ul class="plain">${e.disagree_examples.map((x) => html`<li key=${x.name}>${x.name} <span class="muted">· ${x.team} · squad list ${x.squad_list}, Wikidata ${x.wikidata}${x.blank ? " · age left blank" : " · squad list used"}</span></li>`)}</ul>
            <p class="muted">To settle one yourself, add the right date to <code>birthdates.json</code> (see the README).</p></details>` : null}
          ${e.missing?.length ? html`<details class="xsmall"><summary class="muted">Regulars without an exact birthdate</summary>
            <ul class="plain">${e.missing.map((m) => html`<li key=${m.id}>${m.name} <span class="muted">· ${m.team} · ${m.minutes} min</span></li>`)}</ul></details>` : null}
        </div>`;
      })}
    </div>` : html`<p class="small muted">${status.mode.demo ? "Demo mode: ages come from the demo world." : status.mode.offline ? "Offline mode: squad lists are not fetched." : "None fetched yet. They are fetched in the background (about 20 requests for a league and season)."}</p>`}
  </${Card}>`;
}

/** Event data per league season: how many matches are stored, how well players link to Understat's, and who could not be placed. */
export function EventData({ status, meta }) {
  const order = meta.meta.leagues.map((l) => l.code);
  const items = [...(status.events || [])].sort((a, b) => order.indexOf(a.league) - order.indexOf(b.league) || b.season - a.season);   // league order, newest season first
  const now = Date.now() / 1000;
  const demo = status.mode.demo;
  return html`<${Card} title=${demo ? "Event data: what is stored" : "Event data (WhoScored): what is stored"}
    sub=${demo ? "Passes, duels, tackles, carries and pitch positions, in the same shape the real app reads from WhoScored. In the demo world they are generated here, in the background, and nothing is downloaded. Every metric and map is worked out from the stored matches."
      : "Passes, duels, tackles, carries and pitch positions. Each match is fetched once, kept whole, and every metric and map is worked out from it here, so nothing is asked for again."}>
    ${items.length ? html`<div class="stack" style=${{ "--gap": "18px" }}>
      ${items.map((e) => {
        const run = e.status || {};
        const total = e.total ?? run.finished_matches ?? null;
        const state = run.running ? (demo ? "Generating now" : "Fetching now") : run.stalled ? "Stopped" : total && e.matches >= total ? "Complete" : "Partial";
        return html`<div key=${e.league + e.season} class="stack" style=${{ "--gap": "6px" }}>
          <div class="row between"><b>${leagueName(meta.meta, e.league)} ${seasonLabel(e.season)}</b><${Badge} tone=${state === "Complete" ? "good" : run.running ? "accent" : "warn"}>${state}</${Badge}></div>
          <${Progress} done=${e.matches} total=${total || e.matches || 1} />
          <div class="row between xsmall muted">
            <span>${e.matches}${total ? ` of ${total}` : ""} matches stored${run.running && run.total ? ` · this run: ${run.done || 0} of ${run.total}` : ""}${run.failed ? ` · ${run.failed} failed` : ""}</span>
            <span>${run.running ? "" : run.updated ? `Last run ${relTime(now - run.updated)}` : ""}</span>
          </div>
          ${e.linked != null ? html`<div class="xsmall muted"><b class="num">${e.linked}</b> players matched to Understat${e.unlinked_n ? `, ${e.unlinked_n} with 90+ minutes could not be matched safely and are left out` : ""}.</div>` : null}
          ${run.last_error ? html`<div class="xsmall muted">Last error: ${run.last_error}</div>` : null}
          ${e.unlinked?.length ? html`<details class="xsmall"><summary class="muted">Players left out</summary>
            <ul class="plain">${e.unlinked.map((u) => html`<li key=${u.id}>${u.name} <span class="muted">· ${u.teams.join(" / ")} · ${Math.round(u.minutes)} min${u.candidates?.length > 1 ? " · ambiguous name" : ""}</span></li>`)}</ul></details>` : null}
        </div>`;
      })}
    </div>` : demo ? html`<p class="small muted">${status.mode.demo_events ? "Nothing generated yet: the demo world starts filling this in a few seconds after it starts, current seasons first." : "Switched off for this run (PREM_DEMO_EVENTS=0), so event metrics are blank in the demo world."}</p>`
      : html`<p class="small muted">Nothing stored yet. Switch event data on above (it needs Chrome, Chromium, Brave or Edge, and the optional <code>events</code> extra), or run <code>uv run --extra events prem events sync --league EPL --seasons ${meta.meta.current_season}</code> once.</p>`}
  </${Card}>`;
}

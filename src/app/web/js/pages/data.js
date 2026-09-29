// Data: what is on this computer, how fresh it is, and how to refresh it.
import { html, useEffect, useState } from "../lib/html.js";
import { api, invalidate, useApi } from "../lib/api.js";
import { useMeta, leagueName } from "../lib/scope.js";
import { bytes, plural, relTime, seasonLabel, nf } from "../lib/format.js";
import { Icon } from "../lib/icons.js";
import { Async, Badge, Button, Card, Field, Notice, PageHead, Switch, useDocumentTitle, ErrorState } from "../ui/common.js";
import { DataTable } from "../ui/table.js";

function Progress({ done, total, failed }) {
  const p = total ? (done + failed) / total : 0;
  return html`<div class="progress" role="progressbar" aria-valuenow=${Math.round(p * 100)} aria-valuemin="0" aria-valuemax="100"><i style=${{ width: p * 100 + "%" }}></i></div>`;
}

function SyncCard({ status, meta, onStarted }) {
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
  return html`<${Card} title="Fetch from Understat" sub="Understat is slow to read on purpose (a few requests per second), so a large sync takes a while. It keeps running if you leave this page.">
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

function CheckCard({ status }) {
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const run = async () => {
    setRunning(true); setError(null);
    try { setResult(await api.post("/api/data/check")); } catch (e) { setError(e); } finally { setRunning(false); }
  };
  return html`<${Card} title="Connection check" sub=${status.mode.demo ? "Runs the same steps against the demo world." : "Reads a league, a match and a player from Understat, and a birthdate from Wikidata, without saving anything. Run it when a page shows an error."}
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

function Enrichment({ status }) {
  const rows = [
    { key: "ages", label: "Player ages", source: "Wikidata", p: status.enrichment.ages, note: "Matched by name and club. Only used for the age filter and youth insights." },
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

function DataView({ status, meta, reload }) {
  const cache = status.leagues;
  const rows = [...cache].sort((a, b) => a.league.localeCompare(b.league) || b.season - a.season);
  const now = Date.now() / 1000;
  const cols = [
    { key: "league", label: "League", sortable: false, className: "strong", render: (r) => leagueName(meta.meta, r.league) },
    { key: "season", label: "Season", sortable: false, render: (r) => seasonLabel(r.season) },
    { key: "state", label: "State", sortable: false, render: (r) => html`<${Badge} tone=${r.complete ? "good" : ""}>${r.complete ? "Final" : "Live"}</${Badge}>` },
    { key: "fetched_at", label: "Fetched", sortable: false, render: (r) => relTime(now - r.fetched_at) },
  ];
  const kinds = Object.entries(status.store.kinds);
  const KIND = { league: "League seasons", player: "Player pages", match: "Match shot maps", team: "Team pages", fav: "Favourite positions", ages: "Birthdates", kv: "Your data" };
  return html`
    <${PageHead} eyebrow="System" title="Data" sub=${status.mode.demo ? "You are looking at a synthetic demo world." : "Everything you see is served from a local cache. Understat is only contacted when you ask for fresh data."}
      actions=${html`<${Button} icon="refresh" onClick=${reload}>Refresh</${Button}>`} />
    <div class="tiles">
      <div class="tile"><span class="label">Source</span><span class="value figure" style=${{ fontSize: "24px" }}>${status.mode.demo ? "Demo world" : status.mode.offline ? "Offline cache" : "Understat"}</span><span class="delta">${status.mode.demo ? "synthetic players and results" : "read at a polite pace, cached locally"}</span></div>
      <div class="tile"><span class="label">Cached items</span><span class="value figure">${status.store.total_items}</span><span class="delta">${bytes(status.store.total_bytes)} on disk</span></div>
      <div class="tile"><span class="label">League seasons</span><span class="value figure">${cache.length}</span><span class="delta">${cache.filter((c) => c.complete).length} final, ${cache.filter((c) => !c.complete).length} live</span></div>
    </div>
    <div class="grid cols-2 top">
      <div class="stack">
        <${SyncCard} status=${status} meta=${meta} onStarted=${reload} />
        <${CheckCard} status=${status} />
        <${Enrichment} status=${status} />
      </div>
      <div class="stack">
        <${Card} flush title="League seasons on this computer" sub="Live seasons refresh when they get old; final seasons are kept for good.">
          ${rows.length ? html`<${DataTable} columns=${cols} rows=${rows} rowKey=${(r) => r.league + r.season} dense caption="Cached league seasons" />` : html`<div class="card-body muted">Nothing cached yet. Fetch a league on the left.</div>`}
        </${Card}>
        <${Card} title="Storage" sub=${status.store.path}>
          <dl class="kv">${kinds.map(([k, v]) => html`<dt key=${k + "d"}>${KIND[k] || k}</dt><dd key=${k}>${v.count} · ${bytes(v.bytes)}</dd>`)}</dl>
          <p class="xsmall muted" style=${{ marginTop: "12px" }}>Your shortlist and notes live in the same file and survive cache clears. Clear the cache with <code>prem clear --yes</code>.</p>
        </${Card}>
      </div>
    </div>`;
}

export default function DataPage() {
  const meta = useMeta();
  const q = useApi("/api/data/status", null, { pollMs: 4000, staleMs: 1000 });
  useDocumentTitle("Data");
  return html`<${Async} q=${q}>${(d) => html`<${DataView} status=${d} meta=${meta} reload=${q.reload} />`}</${Async}>`;
}

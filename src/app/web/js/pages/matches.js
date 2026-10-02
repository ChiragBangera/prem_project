// Matches: every fixture of a matchweek as a compact card: the score, who scored, and the numbers behind the result.
import { html, useEffect, useMemo, useRef } from "../lib/html.js";
import { useApi } from "../lib/api.js";
import { useScope } from "../lib/scope.js";
import { href, setQuery, useLocation } from "../lib/router.js";
import { cls, dateShort, plural } from "../lib/format.js";
import { Async, Button, DataNotices, EmptyState, Notice, PageHead, Segmented, useDocumentTitle } from "../ui/common.js";
import { MatchCard, kickoff } from "../ui/matchcard.js";

function RoundStrip({ rounds, value, onPick }) {
  const ref = useRef(null);
  useEffect(() => { ref.current?.querySelector('[aria-current="true"]')?.scrollIntoView({ block: "nearest", inline: "center" }); }, [value]);
  return html`<div class="roundstrip" ref=${ref} role="group" aria-label="Matchweeks">
    ${rounds.map((r) => html`<button type="button" key=${r.round} class=${cls("round", r.played ? "done" : "todo")} aria-current=${String(r.round === value)} onClick=${() => onPick(r.round)} title=${`Matchweek ${r.round}: ${dateShort(r.from)}${r.to !== r.from ? ` to ${dateShort(r.to)}` : ""}`}>${r.round}</button>`)}
  </div>`;
}

/** Group matches by the day they kick off in the viewer's own time zone. */
function byDay(matches) {
  const days = [];
  const index = new Map();
  for (const m of [...matches].sort((a, b) => (a.utc || a.dt).localeCompare(b.utc || b.dt))) {
    const k = kickoff(m);
    let day = index.get(k.key);
    if (!day) { day = { key: k.key, label: k.long, matches: [] }; index.set(k.key, day); days.push(day); }
    day.matches.push(m);
  }
  return days;
}

function RoundSummary({ matches }) {
  const played = matches.filter((m) => m.played);
  if (!played.length) return null;
  const goals = played.reduce((s, m) => s + m.hg + m.ag, 0);
  const home = played.filter((m) => m.hg > m.ag).length, draw = played.filter((m) => m.hg === m.ag).length, away = played.length - home - draw;
  const xg = played.reduce((s, m) => s + (m.hxg ?? 0) + (m.axg ?? 0), 0);
  return html`<div class="round-summary">
    <span><b class="num">${played.length}</b> played</span>
    <span><b class="num">${goals}</b> goals (${(goals / played.length).toFixed(1)} a game)</span>
    <span><b class="num">${xg.toFixed(1)}</b> total xG</span>
    <span>${home} home wins · ${draw} draws · ${away} away wins</span>
  </div>`;
}

function MatchesView({ d, query }) {
  const { scope, meta, rounds, latest_round: latest, coverage } = d;
  const view = query.view === "flagged" ? "flagged" : "round";
  const round = Number(query.round) || latest || rounds.find((r) => !r.played)?.round || 1;
  const current = rounds.find((r) => r.round === round) || rounds[0];
  const flagged = useMemo(() => rounds.flatMap((r) => r.matches.filter((m) => m.flag).map((m) => ({ ...m, round: r.round }))).sort((a, b) => b.dt.localeCompare(a.dt)), [rounds]);
  const list = view === "flagged" ? flagged : current?.matches || [];
  const days = useMemo(() => (view === "flagged" ? [{ key: "all", label: `${plural(flagged.length, "result")} that went against the chances`, matches: flagged }] : byDay(list)), [view, list, flagged]);
  const missingScorers = coverage && coverage.played > coverage.scorers;

  return html`
    <${PageHead} eyebrow=${`${scope.league_name} · ${scope.label}`} title="Matches"
      sub=${view === "flagged" ? `${plural(flagged.length, "result")} this season went against what the chances said: the winner created less, or the favourite only drew.` : `Matchweek ${round}: results with the scorers, and the numbers that explain them. Times are in your time zone.`}
      actions=${html`<${Segmented} label="View" value=${view} onChange=${(v) => setQuery({ view: v === "round" ? null : v })} options=${[{ value: "round", label: "By matchweek" }, { value: "flagged", label: `Results that lied (${flagged.length})` }]} />`} />
    <${DataNotices} scope=${scope} meta=${meta} />
    ${missingScorers ? html`<${Notice} icon="clock">Scorers are shown for ${coverage.scorers} of ${coverage.played} played matches. The rest arrive as the app downloads each match page in the background (<a class="link" href=${href("/data")}>Data status</a>).</${Notice}>` : null}
    ${view === "round" ? html`
      <div class="round-nav">
        <${Button} kind="quiet" icon="chevronLeft" title="Previous matchweek" disabled=${round <= 1} onClick=${() => setQuery({ round: round - 1 })} />
        <${RoundStrip} rounds=${rounds} value=${round} onPick=${(r) => setQuery({ round: r })} />
        <${Button} kind="quiet" icon="chevronRight" title="Next matchweek" disabled=${round >= rounds.length} onClick=${() => setQuery({ round: round + 1 })} />
      </div>
      <div class="round-head"><h2>Matchweek ${round}</h2><span class="muted">${current ? `${dateShort(current.from)}${current.to !== current.from ? ` to ${dateShort(current.to)}` : ""}` : ""}</span><${RoundSummary} matches=${list} /></div>` : null}
    ${list.length
      ? days.map((day) => html`<section class="day" key=${day.key}>
          <h3 class="day-title">${day.label}<span class="muted">${view === "flagged" ? "" : plural(day.matches.length, "match", "matches")}</span></h3>
          <div class="mgrid">${day.matches.map((m) => html`<${MatchCard} key=${m.id} m=${m} showDate=${view === "flagged"} />`)}</div>
        </section>`)
      : html`<${EmptyState} icon="calendar" title="Nothing here" text=${view === "flagged" ? "No result this season strongly defied its chances." : "No matches in this matchweek."} />`}
  `;
}

export default function Matches() {
  const { league, season } = useScope();
  const { query } = useLocation();
  const q = useApi("/api/matches", { league, season });
  useDocumentTitle("Matches");
  return html`<${Async} q=${q}>${(d) => html`<${MatchesView} d=${d} query=${query} />`}</${Async}>`;
}

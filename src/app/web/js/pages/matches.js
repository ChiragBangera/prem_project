// Matches: every fixture of a matchweek as a compact card: the score, who scored, and the numbers behind the result. Pick a team to see its
// whole season instead (what is next, then every result), and "Results that lied" for the games that went against the chances.
import { html, useEffect, useMemo, useRef } from "../lib/html.js";
import { useApi } from "../lib/api.js";
import { useScope } from "../lib/scope.js";
import { href, setQuery, useLocation } from "../lib/router.js";
import { cls, dateShort, nf, plural } from "../lib/format.js";
import { Async, Button, DataNotices, EmptyState, Notice, PageHead, Segmented, Select, useDocumentTitle } from "../ui/common.js";
import { MatchCard, kickoff } from "../ui/matchcard.js";
import { finished, teamRecord, withResult } from "../lib/matchfmt.js";

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
  const played = matches.filter(finished).map(withResult);
  if (!played.length) return null;
  const goals = played.reduce((s, m) => s + m.hg + m.ag, 0);
  const home = played.filter((m) => m.hg > m.ag).length, draw = played.filter((m) => m.hg === m.ag).length, away = played.length - home - draw;
  const known = played.filter((m) => m.hxg != null && m.axg != null);   // a match Understat has not published has no xG: it is left out, not counted as 0
  const xg = known.reduce((s, m) => s + m.hxg + m.axg, 0);
  return html`<div class="round-summary">
    <span><b class="num">${played.length}</b> played</span>
    <span><b class="num">${goals}</b> goals (${(goals / played.length).toFixed(1)} a game)</span>
    ${known.length ? html`<span><b class="num">${xg.toFixed(1)}</b> total xG${known.length < played.length ? ` (${known.length} of ${played.length} matches)` : ""}</span>` : html`<span class="muted">no xG yet</span>`}
    <span>${home} home wins · ${draw} draws · ${away} away wins</span>
  </div>`;
}

function TeamSummary({ matches, team }) {
  const r = teamRecord(matches, team);
  if (!r.played) return null;
  return html`<div class="round-summary">
    <span><b class="num">${r.w}</b> won · <b class="num">${r.d}</b> drawn · <b class="num">${r.l}</b> lost</span>
    <span><b class="num">${r.gf}</b> scored, <b class="num">${r.ga}</b> conceded</span>
    ${r.xgKnown ? html`<span>xG <b class="num">${nf(r.xg, 1)}</b> for, <b class="num">${nf(r.xga, 1)}</b> against${r.xgKnown < r.played ? ` (${r.xgKnown} of ${r.played} games)` : ""}</span>` : null}
    ${r.flagged ? html`<span>${plural(r.flagged, "result")} against the chances</span>` : null}
  </div>`;
}

/** A run of cards under one heading: a day of a matchweek, or a part of a team's season. `top` is a heading straight under the page title. */
function Day({ day, counted, top }) {
  const H = top ? "h2" : "h3";
  return html`<section class="day">
    <${H} class="day-title">${day.label}<span class="muted">${counted ? plural(day.matches.length, "match", "matches") : ""}</span></${H}>
    <div class="mgrid">${day.matches.map((m) => html`<${MatchCard} key=${m.id} m=${m} showDate=${day.dates} />`)}</div>
  </section>`;
}

function MatchesView({ d, query }) {
  const { scope, meta, rounds, latest_round: latest, coverage } = d;
  const view = query.view === "flagged" ? "flagged" : "round";
  const all = useMemo(() => rounds.flatMap((r) => r.matches.map((m) => ({ ...m, round: r.round }))), [rounds]);
  const teams = useMemo(() => [...new Set(all.flatMap((m) => [m.home, m.away]))].sort((a, b) => a.localeCompare(b)), [all]);
  const team = teams.includes(query.team) ? query.team : "";
  const mine = useMemo(() => (team ? all.filter((m) => m.home === team || m.away === team) : all), [all, team]);
  const round = Number(query.round) || latest || rounds.find((r) => !r.played)?.round || 1;
  const current = rounds.find((r) => r.round === round) || rounds[0];
  const flagged = useMemo(() => mine.filter((m) => m.flag).sort((a, b) => b.dt.localeCompare(a.dt)), [mine]);
  const days = useMemo(() => {
    if (view === "flagged") return flagged.length ? [{ key: "all", label: `${plural(flagged.length, "result")} that went against the chances`, matches: flagged, dates: true }] : [];
    if (team) {
      const next = mine.filter((m) => !finished(m)).sort((a, b) => (a.utc || a.dt).localeCompare(b.utc || b.dt));
      const done = mine.filter(finished).sort((a, b) => (b.utc || b.dt).localeCompare(a.utc || a.dt));
      // the next three, then every result, then the rest of the fixtures: the latest result is never more than one row of cards away
      return [
        ...(next.length ? [{ key: "next", label: "Next up", matches: next.slice(0, 3), dates: true }] : []),
        ...(done.length ? [{ key: "done", label: "Results, latest first", matches: done, dates: true }] : []),
        ...(next.length > 3 ? [{ key: "later", label: "Later this season", matches: next.slice(3), dates: true }] : []),
      ];
    }
    return byDay(current?.matches || []).map((day) => ({ ...day, dates: false }));
  }, [view, flagged, team, mine, current]);
  const shown = days.reduce((n, day) => n + day.matches.length, 0);
  const missingScorers = coverage && coverage.played > coverage.scorers;
  const pickTeam = (t) => setQuery({ team: t || null }, { replace: false });

  const sub = view === "flagged"
    ? `${plural(flagged.length, "result")}${team ? ` of ${team}'s` : ""} this season went against what the chances said: the winner created less, or the favourite only drew.`
    : team ? `${team}'s season: the next games, every result with the scorers and the numbers behind it, then the rest of the fixtures. Times are in your time zone.`
      : `Matchweek ${round}: results with the scorers, and the numbers that explain them. Times are in your time zone.`;

  return html`
    <${PageHead} eyebrow=${`${scope.league_name} · ${scope.label}`} title="Matches" sub=${sub}
      actions=${html`<div class="row wrap" style=${{ gap: "8px" }}>
        <${Select} compact label="Team" value=${team} options=${[{ value: "", label: "Every team" }, ...teams.map((t) => ({ value: t, label: t }))]} onChange=${pickTeam} />
        <${Segmented} label="Which matches" value=${view} onChange=${(v) => setQuery({ view: v === "round" ? null : v }, { replace: false })}
          options=${[{ value: "round", label: team ? "Whole season" : "By matchweek" }, { value: "flagged", label: `Results that lied (${flagged.length})` }]} />
      </div>`} />
    <${DataNotices} scope=${scope} meta=${meta} />
    ${missingScorers ? html`<${Notice} icon="clock">Scorers are shown for ${coverage.scorers} of ${coverage.played} played matches. The rest arrive as the app downloads each match page in the background (<a class="link" href=${href("/data")}>Data status</a>).</${Notice}>` : null}
    ${coverage?.unpublished ? html`<${Notice} icon="info">${plural(coverage.unpublished, "finished match", "finished matches")} ${coverage.unpublished === 1 ? "is" : "are"} shown from WhoScored: the score, the scorers and the event data are there. Understat has not published ${coverage.unpublished === 1 ? "it" : "them"}, so ${coverage.unpublished === 1 ? "its" : "their"} xG is missing, not zero.</${Notice}>` : null}
    ${team ? html`<div class="round-head"><h2>${team}</h2><span class="muted">${plural(mine.length, "match", "matches")} this season</span><${TeamSummary} matches=${mine} team=${team} />
      <${Button} kind="quiet" size="sm" icon="x" onClick=${() => pickTeam("")}>Every team</${Button}></div>` : null}
    ${view === "round" && !team ? html`
      <div class="round-nav">
        <${Button} kind="quiet" icon="chevronLeft" title="Previous matchweek" disabled=${round <= 1} onClick=${() => setQuery({ round: round - 1 }, { replace: false })} />
        <${RoundStrip} rounds=${rounds} value=${round} onPick=${(r) => setQuery({ round: r }, { replace: false })} />
        <${Button} kind="quiet" icon="chevronRight" title="Next matchweek" disabled=${round >= rounds.length} onClick=${() => setQuery({ round: round + 1 }, { replace: false })} />
      </div>
      <div class="round-head"><h2>Matchweek ${round}</h2><span class="muted">${current ? `${dateShort(current.from)}${current.to !== current.from ? ` to ${dateShort(current.to)}` : ""}` : ""}</span><${RoundSummary} matches=${current?.matches || []} /></div>` : null}
    ${shown
      ? days.map((day) => html`<${Day} key=${day.key} day=${day} counted=${view !== "flagged"} top=${view === "flagged" && !team} />`)
      : html`<${EmptyState} icon="calendar" title="Nothing here" text=${view === "flagged" ? `No result${team ? ` of ${team}'s` : ""} this season strongly defied its chances.` : "No matches in this matchweek."} />`}
  `;
}

export default function Matches() {
  const { league, season } = useScope();
  const { query } = useLocation();
  const q = useApi("/api/matches", { league, season });
  useDocumentTitle("Matches");
  return html`<${Async} q=${q}>${(d) => html`<${MatchesView} d=${d} query=${query} />`}</${Async}>`;
}

// Matches: every fixture by matchweek, each read through its chances.
import { html, useEffect, useMemo, useRef } from "../lib/html.js";
import { useApi } from "../lib/api.js";
import { useScope } from "../lib/scope.js";
import { setQuery, useLocation } from "../lib/router.js";
import { dateShort, nf, plural, probText, timeOf, weekday, cls } from "../lib/format.js";
import { Icon } from "../lib/icons.js";
import { Async, Badge, Button, Card, Crest, DataNotices, EmptyState, PageHead, Segmented, useDocumentTitle, matchHref } from "../ui/common.js";
import { FLAG_LABEL, labHref, verdict } from "../ui/blocks.js";
import { ProbBar } from "../charts/bars.js";
import { poissonOutcome } from "../lib/stats.js";

function XgDuel({ hxg, axg }) {
  const total = (hxg + axg) || 1;
  return html`<div class="duel" role="img" aria-label=${`Expected goals ${nf(hxg, 2)} to ${nf(axg, 2)}`}>
    <span class="num">${nf(hxg, 1)}</span>
    <span class="duel-bar"><i class="h" style=${{ flex: hxg / total + " 1 0" }}></i><i class="a" style=${{ flex: axg / total + " 1 0" }}></i></span>
    <span class="num">${nf(axg, 1)}</span>
  </div>`;
}

function MatchCard({ m }) {
  const flagged = Boolean(m.flag);
  const homeWon = m.played && m.hg > m.ag, awayWon = m.played && m.ag > m.hg;
  const v = m.flag ? verdict({ ...m, ...(() => { const o = poissonOutcome(m.hxg, m.axg); return { p_home: o.home, p_away: o.away }; })() }) : null;
  return html`<a class=${cls("mcard", flagged && "flagged")} href=${m.played ? matchHref(m.id) : labHref(m.home, m.away)}>
    <div class="mcard-top"><span class="muted xsmall num">${weekday(m.date)} ${dateShort(m.date)}${!m.played ? ` · ${timeOf(m.dt)}` : ""}</span>${m.flag ? html`<${Badge} tone="warn">${FLAG_LABEL[m.flag]}</${Badge}>` : null}</div>
    <div class="mcard-teams">
      <div class=${cls("line", homeWon && "won")}><${Crest} team=${m.home} short=${m.home_short} size=${24} /><span class="name">${m.home}</span><span class="goals figure num">${m.played ? m.hg : ""}</span></div>
      <div class=${cls("line", awayWon && "won")}><${Crest} team=${m.away} short=${m.away_short} size=${24} /><span class="name">${m.away}</span><span class="goals figure num">${m.played ? m.ag : ""}</span></div>
    </div>
    ${m.played ? html`<div class="stack" style=${{ "--gap": "4px" }}><span class="xsmall muted">Chances created (xG)</span><${XgDuel} hxg=${m.hxg} axg=${m.axg} /></div>` : null}
    ${m.forecast ? html`<div class="stack" style=${{ "--gap": "4px" }}><span class="xsmall muted">${m.played ? "Before kickoff, the model gave" : "Model forecast"}</span><${ProbBar} home=${m.forecast.home} draw=${m.forecast.draw} away=${m.forecast.away} homeLabel=${m.home_short} awayLabel=${m.away_short} compact /></div>` : null}
    ${v ? html`<div class="result-verdict">${v}</div>` : null}
  </a>`;
}

function RoundStrip({ rounds, value, onPick }) {
  const ref = useRef(null);
  useEffect(() => { ref.current?.querySelector('[aria-current="true"]')?.scrollIntoView({ block: "nearest", inline: "center" }); }, [value]);
  return html`<div class="roundstrip" ref=${ref} role="group" aria-label="Matchweeks">
    ${rounds.map((r) => html`<button type="button" key=${r.round} class=${cls("round", r.played ? "done" : "todo")} aria-current=${String(r.round === value)} onClick=${() => onPick(r.round)} title=${`${dateShort(r.from)}${r.to !== r.from ? ` to ${dateShort(r.to)}` : ""}`}>${r.round}</button>`)}
  </div>`;
}

function MatchesView({ d, query }) {
  const { scope, meta, rounds, latest_round: latest } = d;
  const view = query.view === "flagged" ? "flagged" : "round";
  const round = Number(query.round) || latest || rounds.find((r) => !r.played)?.round || 1;
  const current = rounds.find((r) => r.round === round) || rounds[0];
  const flagged = useMemo(() => rounds.flatMap((r) => r.matches.filter((m) => m.flag).map((m) => ({ ...m, round: r.round }))).sort((a, b) => b.dt.localeCompare(a.dt)), [rounds]);
  const list = view === "flagged" ? flagged : current?.matches || [];
  return html`
    <${PageHead} eyebrow=${`${scope.league_name} · ${scope.label}`} title="Matches" sub=${view === "flagged" ? `${plural(flagged.length, "result")} this season went against what the chances said.` : `Matchweek ${round}: results next to the chances behind them, and what the model expected beforehand.`}
      actions=${html`<${Segmented} label="View" value=${view} onChange=${(v) => setQuery({ view: v === "round" ? null : v })} options=${[{ value: "round", label: "By matchweek" }, { value: "flagged", label: `Results that lied (${flagged.length})` }]} />`} />
    <${DataNotices} scope=${scope} meta=${meta} />
    ${view === "round" ? html`
      <div class="row" style=${{ gap: "10px" }}>
        <${Button} kind="quiet" icon="chevronLeft" title="Previous matchweek" disabled=${round <= 1} onClick=${() => setQuery({ round: round - 1 })} />
        <${RoundStrip} rounds=${rounds} value=${round} onPick=${(r) => setQuery({ round: r })} />
        <${Button} kind="quiet" icon="chevronRight" title="Next matchweek" disabled=${round >= rounds.length} onClick=${() => setQuery({ round: round + 1 })} />
      </div>
      <div class="row between wrap"><h2 class="section-title" style=${{ fontSize: "var(--fs-lg)" }}>Matchweek ${round} <span class="muted small" style=${{ fontWeight: 400 }}>${current ? `${dateShort(current.from)}${current.to !== current.from ? ` to ${dateShort(current.to)}` : ""}` : ""}</span></h2></div>
    ` : null}
    ${list.length ? html`<div class="mgrid">${list.map((m) => html`<${MatchCard} key=${m.id} m=${m} />`)}</div>` : html`<${EmptyState} icon="calendar" title="Nothing here" text=${view === "flagged" ? "No result this season strongly defied its chances." : "No matches in this matchweek."} />`}
  `;
}

export default function Matches() {
  const { league, season } = useScope();
  const { query } = useLocation();
  const q = useApi("/api/matches", { league, season });
  useDocumentTitle("Matches");
  return html`<${Async} q=${q}>${(d) => html`<${MatchesView} d=${d} query=${query} />`}</${Async}>`;
}

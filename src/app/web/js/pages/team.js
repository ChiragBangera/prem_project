// Team: how a side is really doing (results against chances), how it plays, who drives it, and the match-by-match story.
import { html, useEffect, useMemo } from "../lib/html.js";
import { useApi } from "../lib/api.js";
import { useScope, useMeta } from "../lib/scope.js";
import { navigate, setQuery, useLocation } from "../lib/router.js";
import { formation, nf, ordinal, plural, signed } from "../lib/format.js";
import { Async, Crest, DataNotices, Form, PageHead, Select, Stat, Tabs, useDocumentTitle, teamHref } from "../ui/common.js";
import { rememberVisit } from "../ui/palette.js";
import { buildContext } from "../ui/explore/model.js";
import Overview from "./team-overview.js";
import TeamPlayers from "./team-players.js";
import StyleMaps from "./team-maps.js";
import Chances from "./team-chances.js";
import TeamMatches from "./team-matches.js";
import History from "./team-history.js";

const TAB_KEYS = ["players", "maps", "chances", "matches", "history"];

/** The team's row in the league's team dataset (every team measure, with percentiles) and the rows around it, for the style profile. */
function useTeamProfile(team, scope) {
  const { catalog } = useMeta();
  const q = useApi("/api/teams", { leagues: [scope.league], seasons: [scope.season] });
  const ctx = useMemo(() => (q.data && catalog ? buildContext("team", q.data, catalog) : null), [q.data, catalog]);
  const rows = q.data?.rows || [];
  return { ctx, rows, row: rows.find((r) => r.team === team) || null, loading: q.loading };
}

function TeamView({ d, team, tab }) {
  const { scope, meta: dm, profile: p } = d;
  const t = p.team;
  const profile = useTeamProfile(team, scope);
  const others = d.teams.filter((x) => x.name !== team).map((x) => ({ value: x.name, label: x.name }));
  useEffect(() => { rememberVisit({ kind: "team", href: teamHref(team, { league: scope.league, season: scope.season }), label: team, sub: `${scope.league_name} ${scope.label}` }); }, [team, scope.season]);

  const shift = t.rank_gap;
  const style = [formation(profile.row?.formation) && `Usually ${formation(profile.row.formation)}`, profile.row?.manager && `Manager ${profile.row.manager}`].filter(Boolean).join(" · ");
  const sub = `${ordinal(t.rank)} in the ${scope.league_name} on ${t.pts} points after ${plural(t.played, "game")}.${Math.abs(shift) >= 2 ? ` On expected points they would be ${ordinal(t.rank_xpts)}.` : ""}${style ? ` ${style}.` : ""}`;
  const tabs = [
    { value: "overview", label: "Overview" }, { value: "players", label: "Players", count: p.squad.length }, { value: "maps", label: "Style & maps" },
    { value: "chances", label: "Chances" }, { value: "matches", label: "Matches", count: p.matches.length }, { value: "history", label: "History" },
  ];

  return html`
    <${PageHead} lead=${html`<${Crest} team=${t.team} short=${t.short} size=${46} />`} eyebrow=${`${scope.league_name} · ${scope.label}`} title=${t.team} sub=${sub}
      actions=${html`<${Select} compact label="Compare with another team" value="" options=${[{ value: "", label: "Compare with…" }, ...others]} onChange=${(v) => v && navigate("/compare", { mode: "teams", a: team, b: v })} />`} />
    <${DataNotices} scope=${scope} meta=${dm} />
    <div class="tiles">
      <${Stat} label="Position" value=${ordinal(t.rank)} sub=${`${ordinal(t.rank_xpts)} on expected points`} />
      <${Stat} label="Points" value=${t.pts} sub=${`${nf(t.xpts, 1)} expected (${signed(t.xpts_gap, 1)})`} tone=${t.xpts_gap > 1 ? "up" : t.xpts_gap < -1 ? "down" : ""} />
      <${Stat} label="Goals for–against" value=${`${t.gf}–${t.ga}`} sub=${`xG ${nf(t.xg, 1)}–${nf(t.xga, 1)}`} />
      <${Stat} label="Chance difference" value=${`${signed(t.xgd_pg, 2)}`} sub=${`per game · ${ordinal(t.rank_xgd)} in the league`} />
      <div class="tile"><span class="label">Last five</span><span style=${{ paddingTop: "4px" }}><${Form} items=${t.form} /></span><span class="delta">${t.w}W ${t.d}D ${t.l}L overall</span></div>
    </div>
    <${Tabs} tabs=${tabs} value=${tab} onChange=${(v) => setQuery({ tab: v === "overview" ? null : v, by: null, chart: null }, { replace: false })} label="Team sections" />

    ${tab === "overview" ? html`<${Overview} d=${d} team=${team} profile=${profile} />` : null}
    ${tab === "players" ? html`<${TeamPlayers} team=${team} scope=${scope} squad=${p.squad} concentration=${p.concentration} />` : null}
    ${tab === "maps" ? html`<${StyleMaps} team=${team} scope=${scope} />` : null}
    ${tab === "chances" ? html`<${Chances} team=${team} scope=${scope} />` : null}
    ${tab === "matches" ? html`<${TeamMatches} team=${team} scope=${scope} />` : null}
    ${tab === "history" ? html`<${History} team=${team} league=${scope.league} viewing=${scope.season} />` : null}
  `;
}

export default function Team({ params }) {
  const scope = useScope();
  const { query } = useLocation();
  const team = params.team;
  const league = query.league || scope.league;
  const season = query.season || scope.season;
  const q = useApi("/api/team", { team, league, season });
  const tab = TAB_KEYS.includes(query.tab) ? query.tab : "overview";
  useDocumentTitle(team);
  return html`<${Async} q=${q}>${(d) => html`<${TeamView} d=${d} team=${team} tab=${tab} />`}</${Async}>`;
}

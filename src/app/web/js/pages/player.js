// Player: who he is, how he compares with role peers, how real his finishing is, where he shoots from.
import { html, useEffect, useMemo, useState } from "../lib/html.js";
import { useApi } from "../lib/api.js";
import { useScope, useMeta } from "../lib/scope.js";
import { navigate, setQuery, useLocation } from "../lib/router.js";
import { cls, dateLong, hueOf, initials, int, nf, ordinal, pct, plural, seasonLabel, signed } from "../lib/format.js";
import { Tip } from "../lib/tooltip.js";
import { poissonBinomial, tails } from "../lib/stats.js";
import { Icon } from "../lib/icons.js";
import { Async, Badge, Button, Card, DataNotices, EmptyState, Field, Info, Insights, Notice, PageHead, Segmented, Select, Stat, Star, Switch, Tabs, TeamName, Delta, useDocumentTitle, teamHref, playerHref, metricValue, POS_LABEL } from "../ui/common.js";
import { DataTable } from "../ui/table.js";
import { PercentileBars } from "../charts/bars.js";
import { ShotMap, ShotLegend } from "../charts/pitch.js";
import { GoalsDistribution } from "../charts/dist.js";
import { MiniBars } from "../charts/mini.js";
import { rememberVisit } from "../ui/palette.js";

function Avatar({ name, size = 52 }) {
  return html`<span class="avatar" style=${{ "--h": hueOf(name), width: size + "px", height: size + "px", fontSize: size * 0.36 + "px" }} aria-hidden="true">${initials(name)}</span>`;
}

function findMetric(blocks, key) {
  for (const b of blocks) for (const it of b.items) if (it.key === key) return it;
  return null;
}

// ------------------------------------------------------------------ profile

function AllMetrics({ blocks, group, title = "Every metric", sub, extra }) {
  return html`<${Card} flush title=${title} sub=${sub || `Each row is ranked among ${group}s with enough minutes. The bar is the percentile; hover a metric for what it means.`}>
    <div class="table-wrap"><table class="data dense metric-table">
      <thead><tr><th>Metric</th><th class="num">Per 90 / total</th><th>Percentile</th><th class="num">Rank</th></tr></thead>
      <tbody>
        ${blocks.map((b) => html`<${BlockRows} key=${b.category} block=${b} />`)}
      </tbody>
    </table></div>
    ${extra || null}
  </${Card}>`;
}

/** Defending and passing, from the optional WhoScored event data. Same table as "Every metric", ranked among role peers who have event data. */
function EventCard({ ev, group }) {
  if (!ev || (!ev.available && !ev.stored)) return null;
  if (!ev.available) {
    return html`<${Card} title="Defending and passing"><p class="muted small">No event data for this player in this view. Event data (duels, tackles, passing) only covers the league seasons you have fetched with <code>prem events sync</code>, and only players it could match to Understat.</p></${Card}>`;
  }
  const order = [...new Set(ev.items.map((i) => i.category))];
  const blocks = order.map((category) => ({ category, items: ev.items.filter((i) => i.category === category).map((i) => ({ ...i, pool_n: ev.pool_n })) }));
  const note = html`<div class="card-foot row wrap" style=${{ gap: "12px" }}>
    <span>Based on ${plural(ev.matches, "match", "matches")} and ${int(ev.minutes)} minutes of event data (WhoScored).</span>
    ${ev.in_pool ? null : html`<${Badge} tone="warn" title=${`Below ${ev.pool_minutes} minutes, so the ranking is pulled toward the role average`}>Few minutes: read with care</${Badge}>`}
  </div>`;
  return html`<${AllMetrics} blocks=${blocks} group=${group} title="Defending and passing"
    sub=${ev.pool_n > 1
      ? `Ranked among ${ev.pool_n} ${group}s who have event data (${ev.pool_minutes}+ minutes). Duels are tackles, challenges and aerial duels as the defending side; hover a metric for its exact definition.`
      : `Too little event data to rank ${group}s yet: percentiles appear as more matches are fetched. Duels are tackles, challenges and aerial duels as the defending side.`} extra=${note} />`;
}

function BlockRows({ block }) {
  return html`<tr class="group-row"><th colspan="4">${block.category}</th></tr>
    ${block.items.map((it) => html`<tr key=${it.key}>
      <td><span class="row" style=${{ gap: "6px" }}>${it.label}<${Info} text=${html`<div><b>${it.label}</b><br />${it.what}<br /><span class="muted">${it.read}</span></div>`} /></span></td>
      <td class="num">${metricValue(it, it.value)}</td>
      <td style=${{ width: "34%" }}>${it.pct == null ? html`<span class="muted">not ranked</span>` : html`<span class="row" style=${{ gap: "10px" }}><span class="bar-inline" style=${{ flex: 1 }}><i style=${{ width: it.pct + "%" }}></i></span><b class="num" style=${{ minWidth: "26px", textAlign: "right" }}>${Math.round(it.pct)}</b></span>`}</td>
      <td class="num muted">${it.rank ? `${it.rank} of ${it.pool_n}` : "–"}</td>
    </tr>`)}`;
}

function RoleFacts({ d }) {
  const p = d.player;
  const seasons = Object.entries(d.positions_minutes || {}).sort((a, b) => b[0] - a[0]);
  return html`<${Card} title="Role" sub="How the app decides who he is compared with">
    <dl class="kv">
      <dt>Compared as</dt><dd>${d.group_label}</dd>
      <dt>Decided by</dt><dd>${{ listed: "Understat's listed position", favorite: "Understat favourite position", inferred: "His minutes profile" }[p.group_source] || p.group_source}</dd>
      ${p.favorite ? html`<dt>Favourite position</dt><dd>${p.favorite}</dd>` : null}
      <dt>Peer group</dt><dd>${p.pool_n} ${d.group_label.toLowerCase()}s</dd>
      <dt>Small-sample rule</dt><dd>${p.in_pool ? "Passed" : "Below the minimum"}</dd>
    </dl>
    ${p.group_source === "inferred" ? html`<div class="notice" style=${{ marginTop: "12px" }}><${Icon} name="info" size="sm" /><div>His position is uncertain, so the app assigns the role whose typical profile his minutes resemble. It sharpens once Understat position data is fetched.</div></div>` : null}
    ${seasons.length ? html`<div class="divider" style=${{ margin: "14px 0" }}></div><div class="label" style=${{ marginBottom: "8px" }}>Positions played</div>
      <div class="stack" style=${{ "--gap": "6px" }}>${seasons.map(([s, list]) => html`<div class="row between small" key=${s}><span class="muted">${seasonLabel(s)}</span><span>${list.map((x) => `${x.position} ${int(x.minutes)} min`).join(" · ")}</span></div>`)}</div>` : null}
  </${Card}>`;
}

// ------------------------------------------------------------------ finishing

function FinishingTables({ f }) {
  const [tab, setTab] = useState("by_situation");
  const NAME = { OpenPlay: "Open play", FromCorner: "Corners", SetPiece: "Set pieces", DirectFreekick: "Free kicks", Penalty: "Penalties", RightFoot: "Right foot", LeftFoot: "Left foot", Head: "Header", OtherBodyPart: "Other" };
  const rows = (f[tab] || []).map((r) => ({ ...r, label: NAME[r.name] || r.name, xgps: r.shots ? r.xg / r.shots : null, diff: r.goals - r.xg }));
  const cols = [
    { key: "label", label: "Type", sortable: false, className: "strong" },
    { key: "shots", label: "Shots", num: true, sortable: false },
    { key: "goals", label: "Goals", num: true, sortable: false },
    { key: "xg", label: "xG", num: true, sortable: false, render: (r) => nf(r.xg, 1) },
    { key: "xgps", label: "xG/shot", num: true, sortable: false, render: (r) => (r.xgps == null ? "–" : nf(r.xgps, 3)) },
    { key: "diff", label: "G − xG", num: true, sortable: false, render: (r) => html`<${Delta} value=${r.diff} />` },
  ];
  return html`<${Card} flush title="Where the shots come from" actions=${html`<${Segmented} small label="Breakdown" value=${tab} onChange=${setTab} options=${[{ value: "by_situation", label: "Situation" }, { value: "by_foot", label: "Body part" }, { value: "by_zone", label: "Zone" }]} />`}>
    <${DataTable} columns=${cols} rows=${rows} rowKey=${(r) => r.name} dense caption="Shot breakdown" />
  </${Card}>`;
}

function Finishing({ d }) {
  const f = d.finishing, shots = d.shots || [];
  const npShots = shots.filter((s) => s.situation !== "Penalty");
  const pmf = useMemo(() => poissonBinomial(npShots.map((s) => s.xg)), [shots]);
  const [filter, setFilter] = useState("all");
  const seasons = [...new Set(shots.map((s) => s.season))].sort();
  const [season, setSeason] = useState("all");
  const luck = f.luck_np;
  const actual = f.np_goals;
  const t = tails(pmf, actual);
  const z = luck?.z ?? 0;
  const verdict = Math.abs(z) < 1
    ? `That is in line with the chances: a typical finisher lands close to here, so there is little to explain.`
    : z >= 1
      ? `With these chances, a finisher of average luck scores this many or more about ${pct(t.atLeast, t.atLeast < 0.1 ? 1 : 0)} of the time. ${z >= 2 ? "That is rare: some of it is quality, but expect it to cool." : "Notable, though within what a good season can look like."}`
      : `With these chances, a finisher of average luck scores this few or fewer about ${pct(t.atMost, t.atMost < 0.1 ? 1 : 0)} of the time. ${z <= -2 ? "That is rare: either the finishing is poor or the goals are overdue." : "Below par, though within what a quiet season can look like."}`;
  const visible = shots.filter((s) => (season === "all" || String(s.season) === season)
    && (filter === "all" || (filter === "goals" && s.result === "Goal") || (filter === "open" && s.situation === "OpenPlay") || (filter === "set" && s.situation !== "OpenPlay" && s.situation !== "Penalty")));
  return html`<div class="stack">
    <div class="grid cols-wide-narrow top">
      <${Card} title="How unusual is his finishing?" sub=${`${actual} non-penalty ${actual === 1 ? "goal" : "goals"} from ${nf(f.np_xg, 1)} xG over ${f.np_shots} shots.`}>
        ${npShots.length ? html`<${GoalsDistribution} pmf=${pmf} actual=${actual} expected=${f.np_xg} />` : html`<${EmptyState} compact icon="scatter" title="No shot data" />`}
        <p class="small" style=${{ marginTop: "8px" }}>${verdict}</p>
        <div class="evidence" style=${{ marginTop: "8px" }}>
          <span>Significance (z)<b>${signed(z, 1)}</b></span>
          <span>Expected<b>${nf(luck?.expected, 1)} ± ${nf(luck?.sd, 1)}</b></span>
          ${f.penalties?.taken ? html`<span>Penalties (excluded)<b>${f.penalties.scored}/${f.penalties.taken}</b></span>` : null}
        </div>
        <p class="xsmall muted" style=${{ marginTop: "10px" }}>Bars: the exact chance of each goal tally given the quality of every shot he took. Highlighted bar: what he scored. Tinted bars: tallies at least as extreme.</p>
      </${Card}>
      <${Card} title="Shot quality">
        <dl class="kv">
          <dt>Shots</dt><dd>${f.shots}</dd>
          <dt>On target</dt><dd>${f.on_target} (${pct(f.shots ? f.on_target / f.shots : 0)})</dd>
          <dt>xG per shot</dt><dd>${nf(f.xg_per_shot, 3)}</dd>
          <dt>Average distance</dt><dd>${f.avg_distance_m != null ? nf(f.avg_distance_m, 1) + " m" : "–"}</dd>
          <dt>Big chances (0.30+ xG)</dt><dd>${f.big_chances}</dd>
        </dl>
      </${Card}>
    </div>
    <div class="grid cols-2 top">
      <${Card} title="Shot map" sub=${`${visible.length} shots shown. Hover a shot for the detail.`}
        actions=${html`<div class="row wrap" style=${{ gap: "8px" }}>
          ${seasons.length > 1 ? html`<${Select} compact label="Season" value=${season} options=${[{ value: "all", label: "All seasons" }, ...seasons.map((s) => ({ value: String(s), label: seasonLabel(s) }))]} onChange=${setSeason} />` : null}
          <${Segmented} small label="Filter shots" value=${filter} onChange=${setFilter} options=${[{ value: "all", label: "All" }, { value: "goals", label: "Goals" }, { value: "open", label: "Open play" }, { value: "set", label: "Set pieces" }]} />
        </div>`}>
        ${visible.length ? html`<${ShotMap} shots=${visible} maxWidth=${520} /><div style=${{ marginTop: "10px" }}><${ShotLegend} /></div>` : html`<${EmptyState} compact title="No shots match" />`}
      </${Card}>
      <${FinishingTables} f=${f} />
    </div>
  </div>`;
}

// ------------------------------------------------------------------ seasons

function Seasons({ career }) {
  const rows = [...career].sort((a, b) => a.season - b.season);
  const labels = rows.map((r) => seasonLabel(r.season));
  const cur = rows.length - 1;
  const cols = [
    { key: "season", label: "Season", sortable: false, className: "strong", render: (r) => seasonLabel(r.season) },
    { key: "team", label: "Team", sortable: false, render: (r) => r.team },
    { key: "age", label: "Age", num: true, sortable: false },
    { key: "games", label: "Apps", num: true, sortable: false },
    { key: "minutes", label: "Min", num: true, sortable: false },
    { key: "goals", label: "G", num: true, sortable: false },
    { key: "xg", label: "xG", num: true, sortable: false, render: (r) => nf(r.xg, 1) },
    { key: "assists", label: "A", num: true, sortable: false },
    { key: "xa", label: "xA", num: true, sortable: false, render: (r) => nf(r.xa, 1) },
    { key: "npxg90", label: "npxG/90", num: true, sortable: false, render: (r) => nf(r.npxg90, 2) },
    { key: "xa90", label: "xA/90", num: true, sortable: false, render: (r) => nf(r.xa90, 2) },
    { key: "xgchain90", label: "xGChain/90", num: true, sortable: false, render: (r) => nf(r.xgchain90, 2) },
    { key: "g_xg", label: "G − xG", num: true, sortable: false, render: (r) => html`<${Delta} value=${r.g_xg} />` },
  ];
  const series = [
    { label: "npxG per 90", key: "npxg90", digits: 2 }, { label: "xA per 90", key: "xa90", digits: 2 },
    { label: "xGChain per 90", key: "xgchain90", digits: 2 }, { label: "Minutes", key: "minutes", digits: 0 },
  ];
  return html`<div class="stack">
    ${rows.length > 1 ? html`<div class="grid cols-4">${series.map((s) => html`<${Card} key=${s.key} title=${s.label} sub="By season">
      <${MiniBars} labels=${labels} values=${rows.map((r) => r[s.key])} format=${(v) => nf(v, s.digits)} highlight=${cur} />
    </${Card}>`)}</div>` : null}
    <${Card} flush title="Season by season" sub="Every league season Understat has for him. Rates use league minutes only.">
      <${DataTable} columns=${cols} rows=${[...rows].reverse()} rowKey=${(r) => r.season} dense caption="Career" />
    </${Card}>
  </div>`;
}

// ------------------------------------------------------------------ similar

function SimilarCard({ s, scope, onCompare }) {
  return html`<a class="similar" href=${playerHref(s.id, { league: s.league, season: scope.season })}>
    <div class="sim-score"><b class="figure">${Math.round(s.similarity)}</b><span>similarity</span></div>
    <div class="stack" style=${{ "--gap": "6px", minWidth: 0 }}>
      <div class="row between"><b class="truncate">${s.name}</b><${Star} player=${s} /></div>
      <div class="muted small truncate">${s.team} · ${s.league}${s.age != null ? ` · ${s.age}` : ""} · ${s.minutes} min</div>
      <div class="small"><span class="muted">Both strong on </span>${s.shared_strengths?.length ? s.shared_strengths.join(", ") : "nothing in particular"}</div>
      <div class="small"><span class="muted">Differs most on </span>${s.biggest_difference}</div>
      <div class="row" style=${{ gap: "6px", flexWrap: "wrap" }}>${(s.tags || []).slice(0, 2).map((t) => html`<span class="tag" key=${t}>${t}</span>`)}<span class="muted xsmall">Role score ${s.output != null ? Math.round(s.output) : "–"}</span></div>
    </div>
  </a>`;
}

function Similar({ d, scope, meta, id }) {
  const [maxAge, setMaxAge] = useState("");
  const [others, setOthers] = useState(false);
  const controlled = maxAge !== "" || others;
  const q = useApi(`/api/player/${id}/similar`, { league: d.scope.league || scope.league, seasons: d.scope.seasons, max_age: maxAge || undefined, other_leagues: others ? meta.leagues.map((l) => l.code).filter((c) => c !== (d.scope.league || scope.league)) : undefined, limit: 12 }, { enabled: controlled });
  const list = controlled ? q.data?.similar : d.similar;
  const agesKnown = (list || []).some((s) => s.age != null);
  return html`<div class="stack">
    <${Card} title="Players with a similar profile" sub="Nearest neighbours in percentile space across the metrics that define the role, so a high-volume and a low-volume player of the same style still match.">
      <div class="row wrap" style=${{ gap: "16px", marginBottom: "16px" }}>
        <${Field} label="Age"><${Select} value=${maxAge} label="Maximum age" options=${[{ value: "", label: "Any age" }, { value: "21", label: "21 or younger" }, { value: "23", label: "23 or younger" }, { value: "26", label: "26 or younger" }, { value: "29", label: "29 or younger" }]} onChange=${setMaxAge} /></${Field}>
        <div style=${{ alignSelf: "end", paddingBottom: "6px" }}><${Switch} checked=${others} onChange=${setOthers}>Search other leagues too</${Switch}></div>
        ${controlled && q.loading ? html`<span class="muted small" style=${{ alignSelf: "end", paddingBottom: "8px" }}>Searching…</span>` : null}
      </div>
      ${maxAge && !agesKnown && list?.length === 0 ? html`<${Notice} icon="clock">No one matched, possibly because ages are still loading in the background.</${Notice}>` : null}
      ${list?.length ? html`<div class="similar-grid">${list.map((s) => html`<${SimilarCard} key=${s.id} s=${s} scope=${scope} />`)}</div>` : html`<${EmptyState} compact title="No close matches" text="Loosen the filters or include other leagues." />`}
    </${Card}>
  </div>`;
}

// ------------------------------------------------------------------ page

function PlayerView({ d, id, tab, span, setSpan }) {
  const scope = useScope();
  const metaState = useMeta();
  const meta = metaState.meta;
  const { detail, insights, shortlisted } = d;
  const p = detail.player;
  const t = detail.totals;
  const contrib = findMetric(detail.blocks, "contrib90");
  const npxg90 = findMetric(detail.blocks, "npxg90");
  const profile = detail.profile;
  const dScope = d.scope;
  useEffect(() => { rememberVisit({ kind: "player", href: playerHref(id, { league: dScope.league, season: dScope.seasons?.length === 1 ? dScope.seasons[0] : scope.season }), label: p.name, sub: `${p.team} · ${detail.group_label}` }); }, [id]);

  const tabs = [{ value: "profile", label: "Profile" }, { value: "finishing", label: "Finishing and shots", count: (detail.shots || []).length }, { value: "seasons", label: "Seasons", count: detail.career.length }, { value: "similar", label: "Similar players" }];
  const teamLinks = (p.teams || [p.team]).map((tm, i) => html`${i ? " / " : ""}<a class="link" href=${teamHref(tm)} key=${tm}>${tm}</a>`);
  return html`
    <${PageHead} lead=${html`<${Avatar} name=${p.name} />`} eyebrow=${`${detail.group_label} · ${dScope.league_name}`} title=${p.name}
      sub=${html`${teamLinks}${p.age != null ? ` · ${p.age} years old${p.dob_basis === "name" ? " (unconfirmed: matched by name only)" : p.dob ? ` (born ${dateLong(p.dob)})` : ""}` : ""} · ${int(p.minutes)} minutes in ${plural(p.games, "game")} (${dScope.labels.join(", ")})`}
      actions=${html`<div class="row wrap" style=${{ gap: "8px" }}>
        <${Select} compact label="Seasons included" value=${String(span)} options=${[{ value: "1", label: "This season" }, { value: "2", label: "Last two seasons" }, { value: "3", label: "Last three seasons" }]} onChange=${setSpan} />
        <${Star} player=${{ id: p.id, name: p.name, team: p.team, league: dScope.league }} />
        <${Button} icon="compare" onClick=${() => navigate("/compare", { ids: String(p.id) })}>Compare</${Button}>
      </div>`} />
    <${DataNotices} scope=${dScope} meta=${d.meta} extra=${(d.meta?.warnings || []).slice(0, 2)} />
    ${p.tags?.length ? html`<div class="row wrap" style=${{ gap: "8px" }}>${p.tags.map((tg) => html`<span class="tag strong-tag" key=${tg.key} title=${tg.why}>${tg.label}<span class="muted"> · ${tg.why}</span></span>`)}${!p.in_pool ? html`<${Badge} tone="warn" title="Fewer minutes than the ranking pool requires">Small sample</${Badge}>` : null}</div>` : (!p.in_pool ? html`<${Badge} tone="warn">Small sample</${Badge}>` : null)}
    <div class="tiles">
      <${Stat} label="Role score" value=${p.output != null ? Math.round(p.output) : "–"} sub=${`vs ${p.pool_n} ${detail.group_label.toLowerCase()}s`} title="Average percentile across the metrics that define his role" />
      <${Stat} label="Goals" value=${t.goals} sub=${`${nf(t.xg, 1)} xG · ${signed(t.g_xg, 1)}`} tone=${t.g_xg > 1 ? "up" : t.g_xg < -1 ? "down" : ""} />
      <${Stat} label="Assists" value=${t.assists} sub=${`${nf(t.xa, 1)} xA`} />
      <${Stat} label="npxG + xA per 90" value=${contrib ? nf(contrib.value, 2) : "–"} sub=${contrib?.pct != null ? `${ordinal(Math.round(contrib.pct))} percentile` : ""} />
      <${Stat} label="Share of team chain" value=${pct(detail.team_context.chain_share)} sub=${`${pct(detail.team_context.share_npxg)} of team npxG`} title="How much of the team's attacking play runs through him" />
    </div>
    <${Insights} items=${insights} scope=${dScope} limit=${3} expandable />
    <${Tabs} tabs=${tabs} value=${tab} onChange=${(v) => setQuery({ tab: v === "profile" ? null : v })} label="Player sections" />

    ${tab === "profile" ? html`<div class="stack">
      <div class="grid cols-wide-narrow top">
        <${Card} title=${`Against ${detail.group_label.toLowerCase()}s with enough minutes`} sub=${`Percentile among ${p.pool_n} peers. The tick marks the median. Rankings use small-sample-adjusted rates.`}>
          ${profile.length ? html`<${PercentileBars} items=${profile.map((x) => ({ key: x.key, label: x.short, pct: x.pct, raw: metricValue(x, x.value),
            tip: html`<${Tip} title=${x.label} sub=${`${detail.group_label}s with enough minutes`} rows=${[{ label: "Value", value: metricValue(x, x.value) }, { label: "Percentile", value: x.pct == null ? "–" : Math.round(x.pct) }, { label: "Rank", value: x.rank ? `${x.rank} of ${p.pool_n}` : "–" }]} />` }))} />` : html`<${EmptyState} compact title="Not ranked" text="Goalkeepers and players under the minute threshold are not ranked." />`}
        </${Card}>
        <${RoleFacts} d=${detail} />
      </div>
      ${detail.blocks.length ? html`<${AllMetrics} blocks=${detail.blocks} group=${detail.group_label.toLowerCase()} />` : null}
      <${EventCard} ev=${detail.events} group=${detail.group_label.toLowerCase()} />
    </div>` : null}
    ${tab === "finishing" ? html`<${Finishing} d=${detail} />` : null}
    ${tab === "seasons" ? html`<${Seasons} career=${detail.career} />` : null}
    ${tab === "similar" ? html`<${Similar} d=${{ ...d, scope: dScope, similar: d.similar }} scope=${scope} meta=${meta} id=${id} />` : null}
  `;
}

export default function Player({ params }) {
  const scope = useScope();
  const { query } = useLocation();
  const id = Number(params.id);
  const league = query.league || scope.league;
  const season = query.season || scope.season;
  const span = Number(query.span || 1);
  const [resolved, setResolved] = useState(null);
  const seasons = span > 1 && resolved ? Array.from({ length: span }, (_, i) => resolved - i) : undefined;
  const q = useApi(`/api/player/${id}`, { league, season: seasons ? undefined : season, seasons });
  useEffect(() => { const s = q.data?.scope?.seasons; if (s?.length === 1) setResolved(s[0]); }, [q.data?.scope?.seasons?.join()]);
  const tab = ["finishing", "seasons", "similar"].includes(query.tab) ? query.tab : "profile";
  useDocumentTitle(q.data?.detail?.player?.name || "Player");
  return html`<${Async} q=${q}>${(d) => html`<${PlayerView} d=${d} id=${id} tab=${tab} span=${span} setSpan=${(v) => setQuery({ span: v === "1" ? null : v })} />`}</${Async}>`;
}

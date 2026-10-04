// Player > Match trend: every metric, match by match, with the opponent behind each number, so a good run against weak sides is not mistaken for form.
import { html, useMemo, useState } from "../lib/html.js";
import { useApi } from "../lib/api.js";
import { navigate, setQuery, useLocation } from "../lib/router.js";
import { cls, dateShort, isNum, ordinal, seasonLabel } from "../lib/format.js";
import { fmtMetric } from "../lib/metricfmt.js";
import { Card, EmptyState, Info, Notice, Section, Segmented, Select, Skeleton } from "../ui/common.js";
import { DataTable } from "../ui/table.js";
import { MetricSelect } from "../ui/explore/MetricSelect.js";
import { Legend } from "../charts/core.js";
import { LINE, MatchTrendChart, markColor, tierColor } from "../charts/trend.js";
import { TIERS, TIER_LABEL, alike, changes, deltaText, isFlat, isZeroBased, quickPicks, readTrend, resultText } from "../lib/trend.js";

/** A change in the season figure, coloured by whether it is good for him (blue) or not (orange); style metrics stay uncoloured. */
function Change({ def, d, flat }) {
  if (!isNum(d)) return html`<span class="muted">–</span>`;
  const good = def.hib === null || def.hib === undefined ? null : (d > 0) === (def.hib !== false);
  return html`<span class=${cls("delta-val", !(flat ?? isFlat(def, d)) && good !== null && (good ? "pos" : "neg"))}>${deltaText(def, d)}</span>`;
}

function Coverage({ d, def }) {
  const c = d.coverage;
  const notes = [];
  if (d.player.games && c.played < d.player.games) notes.push(`Drawn from ${c.played} of his ${d.player.games} appearances: the others have no stored match page yet, so they are left out of every line (never counted as zero) and the season line stops short of his profile figure. The Data page shows what is being fetched.`);
  if (def.needs === "events" && c.events < c.played) notes.push(`This metric needs event data, which covers ${c.events} of his ${c.played} stored appearances.`);
  return notes.length ? html`<${Notice} icon="info">${notes.join(" ")}</${Notice}>` : null;
}

function MarkLegend({ colorBy, tiers }) {
  const items = colorBy === "venue"
    ? [{ key: "home", label: "Home", color: markColor({ home: true }, "venue"), shape: "box" }, { key: "away", label: "Away", color: markColor({ home: false }, "venue"), shape: "box" }]
    : TIERS.map((t) => ({ key: t, label: TIER_LABEL[t], color: tierColor[t], shape: "box" }));
  const spans = tiers && tiers.top ? ` The top third is positions ${tiers.top[0]}–${tiers.top[1]}, the middle third ${tiers.mid[0]}–${tiers.mid[1]} and the bottom third ${tiers.bottom[0]}–${tiers.bottom[1]}.` : "";
  return html`<div class="legend-group">
    <span class="legend-title">${colorBy === "venue" ? "Venue" : "Opponent strength"}${colorBy === "venue" ? null : html`<${Info} label="About opponent strength" text=${html`<div>Darker marks are stronger opponents. Strength is the club's place in this season's table by <b>expected points</b> (what its chances deserved), not by the points it won, so a lucky run does not make a side look better than it is.${spans}</div>`} />`}</span>
    <${Legend} items=${items} />
  </div>`;
}

function Splits({ d, metric, def, season }) {
  const rowOf = (label, part, color, note) => {
    const v = part?.v?.[metric];
    const few = !part || part.matches < 2 || part.minutes < 120;
    const diff = isNum(v) && isNum(season) ? v - season : null;
    return html`<tr key=${label} class=${few ? "few" : ""}>
      <td><span class="row" style=${{ gap: "8px" }}>${color ? html`<i class="tier-dot" style=${{ background: color }}></i>` : null}<span>${label}${note ? html` <span class="muted xsmall">${note}</span>` : null}</span></span></td>
      <td class="num">${part?.matches ?? 0}</td><td class="num">${part ? Math.round(part.minutes) : 0}</td>
      <td class="num strong" title=${few && isNum(v) ? "Too few matches to read much into" : undefined}>${isNum(v) ? fmtMetric(def, v) : html`<span class="muted">–</span>`}</td>
      <td class="num">${few ? html`<span class="muted">–</span>` : html`<${Change} def=${def} d=${diff} flat=${alike(def, v, season)} />`}</td>
    </tr>`;
  };
  const range = (t) => (d.tiers?.[t] ? `positions ${d.tiers[t][0]}–${d.tiers[t][1]}` : null);
  return html`<${Card} flush title="Who he played" sub=${`${def.label} over all the matches in each group together (the same formula as his profile, not an average of match figures).`}>
    <div class="table-wrap"><table class="data dense splits">
      <thead><tr><th>Opponents</th><th class="num">Matches</th><th class="num">Minutes</th><th class="num">${def.short || def.label}</th><th class="num" title="Against the season figure">vs season</th></tr></thead>
      <tbody>
        <tr class="group-row"><th colspan="5">By opponent strength</th></tr>
        ${TIERS.map((t) => rowOf(TIER_LABEL[t], d.splits.tier[t], tierColor[t], range(t)))}
        <tr class="group-row"><th colspan="5">By venue</th></tr>
        ${rowOf("Home", d.splits.venue.home)}
        ${rowOf("Away", d.splits.venue.away)}
      </tbody>
    </table></div>
    <div class="card-foot xsmall">Groups with fewer than two matches or 120 minutes are greyed: one game is not a pattern.</div>
  </${Card}>`;
}

function MatchTable({ d, def, series, moves }) {
  const rows = d.matches.map((m, i) => ({ m, i, v: series.m[i], c: series.c[i], d: moves[i] }));
  const cols = [
    { key: "date", label: "Date", firstDir: "desc", value: (r) => r.m.date, render: (r) => dateShort(r.m.date) },
    { key: "opp", label: "Opponent", firstDir: "asc", value: (r) => r.m.opp, render: (r) => html`<span class="row" style=${{ gap: "8px" }}><i class="tier-dot" style=${{ background: markColor(r.m, "opp") }}></i><span><span class="muted xsmall">${r.m.home ? "v" : "at"}</span> ${r.m.opp}</span></span>` },
    { key: "rank", label: "Strength", num: true, firstDir: "asc", title: "The opponent's place in the table by expected points this season (1 is the strongest).", value: (r) => r.m.opp_ctx?.rank_xpts, render: (r) => (r.m.opp_ctx ? ordinal(r.m.opp_ctx.rank_xpts) : "–") },
    { key: "result", label: "Result", sortable: false, render: (r) => resultText(r.m) || "–" },
    { key: "minutes", label: "Min", num: true, value: (r) => (r.m.played ? r.m.minutes : null) },
    { key: "v", label: def.short || def.label, num: true, className: "strong", value: (r) => r.v, render: (r) => (isNum(r.v) ? fmtMetric(def, r.v) : html`<span class="muted xsmall">${!r.m.page ? "no data" : !r.m.played ? "did not play" : "no value"}</span>`) },
    { key: "c", label: "Season so far", num: true, title: "His season figure after this match. The last row is the number on his profile.", value: (r) => r.c, render: (r) => fmtMetric(def, r.c) },
    { key: "d", label: "Change", num: true, title: "How much this match moved the season figure. Blue helped him, orange hurt.", value: (r) => r.d, render: (r) => html`<${Change} def=${def} d=${r.d} />` },
    { key: "report", label: "", sortable: false, render: (r) => (r.m.match_id ? html`<a class="link xsmall" href=${`#/match/${r.m.match_id}`} onClick=${(e) => e.stopPropagation()}>Match report</a>` : null) },
  ];
  return html`<${Card} flush title="Every match" sub="Sort by Change to see which games moved the season figure most.">
    <${DataTable} columns=${cols} rows=${rows} rowKey=${(r) => r.i} initialSort=${{ key: "date", dir: "desc" }} dense caption=${`${def.label}, match by match`} onRowClick=${(r) => r.m.match_id && navigate(`/match/${r.m.match_id}`)} />
  </${Card}>`;
}

function TrendView({ d, cat, group, who }) {
  const { query } = useLocation();
  const keys = d.keys;
  const have = useMemo(() => new Set(keys), [keys]);
  const quick = useMemo(() => quickPicks(cat, group, have, keys), [cat, group, have, keys]);
  const key = have.has(query.tm) ? query.tm : quick[0] || keys[0];
  const def = cat.metrics[key];
  const series = d.series[key];
  const band = d.reference?.[key];
  const colorBy = query.tc === "venue" ? "venue" : "opp";
  const [show, setShow] = useState({ season: true, form: true, band: true });
  const toggle = (k) => setShow((s) => ({ ...s, [k]: !s[k] }));
  const moves = useMemo(() => changes(series.c, series.m), [series]);
  const reads = useMemo(() => readTrend(d, key, def), [d, key, def]);
  const ctx = useMemo(() => ({ metrics: cat.metrics, order: cat.order, groups: cat.groups }), [cat]);
  const lines = [
    { key: "season", label: "Season so far", color: LINE.season },
    { key: "form", label: `Last ${d.window} appearances`, color: LINE.form },
    ...(band ? [{ key: "band", label: `Typical ${who} (middle half)`, color: "color-mix(in oklab, var(--accent) 24%, var(--surface))", shape: "box" }] : []),
  ];
  const season = [...series.c].reverse().find(isNum);
  const target = `${def.label}, match by match, ${d.scope.label}`;
  const fade = isZeroBased(def) ? "faded ones rest on few minutes" : "faded ones rest on few minutes or attempts";
  const marks = colorBy === "venue" ? `Solid marks are home matches and pale ones away matches; ${fade}.` : `${isZeroBased(def) ? "Darker bars" : "Darker dots"} are stronger opponents; ${fade}.`;
  const caption = `One mark per match, oldest on the left, under the opponent's name (H home, A away; the dot below is the result: green a win, red a defeat, a ring a draw). ${marks} The dark line is his season so far after each match and ends on his profile figure; the orange line is his last ${d.window} appearances. A gap means he did not play or the match has no stored data. Hover a match for the detail, click it for the match report.`;
  return html`<div class="stack" style=${{ "--gap": "16px" }}>
    ${query.tm && !have.has(query.tm) ? html`<${Notice} tone="warn" icon="alert">That metric has no match-by-match view for him this season, so ${def.label} is shown instead.</${Notice}>` : null}
    <${Card} title=${def.label} sub=${def.what}
      actions=${html`<${Info} label=${`About ${def.label}`} text=${html`<div><b>${def.label}</b><br />${def.what}<br /><span class="muted">${def.read}</span><br /><span class="muted xsmall">${def.formula}</span></div>`} />`}>
      <div class="trend-controls">
        <label class="rb-field"><span class="rb-label">Metric</span><${MetricSelect} ctx=${ctx} only=${(k) => have.has(k)} compact value=${key} label="Metric" onChange=${(k) => setQuery({ tm: k })} /></label>
        <div class="quick" role="group" aria-label="Quick picks">${quick.map((k) => html`<button type="button" key=${k} class="chip" aria-pressed=${String(k === key)} onClick=${() => setQuery({ tm: k })}>${cat.metrics[k].short || cat.metrics[k].label}</button>`)}</div>
        <${Segmented} small label="Colour the marks by" value=${colorBy} onChange=${(v) => setQuery({ tc: v === "opp" ? null : v })} options=${[{ value: "opp", label: "Opponent strength" }, { value: "venue", label: "Home or away" }]} />
      </div>
      <${Coverage} d=${d} def=${def} />
      <div class="trend-legend"><${MarkLegend} colorBy=${colorBy} tiers=${d.tiers} /><${Legend} items=${lines} hidden=${lines.filter((l) => show[l.key] === false).map((l) => l.key)} onToggle=${toggle} /></div>
      <${MatchTrendChart} matches=${d.matches} series=${series} def=${def} band=${band} colorBy=${colorBy} show=${show} form=${d.window} label=${target}
        onOpen=${(m) => navigate(`/match/${m.match_id}`)} />
      <p class="chart-caption">${caption}</p>
    </${Card}>
    <div class="grid cols-2 top">
      <${Card} title="What stands out">
        ${reads.length ? html`<ul class="reads">${reads.map((r) => html`<li key=${r.kind} class=${cls("read", r.tone)}>${r.text}</li>`)}</ul>` : html`<p class="muted small">Not enough matches with a number to say anything yet.</p>`}
        <p class="xsmall muted" style=${{ marginTop: "10px" }}>Written from the numbers on this page. A pattern over a handful of matches is a hint, not a finding.</p>
      </${Card}>
      <${Splits} d=${d} metric=${key} def=${def} season=${season} />
    </div>
    <${MatchTable} d=${d} def=${def} series=${series} moves=${moves} />
  </div>`;
}

export function PlayerTrend({ id, league, defaultSeason, career, group, groupLabel, catalog }) {
  const { query } = useLocation();
  const seasons = useMemo(() => [...new Set(career.map((r) => r.season))].sort((a, b) => b - a), [career]);
  const season = Number(query.ts) || defaultSeason;
  const q = useApi(`/api/player/${id}/trend`, { league, season }, { keepPrevious: false });
  const options = (seasons.includes(season) ? seasons : [season, ...seasons]).map((s) => ({ value: String(s), label: seasonLabel(s) }));
  const who = `${groupLabel.toLowerCase()}s`;
  const cat = catalog?.player;
  const picker = html`<${Select} compact label="Season" value=${String(season)} options=${options} onChange=${(v) => setQuery({ ts: Number(v) === defaultSeason ? null : v })} />`;
  const d = q.data;
  let body;
  if (q.error && !d) body = html`<${EmptyState} compact icon="calendar" title=${q.error.status === 404 ? `No matches for ${seasonLabel(season)}` : "This view could not load"} text=${q.error.message} action=${q.error.hint ? html`<p class="muted small">${q.error.hint}</p>` : null} />`;
  else if (!d || !cat) body = html`<div aria-busy="true" aria-label="Loading"><${Skeleton} h=${380} r="12px" /></div>`;
  else if (!d.available) body = html`<${EmptyState} compact icon="calendar" title="Nothing to draw yet" text=${d.reason} action=${html`<a class="btn quiet" href="#/data">Open the Data page</a>`} />`;
  else body = null;
  return html`<${Section} title="Match by match" sub=${`How every metric moved through ${d?.scope?.label ? `the ${d.scope.label} season` : "the season"}, and who he played when it did.`} actions=${picker}>
    ${d?.scope?.note ? html`<${Notice} icon="info">${d.scope.note}</${Notice}>` : null}
    ${body ? html`<div class="card"><div class="card-body">${body}</div></div>` : html`<div class=${cls("fade-in", q.refetching && "is-refetching")}><${TrendView} d=${d} cat=${cat} group=${group} who=${who} /></div>`}
  </${Section}>`;
}

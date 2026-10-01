// Compare: players side by side (percentile dot plot) or two teams (numbers, trend, meetings).
import { html, useEffect, useMemo, useState } from "../lib/html.js";
import { useApi } from "../lib/api.js";
import { useScope, useMeta } from "../lib/scope.js";
import { navigate, setQuery, useLocation } from "../lib/router.js";
import { debounce, dateShort, nf, ordinal, plural, signed, cls, fold } from "../lib/format.js";
import { Icon } from "../lib/icons.js";
import { shortlistStore, useStore } from "../lib/store.js";
import { Async, Badge, Button, Card, Crest, DataNotices, EmptyState, Insights, Notice, PageHead, Section, Segmented, Select, Star, TeamName, useDocumentTitle, playerHref, metricValue, POS_LABEL, matchHref, teamHref } from "../ui/common.js";
import { DataTable } from "../ui/table.js";
import { PercentileDots } from "../charts/bars.js";
import { LineChart, SERIES_COLORS } from "../charts/lines.js";
import { ProbBar } from "../charts/bars.js";
import { useStableSlots } from "../lib/slots.js";

// ------------------------------------------------------------------ player picker

function PlayerPicker({ chosen, onAdd, max = 4 }) {
  const [text, setText] = useState("");
  const [term, setTerm] = useState("");
  const push = useMemo(() => debounce(setTerm, 200), []);
  const q = useApi("/api/search", { q: term, limit: 7 }, { enabled: term.trim().length >= 2, staleMs: 60000 });
  const shortlist = useStore(shortlistStore, (s) => s.items);
  const taken = new Set(chosen);
  const full = chosen.length >= max;
  const hits = (q.data?.players || []).filter((p) => !taken.has(p.id));
  const suggestions = shortlist.filter((s) => !taken.has(s.id)).slice(0, 6);
  return html`<div class="stack" style=${{ "--gap": "10px" }}>
    <div class="picker">
      <label class="searchbox" style=${{ width: "100%" }}>
        <${Icon} name="search" size="sm" />
        <input type="search" value=${text} disabled=${full} placeholder=${full ? `Up to ${max} players` : "Add a player by name"} aria-label="Add a player"
          onInput=${(e) => { setText(e.target.value); push(e.target.value); }} />
      </label>
      ${term.trim().length >= 2 && !full ? html`<div class="popover pick-pop" role="listbox">
        ${hits.map((p) => html`<button type="button" class="menu-item" key=${p.id} role="option" onClick=${() => { onAdd(p); setText(""); setTerm(""); }}>
          <b>${p.name}</b><span class="muted small">${p.team} · ${p.league}</span></button>`)}
        ${!hits.length ? html`<div class="muted small" style=${{ padding: "8px 10px" }}>${q.data ? "No unpicked player matches." : "Searching…"}</div>` : null}
      </div>` : null}
    </div>
    ${suggestions.length && !full ? html`<div class="row wrap" style=${{ gap: "6px" }}><span class="xsmall muted">From your shortlist:</span>${suggestions.map((s) => html`<button type="button" class="chip" key=${s.id} onClick=${() => onAdd(s)}><${Icon} name="plus" />${s.name}</button>`)}</div>` : null}
  </div>`;
}

// ------------------------------------------------------------------ players

function PlayersView({ d, ids, remove, scope, colors }) {
  const players = d.players;
  const dots = d.metrics.map((m) => ({ key: m.key, label: m.short || m.label, values: m.values, pct: m.pct, best: m.best, format: (v) => (v == null ? "–" : metricValue({ unit: m.key === "output" ? "count" : undefined, decimals: m.decimals }, v)) }));
  // optional event data: shown only when at least two of the players have some
  const eventDots = (d.event_metrics || []).map((m) => ({ key: m.key, label: m.short || m.label, values: m.values, pct: m.pct, best: m.best, format: (v) => (v == null ? "–" : metricValue({ unit: m.unit, decimals: m.decimals }, v)) }));
  const noEvents = players.filter((p) => !p.ev_minutes).map((p) => p.name);
  const rows = [
    { key: "minutes", label: "Minutes", get: (p) => p.minutes }, { key: "goals", label: "Goals", get: (p) => p.goals },
    { key: "xg", label: "xG", get: (p) => nf(p.xg, 1) }, { key: "g_xg", label: "Goals − xG", get: (p) => signed(p.g_xg, 1) },
    { key: "assists", label: "Assists", get: (p) => p.assists }, { key: "shots", label: "Shots", get: (p) => p.shots },
  ];
  return html`<div class="stack">
    <div class="compare-heads" style=${{ "--n": players.length }}>
      ${players.map((p, i) => html`<div class="cmp-head" key=${p.id}>
        <div class="row between top"><span class="cmp-dot" style=${{ background: colors[i] }}></span><button type="button" class="star" aria-label=${`Remove ${p.name}`} onClick=${() => remove(p.id)}><${Icon} name="x" /></button></div>
        <a class="cmp-name" href=${playerHref(p.id, { league: p.league, season: scope.season })}>${p.name}</a>
        <div class="muted small">${p.team} · ${POS_LABEL[p.group]}${p.age != null ? ` · ${p.age}` : ""}</div>
        <div class="row" style=${{ gap: "10px", marginTop: "6px" }}><div class="cmp-score figure">${p.output != null ? Math.round(p.output) : "–"}</div><span class="xsmall muted">role score<br />${p.pool_n} peers</span></div>
        <div class="row wrap" style=${{ gap: "6px" }}>${(p.tags || []).slice(0, 2).map((t) => html`<span class="tag" key=${t.key} title=${t.why}>${t.label}</span>`)}</div>
      </div>`)}
    </div>
    ${d.note ? html`<${Notice} icon="info">${d.note}</${Notice}>` : null}
    ${d.mixed_groups ? html`<${Notice} tone="warn" icon="alert">These players have different roles. Each percentile is measured against that player's own role, so a defender's 90 and a striker's 90 are not the same skill.</${Notice}>` : null}
    ${d.facts?.length ? html`<${Section} title="The differences that matter"><div class="stack" style=${{ "--gap": "6px" }}>${d.facts.map((f) => html`<div class="fact" key=${f.key}><${Icon} name="arrowRight" size="sm" /><span><b>${f.leader}</b> leads <b>${f.trailer}</b> on ${d.metrics.find((m) => m.key === f.key)?.label || f.key}: ${metricValue({ decimals: d.metrics.find((m) => m.key === f.key)?.decimals ?? 2 }, f.leader_value)} against ${metricValue({ decimals: d.metrics.find((m) => m.key === f.key)?.decimals ?? 2 }, f.trailer_value)}.</span></div>`)}</div></${Section}>` : null}
    <${Card} title="Profile against role peers" sub="Each dot is a player's percentile (0 to 100) among peers in the same role. Ringed: best in the row. The shaded span is the gap between the players.">
      <${PercentileDots} metrics=${dots} subjects=${players} colors=${colors} />
      <div class="legend" style=${{ marginTop: "14px" }}>${players.map((p, i) => html`<span class="item" key=${p.id}><span class="swatch dot" style=${{ background: colors[i] }}></span>${p.name}</span>`)}</div>
    </${Card}>
    ${eventDots.length ? html`<${Card} title="Defending and passing" sub="From WhoScored event data, ranked among players in the same role who have it. Ringed: best in the row.">
      <${PercentileDots} metrics=${eventDots} subjects=${players} colors=${colors} />
      ${noEvents.length ? html`<p class="xsmall muted" style=${{ marginTop: "12px" }}>No event data for ${noEvents.join(", ")} in this season, so there are no dots for ${noEvents.length > 1 ? "them" : "him"}.</p>` : null}
    </${Card}>` : null}
    <${Card} flush title="Season totals">
      <div class="table-wrap"><table class="data dense">
        <thead><tr><th>Stat</th>${players.map((p, i) => html`<th class="num" key=${p.id}><span class="cmp-dot small" style=${{ background: colors[i] }}></span> ${p.name.split(" ").slice(-1)[0]}</th>`)}</tr></thead>
        <tbody>${rows.map((r) => html`<tr key=${r.key}><td>${r.label}</td>${players.map((p) => html`<td class="num" key=${p.id}>${r.get(p)}</td>`)}</tr>`)}</tbody>
      </table></div>
    </${Card}>
  </div>`;
}

function PlayerCompare({ query, scope }) {
  const ids = (query.ids || "").split(",").filter(Boolean).map(Number).slice(0, 4);
  const q = useApi("/api/compare/players", { ids, league: scope.league, season: scope.season }, { enabled: ids.length >= 2 });
  const setIds = (list) => setQuery({ ids: list.join(",") || null });
  const slotOf = useStableSlots(ids);
  const colorOfId = (id) => SERIES_COLORS[slotOf(id)];
  return html`<div class="stack">
    <${Card} title="Who are we comparing?" sub="Two to four players. Add anyone by name, or start from your shortlist.">
      <${PickedChips} ids=${ids} data=${q.data?.players} colorOf=${colorOfId} remove=${(id) => setIds(ids.filter((x) => x !== id))} />
      <${PlayerPicker} chosen=${ids} onAdd=${(p) => setIds([...ids, p.id])} />
    </${Card}>
    ${ids.length < 2
      ? html`<${EmptyState} icon="compare" title=${ids.length ? "Pick one more player" : "Pick two players to start"} text="Percentiles are measured against each player's role, so you can compare a striker with a winger fairly." />`
      : html`<${Async} q=${q}>${(d) => html`<${PlayersView} d=${d} ids=${ids} remove=${(id) => setIds(ids.filter((x) => x !== id))} scope=${scope} colors=${d.players.map((p) => colorOfId(p.id))} />`}</${Async}>`}
  </div>`;
}

function PickedChips({ ids, data, remove, colorOf }) {
  if (!ids.length) return null;
  return html`<div class="row wrap" style=${{ gap: "8px", marginBottom: "12px" }}>${ids.map((id, i) => {
    const p = data?.find((x) => x.id === id);
    return html`<span class="chip on" key=${id}><span class="cmp-dot small" style=${{ background: colorOf(id) }}></span>${p ? p.name : `#${id}`}<button type="button" aria-label="Remove" onClick=${() => remove(id)} class="chip-x"><${Icon} name="x" /></button></span>`;
  })}</div>`;
}

// ------------------------------------------------------------------ teams

function TeamsView({ d, colors }) {
  const { a, b } = d;
  const cum = (xs) => xs.reduce((acc, v) => [...acc, (acc[acc.length - 1] || 0) + v], []);
  const idx = a && d.xgd_by_match.a.map((_, i) => i + 1);
  const dots = a.percentiles.map((pa, i) => {
    const pb = b.percentiles[i];
    return { key: pa.key, label: pa.label, values: [pa.value, pb.value], pct: [pa.percentile, pb.percentile], best: pa.percentile === pb.percentile ? -1 : pa.percentile > pb.percentile ? 0 : 1, format: (v) => nf(v, 2) };
  });
  const cols = [
    { key: "label", label: "Measure", sortable: false, className: "strong" },
    { key: "a", label: a.team, num: true, sortable: false, render: (r) => html`<span class=${r.best === 0 ? "best-val" : ""}>${nf(r.a, 2)}</span>` },
    { key: "b", label: b.team, num: true, sortable: false, render: (r) => html`<span class=${r.best === 1 ? "best-val" : ""}>${nf(r.b, 2)}</span>` },
  ];
  return html`<div class="stack">
    <div class="grid cols-2">
      ${[a, b].map((t, i) => html`<${Card} key=${t.team}>
        <div class="row" style=${{ gap: "14px" }}><${Crest} team=${t.team} short=${t.short} size=${46} />
          <div class="stack" style=${{ "--gap": "4px" }}><a class="cmp-name" href=${teamHref(t.team)}>${t.team}</a>
            <span class="muted small">${ordinal(t.row.rank)} · ${t.row.pts} pts · ${ordinal(t.row.rank_xpts)} on expected points</span></div>
          <span class="cmp-dot" style=${{ background: colors[i], marginLeft: "auto" }}></span></div>
      </${Card}>`)}
    </div>
    <${Card} title="Profile against the league" sub="Percentile among all teams, higher is better. Ringed: the better side on each measure.">
      <${PercentileDots} metrics=${dots} subjects=${[{ name: a.team }, { name: b.team }]} colors=${colors} />
      <div class="legend" style=${{ marginTop: "14px" }}>${[a, b].map((t, i) => html`<span class="item" key=${t.team}><span class="swatch dot" style=${{ background: colors[i] }}></span>${t.team}</span>`)}</div>
    </${Card}>
    <div class="grid cols-2 top">
      <${Card} title="Net chances through the season" sub="Running total of xG minus xGA, match by match.">
        <${LineChart} x=${idx} series=${[{ key: "a", label: a.team, values: cum(d.xgd_by_match.a), color: colors[0], endLabel: a.short }, { key: "b", label: b.team, values: cum(d.xgd_by_match.b), color: colors[1], endLabel: b.short }]}
          height=${280} yFormat=${(v) => signed(v, 0)} xLabel="Match" zeroLine tooltipTitle=${(i) => `After match ${idx[i]}`} tooltipFormat=${(v) => signed(v, 1)} />
      </${Card}>
      <${Card} flush title="The numbers">
        <${DataTable} columns=${cols} rows=${d.metrics.map((m) => ({ ...m, key: m.key }))} rowKey=${(r) => r.key} dense caption="Team comparison" />
      </${Card}>
    </div>
    ${d.meetings?.length ? html`<${Card} title="Head to head this season">
      <div class="stack" style=${{ "--gap": "10px" }}>${d.meetings.map((m) => html`<a class="row between meeting" key=${m.id} href=${matchHref(m.id)}>
        <span class="muted small num">${dateShort(m.date)}</span>
        <span><b>${m.home}</b> ${m.played ? html`<b class="num">${m.hg}–${m.ag}</b>` : "v"} <b>${m.away}</b></span>
        <span class="muted small num">${m.played ? `xG ${nf(m.hxg, 1)}–${nf(m.axg, 1)}` : m.forecast ? `${Math.round(m.forecast.home * 100)}% / ${Math.round(m.forecast.draw * 100)}% / ${Math.round(m.forecast.away * 100)}%` : ""}</span>
      </a>`)}</div>
    </${Card}>` : null}
  </div>`;
}

function TeamCompare({ query, scope }) {
  const meta = useMeta();
  const teamsQ = useApi("/api/league", { league: scope.league, season: scope.season });
  const names = teamsQ.data?.table?.map((t) => t.team).sort() || [];
  const a = query.a || "", b = query.b || "";
  const q = useApi("/api/compare/teams", { a, b, league: scope.league, season: scope.season }, { enabled: Boolean(a && b && a !== b) });
  const opts = [{ value: "", label: "Choose a team" }, ...names.map((n) => ({ value: n, label: n }))];
  const slotOf = useStableSlots([a, b].filter(Boolean), 2);
  return html`<div class="stack">
    <${Card} title="Which teams?" sub="Two teams from the same league and season.">
      <div class="row wrap" style=${{ gap: "12px", alignItems: "end" }}>
        <div class="field"><label>Team A</label><${Select} value=${a} options=${opts} label="Team A" onChange=${(v) => setQuery({ a: v || null })} /></div>
        <button type="button" class="btn quiet icon-only" title="Swap" aria-label="Swap teams" onClick=${() => setQuery({ a: b || null, b: a || null })}><${Icon} name="compare" /></button>
        <div class="field"><label>Team B</label><${Select} value=${b} options=${opts} label="Team B" onChange=${(v) => setQuery({ b: v || null })} /></div>
      </div>
    </${Card}>
    ${!a || !b || a === b
      ? html`<${EmptyState} icon="compare" title=${a === b && a ? "Pick two different teams" : "Pick two teams"} text="See who really is better on chances, pressing and territory, not just the table." />`
      : html`<${Async} q=${q}>${(d) => html`<div class="stack"><${DataNotices} scope=${d.scope} /><${TeamsView} d=${d} colors=${[SERIES_COLORS[slotOf(a)], SERIES_COLORS[slotOf(b)]]} /></div>`}</${Async}>`}
  </div>`;
}

export default function Compare() {
  const scope = useScope();
  const { query } = useLocation();
  const mode = query.mode === "teams" ? "teams" : "players";
  useDocumentTitle("Compare");
  return html`<div class="stack" style=${{ "--gap": "24px" }}>
    <${PageHead} eyebrow="Compare" title=${mode === "players" ? "Players side by side" : "Teams head to head"}
      sub=${mode === "players" ? "Percentile profiles against each player's own role peers, with the gaps spelled out." : "Two teams on chance quality, style and results."}
      actions=${html`<${Segmented} label="What to compare" value=${mode} onChange=${(v) => setQuery({ mode: v === "players" ? null : v })} options=${[{ value: "players", label: "Players" }, { value: "teams", label: "Teams" }]} />`} />
    ${mode === "players" ? html`<${PlayerCompare} query=${query} scope=${scope} />` : html`<${TeamCompare} query=${query} scope=${scope} />`}
  </div>`;
}

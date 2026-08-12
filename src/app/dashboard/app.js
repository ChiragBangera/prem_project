"use strict";

const state = { league: "EPL", tab: "player", season: 2025 };

const $ = (id) => document.getElementById(id);

async function api(path, body, method = "POST") {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(path, opts);
  if (!res.ok) {
    let detail = "";
    try { detail = (await res.json()).detail || ""; } catch (_) { detail = await res.text(); }
    throw new Error(`${res.status}: ${detail || res.statusText}`);
  }
  return res.json();
}

function clear(node) { node.innerHTML = ""; }
function loading(node) { node.innerHTML = `<div class="loading">Loading</div>`; }
function errored(node, msg) { node.innerHTML = `<div class="error">${msg}</div>`; }

const LEAGUE_LABEL = { EPL: "EPL", La_liga: "La Liga", Serie_A: "Serie A", Ligue_1: "Ligue 1" };

// ---------- tabs & league ----------
document.getElementById("tabs").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-tab]");
  if (!btn) return;
  state.tab = btn.dataset.tab;
  document.querySelectorAll("nav.tabs button").forEach((b) => b.classList.toggle("active", b === btn));
  document.querySelectorAll("section.view").forEach((s) => s.classList.toggle("active", s.id === `view-${state.tab}`));
});
document.getElementById("leaguePicker").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-league]");
  if (!btn) return;
  state.league = btn.dataset.league;
  document.querySelectorAll("header.topbar .leagues button").forEach((b) => b.classList.toggle("active", b === btn));
});

function seasonOf(id) { return parseInt($(id).value, 10) || 2025; }

// ---------- PLAYER ----------
$("playerGo").addEventListener("click", runPlayer);
$("playerName").addEventListener("keydown", (e) => { if (e.key === "Enter") runPlayer(); });

async function runPlayer() {
  const name = $("playerName").value.trim();
  if (!name) return;
  const node = $("playerContent"); loading(node);
  $("playerResolved").textContent = "";
  try {
    const d = await api("/api/v1/analyze/player", { player_name: name, league_name: state.league, season: seasonOf("playerSeason") });
    $("playerResolved").textContent = `${d.player.name} · ${d.player.team_title || "—"} · ${d.player.position || "—"}`;
    renderPlayer(node, d);
  } catch (e) { errored(node, e.message); }
}

function renderPlayer(node, d) {
  const radar = d.radar.profile.filter((p) => p.percentile > 0 || p.raw > 0);
  clear(node);
  node.innerHTML = `
    <div class="grid cols-2">
      <div class="card"><h3>Radar / pizza percentile</h3><div id="radar"></div><div class="hint">${d.radar.peer_count} same-position peers · ${d.radar.minutes_threshold} min min</div></div>
      <div class="card"><h3>Per-90 breakdown</h3>${per90Table(d.per90_breakdown)}</div>
    </div>
    <div class="grid cols-2" style="margin-top:16px">
      <div class="card"><h3>Involvement (xGChain / xGBuildup)</h3>${involvement(d.involvement_profile)}</div>
      <div class="card"><h3>Finishing overperformance</h3>${finishing(d.finishing_overperformance)}</div>
    </div>
    <div class="grid cols-2" style="margin-top:16px">
      <div class="card"><h3>Shot selection</h3>${shotSelection(d.shot_selection)}</div>
      <div class="card"><h3>Similar players</h3>${similarPlayers(d.similar_players)}</div>
    </div>
    <div class="caveat"><strong>Limitations.</strong><ul>${d.limitations.map((l) => `<li>${l}</li>`).join("")}</ul></div>
  `;
  drawRadar("radar", radar);
}

function per90Table(b) {
  const rows = [["goals", "Goals"], ["xG", "xG"], ["npxG", "NP xG"], ["assists", "Assists"], ["xA", "xA"], ["shots", "Shots"], ["key_passes", "Key passes"], ["xGChain", "xG chain"], ["xGBuildup", "xG buildup"]];
  return `<table><thead><tr><th></th><th class="num">Total</th><th class="num">Per 90</th></tr></thead><tbody>
    ${rows.map(([k, lbl]) => `<tr><td>${lbl}</td><td class="num">${fmt(b.raw[k])}</td><td class="num">${fmt(b.per90[k], 3)}</td></tr>`).join("")}
  </tbody></table><div class="hint">${fmt(b.minutes, 0)} minutes over ${fmt(b.games, 0)} games · ${b.position_group || b.position || "—"}</div>`;
}

function involvement(i) {
  return `<div class="kv">
    <span class="k">xGChain</span><span class="v">${fmt(i.xGChain)} · ${fmt(i.xGChain_per90, 3)}/90</span>
    <span class="k">xGBuildup</span><span class="v">${fmt(i.xGBuildup)} · ${fmt(i.xGBuildup_per90, 3)}/90</span>
    <span class="k">Buildup share of chain</span><span class="v">${i.buildup_share_of_chain == null ? "N/A" : fmt(i.buildup_share_of_chain, 3)}</span>
  </div><div class="hint">High buildup-vs-chain = pure deep creator; low = shot/assist-involving finisher.</div>`;
}

function finishing(f) {
  const ci = f.g_minus_xg_ci95 ? `${f.g_minus_xg_ci95.low} to ${f.g_minus_xg_ci95.high}` : "N/A";
  const cls = f.g_minus_xg > 0 ? "good" : f.g_minus_xg < 0 ? "bad" : "";
  return `<div class="kv">
    <span class="k">Goals</span><span class="v">${fmt(f.goals, 0)}</span>
    <span class="k">xG</span><span class="v">${fmt(f.xG)}</span>
    <span class="k">G − xG</span><span class="v"><span class="badge ${cls}">${f.g_minus_xg >= 0 ? "+" : ""}${fmt(f.g_minus_xg)}</span></span>
    <span class="k">Std error</span><span class="v">± ${fmt(f.g_minus_xg_std_error)}</span>
    <span class="k">95% CI</span><span class="v">${ci}</span>
  </div><div class="hint">${f.interpretation}</div>`;
}

function shotSelection(s) {
  return `<div class="kv">
    <span class="k">Shots</span><span class="v">${fmt(s.shots, 0)} · ${fmt(s.shots_per90, 2)}/90</span>
    <span class="k">xG per shot</span><span class="v">${s.xG_per_shot == null ? "N/A" : fmt(s.xG_per_shot, 4)}</span>
    <span class="k">NP xG per shot</span><span class="v">${s.npxG_per_shot == null ? "N/A" : fmt(s.npxG_per_shot, 4)}</span>
  </div><div class="hint">${s.interpretation}</div>`;
}

function similarPlayers(s) {
  if (!s.matches.length) return `<div class="empty">No similar players in pool after filters (pool: ${s.pool_after_filters}).</div>`;
  return `<table><thead><tr><th>Player</th><th>Team</th><th class="num">Sim</th><th class="num">Min</th></tr></thead><tbody>
    ${s.matches.map((m) => `<tr><td>${m.player_name}</td><td>${m.team_title || "—"}</td><td class="num">${fmt(m.similarity, 3)}</td><td class="num">${fmt(m.minutes, 0)}</td></tr>`).join("")}
  </tbody></table>`;
}

// radar on SVG
function drawRadar(container, profile) {
  const el = document.getElementById(container);
  if (!el) return;
  const size = 360, cx = size / 2, cy = size / 2, r = 130;
  const n = profile.length;
  if (n < 3) { el.innerHTML = `<div class="empty">Need ≥3 metrics for radar.</div>`; return; }
  const ang = (i) => -Math.PI / 2 + (i * 2 * Math.PI) / n;
  const pt = (i, rad) => [cx + rad * Math.cos(ang(i)), cy + rad * Math.sin(ang(i))];
  let rings = "";
  for (let g = 1; g <= 4; g++) {
    const rr = r * g / 4;
    let pts = ""; for (let i = 0; i < n; i++) { const [x, y] = pt(i, rr); pts += `${x},${y} `; }
    rings += `<polygon points="${pts}" fill="none" stroke="#243040" stroke-width="1"/>`;
  }
  let spokes = "", labels = "";
  for (let i = 0; i < n; i++) {
    const [x, y] = pt(i, r);
    spokes += `<line x1="${cx}" y1="${cy}" x2="${x}" y2="${y}" stroke="#243040" stroke-width="1"/>`;
    const [lx, ly] = pt(i, r + 18);
    labels += `<text x="${lx}" y="${ly}" fill="#8a98a8" font-size="10" text-anchor="middle" dominant-baseline="middle">${profile[i].label}</text>`;
  }
  let poly = ""; const vals = [];
  for (let i = 0; i < n; i++) { const pct = profile[i].percentile; const rr = r * pct / 100; const [x, y] = pt(i, rr); poly += `${x},${y} `; vals.push(`<text x="${x}" y="${y - 6}" fill="#4ea1ff" font-size="9" text-anchor="middle">${Math.round(pct)}</text>`); }
  el.innerHTML = `<svg class="radar-svg" viewBox="0 0 ${size} ${size}">${rings}${spokes}<polygon points="${poly}" fill="rgba(78,161,255,0.18)" stroke="#4ea1ff" stroke-width="2"/>${labels}${vals.join("")}</svg>`;
}

// ---------- TEAM ----------
$("teamGo").addEventListener("click", runTeam);
async function runTeam() {
  const name = $("teamName").value.trim(); if (!name) return;
  const node = $("teamContent"); loading(node);
  try {
    const d = await api("/api/v1/analyze/team", { team_name: name, league_name: state.league, season: seasonOf("teamSeason") });
    renderTeam(node, d);
  } catch (e) { errored(node, e.message); }
}

function renderTeam(node, d) {
  const s = d.style, pp = d.ppda_home_away, f = d.form_momentum;
  clear(node);
  node.innerHTML = `
    <div class="grid cols-2">
      <div class="card"><h3>Style profile · ${s.team}</h3>${styleKv(s)}</div>
      <div class="card"><h3>Pressing home / away</h3>${ppdaKv(pp)}</div>
    </div>
    <div class="card" style="margin-top:16px"><h3>Form & momentum (rolling 5 xGD)</h3><div id="formChart"></div>${f.interpretation ? `<div class="hint">${f.interpretation}</div>` : ""}</div>
    ${(() => { drawFormChartDeferred("formChart", f); return ""; })()}
    ${d.situational_xg_share ? `<div class="card" style="margin-top:16px"><h3>Situational xG share</h3>${situationTable(d.situational_xg_share)}</div>` : ""}
    <div class="caveat"><strong>Limitations.</strong><ul>${d.limitations.map((l) => `<li>${l}</li>`).join("")}</ul></div>
  `;
  drawFormChart("formChart", f);
}

function styleKv(s) {
  return `<div class="kv">
    <span class="k">xG / game</span><span class="v">${fmt(s.xG_per_game)}</span>
    <span class="k">xGA / game</span><span class="v">${fmt(s.xGA_per_game)}</span>
    <span class="k">xG diff / game</span><span class="v">${fmt(s.xG_diff_per_game)}</span>
    <span class="k">NP xGD</span><span class="v">${fmt(s.npxGD)}</span>
    <span class="k">PPDA</span><span class="v">${fmt(s.PPDA)} · opp ${fmt(s.OPPDA)}</span>
    <span class="k">Deep completions</span><span class="v">${s.deep_completions} / allowed ${s.deep_completions_allowed}</span>
    <span class="k">xPTS</span><span class="v">${fmt(s.xPTS)}</span>
  </div><div class="hint">${s.interpretation}</div>`;
}
function ppdaKv(p) {
  return `<div class="kv">
    <span class="k">PPDA home</span><span class="v">${fmt(p.ppda_home)} (${p.matches_home} m)</span>
    <span class="k">PPDA away</span><span class="v">${fmt(p.ppda_away)} (${p.matches_away} m)</span>
  </div><div class="hint">${p.interpretation || ""}</div>`;
}
function drawFormChartDeferred() {} // noop placeholder so the template literal ordering is stable
function drawFormChart(container, f) {
  const el = document.getElementById(container); if (!el || !f.rolling_xgd || !f.rolling_xgd.length) return;
  const w = 1100, h = 240, pad = 28, x0 = pad, x1 = w - pad, y0 = 16, y1 = h - 28;
  const pts = f.rolling_xgd;
  const xs = pts.map((_, i) => x0 + (i * (x1 - x0)) / Math.max(pts.length - 1, 1));
  const vals = pts.map((p) => p.rolling_xGD);
  const yMin = Math.min(...vals), yMax = Math.max(...vals), yPad = Math.max(0.1, (yMax - yMin) / 2);
  const lo = Math.min(yMin - yPad, -0.2), hi = Math.max(yMax + yPad, 0.2);
  const y = (v) => y1 - ((v - lo) / (hi - lo)) * (y1 - y0);
  const line = xs.map((x, i) => `${i ? "L" : "M"}${x},${y(vals[i])}`).join(" ");
  const zero = y(0);
  el.innerHTML = `<svg class="timeline-svg" viewBox="0 0 ${w} ${h}">
    <line x1="${x0}" y1="${zero}" x2="${x1}" y2="${zero}" stroke="#243040" stroke-dasharray="3 4"/>
    <path d="${line}" fill="none" stroke="#41d6a3" stroke-width="2"/>
    <text x="${x0}" y="${zero - 6}" fill="#8a98a8" font-size="10">0 xGD</text>
    <text x="${x0}" y="${y0}" fill="#8a98a8" font-size="10">rolling 5-match xGD — recent: ${f.recent_xGD == null ? "N/A" : fmt(f.recent_xGD)} · season mean ${f.season_mean_xGD == null ? "N/A" : fmt(f.season_mean_xGD)}</text>
  </svg>`;
}

// ---------- LEAGUE ----------
$("leagueGo").addEventListener("click", runLeague);
async function runLeague() {
  const node = $("leagueContent"); loading(node);
  try {
    const d = await api("/api/v1/analyze/league", { league_name: state.league, season: seasonOf("leagueSeason") });
    renderLeague(node, d);
  } catch (e) { errored(node, e.message); }
}
function renderLeague(node, d) {
  const lying = d.is_lying;
  clear(node);
  node.innerHTML = `
    <div class="grid cols-2">
      <div class="card"><h3>xPTS "is-lying" · biggest over/under</h3>
        <table><thead><tr><th>Team</th><th class="num">PTS</th><th class="num">xPTS</th><th class="num">Gap</th></tr></thead><tbody>
          ${[lying.biggest_overperformer, lying.biggest_underperformer].filter(Boolean).map((r) => `<tr><td>${r.team}</td><td class="num">${r.points}</td><td class="num">${fmt(r.xPTS)}</td><td class="num">${gap(r.xPTS_gap)}</td></tr>`).join("")}
        </tbody></table>
      </div>
      <div class="card"><h3>Finishing & defensive variance</h3>${varianceBlock(d.variance)}</div>
    </div>
    <div class="card" style="margin-top:16px"><h3>Full "is-lying" table · ${LEAGUE_LABEL[state.league] || state.league}</h3>${isLyingTable(lying)}</div>
    <div class="grid cols-2" style="margin-top:16px">
      <div class="card"><h3>PPDA ranking (low = intense press)</h3>${ppdaTable(d.ppda_ranking)}</div>
      <div class="card"><h3>League pace</h3>${paceBlock(d.pace)}</div>
    </div>
    <div class="caveat"><strong>Limitations.</strong><ul>${d.limitations.map((l) => `<li>${l}</li>`).join("")}</ul></div>
  `;
}
function gap(v) { return `<span class="badge ${v > 0 ? "good" : v < 0 ? "bad" : ""}">${v >= 0 ? "+" : ""}${fmt(v)}</span>`; }
function isLyingTable(lying) {
  return `<table><thead><tr><th>Team</th><th class="num">PTS</th><th class="num">xPTS</th><th class="num">Gap</th><th class="num">G−xG</th><th class="num">xGA−GA</th></tr></thead><tbody>
    ${lying.rows.map((r) => `<tr><td>${r.team}</td><td class="num">${r.points}</td><td class="num">${fmt(r.xPTS)}</td><td class="num">${gap(r.xPTS_gap)}</td><td class="num">${fmt(r.g_minus_xg)}</td><td class="num">${fmt(r.xga_minus_ga)}</td></tr>`).join("")}
  </tbody></table>`;
}
function varianceBlock(v) {
  const f = v.finishing_variance, d = v.defensive_variance;
  return `<div class="kv">
    <span class="k">Mean G−xG</span><span class="v">${fmt(f.mean_g_minus_xg)}</span>
    <span class="k">Stdev G−xG</span><span class="v">${fmt(f.stdev_g_minus_xg)}</span>
    <span class="k">Mean xGA−GA</span><span class="v">${fmt(d.mean_xga_minus_ga)}</span>
    <span class="k">Stdev xGA−GA</span><span class="v">${fmt(d.stdev_xga_minus_ga)}</span>
  </div><div class="hint">${v.interpretation}</div>`;
}
function ppdaTable(p) {
  return `<table><thead><tr><th>Team</th><th class="num">PPDA</th><th class="num">OPPDA</th><th class="num">DC</th><th class="num">DC allowed</th></tr></thead><tbody>
    ${p.ranking.map((r) => `<tr><td>${r.team}</td><td class="num">${fmt(r.PPDA)}</td><td class="num">${fmt(r.OPPDA)}</td><td class="num">${r.deep_completions}</td><td class="num">${r.deep_completions_allowed}</td></tr>`).join("")}
  </tbody></table><div class="hint">${p.interpretation}</div>`;
}
function paceBlock(p) {
  return `<div class="kv"><span class="k">xG / game</span><span class="v">${fmt(p.xG_per_game)}</span><span class="k">xGA / game</span><span class="v">${fmt(p.xGA_per_game)}</span><span class="k">Matches</span><span class="v">${p.matches}</span></div><div class="hint">${p.interpretation}</div>`;
}

// ---------- MATCH ----------
$("matchGo").addEventListener("click", runMatch);
async function runMatch() {
  const id = $("matchId").value.trim(); if (!id) return;
  const node = $("matchContent"); loading(node);
  try {
    const d = await api(`/api/v1/analyze/match/${encodeURIComponent(id)}`);
    renderMatch(node, d);
  } catch (e) { errored(node, e.message); }
}
function renderMatch(node, d) {
  const n = d.narrative; clear(node);
  node.innerHTML = `
    <div class="card"><h3>${n.narrative}</h3><div class="kv"><span class="k">Scoreline</span><span class="v">${n.scoreline.h} - ${n.scoreline.a}</span><span class="k">xG</span><span class="v">${fmt(n.xG.h)} - ${fmt(n.xG.a)}</span></div></div>
    <div class="card" style="margin-top:16px"><h3>Shot map</h3><div id="shotmap"></div><div class="hint">Coord orientation: defending goal at left. Goal = filled; hover a circle for shot details.</div></div>
    <div class="card" style="margin-top:16px"><h3>xG timeline (cumulative)</h3><div id="xgtl"></div></div>
    <div class="grid cols-2" style="margin-top:16px">
      <div class="card"><h3>Big-chance inventory (xG ≥ ${d.big_chance_inventory.xG_threshold})</h3>${bigChances(d.big_chance_inventory)}</div>
      <div class="card"><h3>Situation breakdown</h3>${situationBreakdown(d.situation_breakdown)}</div>
    </div>
    <div class="caveat"><strong>Limitations.</strong><ul>${d.limitations.map((l) => `<li>${l}</li>`).join("")}</ul></div>
  `;
  drawShotMap("shotmap", d.shot_map);
  drawXgTimeline("xgtl", d.xg_timeline);
}
function bigChances(inv) {
  return `<table><thead><tr><th>Side</th><th>Min</th><th>Player</th><th class="num">xG</th><th>Result</th></tr></thead><tbody>
    ${inv.home.map((s) => row("home", s)).join("")}${inv.away.map((s) => row("away", s)).join("")}
  </tbody></table>`;
  function row(side, s) { return `<tr><td>${side}</td><td>${s.minute}'</td><td>${s.player || "—"}</td><td class="num">${fmt(s.xG)}</td><td>${s.result}</td></tr>`; }
}
function situationBreakdown(sb) {
  const rows = (obj) => Object.entries(obj).sort((a, b) => b[1].xG - a[1].xG).map(([k, v]) => `<tr><td>${k}</td><td class="num">${v.shots}</td><td class="num">${fmt(v.xG)}</td><td class="num">${v.goals}</td></tr>`).join("");
  return `<table><thead><tr><th colspan=4 style="color:var(--accent)">Home</th></tr><tr><th>Situation</th><th class="num">Shots</th><th class="num">xG</th><th class="num">G</th></tr></thead><tbody>${rows(sb.home)}</tbody></table>` +
    `<table style="margin-top:10px"><thead><tr><th colspan=4 style="color:#41d6a3">Away</th></tr><tr><th>Situation</th><th class="num">Shots</th><th class="num">xG</th><th class="num">G</th></tr></thead><tbody>${rows(sb.away)}</tbody></table>`;
}
function drawShotMap(container, sm) {
  const el = document.getElementById(container); if (!el) return;
  const w = 700, h = 460; const px = (v) => v * w; const py = (v) => (1 - v) * h;
  const home = sm.home || [], away = sm.away || [];
  const circles = (shots, color) => shots.map((s) => {
    const r = 4 + Math.sqrt(Math.max(parseFloat(s.xG) || 0, 0.001)) * 14;
    const fill = s.result === "Goal";
    const tip = `${s.player || "?"} ${s.minute}' — ${s.result} (xG ${fmt(s.xG, 3)})`;
    return `<circle cx="${px(s.X)}" cy="${py(s.Y)}" r="${r}" fill="${fill ? color : "none"}" stroke="${color}" stroke-width="${fill ? 2 : 1.2}" opacity="${fill ? 0.85 : 0.55}"><title>${tip}</title></circle>`;
  }).join("");
  const lines = `<line x1="0" y1="${h/2}" x2="${w}" y2="${h/2}" stroke="#1a2230"/><line x1="${w/2}" y1="0" x2="${w/2}" y2="${h}" stroke="#1a2230"/><circle cx="${w/2}" cy="${h/2}" r="60" fill="none" stroke="#1a2230"/><rect x="0" y="${h/2-60}" width="44" height="120" fill="none" stroke="#1a2230"/><rect x="${w-44}" y="${h/2-60}" width="44" height="120" fill="none" stroke="#1a2230"/>`;
  el.innerHTML = `<svg class="pitch-svg" viewBox="0 0 ${w} ${h}"><rect x="0" y="0" width="${w}" height="${h}" fill="#0f1620"/>${lines}<g>${circles(away, "#41d6a3")}</g><g>${circles(home, "#4ea1ff")}</g></svg><div class="hint"><span style="color:#4ea1ff">● home</span> &nbsp; <span style="color:#41d6a3">● away</span> &nbsp; radius scales with xG; filled = goal &nbsp; hover for shot details</div>`;
}
function drawXgTimeline(container, tl) {
  const el = document.getElementById(container); if (!el) return;
  const w = 1100, h = 240, pad = 30, x0 = pad, x1 = w - pad, y0 = 24, y1 = h - 28;
  const home = tl.home || [], away = tl.away || [];
  const allMax = Math.max(...home.map((p) => p.cumulative_xG), ...away.map((p) => p.cumulative_xG), 0.5);
  const minuteMax = Math.max(...home.map((p) => p.minute), ...away.map((p) => p.minute), 90);
  const x = (m) => x0 + (m / minuteMax) * (x1 - x0);
  const y = (v) => y1 - (v / allMax) * (y1 - y0);
  const path = (pts, color) => pts.length ? `<path d="${pts.map((p, i) => `${i ? "L" : "M"}${x(p.minute)},${y(p.cumulative_xG)}`).join(" ")}" fill="none" stroke="${color}" stroke-width="2"/>` : "";
  el.innerHTML = `<svg class="timeline-svg" viewBox="0 0 ${w} ${h}">${path(home, "#4ea1ff")}${path(away, "#41d6a3")}<text x="${x0}" y="${y0}" fill="#8a98a8" font-size="10">cumulative xG</text><text x="${x1-70}" y="${y1+18}" fill="#8a98a8" font-size="10">minute →</text></svg>`;
}

// ---------- DISCOVER ----------
$("discoverGo").addEventListener("click", runDiscover);
async function runDiscover() {
  const node = $("discoverContent"); loading(node);
  try {
    const d = await api("/api/v1/discover/players", {
      league_name: state.league,
      season: seasonOf("leagueSeason"),
      position_group: $("discoverPosition").value || null,
      minimum_minutes: parseFloat($("discoverMinutes").value) || 900,
      order_by: $("discoverOrderBy").value,
    });
    renderDiscover(node, d);
  } catch (e) { errored(node, e.message); }
}
function renderDiscover(node, d) {
  const top = d.players[0];
  clear(node);
  node.innerHTML = `<div class="card"><h3>Top ${d.limit} ${d.position_group || "all-position"} players ≥ ${d.minimum_minutes} min · ordered by ${d.order_by}</h3>
    <table><thead><tr><th>Player</th><th>Team</th><th>Pos</th><th class="num">Min</th><th class="num">NP xG</th><th class="num">xA</th><th class="num">xGChain</th><th class="num">xGBuildup</th><th class="num">G</th><th class="num">A</th></tr></thead><tbody>
      ${d.players.map((p) => `<tr><td data-name="${p.name}">${p.name}</td><td>${p.team}</td><td>${p.position_group}</td><td class="num">${fmt(p.minutes, 0)}</td><td class="num">${fmt(p.npxG)}</td><td class="num">${fmt(p.xA)}</td><td class="num">${fmt(p.xGChain)}</td><td class="num">${fmt(p.xGBuildup)}</td><td class="num">${fmt(p.goals, 0)}</td><td class="num">${fmt(p.assists, 0)}</td></tr>`).join("")}
    </tbody></table>
    <div class="hint">Click a name to load that player in the Player tab${top ? `. Suggested first: ${top.name}.` : ""}.</div>
  </div>`;
  node.querySelectorAll("td[data-name]").forEach((td) => td.addEventListener("click", () => {
    const name = td.getAttribute("data-name");
    $("playerName").value = name;
    document.querySelector('nav.tabs button[data-tab="player"]').click();
    runPlayer();
  }));
}

// ---------- helpers ----------
function fmt(v, d = 2) {
  if (v == null || v === "" || Number.isNaN(v)) return "—";
  const n = Number(v);
  if (Number.isInteger(n) && d === 0) return String(n);
  return n.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });
}

// pre-load
runLeague();

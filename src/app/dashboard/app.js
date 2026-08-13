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

function clear(node) { if (node._timer) clearInterval(node._timer); node.innerHTML = ""; }
function loading(node) {
  node.dataset.t0 = Date.now();
  node.innerHTML = `<div class="loading">Loading <span class="elapsed">(0s)</span></div>`;
  const span = node.querySelector(".elapsed");
  if (node._timer) clearInterval(node._timer);
  node._timer = setInterval(() => {
    const s = Math.round((Date.now() - Number(node.dataset.t0)) / 1000);
    if (span) span.textContent = `(${s}s)`;
  }, 1000);
}
function errored(node, msg) { if (node._timer) clearInterval(node._timer); node.innerHTML = `<div class="error">${msg}</div>`; }

function windowBadge(d) {
  const w = d && d.date_window;
  if (!w || (!w.start_date && !w.end_date)) return "";
  const label = [w.start_date, w.end_date].filter(Boolean).join(" → ");
  return `<span class="badge">window ${label}</span>`;
}

// input persistence + example chips
const PERSIST_IDS = ["playerName", "playerSeason", "teamName", "teamSeason", "leagueSeason",
  "predHome", "predAway", "predSeason", "simSeason", "calSeason",
  "compareA", "compareB", "compareSeason", "discoverMinutes", "discoverPosition", "discoverOrderBy", "matchId"];
PERSIST_IDS.forEach((id) => {
  const el = document.getElementById(id);
  if (!el) return;
  const saved = localStorage.getItem(`prem_${id}`);
  if (saved !== null) el.value = saved;
  el.addEventListener("input", () => localStorage.setItem(`prem_${id}`, el.value));
});
const savedLeague = localStorage.getItem("prem_league");
if (savedLeague) {
  document.querySelectorAll("header.topbar .leagues button").forEach((b) => b.classList.toggle("active", b.dataset.league === savedLeague));
  state.league = savedLeague || state.league;
}

document.addEventListener("click", (e) => {
  const chip = e.target.closest(".example");
  if (!chip) return;
  const input = document.getElementById(chip.dataset.id);
  if (!input) return;
  input.value = chip.dataset.value;
  localStorage.setItem(`prem_${chip.dataset.id}`, chip.dataset.value);
  input.dispatchEvent(new Event("change", { bubbles: true }));
  const action = chip.dataset.action;
  if (action && typeof window[action] === "function") window[action]();
});

const LEAGUE_LABEL = { EPL: "EPL", La_liga: "La Liga", Serie_A: "Serie A", Ligue_1: "Ligue 1" };

// ---------- glossary / explanations ----------
let GLOSSARY = {};
(async () => {
  try {
    const d = await api("/api/v1/glossary", null, "GET");
    GLOSSARY = d.by_key || {};
    window.__GLOSSARY_GROUPS__ = d.groups || [];
    window.__FEATURE_LABELS__ = d.feature_labels || {};
    if (state.tab === "info") renderInfo();
  } catch (_) { /* info degrades gracefully */ }
})();

function term(key, fallback) {
  const entry = GLOSSARY[key];
  const label = entry ? entry.label : fallback || key;
  return `<span class="term" data-term="${key}">${label}</span>`;
}

const tooltipEl = document.getElementById("tooltip");
document.addEventListener("mouseover", (e) => {
  const t = e.target.closest(".term");
  if (!t) return;
  const entry = GLOSSARY[t.dataset.term];
  if (!entry) return;
  tooltipEl.innerHTML = `<strong>${entry.label}</strong><br>${entry.short}<br><span class="tt-long">${entry.long}</span>`;
  tooltipEl.classList.add("show");
});
document.addEventListener("mousemove", (e) => {
  if (!tooltipEl.classList.contains("show")) return;
  const w = tooltipEl.offsetWidth, h = tooltipEl.offsetHeight;
  let x = e.clientX + 14, y = e.clientY + 14;
  if (x + w > window.innerWidth - 8) x = e.clientX - w - 12;
  if (y + h > window.innerHeight - 8) y = e.clientY - h - 12;
  tooltipEl.style.left = `${Math.max(8, x)}px`;
  tooltipEl.style.top = `${Math.max(8, y)}px`;
});
document.addEventListener("mouseout", (e) => {
  if (e.target.closest(".term")) tooltipEl.classList.remove("show");
});

function renderInfo() {
  const node = document.getElementById("infoContent");
  if (!node) return;
  const query = (document.getElementById("infoSearch").value || "").trim().toLowerCase();
  const groups = window.__GLOSSARY_GROUPS__ || [];
  node.innerHTML = groups.map((g) => {
    const entries = g.entries.filter((en) =>
      !query || en.label.toLowerCase().includes(query) || en.key.toLowerCase().includes(query)
        || en.short.toLowerCase().includes(query) || en.long.toLowerCase().includes(query)
    );
    if (!entries.length) return "";
    return `<div class="card" style="margin-top:16px"><h3>${g.group}</h3>
      ${entries.map((en) => `<div class="gloss"><div class="gloss-label">${en.label}</div>
        <div class="gloss-short">${en.short}</div>
        <div class="gloss-long">${en.long}</div></div>`).join("")}
    </div>`;
  }).join("") || `<div class="empty">No metrics match "${query}".</div>`;
}
document.getElementById("infoSearch").addEventListener("input", renderInfo);

// ---------- tabs & league ----------
document.getElementById("tabs").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-tab]");
  if (!btn) return;
  state.tab = btn.dataset.tab;
  document.querySelectorAll("nav.tabs button").forEach((b) => b.classList.toggle("active", b === btn));
  document.querySelectorAll("section.view").forEach((s) => s.classList.toggle("active", s.id === `view-${state.tab}`));
  if (state.tab === "info") renderInfo();
});
document.getElementById("leaguePicker").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-league]");
  if (!btn) return;
  state.league = btn.dataset.league;
  localStorage.setItem("prem_league", state.league);
  document.querySelectorAll("header.topbar .leagues button").forEach((b) => b.classList.toggle("active", b === btn));
});

function seasonOf(id) { return parseInt($(id).value, 10) || 2025; }
function dateOf(id) { const v = $(id).value; return v || null; }

// ---------- PLAYER ----------
$("playerGo").addEventListener("click", runPlayer);
$("playerCareerGo").addEventListener("click", runCareer);
$("playerName").addEventListener("keydown", (e) => { if (e.key === "Enter") runPlayer(); });

async function runPlayer() {
  const name = $("playerName").value.trim();
  if (!name) return;
  const node = $("playerContent"); loading(node);
  $("playerResolved").textContent = "";
  try {
    const d = await api("/api/v1/analyze/player", {
      player_name: name, league_name: state.league, season: seasonOf("playerSeason"),
      start_date: dateOf("playerFrom"), end_date: dateOf("playerTo"),
    });
    $("playerResolved").textContent = `${d.player.name} · ${d.player.team_title || "—"} · ${d.player.position || "—"}`;
    renderPlayer(node, d);
  } catch (e) { errored(node, e.message); }
}

async function runCareer() {
  const name = $("playerName").value.trim();
  if (!name) return;
  const node = $("playerContent"); loading(node);
  $("playerResolved").textContent = "";
  try {
    const d = await api("/api/v1/analyze/player/career", {
      player_name: name, league_name: state.league, season_end: seasonOf("playerSeason"),
    });
    $("playerResolved").textContent = `${d.player_name} · ${d.n_seasons_present} seasons in ${LEAGUE_LABEL[d.league_name] || d.league_name}`;
    renderCareer(node, d);
  } catch (e) { errored(node, e.message); }
}

function renderCareer(node, d) {
  clear(node);
  const present = d.seasons.filter((s) => s.present);
  const latest = present[present.length - 1];
  node.innerHTML = `
    <div class="card"><h3>Career trajectory · ${d.player_name} · ${LEAGUE_LABEL[d.league_name] || d.league_name}</h3>
      <div class="controls">
        <div class="field"><label>Chart metric</label>
          <select id="careerMetric">
            <option value="xGChain_per90">${term("xG_chain")} /90</option>
            <option value="xGBuildup_per90">${term("xG_buildup")} /90</option>
            <option value="goal_involvement_per90">${term("goal_involvement")} /90</option>
            <option value="xG_per90">${term("xG")} /90</option>
            <option value="goals_per90">${term("goals")} /90</option>
            <option value="xG_per_shot">${term("xG_per_shot")}</option>
            <option value="conversion">${term("conversion")}</option>
            <option value="shots_per90">${term("shots")} /90</option>
            <option value="key_passes_per90">${term("key_passes")} /90</option>
          </select>
        </div>
      </div>
      <div id="careerChart"></div>
      <div class="hint">Hover any highlighted metric for what it means. Per-90 rates are the fair cross-season comparison.</div>
    </div>
    <div class="card" style="margin-top:16px"><h3>Season by season</h3>
      <table><thead><tr><th>Season</th><th>Team</th><th>Pos</th><th class="num">Games</th><th class="num">Min</th><th class="num">${term("goals")}</th><th class="num">${term("xG")}</th><th class="num">${term("npxG")}</th><th class="num">${term("assists")}</th><th class="num">${term("xA")}</th><th class="num">${term("shots")}</th><th class="num">${term("xG_per_shot")}</th><th class="num">${term("conversion")}</th><th class="num">${term("goal_involvement")}/90</th><th class="num">${term("cards")}</th></tr></thead><tbody>
        ${d.seasons.map((s, i) => {
          if (!s.present) return `<tr><td>${s.season}</td><td colspan=14 style="color:var(--muted)">— not in this league that season</td></tr>`;
          const changed = i > 0 && d.seasons[i - 1].present && d.seasons[i - 1].team !== s.team;
          return `<tr><td>${s.season}</td><td>${s.team}${changed ? ' <span class="badge good">new team</span>' : ""}</td><td>${s.position_group || "—"}</td>
            <td class="num">${fmt(s.games, 0)}</td><td class="num">${fmt(s.minutes, 0)}</td>
            <td class="num">${fmt(s.goals, 0)}</td><td class="num">${fmt(s.xG)}</td><td class="num">${fmt(s.npxG)}</td>
            <td class="num">${fmt(s.assists, 0)}</td><td class="num">${fmt(s.xA)}</td>
            <td class="num">${fmt(s.shots, 0)}</td><td class="num">${fmt(s.xG_per_shot, 3)}</td><td class="num">${fmt(s.conversion, 3)}</td>
            <td class="num">${fmt(s.goal_involvement_per90, 3)}</td>
            <td class="num">${fmt(s.yellow_cards, 0)}y / ${fmt(s.red_cards, 0)}r</td></tr>`;
        }).join("")}
      </tbody></table>
      ${d.team_changes.length ? `<div class="hint">Team changes: ${d.team_changes.map((c) => `${c.season}: ${c.from} → ${c.to}`).join(" · ")}</div>` : ""}
    </div>
    ${latest && latest.shot_profile ? `
    <div class="grid cols-2" style="margin-top:16px">
      <div class="card"><h3>${term("situations")} · ${latest.season}</h3>${shareBars(latest.shot_profile.situations)}</div>
      <div class="card"><h3>${term("shot_zones")} · ${latest.season}</h3>${shareBars(latest.shot_profile.zones)}</div>
    </div>
    <div class="grid cols-2" style="margin-top:16px">
      <div class="card"><h3>${term("shot_types")} · ${latest.season}</h3>${shareBars(latest.shot_profile.types)}</div>
      <div class="card"><h3>${term("starter_sub")} · ${latest.season}</h3>${roleSplit(latest.role_split)}</div>
    </div>` : ""}
    <div class="caveat"><strong>Interpretation.</strong> ${d.interpretation}<ul>${d.limitations.map((l) => `<li>${l}</li>`).join("")}</ul></div>
  `;
  const draw = () => drawCareerChart("careerChart", present, $("careerMetric").value);
  $("careerMetric").addEventListener("change", draw);
  draw();
}

function shareBars(rows) {
  if (!rows || !rows.length) return `<div class="empty">No shot-profile data.</div>`;
  return rows.map((r) => `
    <div class="bar-row">
      <span class="bar-label">${r.name}</span>
      <div class="bar-track"><div class="bar-fill" style="width:${Math.max(2, r.xG_share * 100)}%"></div></div>
      <span class="bar-val">${Math.round(r.xG_share * 100)}% of xG · ${fmt(r.goals, 0)} G / ${fmt(r.shots, 0)} shots</span>
    </div>`).join("");
}

function roleSplit(roles) {
  if (!roles || !roles.length) return `<div class="empty">No role data.</div>`;
  const total = roles.reduce((a, r) => a + r.minutes, 0) || 1;
  return roles.map((r) => `
    <div class="bar-row">
      <span class="bar-label">${r.role}</span>
      <div class="bar-track"><div class="bar-fill green" style="width:${Math.max(2, (r.minutes / total) * 100)}%"></div></div>
      <span class="bar-val">${fmt(r.minutes, 0)} min (${Math.round((r.minutes / total) * 100)}%) · ${fmt(r.games, 0)} games</span>
    </div>`).join("");
}

function drawCareerChart(container, rows, metricKey) {
  const el = document.getElementById(container);
  if (!el) return;
  if (rows.length < 2) { el.innerHTML = `<div class="empty">Not enough seasons present for a trajectory chart.</div>`; return; }
  const w = 1100, h = 260, pad = 34, x0 = pad, x1 = w - pad, y0 = 18, y1 = h - 30;
  const vals = rows.map((r) => Number(r[metricKey]) || 0);
  const allMax = Math.max(...vals, 0.001);
  const x = (i) => x0 + (i * (x1 - x0)) / Math.max(rows.length - 1, 1);
  const y = (v) => y1 - (v / allMax) * (y1 - y0);
  const path = vals.map((v, i) => `${i ? "L" : "M"}${x(i)},${y(v)}`).join(" ");
  const dots = vals.map((v, i) => `<circle cx="${x(i)}" cy="${y(v)}" r="3.5" fill="#4ea1ff"><title>${rows[i].season}: ${fmt(v, 3)}</title></circle>`).join("");
  const labels = rows.map((r, i) => `<text x="${x(i)}" y="${y1 + 16}" fill="#8a98a8" font-size="10" text-anchor="middle">${r.season}</text>`).join("");
  const entry = GLOSSARY[metricKey] || {};
  el.innerHTML = `<svg class="timeline-svg" viewBox="0 0 ${w} ${h}">
    <path d="${path}" fill="none" stroke="#4ea1ff" stroke-width="2"/>${dots}
    ${labels}
    <text x="${x0}" y="${y0}" fill="#8a98a8" font-size="10">${entry.label || metricKey} by season</text>
  </svg>`;
}

function renderPlayer(node, d) {
  const radar = d.radar.profile.filter((p) => p.percentile > 0 || p.raw > 0);
  clear(node);
  node.innerHTML = `
    <div class="grid cols-2">
      <div class="card"><h3>${term("radar")} · ${term("percentile")} ${windowBadge(d)}</h3><div id="radar"></div><div class="hint">${d.radar.peer_count} same-position peers · ${d.radar.minutes_threshold} min min</div></div>
      <div class="card"><h3>${term("per90")} breakdown</h3>${per90Table(d.per90_breakdown)}</div>
    </div>
    <div class="grid cols-2" style="margin-top:16px">
      <div class="card"><h3>Involvement (${term("xG_chain")} / ${term("xG_buildup")})</h3>${involvement(d.involvement_profile)}</div>
      <div class="card"><h3>${term("g_minus_xg")}</h3>${finishing(d.finishing_overperformance)}</div>
    </div>
    <div class="grid cols-2" style="margin-top:16px">
      <div class="card"><h3>Shot selection</h3>${shotSelection(d.shot_selection)}</div>
      <div class="card"><h3>${term("similar_players")}</h3>${similarPlayers(d.similar_players)}</div>
    </div>
    <div class="caveat"><strong>Limitations.</strong><ul>${d.limitations.map((l) => `<li>${l}</li>`).join("")}</ul></div>
  `;
  drawRadar("radar", radar);
}

function per90Table(b) {
  const rows = [["goals", "goals"], ["xG", "xG"], ["npxG", "npxG"], ["assists", "assists"], ["xA", "xA"], ["shots", "shots"], ["key_passes", "key_passes"], ["xGChain", "xG_chain"], ["xGBuildup", "xG_buildup"]];
  return `<table><thead><tr><th></th><th class="num">Total</th><th class="num">${term("per90")}</th></tr></thead><tbody>
    ${rows.map(([k, gk]) => `<tr><td>${term(gk)}</td><td class="num">${fmt(b.raw[k])}</td><td class="num">${fmt(b.per90[k], 3)}</td></tr>`).join("")}
  </tbody></table><div class="hint">${fmt(b.minutes, 0)} minutes over ${fmt(b.games, 0)} games · ${b.position_group || b.position || "—"}</div>`;
}

function involvement(i) {
  return `<div class="kv">
    <span class="k">${term("xG_chain")}</span><span class="v">${fmt(i.xGChain)} · ${fmt(i.xGChain_per90, 3)}/90</span>
    <span class="k">${term("xG_buildup")}</span><span class="v">${fmt(i.xGBuildup)} · ${fmt(i.xGBuildup_per90, 3)}/90</span>
    <span class="k">Buildup share of chain</span><span class="v">${i.buildup_share_of_chain == null ? "N/A" : fmt(i.buildup_share_of_chain, 3)}</span>
  </div><div class="hint">High buildup-vs-chain = pure deep creator; low = shot/assist-involving finisher.</div>`;
}

function finishing(f) {
  const ci = f.g_minus_xg_ci95 ? `${f.g_minus_xg_ci95.low} to ${f.g_minus_xg_ci95.high}` : "N/A";
  const cls = f.g_minus_xg > 0 ? "good" : f.g_minus_xg < 0 ? "bad" : "";
  return `<div class="kv">
    <span class="k">${term("goals")}</span><span class="v">${fmt(f.goals, 0)}</span>
    <span class="k">${term("xG")}</span><span class="v">${fmt(f.xG)}</span>
    <span class="k">${term("g_minus_xg")}</span><span class="v"><span class="badge ${cls}">${f.g_minus_xg >= 0 ? "+" : ""}${fmt(f.g_minus_xg)}</span></span>
    <span class="k">Std error</span><span class="v">± ${fmt(f.g_minus_xg_std_error)}</span>
    <span class="k">${term("finishing_ci")}</span><span class="v">${ci}</span>
  </div><div class="hint">${f.interpretation}</div>`;
}

function shotSelection(s) {
  return `<div class="kv">
    <span class="k">${term("shots")}</span><span class="v">${fmt(s.shots, 0)} · ${fmt(s.shots_per90, 2)}/90</span>
    <span class="k">${term("xG_per_shot")}</span><span class="v">${s.xG_per_shot == null ? "N/A" : fmt(s.xG_per_shot, 4)}</span>
    <span class="k">NP xG per shot</span><span class="v">${s.npxG_per_shot == null ? "N/A" : fmt(s.npxG_per_shot, 4)}</span>
  </div><div class="hint">${s.interpretation}</div>`;
}

function similarPlayers(s) {
  if (!s.matches.length) return `<div class="empty">No similar players in pool after filters (pool: ${s.pool_after_filters}).</div>`;
  return `<table><thead><tr><th>Player</th><th>Team</th><th class="num">Sim</th><th class="num">Min</th></tr></thead><tbody>
    ${s.matches.map((m) => `<tr><td>${m.player_name}</td><td>${m.team_title || "—"}</td><td class="num">${fmt(m.similarity, 3)}</td><td class="num">${fmt(m.minutes, 0)}</td></tr>`).join("")}
  </tbody></table>`;
}

const RADAR_LABEL_KEYS = { Goals: "goals", xG: "xG", "NP xG": "npxG", Assists: "assists", xA: "xA", Shots: "shots", "Key passes": "key_passes", xGChain: "xG_chain", xGBuildup: "xG_buildup" };
function radarLabelTitle(label) {
  const key = RADAR_LABEL_KEYS[label] || RADAR_LABEL_KEYS[String(label).replace("xGChain", "xGChain").trim()];
  const entry = GLOSSARY[key];
  return entry ? `<title>${entry.label}: ${entry.short}</title>` : "";
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
    labels += `<text x="${lx}" y="${ly}" fill="#8a98a8" font-size="10" text-anchor="middle" dominant-baseline="middle">${radarLabelTitle(profile[i].label)}${profile[i].label}</text>`;
  }
  let poly = ""; const vals = [];
  for (let i = 0; i < n; i++) { const pct = profile[i].percentile; const rr = r * pct / 100; const [x, y] = pt(i, rr); poly += `${x},${y} `; vals.push(`<text x="${x}" y="${y - 6}" fill="#4ea1ff" font-size="9" text-anchor="middle">${Math.round(pct)}</text>`); }
  el.innerHTML = `<svg class="radar-svg" viewBox="0 0 ${size} ${size}">${rings}${spokes}<polygon points="${poly}" fill="rgba(78,161,255,0.18)" stroke="#4ea1ff" stroke-width="2"/>${labels}${vals.join("")}</svg>`;
}

// ---------- TEAM ----------
$("teamGo").addEventListener("click", runTeam);
$("teamTimelineGo").addEventListener("click", runTeamTimeline);
$("teamName").addEventListener("keydown", (e) => { if (e.key === "Enter") runTeam(); });
$("compareA").addEventListener("keydown", (e) => { if (e.key === "Enter") runCompare(); });
$("compareB").addEventListener("keydown", (e) => { if (e.key === "Enter") runCompare(); });
$("matchId").addEventListener("keydown", (e) => { if (e.key === "Enter") runMatch(); });
async function runTeam() {
  const name = $("teamName").value.trim(); if (!name) return;
  const node = $("teamContent"); loading(node);
  try {
    const d = await api("/api/v1/analyze/team", {
      team_name: name, league_name: state.league, season: seasonOf("teamSeason"),
      start_date: dateOf("teamFrom"), end_date: dateOf("teamTo"),
    });
    renderTeam(node, d);
  } catch (e) { errored(node, e.message); }
}
async function runTeamTimeline() {
  const name = $("teamName").value.trim(); if (!name) return;
  const node = $("teamContent"); loading(node);
  try {
    const d = await api("/api/v1/analyze/team/timeline", {
      team_name: name, league_name: state.league, season_end: seasonOf("teamSeason"),
    });
    renderTeamTimeline(node, d);
  } catch (e) { errored(node, e.message); }
}

function renderTeamTimeline(node, d) {
  const months = d.seasons.flatMap((s) => s.months.map((m) => ({ ...m, season: s.season })));
  clear(node);
  node.innerHTML = `
    <div class="card"><h3>Monthly timeline · ${d.team_name} · ${d.seasons.map((s) => s.season).join(" & ")}</h3>
      <div class="controls">
        <div class="field"><label>Chart metric</label>
          <select id="timelineMetric">
            <option value="xG_per_game">${term("xG")} / game</option>
            <option value="xGA_per_game">${term("xGA")} / game</option>
            <option value="npxGD_per_game">${term("npxgd")} / game</option>
            <option value="points_per_game">Points / game</option>
            <option value="ppda">${term("ppda")}</option>
            <option value="oppda">${term("oppda")}</option>
            <option value="g_minus_xg">${term("g_minus_xg")} (month)</option>
            <option value="deep">${term("deep")} (month)</option>
          </select>
        </div>
      </div>
      <div id="timelineChart"></div>
      <div class="hint">Months are not equal (fixture counts differ) — per-game and aggregate metrics are marked as such.</div>
    </div>
    ${d.seasons.map((s) => `
    <div class="card" style="margin-top:16px"><h3>${s.season} · monthly table (${s.n_matches} matches)</h3>
      <table><thead><tr><th>Month</th><th class="num">M</th><th class="num">W/D/L</th><th class="num">Pts</th><th class="num">Pts/g</th><th class="num">${term("goals")}</th><th class="num">${term("xG")}</th><th class="num">${term("xGA")}</th><th class="num">${term("npxgd")}/g</th><th class="num">${term("g_minus_xg")}</th><th class="num">${term("xpts")}</th><th class="num">${term("ppda")}</th><th class="num">${term("deep")}</th></tr></thead><tbody>
        ${s.months.map((m) => `<tr><td>${m.month}</td><td class="num">${m.matches}</td><td class="num">${m.wins}-${m.draws}-${m.loses}</td>
          <td class="num">${m.points}</td><td class="num">${fmt(m.points_per_game)}</td>
          <td class="num">${m.goals}-${m.goals_against}</td><td class="num">${fmt(m.xG)}</td><td class="num">${fmt(m.xGA)}</td>
          <td class="num">${m.npxGD_per_game >= 0 ? "+" : ""}${fmt(m.npxGD_per_game)}</td>
          <td class="num">${m.g_minus_xg >= 0 ? "+" : ""}${fmt(m.g_minus_xg)}</td>
          <td class="num">${fmt(m.xpts)}</td><td class="num">${fmt(m.ppda)}</td><td class="num">${m.deep} / ${m.deep_allowed}</td></tr>`).join("")}
      </tbody></table></div>`).join("")}
    <div class="caveat"><strong>Interpretation.</strong> ${d.interpretation}<ul>${d.limitations.map((l) => `<li>${l}</li>`).join("")}</ul></div>
  `;
  const draw = () => drawTimelineChart("timelineChart", months, $("timelineMetric").value);
  $("timelineMetric").addEventListener("change", draw);
  draw();
}

function drawTimelineChart(container, months, metricKey) {
  const el = document.getElementById(container);
  if (!el) return;
  if (months.length < 2) { el.innerHTML = `<div class="empty">Not enough monthly data.</div>`; return; }
  const w = 1100, h = 260, pad = 40, x0 = pad, x1 = w - pad, y0 = 18, y1 = h - 30;
  const vals = months.map((m) => Number(m[metricKey]) || 0);
  const allMax = Math.max(...vals.map(Math.abs), 0.001);
  const mid = metricKey.includes("g_minus") || metricKey.includes("npxGD") ? 0 : null;
  const lo = mid === 0 ? -allMax : 0;
  const hi = allMax;
  const x = (i) => x0 + (i * (x1 - x0)) / Math.max(months.length - 1, 1);
  const y = (v) => y1 - ((v - lo) / (hi - lo)) * (y1 - y0);
  const color = (m) => (m.season === months[months.length - 1].season ? "#4ea1ff" : "#6b7c8f");
  const path = months.map((m, i) => `${i ? "L" : "M"}${x(i)},${y(Number(m[metricKey]) || 0)}`).join(" ");
  const dots = months.map((m, i) => `<circle cx="${x(i)}" cy="${y(Number(m[metricKey]) || 0)}" r="3.5" fill="${color(m)}"><title>${m.month} (${m.season}): ${fmt(m[metricKey], 2)}</title></circle>`).join("");
  const labels = months.map((m, i) => `<text x="${x(i)}" y="${y1 + 16}" fill="#8a98a8" font-size="9" text-anchor="middle" transform="rotate(-30 ${x(i)} ${y1 + 16})">${m.month.slice(5)}</text>`).join("");
  const zero = mid === 0 ? y(0) : null;
  const entry = GLOSSARY[metricKey] || {};
  el.innerHTML = `<svg class="timeline-svg" viewBox="0 0 ${w} ${h}">
    ${zero !== null ? `<line x1="${x0}" y1="${zero}" x2="${x1}" y2="${zero}" stroke="#243040" stroke-dasharray="3 4"/>` : ""}
    <path d="${path}" fill="none" stroke="#4ea1ff" stroke-width="2"/>${dots}
    ${labels}
    <text x="${x0}" y="${y0}" fill="#8a98a8" font-size="10">${entry.label || metricKey} · <tspan fill="#6b7c8f">grey = older season</tspan></text>
  </svg>`;
}

function renderTeam(node, d) {
  const s = d.style, pp = d.ppda_home_away, f = d.form_momentum;
  clear(node);
  node.innerHTML = `
    <div class="grid cols-2">
      <div class="card"><h3>Style profile · ${s.team} ${windowBadge(d)}</h3>${styleKv(s)}</div>
      <div class="card"><h3>Pressing home / away</h3>${ppdaKv(pp)}</div>
    </div>
    <div class="card" style="margin-top:16px"><h3>${term("form_momentum")} (rolling 5 xGD)</h3><div id="formChart"></div>${f.interpretation ? `<div class="hint">${f.interpretation}</div>` : ""}</div>
    ${(() => { drawFormChartDeferred("formChart", f); return ""; })()}
    ${d.situational_xg_share ? `<div class="card" style="margin-top:16px"><h3>${term("situations")} xG share</h3>${situationTable(d.situational_xg_share)}</div>` : ""}
    <div class="caveat"><strong>Limitations.</strong><ul>${d.limitations.map((l) => `<li>${l}</li>`).join("")}</ul></div>
  `;
  drawFormChart("formChart", f);
}

function styleKv(s) {
  return `<div class="kv">
    <span class="k">${term("xG")} / game</span><span class="v">${fmt(s.xG_per_game)}</span>
    <span class="k">xGA / game</span><span class="v">${fmt(s.xGA_per_game)}</span>
    <span class="k">xG diff / game</span><span class="v">${fmt(s.xG_diff_per_game)}</span>
    <span class="k">${term("npxgd")}</span><span class="v">${fmt(s.npxGD)}</span>
    <span class="k">${term("ppda")}</span><span class="v">${fmt(s.PPDA)} · ${term("oppda")} ${fmt(s.OPPDA)}</span>
    <span class="k">${term("deep")}</span><span class="v">${s.deep_completions} / allowed ${s.deep_completions_allowed}</span>
    <span class="k">${term("xpts")}</span><span class="v">${fmt(s.xPTS)}</span>
  </div><div class="hint">${s.interpretation}</div>`;
}
function ppdaKv(p) {
  return `<div class="kv">
    <span class="k">${term("ppda")} home</span><span class="v">${fmt(p.ppda_home)} (${p.matches_home} m)</span>
    <span class="k">${term("ppda")} away</span><span class="v">${fmt(p.ppda_away)} (${p.matches_away} m)</span>
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
    const d = await api("/api/v1/analyze/league", {
      league_name: state.league, season: seasonOf("leagueSeason"),
      start_date: dateOf("leagueFrom"), end_date: dateOf("leagueTo"),
    });
    renderLeague(node, d);
  } catch (e) { errored(node, e.message); }
}
function renderLeague(node, d) {
  const lying = d.is_lying;
  clear(node);
  node.innerHTML = `
    <div class="grid cols-2">
      <div class="card"><h3>${term("is_lying")} · biggest over/under</h3>
        <table><thead><tr><th>Team</th><th class="num">PTS</th><th class="num">${term("xpts")}</th><th class="num">Gap</th></tr></thead><tbody>
          ${[lying.biggest_overperformer, lying.biggest_underperformer].filter(Boolean).map((r) => `<tr><td>${r.team}</td><td class="num">${r.points}</td><td class="num">${fmt(r.xPTS)}</td><td class="num">${gap(r.xPTS_gap)}</td></tr>`).join("")}
        </tbody></table>
      </div>
      <div class="card"><h3>${term("variance")}</h3>${varianceBlock(d.variance)}</div>
    </div>
    <div class="card" style="margin-top:16px"><h3>Full "is-lying" table · ${LEAGUE_LABEL[state.league] || state.league} ${windowBadge(d)}</h3>${isLyingTable(lying)}</div>
    <div class="grid cols-2" style="margin-top:16px">
      <div class="card"><h3>${term("ppda")} ranking (low = intense press)</h3>${ppdaTable(d.ppda_ranking)}</div>
      <div class="card"><h3>${term("pace")}</h3>${paceBlock(d.pace)}</div>
    </div>
    <div class="caveat"><strong>Limitations.</strong><ul>${d.limitations.map((l) => `<li>${l}</li>`).join("")}</ul></div>
  `;
}
function gap(v) { return `<span class="badge ${v > 0 ? "good" : v < 0 ? "bad" : ""}">${v >= 0 ? "+" : ""}${fmt(v)}</span>`; }
function isLyingTable(lying) {
  return `<table><thead><tr><th>Team</th><th class="num">PTS</th><th class="num">${term("xpts")}</th><th class="num">Gap</th><th class="num">${term("g_minus_xg")}</th><th class="num">xGA−GA</th></tr></thead><tbody>
    ${lying.rows.map((r) => `<tr><td>${r.team}</td><td class="num">${r.points}</td><td class="num">${fmt(r.xPTS)}</td><td class="num">${gap(r.xPTS_gap)}</td><td class="num">${fmt(r.g_minus_xg)}</td><td class="num">${fmt(r.xga_minus_ga)}</td></tr>`).join("")}
  </tbody></table>`;
}
function varianceBlock(v) {
  const f = v.finishing_variance, d = v.defensive_variance;
  return `<div class="kv">
    <span class="k">Mean ${term("g_minus_xg")}</span><span class="v">${fmt(f.mean_g_minus_xg)}</span>
    <span class="k">Stdev ${term("g_minus_xg")}</span><span class="v">${fmt(f.stdev_g_minus_xg)}</span>
    <span class="k">Mean xGA−GA</span><span class="v">${fmt(d.mean_xga_minus_ga)}</span>
    <span class="k">Stdev xGA−GA</span><span class="v">${fmt(d.stdev_xga_minus_ga)}</span>
  </div><div class="hint">${v.interpretation}</div>`;
}
function ppdaTable(p) {
  return `<table><thead><tr><th>Team</th><th class="num">${term("ppda")}</th><th class="num">${term("oppda")}</th><th class="num">${term("deep")}</th><th class="num">DC allowed</th></tr></thead><tbody>
    ${p.ranking.map((r) => `<tr><td>${r.team}</td><td class="num">${fmt(r.PPDA)}</td><td class="num">${fmt(r.OPPDA)}</td><td class="num">${r.deep_completions}</td><td class="num">${r.deep_completions_allowed}</td></tr>`).join("")}
  </tbody></table><div class="hint">${p.interpretation}</div>`;
}
function paceBlock(p) {
  return `<div class="kv"><span class="k">${term("xG")} / game</span><span class="v">${fmt(p.xG_per_game)}</span><span class="k">xGA / game</span><span class="v">${fmt(p.xGA_per_game)}</span><span class="k">Matches</span><span class="v">${p.matches}</span></div><div class="hint">${p.interpretation}</div>`;
}

// ---------- MATCH ----------
$("matchGo").addEventListener("click", runMatch);
$("pickMatch").addEventListener("click", async (e) => {
  e.preventDefault();
  const link = $("pickMatch");
  link.textContent = "finding…";
  try {
    const res = await api("/api/v1/endpoints/league_results", { params: { league_name: state.league, season: seasonOf("leagueSeason") } });
    const matches = (res.data || []).filter((m) => m.id && m.datetime);
    if (!matches.length) throw new Error("No played matches in this league/season.");
    matches.sort((a, b) => String(b.datetime).localeCompare(String(a.datetime)));
    $("matchId").value = matches[0].id;
    link.textContent = `${matches[0].h.title || "?"} vs ${matches[0].a.title || "?"}`;
    runMatch();
  } catch (err) {
    link.textContent = "a recent result";
    errored($("matchContent"), err.message);
  }
});
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
    <div class="card"><h3>${n.narrative}</h3><div class="kv"><span class="k">Scoreline</span><span class="v">${n.scoreline.h} - ${n.scoreline.a}</span><span class="k">${term("xG")}</span><span class="v">${fmt(n.xG.h)} - ${fmt(n.xG.a)}</span><span class="k">${term("g_minus_xg")}</span><span class="v">${fmt(n.scoreline.h - n.xG.h)} / ${fmt(n.scoreline.a - n.xG.a)}</span></div></div>
    <div class="card" style="margin-top:16px"><h3>Shot map</h3><div id="shotmap"></div><div class="hint">Coord orientation: defending goal at left. Goal = filled; hover a circle for shot details.</div></div>
    <div class="card" style="margin-top:16px"><h3>${term("xG")} timeline (cumulative)</h3><div id="xgtl"></div></div>
    <div class="grid cols-2" style="margin-top:16px">
      <div class="card"><h3>${term("big_chance")} inventory (xG ≥ ${d.big_chance_inventory.xG_threshold})</h3>${bigChances(d.big_chance_inventory)}</div>
      <div class="card"><h3>${term("situations")} breakdown</h3>${situationBreakdown(d.situation_breakdown)}</div>
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
  const head = `<tr><th>${term("situations")}</th><th class="num">${term("shots")}</th><th class="num">${term("xG")}</th><th class="num">${term("goals")}</th></tr>`;
  const rows = (obj) => Object.entries(obj).sort((a, b) => b[1].xG - a[1].xG).map(([k, v]) => `<tr><td>${k}</td><td class="num">${v.shots}</td><td class="num">${fmt(v.xG)}</td><td class="num">${v.goals}</td></tr>`).join("");
  return `<table><thead><tr><th colspan=4 style="color:var(--accent)">Home</th></tr>${head}</thead><tbody>${rows(sb.home)}</tbody></table>` +
    `<table style="margin-top:10px"><thead><tr><th colspan=4 style="color:#41d6a3">Away</th></tr>${head}</thead><tbody>${rows(sb.away)}</tbody></table>`;
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
      start_date: dateOf("discoverFrom"), end_date: dateOf("discoverTo"),
    });
    renderDiscover(node, d);
  } catch (e) { errored(node, e.message); }
}
function renderDiscover(node, d) {
  clear(node);
  node.innerHTML = `<div class="card"><h3>Top ${d.limit} ${d.position_group || "all-position"} players ≥ ${d.minimum_minutes} min · ordered by ${d.order_by} ${windowBadge(d)}</h3>
    <table><thead><tr><th>Player</th><th>Team</th><th>Pos</th><th class="num">${term("minutes")}</th><th class="num">${term("npxG")}</th><th class="num">${term("xA")}</th><th class="num">${term("xG_chain")}</th><th class="num">${term("xG_buildup")}</th><th class="num">${term("goals")}</th><th class="num">${term("assists")}</th></tr></thead><tbody>
      ${d.players.map((p) => `<tr><td data-name="${p.name}">${p.name}</td><td>${p.team}</td><td>${p.position_group}</td><td class="num">${fmt(p.minutes, 0)}</td><td class="num">${fmt(p.npxG)}</td><td class="num">${fmt(p.xA)}</td><td class="num">${fmt(p.xGChain)}</td><td class="num">${fmt(p.xGBuildup)}</td><td class="num">${fmt(p.goals, 0)}</td><td class="num">${fmt(p.assists, 0)}</td></tr>`).join("")}
    </tbody></table>
    <div class="hint">Click a name to load that player in the Player tab${d.players[0] ? `. Suggested first: ${d.players[0].name}.` : ""}.</div>
  </div>`;
  node.querySelectorAll("td[data-name]").forEach((td) => td.addEventListener("click", () => {
    const name = td.getAttribute("data-name");
    $("playerName").value = name;
    document.querySelector('nav.tabs button[data-tab="player"]').click();
    runPlayer();
  }));
}

// ---------- COMPARE ----------
$("compareGo").addEventListener("click", runCompare);
$("compareMode").addEventListener("change", () => {
  const mode = $("compareMode").value;
  const players = mode === "players";
  $("compareLabelA").textContent = players ? "Player 1" : "Team 1";
  $("compareLabelB").textContent = players ? "Player 2" : "Team 2";
  $("compareA").placeholder = players ? "e.g. Mohamed Salah" : "e.g. Arsenal";
  $("compareB").placeholder = players ? "e.g. Bukayo Saka" : "e.g. Liverpool";
});

async function runCompare() {
  const a = $("compareA").value.trim(), b = $("compareB").value.trim();
  if (!a || !b) return;
  const node = $("compareContent"); loading(node);
  const mode = $("compareMode").value;
  const common = {
    league_name: state.league, season: seasonOf("compareSeason"),
    start_date: dateOf("compareFrom"), end_date: dateOf("compareTo"),
  };
  try {
    const d = await api(
      mode === "players" ? "/api/v1/compare/players" : "/api/v1/compare/teams",
      mode === "players" ? { player_1: a, player_2: b, ...common } : { team_1: a, team_2: b, ...common }
    );
    if (mode === "players") renderComparePlayers(node, d, a, b);
    else renderCompareTeams(node, d);
  } catch (e) { errored(node, e.message); }
}

function renderComparePlayers(node, d, nameA, nameB) {
  const pa = d.players[nameA], pb = d.players[nameB];
  clear(node);
  node.innerHTML = `
    <div class="grid cols-2">
      <div class="card"><h3>${term("percentile")} ${term("radar")} · shared pool (${d.pool_size} players) ${windowBadge(d)}</h3><div id="compareRadar"></div></div>
      <div class="card"><h3>${term("per90")} comparison</h3>${comparePer90(pa, pb)}</div>
    </div>
    <div class="grid cols-2" style="margin-top:16px">
      <div class="card"><h3>Involvement</h3>${compareInvolvement(pa, pb)}</div>
      <div class="card"><h3>${term("g_minus_xg")}</h3>${compareFinishing(pa, pb)}</div>
    </div>
    <div class="caveat"><strong>Limitations.</strong><ul>${d.limitations.map((l) => `<li>${l}</li>`).join("")}</ul></div>
  `;
  drawCompareRadar("compareRadar", d.radar_labels, pa.radar.profile, pb.radar.profile, nameA, nameB);
}

function comparePer90(pa, pb) {
  const rows = [["goals", "goals"], ["xG", "xG"], ["npxG", "npxG"], ["assists", "assists"], ["xA", "xA"], ["shots", "shots"], ["key_passes", "key_passes"]];
  return `<table><thead><tr><th></th><th class="num">${pa.player.name}</th><th class="num">${pb.player.name}</th></tr></thead><tbody>
    ${rows.map(([k, gk]) => `<tr><td>${term(gk)}</td><td class="num">${fmt(pa.per90_breakdown.per90[k], 3)}</td><td class="num">${fmt(pb.per90_breakdown.per90[k], 3)}</td></tr>`).join("")}
  </tbody></table>
  <div class="hint">${pa.player.name}: ${fmt(pa.per90_breakdown.minutes, 0)} min · ${pb.player.name}: ${fmt(pb.per90_breakdown.minutes, 0)} min</div>`;
}

function compareInvolvement(pa, pb) {
  const i1 = pa.involvement_profile, i2 = pb.involvement_profile;
  return `<div class="kv">
    <span class="k">${term("xG_chain")}</span><span class="v">${pa.player.name}: ${fmt(i1.xGChain)} · ${fmt(i1.xGChain_per90, 3)}/90</span>
    <span class="k"></span><span class="v">${pb.player.name}: ${fmt(i2.xGChain)} · ${fmt(i2.xGChain_per90, 3)}/90</span>
    <span class="k">${term("xG_buildup")}</span><span class="v">${pa.player.name}: ${fmt(i1.xGBuildup)} · ${fmt(i1.xGBuildup_per90, 3)}/90</span>
    <span class="k"></span><span class="v">${pb.player.name}: ${fmt(i2.xGBuildup)} · ${fmt(i2.xGBuildup_per90, 3)}/90</span>
  </div>`;
}

function compareFinishing(pa, pb) {
  const f1 = pa.finishing_overperformance, f2 = pb.finishing_overperformance;
  return `<div class="kv">
    <span class="k">${term("g_minus_xg")}</span><span class="v">${pa.player.name}: <span class="badge ${f1.g_minus_xg > 0 ? "good" : f1.g_minus_xg < 0 ? "bad" : ""}">${f1.g_minus_xg >= 0 ? "+" : ""}${fmt(f1.g_minus_xg)}</span></span>
    <span class="k"></span><span class="v">${pb.player.name}: <span class="badge ${f2.g_minus_xg > 0 ? "good" : f2.g_minus_xg < 0 ? "bad" : ""}">${f2.g_minus_xg >= 0 ? "+" : ""}${fmt(f2.g_minus_xg)}</span></span>
    <span class="k">± std error</span><span class="v">${fmt(f1.g_minus_xg_std_error)} vs ${fmt(f2.g_minus_xg_std_error)}</span>
  </div><div class="hint">${f1.interpretation}</div>`;
}

function drawCompareRadar(container, labels, profileA, profileB, nameA, nameB) {
  const el = document.getElementById(container);
  if (!el) return;
  const size = 360, cx = size / 2, cy = size / 2, r = 130;
  const n = labels.length;
  if (n < 3) { el.innerHTML = `<div class="empty">Need ≥3 metrics.</div>`; return; }
  const byLabelA = Object.fromEntries(profileA.map((p) => [p.label, p.percentile]));
  const byLabelB = Object.fromEntries(profileB.map((p) => [p.label, p.percentile]));
  const ang = (i) => -Math.PI / 2 + (i * 2 * Math.PI) / n;
  const pt = (i, rad) => [cx + rad * Math.cos(ang(i)), cy + rad * Math.sin(ang(i))];
  let rings = "";
  for (let g = 1; g <= 4; g++) {
    const rr = r * g / 4;
    let pts = ""; for (let i = 0; i < n; i++) { const [x, y] = pt(i, rr); pts += `${x},${y} `; }
    rings += `<polygon points="${pts}" fill="none" stroke="#243040" stroke-width="1"/>`;
  }
  let spokes = "", labelsSvg = "";
  for (let i = 0; i < n; i++) {
    const [x, y] = pt(i, r);
    spokes += `<line x1="${cx}" y1="${cy}" x2="${x}" y2="${y}" stroke="#243040" stroke-width="1"/>`;
    const [lx, ly] = pt(i, r + 20);
    labelsSvg += `<text x="${lx}" y="${ly}" fill="#8a98a8" font-size="10" text-anchor="middle" dominant-baseline="middle">${radarLabelTitle(labels[i])}${labels[i]}</text>`;
  }
  const poly = (byLabel, color, fill) => {
    let pts = "";
    for (let i = 0; i < n; i++) {
      const pct = Math.max(0, Math.min(100, byLabel[labels[i]] ?? 0));
      const [x, y] = pt(i, r * pct / 100);
      pts += `${x},${y} `;
    }
    return `<polygon points="${pts}" fill="${fill}" stroke="${color}" stroke-width="2"/>`;
  };
  el.innerHTML = `<svg class="radar-svg" viewBox="0 0 ${size} ${size}">${rings}${spokes}${poly(byLabelA, "#4ea1ff", "rgba(78,161,255,0.18)")}${poly(byLabelB, "#41d6a3", "rgba(65,214,163,0.14)")}${labelsSvg}</svg>
    <div class="hint"><span style="color:#4ea1ff">● ${nameA}</span> &nbsp; <span style="color:#41d6a3">● ${nameB}</span> &nbsp; percentile vs league pool</div>`;
}

function renderCompareTeams(node, d) {
  const t1 = d.team_1, t2 = d.team_2;
  clear(node);
  const meetingsRows = d.head_to_head.map((m) => m.played
    ? `<tr><td>${m.date}</td><td>${m.home}</td><td class="num">${m.home_goals}–${m.away_goals}</td><td>${m.away}</td><td class="num">xG ${fmt(m.home_xg)}–${fmt(m.away_xg)}</td></tr>`
    : `<tr><td>${m.date}</td><td>${m.home}</td><td class="num">upcoming</td><td>${m.away}</td><td class="num">—</td></tr>`).join("");
  node.innerHTML = `
    <div class="grid cols-2">
      <div class="card"><h3>${t1.name} · style</h3>${styleKv(t1.report.style)}</div>
      <div class="card"><h3>${t2.name} · style</h3>${styleKv(t2.report.style)}</div>
    </div>
    <div class="card" style="margin-top:16px"><h3>Head-to-head · ${LEAGUE_LABEL[d.league_name] || d.league_name} ${d.season}</h3>
      ${meetingsRows ? `<table><thead><tr><th>Date</th><th>Home</th><th class="num">Result</th><th>Away</th><th class="num">xG</th></tr></thead><tbody>${meetingsRows}</tbody></table>` : `<div class="empty">No meetings this season (or none in the selected date window).</div>`}
    </div>
    <div class="caveat"><strong>Limitations.</strong><ul>${t1.report.limitations.map((l) => `<li>${l}</li>`).join("")}</ul></div>
  `;
}

// ---------- PREDICT ----------
$("predGo").addEventListener("click", runPredict);
$("simGo").addEventListener("click", runSim);
$("calGo").addEventListener("click", runCal);
$("predHome").addEventListener("keydown", (e) => { if (e.key === "Enter") runPredict(); });
$("predAway").addEventListener("keydown", (e) => { if (e.key === "Enter") runPredict(); });

async function runPredict() {
  const home = $("predHome").value.trim(), away = $("predAway").value.trim();
  if (!home || !away) return;
  const node = $("predictContent"); loading(node);
  try {
    const d = await api("/api/v1/predict/match", {
      league_name: state.league, season: seasonOf("predSeason"),
      home, away, use_xg: $("predUseXg").checked,
    });
    renderForecast(node, d);
  } catch (e) { errored(node, e.message); }
}

function renderForecast(node, d) {
  const dc = d.model.dixon_coles, el = d.model.elo, ens = d.model.ensemble;
  const pi = d.model.pi_ratings, xg = d.model.xgboost;
  const adj = d.model.adjusted, adjLayers = d.model.adjustments, avail = d.model.availability;
  clear(node);
  node.innerHTML = `
    <div class="card">
      <h3>${d.match.home} vs ${d.match.away} · ${LEAGUE_LABEL[d.league_name] || d.league_name} ${d.season}</h3>
      ${probBar(adj)}
      <div class="prob-bar-labels"><span>home ${pct(adj.p_home)}</span><span>draw ${pct(adj.p_draw)}</span><span>away ${pct(adj.p_away)}</span></div>
      <div class="kv">
        <span class="k">${term("lambda")} (adjusted)</span><span class="v">${fmt(adj.lambda_home)} – ${fmt(adj.lambda_away)}</span>
        <span class="k">${term("most_likely_score")}</span><span class="v">${adj.most_likely_score[0]}–${adj.most_likely_score[1]} (${pct(dc.most_likely_score_prob)})</span>
        <span class="k">Fit</span><span class="v">${dc.n_matches} matches · ${term("home_advantage")} ${fmt(dc.home_advantage)} · ρ ${fmt(dc.rho)}</span>
      </div>
    </div>
    <div class="grid cols-3" style="margin-top:16px">
      <div class="card"><h3>${term("dixon_coles")} (base)</h3>${miniProbs(dc)}<div class="hint">fit on ${dc.fit_on}, no adjustments</div></div>
      <div class="card"><h3>${term("elo")}</h3>${miniProbs(el)}<div class="hint">results only · ${d.match.home} ${el.ratings[d.match.home] ?? "—"} vs ${d.match.away} ${el.ratings[d.match.away] ?? "—"}</div></div>
      <div class="card"><h3>${term("ensemble")}</h3>${ens.available ? miniProbs(ens) + `<div class="hint">weight ${ens.weight} on Dixon-Coles</div>` : `<div class="empty">needs ≥40 played matches</div>`}</div>
    </div>
    <div class="grid cols-2" style="margin-top:16px">
      <div class="card"><h3>${term("pi_ratings")}</h3>${miniProbs(pi)}<div class="hint">score-margin ratings, updated sequentially · ${pi.n_matches} matches</div></div>
      <div class="card"><h3>${term("xgboost")}</h3>${xg && xg.available
        ? miniProbs(xg) + `<div class="kv"><span class="k">λ</span><span class="v">${fmt(xg.lambda_home)} – ${fmt(xg.lambda_away)}</span><span class="k">Trained on</span><span class="v">${xg.n_train} matches${xg.pooled ? " · " + term("pooled_training") : ""}</span><span class="k">Kind</span><span class="v">${xg.kind || xg.variant}</span></div>`
        : `<div class="empty">${xg ? xg.reason || "unavailable" : "unavailable"}</div>`}</div>
    </div>
    ${xg && xg.available && xg.feature_importance && xg.feature_importance.length ? `
    <div class="card" style="margin-top:16px"><h3>${term("feature_importance")} · what the model leaned on</h3>${importanceBars(xg.feature_importance)}</div>` : ""}
    <div class="grid cols-2" style="margin-top:16px">
      <div class="card"><h3>${term("scoreline_matrix")} · home ↓ away →</h3>${scorelineMatrix(adj.scoreline_matrix || dc.scoreline_matrix)}</div>
      <div class="card"><h3>${term("over_under")} & ${term("btts")}</h3>${marketsGrid(adj.derived)}</div>
    </div>
    <div class="grid cols-2" style="margin-top:16px">
      <div class="card"><h3>${term("venue_factor")} & ${term("form_overlay")}</h3>${adjustmentKv(adjLayers)}</div>
      <div class="card"><h3>${term("availability")}</h3>${availabilityBlock(avail)}</div>
    </div>
    <div class="caveat"><strong>Interpretation.</strong> ${d.interpretation}<ul>${d.limitations.map((l) => `<li>${l}</li>`).join("")}</ul></div>
  `;
}

function importanceBars(entries) {
  const max = Math.max(...entries.map((e) => e.importance), 0.001);
  const labels = window.__FEATURE_LABELS__ || {};
  return entries.map((e) => `
    <div class="bar-row">
      <span class="bar-label" title="${e.feature}">${labels[e.feature] || e.feature}</span>
      <div class="bar-track"><div class="bar-fill" style="width:${Math.max(2, (e.importance / max) * 100)}%"></div></div>
      <span class="bar-val">${Math.round((e.importance / max) * 100)}</span>
    </div>`).join("");
}

function miniProbs(p) {
  return `<div class="prob-bar small">
    <div class="seg home" style="width:${p.p_home * 100}%">${Math.round(p.p_home * 100)}</div>
    <div class="seg draw" style="width:${p.p_draw * 100}%">${Math.round(p.p_draw * 100)}</div>
    <div class="seg away" style="width:${p.p_away * 100}%">${Math.round(p.p_away * 100)}</div>
  </div>`;
}

function marketsGrid(derived) {
  if (!derived) return `<div class="empty">No market probabilities.</div>`;
  const ou = derived.over_under || {};
  const rows = Object.entries(ou).map(([line, v]) => `
    <div class="kv"><span class="k">Over ${line} / Under ${line}</span>
    <span class="v">${pct(v.over)} / ${pct(v.under)}</span></div>`).join("");
  return `<div class="kv">${rows}
    <span class="k">${term("btts")}</span><span class="v">${pct(derived.both_teams_score)}</span>
    <span class="k">${term("clean_sheet")} (home)</span><span class="v">${pct(derived.clean_sheet_home)}</span>
    <span class="k">${term("clean_sheet")} (away)</span><span class="v">${pct(derived.clean_sheet_away)}</span>
  </div>`;
}

function adjustmentKv(adjLayers) {
  const venue = adjLayers.venue, form = adjLayers.form;
  const venueRow = (team) => team && team.available
    ? `<span class="k">${team.team} — ${term("venue_factor")}</span><span class="v">home ${fmt(team.home_xg_per_game)} xG/g vs away ${fmt(team.away_xg_per_game)} · factor <span class="badge ${team.factor >= 0 ? "good" : "bad"}">${team.factor >= 0 ? "+" : ""}${fmt(team.factor, 4)}</span></span>`
    : `<span class="k">${team ? team.team : "?"} — venue</span><span class="v">insufficient data</span>`;
  const formRow = (team) => team && team.available
    ? `<span class="k">${team.team} — ${term("form_overlay")}</span><span class="v">recent 5: ${fmt(team.recent_xg_per_game)} xG/g vs season ${fmt(team.season_xg_per_game)} · factor <span class="badge ${team.factor >= 0 ? "good" : "bad"}">${team.factor >= 0 ? "+" : ""}${fmt(team.factor, 4)}</span></span>`
    : `<span class="k">${team ? team.team : "?"} — form</span><span class="v">insufficient data</span>`;
  return `<div class="kv">${venueRow(venue.home)}${venueRow(venue.away)}${formRow(form.home)}${formRow(form.away)}</div>`;
}

function availabilityBlock(avail) {
  const card = (side, team) => {
    if (!team) return "";
    if (!team.available) return `<div class="kv"><span class="k">${side}</span><span class="v">${team.player}: not enough on/off-pitch data</span></div>`;
    const down = team.multiplier < 1;
    return `<div class="kv">
      <span class="k">${side} key creator</span><span class="v">${team.player} (xGChain ${fmt(team.xGChain)})</span>
      <span class="k">team xG/g with them</span><span class="v">${fmt(team.team_xG_per_game_with)} (${team.n_with} matches)</span>
      <span class="k">team xG/g without</span><span class="v">${fmt(team.team_xG_per_game_without)} (${team.n_without} matches) <span class="badge ${down ? "bad" : "good"}">×${fmt(team.multiplier, 3)}</span></span>
    </div>`;
  };
  const scenario = avail.scenario
    ? `<div class="kv"><span class="k">If all listed creators are absent</span>
        <span class="v">${pct(avail.scenario.p_home)} / ${pct(avail.scenario.p_draw)} / ${pct(avail.scenario.p_away)}</span></div>`
    : "";
  return `${card("home", avail.home)}${card("away", avail.away)}${scenario}
    <div class="hint">With/without is the team's own xG per game in matches the player started vs missed — a conditional, not a claim about lineups.</div>`;
}

function probBar(p) {
  const hp = Math.round(p.p_home * 1000) / 10, dp = Math.round(p.p_draw * 1000) / 10, ap = Math.round(p.p_away * 1000) / 10;
  return `<div class="prob-bar">
    <div class="seg home" style="width:${hp}%">${hp >= 9 ? hp + "%" : ""}</div>
    <div class="seg draw" style="width:${dp}%">${dp >= 9 ? dp + "%" : ""}</div>
    <div class="seg away" style="width:${ap}%">${ap >= 9 ? ap + "%" : ""}</div>
  </div>`;
}

function scorelineMatrix(matrix) {
  const flat = matrix.flat();
  const max = flat.reduce((a, b) => Math.max(a, b), 0) || 1;
  let cells = "";
  for (let h = 0; h <= 8; h++) {
    cells += `<tr><th class="lbl">${h}</th>`;
    for (let a = 0; a <= 8; a++) {
      const v = matrix[h][a];
      const t = v / max;
      const isMax = v === max && v > 0;
      const bg = t > 0.01 ? `rgba(78,161,255,${(0.05 + 0.55 * t).toFixed(3)})` : "transparent";
      cells += `<td class="num heat${isMax ? " max" : ""}" style="background:${bg}" title="${h}-${a}: ${pct(v)}">${v >= 0.02 ? Math.round(v * 100) : ""}</td>`;
    }
    cells += "</tr>";
  }
  return `<table class="heat"><tbody>${cells}</tbody></table><div class="hint">Rows = home goals, columns = away goals. Brightest cell = most likely scoreline.</div>`;
}

async function runSim() {
  const node = $("predictContent"); loading(node);
  try {
    const d = await api("/api/v1/predict/season", {
      league_name: state.league, season: seasonOf("simSeason"),
      n_sims: parseInt($("simCount").value, 10) || 2000, use_xg: $("predUseXg").checked,
    });
    renderSim(node, d);
  } catch (e) { errored(node, e.message); }
}

function renderSim(node, d) {
  const teams = Object.keys(d.expected_points);
  const nTeams = teams.length;
  const posColor = (i) => (i < 4 ? "var(--accent-2)" : i < 6 ? "var(--accent)" : i >= nTeams - 3 ? "var(--danger)" : "#3a4a5c");
  const finalGoals = d.expected_final_goals || {};
  clear(node);
  node.innerHTML = `
    <div class="card">
      <h3>Rest-of-season simulation · ${LEAGUE_LABEL[d.league_name] || d.league_name} ${d.season}</h3>
      <div class="kv">
        <span class="k">State</span><span class="v">${d.n_played} played · ${d.n_remaining} remaining fixtures · ${d.n_sims} ${term("monte_carlo")} sims</span>
        <span class="k">Model</span><span class="v">Dixon-Coles on ${d.model.fit_on} · ${term("home_advantage")} ${fmt(d.model.home_advantage)} · ρ ${fmt(d.model.rho)}</span>
      </div>
      <table style="margin-top:10px">
        <thead><tr><th>Team</th><th class="num">PTS</th><th class="num">${term("expected_points")}</th><th class="num">Δ</th><th class="num">${term("champion")}</th><th class="num">${term("p_top_4")}</th><th class="num">${term("p_relegation")}</th><th class="num">${term("season_end_goals")} F</th><th class="num">A</th><th>Final position distribution</th></tr></thead>
        <tbody>
          ${teams.map((t) => {
            const cur = d.current_points[t] ?? 0;
            const exp = d.expected_points[t];
            const delta = exp - cur;
            const p4 = d.p_top_4[t] ?? 0, pr = d.p_relegation[t] ?? 0, pc = d.p_champion[t] ?? 0;
            const dist = d.final_position_distribution[t] || [];
            const gf = finalGoals[t], ga = d.expected_goals_against[t] ?? 0;
            return `<tr><td>${t}</td><td class="num">${cur}</td><td class="num">${fmt(exp, 1)}</td>
              <td class="num">${delta >= 0 ? "+" : ""}${fmt(delta, 1)}</td>
              <td class="num">${pc >= 0.005 ? pct(pc) : "—"}</td>
              <td class="num">${pct(p4)}</td><td class="num">${pct(pr)}</td>
              <td class="num">${fmt(gf, 1)}</td><td class="num">${fmt(ga, 1)}</td>
              <td><div class="pos-row" title="position distribution">${dist.map((c, i) => `<span class="pos-seg" style="flex:${Math.max(c, 0.01)};background:${posColor(i)}" title="P${i + 1}: ${pct(c / d.n_sims)}"></span>`).join("")}</div></td></tr>`;
          }).join("")}
        </tbody>
      </table>
      <div class="hint">Bar = simulated final-position distribution (green = top 4, red = bottom 3). Δ = expected minus current points. F/A = projected season-end goals for/against.</div>
    </div>
    ${d.top_scorer_projection && d.top_scorer_projection.length ? `
    <div class="card" style="margin-top:16px"><h3>${term("top_scorer_projection")}</h3>
      <table><thead><tr><th>Player</th><th>Team</th><th class="num">${term("goals")} now</th><th class="num">${term("npxG")}</th><th class="num">${term("per90")}</th><th class="num">Games left</th><th class="num">Projected total</th></tr></thead><tbody>
        ${d.top_scorer_projection.map((p) => `<tr><td>${p.player}</td><td>${p.team}</td><td class="num">${p.goals_now}</td><td class="num">${fmt(p.npxG)}</td><td class="num">${fmt(p.npxG_per90, 3)}</td><td class="num">${p.games_remaining}</td><td class="num">${fmt(p.projected_season_end_goals, 1)}</td></tr>`).join("")}
      </tbody></table>
      <div class="hint">Assumes typical minutes continue and scales each player's npxG/90 by their team's remaining fixtures. Rough by design.</div>
    </div>` : ""}
    <div class="caveat"><ul>${d.limitations.map((l) => `<li>${l}</li>`).join("")}</ul></div>
  `;
}

async function runCal() {
  const node = $("predictContent"); loading(node);
  try {
    const d = await api("/api/v1/predict/calibration", {
      league_name: state.league, season: seasonOf("calSeason"),
      use_xg: $("predUseXg").checked,
    });
    renderCal(node, d);
  } catch (e) { errored(node, e.message); }
}

function renderCal(node, d) {
  const names = {
    dixon_coles: "Dixon-Coles (xG)", elo: "Elo (results)", pi_ratings: "pi-ratings",
    ensemble: "Ensemble (DC+Elo)", xgb_poisson: "XGBoost (goals)", xgb_xg: "XGBoost (xG)",
    xgb_outcome: "XGBoost (W/D/L)", understat: "Understat forecast", baseline: "Naive baseline",
  };
  const rows = Object.entries(d.models).map(([key, m]) => ({ key, name: names[key] || key, ...m }));
  const best = d.best_brier_model;
  clear(node);
  node.innerHTML = `
    <div class="card">
      <h3>Walk-forward calibration · ${LEAGUE_LABEL[d.league_name] || d.league_name} ${d.season}</h3>
      <div class="kv"><span class="k">Protocol</span><span class="v">${d.method} · fit on ${d.fit_on} · refit every ${d.step} matches · ${d.n_played} played matches${d.pooled_training_matches ? ` · ${d.pooled_training_matches} pooled training matches` : ""}</span></div>
      <table style="margin-top:10px">
        <thead><tr><th>Model</th><th class="num">Predictions</th><th class="num">${term("brier")}</th><th class="num">${term("log_loss")}</th><th class="num">${term("rps")}</th><th class="num">${term("accuracy")}</th></tr></thead>
        <tbody>
          ${rows.map((r) => `<tr class="${r.key === best ? "model-best" : ""}">
            <td>${r.name}${r.key === best ? ' <span class="badge good">best</span>' : ""}</td>
            <td class="num">${r.n}</td><td class="num">${fmt(r.brier, 4)}</td>
            <td class="num">${fmt(r.log_loss, 4)}</td><td class="num">${fmt(r.rps, 4)}</td>
            <td class="num">${pct(r.accuracy)}</td></tr>`).join("")}
        </tbody>
      </table>
      <div class="hint">Lower ${term("brier")} / ${term("log_loss")} / ${term("rps")} and higher accuracy are better. ${d.interpretation}</div>
    </div>
    ${d.feature_importance && d.feature_importance.length ? `
    <div class="card" style="margin-top:16px"><h3>${term("feature_importance")} · across all XGBoost models</h3>${importanceBars(d.feature_importance)}</div>` : ""}
    <div class="caveat"><ul>${d.limitations.map((l) => `<li>${l}</li>`).join("")}</ul></div>
  `;
}

function pct(v) { return `${(Math.round((v || 0) * 1000) / 10).toFixed(1)}%`; }

// ---------- helpers ----------
function fmt(v, d = 2) {
  if (v == null || v === "" || Number.isNaN(v)) return "—";
  const n = Number(v);
  if (Number.isInteger(n) && d === 0) return String(n);
  return n.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });
}

// pre-load
runLeague();

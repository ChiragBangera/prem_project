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
const PERSIST_IDS = ["playerName", "teamName", "leagueSeason",
  "matchSeason", "matchId",
  "predHome", "predAway", "predSeason", "simSeason", "calSeason",
  "compareA", "compareB", "compareSeason", "discoverMinutes", "discoverOrderBy"];
PERSIST_IDS.forEach((id) => {
  const el = document.getElementById(id);
  if (!el) return;
  const saved = localStorage.getItem(`prem_${id}`);
  if (saved !== null) el.value = saved;
  el.addEventListener("input", () => localStorage.setItem(`prem_${id}`, el.value));
  el.addEventListener("change", () => localStorage.setItem(`prem_${id}`, el.value));
});
const savedLeague = localStorage.getItem("prem_league");
if (savedLeague) {
  document.querySelectorAll("header.topbar .leagues button").forEach((b) => b.classList.toggle("active", b.dataset.league === savedLeague));
  state.league = savedLeague || state.league;
}
const initialHash = (window.location.hash || "").slice(1);
if (initialHash && document.querySelector(`nav.tabs button[data-tab="${initialHash}"]`)) {
  activateTab(initialHash, false);
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
  activateTab(btn.dataset.tab);
});
document.getElementById("leaguePicker").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-league]");
  if (!btn) return;
  state.league = btn.dataset.league;
  localStorage.setItem("prem_league", state.league);
  document.querySelectorAll("header.topbar .leagues button").forEach((b) => b.classList.toggle("active", b === btn));
});

function seasonOf(id) { return parseInt($(id).value, 10) || 2025; }
function seasonsOf(primaryId) {
  const primary = parseInt($(primaryId).value, 10) || 2025;
  const secondEl = $(primaryId + "2");
  if (secondEl && secondEl.value) {
    const seasons = [primary, parseInt(secondEl.value, 10)].filter((s) => s > 0);
    return [...new Set(seasons)].sort();
  }
  return null;
}
function dateOf(id) { const v = $(id).value; return v || null; }

// ---------- season dropdowns ----------
const SEASON_RANGE = { first: 2014, last: 2025 };

function selectedSeasons(hostId) {
  const host = document.getElementById(hostId);
  if (!host) return [];
  return JSON.parse(host.dataset.seasons || "[]");
}

function seasonOf(id) {
  const el = document.getElementById(id);
  if (el && el.classList.contains("season-multi")) {
    const seasons = selectedSeasons(id);
    return seasons[0] || 2025;
  }
  return parseInt(el.value, 10) || 2025;
}
function seasonsOf(id) {
  const el = document.getElementById(id);
  if (el && el.classList.contains("season-multi")) {
    const seasons = selectedSeasons(id);
    return seasons.length > 1 ? seasons : null;
  }
  return null;
}

function buildPositionMulti(hostId, maxSelections) {
  const host = document.getElementById(hostId);
  if (!host) return;
  const options = [
    ["GK", "GK · goalkeeper"], ["DC", "DC · centre-back"], ["DL", "DL · left-back"],
    ["DR", "DR · right-back"], ["DMC", "DMC · defensive midfield"], ["DML", "DML · left defensive mid"],
    ["DMR", "DMR · right defensive mid"],
    ["MC", "MC · centre midfield"], ["ML", "ML · left midfield"], ["MR", "MR · right midfield"],
    ["AMC", "AMC · attacking mid"], ["AML", "AML · left attacking mid"], ["AMR", "AMR · right attacking mid"],
    ["FWL", "FWL · left forward"], ["FWR", "FWR · right forward"], ["FW", "FW · forward"],
    ["Non", "Non · utility / no fixed role"],
  ];
  let selected = [];
  try {
    const saved = JSON.parse(localStorage.getItem(`prem_${hostId}`) || "[]");
    if (Array.isArray(saved)) selected = saved.filter((v) => options.some(([code]) => code === v));
  } catch (_) { /* ignore */ }
  host.dataset.values = JSON.stringify(selected);
  host.classList.add("season-multi");
  host.innerHTML = `
    <button type="button" class="season-btn" data-season-btn>${selected.length ? selected.join(", ") : "all positions"}</button>
    <div class="season-panel" data-season-panel>
      <div class="season-hint">Pick specific roles (empty = all). DMC/DML are midfield, not defence.</div>
      ${options.map(([code, label]) => `<label class="season-option"><input type="checkbox" value="${code}" ${selected.includes(code) ? "checked" : ""}/> ${label}</label>`).join("")}
    </div>`;
  const btn = host.querySelector("[data-season-btn]");
  const panel = host.querySelector("[data-season-panel]");
  btn.addEventListener("click", (e) => { e.stopPropagation(); panel.classList.toggle("open"); });
  document.addEventListener("click", (e) => { if (!host.contains(e.target)) panel.classList.remove("open"); });
  host.querySelectorAll("input[type=checkbox]").forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      let current = JSON.parse(host.dataset.values || "[]");
      const code = checkbox.value;
      if (checkbox.checked) {
        if (current.length >= maxSelections) { checkbox.checked = false; panel.querySelector(".season-hint").textContent = `Maximum ${maxSelections} — uncheck one first`; return; }
        current = [...current, code];
      } else {
        current = current.filter((v) => v !== code);
      }
      host.dataset.values = JSON.stringify(current);
      localStorage.setItem(`prem_${hostId}`, JSON.stringify(current));
      btn.textContent = current.length ? current.join(", ") : "all positions";
      panel.querySelector(".season-hint").textContent = "Pick specific roles (empty = all). DMC/DML are midfield, not defence.";
      runDiscover();
    });
  });
}

function selectedPositionValues(hostId) {
  const host = document.getElementById(hostId);
  if (!host) return null;
  const values = JSON.parse(host.dataset.values || "[]");
  return values.length ? values : null;
}

function buildSeasonMulti(hostId, maxSeasons) {
  const host = document.getElementById(hostId);
  if (!host) return;
  let seasons = [];
  try {
    const saved = JSON.parse(localStorage.getItem(`prem_${hostId}`) || "[]");
    if (Array.isArray(saved) && saved.length) seasons = saved.filter((s) => s >= SEASON_RANGE.first && s <= SEASON_RANGE.last);
  } catch (_) { /* ignore */ }
  if (!seasons.length) seasons = [2025];
  host.dataset.seasons = JSON.stringify(seasons);
  host.classList.add("season-multi");

  host.innerHTML = `
    <button type="button" class="season-btn" data-season-btn>${labelFor(seasons)}</button>
    <div class="season-panel" data-season-panel>
      <div class="season-hint">Pick 1–${maxSeasons} seasons (multi-season merges stats)</div>
      ${seasonOptions(seasons)}
    </div>`;

  const btn = host.querySelector("[data-season-btn]");
  const panel = host.querySelector("[data-season-panel]");
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    panel.classList.toggle("open");
  });
  document.addEventListener("click", (e) => {
    if (!host.contains(e.target)) panel.classList.remove("open");
  });
  host.querySelectorAll("input[type=checkbox]").forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      let current = selectedSeasons(hostId);
      const year = parseInt(checkbox.value, 10);
      if (checkbox.checked) {
        if (current.length >= maxSeasons) {
          checkbox.checked = false;
          panel.querySelector(".season-hint").textContent = `Maximum ${maxSeasons} seasons — uncheck one first`;
          return;
        }
        current = [...current, year].sort((a, b) => b - a);
      } else {
        current = current.filter((s) => s !== year);
      }
      if (!current.length) current = [2025];
      host.dataset.seasons = JSON.stringify(current);
      localStorage.setItem(`prem_${hostId}`, JSON.stringify(current));
      btn.textContent = labelFor(current);
      panel.querySelector(".season-hint").textContent = `Pick 1–${maxSeasons} seasons (multi-season merges stats)`;
    });
  });
}

function seasonOptions(selected) {
  let html = "";
  for (let s = SEASON_RANGE.last; s >= SEASON_RANGE.first; s--) {
    html += `<label class="season-option"><input type="checkbox" value="${s}" ${selected.includes(s) ? "checked" : ""}/> ${s}</label>`;
  }
  return html;
}

function labelFor(seasons) {
  if (!seasons.length) return "2025";
  if (seasons.length === 1) return `${seasons[0]}`;
  if (seasons.length <= 3) return seasons.join(", ");
  return `${seasons.slice(0, 3).join(", ")} +${seasons.length - 3}`;
}

function populateSeasonSelects() {
  document.querySelectorAll("select.season-select").forEach((select) => {
    const keepValue = select.value || localStorage.getItem(`prem_${select.id}`);
    select.innerHTML = "";
    for (let s = SEASON_RANGE.last; s >= SEASON_RANGE.first; s--) {
      const option = document.createElement("option");
      option.value = String(s);
      option.textContent = `${s}`;
      select.appendChild(option);
    }
    select.value = keepValue || "2025";
  });
  buildSeasonMulti("playerSeasons", 5);
  buildSeasonMulti("teamSeasons", 5);
  buildSeasonMulti("discoverSeasons", 5);
  buildPositionMulti("discoverPositions", 8);
}

function hoverDot(cx, cy, tip, color, r = 4) {
  return `<circle cx="${cx}" cy="${cy}" r="12" fill="transparent" data-tip="${tip}"/><circle cx="${cx}" cy="${cy}" r="${r}" fill="${color}"/>`;
}

// ---------- chart hover tooltip ----------
const chartTipEl = document.getElementById("chartTip");
document.addEventListener("mousemove", (e) => {
  const t = e.target.closest("[data-tip]");
  if (!t) {
    if (chartTipEl) chartTipEl.classList.remove("show");
    return;
  }
  if (!chartTipEl) return;
  chartTipEl.innerHTML = t.dataset.tip.replace(/\n/g, "<br>");
  chartTipEl.classList.add("show");
  const w = chartTipEl.offsetWidth, h = chartTipEl.offsetHeight;
  let x = e.clientX + 14, y = e.clientY + 14;
  if (x + w > window.innerWidth - 8) x = e.clientX - w - 12;
  if (y + h > window.innerHeight - 8) y = e.clientY - h - 12;
  chartTipEl.style.left = `${Math.max(8, x)}px`;
  chartTipEl.style.top = `${Math.max(8, y)}px`;
});

// ---------- hash routing (browser back/forward works across tabs) ----------
function activateTab(tab, push = true) {
  state.tab = tab;
  document.querySelectorAll("nav.tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  document.querySelectorAll("section.view").forEach((s) => s.classList.toggle("active", s.id === `view-${tab}`));
  if (push && window.location.hash !== `#${tab}`) window.history.pushState(null, "", `#${tab}`);
  if (tab === "info") renderInfo();
  if (tab === "match" && !state.roundsLoaded) loadRounds();
  if (tab === "statsbomb" && !state.sbLoaded) { state.sbLoaded = true; loadSbCompetitions(); }
}
window.addEventListener("popstate", () => {
  const tab = (window.location.hash || "#player").slice(1);
  if (document.querySelector(`nav.tabs button[data-tab="${tab}"]`)) activateTab(tab, false);
});
document.addEventListener("click", (e) => {
  if (e.target.closest("[data-back]")) { e.preventDefault(); window.history.back(); }
});

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
      player_name: name, league_name: state.league, season: seasonOf("playerSeasons"),
      seasons: seasonsOf("playerSeasons"),
      start_date: dateOf("playerFrom"), end_date: dateOf("playerTo"),
    });
    const seasonLabel = d.seasons && d.seasons.length > 1 ? ` · ${d.seasons.join("–")}` : "";
    $("playerResolved").textContent = `${d.player.name}${d.player.age != null ? ` (${d.player.age})` : ""} · ${d.player.team_title || "—"} · ${d.player.position || "—"}${seasonLabel}`;
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
      player_name: name, league_name: state.league, season_end: seasonOf("playerSeasons"),
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
  const w = 1100, h = 260, padL = 56, pad = 34, x0 = padL, x1 = w - pad, y0 = 18, y1 = h - 34;
  const vals = rows.map((r) => Number(r[metricKey]) || 0);
  const allMax = Math.max(...vals, 0.001);
  const x = (i) => x0 + (i * (x1 - x0)) / Math.max(rows.length - 1, 1);
  const y = (v) => y1 - (v / allMax) * (y1 - y0);
  const path = vals.map((v, i) => `${i ? "L" : "M"}${x(i)},${y(v)}`).join(" ");
  const dots = vals.map((v, i) => hoverDot(x(i), y(v), `${rows[i].season}: ${fmt(v, 3)}\n${rows[i].team || ""}\n${fmt(rows[i].minutes, 0)} min`, "#83a598")).join("");
  const labels = rows.map((r, i) => `<text x="${x(i)}" y="${y1 + 16}" fill="#a89984" font-size="10" text-anchor="middle">${r.season}</text>`).join("");
  const entry = GLOSSARY[metricKey] || {};
  el.innerHTML = `<svg class="timeline-svg" viewBox="0 0 ${w} ${h}">
    <line x1="${x0}" y1="${y1}" x2="${x1}" y2="${y1}" stroke="#504945"/>
    <line x1="${x0}" y1="${y1}" x2="${x0}" y2="${y0}" stroke="#504945"/>
    <path d="${path}" fill="none" stroke="#83a598" stroke-width="2"/>${dots}
    ${labels}
    <text x="${x0}" y="${y0}" fill="#a89984" font-size="10">${entry.label || metricKey} by season</text>
    <text x="${x0 + (x1 - x0) / 2}" y="${h - 6}" fill="#a89984" font-size="10" text-anchor="middle">season →</text>
    <text x="14" y="${y0 + (y1 - y0) / 2}" fill="#a89984" font-size="10" text-anchor="middle" transform="rotate(-90 14 ${y0 + (y1 - y0) / 2})">${entry.label || metricKey} ↑</text>
  </svg>`;
}

function renderPlayer(node, d) {
  const radar = d.radar.profile.filter((p) => p.percentile > 0 || p.raw > 0);
  clear(node);
  node.innerHTML = `
    ${state.fromDiscover ? `<div style="margin-bottom:10px"><a href="#" data-back class="back-link">← back to Discover</a></div>` : ""}
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
    ${d.pressing_output ? `<div class="card" style="margin-top:16px"><h3>${term("regain_xg")}</h3>${pressingBlock(d.pressing_output)}</div>` : ""}
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
  return `<table><thead><tr><th>Player</th><th>Team</th><th class="num">${term("age")}</th><th class="num">Sim</th><th class="num">Min</th></tr></thead><tbody>
    ${s.matches.map((m) => `<tr><td>${m.player_name}</td><td>${m.team_title || "—"}</td><td class="num">${m.age ?? "—"}</td><td class="num">${fmt(m.similarity, 3)}</td><td class="num">${fmt(m.minutes, 0)}</td></tr>`).join("")}
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
    rings += `<polygon points="${pts}" fill="none" stroke="#504945" stroke-width="1"/>`;
  }
  let spokes = "", labels = "";
  for (let i = 0; i < n; i++) {
    const [x, y] = pt(i, r);
    spokes += `<line x1="${cx}" y1="${cy}" x2="${x}" y2="${y}" stroke="#504945" stroke-width="1"/>`;
    const [lx, ly] = pt(i, r + 18);
    labels += `<text x="${lx}" y="${ly}" fill="#a89984" font-size="10" text-anchor="middle" dominant-baseline="middle">${radarLabelTitle(profile[i].label)}${profile[i].label}</text>`;
  }
  let poly = ""; const vals = [];
  for (let i = 0; i < n; i++) { const pct = profile[i].percentile; const rr = r * pct / 100; const [x, y] = pt(i, rr); poly += `${x},${y} `; vals.push(`<text x="${x}" y="${y - 6}" fill="#83a598" font-size="9" text-anchor="middle">${Math.round(pct)}</text>`); }
  el.innerHTML = `<svg class="radar-svg" viewBox="0 0 ${size} ${size}">${rings}${spokes}<polygon points="${poly}" fill="rgba(131,165,152,0.18)" stroke="#83a598" stroke-width="2"/>${labels}${vals.join("")}</svg>`;
}

function pressingBlock(p) {
  const actions = Object.entries(p.by_action || {}).map(([name, v]) =>
    `<span class="k">· ${name}</span><span class="v">${v.shots} shots · ${fmt(v.xG)} xG · ${v.goals} G</span>`).join("");
  return `<div class="kv">
    <span class="k">Shots after a regain</span><span class="v">${p.regain_shots} of ${p.total_shots}</span>
    <span class="k">xG after a regain</span><span class="v">${fmt(p.regain_xG)} (${pct(p.regain_xG_share)} of total xG)</span>
    <span class="k">Goals after a regain</span><span class="v">${p.regain_goals}</span>
    ${actions}
  </div><div class="hint">${p.interpretation}</div>`;
}

// ---------- TEAM ----------
$("teamGo").addEventListener("click", runTeam);
$("teamName").addEventListener("keydown", (e) => { if (e.key === "Enter") runTeam(); });
$("compareA").addEventListener("keydown", (e) => { if (e.key === "Enter") runCompare(); });
$("compareB").addEventListener("keydown", (e) => { if (e.key === "Enter") runCompare(); });
$("matchId").addEventListener("keydown", (e) => { if (e.key === "Enter") runMatch(); });
async function runTeam() {
  const name = $("teamName").value.trim(); if (!name) return;
  const node = $("teamContent"); loading(node);
  try {
    const d = await api("/api/v1/analyze/team", {
      team_name: name, league_name: state.league, season: seasonOf("teamSeasons"),
      seasons: seasonsOf("teamSeasons"),
      start_date: dateOf("teamFrom"), end_date: dateOf("teamTo"),
    });
    renderTeam(node, d);
  } catch (e) { errored(node, e.message); }
}
function renderTeam(node, d) {
  const s = d.style, pp = d.ppda_home_away, f = d.form_momentum;
  const seasonsLabel = d.seasons && d.seasons.length > 1 ? ` · ${d.seasons.join("–")}` : "";
  clear(node);
  node.innerHTML = `
    <div class="grid cols-2">
      <div class="card"><h3>Style profile · ${s.team}${seasonsLabel} ${windowBadge(d)}</h3>${styleKv(s)}</div>
      <div class="card"><h3>${term("venue_factor")} splits</h3>${homeAwayKv(d.home_away_splits)}</div>
    </div>
    ${seasonComparisonSection(d)}
    <div class="card" style="margin-top:16px"><h3>Rolling trends (5-match)</h3>
      <div class="controls"><div class="field"><label>Metric</label>
        <select id="trendMetric">
          <option value="npxGD">${term("npxgd")}</option>
          <option value="xG_for">${term("xG")} for</option>
          <option value="xG_against">${term("xGA")}</option>
          <option value="goals_for">${term("goals")} for</option>
          <option value="goals_against">Goals against</option>
          <option value="xPTS">${term("xpts")}</option>
          <option value="PPDA">${term("ppda")}</option>
        </select>
      </div></div>
      <div id="trendChart"></div></div>
    <div class="grid cols-2" style="margin-top:16px">
      <div class="card"><h3>${term("half_split")}</h3>${halfSplitTable(d.half_split)}</div>
      <div class="card"><h3>${term("luck_curve")}</h3><div id="luckChart"></div><div class="hint">${d.luck_curve.interpretation}</div></div>
    </div>
    ${d.strength_of_schedule && d.strength_of_schedule.available ? `<div class="grid cols-2" style="margin-top:16px">
      <div class="card"><h3>${term("strength_of_schedule")}</h3>${sosBlock(d.strength_of_schedule)}</div>
      <div class="card"><h3>Pressing home / away</h3>${ppdaKv(pp)}</div>
    </div>` : `<div class="card" style="margin-top:16px"><h3>Pressing home / away</h3>${ppdaKv(pp)}</div>`}
    ${d.situational_xg_share ? `<div class="card" style="margin-top:16px"><h3>${term("situations")} xG share</h3>${situationTable(d.situational_xg_share)}</div>` : ""}
    <div class="caveat"><strong>Limitations.</strong><ul>${d.limitations.map((l) => `<li>${l}</li>`).join("")}</ul></div>
  `;
  drawSeasonComparisonCharts(d);
  node.querySelectorAll(".season-toggle").forEach((chip) => chip.addEventListener("click", () => {
    const season = chip.dataset.season;
    if (state.hiddenSeasons.has(season)) state.hiddenSeasons.delete(season);
    else state.hiddenSeasons.add(season);
    chip.classList.toggle("off", state.hiddenSeasons.has(season));
    drawSeasonComparisonCharts(d);
  }));
  drawLuckChart("luckChart", d.luck_curve);
  const drawTrend = () => drawTrendChart("trendChart", d.metric_trends, $("trendMetric").value);
  $("trendMetric").addEventListener("change", drawTrend);
  drawTrend();
}

function homeAwayKv(ha) {
  if (!ha || !ha.home) return `<div class="empty">No venue splits.</div>`;
  const row = (label, side) => side ? `<span class="k">${label}</span><span class="v">${side.matches} m · ${fmt(side.points_per_game)} ppg · xG ${fmt(side.xG_per_game)} / xGA ${fmt(side.xGA_per_game)} · win ${pct(side.win_rate)}</span>` : "";
  return `<div class="kv">${row("Home", ha.home)}${row("Away", ha.away)}</div><div class="hint">${ha.interpretation || ""}</div>`;
}

function halfSplitTable(hs) {
  if (!hs || !hs.first_half) return `<div class="empty">Not enough matches for a half-season split.</div>`;
  const f = hs.first_half, snd = hs.second_half;
  const row = (label, a, b) => `<tr><td>${label}</td><td class="num">${a}</td><td class="num">${b}</td></tr>`;
  return `<table><thead><tr><th></th><th class="num">First half</th><th class="num">Second half</th></tr></thead><tbody>
    ${row("Matches", f.matches, snd.matches)}
    ${row("W / D / L", `${f.wins}/${f.draws}/${f.loses}`, `${snd.wins}/${snd.draws}/${snd.loses}`)}
    ${row("Points per game", fmt(f.points_per_game), fmt(snd.points_per_game))}
    ${row("xG per game", fmt(f.xG_per_game), fmt(snd.xG_per_game))}
    ${row("xGA per game", fmt(f.xGA_per_game), fmt(snd.xGA_per_game))}
    ${row("npxGD per game", fmt(f.npxGD_per_game), fmt(snd.npxGD_per_game))}
  </tbody></table><div class="hint">${hs.interpretation}</div>`;
}

function sosBlock(sos) {
  return `<div class="kv">
    <span class="k">vs stronger opponents</span><span class="v">${sos.vs_stronger_opponents.matches} m · ${fmt(sos.vs_stronger_opponents.points_per_game)} ppg · xGD ${fmt(sos.vs_stronger_opponents.xGD_per_game)}/g</span>
    <span class="k">vs weaker opponents</span><span class="v">${sos.vs_weaker_opponents.matches} m · ${fmt(sos.vs_weaker_opponents.points_per_game)} ppg · xGD ${fmt(sos.vs_weaker_opponents.xGD_per_game)}/g</span>
  </div><div class="hint">${sos.interpretation}</div>`;
}

function situationTable(s) {
  if (!s || !s.by_situation) return `<div class="empty">No situational data.</div>`;
  const rows = Object.entries(s.by_situation).map(([name, v]) =>
    `<tr><td>${name}</td><td class="num">${fmt(v.xG)}</td><td class="num">${Math.round((v.share || 0) * 100)}%</td></tr>`).join("");
  return `<table><thead><tr><th>${term("situations")}</th><th class="num">${term("xG")}</th><th class="num">share</th></tr></thead><tbody>${rows}</tbody></table>
    <div class="hint">Set-piece xG share: ${Math.round((s.set_piece_xG_share || 0) * 100)}% · ${s.interpretation}</div>`;
}

function seasonComparisonSection(d) {
  const trends = d.season_trends ? Object.entries(d.season_trends) : [];
  if (trends.length < 1) return "";
  const seasons = trends.map(([s]) => s);
  state.hiddenSeasons = state.hiddenSeasons || new Set();
  const chips = seasons.length > 1
    ? seasons.map((s, i) =>
        `<span class="compare-chip season-toggle${state.hiddenSeasons.has(s) ? " off" : ""}" data-season="${s}">
          <span class="dot" style="background:${RADAR_COLORS[i % RADAR_COLORS.length]}"></span>${s}</span>`).join("")
    : "";
  return `<div class="card" style="margin-top:16px"><h3>League position & points · by match week${seasons.length > 1 ? " · season vs season" : ""}</h3>
    <div class="compare-chips">${chips}${chips ? `<span class="chip-hint">click a season to show/hide</span>` : ""}</div>
    <div id="seasonPoints"></div>
    <div id="seasonRank" style="margin-top:14px"></div>
  </div>`;
}

function drawSeasonLines(container, trends, metric, opts) {
  const el = document.getElementById(container);
  if (!el) return;
  const entries = Object.entries(trends);
  const w = 1100, h = 240, padL = 52, pad = 30, x0 = padL, x1 = w - pad, y0 = 16, y1 = h - 42;
  const visible = entries.filter(([s]) => !state.hiddenSeasons.has(s));
  const maxMatchdays = Math.max(...entries.map(([, t]) => t.matchdays.length), 1);
  const x = (i) => x0 + (i * (x1 - x0)) / Math.max(maxMatchdays - 1, 1);
  let lines = "", dots = "", ticks = "";
  for (const [s, t] of visible) {
    const color = RADAR_COLORS[entries.findIndex(([ss]) => ss === s) % RADAR_COLORS.length];
    const vals = t.matchdays.map((m) => m[metric]);
    if (opts.invert) {
      const y = (v) => y0 + ((v - 1) / (opts.ymax - 1)) * (y1 - y0);
      const path = vals.map((v, i) => `${i ? "L" : "M"}${x(i)},${y(v)}`).join(" ");
      lines += `<path d="${path}" fill="none" stroke="${color}" stroke-width="2"/>`;
      dots += t.matchdays.map((m, i) => hoverDot(x(i), y(m[metric]), `${s} · match week ${i + 1}\n${m.date}\nposition ${m.rank} · points ${m.points}\nxPTS ${m.xpts}`, color, 3.5)).join("");
    } else {
      const ymax = Math.max(...entries.flatMap(([, tt]) => tt.matchdays.flatMap((m) => [m[metric], m.xpts])), 1);
      const y = (v) => y1 - (v / ymax) * (y1 - y0);
      const path = vals.map((v, i) => `${i ? "L" : "M"}${x(i)},${y(v)}`).join(" ");
      const xptsPath = t.matchdays.map((m, i) => `${i ? "L" : "M"}${x(i)},${y(m.xpts)}`).join(" ");
      lines += `<path d="${path}" fill="none" stroke="${color}" stroke-width="2"/>`;
      lines += `<path d="${xptsPath}" fill="none" stroke="${color}" stroke-width="1.5" stroke-dasharray="4 3" opacity="0.7"/>`;
      dots += t.matchdays.map((m, i) => hoverDot(x(i), y(m[metric]), `${s} · match week ${i + 1}\n${m.date}\npoints ${m.points} · xPTS ${m.xpts}\nposition ${m.rank}`, color, 3.5)).join("");
    }
  }
  const weekTicks = [];
  for (let wk = 1; wk <= maxMatchdays; wk += 5) {
    weekTicks.push(`<text x="${x(wk - 1)}" y="${y1 + 16}" fill="#a89984" font-size="9" text-anchor="middle">${wk}</text>`);
  }
  const axisLabel = opts.invert ? "league position (1 = top)" : "points ↑";
  el.innerHTML = `<svg class="timeline-svg" viewBox="0 0 ${w} ${h}">
    <line x1="${x0}" y1="${y1}" x2="${x1}" y2="${y1}" stroke="#504945"/>
    <line x1="${x0}" y1="${y1}" x2="${x0}" y2="${y0}" stroke="#504945"/>
    ${opts.invert ? rankTicks(x0, x1, y0, y1, opts.ymax) : ""}
    ${lines}${dots}
    ${opts.invert ? "" : `<text x="${x0}" y="${y0 - 2}" fill="#a89984" font-size="10">— points &nbsp; - - xPTS &nbsp; (solid vs dotted per season)</text>`}
    ${weekTicks.join("")}
    <text x="${x0 + (x1 - x0) / 2}" y="${h - 6}" fill="#a89984" font-size="10" text-anchor="middle">match week (team’s nth league match) →</text>
    <text x="12" y="${y0 + (y1 - y0) / 2}" fill="#a89984" font-size="10" text-anchor="middle" transform="rotate(-90 12 ${y0 + (y1 - y0) / 2})">${axisLabel}</text>
  </svg>`;
}

function rankTicks(x0, x1, y0, y1, nTeams) {
  let out = "";
  const ticks = [1, 5, 10, 15, 20].filter((t) => t <= nTeams);
  for (const t of ticks) {
    const y = y0 + ((t - 1) / (nTeams - 1)) * (y1 - y0);
    out += `<line x1="${x0}" y1="${y}" x2="${x1}" y2="${y}" stroke="#3c3836" stroke-dasharray="2 4"/>`;
    out += `<text x="${x0 - 4}" y="${y + 3}" fill="#a89984" font-size="9" text-anchor="end">${t}</text>`;
  }
  return out;
}

function drawSeasonComparisonCharts(d) {
  if (!d.season_trends) return;
  drawSeasonLines("seasonPoints", d.season_trends, "points", { invert: false });
  drawSeasonLines("seasonRank", d.season_trends, "rank", { invert: true, ymax: Math.max(...Object.values(d.season_trends).map((t) => t.n_teams), 2) });
}

function drawLuckChart(container, lc) {
  const el = document.getElementById(container);
  if (!el || !lc || !lc.points || lc.points.length < 2) { if (el) el.innerHTML = `<div class="empty">No luck-curve data.</div>`; return; }
  const w = 540, h = 220, padL = 46, pad = 30, x0 = padL, x1 = w - pad, y0 = 18, y1 = h - 34;
  const vals = lc.points.map((p) => p.cumulative_g_minus_xg);
  const lo = Math.min(...vals, 0), hi = Math.max(...vals, 0), span = Math.max(hi - lo, 0.5);
  const x = (i) => x0 + (i * (x1 - x0)) / Math.max(vals.length - 1, 1);
  const y = (v) => y1 - ((v - lo) / span) * (y1 - y0);
  const path = vals.map((v, i) => `${i ? "L" : "M"}${x(i)},${y(v)}`).join(" ");
  const dots = lc.points.map((p, i) => hoverDot(x(i), y(p.cumulative_g_minus_xg), `${p.date}\ncumulative G − xG: ${fmt(p.cumulative_g_minus_xg, 2)}`, lc.final >= 0 ? "#b8bb26" : "#fb4934", 3.5)).join("");
  const zero = y(0);
  const step = Math.max(1, Math.floor(vals.length / 12));
  const labels = lc.points.map((p, i) => (i % step === 0 ? `<text x="${x(i)}" y="${y1 + 14}" fill="#a89984" font-size="8.5" text-anchor="middle" transform="rotate(-30 ${x(i)} ${y1 + 14})">${p.date.slice(5)}</text>` : "")).join("");
  el.innerHTML = `<svg class="timeline-svg" viewBox="0 0 ${w} ${h}">
    <line x1="${x0}" y1="${y1}" x2="${x1}" y2="${y1}" stroke="#504945"/>
    <line x1="${x0}" y1="${y1}" x2="${x0}" y2="${y0}" stroke="#504945"/>
    <line x1="${x0}" y1="${zero}" x2="${x1}" y2="${zero}" stroke="#504945" stroke-dasharray="3 4"/>
    <path d="${path}" fill="none" stroke="${lc.final >= 0 ? "#b8bb26" : "#fb4934"}" stroke-width="2"/>${dots}
    ${labels}
    <text x="${x0}" y="${y0}" fill="#a89984" font-size="9">cumulative G − xG · hover for dates</text>
    <text x="${x0 + (x1 - x0) / 2}" y="${h - 6}" fill="#a89984" font-size="9" text-anchor="middle">match week →</text>
    <text x="12" y="${y0 + (y1 - y0) / 2}" fill="#a89984" font-size="9" text-anchor="middle" transform="rotate(-90 12 ${y0 + (y1 - y0) / 2})">G − xG ↑</text>
  </svg>`;
}

function drawTrendChart(container, mt, key) {
  const el = document.getElementById(container);
  if (!el || !mt || !mt.dates || mt.dates.length < 2) { if (el) el.innerHTML = `<div class="empty">No trend data.</div>`; return; }
  const w = 1100, h = 240, padL = 56, pad = 34, x0 = padL, x1 = w - pad, y0 = 18, y1 = h - 40;
  const vals = mt[key] || [];
  const allMax = Math.max(...vals.map(Math.abs), 0.001);
  const x = (i) => x0 + (i * (x1 - x0)) / Math.max(vals.length - 1, 1);
  const y = (v) => y1 - ((v + allMax) / (2 * allMax)) * (y1 - y0);
  const path = vals.map((v, i) => `${i ? "L" : "M"}${x(i)},${y(v)}`).join(" ");
  const dots = vals.map((v, i) => hoverDot(x(i), y(v), `${mt.dates[i]}\n${key}: ${fmt(v, 2)}`, "#83a598", 3.5)).join("");
  const zero = y(0);
  const step = Math.max(1, Math.floor(vals.length / 16));
  const labels = mt.dates.map((d, i) => (i % step === 0 ? `<text x="${x(i)}" y="${y1 + 14}" fill="#a89984" font-size="9" text-anchor="middle" transform="rotate(-30 ${x(i)} ${y1 + 14})">${d.slice(5)}</text>` : "")).join("");
  const entry = GLOSSARY[key] || {};
  el.innerHTML = `<svg class="timeline-svg" viewBox="0 0 ${w} ${h}">
    <line x1="${x0}" y1="${y1}" x2="${x1}" y2="${y1}" stroke="#504945"/>
    <line x1="${x0}" y1="${y1}" x2="${x0}" y2="${y0}" stroke="#504945"/>
    <line x1="${x0}" y1="${zero}" x2="${x1}" y2="${zero}" stroke="#504945" stroke-dasharray="3 4"/>
    <path d="${path}" fill="none" stroke="#83a598" stroke-width="2"/>${dots}
    ${labels}
    <text x="${x0}" y="${y0}" fill="#a89984" font-size="10">rolling ${mt.window}-match ${entry.label || key} · hover for dates</text>
    <text x="${x0 + (x1 - x0) / 2}" y="${h - 6}" fill="#a89984" font-size="10" text-anchor="middle">match week / date →</text>
    <text x="14" y="${y0 + (y1 - y0) / 2}" fill="#a89984" font-size="10" text-anchor="middle" transform="rotate(-90 14 ${y0 + (y1 - y0) / 2})">${entry.label || key} ↑</text>
  </svg>`;
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
$("loadRounds").addEventListener("click", loadRounds);
$("roundSelect").addEventListener("change", () => {
  const round = parseInt($("roundSelect").value, 10);
  const bucket = (state.rounds || []).find((r) => r.round === round);
  $("matchSelect").innerHTML = bucket
    ? bucket.matches.map((m) => `<option value="${m.match_id}">${m.date} · ${m.home} ${m.home_goals}–${m.away_goals} ${m.away}</option>`).join("")
    : `<option value="">no matches</option>`;
  $("matchSelect").dispatchEvent(new Event("change"));
});
$("matchSelect").addEventListener("change", () => {
  const id = $("matchSelect").value;
  if (!id) return;
  $("matchId").value = id;
  runMatch();
});
$("matchSeason").addEventListener("change", () => { state.roundsLoaded = false; loadRounds(); });

async function loadRounds() {
  const season = seasonOf("matchSeason");
  $("roundSelect").innerHTML = `<option value="">loading…</option>`;
  try {
    const d = await api("/api/v1/matches/rounds", { league_name: state.league, season });
    state.rounds = d.rounds || [];
    state.roundsLoaded = true;
    $("roundSelect").innerHTML = `<option value="">round…</option>` +
      state.rounds.map((r) => `<option value="${r.round}">Round ${r.round}</option>`).join("");
  } catch (e) {
    $("roundSelect").innerHTML = `<option value="">unavailable</option>`;
    $("matchSelect").innerHTML = `<option value="">${e.message}</option>`;
  }
}
if ($("pickMatch")) {
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
}
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
    `<table style="margin-top:10px"><thead><tr><th colspan=4 style="color:#b8bb26">Away</th></tr>${head}</thead><tbody>${rows(sb.away)}</tbody></table>`;
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
  const lines = `<line x1="0" y1="${h/2}" x2="${w}" y2="${h/2}" stroke="#3c3836"/><line x1="${w/2}" y1="0" x2="${w/2}" y2="${h}" stroke="#3c3836"/><circle cx="${w/2}" cy="${h/2}" r="60" fill="none" stroke="#3c3836"/><rect x="0" y="${h/2-60}" width="44" height="120" fill="none" stroke="#3c3836"/><rect x="${w-44}" y="${h/2-60}" width="44" height="120" fill="none" stroke="#3c3836"/>`;
  el.innerHTML = `<svg class="pitch-svg" viewBox="0 0 ${w} ${h}"><rect x="0" y="0" width="${w}" height="${h}" fill="#1d2021"/>${lines}<g>${circles(away, "#b8bb26")}</g><g>${circles(home, "#83a598")}</g></svg><div class="hint"><span style="color:#83a598">● home</span> &nbsp; <span style="color:#b8bb26">● away</span> &nbsp; radius scales with xG; filled = goal &nbsp; hover for shot details</div>`;
}
function drawXgTimeline(container, tl) {
  const el = document.getElementById(container); if (!el) return;
  const w = 1100, h = 240, padL = 56, pad = 30, x0 = padL, x1 = w - pad, y0 = 24, y1 = h - 40;
  const home = tl.home || [], away = tl.away || [];
  const allMax = Math.max(...home.map((p) => p.cumulative_xG), ...away.map((p) => p.cumulative_xG), 0.5);
  const minuteMax = Math.max(...home.map((p) => p.minute), ...away.map((p) => p.minute), 90);
  const x = (m) => x0 + (m / minuteMax) * (x1 - x0);
  const y = (v) => y1 - (v / allMax) * (y1 - y0);
  const path = (pts, color) => pts.length ? `<path d="${pts.map((p, i) => `${i ? "L" : "M"}${x(p.minute)},${y(p.cumulative_xG)}`).join(" ")}" fill="none" stroke="${color}" stroke-width="2"/>` : "";
  const dots = (pts, color) => pts.map((p) => hoverDot(x(p.minute), y(p.cumulative_xG), `minute ${p.minute}\ncumulative xG: ${fmt(p.cumulative_xG, 3)}`, color, 3.5)).join("");
  el.innerHTML = `<svg class="timeline-svg" viewBox="0 0 ${w} ${h}">
    <line x1="${x0}" y1="${y1}" x2="${x1}" y2="${y1}" stroke="#504945"/>
    <line x1="${x0}" y1="${y1}" x2="${x0}" y2="${y0}" stroke="#504945"/>
    ${path(home, "#83a598")}${path(away, "#b8bb26")}
    ${dots(home, "#83a598")}${dots(away, "#b8bb26")}
    <text x="${x0}" y="${y0}" fill="#a89984" font-size="10"><tspan fill="#83a598">— home</tspan>  <tspan fill="#b8bb26">— away</tspan>  · hover shots for minute & xG</text>
    <text x="${x0 + (x1 - x0) / 2}" y="${h - 6}" fill="#a89984" font-size="10" text-anchor="middle">minute →</text>
    <text x="14" y="${y0 + (y1 - y0) / 2}" fill="#a89984" font-size="10" text-anchor="middle" transform="rotate(-90 14 ${y0 + (y1 - y0) / 2})">cumulative xG ↑</text>
  </svg>`;
}

// ---------- player basket (discover → compare) ----------
const RADAR_COLORS = ["#83a598", "#b8bb26", "#fabd2f", "#fb4934", "#d3869b",
  "#8ec07c", "#fe8019", "#d79921", "#e78a4e", "#7c9a8e", "#c49a6c", "#689d6a"];

function loadBasket() {
  try {
    state.basket = JSON.parse(localStorage.getItem("prem_basket") || "[]");
  } catch (_) { state.basket = []; }
}
function saveBasket() {
  localStorage.setItem("prem_basket", JSON.stringify(state.basket));
}
function toggleBasket(name, team, age) {
  const existing = state.basket.findIndex((p) => p.name === name);
  if (existing >= 0) state.basket.splice(existing, 1);
  else state.basket.push({ name, team, age });
  saveBasket();
  updateBasketUI();
}
function updateBasketUI() {
  const bar = document.getElementById("discoverBasketBar");
  if (!bar) return;
  bar.style.display = state.basket.length ? "flex" : "none";
  bar.querySelector(".basket-count").textContent = `${state.basket.length} selected`;
  renderCompareBasket();
}
function renderCompareBasket() {
  const host = document.getElementById("compareBasket");
  if (!host) return;
  host.innerHTML = state.basket.length
    ? `<div class="card basket-card">
        <h3>Basket · from Discover</h3>
        <div class="basket-chips">${state.basket.map((p) =>
          `<span class="basket-chip">${p.name}${p.age ? ` (${p.age})` : ""} <span class="basket-x" data-remove="${p.name}">×</span></span>`).join("")}</div>
        <div class="controls" style="margin-top:8px">
          <button class="primary" id="basketCompareGo">Compare ${state.basket.length} players</button>
          <button class="ghost" id="basketClear">Clear</button>
        </div>
      </div>`
    : "";
  host.querySelectorAll("[data-remove]").forEach((x) => x.addEventListener("click", () => {
    state.basket = state.basket.filter((p) => p.name !== x.dataset.remove);
    saveBasket();
    updateBasketUI();
  }));
  const go = document.getElementById("basketCompareGo");
  if (go) go.addEventListener("click", () => { state.pendingBasket = true; runCompare(); });
  const clear = document.getElementById("basketClear");
  if (clear) clear.addEventListener("click", () => { state.basket = []; saveBasket(); updateBasketUI(); });
}
loadBasket();

// ---------- DISCOVER ----------
$("discoverGo").addEventListener("click", runDiscover);
$("discoverOrderBy").addEventListener("change", runDiscover);
$("discoverLimit").addEventListener("change", runDiscover);
let discoverDebounce;
$("discoverMinutes").addEventListener("input", () => { clearTimeout(discoverDebounce); discoverDebounce = setTimeout(runDiscover, 700); });
$("discoverMinAge").addEventListener("input", () => { clearTimeout(discoverDebounce); discoverDebounce = setTimeout(runDiscover, 700); });
$("discoverMaxAge").addEventListener("input", () => { clearTimeout(discoverDebounce); discoverDebounce = setTimeout(runDiscover, 700); });
document.getElementById("discoverSeasons").addEventListener("change", runDiscover);
async function runDiscover() {
  const node = $("discoverContent"); loading(node);
  const scrollY = window.scrollY;
  try {
    const d = await api("/api/v1/discover/players", {
      league_name: state.league,
      season: seasonOf("discoverSeasons"),
      seasons: seasonsOf("discoverSeasons"),
      positions: selectedPositionValues("discoverPositions"),
      minimum_minutes: parseFloat($("discoverMinutes").value) || 900,
      order_by: $("discoverOrderBy").value,
      limit: parseInt($("discoverLimit").value, 10) || 20,
      start_date: dateOf("discoverFrom"), end_date: dateOf("discoverTo"),
      min_age: parseInt($("discoverMinAge").value, 10) || null,
      max_age: parseInt($("discoverMaxAge").value, 10) || null,
    });
    renderDiscover(node, d);
    if (scrollY > 0) window.scrollTo(0, scrollY);
  } catch (e) { errored(node, e.message); }
}
function renderDiscover(node, d) {
  clear(node);
  const seasonsLabel = d.seasons && d.seasons.length > 1 ? ` · ${d.seasons.join("–")}` : "";
  node.innerHTML = `<div class="card"><h3>Top ${d.limit} ${d.position_group || "all-position"} players ≥ ${d.minimum_minutes} min · ordered by ${d.order_by}${seasonsLabel} ${windowBadge(d)}</h3>
    <div class="basket-bar" id="discoverBasketBar" style="display:${state.basket.length ? "flex" : "none"}">
      <span class="basket-count">${state.basket.length} selected</span>
      <button class="primary" id="discoverToCompare">Compare →</button>
      <button class="ghost" id="discoverBasketClear">Clear</button>
    </div>
    <table><thead><tr><th>✓</th><th>Player</th><th>Team</th><th>Pos</th><th class="num">${term("age")}</th><th class="num">${term("team_press")}</th><th class="num">${term("minutes")}</th><th class="num">${term("npxG")}</th><th class="num">/90</th><th class="num">${term("xA")}</th><th class="num">/90</th><th class="num">${term("goal_involvement")}/90</th><th class="num">${term("xG_per_shot")}</th><th class="num">${term("g_minus_xg")}</th><th class="num">${term("goals")}</th><th class="num">${term("assists")}</th><th class="num">${term("cards")}</th></tr></thead><tbody>
      ${d.players.map((p) => {
        const checked = state.basket.some((b) => b.name === p.name) ? "checked" : "";
        return `<tr><td><input type="checkbox" class="basket-check" data-name="${p.name}" data-team="${p.team}" data-age="${p.age ?? ""}" ${checked}/></td>
        <td data-name="${p.name}">${p.name}</td><td>${p.team}</td><td title="${p.position}">${p.favorite_position || p.position_group || p.position || "—"}</td><td class="num">${p.age ?? "—"}</td><td class="num">${fmt(p.team_ppda)}</td><td class="num">${fmt(p.minutes, 0)}</td><td class="num">${fmt(p.npxG)}</td><td class="num">${fmt(p.npxG_per90, 3)}</td><td class="num">${fmt(p.xA)}</td><td class="num">${fmt(p.xA_per90, 3)}</td><td class="num">${fmt(p.goal_involvement_per90, 3)}</td><td class="num">${fmt(p.xG_per_shot, 3)}</td><td class="num">${p.g_minus_xg >= 0 ? "+" : ""}${fmt(p.g_minus_xg)}</td><td class="num">${fmt(p.goals, 0)}</td><td class="num">${fmt(p.assists, 0)}</td><td class="num">${fmt(p.yellow_cards, 0)}y / ${fmt(p.red_cards, 0)}r</td></tr>`;
      }).join("")}
    </tbody></table>
    <div class="hint">Tick players to build a basket, then Compare → to compare all of them at once. Age from Wikidata; ${term("team_press")} is the team's season PPDA.</div>
    <div class="caveat"><ul>${(d.limitations || []).map((l) => `<li>${l}</li>`).join("")}</ul></div>
  </div>`;
  node.querySelectorAll("td[data-name]").forEach((td) => td.addEventListener("click", () => {
    const name = td.getAttribute("data-name");
    $("playerName").value = name;
    localStorage.setItem("prem_playerName", name);
    state.fromDiscover = true;
    activateTab("player");
    runPlayer();
  }));
  node.querySelectorAll(".basket-check").forEach((checkbox) => checkbox.addEventListener("change", () => {
    toggleBasket(checkbox.dataset.name, checkbox.dataset.team, checkbox.dataset.age ? parseInt(checkbox.dataset.age, 10) : null);
  }));
  const toCompare = document.getElementById("discoverToCompare");
  if (toCompare) toCompare.addEventListener("click", () => {
    state.pendingBasket = true;
    activateTab("compare");
    runCompare();
  });
  const clearBasket = document.getElementById("discoverBasketClear");
  if (clearBasket) clearBasket.addEventListener("click", () => {
    state.basket = [];
    saveBasket();
    updateBasketUI();
    node.querySelectorAll(".basket-check").forEach((c) => { c.checked = false; });
  });
}

// ---------- COMPARE ----------
$("compareGo").addEventListener("click", runCompare);
$("compareHighlight").addEventListener("change", () => {
  localStorage.setItem("prem_compareHighlight", $("compareHighlight").checked ? "1" : "0");
  applyHighlightState();
});
function applyHighlightState() {
  const on = $("compareHighlight").checked;
  $("compareContent").classList.toggle("hl-off", !on);
}
(function initHighlight() {
  const saved = localStorage.getItem("prem_compareHighlight");
  if (saved === "0") $("compareHighlight").checked = false;
})();

function playerColors(names) {
  const colors = {};
  names.forEach((n, i) => { colors[n] = RADAR_COLORS[i % RADAR_COLORS.length]; });
  return colors;
}

function compareHeaderChips(d, names) {
  const colors = playerColors(names);
  return `<div class="compare-chips">${names.map((n) => {
    const p = d.players[n].player;
    return `<span class="compare-chip"><span class="dot" style="background:${colors[n]}"></span>${n}${p.age != null ? ` (${p.age})` : ""}<span class="chip-team">${p.team_title || ""} · ${p.favorite_position || p.position_group || ""}</span></span>`;
  }).join("")}</div>`;
}

const PROFILE_LABELS = {
  OpenPlay: "Open play", FromCorner: "From corner", SetPiece: "Set piece",
  DirectFreekick: "Direct free kick", CounterAttack: "Counter attack", Penalty: "Penalty",
  shotPenaltyArea: "Penalty area", shotSixYardBox: "Six-yard box", shotOboxTotal: "Outside box",
  LeftFoot: "Left foot", RightFoot: "Right foot", Head: "Header", OtherBodyPart: "Other body part",
};
function prettyProfileLabel(name) { return PROFILE_LABELS[name] || name; }

function groupedBars(rows, names, colors) {
  return `<table class="gbars"><thead><tr><th></th>${names.map((n) =>
    `<th class="num"><span class="dot" style="background:${colors[n]}"></span>${n}</th>`).join("")}</tr></thead><tbody>
    ${rows.map((row) => {
      const values = row.values;
      const max = Math.max(...values.map((v) => v.value), 0.0001);
      return `<tr><td>${row.label}</td>${values.map((v) => {
        const best = v.value === max && max > 0;
        return `<td class="num${best ? " winner" : ""}"><div class="gbar${best ? " winner" : " dim"}">
          <div class="bar-track"><div class="bar-fill" style="width:${Math.max(2, (v.value / max) * 100)}%;background:${colors[v.name]}"></div></div>
          <span class="bar-val${best ? " best-val" : ""}">${v.text}</span></div></td>`;
      }).join("")}</tr>`;
    }).join("")}
  </tbody></table>`;
}

function profileSection(d, names, title, termKey, kind) {
  const colors = playerColors(names);
  const withProfile = names.filter((n) => {
    const cp = d.players[n].comparison_profile;
    return cp && cp.shot_profile && cp.shot_profile[kind] && cp.shot_profile[kind].length;
  });
  if (!withProfile.length) return "";
  const categories = [...new Set(withProfile.flatMap((n) => d.players[n].comparison_profile.shot_profile[kind].map((s) => s.name)))];
  const rows = categories.map((cat) => ({
    label: prettyProfileLabel(cat),
    values: names.map((n) => {
      const cp = d.players[n].comparison_profile;
      const entry = cp && cp.shot_profile ? cp.shot_profile[kind].find((s) => s.name === cat) : null;
      return {
        name: n,
        value: entry ? entry.xG_share : 0,
        text: entry ? `${Math.round(entry.xG_share * 100)}% · ${entry.shots} sh` : "—",
      };
    }),
  }));
  return `<div class="card" style="margin-top:16px"><h3>${term(termKey)} · xG share</h3>${groupedBars(rows, names, colors)}
    <div class="hint">Bar = share of the player's own xG; value = shots in that category.</div></div>`;
}

function roleSplitSection(d, names) {
  const colors = playerColors(names);
  const withProfile = names.filter((n) => {
    const cp = d.players[n].comparison_profile;
    return cp && cp.role_split && cp.role_split.length;
  });
  if (!withProfile.length) return "";
  const roles = [...new Set(withProfile.flatMap((n) => d.players[n].comparison_profile.role_split.map((r) => r.role)))];
  const rows = roles.map((role) => ({
    label: role,
    values: names.map((n) => {
      const cp = d.players[n].comparison_profile;
      const entry = cp && cp.role_split ? cp.role_split.find((r) => r.role === role) : null;
      const total = cp && cp.role_split ? cp.role_split.reduce((a, r) => a + r.minutes, 0) || 1 : 1;
      return {
        name: n,
        value: entry ? entry.minutes / total : 0,
        text: entry ? `${fmt(entry.minutes, 0)} min · ${fmt(entry.games, 0)} g` : "—",
      };
    }),
  }));
  return `<div class="card" style="margin-top:16px"><h3>${term("starter_sub")} · minutes share</h3>${groupedBars(rows, names, colors)}</div>`;
}

function minuteBucketSection(d, names) {
  const colors = playerColors(names);
  const withData = names.filter((n) => {
    const cp = d.players[n].comparison_profile;
    return cp && cp.minute_buckets && cp.minute_buckets.length;
  });
  if (!withData.length) return "";
  const buckets = d.players[withData[0]].comparison_profile.minute_buckets.map((b) => b.label);
  const rows = buckets.map((label) => ({
    label,
    values: names.map((n) => {
      const cp = d.players[n].comparison_profile;
      const entry = cp && cp.minute_buckets ? cp.minute_buckets.find((b) => b.label === label) : null;
      return {
        name: n,
        value: entry ? entry.xG : 0,
        text: entry ? `${fmt(entry.xG)} xG · ${entry.shots} sh${entry.goals ? ` · ${entry.goals} G` : ""}` : "—",
      };
    }),
  }));
  return `<div class="card" style="margin-top:16px"><h3>When they shoot · xG by 15-minute bucket</h3>${groupedBars(rows, names, colors)}</div>`;
}

function homeAwaySection(d, names) {
  const colors = playerColors(names);
  const withData = names.filter((n) => {
    const cp = d.players[n].comparison_profile;
    return cp && cp.home_away && (cp.home_away.home.shots + cp.home_away.away.shots) > 0;
  });
  if (!withData.length) return "";
  const rows = ["home", "away"].map((venue) => ({
    label: venue,
    values: names.map((n) => {
      const cp = d.players[n].comparison_profile;
      if (!cp || !cp.home_away) return { name: n, value: 0, text: "—" };
      const h = cp.home_away.home, a = cp.home_away.away;
      const total = h.xG + a.xG || 1;
      const entry = venue === "home" ? h : a;
      return {
        name: n,
        value: entry.xG / total,
        text: `${fmt(entry.xG)} xG · ${entry.shots} sh · ${entry.goals} G`,
      };
    }),
  }));
  return `<div class="card" style="margin-top:16px"><h3>Home vs away · xG split</h3>${groupedBars(rows, names, colors)}</div>`;
}
$("compareMode").addEventListener("change", () => {
  const mode = $("compareMode").value;
  const players = mode === "players";
  $("compareLabelA").textContent = players ? "Player 1" : "Team 1";
  $("compareLabelB").textContent = players ? "Player 2" : "Team 2";
  $("compareA").placeholder = players ? "e.g. Mohamed Salah" : "e.g. Arsenal";
  $("compareB").placeholder = players ? "e.g. Bukayo Saka" : "e.g. Liverpool";
});

async function runCompare() {
  const node = $("compareContent");
  const mode = $("compareMode").value;
  const common = {
    league_name: state.league, season: seasonOf("compareSeason"),
    start_date: dateOf("compareFrom"), end_date: dateOf("compareTo"),
  };
  if (mode === "players" && (state.pendingBasket || (!state.pendingBasket && state.basket.length >= 2 && !$("compareA").value.trim()))) {
    const names = state.basket.map((p) => p.name);
    state.pendingBasket = false;
    if (names.length < 2) { errored(node, "Tick at least 2 players in Discover, or use the two-name inputs below."); return; }
    loading(node);
    try {
      const d = await api("/api/v1/compare/players", { players: names, ...common });
      renderComparePlayersMulti(node, d);
    } catch (e) { errored(node, e.message); }
    return;
  }
  state.pendingBasket = false;
  const a = $("compareA").value.trim(), b = $("compareB").value.trim();
  if (!a || !b) return;
  loading(node);
  try {
    const d = await api(
      mode === "players" ? "/api/v1/compare/players" : "/api/v1/compare/teams",
      mode === "players" ? { player_1: a, player_2: b, ...common } : { team_1: a, team_2: b, ...common }
    );
    if (mode === "players") renderComparePlayers(node, d, a, b);
    else renderCompareTeams(node, d);
  } catch (e) { errored(node, e.message); }
}

function renderComparePlayersMulti(node, d) {
  const names = d.order || Object.keys(d.players);
  clear(node);
  const radarEntries = names.slice(0, 5).map((name, i) => ({
    name, color: RADAR_COLORS[i % RADAR_COLORS.length], report: d.players[name],
  }));
  node.innerHTML = `
    ${compareHeaderChips(d, names)}
    <div class="card" style="margin-top:12px"><h3>${term("radar")} · ${names.length} players · shared pool (${d.pool_size}) ${windowBadge(d)}</h3>
      <div id="compareRadar"></div>
      ${names.length > 5 ? `<div class="hint">Radar shows the first 5; tables include all ${names.length}.</div>` : ""}
    </div>
    <div class="card" style="margin-top:16px"><h3>${term("per90")} comparison · best value highlighted</h3>${multiPer90(d, names)}</div>
    <div class="card" style="margin-top:16px"><h3>Involvement & finishing</h3>${multiInvolvement(d, names)}</div>
    <div class="grid cols-2" style="margin-top:16px">
      <div class="card"><h3>${term("xG_per_shot")} & shot volume</h3>${multiShotSelection(d, names)}</div>
      <div class="card"><h3>Creative dominance</h3>${multiCreative(d, names)}</div>
    </div>
    <div class="card" style="margin-top:16px"><h3>${term("regain_xg")}</h3>${multiPressing(d, names)}</div>
    ${profileSection(d, names, "Shot situations", "situations", "situations")}
    ${profileSection(d, names, "Shot zones", "shot_zones", "zones")}
    ${profileSection(d, names, "Shot types", "shot_types", "types")}
    ${roleSplitSection(d, names)}
    ${minuteBucketSection(d, names)}
    ${homeAwaySection(d, names)}
    <div class="caveat"><strong>Limitations.</strong><ul>${d.limitations.map((l) => `<li>${l}</li>`).join("")}</ul></div>
  `;
  drawMultiRadar("compareRadar", d.radar_labels, radarEntries);
  applyHighlightState();
}

function multiPer90(d, names) {
  const rows = [["goals", "goals"], ["xG", "xG"], ["npxG", "npxG"], ["assists", "assists"],
    ["xA", "xA"], ["shots", "shots"], ["key_passes", "key_passes"]];
  const head = `<tr><th></th>${names.map((n) => `<th class="num">${n}${d.players[n].player.age != null ? ` (${d.players[n].player.age})` : ""}</th>`).join("")}</tr>`;
  const body = rows.map(([k, gk]) => {
    const values = names.map((n) => d.players[n].per90_breakdown.per90[k]);
    const best = Math.max(...values.filter((v) => typeof v === "number"));
    return `<tr><td>${term(gk)}</td>${values.map((v) => `<td class="num${v === best ? " best-cell" : ""}">${fmt(v, 3)}</td>`).join("")}</tr>`;
  }).join("");
  return `<table><thead>${head}</thead><tbody>${body}</tbody></table>`;
}

function multiShotSelection(d, names) {
  const rows = [["shots_per90", "shots"], ["xG_per_shot", "xG_per_shot"], ["npxG_per_shot", "npxG"]];
  const head = `<tr><th></th>${names.map((n) => `<th class="num">${n}</th>`).join("")}</tr>`;
  const body = rows.map(([key, gk]) => {
    const values = names.map((n) => d.players[n].shot_selection[key]);
    const best = Math.max(...values.filter((v) => typeof v === "number"));
    return `<tr><td>${term(gk)}</td>${values.map((v) => `<td class="num${v === best ? " best-cell" : ""}">${v == null ? "N/A" : fmt(v, 3)}</td>`).join("")}</tr>`;
  }).join("");
  return `<table><thead>${head}</thead><tbody>${body}</tbody></table>
    <div class="hint">${d.players[names[0]].shot_selection.interpretation}</div>`;
}

function multiCreative(d, names) {
  const head = `<tr><th></th>${names.map((n) => `<th class="num">${n}</th>`).join("")}</tr>`;
  const shares = names.map((n) => d.players[n].creative_dominance.xA_share);
  const best = Math.max(...shares.filter((v) => typeof v === "number"));
  const row = (label, getter, bestVal) => `<tr><td>${label}</td>${names.map((n, i) => {
    const v = getter(d.players[n]);
    return `<td class="num${v === bestVal ? " best-cell" : ""}">${v == null ? "N/A" : fmt(v, 3)}</td>`;
  }).join("")}</tr>`;
  return `<table><thead>${head}</thead><tbody>
    ${row("xA share of team", (r) => r.creative_dominance.xA_share, best)}
    ${row("team xA total", (r) => r.creative_dominance.team_xA, null)}
  </tbody></table><div class="hint">Share of their team's total expected assists — how much the attack runs through them.</div>`;
}

function multiPressing(d, names) {
  const head = `<tr><th></th>${names.map((n) => `<th class="num">${n}</th>`).join("")}</tr>`;
  const withData = names.filter((n) => d.players[n].pressing_output);
  if (!withData.length) return `<div class="empty">Pressing data needs shot-level lookups — unavailable for this comparison.</div>`;
  const shares = withData.map((n) => d.players[n].pressing_output.regain_xG_share);
  const best = Math.max(...shares);
  const row = (label, getter, bestVal) => `<tr><td>${label}</td>${names.map((n) => {
    const p = d.players[n].pressing_output;
    if (!p) return `<td class="num">—</td>`;
    const v = getter(p);
    return `<td class="num${v === bestVal ? " best-cell" : ""}">${fmt(v, 3)}</td>`;
  }).join("")}</tr>`;
  return `<table><thead>${head}</thead><tbody>
    ${row("regain xG share", (p) => p.regain_xG_share, best)}
    ${row("shots after regain", (p) => p.regain_shots, null)}
    ${row("goals after regain", (p) => p.regain_goals, null)}
  </tbody></table><div class="hint">${term("regain_xg")} — share of own xG from chances after possession regains.</div>`;
}

function multiInvolvement(d, names) {
  const chain = names.map((n) => d.players[n].involvement_profile);
  const chainBest = Math.max(...chain.map((c) => c.xGChain_per90));
  const buildupBest = Math.max(...chain.map((c) => c.xGBuildup_per90));
  const rows = (label, getter, best) => `<tr><td>${label}</td>${names.map((n, i) => {
    const v = getter(chain[i]);
    return `<td class="num${v === best ? " best-cell" : ""}">${fmt(v, 3)}</td>`;
  }).join("")}</tr>`;
  return `<table><thead><tr><th>per 90</th>${names.map((n) => `<th class="num">${n}</th>`).join("")}</tr></thead><tbody>
    ${rows(term("xG_chain"), (c) => c.xGChain_per90, chainBest)}
    ${rows(term("xG_buildup"), (c) => c.xGBuildup_per90, buildupBest)}
  </tbody></table>
  <div class="kv" style="margin-top:10px">${names.map((n) => {
    const f = d.players[n].finishing_overperformance;
    return `<span class="k">${n} ${term("g_minus_xg")}</span><span class="v"><span class="badge ${f.g_minus_xg > 0 ? "good" : f.g_minus_xg < 0 ? "bad" : ""}">${f.g_minus_xg >= 0 ? "+" : ""}${fmt(f.g_minus_xg)}</span> ± ${fmt(f.g_minus_xg_std_error)}</span>`;
  }).join("")}</div>`;
}

function drawMultiRadar(container, labels, entries) {
  const el = document.getElementById(container);
  if (!el) return;
  const size = 400, cx = size / 2, cy = size / 2, r = 140;
  const n = labels.length;
  if (n < 3) { el.innerHTML = `<div class="empty">Need ≥3 metrics.</div>`; return; }
  const ang = (i) => -Math.PI / 2 + (i * 2 * Math.PI) / n;
  const pt = (i, rad) => [cx + rad * Math.cos(ang(i)), cy + rad * Math.sin(ang(i))];
  let rings = "";
  for (let g = 1; g <= 4; g++) {
    const rr = r * g / 4;
    let pts = ""; for (let i = 0; i < n; i++) { const [x, y] = pt(i, rr); pts += `${x},${y} `; }
    rings += `<polygon points="${pts}" fill="none" stroke="#504945" stroke-width="1"/>`;
  }
  let spokes = "", labelsSvg = "";
  for (let i = 0; i < n; i++) {
    const [x, y] = pt(i, r);
    spokes += `<line x1="${cx}" y1="${cy}" x2="${x}" y2="${y}" stroke="#504945" stroke-width="1"/>`;
    const [lx, ly] = pt(i, r + 20);
    labelsSvg += `<text x="${lx}" y="${ly}" fill="#a89984" font-size="10" text-anchor="middle" dominant-baseline="middle">${radarLabelTitle(labels[i])}${labels[i]}</text>`;
  }
  const polys = entries.map((entry) => {
    const byLabel = Object.fromEntries(entry.report.radar.profile.map((p) => [p.label, p.percentile]));
    let pts = "";
    for (let i = 0; i < n; i++) {
      const pct = Math.max(0, Math.min(100, byLabel[labels[i]] ?? 0));
      const [x, y] = pt(i, r * pct / 100);
      pts += `${x},${y} `;
    }
    return `<polygon points="${pts}" fill="${entry.color}" fill-opacity="0.10" stroke="${entry.color}" stroke-width="2"/>`;
  }).join("");
  const legend = `<div class="compare-chips" style="margin-top:8px">${entries.map((e) =>
    `<span class="compare-chip"><span class="dot" style="background:${e.color}"></span>${e.name}</span>`).join("")}</div>`;
  el.innerHTML = `<svg class="radar-svg" viewBox="0 0 ${size} ${size}">${rings}${spokes}${polys}${labelsSvg}</svg>
    ${legend}<div class="hint">${term("percentile")} vs league pool · filled areas are semi-transparent so overlaps stay readable</div>`;
}

function renderComparePlayers(node, d, nameA, nameB) {
  const pa = d.players[nameA], pb = d.players[nameB];
  clear(node);
  node.innerHTML = `
    ${compareHeaderChips(d, [nameA, nameB])}
    <div class="grid cols-2" style="margin-top:12px">
      <div class="card"><h3>${term("percentile")} ${term("radar")} · shared pool (${d.pool_size} players) ${windowBadge(d)}</h3><div id="compareRadar"></div></div>
      <div class="card"><h3>${term("per90")} comparison</h3>${comparePer90(pa, pb)}</div>
    </div>
    <div class="grid cols-2" style="margin-top:16px">
      <div class="card"><h3>Involvement</h3>${compareInvolvement(pa, pb)}</div>
      <div class="card"><h3>${term("g_minus_xg")}</h3>${compareFinishing(pa, pb)}</div>
    </div>
    <div class="grid cols-2" style="margin-top:16px">
      <div class="card"><h3>${term("xG_per_shot")} & shot volume</h3>${multiShotSelection(d, [nameA, nameB])}</div>
      <div class="card"><h3>Creative dominance</h3>${multiCreative(d, [nameA, nameB])}</div>
    </div>
    <div class="card" style="margin-top:16px"><h3>${term("regain_xg")}</h3>${multiPressing(d, [nameA, nameB])}</div>
    ${profileSection(d, [nameA, nameB], "Shot situations", "situations", "situations")}
    ${profileSection(d, [nameA, nameB], "Shot zones", "shot_zones", "zones")}
    ${profileSection(d, [nameA, nameB], "Shot types", "shot_types", "types")}
    ${roleSplitSection(d, [nameA, nameB])}
    ${minuteBucketSection(d, [nameA, nameB])}
    ${homeAwaySection(d, [nameA, nameB])}
    <div class="caveat"><strong>Limitations.</strong><ul>${d.limitations.map((l) => `<li>${l}</li>`).join("")}</ul></div>
  `;
  drawMultiRadar("compareRadar", d.radar_labels, [
    { name: nameA, color: RADAR_COLORS[0], report: pa },
    { name: nameB, color: RADAR_COLORS[1], report: pb },
  ]);
  applyHighlightState();
}

function comparePer90(pa, pb) {
  const rows = [["goals", "goals"], ["xG", "xG"], ["npxG", "npxG"], ["assists", "assists"], ["xA", "xA"], ["shots", "shots"], ["key_passes", "key_passes"]];
  return `<table><thead><tr><th></th><th class="num">${pa.player.name}${pa.player.age != null ? ` (${pa.player.age})` : ""}</th><th class="num">${pb.player.name}${pb.player.age != null ? ` (${pb.player.age})` : ""}</th></tr></thead><tbody>
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
    rings += `<polygon points="${pts}" fill="none" stroke="#504945" stroke-width="1"/>`;
  }
  let spokes = "", labelsSvg = "";
  for (let i = 0; i < n; i++) {
    const [x, y] = pt(i, r);
    spokes += `<line x1="${cx}" y1="${cy}" x2="${x}" y2="${y}" stroke="#504945" stroke-width="1"/>`;
    const [lx, ly] = pt(i, r + 20);
    labelsSvg += `<text x="${lx}" y="${ly}" fill="#a89984" font-size="10" text-anchor="middle" dominant-baseline="middle">${radarLabelTitle(labels[i])}${labels[i]}</text>`;
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
  el.innerHTML = `<svg class="radar-svg" viewBox="0 0 ${size} ${size}">${rings}${spokes}${poly(byLabelA, "#83a598", "rgba(131,165,152,0.18)")}${poly(byLabelB, "#b8bb26", "rgba(184,187,38,0.14)")}${labelsSvg}</svg>
    <div class="hint"><span style="color:#83a598">● ${nameA}</span> &nbsp; <span style="color:#b8bb26">● ${nameB}</span> &nbsp; percentile vs league pool</div>`;
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

// ---------- STATSBOMB ----------
$("sbGo").addEventListener("click", runSb);
$("sbCompetition").addEventListener("change", async () => {
  const [competitionId, seasonId] = $("sbCompetition").value.split("/");
  $("sbMatch").innerHTML = `<option value="">loading matches…</option>`;
  try {
    const d = await api("/api/v1/statsbomb/matches", { competition_id: parseInt(competitionId, 10), season_id: parseInt(seasonId, 10) });
    $("sbMatch").innerHTML = d.matches.map((m) => `<option value="${m.match_id}">${m.date} · ${m.home} ${m.home_score}–${m.away_score} ${m.away}</option>`).join("");
  } catch (e) {
    $("sbMatch").innerHTML = `<option value="">${e.message}</option>`;
  }
});

async function loadSbCompetitions() {
  try {
    const d = await api("/api/v1/statsbomb/competitions", null, "GET");
    state.sbNote = d.note;
    const groups = {};
    d.competitions.forEach((c) => {
      groups[c.competition_name] = groups[c.competition_name] || [];
      groups[c.competition_name].push(c);
    });
    $("sbCompetition").innerHTML = `<option value="">competition / season…</option>` +
      Object.entries(groups).map(([name, seasons]) =>
        `<optgroup label="${name}">${seasons.map((s) => `<option value="${s.competition_id}/${s.season_id}">${s.season_name}${s.country ? ` · ${s.country}` : ""}</option>`).join("")}</optgroup>`).join("");
  } catch (e) {
    $("sbCompetition").innerHTML = `<option value="">unavailable: ${e.message}</option>`;
  }
}

async function runSb() {
  const id = $("sbMatch").value;
  if (!id) return;
  const node = $("sbContent"); loading(node);
  try {
    const d = await api(`/api/v1/statsbomb/match/${encodeURIComponent(id)}`);
    renderSb(node, d);
  } catch (e) { errored(node, e.message); }
}

function renderSb(node, d) {
  clear(node);
  const teamCards = Object.entries(d.teams).map(([team, s]) => `
    <div class="card"><h3>${team}</h3><div class="kv">
      <span class="k">${term("sb_touch")}</span><span class="v">${s.touches} · in opp box ${s.touches_opp_box} · opp half ${s.touches_opp_half}</span>
      <span class="k">${term("sb_pressure")}</span><span class="v">${s.pressures} · successful ${s.successful_pressures}</span>
      <span class="k">${term("sb_carry")}</span><span class="v">${s.carries} · ${fmt(s.carry_distance, 0)} m</span>
      <span class="k">${term("sb_recovery")}</span><span class="v">${s.ball_recoveries}</span>
      <span class="k">Passes completed</span><span class="v">${s.passes_completed} / ${s.passes} · final-third entries ${s.final_third_entries}</span>
      <span class="k">Shots / goals</span><span class="v">${s.shots} / ${s.goals}</span>
    </div></div>`).join("");
  const leaderboards = Object.entries(d.player_leaderboards).map(([team, players]) => `
    <div class="card"><h3>${team} · player leaderboards</h3>
      <table><thead><tr><th>Player</th><th class="num">${term("sb_touch")}</th><th class="num">opp box</th><th class="num">${term("sb_pressure")}</th><th class="num">${term("sb_carry")}</th><th class="num">dist m</th><th class="num">${term("sb_recovery")}</th><th class="num">passes ✓</th><th class="num">shots</th></tr></thead><tbody>
        ${players.slice(0, 12).map((p) => `<tr><td>${p.player}</td><td class="num">${p.touches}</td><td class="num">${p.touches_opp_box}</td><td class="num">${p.pressures}</td><td class="num">${p.carries}</td><td class="num">${fmt(p.carry_distance, 0)}</td><td class="num">${p.ball_recoveries}</td><td class="num">${p.passes_completed}</td><td class="num">${p.shots}</td></tr>`).join("")}
      </tbody></table></div>`).join("");
  const defs = Object.entries(d.definitions).map(([k, v]) => `<li><strong>${k}:</strong> ${v}</li>`).join("");
  node.innerHTML = `
    <div class="grid cols-2">${teamCards}</div>
    <div class="grid cols-2" style="margin-top:16px">${leaderboards}</div>
    <div class="caveat"><strong>Definitions.</strong><ul>${defs}</ul></div>
    <div class="caveat"><strong>Limitations.</strong><ul>${d.limitations.map((l) => `<li>${l}</li>`).join("")}</ul></div>
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
      const bg = t > 0.01 ? `rgba(131,165,152,${(0.05 + 0.55 * t).toFixed(3)})` : "transparent";
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
  const posColor = (i) => (i < 4 ? "var(--accent-2)" : i < 6 ? "var(--accent)" : i >= nTeams - 3 ? "var(--danger)" : "#665c54");
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
populateSeasonSelects();
runLeague();

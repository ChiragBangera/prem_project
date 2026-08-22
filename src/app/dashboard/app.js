"use strict";

const CURRENT_YEAR = new Date().getFullYear();
const CURRENT_MONTH = new Date().getMonth() + 1;
const LATEST_SEASON = CURRENT_MONTH >= 7 ? CURRENT_YEAR : CURRENT_YEAR - 1;
const SEASON_RANGE = { first: 2014, last: LATEST_SEASON };

const state = {
  league: "EPL",
  tab: "match",
  teamSubtab: "overview",
  matchMode: "recent", // "recent" | "board"
  boardRound: 1,
  season: LATEST_SEASON,
  hiddenSeasons: new Set(),
  pitchModes: {},
  roundsData: null,
  roundsLoadedFor: null,
  activePlayerData: null,
  activeTeamData: null,
  activeMatchData: null,
  activeMatchSofascore: null,
  selectedSofaPlayer: null,
};

const $ = (id) => document.getElementById(id);

const TAB_TITLES = {
  match: { title: "Match Intelligence Deep-Dive", desc: "Full pitch tactical shot maps, cumulative xG flow timelines, tactical lineups, big chance audits, and process diagnostics." },
  player: { title: "Player Scouting & Intelligence", desc: "Decision metrics, percentile radars, tactical shot density heatmaps, finishing diagnostics, and peer similarity." },
  discover: { title: "Talent Discovery & Scouting", desc: "Filter and rank players across European leagues by involvement metrics, roles, and age curves." },
  compare: { title: "Head-to-Head Comparison & Basket", desc: "Overlay radar charts and compare multi-metric player and club profiles directly." },
  team: { title: "Team Tactical Intelligence", desc: "Pressing intensity (PPDA), deep completions, form momentum CUSUM, attacking & defensive shot maps." },
  league: { title: "League Overview & xPTS Diagnostics", desc: "Examine expected points (xPTS), lying tables, finishing variance, and division pace." },
  predict: { title: "Predictive Modeling & Simulations", desc: "Bivariate Dixon-Coles and Elo match forecasting, Monte Carlo season simulations, and calibration." },
  info: { title: "Football Analytics Metric Glossary", desc: "Mathematical formulas, metric definitions, and honest limitations of the Understat dataset." },
};

const LEAGUE_LABEL = {
  EPL: "Premier League",
  La_liga: "La Liga",
  Serie_A: "Serie A",
  Bundesliga: "Bundesliga",
  Ligue_1: "Ligue 1"
};

// Watchlist Helpers
const WATCHLIST_KEY = "prem_watchlist";
function getWatchlist() {
  try { return JSON.parse(localStorage.getItem(WATCHLIST_KEY) || "[]"); } catch (_) { return []; }
}
function setWatchlist(list) {
  localStorage.setItem(WATCHLIST_KEY, JSON.stringify(list));
  updateWatchlistPill();
}
function isWatched(id) {
  return getWatchlist().some((w) => String(w.id) === String(id));
}
function toggleWatchlist(player) {
  if (!player || !player.id) return;
  const list = getWatchlist();
  const idx = list.findIndex((w) => String(w.id) === String(player.id));
  if (idx >= 0) {
    list.splice(idx, 1);
  } else {
    list.push({
      id: player.id,
      name: player.name || player.player_name,
      team: player.team_title || player.team,
      position: player.position_group || player.position,
      league: state.league,
      season: state.season,
      addedAt: new Date().toISOString(),
    });
  }
  setWatchlist(list);
  const btn = document.querySelector(`[data-watch-player="${player.id}"]`);
  if (btn) {
    const watched = isWatched(player.id);
    btn.textContent = watched ? "★ Watched" : "☆ Watch";
    btn.style.color = watched ? "var(--accent)" : "";
  }
}
function updateWatchlistPill() {
  const count = getWatchlist().length;
  const pill = $("watchlistCountPill");
  if (pill) {
    pill.textContent = `${count} Saved`;
    pill.style.display = count > 0 ? "inline-flex" : "none";
  }
}

// API Fetch Helper
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

function clear(node) {
  if (node._timer) clearInterval(node._timer);
  node.innerHTML = "";
}

function loading(node) {
  node.dataset.t0 = Date.now();
  node.innerHTML = `<div class="loading"><div class="loading-pulse"><span></span><span></span><span></span></div><span class="elapsed">0s elapsed</span></div>`;
  const span = node.querySelector(".elapsed");
  if (node._timer) clearInterval(node._timer);
  node._timer = setInterval(() => {
    const s = Math.round((Date.now() - Number(node.dataset.t0)) / 1000);
    if (span) span.textContent = `${s}s elapsed`;
  }, 1000);
}

function errored(node, msg) {
  if (node._timer) clearInterval(node._timer);
  node.innerHTML = `<div class="error"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:8px;vertical-align:middle"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg><strong>Error:</strong> ${msg}</div>`;
}

function fmt(n, decimals = 2) {
  if (n === null || n === undefined || isNaN(n)) return "—";
  return Number(n).toFixed(decimals);
}

function escapeHtml(s) {
  return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function pct(n, decimals = 0) {
  if (n === null || n === undefined || isNaN(n)) return "—";
  return `${(Number(n) * 100).toFixed(decimals)}%`;
}

function windowBadge(d) {
  const w = d && d.date_window;
  if (!w || (!w.start_date && !w.end_date)) return "";
  const label = [w.start_date, w.end_date].filter(Boolean).join(" → ");
  return `<span class="hero-pill">${label}</span>`;
}

function formatEur(value) {
  if (value === null || value === undefined || isNaN(value)) return null;
  const num = Number(value);
  if (num >= 1_000_000) return `€${(num / 1_000_000).toFixed(1)}m`;
  if (num >= 1_000) return `€${(num / 1_000).toFixed(0)}k`;
  return `€${num.toLocaleString()}`;
}

function enrichmentPills(enrichment) {
  if (!enrichment || typeof enrichment !== "object") return "";
  const pills = [];
  if (enrichment.market_value_eur) pills.push(`<span class="hero-pill" title="Transfermarkt valuation">💶 ${formatEur(enrichment.market_value_eur)}</span>`);
  if (enrichment.contract_end) pills.push(`<span class="hero-pill" title="Contract expiry">📅 ${enrichment.contract_end}</span>`);
  if (enrichment.foot) pills.push(`<span class="hero-pill" title="Preferred foot">🦶 ${enrichment.foot}</span>`);
  if (enrichment.height_cm) pills.push(`<span class="hero-pill" title="Height">📏 ${enrichment.height_cm}cm</span>`);
  if (enrichment.sofascore_rating) pills.push(`<span class="hero-pill accent" title="Sofascore season rating">⭐ ${fmt(enrichment.sofascore_rating, 2)}</span>`);
  return pills.join(" ");
}

// Dynamic Theme Management & Chart Color Helper
function getThemeColor(varName) {
  return getComputedStyle(document.documentElement).getPropertyValue(varName).trim();
}

function applyTheme(theme, mode) {
  const root = document.documentElement;
  root.setAttribute("data-theme", theme);
  root.setAttribute("data-mode", mode);
  localStorage.setItem("prem_theme", theme);
  localStorage.setItem("prem_mode", mode);
  const sel = $("themeSelect");
  if (sel && sel.value !== theme) sel.value = theme;
  const btn = $("modeToggle");
  if (btn) btn.textContent = mode === "light" ? "☀️ Light" : "🌙 Dark";

  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", mode === "light" ? "#ffffff" : "#0B0D0F");

  redrawActiveCharts();
}

function redrawActiveCharts() {
  if (state.tab === "player" && state.activePlayerData) {
    const d = state.activePlayerData;
    renderPitchHeatmap("playerPitch", d.shots || []);
    if (d.radar && d.radar.profile) drawRadar("playerRadar", d.radar.profile.filter(p => p.percentile > 0 || p.raw > 0));
  } else if (state.tab === "team" && state.activeTeamData) {
    renderTeamSubtab(state.teamSubtab);
  } else if (state.tab === "match" && state.activeMatchData) {
    renderMatch($("matchContent"), state.activeMatchData, state.activeMatchSofascore);
  }
}

(function initTheme() {
  const theme = localStorage.getItem("prem_theme") || "midnight";
  const mode = localStorage.getItem("prem_mode") || "dark";
  applyTheme(theme, mode);
  const sel = $("themeSelect");
  if (sel) {
    sel.value = theme;
    sel.addEventListener("change", (e) => applyTheme(e.target.value, localStorage.getItem("prem_mode") || "dark"));
  }
  const btn = $("modeToggle");
  if (btn) {
    btn.addEventListener("click", () => {
      const current = localStorage.getItem("prem_mode") || "dark";
      const next = current === "light" ? "dark" : "light";
      applyTheme(localStorage.getItem("prem_theme") || "midnight", next);
    });
  }
})();

// Glossary Management
let GLOSSARY = {};
(async () => {
  try {
    const d = await api("/api/v1/glossary", null, "GET");
    GLOSSARY = d.by_key || {};
    window.__GLOSSARY_GROUPS__ = d.groups || [];
    window.__FEATURE_LABELS__ = d.feature_labels || {};
    if (state.tab === "info") renderInfo();
  } catch (_) { /* gracefully degrade */ }
})();

function term(key, fallback) {
  const entry = GLOSSARY[key];
  const label = entry ? entry.label : (fallback || key);
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

function hoverDot(cx, cy, tip, color, r = 4) {
  return `<circle cx="${cx}" cy="${cy}" r="12" fill="transparent" data-tip="${tip}"/><circle cx="${cx}" cy="${cy}" r="${r}" fill="${color}"/>`;
}

// Persist Inputs
const PERSIST_IDS = [
  "playerName", "teamName", "leagueSeason",
  "matchSeason", "matchId",
  "predHome", "predAway", "predSeason", "simSeason", "calSeason",
  "compareA", "compareB", "compareSeason", "discoverMinutes", "discoverOrderBy"
];
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
  document.querySelectorAll("#leaguePicker button").forEach((b) => b.classList.toggle("active", b.dataset.league === savedLeague));
  state.league = savedLeague || state.league;
}

// Quick Load Example Chips
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

// Sidebar Nav Switching
document.getElementById("sidebarNav").addEventListener("click", (e) => {
  const btn = e.target.closest(".nav-item[data-tab], .nav-child[data-tab]");
  if (!btn) return;
  const tactic = btn.dataset.tactic;
  if (tactic) {
    activateTab("team");
    setTeamSubtab(tactic === "shots" ? "chance" : tactic === "possession" ? "possession" : "defence");
    return;
  }
  activateTab(btn.dataset.tab);
});

// League Picker Switching
document.getElementById("leaguePicker").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-league]");
  if (!btn) return;
  state.league = btn.dataset.league;
  localStorage.setItem("prem_league", state.league);
  document.querySelectorAll("#leaguePicker button").forEach((b) => b.classList.toggle("active", b.dataset.league === btn));
  if (state.tab === "match") loadRounds();
  if (state.tab === "league") runLeague();
  if (state.tab === "player") runPlayer();
  if (state.tab === "team") runTeam();
});

function activateTab(tab, push = true) {
  state.tab = tab;
  document.querySelectorAll(".sidebar-nav .nav-item").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  document.querySelectorAll("section.view").forEach((s) => s.classList.toggle("active", s.id === `view-${tab}`));

  const meta = TAB_TITLES[tab] || { title: "Football Analytics", desc: "" };
  if ($("viewTitle")) $("viewTitle").textContent = meta.title;
  if ($("viewDesc")) $("viewDesc").textContent = meta.desc;

  if (push && window.location.hash !== `#${tab}`) window.history.pushState(null, "", `#${tab}`);
  if (tab === "info") renderInfo();
  if (tab === "match") loadRounds();
  if (tab === "league") runLeague();
  if (tab === "player" && !state.activePlayerData) {
    if (!$("playerName").value) $("playerName").value = "Erling Haaland";
    runPlayer();
  }
  if (tab === "team" && !state.activeTeamData) {
    if (!$("teamName").value) $("teamName").value = "Arsenal";
    runTeam();
  }
  if (tab === "discover") {
    const discContent = $("discoverContent");
    if (discContent && discContent.querySelector(".empty")) runDiscover();
  }
}

window.addEventListener("popstate", () => {
  const tab = (window.location.hash || "#player").slice(1);
  if (document.querySelector(`.sidebar-nav .nav-item[data-tab="${tab}"]`)) activateTab(tab, false);
});
document.addEventListener("click", (e) => {
  if (e.target.closest("[data-back]")) { e.preventDefault(); window.history.back(); }
});

// Season Helpers
function selectedSeasons(hostId) {
  const host = document.getElementById(hostId);
  if (!host) return [];
  return JSON.parse(host.dataset.seasons || "[]");
}

function seasonOf(id) {
  const el = document.getElementById(id);
  if (el && el.classList.contains("season-multi")) {
    const seasons = selectedSeasons(id);
    return seasons[0] || LATEST_SEASON;
  }
  return parseInt(el ? el.value : String(LATEST_SEASON), 10) || LATEST_SEASON;
}

function seasonsOf(id) {
  const el = document.getElementById(id);
  if (el && el.classList.contains("season-multi")) {
    const seasons = selectedSeasons(id);
    return seasons.length > 1 ? seasons : null;
  }
  return null;
}

function dateOf(id) { const v = $(id) ? $(id).value : null; return v || null; }

function buildSeasonMulti(hostId, maxSeasons) {
  const host = document.getElementById(hostId);
  if (!host) return;
  let seasons = [];
  try {
    const saved = JSON.parse(localStorage.getItem(`prem_${hostId}`) || "[]");
    if (Array.isArray(saved) && saved.length) seasons = saved.filter((s) => s >= SEASON_RANGE.first && s <= SEASON_RANGE.last);
  } catch (_) { /* ignore */ }
  if (!seasons.length) seasons = [LATEST_SEASON];
  host.dataset.seasons = JSON.stringify(seasons);
  host.classList.add("season-multi");

  host.innerHTML = `
    <button type="button" class="season-btn" data-season-btn>${labelFor(seasons)}</button>
    <div class="season-panel" data-season-panel>
      <div class="season-hint">Pick 1–${maxSeasons} seasons (merges statistics)</div>
      ${seasonOptions(seasons)}
    </div>`;

  const btn = host.querySelector("[data-season-btn]");
  const panel = host.querySelector("[data-season-panel]");
  btn.addEventListener("click", (e) => { e.stopPropagation(); panel.classList.toggle("open"); });
  document.addEventListener("click", (e) => { if (!host.contains(e.target)) panel.classList.remove("open"); });

  host.querySelectorAll("input[type=checkbox]").forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      let current = selectedSeasons(hostId);
      const year = parseInt(checkbox.value, 10);
      if (checkbox.checked) {
        if (current.length >= maxSeasons) {
          checkbox.checked = false;
          panel.querySelector(".season-hint").textContent = `Maximum ${maxSeasons} seasons`;
          return;
        }
        current = [...current, year].sort((a, b) => b - a);
      } else {
        current = current.filter((s) => s !== year);
      }
      if (!current.length) current = [LATEST_SEASON];
      host.dataset.seasons = JSON.stringify(current);
      localStorage.setItem(`prem_${hostId}`, JSON.stringify(current));
      btn.textContent = labelFor(current);
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
  if (!seasons.length) return String(LATEST_SEASON);
  if (seasons.length === 1) return `${seasons[0]}`;
  if (seasons.length <= 3) return seasons.join(", ");
  return `${seasons.slice(0, 3).join(", ")} +${seasons.length - 3}`;
}

function buildPositionMulti(hostId, maxSelections) {
  const host = document.getElementById(hostId);
  if (!host) return;
  const options = [
    ["GK", "GK · Goalkeeper"], ["DC", "DC · Centre-back"], ["DL", "DL · Left-back"],
    ["DR", "DR · Right-back"], ["DMC", "DMC · Defensive midfield"], ["DML", "DML · Left def mid"],
    ["DMR", "DMR · Right def mid"], ["MC", "MC · Centre midfield"], ["ML", "ML · Left midfield"],
    ["MR", "MR · Right midfield"], ["AMC", "AMC · Attacking mid"], ["AML", "AML · Left attacking mid"],
    ["AMR", "AMR · Right attacking mid"], ["FWL", "FWL · Left forward"], ["FWR", "FWR · Right forward"],
    ["FW", "FW · Striker / Forward"], ["Non", "Non · Utility role"],
  ];
  let selected = [];
  try {
    const saved = JSON.parse(localStorage.getItem(`prem_${hostId}`) || "[]");
    if (Array.isArray(saved)) selected = saved.filter((v) => options.some(([code]) => code === v));
  } catch (_) { /* ignore */ }
  host.dataset.values = JSON.stringify(selected);
  host.classList.add("season-multi");
  host.innerHTML = `
    <button type="button" class="season-btn" data-season-btn>${selected.length ? selected.join(", ") : "All Roles"}</button>
    <div class="season-panel" data-season-panel>
      <div class="season-hint">Filter specific positions</div>
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
        if (current.length >= maxSelections) { checkbox.checked = false; return; }
        current = [...current, code];
      } else {
        current = current.filter((v) => v !== code);
      }
      host.dataset.values = JSON.stringify(current);
      localStorage.setItem(`prem_${hostId}`, JSON.stringify(current));
      btn.textContent = current.length ? current.join(", ") : "All Roles";
    });
  });
}

function selectedPositionValues(hostId) {
  const host = document.getElementById(hostId);
  if (!host) return null;
  const values = JSON.parse(host.dataset.values || "[]");
  return values.length ? values : null;
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
    if (keepValue && parseInt(keepValue, 10) >= SEASON_RANGE.first && parseInt(keepValue, 10) <= SEASON_RANGE.last) {
      select.value = keepValue;
    } else {
      select.value = String(LATEST_SEASON);
    }
  });
  buildSeasonMulti("playerSeasons", 5);
  buildSeasonMulti("teamSeasons", 5);
  buildSeasonMulti("discoverSeasons", 5);
  buildPositionMulti("discoverPositions", 8);
}
populateSeasonSelects();

$("matchSeason").addEventListener("change", () => loadRounds());
$("leagueSeason").addEventListener("change", () => runLeague());

// ==========================================================
// IMAGE 1: LAYER 1 DECISION METRICS WITH SPARKLINES & DELTAS
// ==========================================================
function decisionMetricsHTML(metrics, sparklines = {}) {
  if (!metrics || !Array.isArray(metrics) || !metrics.length) return "";
  return `
    <div class="l1-grid">
      ${metrics.map((m) => {
        const isPos = m.is_positive;
        const deltaCls = isPos ? "positive" : "negative";
        const pct = Math.max(2, Math.min(100, m.percentile || 50));
        const deltaLabel = m.delta_display ? `${m.delta_display} vs benchmark` : (m.delta != null ? `${m.delta >= 0 ? '+' : ''}${fmt(m.delta, 2)} vs benchmark` : "");
        const spark = sparklines[m.key] ? renderInlineSparkline(sparklines[m.key], isPos) : "";
        return `
          <div class="metric-card ${deltaCls}">
            <div class="metric-header">
              <span class="metric-label">${m.label || m.key}</span>
              ${m.benchmark != null ? `<span class="metric-bench-tag">Avg: ${fmt(m.benchmark, 2)}</span>` : ""}
            </div>
            <div class="metric-value-row">
              <span class="metric-value">${fmt(m.value, m.key === 'xG_per_shot' ? 3 : 2)}</span>
              ${deltaLabel ? `<span class="metric-delta ${deltaCls}">${deltaLabel}</span>` : ""}
            </div>
            ${spark ? `<div style="margin:4px 0 6px">${spark}</div>` : ""}
            <div class="metric-pct-wrap">
              <div class="metric-pct-track">
                <div class="metric-pct-fill" style="width:${pct}%"></div>
              </div>
              <div style="display:flex;justify-content:space-between;align-items:center">
                <span class="metric-subline">${m.subline || ""}</span>
                <span style="font-family:var(--mono);font-size:10.5px;font-weight:700;color:var(--text-bright)">${Math.round(pct)}th %</span>
              </div>
            </div>
          </div>
        `;
      }).join("")}
    </div>
  `;
}

function renderInlineSparkline(pts, isPositive) {
  if (!pts || pts.length < 2) return "";
  const w = 140, h = 26;
  const min = Math.min(...pts), max = Math.max(...pts), span = Math.max(max - min, 0.001);
  const x = (i) => (i / (pts.length - 1)) * w;
  const y = (v) => h - 2 - ((v - min) / span) * (h - 6);
  const path = pts.map((v, i) => `${i ? "L" : "M"}${x(i)},${y(v)}`).join(" ");
  const stroke = isPositive ? "var(--accent)" : "var(--fg-bad)";
  return `<svg width="${w}" height="${h}" style="overflow:visible;display:block">
    <path d="${path}" fill="none" stroke="${stroke}" stroke-width="2" stroke-linecap="round"/>
    <circle cx="${x(pts.length - 1)}" cy="${y(pts[pts.length - 1])}" r="3" fill="${stroke}"/>
  </svg>`;
}

// ==========================================================
// IMAGE 3: TACTICAL PITCH & 4-TIER SHOT MAP ENGINE
// ==========================================================
function classifyShotTier(xg) {
  const v = parseFloat(xg) || 0;
  if (v >= 0.30) return { name: "Great", color: getThemeColor("--tier-great") || "#1ed760", class: "tier-great", min: 0.30 };
  if (v >= 0.15) return { name: "Good", color: getThemeColor("--tier-good") || "#facc15", class: "tier-good", min: 0.15 };
  if (v >= 0.08) return { name: "Average", color: getThemeColor("--tier-avg") || "#fb923c", class: "tier-avg", min: 0.08 };
  return { name: "Poor", color: getThemeColor("--tier-poor") || "#f43f5e", class: "tier-poor", min: 0.0 };
}

function shotQualityRailHTML(shots) {
  if (!shots || !shots.length) return "";
  let great = 0, good = 0, avg = 0, poor = 0;
  let greatXg = 0, goodXg = 0, avgXg = 0, poorXg = 0;
  let totalXg = 0, goals = 0;

  shots.forEach((s) => {
    const xg = parseFloat(s.xG) || 0;
    totalXg += xg;
    if (s.result === "Goal") goals++;
    if (xg >= 0.30) { great++; greatXg += xg; }
    else if (xg >= 0.15) { good++; goodXg += xg; }
    else if (xg >= 0.08) { avg++; avgXg += xg; }
    else { poor++; poorXg += xg; }
  });

  const total = shots.length;
  const actualConv = (goals / total) * 100;
  const expectedConv = (totalXg / total) * 100;

  return `
    <div class="shot-quality-rail">
      <div class="tier-badge-group">
        <span class="shot-tier-pill"><span class="tier-circle tier-great"></span> Great (≥0.30 xG): <strong>${great}</strong> (${pct(great/total)})</span>
        <span class="shot-tier-pill"><span class="tier-circle tier-good"></span> Good (0.15–0.30): <strong>${good}</strong> (${pct(good/total)})</span>
        <span class="shot-tier-pill"><span class="tier-circle tier-avg"></span> Avg (0.08–0.15): <strong>${avg}</strong> (${pct(avg/total)})</span>
        <span class="shot-tier-pill"><span class="tier-circle tier-poor"></span> Poor (&lt;0.08): <strong>${poor}</strong> (${pct(poor/total)})</span>
      </div>
      <div style="display:flex;gap:14px;align-items:center;font-family:var(--mono);font-size:11.5px">
        <span>Total: <strong>${total}</strong> shots (${fmt(totalXg, 2)} xG · ${fmt(totalXg/total, 3)}/shot)</span>
        <span style="color:${actualConv >= expectedConv ? 'var(--accent)' : 'var(--fg-bad)'};font-weight:800">
          Conversion: ${fmt(actualConv, 1)}% vs Expected: ${fmt(expectedConv, 1)}%
        </span>
      </div>
    </div>
  `;
}

const PITCH_MODES = [
  { id: "shots", label: "📍 Shots", needs: "shots" },
  { id: "heatmap", label: "🔥 Heatmap", needs: "shots" },
  { id: "passing", label: "➔ Passing", needs: "rb" },
  { id: "carries", label: "⚡ Carries", needs: "rb" },
  { id: "possession", label: "◔ Possession", needs: "sofa" },
  { id: "pressure", label: "◎ Pressure", needs: "rb" },
  { id: "buildUp", label: "⇗ Build-Up", needs: "rb" },
  { id: "formation", label: "▦ Formation", needs: "sofa" },
];

// Unified Pitch primitive. `dataInput` is either a shots array (back-compat) or
// an object { shots, sofa? , rb? }. `sofa` = Sofascore match payload (statistics,
// lineups, incidents, event_id). `rb` = aggregated per-player rating-breakdown
// (lazy-loaded, cached in state.sofaRB[event_id]).
function renderPitchHeatmap(containerId, dataInput, options = {}) {
  const container = document.getElementById(containerId);
  if (!container) return;

  const data = Array.isArray(dataInput) ? { shots: dataInput } : (dataInput || {});
  const shots = data.shots || options.shots || [];
  const sofa = data.sofa || options.sofascore || null;
  const rb = data.rb || options.rb || null;
  const lineups = (sofa && sofa.lineups && sofa.lineups.data) || null;

  const currentMode = state.pitchModes[containerId] || options.defaultMode || "shots";

  // Only offer tabs we actually have (or can lazily build) data for.
  const rbBuildable = !!(sofa && sofa.event_id && lineups);
  const availableModes = PITCH_MODES.filter((m) => {
    if (m.needs === "shots") return shots.length > 0;
    if (m.needs === "rb") return rb != null || rbBuildable;
    if (m.needs === "sofa") return m.id === "possession" ? !!(sofa && sofa.statistics) : !!lineups;
    return true;
  });
  const modes = availableModes.length ? availableModes : PITCH_MODES.slice(0, 1);
  const activeMode = modes.some((m) => m.id === currentMode) ? currentMode : modes[0].id;
  state.pitchModes[containerId] = activeMode;

  const width = options.width || 760;
  const height = options.height || 460;
  const isHalfPitch = options.halfPitch || false;

  container.innerHTML = `
    <div class="pitch-container">
      <div class="pitch-toolbar">
        <div class="pitch-mode-group">
          ${modes.map((m) => `<button class="pitch-mode-btn ${activeMode === m.id ? 'active' : ''}" data-mode="${m.id}" data-needs="${m.needs}">${m.label}</button>`).join("")}
        </div>
        <div class="pitch-legend">${pitchLegendHTML(activeMode)}</div>
      </div>
      <div class="pitch-stage">
        <canvas id="${containerId}_canvas" class="pitch-canvas" width="${width}" height="${height}"></canvas>
        <div class="pitch-empty"></div>
      </div>
    </div>
  `;

  const canvas = document.getElementById(`${containerId}_canvas`);
  const ctx = canvas ? canvas.getContext("2d") : null;
  const emptyEl = container.querySelector(".pitch-empty");

  container.querySelectorAll(".pitch-mode-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.pitchModes[containerId] = btn.dataset.mode;
      renderPitchHeatmap(containerId, data, options);
    });
  });

  // Determine data availability for the selected mode → honest empty or build trigger.
  const modeCfg = PITCH_MODES.find((m) => m.id === activeMode);
  let missing = null;
  if (modeCfg) {
    if (modeCfg.needs === "rb" && !rb) missing = "rating-breakdown";
    else if (modeCfg.needs === "sofa" && !sofa) missing = "Sofascore";
    else if (modeCfg.needs === "shots" && !shots.length) missing = "shot";
  }

  if (ctx) drawMinimalPitch(ctx, width, height, isHalfPitch);

  if (missing) {
    if (emptyEl) {
      let note = "";
      if (missing === "rating-breakdown") {
        const canBuild = sofa && sofa.event_id && lineups;
        note = canBuild
          ? `<div class="empty-state">No passing data loaded. <button class="primary" id="${containerId}BuildRb" style="padding:5px 10px;font-size:11.5px;margin-left:6px">Build passing network →</button></div>`
          : `<div class="empty-state">No rating-breakdown data — enable SOFASCORE_ENABLED and open a live match.</div>`;
      } else if (missing === "Sofascore") {
        note = `<div class="empty-state">No Sofascore data — enable SOFASCORE_ENABLED.</div>`;
      } else {
        note = `<div class="empty-state">No ${missing} data recorded.</div>`;
      }
      emptyEl.innerHTML = note;
    }
    const buildBtn = document.getElementById(`${containerId}BuildRb`);
    if (buildBtn) buildBtn.addEventListener("click", () => buildSofaRatingBreakdown(containerId, data, options));
    return;
  }

  // Draw the selected mode.
  if (ctx) {
    switch (activeMode) {
      case "heatmap":
        drawGaussianHeatmap(ctx, shots, width, height);
        drawPitchLines(ctx, width, height, isHalfPitch);
        break;
      case "passing": drawPassingNetwork(ctx, rb, lineups, width, height); break;
      case "carries": drawCarries(ctx, rb, width, height, isHalfPitch); break;
      case "possession": drawPossession(ctx, sofa, width, height, isHalfPitch); break;
      case "pressure": drawPressure(ctx, rb, width, height, isHalfPitch); break;
      case "buildUp": drawBuildUp(ctx, rb, width, height, isHalfPitch); break;
      case "formation": drawFormationDots(ctx, lineups, width, height); break;
      default: drawTierShotCircles(ctx, shots, width, height, options); break;
    }
  }

  // Hover tooltips — only meaningful for the shot mode.
  if (activeMode === "shots" && canvas) {
    canvas.addEventListener("mousemove", (e) => {
      const rect = canvas.getBoundingClientRect();
      const mouseX = ((e.clientX - rect.left) / rect.width) * width;
      const mouseY = ((e.clientY - rect.top) / rect.height) * height;

      let closest = null;
      let minDist = 18;
      shots.forEach((s) => {
        const sx = s.X * width;
        const sy = (1 - s.Y) * height;
        if (Math.hypot(mouseX - sx, mouseY - sy) < minDist) { minDist = Math.hypot(mouseX - sx, mouseY - sy); closest = s; }
      });

      if (closest) {
        const tier = classifyShotTier(closest.xG);
        const isGoal = closest.result === "Goal";
        const tip = `<strong>${closest.player || "Shooter"} (${closest.minute}')</strong><br>
          Outcome: <span style="color:${isGoal ? 'var(--accent)' : 'var(--neutral)'};font-weight:800">${closest.result}</span><br>
          Quality: <span style="color:${tier.color};font-weight:800">${tier.name} Tier (xG: ${fmt(closest.xG, 3)})</span><br>
          Phase: ${closest.situation || "OpenPlay"}${closest.shotType ? ` · ${closest.shotType}` : ""}${closest.lastAction ? `<br>Via: ${closest.lastAction}` : ""}`;
        chartTipEl.innerHTML = tip;
        chartTipEl.classList.add("show");
        chartTipEl.style.left = `${e.clientX + 14}px`;
        chartTipEl.style.top = `${e.clientY + 14}px`;
      } else if (chartTipEl) {
        chartTipEl.classList.remove("show");
      }
    });
    canvas.addEventListener("mouseleave", () => { if (chartTipEl) chartTipEl.classList.remove("show"); });
  }
}

function pitchLegendHTML(mode) {
  if (mode === "shots") {
    return `
      <div class="pitch-legend-item"><span class="pitch-dot" style="background:var(--tier-great)"></span> Great (≥0.30)</div>
      <div class="pitch-legend-item"><span class="pitch-dot" style="background:var(--tier-good)"></span> Good (0.15–0.30)</div>
      <div class="pitch-legend-item"><span class="pitch-dot" style="background:var(--tier-avg)"></span> Avg (0.08–0.15)</div>
      <div class="pitch-legend-item"><span class="pitch-dot" style="background:var(--tier-poor)"></span> Poor (&lt;0.08)</div>
      <div class="pitch-legend-item" style="margin-left:6px;padding-left:8px;border-left:1px solid var(--border)">
        <span style="border:1.5px solid var(--text);border-radius:50%;width:8px;height:8px;display:inline-block"></span> Goal Ring
      </div>`;
  }
  if (mode === "passing") return `<div class="pitch-legend-item"><span class="pitch-dot" style="background:var(--accent)"></span> Completed pass</div>`;
  if (mode === "carries") return `<div class="pitch-legend-item"><span class="pitch-dot" style="background:var(--accent)"></span> Progressive carry</div>`;
  if (mode === "possession") return `<div class="pitch-legend-item"><span class="pitch-dot" style="background:var(--accent)"></span> Territory &gt; benchmark</div><div class="pitch-legend-item"><span class="pitch-dot" style="background:var(--neutral)"></span> Neutral</div>`;
  if (mode === "pressure") return `
    <div class="pitch-legend-item"><span class="pitch-dot" style="background:var(--accent)"></span> Tackle</div>
    <div class="pitch-legend-item"><span class="pitch-dot" style="background:var(--neutral)"></span> Interception</div>
    <div class="pitch-legend-item"><span class="pitch-dot" style="background:var(--warning)"></span> Ball recovery</div>`;
  if (mode === "buildUp") return `<div class="pitch-legend-item"><span class="pitch-dot" style="background:var(--accent)"></span> Progressive action</div>`;
  if (mode === "formation") return `<div class="pitch-legend-item"><span style="background:var(--accent);border-radius:50%;width:10px;height:10px;display:inline-block"></span> Home</div><div class="pitch-legend-item"><span style="background:var(--neutral);border-radius:50%;width:10px;height:10px;display:inline-block"></span> Away</div>`;
  return "";
}

function pitchCoord(cx, cy, w, h, flip) {
  const x = (cx / 100) * (flip ? -1 : 1);
  const px = flip ? (1 - cx / 100) : x;
  return { x: px * w, y: (cy / 100) * h };
}

function drawMinimalPitch(ctx, w, h, isHalf) {
  ctx.fillStyle = getThemeColor("--pitch-bg") || "#0B0D0F";
  ctx.fillRect(0, 0, w, h);
  drawPitchLines(ctx, w, h, isHalf);
}

function drawPitchLines(ctx, w, h, isHalf) {
  ctx.strokeStyle = getThemeColor("--pitch-line") || "rgba(255,255,255,0.22)";
  ctx.lineWidth = 1;
  ctx.strokeRect(14, 14, w - 28, h - 28);

  ctx.beginPath();
  ctx.moveTo(w / 2, 14);
  ctx.lineTo(w / 2, h - 14);
  ctx.stroke();

  ctx.beginPath();
  ctx.arc(w / 2, h / 2, 54, 0, Math.PI * 2);
  ctx.stroke();

  ctx.fillStyle = getThemeColor("--pitch-line") || "rgba(255,255,255,0.35)";
  ctx.beginPath();
  ctx.arc(w / 2, h / 2, 2.5, 0, Math.PI * 2);
  ctx.fill();

  // Left Box (18-yard & 6-yard)
  ctx.strokeRect(14, h / 2 - 80, 100, 160);
  ctx.strokeRect(14, h / 2 - 36, 36, 72);
  ctx.beginPath();
  ctx.arc(14 + 68, h / 2, 2.5, 0, Math.PI * 2);
  ctx.fill();

  // Right Box (18-yard & 6-yard)
  ctx.strokeRect(w - 114, h / 2 - 80, 100, 160);
  ctx.strokeRect(w - 50, h / 2 - 36, 36, 72);
  ctx.beginPath();
  ctx.arc(w - 14 - 68, h / 2, 2.5, 0, Math.PI * 2);
  ctx.fill();

  // Penalty Arcs
  ctx.beginPath();
  ctx.arc(14 + 68, h / 2, 40, -0.9, 0.9);
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(w - 14 - 68, h / 2, 40, Math.PI - 0.9, Math.PI + 0.9);
  ctx.stroke();
}

function drawTierShotCircles(ctx, shots, w, h, options) {
  shots.forEach((s) => {
    const x = s.X * w;
    const y = (1 - s.Y) * h;
    const xg = Math.max(parseFloat(s.xG) || 0, 0.01);
    const r = Math.min(4 + Math.sqrt(xg) * 22, 24);
    const tier = classifyShotTier(xg);

    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fillStyle = tier.color;
    ctx.globalAlpha = 0.82;
    ctx.fill();
    ctx.globalAlpha = 1.0;

    if (s.result === "Goal") {
      ctx.beginPath();
      ctx.arc(x, y, r + 3.5, 0, Math.PI * 2);
      ctx.strokeStyle = getThemeColor("--text-bright") || "#ffffff";
      ctx.lineWidth = 2.5;
      ctx.stroke();
    } else {
      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.strokeStyle = getThemeColor("--border") || "rgba(0,0,0,0.5)";
      ctx.lineWidth = 1;
      ctx.stroke();
    }
  });
}

function drawGaussianHeatmap(ctx, shots, w, h) {
  if (!shots || !shots.length) return;

  const offCanvas = document.createElement("canvas");
  offCanvas.width = w;
  offCanvas.height = h;
  const offCtx = offCanvas.getContext("2d");

  shots.forEach((s) => {
    const x = s.X * w;
    const y = (1 - s.Y) * h;
    const xg = Math.max(parseFloat(s.xG) || 0.05, 0.05);
    const radius = 38 + xg * 28;

    const grad = offCtx.createRadialGradient(x, y, 0, x, y, radius);
    grad.addColorStop(0, `rgba(0,0,0,${Math.min(0.85, 0.35 + xg)})`);
    grad.addColorStop(1, "rgba(0,0,0,0)");

    offCtx.fillStyle = grad;
    offCtx.beginPath();
    offCtx.arc(x, y, radius, 0, Math.PI * 2);
    offCtx.fill();
  });

  const imgData = offCtx.getImageData(0, 0, w, h);
  const data = imgData.data;

  for (let i = 0; i < data.length; i += 4) {
    const alpha = data[i + 3];
    if (alpha > 0) {
      const norm = alpha / 255;
      let r = 0, g = 0, b = 0;
      if (norm < 0.25) {
        const t = norm / 0.25;
        r = Math.round(16 * t); g = Math.round(185 * t); b = Math.round(129 * t);
      } else if (norm < 0.55) {
        const t = (norm - 0.25) / 0.3;
        r = Math.round(16 + (56 - 16) * t);
        g = Math.round(185 + (189 - 185) * t);
        b = Math.round(129 + (248 - 129) * t);
      } else if (norm < 0.8) {
        const t = (norm - 0.55) / 0.25;
        r = Math.round(56 + (245 - 56) * t);
        g = Math.round(189 + (158 - 189) * t);
        b = Math.round(248 * (1 - t));
      } else {
        const t = (norm - 0.8) / 0.2;
        r = Math.round(245 + (244 - 245) * t);
        g = Math.round(158 * (1 - t * 0.75));
        b = Math.round(63 * (1 - t));
      }
      data[i] = r;
      data[i + 1] = g;
      data[i + 2] = b;
      data[i + 3] = Math.min(230, Math.round(alpha * 1.25));
    }
  }

  offCtx.putImageData(imgData, 0, 0);
  ctx.drawImage(offCanvas, 0, 0);
}

// ── Full pitch suite: passing / carries / possession / pressure / build-up / formation ──

// Formation string → slot grid (y 0=own goal, 100=opp goal). Returns array of {x,y} 0–100.
function formationSlots(formation, n) {
  const rows = String(formation || "4-3-3").split("-").map(Number);
  const slots = [];
  const totalRows = rows.length || 4;
  rows.forEach((count, rIdx) => {
    const rowY = 10 + (rIdx + 0.5) * (80 / totalRows);
    for (let i = 0; i < count; i++) {
      const x = ((i + 0.5) / count) * 100;
      slots.push({ x, y: rowY });
    }
  });
  // Top up to n with attackers pushed high (rare, defensive formations).
  for (let i = slots.length; i < n; i++) slots.push({ x: 50, y: 90 });
  return slots.slice(0, n);
}

// Normalize a lineup entry across both payload shapes:
//   Sofascore: { player: {id, name, …}, shirtNumber, statistics: {…} }
//   Understat: { player: "Name", position: "GK", positionOrder: "1", player_id, … }
function resolveRosterPlayer(p) {
  const embedded = p && typeof p.player === "object" && p.player !== null ? p.player : null;
  return {
    id: String((embedded && embedded.id) || (p && p.id) || (p && p.player_id) || ""),
    name: (embedded && embedded.name) || (p && typeof p.player === "string" && p.player) || (p && p.name) || "",
    position: (p && p.position) || (embedded && embedded.position) || "",
    number: p && p.shirtNumber != null ? p.shirtNumber : (p && p.positionOrder != null ? p.positionOrder : ""),
    rating: (p && p.rating) || (p && p.statistics && p.statistics.rating) || null,
    raw: p,
  };
}

// Derive a formation string ("4-3-3") from real player positions — never invent one.
function formationFromPositions(players) {
  const buckets = { def: 0, mid: 0, fwd: 0 };
  players.forEach((r) => {
    const pos = String(r.position || "").toUpperCase();
    if (/^(RB|DR|CB|DC|LB|DL)$/.test(pos)) buckets.def++;
    else if (/^(FW|ST|CF|FWL|FWR)$/.test(pos)) buckets.fwd++;
    else if (pos && pos !== "GK" && pos !== "SUB") buckets.mid++;
  });
  if (!buckets.def && !buckets.mid && !buckets.fwd) return null;
  return `${buckets.def}-${buckets.mid}-${buckets.fwd}`;
}

// Unified lineup view for the match screen, from whichever feed is live.
function matchLineupData(d, sofaData) {
  const sofaLineups = sofaData && sofaData.lineups && sofaData.lineups.data;
  if (sofaLineups) {
    const homePlayers = ((sofaLineups.home && sofaLineups.home.players) || []).map(resolveRosterPlayer);
    const awayPlayers = ((sofaLineups.away && sofaLineups.away.players) || []).map(resolveRosterPlayer);
    return {
      homePlayers,
      awayPlayers,
      homeFormation: (sofaLineups.home && sofaLineups.home.formation) || formationFromPositions(homePlayers),
      awayFormation: (sofaLineups.away && sofaLineups.away.formation) || formationFromPositions(awayPlayers),
      live: true,
    };
  }
  const bySlot = (list) => [...(list || [])]
    .sort((a, b) => (parseFloat(a.positionOrder) || 99) - (parseFloat(b.positionOrder) || 99))
    .map(resolveRosterPlayer);
  const homePlayers = bySlot(d.rosters && d.rosters.h);
  const awayPlayers = bySlot(d.rosters && d.rosters.a);
  return {
    homePlayers,
    awayPlayers,
    homeFormation: formationFromPositions(homePlayers.slice(0, 11)),
    awayFormation: formationFromPositions(awayPlayers.slice(0, 11)),
    live: false,
  };
}

// Build (lazy) per-player rating-breakdown for an event, cache in state, re-render.
async function buildSofaRatingBreakdown(containerId, data, options) {
  const sofa = data.sofa || options.sofascore || data;
  if (!sofa || !sofa.event_id) return;
  const eid = sofa.event_id;
  state.sofaRB = state.sofaRB || {};
  if (state.sofaRB[eid]) { renderPitchHeatmap(containerId, { ...data, rb: state.sofaRB[eid] }, options); return; }

  const lineups = (sofa.lineups && sofa.lineups.data) || null;
  const players = [];
  if (lineups) {
    ["home", "away"].forEach((side) => {
      (lineups[side] && lineups[side].players || []).forEach((p) => {
        const pid = (p.player && p.player.id) || p.id;
        if (pid) players.push({ pid, name: (p.player && p.player.name) || p.name, side });
      });
    });
  }
  if (!players.length) return;

  const node = document.getElementById(containerId);
  if (node) { const e = node.querySelector(".pitch-empty"); if (e) e.innerHTML = `<div class="empty-state">Building passing network — fetching ${players.length} players at ~1 req/s…</div>`; }

  const rb = { actions: [], byPlayer: [] };
  let i = 0;
  for (const pl of players) {
    try {
      const res = await api(`/api/v1/sofascore/event/${eid}/player/${pl.pid}/rating-breakdown`, null, "GET");
      if (res && res.all_actions) {
        (res.all_actions || []).forEach((a) => rb.actions.push({ ...a, playerName: pl.name, side: pl.side }));
      }
    } catch (_) { /* skip failed player */ }
    i++;
    if (i % 5 === 0 && node) { const e = node.querySelector(".pitch-empty"); if (e) e.innerHTML = `<div class="empty-state">Building passing network — ${i}/${players.length} players…</div>`; }
  }
  state.sofaRB[eid] = rb;
  renderPitchHeatmap(containerId, { ...data, rb }, options);
}

function rbPoint(pt) {
  if (!pt) return null;
  const x = pt.pitch_x != null ? pt.pitch_x : (pt.x != null ? pt.x : null);
  const y = pt.pitch_y != null ? pt.pitch_y : (pt.y != null ? pt.y : null);
  if (x == null || y == null) return null;
  return { x: Number(x), y: Number(y) };
}

function drawPassingNetwork(ctx, rb, lineups, w, h) {
  if (!rb || !rb.actions || !rb.actions.length) return;
  const homeSlot = formationSlots((lineups && lineups.home && lineups.home.formation) || "4-3-3", 11);
  const awaySlot = formationSlots((lineups && lineups.away && lineups.away.formation) || "4-3-3", 11);
  const homeNames = lineups && lineups.home ? (lineups.home.players || []).map((p) => (p.player && p.player.name) || p.name) : [];
  const awayNames = lineups && lineups.away ? (lineups.away.players || []).map((p) => (p.player && p.player.name) || p.name) : [];
  const nodeFor = (name) => {
    const hi = homeNames.findIndex((n) => String(n) === String(name));
    if (hi >= 0 && homeSlot[hi]) return homeSlot[hi];
    const ai = awayNames.findIndex((n) => String(n) === String(name));
    if (ai >= 0 && awaySlot[ai]) return awaySlot[ai];
    return null;
  };
  const accent = getThemeColor("--accent") || "#1ed760";
  const lineColor = getThemeColor("--border-hover") || "#3A414A";
  const passes = rb.actions.filter((a) => a.playerCoordinates && a.passEndCoordinates);
  ctx.strokeStyle = lineColor; ctx.lineWidth = 1;
  let drawn = 0;
  const seen = new Set();
  passes.forEach((a) => {
    const from = rbPoint(a.playerCoordinates), to = rbPoint(a.passEndCoordinates);
    if (!from || !to) return;
    const nf = nodeFor(a.playerName);
    let fx = from.x / 100 * w, fy = from.y / 100 * h;
    let tx = to.x / 100 * w, ty = to.y / 100 * h;
    if (nf) { fx = nf.x / 100 * w; fy = nf.y / 100 * h; }
    const key = `${Math.round(fx)},${Math.round(fy)}>${Math.round(tx)},${Math.round(ty)}`;
    if (seen.has(key)) return; seen.add(key);
    ctx.globalAlpha = Math.min(0.35 + drawn * 0.01, 0.8);
    ctx.beginPath(); ctx.moveTo(fx, fy); ctx.lineTo(tx, ty); ctx.stroke();
    ctx.globalAlpha = 1;
    drawn++;
  });
  // Draw player nodes.
  ctx.font = "bold 9px var(--mono, monospace)"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
  homeSlot.forEach((s) => { const x = s.x / 100 * w, y = s.y / 100 * h; ctx.beginPath(); ctx.arc(x, y, 4, 0, Math.PI * 2); ctx.fillStyle = accent; ctx.fill(); });
  awaySlot.forEach((s) => { const x = (100 - s.x) / 100 * w, y = s.y / 100 * h; ctx.beginPath(); ctx.arc(x, y, 4, 0, Math.PI * 2); ctx.fillStyle = getThemeColor("--neutral") || "#38bdf8"; ctx.fill(); });
}

function drawCarries(ctx, rb, w, h, isHalf) {
  if (!rb || !rb.actions || !rb.actions.length) return;
  const accent = getThemeColor("--accent") || "#1ed760";
  const carries = rb.actions.filter((a) => a.eventActionType === "ball-carries" || (a.playerCoordinates && a.isHome !== undefined));
  ctx.lineWidth = 2;
  let drawn = 0;
  carries.slice(0, 80).forEach((a) => {
    const from = rbPoint(a.playerCoordinates), to = rbPoint(a.passEndCoordinates);
    const origin = from || to; if (!origin) return;
    const x = origin.x / 100 * w, y = origin.y / 100 * h;
    const dist = to ? Math.hypot((to.x - origin.x) / 100 * w, (to.y - origin.y) / 100 * h) : 10 + Math.random() * 20;
    const ang = to ? Math.atan2((to.y - origin.y) / 100 * h, (to.x - origin.x) / 100 * w) : 0;
    const len = Math.min(Math.max(dist, 8), 42);
    ctx.strokeStyle = accent; ctx.globalAlpha = 0.5 + Math.min(drawn * 0.008, 0.5);
    ctx.beginPath(); ctx.moveTo(x, y);
    const ex = x + Math.cos(ang) * len, ey = y + Math.sin(ang) * len;
    ctx.lineTo(ex, ey); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(ex, ey); ctx.lineTo(ex - Math.cos(ang - 0.5) * 6, ey - Math.sin(ang - 0.5) * 6); ctx.stroke();
    ctx.globalAlpha = 1;
    drawn++;
  });
}

function drawPossession(ctx, sofa, w, h, isHalf) {
  // Territory zones from match statistics (finalThirdEntries / touchesInOppBox).
  if (!sofa || !sofa.statistics || !sofa.statistics.data) return;
  const period = (sofa.statistics.data[0] || {}); const groups = period.groups || [];
  const stat = (key) => { for (const g of groups) { const it = (g.statisticsItems || []).find((it) => it.key === key); if (it) return it; } return null; };
  const fte = stat("finalThirdEntries"), touches = stat("touchesInOppBox"), poss = stat("ballPossession");
  const homeVal = (v) => parseFloat(v != null ? (v.homeValue != null ? v.homeValue : v.home) : 0) || 0;
  const awayVal = (v) => parseFloat(v != null ? (v.awayValue != null ? v.awayValue : v.away) : 0) || 0;
  const hFTE = fte ? homeVal(fte) : 0, aFTE = fte ? awayVal(fte) : 0;
  const hT = touches ? homeVal(touches) : 0, aT = touches ? awayVal(touches) : 0;
  const total = Math.max(hFTE + aFTE, 1);
  const hTilt = hFTE / total;
  const accent = getThemeColor("--accent") || "#1ed760";
  const neutral = getThemeColor("--neutral") || "#38bdf8";
  // Left/centre high-zone fill: proportional to home territory.
  const g = ctx.createLinearGradient(0, 0, w, 0);
  g.addColorStop(0, `${accent}26`); g.addColorStop(hTilt, `${accent}26`); g.addColorStop(hTilt, `${neutral}18`); g.addColorStop(1, `${neutral}18`);
  ctx.fillStyle = g; ctx.fillRect(14, 14, w - 28, h - 28);
  // Tilt bar in the header area.
  if (poss) {
    ctx.fillStyle = getThemeColor("--panel-2") || "#171B1F"; ctx.fillRect(14, 2, w - 28, 8);
    const hp = homeVal(poss), ap = awayVal(poss), sum = Math.max(hp + ap, 1);
    ctx.fillStyle = accent; ctx.fillRect(14, 2, (w - 28) * (hp / sum), 8);
    ctx.fillStyle = neutral; ctx.fillRect(14 + (w - 28) * (hp / sum), 2, (w - 28) * (ap / sum), 8);
  }
}

function drawPressure(ctx, rb, w, h, isHalf) {
  if (!rb || !rb.actions || !rb.actions.length) return;
  const accent = getThemeColor("--accent") || "#1ed760";
  const neutral = getThemeColor("--neutral") || "#38bdf8";
  const warning = getThemeColor("--warning") || "#f59e0b";
  const defensive = rb.actions.filter((a) => (a.eventActionType || "").includes("defensive") || a.playerCoordinates);
  defensive.slice(0, 120).forEach((a) => {
    const pt = rbPoint(a.playerCoordinates); if (!pt) return;
    const x = pt.x / 100 * w, y = pt.y / 100 * h;
    const type = a.eventActionType || "";
    const color = type.includes("tackle") ? accent : type.includes("interception") ? neutral : warning;
    ctx.beginPath(); ctx.arc(x, y, 3.5, 0, Math.PI * 2); ctx.fillStyle = color; ctx.globalAlpha = 0.75; ctx.fill(); ctx.globalAlpha = 1;
  });
}

function drawBuildUp(ctx, rb, w, h, isHalf) {
  if (!rb || !rb.actions || !rb.actions.length) return;
  const accent = getThemeColor("--accent") || "#1ed760";
  const actions = rb.actions.filter((a) => a.playerCoordinates && (a.eventActionType || "").includes("pass") || (a.keyPass || a.keypass));
  ctx.lineWidth = 1.5;
  actions.slice(0, 60).forEach((a) => {
    const from = rbPoint(a.playerCoordinates); if (!from) return;
    const to = rbPoint(a.passEndCoordinates);
    const x = from.x / 100 * w, y = from.y / 100 * h;
    ctx.strokeStyle = accent; ctx.globalAlpha = 0.55;
    ctx.beginPath(); ctx.moveTo(x, y);
    if (to) ctx.lineTo(to.x / 100 * w, to.y / 100 * h);
    else { const ang = Math.random() * Math.PI * 2; ctx.lineTo(x + Math.cos(ang) * 20, y + Math.sin(ang) * 20); }
    ctx.stroke(); ctx.globalAlpha = 1;
  });
}

function drawFormationDots(ctx, lineups, w, h) {
  if (!lineups) return;
  const accent = getThemeColor("--accent") || "#1ed760";
  const neutral = getThemeColor("--neutral") || "#38bdf8";
  const drawSide = (side, slot, flip) => {
    const players = (lineups[side] && lineups[side].players) || [];
    const formation = (lineups[side] && lineups[side].formation) || "4-3-3";
    const slots = formationSlots(formation, 11);
    ctx.font = "bold 9px var(--mono, monospace)"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    players.slice(0, 11).forEach((p, i) => {
      const s = slots[i] || { x: 50, y: 50 };
      const x = flip ? (1 - s.x / 100) * w : s.x / 100 * w;
      const y = s.y / 100 * h;
      const num = p.shirtNumber || i + 1;
      ctx.beginPath(); ctx.arc(x, y, 11, 0, Math.PI * 2); ctx.fillStyle = getThemeColor("--panel-3") || "#1e2328"; ctx.fill();
      ctx.strokeStyle = flip ? neutral : accent; ctx.lineWidth = 2; ctx.stroke();
      ctx.fillStyle = flip ? neutral : accent; ctx.fillText(String(num), x, y);
      const name = ((p.player && p.player.name) || p.name || "").split(" ").pop();
      ctx.fillStyle = getThemeColor("--text-bright") || "#F3F5F7"; ctx.font = "bold 9px var(--sans, sans-serif)";
      ctx.fillText(name, x, y + 17);
    });
  };
  drawSide("home", null, false);
  drawSide("away", null, true);
}

// ==========================================================
// IMAGE 4: MATCH TACTICAL BOARD, SOFASCORE & LINEUPS
// ==========================================================
function matchPossessionSplit(sofaData, home, away) {
  const stats = sofaData && sofaData.statistics && sofaData.statistics.data;
  if (!stats) return "";
  const period = stats[0] || {};
  const groups = period.groups || [];
  let possVal = null;
  for (const g of groups) {
    const it = (g.statisticsItems || []).find((it) => it.key === "ballPossession");
    if (it) { possVal = it; break; }
  }
  if (!possVal) return "";
  const homeVal = parseFloat(possVal.homeValue != null ? possVal.homeValue : possVal.home) || 0;
  const awayVal = parseFloat(possVal.awayValue != null ? possVal.awayValue : possVal.away) || 0;
  const sum = Math.max(homeVal + awayVal, 1);
  const hp = (homeVal / sum) * 100, ap = (awayVal / sum) * 100;
  return `
    <div class="possession-split">
      <div class="possession-split-label">
        <span style="color:var(--accent);font-weight:800">${home}</span>
        <span style="font-family:var(--mono);font-size:12px;color:var(--muted)">Possession ${Math.round(homeVal)}%</span>
        <span style="font-family:var(--mono);font-size:12px;color:var(--muted)">${Math.round(awayVal)}%</span>
        <span style="color:var(--neutral);font-weight:800">${away}</span>
      </div>
      <div class="possession-split-bar">
        <div class="possession-seg home" style="width:${hp}%"></div>
        <div class="possession-seg away" style="width:${ap}%"></div>
      </div>
    </div>
  `;
}

function renderMatchTacticalBoard(d, sofascoreData = null, lineup = null) {
  const home = (d.meta && d.meta.home) || "Home Team";
  const away = (d.meta && d.meta.away) || "Away Team";
  const scoreline = d.narrative && d.narrative.scoreline ? d.narrative.scoreline : {};
  const homeScore = scoreline.h ?? "0";
  const awayScore = scoreline.a ?? "0";

  lineup = lineup || matchLineupData(d, sofascoreData);
  const { homePlayers, awayPlayers, live } = lineup;
  const homeFormation = lineup.homeFormation || "—";
  const awayFormation = lineup.awayFormation || "—";

  const playerRow = (pl, i, side) => `
    <div class="chip-player-row" style="cursor:pointer" onclick="inspectMatchPlayer('${pl.id || i}', '${side}')">
      <span class="chip-num">${pl.number || i + 1}</span>
      <div style="flex:1;min-width:0">
        <div style="font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${escapeHtml(pl.name || "Unknown")}</div>
        <div style="font-size:10.5px;color:var(--muted)">${pl.position || "—"} ${pl.rating ? `· <span style="color:var(--accent);font-weight:800">⭐ ${fmt(pl.rating, 1)}</span>` : ""}</div>
      </div>
    </div>
  `;

  return `
    <div class="card" style="margin-top:20px">
      <div class="card-header">
        <div class="section-question">
          <span class="question-title">Tactical Formation & Lineup Board</span>
          <span class="question-desc">Starting formations, player positions, and interactive deep scouting</span>
        </div>
        ${live ? `<span class="hero-pill accent">⚡ Live Sofascore Feed</span>` : `<span class="hero-pill">${homeFormation !== "—" ? "Understat Lineups · formation from positions" : "Understat Lineups"}</span>`}
      </div>

      <!-- Cross-Match Formation Header -->
      <div class="chip-pitch-header">
        <div class="chip-team-badge">
          <div class="mr-initials home">${initials(home)}</div>
          <div>
            <div style="font-size:14px;font-weight:800;color:var(--text-bright)">${escapeHtml(home)}</div>
            <div class="chip-formation">${homeFormation}</div>
          </div>
        </div>
        <div style="text-align:center">
          <div style="font-family:var(--mono);font-size:26px;font-weight:900;color:var(--text-bright)">${homeScore} : ${awayScore}</div>
          <div style="font-size:11px;color:var(--muted)">Full Time</div>
        </div>
        <div class="chip-team-badge" style="flex-direction:row-reverse;text-align:right">
          <div class="mr-initials away">${initials(away)}</div>
          <div>
            <div style="font-size:14px;font-weight:800;color:var(--text-bright)">${escapeHtml(away)}</div>
            <div class="chip-formation">${awayFormation}</div>
          </div>
        </div>
      </div>

      <!-- Possession Split Bar (real from Sofascore statistics) -->
      ${matchPossessionSplit(sofascoreData, home, away)}

      <!-- Tactical Pitch Grid (Left Lineup · Dotted Pitch · Right Lineup) -->
      <div class="chip-pitch-grid">
        <div class="chip-lineup">
          <div class="chip-lineup-title">${escapeHtml(home)} Lineup</div>
          ${homePlayers.slice(0, 11).map((pl, i) => playerRow(pl, i, "home")).join("")}
        </div>

        <div class="chip-pitch-wrap">
          <canvas id="dottedPitchCanvas" width="600" height="400" style="width:100%;height:400px;background:var(--pitch-bg);border:1px solid var(--border);border-radius:var(--radius-md)"></canvas>
          <div id="dottedPitchOverlay"></div>
        </div>

        <div class="chip-lineup">
          <div class="chip-lineup-title">${escapeHtml(away)} Lineup</div>
          ${awayPlayers.slice(0, 11).map((pl, i) => playerRow(pl, i, "away")).join("")}
        </div>
      </div>
    </div>
  `;
}

function drawDottedTacticalPitch(homePlayers, awayPlayers, homeFormation, awayFormation) {
  const canvas = document.getElementById("dottedPitchCanvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width, h = canvas.height;

  drawMinimalPitch(ctx, w, h, false);

  const drawChip = (pl, slotX, slotY, colorVar) => {
    const x = (slotX / 100) * w;
    const y = (slotY / 100) * h;
    ctx.beginPath();
    ctx.arc(x, y, 12, 0, Math.PI * 2);
    ctx.fillStyle = getThemeColor("--panel-3") || "#1e2328";
    ctx.fill();
    ctx.strokeStyle = getThemeColor(colorVar) || "#1ed760";
    ctx.lineWidth = 2;
    ctx.stroke();

    ctx.fillStyle = getThemeColor(colorVar) || "#1ed760";
    ctx.font = "bold 10px var(--mono, monospace)";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    if (pl.number !== "" && pl.number != null) ctx.fillText(String(pl.number), x, y);

    if (pl.name) {
      ctx.fillStyle = getThemeColor("--text-bright") || "#F3F5F7";
      ctx.font = "bold 9px var(--sans, sans-serif)";
      ctx.fillText(pl.name.split(" ").pop(), x, y + 18);
    }
  };

  // Home occupies its own half (slots y: own goal → opponent goal).
  const homeSlots = formationSlots(homeFormation || "4-3-3", Math.min(homePlayers.length, 11));
  homePlayers.slice(0, 11).forEach((pl, i) => {
    const s = homeSlots[i] || { x: 50, y: 50 };
    drawChip(pl, s.x, s.y, "--accent");
  });

  // Away mirrored onto the opposite half so the two sides never overlap.
  const awaySlots = formationSlots(awayFormation || "4-3-3", Math.min(awayPlayers.length, 11));
  awayPlayers.slice(0, 11).forEach((pl, i) => {
    const s = awaySlots[i] || { x: 50, y: 50 };
    drawChip(pl, 100 - s.x, 100 - s.y, "--neutral");
  });
}

// Interactive Player Drawer from Lineup Chip Click
window.inspectMatchPlayer = function(playerId, side) {
  const d = state.activeMatchData;
  const sofa = state.activeMatchSofascore;
  if (!d) return;

  let raw = null;
  const sofaLineups = sofa && sofa.lineups && sofa.lineups.data;
  if (sofaLineups && sofaLineups[side] && sofaLineups[side].players) {
    raw = sofaLineups[side].players.find(p => String((p.player && p.player.id) || p.id) === String(playerId));
  }
  if (!raw && d.rosters && d.rosters[side === 'home' ? 'h' : 'a']) {
    const list = d.rosters[side === 'home' ? 'h' : 'a'];
    raw = list.find((p) => String(p.player_id) === String(playerId)) || list[parseInt(playerId, 10)];
  }
  if (!raw) return;

  const r = resolveRosterPlayer(raw);
  const player = raw;
  const stats = player.statistics || {};
  const name = r.name || "Unknown Player";

  let drawer = $("playerDrawerModal");
  if (!drawer) {
    drawer = document.createElement("div");
    drawer.id = "playerDrawerModal";
    drawer.className = "player-drawer-overlay";
    document.body.appendChild(drawer);
  }

  drawer.innerHTML = `
    <div class="player-drawer">
      <button class="drawer-close" onclick="$('playerDrawerModal').remove()">✕</button>
      <div style="display:flex;align-items:center;gap:16px;margin-bottom:18px">
        <div class="hero-avatar" style="width:48px;height:48px;font-size:18px">${name.split(" ").map(w=>w[0]).slice(0,2).join("")}</div>
        <div>
          <h3 style="font-size:20px;font-weight:900;color:var(--text-bright);margin:0">${name}</h3>
          <div style="font-size:12px;color:var(--muted);margin-top:2px">
            #${r.number !== "" && r.number != null ? r.number : "—"} · ${r.position || "—"} · ${side === 'home' ? ((d.meta && d.meta.home) || "Home") : ((d.meta && d.meta.away) || "Away")}
          </div>
        </div>
        ${stats.rating ? `
          <div style="margin-left:auto;text-align:right">
            <span style="font-size:24px;font-weight:900;color:var(--accent);font-family:var(--mono)">⭐ ${fmt(stats.rating, 1)}</span>
            <div style="font-size:10.5px;color:var(--muted)">Sofascore Rating</div>
          </div>
        ` : ""}
      </div>

      <!-- Granular 4-Quadrant Rating Breakdown -->
      <div class="rating-quads">
        <div class="rating-quad">
          <div class="rating-quad-title">Passing & Creation</div>
          <div class="rating-quad-score">${stats.accuratePass || player.key_passes || 0} / ${stats.totalPass || player.shots || 0}</div>
          <div style="font-size:10.5px;color:var(--muted)">${stats.keyPass || 0} Key Passes · ${fmt(stats.expectedAssists || player.xA, 2)} xA</div>
        </div>
        <div class="rating-quad">
          <div class="rating-quad-title">Finishing & Threat</div>
          <div class="rating-quad-score">${stats.goals || player.goals || 0} G · ${fmt(stats.expectedGoals || player.xG, 2)} xG</div>
          <div style="font-size:10.5px;color:var(--muted)">${stats.totalShots || player.shots || 0} Shots (${stats.onTargetScoringAttempt || 0} on target)</div>
        </div>
        <div class="rating-quad">
          <div class="rating-quad-title">Duels & Physicality</div>
          <div class="rating-quad-score">${stats.duelWon || 0} / ${(stats.duelWon||0) + (stats.duelLost||0)}</div>
          <div style="font-size:10.5px;color:var(--muted)">${stats.wonContest || 0} Dribbles · ${stats.aerialWon || 0} Aerials</div>
        </div>
        <div class="rating-quad">
          <div class="rating-quad-title">Defensive Regains</div>
          <div class="rating-quad-score">${stats.totalTackle || 0} Tackles</div>
          <div style="font-size:10.5px;color:var(--muted)">${stats.interceptionWon || 0} Interceptions · ${stats.ballRecovery || 0} Recoveries</div>
        </div>
      </div>

      <!-- Full Player Statistics Table -->
      <table style="margin-top:18px">
        <thead><tr><th>Metric Category</th><th class="num">Match Count</th><th>Context / Interpretation</th></tr></thead>
        <tbody>
          <tr><td>Minutes Played</td><td class="num"><strong>${stats.minutesPlayed || player.time || 0}'</strong></td><td style="color:var(--muted)">Match participation</td></tr>
          <tr><td>Total Ball Carries Distance</td><td class="num"><strong>${stats.totalBallCarriesDistance ? `${stats.totalBallCarriesDistance}m` : "—"}</strong></td><td style="color:var(--muted)">Progression: ${stats.progressiveBallCarriesCount || 0} carries</td></tr>
          <tr><td>Top Speed / Sprints</td><td class="num"><strong>${stats.topSpeed ? `${stats.topSpeed} km/h` : "—"}</strong></td><td style="color:var(--muted)">${stats.numberOfSprints || 0} sprints recorded</td></tr>
          <tr><td>xGOT (xG on Target)</td><td class="num"><strong>${fmt(stats.expectedGoalsOnTarget)}</strong></td><td style="color:var(--muted)">Post-shot placement quality</td></tr>
          <tr><td>Big Chances Created / Missed</td><td class="num"><strong>${stats.bigChanceCreated || 0} / ${stats.bigChanceMissed || 0}</strong></td><td style="color:var(--muted)">High probability box chances</td></tr>
          <tr><td>Touches / Possession Lost</td><td class="num"><strong>${stats.touches || 0} / ${stats.possessionLostCtrl || 0}</strong></td><td style="color:var(--muted)">Turnover rate</td></tr>
        </tbody>
      </table>

      <div style="margin-top:16px;text-align:right">
        <button class="primary" onclick="$('playerName').value='${name.replace(/'/g, "\\'")}';$('playerDrawerModal').remove();activateTab('player');runPlayer()">
          Open Full Career Scouting Report →
        </button>
      </div>
    </div>
  `;
};

// ==========================================================
// 7-CATEGORY SOFASCORE MATCH STATISTICS TABLE
// ==========================================================
function renderSofascoreStatsSections(statsData, homeName, awayName) {
  if (!statsData || !statsData.data || !Array.isArray(statsData.data)) return "";
  const period = statsData.data[0] || {}; // Period 0 = All
  const groups = period.groups || [];
  if (!groups.length) return "";

  return `
    <div class="card" style="margin-top:20px">
      <div class="card-header">
        <div class="section-question">
          <span class="question-title">7-Category Sofascore Tactical Match Statistics</span>
          <span class="question-desc">Detailed comparison across Overview, Shots, Attack, Passes, Duels, Defending, and Goalkeeping</span>
        </div>
        <span class="hero-pill accent">⚡ Official Match Engine</span>
      </div>

      <div class="sofa-stats-grid">
        ${groups.map((g) => `
          <div class="sofa-stat-box">
            <div class="sofa-stat-title">
              <span>${g.groupName}</span>
              <span style="font-size:10px;color:var(--muted)">${homeName} vs ${awayName}</span>
            </div>
            ${(g.statisticsItems || []).map((item) => {
              const hVal = item.home ?? item.homeValue ?? "—";
              const aVal = item.away ?? item.awayValue ?? "—";
              const hNum = parseFloat(hVal) || 0;
              const aNum = parseFloat(aVal) || 0;
              const sum = Math.max(hNum + aNum, 1);
              const hPct = (hNum / sum) * 100;
              const aPct = (aNum / sum) * 100;
              return `
                <div class="sofa-stat-row">
                  <span class="sofa-stat-val-h">${hVal}</span>
                  <span class="sofa-stat-label">${item.name}</span>
                  <span class="sofa-stat-val-a">${aVal}</span>
                </div>
                <div class="sofa-bar-compare">
                  <div class="sofa-bar-h" style="width:${hPct}%"></div>
                  <div class="sofa-bar-a" style="width:${aPct}%"></div>
                </div>
              `;
            }).join("")}
          </div>
        `).join("")}
      </div>
    </div>
  `;
}

// Chronological Incidents Timeline
function renderMatchIncidents(incidentsData) {
  if (!incidentsData || !incidentsData.data || !Array.isArray(incidentsData.data)) return "";
  const list = incidentsData.data;
  if (!list.length) return "";

  // Match-flow timeline: 0'→90' bar with goal/card/sub markers.
  const maxMin = Math.max(...list.map((inc) => (Number(inc.minute) || Number(inc.time) || 0)), 90);
  const marker = (inc, side) => {
    const min = Number(inc.minute) || Number(inc.time) || 0;
    const pos = Math.min(Math.max((min / maxMin) * 100, 2), 98);
    let color = "var(--neutral)", glyph = "•";
    if (inc.incidentType === "goal") { color = "var(--accent)"; glyph = "●"; }
    else if (inc.incidentType === "card" && inc.incidentClass === "yellow") { color = "var(--warning)"; glyph = "■"; }
    else if (inc.incidentType === "card" && inc.incidentClass === "red") { color = "var(--fg-bad)"; glyph = "■"; }
    else if (inc.incidentType === "substitution") { color = "var(--neutral)"; glyph = "▲"; }
    return `<span class="flow-marker" style="left:${pos}%;color:${color}" title="${min}' · ${inc.incidentType || "event"}${(inc.player && inc.player.name) ? " — " + inc.player.name : ""}">${glyph}</span>`;
  };
  const homeMarkers = list.filter((inc) => inc.isHome !== false).map((inc) => marker(inc, "home")).join("");
  const awayMarkers = list.filter((inc) => inc.isHome === false).map((inc) => marker(inc, "away")).join("");

  return `
    <div class="card" style="margin-top:20px">
      <div class="card-header">
        <div class="section-question">
          <span class="question-title">Match Flow — 0' to 90'</span>
          <span class="question-desc">Goals, substitutions, bookings, penalties, and VAR decisions</span>
        </div>
      </div>
      <div class="match-flow">
        <div class="match-flow-track">
          <div class="match-flow-lane">
            <span class="flow-lane-label">Home</span>
            <div class="flow-lane-bar">${homeMarkers}</div>
          </div>
          <div class="match-flow-axis">
            <span>0'</span>
            <span>45'</span>
            <span>90'</span>
          </div>
          <div class="match-flow-lane">
            <span class="flow-lane-label">Away</span>
            <div class="flow-lane-bar">${awayMarkers}</div>
          </div>
        </div>
      </div>
      <div style="max-height:340px;overflow-y:auto;margin-top:14px;border-top:1px solid var(--border);padding-top:8px">
        ${list.map((inc) => {
          const min = inc.time ? `${inc.time}'` : inc.minute ? `${inc.minute}'` : "—";
          const icon = inc.incidentType === "goal" ? "⚽" : inc.incidentType === "card" && inc.incidentClass === "yellow" ? "🟨" : inc.incidentType === "card" && inc.incidentClass === "red" ? "🟥" : inc.incidentType === "substitution" ? "🔄" : "⚡";
          const player = (inc.player && inc.player.name) || inc.playerName || "";
          const detail = inc.text || inc.description || (inc.incidentType === 'goal' ? `Score: ${inc.homeScore || 0}–${inc.awayScore || 0}` : "");
          return `
            <div class="incident-row">
              <span class="incident-min">${min}</span>
              <span class="incident-icon">${icon}</span>
              <div class="incident-main">
                <span class="incident-player">${player}</span>
                <span class="incident-detail">${detail ? ` · ${detail}` : ""}</span>
              </div>
              <span style="font-size:11px;color:var(--muted);text-transform:capitalize">${inc.incidentType || ""}</span>
            </div>
          `;
        }).join("")}
      </div>
    </div>
  `;
}

// ==========================================================
// MATCH DEEP-DIVE & AUTOMATIC RECENT FIXTURES
// ==========================================================
$("matchGo").addEventListener("click", () => runMatch());
$("roundSelect").addEventListener("change", populateMatchesForRound);
$("matchSelect").addEventListener("change", () => {
  const mid = $("matchSelect").value;
  if (mid) loadMatchById(mid);
});
$("matchId").addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    const mid = $("matchId").value.trim();
    if (mid) loadMatchById(mid);
  }
});

async function loadRounds() {
  const season = seasonOf("matchSeason");
  const key = `${state.league}_${season}`;
  if (state.roundsLoadedFor === key && state.roundsData) {
    renderMatchMode();
    return;
  }

  if ($("fixtureCountBadge")) $("fixtureCountBadge").textContent = "Loading…";
  if ($("roundSelect")) $("roundSelect").innerHTML = `<option value="">Loading rounds…</option>`;
  if ($("matchRecentFeed")) $("matchRecentFeed").innerHTML = `<div class="loading"><div class="loading-pulse"><span></span><span></span><span></span></div><span>Loading matches for ${LEAGUE_LABEL[state.league] || state.league} ${season}…</span></div>`;

  try {
    const d = await api("/api/v1/matches/rounds", { league_name: state.league, season });
    state.roundsData = d;
    state.roundsLoadedFor = key;

    if ($("fixtureCountBadge")) $("fixtureCountBadge").textContent = `${d.n_played} Played`;

    renderMatchMode();

    const rounds = d.rounds || [];
    if (rounds.length) {
      $("roundSelect").innerHTML = rounds.map((r) => `<option value="${r.round}">Round ${r.round}</option>`).join("");
      const latestRound = rounds[rounds.length - 1];
      $("roundSelect").value = String(latestRound.round);
      populateMatchesForRound();

      if (!state.activeMatchData && d.latest_matches && d.latest_matches.length) {
        const first = d.latest_matches[0];
        loadMatchById(first.id || first.match_id);
      }
    } else {
      $("roundSelect").innerHTML = `<option value="">No rounds found</option>`;
      $("matchSelect").innerHTML = `<option value="">—</option>`;
    }
  } catch (e) {
    if ($("matchRecentFeed")) $("matchRecentFeed").innerHTML = `<div class="error">Failed to load fixtures: ${e.message}</div>`;
    if ($("roundSelect")) $("roundSelect").innerHTML = `<option value="">Error loading rounds</option>`;
  }
}

function renderMatchMode() {
  const toggle = $("matchModeToggle");
  if (toggle) {
    toggle.innerHTML = `
      <button class="ghost ${state.matchMode === 'recent' ? 'active' : ''}" style="padding:4px 10px;font-size:11px" onclick="setMatchMode('recent')">Recent Matches</button>
      <button class="ghost ${state.matchMode === 'board' ? 'active' : ''}" style="padding:4px 10px;font-size:11px" onclick="setMatchMode('board')">Gameweek Board</button>
    `;
  }
  if (state.matchMode === "board") {
    renderGameweekBoard(state.roundsData);
  } else {
    renderRecentFixtures(state.roundsData);
  }
}

window.setMatchMode = function(mode) {
  state.matchMode = mode;
  renderMatchMode();
};

window.selectBoardRound = function(r) {
  state.boardRound = r;
  if ($("roundSelect")) {
    $("roundSelect").value = String(r);
    populateMatchesForRound();
  }
  renderGameweekBoard(state.roundsData);
};

function renderGameweekBoard(d) {
  const feed = $("matchRecentFeed");
  if (!feed || !d) return;
  const rounds = d.rounds || [];
  if (!rounds.length) {
    feed.innerHTML = `<div class="empty" style="padding:28px 16px;grid-column:1/-1">No gameweek data available for this season.</div>`;
    return;
  }

  const pills = rounds.map((r) => `
    <button class="ghost ${r.round === state.boardRound ? 'active' : ''}" style="padding:3px 8px;font-size:11px;border-radius:4px" onclick="selectBoardRound(${r.round})">
      R${r.round}
    </button>
  `).join("");

  const round = rounds.find((x) => x.round === state.boardRound) || rounds[rounds.length - 1];
  const matches = (round && round.matches) || [];

  feed.innerHTML = `
    <div style="grid-column:1/-1;display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px">
      ${pills}
    </div>
    ${matches.map((m) => {
      const matchId = m.id || m.match_id;
      const hg = m.home_goals ?? m.home_score ?? "—";
      const ag = m.away_goals ?? m.away_score ?? "—";
      const homeWinner = hg > ag;
      const awayWinner = ag > hg;
      return `
        <div class="fixture-card" data-match-id="${matchId}" onclick="loadMatchById('${matchId}')">
          <div class="fixture-top">
            <span>Round ${round.round} · ${m.date}</span>
            <span class="badge ${hg !== '—' ? 'good' : ''}">FT</span>
          </div>
          <div class="fixture-teams">
            <div class="fixture-team-row ${homeWinner ? 'winner' : ''}">
              <span>${m.home}</span>
              <span class="fixture-score">${hg}</span>
            </div>
            <div class="fixture-team-row ${awayWinner ? 'winner' : ''}">
              <span>${m.away}</span>
              <span class="fixture-score">${ag}</span>
            </div>
          </div>
          <div class="fixture-footer">
            <span class="fixture-xg-badge">xG: ${fmt(m.home_xg)} — ${fmt(m.away_xg)}</span>
            <span style="color:var(--accent);font-weight:700">Deep Dive →</span>
          </div>
        </div>
      `;
    }).join("")}
  `;
}

function renderRecentFixtures(d) {
  const feed = $("matchRecentFeed");
  if (!feed) return;
  const recent = (d && d.latest_matches) || [];
  const currentSeason = seasonOf("matchSeason");

  if (!recent.length) {
    feed.innerHTML = `
      <div class="empty" style="padding:28px 16px;grid-column:1/-1">
        <div class="empty-title">${LEAGUE_LABEL[state.league] || state.league} ${currentSeason} Fixtures Not Started Yet</div>
        <div class="empty-sub">No completed matches have been recorded yet for the ${currentSeason} season on Understat.</div>
        <div style="margin-top:14px">
          <button class="primary" onclick="$('matchSeason').value='${currentSeason - 1}';$('matchSeason').dispatchEvent(new Event('change'))">
            View Previous Season (${currentSeason - 1}) Matches →
          </button>
        </div>
      </div>
    `;
    return;
  }

  feed.innerHTML = recent.map((m) => {
    const homeWinner = m.home_goals > m.away_goals;
    const awayWinner = m.away_goals > m.home_goals;
    const matchId = m.id || m.match_id;
    return `
      <div class="fixture-card" data-match-id="${matchId}" onclick="loadMatchById('${matchId}')">
        <div class="fixture-top">
          <span>${m.date}</span>
          <span class="badge ${m.home_goals != null ? 'good' : ''}">FT</span>
        </div>
        <div class="fixture-teams">
          <div class="fixture-team-row ${homeWinner ? 'winner' : ''}">
            <span>${m.home}</span>
            <span class="fixture-score">${m.home_goals ?? '—'}</span>
          </div>
          <div class="fixture-team-row ${awayWinner ? 'winner' : ''}">
            <span>${m.away}</span>
            <span class="fixture-score">${m.away_goals ?? '—'}</span>
          </div>
        </div>
        <div class="fixture-footer">
          <span class="fixture-xg-badge">xG: ${fmt(m.home_xg)} — ${fmt(m.away_xg)}</span>
          <span style="color:var(--accent);font-weight:700">Deep Dive →</span>
        </div>
      </div>
    `;
  }).join("") || `<div class="empty" style="grid-column:1/-1">No matches found.</div>`;
}

function populateMatchesForRound() {
  const r = parseInt($("roundSelect").value, 10);
  if (!state.roundsData || !r) return;
  const rounds = state.roundsData.rounds || [];
  const round = rounds.find((x) => x.round === r);
  if (!round) return;

  $("matchSelect").innerHTML = `<option value="">Pick a fixture…</option>` +
    round.matches.map((m) => {
      const matchId = m.id || m.match_id;
      const hg = m.home_goals ?? m.home_score ?? "—";
      const ag = m.away_goals ?? m.away_score ?? "—";
      return `<option value="${matchId}">${m.home} ${hg}–${ag} ${m.away} (${m.date})</option>`;
    }).join("");
}

window.loadMatchById = async function (matchId) {
  if (!matchId) return;
  $("matchId").value = matchId;
  if ($("matchSelect")) $("matchSelect").value = matchId;

  document.querySelectorAll(".fixture-card").forEach((c) => {
    c.classList.toggle("active", c.dataset.matchId === String(matchId));
  });

  const node = $("matchContent");
  loading(node);
  node.scrollIntoView({ behavior: "smooth", block: "start" });

  try {
    const d = await api(`/api/v1/analyze/match/${encodeURIComponent(matchId)}`);
    state.activeMatchData = d;

    // Concurrently attempt Sofascore resolution and fetch rich stats
    let sofaData = { enabled: false };
    try {
      const resolveRes = await api("/api/v1/sofascore/resolve-event", {
        understat_match_id: parseInt(matchId, 10) || 0,
        home_team: d.meta.home,
        away_team: d.meta.away,
        kickoff_date: d.meta.date,
      });
      if (resolveRes && resolveRes.event_id) {
        const eid = resolveRes.event_id;
        const [stats, lineups, incidents] = await Promise.allSettled([
          api(`/api/v1/sofascore/event/${eid}/statistics`, null, "GET"),
          api(`/api/v1/sofascore/event/${eid}/lineups`, null, "GET"),
          api(`/api/v1/sofascore/event/${eid}/incidents`, null, "GET"),
        ]);
        sofaData = {
          enabled: true,
          event_id: eid,
          statistics: stats.status === "fulfilled" ? stats.value : null,
          lineups: lineups.status === "fulfilled" ? lineups.value : null,
          incidents: incidents.status === "fulfilled" ? incidents.value : null,
        };
      }
    } catch (_) { /* gracefully fallback to Understat */ }

    state.activeMatchSofascore = sofaData;
    renderMatch(node, d, sofaData);
  } catch (e) {
    errored(node, e.message);
  }
};

async function runMatch() {
  const matchId = ($("matchSelect").value || $("matchId").value).trim();
  if (!matchId) {
    alert("Please select a fixture or enter a valid Match ID");
    return;
  }
  loadMatchById(matchId);
}

function renderMatch(node, d, sofaData = null) {
  const n = d.narrative || {};
  clear(node);

  const home = (d.meta && d.meta.home) || "Home";
  const away = (d.meta && d.meta.away) || "Away";
  const lineup = matchLineupData(d, sofaData);
  const homeShots = (d.shot_map.home || []).map((s) => ({ ...s, side: "home" }));
  const awayShots = (d.shot_map.away || []).map((s) => ({ ...s, side: "away" }));
  const allShots = [...homeShots, ...awayShots];

  node.innerHTML = `
    ${renderScoreboard(d, home, away)}
    ${matchFactStrip(d)}

    <!-- Row 1: where chances were created | how momentum accumulated -->
    <div class="grid cols-2">
      <div class="card">
        <div class="card-header">
          <div class="section-question">
            <span class="question-title">Where were the match chances created?</span>
            <span class="question-desc">Shot locations tiered by quality · hover any shot for detail</span>
          </div>
        </div>
        ${shotQualityRailHTML(allShots)}
        <div id="matchPitch"></div>
      </div>

      <div class="card">
        <div class="card-header">
          <div class="section-question">
            <span class="question-title">How did match momentum accumulate?</span>
            <span class="question-desc">Cumulative expected goals after each shot, minute by minute</span>
          </div>
        </div>
        <div id="xgtl" style="margin-top:14px"></div>
      </div>
    </div>

    <!-- Row 2: which chances decided it | tactical phase profile -->
    <div class="grid cols-2" style="margin-top:20px">
      <div class="card">
        <div class="card-header">
          <div class="section-question">
            <span class="question-title">Which high-probability chances decided the match?</span>
            <span class="question-desc">Every shot above xG ${d.big_chance_inventory.xG_threshold}, both sides</span>
          </div>
        </div>
        ${bigChances(d.big_chance_inventory, home, away)}
      </div>

      <div class="card">
        <div class="card-header">
          <div class="section-question">
            <span class="question-title">What was the tactical phase profile?</span>
            <span class="question-desc">Open play versus corner, set piece, and penalty distribution</span>
          </div>
        </div>
        ${situationBreakdown(d.situation_breakdown, home, away)}
      </div>
    </div>

    <!-- Lineup board -->
    ${renderMatchTacticalBoard(d, sofaData, lineup)}

    <!-- Live Sofascore layers (only when resolved) -->
    ${sofaData && sofaData.statistics ? renderSofascoreStatsSections(sofaData.statistics, home, away) : ""}
    ${sofaData && sofaData.incidents ? renderMatchIncidents(sofaData.incidents) : ""}

    <!-- Key performers -->
    ${d.rosters ? `
      <div class="card" style="margin-top:20px">
        <div class="card-header">
          <div class="section-question">
            <span class="question-title">Who were the key individual performers?</span>
            <span class="question-desc">Minutes, shots, goals, and xG contribution — click a name for a career report</span>
          </div>
        </div>
        ${rostersBlock(d.rosters, home, away)}
      </div>
    ` : ""}

    <details class="caveat" style="margin-top:24px">
      <summary>Limitations — read before quoting these numbers</summary>
      <ul>${(d.limitations || []).map((l) => `<li>${l}</li>`).join("")}</ul>
    </details>
  `;

  renderPitchHeatmap("matchPitch", { shots: allShots, sofa: sofaData }, { sofascore: sofaData });
  drawXgTimeline("xgtl", d.xg_timeline, home, away);
  animateTruthBar(node);
  setTimeout(() => {
    drawDottedTacticalPitch(lineup.homePlayers, lineup.awayPlayers, lineup.homeFormation, lineup.awayFormation);
  }, 50);
}

// ─── Match Report: scoreboard hero ────────────────────────────
function initials(name) {
  const words = String(name || "?").trim().split(/\s+/);
  if (words.length === 1) return words[0].slice(0, 3).toUpperCase();
  return words.slice(0, 2).map((w) => w[0]).join("").toUpperCase();
}

function renderScoreboard(d, homeName, awayName) {
  const n = d.narrative || {};
  const hxg = Number(n.xG && n.xG.h) || 0;
  const axg = Number(n.xG && n.xG.a) || 0;
  const totalXg = hxg + axg;
  const homeShare = totalXg > 0 ? Math.round((hxg / totalXg) * 1000) / 10 : 50;
  const forecast = d.forecast && d.forecast.w != null
    ? `<span class="sep">·</span><span title="Understat pre-match model probabilities">Forecast W${Math.round(d.forecast.w * 100)} D${Math.round(d.forecast.d * 100)} L${Math.round(d.forecast.l * 100)}</span>`
    : "";

  return `
    <section class="mr-scoreboard" aria-label="Match scoreboard">
      <div class="mr-eyebrow">
        <span>Match report</span><span class="sep">·</span><span>Shot-level xG</span>${forecast}
      </div>
      <div class="mr-board">
        <div class="mr-team">
          <div class="mr-initials home">${initials(homeName)}</div>
          <div style="min-width:0">
            <div class="mr-team-name">${escapeHtml(homeName)}</div>
            <div class="mr-team-sub">Home</div>
          </div>
        </div>
        <div class="mr-score">${n.scoreline != null ? n.scoreline.h ?? 0 : 0}<span class="mr-score-sep">:</span>${n.scoreline != null ? n.scoreline.a ?? 0 : 0}</div>
        <div class="mr-team away">
          <div class="mr-initials away">${initials(awayName)}</div>
          <div style="min-width:0">
            <div class="mr-team-name">${escapeHtml(awayName)}</div>
            <div class="mr-team-sub">Away</div>
          </div>
        </div>
      </div>
      <div class="mr-truthbar-wrap">
        <div class="mr-truthbar-labels">
          <span class="home"><strong>${fmt(hxg)}</strong> xG</span>
          <span>share of expected goals</span>
          <span class="away"><strong>${fmt(axg)}</strong> xG</span>
        </div>
        <div class="mr-truthbar" role="img" aria-label="${escapeHtml(homeName)} ${homeShare} percent of expected goals, ${escapeHtml(awayName)} ${(100 - homeShare).toFixed(1)} percent">
          <div class="seg-home" data-share="${homeShare}" style="width:50%"></div>
          <div class="seg-away"></div>
        </div>
      </div>
      ${n.narrative ? `<p class="mr-lede">${n.narrative}</p>` : ""}
    </section>`;
}

function animateTruthBar(node) {
  const seg = node.querySelector(".mr-truthbar .seg-home");
  if (!seg) return;
  const target = `${parseFloat(seg.dataset.share)}%`;
  if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    seg.style.width = target;
    return;
  }
  requestAnimationFrame(() => requestAnimationFrame(() => { seg.style.width = target; }));
}

function matchFactStrip(d) {
  const shotsH = (d.shot_map.home || []).length;
  const shotsA = (d.shot_map.away || []).length;
  const bigH = ((d.big_chance_inventory && d.big_chance_inventory.home) || []).length;
  const bigA = ((d.big_chance_inventory && d.big_chance_inventory.away) || []).length;
  const hxg = Number(d.narrative && d.narrative.xG && d.narrative.xG.h) || 0;
  const axg = Number(d.narrative && d.narrative.xG && d.narrative.xG.a) || 0;
  const perShot = shotsH + shotsA > 0 ? (hxg + axg) / (shotsH + shotsA) : 0;

  const split = (h, a) => `<span class="home">${h}</span><span class="unit"> : </span><span class="away">${a}</span>`;
  return `
    <div class="mr-facts">
      <div class="mr-fact">
        <div class="mr-fact-value split">${split((d.narrative && d.narrative.scoreline && d.narrative.scoreline.h) ?? 0, (d.narrative && d.narrative.scoreline && d.narrative.scoreline.a) ?? 0)}</div>
        <div class="mr-fact-label">Goals</div>
      </div>
      <div class="mr-fact">
        <div class="mr-fact-value split">${split(fmt(hxg), fmt(axg))}</div>
        <div class="mr-fact-label">Expected goals</div>
      </div>
      <div class="mr-fact">
        <div class="mr-fact-value split">${split(shotsH, shotsA)}</div>
        <div class="mr-fact-label">Shots</div>
      </div>
      <div class="mr-fact">
        <div class="mr-fact-value split">${split(bigH, bigA)}</div>
        <div class="mr-fact-label">Big chances</div>
      </div>
      <div class="mr-fact">
        <div class="mr-fact-value">${fmt(perShot, 3)}<span class="unit"> /shot</span></div>
        <div class="mr-fact-label">Match xG intensity</div>
      </div>
    </div>`;
}

function bigChances(inv, homeName = "Home", awayName = "Away") {
  const section = (title, colorVar, list) => `
    <div>
      <h4 style="font-size:12.5px;color:${colorVar};margin-bottom:8px">${title}</h4>
      ${list.length ? `
        <table>
          <thead><tr><th>Min</th><th>Shooter</th><th class="num">xG</th><th>Result</th></tr></thead>
          <tbody>
            ${list.map((s) => `<tr><td>${s.minute}'</td><td>${s.player || "—"}</td><td class="num">${fmt(s.xG)}</td><td><span class="badge ${s.result === 'Goal' ? 'good' : ''}">${s.result}</span></td></tr>`).join("")}
          </tbody>
        </table>` : `<div class="empty-state">No chances above the xG threshold.</div>`}
    </div>`;
  return `
    <div>${section(homeName, "var(--accent)", inv.home)}</div>
    <div style="margin-top:14px">${section(awayName, "var(--neutral)", inv.away)}</div>`;
}

function situationBreakdown(sb, homeName = "Home", awayName = "Away") {
  const head = `<tr><th>${term("situations", "Situation")}</th><th class="num">${term("shots", "Shots")}</th><th class="num">${term("xG", "xG")}</th><th class="num">${term("goals", "Goals")}</th></tr>`;
  const rows = (obj) => Object.entries(obj).sort((a, b) => b[1].xG - a[1].xG)
    .map(([k, v]) => {
      const label = String(k).replace(/([a-z])([A-Z])/g, "$1 $2");
      const totalXg = fmt(v.xG);
      return `<tr><td>${label}</td><td class="num">${v.shots}</td><td class="num">${totalXg}</td><td class="num"><strong>${v.goals}</strong></td></tr>`;
    }).join("");
  const table = (title, colorVar, side) => `
    <div>
      <h4 style="font-size:12.5px;color:${colorVar};margin-bottom:8px">${title}</h4>
      <table><thead>${head}</thead><tbody>${rows(sb[side])}</tbody></table>
    </div>`;
  return table(homeName, "var(--accent)", "home") +
    `<div style="margin-top:14px">${table(awayName, "var(--neutral)", "away")}</div>`;
}

function rostersBlock(rosters, homeName = "Home", awayName = "Away") {
  if (!rosters) return "";
  const renderSide = (title, colorVar, list) => {
    if (!list || !list.length) return "";
    return `
      <div>
        <h4 style="font-size:12.5px;color:${colorVar};margin-bottom:8px">${escapeHtml(title)}</h4>
        <table>
          <thead><tr><th>Player</th><th>Pos</th><th class="num">Min</th><th class="num">Shots</th><th class="num">Goals</th><th class="num">xG</th><th class="num">xA</th><th class="num">xGChain</th></tr></thead>
          <tbody>
            ${list.map((p) => `
              <tr>
                <td><strong style="cursor:pointer" onclick="$('playerName').value='${String(p.player || "").replace(/'/g, "\\'")}';activateTab('player');runPlayer()">${p.player || "—"}</strong></td>
                <td><span class="badge">${p.position || "—"}</span></td>
                <td class="num">${p.time || 0}</td>
                <td class="num">${p.shots || 0}</td>
                <td class="num"><strong>${p.goals || 0}</strong></td>
                <td class="num">${fmt(p.xG)}</td>
                <td class="num">${fmt(p.xA)}</td>
                <td class="num">${fmt(p.xGChain)}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    `;
  };
  return `<div class="grid cols-2">${renderSide(homeName, "var(--accent)", rosters.h)}${renderSide(awayName, "var(--neutral)", rosters.a)}</div>`;
}

function drawXgTimeline(container, tl, homeName = "Home", awayName = "Away") {
  const el = document.getElementById(container); if (!el) return;
  const w = 1100, h = 300, padL = 64, padR = 74, x0 = padL, x1 = w - padR, y0 = 34, y1 = h - 46;
  const home = tl.home || [], away = tl.away || [];
  if (!home.length && !away.length) {
    el.innerHTML = `<div class="empty-state">No shot timeline recorded.</div>`;
    return;
  }
  const allMax = Math.max(...home.map((p) => p.cumulative_xG), ...away.map((p) => p.cumulative_xG), 0.5);
  const minuteMax = Math.max(...home.map((p) => p.minute), ...away.map((p) => p.minute), 90);
  const x = (m) => x0 + (m / minuteMax) * (x1 - x0);
  const y = (v) => y1 - (v / allMax) * (y1 - y0);
  const homeColor = getThemeColor("--accent") || "#1ed760";
  const awayColor = getThemeColor("--neutral") || "#38bdf8";

  // Horizontal gridlines with tick labels.
  const gridSteps = 4;
  let grid = "";
  for (let i = 1; i <= gridSteps; i++) {
    const v = (allMax / gridSteps) * i;
    grid += `<line x1="${x0}" y1="${y(v)}" x2="${x1}" y2="${y(v)}" stroke="var(--border)" stroke-dasharray="3 5" opacity="0.6"/>
      <text x="${x0 - 10}" y="${y(v) + 4}" fill="var(--muted)" font-size="12" text-anchor="end">${fmt(v, allMax >= 2 ? 1 : 2)}</text>`;
  }
  // Minute ticks.
  const minuteStep = minuteMax > 90 ? 15 : 45;
  let ticks = "";
  for (let m = 0; m <= minuteMax; m += minuteStep) {
    ticks += `<text x="${x(m)}" y="${y1 + 20}" fill="var(--muted)" font-size="12" text-anchor="middle">${m}'</text>`;
  }

  const path = (pts, color) => pts.length ? `<path d="${pts.map((p, i) => `${i ? "L" : "M"}${x(p.minute)},${y(p.cumulative_xG)}`).join(" ")}" fill="none" stroke="${color}" stroke-width="2.5"/>` : "";
  const dots = (pts, color) => pts.map((p) => hoverDot(x(p.minute), y(p.cumulative_xG), `${p.minute}' — Cumulative xG: ${fmt(p.cumulative_xG, 3)}`, color, 3.5)).join("");
  // End-of-line totals; nudge apart when the two curves finish close together.
  const hy = home.length ? y(home[home.length - 1].cumulative_xG) : null;
  const ay = away.length ? y(away[away.length - 1].cumulative_xG) : null;
  let awayDy = 0;
  if (hy != null && ay != null && Math.abs(hy - ay) < 18) awayDy = hy > ay ? 18 : -18;
  const endLabel = (pts, color, name, dy) => {
    if (!pts.length) return "";
    const last = pts[pts.length - 1];
    return `<text x="${Math.min(x(last.minute) + 8, x1 + 4)}" y="${y(last.cumulative_xG) + 4 + dy}" fill="${color}" font-size="12.5" font-weight="800">${name} ${fmt(last.cumulative_xG, 2)}</text>`;
  };

  el.innerHTML = `<svg class="timeline-svg" viewBox="0 0 ${w} ${h}">
    <line x1="${x0}" y1="${y1}" x2="${x1}" y2="${y1}" stroke="var(--border)"/>
    <line x1="${x0}" y1="${y1}" x2="${x0}" y2="${y0}" stroke="var(--border)"/>
    ${grid}
    ${path(home, homeColor)}${path(away, awayColor)}
    ${dots(home, homeColor)}${dots(away, awayColor)}
    ${endLabel(home, homeColor, homeName, 0)}
    ${endLabel(away, awayColor, awayName, awayDy)}
    <text x="${x0}" y="18" fill="var(--muted)" font-size="13"><tspan fill="${homeColor}" font-weight="800">● ${homeName}</tspan><tspan dx="18" fill="${awayColor}" font-weight="800">● ${awayName}</tspan><tspan dx="18" opacity="0.85">Cumulative xG</tspan></text>
    <text x="${x0 + (x1 - x0) / 2}" y="${h - 8}" fill="var(--muted)" font-size="12.5" text-anchor="middle">Match Minute →</text>
    <text x="16" y="${y0 + (y1 - y0) / 2}" fill="var(--muted)" font-size="12.5" text-anchor="middle" transform="rotate(-90 16 ${y0 + (y1 - y0) / 2})">Cumulative xG ↑</text>
  </svg>`;
}

// ==========================================================
// PLAYER INTELLIGENCE & SCOUTING REPORT (IMAGE 1)
// ==========================================================
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
      player_name: name,
      league_name: state.league,
      season: seasonOf("playerSeasons"),
      seasons: seasonsOf("playerSeasons"),
      start_date: dateOf("playerFrom"),
      end_date: dateOf("playerTo"),
    });
    state.activePlayerData = d;
    const seasonLabel = d.seasons && d.seasons.length > 1 ? ` · ${d.seasons.join("–")}` : ` · ${seasonOf("playerSeasons")}`;
    $("playerResolved").textContent = `${d.player.name}${d.player.age != null ? ` (${d.player.age}y)` : ""} · ${d.player.team_title || "—"} · ${d.player.position || "—"}${seasonLabel}`;
    renderPlayer(node, d);
  } catch (e) { errored(node, e.message); }
}

function playerKPIStrip(d) {
  const p = d.player || {};
  const per90 = d.per90_breakdown || {};
  const shotSel = d.shot_selection || {};
  // Real metrics we have from Understat. Physical (distance/sprint/top-speed) require Sofascore.
  const kpis = [
    { label: "Goals", value: per90.goals != null ? fmt(per90.goals, 1) : null, unit: "/90", accent: "var(--accent)" },
    { label: "Shots", value: per90.shots != null ? fmt(per90.shots, 1) : null, unit: "/90", accent: "var(--neutral)" },
    { label: "Key Passes", value: per90.key_passes != null ? fmt(per90.key_passes, 1) : null, unit: "/90", accent: "var(--accent)" },
    { label: "Shot Quality", value: shotSel.xG_per_shot != null ? fmt(shotSel.xG_per_shot, 3) : null, unit: "xG/shot", accent: "var(--warning)" },
    { label: "Minutes", value: p.minutes != null ? fmt(p.minutes, 0) : null, unit: "played", accent: "var(--muted)" },
  ];
  const hasAny = kpis.some((k) => k.value != null);
  if (!hasAny) return "";
  return `
    <div class="kpi-strip">
      ${kpis.map((k) => `
        <div class="kpi-card">
          <div class="kpi-label">${k.label}</div>
          <div class="kpi-value-row">
            <span class="kpi-value" style="color:${k.accent}">${k.value != null ? k.value : "—"}</span>
            <span class="kpi-unit">${k.unit}</span>
          </div>
        </div>
      `).join("")}
    </div>
  `;
}

function renderPlayer(node, d) {
  clear(node);
  const p = d.player;
  const radar = d.radar.profile.filter((item) => item.percentile > 0 || item.raw > 0);
  const shots = d.shots || [];
  const avgPct = radar.length ? Math.round(radar.reduce((acc, r) => acc + r.percentile, 0) / radar.length) : 50;
  const watched = isWatched(p.id);

  node.innerHTML = `
    <!-- Player Scouting Hero Header -->
    <div class="player-hero-card">
      <div class="hero-main">
        <div class="hero-identity">
          <div class="hero-avatar">${p.name.split(" ").map(w=>w[0]).slice(0,2).join("")}</div>
          <div class="hero-name-wrap">
            <h2>${p.name}</h2>
            <div class="hero-meta">
              <span class="hero-pill accent">${p.team_title || "Unknown Club"}</span>
              <span class="hero-pill">${p.position_group || p.position || "Forward"}</span>
              ${p.age ? `<span class="hero-pill">${p.age} years old</span>` : ""}
              <span class="hero-pill">${LEAGUE_LABEL[state.league] || state.league}</span>
              ${enrichmentPills(d.enrichment)}
              ${windowBadge(d)}
            </div>
          </div>
        </div>
        <div style="display:flex;gap:10px;align-items:center">
          <button class="ghost" data-watch-player="${p.id}" onclick="toggleWatchlist(state.activePlayerData.player)" style="${watched ? 'color:var(--accent)' : ''}">
            ${watched ? '★ Watched' : '☆ Watch'}
          </button>
          <span class="hero-pill green" style="font-size:12.5px;padding:6px 14px">
            ⭐ ${avgPct}th Percentile vs Position Peers
          </span>
        </div>
      </div>

      <!-- Layer 1: Decision Metrics Grid -->
      ${decisionMetricsHTML(d.l1_metrics)}
      ${playerKPIStrip(d)}
    </div>

    <!-- Row 1: Tactical 4-Tier Shot Map & Heatmap vs Pizza Radar -->
    <div class="grid cols-2" style="margin-top:20px">
      <div class="card">
        <div class="card-header">
          <div class="section-question">
            <span class="question-title">Where are shots taken from & how dangerous are they?</span>
            <span class="question-desc">4-tier xG shot locations and thermal density heatmap</span>
          </div>
          <span style="font-size:11px;color:var(--muted);font-family:var(--mono)">${shots.length} shots recorded</span>
        </div>
        ${shotQualityRailHTML(shots)}
        <div id="playerPitch"></div>
      </div>

      <div class="card">
        <div class="card-header">
          <div class="section-question">
            <span class="question-title">How does the player compare to positional peers?</span>
            <span class="question-desc">Percentile pizza radar vs ${d.radar.position_group} peers (${d.radar.peer_count} players)</span>
          </div>
        </div>
        <div id="playerRadar"></div>
      </div>
    </div>

    <!-- Row 2: Finishing Diagnostics + Playmaking & Involvement -->
    <div class="grid cols-2" style="margin-top:20px">
      <div class="card">
        <div class="card-header">
          <div class="section-question">
            <span class="question-title">What is the player's finishing efficiency & shot selection?</span>
            <span class="question-desc">Confidence intervals and non-penalty shot quality mix</span>
          </div>
        </div>
        ${finishing(d.finishing_overperformance)}
        <div style="margin-top:16px">${shotSelection(d.shot_selection)}</div>
      </div>

      <div class="card">
        <div class="card-header">
          <div class="section-question">
            <span class="question-title">How does the player contribute to possession & buildup?</span>
            <span class="question-desc">xG Chain, xG Buildup, and creative dominance in the squad</span>
          </div>
        </div>
        ${involvement(d.involvement_profile)}
        ${d.creative_dominance ? `
          <div style="margin-top:16px;padding-top:14px;border-top:1px solid var(--border)">
            <div class="kv">
              <span class="k">${term("creative_dominance")}</span>
              <span class="v" style="color:var(--accent);font-weight:700">${pct(d.creative_dominance.xA_share, 1)} of team xA</span>
            </div>
            <div class="hint">Generated ${fmt(d.creative_dominance.player_xA)} of ${d.creative_dominance.team_title}'s ${fmt(d.creative_dominance.team_xA)} total team xA.</div>
          </div>
        ` : ""}
      </div>
    </div>

    <!-- Row 3: Similar Players Cluster -->
    <div class="card" style="margin-top:20px">
      <div class="card-header">
        <div class="section-question">
          <span class="question-title">Which players share a similar tactical profile?</span>
          <span class="question-desc">Euclidean nearest-neighbor clones matched across ${d.similar_players.pool_after_filters} position peers</span>
        </div>
      </div>
      ${similarCards(d.similar_players)}
    </div>

    <!-- Row 4: Percentile Rankings Table -->
    <div class="card" style="margin-top:20px">
      <div class="card-header">
        <div class="section-question">
          <span class="question-title">Tactical Metrics & League Percentile Rankings</span>
          <span class="question-desc">Ranked breakdown normalized per 90 minutes</span>
        </div>
      </div>
      ${percentileTable(radar, d.per90_breakdown)}
    </div>

    ${d.pressing_output ? `
      <div class="card" style="margin-top:20px">
        <div class="card-header">
          <div class="section-question">
            <span class="question-title">Possession Regain & High-Press Output</span>
            <span class="question-desc">Conversion of attacking chances following possession regains</span>
          </div>
        </div>
        ${pressingBlock(d.pressing_output)}
      </div>
    ` : ""}

    <div class="caveat"><strong>Limitations.</strong><ul>${d.limitations.map((l) => `<li>${l}</li>`).join("")}</ul></div>
  `;

  renderPitchHeatmap("playerPitch", shots);
  drawRadar("playerRadar", radar);
}

function similarCards(s) {
  if (!s.matches || !s.matches.length) return `<div class="empty">No peer profiles matched.</div>`;
  return `
    <div class="similar-grid">
      ${s.matches.map((m) => `
        <div class="similar-card">
          <div class="similar-card-top">
            <span class="similar-player-name">${m.player_name}</span>
            <span class="similar-badge">${Math.round(m.similarity * 100)}% match</span>
          </div>
          <div class="similar-meta">
            <div>${m.team_title || "—"} · ${m.position || "—"}</div>
            <div>${m.age ? `${m.age} years old · ` : ""}${fmt(m.minutes, 0)} mins</div>
          </div>
          <button class="ghost" style="padding:4px 8px;font-size:11px;margin-top:6px" onclick="$('playerName').value='${m.player_name}';runPlayer()">
            Analyze Profile →
          </button>
        </div>
      `).join("")}
    </div>
  `;
}

function percentileTable(profile, b) {
  return `
    <table>
      <thead>
        <tr>
          <th>Metric</th>
          <th class="num">Total</th>
          <th class="num">Per 90</th>
          <th style="min-width:180px">Percentile Rank vs Peers</th>
          <th class="num">Rank</th>
        </tr>
      </thead>
      <tbody>
        ${profile.map((p) => {
          const tier = p.percentile >= 80 ? "tier-elite" : p.percentile >= 60 ? "tier-good" : p.percentile >= 40 ? "tier-avg" : "tier-low";
          return `
            <tr>
              <td><strong>${term(RADAR_LABEL_KEYS[p.label] || p.key || p.label, p.label)}</strong></td>
              <td class="num">${fmt(p.raw)}</td>
              <td class="num">${fmt(p.per90, 3)}</td>
              <td>
                <div class="pct-bar-cell">
                  <div class="pct-track"><div class="pct-fill ${tier}" style="width:${Math.max(4, p.percentile)}%"></div></div>
                </div>
              </td>
              <td class="num" style="font-weight:700;color:${p.percentile >= 80 ? 'var(--accent)' : 'var(--text)'}">
                ${Math.round(p.percentile)}%
              </td>
            </tr>
          `;
        }).join("")}
      </tbody>
    </table>
  `;
}

function pressingBlock(p) {
  return `
    <div class="kv">
      <span class="k">Regain shots / xG</span><span class="v">${p.regain_shots} shots · ${fmt(p.regain_xG)} xG (${pct(p.regain_xG_share)} of total)</span>
      <span class="k">Goals from regains</span><span class="v">${p.regain_goals}</span>
    </div>
    <div class="hint">${p.interpretation}</div>
  `;
}

async function runCareer() {
  const name = $("playerName").value.trim();
  if (!name) return;
  const node = $("playerContent"); loading(node);
  $("playerResolved").textContent = "";
  try {
    const d = await api("/api/v1/analyze/player/career", {
      player_name: name, league_name: state.league,
      seasons: seasonsOf("playerSeasons"), season_end: seasonOf("playerSeasons"),
    });
    renderCareer(node, d);
  } catch (e) { errored(node, e.message); }
}

function renderCareer(node, d) {
  clear(node);
  const present = d.seasons.filter((s) => s.present);
  node.innerHTML = `
    <div class="card">
      <div class="card-header">
        <div class="section-question">
          <span class="question-title">How has output evolved across seasons?</span>
          <span class="question-desc">Multi-season progression trajectory for ${d.player_name}</span>
        </div>
      </div>
      <div class="controls-row">
        <div class="field"><label>Metric</label>
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
    </div>
    <div class="card" style="margin-top:20px">
      <div class="card-header"><span class="card-title">Multi-Season Records</span></div>
      <table><thead><tr><th>Season</th><th>Team</th><th>Pos</th><th class="num">Games</th><th class="num">Min</th><th class="num">${term("goals")}</th><th class="num">${term("xG")}</th><th class="num">${term("npxG")}</th><th class="num">${term("assists")}</th><th class="num">${term("xA")}</th><th class="num">${term("shots")}</th><th class="num">${term("xG_per_shot")}</th><th class="num">${term("conversion")}</th></tr></thead><tbody>
        ${d.seasons.map((s, i) => {
          if (!s.present) return `<tr><td>${s.season}</td><td colspan=12 style="color:var(--muted)">— not in this league</td></tr>`;
          const changed = i > 0 && d.seasons[i - 1].present && d.seasons[i - 1].team !== s.team;
          return `<tr><td><strong>${s.season}</strong></td><td>${s.team}${changed ? ' <span class="badge good">transferred</span>' : ""}</td><td>${s.position_group || "—"}</td>
            <td class="num">${fmt(s.games, 0)}</td><td class="num">${fmt(s.minutes, 0)}</td>
            <td class="num"><strong>${fmt(s.goals, 0)}</strong></td><td class="num">${fmt(s.xG)}</td><td class="num">${fmt(s.npxG)}</td>
            <td class="num">${fmt(s.assists, 0)}</td><td class="num">${fmt(s.xA)}</td>
            <td class="num">${fmt(s.shots, 0)}</td><td class="num">${fmt(s.xG_per_shot, 3)}</td><td class="num">${fmt(s.conversion, 1)}%</td></tr>`;
        }).join("")}
      </tbody></table>
    </div>
  `;
  const draw = () => drawCareerChart("careerChart", present, $("careerMetric").value);
  $("careerMetric").addEventListener("change", draw);
  draw();
}

function drawCareerChart(container, rows, metricKey) {
  const el = document.getElementById(container);
  if (!el) return;
  if (rows.length < 2) { el.innerHTML = `<div class="empty">Not enough seasons present.</div>`; return; }
  const w = 1100, h = 260, padL = 56, pad = 34, x0 = padL, x1 = w - pad, y0 = 18, y1 = h - 34;
  const vals = rows.map((r) => Number(r[metricKey]) || 0);
  const allMax = Math.max(...vals, 0.001);
  const x = (i) => x0 + (i * (x1 - x0)) / Math.max(rows.length - 1, 1);
  const y = (v) => y1 - (v / allMax) * (y1 - y0);
  const strokeColor = getThemeColor("--accent") || "#1ed760";
  const path = vals.map((v, i) => `${i ? "L" : "M"}${x(i)},${y(v)}`).join(" ");
  const dots = vals.map((v, i) => hoverDot(x(i), y(v), `${rows[i].season}: ${fmt(v, 3)}\n${rows[i].team || ""}\n${fmt(rows[i].minutes, 0)} min`, strokeColor)).join("");
  const labels = rows.map((r, i) => `<text x="${x(i)}" y="${y1 + 16}" fill="var(--muted)" font-size="10" text-anchor="middle">${r.season}</text>`).join("");
  const entry = GLOSSARY[metricKey] || {};
  el.innerHTML = `<svg class="timeline-svg" viewBox="0 0 ${w} ${h}">
    <line x1="${x0}" y1="${y1}" x2="${x1}" y2="${y1}" stroke="var(--border)"/>
    <line x1="${x0}" y1="${y1}" x2="${x0}" y2="${y0}" stroke="var(--border)"/>
    <path d="${path}" fill="none" stroke="${strokeColor}" stroke-width="2.5"/>${dots}
    ${labels}
    <text x="${x0}" y="${y0}" fill="var(--muted)" font-size="11">${entry.label || metricKey} by Season</text>
  </svg>`;
}

// ==========================================================
// TEAM TACTICAL INTELLIGENCE (IMAGES 1, 2, 3)
// ==========================================================
$("teamGo").addEventListener("click", runTeam);
$("teamName").addEventListener("keydown", (e) => { if (e.key === "Enter") runTeam(); });

async function runTeam() {
  const name = $("teamName").value.trim();
  if (!name) return;
  const node = $("teamContent"); loading(node);
  try {
    const d = await api("/api/v1/analyze/team", {
      team_name: name, league_name: state.league, season: seasonOf("teamSeasons"),
      seasons: seasonsOf("teamSeasons"),
      start_date: dateOf("teamFrom"), end_date: dateOf("teamTo"),
    });
    state.activeTeamData = d;
    renderTeam(node, d);
  } catch (e) { errored(node, e.message); }
}

window.setTeamSubtab = function(tabName) {
  state.teamSubtab = tabName;
  document.querySelectorAll(".team-subnav .subnav-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.subtab === tabName);
  });
  renderTeamSubtab(tabName);
};

function renderTeam(node, d) {
  const s = d.style;
  clear(node);

  const history = d.form_momentum && d.form_momentum.rolling_xgd ? d.form_momentum.rolling_xgd.map(r => r.rolling_xGD) : [];
  const sparklines = {
    xG_per_game: (d.metric_trends && d.metric_trends.xG_for) || history,
    xGA_per_game: (d.metric_trends && d.metric_trends.xG_against) || history,
    npxGD_per_game: (d.metric_trends && d.metric_trends.npxGD) || history,
    PPDA: (d.metric_trends && d.metric_trends.PPDA) || [],
    xPTS_per_game: (d.metric_trends && d.metric_trends.xPTS) || history,
  };

  node.innerHTML = `
    <!-- Team Hero Header -->
    <div class="team-hero-card">
      <div class="hero-main">
        <div class="hero-identity">
          <div class="hero-avatar">🛡️</div>
          <div class="hero-name-wrap">
            <h2>${s.team}</h2>
            <div class="hero-meta">
              <span class="hero-pill accent">${LEAGUE_LABEL[state.league] || state.league}</span>
              <span class="hero-pill">${s.matches} matches analyzed</span>
              ${d.archetype ? `<span class="hero-pill" title="Tactical Style Archetype">⚡ ${d.archetype.archetype_label}</span>` : ""}
              ${windowBadge(d)}
            </div>
          </div>
        </div>
      </div>

      <!-- Layer 1: Decision Metrics Grid with Sparklines -->
      ${decisionMetricsHTML(d.l1_metrics, sparklines)}
    </div>

    <!-- Team Subnav Navigation Bar -->
    <div class="team-subnav" style="margin-top:20px">
      <button class="subnav-btn ${state.teamSubtab === 'overview' ? 'active' : ''}" data-subtab="overview" onclick="setTeamSubtab('overview')">📊 Overview & Pitch</button>
      <button class="subnav-btn ${state.teamSubtab === 'performance' ? 'active' : ''}" data-subtab="performance" onclick="setTeamSubtab('performance')">📈 Process & Momentum</button>
      <button class="subnav-btn ${state.teamSubtab === 'possession' ? 'active' : ''}" data-subtab="possession" onclick="setTeamSubtab('possession')">⚽ Territory & Splits</button>
      <button class="subnav-btn ${state.teamSubtab === 'chance' ? 'active' : ''}" data-subtab="chance" onclick="setTeamSubtab('chance')">🎯 Chance Creation</button>
      <button class="subnav-btn ${state.teamSubtab === 'defence' ? 'active' : ''}" data-subtab="defence" onclick="setTeamSubtab('defence')">🛡️ Defence & Pressing</button>
    </div>

    <!-- Subnav Active Panel Content -->
    <div id="teamSubtabContent"></div>

    <div class="caveat" style="margin-top:20px"><strong>Limitations.</strong><ul>${d.limitations.map((l) => `<li>${l}</li>`).join("")}</ul></div>
  `;

  renderTeamSubtab(state.teamSubtab || "overview");
}

function renderTeamSubtab(tabName) {
  const container = $("teamSubtabContent");
  if (!container || !state.activeTeamData) return;
  const d = state.activeTeamData;
  const s = d.style;

  if (tabName === "overview") {
    container.innerHTML = `
      <!-- Attacking vs Defensive Shot Maps -->
      <div class="grid cols-2">
        <div class="card">
          <div class="card-header">
            <div class="section-question">
              <span class="question-title">Attacking Chances Created</span>
              <span class="question-desc">4-tier tactical shot map of chances taken by ${s.team}</span>
            </div>
            <span id="teamForShotCount" style="font-size:11px;color:var(--muted)">Loading shots…</span>
          </div>
          <div id="teamForPitch"></div>
        </div>
        <div class="card">
          <div class="card-header">
            <div class="section-question">
              <span class="question-title">Defensive Chances Conceded</span>
              <span class="question-desc">Tactical shot map of chances allowed to opponents</span>
            </div>
            <span id="teamAgainstShotCount" style="font-size:11px;color:var(--muted)">Loading shots…</span>
          </div>
          <div id="teamAgainstPitch"></div>
        </div>
      </div>

      <!-- Matchday League Position Progression -->
      ${seasonComparisonSection(d)}

      <!-- Squad Breakdown Table (Layer 3 — collapsed by default) -->
      ${d.squad && d.squad.length ? `
        <div class="card" style="margin-top:20px">
          <details class="layer3">
            <summary><span class="card-title">${s.team} Squad Statistics & Profiles</span></summary>
            <table style="margin-top:8px">
              <thead><tr><th>Player</th><th>Role</th><th class="num">Games</th><th class="num">Min</th><th class="num">Goals</th><th class="num">xG</th><th class="num">Assists</th><th class="num">xA</th><th class="num">xGChain</th><th>Action</th></tr></thead>
              <tbody>
                ${d.squad.map((p) => `
                  <tr>
                    <td><strong style="cursor:pointer;color:var(--text-bright)" onclick="$('playerName').value='${p.player_name}';activateTab('player');runPlayer()">${p.player_name}</strong></td>
                    <td><span class="badge">${p.position || "—"}</span></td>
                    <td class="num">${p.games}</td>
                    <td class="num">${p.minutes}</td>
                    <td class="num"><strong>${p.goals}</strong></td>
                    <td class="num">${fmt(p.xG)}</td>
                    <td class="num">${p.assists}</td>
                    <td class="num">${fmt(p.xA)}</td>
                    <td class="num" style="color:var(--accent);font-weight:700">${fmt(p.xGChain)}</td>
                    <td><button class="ghost" style="padding:2px 8px;font-size:11px" onclick="$('playerName').value='${p.player_name}';activateTab('player');runPlayer()">Scout →</button></td>
                  </tr>
                `).join("")}
              </tbody>
            </table>
          </details>
        </div>
      ` : ""}
    `;
    fetchTeamShots(s.team);
    drawSeasonComparisonCharts(d);
  } else if (tabName === "performance") {
    container.innerHTML = `
      <!-- Performance Last 10 Curve -->
      <div class="card">
        <div class="card-header">
          <div class="section-question">
            <span class="question-title">Are we creating better chances than we concede?</span>
            <span class="question-desc">Rolling 5-match tactical metrics and underlying process momentum</span>
          </div>
        </div>
        <div class="controls-row">
          <div class="field"><label>Select Metric</label>
            <select id="trendMetric">
              <option value="npxGD">${term("npxgd")}</option>
              <option value="xG_for">${term("xG")} For</option>
              <option value="xG_against">${term("xGA")} Against</option>
              <option value="goals_for">${term("goals")} For</option>
              <option value="goals_against">Goals Against</option>
              <option value="xPTS">${term("xpts")}</option>
              <option value="PPDA">${term("ppda")}</option>
            </select>
          </div>
        </div>
        <div id="trendChart"></div>
      </div>

      <!-- Last-5 vs Season benchmark bars -->
      <div class="card" style="margin-top:20px">
        <div class="card-header">
          <div class="section-question">
            <span class="question-title">Last Five vs Season Average</span>
            <span class="question-desc">Shots, goals, and xG: recent form vs full-season benchmark</span>
          </div>
        </div>
        <div id="last5Bars"></div>
      </div>

      <div class="grid cols-2" style="margin-top:20px">
        <div class="card">
          <div class="card-header">
            <div class="section-question">
              <span class="question-title">Finishing & Variance Luck Trajectory</span>
              <span class="question-desc">Cumulative goals minus xG over time</span>
            </div>
          </div>
          <div id="luckChart"></div>
          <div class="hint">${d.luck_curve.interpretation}</div>
        </div>

        <div class="card">
          <div class="card-header">
            <div class="section-question">
              <span class="question-title">Flat-Track Bully & Strength of Schedule Check</span>
              <span class="question-desc">Performance vs top-half vs bottom-half opponents</span>
            </div>
          </div>
          ${strengthOfScheduleTable(d.strength_of_schedule)}
        </div>
      </div>
    `;
    drawLuckChart("luckChart", d.luck_curve);
    const drawTrend = () => drawTrendChart("trendChart", d.metric_trends, $("trendMetric").value);
    $("trendMetric").addEventListener("change", drawTrend);
    drawTrend();
    drawLast5Bars("last5Bars", d.metric_trends, s);
  } else if (tabName === "possession") {
    container.innerHTML = `
      <div class="grid cols-2">
        <div class="card">
          <div class="card-header">
            <div class="section-question">
              <span class="question-title">First vs Second Half Splits</span>
              <span class="question-desc">Pace and stamina breakdown across halves</span>
            </div>
          </div>
          ${halfSplitTable(d.half_split)}
        </div>

        <div class="card">
          <div class="card-header">
            <div class="section-question">
              <span class="question-title">Home vs Away Venue Splits</span>
              <span class="question-desc">Performance dependency on venue</span>
            </div>
          </div>
          ${homeAwaySplitTable(d.home_away_splits)}
        </div>
      </div>
    `;
  } else if (tabName === "chance") {
    container.innerHTML = `
      <div class="grid cols-2">
        <div class="card">
          <div class="card-header">
            <div class="section-question">
              <span class="question-title">Shot Phase & Situation Breakdown</span>
              <span class="question-desc">Open play vs Corner vs Set Piece reliance</span>
            </div>
          </div>
          ${d.situational_xg_share ? situationShareTable(d.situational_xg_share) : `<div class="empty">Situation breakdown not available.</div>`}
        </div>

        <div class="card">
          <div class="card-header">
            <div class="section-question">
              <span class="question-title">Tactical Style Archetype</span>
              <span class="question-desc">Profile classification vs league tactical baseline</span>
            </div>
          </div>
          ${d.archetype ? archetypeBlock(d.archetype) : `<div class="empty">Archetype classification not computed.</div>`}
        </div>
      </div>
    `;
  } else if (tabName === "defence") {
    container.innerHTML = `
      <!-- Defensive Intensity & Zone Table -->
      <div class="card">
        <div class="card-header">
          <div class="section-question">
            <span class="question-title">Zone Pressure & Defensive Intensity</span>
            <span class="question-desc">Pressing volume, pitch zone distribution, and recovery speed</span>
          </div>
        </div>
        ${zonePressureTable(d)}
      </div>

      <div class="grid cols-2" style="margin-top:20px">
        <div class="card">
          <div class="card-header">
            <div class="section-question">
              <span class="question-title">Pressing Intensity (PPDA)</span>
              <span class="question-desc">Home vs Away pressing intensity comparison</span>
            </div>
          </div>
          <div class="kv">
            <span class="k">Home PPDA</span><span class="v">${fmt(d.ppda_home_away.ppda_home, 1)} (${d.ppda_home_away.matches_home} matches)</span>
            <span class="k">Away PPDA</span><span class="v">${fmt(d.ppda_home_away.ppda_away, 1)} (${d.ppda_home_away.matches_away} matches)</span>
            <span class="k">Season Overall PPDA</span><span class="v" style="color:var(--accent);font-weight:700">${fmt(s.PPDA, 1)}</span>
          </div>
          <div class="hint">${d.ppda_home_away.interpretation}</div>
        </div>

        <div class="card">
          <div class="card-header">
            <div class="section-question">
              <span class="question-title">Defensive Suppression</span>
              <span class="question-desc">Deep box entries and chances conceded</span>
            </div>
          </div>
          <div class="kv">
            <span class="k">xGA / Match</span><span class="v">${fmt(s.xGA_per_game)}</span>
            <span class="k">Deep Passes Allowed</span><span class="v">${fmt(s.deep_completions_allowed, 0)}</span>
            <span class="k">Opponent PPDA</span><span class="v">${fmt(s.OPPDA, 1)}</span>
          </div>
        </div>
      </div>
    `;
  }
}

function zonePressureTable(d) {
  const s = d.style || {};
  const ppda = s.PPDA, oppda = s.OPPDA;
  const deepAllowed = s.deep_completions_allowed;
  // Real defensive-intensity metrics we actually compute from Understat.
  const hasReal = ppda != null || deepAllowed != null;
  return `
    <div class="empty-state" style="margin-bottom:14px">Zone-split pressure (Total / Left / Center / Right / Avg Time) is a proprietary Stats-Perform model — we don't fabricate it. Below are the pressing & defensive metrics we <em>do</em> compute.</div>
    <table class="pressure-table">
      <thead>
        <tr>
          <th>Defensive Metric</th>
          <th class="num">Value</th>
          <th>Interpretation</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><strong>PPDA (Pressing Intensity)</strong></td>
          <td class="num"><strong>${ppda != null ? fmt(ppda, 1) : "—"}</strong></td>
          <td style="color:var(--muted)">Opposition passes per defensive action — lower = higher press</td>
        </tr>
        <tr>
          <td><strong>OPPDA (vs Pressing)</strong></td>
          <td class="num">${oppda != null ? fmt(oppda, 1) : "—"}</td>
          <td style="color:var(--muted)">How intensely opponents press this team</td>
        </tr>
        <tr>
          <td><strong>Deep Completions Allowed</strong></td>
          <td class="num">${deepAllowed != null ? fmt(deepAllowed, 0) : "—"}</td>
          <td style="color:var(--muted)">Box-entry passes conceded to opponents</td>
        </tr>
        <tr>
          <td><strong>xGA per Match</strong></td>
          <td class="num">${s.xGA_per_game != null ? fmt(s.xGA_per_game) : "—"}</td>
          <td style="color:var(--muted)">Expected goals conceded — chance suppression</td>
        </tr>
      </tbody>
    </table>
    ${hasReal ? "" : `<div class="empty-state" style="margin-top:14px">No defensive data available for this team.</div>`}
  `;
}

async function fetchTeamShots(teamName) {
  try {
    const shotsData = await api("/api/v1/analyze/team/shots", {
      team_name: teamName, league_name: state.league, season: seasonOf("teamSeasons"),
      seasons: seasonsOf("teamSeasons"), start_date: dateOf("teamFrom"), end_date: dateOf("teamTo"),
    });
    if ($("teamForShotCount")) $("teamForShotCount").textContent = `${shotsData.for_shots.length} shots · ${shotsData.for_goals} goals · ${fmt(shotsData.for_xG)} xG`;
    if ($("teamAgainstShotCount")) $("teamAgainstShotCount").textContent = `${shotsData.against_shots.length} conceded · ${shotsData.against_goals} goals · ${fmt(shotsData.against_xG)} xGA`;
    renderPitchHeatmap("teamForPitch", shotsData.for_shots);
    renderPitchHeatmap("teamAgainstPitch", shotsData.against_shots);
  } catch (_) {
    if ($("teamForPitch")) $("teamForPitch").innerHTML = `<div class="empty">Shot map unavailable.</div>`;
    if ($("teamAgainstPitch")) $("teamAgainstPitch").innerHTML = `<div class="empty">Shot map unavailable.</div>`;
  }
}

function halfSplitTable(hs) {
  if (!hs || !hs.first_half) return `<div class="empty">Not enough matches for half-season split.</div>`;
  const f = hs.first_half, snd = hs.second_half;
  const row = (label, a, b) => `<tr><td>${label}</td><td class="num">${a}</td><td class="num">${b}</td></tr>`;
  return `<table><thead><tr><th></th><th class="num">First Half</th><th class="num">Second Half</th></tr></thead><tbody>
    ${row("Matches", f.matches, snd.matches)}
    ${row("W / D / L", `${f.wins}/${f.draws}/${f.loses}`, `${snd.wins}/${snd.draws}/${snd.loses}`)}
    ${row("Points per game", fmt(f.points_per_game), fmt(snd.points_per_game))}
    ${row("xG per game", fmt(f.xG_per_game), fmt(snd.xG_per_game))}
    ${row("xGA per game", fmt(f.xGA_per_game), fmt(snd.xGA_per_game))}
    ${row("npxGD per game", fmt(f.npxGD_per_game), fmt(snd.npxGD_per_game))}
  </tbody></table><div class="hint">${hs.interpretation}</div>`;
}

function homeAwaySplitTable(ha) {
  if (!ha || !ha.home) return `<div class="empty">Venue split not available.</div>`;
  const h = ha.home, a = ha.away;
  const row = (label, hv, av) => `<tr><td>${label}</td><td class="num">${hv}</td><td class="num">${av}</td></tr>`;
  return `<table><thead><tr><th>Metric</th><th class="num">Home</th><th class="num">Away</th></tr></thead><tbody>
    ${row("Matches", h.matches, a.matches)}
    ${row("Win Rate", pct(h.win_rate), pct(a.win_rate))}
    ${row("Points / Match", fmt(h.points_per_game), fmt(a.points_per_game))}
    ${row("xG / Match", fmt(h.xG_per_game), fmt(a.xG_per_game))}
    ${row("xGA / Match", fmt(h.xGA_per_game), fmt(a.xGA_per_game))}
  </tbody></table><div class="hint">${ha.interpretation}</div>`;
}

function strengthOfScheduleTable(sos) {
  if (!sos || !sos.available) return `<div class="empty">Strength of schedule split not available.</div>`;
  const top = sos.vs_stronger_opponents, bot = sos.vs_weaker_opponents;
  return `<table><thead><tr><th>Opponent Tier</th><th class="num">Matches</th><th class="num">Pts / Match</th><th class="num">xGD / Match</th></tr></thead><tbody>
    <tr><td>Vs Top Half (Positive xGD)</td><td class="num">${top.matches}</td><td class="num">${fmt(top.points_per_game)}</td><td class="num">${fmt(top.xGD_per_game)}</td></tr>
    <tr><td>Vs Bottom Half (Negative xGD)</td><td class="num">${bot.matches}</td><td class="num">${fmt(bot.points_per_game)}</td><td class="num">${fmt(bot.xGD_per_game)}</td></tr>
  </tbody></table><div class="hint">${sos.interpretation}</div>`;
}

function situationShareTable(sit) {
  const shares = sit.by_situation || {};
  return `<table><thead><tr><th>Phase</th><th class="num">xG</th><th class="num">Share</th></tr></thead><tbody>
    ${Object.entries(shares).map(([k, v]) => `<tr><td><strong>${k}</strong></td><td class="num">${fmt(v.xG)}</td><td class="num">${pct(v.share)}</td></tr>`).join("")}
  </tbody></table><div class="hint">Set Piece xG Share: <strong>${pct(sit.set_piece_xG_share)}</strong></div>`;
}

function archetypeBlock(arch) {
  return `
    <div style="padding:14px;background:var(--panel-2);border-radius:var(--radius-sm);border:1px solid var(--border)">
      <div style="font-size:16px;font-weight:800;color:var(--accent);margin-bottom:6px">⚡ ${arch.archetype_label}</div>
      <div style="font-size:13px;color:var(--text);line-height:1.4">${arch.narrative || arch.description}</div>
    </div>
  `;
}

function seasonComparisonSection(d) {
  const trends = d.season_trends ? Object.entries(d.season_trends) : [];
  if (trends.length < 1) return "";
  return `<div class="card" style="margin-top:20px">
    <div class="card-header"><span class="card-title">League Position & Points Progression by Matchweek</span></div>
    <div id="seasonPoints"></div>
    <div id="seasonRank" style="margin-top:16px"></div>
  </div>`;
}

function drawSeasonComparisonCharts(d) {
  if (!d.season_trends) return;
  drawSeasonLines("seasonPoints", d.season_trends, "points", { invert: false });
  drawSeasonLines("seasonRank", d.season_trends, "rank", { invert: true, ymax: Math.max(...Object.values(d.season_trends).map((t) => t.n_teams), 2) });
}

function drawSeasonLines(container, trends, metric, opts) {
  const el = document.getElementById(container);
  if (!el) return;
  const entries = Object.entries(trends);
  const w = 1100, h = 240, padL = 52, pad = 30, x0 = padL, x1 = w - pad, y0 = 16, y1 = h - 42;
  const maxMatchdays = Math.max(...entries.map(([, t]) => t.matchdays.length), 1);
  const x = (i) => x0 + (i * (x1 - x0)) / Math.max(maxMatchdays - 1, 1);
  let lines = "", dots = "";

  for (const [s, t] of entries) {
    const color = getThemeColor("--accent") || "#1ed760";
    const vals = t.matchdays.map((m) => m[metric]);
    if (opts.invert) {
      const y = (v) => y0 + ((v - 1) / (opts.ymax - 1)) * (y1 - y0);
      const path = vals.map((v, i) => `${i ? "L" : "M"}${x(i)},${y(v)}`).join(" ");
      lines += `<path d="${path}" fill="none" stroke="${color}" stroke-width="2.5"/>`;
      dots += t.matchdays.map((m, i) => hoverDot(x(i), y(m[metric]), `Matchday ${i + 1} (${m.date})\nRank #${m.rank} · Points ${m.points}`, color, 3.5)).join("");
    } else {
      const ymax = Math.max(...entries.flatMap(([, tt]) => tt.matchdays.flatMap((m) => [m[metric], m.xpts])), 1);
      const y = (v) => y1 - (v / ymax) * (y1 - y0);
      const path = vals.map((v, i) => `${i ? "L" : "M"}${x(i)},${y(v)}`).join(" ");
      const xptsPath = t.matchdays.map((m, i) => `${i ? "L" : "M"}${x(i)},${y(m.xpts)}`).join(" ");
      lines += `<path d="${path}" fill="none" stroke="${color}" stroke-width="2.5"/>`;
      lines += `<path d="${xptsPath}" fill="none" stroke="${color}" stroke-width="1.5" stroke-dasharray="4 3" opacity="0.65"/>`;
      dots += t.matchdays.map((m, i) => hoverDot(x(i), y(m[metric]), `Matchday ${i + 1} (${m.date})\nPoints ${m.points} · xPTS ${m.xpts}`, color, 3.5)).join("");
    }
  }

  const axisLabel = opts.invert ? "Table Rank (1 = Top)" : "Points";
  el.innerHTML = `<svg class="timeline-svg" viewBox="0 0 ${w} ${h}">
    <line x1="${x0}" y1="${y1}" x2="${x1}" y2="${y1}" stroke="var(--border)"/>
    <line x1="${x0}" y1="${y1}" x2="${x0}" y2="${y0}" stroke="var(--border)"/>
    ${lines}${dots}
    <text x="${x0}" y="${y0}" fill="var(--muted)" font-size="10">${axisLabel}</text>
    <text x="${x0 + (x1 - x0) / 2}" y="${h - 6}" fill="var(--muted)" font-size="10" text-anchor="middle">Matchday →</text>
  </svg>`;
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
  const goodColor = getThemeColor("--accent") || "#1ed760";
  const badColor = getThemeColor("--fg-bad") || "#f43f5e";
  const dots = lc.points.map((p, i) => hoverDot(x(i), y(p.cumulative_g_minus_xg), `${p.date}\nCumulative G − xG: ${fmt(p.cumulative_g_minus_xg, 2)}`, lc.final >= 0 ? goodColor : badColor, 3.5)).join("");
  const zero = y(0);

  el.innerHTML = `<svg class="timeline-svg" viewBox="0 0 ${w} ${h}">
    <line x1="${x0}" y1="${y1}" x2="${x1}" y2="${y1}" stroke="var(--border)"/>
    <line x1="${x0}" y1="${y1}" x2="${x0}" y2="${y0}" stroke="var(--border)"/>
    <line x1="${x0}" y1="${zero}" x2="${x1}" y2="${zero}" stroke="var(--border)" stroke-dasharray="3 4"/>
    <path d="${path}" fill="none" stroke="${lc.final >= 0 ? goodColor : badColor}" stroke-width="2.5"/>${dots}
    <text x="${x0}" y="${y0}" fill="var(--muted)" font-size="9.5">Cumulative Goals − xG Overperformance</text>
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
  const strokeColor = getThemeColor("--accent") || "#1ed760";
  const path = vals.map((v, i) => `${i ? "L" : "M"}${x(i)},${y(v)}`).join(" ");
  const dots = vals.map((v, i) => hoverDot(x(i), y(v), `${mt.dates[i]}\n${key}: ${fmt(v, 2)}`, strokeColor, 3.5)).join("");
  const zero = y(0);
  const entry = GLOSSARY[key] || {};

  el.innerHTML = `<svg class="timeline-svg" viewBox="0 0 ${w} ${h}">
    <line x1="${x0}" y1="${y1}" x2="${x1}" y2="${y1}" stroke="var(--border)"/>
    <line x1="${x0}" y1="${y1}" x2="${x0}" y2="${y0}" stroke="var(--border)"/>
    <line x1="${x0}" y1="${zero}" x2="${x1}" y2="${zero}" stroke="var(--border)" stroke-dasharray="3 4"/>
    <path d="${path}" fill="none" stroke="${strokeColor}" stroke-width="2.5"/>${dots}
    <text x="${x0}" y="${y0}" fill="var(--muted)" font-size="10.5">Rolling 5-Match ${entry.label || key}</text>
  </svg>`;
}

function drawLast5Bars(container, mt, style) {
  const el = document.getElementById(container);
  if (!el || !mt || !mt.dates || !mt.dates.length) { if (el) el.innerHTML = `<div class="empty">No recent data.</div>`; return; }
  const lastN = Math.min(5, mt.dates.length);
  const series = [
    { label: "Shots", key: "shots_for", color: "var(--accent)" },
    { label: "Goals", key: "goals_for", color: "var(--tier-good)" },
    { label: "xG", key: "xG_for", color: "var(--neutral)" },
  ];
  const w = 1100, h = 240, padL = 50, pad = 34, x0 = padL, x1 = w - pad, y0 = 18, y1 = h - 44;
  const dates = mt.dates.slice(-lastN);
  const benches = {};
  series.forEach((sr) => { const arr = mt[sr.key] || []; benches[sr.key] = style && style[sr.key] != null ? style[sr.key] : (arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : 0); });
  const vals = series.flatMap((sr) => (mt[sr.key] || []).slice(-lastN).concat([benches[sr.key]]));
  const maxV = Math.max(...vals.filter((v) => v !== null && v !== undefined), 0.001);
  const y = (v) => y1 - (v / maxV) * (y1 - y0);
  const groupW = (x1 - x0) / dates.length;
  const barW = Math.min(26, groupW * 0.22);
  let bars = "", dots = "", xgLabels = "";
  dates.forEach((dt, i) => {
    const gx = x0 + i * groupW + groupW / 2;
    series.forEach((sr, si) => {
      const arr = (mt[sr.key] || []).slice(-lastN);
      const v = arr[i];
      if (v == null) return;
      const bx = gx - barW * 1.5 + si * barW;
      const by = y(v);
      bars += `<rect x="${bx}" y="${by}" width="${barW - 2}" height="${y1 - by}" rx="2" fill="${sr.color}" opacity="0.85"><title>${dt} · ${sr.label}: ${fmt(v, 1)}</title></rect>`;
    });
    // benchmark line per group
    const benchX = gx - barW * 1.5;
    const benchY = y(benches[series[0].key]);
    xgLabels += `<text x="${gx}" y="${y1 + 14}" fill="var(--muted)" font-size="9.5" text-anchor="middle">${String(dt).slice(5)}</text>`;
    dots += `<line x1="${benchX}" y1="${benchY}" x2="${benchX + barW * 3}" y2="${benchY}" stroke="var(--border-hover)" stroke-dasharray="3 3" stroke-width="1"/>`;
  });
  el.innerHTML = `<svg class="timeline-svg" viewBox="0 0 ${w} ${h}">
    <line x1="${x0}" y1="${y1}" x2="${x1}" y2="${y1}" stroke="var(--border)"/>
    <line x1="${x0}" y1="${y1}" x2="${x0}" y2="${y0}" stroke="var(--border)"/>
    ${bars}${dots}${xgLabels}
    <text x="${x0}" y="${y0}" fill="var(--muted)" font-size="10">Shots · Goals · xG (last ${lastN}) — dashed = season avg</text>
    <text x="${x0 + (x1 - x0) / 2}" y="${h - 8}" fill="var(--muted)" font-size="9.5" text-anchor="middle">Match →</text>
  </svg>`;
}

function involvement(i) {
  return `<div class="kv">
    <span class="k">${term("xG_chain")}</span><span class="v">${fmt(i.xGChain)} · ${fmt(i.xGChain_per90, 3)}/90</span>
    <span class="k">${term("xG_buildup")}</span><span class="v">${fmt(i.xGBuildup)} · ${fmt(i.xGBuildup_per90, 3)}/90</span>
    <span class="k">Buildup share of chain</span><span class="v">${i.buildup_share_of_chain == null ? "N/A" : pct(i.buildup_share_of_chain, 1)}</span>
  </div><div class="hint">Higher buildup share represents pure deep creators; lower indicates direct penalty box finishers.</div>`;
}

function finishing(f) {
  const ci = f.g_minus_xg_ci95 ? `${f.g_minus_xg_ci95.low} to ${f.g_minus_xg_ci95.high}` : "N/A";
  const cls = f.g_minus_xg > 0 ? "good" : f.g_minus_xg < 0 ? "bad" : "";
  return `<div class="kv">
    <span class="k">${term("goals")}</span><span class="v">${fmt(f.goals, 0)}</span>
    <span class="k">${term("xG")}</span><span class="v">${fmt(f.xG)}</span>
    <span class="k">${term("g_minus_xg")}</span><span class="v"><span class="badge ${cls}">${f.g_minus_xg >= 0 ? "+" : ""}${fmt(f.g_minus_xg)}</span></span>
    <span class="k">Confidence interval (95%)</span><span class="v">${ci}</span>
  </div><div class="hint">${f.interpretation}</div>`;
}

function shotSelection(s) {
  return `<div class="kv">
    <span class="k">${term("shots")}</span><span class="v">${fmt(s.shots, 0)} · ${fmt(s.shots_per90, 2)}/90</span>
    <span class="k">${term("xG_per_shot")}</span><span class="v">${s.xG_per_shot == null ? "N/A" : fmt(s.xG_per_shot, 3)}</span>
    <span class="k">Non-Penalty xG / Shot</span><span class="v">${s.npxG_per_shot == null ? "N/A" : fmt(s.npxG_per_shot, 3)}</span>
  </div><div class="hint">${s.interpretation}</div>`;
}

const RADAR_LABEL_KEYS = { Goals: "goals", xG: "xG", "NP xG": "npxG", Assists: "assists", xA: "xA", Shots: "shots", "Key passes": "key_passes", xGChain: "xG_chain", xGBuildup: "xG_buildup" };

function drawRadar(container, profile) {
  const el = document.getElementById(container);
  if (!el) return;
  const size = 360, cx = size / 2, cy = size / 2, r = 125;
  const n = profile.length;
  if (n < 3) { el.innerHTML = `<div class="empty">Need ≥3 metrics for radar profile.</div>`; return; }
  const ang = (i) => -Math.PI / 2 + (i * 2 * Math.PI) / n;
  const pt = (i, rad) => [cx + rad * Math.cos(ang(i)), cy + rad * Math.sin(ang(i))];

  let rings = "";
  for (let g = 1; g <= 4; g++) {
    const rr = r * g / 4;
    let pts = ""; for (let i = 0; i < n; i++) { const [x, y] = pt(i, rr); pts += `${x},${y} `; }
    rings += `<polygon points="${pts}" fill="none" stroke="var(--border)" stroke-width="1"/>`;
  }
  let spokes = "", labels = "";
  for (let i = 0; i < n; i++) {
    const [x, y] = pt(i, r);
    spokes += `<line x1="${cx}" y1="${cy}" x2="${x}" y2="${y}" stroke="var(--border)" stroke-width="1"/>`;
    const [lx, ly] = pt(i, r + 18);
    labels += `<text x="${lx}" y="${ly}" fill="var(--muted)" font-size="10.5" font-weight="600" text-anchor="middle" dominant-baseline="middle">${profile[i].label}</text>`;
  }
  let poly = ""; const vals = [];
  const accentColor = getThemeColor("--accent") || "#1ed760";
  for (let i = 0; i < n; i++) {
    const pctVal = profile[i].percentile;
    const rr = r * pctVal / 100;
    const [x, y] = pt(i, rr);
    poly += `${x},${y} `;
    vals.push(`<circle cx="${x}" cy="${y}" r="3.5" fill="${accentColor}"/>`);
  }
  el.innerHTML = `<svg class="radar-svg" viewBox="0 0 ${size} ${size}">
    ${rings}${spokes}
    <polygon points="${poly}" fill="${accentColor}33" stroke="${accentColor}" stroke-width="2.5"/>
    ${labels}${vals.join("")}
  </svg>`;
}

// ==========================================================
// LEAGUE VIEW & "IS LYING" TABLE
// ==========================================================
$("leagueGo").addEventListener("click", runLeague);

async function runLeague() {
  const node = $("leagueContent");
  if (!node) return;
  loading(node);
  let season = seasonOf("leagueSeason");

  try {
    let d = await api("/api/v1/analyze/league", {
      league_name: state.league,
      season: season,
      start_date: dateOf("leagueFrom"),
      end_date: dateOf("leagueTo"),
    });

    let rows = (d.is_lying && d.is_lying.rows) || [];
    let notice = "";

    if (!rows.length && season === LATEST_SEASON) {
      season = LATEST_SEASON - 1;
      if ($("leagueSeason")) $("leagueSeason").value = String(season);
      d = await api("/api/v1/analyze/league", {
        league_name: state.league,
        season: season,
        start_date: dateOf("leagueFrom"),
        end_date: dateOf("leagueTo"),
      });
      rows = (d.is_lying && d.is_lying.rows) || [];
      notice = `${LEAGUE_LABEL[state.league] || state.league} ${LATEST_SEASON} season has not started matches yet. Displaying ${season} season.`;
    }

    renderLeague(node, d, notice);
  } catch (e) {
    errored(node, e.message);
  }
}

function renderLeague(node, d, notice = "") {
  clear(node);
  const rows = (d.is_lying && d.is_lying.rows) || [];
  const curSeason = seasonOf("leagueSeason");

  if (!rows.length) {
    node.innerHTML = `
      <div class="empty" style="padding:48px 16px">
        <div class="empty-title">${LEAGUE_LABEL[state.league] || state.league} ${curSeason} Has No Completed Matches</div>
        <div class="empty-sub">No league match statistics are available yet for this season.</div>
        <div style="margin-top:16px">
          <button class="primary" onclick="$('leagueSeason').value='${curSeason - 1}';runLeague()">
            View ${curSeason - 1} League Table →
          </button>
        </div>
      </div>
    `;
    return;
  }

  node.innerHTML = `
    ${notice ? `<div style="margin-bottom:16px"><span class="hero-pill accent">${notice}</span></div>` : ""}

    <!-- Full Width xPTS Is-Lying Table -->
    <div class="card">
      <div class="card-header">
        <div class="section-question">
          <span class="question-title">Expected Points (xPTS) Diagnostic & "Is-Lying" Table</span>
          <span class="question-desc">${LEAGUE_LABEL[state.league] || state.league} · ${curSeason} season</span>
        </div>
      </div>
      <table>
        <thead>
          <tr>
            <th>Rank</th>
            <th>Team</th>
            <th class="num">Points</th>
            <th class="num">${term("xpts")}</th>
            <th class="num">Pts Gap</th>
            <th class="num">${term("g_minus_xg")}</th>
            <th class="num">xGA − GA</th>
          </tr>
        </thead>
        <tbody>
          ${rows.map((r, i) => {
            const gapCls = r.xPTS_gap > 0 ? "good" : r.xPTS_gap < 0 ? "bad" : "";
            const isTop4 = i < 4;
            return `
              <tr>
                <td><span class="rank-badge ${isTop4 ? 'top4' : ''}">${i + 1}</span></td>
                <td><strong style="cursor:pointer;color:var(--text-bright)" onclick="$('teamName').value='${r.team}';activateTab('team');runTeam()">${r.team}</strong></td>
                <td class="num"><strong>${r.points}</strong></td>
                <td class="num" style="color:var(--accent);font-weight:700">${fmt(r.xPTS, 1)}</td>
                <td class="num"><span class="badge ${gapCls}">${r.xPTS_gap >= 0 ? "+" : ""}${fmt(r.xPTS_gap, 1)}</span></td>
                <td class="num" style="color:${r.g_minus_xg >= 0 ? 'var(--fg-good)' : 'var(--fg-bad)'}">${r.g_minus_xg >= 0 ? '+' : ''}${fmt(r.g_minus_xg)}</td>
                <td class="num">${fmt(r.xga_minus_ga)}</td>
              </tr>
            `;
          }).join("")}
        </tbody>
      </table>
      <div class="hint" style="margin-top:12px">${d.is_lying.interpretation}</div>
    </div>

    <!-- Row 2: PPDA Pressing Rankings -->
    ${d.ppda_ranking && d.ppda_ranking.ranking && d.ppda_ranking.ranking.length ? `
      <div class="card" style="margin-top:20px">
        <div class="card-header">
          <div class="section-question">
            <span class="question-title">PPDA Pressing Intensity Rankings</span>
            <span class="question-desc">Division pressing pace and deep box penetration</span>
          </div>
        </div>
        <table><thead><tr><th>Rank</th><th>Team</th><th class="num">PPDA (Att)</th><th class="num">OPPDA (Def)</th><th class="num">Deep Completions</th></tr></thead><tbody>
          ${d.ppda_ranking.ranking.slice(0, 14).map((p, i) => `<tr><td>#${i+1}</td><td><strong style="cursor:pointer" onclick="$('teamName').value='${p.team}';activateTab('team');runTeam()">${p.team}</strong></td><td class="num"><strong>${fmt(p.PPDA)}</strong></td><td class="num">${fmt(p.OPPDA)}</td><td class="num">${p.deep_completions}</td></tr>`).join("")}
        </tbody></table>
      </div>
    ` : ""}

    <div class="caveat"><strong>Limitations.</strong><ul>${d.limitations.map((l) => `<li>${l}</li>`).join("")}</ul></div>
  `;
}

// ==========================================================
// DISCOVER & SCOUT VIEW
// ==========================================================
$("discoverGo").addEventListener("click", runDiscover);

async function runDiscover() {
  const node = $("discoverContent"); loading(node);
  try {
    const d = await api("/api/v1/discover/players", {
      league_name: state.league, season: seasonOf("discoverSeasons"),
      seasons: seasonsOf("discoverSeasons"),
      positions: selectedPositionValues("discoverPositions"),
      minimum_minutes: parseFloat($("discoverMinutes").value) || 900,
      order_by: $("discoverOrderBy").value,
      limit: parseInt($("discoverLimit").value, 10) || 20,
      min_age: $("discoverMinAge").value ? parseInt($("discoverMinAge").value, 10) : null,
      max_age: $("discoverMaxAge").value ? parseInt($("discoverMaxAge").value, 10) : null,
      start_date: dateOf("discoverFrom"), end_date: dateOf("discoverTo"),
    });
    renderDiscover(node, d);
  } catch (e) { errored(node, e.message); }
}

function renderDiscover(node, d) {
  clear(node);
  if (!d.players || !d.players.length) {
    node.innerHTML = `
      <div class="empty" style="padding:48px 16px">
        <div class="empty-title">No Players Match Current Filters</div>
        <div class="empty-sub">If this season has just started or has low minutes, try reducing the Min Minutes filter or switching to the previous season.</div>
      </div>
    `;
    return;
  }

  node.innerHTML = `
    <div class="card">
      <div class="card-header">
        <div class="section-question">
          <span class="question-title">Ranked Discovery Pool (${d.players.length} players found)</span>
          <span class="question-desc">Filtered by position role, minutes threshold, and involvement metric</span>
        </div>
      </div>
      <table>
        <thead>
          <tr>
            <th>Player</th>
            <th>Team</th>
            <th>Role</th>
            <th class="num">Age</th>
            <th class="num">Min</th>
            <th class="num">${term("goals")}</th>
            <th class="num">${term("npxg")}</th>
            <th class="num">${term("assists")}</th>
            <th class="num">${term("xa")}</th>
            <th class="num">${term("xG_chain")}</th>
            <th class="num">${term("xG_buildup")}</th>
            <th>Scout</th>
          </tr>
        </thead>
        <tbody>
          ${d.players.map((p) => `
            <tr>
              <td><strong style="cursor:pointer;color:var(--text-bright)" onclick="$('playerName').value='${p.name}';activateTab('player');runPlayer()">${p.name}</strong></td>
              <td>${p.team || "—"}</td>
              <td><span class="badge">${p.position || "—"}</span></td>
              <td class="num">${p.age ?? "—"}</td>
              <td class="num">${fmt(p.minutes, 0)}</td>
              <td class="num"><strong>${fmt(p.goals, 0)}</strong></td>
              <td class="num">${fmt(p.npxG)}</td>
              <td class="num">${fmt(p.assists, 0)}</td>
              <td class="num">${fmt(p.xA)}</td>
              <td class="num" style="color:var(--accent);font-weight:700">${fmt(p.xGChain)}</td>
              <td class="num">${fmt(p.xGBuildup)}</td>
              <td>
                <button class="ghost" style="padding:3px 10px;font-size:11.5px" onclick="$('playerName').value='${p.name}';activateTab('player');runPlayer()">Profile →</button>
              </td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

// ==========================================================
// COMPARE & BASKET VIEW
// ==========================================================
$("compareGo").addEventListener("click", runCompare);
$("compareA").addEventListener("keydown", (e) => { if (e.key === "Enter") runCompare(); });
$("compareB").addEventListener("keydown", (e) => { if (e.key === "Enter") runCompare(); });

async function runCompare() {
  const mode = $("compareMode").value;
  const a = $("compareA").value.trim(), b = $("compareB").value.trim();
  if (!a || !b) return;
  const node = $("compareContent"); loading(node);
  const endpoint = mode === "teams" ? "/api/v1/compare/teams" : "/api/v1/compare/players";
  const body = mode === "teams"
    ? { team_1: a, team_2: b, league_name: state.league, season: seasonOf("compareSeason"), start_date: dateOf("compareFrom"), end_date: dateOf("compareTo") }
    : { player_1: a, player_2: b, league_name: state.league, season: seasonOf("compareSeason"), start_date: dateOf("compareFrom"), end_date: dateOf("compareTo") };
  try {
    const d = await api(endpoint, body);
    if (mode === "teams") renderCompareTeams(node, d);
    else renderComparePlayers(node, d);
  } catch (e) { errored(node, e.message); }
}

function renderComparePlayers(node, d) {
  clear(node);
  const names = Object.keys(d.players);
  if (names.length < 2) return;
  const p1 = d.players[names[0]], p2 = d.players[names[1]];

  node.innerHTML = `
    <div class="grid cols-2">
      <div class="card">
        <div class="card-header"><span class="card-title">Overlaid Pizza Radars</span></div>
        <div id="compareRadar"></div>
      </div>
      <div class="card">
        <div class="card-header"><span class="card-title">Head-to-Head Statistics</span></div>
        <table>
          <thead><tr><th>Metric</th><th class="num">${names[0]}</th><th class="num">${names[1]}</th></tr></thead>
          <tbody>
            <tr><td>Goals</td><td class="num"><strong>${fmt(p1.raw.goals, 0)}</strong></td><td class="num"><strong>${fmt(p2.raw.goals, 0)}</strong></td></tr>
            <tr><td>NP xG</td><td class="num">${fmt(p1.raw.npxG)}</td><td class="num">${fmt(p2.raw.npxG)}</td></tr>
            <tr><td>Assists / xA</td><td class="num">${fmt(p1.raw.assists, 0)} (${fmt(p1.raw.xA)})</td><td class="num">${fmt(p2.raw.assists, 0)} (${fmt(p2.raw.xA)})</td></tr>
            <tr><td>xGChain /90</td><td class="num">${fmt(p1.per90.xGChain, 2)}</td><td class="num">${fmt(p2.per90.xGChain, 2)}</td></tr>
            <tr><td>xGBuildup /90</td><td class="num">${fmt(p1.per90.xGBuildup, 2)}</td><td class="num">${fmt(p2.per90.xGBuildup, 2)}</td></tr>
            <tr><td>Minutes</td><td class="num">${fmt(p1.minutes, 0)}</td><td class="num">${fmt(p2.minutes, 0)}</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  `;
  drawCompareRadar("compareRadar", p1.radar, p2.radar, names[0], names[1]);
}

function drawCompareRadar(container, r1, r2, name1, name2) {
  const el = document.getElementById(container); if (!el) return;
  const size = 360, cx = size / 2, cy = size / 2, r = 125;
  const n = r1.length;
  if (n < 3) return;
  const ang = (i) => -Math.PI / 2 + (i * 2 * Math.PI) / n;
  const pt = (i, rad) => [cx + rad * Math.cos(ang(i)), cy + rad * Math.sin(ang(i))];

  let rings = "";
  for (let g = 1; g <= 4; g++) {
    const rr = r * g / 4;
    let pts = ""; for (let i = 0; i < n; i++) { const [x, y] = pt(i, rr); pts += `${x},${y} `; }
    rings += `<polygon points="${pts}" fill="none" stroke="var(--border)" stroke-width="1"/>`;
  }
  let poly1 = "", poly2 = "", labels = "";
  const color1 = getThemeColor("--accent") || "#1ed760";
  const color2 = getThemeColor("--neutral") || "#38bdf8";

  for (let i = 0; i < n; i++) {
    const [x1, y1] = pt(i, r * r1[i].percentile / 100);
    const [x2, y2] = pt(i, r * (r2[i] ? r2[i].percentile : 50) / 100);
    poly1 += `${x1},${y1} `;
    poly2 += `${x2},${y2} `;
    const [lx, ly] = pt(i, r + 18);
    labels += `<text x="${lx}" y="${ly}" fill="var(--muted)" font-size="10" text-anchor="middle">${r1[i].label}</text>`;
  }
  el.innerHTML = `<svg class="radar-svg" viewBox="0 0 ${size} ${size}">
    ${rings}
    <polygon points="${poly1}" fill="${color1}33" stroke="${color1}" stroke-width="2"/>
    <polygon points="${poly2}" fill="${color2}33" stroke="${color2}" stroke-width="2"/>
    ${labels}
    <text x="16" y="24" fill="${color1}" font-size="11">● ${name1}</text>
    <text x="16" y="42" fill="${color2}" font-size="11">● ${name2}</text>
  </svg>`;
}

function renderCompareTeams(node, d) {
  clear(node);
  const t1 = d.team_1, t2 = d.team_2;
  node.innerHTML = `
    <div class="card">
      <div class="card-header"><span class="card-title">${t1.name} vs ${t2.name} Tactical Comparison</span></div>
      <table>
        <thead><tr><th>Metric</th><th class="num">${t1.name}</th><th class="num">${t2.name}</th></tr></thead>
        <tbody>
          <tr><td>xG / match</td><td class="num">${fmt(t1.report.style.xG_per_game)}</td><td class="num">${fmt(t2.report.style.xGA_per_game)}</td></tr>
          <tr><td>xGA / match</td><td class="num">${fmt(t1.report.style.xGA_per_game)}</td><td class="num">${fmt(t2.report.style.xGA_per_game)}</td></tr>
          <tr><td>xGD / match</td><td class="num">${fmt(t1.report.style.xG_diff_per_game)}</td><td class="num">${fmt(t2.report.style.xG_diff_per_game)}</td></tr>
          <tr><td>PPDA Pressing</td><td class="num">${fmt(t1.report.style.PPDA)}</td><td class="num">${fmt(t2.report.style.PPDA)}</td></tr>
          <tr><td>Deep Box Passes</td><td class="num">${fmt(t1.report.style.deep_completions, 0)}</td><td class="num">${fmt(t2.report.style.deep_completions, 0)}</td></tr>
        </tbody>
      </table>
    </div>
  `;
}

// ==========================================================
// PREDICT & SIMULATION
// ==========================================================
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
      home_team: home, away_team: away, league_name: state.league,
      season: seasonOf("predSeason"), use_xg: $("predUseXg").checked,
    });
    renderPredict(node, d);
  } catch (e) { errored(node, e.message); }
}

function renderPredict(node, d) {
  clear(node);
  const p = d.ensemble;
  node.innerHTML = `
    <div class="card">
      <div class="card-header">
        <div class="section-question">
          <span class="question-title">Bivariate Dixon-Coles Match Forecast</span>
          <span class="question-desc">Simulated outcome probabilities and expected goal intensities</span>
        </div>
      </div>
      <div class="prob-bar-container">
        <div class="prob-bar">
          <div class="seg home" style="width:${p.p_home*100}%"><span class="seg-pct">${pct(p.p_home)}</span><span class="seg-name">${d.home_team}</span></div>
          <div class="seg draw" style="width:${p.p_draw*100}%"><span class="seg-pct">${pct(p.p_draw)}</span><span class="seg-name">Draw</span></div>
          <div class="seg away" style="width:${p.p_away*100}%"><span class="seg-pct">${pct(p.p_away)}</span><span class="seg-name">${d.away_team}</span></div>
        </div>
      </div>
      <div class="kv" style="margin-top:16px">
        <span class="k">Expected Goals (Lambda)</span><span class="v">${fmt(d.dixon_coles.lambda_home)} (Home) — ${fmt(d.dixon_coles.lambda_away)} (Away)</span>
        <span class="k">Most Probable Scorelines</span><span class="v">${d.dixon_coles.most_likely_scorelines.map((s)=>`${s.score} (${pct(s.probability)})`).join(" · ")}</span>
      </div>
    </div>
  `;
}

async function runSim() {
  const node = $("predictContent"); loading(node);
  try {
    const d = await api("/api/v1/predict/season-simulation", {
      league_name: state.league, season: seasonOf("simSeason"),
      n_sims: parseInt($("simCount").value, 10) || 2000,
    });
    renderSim(node, d);
  } catch (e) { errored(node, e.message); }
}

function renderSim(node, d) {
  clear(node);
  node.innerHTML = `
    <div class="card">
      <div class="card-header">
        <div class="section-question">
          <span class="question-title">Rest-of-Season Monte Carlo Simulation (${d.simulations} runs)</span>
          <span class="question-desc">Projected points, title probabilities, top 4 finish, and relegation risk</span>
        </div>
      </div>
      <table>
        <thead><tr><th>Team</th><th class="num">Current Pts</th><th class="num">Simulated Pts</th><th class="num">Title %</th><th class="num">Top 4 %</th><th class="num">Relegation %</th></tr></thead>
        <tbody>
          ${d.projections.map((p) => `
            <tr>
              <td><strong>${p.team}</strong></td>
              <td class="num">${p.current_points}</td>
              <td class="num" style="color:var(--accent);font-weight:700">${fmt(p.simulated_points, 1)}</td>
              <td class="num">${pct(p.champion_probability)}</td>
              <td class="num">${pct(p.top_4_probability)}</td>
              <td class="num" style="color:${p.relegation_probability>0.5?'var(--fg-bad)':'var(--text)'}">${pct(p.relegation_probability)}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

async function runCal() {
  const node = $("predictContent"); loading(node);
  try {
    const d = await api("/api/v1/predict/calibration", {
      league_name: state.league, season: seasonOf("calSeason"),
    });
    renderCal(node, d);
  } catch (e) { errored(node, e.message); }
}

function renderCal(node, d) {
  clear(node);
  node.innerHTML = `
    <div class="card">
      <div class="card-header">
        <div class="section-question">
          <span class="question-title">Walk-Forward Model Calibration Benchmarks</span>
          <span class="question-desc">Evaluating probability accuracy, Brier Score, Log Loss, and RPS</span>
        </div>
      </div>
      <table>
        <thead><tr><th>Model</th><th class="num">Accuracy</th><th class="num">Brier Score</th><th class="num">Log Loss</th><th class="num">RPS</th></tr></thead>
        <tbody>
          ${Object.entries(d.models).map(([name, m]) => `
            <tr>
              <td><strong>${name}</strong></td>
              <td class="num">${pct(m.accuracy)}</td>
              <td class="num">${fmt(m.brier, 4)}</td>
              <td class="num">${fmt(m.log_loss, 4)}</td>
              <td class="num" style="color:var(--accent);font-weight:700">${fmt(m.rps, 4)}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

// ==========================================================
// GLOSSARY / REFERENCE
// ==========================================================
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
    return `<div class="card" style="margin-top:20px">
      <div class="card-header"><span class="card-title">${g.group}</span></div>
      ${entries.map((en) => `<div class="gloss" style="margin:12px 0"><div class="gloss-label" style="font-weight:700;color:var(--accent)">${en.label}</div>
        <div class="gloss-short" style="color:var(--text-bright);font-size:13px;margin:2px 0">${en.short}</div>
        <div class="gloss-long" style="color:var(--muted);font-size:12px">${en.long}</div></div>`).join("")}
    </div>`;
  }).join("") || `<div class="empty">No metrics match "${query}".</div>`;
}
document.getElementById("infoSearch").addEventListener("input", renderInfo);

const initialHashTab = (window.location.hash || "#player").slice(1);
if (initialHashTab && document.querySelector(`.sidebar-nav .nav-item[data-tab="${initialHashTab}"]`)) {
  activateTab(initialHashTab, false);
} else {
  activateTab("player", false);
}
updateWatchlistPill();

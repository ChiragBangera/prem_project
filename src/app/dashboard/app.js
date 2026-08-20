"use strict";

const CURRENT_YEAR = new Date().getFullYear();
const CURRENT_MONTH = new Date().getMonth() + 1; // 1-12
// European football seasons start in July/August
const LATEST_SEASON = CURRENT_MONTH >= 7 ? CURRENT_YEAR : CURRENT_YEAR - 1;
const SEASON_RANGE = { first: 2014, last: LATEST_SEASON };

const state = {
  league: "EPL",
  tab: "match",
  season: LATEST_SEASON,
  hiddenSeasons: new Set(),
  pitchModes: {}, // containerId -> 'shots' | 'heatmap'
  roundsData: null,
  roundsLoadedFor: null,
};

const $ = (id) => document.getElementById(id);

const TAB_TITLES = {
  match: { title: "Match Intelligence Deep-Dive", desc: "Full pitch tactical shot maps, cumulative xG timelines, big chance audits, and process diagnostics." },
  player: { title: "Player Scouting & Intelligence", desc: "Radars, tactical shot density heatmaps, finishing diagnostics, and peer similarity." },
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
  const btn = e.target.closest(".nav-item[data-tab]");
  if (!btn) return;
  activateTab(btn.dataset.tab);
});

// League Picker Switching
document.getElementById("leaguePicker").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-league]");
  if (!btn) return;
  state.league = btn.dataset.league;
  localStorage.setItem("prem_league", state.league);
  document.querySelectorAll("#leaguePicker button").forEach((b) => b.classList.toggle("active", b === btn));
  if (state.tab === "match") loadRounds();
  if (state.tab === "league") runLeague();
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

// Season dropdown change listeners for immediate reactivity
$("matchSeason").addEventListener("change", () => loadRounds());
$("leagueSeason").addEventListener("change", () => runLeague());

// Chart Tooltip
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

// ==========================================================
// TACTICAL PITCH & GAUSSIAN HEATMAP CANVAS ENGINE
// ==========================================================
function renderPitchHeatmap(containerId, shots, options = {}) {
  const container = document.getElementById(containerId);
  if (!container) return;

  const currentMode = state.pitchModes[containerId] || options.defaultMode || "shots";
  state.pitchModes[containerId] = currentMode;

  const width = options.width || 700;
  const height = options.height || 440;
  const isHalfPitch = options.halfPitch || false;

  container.innerHTML = `
    <div class="pitch-container">
      <div class="pitch-toolbar">
        <div class="pitch-mode-group">
          <button class="pitch-mode-btn ${currentMode === 'shots' ? 'active' : ''}" data-mode="shots">📍 Shot Map</button>
          <button class="pitch-mode-btn ${currentMode === 'heatmap' ? 'active' : ''}" data-mode="heatmap">🔥 Density Heatmap</button>
        </div>
        <div class="pitch-legend">
          <div class="pitch-legend-item"><span class="pitch-dot" style="background:#f59e0b;box-shadow:0 0 8px #f59e0b"></span> Goal</div>
          <div class="pitch-legend-item"><span class="pitch-dot" style="background:#38bdf8"></span> Saved</div>
          <div class="pitch-legend-item"><span class="pitch-dot" style="background:#f43f5e"></span> Missed</div>
          <div class="pitch-legend-item"><span class="pitch-dot" style="background:#94a3b8"></span> Blocked</div>
          <span style="opacity:0.6;margin-left:4px">Radius = xG size</span>
        </div>
      </div>
      <canvas id="${containerId}_canvas" class="pitch-canvas" width="${width}" height="${height}"></canvas>
    </div>
  `;

  const canvas = document.getElementById(`${containerId}_canvas`);
  const ctx = canvas.getContext("2d");

  container.querySelectorAll(".pitch-mode-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.pitchModes[containerId] = btn.dataset.mode;
      renderPitchHeatmap(containerId, shots, options);
    });
  });

  drawPitchBackground(ctx, width, height, isHalfPitch);

  if (currentMode === "heatmap") {
    drawGaussianHeatmap(ctx, shots, width, height);
    drawPitchLines(ctx, width, height, isHalfPitch);
  } else {
    drawShotCircles(ctx, shots, width, height, options);
  }

  canvas.addEventListener("mousemove", (e) => {
    if (currentMode !== "shots") {
      if (chartTipEl) chartTipEl.classList.remove("show");
      return;
    }
    const rect = canvas.getBoundingClientRect();
    const mouseX = ((e.clientX - rect.left) / rect.width) * width;
    const mouseY = ((e.clientY - rect.top) / rect.height) * height;

    let closest = null;
    let minDist = 18;

    shots.forEach((s) => {
      const sx = s.X * width;
      const sy = (1 - s.Y) * height;
      const dist = Math.hypot(mouseX - sx, mouseY - sy);
      if (dist < minDist) {
        minDist = dist;
        closest = s;
      }
    });

    if (closest) {
      const tip = `<strong>${closest.player || "Shooter"} (${closest.minute}')</strong><br>
        Outcome: <span style="color:${closest.result === 'Goal' ? '#f59e0b' : '#38bdf8'};font-weight:700">${closest.result}</span><br>
        xG: <strong>${fmt(closest.xG, 3)}</strong> · ${closest.situation || "OpenPlay"}<br>
        Shot: ${closest.shotType || "Foot"}${closest.lastAction ? ` · Via ${closest.lastAction}` : ""}`;
      chartTipEl.innerHTML = tip;
      chartTipEl.classList.add("show");
      chartTipEl.style.left = `${e.clientX + 14}px`;
      chartTipEl.style.top = `${e.clientY + 14}px`;
    } else {
      if (chartTipEl) chartTipEl.classList.remove("show");
    }
  });

  canvas.addEventListener("mouseleave", () => {
    if (chartTipEl) chartTipEl.classList.remove("show");
  });
}

function drawPitchBackground(ctx, w, h, isHalf) {
  const stripes = 12;
  const sw = w / stripes;
  for (let i = 0; i < stripes; i++) {
    ctx.fillStyle = i % 2 === 0 ? "#092014" : "#06180e";
    ctx.fillRect(i * sw, 0, sw, h);
  }
  drawPitchLines(ctx, w, h, isHalf);
}

function drawPitchLines(ctx, w, h, isHalf) {
  ctx.strokeStyle = "rgba(255, 255, 255, 0.35)";
  ctx.lineWidth = 1.5;
  ctx.strokeRect(12, 12, w - 24, h - 24);

  // Center Line & Circle
  ctx.beginPath();
  ctx.moveTo(w / 2, 12);
  ctx.lineTo(w / 2, h - 12);
  ctx.stroke();

  ctx.beginPath();
  ctx.arc(w / 2, h / 2, 52, 0, Math.PI * 2);
  ctx.stroke();

  ctx.fillStyle = "rgba(255, 255, 255, 0.4)";
  ctx.beginPath();
  ctx.arc(w / 2, h / 2, 2.5, 0, Math.PI * 2);
  ctx.fill();

  // Left Box
  ctx.strokeRect(12, h / 2 - 76, 96, 152);
  ctx.strokeRect(12, h / 2 - 34, 32, 68);
  ctx.beginPath();
  ctx.arc(12 + 64, h / 2, 2, 0, Math.PI * 2);
  ctx.fill();

  // Right Box
  ctx.strokeRect(w - 108, h / 2 - 76, 96, 152);
  ctx.strokeRect(w - 44, h / 2 - 34, 32, 68);
  ctx.beginPath();
  ctx.arc(w - 12 - 64, h / 2, 2, 0, Math.PI * 2);
  ctx.fill();

  // Arcs
  ctx.beginPath();
  ctx.arc(12 + 64, h / 2, 38, -0.9, 0.9);
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(w - 12 - 64, h / 2, 38, Math.PI - 0.9, Math.PI + 0.9);
  ctx.stroke();
}

function drawShotCircles(ctx, shots, w, h, options) {
  shots.forEach((s) => {
    const x = s.X * w;
    const y = (1 - s.Y) * h;
    const xg = Math.max(parseFloat(s.xG) || 0, 0.01);
    const r = Math.min(4 + Math.sqrt(xg) * 20, 24);

    let fill = "rgba(148, 163, 184, 0.4)";
    let stroke = "#94a3b8";

    if (s.result === "Goal") {
      fill = "rgba(245, 158, 11, 0.9)";
      stroke = "#f59e0b";
      ctx.beginPath();
      ctx.arc(x, y, r + 4, 0, Math.PI * 2);
      ctx.strokeStyle = "rgba(245, 158, 11, 0.4)";
      ctx.lineWidth = 2;
      ctx.stroke();
    } else if (s.result === "SavedShot") {
      fill = "rgba(56, 189, 248, 0.75)";
      stroke = "#38bdf8";
    } else if (s.result === "MissedShots" || s.result === "ShotOnPost") {
      fill = "rgba(244, 63, 94, 0.7)";
      stroke = "#f43f5e";
    } else if (s.result === "BlockedShot") {
      fill = "rgba(100, 116, 139, 0.5)";
      stroke = "#64748b";
    }

    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fillStyle = fill;
    ctx.fill();
    ctx.strokeStyle = stroke;
    ctx.lineWidth = 1.5;
    ctx.stroke();
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
    const radius = 36 + xg * 26;

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
    renderRecentFixtures(state.roundsData);
    return;
  }

  if ($("fixtureCountBadge")) $("fixtureCountBadge").textContent = "Loading…";
  if ($("roundSelect")) $("roundSelect").innerHTML = `<option value="">Loading rounds…</option>`;
  if ($("matchRecentFeed")) $("matchRecentFeed").innerHTML = `<div class="loading"><div class="loading-pulse"><span></span><span></span><span></span></div><span>Loading recent matches for ${LEAGUE_LABEL[state.league] || state.league} ${season}…</span></div>`;

  try {
    const d = await api("/api/v1/matches/rounds", { league_name: state.league, season });
    state.roundsData = d;
    state.roundsLoadedFor = key;

    if ($("fixtureCountBadge")) $("fixtureCountBadge").textContent = `${d.n_played} Played`;

    renderRecentFixtures(d);

    const rounds = d.rounds || [];
    if (rounds.length) {
      $("roundSelect").innerHTML = rounds.map((r) => `<option value="${r.round}">Round ${r.round}</option>`).join("");
      const latestRound = rounds[rounds.length - 1];
      $("roundSelect").value = String(latestRound.round);
      populateMatchesForRound();
    } else {
      $("roundSelect").innerHTML = `<option value="">No rounds found</option>`;
      $("matchSelect").innerHTML = `<option value="">—</option>`;
    }
  } catch (e) {
    if ($("matchRecentFeed")) $("matchRecentFeed").innerHTML = `<div class="error">Failed to load fixtures: ${e.message}</div>`;
    if ($("roundSelect")) $("roundSelect").innerHTML = `<option value="">Error loading rounds</option>`;
  }
}

function renderRecentFixtures(d) {
  const feed = $("matchRecentFeed");
  if (!feed) return;
  const recent = d.latest_matches || [];
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
  }).join("");
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
    renderMatch(node, d);
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

function renderMatch(node, d) {
  const n = d.narrative;
  clear(node);

  const homeShots = (d.shot_map.home || []).map((s) => ({ ...s, side: "home" }));
  const awayShots = (d.shot_map.away || []).map((s) => ({ ...s, side: "away" }));
  const allShots = [...homeShots, ...awayShots];

  node.innerHTML = `
    <!-- Match Hero Scoreline Banner -->
    <div class="player-hero-card">
      <div class="hero-main" style="justify-content:center;text-align:center">
        <div>
          <div style="font-size:11px;text-transform:uppercase;color:var(--accent);letter-spacing:1.2px;font-weight:800">
            OFFICIAL MATCH INTELLIGENCE
          </div>
          <div style="font-size:36px;font-weight:900;color:var(--text-bright);margin:8px 0;letter-spacing:-0.5px">
            ${n.scoreline.h} — ${n.scoreline.a}
          </div>
          <div style="font-size:15px;color:var(--accent);font-family:var(--mono);font-weight:700">
            Expected Goals (xG): ${fmt(n.xG.h)} vs ${fmt(n.xG.a)}
          </div>
          <div class="hint" style="margin-top:10px;max-width:650px;margin-left:auto;margin-right:auto;font-size:13px">
            ${n.narrative}
          </div>
        </div>
      </div>
    </div>

    <!-- Row 1: Full Pitch Shot Map vs Cumulative xG Flow Timeline -->
    <div class="grid cols-2">
      <div class="card">
        <div class="card-header">
          <span class="card-title">
            <svg class="card-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="m4.93 4.93 4.24 4.24M14.83 14.83l4.24 4.24"/></svg>
            Full Pitch Tactical Shot Map & Heatmap
          </span>
          <span style="font-size:11px;color:var(--muted)">${allShots.length} total shots</span>
        </div>
        <div id="matchPitch"></div>
      </div>

      <div class="card">
        <div class="card-header">
          <span class="card-title">
            <svg class="card-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
            Cumulative xG Timeline Flow
          </span>
        </div>
        <div id="xgtl"></div>
      </div>
    </div>

    <!-- Row 2: Big Chance Inventory vs Situations Breakdown -->
    <div class="grid cols-2" style="margin-top:20px">
      <div class="card">
        <div class="card-header">
          <span class="card-title">Big Chance Inventory (xG ≥ ${d.big_chance_inventory.xG_threshold})</span>
        </div>
        ${bigChances(d.big_chance_inventory)}
      </div>

      <div class="card">
        <div class="card-header">
          <span class="card-title">Situations Breakdown (Open Play vs Set Pieces)</span>
        </div>
        ${situationBreakdown(d.situation_breakdown)}
      </div>
    </div>

    <div class="caveat"><strong>Limitations.</strong><ul>${d.limitations.map((l) => `<li>${l}</li>`).join("")}</ul></div>
  `;

  renderPitchHeatmap("matchPitch", allShots);
  drawXgTimeline("xgtl", d.xg_timeline);
}

function bigChances(inv) {
  return `<table><thead><tr><th>Side</th><th>Min</th><th>Shooter</th><th class="num">xG</th><th>Result</th></tr></thead><tbody>
    ${inv.home.map((s) => row("Home", s)).join("")}${inv.away.map((s) => row("Away", s)).join("")}
  </tbody></table>`;
  function row(side, s) { return `<tr><td><strong>${side}</strong></td><td>${s.minute}'</td><td>${s.player || "—"}</td><td class="num">${fmt(s.xG)}</td><td><span class="badge ${s.result === 'Goal' ? 'good' : ''}">${s.result}</span></td></tr>`; }
}

function situationBreakdown(sb) {
  const head = `<tr><th>${term("situations")}</th><th class="num">${term("shots")}</th><th class="num">${term("xG")}</th><th class="num">${term("goals")}</th></tr>`;
  const rows = (obj) => Object.entries(obj).sort((a, b) => b[1].xG - a[1].xG).map(([k, v]) => `<tr><td>${k}</td><td class="num">${v.shots}</td><td class="num">${fmt(v.xG)}</td><td class="num"><strong>${v.goals}</strong></td></tr>`).join("");
  return `<table><thead><tr><th colspan=4 style="color:var(--accent)">Home Team</th></tr>${head}</thead><tbody>${rows(sb.home)}</tbody></table>` +
    `<table style="margin-top:14px"><thead><tr><th colspan=4 style="color:var(--accent-emerald)">Away Team</th></tr>${head}</thead><tbody>${rows(sb.away)}</tbody></table>`;
}

function drawXgTimeline(container, tl) {
  const el = document.getElementById(container); if (!el) return;
  const w = 1100, h = 260, padL = 56, pad = 30, x0 = padL, x1 = w - pad, y0 = 24, y1 = h - 40;
  const home = tl.home || [], away = tl.away || [];
  const allMax = Math.max(...home.map((p) => p.cumulative_xG), ...away.map((p) => p.cumulative_xG), 0.5);
  const minuteMax = Math.max(...home.map((p) => p.minute), ...away.map((p) => p.minute), 90);
  const x = (m) => x0 + (m / minuteMax) * (x1 - x0);
  const y = (v) => y1 - (v / allMax) * (y1 - y0);
  const path = (pts, color) => pts.length ? `<path d="${pts.map((p, i) => `${i ? "L" : "M"}${x(p.minute)},${y(p.cumulative_xG)}`).join(" ")}" fill="none" stroke="${color}" stroke-width="2.5"/>` : "";
  const dots = (pts, color) => pts.map((p) => hoverDot(x(p.minute), y(p.cumulative_xG), `${p.minute}' — Cumulative xG: ${fmt(p.cumulative_xG, 3)}`, color, 3.5)).join("");

  el.innerHTML = `<svg class="timeline-svg" viewBox="0 0 ${w} ${h}">
    <line x1="${x0}" y1="${y1}" x2="${x1}" y2="${y1}" stroke="#1e293b"/>
    <line x1="${x0}" y1="${y1}" x2="${x0}" y2="${y0}" stroke="#1e293b"/>
    ${path(home, "#38bdf8")}${path(away, "#10b981")}
    ${dots(home, "#38bdf8")}${dots(away, "#10b981")}
    <text x="${x0}" y="${y0}" fill="#94a3b8" font-size="10.5"><tspan fill="#38bdf8">— Home</tspan>  <tspan fill="#10b981">— Away</tspan>  · Cumulative Match xG</text>
    <text x="${x0 + (x1 - x0) / 2}" y="${h - 6}" fill="#94a3b8" font-size="10" text-anchor="middle">Minute →</text>
    <text x="14" y="${y0 + (y1 - y0) / 2}" fill="#94a3b8" font-size="10" text-anchor="middle" transform="rotate(-90 14 ${y0 + (y1 - y0) / 2})">xG ↑</text>
  </svg>`;
}

// ==========================================================
// PLAYER INTELLIGENCE & SCOUTING REPORT
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
    const seasonLabel = d.seasons && d.seasons.length > 1 ? ` · ${d.seasons.join("–")}` : ` · ${seasonOf("playerSeasons")}`;
    $("playerResolved").textContent = `${d.player.name}${d.player.age != null ? ` (${d.player.age}y)` : ""} · ${d.player.team_title || "—"} · ${d.player.position || "—"}${seasonLabel}`;
    renderPlayer(node, d);
  } catch (e) { errored(node, e.message); }
}

function renderPlayer(node, d) {
  clear(node);
  const p = d.player;
  const raw = d.per90_breakdown.raw;
  const p90 = d.per90_breakdown.per90;
  const radar = d.radar.profile.filter((item) => item.percentile > 0 || item.raw > 0);
  const shots = d.shots || [];
  const avgPct = radar.length ? Math.round(radar.reduce((acc, r) => acc + r.percentile, 0) / radar.length) : 50;

  node.innerHTML = `
    <!-- Player Hero Header -->
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
              ${windowBadge(d)}
            </div>
          </div>
        </div>
        <div>
          <span class="hero-pill green" style="font-size:12.5px;padding:6px 14px">
            ⭐ ${avgPct}th Percentile vs Position Peers
          </span>
        </div>
      </div>

      <!-- Headline KPI Grid -->
      <div class="kpi-row">
        <div class="kpi-card">
          <span class="kpi-label">${term("goals")}</span>
          <span class="kpi-value">${fmt(raw.goals, 0)}</span>
          <span class="kpi-sub">${fmt(p90.goals, 2)} /90</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">${term("npxg")}</span>
          <span class="kpi-value">${fmt(raw.npxG)}</span>
          <span class="kpi-sub">${fmt(p90.npxG, 2)} /90</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">${term("assists")} / ${term("xa")}</span>
          <span class="kpi-value">${fmt(raw.assists, 0)} <span style="font-size:14px;color:var(--muted)">(${fmt(raw.xA)})</span></span>
          <span class="kpi-sub">${fmt(p90.xA, 2)} xA /90</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">${term("conversion")}</span>
          <span class="kpi-value">${fmt(d.shot_selection.conversion || (raw.goals / Math.max(raw.shots, 1) * 100), 1)}%</span>
          <span class="kpi-sub">${fmt(raw.shots, 0)} total shots</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">${term("xG_chain")}</span>
          <span class="kpi-value">${fmt(p90.xGChain, 2)}</span>
          <span class="kpi-sub">Possession involvement</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">${term("xG_buildup")}</span>
          <span class="kpi-value">${fmt(p90.xGBuildup, 2)}</span>
          <span class="kpi-sub">Deep buildup play</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">${term("g_minus_xg")}</span>
          <span class="kpi-value ${d.finishing_overperformance.g_minus_xg >= 0 ? 'positive' : 'negative'}">
            ${d.finishing_overperformance.g_minus_xg >= 0 ? '+' : ''}${fmt(d.finishing_overperformance.g_minus_xg)}
          </span>
          <span class="kpi-sub">${fmt(d.per90_breakdown.minutes, 0)} mins</span>
        </div>
      </div>
    </div>

    <!-- Row 1: Tactical Pitch & Density Heatmap + Radar Pizza Chart -->
    <div class="grid cols-2">
      <div class="card">
        <div class="card-header">
          <span class="card-title">
            <svg class="card-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="m4.93 4.93 4.24 4.24M14.83 14.83l4.24 4.24"/></svg>
            Tactical Pitch Shot Map & Density Heatmap
          </span>
          <span style="font-size:11px;color:var(--muted);font-family:var(--mono)">${shots.length} shots recorded</span>
        </div>
        <div id="playerPitch"></div>
      </div>

      <div class="card">
        <div class="card-header">
          <span class="card-title">
            <svg class="card-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
            Percentile Radar Profile (vs ${d.radar.position_group} peers)
          </span>
          <span style="font-size:11px;color:var(--muted);font-family:var(--mono)">${d.radar.peer_count} peer players</span>
        </div>
        <div id="playerRadar"></div>
      </div>
    </div>

    <!-- Row 2: Finishing Diagnostics + Playmaking & Involvement -->
    <div class="grid cols-2" style="margin-top:20px">
      <div class="card">
        <div class="card-header">
          <span class="card-title">Finishing & Shot Quality Diagnostics</span>
        </div>
        ${finishing(d.finishing_overperformance)}
        <div style="margin-top:16px">${shotSelection(d.shot_selection)}</div>
      </div>

      <div class="card">
        <div class="card-header">
          <span class="card-title">Playmaking & Possession Involvement</span>
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
        <span class="card-title">Similar Player Profiles (Euclidean Peer Clustered)</span>
        <span style="font-size:11px;color:var(--muted)">Pool: ${d.similar_players.pool_after_filters} players</span>
      </div>
      ${similarCards(d.similar_players)}
    </div>

    <!-- Row 4: Percentile Rankings Table -->
    <div class="card" style="margin-top:20px">
      <div class="card-header">
        <span class="card-title">Tactical Metrics & League Percentile Rankings</span>
      </div>
      ${percentileTable(radar, d.per90_breakdown)}
    </div>

    ${d.pressing_output ? `
      <div class="card" style="margin-top:20px">
        <div class="card-header"><span class="card-title">Possession Regain & High-Press Output</span></div>
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
          <button class="ghost" style="padding:4px 8px;font-size:11px;margin-top:4px" onclick="$('playerName').value='${m.player_name}';runPlayer()">
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
              <td class="num" style="font-weight:700;color:${p.percentile >= 80 ? 'var(--accent-emerald)' : 'var(--text)'}">
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
      <div class="card-header"><span class="card-title">Career Trajectory · ${d.player_name}</span></div>
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
  const path = vals.map((v, i) => `${i ? "L" : "M"}${x(i)},${y(v)}`).join(" ");
  const dots = vals.map((v, i) => hoverDot(x(i), y(v), `${rows[i].season}: ${fmt(v, 3)}\n${rows[i].team || ""}\n${fmt(rows[i].minutes, 0)} min`, "#38bdf8")).join("");
  const labels = rows.map((r, i) => `<text x="${x(i)}" y="${y1 + 16}" fill="#94a3b8" font-size="10" text-anchor="middle">${r.season}</text>`).join("");
  const entry = GLOSSARY[metricKey] || {};
  el.innerHTML = `<svg class="timeline-svg" viewBox="0 0 ${w} ${h}">
    <line x1="${x0}" y1="${y1}" x2="${x1}" y2="${y1}" stroke="#1e293b"/>
    <line x1="${x0}" y1="${y1}" x2="${x0}" y2="${y0}" stroke="#1e293b"/>
    <path d="${path}" fill="none" stroke="#38bdf8" stroke-width="2.5"/>${dots}
    ${labels}
    <text x="${x0}" y="${y0}" fill="#94a3b8" font-size="11">${entry.label || metricKey} by Season</text>
  </svg>`;
}

// ==========================================================
// TEAM TACTICAL INTELLIGENCE
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
    renderTeam(node, d);
  } catch (e) { errored(node, e.message); }
}

function renderTeam(node, d) {
  const s = d.style;
  clear(node);

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
              ${windowBadge(d)}
            </div>
          </div>
        </div>
      </div>

      <!-- Headline KPI Cards -->
      <div class="kpi-row">
        <div class="kpi-card">
          <span class="kpi-label">${term("xG")} / Game</span>
          <span class="kpi-value">${fmt(s.xG_per_game)}</span>
          <span class="kpi-sub">Attacking chance quality</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">${term("xGA")} / Game</span>
          <span class="kpi-value">${fmt(s.xGA_per_game)}</span>
          <span class="kpi-sub">Defensive concession</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">xG Difference</span>
          <span class="kpi-value ${s.xG_diff_per_game >= 0 ? 'positive' : 'negative'}">
            ${s.xG_diff_per_game >= 0 ? '+' : ''}${fmt(s.xG_diff_per_game)}
          </span>
          <span class="kpi-sub">${term("npxgd")}: ${fmt(s.npxGD)}</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">${term("ppda")} Pressing</span>
          <span class="kpi-value">${fmt(s.PPDA)}</span>
          <span class="kpi-sub">Opponent PPDA: ${fmt(s.OPPDA)}</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">${term("deep")} Passes</span>
          <span class="kpi-value">${fmt(s.deep_completions, 0)}</span>
          <span class="kpi-sub">Allowed: ${fmt(s.deep_completions_allowed, 0)}</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">${term("xpts")} Total</span>
          <span class="kpi-value">${fmt(s.xPTS, 1)}</span>
          <span class="kpi-sub">Expected points</span>
        </div>
      </div>
    </div>

    <!-- Row 1: Attacking vs Defensive Shot Maps / Heatmaps -->
    <div class="grid cols-2">
      <div class="card">
        <div class="card-header">
          <span class="card-title">Attacking Shots Created</span>
          <span id="teamForShotCount" style="font-size:11px;color:var(--muted)">Loading shots…</span>
        </div>
        <div id="teamForPitch"></div>
      </div>
      <div class="card">
        <div class="card-header">
          <span class="card-title">Defensive Shots Conceded</span>
          <span id="teamAgainstShotCount" style="font-size:11px;color:var(--muted)">Loading shots…</span>
        </div>
        <div id="teamAgainstPitch"></div>
      </div>
    </div>

    <!-- Row 2: Matchday Progression Trajectory -->
    ${seasonComparisonSection(d)}

    <!-- Row 3: 5-Match Rolling Trend Charts -->
    <div class="card" style="margin-top:20px">
      <div class="card-header"><span class="card-title">5-Match Rolling Tactical Trends</span></div>
      <div class="controls-row">
        <div class="field"><label>Metric</label>
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

    <!-- Row 4: Splits & Luck Curve -->
    <div class="grid cols-2" style="margin-top:20px">
      <div class="card">
        <div class="card-header"><span class="card-title">First vs Second Half Splits</span></div>
        ${halfSplitTable(d.half_split)}
      </div>
      <div class="card">
        <div class="card-header"><span class="card-title">Cumulative Finishing Luck Curve</span></div>
        <div id="luckChart"></div>
        <div class="hint">${d.luck_curve.interpretation}</div>
      </div>
    </div>

    <!-- Row 5: Squad Roster & Creation Contributions -->
    ${d.squad && d.squad.length ? `
      <div class="card" style="margin-top:20px">
        <div class="card-header">
          <div>
            <span class="card-title">Squad Performance & Creation Contributions</span>
            <div style="font-size:11.5px;color:var(--muted);margin-top:2px">
              Individual player underlying threat, creation, and progression metrics · Click any player to open full deep-dive profile
            </div>
          </div>
          <span class="mono" style="font-size:11.5px;color:var(--muted)">${d.squad.length} Players</span>
        </div>
        <div class="table-responsive">
          <table class="dense-table" id="teamSquadTable">
            <thead>
              <tr>
                <th>Player</th>
                <th>Pos</th>
                <th class="num">Games</th>
                <th class="num">Min</th>
                <th class="num">G</th>
                <th class="num">${term("xG")}</th>
                <th class="num">${term("g_minus_xg", "G−xG")}</th>
                <th class="num">${term("npxG")}</th>
                <th class="num">A</th>
                <th class="num">${term("xA")}</th>
                <th class="num">${term("xG_chain", "xGChain")}</th>
                <th class="num">${term("xG_buildup", "xGBuildup")}</th>
                <th class="num">${term("npxG", "NPxG/90")}</th>
                <th class="num">${term("xA", "xA/90")}</th>
                <th class="num">${term("xG_chain", "Chain/90")}</th>
              </tr>
            </thead>
            <tbody>
              ${[...d.squad].sort((a, b) => (b.xG || 0) - (a.xG || 0)).map(p => {
                const min = p.minutes || 0;
                const npxg90 = min > 0 ? ((p.npxG || 0) / min) * 90 : 0;
                const xa90 = min > 0 ? ((p.xA || 0) / min) * 90 : 0;
                const chain90 = min > 0 ? ((p.xGChain || 0) / min) * 90 : 0;
                const gDiff = (p.goals || 0) - (p.xG || 0);

                return `
                  <tr>
                    <td>
                      <strong style="cursor:pointer;color:var(--text-bright)" onclick="$('playerName').value='${p.player_name}';activateTab('player');runPlayer()" title="Open ${p.player_name} Analytics">
                        ${p.player_name}
                      </strong>
                    </td>
                    <td><span class="badge">${p.position || '—'}</span></td>
                    <td class="num">${p.games || 0}</td>
                    <td class="num">${p.minutes || 0}</td>
                    <td class="num"><strong>${p.goals || 0}</strong></td>
                    <td class="num" style="color:var(--accent);font-weight:600">${fmt(p.xG, 2)}</td>
                    <td class="num" style="color:${gDiff >= 0 ? 'var(--fg-good)' : 'var(--fg-bad)'}">${gDiff >= 0 ? '+' : ''}${fmt(gDiff, 2)}</td>
                    <td class="num">${fmt(p.npxG, 2)}</td>
                    <td class="num"><strong>${p.assists || 0}</strong></td>
                    <td class="num">${fmt(p.xA, 2)}</td>
                    <td class="num" style="color:var(--accent);font-weight:600">${fmt(p.xGChain, 2)}</td>
                    <td class="num">${fmt(p.xGBuildup, 2)}</td>
                    <td class="num" style="font-weight:700">${fmt(npxg90, 2)}</td>
                    <td class="num">${fmt(xa90, 2)}</td>
                    <td class="num">${fmt(chain90, 2)}</td>
                  </tr>
                `;
              }).join("")}
            </tbody>
          </table>
        </div>
      </div>
    ` : ""}

    <div class="caveat" style="margin-top:20px"><strong>Limitations.</strong><ul>${d.limitations.map((l) => `<li>${l}</li>`).join("")}</ul></div>
  `;

  (async () => {
    try {
      const shotsData = await api("/api/v1/analyze/team/shots", {
        team_name: s.team, league_name: state.league, season: seasonOf("teamSeasons"),
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
  })();

  drawSeasonComparisonCharts(d);
  drawLuckChart("luckChart", d.luck_curve);
  const drawTrend = () => drawTrendChart("trendChart", d.metric_trends, $("trendMetric").value);
  $("trendMetric").addEventListener("change", drawTrend);
  drawTrend();
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

function drawSeasonComparisonCharts(d) {
  if (!d.season_trends) return;
  drawSeasonLines("seasonPoints", d.season_trends, "points", { invert: false });
  drawSeasonLines("seasonRank", d.season_trends, "rank", { invert: true, ymax: Math.max(...Object.values(d.season_trends).map((t) => t.n_teams), 2) });
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

function drawSeasonLines(container, trends, metric, opts) {
  const el = document.getElementById(container);
  if (!el) return;
  const entries = Object.entries(trends);
  const w = 1100, h = 240, padL = 52, pad = 30, x0 = padL, x1 = w - pad, y0 = 16, y1 = h - 42;
  const maxMatchdays = Math.max(...entries.map(([, t]) => t.matchdays.length), 1);
  const x = (i) => x0 + (i * (x1 - x0)) / Math.max(maxMatchdays - 1, 1);
  let lines = "", dots = "";

  for (const [s, t] of entries) {
    const color = "#38bdf8";
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
    <line x1="${x0}" y1="${y1}" x2="${x1}" y2="${y1}" stroke="#1e293b"/>
    <line x1="${x0}" y1="${y1}" x2="${x0}" y2="${y0}" stroke="#1e293b"/>
    ${lines}${dots}
    <text x="${x0}" y="${y0}" fill="#94a3b8" font-size="10">${axisLabel}</text>
    <text x="${x0 + (x1 - x0) / 2}" y="${h - 6}" fill="#94a3b8" font-size="10" text-anchor="middle">Matchday →</text>
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
  const dots = lc.points.map((p, i) => hoverDot(x(i), y(p.cumulative_g_minus_xg), `${p.date}\nCumulative G − xG: ${fmt(p.cumulative_g_minus_xg, 2)}`, lc.final >= 0 ? "#10b981" : "#f43f5e", 3.5)).join("");
  const zero = y(0);

  el.innerHTML = `<svg class="timeline-svg" viewBox="0 0 ${w} ${h}">
    <line x1="${x0}" y1="${y1}" x2="${x1}" y2="${y1}" stroke="#1e293b"/>
    <line x1="${x0}" y1="${y1}" x2="${x0}" y2="${y0}" stroke="#1e293b"/>
    <line x1="${x0}" y1="${zero}" x2="${x1}" y2="${zero}" stroke="#1e293b" stroke-dasharray="3 4"/>
    <path d="${path}" fill="none" stroke="${lc.final >= 0 ? '#10b981' : '#f43f5e'}" stroke-width="2.5"/>${dots}
    <text x="${x0}" y="${y0}" fill="#94a3b8" font-size="9.5">Cumulative Goals − xG Overperformance</text>
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
  const dots = vals.map((v, i) => hoverDot(x(i), y(v), `${mt.dates[i]}\n${key}: ${fmt(v, 2)}`, "#38bdf8", 3.5)).join("");
  const zero = y(0);
  const entry = GLOSSARY[key] || {};

  el.innerHTML = `<svg class="timeline-svg" viewBox="0 0 ${w} ${h}">
    <line x1="${x0}" y1="${y1}" x2="${x1}" y2="${y1}" stroke="#1e293b"/>
    <line x1="${x0}" y1="${y1}" x2="${x0}" y2="${y0}" stroke="#1e293b"/>
    <line x1="${x0}" y1="${zero}" x2="${x1}" y2="${zero}" stroke="#1e293b" stroke-dasharray="3 4"/>
    <path d="${path}" fill="none" stroke="#38bdf8" stroke-width="2.5"/>${dots}
    <text x="${x0}" y="${y0}" fill="#94a3b8" font-size="10.5">Rolling 5-Match ${entry.label || key}</text>
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
    rings += `<polygon points="${pts}" fill="none" stroke="#1e293b" stroke-width="1"/>`;
  }
  let spokes = "", labels = "";
  for (let i = 0; i < n; i++) {
    const [x, y] = pt(i, r);
    spokes += `<line x1="${cx}" y1="${cy}" x2="${x}" y2="${y}" stroke="#1e293b" stroke-width="1"/>`;
    const [lx, ly] = pt(i, r + 18);
    labels += `<text x="${lx}" y="${ly}" fill="#94a3b8" font-size="10.5" font-weight="600" text-anchor="middle" dominant-baseline="middle">${profile[i].label}</text>`;
  }
  let poly = ""; const vals = [];
  for (let i = 0; i < n; i++) {
    const pct = profile[i].percentile;
    const rr = r * pct / 100;
    const [x, y] = pt(i, rr);
    poly += `${x},${y} `;
    vals.push(`<circle cx="${x}" cy="${y}" r="3.5" fill="#38bdf8"/>`);
  }
  el.innerHTML = `<svg class="radar-svg" viewBox="0 0 ${size} ${size}">
    ${rings}${spokes}
    <polygon points="${poly}" fill="rgba(56,189,248,0.2)" stroke="#38bdf8" stroke-width="2.5"/>
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

    // If active season has 0 matches played for this league, automatically fall back to previous season
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

let leagueDataCache = null;
let leagueTableState = { sortKey: "rank", sortDir: "asc", viewMode: "all" };

function renderLeague(node, d, notice = "") {
  clear(node);
  leagueDataCache = d;
  const rawRows = d.table || (d.is_lying && d.is_lying.table_order_rows) || (d.is_lying && d.is_lying.rows) || [];
  const curSeason = seasonOf("leagueSeason");

  if (!rawRows.length) {
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

  // Calculate high-water marks for KPI cards
  const sortedByPts = [...rawRows].sort((a, b) => b.points - a.points);
  const sortedByXPts = [...rawRows].sort((a, b) => (b.xPTS || 0) - (a.xPTS || 0));
  const sortedByNPxGD = [...rawRows].sort((a, b) => (b.npxGD || 0) - (a.npxGD || 0));
  const sortedByPPDA = [...rawRows].filter(r => (r.PPDA || 0) > 0).sort((a, b) => a.PPDA - b.PPDA);
  const sortedByDC = [...rawRows].sort((a, b) => (b.deep_completions || 0) - (a.deep_completions || 0));
  const overperformer = d.is_lying && d.is_lying.biggest_overperformer;
  const underperformer = d.is_lying && d.is_lying.biggest_underperformer;

  const leader = sortedByPts[0] || {};
  const xptsLeader = sortedByXPts[0] || {};
  const npxgdLeader = sortedByNPxGD[0] || {};
  const pressLeader = sortedByPPDA[0] || {};
  const dcLeader = sortedByDC[0] || {};

  node.innerHTML = `
    ${notice ? `<div style="margin-bottom:16px"><span class="hero-pill accent">${notice}</span></div>` : ""}

    <!-- League KPI Overview Strip -->
    <div class="kpi-row" style="margin-bottom:20px">
      <div class="kpi-card" style="cursor:pointer" onclick="$('teamName').value='${leader.team || ''}';activateTab('team');runTeam()">
        <span class="kpi-label">🏆 Table Leader</span>
        <span class="kpi-value" style="font-size:18px">${leader.team || '—'}</span>
        <span class="kpi-sub">${leader.points || 0} pts · ${leader.matches || 0} matches</span>
      </div>
      <div class="kpi-card" style="cursor:pointer" onclick="$('teamName').value='${xptsLeader.team || ''}';activateTab('team');runTeam()">
        <span class="kpi-label">⚡ ${term("xpts", "xPTS")} Leader</span>
        <span class="kpi-value" style="font-size:18px">${xptsLeader.team || '—'}</span>
        <span class="kpi-sub">${fmt(xptsLeader.xPTS, 1)} expected pts</span>
      </div>
      <div class="kpi-card" style="cursor:pointer" onclick="$('teamName').value='${npxgdLeader.team || ''}';activateTab('team');runTeam()">
        <span class="kpi-label">🛡️ Best ${term("npxgd", "NPxGD")} Process</span>
        <span class="kpi-value" style="font-size:18px">${npxgdLeader.team || '—'}</span>
        <span class="kpi-sub">${fmt(npxgdLeader.npxGD, 1)} open-play diff</span>
      </div>
      <div class="kpi-card" style="cursor:pointer" onclick="$('teamName').value='${pressLeader.team || ''}';activateTab('team');runTeam()">
        <span class="kpi-label">🔥 Most Intense ${term("ppda", "PPDA")}</span>
        <span class="kpi-value" style="font-size:18px">${pressLeader.team || '—'}</span>
        <span class="kpi-sub">${fmt(pressLeader.PPDA, 1)} passes allowed / action</span>
      </div>
      <div class="kpi-card" style="cursor:pointer" onclick="$('teamName').value='${dcLeader.team || ''}';activateTab('team');runTeam()">
        <span class="kpi-label">🎯 Box Penetration (${term("dc", "DC")})</span>
        <span class="kpi-value" style="font-size:18px">${dcLeader.team || '—'}</span>
        <span class="kpi-sub">${dcLeader.deep_completions || 0} deep box passes</span>
      </div>
      ${overperformer ? `
      <div class="kpi-card" style="cursor:pointer" onclick="$('teamName').value='${overperformer.team || ''}';activateTab('team');runTeam()">
        <span class="kpi-label">🎲 Luck / Flattery Gap</span>
        <span class="kpi-value" style="font-size:18px;color:${overperformer.xPTS_gap > 0 ? 'var(--fg-good)' : 'var(--fg-bad)'}">
          ${overperformer.team} (+${fmt(overperformer.xPTS_gap, 1)})
        </span>
        <span class="kpi-sub">PTS outrunning xG process</span>
      </div>
      ` : ""}
    </div>

    <!-- Complete 19-Metric Team League Table -->
    <div class="card">
      <div class="card-header" style="flex-wrap:wrap;gap:12px;align-items:center">
        <div>
          <span class="card-title">Comprehensive League Intelligence & Process Table</span>
          <div style="font-size:11.5px;color:var(--muted);margin-top:2px">
            All 19 official Understat match & process metrics · Click any column header to sort · Hover headers for metric definitions
          </div>
        </div>
        <span class="mono" style="font-size:11.5px;color:var(--muted)">${LEAGUE_LABEL[state.league] || state.league} · ${curSeason}</span>
      </div>

      <!-- View Preset Switchers -->
      <div class="view-pills-row">
        <span style="font-size:11.5px;color:var(--muted);font-weight:700;margin-right:4px">Table View:</span>
        <button class="view-pill-btn ${leagueTableState.viewMode === 'all' ? 'active' : ''}" onclick="setLeagueViewMode('all')">Full 19-Metric Board</button>
        <button class="view-pill-btn ${leagueTableState.viewMode === 'standard' ? 'active' : ''}" onclick="setLeagueViewMode('standard')">Standings & Results (M, W, D, L, G, GA, PTS)</button>
        <button class="view-pill-btn ${leagueTableState.viewMode === 'expected' ? 'active' : ''}" onclick="setLeagueViewMode('expected')">Expected Goals Process (xG, NPxG, xGA, NPxGA, NPxGD, xPTS)</button>
        <button class="view-pill-btn ${leagueTableState.viewMode === 'pressing' ? 'active' : ''}" onclick="setLeagueViewMode('pressing')">Pressing & Penetration (PPDA, OPPDA, DC, ODC)</button>
      </div>

      <div class="table-responsive" id="leagueTableContainer">
        ${renderLeagueTableHTML(rawRows, leagueTableState.viewMode, leagueTableState.sortKey, leagueTableState.sortDir)}
      </div>

      <!-- Metric Glossary & Quick Cheat-Sheet -->
      <div class="metric-legend-card">
        <div class="metric-legend-item">
          <strong>№ / M / W / D / L:</strong> <span>Rank, Matches Played, Wins (3pts), Draws (1pt), Losses (0pts).</span>
        </div>
        <div class="metric-legend-item">
          <strong>G / GA / GD / PTS:</strong> <span>Goals Scored, Goals Against, Goal Diff, Actual Championship Points.</span>
        </div>
        <div class="metric-legend-item">
          <strong>xG / NPxG:</strong> <span>Expected Goals from all shots; NPxG excludes penalties (0.76 xG each) for open-play truth.</span>
        </div>
        <div class="metric-legend-item">
          <strong>xGA / NPxGA:</strong> <span>Expected Goals Against conceded; NPxGA measures non-penalty defensive quality.</span>
        </div>
        <div class="metric-legend-item">
          <strong>NPxGD:</strong> <span>Non-Penalty Expected Goal Diff (NPxG − NPxGA) — single best underlying strength metric.</span>
        </div>
        <div class="metric-legend-item">
          <strong>PPDA / OPPDA:</strong> <span>Passes Allowed per Defensive Action in attacking 60%. Lower = intense press; OPPDA = press resistance.</span>
        </div>
        <div class="metric-legend-item">
          <strong>DC / ODC:</strong> <span>Deep Completions (non-cross passes within 20yd of goal) and ODC (deep completions conceded).</span>
        </div>
        <div class="metric-legend-item">
          <strong>xPTS / Gap:</strong> <span>Expected Points simulated from chance distributions; Gap = PTS − xPTS (table flattery vs harshness).</span>
        </div>
      </div>

      <div class="hint" style="margin-top:12px">${d.is_lying.interpretation}</div>
    </div>

    <!-- Row 2: Finishing & Defensive Variance Breakdown -->
    ${d.variance ? `
      <div class="grid cols-2" style="margin-top:20px">
        <div class="card">
          <div class="card-header"><span class="card-title">Finishing Variance & Luck Analysis</span></div>
          <div class="kpi-row" style="margin-bottom:12px">
            <div class="kpi-card">
              <span class="kpi-label">Mean ${term("g_minus_xg", "G − xG")}</span>
              <span class="kpi-value">${fmt(d.variance.finishing_variance.mean_g_minus_xg)}</span>
              <span class="kpi-sub">League finishing baseline</span>
            </div>
            <div class="kpi-card">
              <span class="kpi-label">Finishing Spread (StDev)</span>
              <span class="kpi-value">${fmt(d.variance.finishing_variance.stdev_g_minus_xg)}</span>
              <span class="kpi-sub">Dispersion of finishing luck</span>
            </div>
          </div>
          <div class="hint">${d.variance.interpretation}</div>
        </div>

        <div class="card">
          <div class="card-header"><span class="card-title">League Process Pace</span></div>
          <div class="kpi-row" style="margin-bottom:12px">
            <div class="kpi-card">
              <span class="kpi-label">Average xG / Game</span>
              <span class="kpi-value">${fmt(d.pace ? d.pace.xG_per_game : 0)}</span>
              <span class="kpi-sub">Total chance volume pace</span>
            </div>
            <div class="kpi-card">
              <span class="kpi-label">Matches Completed</span>
              <span class="kpi-value">${d.pace ? d.pace.matches : 0}</span>
              <span class="kpi-sub">Sample size</span>
            </div>
          </div>
          <div class="hint">${d.pace ? d.pace.interpretation : ''}</div>
        </div>
      </div>
    ` : ""}

    <!-- Limitations -->
    <div class="caveat" style="margin-top:20px"><strong>Limitations & Analytical Honesty.</strong><ul>${d.limitations.map((l) => `<li>${l}</li>`).join("")}</ul></div>
  `;
}

function setLeagueViewMode(mode) {
  leagueTableState.viewMode = mode;
  const rawRows = (leagueDataCache && leagueDataCache.table) ||
                  (leagueDataCache && leagueDataCache.is_lying && leagueDataCache.is_lying.table_order_rows) ||
                  (leagueDataCache && leagueDataCache.is_lying && leagueDataCache.is_lying.rows) || [];
  const container = $("leagueTableContainer");
  if (container) {
    container.innerHTML = renderLeagueTableHTML(rawRows, leagueTableState.viewMode, leagueTableState.sortKey, leagueTableState.sortDir);
  }
  document.querySelectorAll(".view-pill-btn").forEach(btn => {
    btn.classList.toggle("active", btn.getAttribute("onclick").includes(`'${mode}'`));
  });
}

function sortLeagueTable(key) {
  if (leagueTableState.sortKey === key) {
    leagueTableState.sortDir = leagueTableState.sortDir === "asc" ? "desc" : "asc";
  } else {
    leagueTableState.sortKey = key;
    // Default descending for points/goals/metrics, ascending for rank/PPDA
    leagueTableState.sortDir = (key === "rank" || key === "PPDA" || key === "OPPDA" || key === "losses" || key === "goals_against" || key === "xGA" || key === "npxGA" || key === "deep_completions_allowed") ? "asc" : "desc";
  }
  const rawRows = (leagueDataCache && leagueDataCache.table) ||
                  (leagueDataCache && leagueDataCache.is_lying && leagueDataCache.is_lying.table_order_rows) ||
                  (leagueDataCache && leagueDataCache.is_lying && leagueDataCache.is_lying.rows) || [];
  const container = $("leagueTableContainer");
  if (container) {
    container.innerHTML = renderLeagueTableHTML(rawRows, leagueTableState.viewMode, leagueTableState.sortKey, leagueTableState.sortDir);
  }
}

function renderLeagueTableHTML(rows, viewMode, sortKey, sortDir) {
  const sorted = [...rows].sort((a, b) => {
    let valA = a[sortKey] !== undefined ? a[sortKey] : 0;
    let valB = b[sortKey] !== undefined ? b[sortKey] : 0;
    if (typeof valA === "string") valA = valA.toLowerCase();
    if (typeof valB === "string") valB = valB.toLowerCase();
    if (valA < valB) return sortDir === "asc" ? -1 : 1;
    if (valA > valB) return sortDir === "asc" ? 1 : -1;
    // Tiebreaker: Points desc, then GD desc, then Goals desc
    if (b.points !== a.points) return b.points - a.points;
    if ((b.gd || 0) !== (a.gd || 0)) return (b.gd || 0) - (a.gd || 0);
    return (b.goals || 0) - (a.goals || 0);
  });

  const dirArrow = sortDir === "asc" ? "▲" : "▼";
  const th = (key, label, dataTerm, isNum = true, isSticky = "") => {
    const active = sortKey === key;
    return `
      <th class="${isNum ? 'num' : ''} sortable ${active ? 'sort-active' : ''} ${isSticky}"
          onclick="sortLeagueTable('${key}')"
          title="Click to sort by ${label}">
        ${term(dataTerm, label)}
        ${active ? `<span style="font-size:10px;margin-left:2px">${dirArrow}</span>` : ''}
      </th>
    `;
  };

  return `
    <table class="dense-table">
      <thead>
        <tr>
          ${th("rank", "№", "rank", false, "table-sticky-rank")}
          ${th("team", "Team", "team", false, "table-sticky-team")}
          ${(viewMode === 'all' || viewMode === 'standard' || viewMode === 'expected' || viewMode === 'pressing') ? th("matches", "M", "matches") : ''}
          ${(viewMode === 'all' || viewMode === 'standard') ? th("wins", "W", "wins") : ''}
          ${(viewMode === 'all' || viewMode === 'standard') ? th("draws", "D", "draws") : ''}
          ${(viewMode === 'all' || viewMode === 'standard') ? th("losses", "L", "losses") : ''}
          ${(viewMode === 'all' || viewMode === 'standard') ? th("goals", "G", "goals") : ''}
          ${(viewMode === 'all' || viewMode === 'standard') ? th("goals_against", "GA", "ga") : ''}
          ${(viewMode === 'all' || viewMode === 'standard') ? th("gd", "GD", "gd") : ''}
          ${(viewMode === 'all' || viewMode === 'standard' || viewMode === 'expected') ? th("points", "PTS", "pts") : ''}
          ${(viewMode === 'all' || viewMode === 'expected' || viewMode === 'pressing') ? th("xG", "xG", "xG") : ''}
          ${(viewMode === 'all' || viewMode === 'expected') ? th("npxG", "NPxG", "npxG") : ''}
          ${(viewMode === 'all' || viewMode === 'expected' || viewMode === 'pressing') ? th("xGA", "xGA", "xGA") : ''}
          ${(viewMode === 'all' || viewMode === 'expected') ? th("npxGA", "NPxGA", "npxga") : ''}
          ${(viewMode === 'all' || viewMode === 'expected' || viewMode === 'pressing') ? th("npxGD", "NPxGD", "npxgd") : ''}
          ${(viewMode === 'all' || viewMode === 'pressing') ? th("PPDA", "PPDA", "ppda") : ''}
          ${(viewMode === 'all' || viewMode === 'pressing') ? th("OPPDA", "OPPDA", "oppda") : ''}
          ${(viewMode === 'all' || viewMode === 'pressing') ? th("deep_completions", "DC", "dc") : ''}
          ${(viewMode === 'all' || viewMode === 'pressing') ? th("deep_completions_allowed", "ODC", "odc") : ''}
          ${(viewMode === 'all' || viewMode === 'expected') ? th("xPTS", "xPTS", "xpts") : ''}
          ${(viewMode === 'all' || viewMode === 'expected') ? th("xPTS_gap", "Pts Gap", "xpts_gap") : ''}
          ${(viewMode === 'expected') ? th("g_minus_xg", "G − xG", "g_minus_xg") : ''}
          ${(viewMode === 'expected') ? th("xga_minus_ga", "xGA − GA", "xga_minus_ga") : ''}
        </tr>
      </thead>
      <tbody>
        ${sorted.map((r, i) => {
          const isTop4 = r.rank <= 4;
          const isRelegation = r.rank >= (sorted.length - 2);
          const gapCls = (r.xPTS_gap || 0) > 0 ? "good" : (r.xPTS_gap || 0) < 0 ? "bad" : "";
          const gd = r.gd !== undefined ? r.gd : (r.goals - r.goals_against);

          return `
            <tr>
              <td class="table-sticky-rank">
                <span class="rank-badge ${isTop4 ? 'top4' : isRelegation ? 'relegation' : ''}">${r.rank}</span>
              </td>
              <td class="table-sticky-team">
                <strong style="cursor:pointer;color:var(--text-bright)" onclick="$('teamName').value='${r.team}';activateTab('team');runTeam()" title="View ${r.team} Team Analytics">
                  ${r.team}
                </strong>
              </td>
              ${(viewMode === 'all' || viewMode === 'standard' || viewMode === 'expected' || viewMode === 'pressing') ? `<td class="num">${r.matches}</td>` : ''}
              ${(viewMode === 'all' || viewMode === 'standard') ? `<td class="num">${r.wins}</td>` : ''}
              ${(viewMode === 'all' || viewMode === 'standard') ? `<td class="num">${r.draws}</td>` : ''}
              ${(viewMode === 'all' || viewMode === 'standard') ? `<td class="num">${r.losses}</td>` : ''}
              ${(viewMode === 'all' || viewMode === 'standard') ? `<td class="num">${r.goals}</td>` : ''}
              ${(viewMode === 'all' || viewMode === 'standard') ? `<td class="num">${r.goals_against}</td>` : ''}
              ${(viewMode === 'all' || viewMode === 'standard') ? `<td class="num" style="color:${gd >= 0 ? 'var(--text)' : 'var(--fg-bad)'};font-weight:600">${gd > 0 ? '+' : ''}${gd}</td>` : ''}
              ${(viewMode === 'all' || viewMode === 'standard' || viewMode === 'expected') ? `<td class="num"><strong>${r.points}</strong></td>` : ''}
              ${(viewMode === 'all' || viewMode === 'expected' || viewMode === 'pressing') ? `<td class="num" style="color:var(--accent);font-weight:600">${fmt(r.xG, 2)}</td>` : ''}
              ${(viewMode === 'all' || viewMode === 'expected') ? `<td class="num">${fmt(r.npxG, 2)}</td>` : ''}
              ${(viewMode === 'all' || viewMode === 'expected' || viewMode === 'pressing') ? `<td class="num">${fmt(r.xGA, 2)}</td>` : ''}
              ${(viewMode === 'all' || viewMode === 'expected') ? `<td class="num">${fmt(r.npxGA, 2)}</td>` : ''}
              ${(viewMode === 'all' || viewMode === 'expected' || viewMode === 'pressing') ? `<td class="num" style="color:${(r.npxGD || 0) >= 0 ? 'var(--fg-good)' : 'var(--fg-bad)'};font-weight:700">${(r.npxGD || 0) >= 0 ? '+' : ''}${fmt(r.npxGD, 2)}</td>` : ''}
              ${(viewMode === 'all' || viewMode === 'pressing') ? `<td class="num"><strong>${fmt(r.PPDA, 2)}</strong></td>` : ''}
              ${(viewMode === 'all' || viewMode === 'pressing') ? `<td class="num">${fmt(r.OPPDA, 2)}</td>` : ''}
              ${(viewMode === 'all' || viewMode === 'pressing') ? `<td class="num">${r.deep_completions || 0}</td>` : ''}
              ${(viewMode === 'all' || viewMode === 'pressing') ? `<td class="num">${r.deep_completions_allowed || 0}</td>` : ''}
              ${(viewMode === 'all' || viewMode === 'expected') ? `<td class="num" style="color:var(--accent);font-weight:700">${fmt(r.xPTS, 2)}</td>` : ''}
              ${(viewMode === 'all' || viewMode === 'expected') ? `<td class="num"><span class="badge ${gapCls}">${(r.xPTS_gap || 0) >= 0 ? '+' : ''}${fmt(r.xPTS_gap, 2)}</span></td>` : ''}
              ${(viewMode === 'expected') ? `<td class="num" style="color:${(r.g_minus_xg || 0) >= 0 ? 'var(--fg-good)' : 'var(--fg-bad)'}">${(r.g_minus_xg || 0) >= 0 ? '+' : ''}${fmt(r.g_minus_xg, 2)}</td>` : ''}
              ${(viewMode === 'expected') ? `<td class="num">${fmt(r.xga_minus_ga, 2)}</td>` : ''}
            </tr>
          `;
        }).join("")}
      </tbody>
    </table>
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
      <div class="card-header"><span class="card-title">Ranked Discovery Pool (${d.players.length} players found)</span></div>
      <div class="table-responsive">
        <table class="dense-table">
          <thead>
            <tr>
              <th>Player</th>
              <th>Team</th>
              <th>Role</th>
              <th class="num">Age</th>
              <th class="num">Min</th>
              <th class="num">${term("goals")}</th>
              <th class="num">${term("xG")}</th>
              <th class="num">${term("npxg")}</th>
              <th class="num">${term("npxg", "NPxG/90")}</th>
              <th class="num">${term("assists")}</th>
              <th class="num">${term("xa")}</th>
              <th class="num">${term("xa", "xA/90")}</th>
              <th class="num">${term("xG_chain")}</th>
              <th class="num">${term("xG_chain", "Chain/90")}</th>
              <th class="num">${term("xG_buildup")}</th>
              <th class="num">${term("xG_buildup", "Buildup/90")}</th>
              <th>Scout</th>
            </tr>
          </thead>
          <tbody>
            ${d.players.map((p) => {
              const min = p.time || 0;
              const npxg90 = min > 0 ? ((p.npxG || 0) / min) * 90 : 0;
              const xa90 = min > 0 ? ((p.xA || 0) / min) * 90 : 0;
              const chain90 = min > 0 ? ((p.xGChain || 0) / min) * 90 : 0;
              const build90 = min > 0 ? ((p.xGBuildup || 0) / min) * 90 : 0;

              return `
                <tr>
                  <td><strong style="cursor:pointer;color:var(--text-bright)" onclick="$('playerName').value='${p.player_name}';activateTab('player');runPlayer()">${p.player_name}</strong></td>
                  <td>${p.team_title || "—"}</td>
                  <td><span class="badge">${p.position || "—"}</span></td>
                  <td class="num">${p.age ?? "—"}</td>
                  <td class="num">${fmt(p.time, 0)}</td>
                  <td class="num"><strong>${fmt(p.goals, 0)}</strong></td>
                  <td class="num" style="color:var(--accent);font-weight:600">${fmt(p.xG, 2)}</td>
                  <td class="num">${fmt(p.npxG, 2)}</td>
                  <td class="num" style="font-weight:700">${fmt(npxg90, 2)}</td>
                  <td class="num"><strong>${fmt(p.assists, 0)}</strong></td>
                  <td class="num">${fmt(p.xA, 2)}</td>
                  <td class="num" style="font-weight:700">${fmt(xa90, 2)}</td>
                  <td class="num" style="color:var(--accent);font-weight:600">${fmt(p.xGChain, 2)}</td>
                  <td class="num">${fmt(chain90, 2)}</td>
                  <td class="num">${fmt(p.xGBuildup, 2)}</td>
                  <td class="num">${fmt(build90, 2)}</td>
                  <td>
                    <button class="ghost" style="padding:3px 10px;font-size:11.5px" onclick="$('playerName').value='${p.player_name}';activateTab('player');runPlayer()">Profile →</button>
                  </td>
                </tr>
              `;
            }).join("")}
          </tbody>
        </table>
      </div>
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
        <div class="card-header"><span class="card-title">Head-to-Head Comprehensive Metrics</span></div>
        <div class="table-responsive">
          <table class="dense-table">
            <thead><tr><th>Metric</th><th class="num">${names[0]}</th><th class="num">${names[1]}</th></tr></thead>
            <tbody>
              <tr><td>${term("goals", "Goals")}</td><td class="num"><strong>${fmt(p1.raw.goals, 0)}</strong></td><td class="num"><strong>${fmt(p2.raw.goals, 0)}</strong></td></tr>
              <tr><td>${term("xG", "Expected Goals (xG)")}</td><td class="num" style="color:var(--accent);font-weight:600">${fmt(p1.raw.xG, 2)}</td><td class="num" style="color:var(--accent-emerald);font-weight:600">${fmt(p2.raw.xG, 2)}</td></tr>
              <tr><td>${term("npxG", "Non-Penalty xG (NPxG)")}</td><td class="num">${fmt(p1.raw.npxG, 2)}</td><td class="num">${fmt(p2.raw.npxG, 2)}</td></tr>
              <tr><td>${term("npxG", "NPxG / 90")}</td><td class="num" style="font-weight:700">${fmt(p1.per90.npxG, 2)}</td><td class="num" style="font-weight:700">${fmt(p2.per90.npxG, 2)}</td></tr>
              <tr><td>${term("assists", "Assists")}</td><td class="num"><strong>${fmt(p1.raw.assists, 0)}</strong></td><td class="num"><strong>${fmt(p2.raw.assists, 0)}</strong></td></tr>
              <tr><td>${term("xA", "Expected Assists (xA)")}</td><td class="num">${fmt(p1.raw.xA, 2)}</td><td class="num">${fmt(p2.raw.xA, 2)}</td></tr>
              <tr><td>${term("xA", "xA / 90")}</td><td class="num" style="font-weight:700">${fmt(p1.per90.xA, 2)}</td><td class="num" style="font-weight:700">${fmt(p2.per90.xA, 2)}</td></tr>
              <tr><td>${term("shots", "Shots")}</td><td class="num">${fmt(p1.raw.shots, 0)}</td><td class="num">${fmt(p2.raw.shots, 0)}</td></tr>
              <tr><td>${term("key_passes", "Key Passes")}</td><td class="num">${fmt(p1.raw.key_passes, 0)}</td><td class="num">${fmt(p2.raw.key_passes, 0)}</td></tr>
              <tr><td>${term("xG_chain", "xGChain / 90")}</td><td class="num" style="color:var(--accent);font-weight:600">${fmt(p1.per90.xGChain, 2)}</td><td class="num" style="color:var(--accent-emerald);font-weight:600">${fmt(p2.per90.xGChain, 2)}</td></tr>
              <tr><td>${term("xG_buildup", "xGBuildup / 90")}</td><td class="num">${fmt(p1.per90.xGBuildup, 2)}</td><td class="num">${fmt(p2.per90.xGBuildup, 2)}</td></tr>
              <tr><td>${term("minutes", "Minutes Played")}</td><td class="num">${fmt(p1.minutes, 0)}</td><td class="num">${fmt(p2.minutes, 0)}</td></tr>
            </tbody>
          </table>
        </div>
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
    rings += `<polygon points="${pts}" fill="none" stroke="#1e293b" stroke-width="1"/>`;
  }
  let poly1 = "", poly2 = "", labels = "";
  for (let i = 0; i < n; i++) {
    const [x1, y1] = pt(i, r * r1[i].percentile / 100);
    const [x2, y2] = pt(i, r * (r2[i] ? r2[i].percentile : 50) / 100);
    poly1 += `${x1},${y1} `;
    poly2 += `${x2},${y2} `;
    const [lx, ly] = pt(i, r + 18);
    labels += `<text x="${lx}" y="${ly}" fill="#94a3b8" font-size="10" text-anchor="middle">${r1[i].label}</text>`;
  }
  el.innerHTML = `<svg class="radar-svg" viewBox="0 0 ${size} ${size}">
    ${rings}
    <polygon points="${poly1}" fill="rgba(56,189,248,0.2)" stroke="#38bdf8" stroke-width="2"/>
    <polygon points="${poly2}" fill="rgba(16,185,129,0.2)" stroke="#10b981" stroke-width="2"/>
    ${labels}
    <text x="16" y="24" fill="#38bdf8" font-size="11">● ${name1}</text>
    <text x="16" y="42" fill="#10b981" font-size="11">● ${name2}</text>
  </svg>`;
}

function renderCompareTeams(node, d) {
  clear(node);
  const t1 = d.team_1, t2 = d.team_2;
  const s1 = t1.style || {}, s2 = t2.style || {};

  node.innerHTML = `
    <div class="card">
      <div class="card-header"><span class="card-title">${t1.team} vs ${t2.team} Tactical & Process Comparison</span></div>
      <div class="table-responsive">
        <table class="dense-table">
          <thead><tr><th>Metric</th><th class="num">${t1.team}</th><th class="num">${t2.team}</th></tr></thead>
          <tbody>
            <tr><td>${term("pts", "Points (PTS)")}</td><td class="num"><strong>${s1.points ?? '—'}</strong></td><td class="num"><strong>${s2.points ?? '—'}</strong></td></tr>
            <tr><td>${term("xpts", "Expected Points (xPTS)")}</td><td class="num" style="color:var(--accent);font-weight:700">${fmt(s1.xPTS, 1)}</td><td class="num" style="color:var(--accent-emerald);font-weight:700">${fmt(s2.xPTS, 1)}</td></tr>
            <tr><td>${term("xpts_gap", "PTS − xPTS Gap")}</td><td class="num">${(s1.xPTS_gap || 0) >= 0 ? '+' : ''}${fmt(s1.xPTS_gap, 1)}</td><td class="num">${(s2.xPTS_gap || 0) >= 0 ? '+' : ''}${fmt(s2.xPTS_gap, 1)}</td></tr>
            <tr><td>${term("goals", "Goals Scored (G)")}</td><td class="num">${s1.goals ?? '—'}</td><td class="num">${s2.goals ?? '—'}</td></tr>
            <tr><td>${term("xG", "Expected Goals (xG)")}</td><td class="num">${fmt(s1.xG, 2)}</td><td class="num">${fmt(s2.xG, 2)}</td></tr>
            <tr><td>${term("npxG", "Non-Penalty xG (NPxG)")}</td><td class="num">${fmt(s1.npxG, 2)}</td><td class="num">${fmt(s2.npxG, 2)}</td></tr>
            <tr><td>${term("xG", "xG / Game")}</td><td class="num" style="font-weight:600">${fmt(s1.xG_per_game, 2)}</td><td class="num" style="font-weight:600">${fmt(s2.xG_per_game, 2)}</td></tr>
            <tr><td>${term("ga", "Goals Against (GA)")}</td><td class="num">${s1.goals_against ?? '—'}</td><td class="num">${s2.goals_against ?? '—'}</td></tr>
            <tr><td>${term("xGA", "Expected Goals Against (xGA)")}</td><td class="num">${fmt(s1.xGA, 2)}</td><td class="num">${fmt(s2.xGA, 2)}</td></tr>
            <tr><td>${term("npxga", "Non-Penalty xGA (NPxGA)")}</td><td class="num">${fmt(s1.npxGA, 2)}</td><td class="num">${fmt(s2.npxGA, 2)}</td></tr>
            <tr><td>${term("xGA", "xGA / Game")}</td><td class="num" style="font-weight:600">${fmt(s1.xGA_per_game, 2)}</td><td class="num" style="font-weight:600">${fmt(s2.xGA_per_game, 2)}</td></tr>
            <tr><td>${term("npxgd", "Non-Penalty xGD (NPxGD)")}</td><td class="num" style="font-weight:700;color:${(s1.npxGD || 0) >= 0 ? 'var(--fg-good)' : 'var(--fg-bad)'}">${(s1.npxGD || 0) >= 0 ? '+' : ''}${fmt(s1.npxGD, 2)}</td><td class="num" style="font-weight:700;color:${(s2.npxGD || 0) >= 0 ? 'var(--fg-good)' : 'var(--fg-bad)'}">${(s2.npxGD || 0) >= 0 ? '+' : ''}${fmt(s2.npxGD, 2)}</td></tr>
            <tr><td>${term("ppda", "PPDA Pressing Intensity")}</td><td class="num"><strong>${fmt(s1.PPDA, 2)}</strong></td><td class="num"><strong>${fmt(s2.PPDA, 2)}</strong></td></tr>
            <tr><td>${term("oppda", "OPPDA Press Resistance")}</td><td class="num">${fmt(s1.OPPDA, 2)}</td><td class="num">${fmt(s2.OPPDA, 2)}</td></tr>
            <tr><td>${term("dc", "Deep Completions (DC)")}</td><td class="num">${s1.deep_completions ?? 0}</td><td class="num">${s2.deep_completions ?? 0}</td></tr>
            <tr><td>${term("odc", "Opponent Deep Completions (ODC)")}</td><td class="num">${s1.deep_completions_allowed ?? 0}</td><td class="num">${s2.deep_completions_allowed ?? 0}</td></tr>
          </tbody>
        </table>
      </div>
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
      <div class="card-header"><span class="card-title">Forecast Outcome Probabilities</span></div>
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
      <div class="card-header"><span class="card-title">Rest-of-Season Simulation (${d.simulations} runs)</span></div>
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
      <div class="card-header"><span class="card-title">Walk-Forward Model Calibration Benchmarks</span></div>
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

// Initial View Activation Trigger
const initialHashTab = (window.location.hash || "#player").slice(1);
if (initialHashTab && document.querySelector(`.sidebar-nav .nav-item[data-tab="${initialHashTab}"]`)) {
  activateTab(initialHashTab, false);
} else {
  activateTab("player", false);
}

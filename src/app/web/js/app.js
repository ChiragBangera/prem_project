// Application shell: rail navigation, top bar, routing, theme, command palette.
import { html, useEffect, useRef, useState } from "./lib/html.js";
import { Icon } from "./lib/icons.js";
import { ui, metaStore, pending, shortlistStore, useStore } from "./lib/store.js";
import { useApi } from "./lib/api.js";
import { compile, match, useLocation, href, navigate } from "./lib/router.js";
import { TooltipHost } from "./lib/tooltip.js";
import { relTime } from "./lib/format.js";
import { useMedia } from "./lib/media.js";
import { setLeague, setSeason, seasonOptions } from "./lib/scope.js";
import { ErrorBoundary, ErrorState, PageSkeleton, Select, Button } from "./ui/common.js";
import { Palette } from "./ui/palette.js";

import Briefing from "./pages/briefing.js";
import League from "./pages/league.js";
import Team from "./pages/team.js";
import Scout from "./pages/scout.js";
import Teams from "./pages/teams.js";
import Player from "./pages/player.js";
import Compare from "./pages/compare.js";
import Matches from "./pages/matches.js";
import MatchPage from "./pages/match.js";
import Shortlist from "./pages/shortlist.js";
import DataPage from "./pages/data.js";
import Dictionary from "./pages/dictionary.js";
import Guide from "./pages/guide.js";

/** A page that only forwards to another address: kept so old links and bookmarks keep working. */
const redirect = (to) => function Redirect() {
  useEffect(() => { navigate(to, undefined, { replace: true }); }, []);
  return null;
};

const routes = compile([
  { path: "/", page: Briefing, nav: "/" },
  { path: "/league", page: League, nav: "/league" },
  { path: "/team/:team", page: Team, nav: "/teams" },
  { path: "/scout", page: Scout, nav: "/scout" },
  { path: "/teams", page: Teams, nav: "/teams" },
  { path: "/player/:id", page: Player, nav: "/scout" },
  { path: "/compare", page: Compare, nav: "/compare" },
  { path: "/matches", page: Matches, nav: "/matches" },
  { path: "/match/:id", page: MatchPage, nav: "/matches" },
  { path: "/shortlist", page: Shortlist, nav: "/shortlist" },
  { path: "/data", page: DataPage, nav: "/data" },
  { path: "/dictionary", page: Dictionary, nav: "/dictionary" },
  { path: "/guide", page: Guide, nav: "/guide" },
  { path: "/method", page: redirect("/dictionary"), nav: "/dictionary" },
  { path: "/forecast", page: redirect("/"), nav: "/" },
]);

const NAV = [
  { label: "Read", items: [
    { path: "/", name: "Briefing", icon: "briefing" },
    { path: "/league", name: "League", icon: "table" },
    { path: "/matches", name: "Matches", icon: "calendar" },
  ] },
  { label: "Explore", items: [
    { path: "/scout", name: "Scout", icon: "scout" },
    { path: "/teams", name: "Teams", icon: "shield" },
    { path: "/compare", name: "Compare", icon: "compare", mobile: false },
    { path: "/shortlist", name: "Shortlist", icon: "star", count: true, mobile: false },
  ] },
  { label: "Reference", items: [
    { path: "/dictionary", name: "Dictionary", icon: "dictionary", mobile: false },
    { path: "/guide", name: "Guide", icon: "info", mobile: false },
  ] },
  { label: "System", items: [
    { path: "/data", name: "Data", icon: "database" },
  ] },
];

function BrandMark() {
  return html`<svg class="brand-mark" viewBox="0 0 32 32" aria-hidden="true">
    <path d="M6 26V12M12 26V6.5M18 26V16M24 26V13" stroke="var(--accent)" stroke-width="3.2" stroke-linecap="round" fill="none" />
    <circle cx="24" cy="6.5" r="2.6" fill="var(--c2)" />
  </svg>`;
}

function Rail({ current, meta }) {
  const count = useStore(shortlistStore, (s) => s.items.length);
  return html`<nav class="rail" aria-label="Main">
    <a class="brand" href=${href("/")} aria-label="Prem Lab, briefing">
      <${BrandMark} />
      <div><div class="brand-name">PREM LAB</div><div class="brand-sub">Personal analytics</div></div>
    </a>
    ${NAV.map((group, gi) => html`<div class="nav" key=${group.label}>
      ${gi ? html`<div class="nav-label">${group.label}</div>` : html`<div class="nav-label" style=${{ paddingTop: 0 }}>${group.label}</div>`}
      ${group.items.map((item) => html`<a key=${item.path} class=${"nav-item" + (item.mobile === false ? " hide-mobile" : "")} href=${href(item.path)} aria-current=${current === item.path ? "page" : undefined}>
        <${Icon} name=${item.icon} /><span>${item.name}</span>${item.count && count ? html`<span class="count">${count}</span>` : null}
      </a>`)}
    </div>`)}
    <div class="rail-foot">
      ${meta ? html`<div>v${meta.app.version} · ${meta.mode.demo ? "demo data" : meta.mode.offline ? "offline cache" : "Understat"}</div>` : null}
      <div>Press <kbd>/</kbd> to search anywhere</div>
    </div>
  </nav>`;
}

function DataPill({ meta }) {
  if (!meta) return null;
  if (meta.mode.demo) return html`<a class="pill warn" href=${href("/data")} title="Everything shown is synthetic demo data"><i></i><span class="pill-text">Demo data</span></a>`;
  const newest = Math.max(0, ...(meta.cache?.leagues || []).map((l) => l.fetched_at || 0));
  const auto = meta.auto || {};
  const busy = (meta.jobs || []).some((j) => j.state === "running") || auto.running || Boolean(auto.events_running);
  const age = newest ? Date.now() / 1000 - newest : null;
  const problem = auto.enabled && auto.errors > 0;
  const label = busy ? (auto.events_running ? `Fetching ${auto.events_running}…` : "Updating…") : meta.mode.offline ? "Offline cache" : age == null ? "No data yet" : `Updated ${relTime(age)}`;
  const title = meta.mode.offline ? "Offline: serving what is stored" : auto.enabled ? `Updates itself in the background${problem ? " (the last cycle had problems: open Data)" : ""}` : "Automatic updates are off: open Data";
  return html`<a class=${"pill" + ((age == null && !busy) || problem ? " warn" : "")} href=${href("/data")} title=${title}><i class=${busy ? "live" : ""}></i><span class="pill-text">${label}</span></a>`;
}

function ThemeToggle() {
  const theme = useStore(ui, (s) => s.theme);
  const next = { system: "light", light: "dark", dark: "system" }[theme] || "light";
  const icon = { system: "monitor", light: "sun", dark: "moon" }[theme] || "monitor";
  return html`<${Button} kind="quiet" icon=${icon} title=${`Theme: ${theme}. Switch to ${next}.`} onClick=${() => ui.set({ theme: next })} />`;
}

function TopBar({ meta, onSearch }) {
  const scope = useStore(ui, (s) => ({ league: s.league, season: s.season }));
  const narrow = useMedia("(max-width: 720px)");
  const seasons = seasonOptions(meta).map((o) => (narrow && o.value === "auto" ? { ...o, label: "Latest" } : o));
  const leagues = (meta?.leagues || [{ code: "EPL", name: "Premier League", short: "EPL" }]).map((l) => ({ value: l.code, label: narrow ? l.short || l.code : l.name }));
  return html`<header class="topbar">
    <div class="scope-controls" role="group" aria-label="League and season">
      <${Select} label="League" value=${scope.league} options=${leagues} onChange=${setLeague} />
      <${Select} label="Season" value=${scope.season} options=${seasons} onChange=${setSeason} />
    </div>
    <div class="spacer"></div>
    <button type="button" class="search-trigger" onClick=${onSearch} aria-label="Search players, teams and pages"><${Icon} name="search" size="sm" /><span>Search players, teams…</span><kbd>⌘K</kbd></button>
    <${ThemeToggle} />
    <${DataPill} meta=${meta} />
  </header>`;
}

function ProgressLine() {
  const busy = useStore(pending, (s) => s.n > 0);
  const [show, setShow] = useState(false);
  useEffect(() => {
    if (!busy) { setShow(false); return undefined; }
    const t = setTimeout(() => setShow(true), 250);
    return () => clearTimeout(t);
  }, [busy]);
  return show ? html`<div class="progress-line" role="progressbar" aria-label="Loading"><i></i></div>` : null;
}

function applyTheme(theme) {
  const root = document.documentElement;
  if (theme === "light" || theme === "dark") root.dataset.theme = theme;
  else delete root.dataset.theme;
}

export function App() {
  const loc = useLocation();
  const theme = useStore(ui, (s) => s.theme);
  const metaQ = useApi("/api/meta", null, { pollMs: 60000, staleMs: 30000 });
  const catQ = useApi("/api/catalog", null, { staleMs: 3600000 });
  const shortlistQ = useApi("/api/shortlist", null, { staleMs: 5000 });
  const meta = metaQ.data;
  const [paletteOpen, setPaletteOpen] = useState(false);
  const mainRef = useRef(null);

  useEffect(() => applyTheme(theme), [theme]);
  useEffect(() => { if (metaQ.data || catQ.data) metaStore.set({ meta: metaQ.data, catalog: catQ.data, error: null }); }, [metaQ.data, catQ.data]);
  useEffect(() => { if (shortlistQ.data) shortlistStore.set({ items: shortlistQ.data.items || [], loaded: true }); }, [shortlistQ.data]);

  // keyboard: Cmd/Ctrl+K or "/" opens search
  useEffect(() => {
    const onKey = (e) => {
      const tag = (e.target?.tagName || "").toLowerCase();
      const typing = tag === "input" || tag === "textarea" || tag === "select" || e.target?.isContentEditable;
      if ((e.key === "k" && (e.metaKey || e.ctrlKey)) || (e.key === "/" && !typing && !e.metaKey && !e.ctrlKey)) {
        e.preventDefault();
        setPaletteOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // new page: scroll to top and hand focus to the main region for keyboard/screen-reader users
  useEffect(() => {
    window.scrollTo(0, 0);
    mainRef.current?.focus({ preventScroll: true });
  }, [loc.path]);

  const found = match(routes, loc.path);
  const Page = found?.route.page;
  const dataReady = catQ.data && metaQ.data;
  const bootError = (metaQ.error && !metaQ.data) || (catQ.error && !catQ.data);

  return html`<div class="app">
    <${Rail} current=${found?.route.nav} meta=${meta} />
    <div class="main">
      ${meta?.mode?.demo ? html`<div class="demo-strip"><b>Demo data</b><span>Every player, score and statistic here is synthetic, so you can explore safely. Real Understat data replaces it once this machine can reach the site.</span><a class="link" href=${href("/data")}>Data status</a></div>` : null}
      <${TopBar} meta=${meta} onSearch=${() => setPaletteOpen(true)} />
      <main id="main" class="page" tabindex="-1" ref=${mainRef}>
        ${bootError
          ? html`<${ErrorState} error=${metaQ.error || catQ.error} onRetry=${() => { metaQ.reload(); catQ.reload(); }} />`
          : !dataReady
            ? html`<${PageSkeleton} />`
            : html`<${ErrorBoundary} resetKey=${loc.path + JSON.stringify(loc.query)}>
                ${Page
                  ? html`<${Page} key=${loc.path} params=${found.params} query=${loc.query} />`
                  : html`<div class="card"><div class="state"><h2>No such page</h2><p>The address ${loc.path} does not exist.</p><a class="btn" href=${href("/")}>Back to the briefing</a></div></div>`}
              </${ErrorBoundary}>`}
      </main>
    </div>
    ${paletteOpen ? html`<${Palette} onClose=${() => setPaletteOpen(false)} />` : null}
    <${TooltipHost} />
    <${ProgressLine} />
  </div>`;
}

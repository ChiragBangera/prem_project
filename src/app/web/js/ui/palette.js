// Command palette: jump to any page, team or player. Opens with Cmd/Ctrl+K or "/".
import { html, useEffect, useLayoutEffect, useMemo, useRef, useState } from "../lib/html.js";
import { Icon } from "../lib/icons.js";
import { navigate } from "../lib/router.js";
import { ui, useStore } from "../lib/store.js";
import { useApi } from "../lib/api.js";
import { fold, seasonLabel } from "../lib/format.js";
import { Crest, Kbd } from "./common.js";

export const PAGES = [
  { path: "/", name: "Briefing", icon: "briefing", hint: "What matters right now" },
  { path: "/league", name: "League table", icon: "table", hint: "Standings, expected points, style" },
  { path: "/matches", name: "Matches", icon: "calendar", hint: "Results with scorers, xG and possession" },
  { path: "/scout", name: "Scout: players", icon: "scout", hint: "Find players with any filter, lens or metric" },
  { path: "/teams", name: "Teams: scout for clubs", icon: "shield", hint: "Every team measure: filters, lenses, columns, map" },
  { path: "/compare", name: "Compare", icon: "compare", hint: "Players or teams side by side" },
  { path: "/shortlist", name: "Shortlist", icon: "star", hint: "Players you are tracking" },
  { path: "/dictionary", name: "Data dictionary", icon: "dictionary", hint: "Every metric: raw or derived, how it is made and read" },
  { path: "/data", name: "Data", icon: "database", hint: "Automatic updates, coverage, storage" },
  { path: "/guide", name: "Guide: where to find things", icon: "info", hint: "Maps, filters, lenses, xPts and every other chart: where each one lives" },
  { path: "/scout", name: "Lenses", icon: "scout", hint: "Quick filters in Scout: Goal threats, Ball winners, Hidden gems ..." },
  { path: "/teams", name: "Style profile and pitch maps", icon: "shield", hint: "Open a team: Overview, then Style & maps" },
];

export function rememberVisit(item) {
  ui.set((s) => {
    const rest = (s.recent || []).filter((r) => r.href !== item.href);
    return { recent: [item, ...rest].slice(0, 8) };
  });
}

export function Palette({ onClose }) {
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef(null);
  const recent = useStore(ui, (s) => s.recent);
  const term = q.trim();
  const search = useApi("/api/search", { q: term, limit: 8 }, { enabled: term.length >= 2, staleMs: 60000 });

  // The palette mounts fresh each time it opens, so there is no state to reset (and no race with the first keystrokes).
  useLayoutEffect(() => {
    inputRef.current?.focus();
    // Escape closes it from anywhere, even before focus has landed in the input
    const esc = (e) => { if (e.key === "Escape") { e.preventDefault(); onClose(); } };
    document.addEventListener("keydown", esc);
    return () => document.removeEventListener("keydown", esc);
  }, []);

  const groups = useMemo(() => {
    const out = [];
    const needle = fold(term);
    const pages = PAGES.filter((p) => !needle || fold(p.name).includes(needle) || fold(p.hint).includes(needle));
    if (pages.length && (!needle || pages.length < PAGES.length)) out.push({ title: needle ? "Pages" : "Go to", items: pages.map((p) => ({ key: p.path + p.name, label: p.name, meta: p.hint, icon: p.icon, go: () => navigate(p.path) })) });
    if (term.length >= 2 && search.data) {
      const teams = (search.data.teams || []).map((t) => ({ key: "t" + t.league + t.name, label: t.name, meta: `Team · ${t.league}`, crest: t, go: () => navigate(`/team/${encodeURIComponent(t.name)}`) }));
      const players = (search.data.players || []).map((p) => ({
        key: "p" + p.id, label: p.name, meta: `${p.team} · ${p.league} ${seasonLabel(p.season)}`, icon: "users",
        go: () => navigate(`/player/${p.id}`, { league: p.league, season: p.season }),
      }));
      if (teams.length) out.push({ title: "Teams", items: teams });
      if (players.length) out.push({ title: "Players", items: players });
    }
    if (!needle && recent?.length) out.push({ title: "Recent", items: recent.map((r) => ({ key: "r" + r.href, label: r.label, meta: r.sub, icon: r.kind === "team" ? "table" : "users", go: () => { window.location.hash = r.href.slice(1); } })) });
    return out;
  }, [term, search.data, recent]);

  const flat = groups.flatMap((g) => g.items);
  useEffect(() => setActive(0), [term, flat.length]);

  const run = (item) => { onClose(); item?.go(); };
  const onKey = (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(flat.length - 1, a + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(0, a - 1)); }
    else if (e.key === "Enter") { e.preventDefault(); run(flat[active]); }
  };
  let index = -1;
  return html`<div class="palette-backdrop" onMouseDown=${(e) => { if (e.target === e.currentTarget) onClose(); }}>
    <div class="palette" role="dialog" aria-modal="true" aria-label="Search and jump" onKeyDown=${onKey}>
      <div class="palette-input">
        <${Icon} name="search" class="muted" />
        <input ref=${inputRef} value=${q} onInput=${(e) => setQ(e.target.value)} placeholder="Search players, teams or pages" aria-label="Search" autocomplete="off" spellcheck="false" />
        <${Kbd}>esc</${Kbd}>
      </div>
      <div class="palette-list" role="listbox">
        ${groups.map((g) => html`<div key=${g.title}>
          <div class="palette-group">${g.title}</div>
          ${g.items.map((it) => {
            index += 1;
            const i = index;
            return html`<button type="button" key=${it.key} class="palette-item" role="option" aria-selected=${String(i === active)} onMouseEnter=${() => setActive(i)} onClick=${() => run(it)}>
              ${it.crest ? html`<${Crest} team=${it.crest.name} short=${it.crest.short} size=${26} />` : html`<span class="tone neutral" style=${{ width: "26px", height: "26px", borderRadius: "7px" }}><${Icon} name=${it.icon} size="sm" /></span>`}
              <span class="truncate">${it.label}</span>
              <span class="meta truncate">${it.meta || ""}</span>
            </button>`;
          })}
        </div>`)}
        ${!flat.length ? html`<div class="state center"><p>${term.length < 2 ? "Type at least two letters." : search.data ? `No page, team or player matches “${term}”.` : "Searching…"}</p></div>` : null}
      </div>
    </div>
  </div>`;
}

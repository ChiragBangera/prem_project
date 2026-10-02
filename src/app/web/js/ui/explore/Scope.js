// Which leagues and seasons are loaded into the explorer. The top bar's league and season are the starting point; this widens or changes them for one page.
import { html } from "../../lib/html.js";
import { setQuery } from "../../lib/router.js";
import { seasonLabel } from "../../lib/format.js";
import { Popover } from "../common.js";

export const csvList = (v) => (v ? String(v).split(",").map((s) => s.trim()).filter(Boolean) : []);

/** The leagues and seasons a page should load: its own choice in the URL (`lg`, `ss`), else the top bar's. */
export function scopeFromQuery(query, scope) {
  const leagues = csvList(query.lg);
  const seasons = csvList(query.ss);
  return { leagues: leagues.length ? leagues : [scope.league], seasons: seasons.length ? seasons : [scope.season], custom: leagues.length > 0 || seasons.length > 0 };
}

const toggle = (list, v) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);

export function ScopePicker({ meta, active, resolvedLabels }) {
  const leagues = meta.leagues;
  const seasons = meta.seasons.slice(0, 10);
  const leagueSel = active.leagues;
  const seasonSel = active.seasons.map(String);
  const nameOf = (c) => leagues.find((l) => l.code === c)?.short || c;
  const summary = [leagueSel.length > 1 ? `${leagueSel.length} leagues` : nameOf(leagueSel[0]), resolvedLabels?.length ? (resolvedLabels.length > 1 ? `${resolvedLabels.length} seasons` : resolvedLabels[0]) : seasonSel.length > 1 ? `${seasonSel.length} seasons` : seasonSel[0] === "auto" ? "Latest" : seasonLabel(seasonSel[0])].join(" · ");
  const set = (nextLeagues, nextSeasons) => setQuery({ lg: nextLeagues.join(",") || null, ss: nextSeasons.join(",") || null });
  return html`<${Popover} label="Data" summary=${summary} icon="database" width=${360} align="right" title="Which leagues and seasons to load">
    <div class="stack" style=${{ "--gap": "14px" }}>
      <div class="stack" style=${{ "--gap": "6px" }}><span class="eyebrow">Leagues</span>
        <div class="chipgroup">${leagues.map((l) => html`<button type="button" class="chip" key=${l.code} aria-pressed=${String(leagueSel.includes(l.code))}
          onClick=${() => { const next = toggle(leagueSel, l.code); if (next.length) set(next, seasonSel); }}>${l.name}</button>`)}</div></div>
      <div class="stack" style=${{ "--gap": "6px" }}><span class="eyebrow">Seasons</span>
        <div class="chipgroup"><button type="button" class="chip" aria-pressed=${String(seasonSel.length === 1 && seasonSel[0] === "auto")} onClick=${() => set(leagueSel, ["auto"])}>Latest</button>
          ${seasons.map((s) => html`<button type="button" class="chip" key=${s.season} aria-pressed=${String(seasonSel.includes(String(s.season)))}
          onClick=${() => { const base = seasonSel.filter((x) => x !== "auto"); const next = toggle(base, String(s.season)); set(leagueSel, next.length ? next : ["auto"]); }}>${s.label}</button>`)}</div></div>
      <p class="xsmall muted">Several seasons of one player are combined into one profile. Several leagues are listed together, and percentiles then compare everyone selected. Seasons you have not downloaded appear once they have been fetched on the Data page.</p>
    </div>
  </${Popover}>`;
}

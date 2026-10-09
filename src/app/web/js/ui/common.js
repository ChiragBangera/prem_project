// Shared building blocks: identity, cards, controls, states and insight cards.
import { html, useEffect, useLayoutEffect, useRef, useState, Component } from "../lib/html.js";
import { Icon } from "../lib/icons.js";
import { href } from "../lib/router.js";
import { cls, hueOf, initials, nf, signed } from "../lib/format.js";
import { tooltip } from "../lib/tooltip.js";
import { helpFor } from "../lib/help.js";
import { api, invalidate } from "../lib/api.js";
import { favouritesStore, shortlistStore, useStore } from "../lib/store.js";

// ------------------------------------------------------------------ links

export const teamHref = (team, query) => href(`/team/${encodeURIComponent(team)}`, query);
export const playerHref = (id, query) => href(`/player/${id}`, query);
export const matchHref = (id, query) => href(`/match/${id}`, query);

export function linkHref(link, scope) {
  if (!link) return null;
  const p = link.params || {};
  if (link.route === "team") return teamHref(p.team);
  if (link.route === "player") return playerHref(p.id, { league: p.league || scope?.league, season: p.season });
  if (link.route === "match") return matchHref(p.id);
  return null;
}

export function useDocumentTitle(title) {
  useEffect(() => { document.title = title ? `${title} · Prem Lab` : "Prem Lab"; }, [title]);
}

// ------------------------------------------------------------------ identity

export function Crest({ team, short, size = 24, round }) {
  const label = short || initials(team).slice(0, 3);
  return html`<span class=${cls("crest", round && "round")} style=${{ "--h": hueOf(team || label), "--s": size + "px" }} aria-hidden="true">${label.slice(0, 3)}</span>`;
}

export function TeamName({ team, short, size = 22, link = true, strong = true, sub }) {
  const inner = html`<${Crest} team=${team} short=${short} size=${size} /><span class=${strong ? "" : "secondary"}>${team}</span>${sub ? html`<span class="muted small">${sub}</span>` : null}`;
  return link
    ? html`<a class="cell-team" href=${teamHref(team)}>${inner}</a>`
    : html`<span class="cell-team">${inner}</span>`;
}

export function Form({ items = [] }) {
  return html`<span class="form" role="img" aria-label=${"Last results: " + items.join(" ").toUpperCase()}>${items.map((r, i) => html`<i class=${r} key=${i}>${r.toUpperCase()}</i>`)}</span>`;
}

// ------------------------------------------------------------------ text-level

export function Badge({ tone, children, title }) {
  return html`<span class=${cls("badge", tone)} title=${title}>${children}</span>`;
}

export function Kbd({ children }) { return html`<kbd>${children}</kbd>`; }

/** Signed value coloured by direction: blue = above expectation, orange = below. Never the only cue (sign is printed). */
export function Delta({ value, digits = 1, suffix = "", inverse = false, class: klass }) {
  if (value == null || !Number.isFinite(value)) return html`<span class="muted">–</span>`;
  const up = inverse ? value < 0 : value > 0;
  const flat = Math.abs(value) < Math.pow(10, -digits) / 2;
  return html`<span class=${cls("delta-val", flat ? "" : up ? "pos" : "neg", klass)}>${signed(value, digits)}${suffix}</span>`;
}

/** True for ready-made content (an html`` template, or a list of them) as opposed to the { what, good, bad } help object. */
export const isContent = (v) => Array.isArray(v) || (typeof v === "object" && v !== null && "props" in v);

/** (i) button. `text` is a string, ready-made content (an html`` template), or { what, good, bad } from lib/help.js. Opens on hover, focus or tap. */
export function Info({ text, label = "About this" }) {
  const ref = useRef(null);
  const body = typeof text === "string" || !text || isContent(text)
    ? text
    : html`<div class="help-body">
        ${text.what ? html`<p>${text.what}</p>` : null}
        ${text.good ? html`<p><b>Good: </b>${text.good}</p>` : null}
        ${text.bad ? html`<p><b>Watch for: </b>${text.bad}</p>` : null}
      </div>`;
  const show = () => {
    const r = ref.current.getBoundingClientRect();
    tooltip.at(r.left + r.width / 2, r.bottom + 4, html`<div style=${{ maxWidth: "300px" }}>${body}</div>`);
  };
  return html`<button class="info" type="button" ref=${ref} aria-label=${label} onMouseEnter=${show} onFocus=${show} onClick=${show} onMouseLeave=${tooltip.hide} onBlur=${tooltip.hide}><${Icon} name="info" size="sm" /></button>`;
}

// ------------------------------------------------------------------ layout

export function PageHead({ title, sub, eyebrow, actions, lead }) {
  return html`<header class="page-head">
    <div class="titles">
      ${eyebrow ? html`<div class="eyebrow">${eyebrow}</div>` : null}
      <div class="row" style=${{ gap: "14px" }}>${lead || null}<h1 class="page-title">${title}</h1></div>
      ${sub ? html`<p class="page-sub">${sub}</p>` : null}
    </div>
    ${actions ? html`<div class="page-actions">${actions}</div>` : null}
  </header>`;
}

export function Card({ title, sub, actions, children, flush, class: klass, id, pad = true, info }) {
  const help = info || helpFor(title);
  return html`<section class=${cls("card", klass)} id=${id}>
    ${title || actions ? html`<div class="card-head">
      <div style=${{ minWidth: 0 }}>${title ? html`<h2 class="card-title">${title}${help ? html` <${Info} text=${help} label=${`About: ${typeof title === "string" ? title : "this chart"}`} />` : null}</h2>` : null}${sub ? html`<p class="card-sub">${sub}</p>` : null}</div>
      ${actions ? html`<div class="chart-actions">${actions}</div>` : null}
    </div>` : null}
    <div class=${cls("card-body", flush && "flush", !pad && "flush")}>${children}</div>
  </section>`;
}

export function Section({ title, sub, actions, children, id, info }) {
  const help = info || helpFor(title);
  return html`<section class="stack" style=${{ "--gap": "12px" }} id=${id}>
    <div class="row between wrap"><div class="section-title"><h2>${title}${help ? html` <${Info} text=${help} label=${`About: ${typeof title === "string" ? title : "this section"}`} />` : null}</h2>${sub ? html`<span class="sub">${sub}</span>` : null}</div>${actions ? html`<div class="row">${actions}</div>` : null}</div>
    ${children}
  </section>`;
}

export function Stat({ label, value, sub, tone, title }) {
  return html`<div class="tile" title=${title}>
    <span class="label">${label}</span>
    <span class="value figure">${value}</span>
    ${sub ? html`<span class=${cls("delta", tone)}>${sub}</span>` : null}
  </div>`;
}

// ------------------------------------------------------------------ controls

export function Button({ children, onClick, kind, icon, size, disabled, title, type = "button", class: klass, ...rest }) {
  return html`<button type=${type} class=${cls("btn", kind, size, !children && "icon-only", klass)} onClick=${onClick} disabled=${disabled} title=${title} aria-label=${!children ? title : undefined} ...${rest}>
    ${icon ? html`<${Icon} name=${icon} size=${size === "sm" ? "sm" : ""} />` : null}${children}
  </button>`;
}

export function Segmented({ options, value, onChange, label, small }) {
  return html`<div class=${cls("segmented", small && "sm")} role="group" aria-label=${label}>
    ${options.map((o) => {
      const opt = typeof o === "string" ? { value: o, label: o } : o;
      return html`<button type="button" key=${opt.value} aria-pressed=${String(opt.value === value)} onClick=${() => onChange(opt.value)} title=${opt.title}>${opt.label}</button>`;
    })}
  </div>`;
}

export function Tabs({ tabs, value, onChange, label }) {
  return html`<div class="tabs" role="tablist" aria-label=${label}>
    ${tabs.map((t) => html`<button type="button" role="tab" key=${t.value} aria-selected=${String(t.value === value)} onClick=${() => onChange(t.value)}>${t.label}${t.count != null ? html` <span class="muted num">${t.count}</span>` : null}</button>`)}
  </div>`;
}

export function Select({ value, options, onChange, label, compact, id, title }) {
  return html`<select class=${cls("select", compact && "compact")} id=${id} value=${value} aria-label=${label} title=${title} onChange=${(e) => onChange(e.target.value)}>
    ${options.map((o) => {
      const opt = typeof o === "string" ? { value: o, label: o } : o;
      return html`<option key=${opt.value} value=${opt.value} selected=${String(opt.value) === String(value)}>${opt.label}</option>`;
    })}
  </select>`;
}

export function Field({ label, children, hint }) {
  return html`<div class="field"><label>${label}</label>${children}${hint ? html`<span class="xsmall muted">${hint}</span>` : null}</div>`;
}

export function Switch({ checked, onChange, children }) {
  return html`<label class="switch"><input type="checkbox" checked=${checked} onChange=${(e) => onChange(e.target.checked)} /><span>${children}</span></label>`;
}

/** A quiet text box with a search icon. */
export function SearchBox({ value, onInput, placeholder = "Search", width }) {
  return html`<label class="searchbox" style=${width ? { width } : null}>
    <${Icon} name="search" size="sm" />
    <input type="search" value=${value} placeholder=${placeholder} aria-label=${placeholder} onInput=${(e) => onInput(e.target.value)} />
  </label>`;
}

/** Dual-thumb range. Values snap to `step`. */
export function RangeSlider({ min, max, step = 1, value, onChange, format = (v) => v, label }) {
  const [lo, hi] = value;
  const pct = (v) => ((v - min) / (max - min || 1)) * 100;
  return html`<div class="field">
    <div class="row between"><label>${label}</label><span class="range-values num">${format(lo)} – ${format(hi)}</span></div>
    <div class="range">
      <div class="track"></div>
      <div class="fill" style=${{ left: pct(lo) + "%", right: 100 - pct(hi) + "%" }}></div>
      <input type="range" min=${min} max=${max} step=${step} value=${lo} aria-label=${label + " minimum"} onInput=${(e) => onChange([Math.min(Number(e.target.value), hi), hi])} />
      <input type="range" min=${min} max=${max} step=${step} value=${hi} aria-label=${label + " maximum"} onInput=${(e) => onChange([lo, Math.max(Number(e.target.value), lo)])} />
    </div>
  </div>`;
}

/**
 * A chip that opens a small panel (used by the filter bars). Closes on outside click and Escape.
 * Uncontrolled by default; pass `open` and `onOpenChange` to control it from outside (for example to reopen it on a filter chip).
 */
export function Popover({ label, summary, active, children, width = 300, align = "left", icon, open: controlled, onOpenChange, title, class: klass }) {
  const [inner, setInner] = useState(false);
  const open = controlled !== undefined ? controlled : inner;
  const setOpen = (v) => { if (controlled === undefined) setInner(v); onOpenChange && onOpenChange(v); };
  const ref = useRef(null);
  const panel = useRef(null);
  const [shift, setShift] = useState(0);
  useLayoutEffect(() => {   // a panel that would run off the screen slides back in, by as little as it needs
    if (!open || !panel.current) { setShift(0); return; }
    const r = panel.current.getBoundingClientRect(), edge = document.documentElement.clientWidth;
    let dx = r.right > edge - 8 ? edge - 8 - r.right : 0;
    if (r.left + dx < 8) dx = 8 - r.left;
    setShift(Math.round(dx));
  }, [open, align, width]);
  useEffect(() => {
    if (!open) return undefined;
    const off = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    const esc = (e) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", off);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", off); document.removeEventListener("keydown", esc); };
  }, [open]);
  return html`<div class="popover-anchor" ref=${ref}>
    <button type="button" class=${cls("chip", active && "on", klass)} aria-haspopup="dialog" aria-expanded=${String(open)} title=${title} onClick=${() => setOpen(!open)}>
      ${icon ? html`<${Icon} name=${icon} />` : null}${label}${summary ? html`<b>${summary}</b>` : null}<${Icon} name="chevronDown" />
    </button>
    ${open ? html`<div ref=${panel} class=${cls("popover pad", align === "right" && "popover-right")} style=${{ width: width + "px", maxWidth: "calc(100vw - 32px)", transform: shift ? `translateX(${shift}px)` : undefined }} role="dialog" aria-label=${label}>${children}</div>` : null}
  </div>`;
}

// ------------------------------------------------------------------ states

export function Skeleton({ h = 16, w = "100%", r }) {
  return html`<div class="skeleton" style=${{ height: h + "px", width: typeof w === "number" ? w + "px" : w, borderRadius: r }}></div>`;
}

export function PageSkeleton({ rows = 3 }) {
  return html`<div class="stack" aria-busy="true" aria-label="Loading">
    <${Skeleton} h=${34} w="38%" />
    <div class="insights">${[0, 1, 2].map((i) => html`<${Skeleton} key=${i} h=${132} r="12px" />`)}</div>
    ${Array.from({ length: rows }, (_, i) => html`<${Skeleton} key=${i} h=${260} r="12px" />`)}
  </div>`;
}

export function EmptyState({ title, text, action, icon = "search", compact }) {
  return html`<div class=${cls("state", "center", compact && "compact")}>
    <${Icon} name=${icon} size="lg" class="muted" />
    <h2>${title}</h2>
    ${text ? html`<p>${text}</p>` : null}
    ${action || null}
  </div>`;
}

export function ErrorState({ error, onRetry }) {
  const e = error || {};
  return html`<div class="card"><div class="state">
    <${Icon} name="alert" size="lg" class="muted" />
    <h2>${e.status === 404 ? "Nothing found" : "This view could not load"}</h2>
    <p>${e.message || "Something went wrong."}</p>
    ${e.hint ? html`<p class="muted">${e.hint}</p>` : null}
    <div class="row" style=${{ marginTop: "8px" }}>
      ${onRetry ? html`<${Button} icon="refresh" onClick=${onRetry}>Try again</${Button}>` : null}
      <a class="btn quiet" href=${href("/data")}>Open Data</a>
    </div>
  </div></div>`;
}

export function Notice({ tone, icon = "info", children }) {
  return html`<div class=${cls("notice", tone)} role=${tone === "crit" ? "alert" : "status"}><${Icon} name=${icon} size="sm" /><div>${children}</div></div>`;
}

/** Renders data-source caveats that every page must be honest about. */
export function DataNotices({ scope, meta, extra = [] }) {
  const notes = [];
  if (scope?.note) notes.push(html`<${Notice} key="note" icon="info">${scope.note}</${Notice}>`);
  if (meta?.stale) notes.push(html`<${Notice} key="stale" tone="warn" icon="alert">Showing saved data. ${meta.error ? `Refresh failed: ${meta.error}` : "The last refresh did not complete."} <a class="link" href=${href("/data")}>Data status</a></${Notice}>`);
  extra.filter(Boolean).forEach((t, i) => notes.push(html`<${Notice} key=${"x" + i} icon="info">${t}</${Notice}>`));
  return notes.length ? html`<div class="stack" style=${{ "--gap": "8px" }}>${notes}</div>` : null;
}

/** Wraps a useApi() result: first-load skeleton, error with retry, and a dimmed re-fetch. */
export function Async({ q, children, skeleton }) {
  if (q.error && !q.data) return html`<${ErrorState} error=${q.error} onRetry=${q.reload} />`;
  if (!q.data) return skeleton || html`<${PageSkeleton} />`;
  return html`<div class=${cls("stack", "fade-in", q.refetching && "is-refetching")} style=${{ "--gap": "24px" }}>
    ${q.error ? html`<${Notice} tone="warn" icon="alert">Could not refresh: ${q.error.message}</${Notice}>` : null}
    ${children(q.data)}
  </div>`;
}

export class ErrorBoundary extends Component {
  state = { error: null };
  static getDerivedStateFromError(error) { return { error }; }
  componentDidCatch(error) { console.error("Render error:", error); }
  componentDidUpdate(prev) { if (prev.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null }); }
  render() {
    if (!this.state.error) return this.props.children;
    return html`<div class="card"><div class="state">
      <${Icon} name="alert" size="lg" class="muted" />
      <h2>This page hit a bug</h2>
      <p>${String(this.state.error.message || this.state.error)}</p>
      <${Button} onClick=${() => this.setState({ error: null })}>Try again</${Button}>
    </div></div>`;
  }
}

// ------------------------------------------------------------------ insights

const TONE_ICON = { positive: "trendUp", negative: "trendDown", warning: "alert", info: "info", neutral: "info" };
const CONF_LABEL = { high: "", medium: "Moderate evidence", low: "Small sample" };
// The tone also gets a word, so it never rests on colour alone.
const KICKER = { positive: "Upside", negative: "Downside", warning: "Watch", info: "Context", neutral: "Context" };

export function InsightCard({ insight, scope, compact }) {
  const to = linkHref(insight.link, scope);
  const Tag = to ? "a" : "div";
  const conf = CONF_LABEL[insight.confidence];
  return html`<${Tag} class=${cls("insight", to && "linked")} href=${to || undefined}>
    <div class="insight-top">
      <span class=${cls("tone", insight.tone)} aria-hidden="true"><${Icon} name=${TONE_ICON[insight.tone] || "info"} size="sm" /></span>
      <div class="stack" style=${{ "--gap": "5px" }}>
        <div class=${cls("kicker", insight.tone)}>${KICKER[insight.tone] || "Context"}</div>
        <div class="insight-head">${insight.headline}</div>
        ${!compact && insight.detail ? html`<div class="insight-detail">${insight.detail}</div>` : null}
      </div>
      ${to ? html`<span class="go" aria-hidden="true"><${Icon} name="arrowUpRight" size="sm" /></span>` : null}
    </div>
    ${insight.evidence?.length ? html`<div class="evidence">${insight.evidence.slice(0, 4).map((e, i) => html`<span key=${i}>${e.label}<b>${e.value}</b></span>`)}</div>` : null}
    ${conf ? html`<div class="insight-foot"><span class=${cls("conf", insight.confidence === "low" && "low")}>${conf}</span></div>` : null}
  </${Tag}>`;
}

export function Insights({ items, scope, limit, compact, expandable, empty = "Nothing stands out right now. That is a finding too: no team or player is far from expectation." }) {
  const [open, setOpen] = useState(false);
  const all = items || [];
  const list = open || !limit ? all : all.slice(0, limit);
  if (!all.length) return html`<div class="well muted">${empty}</div>`;
  return html`<div class="stack" style=${{ "--gap": "12px" }}>
    <div class="insights">${list.map((i) => html`<${InsightCard} key=${i.id} insight=${i} scope=${scope} compact=${compact} />`)}</div>
    ${expandable && limit && all.length > limit ? html`<div><${Button} size="sm" kind="quiet" icon=${open ? "chevronLeft" : "chevronDown"} onClick=${() => setOpen(!open)}>${open ? "Show fewer" : `Show ${all.length - limit} more`}</${Button}></div>` : null}
  </div>`;
}

// ------------------------------------------------------------------ shortlist

/** Toggles instantly and reconciles with the server; a failed save puts things back. */
export async function toggleShortlist(player) {
  const before = shortlistStore.get().items;
  const has = before.some((i) => Number(i.id) === Number(player.id));
  const optimistic = has ? before.filter((i) => Number(i.id) !== Number(player.id)) : [{ id: player.id, name: player.name, team: player.team, league: player.league || "EPL", note: "" }, ...before];
  shortlistStore.set({ items: optimistic, loaded: true });
  try {
    const res = has
      ? await api.del(`/api/shortlist/${player.id}`)
      : await api.put(`/api/shortlist/${player.id}`, { name: player.name, team: player.team, league: player.league || "EPL" });
    shortlistStore.set({ items: res.items, loaded: true });
    invalidate("/api/shortlist");
  } catch (_) {
    shortlistStore.set({ items: before, loaded: true });
  }
}

export function Star({ player }) {
  const items = useStore(shortlistStore, (s) => s.items);
  const on = items.some((i) => Number(i.id) === Number(player.id));
  return html`<button type="button" class="star" aria-pressed=${String(on)} aria-label=${(on ? "Remove " : "Add ") + player.name + (on ? " from shortlist" : " to shortlist")}
    title=${on ? "On your shortlist" : "Add to shortlist"} onClick=${(e) => { e.preventDefault(); e.stopPropagation(); toggleShortlist(player); }}><${Icon} name="star" /></button>`;
}

// ------------------------------------------------------------------ favourite teams

/** Whether a team is a favourite (by league and name; without a league, by name in any league). */
export function useFavourite(team, league) {
  return useStore(favouritesStore, (s) => s.teams.some((t) => t.team === team && (!league || t.league === league)));
}

/** Toggles instantly and reconciles with the server; a failed save puts things back. */
export async function toggleFavourite(league, team) {
  const before = favouritesStore.get().teams;
  const on = before.some((t) => t.league === league && t.team === team);
  favouritesStore.set({ teams: on ? before.filter((t) => !(t.league === league && t.team === team)) : [...before, { league, team }], loaded: true });
  try {
    const res = await api.put("/api/favourites/teams", { league, team, favourite: !on });
    favouritesStore.set({ teams: res.teams, loaded: true });
    invalidate("/api/favourites");
  } catch (_) {
    favouritesStore.set({ teams: before, loaded: true });
  }
}

/** "Favourite team" toggle: a favourite's matches are read at half time as well as full time, and marked on the match lists. */
export function FavouriteButton({ league, team, compact = false }) {
  const on = useFavourite(team, league);
  return html`<button type="button" class=${cls("btn fav-btn", compact ? "sm" : "")} aria-pressed=${String(on)}
    title=${on ? `${team} is a favourite: its matches are read at half time as well as full time. Click to remove.` : `Make ${team} a favourite: its matches are read at half time as well as full time`}
    onClick=${(e) => { e.preventDefault(); e.stopPropagation(); toggleFavourite(league, team); }}><${Icon} name="star" size="sm" /><span>${on ? "Favourite" : "Add to favourites"}</span></button>`;
}

// ------------------------------------------------------------------ small formatting helpers for pages

export const POS_LABEL = { GK: "Goalkeeper", DEF: "Defender", MID: "Midfielder", ATT: "Attacker" };

export function metricValue(m, v) {
  if (v == null || !Number.isFinite(v)) return "–";
  if (m?.unit === "share") return `${(v * 100).toFixed(0)}%`;
  return nf(v, m?.decimals ?? 2);
}

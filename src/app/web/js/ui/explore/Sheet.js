// The explorer's table. Every measure column is the same width and carries a short name; pointing at a heading gives the full name and what
// it means, and clicking it opens a menu: the spread among the rows listed, sort either way, keep the top or bottom, set a limit, hide it.
// Cells are shaded by where the row ranks among its peers, so a strong row reads as a darker row.
import { html, useEffect, useLayoutEffect, useMemo, useRef, useState } from "../../lib/html.js";
import { cls, debounce } from "../../lib/format.js";
import { entryState, stampEntry } from "../../lib/router.js";
import { tooltip, Tip } from "../../lib/tooltip.js";
import { blank, fmtMetric, fmtPct } from "../../lib/metricfmt.js";
import { finiteValues, histogram } from "../../lib/filters.js";
import { Button } from "../common.js";
import { thinSample } from "../cells.js";
import { HistBars } from "./Rail.js";

export const COL_W = 92;      // every measure column, unless a table asks for narrower ones
const PAGE = 60;

/** The shade class for a percentile: three steps up from the middle, one for the bottom, none in between. */
export const shadeOf = (p) => (p == null ? "" : p >= 90 ? "s5" : p >= 75 ? "s4" : p >= 55 ? "s3" : p <= 15 ? "s1" : "");

/** A column spec as an object: a string is a measure of the catalog. */
export const colSpec = (c) => (typeof c === "string" ? { key: c } : c);

/** A share "that came to a shot" and the measure of how often the action was done: the cell draws both (see `SplitBar`). The first volume
 *  measure the catalog has is used; a share with none is drawn as a plain number. */
export const SPLIT_OF = {
  progact_shot_pct: ["progact90", "progact_pg"], progpass_shot_pct: ["prog_passes90", "prog_pg"], carryprog_shot_pct: ["carryprog90", "carryprog_pg"],
  takeon_shot_pct: ["takeonswon90", "takeonswon_pg"], cross_shot_pct: ["crosses90", "crosses_pg"], f3entry_shot_pct: ["f3entry90", "f3entry_pg"],
  move_shot_pct: ["moves90", "moves_pg"],
};

/** Under the number: a bar as long as how often he did it (against the most in the list), its solid part the share that came to a shot,
 *  the hatched part the rest. Volume and what came of it in one cell, so a high share on three actions does not read as a high share. */
function SplitBar({ volume, max, share }) {
  return html`<span class="dk-split" aria-hidden="true"><i style=${{ width: `${Math.max(4, Math.min(100, (volume / max) * 100))}%` }}><b style=${{ width: `${Math.max(0, Math.min(100, share * 100))}%` }}></b></i></span>`;
}

function Cell({ row, ctx, k, mark, peerWord, split }) {
  const i = ctx.idx[k], def = ctx.metrics[k], v = row.v[i];
  if (blank(v)) return html`<span class="dk-c none">–</span>`;
  const p = row.p[i], neutral = def?.hib === null || ctx.plain?.has(k), thin = thinSample(row, def);
  const role = ctx.roles?.plural?.[row.group], poolN = ctx.groupSizes?.[row.group];
  const among = ctx.pctWhat ? ctx.pctWhat(row) : row.group ? `Better than, among ${role?.toLowerCase() || "peers"}${poolN ? ` (${poolN})` : ""}` : `Better than, in ${peerWord}`;
  const move = (e) => tooltip.move(e, html`<${Tip} title=${def?.label || k} sub=${`${row.name ?? row.team}${role && !ctx.pctWhat ? ` · ${role} pool` : ""}`} rows=${[
    { label: "Value", value: fmtMetric(def, v) },
    ...(split && !blank(row.v[split.i]) ? [{ label: ctx.metrics[split.key]?.label || "How often", value: fmtMetric(ctx.metrics[split.key], row.v[split.i]) }] : []),
    ...(p != null && !ctx.plain?.has(k) ? [{ label: among, value: `${fmtPct(p)}%` }] : []),
    ...(def?.hib === null ? [{ label: "Reading", value: "style, not quality" }] : []),
    ...(mark ? [{ label: "Among the rows listed", value: mark === "best" ? "the best" : "the weakest" }] : []),
    ...(thin ? [{ label: "Sample", value: "small: read with care" }] : []),
  ]} />`);
  return html`<span class=${cls("dk-c", !neutral && shadeOf(p), thin && "thin", mark && `mk-${mark}`)} onMouseMove=${move} onMouseLeave=${tooltip.hide}>${fmtMetric(def, v)}${split && !blank(row.v[split.i]) && split.max > 0 ? html`<${SplitBar} volume=${row.v[split.i]} max=${split.max} share=${v / split.scale} />` : null}</span>`;
}

/** The menu under a heading. Filtering parts appear only where the list can be filtered. */
function HeadMenu({ k, at, model, peers, onClose }) {
  const { ctx, view, filtered, setView, setFilters, setColumns, columns } = model;
  const def = ctx.metrics[k];
  const ref = useRef(null);
  const [pos, setPos] = useState({ left: at.left, top: at.top, ready: false });
  const [typed, setTyped] = useState("");
  const [op, setOp] = useState(def?.hib === false ? "<=" : ">=");
  // Place it under the heading, inside the window. An ancestor with a transform makes "fixed" relative to that ancestor, not the window, so
  // the menu is drawn once where asked, measured, and moved by however far that put it from where it should be.
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const r = el.getBoundingClientRect(), root = document.documentElement;
    const offX = r.left - at.left, offY = r.top - at.top;
    const left = Math.max(8, Math.min(at.left, root.clientWidth - r.width - 8));
    const top = Math.max(8, Math.min(at.top, root.clientHeight - r.height - 8));
    setPos({ left: left - offX, top: top - offY, ready: true });
  }, []);
  useEffect(() => {
    const off = (e) => { if (ref.current && !ref.current.contains(e.target) && !e.target.closest?.(".dk-th")) onClose(); };
    const esc = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("mousedown", off); document.addEventListener("keydown", esc); window.addEventListener("resize", onClose);
    return () => { document.removeEventListener("mousedown", off); document.removeEventListener("keydown", esc); window.removeEventListener("resize", onClose); };
  }, []);
  const hist = useMemo(() => histogram(finiteValues(filtered, k, ctx), Math.min(26, Math.max(8, filtered.length))), [filtered, k, ctx]);
  const share = def?.unit === "share";
  const addRule = (rule) => { setFilters((s) => ({ ...s, rules: [...s.rules.filter((r) => !(r.metric === k && r.on === rule.on && r.op === rule.op)), rule] })); onClose(); };
  const sort = (dir) => { setView({ sort: k, dir }); onClose(); };
  const best = def?.hib === false ? "asc" : "desc";
  const ranked = Boolean(setFilters) && filtered.some((r) => r.p[ctx.idx[k]] != null) && def?.hib !== null;
  const limit = typed !== "" && Number.isFinite(Number(typed)) ? Number(typed) : null;
  return html`<div class="dk-menu" ref=${ref} style=${{ left: pos.left + "px", top: pos.top + "px", visibility: pos.ready ? "visible" : "hidden" }} role="dialog" aria-label=${def?.label}>
    <div><h3>${def?.label}</h3><p>${def?.what}${def?.read ? ` ${def.read}` : ""}</p></div>
    ${hist ? html`<div><${HistBars} values=${hist.sorted} lo=${hist.lo} hi=${hist.hi} bins=${hist.counts.length} label=${`Spread of ${def?.label}`} />
      <div class="dk-scale"><span>${fmtMetric(def, hist.sorted[0])}</span><span>middle ${fmtMetric(def, hist.median)}</span><span>${fmtMetric(def, hist.sorted[hist.sorted.length - 1])}</span></div>
      <p class="dk-note">The ${hist.n.toLocaleString("en-GB")} listed now.</p></div>` : html`<p class="dk-note">Too few values in this list to draw its spread.</p>`}
    <div class="dk-two">
      <${Button} size="sm" kind=${view.sort === k && view.dir === best ? "primary" : ""} onClick=${() => sort(best)}>${def?.hib === false ? "Lowest first" : "Highest first"}</${Button}>
      <${Button} size="sm" kind=${view.sort === k && view.dir !== best ? "primary" : ""} onClick=${() => sort(best === "desc" ? "asc" : "desc")}>${def?.hib === false ? "Highest first" : "Lowest first"}</${Button}>
    </div>
    ${ranked ? html`<div><p class="dk-label">Keep only, among ${peers}</p><div class="dk-chips">
      ${[[90, "Top 10%"], [75, "Top 25%"], [50, "Top half"]].map(([p, w]) => html`<button type="button" key=${p} class="chip" onClick=${() => addRule({ metric: k, op: ">=", on: "pct", value: p })}>${w}</button>`)}
      <button type="button" class="chip" onClick=${() => addRule({ metric: k, op: "<=", on: "pct", value: 25 })}>Bottom 25%</button></div></div>` : null}
    ${setFilters ? html`<form class="dk-limit" onSubmit=${(e) => { e.preventDefault(); if (limit != null) addRule({ metric: k, op, on: "value", value: share ? limit / 100 : limit }); }}>
      <select class="select compact" value=${op} aria-label="At least or at most" onChange=${(e) => setOp(e.target.value)}><option value=">=" selected=${op === ">="}>At least</option><option value="<=" selected=${op === "<="}>At most</option></select>
      <input class="input" type="number" step="any" placeholder=${share ? "a percentage" : "a number"} value=${typed} onInput=${(e) => setTyped(e.target.value)} aria-label="Limit" />
      <${Button} size="sm" type="submit" disabled=${limit == null}>Add</${Button}>
    </form>` : null}
    ${setColumns && columns?.keys.includes(k) && k !== "minutes" ? html`<button type="button" class="linklike" onClick=${() => { setColumns(columns.keys.filter((x) => x !== k)); onClose(); }}>Hide this column</button>` : null}
  </div>`;
}

/**
 * model: from useExplorer(), or anything with the same { ctx, view, filtered, shown, setView } (a table that cannot be filtered leaves out
 * setFilters; one whose columns are fixed leaves out setColumns). lead: the first, sticky column: { label, width, sortKey, firstDir, render(row, rank) }.
 * keys: the columns after it, in order. A string is a measure of the catalog; an object is { key, label, title, width, render(row), sort }:
 * a measure key keeps the measure's heading and menu and draws its cell with `render`, any other key is a plain column that sorts by `sort`
 * when given. peers: who a rank is among, in words ("his role", "the league"). picked: the row key now open beside the table; onPick(row).
 * marks: { measure: { best: Set, worst: Set } } of row keys to ring. colWidth: the width of every measure column.
 */
export function Sheet({ model, lead, keys, rowKey, picked, onPick, peers = "his role", caption = "Results", marks = null, colWidth = COL_W }) {
  const { ctx, view, shown, setView } = model;
  const cols = useMemo(() => keys.map(colSpec), [keys]);
  const [menu, setMenu] = useState(null);
  // Coming Back from a player's page lands where the list was left: how far down it was scrolled and how many rows were showing are kept
  // with the history entry (the list scrolls in its own box, so the page's own scroll memory does not cover it).
  const box = useRef(null), was = useRef(entryState()), first = useRef(true);
  const [count, setCount] = useState(() => Math.max(PAGE, was.current.sheetN || 0));
  useEffect(() => { if (first.current) { first.current = false; return; } setCount(PAGE); if (box.current) box.current.scrollTop = 0; }, [shown]);
  useLayoutEffect(() => { if (was.current.sheetY && box.current) box.current.scrollTop = was.current.sheetY; }, []);
  const keep = useMemo(() => debounce((y, n) => stampEntry({ sheetY: y, sheetN: n }), 150), []);
  useEffect(() => { setMenu(null); }, [view.sort, view.dir, cols.map((c) => c.key).join()]);
  const rows = shown.slice(0, count);
  // for each "came to a shot" share on show: where its volume measure is, the most anyone listed did, and whether the share runs to 1 or to 100
  const splits = useMemo(() => {
    const out = {};
    for (const c of cols) {
      const key = (SPLIT_OF[c.key] || []).find((v) => ctx.idx[v] !== undefined);
      if (!key || c.render) continue;
      const i = ctx.idx[key], si = ctx.idx[c.key];
      // the most among the regulars: a rate from a few minutes can be several times anyone else's, and would shrink every other bar
      // (the bar is full at the 95th percentile of the regulars, so one extreme does not shorten the rest either)
      const vols = shown.filter((r) => r.in_pool !== false && !blank(r.v[i])).map((r) => r.v[i]).sort((a, b) => a - b);
      const max = vols.length ? vols[Math.min(vols.length - 1, Math.floor(vols.length * 0.95))] : 0;
      const top = Math.max(0, ...shown.map((r) => (blank(r.v[si]) ? 0 : r.v[si])));
      out[c.key] = { key, i, max, scale: top > 1.5 ? 100 : 1 };
    }
    return out;
  }, [cols, shown, ctx]);
  const isMeasure = (c) => Boolean(ctx.metrics[c.key]) && ctx.idx[c.key] !== undefined;
  const openMenu = (k, e) => { const r = e.currentTarget.getBoundingClientRect(); setMenu(menu?.k === k ? null : { k, at: { left: r.left, top: r.bottom + 6 } }); tooltip.hide(); };
  const hint = (title, what, more) => (e) => {
    if (menu || !what) return;
    const r = e.currentTarget.getBoundingClientRect();
    tooltip.at(r.left + r.width / 2, r.bottom + 2, html`<div style=${{ maxWidth: "260px" }}><div class="tt-title">${title}</div>${what}${more ? html`<div class="tt-sub" style=${{ marginTop: "4px" }}>${more}</div>` : null}</div>`);
  };
  const sortBy = (key, firstDir = "desc") => setView({ sort: key, dir: view.sort === key ? (view.dir === "asc" ? "desc" : "asc") : firstDir });
  const arrow = (k) => (view.sort === k ? html`<span class="dk-arrow" aria-hidden="true">${view.dir === "asc" ? "↑" : "↓"}</span>` : null);
  const ariaSort = (k) => (view.sort === k ? (view.dir === "asc" ? "ascending" : "descending") : undefined);
  const width = lead.width + cols.reduce((s, c) => s + (c.width || colWidth), 0);
  const heading = (c) => {
    if (isMeasure(c)) {
      const def = ctx.metrics[c.key];
      return html`<th key=${c.key} scope="col" class=${cls(view.sort === c.key && "sorted", menu?.k === c.key && "open")} aria-sort=${ariaSort(c.key)}>
        <button type="button" class="dk-th" aria-haspopup="dialog" aria-expanded=${String(menu?.k === c.key)} aria-label=${def.label} onClick=${(e) => openMenu(c.key, e)}
          onMouseEnter=${hint(def.label, def.what, "Click for sorting and filtering")} onMouseLeave=${tooltip.hide}><span class="dk-short">${c.label || def.short}</span>${arrow(c.key)}</button></th>`;
    }
    return html`<th key=${c.key} scope="col" class=${cls("dk-plain", c.align === "left" && "left", c.sort && view.sort === c.sort && "sorted")} aria-sort=${c.sort ? ariaSort(c.sort) : undefined}>
      ${c.sort
        ? html`<button type="button" class="dk-th" onClick=${() => sortBy(c.sort, c.firstDir)} onMouseEnter=${hint(c.full || c.label, c.title, "Click to sort")} onMouseLeave=${tooltip.hide}><span class="dk-short">${c.label}</span>${arrow(c.sort)}</button>`
        : html`<span class="dk-th" tabindex=${c.title ? 0 : undefined} onMouseEnter=${hint(c.full || c.label, c.title)} onMouseLeave=${tooltip.hide}>${c.label}</span>`}</th>`;
  };
  const cell = (row, c, id) => {
    if (c.render) return html`<td key=${c.key} class=${cls("cx", c.className, view.sort === (isMeasure(c) ? c.key : c.sort) && "sorted")}>${c.render(row)}</td>`;
    const m = marks?.[c.key];
    const mark = m ? (m.best.has(id) ? "best" : m.worst.has(id) ? "worst" : null) : null;
    return html`<td key=${c.key} class=${view.sort === c.key ? "sorted" : ""}><${Cell} row=${row} ctx=${ctx} k=${c.key} mark=${mark} peerWord=${peers} split=${splits[c.key]} /></td>`;
  };
  return html`<div class="dk-scroll" ref=${box} onScroll=${(e) => { if (menu) setMenu(null); keep(Math.round(e.currentTarget.scrollTop), count); }}>
    <table class="dk-sheet" style=${{ width: width + "px" }}>
      <caption class="sr-only">${caption}</caption>
      <colgroup><col style=${{ width: lead.width + "px" }} />${cols.map((c) => html`<col key=${c.key} style=${{ width: (c.width || colWidth) + "px" }} />`)}</colgroup>
      <thead><tr>
        <th scope="col" class=${cls("dk-lead", view.sort === lead.sortKey && "sorted")} aria-sort=${ariaSort(lead.sortKey)}>
          <button type="button" class="dk-th" onClick=${() => sortBy(lead.sortKey, lead.firstDir || "asc")}>${lead.label}${arrow(lead.sortKey)}</button></th>
        ${cols.map(heading)}
      </tr></thead>
      <tbody>${rows.map((row, i) => {
        const id = rowKey(row);
        return html`<tr key=${id} class=${cls(picked === id && "picked", lead.rowClass?.(row))} tabindex=${onPick ? "0" : undefined} onClick=${() => onPick && onPick(row)}
          onKeyDown=${(e) => { if (e.key === "Enter" && e.target === e.currentTarget && onPick) onPick(row); }}>
          <td class="dk-lead">${lead.render(row, i + 1)}</td>
          ${cols.map((c) => cell(row, c, id))}
        </tr>`;
      })}</tbody>
    </table>
    ${shown.length > count ? html`<div class="dk-more"><span class="muted small">Showing ${count} of ${shown.length.toLocaleString("en-GB")}</span>
      <${Button} size="sm" onClick=${() => setCount(count + PAGE)}>Show ${Math.min(PAGE, shown.length - count)} more</${Button}><${Button} size="sm" kind="quiet" onClick=${() => setCount(Infinity)}>Show all</${Button}></div>` : null}
    ${menu ? html`<${HeadMenu} key=${menu.k} k=${menu.k} at=${menu.at} model=${model} peers=${peers} onClose=${() => setMenu(null)} />` : null}
  </div>`;
}

/** The key to the shading, in one line. */
export function ShadeKey({ peers = "his role" }) {
  return html`<span class="dk-key" title=${`A darker cell ranks higher in ${peers}; an orange one is in the bottom 15%. Point at any cell for the exact rank.`}>Shade: rank in ${peers}
    <i class="s1"></i><i class="s0"></i><i class="s3"></i><i class="s4"></i><i class="s5"></i><span>low to high</span></span>`;
}

/** The key to the rings a match table draws on its best and weakest cells. */
export function MarkKey() {
  return html`<span class="dk-key"><i class="mk-best"></i><span>best</span><i class="mk-worst"></i><span>weakest, among the rows listed</span></span>`;
}

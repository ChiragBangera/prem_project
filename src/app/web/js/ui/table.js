// Sortable data table with sticky header, sticky first column, heat cells, column bands and "show more" paging.
import { html, useEffect, useMemo, useRef, useState } from "../lib/html.js";
import { cls } from "../lib/format.js";
import { tooltip } from "../lib/tooltip.js";
import { toCsv, download } from "../lib/csv.js";
import { divColor, seqColor } from "../charts/core.js";
import { Button } from "./common.js";

const isBlank = (v) => v == null || (typeof v === "number" && !Number.isFinite(v)) || v === "";

function compare(a, b, dir) {
  const ab = isBlank(a), bb = isBlank(b);
  if (ab || bb) return ab && bb ? 0 : ab ? 1 : -1; // blanks always last
  const r = typeof a === "string" || typeof b === "string" ? String(a).localeCompare(String(b), "en", { sensitivity: "base", numeric: true }) : a - b;
  return dir === "asc" ? r : -r;
}

/** Heat cells stay pale enough for dark text in both themes: magnitude reads as lightness, never as a wall of colour. */
function heatStyle(col, value) {
  const h = col.heat;
  if (!h || isBlank(value)) return null;
  const [lo, hi] = h.domain;
  if (h.mode === "div") {
    const span = Math.max(Math.abs(lo), Math.abs(hi)) || 1;
    const t = Math.max(-1, Math.min(1, value / span));
    return { background: divColor(t * (h.strength ?? 0.5)) };
  }
  let t = (value - lo) / (hi - lo || 1);
  if (h.invert) t = 1 - t;
  t = Math.max(0, Math.min(1, t)) * (h.strength ?? 0.42);
  return { background: seqColor(t) };
}

/**
 * columns: [{ key, label, num, sortable, sticky, width, render(row, i), value(row), title, heat, band }]
 *   `band` names the group a column belongs to; consecutive columns with the same band share one heading cell above the headers.
 * sort / onSort: controlled sorting. presorted: the rows are already in the order wanted (the table only shows the arrow).
 */
/**
 * Whether a scrolling box has more to show to its left or right: a table wider than its card otherwise just looks cut off, because the
 * scroll bar is hidden on most systems until the pointer is over it.
 */
function useScrollEdges() {
  const ref = useRef(null);
  const [edges, setEdges] = useState({ left: false, right: false });
  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const measure = () => {
      const left = el.scrollLeft > 2, right = el.scrollLeft + el.clientWidth < el.scrollWidth - 2;
      setEdges((e) => (e.left === left && e.right === right ? e : { left, right }));
    };
    measure();
    el.addEventListener("scroll", measure, { passive: true });
    const seen = typeof ResizeObserver === "function" ? new ResizeObserver(measure) : null;
    seen?.observe(el);
    if (el.firstElementChild) seen?.observe(el.firstElementChild);
    return () => { el.removeEventListener("scroll", measure); seen?.disconnect(); };
  }, []);
  return [ref, edges];
}

export function DataTable({
  columns, rows, rowKey = (r, i) => i, initialSort, sort: controlled, onSort, onRowClick, dense, maxHeight,
  rowClass, zone, pageSize, caption, empty = "No rows match.", footer, id, tight, presorted, bandLabels,
}) {
  const [scrollRef, edges] = useScrollEdges();
  const [inner, setInner] = useState(initialSort || null);
  const [shown, setShown] = useState(pageSize || Infinity);
  const sort = controlled !== undefined ? controlled : inner;
  useEffect(() => { setShown(pageSize || Infinity); }, [rows, pageSize]);

  const sorted = useMemo(() => {
    if (!sort || presorted) return rows;
    const col = columns.find((c) => c.key === sort.key);
    if (!col) return rows;
    const get = col.value || ((r) => r[col.key]);
    return [...rows].sort((a, b) => compare(get(a), get(b), sort.dir));
  }, [rows, sort, columns, presorted]);

  const clickHeader = (col) => {
    if (col.sortable === false) return;
    const dir = sort?.key === col.key ? (sort.dir === "desc" ? "asc" : "desc") : col.firstDir || (col.num ? "desc" : "asc");
    const next = { key: col.key, dir };
    onSort ? onSort(next) : setInner(next);
  };

  const visible = sorted.slice(0, shown);
  const showHint = (col) => (e) => {
    if (!col.title) return;
    const r = e.currentTarget.getBoundingClientRect();
    tooltip.at(r.left + r.width / 2, r.bottom + 2, html`<div style=${{ maxWidth: "280px" }}><div class="tt-title">${col.fullLabel || col.label}</div>${col.title}</div>`);
  };

  // band heading cells: run-length of consecutive columns with the same band name
  const bands = useMemo(() => {
    if (!columns.some((c) => c.band !== undefined)) return null;
    const out = [];
    for (const c of columns) {
      const name = c.band ?? "";
      const last = out[out.length - 1];
      if (last && last.name === name) last.span += 1; else out.push({ name, span: 1, sticky: c.sticky });
    }
    return out;
  }, [columns]);
  const bandStart = useMemo(() => {
    const starts = new Set();
    let prev;
    columns.forEach((c, i) => { if (i > 0 && c.band !== prev && c.band) starts.add(c.key); prev = c.band; });
    return starts;
  }, [columns]);

  return html`<div class=${cls("table-frame", edges.left && "more-left", edges.right && "more-right")}><div class=${cls("table-wrap", maxHeight && "tall")} style=${maxHeight ? { maxHeight } : null} id=${id} ref=${scrollRef}>
    <table class=${cls("data", dense && "dense", tight && "tight", bands && "banded")}>
      ${caption ? html`<caption class="sr-only">${caption}</caption>` : null}
      <thead>
        ${bands ? html`<tr class="band-row">${bands.map((b, i) => html`<th key=${i} colspan=${b.span} class=${cls("band", b.name && "named", b.sticky && "sticky-col")}>${b.name ? (bandLabels?.[b.name] || b.name) : ""}</th>`)}</tr>` : null}
        <tr>
        ${columns.map((c) => html`<th key=${c.key} scope="col"
            class=${cls(c.num && "num", c.sortable !== false && "sortable", c.sticky && "sticky-col", c.headClass, bandStart.has(c.key) && "band-start", sort?.key === c.key && "sorted")}
            style=${c.width ? { width: c.width, minWidth: c.width } : null}
            aria-sort=${sort?.key === c.key ? (sort.dir === "asc" ? "ascending" : "descending") : undefined}
            onClick=${() => clickHeader(c)} onMouseEnter=${showHint(c)} onMouseLeave=${tooltip.hide}>
            ${c.label}<span class="sort" aria-hidden="true">${sort?.key === c.key ? (sort.dir === "asc" ? "▲" : "▼") : ""}</span>
          </th>`)}
        </tr>
      </thead>
      <tbody>
        ${visible.map((row, i) => {
          const z = zone ? zone(row, i) : null;
          return html`<tr key=${rowKey(row, i)} class=${cls(onRowClick && "clickable", rowClass && rowClass(row, i))}
            onClick=${onRowClick ? () => onRowClick(row) : undefined}
            onKeyDown=${onRowClick ? (e) => { if (e.key === "Enter") onRowClick(row); } : undefined} tabindex=${onRowClick ? 0 : undefined}>
            ${columns.map((c, ci) => {
              const raw = c.value ? c.value(row) : row[c.key];
              const heat = heatStyle(c, raw);
              return html`<td key=${c.key} class=${cls(c.num && "num", c.sticky && "sticky-col", ci === 0 && z && "zone-" + z, c.className, bandStart.has(c.key) && "band-start", sort?.key === c.key && "sorted")} style=${heat}>${c.render ? c.render(row, i) : isBlank(raw) ? html`<span class="muted">–</span>` : raw}</td>`;
            })}
          </tr>`;
        })}
        ${!visible.length ? html`<tr><td colspan=${columns.length} class="muted" style=${{ textAlign: "center", height: "72px", whiteSpace: "normal" }}>${empty}</td></tr>` : null}
      </tbody>
    </table>
    ${sorted.length > shown ? html`<div class="table-more"><span class="muted small">Showing ${shown} of ${sorted.length}</span>
      <${Button} size="sm" onClick=${() => setShown(shown + (pageSize || 50))}>Show ${Math.min(pageSize || 50, sorted.length - shown)} more</${Button}>
      <${Button} size="sm" kind="quiet" onClick=${() => setShown(Infinity)}>Show all</${Button}></div>` : null}
    ${footer || null}
  </div></div>`;
}

/** Downloads the given rows as CSV using each column's plain value. */
export function CsvButton({ columns, rows, filename = "prem-lab.csv", label = "CSV" }) {
  const go = () => {
    const cols = columns.filter((c) => c.csv !== false).map((c) => ({ label: c.csvLabel || c.label, export: c.csvValue || c.value || ((r) => r[c.key]) }));
    download(filename, toCsv(cols, rows));
  };
  return html`<${Button} size="sm" icon="download" onClick=${go} title="Download as CSV">${label}</${Button}>`;
}

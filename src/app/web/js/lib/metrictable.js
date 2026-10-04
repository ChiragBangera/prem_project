// The order of the "Every metric" table on the Player page: by the column asked for, with the groups kept or dissolved. Pure, so it is tested without a browser.
import { isNum } from "./format.js";

/** The sortable columns, and the way round that is more useful the first time one is clicked (best first, A to Z). */
export const SORTS = {
  metric: { label: "metric", asc: "A to Z", desc: "Z to A", firstDir: "asc" },
  value: { label: "value", asc: "lowest first", desc: "highest first", firstDir: "desc" },
  pct: { label: "percentile", asc: "lowest first", desc: "highest first", firstDir: "desc" },
  rank: { label: "rank", asc: "best first", desc: "worst first", firstDir: "asc" },
};

/** One click on a column header: a new column starts the way round that suits it, the same column turns round. */
export function nextSort(sort, key) {
  if (sort && sort.key === key) return { key, dir: sort.dir === "asc" ? "desc" : "asc" };
  return { key, dir: SORTS[key].firstDir };
}

/** The sort in words: "percentile, highest first". */
export const describeSort = (sort) => `${SORTS[sort.key].label}, ${SORTS[sort.key][sort.dir]}`;

/** What a sort on this column reads from a row. A rank of a style metric is not shown, so it does not count. */
function read(it, key) {
  if (key === "metric") return it.label;
  if (key === "value") return it.value;
  if (key === "pct") return it.pct;
  return it.hib === null ? null : it.rank;
}

/**
 * Where a row stands before the order is applied: metrics with a number to compare first, then (for percentile and rank only) the style metrics, whose
 * high or low is neither better nor worse, then those with no number at all. The direction never moves a row between these three.
 */
function tier(it, key) {
  if (key === "metric") return 0;
  if (key === "value") return isNum(it.value) ? 0 : 2;
  const ranked = key === "pct" ? it.pct : it.rank;
  if (!isNum(ranked)) return 2;
  return it.hib === null ? 1 : 0;
}

function compare(a, b, key, dir) {
  const ta = tier(a.it, key), tb = tier(b.it, key);
  if (ta !== tb) return ta - tb;
  let r = 0;
  if (key === "metric") r = String(a.it.label).localeCompare(String(b.it.label), "en", { sensitivity: "base", numeric: true });
  else if (ta !== 2) r = read(a.it, key) - read(b.it, key);
  return (dir === "desc" ? -r : r) || a.at - b.at;       // ties keep the order the table started in, whichever way round
}

/**
 * The table's rows in the order asked for. `blocks` is the profile's metrics by kind: `[{ category, blurb, items }]`; the input is not changed.
 * Grouped: the same blocks, each sorted inside itself. Flat: one block with no heading that holds every row, each row told which kind it came from
 * (`kind`), so a list sorted by percentile still says whether a metric is about shooting or about passing.
 */
export function orderMetrics(blocks, sort, grouped) {
  let at = 0;
  const entries = blocks.map((block) => ({ block, rows: block.items.map((it) => ({ it, kind: block.category, at: at++ })) }));
  const order = (rows) => (sort ? [...rows].sort((a, b) => compare(a, b, sort.key, sort.dir)) : rows);
  if (grouped) return entries.map(({ block, rows }) => ({ ...block, items: order(rows).map((r) => r.it) }));
  const all = order(entries.flatMap((e) => e.rows));
  return [{ category: null, blurb: null, items: all.map((r) => ({ ...r.it, kind: r.kind })) }];
}

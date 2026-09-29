// Shortlist: the players you are tracking, their current numbers, and your own notes.
import { html, useEffect, useMemo, useRef, useState } from "../lib/html.js";
import { api, invalidate, useApi } from "../lib/api.js";
import { useScope, useMeta } from "../lib/scope.js";
import { navigate } from "../lib/router.js";
import { debounce, nf, signed, plural } from "../lib/format.js";
import { Icon } from "../lib/icons.js";
import { shortlistStore, useStore } from "../lib/store.js";
import { Async, Button, Card, EmptyState, PageHead, Notice, Star, toggleShortlist, useDocumentTitle, metricValue } from "../ui/common.js";
import { DataTable, CsvButton } from "../ui/table.js";
import { PctCell, PlayerCell, ScoreCell, TagCell } from "../ui/cells.js";

const KEYS = ["npxg90", "xa90", "xgchain90", "xgbuildup90"];

function NoteCell({ item }) {
  const [text, setText] = useState(item.note || "");
  const [saved, setSaved] = useState(true);
  const save = useMemo(() => debounce(async (v) => {
    try {
      const res = await api.put(`/api/shortlist/${item.id}`, { note: v });
      shortlistStore.set({ items: res.items, loaded: true });
      setSaved(true);
    } catch (_) { setSaved(false); }
  }, 500), [item.id]);
  useEffect(() => setText(item.note || ""), [item.id]);
  return html`<div class="notecell"><input class="input" value=${text} placeholder="Add a note" aria-label=${`Note on ${item.name}`}
    onClick=${(e) => e.stopPropagation()} onInput=${(e) => { setText(e.target.value); setSaved(false); save(e.target.value); }} />
    ${!saved ? html`<span class="xsmall muted">saving…</span>` : null}</div>`;
}

function ShortlistView({ items, rows, catalog, scope }) {
  const byId = new Map(rows.map((r) => [r.id, r]));
  const merged = items.map((it) => ({ ...it, stats: byId.get(it.id) || null }));
  const missing = merged.filter((m) => !m.stats);
  const [picked, setPicked] = useState([]);
  const cols = [
    { key: "pick", label: "", sortable: false, csv: false, width: "34px", render: (r) => html`<input type="checkbox" aria-label=${`Select ${r.name}`} checked=${picked.includes(r.id)} onClick=${(e) => e.stopPropagation()} onChange=${(e) => setPicked(e.target.checked ? [...picked, r.id].slice(-4) : picked.filter((x) => x !== r.id))} />` },
    { key: "star", label: "", sortable: false, csv: false, width: "34px", render: (r) => html`<${Star} player=${r} />` },
    { key: "name", label: "Player", sticky: true, firstDir: "asc", render: (r) => (r.stats ? html`<${PlayerCell} row=${r.stats} season=${scope.season} />` : html`<span class="cell-player"><span class="name">${r.name}</span><span class="sub">${r.team} · no data for this season</span></span>`) },
    { key: "output", label: "Role score", num: true, value: (r) => r.stats?.output, render: (r) => (r.stats ? html`<${ScoreCell} row=${r.stats} />` : "–") },
    { key: "minutes", label: "Min", num: true, value: (r) => r.stats?.minutes },
    ...KEYS.map((k) => ({ key: k, label: catalog.metrics[k].short, num: true, value: (r) => r.stats?.[k], title: catalog.metrics[k].what, render: (r) => (r.stats ? html`<${PctCell} row=${r.stats} metric=${k} def=${catalog.metrics[k]} />` : "–") })),
    { key: "g_xg", label: "G − xG", num: true, value: (r) => r.stats?.g_xg, render: (r) => (r.stats ? html`<span class=${"delta-val " + (r.stats.g_xg > 0.5 ? "pos" : r.stats.g_xg < -0.5 ? "neg" : "")}>${signed(r.stats.g_xg, 1)}</span>` : "–") },
    { key: "tags", label: "Profile", sortable: false, csv: false, render: (r) => (r.stats ? html`<${TagCell} row=${r.stats} />` : null) },
    { key: "note", label: "Your note", sortable: false, csvLabel: "Note", value: (r) => r.note, render: (r) => html`<${NoteCell} item=${r} />` },
    { key: "remove", label: "", sortable: false, csv: false, width: "40px", render: (r) => html`<button type="button" class="star" aria-label=${`Remove ${r.name}`} title="Remove from shortlist" onClick=${(e) => { e.stopPropagation(); toggleShortlist(r); }}><${Icon} name="trash" /></button>` },
  ];
  return html`
    <${PageHead} eyebrow="Shortlist" title="Players you are tracking" sub=${`${plural(items.length, "player")}. Numbers are this season's, compared with role peers. Notes are stored on this computer.`}
      actions=${html`<div class="row wrap" style=${{ gap: "8px" }}>
        <${Button} icon="compare" disabled=${picked.length < 2} onClick=${() => navigate("/compare", { ids: picked.join(",") })}>${picked.length < 2 ? "Tick two to compare" : `Compare ${picked.length}`}</${Button}>
        <${CsvButton} columns=${cols} rows=${merged} filename="prem-lab-shortlist.csv" />
      </div>`} />
    ${missing.length ? html`<${Notice} icon="info">${missing.map((m) => m.name).join(", ")} ${missing.length === 1 ? "has" : "have"} no minutes in the season shown (injured, moved league, or a different season is selected).</${Notice}>` : null}
    <${Card} flush>
      <${DataTable} columns=${cols} rows=${merged} rowKey=${(r) => r.id} initialSort=${{ key: "output", dir: "desc" }} tight caption="Shortlist"
        onRowClick=${(r) => navigate(`/player/${r.id}`, { league: r.league, season: scope.season })} />
    </${Card}>`;
}

export default function Shortlist() {
  const scope = useScope();
  const meta = useMeta();
  const items = useStore(shortlistStore, (s) => s.items);
  const leagues = [...new Set(items.map((i) => i.league || "EPL"))];
  const q = useApi("/api/players", { leagues: leagues.length ? leagues : [scope.league], seasons: [scope.season], min_minutes: 90 }, { enabled: items.length > 0 });
  useDocumentTitle("Shortlist");
  if (!items.length) {
    return html`<div class="stack"><${PageHead} eyebrow="Shortlist" title="Players you are tracking" sub="A private list with your own notes." />
      <${Card}><${EmptyState} icon="star" title="Nobody yet" text="Star a player in Scout or on their profile to keep an eye on them here, with notes and live numbers."
        action=${html`<${Button} kind="primary" icon="scout" onClick=${() => navigate("/scout")}>Open Scout</${Button}>`} /></${Card}></div>`;
  }
  return html`<${Async} q=${q}>${(d) => html`<${ShortlistView} items=${items} rows=${d.rows} catalog=${meta.catalog} scope=${scope} />`}</${Async}>`;
}

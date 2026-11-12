// Shortlist: the players you are tracking, on the same sheet as Scout (column sets, a menu on each heading, shading by rank in the role),
// with your own note on each, one player beside the list and a tray to compare them.
import { html, useEffect, useMemo, useState } from "../lib/html.js";
import { api, useApi } from "../lib/api.js";
import { useScope, useMeta } from "../lib/scope.js";
import { navigate, useLocation } from "../lib/router.js";
import { cls, debounce, plural } from "../lib/format.js";
import { useMedia } from "../lib/media.js";
import { shortlistStore, useStore } from "../lib/store.js";
import { Async, Button, Card, EmptyState, PageHead, Notice, Star, useDocumentTitle } from "../ui/common.js";
import { CsvButton } from "../ui/table.js";
import { PlayerCell } from "../ui/cells.js";
import { useExplorer, sortSentence, openPlayer } from "../ui/explore/model.js";
import { ShadeKey, Sheet } from "../ui/explore/Sheet.js";
import { Peek } from "../ui/explore/Peek.js";
import { ColumnPicker } from "../ui/explore/ColumnPicker.js";
import { CompareTray } from "../ui/explore/Tray.js";

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
    onClick=${(e) => e.stopPropagation()} onKeyDown=${(e) => e.stopPropagation()} onInput=${(e) => { setText(e.target.value); setSaved(false); save(e.target.value); }} />
    ${!saved ? html`<span class="xsmall muted">saving…</span>` : null}</div>`;
}

const NOTE = { key: "note", label: "Your note", width: 240, align: "left", className: "left", title: "Kept on this computer. Type to change it; it saves itself.", render: (r) => html`<${NoteCell} item=${r.item} />` };

function ShortlistView({ items, payload, catalog, scope, query }) {
  // the shortlisted players with this season's numbers, and the ones with none (an injury, a move, another season) as blank rows, so their note stays in reach
  const rows = useMemo(() => {
    const byId = new Map(payload.rows.map((r) => [r.id, r]));
    const empty = payload.keys.map(() => null);
    return items.map((it) => {
      const r = byId.get(it.id);
      return r ? { ...r, note: it.note || "", item: it } : { id: it.id, name: it.name, team: it.team, league: it.league, v: empty, p: empty, note: it.note || "", item: it, missing: true };
    });
  }, [items, payload]);
  const derived = useMemo(() => ({ ...payload, rows }), [payload, rows]);
  const model = useExplorer({ level: "player", payload: derived, catalog, query });
  const { ctx, view, sorted, columns, setView } = model;
  const narrow = useMedia("(max-width: 1000px)");
  const [peekId, setPeekId] = useState(null);
  const peeked = peekId != null && !narrow ? sorted.find((r) => r.id === peekId && !r.missing) : null;
  const picks = useMemo(() => new Set(view.cmp), [view.cmp.join()]);
  const onPick = (id, on) => setView({ cmp: on ? [...view.cmp.filter((x) => x !== id), id].slice(-4) : view.cmp.filter((x) => x !== id) });
  const missing = rows.filter((r) => r.missing);
  const keys = useMemo(() => {
    const set = columns.keys.filter((k) => k !== "minutes");
    const pin = ctx.metrics[view.sort] && ctx.idx[view.sort] !== undefined && view.sort !== "minutes" && !set.includes(view.sort) ? [view.sort] : [];
    return [NOTE, ...pin, ...set, ...(ctx.idx.minutes !== undefined ? ["minutes"] : [])];
  }, [columns.keys.join(), view.sort, ctx]);
  const lead = { label: "Player", width: narrow ? 190 : 270, sortKey: "name",
    render: (r) => html`<div class="dk-who">${r.missing
      ? html`<div class="pcell"><${Star} player=${r} /><span class="cell-player"><span class="name">${r.name}</span><span class="sub">${r.team} · no minutes this season</span></span></div>`
      : html`<${PlayerCell} row=${r} ctx=${ctx} season=${scope.season} picked=${picks.has(r.id)} onPick=${onPick} />`}</div>` };
  const csv = [{ label: "Player", value: (r) => r.name }, { label: "Club", value: (r) => r.team }, { label: "Note", value: (r) => r.note },
    ...keys.filter((k) => typeof k === "string").map((k) => ({ label: ctx.metrics[k].label, value: (r) => r.v[ctx.idx[k]] }))];

  return html`
    <${PageHead} eyebrow="Shortlist" title="Players you are tracking" sub=${`${plural(items.length, "player")}. Numbers are this season's, each ranked against the league's players in the same role. Notes are stored on this computer.`}
      actions=${html`<${CsvButton} columns=${csv} rows=${sorted} filename="prem-lab-shortlist.csv" />`} />
    ${missing.length ? html`<${Notice} icon="info">${missing.map((m) => m.name).join(", ")} ${missing.length === 1 ? "has" : "have"} no minutes in the season shown (injured, moved league, or a different season is selected). ${missing.length === 1 ? "He stays" : "They stay"} on the list with ${missing.length === 1 ? "his" : "their"} note.</${Notice}>` : null}
    <div class=${cls("desk", "norail", "fit", peeked && "peeking")}>
      <section class="dk-main" aria-label="Shortlist">
        <div class="dk-setrow"><div class="dk-sets" role="tablist" aria-label="Which measures to show">
          ${columns.custom ? html`<button type="button" role="tab" aria-selected="true" title="The measures you chose yourself">Your columns</button>` : null}
          ${ctx.views.map((v) => html`<button type="button" role="tab" key=${v.key} aria-selected=${String(columns.preset === v.key)} title=${v.blurb} onClick=${() => setView({ cols: v.key === "overview" ? null : v.key })}>${v.label}</button>`)}
          </div><${ColumnPicker} model=${model} />
        </div>
        <${Sheet} model=${model} lead=${lead} keys=${keys} rowKey=${(r) => r.id} picked=${peeked?.id ?? null} caption="Shortlist"
          onPick=${(r) => (r.missing ? null : narrow ? openPlayer(r, scope) : setPeekId(peekId === r.id ? null : r.id))} />
        <div class="dk-foot"><span>${sortSentence(view, ctx)} ${narrow ? "Tap a player to open his page; the star takes him off." : "Tick two or more to compare them; click a row to see the player beside the list; the star takes him off."}</span><${ShadeKey} /></div>
      </section>
      ${peeked ? html`<${Peek} row=${peeked} ctx=${ctx} season=${scope.season} picked=${picks.has(peeked.id)} onPick=${onPick} onClose=${() => setPeekId(null)} />` : null}
    </div>
    <${CompareTray} ids=${view.cmp} rows=${rows} onChange=${(ids) => setView({ cmp: ids })} />`;
}

export default function Shortlist() {
  const scope = useScope();
  const meta = useMeta();
  const { query } = useLocation();
  const items = useStore(shortlistStore, (s) => s.items);
  const leagues = [...new Set(items.map((i) => i.league || "EPL"))];
  const q = useApi("/api/players", { leagues: leagues.length ? leagues : [scope.league], seasons: [scope.season], min_minutes: 1 }, { enabled: items.length > 0 });
  useDocumentTitle("Shortlist");
  if (!items.length) {
    return html`<div class="stack"><${PageHead} eyebrow="Shortlist" title="Players you are tracking" sub="A private list with your own notes." />
      <${Card}><${EmptyState} icon="star" title="Nobody yet" text="Star a player in Scout or on their profile to keep an eye on them here, with notes and live numbers."
        action=${html`<${Button} kind="primary" icon="scout" onClick=${() => navigate("/scout")}>Open Scout</${Button}>`} /></${Card}></div>`;
  }
  return html`<${Async} q=${q}>${(d) => html`<${ShortlistView} items=${items} payload=${d} catalog=${meta.catalog} scope=${scope} query=${query} />`}</${Async}>`;
}

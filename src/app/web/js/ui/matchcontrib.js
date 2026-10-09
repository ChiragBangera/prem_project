// Who made the chances: each team's expected goals (or assists) split by player, biggest first, with the running share (a Pareto).
import { html, useMemo, useState } from "../lib/html.js";
import { nf } from "../lib/format.js";
import { Card, Segmented, playerHref } from "./common.js";

const MEASURES = [
  { value: "xg", label: "Shots (xG)", of: (p) => p.xg, word: "xG", noun: "took" },
  { value: "xa", label: "Passes (xA)", of: (p) => p.xa, word: "xA", noun: "set up" },
  { value: "both", label: "Both", of: (p) => p.xg + p.xa, word: "xG + xA", noun: "were behind" },
];
const SHOWN = 6;

/** "Enzo Fonete" -> "E. Fonete": the surname is what is recognised, and it keeps a column narrow. One word stays as it is. */
export const shortName = (name) => { const [first, ...rest] = name.trim().split(/\s+/); return rest.length ? `${first[0]}. ${rest.join(" ")}` : name; };

/** One team's players for a measure: the biggest contributors, a pooled "others" line, each with its share and the running share. Pure, so it can be tested. */
export function contributors(players, of, shown = SHOWN) {
  const all = players.map((p) => ({ p, v: of(p) })).filter((x) => x.v > 0.0049).sort((a, b) => b.v - a.v);
  const total = all.reduce((s, x) => s + x.v, 0);
  if (!total) return { total: 0, rows: [] };
  const head = all.slice(0, shown), rest = all.slice(shown);
  const rows = head.map((x) => ({ id: x.p.id, name: x.p.name, v: x.v }));
  if (rest.length) rows.push({ id: null, name: `${rest.length} other${rest.length > 1 ? "s" : ""}`, v: rest.reduce((s, x) => s + x.v, 0) });
  let run = 0;
  return { total, rows: rows.map((r) => { run += r.v; return { ...r, share: r.v / total, cum: run / total }; }) };
}

function Side({ team, color, data, word, max, scope }) {
  const top2 = data.rows.slice(0, 2).reduce((s, r) => s + r.share, 0);
  return html`<div class="contrib-side">
    <div class="contrib-head"><span class="cmp-dot" style=${{ background: color }}></span><b>${team}</b><span class="muted small num">${nf(data.total, 2)} ${word}</span></div>
    ${data.rows.length ? html`<div class="contrib-rows"><div class="contrib-row contrib-colhead xsmall muted"><span></span><span></span><span class="num">${word}</span><span class="num">Share</span><span class="num" title="Running share: this player and everyone above">Σ</span></div>${data.rows.map((r) => html`<div class="contrib-row" key=${r.name}>
      ${r.id ? html`<a class="link truncate" title=${r.name} href=${playerHref(r.id, scope)}>${shortName(r.name)}</a>` : html`<span class="muted truncate">${r.name}</span>`}
      <span class="contrib-track" title=${`${r.name}: ${nf(r.v, 2)} ${word}, ${Math.round(r.share * 100)}% of the team's, ${Math.round(r.cum * 100)}% with everyone above`}><i style=${{ width: (r.v / max) * 100 + "%", background: r.id ? color : "var(--ink-3)" }}></i></span>
      <b class="num">${nf(r.v, 2)}</b><span class="num muted">${Math.round(r.share * 100)}%</span><span class="num muted contrib-cum">${Math.round(r.cum * 100)}%</span>
    </div>`)}</div>
    <p class="xsmall muted contrib-note">${data.rows.length > 1 ? `The top two account for ${Math.round(top2 * 100)}%.` : "One player accounts for all of it."}</p>` : html`<p class="muted small">Nothing to split.</p>`}
  </div>`;
}

export function Contributors({ players, f, scope }) {
  const [measure, setMeasure] = useState("xg");
  const m = MEASURES.find((x) => x.value === measure);
  const data = useMemo(() => ({ h: contributors(players.home, m.of), a: contributors(players.away, m.of) }), [players, m]);
  const max = Math.max(0.01, ...data.h.rows.map((r) => r.v), ...data.a.rows.map((r) => r.v));
  return html`<${Card} title="Who made the chances" sub="Each team's expected goals split by player, biggest first. The bars share one scale, so the two teams compare; Σ is the running share."
    actions=${html`<${Segmented} small label="Measure" value=${measure} onChange=${setMeasure} options=${MEASURES.map(({ value, label }) => ({ value, label }))} />`}>
    <div class="contrib">
      <${Side} team=${f.home} color="var(--c1)" data=${data.h} word=${m.word} max=${max} scope=${scope} />
      <${Side} team=${f.away} color="var(--c2)" data=${data.a} word=${m.word} max=${max} scope=${scope} />
    </div>
  </${Card}>`;
}

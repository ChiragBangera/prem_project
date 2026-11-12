// The Match page's "Moves" section: the match cut into possessions. How each side built (numbers), every move in order with its passes
// numbered on a pitch, how it ended, who lost the ball and who took it, and where on the pitch each side's moves broke down.
// Everything comes from c.possessions (see app/events/possessions.py) through lib/matchcentre.js.
import { html, useEffect, useMemo, useRef, useState } from "../lib/html.js";
import { nf } from "../lib/format.js";
import { Badge, Card, EmptyState, Segmented } from "./common.js";
import { Tug } from "./matchlive.js";
import { PeriodPicker } from "./matchcentre.js";
import { Pitch } from "../charts/pitchmaps.js";
import { BreakLayer, MovePitch } from "../charts/movepitch.js";
import { MOVE_END, MOVE_START, SK, minuteLabel, moveBreaks, moveClock, moveEnding, moveLeaders, moveLines, movePlayers, moveShot, moveStats, pickMoves } from "../lib/matchcentre.js";

const COLOR = ["var(--c1)", "var(--c2)"];
const whole = (v) => nf(v, 0);
const lastName = (c, id) => { const parts = String(c.names?.[id] || "").trim().split(/\s+/); return parts[parts.length - 1] || "–"; };

const RULE = "A move is one side's run of actions. It ends when that side shoots, when play stops (a foul, an offside, the ball out, the half), or when the other side takes the ball: a tackle won, an interception, a clearance, a blocked pass, a loose ball picked up, or simply their next pass. A stray touch or a failed tackle that leaves the ball with the same side does not end it. Who lost it is the last player of the move; after a completed pass nobody is named, because the data does not say who it was meant for. Carries are estimated from the gaps between actions.";

const NUMBERS = [
  ["moves", "Moves"], ["passes_per", "Passes per move", (v) => nf(v, 1)], ["long", "Moves of 10+ passes"], ["f3", "Reached the final third"],
  ["box", "Reached the box"], ["shots", "Ended in a shot"], ["lost", "Taken off them", whole, "low"], ["out", "Played out of play", whole, "low"],
];

function NumbersCard({ c, f, period }) {
  const stats = useMemo(() => moveStats(c, period), [c, period]);
  return html`<${Card} title="How each side built" sub="Every spell of possession counted the same way for both sides." info=${RULE}>
    <div class="row between xsmall" style=${{ marginBottom: "10px" }}><b style=${{ color: "var(--ink)" }}>${f.home}</b><b style=${{ color: "var(--ink)" }}>${f.away}</b></div>
    <div class="stack" style=${{ "--gap": "11px" }}>${NUMBERS.map(([key, label, format = whole, better]) => (stats[0][key] == null || stats[1][key] == null ? null
      : html`<${Tug} key=${key} label=${label} home=${stats[0][key]} away=${stats[1][key]} format=${format} inverse=${better === "low"} />`))}</div>
  </${Card}>`;
}

function Board({ title, sub, rows, hrefOf, unit }) {
  const max = rows[0]?.value || 1;
  return html`<div class="moveboard">
    <div class="leader-label">${title}</div>
    <p class="xsmall muted moveboard-sub">${sub}</p>
    ${rows.length ? rows.map((p) => html`<div class="moveboard-row" key=${p.id}>
      <span class="truncate"><i class="side-dot" style=${{ background: COLOR[p.tm] }}></i>${hrefOf(p.id) ? html`<a class="link" href=${hrefOf(p.id)}>${p.name}</a>` : p.name}</span>
      <span class="moveboard-bar"><i style=${{ width: `${(100 * p.value) / max}%`, background: COLOR[p.tm] }}></i></span>
      <b class="num" title=${`${p.value} ${unit}`}>${p.value}</b>
    </div>`) : html`<p class="small muted">Nobody yet.</p>`}
  </div>`;
}

function LeadersCard({ c, period, hrefOf }) {
  const { lost, broke } = useMemo(() => moveLeaders(c, period, 6), [c, period]);
  return html`<${Card} title="Who lost it, who won it" sub="Counted move by move, both sides together. Players on the ball most lose it most: read it beside how much they had it.">
    <div class="moveboards">
      <${Board} title="Lost the ball most" sub="The last player of a move the other side took, or who played it out." rows=${lost} hrefOf=${hrefOf} unit="moves ended with him" />
      <${Board} title="Broke up most moves" sub="The player whose action ended an opponent's move." rows=${broke} hrefOf=${hrefOf} unit="moves ended by him" />
    </div>
  </${Card}>`;
}

const ENDED = [{ value: "any", label: "Anything" }, { value: "goal", label: "A goal" }, { value: "shot", label: "Any shot" }, { value: "lost", label: "Lost it" }, { value: "out", label: "Out of play" }];
const LENGTHS = [{ value: "0", label: "Any" }, { value: "3", label: "3+" }, { value: "5", label: "5+" }, { value: "10", label: "10+" }];

function EndBadge({ m }) {
  const e = MOVE_END[m.end] || { label: m.end };
  return html`<${Badge} tone=${e.tone || (e.group === "shot" ? "accent" : "")}>${e.label}</${Badge}>`;
}

function MoveRow({ c, f, m, selected, onPick, refFn }) {
  const who = movePlayers(m);
  const names = who.length > 4 ? `${who.slice(0, 3).map((p) => lastName(c, p)).join(", ")} … ${lastName(c, who[who.length - 1])}` : who.map((p) => lastName(c, p)).join(", ");
  const shot = moveShot(c, m);
  return html`<button type="button" role="option" aria-selected=${String(selected)} tabindex=${selected ? 0 : -1} class=${"move-row" + (selected ? " on" : "")} onClick=${onPick} ref=${refFn}>
    <span class="num move-min">${minuteLabel(m.pe, Math.floor(m.c0 / 60))}</span>
    <span class="move-main">
      <span class="move-top"><i class="side-dot" style=${{ background: COLOR[m.tm] }} title=${m.tm === 0 ? f.home : f.away}></i><b>${m.n} ${m.n === 1 ? "pass" : "passes"}</b><span class="muted"> · ${MOVE_START[m.st] || "Open play"}</span></span>
      <span class="move-names truncate">${names}</span>
    </span>
    <span class="move-end"><${EndBadge} m=${m} />${shot?.xg != null ? html`<span class="num xsmall muted">${nf(shot.xg, 2)} xG</span>` : null}</span>
  </button>`;
}

function MoveDetail({ c, f, m, hrefOf, onStep, index, total }) {
  const [active, setActive] = useState(null);
  const lines = useMemo(() => moveLines(c, m), [c, m]);
  const shot = moveShot(c, m);
  const team = m.tm === 0 ? f.home : f.away;
  const secs = Math.max(0, m.c1 - m.c0);
  const starter = m.sp ? ` by ${lastName(c, m.sp)}` : "";
  useEffect(() => setActive(null), [m]);
  return html`<div class="move-detail">
    <div class="move-head">
      <div>
        <div class="move-title"><i class="side-dot" style=${{ background: COLOR[m.tm] }}></i>${team} <span class="muted">· ${moveClock(m)}</span></div>
        <div class="small muted">${MOVE_START[m.st] || "Open play"}${starter} → <b style=${{ color: "var(--ink)" }}>${moveEnding(c, m)}</b></div>
      </div>
      <div class="move-step" role="group" aria-label="Step through the moves">
        <button type="button" class="btn sm" onClick=${() => onStep(-1)} disabled=${index <= 0} aria-label="Previous move">‹</button>
        <span class="num xsmall muted">${index + 1} of ${total}</span>
        <button type="button" class="btn sm" onClick=${() => onStep(1)} disabled=${index >= total - 1} aria-label="Next move">›</button>
      </div>
    </div>
    <${MovePitch} move=${m} lines=${lines} names=${c.names} color=${COLOR[m.tm]} shot=${shot} active=${active} label=${`${team}: the move at ${moveClock(m)}, action by action`} />
    <div class="legend move-legend">
      <span class="item"><svg width="26" height="10" aria-hidden="true"><line x1="1" y1="5" x2="24" y2="5" stroke="currentColor" stroke-width="2" /></svg>Pass</span>
      <span class="item"><svg width="26" height="10" aria-hidden="true"><line x1="1" y1="5" x2="24" y2="5" stroke="currentColor" stroke-width="2" stroke-dasharray="1 4" stroke-linecap="round" /></svg>Carry (estimated)</span>
      <span class="item"><svg width="26" height="10" aria-hidden="true"><line x1="1" y1="5" x2="24" y2="5" stroke="currentColor" stroke-width="1.6" stroke-dasharray="5 3" /></svg>Did not arrive</span>
      <span class="item"><svg width="12" height="12" aria-hidden="true"><circle cx="6" cy="6" r="5" fill="none" stroke="currentColor" stroke-width="1.4" /><path d="M3.5 3.5l5 5m0 -5l-5 5" stroke="currentColor" stroke-width="1.4" /></svg>Where it was taken</span>
    </div>
    <div class="duo-facts move-facts">
      <div><span>Passes completed</span><b class="num">${m.n}</b></div>
      <div><span>Players involved</span><b class="num">${movePlayers(m).length}</b></div>
      <div><span>Lasted</span><b class="num">${secs} s</b></div>
    </div>
    <ol class="move-lines">${lines.map((l, i) => html`<li key=${i} class=${(l.n == null ? "carry" : "") + (l.ok ? "" : " miss")}
      onMouseEnter=${() => l.step != null && setActive(l.step)} onMouseLeave=${() => setActive(null)}>
      ${l.n != null ? html`<span class="move-n num" style=${{ background: l.ok || l.kind === SK.SHOT ? COLOR[m.tm] : "transparent", borderColor: COLOR[m.tm], color: l.ok || l.kind === SK.SHOT ? "#fff" : "var(--ink)" }}>${l.n}</span>` : html`<span class="move-n none"></span>`}
      <span>${l.text}</span></li>`)}
      <li class="move-endline"><span class="move-n none"></span><b>${moveEnding(c, m)}</b>${m.end === "lost" && m.by && hrefOf(m.by) ? html` <a class="link small" href=${hrefOf(m.by)}>${c.names?.[m.by]}</a>` : null}</li>
    </ol>
  </div>`;
}

function Explorer({ c, f, period, onPeriod, hrefOf }) {
  const [tm, setTm] = useState("both");
  const [ended, setEnded] = useState("any");
  const [min, setMin] = useState("3");
  const [box, setBox] = useState(false);
  const [chosen, setChosen] = useState(null);
  const all = c.possessions || [];
  const rows = useMemo(() => pickMoves(c, { period, tm: tm === "both" ? null : Number(tm), ended, minPasses: Number(min), box }), [c, period, tm, ended, min, box]);
  const inPeriod = useMemo(() => pickMoves(c, { period }).length, [c, period]);
  // opens on a goal if there was one, else on the longest move
  const fallback = useMemo(() => rows.find((m) => m.end === "goal") || rows.reduce((a, m) => (!a || m.n > a.n ? m : a), null), [rows]);
  const current = rows.includes(chosen) ? chosen : fallback;
  const index = rows.indexOf(current);
  const refs = useRef(new Map());
  const focusNext = useRef(false);
  const step = (d, focus) => { const next = rows[Math.min(rows.length - 1, Math.max(0, index + d))]; if (next) { focusNext.current = Boolean(focus); setChosen(next); } };
  useEffect(() => {
    const el = refs.current.get(current);
    if (!el) return;
    const list = el.parentElement;
    if (el.offsetTop < list.scrollTop || el.offsetTop + el.offsetHeight > list.scrollTop + list.clientHeight) list.scrollTop = el.offsetTop - list.clientHeight / 2 + el.offsetHeight / 2;
    if (focusNext.current) { el.focus({ preventScroll: true }); focusNext.current = false; }
  }, [current]);
  const onKey = (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowRight") { e.preventDefault(); step(1, true); }
    else if (e.key === "ArrowUp" || e.key === "ArrowLeft") { e.preventDefault(); step(-1, true); }
  };
  const hidden = inPeriod - rows.length;
  const reset = () => { setTm("both"); setEnded("any"); setMin("0"); setBox(false); };
  return html`<${Card} title="Every move, pass by pass" sub="Pick a move to see it drawn: each action numbered in order, who played it, and how it ended." info=${RULE}
    actions=${html`<${PeriodPicker} c=${c} value=${period} onChange=${onPeriod} />`}>
    <div class="move-filters">
      <label class="move-filter"><span>Side</span><${Segmented} small label="Side" value=${tm} onChange=${setTm} options=${[{ value: "both", label: "Both" }, { value: "0", label: f.home_short || f.home }, { value: "1", label: f.away_short || f.away }]} /></label>
      <div class="move-filter"><span>Ended in</span><div class="chipgroup" role="group" aria-label="How the move ended">${ENDED.map((o) => html`<button type="button" key=${o.value} class="chip" aria-pressed=${String(ended === o.value)} onClick=${() => setEnded(o.value)}>${o.label}</button>`)}</div></div>
      <label class="move-filter"><span>Passes</span><${Segmented} small label="Passes completed" value=${min} onChange=${setMin} options=${LENGTHS} /></label>
      <div class="move-filter"><span>Where</span><button type="button" class="chip" aria-pressed=${String(box)} onClick=${() => setBox(!box)}>Reached the box</button></div>
    </div>
    <p class="small muted move-count" aria-live="polite"><b class="num" style=${{ color: "var(--ink)" }}>${rows.length}</b> of ${inPeriod} moves${hidden > 0 ? html` · ${hidden} hidden by the choices above. <button type="button" class="link-btn" onClick=${reset}>Show every move</button>` : ""}</p>
    ${!all.length ? html`<${EmptyState} compact title="No moves to show" text="This match's event data has no possessions yet." />`
      : !rows.length ? html`<${EmptyState} compact title="No move fits" text="Nothing in this part of the match matches those choices." action=${html`<button type="button" class="btn sm" onClick=${reset}>Show every move</button>`} />`
      : html`<div class="moves">
        <div class="move-list" role="listbox" aria-label="Moves, in order" onKeyDown=${onKey}>
          ${rows.map((m) => html`<${MoveRow} key=${all.indexOf(m)} c=${c} f=${f} m=${m} selected=${m === current} onPick=${() => setChosen(m)} refFn=${(el) => (el ? refs.current.set(m, el) : refs.current.delete(m))} />`)}
        </div>
        ${current ? html`<${MoveDetail} c=${c} f=${f} m=${current} hrefOf=${hrefOf} onStep=${step} index=${index} total=${rows.length} />` : null}
      </div>`}
  </${Card}>`;
}

function BreaksCard({ c, f, period }) {
  const side = (tm) => {
    const rows = moveBreaks(c, tm, period);
    const name = tm === 0 ? f.home : f.away;
    const own = rows.filter((r) => r[0] < 500).length, f3 = rows.filter((r) => r[0] >= 667).length;
    return html`<div class="duo-side" key=${tm}>
      <div class="duo-head"><b><i class="side-dot" style=${{ background: COLOR[tm] }}></i>${name}</b><span class="muted small num">${rows.length} moves taken off them</span></div>
      <${Pitch} label=${`${name}: where its moves were taken off it`} maxWidth=${0} caption=${false}><${BreakLayer} rows=${rows} names=${c.names} color="var(--pitch-ink)" /></${Pitch}>
      <div class="duo-facts">
        <div><span>In their own half</span><b class="num">${own}</b></div>
        <div><span>In the final third</span><b class="num">${f3}</b></div>
        <div><span>Share in their own half</span><b class="num">${rows.length ? `${nf((100 * own) / rows.length, 0)}%` : "–"}</b></div>
      </div>
    </div>`;
  };
  return html`<${Card} title="Where the moves broke down" sub="Each cross is a move the other side took, drawn where they took it, in the direction the side with the ball was attacking. Losing it on the left of the map is losing it near your own goal.">
    <div class="duo">${side(0)}${side(1)}</div>
  </${Card}>`;
}

export function MovesSection({ c, f, period, onPeriod, hrefOf }) {
  return html`<div class="stack" style=${{ "--gap": "16px" }}>
    <${Explorer} c=${c} f=${f} period=${period} onPeriod=${onPeriod} hrefOf=${hrefOf} />
    <div class="mrow m-5-7">
      <${NumbersCard} c=${c} f=${f} period=${period} />
      <${LeadersCard} c=${c} period=${period} hrefOf=${hrefOf} />
    </div>
    <${BreaksCard} c=${c} f=${f} period=${period} />
  </div>`;
}

// The shot board: one way to look at shots at every level (a match, a player's season, a team's season).
// A map, the same shots in a list beside it, and the detail of whichever one is picked. Hovering a row rings its circle and the other way round.
import { html, useEffect, useMemo, useRef, useState } from "../lib/html.js";
import { dateShort, nf, plural } from "../lib/format.js";
import { SHOT_RESULTS, SHOT_SITUATIONS, bodyWord, filterShots, lastActionWord, orderShots, resultWord, shotTakers, shotTotals, situationWord } from "../lib/shots.js";
import { ShotLegend, ShotPitch } from "../charts/pitch.js";
import { Badge, Button, EmptyState, Segmented, Select } from "./common.js";

const LIST_STEP = 60;      // rows drawn before "Show all": a season of a team's shots is several hundred
const CHIP_TAKERS = 14;    // more takers than this and the chips become a menu

function totalsLine(t, hasXg) {
  const parts = [plural(t.n, "shot"), `${t.goals} ${t.goals === 1 ? "goal" : "goals"}`, `${t.on_target} on target`];
  if (hasXg && t.xg != null) {
    parts.push(`${nf(t.xg, 2)} xG`);
    if (t.per != null) parts.push(`${nf(t.per, 2)} per shot`);
    else if (t.known < t.n) parts.push(`${t.n - t.known} with no xG`);
  }
  return parts.join(" · ");
}

function Row({ s, sides, multi, hasXg, hot, sel, onHot, onPick, playerHref, matchHref, refOf }) {
  const side = sides[s.side ?? 0] || sides[0];
  const where = s.opponent ? `${s.home === false ? "at" : "v"} ${s.opponent}` : null;
  const main = s.player || where || resultWord(s.result);
  const sub = [s.player && multi ? where : null, situationWord(s.situation), s.assisted_by ? `assist ${s.assisted_by}` : null].filter(Boolean).join(" · ");
  const came = lastActionWord(s.last_action);
  const pHref = playerHref ? playerHref(s) : undefined, mHref = matchHref ? matchHref(s) : undefined;
  return html`<div class=${"shotrow" + (hot ? " hot" : "") + (sel ? " sel" : "")} ref=${refOf}>
    <button type="button" aria-expanded=${String(sel)} onClick=${() => onPick(s)} onMouseEnter=${() => onHot(s.id)} onMouseLeave=${() => onHot(null)} onFocus=${() => onHot(s.id)} onBlur=${() => onHot(null)}>
      <i class="sr-dot" style=${{ background: side.color }} title=${side.label}></i>
      <span class="sr-when">${multi && s.date ? html`<b>${dateShort(s.date)}</b>` : null}${s.minute}′</span>
      <span class="sr-main"><span>${main}</span><span class="xsmall muted">${sub}</span></span>
      <${Badge} tone=${s.result === "Goal" ? "good" : ""}>${resultWord(s.result)}</${Badge}>
      ${hasXg ? html`<span class=${"sr-xg" + (s.xg == null ? " none" : "")} title=${s.xg == null ? "No xG for this shot" : "Expected goals: the chance an average finisher scores it"}>${s.xg == null ? "–" : nf(s.xg, 2)}</span>` : null}
    </button>
    ${sel ? html`<div class="sr-detail">
      <dl>
        ${s.player ? html`<dt>Taken by</dt><dd>${s.player}${side.label ? ` (${side.label})` : ""}</dd>` : null}
        <dt>When</dt><dd>${s.minute}′${where ? `, ${where}` : ""}${s.date ? `, ${dateShort(s.date)}` : ""}</dd>
        <dt>Result</dt><dd>${resultWord(s.result)}</dd>
        <dt>xG</dt><dd>${s.xg == null ? "No xG for this shot" : `${nf(s.xg, 2)}: an average finisher scores about ${Math.max(1, Math.round(s.xg * 100))} in 100 like it`}</dd>
        ${s.type ? html`<dt>Body part</dt><dd>${bodyWord(s.type)}</dd>` : null}
        ${s.situation ? html`<dt>Situation</dt><dd>${situationWord(s.situation)}</dd>` : null}
        ${s.assisted_by ? html`<dt>Assisted by</dt><dd>${s.assisted_by}</dd>` : null}
        ${came ? html`<dt>Came from</dt><dd>${came}</dd>` : null}
      </dl>
      ${pHref || mHref ? html`<div class="sr-links">${pHref ? html`<a class="link" href=${pHref}>${s.player}'s page</a>` : null}${mHref ? html`<a class="link" href=${mHref}>Open the match</a>` : null}</div>` : null}
    </div>` : null}
  </div>`;
}

/**
 * shots: see lib/shots.js. sides: [{ label, color, mirror }] by each shot's `side` (one or two).
 * layout: "full" pitch or the attacking "half". takers: offer a filter by who took the shot (`takerSides`: only for these sides).
 * multi: the list spans several matches, so each row carries its date and opponent. hasXg false: a match read before xG exists.
 * controls: extra controls for the top row (a season picker). playerHref / matchHref: (shot) => address or undefined.
 */
export function ShotBoard({ shots, sides, layout = "full", takers = false, takerSides = null, multi = false, hasXg = true, sort = "time", controls, playerHref, matchHref, empty = "No shots match this filter.", maxWidth }) {
  const [situation, setSituation] = useState("all");
  const [result, setResult] = useState("all");
  const [side, setSide] = useState("both");
  const [taker, setTaker] = useState(null);
  const [order, setOrder] = useState(sort);
  const [sel, setSel] = useState(null);
  const [hot, setHot] = useState(null);
  const [limit, setLimit] = useState(LIST_STEP);
  const listRef = useRef(null), rowRefs = useRef(new Map());

  const two = sides.length > 1;
  const people = useMemo(() => (takers ? shotTakers(shots).filter((t) => !takerSides || takerSides.includes(t.side)) : []), [shots, takers, takerSides]);
  const who = people.some((t) => t.key === taker) ? taker : null;   // a taker who is not in this list any more (another season) is no filter
  const visible = useMemo(() => orderShots(filterShots(shots, { side: side === "both" || !two ? null : Number(side), taker: who, situation, result }), order),
    [shots, side, two, who, situation, result, order]);
  const picked = visible.some((s) => s.id === sel) ? sel : null;
  const anyNoXg = hasXg && visible.some((s) => s.xg == null);
  useEffect(() => setLimit(LIST_STEP), [shots, side, who, situation, result, order]);

  const pick = (s, fromMap) => {
    const next = picked === s.id ? null : s.id;
    setSel(next);
    if (next == null || !fromMap) return;
    const at = visible.findIndex((x) => x.id === s.id);
    if (at >= limit) setLimit(visible.length);
    // bring its row into view inside the list only: the page itself must not jump
    requestAnimationFrame(() => {
      const row = rowRefs.current.get(s.id), box = listRef.current;
      if (row && box) box.scrollTop = Math.max(0, row.offsetTop - box.offsetTop - 40);
    });
  };

  const situations = SHOT_SITUATIONS.filter((x) => x.value === "all" || shots.some(x.test));
  const shownSides = sides.map((sd, i) => ({ ...sd, i })).filter((sd) => (side === "both" || !two || Number(side) === sd.i) && (who == null || who.startsWith(sd.i + ":")));
  const rows = visible.slice(0, limit);

  return html`<div class=${"shotboard" + (layout === "half" ? " half" : "") + (multi ? " multi" : "")}>
    <div class="sbd-controls">
      ${two ? html`<${Segmented} small label="Which side" value=${side} onChange=${(v) => { setSide(v); setTaker(null); }} options=${[{ value: "both", label: "Both" }, ...sides.map((sd, i) => ({ value: String(i), label: sd.short || sd.label }))]} />` : null}
      ${situations.length > 2 ? html`<${Segmented} small label="Situation" value=${situation} onChange=${setSituation} options=${situations.map((x) => ({ value: x.value, label: x.label }))} />` : null}
      <${Segmented} small label="Result" value=${result} onChange=${setResult} options=${SHOT_RESULTS.map((x) => ({ value: x.value, label: x.label }))} />
      ${people.length > CHIP_TAKERS ? html`<${Select} compact label="Taken by" value=${who || ""} onChange=${(v) => setTaker(v || null)}
        options=${[{ value: "", label: "Taken by anyone" }, ...people.map((t) => ({ value: t.key, label: `${t.name} (${t.n})` }))]} />` : null}
      ${controls || null}
    </div>
    ${people.length > 1 && people.length <= CHIP_TAKERS ? html`<div class="sbd-takers" role="group" aria-label="Show one player's shots">
      <button type="button" class="chip" aria-pressed=${String(who == null)} onClick=${() => setTaker(null)}>Everyone</button>
      ${people.map((t) => html`<button type="button" key=${t.key} class="chip" aria-pressed=${String(who === t.key)} onClick=${() => setTaker(who === t.key ? null : t.key)}
        title=${`${t.name}: ${plural(t.n, "shot")}, ${t.goals} ${t.goals === 1 ? "goal" : "goals"}${t.xg != null ? `, ${nf(t.xg, 2)} xG` : ""}`}>
        <i style=${{ background: sides[t.side]?.color }}></i>${t.name} <span class="muted">${t.n}</span></button>`)}
    </div>` : null}
    ${visible.length ? html`<div class="sbd-body">
      <div class="sbd-map">
        <${ShotPitch} shots=${visible} sides=${sides} layout=${layout} hot=${hot} sel=${picked} onHot=${setHot} onPick=${(s) => pick(s, true)} maxWidth=${maxWidth} />
        <div class="sbd-totals">${shownSides.map((sd) => {
          const t = shotTotals(visible.filter((s) => (s.side ?? 0) === sd.i));
          return html`<span key=${sd.i}><i style=${{ background: sd.color }}></i><span><b>${sd.label}</b>${sd.goal ? ` (${sd.goal})` : ""}: ${totalsLine(t, hasXg)}</span></span>`;
        })}</div>
        <${ShotLegend} noXg=${anyNoXg} size=${hasXg} />
        ${hasXg ? null : html`<p class="xsmall muted" style=${{ margin: 0 }}>Every circle is the same size until Understat's xG arrives after full time. No xG is estimated in the meantime.</p>`}
      </div>
      <div class="sbd-side">
        <div class="sbd-head"><span>${plural(visible.length, "shot")}. Pick one for its detail.</span>
          ${hasXg ? html`<${Segmented} small label="Order of the list" value=${order} onChange=${setOrder} options=${[{ value: "time", label: "In order" }, { value: "xg", label: "Best chance first" }]} />` : null}</div>
        <div class="sbd-list" ref=${listRef}>
          ${rows.map((s) => html`<${Row} key=${s.id} s=${s} sides=${sides} multi=${multi} hasXg=${hasXg} hot=${hot === s.id} sel=${picked === s.id} onHot=${setHot} onPick=${(x) => pick(x, false)}
            playerHref=${playerHref} matchHref=${matchHref} refOf=${(el) => { if (el) rowRefs.current.set(s.id, el); else rowRefs.current.delete(s.id); }} />`)}
        </div>
        ${visible.length > limit ? html`<div class="sbd-more"><${Button} kind="quiet" size="sm" onClick=${() => setLimit(visible.length)}>Show all ${visible.length}</${Button}></div>` : null}
      </div>
    </div>` : html`<${EmptyState} compact icon="scatter" title="No shots to show" text=${empty} />`}
  </div>`;
}

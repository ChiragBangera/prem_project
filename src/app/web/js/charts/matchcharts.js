// The Match page's own charts, drawn from a match's event rows: who was on top minute by minute, the goals, cards and substitutions along the
// clock, where the shots went in the goal, which side each team attacked down, and the line-ups on a pitch.
import { html, useState } from "../lib/html.js";
import { tooltip } from "../lib/tooltip.js";
import { nf } from "../lib/format.js";
import { Frame, scaleLinear } from "./core.js";
import { L, W, PitchMarks, Stripes } from "./pitchmaps.js";
import { minuteLabel, momentum } from "../lib/matchcentre.js";

const SIDE_COLOR = ["var(--c1)", "var(--c2)"];
const surname = (name) => String(name || "").trim().split(" ").slice(-1)[0];
const KIND_WORD = { goal: "Goal", penalty: "Penalty scored", own_goal: "Own goal", yellow: "Yellow card", red: "Red card", sub: "Substitution" };

/** The ticks of a match clock: the continuous minute each sits at, and the match minute it is called. */
function clockTicks(clock) {
  const ht = clock.ht ?? 45, from2 = clock.second_from ?? ht + 1, end = clock.end ?? 90;
  const ticks = [0, 15, 30].map((m) => ({ at: m, label: m === 0 ? "KO" : `${m}′` }));
  if (clock.second_from != null) [15, 30, 45].forEach((d) => { if (from2 + d <= end + 1) ticks.push({ at: from2 + d, label: `${45 + d}′` }); });
  return { ticks, ht, from2, end, hasSecond: clock.second_from != null };
}

function eventTip(c, f, t) {
  const who = t.p ? c.names?.[t.p] : t.kind === "yellow" || t.kind === "red" ? "Team official" : "";
  const other = t.other ? c.names?.[t.other] : null;
  return html`<div>
    <div class="tt-title">${minuteLabel(t.pe, t.mi)} · ${KIND_WORD[t.kind] || t.kind}${t.second ? " (second yellow)" : ""}</div>
    <div class="tt-sub">${who}${who ? " · " : ""}${t.tm === 0 ? f.home : f.away}</div>
    ${other ? html`<div class="tt-row"><span class="k">${t.kind === "sub" ? "Replaced" : "Assist"}</span><span class="v">${other}</span></div>` : null}
  </div>`;
}

/** A goal, card or substitution as a small mark centred on (0, 0). */
export function EventGlyph({ kind, color, size = 7 }) {
  if (kind === "goal" || kind === "penalty" || kind === "own_goal") {
    return html`<g class="ev-goal"><circle r=${size} style=${{ fill: kind === "own_goal" ? "var(--surface)" : color, stroke: kind === "own_goal" ? color : "var(--surface)" }} stroke-width="2" />
      ${kind === "penalty" ? html`<text class="ev-letter" dy="0.36em" text-anchor="middle" style=${{ fontSize: size * 1.25 + "px" }}>P</text>` : null}
      ${kind === "own_goal" ? html`<text class="ev-letter og" dy="0.36em" text-anchor="middle" style=${{ fontSize: size * 0.95 + "px", fill: color }}>OG</text>` : null}</g>`;
  }
  if (kind === "yellow" || kind === "red") return html`<rect class=${"ev-card " + kind} x=${-size * 0.5} y=${-size * 0.72} width=${size} height=${size * 1.44} rx="1.5" />`;
  return html`<path class="ev-sub" d=${`M${-size * 0.6} ${-size * 0.15}L0 ${-size * 0.75}L${size * 0.6} ${-size * 0.15}M${-size * 0.6} ${size * 0.75}L0 ${size * 0.15}L${size * 0.6} ${size * 0.75}`} />`;
}

/**
 * Momentum: for every minute, how much each side had the ball in the final third (see lib/matchcentre.js momentum). The home side grows upward,
 * the away side downward, so who was on top and when reads at a glance; goals, cards and substitutions sit on the same clock.
 */
export function Momentum({ c, f, height = 260 }) {
  const [hover, setHover] = useState(null);
  const mo = momentum(c);
  const { ticks, ht, from2, end, hasSecond } = clockTicks(c.clock);
  const gap = hasSecond ? 2.4 : 0;                       // a breath between the halves, in minutes
  const pos = (em, pe) => (hasSecond && (pe === 2 || em >= from2) ? em + gap : em);
  const events = c.timeline || [];
  const lane = (list) => {                                // marks that share a minute step outward instead of covering each other
    let last = -99, depth = 0;
    return list.map((t) => { depth = t.em - last <= 1 ? depth + 1 : 0; last = t.em; return { ...t, depth }; });
  };
  const marks = [...lane(events.filter((t) => t.tm === 0)), ...lane(events.filter((t) => t.tm === 1))];
  return html`<${Frame} height=${height} class="momentum" label=${`Momentum: ${f.home} above the line, ${f.away} below`} margin=${{ top: 30, right: 12, bottom: 30, left: 12 }} onLeave=${() => { setHover(null); tooltip.hide(); }}>
    ${({ iw, ih }) => {
      const sx = scaleLinear([-0.5, end + gap + 0.5], [0, iw]);
      const mid = ih / 2, gutter = 9, reach = mid - gutter - 2;   // the clock runs through a gutter between the two sides
      const bw = Math.max(1.5, sx(1) - sx(0) - 1.2);
      const barH = (v) => (v / mo.max) * reach;
      return html`<g>
        <text class="mo-team" x="0" y="-16">${f.home}</text>
        <text class="mo-team" x="0" y=${ih + 24}>${f.away}</text>
        ${ticks.map((t) => html`<g key=${t.at} transform=${`translate(${sx(pos(t.at, t.at >= from2 && hasSecond ? 2 : 1))},0)`}><line class="grid-line" y1="0" y2=${mid - gutter} /><line class="grid-line" y1=${mid + gutter} y2=${ih} /><text class="tick-label" y=${mid + 3.5} text-anchor="middle">${t.label}</text></g>`)}
        ${hasSecond ? html`<g transform=${`translate(${sx(ht + 0.5 + gap / 2)},0)`}><line class="ref-line" y1="-6" y2=${mid - gutter} /><line class="ref-line" y1=${mid + gutter} y2=${ih + 6} /><text class="tick-label strong" y=${mid + 3.5} text-anchor="middle">HT</text></g>` : null}
        ${mo.minutes.map((m) => {
          const pe = hasSecond && m >= from2 ? 2 : 1;
          const x = sx(pos(m, pe)) - bw / 2;
          const lead = mo.net[m];
          return html`<g key=${m} class=${hover === m ? "mo-min on" : "mo-min"}>
            ${mo.home[m] > 0 ? html`<rect x=${x} y=${mid - gutter - barH(mo.home[m])} width=${bw} height=${barH(mo.home[m])} rx=${Math.min(2, bw / 2)} style=${{ fill: SIDE_COLOR[0], opacity: lead >= 0 ? 1 : 0.38 }} />` : null}
            ${mo.away[m] > 0 ? html`<rect x=${x} y=${mid + gutter} width=${bw} height=${barH(mo.away[m])} rx=${Math.min(2, bw / 2)} style=${{ fill: SIDE_COLOR[1], opacity: lead <= 0 ? 1 : 0.38 }} />` : null}
          </g>`;
        })}
        ${marks.map((t, i) => {
          const y = t.tm === 0 ? -8 - t.depth * 15 : ih + 8 + t.depth * 15;
          return html`<g key=${i} class="mo-ev" transform=${`translate(${sx(pos(t.em, t.pe))},${Math.max(-24, Math.min(ih + 24, y))})`}
            onMouseMove=${(e) => tooltip.move(e, eventTip(c, f, t))} onMouseLeave=${tooltip.hide}>
            ${t.kind === "goal" || t.kind === "penalty" || t.kind === "own_goal" ? html`<line class="mo-goal-line" y1=${t.tm === 0 ? 8 : -8} y2=${t.tm === 0 ? mid + 8 + t.depth * 15 : -(ih - mid) - 8 - t.depth * 15} style=${{ stroke: SIDE_COLOR[t.tm] }} />` : null}
            <${EventGlyph} kind=${t.kind} color=${SIDE_COLOR[t.tm]} size=${t.kind === "sub" ? 5 : 6.5} />
          </g>`;
        })}
        ${hover != null ? html`<line class="crosshair" pointer-events="none" x1=${sx(pos(hover, hasSecond && hover >= from2 ? 2 : 1))} x2=${sx(pos(hover, hasSecond && hover >= from2 ? 2 : 1))} y1="0" y2=${ih} />` : null}
        <rect class="hit" x="0" y="0" width=${iw} height=${ih} onMouseMove=${(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          let m = sx.invert(e.clientX - rect.left);
          if (hasSecond && m > ht + 0.5) m = Math.max(from2, m - gap);
          m = Math.max(0, Math.min(end, Math.round(m)));
          const pe = hasSecond && m >= from2 ? 2 : 1;
          const mi = pe === 2 ? 45 + (m - from2) : m;
          const here = events.filter((t) => t.em === m);
          setHover(m);
          tooltip.move(e, html`<div><div class="tt-title">${minuteLabel(pe, mi)}</div>
            <div class="tt-row"><span class="k"><i class="key" style=${{ background: SIDE_COLOR[0] }}></i>${f.home}</span><span class="v">${nf(mo.home[m], 1)}</span></div>
            <div class="tt-row"><span class="k"><i class="key" style=${{ background: SIDE_COLOR[1] }}></i>${f.away}</span><span class="v">${nf(mo.away[m], 1)}</span></div>
            ${here.map((t, i) => html`<div class="tt-sub" key=${i}>${KIND_WORD[t.kind]}: ${t.p ? c.names?.[t.p] : "team official"}</div>`)}
            <div class="tt-sub">Final-third touches a minute, over five minutes</div></div>`);
        }} />
      </g>`;
    }}
  </${Frame}>`;
}

/** Where on-target shots (and near misses) went in the goal, as the shooter saw it. Size is chance quality when xG is known. */
export function GoalMouth({ shots, names, color = "var(--c1)", label }) {
  // Opta's goal mouth: posts at 45.2 and 54.8 across (the left post, as the shooter sees it, is the higher number), crossbar at 38 up
  const GW = 7.32, GH = 2.44, PAD_X = 1.5, PAD_T = 1.1;
  const placed = (shots || []).filter((s) => s.gy != null && s.gz != null && s.result !== "BlockedShot").map((s) => ({
    ...s, sx: ((548 - s.gy) / 96) * GW, sy: GH - (s.gz / 380) * GH,
  })).filter((s) => s.sx > -PAD_X && s.sx < GW + PAD_X && s.sy > -PAD_T);
  const r = (s) => (s.xg == null ? 0.16 : 0.1 + Math.sqrt(s.xg) * 0.26);
  const word = { Goal: "Goal", SavedShot: "Saved", ShotOnPost: "Hit the post", MissedShots: "Off target" };
  return html`<svg class="goalmouth" viewBox=${`${-PAD_X} ${-PAD_T} ${GW + 2 * PAD_X} ${GH + PAD_T + 0.5}`} role="img" aria-label=${label}>
    <rect class="gm-turf" x=${-PAD_X} y=${GH} width=${GW + 2 * PAD_X} height="0.5" />
    <g class="gm-net">${[1, 2, 3, 4, 5].map((i) => html`<line key=${"v" + i} x1=${(GW * i) / 6} x2=${(GW * i) / 6} y1="0" y2=${GH} />`)}${[1, 2].map((i) => html`<line key=${"h" + i} x1="0" x2=${GW} y1=${(GH * i) / 3} y2=${(GH * i) / 3} />`)}</g>
    <path class="gm-frame" d=${`M0 ${GH}V0H${GW}V${GH}`} />
    ${[...placed].sort((a, b) => (a.result === "Goal") - (b.result === "Goal")).map((s, i) => html`<circle key=${i} cx=${s.sx} cy=${Math.min(GH - 0.02, s.sy)} r=${r(s)}
      class=${"gm-shot " + (s.result === "Goal" ? "goal" : s.result === "SavedShot" ? "saved" : "off")} style=${{ "--col": color }}
      onMouseMove=${(e) => tooltip.move(e, html`<div><div class="tt-title">${word[s.result] || s.result}${s.xg != null ? ` · ${nf(s.xg, 2)} xG` : ""}</div><div class="tt-sub">${names?.[s.p] || ""} · ${minuteLabel(s.pe, s.mi)}</div></div>`)} onMouseLeave=${tooltip.hide} />`)}
  </svg>`;
}

/** Which side a team attacked down: its final-third touches split left, centre and right, drawn on the final third it attacked. */
export function Channels({ shares, counts, color = "var(--c1)", label }) {
  const lanes = ["Left", "Centre", "Right"];
  const top = Math.max(1, ...shares);
  return html`<svg class="channels" viewBox="0 0 120 68" role="img" aria-label=${label}>
    <g class="pitch"><rect class="turf" x="0" y="0" width="120" height="68" rx="1" />
      <rect class="mark" x="0.5" y="0.5" width="119" height="67" /><rect class="mark" x="88" y="13.84" width="31.5" height="40.32" /><rect class="mark" x="109" y="24.84" width="10.5" height="18.32" /></g>
    ${shares.map((v, i) => {
      const y = 68 / 6 + (i * 68) / 3, len = 22 + 58 * (v / top), wd = 4 + 12 * (v / top);
      return html`<g key=${i} onMouseMove=${(e) => tooltip.move(e, html`<div><div class="tt-title">${lanes[i]}: ${nf(v, 0)}%</div><div class="tt-sub">${counts[i]} final-third touches</div></div>`)} onMouseLeave=${tooltip.hide}>
        <path d=${`M6 ${y - wd / 2}H${6 + len - wd * 0.7}V${y - wd * 0.95}L${6 + len + wd * 0.5} ${y}L${6 + len - wd * 0.7} ${y + wd * 0.95}V${y + wd / 2}H6Z`} style=${{ fill: color, fillOpacity: 0.35 + 0.6 * (v / top) }} />
        <text class="ch-val" x="12" y=${y} dy="0.35em">${nf(v, 0)}%</text>
        <text class="ch-lane" x="116" y=${y} dy="0.35em" text-anchor="end">${lanes[i]}</text>
      </g>`;
    })}
  </svg>`;
}

/** Both line-ups on one pitch as they set out: the home side on the left attacking right, the away side on the right. */
export function FormationPitch({ c, f, hrefOf }) {
  const happened = (pid) => {
    const mine = (c.timeline || []).filter((t) => t.p === pid);
    return { goals: mine.filter((t) => t.kind === "goal" || t.kind === "penalty").length, yellow: mine.some((t) => t.kind === "yellow"), red: mine.some((t) => t.kind === "red"),
      off: (c.timeline || []).find((t) => t.kind === "sub" && t.other === pid) };
  };
  // the lines of a shape (keeper, defence, midfield ...) are spread evenly over the half, however close WhoScored's own grid puts them
  const lines = (team) => [...new Set(team.players.filter((p) => p.start && p.slot).map((p) => p.slot[1]))].sort((a, b) => a - b);
  const draw = (team, tm) => team.players.filter((p) => p.start && p.slot).map((p) => {
    const rows = lines(team), at = rows.indexOf(p.slot[1]);
    const depth = 5 + (rows.length > 1 ? at / (rows.length - 1) : 0) * 40, across = p.slot[0] / 10;
    const x = tm === 0 ? depth : L - depth, y = (tm === 0 ? 1 - across : across) * (W - 12) + 5;
    const h = happened(p.id);
    const link = hrefOf?.(p.id);
    const body = html`<g class="fp-player" transform=${`translate(${x},${y})`} onMouseMove=${(e) => tooltip.move(e, html`<div><div class="tt-title">${p.shirt ?? ""} ${p.name}</div>
        <div class="tt-sub">${p.pos}${p.rating ? ` · WhoScored rating ${nf(p.rating, 1)}` : ""}</div>
        ${h.goals ? html`<div class="tt-row"><span class="k">Goals</span><span class="v">${h.goals}</span></div>` : null}
        ${h.off ? html`<div class="tt-row"><span class="k">Off</span><span class="v">${minuteLabel(h.off.pe, h.off.mi)} for ${c.names?.[h.off.p] || ""}</span></div>` : null}</div>`)} onMouseLeave=${tooltip.hide}>
      <circle r="2.8" style=${{ fill: SIDE_COLOR[tm] }} class="fp-dot" />
      <text class="fp-num" dy="0.36em" text-anchor="middle">${p.shirt ?? ""}</text>
      <text class="fp-name" y="5.6" text-anchor="middle">${surname(p.name)}</text>
      ${h.goals ? html`<g transform="translate(3,-2.6)"><circle r="1.25" class="fp-ball" />${h.goals > 1 ? html`<text class="fp-count" x="1.9" dy="0.35em">${h.goals}</text>` : null}</g>` : null}
      ${h.red || h.yellow ? html`<rect class=${"ev-card " + (h.red ? "red" : "yellow")} x="-4.2" y="-4" width="1.5" height="2.1" rx="0.25" />` : null}
      ${h.off ? html`<path class="fp-off" d="M-4.4 1.2l1 1.3l1-1.3" />` : null}
    </g>`;
    return link ? html`<a key=${p.id} href=${link}>${body}</a>` : html`<g key=${p.id}>${body}</g>`;
  });
  return html`<figure class="pitchmap formation">
    <svg viewBox="-3 -3 111 74" role="img" aria-label=${`Line-ups: ${f.home} ${c.teams[0].formation || ""}, ${f.away} ${c.teams[1].formation || ""}`}>
      <g class="pitch"><rect class="turf" x="0" y="0" width=${L} height=${W} rx="0.6" /><${Stripes} /><${PitchMarks} /></g>
      ${draw(c.teams[0], 0)}${draw(c.teams[1], 1)}
    </svg>
  </figure>`;
}

/** Possession and field tilt in each quarter-hour: one split bar per block, home from the left. */
export function BlockBars({ rows, measure, f }) {
  return html`<div class="blockbars" role="img" aria-label=${`${measure === "tilt" ? "Field tilt" : "Possession"} by period`}>
    ${rows.map((b) => {
      const v = b[measure];
      return html`<div class="bb-row" key=${b.label}>
        <span class="bb-label num">${b.label}′</span>
        ${v == null ? html`<span class="bb-track empty"></span>` : html`<span class="bb-track" onMouseMove=${(e) => tooltip.move(e, html`<div><div class="tt-title">${b.label}′</div>
            <div class="tt-row"><span class="k"><i class="key" style=${{ background: SIDE_COLOR[0] }}></i>${f.home}</span><span class="v">${nf(v, 0)}%</span></div>
            <div class="tt-row"><span class="k"><i class="key" style=${{ background: SIDE_COLOR[1] }}></i>${f.away}</span><span class="v">${nf(100 - v, 0)}%</span></div>
            <div class="tt-sub">Shots ${b.shots[0]} – ${b.shots[1]}</div></div>`)} onMouseLeave=${tooltip.hide}>
          <i class="h" style=${{ width: v + "%" }}><b>${nf(v, 0)}</b></i><i class="a" style=${{ width: 100 - v + "%" }}><b>${nf(100 - v, 0)}</b></i><u></u>
        </span>`}
      </div>`;
    })}
  </div>`;
}

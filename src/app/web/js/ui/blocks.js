// Domain blocks shared by several pages: an upcoming fixture with its context, a mover, a signed gap.
import { html } from "../lib/html.js";
import { ordinal, signed } from "../lib/format.js";
import { Icon } from "../lib/icons.js";
import { Crest, teamHref, Delta } from "./common.js";
import { FormCell } from "./cells.js";
import { kickoff } from "./matchcard.js";

/** An upcoming match: when (in the viewer's time zone), who, and what each side looks like going in (league position, form, chance difference). */
export function FixtureRow({ f }) {
  const k = kickoff(f);
  const side = (name, short, rank, form, xgd) => html`<div class="fx-side">
    <${Crest} team=${name} short=${short} size=${26} />
    <div class="stack" style=${{ "--gap": "2px", minWidth: 0 }}>
      <a class="fx-name" href=${teamHref(name)}>${name}</a>
      <span class="fx-ctx xsmall muted">${rank ? ordinal(rank) : ""}${xgd != null ? ` · xGD ${signed(xgd, 2)}/g` : ""}</span>
    </div>
    ${form && form.length ? html`<${FormCell} items=${form} />` : null}
  </div>`;
  return html`<div class="fixture-row">
    <div class="fx-when"><b class="num">${k.time}</b><span class="muted xsmall">${k.day}${f.round ? ` · MW${f.round}` : ""}</span></div>
    <div class="fx-teams">
      ${side(f.home, f.home_short, f.home_rank, f.home_form, f.home_xgd)}
      ${side(f.away, f.away_short, f.away_rank, f.away_form, f.away_xgd)}
    </div>
  </div>`;
}

export function MoverRow({ m, up }) {
  return html`<div class="mover"><${Icon} name=${up ? "trendUp" : "trendDown"} size="sm" class=${up ? "up" : "down"} />
    <a class="cell-team" href=${teamHref(m.team)}><${Crest} team=${m.team} short=${m.short} size=${20} />${m.team}</a>
    <span class="muted num">${m.from}<i>→</i>${m.to}</span></div>`;
}

/** A signed gap with a small bar: blue above expectation, orange below. */
export function GapCell({ value, max = 12, digits = 1 }) {
  if (value == null || !Number.isFinite(value)) return html`<span class="muted">–</span>`;
  const w = Math.min(50, (Math.abs(value) / max) * 50);
  return html`<span class="gap-bar">
    <span class="gap-track" aria-hidden="true"><i class="axis"></i><i class=${"fill " + (value >= 0 ? "pos" : "neg")} style=${value >= 0 ? { left: "50%", width: w + "%" } : { right: "50%", width: w + "%" }}></i></span>
    <span class="val"><${Delta} value=${value} digits=${digits} /></span>
  </span>`;
}

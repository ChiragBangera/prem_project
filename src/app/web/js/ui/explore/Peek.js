// One row beside the list: who it is, how it ranks on what matters, and where to go next. Opening it never leaves the list.
import { html } from "../../lib/html.js";
import { Icon } from "../../lib/icons.js";
import { cls, formation, ordinal } from "../../lib/format.js";
import { blank, fmtMetric } from "../../lib/metricfmt.js";
import { Button, Crest, FavouriteButton, Form, Star, playerHref, teamHref } from "../common.js";

const KEYS = {
  ATT: ["npxg90", "shots90", "xgps", "xa90", "kp90", "takeonswon90", "touchbox90", "progact_shot_pct"],
  MID: ["xa90", "kp90", "prog_passes90", "pass_acc", "progact90", "progact_shot_pct", "tklint90", "recoveries90"],
  DEF: ["tklint90", "def_duel_win", "aerial_win", "clearances90", "recoveries90", "prog_passes90", "pass_acc", "carryprog90"],
  GK: ["save_pct", "saves90", "ga90", "cs_pct", "claims90", "sweeper90", "pass_acc", "long_acc"],
};
const TEAM_KEYS = { quality: ["ppg", "xgd_pg", "xg_pg", "xga_pg", "g_xg_pg"], style: ["poss", "tilt", "ppda", "def_height", "direct_pg"] };

/** A measure with its value and a bar for its rank; grey when the measure describes style rather than quality. */
function RankBar({ ctx, row, k, peers }) {
  const i = ctx.idx[k], def = ctx.metrics[k], p = row.p[i], style = def.hib === null;
  return html`<div class=${cls("dk-pbar", style && "style")} title=${p != null ? `${style ? "Higher than" : "Better than"} ${Math.round(p)}% of ${peers}` : "Not ranked: too small a sample"}><span>${def.label}</span><b>${fmtMetric(def, row.v[i])}</b>
    <div class="track"><i style=${{ width: (p ?? 0) + "%" }}></i><u></u></div></div>`;
}

const has = (ctx, row, k) => ctx.idx[k] !== undefined && ctx.metrics[k] && !blank(row.v[ctx.idx[k]]);

/**
 * A player. `note` replaces the line under the bars (a match says what its bars rank); `facts` adds to the figures at the top;
 * leave out `onPick` where there is nothing to compare with.
 */
export function Peek({ row, ctx, season, picked, onPick, onClose, note, facts = [] }) {
  const position = ctx.positions?.labels?.[row.pos2] || ctx.roles?.labels?.[row.group];
  const peers = ctx.roles?.plural?.[row.group]?.toLowerCase() || "players";
  const at = (k) => ctx.idx[k];
  const minutes = at("minutes") !== undefined ? row.v[at("minutes")] : null;
  const score = at("output") !== undefined ? row.v[at("output")] : null;
  const bars = (KEYS[row.group] || []).filter((k) => has(ctx, row, k));
  const age = row.age != null && row.dob_basis !== "name" ? row.age : null;
  const href = playerHref(row.id, { league: row.league, season: row.seasons?.length === 1 ? row.seasons[0] : season });
  return html`<aside class="dk-peek" aria-label=${`${row.name}, at a glance`}>
    <div class="dk-peek-head"><div><h2>${row.name}</h2><p>${[row.team, position, age != null ? `${age} years old` : null].filter(Boolean).join(", ")}</p></div>
      <button type="button" class="dk-x" aria-label="Close" onClick=${onClose}><${Icon} name="x" /></button></div>
    <div class="dk-peek-facts">
      ${minutes != null ? html`<span><b>${Math.round(minutes).toLocaleString("en-GB")}</b>minutes</span>` : null}
      ${!blank(score) ? html`<span><b>${Math.round(score)}</b>role score</span>` : null}
      ${facts.map((f) => html`<span key=${f.label}><b>${f.value}</b>${f.label}</span>`)}
      ${row.in_pool === false ? html`<span class="warn">Small sample</span>` : null}
    </div>
    ${row.tags?.length ? html`<div class="dk-peek-tags">${row.tags.map((t) => html`<span key=${t.key} class="tag" title=${t.why}>${t.label}</span>`)}</div>` : null}
    ${bars.length ? html`<div class="dk-pbars">${bars.map((k) => html`<${RankBar} key=${k} ctx=${ctx} row=${row} k=${k} peers=${peers} />`)}</div>
    <p class="dk-note">${note || `Each bar ranks him among ${peers}; the tick is the middle of the role.`}</p>` : html`<p class="dk-note">No ranked measures for him in this selection yet.</p>`}
    <div class="dk-peek-acts">
      ${href ? html`<a class="btn primary" href=${href}>Open full profile</a>` : html`<p class="dk-note">WhoScored lists him but Understat does not, so he has no profile here.</p>`}
      ${onPick ? html`<${Button} onClick=${() => onPick(row.id, !picked)}>${picked ? "Remove from compare" : "Add to compare"}</${Button}>` : null}
      ${row.id > 0 ? html`<span class="dk-peek-star"><${Star} player=${row} /><span>Shortlist</span></span>` : null}
    </div>
  </aside>`;
}

/** A team: where it stands, its form, and how it ranks in its league on results, chances and style. */
export function TeamPeek({ row, ctx, leagueName, pool, onClose }) {
  const n = pool || null;
  const peers = `the ${n ? `${n} ` : ""}teams in its league`;
  const quality = TEAM_KEYS.quality.filter((k) => has(ctx, row, k));
  const style = TEAM_KEYS.style.filter((k) => has(ctx, row, k));
  const v = (k) => (ctx.idx[k] !== undefined ? row.v[ctx.idx[k]] : null);
  const season = row.season ? `${row.season}/${String(row.season + 1).slice(-2)}` : "";
  return html`<aside class="dk-peek" aria-label=${`${row.team}, at a glance`}>
    <div class="dk-peek-head"><div class="dk-peek-team"><${Crest} team=${row.team} short=${row.short} size=${36} /><div><h2>${row.team}</h2>
      <p>${[row.rank ? `${ordinal(row.rank)} in the ${leagueName || row.league}` : leagueName || row.league, season].filter(Boolean).join(", ")}</p></div></div>
      <button type="button" class="dk-x" aria-label="Close" onClick=${onClose}><${Icon} name="x" /></button></div>
    <div class="dk-peek-facts">
      ${!blank(v("pts")) ? html`<span><b>${v("pts")}</b>points</span>` : null}
      ${!blank(v("xpts")) ? html`<span><b>${fmtMetric(ctx.metrics.xpts, v("xpts"))}</b>expected</span>` : null}
      ${!blank(v("played")) ? html`<span><b>${v("played")}</b>played</span>` : null}
    </div>
    ${row.form?.length ? html`<div class="dk-peek-form"><span>Last five, oldest first</span><${Form} items=${row.form} /></div>` : null}
    ${[formation(row.formation) && `Usually ${formation(row.formation)}`, row.manager && `Manager ${row.manager}`].filter(Boolean).length
      ? html`<p class="dk-peek-line">${[formation(row.formation) && `Usually ${formation(row.formation)}`, row.manager && `Manager ${row.manager}`].filter(Boolean).join(" · ")}</p>` : null}
    ${quality.length ? html`<div class="dk-pbars"><p class="dk-label">Results and chances</p>${quality.map((k) => html`<${RankBar} key=${k} ctx=${ctx} row=${row} k=${k} peers=${peers} />`)}</div>` : null}
    ${style.length ? html`<div class="dk-pbars"><p class="dk-label">How they play</p>${style.map((k) => html`<${RankBar} key=${k} ctx=${ctx} row=${row} k=${k} peers=${peers} />`)}</div>` : null}
    <p class="dk-note">Each bar ranks them among ${peers}; the tick is the middle. Grey bars describe style, where neither end is better.</p>
    <div class="dk-peek-acts">
      <a class="btn primary" href=${teamHref(row.team, { league: row.league, season: row.season })}>Open team page</a>
      <${FavouriteButton} league=${row.league} team=${row.team} />
    </div>
  </aside>`;
}

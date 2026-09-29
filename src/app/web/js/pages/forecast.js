// Forecast: upcoming fixtures, a match lab for any pairing, the season simulation, and how accurate it has been.
import { html, useMemo } from "../lib/html.js";
import { useApi } from "../lib/api.js";
import { useScope } from "../lib/scope.js";
import { href, navigate, setQuery, useLocation } from "../lib/router.js";
import { dateShort, nf, ordinal, pct, plural, probText, signed, timeOf, weekday, cls } from "../lib/format.js";
import { Async, Badge, Button, Card, Crest, DataNotices, EmptyState, Field, Notice, PageHead, Select, Stat, Tabs, TeamName, useDocumentTitle, teamHref } from "../ui/common.js";
import { DataTable } from "../ui/table.js";
import { ProbBar, BarList } from "../charts/bars.js";
import { PositionStrip, Reliability, ScorelineMatrix } from "../charts/heat.js";
import { labHref } from "../ui/blocks.js";

// ------------------------------------------------------------------ fixtures

function ModelNote({ model }) {
  return html`<${Card} title="How these numbers are made">
    <div class="stack small" style=${{ "--gap": "8px" }}>
      <p>A blend of two models: <b>${Math.round(model.weights.ratings * 100)}%</b> team ratings fitted on expected goals (attack and defence strengths, recent games weighted more) and <b>${Math.round(model.weights.elo * 100)}%</b> Elo.</p>
      <p>Scorelines use a Poisson model with a small correction for low scores (rho ${nf(model.rho, 3)}), fitted on ${model.matches} matches.
        Home advantage is worth about ${pct(model.home_advantage)} more goals.${model.used_previous_season ? " Early in the season the previous season is blended in as a prior." : ""}</p>
      <p class="muted">Bookmaker odds are not used. Understat's own numbers are shown for comparison only.</p>
    </div>
  </${Card}>`;
}

function Fixtures({ scope }) {
  const q = useApi("/api/forecast/fixtures", { league: scope.league, season: scope.season, limit: 20 });
  return html`<${Async} q=${q}>${(d) => {
    const cols = [
      { key: "dt", label: "Kickoff", firstDir: "asc", render: (r) => html`<span class="stack" style=${{ "--gap": "0" }}><b>${weekday(r.date)} ${dateShort(r.date)}</b><span class="muted xsmall">${timeOf(r.dt)} · MW${r.round}</span></span>` },
      { key: "home", label: "Match", firstDir: "asc", render: (r) => html`<span class="stack" style=${{ "--gap": "3px" }}><${TeamName} team=${r.home} short=${r.home_short} link=${false} size=${20} /><${TeamName} team=${r.away} short=${r.away_short} link=${false} size=${20} /></span>` },
      { key: "p_home", label: "Result probabilities", sortable: false, render: (r) => html`<div style=${{ width: "230px" }}><${ProbBar} home=${r.p_home} draw=${r.p_draw} away=${r.p_away} homeLabel=${r.home_short} awayLabel=${r.away_short} compact /></div>` },
      { key: "exp_home", label: "Expected goals", num: true, value: (r) => r.exp_home + r.exp_away, render: (r) => `${nf(r.exp_home, 1)} – ${nf(r.exp_away, 1)}` },
      { key: "most_likely", label: "Likeliest score", num: true, sortable: false, render: (r) => `${r.most_likely[0]}–${r.most_likely[1]}` },
      { key: "over25", label: "Over 2.5", num: true, render: (r) => probText(r.over25) },
      { key: "btts", label: "Both score", num: true, render: (r) => probText(r.btts) },
      { key: "understat", label: "Understat", num: true, sortable: false, title: "Understat's own home / draw / away, for comparison.", render: (r) => (r.understat ? html`<span class="muted xsmall">${Math.round(r.understat.home * 100)} / ${Math.round(r.understat.draw * 100)} / ${Math.round(r.understat.away * 100)}</span>` : html`<span class="muted">–</span>`) },
    ];
    const gaps = d.fixtures.filter((f) => f.understat).map((f) => {
      const diffs = [["home", f.p_home - f.understat.home, f.home], ["draw", f.p_draw - f.understat.draw, "a draw"], ["away", f.p_away - f.understat.away, f.away]];
      const top = diffs.sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))[0];
      return { f, side: top[0], diff: top[1], who: top[2] };
    }).filter((g) => Math.abs(g.diff) >= 0.06).sort((a, b) => Math.abs(b.diff) - Math.abs(a.diff)).slice(0, 4);
    return html`<div class="stack">
      <${DataNotices} scope=${d.scope} meta=${d.meta} />
      ${d.fixtures.some((f) => f.low_evidence) ? html`<${Notice} tone="warn" icon="alert">Some teams have played few games this season, so their forecasts lean on last season's ratings and carry more uncertainty.</${Notice}>` : null}
      <${Card} flush title="Next fixtures" sub="Click a fixture to open it in the match lab.">
        <${DataTable} columns=${cols} rows=${d.fixtures} rowKey=${(r) => r.id} initialSort=${{ key: "dt", dir: "asc" }} dense onRowClick=${(r) => navigate("/forecast", { tab: "lab", home: r.home, away: r.away })} caption="Fixture forecasts" />
      </${Card}>
      <div class="grid cols-2 top">
        ${gaps.length ? html`<${Card} title="Where the model disagrees with Understat" sub="Gaps of six points or more on one outcome.">
          <div class="stack" style=${{ "--gap": "10px" }}>${gaps.map((g) => html`<a class="row between gap-row" key=${g.f.id} href=${labHref(g.f.home, g.f.away)}>
            <span><b>${g.f.home}</b> v <b>${g.f.away}</b><br /><span class="muted small">${g.diff > 0 ? "Model is higher" : "Model is lower"} on ${g.who}</span></span>
            <span class=${"delta-val " + (g.diff > 0 ? "pos" : "neg")}>${signed(g.diff * 100, 0)} pts</span></a>`)}</div>
        </${Card}>` : null}
        <${ModelNote} model=${d.model} />
      </div>
    </div>`;
  }}</${Async}>`;
}

// ------------------------------------------------------------------ match lab

function Lab({ scope, query }) {
  const league = useApi("/api/league", { league: scope.league, season: scope.season });
  const fixtures = useApi("/api/forecast/fixtures", { league: scope.league, season: scope.season, limit: 8 });
  const names = league.data?.table?.map((t) => t.team).sort() || [];
  const home = query.home || "", away = query.away || "";
  const ready = Boolean(home && away && home !== away);
  const q = useApi("/api/forecast/match", { home, away, league: scope.league, season: scope.season }, { enabled: ready });
  const opts = [{ value: "", label: "Choose a team" }, ...names.map((n) => ({ value: n, label: n }))];
  return html`<div class="stack">
    <${Card} title="Pick any two teams" sub="The model plays a match that may not be scheduled: home advantage goes to the first team.">
      <div class="row wrap" style=${{ gap: "12px", alignItems: "end" }}>
        <${Field} label="Home"><${Select} value=${home} options=${opts} label="Home team" onChange=${(v) => setQuery({ home: v || null })} /></${Field}>
        <button type="button" class="btn quiet icon-only" title="Swap home and away" aria-label="Swap home and away" onClick=${() => setQuery({ home: away || null, away: home || null })}>⇄</button>
        <${Field} label="Away"><${Select} value=${away} options=${opts} label="Away team" onChange=${(v) => setQuery({ away: v || null })} /></${Field}>
      </div>
      ${fixtures.data?.fixtures?.length ? html`<div class="row wrap" style=${{ gap: "6px", marginTop: "14px" }}><span class="xsmall muted">Or start from a real fixture:</span>${fixtures.data.fixtures.slice(0, 6).map((f) => html`<button type="button" class="chip" key=${f.id} onClick=${() => setQuery({ home: f.home, away: f.away })}>${f.home_short} v ${f.away_short}</button>`)}</div>` : null}
    </${Card}>
    ${!ready ? html`<${EmptyState} icon="forecast" title=${home && home === away ? "Pick two different teams" : "Pick a home and an away team"} text="You get result probabilities, the likeliest scorelines, goal markets and how the two models see it." />`
      : html`<${Async} q=${q}>${(d) => html`<${LabResult} d=${d} />`}</${Async}>`}
  </div>`;
}

function LabResult({ d }) {
  const f = d.forecast;
  const rows = [["Ratings model", f.models.ratings], ["Elo", f.models.elo], ...(f.understat ? [["Understat", f.understat]] : [])];
  return html`<div class="stack">
    <${DataNotices} scope=${d.scope} meta=${d.meta} />
    <div class="grid cols-wide-narrow top">
      <${Card} title=${`${f.home} v ${f.away}`} sub=${`Forecast as of ${f.as_of}`}>
        <div class="stack" style=${{ "--gap": "18px" }}>
          <div class="lab-probs">
            <div><span class="label">${f.home} win</span><b class="figure">${probText(f.p_home)}</b></div>
            <div><span class="label">Draw</span><b class="figure">${probText(f.p_draw)}</b></div>
            <div><span class="label">${f.away} win</span><b class="figure">${probText(f.p_away)}</b></div>
          </div>
          <${ProbBar} home=${f.p_home} draw=${f.p_draw} away=${f.p_away} hideLabels />
          <div class="tiles">
            <${Stat} label="Expected goals" value=${`${nf(f.expected_goals.home, 1)}–${nf(f.expected_goals.away, 1)}`} />
            <${Stat} label="Likeliest score" value=${`${f.most_likely[0]}–${f.most_likely[1]}`} sub=${probText(f.top_scorelines[0].p)} />
            <${Stat} label="Over 2.5 goals" value=${probText(f.markets.over["2.5"])} />
            <${Stat} label="Both score" value=${probText(f.markets.btts)} />
          </div>
        </div>
      </${Card}>
      <${Card} title="Markets">
        <${BarList} max=${1} rows=${[
          { key: "o15", label: "Over 1.5 goals", value: f.markets.over["1.5"], right: probText(f.markets.over["1.5"]) },
          { key: "o25", label: "Over 2.5 goals", value: f.markets.over["2.5"], right: probText(f.markets.over["2.5"]) },
          { key: "o35", label: "Over 3.5 goals", value: f.markets.over["3.5"], right: probText(f.markets.over["3.5"]) },
          { key: "btts", label: "Both teams score", value: f.markets.btts, right: probText(f.markets.btts) },
          { key: "csh", label: `${f.home} clean sheet`, value: f.markets.clean_sheet_home, right: probText(f.markets.clean_sheet_home) },
          { key: "csa", label: `${f.away} clean sheet`, value: f.markets.clean_sheet_away, right: probText(f.markets.clean_sheet_away) },
        ]} />
      </${Card}>
    </div>
    <div class="grid cols-2 top">
      <${Card} title="Scoreline probabilities" sub="Percent chance of each exact score. The ringed cell is the likeliest.">
        <${ScorelineMatrix} matrix=${f.matrix} homeName=${f.home} awayName=${f.away} />
      </${Card}>
      <div class="stack">
        <${Card} title="Most likely scorelines">
          <${BarList} max=${f.top_scorelines[0].p} rows=${f.top_scorelines.map((s, i) => ({ key: i, label: `${f.home_short || f.home} ${s.score[0]}–${s.score[1]} ${f.away_short || f.away}`, value: s.p, right: pct(s.p, 1) }))} />
        </${Card}>
        <${Card} flush title="How the two models see it" sub=${`Blend: ${Math.round(f.models.weights.ratings * 100)}% ratings, ${Math.round(f.models.weights.elo * 100)}% Elo.`}>
          <div class="table-wrap"><table class="data dense"><thead><tr><th>Model</th><th class="num">${f.home}</th><th class="num">Draw</th><th class="num">${f.away}</th></tr></thead><tbody>
            ${rows.map(([name, m]) => html`<tr key=${name}><td>${name}</td><td class="num">${pct(m.home)}</td><td class="num">${pct(m.draw)}</td><td class="num">${pct(m.away)}</td></tr>`)}
            <tr><td><b>Blend</b></td><td class="num"><b>${pct(f.p_home)}</b></td><td class="num"><b>${pct(f.p_draw)}</b></td><td class="num"><b>${pct(f.p_away)}</b></td></tr>
          </tbody></table></div>
          <div class="card-foot">Elo: ${f.home} ${Math.round(f.models.elo_ratings[f.home])}, ${f.away} ${Math.round(f.models.elo_ratings[f.away])}. Ratings rest on about ${Math.round(f.evidence.home)} and ${Math.round(f.evidence.away)} matches of evidence.</div>
        </${Card}>
      </div>
    </div>
  </div>`;
}

// ------------------------------------------------------------------ season

function RangeCell({ p10, p90, exp, lo, hi }) {
  const pos = (v) => ((v - lo) / (hi - lo || 1)) * 100;
  return html`<div class="range-cell" title=${`Middle 80% of simulations: ${p10}–${p90} points`}>
    <i class="rc-line"></i><i class="rc-span" style=${{ left: pos(p10) + "%", width: Math.max(1, pos(p90) - pos(p10)) + "%" }}></i><i class="rc-dot" style=${{ left: pos(exp) + "%" }}></i>
  </div>`;
}

function Season({ scope }) {
  const q = useApi("/api/forecast/season", { league: scope.league, season: scope.season, sims: 4000 });
  return html`<${Async} q=${q}>${(d) => {
    const sim = d.simulation;
    const lo = Math.min(...sim.teams.map((t) => t.points_p10)) - 1, hi = Math.max(...sim.teams.map((t) => t.points_p90)) + 1;
    const cols = [
      { key: "exp_position", label: "Proj.", num: true, firstDir: "asc", width: "56px", render: (r) => html`<span class="rank">${Math.round(r.exp_position)}</span>`, title: "Average finishing position across the simulations." },
      { key: "team", label: "Team", sticky: true, firstDir: "asc", render: (r) => html`<${TeamName} team=${r.team} short=${r.short} />` },
      { key: "points", label: "Pts now", num: true, render: (r) => html`<span>${r.points}</span> <span class="muted xsmall">(${r.played} played)</span>` },
      { key: "exp_points", label: "Projected final points", num: true, render: (r) => html`<span class="row" style=${{ gap: "12px", justifyContent: "flex-end" }}><${RangeCell} p10=${r.points_p10} p90=${r.points_p90} exp=${r.exp_points} lo=${lo} hi=${hi} /><b class="num" style=${{ minWidth: "34px", textAlign: "right" }}>${Math.round(r.exp_points)}</b></span>`, title: "Dot: average. Bar: the middle 80% of simulated seasons." },
      { key: "p_title", label: "Title", num: true, render: (r) => probText(r.p_title) },
      { key: "p_top4", label: `Top ${sim.ucl_places}`, num: true, render: (r) => probText(r.p_top4) },
      { key: "p_relegation", label: "Relegation", num: true, render: (r) => probText(r.p_relegation) },
      { key: "distribution", label: "Finishing position, 1st to 20th", sortable: false, render: (r) => html`<${PositionStrip} dist=${r.distribution} team=${r.team} />`, title: "Each cell is one finishing position; darker means likelier." },
    ];
    return html`<div class="stack">
      <${DataNotices} scope=${d.scope} meta=${d.meta} />
      <${Card} flush title="How the season could end" sub=${`${sim.n_sims.toLocaleString("en-GB")} simulated seasons, playing out the ${plural(sim.remaining_fixtures, "match", "matches")} still to come from each team's rating.`}>
        <${DataTable} columns=${cols} rows=${sim.teams} rowKey=${(r) => r.team} initialSort=${{ key: "exp_position", dir: "asc" }} dense caption="Season simulation"
          zone=${(r) => (r.exp_position <= sim.ucl_places + 0.5 ? "ucl" : r.exp_position > sim.teams.length - sim.relegation_places - 0.5 ? "rel" : "none")} />
        <div class="card-foot">A simulation is a range of outcomes, not a prediction. A team on 90% is still beaten one time in ten.</div>
      </${Card}>
    </div>`;
  }}</${Async}>`;
}

// ------------------------------------------------------------------ accuracy

const MODEL_NAME = { ensemble: "Blend (used here)", ratings: "Ratings model", elo: "Elo", understat: "Understat", baseline: "Baseline: league averages" };

function Accuracy({ scope }) {
  const q = useApi("/api/forecast/calibration", { league: scope.league, season: scope.season });
  return html`<${Async} q=${q}>${(d) => {
    const c = d.calibration;
    const order = ["ensemble", "ratings", "elo", "understat", "baseline"].filter((k) => c.models[k]);
    const rows = order.map((k) => ({ key: k, name: MODEL_NAME[k], ...c.models[k] }));
    const best = (metric, dir) => Math.min(...rows.map((r) => dir * r[metric])) * dir;
    const cell = (metric, digits, dir = 1) => (r) => html`<span class=${r[metric] === best(metric, dir) ? "best-val" : ""}>${nf(r[metric], digits)}</span>`;
    const cols = [
      { key: "name", label: "Model", sortable: false, className: "strong" },
      { key: "n", label: "Matches", num: true, sortable: false },
      { key: "rps", label: "RPS", num: true, sortable: false, render: cell("rps", 3), title: "Ranked probability score: how far the forecast was from what happened, respecting the order home > draw > away. Lower is better." },
      { key: "brier", label: "Brier", num: true, sortable: false, render: cell("brier", 3), title: "Average squared error of the three probabilities. Lower is better." },
      { key: "log_loss", label: "Log loss", num: true, sortable: false, render: cell("log_loss", 3), title: "Punishes confident wrong forecasts hardest. Lower is better." },
      { key: "accuracy", label: "Top pick hit", num: true, sortable: false, render: (r) => html`<span class=${r.accuracy === Math.max(...rows.map((x) => x.accuracy)) ? "best-val" : ""}>${pct(r.accuracy)}</span>`, title: "How often the most likely outcome happened." },
    ];
    return html`<div class="stack">
      <${DataNotices} scope=${d.scope} meta=${d.meta} />
      <div class="tiles">
        <${Stat} label="Matches scored" value=${c.n_scored} sub="each predicted from earlier games only" />
        <${Stat} label="Better than the baseline" value=${pct(c.skill_vs_baseline)} sub="on ranked probability score" tone=${c.skill_vs_baseline > 0 ? "up" : "down"} title="How much lower the blend's RPS is than always forecasting the league's average home/draw/away split." />
        <${Stat} label="Method" value="Walk-forward" sub=${`refit every ${c.block} matches`} />
      </div>
      <div class="grid cols-wide-narrow top">
        <${Card} flush title="Models compared" sub="Lower is better on the first three; best in each column is bold.">
          <${DataTable} columns=${cols} rows=${rows} rowKey=${(r) => r.key} dense caption="Forecast accuracy" />
          <div class="card-foot">Every match is predicted using only the games played before it, so this is an honest test, not a fit to the past.</div>
        </${Card}>
        <${Card} title="Do the percentages mean what they say?" sub="Forecasts grouped by the probability given. Dot size: how many forecasts. On the line means well calibrated.">
          <${Reliability} bins=${c.reliability} />
        </${Card}>
      </div>
    </div>`;
  }}</${Async}>`;
}

export default function Forecast() {
  const scope = useScope();
  const { query } = useLocation();
  const tab = ["lab", "season", "accuracy"].includes(query.tab) ? query.tab : "fixtures";
  useDocumentTitle("Forecast");
  const tabs = [{ value: "fixtures", label: "Fixtures" }, { value: "lab", label: "Match lab" }, { value: "season", label: "Season" }, { value: "accuracy", label: "Accuracy" }];
  return html`<div class="stack" style=${{ "--gap": "24px" }}>
    <${PageHead} eyebrow="Forecast" title="What happens next" sub="Probabilities from the chances each team creates and allows, not from the table or the bookmakers." />
    <${Tabs} tabs=${tabs} value=${tab} onChange=${(v) => setQuery({ tab: v === "fixtures" ? null : v, home: null, away: null })} label="Forecast sections" />
    ${tab === "fixtures" ? html`<${Fixtures} scope=${scope} />` : null}
    ${tab === "lab" ? html`<${Lab} scope=${scope} query=${query} />` : null}
    ${tab === "season" ? html`<${Season} scope=${scope} />` : null}
    ${tab === "accuracy" ? html`<${Accuracy} scope=${scope} />` : null}
  </div>`;
}

// Method: how every number in the app is made, in plain language.
import { html, useMemo, useState } from "../lib/html.js";
import { useMeta } from "../lib/scope.js";
import { fold } from "../lib/format.js";
import { Card, PageHead, SearchBox, Section, useDocumentTitle } from "../ui/common.js";

const PRINCIPLES = [
  { h: "Results are noisy; chances are less so", p: "A goal is rare and lumpy. The quality of the chances a team or player creates is a steadier signal of what will happen next. So the app keeps showing both, and names the gap between them." },
  { h: "Small samples are treated cautiously", p: "Per-90 rates swing wildly over a few games. Players are ranked only against peers with enough minutes, and every rate is pulled toward the role average in proportion to how little football is behind it. A cameo cannot top a leaderboard." },
  { h: "Everyone is compared with their own role", p: "A defender's 0.1 npxG per 90 is ordinary and a striker's is poor. Percentiles are always among players of the same role with enough minutes, so 90 means the same thing wherever you see it." },
  { h: "Luck is measured, not guessed", p: "For a player, the app takes every shot he had, gives each its xG, and works out the exact chance of every possible goal tally. Where his actual total falls in that distribution is the significance (z) you see on player pages." },
];

const METHODS = [
  { h: "Expected points", p: "For each match, every shot's xG is treated as an independent chance of scoring. That gives the exact probability of each team scoring 0, 1, 2… goals, and so of a home win, draw and away win. Expected points are 3 × P(win) + 1 × P(draw). Summed across a season, they show the table the chances deserved." },
  { h: "Roles and ranking", p: "Understat lists positions as combinations (for example 'F M S'). Players are grouped into goalkeeper, defender, midfielder or attacker from those letters; when a player's positions straddle groups, the role is inferred by which group's typical profile his minutes resemble, and refined by Understat's favourite position when available. The peer pool is players with at least about a quarter of the minutes a full-time player could have had. Ranking uses rates shrunk toward the role average with a prior worth about eight games." },
  { h: "Role score", p: "The average percentile across the metrics that define the role: goal threat and shot volume for attackers, creation and involvement for midfielders, progression and involvement for defenders. It is a starting point for a shortlist, not a verdict: open the profile to see which parts drive it." },
  { h: "Similar players", p: "Every player is described by his percentiles across his role's key metrics. Similarity is the closeness of two percentile profiles, so a high-volume and a low-volume player with the same style still match. The card lists the metrics where both are strong and the one where they differ most." },
  { h: "Team ratings and forecasts", p: "Each team gets an attack and a defence rating from a Poisson model fitted on expected goals, with recent matches weighted more and last season blended in early on. Scorelines use the standard low-score correction (Dixon-Coles) with its parameter fitted on real goals. The final probabilities blend that model (70%) with an Elo rating built from results (30%). Season odds come from playing out the remaining fixtures thousands of times." },
  { h: "Accuracy", p: "Forecast accuracy is tested walk-forward: each match is predicted using only the games before it, refitting every ten matches. Models are scored with ranked probability score, Brier score and log loss, and compared with a baseline that always predicts the league's average result split, and with Understat's own numbers." },
  { h: "Where the data comes from", p: "Match, shot and player data come from Understat, read at a slow, polite pace and stored on this computer. Birthdates come from Wikidata, matched by name and club. Nothing is sent anywhere else; the app works offline from its cache." },
  { h: "What it cannot tell you", p: "Expected goals ignore goalkeeping, defensive actions and off-ball work. Position-specific metrics are limited to what Understat records, so defenders and goalkeepers are only partly captured. Treat every number as evidence to weigh, and watch the sample size." },
];

function Glossary({ groups, query }) {
  const needle = fold(query);
  const filtered = groups.map((g) => ({ ...g, entries: g.entries.filter((e) => !needle || fold(e.term + " " + e.short + " " + e.long).includes(needle)) })).filter((g) => g.entries.length);
  if (!filtered.length) return html`<div class="well muted">Nothing in the glossary matches “${query}”.</div>`;
  return html`<div class="stack" style=${{ "--gap": "24px" }}>${filtered.map((g) => html`<section key=${g.group} id=${"g-" + g.group.toLowerCase().replace(/\W+/g, "-")}>
    <h3 class="gloss-group">${g.group}</h3><p class="muted small" style=${{ margin: "4px 0 12px" }}>${g.blurb}</p>
    <dl class="gloss">${g.entries.map((e) => html`<div key=${e.key}><dt>${e.term}</dt><dd><b>${e.short}</b> ${e.long}</dd></div>`)}</dl>
  </section>`)}</div>`;
}

function MetricTable({ metrics, title }) {
  const byCat = {};
  Object.values(metrics).forEach((m) => { (byCat[m.category] ||= []).push(m); });
  return html`<${Card} flush title=${title}>
    <div class="table-wrap"><table class="data dense"><thead><tr><th>Metric</th><th>Shown as</th><th>What it is</th><th>How to read it</th></tr></thead><tbody>
      ${Object.entries(byCat).map(([cat, list]) => html`<tr class="group-row" key=${"c" + cat}><th colspan="4">${cat}</th></tr>${list.map((m) => html`<tr key=${m.key}><td style=${{ fontWeight: 650 }}>${m.label}</td><td class="muted">${m.short}</td><td style=${{ whiteSpace: "normal", minWidth: "220px" }}>${m.what}</td><td class="secondary" style=${{ whiteSpace: "normal", minWidth: "220px" }}>${m.read}${m.higher_is_better === false ? " (lower is better)" : ""}</td></tr>`)}`)}
    </tbody></table></div>
  </${Card}>`;
}

export default function Method() {
  const { catalog } = useMeta();
  const [q, setQ] = useState("");
  useDocumentTitle("Method");
  return html`<div class="stack" style=${{ "--gap": "28px" }}>
    <${PageHead} eyebrow="System" title="Method" sub="How every number in Prem Lab is made, what it can and cannot tell you, and a glossary of the terms." />
    <div class="grid cols-2">${PRINCIPLES.map((p) => html`<${Card} key=${p.h}><h3 class="card-title">${p.h}</h3><p class="secondary" style=${{ marginTop: "6px" }}>${p.p}</p></${Card}>`)}</div>
    <${Section} title="How the analysis works">
      <div class="grid cols-2 top">${METHODS.map((m) => html`<div class="method" key=${m.h}><h3>${m.h}</h3><p>${m.p}</p></div>`)}</div>
    </${Section}>
    <${Section} title="Glossary" actions=${html`<${SearchBox} value=${q} onInput=${setQ} placeholder="Search the glossary" width="240px" />`}>
      <${Card}><${Glossary} groups=${catalog.glossary.groups} query=${q} /></${Card}>
    </${Section}>
    <${Section} title="Every metric">
      <${MetricTable} metrics=${catalog.metrics} title="Player metrics" />
      <${MetricTable} metrics=${catalog.team_metrics} title="Team metrics" />
    </${Section}>
  </div>`;
}

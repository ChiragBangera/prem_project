// Guide: where every chart and feature lives, and how to read the colours.
import { html } from "../lib/html.js";
import { href } from "../lib/router.js";
import { FEATURES } from "../lib/help.js";
import { Card, PageHead, useDocumentTitle } from "../ui/common.js";

export default function Guide() {
  useDocumentTitle("Guide");
  return html`<div class="stack" style=${{ "--gap": "24px" }}>
    <${PageHead} eyebrow="Guide" title="Where to find things" sub="Every chart and feature, where it lives, and what it is for. Look for the (i) button next to a chart title for what it shows, what good looks like and what to watch for." />
    <${Card} title="How to read the colours">
      <div class="stack" style=${{ "--gap": "8px" }}>
        <p><b>Blue</b> means above expectation and <b>orange</b> means below. Neither is good or bad on its own: a team with far more points than its chances deserve is blue, and that is usually luck that fades.</p>
        <p><b>Percentile bars</b> always read higher is better. 50 is average, 90 is better than nine in ten comparable players or teams.</p>
        <p><b>Small sample</b> means few minutes or games. Treat those numbers as a hint, not a verdict.</p>
      </div>
    </${Card}>
    <${Card} title="Pitch drawings">
      <div class="stack" style=${{ "--gap": "8px" }}>
        <p><b>Team maps</b> (a team's page, Style & maps): touch heat map, passes by type, pass network, defending, carries, take-ons and goalkeeper actions, for the whole season, home or away, or the last 5, 10 or 20 matches. <b>Player maps</b> (a player's page, Maps) show the same for one player.</p>
        <p><b>Shot maps</b>: every shot a team took and faced (a team's page, Chances), one player's shots (Finishing and shots), and both teams' shots in a match report.</p>
        <p>On every pitch the team attacks left to right and its left wing is at the top, so any two maps read the same way. Maps need event data; where it is not stored yet the page says so instead of drawing an empty pitch.</p>
      </div>
    </${Card}>
    <${Card} title="Scout and Teams in one minute">
      <div class="stack" style=${{ "--gap": "8px" }}>
        <p><b>Nothing is pre-selected.</b> Every player (or team) is listed until you narrow it down, and the count above the table always matches the table.</p>
        <p><b>Filters add up.</b> Role, position, profile, club, minutes, age, playing time and any metric limit each narrow the list on their own. The strip under the filters shows exactly what is active, with a cross to remove each.</p>
        <p><b>Lenses are quick filters.</b> Point at one to read the rules it adds. It never changes your columns or sorting; two buttons offer its metrics as columns or as the sort, if you want them.</p>
        <p><b>Columns are yours.</b> Pick a set (Attacking, Defending ...) or tick any metric. Columns sit under headings by kind, and the column you sorted by is always shown. <b>Show Top N</b> limits both the table and the map.</p>
      </div>
    </${Card}>
    <${Card} title="Find a chart or feature" flush>
      <div class="guide-list" style=${{ padding: "4px 20px 12px" }}>
        ${FEATURES.map((f) => html`<div class="guide-item" key=${f.name}>
          <div><a class="link" href=${href(f.href)}><b>${f.name}</b></a><div class="where">${f.where}</div></div>
          <div>${f.what}</div>
        </div>`)}
      </div>
    </${Card}>
  </div>`;
}

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
      <div class="stack guide-text" style=${{ "--gap": "8px" }}>
        <p><b>Blue</b> means above expectation and <b>orange</b> means below. Neither is good or bad on its own: a team with far more points than its chances deserve is blue, and that is usually luck that fades.</p>
        <p><b>Percentile bars</b> always read higher is better. 50 is average, 90 is better than nine in ten comparable players or teams.</p>
        <p><b>Shaded cells</b> in a table (Scout, Teams, a squad, a match's players, the shortlist, the league table) work the same way: the darker the cell, the higher it ranks among comparable players or teams; an orange cell is in the bottom 15%. A grey bar or an unshaded cell is a matter of style, where neither end is better.</p>
        <p><b>Small sample</b> means few minutes or games. Treat those numbers as a hint, not a verdict.</p>
      </div>
    </${Card}>
    <${Card} title="Pitch drawings">
      <div class="stack guide-text" style=${{ "--gap": "8px" }}>
        <p><b>Team maps</b> (a team's page, Style & maps): touch heat map, passes by type, pass network, defending, carries, take-ons and goalkeeper actions, for the whole season, home or away, or the last 5, 10 or 20 matches. <b>Player maps</b> (a player's page, Maps) show the same for one player.</p>
        <p><b>Shot maps</b>: every shot a team took and faced (a team's page, Chances), one player's shots (Finishing and shots), and both teams' shots in a match (Shots). They all read the same way: a bigger circle is a better chance, a solid circle with a dark rim is a goal, a half-filled one was saved, a faint one missed or was blocked, and a dashed outline is a shot with no xG yet. The list beside the map holds the same shots; pick one, there or on the pitch, for who took it, what it was worth and how it came about.</p>
        <p>On every pitch the team attacks left to right and its left wing is at the top, so any two maps read the same way. Maps need event data; where it is not stored yet the page says so instead of drawing an empty pitch.</p>
      </div>
    </${Card}>
    <${Card} title="Busy, or productive? Volume against what came of it">
      <div class="stack guide-text" style=${{ "--gap": "8px" }}>
        <p>A player can pass forward, run with the ball and beat his man all afternoon without a chance coming of it. So wherever the app counts progressive passes, progressive carries, take-ons won and crosses, it also counts <b>how many were in a move that came to a shot</b> (the move's own shot, or one from the corner, free kick or penalty it won).</p>
        <p><b>The split bar</b> shows both at once: its length is how often he did it, the solid part came to a shot, the hatched part did not. It is on a player's Profile ("What his actions led to") and on a match's Players tab under By half ("Busy, and what came of it"). On the Profile the bar has a dark end for three kinds of action: the times his side had lost the ball again within three actions. In a table (Scout, a team's Players) the same bar sits under the number in every "came to a shot" column: there its length is measured against the busiest regulars in the list.</p>
        <p><b>Moves over a season.</b> A team's Style &amp; maps tab ends with "How their moves end": every spell of possession, by how it ended and by where and how it began, where the ball is lost, who lost it most and who took it off the opponents most. A player's Maps tab ends with "Moves he was part of": where he lost the ball (and how), and where he took it off the other side. They are the same moves a match's Moves tab lists, added up.</p>
        <p><b>On Scout's map</b>, start from the question "Busy, or productive?". Each role has its own trend line, and the players furthest below their role's line are named: a lot of forward movement, less to show for it than usual. The lens "Busy, little end product" filters the table the same way.</p>
        <p>It describes actions, not worth. A pass can be the right one and the next player can still waste it, and one match is a small sample.</p>
      </div>
    </${Card}>
    <${Card} title="What the app cannot show: distance covered, sprints, pressing runs">
      <div class="stack guide-text" style=${{ "--gap": "8px" }}>
        <p><b>Distance covered, sprints and high-intensity runs are not in the app.</b> They need tracking data (every player's position many times a second), and neither Understat nor WhoScored publishes it. The app does not estimate them: a made-up number would look like a measurement.</p>
        <p>The nearest thing is a <b>carry</b>: the ball moving at least 3 metres with the same side on it between two events. That is worked out from the order of events, it only covers a player with the ball, and it is labelled an estimate wherever it appears.</p>
      </div>
    </${Card}>
    <${Card} title="The tables in one minute">
      <div class="stack guide-text" style=${{ "--gap": "8px" }}>
        <p><b>Nothing is pre-selected.</b> Every player (or team) is listed until you narrow it down, and the count above the table always matches the table.</p>
        <p><b>Scout, Teams, a team's Players tab and a match's Deep analytics are one desk of three parts.</b> Filters sit in a rail on the left and add up: role, position, age, minutes, profile, club and a rule on any measure (Teams adds the usual formation; a match adds the side and who started). Every active one shows as a pill above the table with a cross to remove it.</p>
        <p><b>The table starts at the top.</b> Sets of measures are tabs, every measure column is the same width, and a heading shows a short name: point at it for the full name, click it for the measure's spread, sorting, "keep only the top 25%" and an exact limit. The league table and the shortlist use the same table and headings.</p>
        <p><b>Click a row</b> to see the player or team beside the list without leaving it; the name opens the full page. In a match, the best and the weakest number of each measure among the players listed are ringed.</p>
        <p><b>Ready-made searches</b> (Goal threats, Ball winners ...) say which rules they apply, show their measures and rank by the main one. "Edit these rules" hands the rules to you. Name a search under "Your searches" to keep it. <b>Top N</b> limits both the table and the map.</p>
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

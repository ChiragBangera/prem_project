// Where shots went in the goal over a set of matches (a player's season, a team's shots and the shots it faced): the same goal the match
// page draws for one match, from the same two numbers of the event data. No xG here: WhoScored has none, so every circle is one size.
import { html } from "../lib/html.js";
import { useApi } from "../lib/api.js";
import { plural } from "../lib/format.js";
import { GoalMouth } from "../charts/matchcharts.js";
import { Card } from "./common.js";

const line = (shots) => {
  const goals = shots.filter((s) => s.result === "Goal").length, saved = shots.filter((s) => s.result === "SavedShot").length;
  return `${plural(goals, "goal")}, ${saved} saved, ${shots.length - goals - saved} off target or against the frame`;
};

/** One goal per side. sides: [{ label, color, shots }]; names: player id -> name; matches: how many matches the shots come from. */
export function GoalMouthSeason({ sides, names, matches, title = "Where the shots went in the goal" }) {
  const shown = sides.filter((s) => s.shots?.length);
  if (!shown.length) return null;
  return html`<${Card} title=${title}
    sub=${`Each goal as the shooter saw it${matches ? `, over ${plural(matches, "match", "matches")}` : ""}. Filled: scored. Ringed: saved. Faint: off target or against the frame. Blocked shots never got there, so they are left out; one that went far wide or high is counted but not drawn. This comes from the event data, which has no xG, so every circle is the same size.`}>
    <div class=${"goalmouths" + (shown.length === 1 ? " one" : "")}>${shown.map((s) => html`<div class="goalmouth-side" key=${s.label}>
      <div class="row between wrap"><b><i class="side-dot" style=${{ background: s.color }}></i>${s.label}</b><span class="muted small num">${line(s.shots)}</span></div>
      <${GoalMouth} shots=${s.shots} names=${names} color=${s.color} label=${`${s.label}: where the shots went in the goal`} />
    </div>`)}</div>
  </${Card}>`;
}

/** A player's season: fetched from his maps (the same request his Maps tab makes, so it is usually already there). */
export function PlayerGoalMouth({ id, league, season, name }) {
  const q = useApi(`/api/maps/player/${id}`, { league, season });
  const gm = q.data?.goal_mouth;
  if (!gm?.for?.length) return null;
  return html`<${GoalMouthSeason} title="Where his shots went in the goal" matches=${q.data.n} names=${{ [q.data.ws_id]: q.data.name || name }}
    sides=${[{ label: q.data.name || name || "His shots", color: "var(--c1)", shots: gm.for }]} />`;
}

/** A team's season: the shots it took and the shots it faced. */
export function TeamGoalMouth({ team, scope }) {
  const q = useApi("/api/maps/team", { team, league: scope.league, season: scope.season });
  const gm = q.data?.goal_mouth;
  if (!gm || !(gm.for.length + gm.against.length)) return null;
  return html`<${GoalMouthSeason} matches=${q.data.n} names=${q.data.names}
    sides=${[{ label: `${team}'s shots`, color: "var(--c1)", shots: gm.for }, { label: "Shots they faced", color: "var(--c2)", shots: gm.against }]} />`;
}

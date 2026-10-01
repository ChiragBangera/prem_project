// Plain-language help for every card and chart: what it shows, what good looks like, what to watch for.
// Card and Section look their title up here, so an (i) button appears automatically wherever there is an entry.
// Colour rule used across the app: blue = above expectation, orange = below. Neither colour means good or bad on its own.

const SHOT_MAP = {
  what: "Every shot drawn where it was taken. Circle size is the quality of the chance (xG): a big circle is a big chance. A dark rim marks a goal.",
  good: "Big circles close to the goal, and rimmed circles inside them: good positions that were finished.",
  bad: "Lots of small circles far from goal means speculative shooting. Big circles with no rim are chances that were wasted.",
};

const PERCENTILES = {
  what: "Each bar is a percentile: the share of comparable players (same role, enough minutes) he is above. The tick marks the median.",
  good: "Longer bars. 50 is average, 90 means better than 90% of peers. Every bar reads 'higher is better', including defensive ones.",
  bad: "Short bars are weaker than most peers. Small-sample players are flagged, since a few minutes can swing any rate.",
};

const TEAM_PERCENTILES = {
  what: "Where the team ranks among all teams in the league on each measure. The tick marks the league median.",
  good: "Longer bars. Every bar reads 'higher is better': a long 'Chance prevention' bar means few chances allowed.",
  bad: "Short bars are bottom-of-the-league areas. Compare 'Results' with 'Overall quality': results far above quality often fade.",
};

const XPTS = {
  what: "Points actually won (solid line) against expected points (dashed): the points the chances created and allowed were worth.",
  good: "Both lines rising together means results are backed by performances.",
  bad: "Points far above expected points is usually luck that fades; far below is bad luck that tends to correct.",
};

export const HELP = {
  // Briefing
  "What stands out": {
    what: "Findings the numbers throw up right now, ranked by how far they sit from expectation.",
    good: "'Upside' items: better than the results show, or likely to last.",
    bad: "'Watch' and 'Downside' items: results flattering the team or player. 'Small sample' means few games or minutes, so be cautious.",
  },
  "The run-in": {
    what: "The rest of the season replayed thousands of times using the model's win, draw and loss probabilities.",
    good: "A high percentage in Title or Top 4 means that outcome happens in most of the replays.",
    bad: "A high percentage in Relegation is danger. A small percentage is still possible, just rare.",
  },
  "Next fixtures": {
    what: "The model's win, draw and loss chances for each game, with the most likely score. Built from chances created and allowed, not bookmakers.",
    good: "A long bar for the team means the model expects it to win. Near-equal thirds is an open game.",
    bad: "Treat them as odds, not predictions: a 20% outcome still happens one game in five.",
  },
  "Latest results": {
    what: "Recent scores with the xG (chances) underneath.",
    good: "When the score matches the xG, the result was deserved.",
    bad: "'Did not follow the chances' marks results that flattered a team or were unfair to them.",
  },
  "Points against expected points": {
    what: "Each team's actual points against the points the chances were worth (xPts).",
    good: "Small gaps mean the table reflects performance.",
    bad: "A big positive gap means over-performing, likely to slip. A big negative gap means under-performing, likely to recover.",
  },

  // League
  "Attack against defence": {
    what: "Each team placed by chances created against chances allowed per game. Dotted lines are league averages; click a team to open it.",
    good: "Teams that create a lot and allow little, the strongest underlying sides.",
    bad: "Teams that create little and allow a lot. A team far from where the table would put it is a candidate to rise or fall.",
  },
  "The race, matchweek by matchweek": {
    what: "Each team's league position after every round, drawn as a line.",
    good: "Lines rising or staying near the top.",
    bad: "Lines falling toward the bottom places. Click a team to follow it.",
  },

  // Match report
  "What the chances say": {
    what: "The result the chances deserved, from playing out every shot.",
    good: "When the deserved result matches the score, nothing lucky happened.",
    bad: "If the winner had a lower deserved chance, the result flattered them.",
  },
  "How the chances built up": {
    what: "Running total of xG for each side through the match. Steps up are shots; the bigger the step, the better the chance.",
    good: "The higher line was creating the better chances at that point.",
    bad: "Flat stretches mean no danger. A line that jumps late can hide a game that was quiet for most of it.",
  },
  "Shot map": SHOT_MAP,
  "Head to head": {
    what: "Team totals side by side: shots, xG, and other match numbers.",
    good: "The longer side of each bar did more of that thing.",
    bad: "Shots alone mislead. Compare xG per shot to see who took better chances.",
  },
  "The best chances": {
    what: "The highest-quality shots of the match, in order of xG.",
    good: "High xG (0.30+) is a big chance: about one in three or better to score.",
    bad: "Big chances missed are where the result was decided.",
  },
  "When the chances came": {
    what: "Expected goals (xG) for each side in each period of the match.",
    good: "A taller bar means that side created better chances in that period.",
    bad: "Very short bars mean a quiet spell. One tall bar can be a single big chance rather than sustained pressure.",
  },

  // Player
  "Every metric": PERCENTILES,
  "Role": {
    what: "How the app decides who this player is compared with (attacker, midfielder, defender, goalkeeper).",
    good: "A clear role gives fair comparisons.",
    bad: "Roles inferred from minutes alone are less exact and sharpen as position data arrives.",
  },
  "Where the shots come from": {
    what: "His shots split by situation (open play, set piece, penalty), body part or zone. Use the buttons to switch.",
    good: "Most shots from central zones near goal and from open play: the best positions.",
    bad: "Lots of long shots or a heavy reliance on penalties means lower-quality, less repeatable output.",
  },
  "How unusual is his finishing?": {
    what: "Each bar is the chance of him scoring exactly that many goals from the shots he took. The highlighted bar is what he actually scored.",
    good: "The highlighted bar among the tallest bars means finishing is ordinary and the numbers are trustworthy.",
    bad: "Highlighted bar far to the right (tinted bars) means running hot and likely to cool. Far to the left means unlucky and goals may follow.",
  },
  "Shot quality": {
    what: "Average quality of his shots (xG per shot) and how many were big chances.",
    good: "Higher xG per shot means he gets into better positions.",
    bad: "Low xG per shot with many shots means speculative shooting.",
  },
  "Season by season": {
    what: "Every league season Understat has for him, with per-90 rates.",
    good: "Steady or rising rates across seasons.",
    bad: "One outlier season can be luck, so check the minutes.",
  },
  "Players with a similar profile": {
    what: "Players whose percentile profile is closest across the metrics that define the role.",
    good: "High match percentages mean a very similar style.",
    bad: "Similar style is not similar quality. Compare minutes and role score too.",
  },

  // Team
  "Every match: chances against results": {
    what: "One bar per match: blue if the team created more chances than it allowed, orange if it allowed more. The marker above is what happened: won, drew or lost.",
    good: "Blue bars and green wins together: winning while the better team.",
    bad: "Wins on orange bars were lucky; losses on blue bars were unlucky. A row of orange bars is a warning.",
  },
  "Against the rest of the league": TEAM_PERCENTILES,
  "Chances created and allowed": {
    what: "Rolling five-match average of xG for (created) and against (allowed). Until six matches are played it shows each match instead.",
    good: "The 'for' line above the 'against' line and rising.",
    bad: "'Against' climbing above 'for' means the team is being outplayed.",
  },
  "Points and expected points": XPTS,
  "Squad contributions": {
    what: "Every player's minutes, goals against xG, assists and share of the team's attacking output.",
    good: "Output spread across several players; G – xG near zero means unremarkable finishing.",
    bad: "One player carrying most of the xG is a dependency. Big positive G – xG usually fades.",
  },
  "Splits": {
    what: "The same team in different circumstances, such as home and away or against strong and weak sides.",
    good: "Strong splits everywhere means a consistent team.",
    bad: "A big home/away gap or poor results against weaker sides shows where points leak.",
  },
  "What is next": {
    what: "Upcoming games with win, draw and loss chances and how strong each opponent is.",
    good: "Green 'easy' opponents and high win chances.",
    bad: "A tougher run-in than the games already played.",
  },

  // Team history
  "Seasons to compare": {
    what: "Pick which of this team's seasons to lay over each other. Each keeps its own colour in every chart and in the table.",
    good: "Five seasons is a good window: enough to see a pattern without the chart getting crowded.",
    bad: "Seasons where the team was in a lower division cannot be drawn and are listed as 'not in the league'.",
  },
  "Seasons side by side": {
    what: "One row per season: final position, points, expected points (xPts), goal difference and expected goal difference (xGD).",
    good: "Points close to xPts and xGD in line with GD mean the finish was earned by the chances.",
    bad: "Points far above xPts (blue) means a lucky finish that often fades the next year; far below (orange) means an unlucky one.",
  },
  "Points by matchweek": {
    what: "Running total of league points after each of the team's matches, one line per season. Matchweek means the team's nth match, so a postponed game shifts later weeks.",
    good: "A line that is higher and steeper than the others: a faster start or a better run.",
    bad: "A line that flattens early shows a stall. Compare the finish, not just the start: the lines can cross.",
  },
  "League position by matchweek": {
    what: "The team's table position after each round, one line per season. 1st is at the top.",
    good: "Lines near the top of the chart, especially staying there.",
    bad: "Lines sinking toward the bottom places. Early-season positions swing a lot, so read the later weeks.",
  },
  "Chances trend by matchweek": {
    what: "Chances created minus chances allowed (xG difference). 'Running total' adds it up over the season; 'Last 5 matches' shows the current form of the chances.",
    good: "Above the zero line and rising: the team keeps creating more than it allows.",
    bad: "Below zero means being outplayed. A season with good points but a low xG line is likely to slip.",
  },

  // Optional event data
  "Defending and passing": {
    what: "Duels, tackles, interceptions and passing from WhoScored's event data, each ranked among players in the same role who have event data. Defensive duels are tackles, challenges and aerial duels as the defending side.",
    good: "Long bars. A high duel win rate on plenty of duels, strong interception and recovery numbers, and passing that is both accurate and moves the ball forward.",
    bad: "A high duel count can just mean a team that defends a lot, and a high forward-pass ratio with poor accuracy is losing the ball. Read volume and rate together, and watch the minutes behind each number.",
  },

  // Forecast and compare
  "Markets": {
    what: "The model's probabilities for common bets, such as over 2.5 goals and both teams scoring.",
    good: "Useful as a sense of how open a game is.",
    bad: "These are model estimates, not offers, and not tested against bookmaker prices.",
  },
  "Scoreline probabilities": {
    what: "The chance of every exact score. The ringed cell is the likeliest.",
    good: "A concentrated cluster shows the likely region.",
    bad: "Even the top score is usually under 15%, so exact scores are hard to call.",
  },
  "How the season could end": {
    what: "Thousands of simulated seasons, playing out every remaining match from each team's rating: how often each team finishes in each position.",
    good: "A high percentage for a high finish means that outcome is likely.",
    bad: "A wide spread means an uncertain finish.",
  },
  "Do the percentages mean what they say?": {
    what: "A check of the model against past matches: when it said 60%, did that happen about 60% of the time?",
    good: "Dots on the diagonal line: the percentages can be trusted.",
    bad: "Dots far from the line mean the model was over- or under-confident.",
  },
  "Models compared": {
    what: "How this model's past forecasts compare with simpler alternatives.",
    good: "Lower is better on the error columns. The best in each column is bold.",
    bad: "Small differences are noise over a short stretch of games.",
  },
  "Profile against role peers": PERCENTILES,
  "Profile against the league": TEAM_PERCENTILES,
  "Net chances through the season": {
    what: "Running total of xG created minus xG allowed, match by match.",
    good: "A line that climbs means the team keeps creating more than it allows.",
    bad: "A line that falls means it is being outplayed.",
  },
};

/** Help for a card title. Handles the few titles that are built from data. */
export function helpFor(title) {
  if (typeof title !== "string") {
    return null;
  }
  if (HELP[title]) return HELP[title];
  if (title.startsWith("Against ") && title.endsWith("with enough minutes")) return PERCENTILES;
  return null;
}

export const FEATURES = [
  { name: "Shot map: player", where: "Scout → click a player → 'Finishing and shots' tab", what: "Every shot he has taken, on a pitch, plus how lucky or unlucky his finishing is.", href: "/scout" },
  { name: "Shot map: match", where: "Matches → click any match → 'Shot map' card", what: "Both teams' shots on one pitch for a single game.", href: "/matches" },
  { name: "Where a team's chances come from", where: "League → click a team → 'Chances' tab", what: "Chances created and allowed in seven breakdowns (situation, shot zone, timing, game state, attack speed, formation, shot result), each explained and ranked against the league. Not a pitch drawing.", href: "/league" },
  { name: "Chances against results, match by match", where: "League → click a team → Overview", what: "Shows which results were deserved and which were lucky.", href: "/league" },
  { name: "Expected points (xPts)", where: "League → 'Expected' view", what: "The table the chances say it should be, and who is over- or under-performing.", href: "/league" },
  { name: "Title, top-4 and relegation odds", where: "Briefing → 'The run-in'; Forecast → 'Season'", what: "The rest of the season simulated thousands of times.", href: "/" },
  { name: "Find players by role and style", where: "Scout → pick a Lens (Goal threats, Hidden gems, Young and good...)", what: "Ranked player list with filters for role, minutes, age and club.", href: "/scout" },
  { name: "Lucky or unlucky finishers", where: "Scout → 'Unlucky finishers' and 'Running hot' lenses", what: "Players scoring well below or above what their chances say.", href: "/scout" },
  { name: "Compare two players or two teams", where: "Compare, or tick players in Scout", what: "Side-by-side percentile profiles with the differences spelled out.", href: "/compare" },
  { name: "Next fixtures and match odds", where: "Forecast → 'Fixtures' and 'Match lab'", what: "Win, draw and loss chances and likely scores for any pairing.", href: "/forecast" },
  { name: "Compare a team across seasons", where: "League → click a team → 'History' tab", what: "Points, league position and chances by matchweek, with up to 8 of the team's seasons laid over each other.", href: "/league" },
  { name: "Defending and passing metrics", where: "Scout → 'Defending & passing' columns (after fetching event data); the player page card", what: "Defensive duels, tackles, interceptions, forward-pass ratio and progressive passes per 90, ranked among players in the same role. Optional: needs event data fetched with prem events sync.", href: "/scout" },
  { name: "Track players you like", where: "Star any player, then open Shortlist", what: "Live numbers and your own notes.", href: "/shortlist" },
  { name: "Sync more leagues and seasons", where: "Data", what: "Fetch other leagues or older seasons and check the connection.", href: "/data" },
  { name: "What a number means", where: "Method, or hover any (i) button", what: "Plain-language definitions of every metric.", href: "/method" },
];

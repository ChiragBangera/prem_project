// Plain-language help for every card and chart: what it shows, what good looks like, what to watch for.
// Card and Section look their title up here, so an (i) button appears automatically wherever there is an entry.
// Colour rule used across the app: blue = above expectation, orange = below. Neither colour means good or bad on its own.

const SHOT_MAP = {
  what: "Every shot drawn where it was taken. Circle size is the quality of the chance (xG): a big circle is a big chance. A dark rim marks a goal.",
  good: "Big circles close to the goal, and rimmed circles inside them: good positions that were finished.",
  bad: "Lots of small circles far from goal means speculative shooting. Big circles with no rim are chances that were wasted.",
};

const PERCENTILES = {
  what: "Each bar places him among comparable players (same role, enough minutes): a full bar is the best of them, an empty bar the lowest, and the tick the typical one (the median). The number is how many of every 100 of them he beats.",
  good: "Longer bars. 50 is typical, 90 means better than 90 of every 100. For things like fouls and errors the bar is flipped, so a longer bar is still better.",
  bad: "Short bars are weaker than most peers. Grey bars describe style, not quality, so neither long nor short is better. A few minutes can swing any rate, so small samples are flagged.",
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
  "Next fixtures": {
    what: "The coming matches, with kickoff in your own time zone and what each side looks like going in: league position, last five results and chance difference per game.",
    good: "A side high in the table with strong recent form and a positive chance difference is in good shape.",
    bad: "Form is five matches, a small sample. The chance difference is the steadier guide.",
  },
  "Latest results": {
    what: "Recent scores with who scored, the xG (chances), possession and shots.",
    good: "When the score matches the xG, the result was deserved.",
    bad: "'Against the run of play' marks results that flattered a team or were unfair to them.",
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
  "How the game was played": {
    what: "Possession (share of passes), passing, corners, fouls, cards and the shape each side used, from the event data.",
    good: "More of the ball is not the same as better chances: compare it with the xG.",
    bad: "A side with little possession can still be the dangerous one (counter-attacking). Read possession next to chance quality.",
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
  "Maps": {
    what: "Where he touches the ball, passes, defends and carries it, drawn from every match of the event data he played. Choose a layer above the pitch.",
    good: "Heat where his role says it should be: a full-back high on the touchline, a centre-back in front of his own box.",
    bad: "Few matches make a thin picture. Carries are an estimate from the order of events, and a pass network's receiver is inferred.",
  },

  // Team
  "Every match: chances against results": {
    what: "One bar per match: blue if the team created more chances than it allowed, orange if it allowed more. The marker above is what happened: won, drew or lost.",
    good: "Blue bars and green wins together: winning while the better team.",
    bad: "Wins on orange bars were lucky; losses on blue bars were unlucky. A row of orange bars is a warning.",
  },
  "How they play": {
    what: "Where the team stands among the teams of its own league and season on results, chance creation and prevention, possession, pressing and set pieces. Bars are percentiles; a dot on a track is a style measure where more is neither better nor worse.",
    good: "Long bars in the areas that matter for the way the team wants to play. The thin tick is the league median.",
    bad: "A style measure is not a grade: a low possession share can be a plan. Read the style next to the chance quality.",
  },
  "Against the rest of the league": TEAM_PERCENTILES,
  "Chances created and allowed": {
    what: "Rolling five-match average of xG for (created) and against (allowed). Until six matches are played it shows each match instead.",
    good: "The 'for' line above the 'against' line and rising.",
    bad: "'Against' climbing above 'for' means the team is being outplayed.",
  },
  "Points and expected points": XPTS,
  "Where the output comes from": {
    what: "The squad's biggest contributors to the team's non-penalty xG, xA and attacking chains, as shares.",
    good: "Output spread across several players.",
    bad: "One or two players carrying most of it is a dependency: the team is easier to stop, and fragile when they are missing.",
  },
  "Splits": {
    what: "The same team in different circumstances, such as home and away or against strong and weak sides.",
    good: "Strong splits everywhere means a consistent team.",
    bad: "A big home/away gap or poor results against weaker sides shows where points leak.",
  },
  "What is next": {
    what: "Upcoming games, with kickoff in your time zone and how strong each opponent is on chance difference.",
    good: "Kind opponents and a run-in easier than the games already played.",
    bad: "A tougher run-in than the games already played.",
  },
  "Style and maps": {
    what: "Pitch maps of everything the team does with the ball and against it, from the event data: touches, passes, pass network, defending, carries, take-ons, goalkeeper actions and shots.",
    good: "Shapes that match the way the manager says the team plays.",
    bad: "A few matches make a thin picture; narrow by home, away or recent matches only when there are enough.",
  },
  "Every shot": SHOT_MAP,
  "Match by match": {
    what: "Every league match with the score, the chances and (where event data is stored) possession, passing, field tilt, pressing and the shape used.",
    good: "Results that follow the chances and style that stays steady.",
    bad: "A dash means no event data for that match yet, never zero.",
  },
  "Does having the ball help?": {
    what: "One dot per match: possession on the way across, chance difference up the side, coloured by the result.",
    good: "Dots rising to the right mean possession turns into better chances for this team.",
    bad: "Dots high on the left show a team that is dangerous without the ball.",
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

  // Data
  "Automatic updates": {
    what: "While the app is open it looks for newly finished matches and fetches only those, politely and within a time budget. It keeps what it has if something fails and tries again later.",
    good: "'On', with a recent cycle and no problems.",
    bad: "Problems listed under 'Needs attention' are retried by themselves with a growing delay; a season that does not exist yet is not a problem.",
  },
  "What is on this computer": {
    what: "Each league season stored, and how complete each layer is: league data, match pages (scorers, shots, positions) and event data (maps, passing, duels).",
    good: "Bars full for the finished seasons you care about.",
    bad: "A part-filled bar for a live season is normal: it fills as matches are played and fetched.",
  },

  // Compare
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
  { name: "Find players by anything", where: "Scout", what: "Every player is listed; narrow with role, position, profile, club, minutes, age, playing time or a limit on any metric. Nothing is pre-selected.", href: "/scout" },
  { name: "Lenses: quick filters, explained", where: "Scout and Teams → Lenses row", what: "Goal threats, Ball winners, Hidden gems and more. Point at one to read exactly which rules it adds; it never changes your columns or sorting.", href: "/scout" },
  { name: "Your own columns", where: "Scout and Teams → Columns", what: "Pick any of the metrics (or start from Attacking, Defending, Passing ...). They are grouped under their kind in the table.", href: "/scout" },
  { name: "The map, and Top N", where: "Scout and Teams → Table / Map", what: "Plot everyone on any two metrics. 'Show Top 20' limits both the table and the map to the first 20 of your sort.", href: "/scout" },
  { name: "Scout for teams", where: "Teams", what: "The same filters, lenses, columns and map over every team measure: results, chances, possession, pressing, set pieces, discipline.", href: "/teams" },
  { name: "Team style profile", where: "Teams → a team → Overview → 'How they play'", what: "Where a side stands in its league on results, creating, preventing, possession, pressing and set pieces.", href: "/teams" },
  { name: "Pitch maps for a team", where: "A team → Style & maps", what: "Touch heat map, passes by type, pass network, defending, carries, take-ons, goalkeeper actions and shots, for the whole season, home or away, or the last 5, 10 or 20 matches.", href: "/teams" },
  { name: "Pitch maps for a player", where: "A player → Maps", what: "The same layers for one player across all his matches.", href: "/scout" },
  { name: "Chances in one chart with toggles", where: "A team → Chances", what: "Break the chances down by situation, zone, timing, game state, speed, formation or result, and draw them as bars, versus the league, columns, a mix or on the pitch. Every shot is drawn below.", href: "/teams" },
  { name: "The whole squad, ranked", where: "A team → Players", what: "The club's players in the same table as Scout, with lenses, columns and a map.", href: "/teams" },
  { name: "Match by match", where: "A team → Matches", what: "Every league match with the chances, possession, passing and pressing, and whether having the ball helped.", href: "/teams" },
  { name: "Matches, with scorers", where: "Matches", what: "Each matchweek as compact cards: score, scorers, xG, possession and shots. Times are in your time zone. 'Results that lied' lists results that went against the chances.", href: "/matches" },
  { name: "Expected points (xPts)", where: "League → 'Expected' view", what: "The table the chances say it should be, and who is over- or under-performing.", href: "/league" },
  { name: "Compare two players or two teams", where: "Compare, or tick players in Scout", what: "Side-by-side percentile profiles with the differences spelled out.", href: "/compare" },
  { name: "Track players you like", where: "Star any player, then open Shortlist", what: "Live numbers and your own notes.", href: "/shortlist" },
  { name: "What a number means", where: "Dictionary, or hover any (i) button", what: "Every metric, raw or derived: its formula, inputs, how to read it, caveats and typical values.", href: "/dictionary" },
  { name: "How fresh the data is, and what failed", where: "Data", what: "Automatic updates, coverage of every league season, what the last cycle did, what failed and when it will retry. Switch event data on or off.", href: "/data" },
];

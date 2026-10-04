# Features

What the app does, page by page. The [README](../README.md) has the short version and how to run it.

## The pages

Every page opens with findings, then the evidence.

- **Briefing**: what stands out right now: teams above or below what their chances deserve, players riding luck, the title race, the latest results with who scored and how the chances split, the next fixtures with each side's position, form and chance difference, the biggest movers, and your shortlist.
- **League**: standings read three ways (results, expected, style), attack against defence, and the table race matchweek by matchweek.
- **Matches**: every match of a matchweek as a compact card: big score, scorers and minutes, possession and shots, the chances behind the result, and a flag on the ones that went against them. Open one for the full report: the deserved result, xG race, shot map, head to head, the best chances, and (with event data) how each side played: possession, passing, shape.
- **Scout**: find players by what they do (below).
- **Teams**: the same explorer for teams: every team measure, ranked within its own league and season.
- **Team page**: **Overview** (every match as chances against results, what is next, how they play), **Players** (the squad, with per-player metrics), **Style & maps** (a style profile and pitch maps), **Chances** (where chances come from and where they are allowed, one chart with toggles), **Matches** (match by match, and whether having the ball helps) and **History** (seasons side by side).
- **Player page**: Profile against role peers (every metric is searchable; the bars say who he is compared with and what a full bar, an empty bar and the tick mean), pitch **Maps**, a **Match log**, **Finishing and shots** (an exact "how unusual is his finishing" distribution and a shot map), **Seasons** and statistically **Similar players**.
- **Compare**: players (a percentile dot plot with the differences spelled out) or two teams (numbers, style, trend, meetings).
- **Shortlist**: players you track, live numbers and your own notes.
- **Dictionary**: every raw field and every derived number: what it is, its formula, where it comes from, what it needs, how to read it, and what a typical value looks like. Plus every event type and qualifier, every profile tag and lens in words.
- **Guide** and **Data**: where to find things, and what is stored, what the updater did, what failed, and how complete each layer is.

Press `/` or `Ctrl`/`⌘` + `K` anywhere to search players, teams and pages. The address bar carries the page's state (filters, sort, columns, scope), so any view can be bookmarked or sent to someone.

## Scout and Teams: nothing is pre-selected

Both pages list **everyone** until you narrow them down, and every control is yours:

- **Filters add up**, each one independent. For players: role, exact position, club, minutes, age, playing time and **Profile** (the tags below). For teams: formation. For both, a **metric filter**: "keep those whose value, or percentile, is above or below a limit" on any of the ~110 player (or ~100 team) metrics. Each active filter shows as a chip you can remove.
- **Lenses are quick filters, explained.** "Goal threats", "Ball winners", "Unlucky finishers", "Young and good", "Ever-present" (19 for players), "High press", "Possession-dominant", "Set-piece reliant" (13 for teams) ... A lens is nothing but a set of filter rules; point at one and the page lists exactly which rules it applies and which metrics it looks at. A lens never changes your sort, columns or other filters.
- **Profile tags** describe how a player plays: Poacher, Complete forward, Chance creator, Playmaker, Ball-playing defender, Aerial dominator, Sweeper-keeper ... 27 in all. Each is a short rule on role percentiles that you can read in the Dictionary, and each tag shown on a player says why he earned it.
- **The table is yours too.** Columns come in groups (shooting, creating, passing, defending ...). Pick a ready-made set (Overview, Attacking, Creating, Passing, Carrying, Defending, Duels, Goalkeeping, Set pieces, Discipline) or choose any of the metrics as a column. Click any heading to sort; blanks always sort last, never as zero.
- **Top N** (10, 20, 50, 100 or your own number) applies to the table **and** the map, so "the ten best ball-winners among defenders under 23" is two clicks.
- **The map** plots any metric against any other, coloured by role (players) or league, sized by minutes, with outliers fenced so one cameo cannot flatten the picture.
- A short **read of the ranking** (who leads, how far ahead, how the top group differs from the rest) sits above the table, and a note appears when a rate is led by players with very few minutes.
- Percentiles always compare a player **only with his own role** (a team only with its own league and season), shrunk toward the average in proportion to how little football stands behind them.
- Tick up to four players to compare, export what you see as CSV, or copy a link to exactly this view.

## Pitch maps (event data)

With event data stored, every player and team has maps drawn from the real positions of every touch: **Touches** (heat), **Passes** (progressive, key passes, into the box, long balls, crosses, through balls), **Pass network** (average positions and the strongest links), **Defending** (tackles, interceptions, recoveries, clearances, aerials), **Carries**, **Take-ons**, **Shots** and **Goalkeeper** actions, filterable by home/away and by match. All maps attack left to right with the left wing at the top. Where no events are stored a map says so rather than drawing nothing.

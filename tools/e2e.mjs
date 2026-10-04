#!/usr/bin/env node
// End-to-end behaviour checks against a running server (use --demo so the data is deterministic).
//
//   prem serve --demo --no-open --port 8765 --today 2027-03-10 &
//   node tools/e2e.mjs --base http://127.0.0.1:8765
//
// Every check drives the real UI in headless Chromium. Exit code 1 if any check fails. The demo world fills in its own match pages and
// event data in the background (a few minutes); the script waits for the Premier League's current season before it checks anything
// that needs them. Pass --chromium /path/to/chrome to use a browser Playwright did not install.
import { createRequire } from "node:module";

const args = Object.fromEntries(process.argv.slice(2).reduce((acc, a, i, all) => (a.startsWith("--") ? [...acc, [a.slice(2), all[i + 1]]] : acc), []));
const base = args.base || "http://127.0.0.1:8765";

function loadPlaywright() {
  for (const root of [process.env.PLAYWRIGHT_MODULE, "/opt/node22/lib/node_modules/", process.cwd() + "/"].filter(Boolean)) {
    try { return createRequire(root)("playwright"); } catch (_) { /* next */ }
  }
  throw new Error("Playwright not found. Install it with `npm i -D playwright` or set PLAYWRIGHT_MODULE.");
}
const { chromium } = loadPlaywright();

const results = [];
let page, ctx, consoleErrors;

async function fresh(viewport = { width: 1440, height: 900 }, colorScheme = "light") {
  if (ctx) await ctx.close();
  ctx = await browser.newContext({ viewport, colorScheme });
  page = await ctx.newPage();
  consoleErrors = [];
  page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text()); });
  page.on("pageerror", (e) => consoleErrors.push(String(e)));
}

const settled = async () => {
  await page.waitForFunction(() => !document.querySelector(".skeleton, [aria-busy='true']"), null, { timeout: 30000 });
  await page.waitForTimeout(250);
};
const go = async (hash) => { await page.keyboard.press("Escape"); await page.goto(`${base}/#${hash}`); await settled(); };
const h1 = () => page.locator("h1.page-title").first().innerText();
const bodyText = () => page.locator("main").innerText();
const noBug = async () => expect(!(await bodyText()).includes("This page hit a bug"), "the page crashed: " + (await bodyText()).slice(0, 160));
/** "587 players" / "Top 10 of 27" at the head of the results bar -> the number of rows the list is about. */
const resultCount = async () => {
  const lead = (await page.locator(".results-bar").first().innerText()).split("\n")[0];
  const m = /(\d[\d,]*)\s+(?:players|teams)/.exec(lead) || /of\s+(\d[\d,]*)/.exec(lead);
  return { lead, n: m ? Number(m[1].replace(/,/g, "")) : NaN };
};

async function check(name, fn) {
  try {
    await fn();
    results.push({ name, ok: true });
    console.log(`  ok    ${name}`);
  } catch (err) {
    results.push({ name, ok: false, err });
    console.log(`  FAIL  ${name}\n        ${String(err.message || err).split("\n")[0]}`);
    if (args.debug) console.log("        page says:", JSON.stringify((await page.evaluate(() => (document.querySelector(".palette-list") || document.querySelector("main"))?.innerText.slice(0, 240))) || ""));
  }
}
const expect = (cond, msg) => { if (!cond) throw new Error(msg); };

const browser = await chromium.launch({ executablePath: args.chromium || process.env.CHROMIUM_PATH || undefined });
await fresh();

// The demo world writes its own match pages and event data in the background. Wait until the Premier League's current season has both.
console.log("Waiting for the demo world's background data (Premier League, current season)");
{
  const deadline = Date.now() + 240000;
  let ready = false;
  while (Date.now() < deadline && !ready) {
    const status = await (await page.request.get(`${base}/api/data/status`)).json();
    const epl = (status.events || []).filter((e) => e.league === "EPL").sort((a, b) => b.season - a.season)[0];
    ready = Boolean(epl && epl.status && !epl.status.running && epl.status.finished && epl.matches > 20);
    if (!ready) await page.waitForTimeout(2000);
  }
  if (!ready) { console.log("  the demo world did not finish its event data in time; checks that need it will fail"); }
}

console.log("Boot and navigation");
await check("briefing loads with findings, results with scorers, and no console errors", async () => {
  await go("/");
  expect((await h1()) === "Briefing", "H1 should be Briefing");
  expect((await page.locator(".insight").count()) >= 3, "expected at least three insight cards");
  expect((await page.locator(".mc").count()) >= 3, "expected the latest results as match cards");
  expect((await page.locator(".mc .mc-scorer").count()) >= 1, "match cards should name their scorers");
  expect(consoleErrors.length === 0, "console errors: " + consoleErrors.join(" | "));
});
await check("rail navigation reaches every section", async () => {
  for (const [label, title] of [["League", "League table"], ["Matches", "Matches"], ["Scout", "Scout"], ["Teams", "Teams"], ["Compare", "Players side by side"], ["Shortlist", "Players you are tracking"],
    ["Dictionary", "Data dictionary"], ["Guide", "Where to find things"], ["Data", "Data"], ["Briefing", "Briefing"]]) {
    await page.locator(".rail .nav-item", { hasText: label }).first().click();
    await settled();
    expect((await h1()) === title, `${label}: H1 was "${await h1()}"`);
    await noBug();
  }
});
await check("the retired forecast and method addresses still land somewhere useful", async () => {
  await go("/forecast");
  await page.waitForFunction(() => document.querySelector("h1.page-title")?.textContent === "Briefing", null, { timeout: 8000 });
  await go("/method");
  await page.waitForFunction(() => document.querySelector("h1.page-title")?.textContent === "Data dictionary", null, { timeout: 8000 });
});
await check("unknown route shows a friendly page", async () => {
  await go("/nowhere");
  expect((await page.locator("main").innerText()).includes("No such page"), "missing 404 message");
});

console.log("Search palette");
await check("Ctrl+K finds a team and opens it", async () => {
  await go("/");
  await page.keyboard.press("Control+k");
  await page.locator(".palette input").fill("everton");
  await page.locator(".palette-item", { hasText: "Everton" }).first().waitFor();
  await page.keyboard.press("Enter");
  await settled();
  expect((await h1()) === "Everton", "should land on the Everton page");
});
await check("palette finds a player by partial name and a page by its name", async () => {
  await go("/");
  await page.keyboard.press("/");
  await page.locator(".palette input").fill("milov");
  await page.locator(".palette-item", { hasText: "Luka Milović" }).first().waitFor();
  await page.locator(".palette-item", { hasText: "Luka Milović" }).first().click();
  await settled();
  expect((await h1()).includes("Milović"), "should land on the player page");
  await page.keyboard.press("Control+k");
  await page.locator(".palette input").fill("dictionary");
  await page.locator(".palette-item", { hasText: "Dictionary" }).first().waitFor();
  await page.keyboard.press("Escape");
  expect((await page.locator(".palette").count()) === 0, "Escape should close the palette");
});

console.log("League");
await check("table views and venue filter change the data", async () => {
  await go("/league");
  const first = await page.locator("table.data tbody tr").first().innerText();
  expect((await page.locator("table.data tbody tr").count()) === 20, "20 teams expected");
  await page.getByRole("button", { name: "Expected", exact: true }).click();
  await settled();
  expect(await page.locator("th", { hasText: "Pts − xPts" }).count(), "expected view should show Pts − xPts");
  await page.getByRole("button", { name: "Home", exact: true }).click();
  await settled();
  expect(page.url().includes("venue=h"), "venue should be in the URL");
  const played = await page.locator("table.data tbody tr").first().innerText();
  expect(played !== first, "home-only table should differ");
});
await check("clicking a team row opens the team page", async () => {
  await go("/league");
  await page.locator("table.data tbody tr").first().click();
  await settled();
  expect((await page.locator(".tabs button", { hasText: "Style & maps" }).count()) === 1, "team tabs missing");
});

console.log("Scout: nothing is pre-selected and every control is yours");
await check("it lists everyone, with no filter, lens or sort chosen for you", async () => {
  await go("/scout");
  const { n, lead } = await resultCount();
  expect(n > 300, "everyone should be listed: " + lead);
  expect(!page.url().includes("?"), "no filter should be in the address: " + page.url());
  const pressed = await page.locator(".filterbar .chip[aria-pressed=true]").allInnerTexts();
  expect(pressed.length === 1 && pressed[0].trim() === "All", "only the All role chip is on, saw: " + pressed.join(" | "));
  expect((await page.locator(".chip.lens[aria-pressed=true]").count()) === 0, "no lens should be on");
  expect((await page.locator(".filterbar").innerText()).includes("No filters"), "the filter bar should say nothing is filtered");
});
await check("a lens is an explained quick filter that leaves your other choices alone", async () => {
  await go("/scout");
  const all = (await resultCount()).n;
  await page.locator(".chip.lens", { hasText: "Goal threats" }).click();
  await settled();
  expect(page.url().includes("lens=goal_threats"), "the lens should be in the address");
  const lensOnly = (await resultCount()).n;
  expect(lensOnly > 5 && lensOnly < all, `the lens should narrow the list (${all} -> ${lensOnly})`);
  const panel = await page.locator(".lensbar").innerText();
  expect(/keeps players where/i.test(panel) && panel.includes("Non-penalty xG per 90"), "the lens should say which rules it applies");
  await page.locator(".filterbar .chip", { hasText: /^Attackers/ }).click();
  await settled();
  const both = (await resultCount()).n;
  expect(both > 0 && both < lensOnly, `a role on top of the lens should narrow it further (${lensOnly} -> ${both})`);
  expect(page.url().includes("lens=goal_threats") && page.url().includes("r=ATT"), "both choices should be in the address");
  await page.getByRole("button", { name: "Switch off" }).first().click();
  await settled();
  expect(!page.url().includes("lens=") && page.url().includes("r=ATT"), "switching the lens off should keep the role");
});
await check("a metric filter, the profile filter and Top N each narrow the list on their own", async () => {
  await go("/scout?f=npxg90>=p80");
  const rule = await resultCount();
  expect(rule.n > 20 && rule.n < 200, "a top-20% npxG rule should keep a fifth or so: " + rule.lead);
  expect((await page.locator(".fchip", { hasText: "npxG/90" }).count()) === 1, "the rule should show as a chip");
  await go("/scout?tag=poacher");
  const tagged = await page.locator("table.data tbody tr").evaluateAll((rows) => rows.map((r) => r.innerText.includes("Poacher")));
  expect(tagged.length > 3 && tagged.every(Boolean), "every row should carry the Poacher tag");
  await go("/scout?top=10");
  expect((await page.locator("table.data tbody tr").count()) === 10, "Top 10 should show ten rows");
  expect((await resultCount()).lead.startsWith("Top 10 of"), "the results bar should say it is the top ten");
});
await check("any metric can be a column and a sort, blanks never sort as zero", async () => {
  await go("/scout?cols=defending&sort=tackles90");
  const heads = await page.locator("table.data thead th").allInnerTexts();
  expect(heads.some((t) => t.startsWith("Tackles/90")) && heads.some((t) => t.startsWith("Int/90")), "the defending columns should be shown: " + heads.join(" | ").slice(0, 200));
  expect((await page.locator("table.data thead th.sorted").innerText()).startsWith("Tackles/90"), "the table should be sorted by tackles");
  expect((await page.locator(".results-bar").first().innerText()).includes("By Tackles per 90, highest first"), "the results bar should say how the list is sorted");
  expect((await page.locator('select[aria-label="Sort by"]').inputValue()) === "tackles90", "the sort menu should show it too");
  await page.locator("table.data thead th", { hasText: "Tackle %" }).first().click();    // a click on any heading re-sorts by it
  await settled();
  expect(!page.url().includes("sort=tackles90") && page.url().includes("sort="), "clicking another heading should change the sort: " + page.url());
});
await check("player rows carry event metrics once event data is stored", async () => {
  await go("/scout?cols=passing");
  const cells = await page.locator("table.data tbody tr").evaluateAll((rows) => rows.slice(0, 40).map((r) => r.innerText));
  expect(cells.some((t) => /\d+%/.test(t)), "pass accuracy should have values for players with event data");
});
await check("text search narrows the list and a role chip and reset bring it back", async () => {
  await go("/scout");
  const everyone = (await resultCount()).n;
  await page.getByPlaceholder("Search by player or club").fill("everton");
  await page.waitForTimeout(500);
  const teams = await page.locator("table.data tbody tr .cell-player .sub").allInnerTexts();
  expect(teams.length > 3 && teams.every((t) => t.startsWith("Everton")), "search should keep Everton players only");
  await page.getByRole("button", { name: /Clear all|Reset/ }).first().click();
  await settled();
  expect((await resultCount()).n === everyone, "clearing should bring everyone back");
});
await check("the map draws every player in the selection and honours Top N", async () => {
  await go("/scout?view=map");
  await page.waitForSelector(".chart svg circle");
  expect((await page.locator(".chart svg .dot-mark").count()) > 100, "expected a dot for most players");
  await go("/scout?view=map&top=20");
  expect((await page.locator(".chart svg .dot-mark").count()) <= 20, "Top 20 should limit the map as well as the table");
});
await check("ticking two players enables Compare", async () => {
  await go("/scout");
  await page.locator("table.data tbody tr input[type=checkbox]").nth(0).check();
  await page.locator("table.data tbody tr input[type=checkbox]").nth(1).check();
  await page.locator(".tray").getByRole("button", { name: /Compare 2/ }).click();
  await settled();
  expect(page.url().includes("/compare?ids="), "should be on compare");
  expect((await page.locator(".cmp-head").count()) === 2, "two player cards expected");
});
await check("age filter narrows to known ages", async () => {
  await go("/scout?age=16-22&unk=0");
  const subs = await page.locator("table.data tbody tr .cell-player .sub").allInnerTexts();
  expect(subs.length > 0, "some young players expected in the demo world");
  expect(subs.every((t) => Number(t.split(" · ").pop()) <= 22), "everyone should be 22 or younger: " + subs.slice(0, 3).join(" | "));
});

console.log("Teams: the same explorer, one level up");
await check("every team is listed, lenses explain themselves, and event measures are filled in", async () => {
  await go("/teams");
  expect((await resultCount()).n === 20, "20 teams expected");
  await page.locator(".chip.lens", { hasText: "High press" }).click();
  await settled();
  const pressing = (await resultCount()).n;
  expect(pressing > 0 && pressing < 20, "the lens should keep some of the teams: " + pressing);
  expect(page.url().includes("lens="), "the lens should be in the address");
  await go("/teams?cols=possession&sort=poss");
  const poss = await page.locator("table.data tbody tr").evaluateAll((rows) => rows.slice(0, 20).map((r) => r.innerText));
  expect(poss.filter((t) => /\d+%/.test(t)).length >= 15, "possession should be known for the teams with event data");
});
await check("the team map plots all twenty and a row opens the team", async () => {
  await go("/teams?view=map");
  await page.waitForSelector(".chart svg circle");
  expect((await page.locator(".chart svg .dot-mark").count()) === 20, "20 dots expected");
  await go("/teams");
  await page.locator("table.data tbody tr").first().click();
  await settled();
  expect(page.url().includes("/team/"), "should open a team page");
});

console.log("Team page");
await check("every tab opens", async () => {
  await go("/team/Arsenal");
  for (const tab of ["Players", "Style & maps", "Chances", "Matches", "History", "Overview"]) {
    await page.locator(".tabs button", { hasText: tab }).first().click();
    await settled();
    await noBug();
    expect((await page.locator("main .card").count()) >= 1, `${tab}: no content`);
  }
});
await check("style & maps draws every layer from the stored events", async () => {
  await go("/team/Arsenal?tab=maps");
  await page.waitForSelector(".maplab svg");
  for (const layer of ["Touches", "Passes", "Pass network", "Defending", "Carries", "Take-ons", "Shots", "Goalkeeper"]) {
    await page.locator(".maplab-tabs button", { hasText: new RegExp(`^${layer}$`) }).click();
    await page.waitForTimeout(200);
    await noBug();
    expect((await page.locator(".maplab svg").count()) >= 1, `${layer}: nothing drawn`);
  }
  expect((await bodyText()).toLowerCase().includes("attacking left to right"), "the maps should say which way they attack");
});
await check("chances tab: one chart area with toggles, and the chart changes", async () => {
  await go("/team/Arsenal?tab=chances");
  expect((await page.locator(".chart-toggles button").count()) >= 8, "the break-downs and the chart types should be toggles");
  const before = await page.locator("main").innerHTML();
  await page.locator(".chart-toggles button", { hasText: "Versus the league" }).click();
  await settled();
  expect((await page.locator("main").innerHTML()) !== before, "choosing another chart should redraw it");
  await page.locator(".chart-toggles button", { hasText: "Timing" }).click();
  await settled();
  await noBug();
});
await check("players tab lists the squad with metrics", async () => {
  await go("/team/Arsenal?tab=players");
  expect((await page.locator("table.data tbody tr").count()) >= 15, "the squad should be listed");
});
await check("manager stints render as a table when managers.json has them", async () => {
  await page.route("**/api/team?*", async (route) => {
    const res = await route.fetch();
    const body = await res.json();
    body.profile.eras = [
      { manager: "Test Manager A", start: "2026-08-01", end: "2026-11-30", played: 12, pts_pg: 1.5, xpts_pg: 1.6, xg_pg: 1.7, xga_pg: 1.3, xgd_pg: 0.4 },
      { manager: "Test Manager B", start: "2026-12-01", end: null, played: 18, pts_pg: 1.1, xpts_pg: 1.5, xg_pg: 1.5, xga_pg: 1.5, xgd_pg: 0.0 },
    ];
    await route.fulfill({ response: res, json: body });
  });
  await go("/team/Everton");
  // the page may draw a stored copy first and then the answer it asked for (the one with the stints): wait for that, instead of reading at once
  await page.waitForFunction(() => /Test Manager A/.test(document.querySelector("main")?.innerText || ""), null, { timeout: 15000 });
  const text = await page.locator("main").innerText();
  expect(text.includes("Test Manager A") && text.includes("Test Manager B") && text.includes("now"), "manager table missing");
  await page.unroute("**/api/team?*");
});

console.log("Player");
await check("profile, every-metric search, maps, match log, finishing, similar players", async () => {
  await go("/player/100844");
  expect((await page.locator(".pbar").count()) >= 6, "percentile bars missing");
  await page.getByPlaceholder("Find a metric").fill("tackle");
  await page.waitForTimeout(300);
  expect((await bodyText()).toLowerCase().includes("tackles per 90"), "the metric search should find the tackle metrics");
  await page.locator(".tabs button", { hasText: "Maps" }).click();
  await settled();
  await page.waitForSelector(".maplab svg");
  await page.locator(".tabs button", { hasText: "Match log" }).click();
  await settled();
  expect((await page.locator("table.data tbody tr").count()) > 5, "match log rows missing");
  await page.locator(".tabs button", { hasText: "Finishing" }).click();
  await settled();
  expect((await page.locator(".shotmap svg circle.shot").count()) > 20, "shots missing");
  expect((await page.locator("svg[aria-label^='Chance of each possible goal tally'] rect").count()) > 5, "distribution bars missing");
  await page.locator(".tabs button", { hasText: "Similar" }).click();
  await settled();
  expect((await page.locator(".similar").count()) >= 4, "similar players missing");
});
await check("the (i) beside a metric explains it and reads where he stands", async () => {
  await go("/player/100844");
  await page.locator(".metric-table .info").first().hover();
  await page.waitForFunction(() => (document.querySelector(".tooltip.on")?.innerText || "").length > 80, null, { timeout: 5000 });
  const tip = await page.locator(".tooltip.on").innerText();
  expect(/Minutes/.test(tip) && /Where he stands/.test(tip) && /Better than \d+ of every 100 attackers/.test(tip), "the tooltip should explain the metric and read the bar: " + tip.slice(0, 160));
});
await check("the percentile bars say who he is compared with and what a bar means", async () => {
  await go("/player/100844");
  const key = await page.locator(".bar-key").innerText();
  expect(/the \d+ attackers in the Premier League who have played at least \d+ minutes/.test(key), "who he is compared with: " + key.slice(0, 200));
  expect(/full bar is the best of them/.test(key) && /Grey bars/.test(key) && /flipped/.test(key), "what the bar means: " + key.slice(0, 300));
  expect((await page.locator(".metric-table th.bar-col").innerText()).includes("Where he stands among the"), "the column should say who the bar compares him with");
  expect((await page.locator(".pbars .pbar-axis").count()) === 1, "the profile card should carry the scale (lowest, typical, best)");
  const card = await page.locator(".card", { hasText: "Against attackers" }).first().innerText();
  expect(/better than \d+ of every 100/.test(card), "the card should say what a number means: " + card.slice(0, 200));
});

console.log("Player: match trend");
await check("match trend: the chart, the lines, and the opponent behind each match", async () => {
  await go("/player/100844?tab=trend");
  await page.waitForSelector(".trend-chart svg");
  expect((await page.locator(".trend-chart .mark").count()) >= 20, "a mark for each match he played");
  expect((await page.locator(".trend-chart .trend-line").count()) === 2, "the season line and the form line");
  expect((await page.locator(".trend-chart .slot-label").count()) >= 25, "every match should be labelled with its opponent");
  await page.locator(".trend-chart rect.hit").nth(7).hover();
  await page.waitForFunction(() => /by expected points/.test(document.querySelector(".tooltip.on")?.innerText || ""), null, { timeout: 5000 });
  const tip = await page.locator(".tooltip.on").innerText();
  expect(/Matchweek \d+/.test(tip) && /Season so far/.test(tip) && /(top|middle|bottom)-third side/.test(tip), "the tooltip should name the match, the season figure and how strong the opponent was: " + tip.slice(0, 220));
  const reads = await page.locator(".reads .read").allInnerTexts();
  expect(reads.length >= 2, "what stands out should say something: " + reads.join(" | "));
  expect((await page.locator("table.splits tbody tr").count()) >= 7, "who he played: three tiers, home and away");
  expect((await page.locator("table.data:not(.splits) tbody tr").count()) >= 25, "every match should be listed");
});
await check("match trend: metric, quick picks, colouring, season and the match report", async () => {
  await go("/player/100844?tab=trend");
  await page.waitForSelector(".trend-chart svg");
  await page.locator("main select[aria-label='Metric']").selectOption("pass_acc");
  await page.waitForFunction(() => [...document.querySelectorAll("h2.card-title")].some((h) => h.innerText.includes("Pass accuracy")), null, { timeout: 10000 });
  expect((await page.locator(".trend-chart .mark.dot").count()) >= 10, "a share is drawn as dots, not as bars from zero");
  expect(page.url().includes("tm=pass_acc"), "the metric should be in the address: " + page.url());
  await page.locator(".quick .chip").first().click();
  await page.waitForFunction(() => document.querySelector(".quick .chip")?.getAttribute("aria-pressed") === "true", null, { timeout: 5000 });
  expect((await page.locator(".trend-chart rect.mark").count()) >= 10, "a rate is drawn as bars");
  await page.locator(".segmented button", { hasText: "Home or away" }).click();
  await page.waitForFunction(() => /Venue/.test(document.querySelector(".trend-legend")?.innerText || ""), null, { timeout: 5000 });
  await page.locator("main select[aria-label='Season']").selectOption("2025");
  await page.waitForFunction(() => document.querySelector("main").innerText.includes("through the 2025/26 season"), null, { timeout: 15000 });
  expect((await page.locator(".trend-chart .slot-label").count()) >= 36, "last season has its own matches");
  await page.locator(".trend-chart rect.hit.go").nth(3).click();
  await page.waitForFunction(() => location.hash.startsWith("#/match/"), null, { timeout: 5000 });
});
await check("match trend: arrow keys walk the matches and show each one", async () => {
  await go("/player/100844?tab=trend");
  await page.waitForSelector(".trend-chart svg");
  await page.locator(".trend-scroll").focus();
  await page.keyboard.press("ArrowLeft");
  await page.waitForFunction(() => /Matchweek/.test(document.querySelector(".tooltip.on")?.innerText || ""), null, { timeout: 5000 });
  const last = await page.locator(".tooltip.on").innerText();
  await page.keyboard.press("ArrowLeft");
  await page.waitForTimeout(200);
  expect((await page.locator(".tooltip.on").innerText()) !== last, "the left arrow should move to the previous match");
});
await check("a metric in the profile table opens its match-by-match trend", async () => {
  await go("/player/100844");
  const skipped = page.locator(".metric-table tr", { hasText: "Appearances" }).first();
  expect((await skipped.locator(".trend-link").count()) === 0, "a season-long metric has no match-by-match view");
  await page.locator(".metric-table tr", { hasText: "Non-penalty xG per 90" }).first().locator(".trend-link").click();
  await page.waitForSelector(".trend-chart svg");
  expect(page.url().includes("tab=trend") && page.url().includes("tm=npxg90"), "the link should open that metric's trend: " + page.url());
  expect((await page.locator("h2.card-title", { hasText: "Non-penalty xG per 90" }).count()) >= 1, "the chart should be about that metric");
});
await check("match trend: a season with nothing stored says so instead of drawing nothing", async () => {
  await go("/player/100844?tab=trend&ts=2024");
  await page.waitForFunction(() => /Nothing to draw yet/.test(document.querySelector("main").innerText), null, { timeout: 15000 });
  expect((await page.locator("main select[aria-label='Season']").count()) === 1, "the season choice must stay, so there is a way back");
});
await check("shortlist: star, note, persist, remove", async () => {
  await go("/player/100844");
  const star = page.locator(".page-actions .star");
  if ((await star.getAttribute("aria-pressed")) === "true") await star.click();
  await star.click();
  await page.waitForFunction(() => document.querySelector(".page-actions .star")?.getAttribute("aria-pressed") === "true", null, { timeout: 5000 });
  await go("/shortlist");
  const note = page.getByLabel("Note on Luka Milović");
  await note.fill("e2e note");
  await page.waitForTimeout(900);
  await page.reload();
  await settled();
  expect((await page.getByLabel("Note on Luka Milović").inputValue()) === "e2e note", "note should persist");
  await page.getByLabel("Remove Luka Milović").first().click();
  await page.waitForTimeout(400);
  expect((await page.locator("main").innerText()).includes("Nobody yet") || (await page.getByLabel("Note on Luka Milović").count()) === 0, "player should be removed");
});

console.log("Compare, matches");
await check("team compare shows both teams, their style and the head to head", async () => {
  await go("/compare?mode=teams&a=Everton&b=Arsenal");
  expect((await page.locator(".pdot-row").count()) >= 6, "profile rows missing");
  const text = await bodyText();
  expect(text.includes("Head to head") && text.includes("Style compared"), "head to head or style comparison missing");
});
await check("matches: day-grouped cards with scorers, round navigation and flagged results", async () => {
  await go("/matches");
  expect((await page.locator(".day-title").count()) >= 2, "matches should be grouped by day");
  expect((await page.locator(".mc").count()) >= 8, "a matchweek of cards expected");
  expect((await page.locator(".mc .mc-scorer").count()) >= 1, "scorers should be on the cards");
  const stats = await page.locator(".mc .mc-stats").first().innerText();
  expect(/XG/i.test(stats) && /POSSESSION/i.test(stats) && /SHOTS/i.test(stats), "cards should show xG, possession and shots: " + stats.replace(/\n/g, " "));
  const before = await page.locator(".mc").first().innerText();
  await page.getByRole("button", { name: "Previous matchweek" }).click();
  await settled();
  expect((await page.locator(".mc").first().innerText()) !== before, "previous round should change the cards");
  await page.getByRole("button", { name: /Results that lied/ }).click();
  await settled();
  expect((await page.locator(".mc.flagged").count()) > 3, "flagged matches expected");
});
await check("match report: scoreboard with scorers, xG race, shot map and how the game was played", async () => {
  await go("/matches");
  await page.locator("a.mc").first().click();
  await settled();
  expect((await page.locator(".scoreboard").count()) === 1, "scoreboard missing");
  expect((await page.locator("svg[aria-label^='Cumulative xG']").count()) === 1, "xG race missing");
  expect((await page.locator(".shotmap svg circle.shot").count()) > 4, "shots missing");
  expect((await bodyText()).includes("How the game was played"), "the event-data card is missing");
});

console.log("Dictionary, guide, data");
await check("dictionary: search finds a metric and every section opens", async () => {
  await go("/dictionary");
  await page.getByPlaceholder(/Search \d+ metrics/).fill("tackle");
  await page.waitForTimeout(300);
  expect((await bodyText()).toLowerCase().includes("tackles per 90"), "searching should find tackles per 90");
  for (const tab of ["Raw data", "Events and qualifiers", "Profiles and lenses", "How to read the numbers", "Metrics"]) {
    await page.locator(".tabs button", { hasText: tab }).click();
    await settled();
    await noBug();
  }
  await page.locator(".tabs button", { hasText: "Profiles and lenses" }).click();
  await settled();
  expect((await bodyText()).includes("Poacher") && (await bodyText()).includes("Goal threats"), "tags and lenses should be explained");
});
await check("guide opens", async () => {
  await go("/guide");
  await noBug();
  expect((await page.locator("main .card").count()) >= 3, "guide cards missing");
});
await check("data page: sources, coverage and event data are shown, nothing crashes while the demo fills in", async () => {
  await go("/data");
  await noBug();
  const text = await bodyText();
  expect(text.includes("Demo world"), "demo source tile missing");
  expect(text.includes("What is on this computer") && text.includes("Event data: what is stored"), "coverage and event cards missing");
  expect((await page.locator("main table.data tbody tr").count()) >= 1, "coverage table empty");
});

console.log("Scope and theme");
await check("changing the season reloads the briefing for a finished year", async () => {
  await go("/");
  const season = page.locator('select[aria-label="Season"]');
  await season.selectOption("2025");
  await page.waitForFunction(() => document.querySelector(".page-sub")?.textContent.includes("won the 2025/26 title"), null, { timeout: 30000 });
  await season.selectOption("auto");
  await settled();
});
await check("theme toggle cycles light, dark and system", async () => {
  await go("/");
  const btn = page.locator(".topbar button[title^='Theme']");
  const seen = new Set();
  const current = () => page.evaluate(() => document.documentElement.dataset.theme || "system");
  for (let i = 0; i < 3; i++) {
    const before = await current();
    await btn.click();
    await page.waitForFunction((b) => (document.documentElement.dataset.theme || "system") !== b, before, { timeout: 5000 });
    seen.add(await current());
  }
  expect(seen.has("light") && seen.has("dark") && seen.has("system"), "themes seen: " + [...seen].join(","));
});

console.log("Accessibility basics");
const AUDIT = () => {
  const name = (el) => (el.getAttribute("aria-label") || el.getAttribute("aria-labelledby") || el.innerText || el.textContent || el.title || "").trim();
  const bad = [];
  for (const b of document.querySelectorAll("button, [role=button]")) if (!name(b)) bad.push(`a button with no name (${b.className})`);
  for (const i of document.querySelectorAll("input, select, textarea")) {
    const lab = i.id && document.querySelector(`label[for="${i.id}"]`);
    if (!(i.getAttribute("aria-label") || i.getAttribute("aria-labelledby") || lab || i.closest("label") || i.title)) bad.push(`a ${i.type || i.tagName} with no label (${i.placeholder || i.className})`);
  }
  for (const a of document.querySelectorAll("a")) if (!name(a)) bad.push(`a link with no text (${a.getAttribute("href")})`);
  for (const s of document.querySelectorAll("svg[role=img]")) if (!(s.getAttribute("aria-label") || s.querySelector("title"))) bad.push("a chart with no description");
  const ids = new Set();
  for (const e of document.querySelectorAll("[id]")) { if (ids.has(e.id)) bad.push(`a repeated id (${e.id})`); ids.add(e.id); }
  const levels = [...document.querySelectorAll("h1,h2,h3,h4")].map((h) => Number(h.tagName[1]));
  for (let i = 1; i < levels.length; i++) if (levels[i] - levels[i - 1] > 1) bad.push(`a heading level skipped (h${levels[i - 1]} to h${levels[i]})`);
  if (document.querySelectorAll("h1").length !== 1) bad.push("the page should have exactly one h1");
  return bad;
};
for (const route of ["/", "/league", "/matches", "/scout", "/teams", "/team/Arsenal", "/team/Arsenal?tab=maps", "/player/100844", "/player/100844?tab=trend", "/compare?mode=teams&a=Everton&b=Arsenal", "/dictionary", "/guide", "/data", "/shortlist"]) {
  await check(`controls are labelled and headings are in order: ${route}`, async () => {
    await go(route);
    const bad = await page.evaluate(AUDIT);
    expect(bad.length === 0, bad.slice(0, 4).join("; "));
  });
}

console.log("Phone layout");
await fresh({ width: 390, height: 844 });
for (const route of ["/", "/league", "/matches", "/scout", "/scout?view=map", "/teams", "/team/Everton", "/team/Everton?tab=maps", "/player/100844", "/player/100844?tab=trend", "/match/10260292", "/dictionary", "/data"]) {
  await check(`no horizontal scroll at 390px: ${route}`, async () => {
    await go(route);
    const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(over <= 1, `page overflows by ${over}px`);
    expect((await page.locator(".rail").isVisible()), "bottom navigation missing");
  });
}

await browser.close();
const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
process.exit(failed.length ? 1 : 0);

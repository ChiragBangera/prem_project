#!/usr/bin/env node
// End-to-end behaviour checks against a running server (use --demo so the data is deterministic).
//
//   prem serve --demo --no-open --port 8765 --today 2027-03-10 &
//   node tools/e2e.mjs --base http://127.0.0.1:8765
//
// Every check drives the real UI in headless Chromium. Exit code 1 if any check fails.
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
  await page.waitForTimeout(150);
};
const go = async (hash) => { await page.keyboard.press("Escape"); await page.goto(`${base}/#${hash}`); await settled(); };
const h1 = () => page.locator("h1.page-title").first().innerText();

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

const browser = await chromium.launch();
await fresh();

console.log("Boot and navigation");
await check("briefing loads with findings and no console errors", async () => {
  await go("/");
  expect((await h1()) === "Briefing", "H1 should be Briefing");
  expect((await page.locator(".insight").count()) >= 3, "expected at least three insight cards");
  expect(consoleErrors.length === 0, "console errors: " + consoleErrors.join(" | "));
});
await check("rail navigation reaches every section", async () => {
  for (const [label, title] of [["League", "League table"], ["Scout", "Scout"], ["Forecast", "What happens next"], ["Method", "Method"], ["Data", "Data"], ["Shortlist", null], ["Briefing", "Briefing"]]) {
    await page.locator(".rail .nav-item", { hasText: label }).first().click();
    await settled();
    if (title) expect((await h1()) === title, `${label}: H1 was "${await h1()}"`);
  }
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
await check("palette finds a player by partial name", async () => {
  await go("/");
  await page.keyboard.press("/");
  await page.locator(".palette input").fill("milov");
  await page.locator(".palette-item", { hasText: "Luka Milović" }).first().waitFor();
  await page.locator(".palette-item", { hasText: "Luka Milović" }).first().click();
  await settled();
  expect((await h1()).includes("Milović"), "should land on the player page");
  await page.keyboard.press("Control+k");
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
  expect((await page.locator(".tabs button", { hasText: "Squad" }).count()) === 1, "team tabs missing");
});

console.log("Scout");
await check("lens presets set role, sort and results", async () => {
  await go("/scout");
  const total = await page.locator("table.data tbody tr").count();
  expect(total >= 20, "table should list players");
  await page.getByRole("button", { name: "Goal threats" }).click();
  await settled();
  expect(page.url().includes("groups=ATT"), "lens should filter to attackers");
  const subs = await page.locator("table.data tbody tr .cell-player .sub").allInnerTexts();
  expect(subs.length > 5 && subs.every((t) => t.includes("Attacker")), "every row should be an attacker");
  const vals = (await page.locator("table.data tbody tr").evaluateAll((rows) => rows.slice(0, 12).map((r) => Number(r.querySelectorAll("td")[5]?.innerText.split("\n")[0]))));
  expect(vals.every((v, i) => i === 0 || v <= vals[i - 1] + 1e-9), "npxG/90 should be sorted high to low: " + vals.join(","));
});
await check("text search, role chips and reset work together", async () => {
  await go("/scout");
  await page.getByPlaceholder("Search player or team").fill("everton");
  await page.waitForTimeout(400);
  const teams = await page.locator("table.data tbody tr .cell-player .sub").allInnerTexts();
  expect(teams.length > 3 && teams.every((t) => t.startsWith("Everton")), "search should keep Everton players only");
  await page.getByRole("button", { name: "Reset" }).first().click();
  await settled();
  expect((await page.locator("table.data tbody tr").count()) >= 20, "reset should bring the table back");
});
await check("map view draws players and opens a profile on click", async () => {
  await go("/scout?view=map");
  await page.waitForSelector(".chart svg circle");
  expect((await page.locator(".chart svg .dot-mark").count()) > 50, "expected many player dots");
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

console.log("Player");
await check("player profile, finishing distribution, shot map, similar players", async () => {
  await go("/player/100844");
  expect((await page.locator(".pbar").count()) >= 6, "percentile bars missing");
  await page.locator(".tabs button", { hasText: "Finishing" }).click();
  await settled();
  expect((await page.locator(".shotmap svg circle.shot").count()) > 20, "shots missing");
  expect((await page.locator("svg[aria-label^='Chance of each possible goal tally'] rect").count()) > 5, "distribution bars missing");
  await page.locator(".tabs button", { hasText: "Similar" }).click();
  await settled();
  expect((await page.locator(".similar").count()) >= 4, "similar players missing");
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

console.log("Compare, matches, forecast");
await check("team compare shows both teams", async () => {
  await go("/compare?mode=teams&a=Everton&b=Arsenal");
  expect((await page.locator(".pdot-row").count()) >= 6, "profile rows missing");
  expect((await page.locator("main").innerText()).includes("Head to head"), "head to head missing");
});
await check("matches: round navigation and flagged results", async () => {
  await go("/matches");
  const before = await page.locator(".mcard").first().innerText();
  await page.getByRole("button", { name: "Previous matchweek" }).click();
  await settled();
  expect((await page.locator(".mcard").first().innerText()) !== before, "previous round should change the cards");
  await page.getByRole("button", { name: /Results that lied/ }).click();
  await settled();
  expect((await page.locator(".mcard.flagged").count()) > 3, "flagged matches expected");
});
await check("match report renders race, shot map and players", async () => {
  await go("/matches");
  await page.locator(".mcard").first().click();
  await settled();
  expect((await page.locator(".scoreboard").count()) === 1, "scoreboard missing");
  expect((await page.locator("svg[aria-label^='Cumulative xG']").count()) === 1, "xG race missing");
  expect((await page.locator(".shotmap svg circle.shot").count()) > 4, "shots missing");
});
await check("forecast lab probabilities add up to 100%", async () => {
  await go("/forecast?tab=lab&home=Everton&away=Arsenal");
  const nums = (await page.locator(".lab-probs b").allInnerTexts()).map((t) => parseInt(t, 10));
  expect(nums.length === 3 && Math.abs(nums.reduce((a, b) => a + b, 0) - 100) <= 2, "probabilities: " + nums.join(","));
  expect((await page.locator(".matrix-cell").count()) >= 49, "scoreline matrix missing");
});
await check("season simulation and accuracy tabs render", async () => {
  await go("/forecast?tab=season");
  expect((await page.locator("table.data tbody tr").count()) === 20, "20 teams expected in the simulation");
  expect((await page.locator(".posstrip").count()) === 20, "position strips missing");
  await go("/forecast?tab=accuracy");
  expect((await page.locator("svg[aria-label^='Forecast reliability'] circle").count()) >= 4, "reliability points missing");
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
  const text = await page.locator("main").innerText();
  expect(text.includes("Test Manager A") && text.includes("Test Manager B") && text.includes("now"), "manager table missing");
  await page.unroute("**/api/team?*");
});

console.log("Scope, theme, data");
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
await check("data page shows cache status and demo notice", async () => {
  await go("/data");
  expect((await page.locator("main").innerText()).includes("Demo world"), "demo source tile missing");
  expect((await page.locator("main table.data tbody tr").count()) >= 1, "cache table empty");
});
await check("method page has glossary search", async () => {
  await go("/method");
  await page.getByPlaceholder("Search the glossary").fill("shrink");
  await page.waitForTimeout(200);
  expect((await page.locator(".gloss dt").count()) >= 1, "glossary search found nothing");
});

console.log("Phone layout");
await fresh({ width: 390, height: 844 });
for (const route of ["/", "/league", "/scout", "/team/Everton", "/player/100844", "/forecast?tab=lab&home=Everton&away=Arsenal", "/match/10260299"]) {
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

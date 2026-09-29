#!/usr/bin/env node
// Visual smoke test: opens routes in headless Chromium, records console errors and failed API calls,
// and writes screenshots. Used to review the UI end to end.
//
//   node tools/shoot.mjs --base http://127.0.0.1:8000 --routes "/;/league;/scout" --theme light,dark --size 1440x900,390x844
//
// Playwright is resolved from the local install, PLAYWRIGHT_MODULE, or the global npm root.
import { createRequire } from "node:module";
import { mkdirSync } from "node:fs";
import { join } from "node:path";

const args = Object.fromEntries(
  process.argv.slice(2).reduce((acc, a, i, all) => (a.startsWith("--") ? [...acc, [a.slice(2), all[i + 1] && !all[i + 1].startsWith("--") ? all[i + 1] : "true"]] : acc), []),
);

const base = args.base || "http://127.0.0.1:8000";
const out = args.out || "shots";
const routes = (args.routes || "/").split(";").map((r) => r.trim()).filter(Boolean);
const themes = (args.theme || "light").split(",");
const sizes = (args.size || "1440x900").split(",").map((s) => s.split("x").map(Number));
const full = args.full !== "false";
const settle = Number(args.settle || 700);
const maxh = Number(args.maxh || 0); // clip tall pages, e.g. --maxh 1800, so screenshots stay readable
const yOffset = Number(args.y || 0);

function loadPlaywright() {
  const candidates = [process.env.PLAYWRIGHT_MODULE, "/opt/node22/lib/node_modules/", process.cwd() + "/"].filter(Boolean);
  for (const root of candidates) {
    try { return createRequire(root)("playwright"); } catch (_) { /* try next */ }
  }
  throw new Error("Playwright not found. Install it with `npm i -D playwright` or set PLAYWRIGHT_MODULE.");
}

const { chromium } = loadPlaywright();
mkdirSync(out, { recursive: true });

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined });
let problems = 0;

for (const [width, height] of sizes) {
  for (const theme of themes) {
    const ctx = await browser.newContext({
      viewport: { width, height },
      colorScheme: theme === "dark" ? "dark" : "light",
      deviceScaleFactor: 1,
    });
    await ctx.addInitScript((t) => {
      try { localStorage.setItem("prem.ui.v1", JSON.stringify({ theme: t, league: "EPL", season: "auto" })); } catch (_) { /* ignore */ }
    }, theme);
    const page = await ctx.newPage();
    const errors = [];
    page.on("console", (m) => { if (m.type() === "error") errors.push("console: " + m.text()); });
    page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
    page.on("response", (r) => { if (r.status() >= 400 && r.url().includes("/api/")) errors.push(`HTTP ${r.status()} ${r.url().replace(base, "")}`); });
    page.on("requestfailed", (r) => { if (!r.url().includes("favicon")) errors.push("requestfailed: " + r.url().replace(base, "")); });

    for (const route of routes) {
      errors.length = 0;
      await page.goto(base + "/#" + route, { waitUntil: "networkidle" });
      await page.waitForFunction(() => !document.querySelector(".skeleton, [aria-busy='true']"), null, { timeout: 60000 }).catch(() => errors.push("timeout: skeleton still visible"));
      await page.waitForTimeout(settle);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      if (overflow > 1) {
        const culprits = await page.evaluate(() => {
          const vw = document.documentElement.clientWidth;
          return [...document.querySelectorAll("body *")]
            .filter((el) => el.getBoundingClientRect().right > vw + 1 && !el.closest(".table-wrap, .tabs, .chart-table, .palette-list"))
            .slice(0, 6)
            .map((el) => `${el.tagName.toLowerCase()}.${String(el.className && el.className.baseVal !== undefined ? el.className.baseVal : el.className).split(" ").join(".")} → right ${Math.round(el.getBoundingClientRect().right)}`);
        });
        errors.push(`horizontal overflow: ${overflow}px\n       ${culprits.join("\n       ")}`);
      }
      const name = `${route.replace(/[^a-z0-9]+/gi, "_").replace(/^_|_$/g, "") || "home"}__${theme}_${width}`;
      if (maxh) {
        const total = await page.evaluate(() => document.documentElement.scrollHeight);
        await page.screenshot({ path: join(out, name + ".png"), fullPage: true, clip: { x: 0, y: Math.min(yOffset, Math.max(0, total - 100)), width, height: Math.min(maxh, total - yOffset) } });
      } else {
        await page.screenshot({ path: join(out, name + ".png"), fullPage: full });
      }
      const flag = errors.length ? "  !! " + errors.join("\n     ") : "";
      if (errors.length) problems += 1;
      console.log(`${errors.length ? "FAIL" : "ok  "} ${theme.padEnd(5)} ${String(width).padStart(4)}  ${route}${flag}`);
    }
    await ctx.close();
  }
}
await browser.close();
process.exit(problems ? 1 : 0);

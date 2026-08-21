// QA evidence capture — drives the live app at 127.0.0.1:8000 and screenshots
// every tab with real data at desktop (1440x900) and mobile (375x812).
// Read-only QA tooling: does not modify product code.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE = 'http://127.0.0.1:8000/dashboard/';
const OUT = path.join(__dirname, '..', 'screenshots');
if (!fs.existsSync(OUT)) fs.mkdirSync(OUT, { recursive: true });

const report = { checks: [], consoleErrors: [], pageErrors: [], failedRequests: [] };

function check(name, ok, detail) {
  report.checks.push({ name, ok, detail: detail || '' });
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? ' — ' + detail : ''}`);
}

async function waitWithRetry(page, sel, clickSel, attempts = 3, timeout = 60000) {
  for (let i = 1; i <= attempts; i++) {
    try {
      await page.waitForSelector(sel, { state: 'visible', timeout });
      return;
    } catch (e) {
      console.log(`retry ${i}/${attempts} for ${sel}`);
      if (i === attempts) throw e;
      if (clickSel) { try { await page.click(clickSel); } catch (e2) {} }
    }
  }
}

async function settle(page, ms = 1200) {
  try { await page.waitForLoadState('networkidle', { timeout: 15000 }); } catch (e) {}
  await page.waitForTimeout(ms);
}

async function shot(page, name) {
  await page.screenshot({ path: path.join(OUT, name), fullPage: true });
  console.log(`SHOT ${name}`);
}

// Count elements matching selector; returns -1 if none
async function count(page, sel) {
  return page.locator(sel).count();
}

(async () => {
  const browser = await chromium.launch();

  const mk = async (w, h) => {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 2 });
    const page = await ctx.newPage();
    page.on('console', (m) => { if (m.type() === 'error') report.consoleErrors.push(`[${w}] ${m.text()}`); });
    page.on('pageerror', (e) => report.pageErrors.push(`[${w}] ${e.message}`));
    page.on('requestfailed', (r) => report.failedRequests.push(`[${w}] ${r.method()} ${r.url()} :: ${r.failure() && r.failure().errorText}`));
    return page;
  };

  const d = await mk(1440, 900);
  const m = await mk(375, 812);

  // ---------------------------------------------------------------- 1. PLAYER
  async function openTab(page, tab) {
    // The app routes via .nav-item clicks / popstate only — a same-document
    // goto('#x') does NOT activate the view. Click the sidebar item.
    await page.goto(BASE, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector(`.sidebar-nav .nav-item[data-tab="${tab}"]`, { timeout: 30000 });
    await page.click(`.sidebar-nav .nav-item[data-tab="${tab}"]`);
    await page.waitForSelector(`#view-${tab}.active`, { timeout: 15000 });
  }

  async function doPlayer(page, tag) {
    await openTab(page, 'player');
    await page.fill('#playerName', 'Mohamed Salah');
    await page.click('#playerGo');
    await waitWithRetry(page, '.player-hero-card', '#playerGo', 3, 60000);
    await waitWithRetry(page, '#playerRadar svg', '#playerGo', 2, 45000);
    await settle(page);
    const heroTxt = await page.locator('.player-hero-card').first().innerText();
    check(`player(${tag}) hero card has name`, /salah/i.test(heroTxt), heroTxt.slice(0, 80).replace(/\n/g, ' | '));
    const radarPaths = await page.locator('#playerRadar svg *').count();
    check(`player(${tag}) radar svg populated`, radarPaths > 10, `${radarPaths} svg nodes`);
    const zoneBars = await count(page, '#view-player .bar, #view-player [class*="zone"], #view-player table tr');
    check(`player(${tag}) zones/types content present`, zoneBars > 0, `${zoneBars} rows/bars`);
    await shot(page, tag === '1440' ? 'player-1440.png' : 'player-375.png');
  }

  await doPlayer(d, '1440');
  // career trajectory (desktop)
  await d.click('#playerCareerGo');
  await waitWithRetry(d, '#careerChart svg', '#playerCareerGo', 3, 60000);
  await settle(d);
  const careerPts = await d.locator('#careerChart svg *').count();
  check('player career chart populated', careerPts > 10, `${careerPts} svg nodes`);
  await shot(d, 'career-1440.png');

  await doPlayer(m, '375');

  // -------------------------------------------------------------- 2. DISCOVER
  async function setDiscoverSeason(page, year) {
    await page.click('#discoverSeasons [data-season-btn]');
    await page.waitForSelector('#discoverSeasons .season-panel', { state: 'visible', timeout: 5000 });
    const boxes = page.locator('#discoverSeasons input[type="checkbox"]');
    const n = await boxes.count();
    for (let i = 0; i < n; i++) { try { await boxes.nth(i).uncheck(); } catch (e) {} }
    await page.locator(`#discoverSeasons input[value="${year}"]`).check();
    await page.click('#discoverSeasons [data-season-btn]');
    await page.waitForTimeout(300);
  }

  async function gotoDiscover(page) {
    await openTab(page, 'discover');
    // NOTE: app defaults discover to season 2026 which has NO data (empty state).
    // For evidence of populated UI we select 2025 explicitly.
    await setDiscoverSeason(page, 2025);
  }
  // totals run @1440
  await gotoDiscover(d);
  await d.fill('#discoverMinutes', '900');
  await d.click('#discoverGo');
  await waitWithRetry(d, '#discoverContent table tbody tr', '#discoverGo', 3, 60000);
  await settle(d);
  let rows = await count(d, '#discoverContent table tbody tr');
  check('discover(totals) rows rendered', rows > 0, `${rows} rows`);
  const tplBadgeTotals = await count(d, '#discoverContent .similar-badge');
  await shot(d, 'discover-totals-1440.png');

  // phase-1 controls run @1440
  await gotoDiscover(d);
  await d.fill('#discoverMinutes', '900');
  await d.check('#per90_tgl');
  await d.fill('#thresh_npxG', '0.3');
  await d.fill('#templatePlayer', 'Erling Haaland');
  await d.click('#discoverGo');
  await waitWithRetry(d, '#discoverContent table tbody tr', '#discoverGo', 3, 60000);
  await settle(d);
  rows = await count(d, '#discoverContent .similar-badge');
  check('discover(template) similarity badges', rows > 0, `${rows} badges`);
  const sparks = await count(d, '#discoverContent td div[data-tip]');
  check('discover(template) sparkline bars', sparks > 0, `${sparks} bar nodes`);
  const scatterNodes = await count(d, '#discoverAgeScatter svg *');
  check('discover(template) age scatter svg', scatterNodes > 5, `${scatterNodes} svg nodes`);
  const firstBadge = await d.locator('#discoverContent tbody tr').first().locator('.similar-badge').innerText().catch(() => 'none');
  check('discover(template) top row carries similarity badge', /\d+%/.test(firstBadge), `top badge: ${firstBadge}`);
  await shot(d, 'discover-template-1440.png');

  // phase-1 controls run @375
  await gotoDiscover(m);
  await m.fill('#discoverMinutes', '900');
  await m.check('#per90_tgl');
  await m.fill('#thresh_npxG', '0.3');
  await m.fill('#templatePlayer', 'Erling Haaland');
  await m.click('#discoverGo');
  await waitWithRetry(m, '#discoverContent table tbody tr', '#discoverGo', 3, 60000);
  await settle(m);
  await shot(m, 'discover-template-375.png');
  check('discover(375) badges present', (await count(m, '#discoverContent .similar-badge')) > 0, '');

  // ------------------------------------------------------------------ 3. TEAM
  async function doTeam(page, tag) {
    await openTab(page, 'team');
    await page.fill('#teamName', 'Arsenal');
    await page.click('#teamGo');
    await waitWithRetry(page, '.team-hero-card', '#teamGo', 3, 60000);
    await waitWithRetry(page, '#trendChart svg', '#teamGo', 2, 45000);
    await settle(page);
    await shot(page, tag === '1440' ? 'team-1440.png' : 'team-375.png');
  }
  await doTeam(d, '1440');
  const trendOpts = await d.locator('#trendMetric option').allTextContents();
  const deepOpt = trendOpts.find((t) => /deep/i.test(t));
  check('team trendMetric has deep completions option', !!deepOpt, `options: ${trendOpts.join(', ')}`);
  await doTeam(m, '375');

  // ---------------------------------------------------------------- 4. LEAGUE
  await openTab(d, 'league');
  await d.click('#leagueGo');
  await waitWithRetry(d, '#leagueTableContainer table tbody tr', '#leagueGo', 3, 60000);
  await settle(d, 2000);
  const leagueRows = await count(d, '#leagueTableContainer table tbody tr');
  check('league table rows', leagueRows >= 18, `${leagueRows} rows`);
  const divNodes = await count(d, '#leagueDivergenceChart svg *');
  check('league divergence chart svg populated', divNodes > 5, `${divNodes} svg nodes`);
  const quadTxt = await d.locator('#leaguePressQuadrant').innerText().catch(() => '');
  const quadSvgNodes = await count(d, '#leaguePressQuadrant svg *');
  check('league quadrant chart populated', quadSvgNodes > 5, `${quadSvgNodes} svg nodes; text: ${quadTxt.slice(0, 60)}`);
  await shot(d, 'league-1440.png');

  // ---------------------------------------------------------------- 5. MATCH
  async function doMatch(page, tag) {
    await openTab(page, 'match');
    // App defaults to season 2026 (no matches played yet) -> empty state.
    // Use the app's own escape hatch: "View Previous Season (2025) Matches".
    try {
      await page.waitForSelector('.fixture-card', { state: 'visible', timeout: 12000 });
    } catch (e) {
      const prevBtn = page.locator('button:has-text("View Previous Season")');
      if (await prevBtn.count()) {
        console.log('match: season 2026 empty — clicking View Previous Season');
        await prevBtn.first().click();
      }
      await waitWithRetry(page, '.fixture-card', null, 3, 60000);
    }
    await settle(page);
    const fixtures = await count(page, '.fixture-card');
    check(`match(${tag}) fixture cards auto-loaded`, fixtures > 0, `${fixtures} cards`);
    await page.locator('.fixture-card').first().click();
    await waitWithRetry(page, '#matchContent .player-hero-card', null, 1, 60000).catch(async () => {
      await page.locator('.fixture-card').first().click();
      await waitWithRetry(page, '#matchContent .player-hero-card', null, 2, 60000);
    });
    await waitWithRetry(page, '#xgtl svg', null, 2, 45000);
    await settle(page, 1500);
    const rosterTxt = await page.locator('#matchContent').innerText();
    check(`match(${tag}) rosters block`, /Match Rosters & Player Ledgers/i.test(rosterTxt), '');
    const pill = await count(page, '#matchContent .hero-pill');
    check(`match(${tag}) forecast pill`, pill > 0, `${pill} pills`);
    await shot(page, tag === '1440' ? 'match-1440.png' : 'match-375.png');
  }
  await doMatch(d, '1440');
  await doMatch(m, '375');

  // --------------------------------------------------------------- 6. PREDICT
  await openTab(d, 'predict');
  await d.fill('#predHome', 'Arsenal');
  await d.fill('#predAway', 'Liverpool');
  await d.click('#predGo');
  await d.waitForTimeout(3000);
  await settle(d, 2000);
  const predTxt = await d.locator('#view-predict').innerText();
  check('predict output rendered', predTxt.length > 200 && !/error/i.test(predTxt.slice(0, 400)), `len=${predTxt.length}`);
  await shot(d, 'predict-1440.png');

  await browser.close();

  fs.writeFileSync(path.join(OUT, 'capture-report.json'), JSON.stringify(report, null, 2));
  console.log('\n=== SUMMARY ===');
  console.log(`checks: ${report.checks.filter((c) => c.ok).length}/${report.checks.length} passed`);
  console.log(`console errors: ${report.consoleErrors.length}, page errors: ${report.pageErrors.length}, failed requests: ${report.failedRequests.length}`);
  for (const e of report.pageErrors.slice(0, 10)) console.log('PAGEERROR:', e);
  for (const e of report.failedRequests.slice(0, 10)) console.log('REQFAIL:', e);
})().catch((e) => { console.error('FATAL', e); process.exit(1); });

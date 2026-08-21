// QA evidence capture — Phase 1 delivery review ("frontend sucks?" investigation).
// Drives the live app at 127.0.0.1:8000 through all six views at desktop
// (1440x900) and mobile (375x812), saving fullPage screenshots into screenshots/
// with the p1-* names requested by the delivery lead. Read-only QA tooling:
// does not modify product code.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE = 'http://127.0.0.1:8000/dashboard/';
const OUT = path.join(__dirname, '..', 'screenshots');
if (!fs.existsSync(OUT)) fs.mkdirSync(OUT, { recursive: true });

const report = { checks: [], consoleErrors: [], pageErrors: [], failedRequests: [] };

function check(name, ok, detail) {
  report.checks.push({ name, ok: !!ok, detail: detail || '' });
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? ' — ' + detail : ''}`);
}

async function shot(page, name) {
  await page.screenshot({ path: path.join(OUT, name), fullPage: true });
  console.log(`SHOT ${name}`);
}

async function count(page, sel) {
  return page.locator(sel).count();
}

// Live Understat fetches are slow/rate-limited; retry the action+wait combo.
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

// Detect horizontal overflow (a classic mobile-layout defect)
async function overflow(page) {
  return page.evaluate(() => ({
    scrollW: document.documentElement.scrollWidth,
    innerW: window.innerWidth,
    bodyScrollW: document.body ? document.body.scrollWidth : -1,
  }));
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

  async function openTab(page, tab) {
    // App routes via sidebar clicks only; same-document hash goto does not activate.
    await page.goto(BASE, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector(`.sidebar-nav .nav-item[data-tab="${tab}"]`, { timeout: 30000 });
    await page.click(`.sidebar-nav .nav-item[data-tab="${tab}"]`);
    await page.waitForSelector(`#view-${tab}.active`, { timeout: 15000 });
  }

  async function logOverflow(page, tag) {
    const o = await overflow(page);
    const bad = o.scrollW > o.innerW + 2;
    check(`${tag} no horizontal overflow`, !bad, `scrollWidth=${o.scrollW} innerWidth=${o.innerW}${bad ? '  <-- HORIZONTAL SCROLL' : ''}`);
  }

  // ------------------------------------------------------------- 1. PLAYER
  async function doPlayer(page, tag) {
    await openTab(page, 'player');
    await page.fill('#playerName', 'Mohamed Salah');
    await page.click('#playerGo');
    await waitWithRetry(page, '.player-hero-card', '#playerGo', 3, 60000);
    await page.waitForTimeout(2000);
    const heroTxt = await page.locator('.player-hero-card').first().innerText();
    check(`player(${tag}) hero shows Salah`, /salah/i.test(heroTxt), heroTxt.slice(0, 70).replace(/\n/g, ' | '));
    await logOverflow(page, `player(${tag})`);
    await shot(page, tag === '1440' ? 'p1-player-1440.png' : 'p1-player-375.png');
  }
  await doPlayer(d, '1440');
  // career trajectory (desktop)
  await d.click('#playerCareerGo');
  await waitWithRetry(d, '#careerChart svg', '#playerCareerGo', 3, 60000);
  await d.waitForTimeout(1500);
  const careerNodes = await count(d, '#careerChart svg *');
  check('career chart svg populated', careerNodes > 10, `${careerNodes} svg nodes`);
  await shot(d, 'p1-career-1440.png');
  await doPlayer(m, '375');

  // ------------------------------------------------------------ 2. DISCOVER
  async function setDiscoverSeason2025(page) {
    // App defaults discover to season 2026 (not yet played -> guaranteed empty).
    // Use the app's own season multi-select to pick 2025 (completed season).
    await page.click('#discoverSeasons [data-season-btn]');
    await page.waitForSelector('#discoverSeasons .season-panel', { state: 'visible', timeout: 5000 });
    const boxes = page.locator('#discoverSeasons input[type="checkbox"]');
    const n = await boxes.count();
    for (let i = 0; i < n; i++) { try { await boxes.nth(i).uncheck(); } catch (e) {} }
    await page.locator('#discoverSeasons input[value="2025"]').check();
    await page.click('#discoverSeasons [data-season-btn]');
    await page.waitForTimeout(300);
  }

  async function gotoDiscover(page) {
    await openTab(page, 'discover');
    try {
      await page.waitForSelector('#discoverContent table tbody tr, #discoverContent .empty-state, #discoverContent .card', { timeout: 4000 });
    } catch (e) {}
    const hasRows = await count(page, '#discoverContent table tbody tr');
    if (!hasRows) {
      console.log('discover: default season empty — switching to 2025 via app UI');
      await setDiscoverSeason2025(page);
    }
  }

  async function doDiscoverBase(page, tag) {
    await gotoDiscover(page);
    await page.click('#discoverGo');
    // wait for either result rows or an explicit empty/error message (~20s budget)
    try {
      await waitWithRetry(page, '#discoverContent table tbody tr', '#discoverGo', 2, 30000);
    } catch (e) {
      const txt = await page.locator('#discoverContent').innerText().catch(() => '');
      check(`discover(${tag}) rendered rows`, false, `no rows; content: ${txt.slice(0, 120).replace(/\n/g, ' | ')}`);
    }
    await page.waitForTimeout(2000);
    const rows = await count(page, '#discoverContent table tbody tr');
    check(`discover(${tag}) rows rendered`, rows > 0, `${rows} rows`);
    await logOverflow(page, `discover(${tag})`);
    await shot(page, tag === '1440' ? 'p1-discover-1440.png' : 'p1-discover-375.png');
    return rows;
  }

  await doDiscoverBase(d, '1440');

  // phase-1 controls: per90 toggle + npxG threshold + template player
  await gotoDiscover(d);
  await d.check('#per90_tgl');
  await d.fill('#thresh_npxG', '0.3');
  await d.fill('#templatePlayer', 'Erling Haaland');
  await d.click('#discoverGo');
  let tplRows = 0;
  try {
    await waitWithRetry(d, '#discoverContent table tbody tr', '#discoverGo', 2, 30000);
  } catch (e) {}
  await d.waitForTimeout(2000);
  tplRows = await count(d, '#discoverContent table tbody tr');
  const badges = await count(d, '#discoverContent .similar-badge');
  check('discover(tpl) rows rendered', tplRows > 0, `${tplRows} rows, ${badges} similarity badges`);
  await logOverflow(d, 'discover(tpl)');
  await shot(d, 'p1-discover-tpl-1440.png');

  await doDiscoverBase(m, '375');

  // ---------------------------------------------------------------- 3. TEAM
  async function doTeam(page, tag) {
    await openTab(page, 'team');
    await page.fill('#teamName', 'Arsenal');
    await page.click('#teamGo');
    await waitWithRetry(page, '.team-hero-card', '#teamGo', 3, 60000);
    await page.waitForTimeout(10000); // squad table is slow
    const heroTxt = await page.locator('.team-hero-card').first().innerText();
    check(`team(${tag}) hero shows Arsenal`, /arsenal/i.test(heroTxt), heroTxt.slice(0, 70).replace(/\n/g, ' | '));
    const squadRows = await count(page, '#view-team table tbody tr');
    check(`team(${tag}) squad table rows exist`, squadRows > 0, `${squadRows} rows`);
    await logOverflow(page, `team(${tag})`);
    await shot(page, tag === '1440' ? 'p1-team-1440.png' : 'p1-team-375.png');
  }
  await doTeam(d, '1440');
  await doTeam(m, '375');

  // --------------------------------------------------------------- 4. LEAGUE
  await openTab(d, 'league');
  let leagueRows = 0;
  try {
    await d.waitForSelector('#leagueTableContainer table tbody tr', { state: 'visible', timeout: 15000 });
  } catch (e) {
    console.log('league: no auto-load within 15s — clicking #leagueGo');
    await d.click('#leagueGo');
    await d.waitForSelector('#leagueTableContainer table tbody tr', { state: 'visible', timeout: 30000 }).catch(() => {});
  }
  await d.waitForTimeout(2000);
  leagueRows = await count(d, '#leagueTableContainer table tbody tr');
  check('league table rows', leagueRows >= 18, `${leagueRows} rows`);
  await logOverflow(d, 'league');
  await shot(d, 'p1-league-1440.png');

  // ---------------------------------------------------------------- 5. MATCH
  async function doMatch(page, tag) {
    await openTab(page, 'match');
    try {
      await page.waitForSelector('.fixture-card', { state: 'visible', timeout: 25000 });
    } catch (e) {
      const prevBtn = page.locator('button:has-text("View Previous Season")');
      if (await prevBtn.count()) {
        console.log(`match(${tag}): current season empty — clicking View Previous Season`);
        await prevBtn.first().click();
        await waitWithRetry(page, '.fixture-card', null, 3, 60000);
      } else {
        throw e;
      }
    }
    await page.waitForTimeout(1000);
    const fixtures = await count(page, '.fixture-card');
    check(`match(${tag}) fixture cards`, fixtures > 0, `${fixtures} cards`);
    await page.locator('.fixture-card').first().click();
    await waitWithRetry(page, '#matchContent .player-hero-card', null, 1, 60000).catch(async () => {
      await page.locator('.fixture-card').first().click();
      await waitWithRetry(page, '#matchContent .player-hero-card', null, 2, 60000);
    });
    await page.waitForTimeout(5000); // let charts settle
    const mcTxt = await page.locator('#matchContent').innerText();
    check(`match(${tag}) match content populated`, mcTxt.length > 200, `len=${mcTxt.length}`);
    await logOverflow(page, `match(${tag})`);
    await shot(page, tag === '1440' ? 'p1-match-1440.png' : 'p1-match-375.png');
  }
  await doMatch(d, '1440');
  await doMatch(m, '375');

  // -------------------------------------------------------------- 6. PREDICT
  await openTab(d, 'predict');
  await d.fill('#predHome', 'Arsenal');
  await d.fill('#predAway', 'Liverpool');
  await d.click('#predGo');
  let predLen = 0;
  try {
    await d.waitForFunction(
      () => {
        const el = document.querySelector('#predictContent');
        return el && el.innerText.trim().length > 120 && !/generating|loading/i.test(el.innerText);
      },
      { timeout: 40000 }
    );
  } catch (e) {}
  await d.waitForTimeout(2000);
  predLen = (await d.locator('#predictContent').innerText()).length;
  check('predict content rendered', predLen > 120, `len=${predLen}`);
  await logOverflow(d, 'predict');
  await shot(d, 'p1-predict-1440.png');

  await browser.close();

  fs.writeFileSync(path.join(OUT, 'p1-capture-report.json'), JSON.stringify(report, null, 2));
  console.log('\n=== SUMMARY ===');
  console.log(`checks: ${report.checks.filter((c) => c.ok).length}/${report.checks.length} passed`);
  console.log(`console errors: ${report.consoleErrors.length}, page errors: ${report.pageErrors.length}, failed requests: ${report.failedRequests.length}`);
  for (const e of report.pageErrors.slice(0, 10)) console.log('PAGEERROR:', e);
  for (const e of report.consoleErrors.slice(0, 10)) console.log('CONSOLEERR:', e);
  for (const e of report.failedRequests.slice(0, 10)) console.log('REQFAIL:', e);
})().catch((e) => { console.error('FATAL', e); process.exit(1); });

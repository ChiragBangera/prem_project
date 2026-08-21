const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch();
  // Season 2025 (complete) at desktop
  let ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  let page = await ctx.newPage();
  await page.goto('http://127.0.0.1:8000/dashboard/#match', { waitUntil: 'domcontentloaded' });
  await page.selectOption('#matchSeason', '2025');
  await page.waitForTimeout(4000);
  await page.click('#matchModeToggle button:has-text("Gameweek Board")');
  await page.waitForTimeout(5000);
  const pills = await page.evaluate(() => [...document.querySelectorAll('#matchRecentFeed .view-pill-btn')].map(b => b.textContent).slice(0, 10).join(','));
  console.log('PILLS:', pills);
  const badge = await page.evaluate(() => document.querySelector('#matchRecentFeed .hero-pill')?.textContent || 'NO BADGE');
  console.log('STATUS BADGE:', badge);
  const cards = await page.evaluate(() => document.querySelectorAll('#matchRecentFeed .fixture-card').length);
  console.log('CARDS R38:', cards);
  await page.screenshot({ path: 'screenshots/p3-board-1440.png' });
  // Click round 1 pill
  await page.click('#matchRecentFeed button.view-pill-btn:has-text("1")');
  await page.waitForTimeout(800);
  const r1cards = await page.evaluate(() => document.querySelectorAll('#matchRecentFeed .fixture-card').length);
  console.log('CARDS R1:', r1cards);
  // Deep-dive click still works from board (first played card)
  await page.click('#matchRecentFeed .fixture-card');
  await page.waitForSelector('#matchContent .player-hero-card', { timeout: 30000 });
  console.log('DEEP DIVE FROM BOARD: OK');
  await ctx.close();

  // Mobile 375 board
  ctx = await browser.newContext({ viewport: { width: 375, height: 812 } });
  page = await ctx.newPage();
  await page.goto('http://127.0.0.1:8000/dashboard/#match', { waitUntil: 'domcontentloaded' });
  await page.selectOption('#matchSeason', '2025');
  await page.waitForTimeout(4000);
  await page.click('#matchModeToggle button:has-text("Gameweek Board")');
  await page.waitForTimeout(5000);
  const sw = await page.evaluate(() => document.documentElement.scrollWidth);
  console.log('MOBILE scrollWidth:', sw, sw <= 377 ? 'PASS' : 'FAIL');
  await page.screenshot({ path: 'screenshots/p3-board-375.png' });
  await ctx.close();
  // Recent Results default unchanged (2025)
  ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  page = await ctx.newPage();
  await page.goto('http://127.0.0.1:8000/dashboard/#match', { waitUntil: 'domcontentloaded' });
  await page.selectOption('#matchSeason', '2025');
  await page.waitForTimeout(4500);
  const toggle = await page.evaluate(() => document.getElementById('matchModeToggle')?.textContent || 'NO TOGGLE');
  const recentCards = await page.evaluate(() => document.querySelectorAll('#matchRecentFeed .fixture-card').length);
  console.log('TOGGLE:', JSON.stringify(toggle), '| recent cards:', recentCards);
  await ctx.close();
  await browser.close();
})();

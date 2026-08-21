const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  await page.goto('http://127.0.0.1:8000/dashboard/#team', { waitUntil: 'domcontentloaded' });
  await page.fill('#teamName', 'Arsenal');
  await page.click('#teamGo');
  await page.waitForSelector('.team-hero-card', { timeout: 40000 });
  await page.waitForTimeout(9000);
  const badge = await page.evaluate(() => {
    const pills = [...document.querySelectorAll('.hero-pill')];
    return pills.find(p => p.textContent.includes('🧬'))?.textContent || 'NO BADGE';
  });
  console.log('TEAM BADGE:', badge);
  const chip = await page.evaluate(() => document.querySelector('.chart-subtitle')?.textContent || '');
  console.log('DNA SUBTITLE:', chip);
  const peers = await page.evaluate(() => [...document.querySelectorAll('.view-pill-btn')].map(b => b.textContent).slice(0, 5));
  console.log('PEER CHIPS:', peers.join(' | '));
  await page.screenshot({ path: 'screenshots/p2-team-badge.png', fullPage: false });
  // League
  await page.click('[data-tab="league"]');
  await page.waitForSelector('#leagueTableContainer tr', { timeout: 40000 });
  await page.waitForTimeout(3000);
  const archCard = await page.evaluate(() => {
    const cards = [...document.querySelectorAll('.card')];
    const c = cards.find(x => x.querySelector('.card-title')?.textContent === 'Tactical Archetypes');
    if (!c) return 'NO CARD';
    const groups = [...c.querySelectorAll('div[style*="min-width"]')].map(g => g.querySelector('div')?.textContent);
    return groups.join(' || ');
  });
  console.log('LEAGUE ARCHETYPES:', archCard);
  await page.screenshot({ path: 'screenshots/p2-league-archetypes.png', fullPage: true });
  await browser.close();
})();

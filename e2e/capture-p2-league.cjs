const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  await page.goto('http://127.0.0.1:8000/dashboard/#league', { waitUntil: 'domcontentloaded' });
  try {
    await page.waitForSelector('#leagueTableContainer tr', { timeout: 60000 });
  } catch (e) {
    const html = await page.evaluate(() => document.getElementById('leagueContent')?.innerHTML.slice(0, 300) || 'EMPTY');
    console.log('TIMEOUT. leagueContent head:', html);
  }
  await page.waitForTimeout(2000);
  const archCard = await page.evaluate(() => {
    const cards = [...document.querySelectorAll('.card')];
    const c = cards.find(x => x.querySelector('.card-title')?.textContent === 'Tactical Archetypes');
    if (!c) return 'NO CARD';
    return [...c.querySelectorAll('div[style*="min-width"]')].map(g => g.querySelector('div')?.textContent).join(' || ');
  });
  console.log('LEAGUE ARCHETYPES:', archCard);
  await page.screenshot({ path: 'screenshots/p2-league-archetypes.png', fullPage: true });
  console.log('saved screenshots/p2-league-archetypes.png');
  await browser.close();
})();

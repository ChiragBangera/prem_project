const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 375, height: 812 } });
  const page = await ctx.newPage();
  await page.goto('http://127.0.0.1:8000/dashboard/#player', { waitUntil: 'domcontentloaded' });
  const views = [
    ['player', async () => { await page.fill('#playerName', 'Mohamed Salah'); await page.click('#playerGo'); await page.waitForSelector('.player-hero-card', { timeout: 30000 }); await page.waitForTimeout(2500); }],
    ['discover', async () => { await page.click('[data-tab="discover"]'); await page.click('#discoverGo'); await page.waitForTimeout(15000); }],
    ['team', async () => { await page.click('[data-tab="team"]'); await page.fill('#teamName', 'Arsenal'); await page.click('#teamGo'); await page.waitForSelector('.team-hero-card', { timeout: 30000 }); await page.waitForTimeout(8000); }],
    ['match', async () => { await page.click('[data-tab="match"]'); await page.waitForSelector('.fixture-card', { timeout: 30000 }); await page.click('.fixture-card'); await page.waitForTimeout(6000); }],
  ];
  for (const [name, action] of views) {
    try { await action(); } catch (e) { console.log(name, 'ACTION FAIL:', e.message.slice(0, 80)); }
    await page.waitForTimeout(1000);
    const m = await page.evaluate(() => {
      const offenders = [];
      document.querySelectorAll('body *').forEach(el => {
        const r = el.getBoundingClientRect();
        if (r.width > 0 && (r.right > 377 || r.left < -2)) {
          offenders.push(`${el.tagName.toLowerCase()}${el.id ? '#' + el.id : ''}.${(el.className && el.className.toString ? el.className.toString() : '').split(' ')[0]} w=${Math.round(r.width)} right=${Math.round(r.right)}`);
        }
      });
      return { sw: document.documentElement.scrollWidth, iw: window.innerWidth, top: offenders.sort((a,b)=>parseInt(b.match(/right=(\d+)/)-a.match(/right=(\d+)/))).slice(0,5) };
    });
    console.log(`${name}: scrollWidth=${m.sw} innerWidth=${m.iw} ${m.sw <= 377 ? 'PASS' : 'FAIL'}`);
    m.top.forEach(t => console.log('   ', t));
  }
  await browser.close();
})();

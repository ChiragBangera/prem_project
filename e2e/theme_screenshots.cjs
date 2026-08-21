const { chromium } = require('playwright');
const themes = ['midnight','nord','gruvbox','studio'];
const modes = ['dark','light'];
(async () => {
  const browser = await chromium.launch();
  for (const theme of themes) {
    for (const mode of modes) {
      const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
      const page = await ctx.newPage();
      await page.goto('http://127.0.0.1:8000/dashboard/', {waitUntil:'domcontentloaded'});
      await page.waitForTimeout(1000);
      await page.evaluate(({theme,mode}) => {
        localStorage.setItem('prem_theme', theme);
        localStorage.setItem('prem_mode', mode);
        document.documentElement.setAttribute('data-theme', theme);
        document.documentElement.setAttribute('data-mode', mode);
      }, {theme, mode});
      await page.reload({waitUntil:'domcontentloaded'});
      await page.waitForTimeout(1500);
      await page.click('[data-tab="discover"]');
      await page.waitForTimeout(800);
      const sw = await page.evaluate(() => document.documentElement.scrollWidth);
      console.log(`${theme}/${mode} scrollWidth:${sw} ${sw<=1440?'PASS':'FAIL'}`);
      await page.screenshot({path:`screenshots/theme-${theme}-${mode}-1440.png`, fullPage:false});
      await ctx.close();
    }
  }
  // mobile check for filters
  for (const theme of ['midnight','nord']) {
    const ctx = await browser.newContext({ viewport: { width: 375, height: 812 } });
    const page = await ctx.newPage();
    await page.goto('http://127.0.0.1:8000/dashboard/', {waitUntil:'domcontentloaded'});
    await page.evaluate(({theme}) => {
      localStorage.setItem('prem_theme', theme);
      localStorage.setItem('prem_mode', 'dark');
      document.documentElement.setAttribute('data-theme', theme);
      document.documentElement.setAttribute('data-mode', 'dark');
    }, {theme});
    await page.reload({waitUntil:'domcontentloaded'});
    await page.waitForTimeout(1200);
    await page.click('[data-tab="discover"]');
    await page.waitForTimeout(800);
    const sw = await page.evaluate(() => document.documentElement.scrollWidth);
    console.log(`mobile ${theme}/dark scrollWidth:${sw} ${sw<=375?'PASS':'FAIL'}`);
    await page.screenshot({path:`screenshots/theme-${theme}-dark-375.png`, fullPage:false});
    await ctx.close();
  }
  await browser.close();
})();

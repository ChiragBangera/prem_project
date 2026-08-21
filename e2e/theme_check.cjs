const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  await page.goto('http://127.0.0.1:8000/dashboard/', {waitUntil:'domcontentloaded'});
  await page.waitForTimeout(1500);
  const initial = await page.evaluate(() => document.documentElement.getAttribute('data-theme') + '/' + document.documentElement.getAttribute('data-mode'));
  console.log('initial theme:', initial);
  // check picker exists
  const picker = await page.evaluate(() => !!document.getElementById('themeSelect'));
  console.log('picker exists:', picker);
  const modes = await page.evaluate(() => document.getElementById('modeToggle')?.textContent);
  console.log('mode btn:', modes);
  // switch to nord
  await page.selectOption('#themeSelect', 'nord');
  await page.waitForTimeout(500);
  let t = await page.evaluate(() => document.documentElement.getAttribute('data-theme'));
  console.log('after nord select:', t);
  // toggle light
  await page.click('#modeToggle');
  await page.waitForTimeout(500);
  let m = await page.evaluate(() => document.documentElement.getAttribute('data-mode'));
  console.log('after toggle:', m);
  // screenshot nord light
  await page.screenshot({path:'/tmp/nord-light.png', fullPage:false});
  // switch to gruvbox dark
  await page.selectOption('#themeSelect', 'gruvbox');
  await page.click('#modeToggle'); // should go dark if was light
  await page.waitForTimeout(300);
  let g = await page.evaluate(() => document.documentElement.getAttribute('data-theme') + '/' + document.documentElement.getAttribute('data-mode'));
  console.log('gruvbox:', g);
  await page.screenshot({path:'/tmp/gruvbox-dark.png', fullPage:false});
  // check filters at discover
  await page.click('[data-tab="discover"]');
  await page.waitForTimeout(1000);
  const sw = await page.evaluate(() => document.documentElement.scrollWidth);
  console.log('discover scrollWidth 1440:', sw);
  await browser.close();
})();

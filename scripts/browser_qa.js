const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const baseUrl = process.env.SEGUE_QA_URL || 'http://127.0.0.1:8000';
const output = path.resolve(__dirname, '..', 'out', 'browser-qa');
const demoWallet = '0x48C8B4D40dE216C652ED4D67f6466CeBA90054CA';
const freshWallet = '0x1111111111111111111111111111111111111111';
const sizes = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'tablet', width: 768, height: 1024 },
  { name: 'mobile-430', width: 430, height: 932 },
  { name: 'mobile-390', width: 390, height: 844 },
];

async function capture(page, name, url, waitFor) {
  const errors = [];
  page.on('console', message => { if (message.type() === 'error') errors.push(`console: ${message.text()}`); });
  page.on('pageerror', error => errors.push(`page: ${error.message}`));
  await page.goto(url, { waitUntil: 'domcontentloaded' });
  if (waitFor) await page.waitForFunction(waitFor, undefined, { timeout: 60000 });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  await page.screenshot({ path: path.join(output, `${name}.png`), fullPage: true });
  return { name, url, viewport: page.viewportSize(), overflow, errors };
}

(async () => {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const results = [];
  try {
    for (const size of sizes) {
      const context = await browser.newContext({ viewport: { width: size.width, height: size.height } });
      const page = await context.newPage();
      results.push(await capture(page, `landing-${size.name}`, `${baseUrl}/`, () => document.documentElement.dataset.demoState !== 'LOADING'));
      await context.close();
    }

    const disconnectedContext = await browser.newContext({ viewport: { width: 390, height: 844 } });
    const disconnected = await disconnectedContext.newPage();
    results.push(await capture(disconnected, 'workspace-disconnected-mobile-390', `${baseUrl}/app.html`));
    await disconnectedContext.close();

    const freshContext = await browser.newContext({ viewport: { width: 768, height: 1024 } });
    await freshContext.addInitScript(address => {
      window.ethereum = {
        request: async ({ method }) => method === 'eth_chainId' ? '0x2105' : method === 'eth_accounts' || method === 'eth_requestAccounts' ? [address] : null,
        on: () => {},
      };
    }, freshWallet);
    const fresh = await freshContext.newPage();
    results.push(await capture(fresh, 'workspace-fresh-tablet', `${baseUrl}/app.html`, () => document.querySelector('#summary-holdings')?.textContent !== 'Reading…'));
    await freshContext.close();

    for (const size of [sizes[0], sizes[2]]) {
      const context = await browser.newContext({ viewport: { width: size.width, height: size.height } });
      const page = await context.newPage();
      results.push(await capture(page, `workspace-demo-${size.name}`, `${baseUrl}/app.html?demo=1`, () => document.querySelector('#summary-credit')?.textContent.includes('USDC')));
      await page.getByRole('button', { name: 'Sequences' }).click();
      await page.waitForTimeout(300);
      const sequenceOverflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
      const hasThreeSteps = await page.locator('.sequence-card').filter({ hasText: '3 dependent steps' }).count() > 0;
      await page.screenshot({ path: path.join(output, `sequences-${size.name}.png`), fullPage: true });
      results.push({ name: `sequences-${size.name}`, viewport: size, overflow: sequenceOverflow, hasThreeSteps, errors: [] });
      await context.close();
    }
  } finally {
    await browser.close();
  }
  const report = { baseUrl, demoWallet, freshWallet, capturedAt: new Date().toISOString(), results };
  fs.writeFileSync(path.join(output, 'report.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
  if (results.some(result => result.overflow || result.errors.length)) process.exitCode = 1;
})();

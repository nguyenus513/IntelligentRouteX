import { expect, test } from '@playwright/test';
import { backendIsUp, expectNoSevereConsoleErrors, gotoTab, openDashboard } from './helpers';

test('loads dashboard, reports health state, navigates all tabs', async ({ page, request }) => {
  const backendReady = await backendIsUp(request);
  const consoleErrors = await openDashboard(page);

  await expect(page.getByText(backendReady ? /Health UP/i : /Backend offline|Health DOWN|Health UNKNOWN/i).first()).toBeVisible({ timeout: 12_000 });

  for (const tab of ['Live', 'Benchmark Compare', 'Demo Builder', 'Decision Trace', 'API Sandbox']) {
    await gotoTab(page, tab);
    await expect(page.locator('.panel').first()).toBeVisible();
  }

  await expect(page.locator('.realMap')).toBeVisible();
  await expectNoSevereConsoleErrors(consoleErrors);
});

test('offline or locked controls remain safe when backend is not ready', async ({ page, request }) => {
  const backendReady = await backendIsUp(request);
  await openDashboard(page);
  test.skip(backendReady, 'Backend is online; offline lock case not applicable.');

  await gotoTab(page, 'Live');
  await expect(page.getByRole('button', { name: /Start Live/i })).toBeDisabled();
  await gotoTab(page, 'API Sandbox');
  await clickAndExpectNoCrash(page, /Health/i);
});

async function clickAndExpectNoCrash(page: import('@playwright/test').Page, name: RegExp) {
  const button = page.getByRole('button', { name }).first();
  await expect(button).toBeVisible();
  if (await button.isEnabled()) await button.click();
  await expect(page.locator('body')).toBeVisible();
}

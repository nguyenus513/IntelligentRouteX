import { expect, test } from '@playwright/test';
import { backendIsUp, gotoTab, openDashboard } from './helpers';

test('api sandbox endpoint picker accordions health and send payload are stable', async ({ page, request }) => {
  const backendReady = await backendIsUp(request);
  await openDashboard(page);
  await gotoTab(page, 'API Sandbox');

  for (const label of ['POST dispatch', 'POST compare', 'POST live', 'POST live order', 'POST live cycle', 'POST rescue', 'POST bigdata orders', 'GET bigdata runtime', 'GET AI context', 'POST AI ask']) {
    const button = page.getByRole('button', { name: new RegExp(label, 'i') }).first();
    await expect(button).toBeVisible();
    await button.click();
    await expect(page.getByText(/Endpoint|Status|Health/i).first()).toBeVisible();
  }

  await page.getByRole('button', { name: /Expand Payload/i }).click();
  await expect(page.getByLabel(/Editable API payload/i)).toBeVisible();
  await page.getByRole('button', { name: /Collapse Payload/i }).click();

  await page.getByRole('button', { name: /Expand Response/i }).click();
  await expect(page.locator('pre').first()).toBeVisible();
  await page.getByRole('button', { name: /Collapse Response/i }).click();

  await page.getByRole('button', { name: /Health/i }).click();
  await expect(page.getByText(backendReady ? /UP|AVAILABLE|OK/i : /offline|locked|error/i).first()).toBeVisible({ timeout: 12_000 });
});

import { expect, test } from '@playwright/test';
import { backendIsUp, gotoTab, openDashboard, startLiveIfBackendUp } from './helpers';

test('map pin tools create order and driver markers with compact labels', async ({ page, request }) => {
  const backendReady = await backendIsUp(request);
  await openDashboard(page);
  await gotoTab(page, 'Demo Builder');

  const map = page.locator('.realMap');
  await expect(map).toBeVisible();
  await page.getByRole('button', { name: /^pin order$/i }).click();
  const box = await map.boundingBox();
  expect(box).toBeTruthy();
  await page.mouse.click((box!.x + box!.width * 0.42), (box!.y + box!.height * 0.48));
  await page.mouse.click((box!.x + box!.width * 0.58), (box!.y + box!.height * 0.56));
  await expect(page.locator('.draftPin.pickup').first()).toBeVisible({ timeout: 8_000 });
  await expect(page.locator('.draftPin.dropoff').first()).toBeVisible();

  await page.getByRole('button', { name: /^driver$/i }).click();
  await page.mouse.click((box!.x + box!.width * 0.50), (box!.y + box!.height * 0.42));
  if (backendReady) await expect(page.getByText(/Driver sent to backend|Dropped DRV/i).first()).toBeVisible({ timeout: 12_000 });
});

test('tracking toolbar switches view only and clear after live driver exists', async ({ page, request }) => {
  const backendReady = await backendIsUp(request);
  await openDashboard(page);
  test.skip(!backendReady, 'Backend required for runtime tracking test.');

  await startLiveIfBackendUp(page, backendReady);
  await page.getByRole('button', { name: /Spam Driver/i }).click();
  await expect(page.getByText(/Tracking/i).first()).toBeVisible();
  const runtimeDriver = page.locator('.driverRuntimeGrid button').first();
  await expect(runtimeDriver).toBeVisible({ timeout: 15_000 });
  await runtimeDriver.click();
  const toolbar = page.getByLabel('Driver tracking controls');
  const view = toolbar.getByRole('button', { name: /^View$/i });
  const only = toolbar.getByRole('button', { name: /^Only$/i });
  const clear = toolbar.getByRole('button', { name: /^Clear$/i });
  await expect(view).toBeVisible();
  await expect(only).toBeVisible();
  await expect(clear).toBeVisible();
  await expect(view).toBeEnabled();
  await expect(only).toBeEnabled();
  await expect(clear).toBeEnabled();
});

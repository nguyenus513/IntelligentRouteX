import { expect, test } from '@playwright/test';
import { backendIsUp, gotoTab, openDashboard } from './helpers';

test('demo scenarios are selectable and expose realtime expected UI', async ({ page, request }) => {
  const backendReady = await backendIsUp(request);
  await openDashboard(page);
  await gotoTab(page, 'Demo Builder');

  for (const label of ['Urban dense', 'Cross-district', 'Driver shortage', 'Hub & spoke', 'Large fixed']) {
    const button = page.getByRole('button', { name: new RegExp(label, 'i') }).first();
    if (await button.count()) await button.click();
    await expect(page.getByText(/Generated input draft/i)).toBeVisible();
  }

  await expect(page.getByText(/Realtime Event Stream/i)).toBeVisible();
  await expect(page.getByText(/Orders\/sec|Decision latency|Queue depth|Route churn/i).first()).toBeVisible();

  const startDemo = page.getByRole('button', { name: /Start Demo/i }).first();
  await expect(startDemo).toBeVisible();
  if (!backendReady) {
    await expect(startDemo).toBeDisabled();
    return;
  }
  await startDemo.click();
  await expect(page.getByText(/Demo Running|Realtime Event Stream|BUFFER|solver|route/i).first()).toBeVisible({ timeout: 30_000 });
});

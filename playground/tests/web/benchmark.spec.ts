import { expect, test } from '@playwright/test';
import { backendIsUp, gotoTab, openDashboard } from './helpers';

test('benchmark dataset picker clear and result table contract', async ({ page, request }) => {
  const backendReady = await backendIsUp(request);
  await openDashboard(page);
  await gotoTab(page, 'Benchmark Compare');

  const panel = page.locator('.panel').filter({ hasText: 'Benchmark Compare' }).first();
  await expect(panel.getByRole('button', { name: /Start Benchmark|Stop Benchmark/i })).toBeVisible();
  await expect(panel.getByRole('button', { name: /^Clear$/i })).toBeVisible();
  await page.getByRole('button', { name: /HCM dinner peak/i }).click();
  await page.getByRole('button', { name: /Driver scarcity/i }).click();

  if (!backendReady) {
    await expect(panel.getByRole('button', { name: /Start Benchmark/i })).toBeDisabled();
    return;
  }

  await panel.getByRole('button', { name: /Start Benchmark/i }).click();
  await expect(page.getByText(/IRX|VROOM|ORTOOLS|PYVRP|DISTANCE_NEAREST|ONE_BY_ONE/i).first()).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText(/Solver|Runtime|Distance|Late|Coverage|Result/i).first()).toBeVisible();
  await panel.getByRole('button', { name: /^Clear$/i }).click();
  await expect(page.locator('body')).toBeVisible();
});

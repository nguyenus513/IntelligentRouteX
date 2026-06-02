import { expect, test } from '@playwright/test';
import { backendIsUp, clickIfEnabled, gotoTab, openDashboard, startLiveIfBackendUp } from './helpers';

test('live start stop auto toggles spam and cycle controls', async ({ page, request }) => {
  const backendReady = await backendIsUp(request);
  await openDashboard(page);
  test.skip(!backendReady, 'Backend required for live control test.');

  await startLiveIfBackendUp(page, backendReady);
  await expect(page.getByText(/Auto order: OFF/i)).toBeVisible();
  await expect(page.getByText(/Auto driver: OFF/i)).toBeVisible();

  await clickIfEnabled(page, /Auto Order OFF/i);
  await expect(page.getByRole('button', { name: /Auto Order ON/i })).toBeVisible();
  await clickIfEnabled(page, /Auto Order ON/i);
  await expect(page.getByRole('button', { name: /Auto Order OFF/i })).toBeVisible();

  await clickIfEnabled(page, /Auto Driver OFF/i);
  await expect(page.getByRole('button', { name: /Auto Driver ON/i })).toBeVisible();
  await clickIfEnabled(page, /Auto Driver ON/i);
  await expect(page.getByRole('button', { name: /Auto Driver OFF/i })).toBeVisible();

  await clickIfEnabled(page, /Spam Driver/i);
  await clickIfEnabled(page, /Spam Order/i);
  await clickIfEnabled(page, /Run Cycle/i);

  await expect(page.getByText(/Live Dispatch Queue/i)).toBeVisible();
  await expect(page.getByText(/Backend buffer|Assigned|Idle Drivers/i).first()).toBeVisible();

  await clickIfEnabled(page, /Stop Live/i);
  await expect(page.getByRole('button', { name: /Start Live/i })).toBeVisible({ timeout: 12_000 });
});

test('live queue and aging panels render backend state without crashing', async ({ page, request }) => {
  const backendReady = await backendIsUp(request);
  await openDashboard(page);
  test.skip(!backendReady, 'Backend required for live queue test.');

  await startLiveIfBackendUp(page, backendReady);
  await expect(page.getByText('Aging Priority Monitor')).toBeVisible();
  await expect(page.getByText(/NORMAL|Buffered Now|Oldest/i).first()).toBeVisible();
  await expect(page.getByText(/Driver Runtime|Live Dispatch Queue/i).first()).toBeVisible();
});

import { expect, type Page, type APIRequestContext } from '@playwright/test';

export const backendBaseUrl = process.env.IRX_BACKEND_URL ?? 'http://127.0.0.1:18116';

export async function backendIsUp(request: APIRequestContext) {
  try {
    const response = await request.get(`${backendBaseUrl}/actuator/health`, { timeout: 3_000 });
    if (!response.ok()) return false;
    const payload = await response.json().catch(() => ({}));
    return String(payload.status ?? '').toUpperCase() === 'UP';
  } catch {
    return false;
  }
}

export async function openDashboard(page: Page) {
  const consoleErrors: string[] = [];
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  await expect(page.getByText(/IRX Control Tower Client/i).first()).toBeVisible();
  return consoleErrors;
}

export async function gotoTab(page: Page, name: string) {
  await page.getByRole('button', { name, exact: true }).click();
  await expect(page.getByText(name, { exact: false }).first()).toBeVisible();
}

export async function clickIfEnabled(page: Page, name: RegExp | string) {
  const button = page.getByRole('button', { name }).first();
  await expect(button).toBeVisible();
  if (await button.isEnabled()) await button.click();
  return button;
}

export async function expectNoSevereConsoleErrors(errors: string[]) {
  const severe = errors.filter((line) => !/favicon|leaflet|tile|net::ERR_ABORTED/i.test(line));
  expect(severe, severe.join('\n')).toHaveLength(0);
}

export async function startLiveIfBackendUp(page: Page, backendReady: boolean) {
  await gotoTab(page, 'Live');
  const start = page.getByRole('button', { name: /Start Live|Stop Live/i }).first();
  await expect(start).toBeVisible();
  if (!backendReady) {
    await expect(start).toBeDisabled();
    return false;
  }
  const label = await start.textContent();
  if (/Start Live/i.test(label ?? '')) await start.click();
  await expect(page.getByRole('button', { name: /Stop Live/i })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(/LIVE RUNNING|Session:/i).first()).toBeVisible();
  return true;
}

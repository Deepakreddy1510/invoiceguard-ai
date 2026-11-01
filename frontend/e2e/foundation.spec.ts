import { test, expect } from '@playwright/test';
test('React loads seeded procurement through Vite, FastAPI and PostgreSQL', async ({ page }) => {
  await page.goto('/purchase-orders');
  await expect(page.getByText('4 records · API connected')).toBeVisible();
  await expect(page.getByText('PO-2026-001')).toBeVisible();
  await expect(page.getByRole('row').filter({hasText:'PO-2026-001'}).getByRole('cell').nth(1)).toHaveText('USD 2,200.00');
  await expect(page.getByText('Vendor suspended')).toBeVisible();
  await expect(page.getByText(/Authorization is not a payment/)).toBeVisible();
});

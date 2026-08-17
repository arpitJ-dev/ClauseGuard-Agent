import { expect, type Page, test } from "@playwright/test";
import path from "node:path";

const fixtures = path.resolve(import.meta.dirname, "fixtures");
const browserErrors = new WeakMap<Page, string[]>();

async function openIntake(page: Page): Promise<void> {
  const menu = page.getByRole("button", { name: "Toggle workspace panel" });
  if (await menu.isVisible()) await menu.click();
}

test.beforeEach(async ({ page }) => {
  const errors: string[] = [];
  browserErrors.set(page, errors);
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(page.getByText("Engine ready")).toBeAttached();
  await openIntake(page);
});

test.afterEach(async ({ page }) => {
  expect(browserErrors.get(page) ?? []).toEqual([]);
});

test("analyzes a contract and exposes an explainable report", async ({ page }) => {
  const response = await page.request.get("/");
  expect(response.headers()["content-security-policy"]).toContain("default-src 'self'");
  expect(response.headers()["content-security-policy"]).toContain("object-src 'none'");
  expect(response.headers()["permissions-policy"]).toContain("camera=()");
  expect(response.headers()["cross-origin-resource-policy"]).toBe("same-origin");

  await page
    .getByLabel("Contract", { exact: true })
    .setInputFiles(path.join(fixtures, "modified.txt"));
  await page.getByRole("button", { name: "Run analysis" }).click();

  await expect(page.getByRole("heading", { name: "SERVICE AGREEMENT" })).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByRole("heading", { name: "Accepted findings" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Score breakdown" }).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Supporting evidence" }).first()).toBeVisible();

  await page.getByRole("button", { name: "Audit" }).click();
  await expect(page.getByRole("heading", { name: "Analysis record" })).toBeVisible();
  await expect(page.getByText("Review limitations")).toBeVisible();

  await page.reload();
  await expect(page.getByText("Engine ready")).toBeAttached();
  await openIntake(page);
  await page
    .getByRole("button", { name: /modified\.txt\s+Analysis/i })
    .first()
    .click();
  await expect(page.getByRole("heading", { name: "SERVICE AGREEMENT" })).toBeVisible();
});

test("compares contract versions and identifies clause deltas", async ({ page }) => {
  await page.getByRole("button", { name: "Compare" }).click();
  await page
    .getByLabel("Original", { exact: true })
    .setInputFiles(path.join(fixtures, "original.txt"));
  await page
    .getByLabel("Modified", { exact: true })
    .setInputFiles(path.join(fixtures, "modified.txt"));
  await page.getByRole("button", { name: "Compare versions" }).click();

  await expect(page.getByText("Version comparison")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "Clause changes" })).toBeVisible();
  await expect(page.getByText("Changed", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("immediately on demand", { exact: false }).first()).toBeVisible();
});

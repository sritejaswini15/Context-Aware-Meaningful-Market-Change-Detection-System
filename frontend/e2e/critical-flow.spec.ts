import { expect, test } from "@playwright/test";

const shots = process.env.E2E_SCREENSHOTS;
const snap = async (page: import("@playwright/test").Page, name: string) => {
  if (shots) await page.screenshot({ path: `${shots}/${name}.png`, fullPage: true });
};

test("sign up → watchlist → market changes → since you last checked → see why → acknowledge", async ({ page }) => {
  const email = `e2e-${Date.now()}@example.com`;

  // 1. Sign up
  await page.goto("/signup");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("correct-horse-battery");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/onboarding/);

  // Start from a calm, deterministic market.
  const reset = await page.request.post("/api/demo/scenario", { data: { key: "NORMAL_MOVEMENT" } });
  expect(reset.ok()).toBeTruthy();

  // 2. Onboarding: welcome → stocks → sensitivity → start
  await expect(page.getByRole("heading", { name: "Welcome to Knoww." })).toBeVisible();
  await snap(page, "01-onboarding");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("button", { name: /NVDA/ })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("radio", { name: /Balanced/ }).click();
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: "Start monitoring" }).click();

  // 3. Command Center: nothing meaningful yet
  await expect(page.getByRole("heading", { name: "Since you last checked" })).toBeVisible();
  await expect(page.getByText("You're all caught up.")).toBeVisible();
  await snap(page, "02-all-caught-up");

  // 4. Create a second watchlist and add a stock
  await page.getByRole("link", { name: "Watchlists" }).first().click();
  await page.getByRole("button", { name: "New watchlist" }).click();
  await page.getByLabel("Name").fill("Semiconductors");
  await page.getByRole("button", { name: "Create" }).click();
  await page.getByRole("link", { name: /Semiconductors/ }).click();
  await page.getByRole("button", { name: "Add stock" }).first().click();
  await page.getByPlaceholder("Company or ticker").fill("AMD");
  await page.getByRole("button", { name: "Add", exact: true }).first().click();
  await expect(page.getByRole("dialog").getByRole("button", { name: "Added" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("link", { name: "AMD", exact: true })).toBeVisible();
  await snap(page, "03-watchlist");

  // 5. The market changes while the user is away (demo control in the top bar)
  await page.getByRole("button", { name: "Open demo market controls" }).click();
  await page.getByRole("button", { name: /Stock-specific drop/ }).click();
  await expect(page.getByRole("dialog")).toBeHidden();

  // 6. Return to the dashboard
  await page.getByRole("link", { name: "Command Center" }).click();
  const card = page.getByRole("article").filter({ hasText: "NVIDIA" });
  await expect(card).toBeVisible();
  await expect(card.getByText("High attention")).toBeVisible();
  await expect(card.getByText("since you last checked", { exact: true })).toBeVisible();
  await expect(page.getByText("You're all caught up.")).toBeHidden();
  await snap(page, "04-since-you-last-checked");

  // 7. Open the explanation
  await card.getByRole("button", { name: /See why/ }).click();
  const sheet = page.getByRole("dialog");
  await expect(sheet.getByText("Why it matters")).toBeVisible();
  await expect(sheet.getByText("How the score was calculated")).toBeVisible();
  await snap(page, "05-see-why");

  // 8. Acknowledge: no longer treated as new
  await sheet.getByRole("button", { name: "Mark as reviewed" }).click();
  await expect(sheet).toBeHidden();
  await expect(page.getByRole("heading", { name: "Reviewed" })).toBeVisible();
  await expect(page.getByRole("article").filter({ hasText: "NVIDIA" }).getByText("Reviewed")).toBeVisible();
  await snap(page, "06-reviewed");

  // 9. Stock investigation page renders the reasoning
  await page.goto("/stocks/NVDA");
  await expect(page.getByRole("heading", { name: "NVIDIA Corporation" })).toBeVisible();
  await expect(page.getByText("Is it the stock, the sector or the market?")).toBeVisible();
  await snap(page, "07-stock");
});

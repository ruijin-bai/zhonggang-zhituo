import { expect, test } from "@playwright/test";

const HERO_ID = "west-africa-port-access-corridor";
const HERO_TITLE = "西非港口集疏运走廊示范项目";

test("admin can create an assigned Pursuit Work Item through the real BFF", async ({ page }) => {
  const workItemTitle = `E2E 经营任务 ${Date.now()}`;

  await page.goto(`/pursuit/opportunities/${HERO_ID}`);

  await expect(page.getByRole("heading", { level: 1, name: HERO_TITLE })).toBeVisible();
  await expect(page.getByText("Canonical Pursuit Workspace")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Work Items" })).toBeVisible();

  const createForm = page
    .locator("form")
    .filter({ has: page.getByRole("button", { name: "创建 Work Item", exact: true }) });

  await createForm.locator('input[name="title"]').fill(workItemTitle);
  await createForm
    .locator('select[name="assignee_membership_id"]')
    .selectOption({ label: "智拓管理员 · admin" });
  await createForm.locator('select[name="priority"]').selectOption("high");

  const mutationCompleted = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/pursuit/mutate") &&
      response.request().method() === "POST" &&
      response.ok(),
  );
  await createForm.getByRole("button", { name: "创建 Work Item", exact: true }).click();
  await mutationCompleted;

  await page.goto("/pursuit");
  await expect(page.getByRole("heading", { level: 1, name: "我的经营工作" })).toBeVisible();
  await expect(page.getByRole("link", { name: workItemTitle, exact: true })).toBeVisible();
});

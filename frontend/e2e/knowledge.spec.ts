import { expect, test } from "@playwright/test";

test("student knowledge pages are removed while the rest of the product remains usable", async ({ page, request }) => {
  const suffix = `${Date.now()}`;
  const email = `knowledge-route-${suffix}@example.com`;
  const password = "KnowledgeRouteE2e123";
  let cleanupStatus = 204;
  try {
    await page.goto("/register", { waitUntil: "commit" });
    await page.getByLabel("用户名").fill(`route${suffix.slice(-8)}`);
    await page.getByLabel("昵称").fill("知识入口验收同学");
    await page.getByLabel("邮箱").fill(email);
    await page.getByLabel(/^密码/).fill(password);
    await page.getByRole("button", { name: "注册并登录" }).click();
    await expect(page.getByRole("heading", { name: /知识入口验收同学/ })).toBeVisible();
    await expect(page.getByRole("link", { name: "知识库" })).toHaveCount(0);

    await page.goto("/knowledge/import");
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("heading", { name: /读懂校园信息/ })).toBeVisible();

    await page.goto("/knowledge/sources");
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("link", { name: "问问大师兄", exact: true })).toBeVisible();
  } finally {
    const login = await request.post("http://127.0.0.1:8000/api/auth/login", { data: { email, password } });
    if (login.status() === 200) cleanupStatus = (await request.delete("http://127.0.0.1:8000/api/auth/account")).status();
  }
  expect(cleanupStatus).toBe(204);
});

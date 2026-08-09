import { expect, test } from "@playwright/test";

test("chat requests consent, resumes with current position and opens the real map route", async ({ page, context, request }) => {
  test.skip(process.env.E2E_REQUIRE_AMAP !== "1", "requires the owner's local AMap credentials");
  test.setTimeout(240_000);
  const suffix = Date.now();
  const email = `geo-${suffix}@example.com`;
  const password = "GeolocationPass123";
  const campuses = await (await request.get("http://127.0.0.1:8000/api/campuses")).json();
  const qingyuan = campuses.find((item: { slug: string }) => item.slug === "qingyuan");
  await context.grantPermissions(["geolocation"], { origin: "http://127.0.0.1:5173" });
  await context.setGeolocation({ latitude: 23.715, longitude: 113.084, accuracy: 18 });
  try {
    await page.goto("/register", { waitUntil: "commit" });
    await page.getByLabel("用户名").fill(`geo${String(suffix).slice(-8)}`);
    await page.getByLabel("昵称").fill("定位验收同学");
    await page.getByLabel("邮箱").fill(email);
    await page.getByLabel(/^密码/).fill(password);
    await page.getByLabel("所属校区").selectOption(qingyuan.id);
    await page.getByRole("button", { name: "注册并登录" }).click();
    await expect(page.getByRole("heading", { name: /定位验收同学，今天先做哪一件/ })).toBeVisible();
    await page.goto("/chat", { waitUntil: "commit" });
    await page.getByLabel("消息").fill("图书馆怎么走？");
    await page.getByRole("button", { name: "发送" }).click();
    const sheet = page.getByRole("dialog", { name: "用你的当前位置规划路线？" });
    await expect(sheet).toBeVisible({ timeout: 90_000 });
    await expect(sheet).toContainText("不会保存你的实时位置");
    await sheet.getByRole("button", { name: "使用我的位置" }).click();
    await expect(page.getByText(/后端尚未配置高德 WebService Key|路线已经算好/).first()).toBeVisible({ timeout: 90_000 });
    const mapLink = page.getByRole("link", { name: /开始导航|在地图中查看路线/ }).last();
    await expect(mapLink).toBeVisible();
    await mapLink.click();
    await expect(page.getByText("定位较准确")).toBeVisible();
    await expect(page.getByText(/km · 约/)).toBeVisible({ timeout: 60_000 });
    await expect(page.locator(".amap-marker").first()).toBeVisible();
    await expect.poll(async () => page.evaluate(async () => {
      const runs = await (await fetch("/api/agent/runs", { credentials: "include" })).json();
      return runs.find((run: { goal: string }) => run.goal.includes("图书馆怎么走"))?.status;
    })).toBe("completed");
  } finally {
    await request.post("http://127.0.0.1:8000/api/auth/login", { data: { email, password } });
    await request.delete("http://127.0.0.1:8000/api/auth/account");
  }
});

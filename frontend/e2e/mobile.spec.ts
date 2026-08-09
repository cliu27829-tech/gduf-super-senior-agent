import { expect, test } from "@playwright/test";

test("core student workflows remain usable on a phone viewport", async ({ page, request }) => {
  const suffix = `${Date.now()}`;
  const email = `mobile-${suffix}@example.com`;
  const password = "MobileE2ePassword123";
  let cleanupStatus = 204;

  await page.setViewportSize({ width: 390, height: 844 });
  try {
    await page.goto("/register", { waitUntil: "commit" });
    await page.getByLabel("用户名").fill(`mobile${suffix.slice(-8)}`);
    await page.getByLabel("昵称").fill("手机端同学");
    await page.getByLabel("邮箱").fill(email);
    await page.getByLabel(/^密码/).fill(password);
    await expect(page.getByLabel("所属校区")).not.toHaveValue("");
    await page.getByRole("button", { name: "注册并登录" }).click();
    await expect(page.getByRole("heading", { name: /手机端同学，今天先做哪一件/ })).toBeVisible();
    await expect(page.locator(".mobile-nav")).toBeVisible();

    for (const viewport of [
      { width: 390, height: 844 },
      { width: 393, height: 852 },
      { width: 412, height: 915 },
    ]) {
      await page.setViewportSize(viewport);
      await page.goto("/chat", { waitUntil: "commit" });
      await expect(page.getByRole("heading", { name: "问问大师兄" })).toBeVisible();
      await expect(page.getByLabel("消息")).toBeVisible();
      await expect(page.getByRole("button", { name: "发送" })).toBeVisible();
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(overflow).toBeLessThanOrEqual(1);
    }

    await page.setViewportSize({ width: 390, height: 844 });

    for (const [path, heading] of [
      ["/notifications", "先看清规则，再保存要做的事"],
      ["/tasks", "保留条件和证据的真实待办"],
      ["/processes", "按来源一步步把事情办完"],
    ] as const) {
      await page.goto(path, { waitUntil: "commit" });
      await expect(page.getByRole("heading", { name: heading })).toBeVisible();
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(overflow).toBeLessThanOrEqual(1);
    }
  } finally {
    const login = await request.post("http://127.0.0.1:8000/api/auth/login", { data: { email, password } });
    if (login.status() === 200) {
      cleanupStatus = (await request.delete("http://127.0.0.1:8000/api/auth/account")).status();
    }
  }
  expect(cleanupStatus).toBe(204);
});

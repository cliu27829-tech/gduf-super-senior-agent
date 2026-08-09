import { expect, test } from "@playwright/test";

test("Agent run pauses for location, resumes the same run, and exposes real action cards", async ({ page, context, request }) => {
  test.setTimeout(240_000);
  const suffix = `${Date.now()}`;
  const email = `agent-run-${suffix}@example.com`;
  const password = "AgentRunE2ePass123";
  const campuses = await (await request.get("http://127.0.0.1:8000/api/campuses")).json();
  const qingyuan = campuses.find((item: { slug: string }) => item.slug === "qingyuan");
  const chatPayloads: Record<string, unknown>[] = [];
  page.on("request", (outgoing) => {
    if (outgoing.url().includes("/api/agent/chat/stream") && outgoing.method() === "POST") {
      chatPayloads.push(outgoing.postDataJSON());
    }
  });
  page.on("dialog", (dialog) => dialog.accept());
  await context.grantPermissions(["geolocation"], { origin: "http://127.0.0.1:5173" });
  await context.setGeolocation({ latitude: 23.717, longitude: 113.087, accuracy: 180 });

  try {
    await page.goto("/register", { waitUntil: "commit" });
    await page.getByLabel("用户名").fill(`agentrun${suffix.slice(-7)}`);
    await page.getByLabel("昵称").fill("Agent验收同学");
    await page.getByLabel("邮箱").fill(email);
    await page.getByLabel(/^密码/).fill(password);
    await page.getByLabel("所属校区").selectOption(qingyuan.id);
    await page.getByRole("button", { name: "注册并登录" }).click();
    await expect(page.getByRole("heading", { name: /Agent验收同学，今天先做哪一件/ })).toBeVisible();
    await page.goto("/chat", { waitUntil: "commit" });
    await expect(page.getByRole("heading", { name: "问问大师兄" })).toBeVisible();

    await page.getByLabel("消息").fill("北饭怎么走？");
    await page.getByRole("button", { name: "发送" }).click();
    const sheet = page.getByRole("dialog", { name: "用你的当前位置规划路线？" });
    await expect(sheet).toBeVisible({ timeout: 90_000 });
    await expect(sheet.getByRole("button", { name: "使用我的位置" })).toBeEnabled();
    const pausedRunId = await page.evaluate(async () => {
      const response = await fetch("/api/agent/runs", { credentials: "include" });
      const runs = await response.json();
      return runs[0].id as string;
    });
    await sheet.getByRole("button", { name: "使用我的位置" }).click();
    await expect(page.getByText(/还没有经过核验的精确坐标|精确入口仍待管理员核验/).first()).toBeVisible({ timeout: 90_000 });
    expect(chatPayloads).toHaveLength(2);
    expect(chatPayloads[0].agent_run_id).toBeNull();
    expect(chatPayloads[1].agent_run_id).toBe(pausedRunId);
    expect(chatPayloads[1].resume_navigation).toBe(true);
    await expect(page.getByRole("link", { name: "开始导航" })).toHaveCount(0);

    await page.getByLabel("消息").fill("明天下午3点提醒我复习高数");
    await page.getByRole("button", { name: "发送" }).click();
    const action = page.getByRole("button", { name: "确认保存提醒" }).last();
    await expect(action).toBeVisible({ timeout: 90_000 });
    await action.click();
    await expect(page.getByText("已完成", { exact: true }).last()).toBeVisible();

    if (process.env.E2E_REQUIRE_AMAP === "1") {
      await page.goto("/map?origin=qy-library&waypoints=qy-ming-lake&destination=qy-mulan-square", { waitUntil: "commit" });
      await expect(page.getByText(/km · 约/)).toBeVisible({ timeout: 60_000 });
      await expect(page.locator(".amap-marker").first()).toBeVisible();
    }

    await page.setViewportSize({ width: 390, height: 844 });
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  } finally {
    await request.post("http://127.0.0.1:8000/api/auth/login", { data: { email, password } });
    await request.delete("http://127.0.0.1:8000/api/auth/account");
  }
});

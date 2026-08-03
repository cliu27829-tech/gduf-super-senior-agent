import { expect, test } from "@playwright/test";

test("registers and completes the three real MVP workflows", async ({ page }) => {
  const suffix = `${Date.now()}`;
  const email = `e2e-${suffix}@example.com`;
  const username = `e2e${suffix.slice(-8)}`;
  const password = "E2ePassword123";
  const consoleErrors: string[] = [];
  const failedRequests: string[] = [];
  const serverErrors: string[] = [];
  const clientErrors: string[] = [];

  page.on("console", (message) => { if (message.type() === "error" && !message.text().startsWith("Failed to load resource:")) consoleErrors.push(message.text()); });
  page.on("requestfailed", (request) => {
    const errorText = request.failure()?.errorText || "failed";
    // Chromium reports successful downloads and 204 responses as ERR_ABORTED in CDP.
    if (errorText !== "net::ERR_ABORTED") failedRequests.push(`${request.method()} ${request.url()} ${errorText}`);
  });
  page.on("response", (response) => {
    const status = response.status();
    if (status >= 500) serverErrors.push(`${status} ${response.url()}`);
    else if (status >= 400 && !(status === 401 && /\/api\/auth\/(me|refresh)$/.test(response.url()))) clientErrors.push(`${status} ${response.url()}`);
  });

  await page.goto("/register");
  await page.getByLabel("用户名").fill(username);
  await page.getByLabel("昵称").fill("端到端同学");
  await page.getByLabel("邮箱").fill(email);
  await page.getByLabel(/^密码/).fill(password);
  await expect(page.getByLabel("所属校区")).not.toHaveValue("");
  await page.getByRole("button", { name: "注册并登录" }).click();
  await expect(page.getByRole("heading", { name: /端到端同学，今天先做哪一件/ })).toBeVisible();

  await page.reload();
  await expect(page.getByRole("heading", { name: /端到端同学，今天先做哪一件/ })).toBeVisible();
  await page.getByRole("link", { name: "问师兄" }).first().click();

  const send = async (message: string) => {
    const assistantCount = await page.locator(".message.assistant").count();
    await page.getByLabel("消息").fill(message);
    await page.getByRole("button", { name: "发送" }).click();
    await expect(page.locator(".message.assistant")).toHaveCount(assistantCount + 1);
    return page.locator(".message.assistant").last();
  };

  const greeting = await send("你好，你能做什么？");
  await expect(greeting).toContainText("广金大师兄");
  await expect(greeting).toContainText("基础模式");

  const guidance = await send("大一高数跟不上怎么办？");
  await expect(guidance).toContainText(/概念|错题|基础题/);

  const food = await send("北苑饭堂有什么吃的？");
  await expect(food).toContainText("当日菜单");
  await expect(food.getByText("饭堂与档口")).toBeVisible();
  await expect(food.getByText("来源", { exact: true })).toBeVisible();

  await page.getByRole("link", { name: "处理通知" }).first().click();
  await page.getByLabel("通知文本").fill("请各班同学于2099年9月3日下午5点前提交学生信息表，文件命名为学号+姓名，发送给班长。材料：学生信息表");
  await page.getByRole("button", { name: "解析通知" }).click();
  const title = page.getByLabel("标题").first();
  await expect(title).toBeVisible();
  await title.fill("E2E 学生信息表");
  await page.getByRole("checkbox", { name: /我已逐项核对/ }).check();
  await page.getByRole("button", { name: /确认并保存 1 条任务/ }).click();
  await expect(page.getByRole("heading", { name: "任务已保存" })).toBeVisible();
  await page.getByRole("link", { name: "前往任务中心" }).click();
  await expect(page.getByText("E2E 学生信息表", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "编辑" }).click();
  await page.getByLabel("标题").fill("E2E 已编辑任务");
  await page.getByLabel("提交方式").fill("班群文件");
  await page.getByRole("button", { name: "保存任务" }).click();
  await expect(page.getByText("E2E 已编辑任务", { exact: true })).toBeVisible();

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: "导出全部 ICS" }).click();
  const download = await downloadPromise;
  const stream = await download.createReadStream();
  const chunks: Buffer[] = [];
  for await (const chunk of stream) chunks.push(Buffer.from(chunk));
  const ics = Buffer.concat(chunks).toString("utf8");
  expect((ics.match(/BEGIN:VALARM/g) || []).length).toBe(2);
  expect(ics).toContain("Asia/Shanghai");
  expect(ics).toContain("班群文件");

  await page.getByRole("button", { name: "退出" }).click();
  await expect(page.getByRole("heading", { name: "继续处理你的校园事项" })).toBeVisible();
  await page.getByLabel("邮箱").fill(email);
  await page.getByLabel(/^密码/).fill(password);
  await page.getByRole("button", { name: "登录" }).click();
  await page.getByRole("link", { name: "任务中心" }).first().click();
  await expect(page.getByText("E2E 已编辑任务", { exact: true })).toBeVisible();

  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "删除" }).click();
  await expect(page.getByText("E2E 已编辑任务", { exact: true })).toHaveCount(0);

  await page.getByRole("link", { name: "端" }).click();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "删除账户和个人数据" }).click();
  await expect(page.getByRole("link", { name: "登录" })).toBeVisible();

  expect(serverErrors).toEqual([]);
  expect(clientErrors).toEqual([]);
  expect(failedRequests).toEqual([]);
  expect(consoleErrors).toEqual([]);
});

import { expect, test } from "@playwright/test";

test("registers and completes the three real MVP workflows", async ({ page, request }) => {
  test.setTimeout(180_000);
  const suffix = `${Date.now()}`;
  const email = `e2e-${suffix}@example.com`;
  const username = `e2e${suffix.slice(-8)}`;
  const password = "E2ePassword123";
  const consoleErrors: string[] = [];
  const failedRequests: string[] = [];
  const serverErrors: string[] = [];
  const clientErrors: string[] = [];
  let cleanupStatus = 204;

  page.on("dialog", (dialog) => dialog.accept());
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

  try {
  await page.goto("/register", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "创建账号" })).toBeVisible();
  await page.getByLabel("用户名").fill(username);
  await page.getByLabel("昵称").fill("端到端同学");
  await page.getByLabel("邮箱").fill(email);
  await page.getByLabel(/^密码/).fill(password);
  await expect(page.getByLabel("所属校区")).not.toHaveValue("");
  await page.getByRole("button", { name: "注册并登录" }).click();
  await expect(page.getByRole("heading", { name: /端到端同学，今天先做哪一件/ })).toBeVisible();

  await page.reload({ waitUntil: "commit" });
  await expect(page.getByRole("heading", { name: /端到端同学，今天先做哪一件/ })).toBeVisible();
  await page.getByRole("link", { name: "问大师兄" }).first().click();
  await expect(page.getByRole("heading", { name: "问问大师兄" })).toBeVisible();
  await expect(page.locator(".connection-dot.online")).toBeVisible();
  await expect(page.locator(".message.assistant")).toHaveCount(1);

  const send = async (message: string) => {
    const answers = page.locator(".message.assistant");
    const assistantCount = await answers.count();
    await page.getByLabel("消息").fill(message);
    await page.getByRole("button", { name: "发送" }).click();
    await expect(answers).toHaveCount(assistantCount + 1);
    const answer = answers.last();
    await expect(answer.locator(".markdown-message")).toBeVisible({ timeout: 90_000 });
    await expect(answer.locator(".typing-cursor")).toHaveCount(0);
    await expect(page.locator(".stop-button")).toHaveCount(0);
    return answer;
  };

  const greeting = await send("你好，你能做什么？");
  await expect(greeting).not.toContainText("基础模式");
  expect((await greeting.innerText()).length).toBeGreaterThan(30);

  const guidance = await send("大一高数跟不上怎么办？");
  expect((await guidance.innerText()).length).toBeGreaterThan(30);

  await send("我叫小明，请记住。");
  const memory = await send("我刚才说我叫什么？");
  await expect(memory).toContainText("小明");

  const food = await send("北苑饭堂有什么吃的？");
  await expect(food).toContainText(/历史|待核验|不代表现在|不提供可靠实时菜单/);
  await expect(food).not.toContainText(/这是今天的菜单|当日实时菜单/);
  await expect(food.getByText("饭堂与档口")).toBeVisible();
  await expect(food.getByText("查看来源", { exact: true })).toBeVisible();

  await page.getByRole("link", { name: "校园地图" }).first().click();
  await expect(
    page.getByLabel(/高德真实道路地图/).or(page.getByRole("heading", { name: "需要配置高德地图凭据" })),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: /北苑饭堂/ })).toBeVisible();

  await page.goto("/processes", { waitUntil: "commit" });
  await page.getByRole("button", { name: /校园卡丢失挂失与补卡/ }).click();
  await expect(page.getByText("校园卡办理流程")).toBeVisible();
  const processTasksResponse = page.waitForResponse((response) =>
    response.url().includes("/create-tasks") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "确认并保存为任务" }).click();
  expect((await processTasksResponse).ok()).toBe(true);
  await expect(page.getByText(/已保存 \d+ 条任务/)).toBeVisible();

  await page.getByRole("link", { name: "通知" }).first().click();
  await page.getByLabel("通知原文").fill("请各班同学于2099年9月3日下午5点前提交学生信息表，文件命名为学号+姓名，发送给班长。材料：学生信息表");
  await page.getByRole("button", { name: "解析通知" }).click();
  const title = page.getByLabel("任务标题").first();
  await expect(title).toBeVisible();
  await title.fill("E2E 学生信息表");
  await page.getByRole("checkbox", { name: /我已核对任务/ }).check();
  await page.getByRole("button", { name: /确认并保存 1 条任务/ }).click();
  await expect(page.getByRole("heading", { name: "任务已保存" })).toBeVisible();
  await page.getByRole("link", { name: "前往任务中心" }).click();
  await expect(page.getByText("E2E 学生信息表", { exact: true })).toBeVisible();

  await page.locator("article.task-table-row").filter({ hasText: "E2E 学生信息表" }).getByRole("button", { name: "编辑" }).click();
  await page.getByRole("textbox", { name: "标题", exact: true }).fill("E2E 已编辑任务");
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
  await expect(page.getByRole("heading", { name: "校园里的事情，接着交给大师兄。" })).toBeVisible();
  await page.getByLabel("邮箱").fill(email);
  await page.getByLabel(/^密码/).fill(password);
  await page.getByRole("button", { name: "登录" }).click();
  await page.getByRole("link", { name: "任务" }).first().click();
  await expect(page.getByText("E2E 已编辑任务", { exact: true })).toBeVisible();

  await page.locator("article.task-table-row").filter({ hasText: "E2E 已编辑任务" }).getByRole("button", { name: "删除" }).click();
  await expect(page.getByText("E2E 已编辑任务", { exact: true })).toHaveCount(0);

  await page.getByRole("link", { name: "端" }).click();
  await page.getByRole("button", { name: "删除账户和个人数据" }).click();
  await expect(page.getByRole("link", { name: "登录" })).toBeVisible();

  expect(serverErrors).toEqual([]);
  expect(clientErrors).toEqual([]);
  expect(failedRequests).toEqual([]);
  expect(consoleErrors).toEqual([]);
  } finally {
    const login = await request.post("http://127.0.0.1:8000/api/auth/login", { data: { email, password } });
    if (login.status() === 200) {
      cleanupStatus = (await request.delete("http://127.0.0.1:8000/api/auth/account")).status();
    }
  }
  expect(cleanupStatus).toBe(204);
});

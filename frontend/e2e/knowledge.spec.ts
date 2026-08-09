import { expect, test } from "@playwright/test";

test("imports, deduplicates, searches, opens, and deletes private knowledge", async ({ page, request }) => {
  test.setTimeout(120_000);
  const suffix = `${Date.now()}`;
  const email = `knowledge-${suffix}@example.com`;
  const username = `knowledge${suffix.slice(-8)}`;
  const password = "KnowledgeE2ePassword123";

  await expect.poll(async () => (await request.get("http://127.0.0.1:8000/ready")).status()).toBe(200);
  await expect.poll(async () => (await request.get("http://127.0.0.1:5173/login")).status()).toBe(200);

  await page.goto("/register", { waitUntil: "commit" });
  await page.getByLabel("用户名").fill(username);
  await page.getByLabel("昵称").fill("知识验收同学");
  await page.getByLabel("邮箱").fill(email);
  await page.getByLabel(/^密码/).fill(password);
  await page.getByRole("button", { name: "注册并登录" }).click();
  await expect(page.getByRole("heading", { name: /知识验收同学，今天先做哪一件/ })).toBeVisible();

  let cleanupStatus: number;
  try {
    await page.goto("/knowledge/import");
    const textForm = page.getByRole("heading", { name: "粘贴文章正文" }).locator("..");
    await textForm.getByLabel("标题").fill("奖学金申请说明");
    await textForm.getByLabel("发布者（可选）").fill("个人整理");
    await textForm.getByLabel("正文").fill("奖学金申请需要准备成绩单和申请材料，正式时间以学校通知为准。");
    await textForm.getByRole("button", { name: "保存并建立索引" }).click();
    await expect(page.getByRole("status")).toContainText("导入 1 篇");

    await textForm.getByLabel("标题").fill("奖学金申请说明");
    await textForm.getByLabel("正文").fill("奖学金申请需要准备成绩单和申请材料，正式时间以学校通知为准。");
    await textForm.getByRole("button", { name: "保存并建立索引" }).click();
    await expect(page.getByRole("status")).toContainText("跳过重复 1 篇");

    await page.getByRole("link", { name: "来源与检索" }).click();
    await expect(page.getByRole("heading", { name: "资料来源" })).toBeVisible();
    await page.getByPlaceholder("例如：奖学金申请条件").fill("奖学金申请");
    await page.getByRole("button", { name: "搜索" }).click();
    await expect(page.getByRole("heading", { name: "检索结果" })).toBeVisible();
    await page.getByText("奖学金申请说明").first().click();
    const drawer = page.getByRole("complementary", { name: "知识来源详情" });
    await expect(drawer).toContainText("仅自己可见");
    await expect(drawer).toContainText("成绩单和申请材料");
    page.once("dialog", (dialog) => dialog.accept());
    await drawer.getByRole("button", { name: "删除资料" }).click();
    await expect(page.getByText("奖学金申请说明")).toHaveCount(0);
  } finally {
    await request.post("http://127.0.0.1:8000/api/auth/login", { data: { email, password } });
    cleanupStatus = (await request.delete("http://127.0.0.1:8000/api/auth/account")).status();
  }
  expect(cleanupStatus).toBe(204);
});

test("imports an owner-authorized PDF text layer without persisting the raw file", async ({ page, request }) => {
  const pdfPath = process.env.E2E_PRIVATE_PDF;
  test.skip(!pdfPath, "requires an explicitly approved local PDF path");
  test.setTimeout(120_000);
  const suffix = `${Date.now()}`;
  const email = `knowledge-pdf-${suffix}@example.com`;
  const password = "KnowledgePdfE2ePassword123";
  let cleanupStatus: number;
  try {
    await page.goto("/register", { waitUntil: "commit" });
    await page.getByLabel("用户名").fill(`knowledgepdf${suffix.slice(-8)}`);
    await page.getByLabel("昵称").fill("PDF验收同学");
    await page.getByLabel("邮箱").fill(email);
    await page.getByLabel(/^密码/).fill(password);
    await page.getByRole("button", { name: "注册并登录" }).click();
    await expect(page.getByRole("heading", { name: /PDF验收同学，今天先做哪一件/ })).toBeVisible();
    await page.goto("/knowledge/import");
    await page.getByLabel("选择知识文件").setInputFiles(pdfPath!);
    await expect(page.getByRole("status")).toContainText("待导入 1 个文件");
    await page.getByRole("button", { name: "导入文件" }).click();
    await expect(page.getByRole("status")).toContainText("导入 1 篇", { timeout: 60_000 });
    await page.getByRole("link", { name: "来源与检索" }).click();
    await expect(page.getByText(/个检索分块/).first()).toBeVisible();
  } finally {
    await request.post("http://127.0.0.1:8000/api/auth/login", { data: { email, password } });
    cleanupStatus = (await request.delete("http://127.0.0.1:8000/api/auth/account")).status();
  }
  expect(cleanupStatus).toBe(204);
});

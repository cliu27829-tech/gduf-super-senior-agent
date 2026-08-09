import { expect, test } from "@playwright/test";

test("admin reviews private knowledge and the owner sees the shared update", async ({ page, request }) => {
  const adminEmail = process.env.E2E_ADMIN_EMAIL;
  const adminPassword = process.env.E2E_ADMIN_PASSWORD;
  test.skip(!adminEmail || !adminPassword, "requires an ephemeral local E2E admin account");
  test.setTimeout(120_000);
  const suffix = `${Date.now()}`;
  const email = `review-owner-${suffix}@example.com`;
  const password = "ReviewOwnerE2ePassword123";

  let documentId = "";
  let ownerCleanupStatus = 204;
  let documentCleanupStatus = 204;
  try {
    await page.goto("/register", { waitUntil: "commit" });
    await page.getByLabel("用户名").fill(`reviewowner${suffix.slice(-8)}`);
    await page.getByLabel("昵称").fill("审核资料同学");
    await page.getByLabel("邮箱").fill(email);
    await page.getByLabel(/^密码/).fill(password);
    await page.getByRole("button", { name: "注册并登录" }).click();
    await expect(page.getByRole("heading", { name: /审核资料同学，今天先做哪一件/ })).toBeVisible();
    const importResult = await page.evaluate(async () => {
      const response = await fetch("/api/knowledge/import/text", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: "管理员审核验收资料", content: "这是一条仅用于本地端到端审核的资料，审核前只对导入用户可见。" }),
      });
      if (!response.ok) throw new Error(`knowledge import failed: ${response.status}`);
      return response.json() as Promise<{ document_ids: string[] }>;
    });
    documentId = importResult.document_ids[0] || "";
    expect(documentId).not.toBe("");
    await page.getByRole("button", { name: "退出" }).click();

    await page.goto("/login", { waitUntil: "commit" });
    await page.getByLabel("邮箱").fill(adminEmail!);
    await page.getByLabel(/^密码/).fill(adminPassword!);
    await page.getByRole("button", { name: "登录" }).click();
    await expect(page.getByRole("link", { name: "管理后台" })).toBeVisible();
    await page.goto("/admin/knowledge", { waitUntil: "commit" });
    await expect(page.getByRole("heading", { name: "内部知识资料审核" })).toBeVisible();
    await expect(page.getByText("管理员审核验收资料").first()).toBeVisible();

    const promptAnswers = ["对照本地验收原文", "title,content", "验收测试证据", "仅用于自动测试"];
    page.on("dialog", async (dialog) => {
      if (dialog.type() === "prompt") await dialog.accept(promptAnswers.shift() || "自动测试");
      else await dialog.accept();
    });
    await page.getByRole("button", { name: "核验并共享" }).first().click();
    await expect(page.getByText("知识资料审核已保存，核验记录和管理员审计日志均已写入")).toBeVisible();

    await page.getByRole("button", { name: "退出" }).click();
    await page.goto("/login", { waitUntil: "commit" });
    await page.getByLabel("邮箱").fill(email);
    await page.getByLabel(/^密码/).fill(password);
    await page.getByRole("button", { name: "登录" }).click();
    await expect(page.getByRole("heading", { name: /审核资料同学，今天先做哪一件/ })).toBeVisible();
    const ownerSource = await page.evaluate(async (sourceId) => {
      const response = await fetch(`/api/knowledge/sources/${sourceId}`, { credentials: "include" });
      return { status: response.status, body: await response.json() as { visibility: string; review_status: string } };
    }, documentId);
    expect(ownerSource.status).toBe(200);
    expect(ownerSource.body.visibility).toBe("public");
    expect(ownerSource.body.review_status).toBe("approved");
  } finally {
    const ownerLogin = await request.post("http://127.0.0.1:8000/api/auth/login", { data: { email, password } });
    if (ownerLogin.status() === 200) {
      if (documentId) {
        documentCleanupStatus = (await request.delete(
          `http://127.0.0.1:8000/api/knowledge/sources/${documentId}?confirmed=true`,
        )).status();
      }
      ownerCleanupStatus = (await request.delete("http://127.0.0.1:8000/api/auth/account")).status();
    }
  }
  expect(ownerCleanupStatus).toBe(204);
  expect(documentCleanupStatus).toBe(204);
});

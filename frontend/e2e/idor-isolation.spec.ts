import { expect, request as playwrightRequest, test } from "@playwright/test";

test("two users cannot read, change, continue or export each other's resources", async ({ page }) => {
  const apiBase = "http://127.0.0.1:8000/api";
  const suffix = Date.now();
  const campuses = await (await page.request.get(`${apiBase}/campuses`)).json();
  const campusId = campuses[0].id as string;
  const password = "IsolationPass123";
  const a = await playwrightRequest.newContext();
  const b = await playwrightRequest.newContext();
  const account = (label: string) => ({
    username: `${label}${suffix}`,
    nickname: `${label.toUpperCase()}同学`,
    email: `${label}-${suffix}@example.com`,
    password,
    campus_id: campusId,
    grade: "2026级",
    major: "测试专业",
  });
  const accountA = account("idora");
  const accountB = account("idorb");
  try {
    expect((await a.post(`${apiBase}/auth/register`, { data: accountA })).status()).toBe(201);
    const task = await (await a.post(`${apiBase}/tasks`, { data: {
      title: "A 的隐藏任务", description: "只属于A", deadline: "2099-09-03T17:00:00+08:00",
      location: "", course: "", task_type: "general", materials: [], submission_target: "",
      submission_method: "", file_naming: "", source_text: "", reminder_minutes: [], confirmed: true,
    } })).json();
    const note = await (await a.post(`${apiBase}/notes`, { data: { title: "A 的隐藏便签", content: "私有内容", confirmed: true } })).json();
    const conversation = await (await a.post(`${apiBase}/agent/conversations`)).json();

    expect((await b.post(`${apiBase}/auth/register`, { data: accountB })).status()).toBe(201);
    for (const response of [
      await b.get(`${apiBase}/tasks/${task.id}`),
      await b.patch(`${apiBase}/tasks/${task.id}`, { data: { title: "越权修改", confirmed: true } }),
      await b.get(`${apiBase}/tasks/export/ics?task_ids=${task.id}`),
      await b.get(`${apiBase}/notes/${note.id}`),
      await b.delete(`${apiBase}/notes/${note.id}?confirmed=true`),
      await b.get(`${apiBase}/agent/conversations/${conversation.id}`),
      await b.post(`${apiBase}/agent/chat`, { data: { message: "继续", conversation_id: conversation.id } }),
      await b.delete(`${apiBase}/agent/conversations/${conversation.id}`),
    ]) expect(response.status()).toBe(404);

    await page.goto("/login", { waitUntil: "commit" });
    await page.getByLabel("邮箱").fill(accountB.email);
    await page.getByLabel(/^密码/).fill(password);
    await page.getByRole("button", { name: "登录" }).click();
    await page.goto("/tasks", { waitUntil: "commit" });
    await expect(page.getByText("A 的隐藏任务", { exact: true })).toHaveCount(0);
    await page.goto("/profile", { waitUntil: "commit" });
    await expect(page.getByText("A 的隐藏便签", { exact: true })).toHaveCount(0);
  } finally {
    await a.delete(`${apiBase}/auth/account`);
    await b.delete(`${apiBase}/auth/account`);
    await a.dispose(); await b.dispose();
  }
});

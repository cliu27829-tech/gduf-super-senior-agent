import { expect, test } from "@playwright/test";

test("loads the configured AMap base map and geocoded campus marker", async ({ page, request }) => {
  test.skip(process.env.E2E_REQUIRE_AMAP !== "1", "requires the owner's local AMap credentials");
  test.setTimeout(180_000);
  const suffix = `${Date.now()}`;
  const email = `amap-${suffix}@example.com`;
  const username = `amap${suffix.slice(-8)}`;
  const password = "AmapE2ePassword123";
  const consoleErrors: string[] = [];
  const unexpectedRequestFailures: string[] = [];
  const failedMapResponses: string[] = [];
  let sawSuccessfulMapResponse = false;

  await page.setViewportSize({ width: 1280, height: 1100 });
  await expect.poll(async () => (await request.get("http://127.0.0.1:8000/ready")).status()).toBe(200);
  await expect.poll(async () => (await request.get("http://127.0.0.1:5173/login")).status()).toBe(200);

  page.on("console", (message) => {
    const text = message.text();
    const expectedHeadlessRendererNoise = text === "Network error" || text.includes("OES_element_index_uint failed");
    if (message.type() === "error" && !text.startsWith("Failed to load resource:") && !expectedHeadlessRendererNoise) {
      consoleErrors.push(text);
    }
  });
  page.on("requestfailed", (request) => {
    const requestUrl = new URL(request.url());
    const failure = `${requestUrl.hostname}${requestUrl.pathname} ${request.failure()?.errorText || "failed"}`;
    if (failure.includes("google")) return;
    const isAmapTileRequest = /(?:jsapi-data\d*|jsapi)\.amap\.com/.test(failure);
    const isExpectedCancellation = /ERR_(?:ABORTED|INSUFFICIENT_RESOURCES)/.test(failure);
    if (!(isAmapTileRequest && isExpectedCancellation)) unexpectedRequestFailures.push(failure);
  });
  page.on("response", (response) => {
    if (!/amap|_AMapService/i.test(response.url())) return;
    const requestUrl = new URL(response.url());
    if (response.status() >= 200 && response.status() < 400) {
      sawSuccessfulMapResponse = true;
    } else {
      failedMapResponses.push(`${requestUrl.hostname}${requestUrl.pathname} ${response.status()}`);
    }
  });

  await page.goto("/register", { waitUntil: "commit" });
  await expect(page.getByRole("heading", { name: "创建账号" })).toBeVisible();
  await page.getByLabel("用户名").fill(username);
  await page.getByLabel("昵称").fill("地图验收同学");
  await page.getByLabel("邮箱").fill(email);
  await page.getByLabel(/^密码/).fill(password);
  await page.getByRole("button", { name: "注册并登录" }).click();
  await expect(page.getByRole("heading", { name: /地图验收同学，今天先做哪一件/ })).toBeVisible();

  let cleanupStatus: number;
  try {
    await page.getByRole("link", { name: "校园地图" }).first().click();
  const canvas = page.getByLabel(/广州校本部高德真实道路地图/);
  await expect(canvas).toBeVisible();
  await expect(page.locator(".amap-maps")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".amap-marker").first()).toBeVisible({ timeout: 30_000 });
  const canvasBox = await canvas.boundingBox();
  expect(canvasBox).not.toBeNull();
  await expect.poll(async () => page.locator(".amap-marker").evaluateAll((elements, bounds) => elements.some((element) => {
    const rect = element.getBoundingClientRect();
    const centerX = rect.x + rect.width / 2;
    const centerY = rect.y + rect.height / 2;
    return rect.width > 0 && rect.height > 0
      && centerX >= bounds.x && centerX <= bounds.x + bounds.width
      && centerY >= bounds.y && centerY <= bounds.y + bounds.height;
  }), canvasBox!)).toBe(true);
  const markerPoint = await page.locator(".amap-marker").evaluateAll((elements, bounds) => {
    const marker = elements.find((element) => {
      const rect = element.getBoundingClientRect();
      const centerX = rect.x + rect.width / 2;
      const centerY = rect.y + rect.height / 2;
      return rect.width > 0 && rect.height > 0
        && centerX >= bounds.x && centerX <= bounds.x + bounds.width
        && centerY >= bounds.y && centerY <= bounds.y + bounds.height;
    });
    if (!marker) return null;
    const rect = marker.getBoundingClientRect();
    return { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 };
  }, canvasBox!);
  expect(markerPoint).not.toBeNull();
  await page.mouse.click(markerPoint!.x, markerPoint!.y);
  await expect(page.getByRole("complementary", { name: "地点详情" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "广州校本部" })).toBeVisible();
  await page.getByRole("button", { name: "关闭" }).click();

  await page.getByLabel("路线终点地址").fill("广州市天河区龙洞迎龙路");
  await page.getByRole("button", { name: "规划步行路线" }).click();
  await expect(page.getByText(/km · 约/)).toBeVisible({ timeout: 45_000 });
  await expect(page.getByText("查看路线步骤")).toBeVisible();

  const campus = page.getByRole("combobox", { name: "选择校区" });
  await page.getByRole("option", { name: "肇庆校区" });
  await page.getByRole("option", { name: "清远校区" });
  await page.selectOption("select[aria-label='选择校区']", { label: "肇庆校区" });
  await expect(campus).toHaveValue(/.+/);
  await expect(page.getByLabel(/肇庆校区高德真实道路地图/)).toBeVisible();
  await expect(page.locator(".amap-maps").last()).toBeVisible({ timeout: 30_000 });

  expect(sawSuccessfulMapResponse).toBe(true);
  expect(failedMapResponses).toEqual([]);
  expect(unexpectedRequestFailures).toEqual([]);
    expect(consoleErrors).toEqual([]);
  } finally {
    await request.post("http://127.0.0.1:8000/api/auth/login", { data: { email, password } });
    cleanupStatus = (await request.delete("http://127.0.0.1:8000/api/auth/account")).status();
  }
  expect(cleanupStatus).toBe(204);
});

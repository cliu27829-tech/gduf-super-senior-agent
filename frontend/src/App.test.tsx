import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";
import { campus, json, renderAt, routeFetch, user } from "./test/test-utils";

afterEach(() => vi.unstubAllGlobals());

describe("public and route guards", () => {
  it("renders the product promise and honest realtime disclaimer", async () => {
    vi.stubGlobal("fetch", routeFetch({
      "/api/auth/me": () => json({ detail: "unauthorized" }, 401),
      "/api/campuses": [campus],
    }));
    renderAt("/", <App />);
    expect(screen.getByRole("heading", { name: /读懂校园信息/ })).toBeInTheDocument();
    expect(screen.getByText(/当前没有可靠的实时饭堂菜单/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("广州校本部")).toBeInTheDocument());
  });

  it("redirects anonymous visitors from protected pages to login", async () => {
    vi.stubGlobal("fetch", routeFetch({
      "/api/auth/me": () => json({ detail: "unauthorized" }, 401),
      "/api/campuses": [campus],
    }));
    renderAt("/tasks", <App />);
    expect(await screen.findByRole("heading", { name: "继续处理你的校园事项" })).toBeInTheDocument();
  });

  it("renders registration fields and the selected campus", async () => {
    vi.stubGlobal("fetch", routeFetch({
      "/api/auth/me": () => json({ detail: "unauthorized" }, 401),
      "/api/campuses": [campus],
    }));
    renderAt("/register", <App />);
    expect(await screen.findByRole("heading", { name: "先选校区，再把事情办明白" })).toBeInTheDocument();
    expect(screen.getByLabelText("邮箱")).toBeInTheDocument();
    expect(screen.getByLabelText(/^密码/)).toBeInTheDocument();
    expect(await screen.findByRole("option", { name: "广州校本部" })).toBeInTheDocument();
  });

  it("redirects ordinary users away from the admin area", async () => {
    vi.stubGlobal("fetch", routeFetch({
      "/api/auth/me": user,
      "/api/tasks": [],
      "/api/campuses": [campus],
    }));
    renderAt("/admin", <App />);
    expect(await screen.findByRole("heading", { name: /同学，今天先做哪一件/ })).toBeInTheDocument();
    expect(screen.queryByText("数据管理后台")).not.toBeInTheDocument();
  });

  it("allows administrators into the management dashboard", async () => {
    vi.stubGlobal("fetch", routeFetch({
      "/api/auth/me": { ...user, role: "admin" },
      "/api/admin/dashboard": { users: 4, active_users: 4, locations: 12, canteens: 3, pending_feedback: 1, stale_records: 2, recent_errors: 0 },
      "/api/campuses": [campus],
    }));
    renderAt("/admin", <App />);
    expect(await screen.findByText("数据管理后台")).toBeInTheDocument();
    expect(await screen.findByText("数据发布原则")).toBeInTheDocument();
    expect(await screen.findByText("12")).toBeInTheDocument();
  });
});

describe("campus workflows", () => {
  it("submits a real login request and opens the protected dashboard", async () => {
    let submitted = false;
    vi.stubGlobal("fetch", routeFetch({
      "/api/auth/login": (_input: RequestInfo | URL, init?: RequestInit) => {
        submitted = JSON.parse(String(init?.body)).email === user.email;
        return json({ user });
      },
      "/api/auth/me": () => json({ detail: "unauthorized" }, 401),
      "/api/campuses": [campus],
      "/api/tasks": [],
    }));
    renderAt("/login", <App />);
    await userEvent.type(await screen.findByLabelText("邮箱"), user.email);
    await userEvent.type(screen.getByLabelText(/^密码/), "Password123");
    await userEvent.click(screen.getByRole("button", { name: "登录" }));
    expect(await screen.findByRole("heading", { name: /同学，今天先做哪一件/ })).toBeInTheDocument();
    expect(submitted).toBe(true);
  });

  it("sends chat input and renders the answer, tool result and source", async () => {
    vi.stubGlobal("fetch", routeFetch({
      "/api/auth/me": user,
      "/api/agent/conversations": [],
      "/api/agent/chat": {
        conversation_id: "conversation-1", message_id: "message-1", intent: "campus_location_search",
        answer: "图书馆位于东区。", degraded: false, data_status: "verified",
        tool_results: [{ tool: "location_search", status: "success", title: "校园地点", data: [{ id: "lib", name: "图书馆", area: "东区" }] }],
        sources: [{ title: "校方地点说明", url: "https://example.edu", publisher: "广东金融学院" }],
      },
    }));
    renderAt("/chat", <App />);
    await userEvent.type(await screen.findByLabelText("消息"), "图书馆在哪里？");
    await userEvent.click(screen.getByRole("button", { name: "发送" }));
    expect(await screen.findByText("图书馆位于东区。")).toBeInTheDocument();
    expect(screen.getByText("校园地点")).toBeInTheDocument();
    expect(screen.getByText("校方地点说明")).toBeInTheDocument();
  });

  it("shows canteen records with a non-realtime warning", async () => {
    vi.stubGlobal("fetch", routeFetch({
      "/api/auth/me": user,
      "/api/campuses": [campus],
      "/api/canteens": [{
        id: "canteen-1", campus_id: campus.id, location_id: null, name: "第一饭堂",
        floors: ["一楼"], opening_hours: "待核验", payment_methods: [], verification_status: "needs_verification",
        data_status: "historical", verified_at: null, confidence: 0.3, is_active: true, stalls: [], source: null,
        today_menu_available: false, today_menu_message: "没有可靠的今日菜单数据",
      }],
    }));
    renderAt("/canteens", <App />);
    expect(await screen.findByRole("heading", { name: "第一饭堂" })).toBeInTheDocument();
    expect(screen.getByText("今日菜单：暂无可靠数据")).toBeInTheDocument();
    expect(screen.getByText(/不会根据旧资料或模型猜测/)).toBeInTheDocument();
  });

  it("shows a visible error when canteen API loading fails", async () => {
    vi.stubGlobal("fetch", routeFetch({
      "/api/auth/me": user,
      "/api/campuses": [campus],
      "/api/canteens": () => json({ detail: "饭堂服务暂时不可用" }, 503),
    }));
    renderAt("/canteens", <App />);
    expect(await screen.findByRole("alert")).toHaveTextContent("饭堂服务暂时不可用");
  });

  it("filters map locations and opens a sourced detail drawer", async () => {
    vi.stubGlobal("fetch", routeFetch({
      "/api/auth/me": user,
      "/api/campuses": [campus],
      "/api/locations": [
        { id: "lib", campus_id: campus.id, name: "图书馆", aliases: [], category: "library", sub_category: "", description: "自习", address: "校园内", area: "东区", floor: "", latitude: null, longitude: null, map_x: 0.3, map_y: 0.4, opening_hours: "待核验", phone: "", services: [], payment_methods: [], verification_status: "verified", verification_method: "manual", verified_at: "2026-08-01T00:00:00Z", verified_by: "admin", confidence: 0.9, freshness_status: "current", data_status: "verified", is_active: true, updated_at: "2026-08-03T00:00:00Z", sources: [{ id: "source-1", title: "校方地点说明", url: "https://example.edu", publisher: "广东金融学院", source_type: "official", published_at: null, fetched_at: null, verified_at: null, confidence: 1, is_official: true }] },
        { id: "shop", campus_id: campus.id, name: "校园超市", aliases: [], category: "supermarket", sub_category: "", description: "", address: "西区", area: "", floor: "", latitude: null, longitude: null, map_x: 0.6, map_y: 0.5, opening_hours: "", phone: "", services: [], payment_methods: [], verification_status: "needs_verification", verification_method: "seed", verified_at: null, verified_by: "", confidence: 0.2, freshness_status: "needs_verification", data_status: "seed", is_active: true, updated_at: "2026-08-03T00:00:00Z", sources: [] },
      ],
    }));
    renderAt("/map", <App />);
    expect(await screen.findByRole("button", { name: "查看图书馆" })).toBeInTheDocument();
    await userEvent.type(screen.getByPlaceholderText(/搜索教学楼/), "图书");
    expect(screen.queryByRole("button", { name: "查看校园超市" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "查看图书馆" }));
    expect(screen.getByRole("complementary", { name: "地点详情" })).toBeInTheDocument();
    expect(screen.getByText("校方地点说明")).toBeInTheDocument();
  });

  it("parses a notification into editable drafts before saving", async () => {
    const savedTask = { id: "saved-task", user_id: user.id, title: "提交课程报告", description: "", deadline: "2099-09-03T17:00:00+08:00", location: "教学平台", course: "", task_type: "general", materials: ["报告"], submission_target: "任课老师", submission_method: "在线提交", file_naming: "学号-姓名", source_text: "通知", source_url: "", status: "pending", needs_confirmation: false, completed_at: null, created_at: "2026-08-03T00:00:00Z", updated_at: "2026-08-03T00:00:00Z" };
    vi.stubGlobal("fetch", routeFetch({
      "/api/auth/me": user,
      "/api/notifications/parse": {
        drafts: [{ title: "提交课程报告", deadline: "2099-09-03T17:00:00+08:00", location: "教学平台", materials: ["报告"], submission_target: "任课老师", submission_method: "在线提交", file_naming: "学号-姓名", notes: "", source_text: "通知", source_url: "", needs_confirmation: false, confidence: 0.9, date_explanation: "已识别明确日期" }],
        extraction_mode: "rules",
        warning: "当前使用规则解析，请核对日期。",
      },
      "/api/notifications/confirm": [savedTask],
    }));
    renderAt("/notifications", <App />);
    const input = await screen.findByLabelText("通知文本");
    await userEvent.type(input, "9月3日前提交课程报告");
    await userEvent.click(screen.getByRole("button", { name: "解析通知" }));
    expect(await screen.findByDisplayValue("提交课程报告")).toBeInTheDocument();
    expect(screen.getByText("当前使用规则解析，请核对日期。")).toBeInTheDocument();
    const save = screen.getByRole("button", { name: /确认并保存 1 条任务/ });
    expect(save).toBeDisabled();
    await userEvent.click(screen.getByRole("checkbox", { name: /我已逐项核对/ }));
    expect(save).toBeEnabled();
    await userEvent.click(save);
    expect(await screen.findByRole("heading", { name: "任务已保存" })).toBeInTheDocument();
  });

  it("keeps campuses separated in the selector", async () => {
    const secondCampus = { ...campus, id: "campus-zq", slug: "zhaoqing", name: "肇庆校区" };
    vi.stubGlobal("fetch", routeFetch({
      "/api/auth/me": user,
      "/api/campuses": [campus, secondCampus],
      "/api/locations": [],
    }));
    renderAt("/map", <App />);
    const selector = await screen.findByRole("combobox", { name: "选择校区" });
    await screen.findByRole("option", { name: "肇庆校区" });
    expect(selector).toHaveValue(campus.id);
    await userEvent.selectOptions(selector, secondCampus.id);
    await waitFor(() => expect(selector).toHaveValue(secondCampus.id));
  });

  it("opens an existing task in the edit drawer", async () => {
    vi.stubGlobal("fetch", routeFetch({
      "/api/auth/me": user,
      "/api/tasks": [{ id: "task-1", user_id: user.id, title: "需要编辑的任务", description: "原备注", deadline: "2099-09-03T09:00:00Z", location: "教学平台", course: "测试课", task_type: "assignment", materials: ["报告"], submission_target: "任课老师", submission_method: "在线", file_naming: "学号-姓名", source_text: "原通知", source_url: "", status: "pending", needs_confirmation: false, completed_at: null, created_at: "2026-08-03T00:00:00Z", updated_at: "2026-08-03T00:00:00Z" }],
    }));
    renderAt("/tasks", <App />);
    expect(await screen.findByText("需要编辑的任务")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "编辑" }));
    expect(screen.getByDisplayValue("需要编辑的任务")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "需要编辑的任务" })).toBeInTheDocument();
  });

  it("confirms before deleting a task and removes it after the API succeeds", async () => {
    const task = { id: "delete-task", user_id: user.id, title: "待删除任务", description: "", deadline: null, location: "", course: "", task_type: "general", materials: [], submission_target: "", submission_method: "", file_naming: "", source_text: "", source_url: "", status: "pending", needs_confirmation: false, completed_at: null, created_at: "2026-08-03T00:00:00Z", updated_at: "2026-08-03T00:00:00Z" };
    let deleted = false;
    vi.stubGlobal("confirm", vi.fn(() => true));
    vi.stubGlobal("fetch", routeFetch({
      "/api/auth/me": user,
      "/api/tasks/delete-task": (_input: RequestInfo | URL, init?: RequestInit) => { deleted = init?.method === "DELETE"; return new Response(null, { status: 204 }); },
      "/api/tasks": () => json(deleted ? [] : [task]),
    }));
    renderAt("/tasks", <App />);
    expect(await screen.findByText("待删除任务")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "删除" }));
    await waitFor(() => expect(screen.queryByText("待删除任务")).not.toBeInTheDocument());
    expect(deleted).toBe(true);
  });

  it("shows a truthful empty state when a campus has no canteen records", async () => {
    vi.stubGlobal("fetch", routeFetch({
      "/api/auth/me": user,
      "/api/campuses": [campus],
      "/api/canteens": [],
    }));
    renderAt("/canteens", <App />);
    expect(await screen.findByText("该校区暂无可公开饭堂记录")).toBeInTheDocument();
    expect(screen.getByText(/不会自动生成饭堂/)).toBeInTheDocument();
  });
});

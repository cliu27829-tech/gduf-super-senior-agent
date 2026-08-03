import { afterEach, expect, it, vi } from "vitest";
import { api } from "./api";
import { json } from "./test/test-utils";

afterEach(() => vi.unstubAllGlobals());

it("retries one protected request after a successful cookie refresh", async () => {
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(json({ detail: "expired" }, 401))
    .mockResolvedValueOnce(json({ user: { id: "user-1" } }))
    .mockResolvedValueOnce(json([{ id: "task-1" }]));
  vi.stubGlobal("fetch", fetchMock);
  const tasks = await api<{ id: string }[]>("/tasks");
  expect(tasks).toEqual([{ id: "task-1" }]);
  expect(fetchMock).toHaveBeenCalledTimes(3);
  expect(String(fetchMock.mock.calls[1][0])).toContain("/api/auth/refresh");
});

it("does not retry a failed authentication endpoint", async () => {
  const fetchMock = vi.fn().mockResolvedValue(json({ detail: "邮箱或密码错误" }, 401));
  vi.stubGlobal("fetch", fetchMock);
  await expect(api("/auth/login", { method: "POST", body: "{}" })).rejects.toThrow("邮箱或密码错误");
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

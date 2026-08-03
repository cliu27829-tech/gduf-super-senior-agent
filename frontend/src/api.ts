const API_URL = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

type ApiOptions = RequestInit & { timeoutMs?: number };

async function parseError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) return body.detail.map((item: { msg?: string }) => item.msg || "参数错误").join("；");
  } catch {
    return "服务暂时不可用";
  }
  return "请求失败";
}

export async function api<T>(path: string, options: ApiOptions = {}, retry = true): Promise<T> {
  const { timeoutMs = 15000, ...requestOptions } = options;
  const headers = new Headers(options.headers);
  if (!(options.body instanceof FormData) && options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  if (requestOptions.signal) requestOptions.signal.addEventListener("abort", () => controller.abort(), { once: true });
  let response: Response;
  try {
    response = await fetch(`${API_URL}/api${path}`, {
      ...requestOptions,
      headers,
      credentials: "include",
      signal: controller.signal,
    });
  } catch (reason) {
    if (reason instanceof DOMException && reason.name === "AbortError") throw new ApiError("请求超时，请检查后端服务后重试", 408);
    throw new ApiError("无法连接后端服务，请稍后重试", 0);
  } finally {
    window.clearTimeout(timer);
  }
  if (response.status === 401 && retry && !path.startsWith("/auth/")) {
    let refreshed: Response;
    try {
      refreshed = await fetch(`${API_URL}/api/auth/refresh`, { method: "POST", credentials: "include" });
    } catch {
      window.dispatchEvent(new Event("gduf:unauthorized"));
      throw new ApiError("登录状态已失效，请重新登录", 401);
    }
    if (refreshed.ok) return api<T>(path, options, false);
    window.dispatchEvent(new Event("gduf:unauthorized"));
  }
  if (!response.ok) throw new ApiError(await parseError(response), response.status);
  if (response.status === 204) return undefined as T;
  const contentType = response.headers.get("content-type") || "";
  return (contentType.includes("application/json") ? response.json() : response.text()) as Promise<T>;
}

export function apiFileUrl(path: string): string {
  return `${API_URL}/api${path}`;
}

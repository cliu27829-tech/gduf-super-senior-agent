import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";
import { AuthProvider } from "../auth";
import { LocationProvider } from "../location";

export const campus = {
  id: "campus-gz",
  slug: "guangzhou",
  name: "广州校本部",
  address: "",
  data_notice: "历史与待核验数据并存",
  is_active: true,
  updated_at: "2026-08-03T00:00:00Z",
};

export const user = {
  id: "user-1",
  email: "student@example.com",
  username: "student",
  nickname: "同学",
  role: "user",
  campus_id: campus.id,
  grade: "2026级",
  major: "金融学",
  preferred_name: "",
  address_style: "同学",
  preferred_location_id: null,
  is_active: true,
  created_at: "2026-08-03T00:00:00Z",
};

export function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

export function routeFetch(
  routes: Record<string, unknown | ((input: RequestInfo | URL, init?: RequestInit) => Response | Promise<Response>)>,
) {
  return async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = String(input);
    const key = Object.keys(routes).find((route) => url.includes(route));
    if (!key) return json({ detail: `unmocked request: ${url}` }, 500);
    const value = routes[key];
    return typeof value === "function" ? value(input, init) : json(value);
  };
}

export function renderAt(path: string, children: ReactNode) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider><LocationProvider>{children}</LocationProvider></AuthProvider>
    </MemoryRouter>,
  );
}

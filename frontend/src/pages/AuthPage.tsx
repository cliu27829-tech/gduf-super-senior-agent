import { useEffect, useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import type { Campus } from "../types";

export default function AuthPage({ mode }: { mode: "login" | "register" }) {
  const { user, login, register } = useAuth();
  const [campuses, setCampuses] = useState<Campus[]>([]);
  const [form, setForm] = useState({ username: "", nickname: "", email: "", password: "", campus_id: "", grade: "", major: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  useEffect(() => { api<Campus[]>("/campuses").then((rows) => { setCampuses(rows); setForm((value) => ({ ...value, campus_id: value.campus_id || rows[0]?.id || "" })); }).catch(() => undefined); }, []);
  if (user) return <Navigate to="/dashboard" replace />;
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true); setError("");
    try {
      if (mode === "login") await login(form.email, form.password);
      else await register(form);
      const target = (location.state as { from?: string } | null)?.from || "/dashboard";
      navigate(target, { replace: true });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "操作失败，请稍后重试");
    } finally { setBusy(false); }
  };
  const field = (key: keyof typeof form, value: string) => setForm((current) => ({ ...current, [key]: value }));
  return (
    <section className="auth-layout section-wrap">
      <div className="auth-aside"><p className="eyebrow">{mode === "login" ? "欢迎回来" : "加入广金大师兄"}</p><h1>{mode === "login" ? "继续处理你的校园事项" : "先选校区，再把事情办明白"}</h1><ul><li>密码使用 Argon2 哈希，服务端不保存明文</li><li>登录令牌保存在 HttpOnly Cookie</li><li>不同用户的任务和对话严格隔离</li></ul></div>
      <form className="form-card" onSubmit={submit}>
        <h2>{mode === "login" ? "登录" : "创建账号"}</h2>
        {error && <div className="error-banner" role="alert">{error}</div>}
        {mode === "register" && <>
          <label>用户名<input required minLength={2} value={form.username} onChange={(e) => field("username", e.target.value)} autoComplete="username" /></label>
          <label>昵称<input value={form.nickname} onChange={(e) => field("nickname", e.target.value)} placeholder="大家怎么称呼你" /></label>
        </>}
        <label>邮箱<input required type="email" value={form.email} onChange={(e) => field("email", e.target.value)} autoComplete="email" /></label>
        <label>密码<input required type="password" minLength={mode === "register" ? 8 : 1} value={form.password} onChange={(e) => field("password", e.target.value)} autoComplete={mode === "login" ? "current-password" : "new-password"} /><small>{mode === "register" ? "至少 8 位，包含字母和数字" : "忘记密码功能尚未接入邮件，请联系管理员"}</small></label>
        {mode === "register" && <>
          <label>所属校区<select required value={form.campus_id} onChange={(e) => field("campus_id", e.target.value)}>{campuses.map((campus) => <option value={campus.id} key={campus.id}>{campus.name}</option>)}</select></label>
          <div className="form-grid"><label>年级（选填）<input value={form.grade} onChange={(e) => field("grade", e.target.value)} placeholder="例如 2026级" /></label><label>专业（选填）<input value={form.major} onChange={(e) => field("major", e.target.value)} /></label></div>
        </>}
        <button className="button full" disabled={busy}>{busy ? "正在处理…" : mode === "login" ? "登录" : "注册并登录"}</button>
        <p className="form-switch">{mode === "login" ? <>还没有账号？<Link to="/register">立即注册</Link></> : <>已有账号？<Link to="/login">直接登录</Link></>}</p>
      </form>
    </section>
  );
}


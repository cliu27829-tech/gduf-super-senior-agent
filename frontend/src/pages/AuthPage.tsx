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
  const [showPassword, setShowPassword] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  useEffect(() => { api<Campus[]>("/campuses").then((rows) => { setCampuses(rows); setForm((value) => ({ ...value, campus_id: value.campus_id || rows[0]?.id || "" })); }).catch((reason) => setError(reason instanceof Error ? reason.message : "校区数据加载失败")); }, []);
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
  const passwordChecks = {
    length: form.password.length >= 8,
    letter: /[A-Za-z]/.test(form.password),
    number: /\d/.test(form.password),
  };
  return (
    <section className="auth-layout section-wrap" aria-labelledby="auth-title">
      <div className="auth-aside">
        <div className="auth-brand-lockup"><span className="brand-mark auth-mark" aria-hidden="true">广</span><span>广东金融学院学生校园助手</span></div>
        <p className="eyebrow">{mode === "login" ? "欢迎回来" : "加入广金大师兄"}</p>
        <h1>{mode === "login" ? "校园里的事情，接着交给大师兄。" : "从今天起，把校园事项理清楚。"}</h1>
        <p className="auth-lead">查地点、读通知、记任务，也可以直接问学习和校园生活问题。</p>
        <div className="auth-values"><span>校园问答</span><span>通知转任务</span><span>地点与路线</span></div>
      </div>
      <form className="form-card" onSubmit={submit}>
        <header><p className="eyebrow">广金大师兄</p><h2 id="auth-title">{mode === "login" ? "登录账号" : "创建账号"}</h2><p>{mode === "login" ? "回来看看今天还有哪些事。" : "填写基本信息，之后可以随时在个人中心修改。"}</p></header>
        {error && <div className="error-banner" role="alert">{error}</div>}
        {mode === "register" && <>
          <label>用户名<input required minLength={2} value={form.username} onChange={(e) => field("username", e.target.value)} autoComplete="username" placeholder="用于站内显示和登录识别" /></label>
          <label>昵称<input value={form.nickname} onChange={(e) => field("nickname", e.target.value)} placeholder="大家怎么称呼你" /></label>
        </>}
        <label>邮箱<input required type="email" value={form.email} onChange={(e) => field("email", e.target.value)} autoComplete="email" placeholder="name@example.com" /></label>
        <label>密码<div className="password-field"><input required type={showPassword ? "text" : "password"} minLength={mode === "register" ? 8 : 1} value={form.password} onChange={(e) => field("password", e.target.value)} autoComplete={mode === "login" ? "current-password" : "new-password"} /><button type="button" onClick={() => setShowPassword((value) => !value)} aria-label={showPassword ? "隐藏密码" : "显示密码"}>{showPassword ? "隐藏" : "显示"}</button></div>{mode === "register" ? <span className="password-rules" aria-live="polite"><small className={passwordChecks.length ? "met" : ""}>至少 8 位</small><small className={passwordChecks.letter ? "met" : ""}>含字母</small><small className={passwordChecks.number ? "met" : ""}>含数字</small></span> : <small>请输入注册时使用的密码</small>}</label>
        {mode === "register" && <>
          <label>所属校区<select required value={form.campus_id} onChange={(e) => field("campus_id", e.target.value)}>{campuses.map((campus) => <option value={campus.id} key={campus.id}>{campus.name}</option>)}</select></label>
          <div className="form-grid"><label>年级（选填）<input value={form.grade} onChange={(e) => field("grade", e.target.value)} placeholder="例如 2026级" /></label><label>专业（选填）<input value={form.major} onChange={(e) => field("major", e.target.value)} /></label></div>
        </>}
        <button className="button full" disabled={busy || (mode === "register" && !Object.values(passwordChecks).every(Boolean))}>{busy ? "正在处理…" : mode === "login" ? "登录" : "注册并登录"}</button>
        <p className="form-switch">{mode === "login" ? <>还没有账号？<Link to="/register">立即注册</Link></> : <>已有账号？<Link to="/login">直接登录</Link></>}</p>
      </form>
    </section>
  );
}

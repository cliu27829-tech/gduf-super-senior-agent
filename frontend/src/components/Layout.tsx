import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import type { Reminder } from "../types";

const navItems = [
  ["/dashboard", "首页"],
  ["/chat", "问大师兄"],
  ["/map", "校园地图"],
  ["/notifications", "通知"],
  ["/tasks", "任务"],
];

const lifeItems = [["/canteens", "饭堂"], ["/processes", "办事流程"]];

function Navigation({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav className="main-nav" aria-label="主导航">
      {navItems.map(([path, label]) => (
        <NavLink key={path} to={path} onClick={onNavigate} className={({ isActive }) => isActive ? "active" : ""}>{label}</NavLink>
      ))}
      <details className="nav-menu"><summary>校园生活 <span aria-hidden="true">⌄</span></summary><div>{lifeItems.map(([path, label]) => <NavLink key={path} to={path} onClick={onNavigate} className={({ isActive }) => isActive ? "active" : ""}>{label}</NavLink>)}</div></details>
    </nav>
  );
}

export function Layout() {
  const { user, logout } = useAuth();
  const { pathname } = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  useEffect(() => setMobileOpen(false), [pathname]);
  return (
    <div className={`app-shell ${pathname === "/chat" ? "chat-route" : ""}`}>
      <a className="skip-link" href="#main">跳到主要内容</a>
      <header className="site-header">
        <div className="header-inner">
          <NavLink to="/" className="brand" aria-label="广金大师兄首页">
            <span className="brand-mark" aria-hidden="true">广</span>
            <span><strong>广金大师兄</strong><small>读懂校园信息，帮你把事情办明白。</small></span>
          </NavLink>
          {user && <Navigation />}
          <div className="account-actions">
            {user ? (
              <>
                {user.role === "admin" && <NavLink className="text-link" to="/admin">管理后台</NavLink>}
                <NavLink className="avatar-link" to="/profile">{(user.nickname || user.username).slice(0, 1)}</NavLink>
                <button className="ghost-button compact" onClick={() => void logout()}>退出</button>
              </>
            ) : (
              <><NavLink className="text-link" to="/login">登录</NavLink><NavLink className="button compact" to="/register">注册</NavLink></>
            )}
          </div>
          {user && <button className="mobile-menu-trigger" type="button" aria-expanded={mobileOpen} aria-controls="mobile-navigation" onClick={() => setMobileOpen((value) => !value)}>{mobileOpen ? "关闭" : "菜单"}</button>}
        </div>
        {user && <div id="mobile-navigation" className={`mobile-nav ${mobileOpen ? "open" : ""}`}><Navigation onNavigate={() => setMobileOpen(false)} /></div>}
      </header>
      <main id="main"><Outlet /></main>
      {user && <ReminderWatcher />}
      <footer className="site-footer">
        <p>广金大师兄 · 校园信息以来源、核验状态和更新时间为准</p>
        <p>地点、菜单和办事信息以页面标注的来源、核验状态与更新时间为准。</p>
      </footer>
    </div>
  );
}

function ReminderWatcher() {
  const [reminders, setReminders] = useState<Reminder[]>([]);
  useEffect(() => {
    let active = true;
    const check = async () => {
      try {
        const due = await api<Reminder[]>("/reminders/check", { method: "POST" });
        if (!active || !due.length) return;
        setReminders((current) => [...current, ...due.filter((item) => !current.some((existing) => existing.id === item.id))]);
        if ("Notification" in window && Notification.permission === "granted") {
          due.filter((item) => item.channels.includes("browser")).forEach((item) => new Notification(item.title, { body: item.body }));
        }
      } catch { /* 登录刷新和错误提示由各业务页面处理，轮询保持静默。 */ }
    };
    void check();
    const timer = window.setInterval(() => void check(), 30_000);
    return () => { active = false; window.clearInterval(timer); };
  }, []);
  const dismiss = async (item: Reminder) => {
    setReminders((current) => current.filter((row) => row.id !== item.id));
    try { await api(`/reminders/${item.id}`, { method: "PATCH", body: JSON.stringify({ status: "dismissed", confirmed: true }) }); } catch { /* toast remains dismissed locally */ }
  };
  return <div className="reminder-toasts" aria-live="assertive">{reminders.map((item) => <aside className="reminder-toast" key={item.id}><span>提醒</span><strong>{item.title}</strong>{item.body && <p>{item.body}</p>}<div className="reminder-toast-actions"><button onClick={() => void dismiss(item)}>知道了</button>{item.location_id && <NavLink to={`/map?destination=${encodeURIComponent(item.location_id)}&use_current=1`}>从我这里去</NavLink>}</div></aside>)}</div>;
}

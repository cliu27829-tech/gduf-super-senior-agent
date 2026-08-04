import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth";

const navItems = [
  ["/dashboard", "工作台"],
  ["/chat", "问师兄"],
  ["/map", "校园地图"],
  ["/canteens", "饭堂"],
  ["/notifications", "处理通知"],
  ["/tasks", "任务中心"],
  ["/processes", "办事流程"],
];

function Navigation() {
  return (
    <nav className="main-nav" aria-label="主导航">
      {navItems.map(([path, label]) => (
        <NavLink key={path} to={path} className={({ isActive }) => isActive ? "active" : ""}>{label}</NavLink>
      ))}
    </nav>
  );
}

export function Layout() {
  const { user, logout } = useAuth();
  return (
    <div className="app-shell">
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
        </div>
        {user && <div className="mobile-nav"><Navigation /></div>}
      </header>
      <main id="main"><Outlet /></main>
      <footer className="site-footer">
        <p>广金大师兄 · 校园信息以来源、核验状态和更新时间为准</p>
        <p>目前不提供可靠实时菜单或网站关闭后的主动推送；路线仅在高德凭据和核验坐标齐全时启用。</p>
      </footer>
    </div>
  );
}

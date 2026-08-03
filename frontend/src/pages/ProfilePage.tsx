import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { formatDate } from "../components/StatusBadge";
import type { Campus } from "../types";

export default function ProfilePage() {
  const { user, refreshUser, logout } = useAuth();
  const navigate = useNavigate();
  const [campuses, setCampuses] = useState<Campus[]>([]);
  const [profile, setProfile] = useState({ nickname: user?.nickname || "", campus_id: user?.campus_id || "", grade: user?.grade || "", major: user?.major || "" });
  const [passwords, setPasswords] = useState({ current_password: "", new_password: "" });
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  useEffect(() => { api<Campus[]>("/campuses").then(setCampuses).catch((reason) => setError(reason instanceof Error ? reason.message : "校区数据加载失败")); }, []);
  const saveProfile = async (event: FormEvent) => { event.preventDefault(); setError(""); try { await api("/auth/me", { method: "PATCH", body: JSON.stringify(profile) }); await refreshUser(); setMessage("个人资料已更新"); } catch (reason) { setError(reason instanceof Error ? reason.message : "更新失败"); } };
  const changePassword = async (event: FormEvent) => { event.preventDefault(); setError(""); try { await api("/auth/change-password", { method: "POST", body: JSON.stringify(passwords) }); setMessage("密码已修改，请重新登录"); setTimeout(() => navigate("/login"), 800); } catch (reason) { setError(reason instanceof Error ? reason.message : "修改失败"); } };
  const deleteAccount = async () => { if (!window.confirm("确定永久删除账户及其任务、对话数据吗？此操作不可撤销。")) return; setError(""); try { await api("/auth/account", { method: "DELETE" }); await refreshUser(); navigate("/"); } catch (reason) { setError(reason instanceof Error ? reason.message : "删除账户失败"); } };
  return (
    <section className="page section-wrap profile-page">
      <div className="page-heading"><div><p className="eyebrow">个人中心</p><h1>管理账号和所属校区</h1><p>账户创建于 {formatDate(user?.created_at)}</p></div><div className="profile-avatar">{(user?.nickname || user?.username || "广").slice(0, 1)}</div></div>
      {message && <div className="success-banner" role="status">{message}</div>}{error && <div className="error-banner" role="alert">{error}</div>}
      <div className="profile-grid"><form className="panel" onSubmit={saveProfile}><h2>基本资料</h2><label>邮箱<input disabled value={user?.email || ""} /><small>当前版本不支持修改登录邮箱</small></label><label>昵称<input value={profile.nickname} onChange={(e) => setProfile({ ...profile, nickname: e.target.value })} /></label><label>所属校区<select value={profile.campus_id} onChange={(e) => setProfile({ ...profile, campus_id: e.target.value })}>{campuses.map((campus) => <option key={campus.id} value={campus.id}>{campus.name}</option>)}</select></label><div className="form-grid"><label>年级<input value={profile.grade} onChange={(e) => setProfile({ ...profile, grade: e.target.value })} /></label><label>专业<input value={profile.major} onChange={(e) => setProfile({ ...profile, major: e.target.value })} /></label></div><button className="button">保存资料</button></form><div className="profile-side"><form className="panel" onSubmit={changePassword}><h2>修改密码</h2><label>当前密码<input type="password" required value={passwords.current_password} onChange={(e) => setPasswords({ ...passwords, current_password: e.target.value })} /></label><label>新密码<input type="password" minLength={8} required value={passwords.new_password} onChange={(e) => setPasswords({ ...passwords, new_password: e.target.value })} /><small>至少 8 位，包含字母和数字</small></label><button className="ghost-button">修改并退出登录</button></form><div className="panel privacy-card"><h2>隐私与安全</h2><p>密码采用 Argon2 哈希；登录令牌存放在 HttpOnly Cookie；DeepSeek Key 只存在服务端环境变量。</p><p>系统不会公开你上传的通知，也不会在日志中记录密码、Token 或完整私密通知。</p><button className="text-link" onClick={() => void logout()}>退出当前账号</button><button className="danger-link" onClick={() => void deleteAccount()}>删除账户和个人数据</button></div></div></div>
    </section>
  );
}

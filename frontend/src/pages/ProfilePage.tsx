import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { formatDate } from "../components/StatusBadge";
import type { Campus, Location, Note, Reminder } from "../types";

export default function ProfilePage() {
  const { user, refreshUser, logout } = useAuth();
  const navigate = useNavigate();
  const [campuses, setCampuses] = useState<Campus[]>([]);
  const [locations, setLocations] = useState<Location[]>([]);
  const [profile, setProfile] = useState({ nickname: user?.nickname || "", campus_id: user?.campus_id || "", grade: user?.grade || "", major: user?.major || "", preferred_name: user?.preferred_name || "", address_style: user?.address_style || "同学", preferred_location_id: user?.preferred_location_id || "" });
  const [passwords, setPasswords] = useState({ current_password: "", new_password: "" });
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  useEffect(() => { api<Campus[]>("/campuses").then(setCampuses).catch((reason) => setError(reason instanceof Error ? reason.message : "校区数据加载失败")); }, []);
  useEffect(() => {
    if (!profile.campus_id) return;
    api<Location[]>(`/locations?campus_id=${encodeURIComponent(profile.campus_id)}`).then(setLocations).catch(() => setLocations([]));
  }, [profile.campus_id]);
  const saveProfile = async (event: FormEvent) => { event.preventDefault(); setError(""); try { await api("/auth/me", { method: "PATCH", body: JSON.stringify(profile) }); await refreshUser(); setMessage("个人资料已更新"); } catch (reason) { setError(reason instanceof Error ? reason.message : "更新失败"); } };
  const changePassword = async (event: FormEvent) => { event.preventDefault(); setError(""); try { await api("/auth/change-password", { method: "POST", body: JSON.stringify(passwords) }); setMessage("密码已修改，请重新登录"); setTimeout(() => navigate("/login"), 800); } catch (reason) { setError(reason instanceof Error ? reason.message : "修改失败"); } };
  const deleteAccount = async () => { if (!window.confirm("确定永久删除账户及其任务、对话数据吗？此操作不可撤销。")) return; setError(""); try { await api("/auth/account", { method: "DELETE" }); await refreshUser(); navigate("/"); } catch (reason) { setError(reason instanceof Error ? reason.message : "删除账户失败"); } };
  return (
    <section className="page section-wrap profile-page">
      <div className="page-heading"><div><p className="eyebrow">个人中心</p><h1>管理账号和所属校区</h1><p>账户创建于 {formatDate(user?.created_at)}</p></div><div className="profile-avatar">{(user?.nickname || user?.username || "广").slice(0, 1)}</div></div>
      {message && <div className="success-banner" role="status">{message}</div>}{error && <div className="error-banner" role="alert">{error}</div>}
      <div className="profile-grid"><form className="panel" onSubmit={saveProfile}><h2>基本资料与称呼偏好</h2><label>邮箱<input disabled value={user?.email || ""} /><small>当前版本不支持修改登录邮箱</small></label><label>昵称<input value={profile.nickname} onChange={(e) => setProfile({ ...profile, nickname: e.target.value })} /></label><label>所属校区<select value={profile.campus_id} onChange={(e) => setProfile({ ...profile, campus_id: e.target.value, preferred_location_id: "" })}>{campuses.map((campus) => <option key={campus.id} value={campus.id}>{campus.name}</option>)}</select></label><div className="form-grid"><label>年级<input value={profile.grade} onChange={(e) => setProfile({ ...profile, grade: e.target.value })} /></label><label>专业<input value={profile.major} onChange={(e) => setProfile({ ...profile, major: e.target.value })} /></label></div><div className="form-grid"><label>希望大师兄叫你<input value={profile.preferred_name} onChange={(e) => setProfile({ ...profile, preferred_name: e.target.value })} placeholder="留空则用昵称" /></label><label>称呼方式<select value={profile.address_style} onChange={(e) => setProfile({ ...profile, address_style: e.target.value as typeof profile.address_style })}><option value="同学">同学</option><option value="师弟">师弟</option><option value="师妹">师妹</option><option value="兄弟">兄弟</option><option value="名字">只叫名字</option></select></label></div><label>常用地点<select value={profile.preferred_location_id} onChange={(e) => setProfile({ ...profile, preferred_location_id: e.target.value })}><option value="">未设置</option>{locations.map((location) => <option key={location.id} value={location.id}>{location.name}</option>)}</select><small>仅显示当前校区可公开查询的地点，用于“从我常去的地方出发”等上下文。</small></label><button className="button">保存资料</button></form><div className="profile-side"><form className="panel" onSubmit={changePassword}><h2>修改密码</h2><label>当前密码<input type="password" required value={passwords.current_password} onChange={(e) => setPasswords({ ...passwords, current_password: e.target.value })} /></label><label>新密码<input type="password" minLength={8} required value={passwords.new_password} onChange={(e) => setPasswords({ ...passwords, new_password: e.target.value })} /><small>至少 8 位，包含字母和数字</small></label><button className="ghost-button">修改并退出登录</button></form><div className="panel privacy-card"><h2>隐私与安全</h2><p>密码采用 Argon2 哈希；登录令牌存放在 HttpOnly Cookie；DeepSeek Key 只存在服务端环境变量。</p><p>系统不会公开你上传的通知，也不会在日志中记录密码、Token 或完整私密通知。</p><button className="text-link" onClick={() => void logout()}>退出当前账号</button>{user?.role === "admin" ? <small>管理员账号需保留审计记录，如需停用请由运维人员处理。</small> : <button className="danger-link" onClick={() => void deleteAccount()}>删除账户和个人数据</button>}</div></div></div>
      <PersonalOrganizer />
    </section>
  );
}

function PersonalOrganizer() {
  const [notes, setNotes] = useState<Note[]>([]);
  const [reminders, setReminders] = useState<Reminder[]>([]);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const load = async (q = query) => {
    try {
      const [noteRows, reminderRows] = await Promise.all([
        api<Note[]>(`/notes?q=${encodeURIComponent(q)}`),
        api<Reminder[]>("/reminders?status=scheduled"),
      ]);
      setNotes(noteRows); setReminders(reminderRows);
    } catch (reason) { setStatus(reason instanceof Error ? reason.message : "个人助理数据加载失败"); }
  };
  useEffect(() => { void load(""); }, []);
  const patchNote = async (note: Note, changes: Partial<Note>) => { await api(`/notes/${note.id}`, { method: "PATCH", body: JSON.stringify({ ...changes, confirmed: true }) }); await load(); };
  const editNote = async (note: Note) => {
    const content = window.prompt("编辑便签内容", note.content); if (content === null || !content.trim()) return;
    const title = window.prompt("编辑便签标题", note.title); if (title === null || !title.trim()) return;
    try { await patchNote(note, { title, content }); setStatus("便签已更新"); } catch (reason) { setStatus(reason instanceof Error ? reason.message : "更新失败"); }
  };
  const deleteNote = async (note: Note) => {
    if (!window.confirm(`删除便签“${note.title}”？`)) return;
    try { await api(`/notes/${note.id}?confirmed=true`, { method: "DELETE" }); await load(); } catch (reason) { setStatus(reason instanceof Error ? reason.message : "删除失败"); }
  };
  const cancelReminder = async (reminder: Reminder) => {
    if (!window.confirm(`取消提醒“${reminder.title}”？`)) return;
    try { await api(`/reminders/${reminder.id}?confirmed=true`, { method: "DELETE" }); await load(); } catch (reason) { setStatus(reason instanceof Error ? reason.message : "取消失败"); }
  };
  const requestNotifications = async () => {
    if (!("Notification" in window)) return setStatus("当前浏览器不支持系统通知，站内提醒仍可使用。");
    const result = await Notification.requestPermission();
    setStatus(result === "granted" ? "浏览器通知已授权；仅标记 browser 渠道的提醒会显示系统通知。" : "未获得浏览器通知权限，站内提醒仍可使用。");
  };
  return <section className="organizer-grid">
    <div className="panel"><div className="panel-heading"><div><p className="eyebrow">我的便签</p><h2>随手记下，随时找回</h2></div></div><form className="note-search" onSubmit={(event) => { event.preventDefault(); void load(query); }}><input aria-label="搜索便签" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索标题或内容" /><button className="ghost-button compact">搜索</button></form><div className="note-list">{notes.map((note) => <article key={note.id} className={note.pinned ? "pinned" : ""}><header><strong>{note.title}</strong><button onClick={() => void patchNote(note, { pinned: !note.pinned })}>{note.pinned ? "取消置顶" : "置顶"}</button></header><p>{note.content}</p><small>{note.tags.join(" · ") || "无标签"}</small><footer><button onClick={() => void editNote(note)}>编辑</button><button onClick={() => void deleteNote(note)}>删除</button></footer></article>)}{!notes.length && <p className="empty-copy">还没有便签，可以在对话或通知解析后保存。</p>}</div></div>
    <div className="panel"><div className="panel-heading"><div><p className="eyebrow">我的提醒</p><h2>即将提醒</h2></div><button className="ghost-button compact" onClick={() => void requestNotifications()}>浏览器通知</button></div><div className="reminder-list">{reminders.map((reminder) => <article key={reminder.id}><div><strong>{reminder.title}</strong><small>{new Date(reminder.remind_at).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" })}</small></div><button onClick={() => void cancelReminder(reminder)}>取消</button></article>)}{!reminders.length && <p className="empty-copy">暂无计划中的提醒。</p>}</div><p className="push-note">站内提醒需要页面保持打开；浏览器通知需明确授权。localhost 不具备可靠 Web Push，正式 HTTPS 部署后再启用。</p></div>
    {status && <div className="success-banner organizer-status" role="status">{status}</div>}
  </section>;
}

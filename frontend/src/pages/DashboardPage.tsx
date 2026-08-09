import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { EmptyState, Loading } from "../components/ProtectedRoute";
import { formatDate } from "../components/StatusBadge";
import type { Campus, Location, Note, Reminder, Task } from "../types";

type AgentRunSummary = { id: string; conversation_id: string; goal: string; intent: string; status: string; summary: string; updated_at: string };

export default function DashboardPage() {
  const { user } = useAuth();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [campuses, setCampuses] = useState<Campus[]>([]);
  const [reminders, setReminders] = useState<Reminder[]>([]);
  const [notes, setNotes] = useState<Note[]>([]);
  const [locations, setLocations] = useState<Location[]>([]);
  const [agentRuns, setAgentRuns] = useState<AgentRunSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => { Promise.all([api<Task[]>("/tasks"), api<Campus[]>("/campuses"), api<Reminder[]>("/reminders?status=scheduled"), api<Note[]>("/notes?limit=3"), api<Location[]>(`/locations${user?.campus_id ? `?campus_id=${encodeURIComponent(user.campus_id)}` : ""}`), api<AgentRunSummary[]>("/agent/runs?limit=5")]).then(([taskRows, campusRows, reminderRows, noteRows, locationRows, runRows]) => { setTasks(taskRows); setCampuses(campusRows); setReminders(reminderRows); setNotes(noteRows); setLocations(locationRows); setAgentRuns(runRows); }).catch((reason) => setError(reason instanceof Error ? reason.message : "工作台加载失败")).finally(() => setLoading(false)); }, [user?.campus_id]);
  if (loading) return <Loading />;
  const now = Date.now();
  const today = tasks.filter((task) => task.deadline && new Date(task.deadline).toDateString() === new Date().toDateString() && task.status === "pending");
  const overdue = tasks.filter((task) => task.deadline && new Date(task.deadline).getTime() < now && task.status === "pending");
  const upcoming = tasks.filter((task) => task.deadline && new Date(task.deadline).getTime() >= now && new Date(task.deadline).getTime() < now + 7 * 86400000 && task.status === "pending");
  const campus = campuses.find((item) => item.id === user?.campus_id);
  const nextReminder = reminders[0];
  const commonLocations = locations.filter((item) => item.coordinate_accuracy === "exact" && item.coordinate_verified_at).slice(0, 4);
  return (
    <section className="page section-wrap">
      {error && <div className="error-banner" role="alert">{error}</div>}
      <div className="page-heading"><div><p className="eyebrow">我的工作台</p><h1>{user?.nickname || user?.username}，今天先做哪一件？</h1><p>{campus?.name || "尚未选择校区"} · 中国标准时间</p></div><Link className="button" to="/notifications">粘贴一条通知</Link></div>
      <div className="metric-grid"><article><span>今日任务</span><strong>{today.length}</strong><small>今天截止</small></article><article><span>即将截止</span><strong>{upcoming.length}</strong><small>未来 7 天</small></article><article><span>即将提醒</span><strong>{reminders.length}</strong><small>站内提醒</small></article><article className={overdue.length ? "danger-metric" : ""}><span>已逾期</span><strong>{overdue.length}</strong><small>需要尽快处理</small></article></div>
      <div className="dashboard-grid">
        <article className="panel"><div className="panel-heading"><h2>今天的安排</h2><Link to="/tasks">查看全部</Link></div>{[...today, ...upcoming.filter((task) => !today.some((row) => row.id === task.id))].length ? <div className="task-stack">{[...today, ...upcoming.filter((task) => !today.some((row) => row.id === task.id))].slice(0, 5).map((task) => <Link to="/tasks" className="task-row" key={task.id}><span className="task-dot" /><div><strong>{task.title}</strong><small>{formatDate(task.deadline)}{task.location ? ` · ${task.location}` : ""}</small></div><b>→</b></Link>)}</div> : <EmptyState title="今天暂时没有任务" detail="可以粘贴通知，确认后保存为任务和提醒。" />}</article>
        <article className="panel quick-panel"><h2>快捷入口</h2><Link to="/map"><span>⌖</span><div><strong>查校园地点</strong><small>来源与核验状态一起看</small></div></Link><Link to="/canteens"><span>食</span><div><strong>看饭堂</strong><small>没有实时菜单时不会编造</small></div></Link><Link to="/chat"><span>问</span><div><strong>问大师兄</strong><small>地点、办事、学习与生活</small></div></Link></article>
      </div>
      <div className="dashboard-grid dashboard-organizer"><article className="panel"><div className="panel-heading"><h2>下一次提醒</h2><Link to="/profile">管理提醒</Link></div>{nextReminder ? <div className="next-reminder"><span>{new Date(nextReminder.remind_at).toLocaleDateString("zh-CN", { month: "short", day: "numeric", timeZone: "Asia/Shanghai" })}</span><div><strong>{nextReminder.title}</strong><small>{new Date(nextReminder.remind_at).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" })}{nextReminder.location_name ? ` · ${nextReminder.location_name}` : ""}</small></div>{nextReminder.location_id && <Link to={`/map?destination=${encodeURIComponent(nextReminder.location_id)}&use_current=1`}>去这里</Link>}</div> : <p className="empty-copy">暂无即将提醒。</p>}</article><article className="panel"><div className="panel-heading"><h2>我的便签</h2><Link to="/profile">查看全部</Link></div>{notes.map((item) => <div className="note-preview" key={item.id}><strong>{item.pinned ? "📌 " : ""}{item.title}</strong><p>{item.content}</p></div>)}{!notes.length && <p className="empty-copy">可以在对话里说“把刚才的要求记一下”。</p>}</article></div>
      <article className="panel recent-agent-runs"><div className="panel-heading"><h2>大师兄最近处理</h2><Link to="/chat">继续交给大师兄</Link></div>{agentRuns.length ? <div>{agentRuns.map((run) => <Link to="/chat" key={run.id}><span className={`run-status run-${run.status}`}>{run.status === "completed" ? "✓" : run.status.startsWith("waiting") ? "…" : run.status === "failed" ? "!" : "●"}</span><div><strong>{run.goal}</strong><small>{run.summary || (run.status === "completed" ? "已完成并通过核验" : "等待继续处理")} · {new Date(run.updated_at).toLocaleString("zh-CN")}</small></div><b>{run.status === "completed" ? "已完成" : run.status.startsWith("waiting") ? "等待操作" : run.status === "failed" ? "未完成" : "处理中"}</b></Link>)}</div> : <p className="empty-copy">还没有 Agent 执行记录。第一次对话完成后会在这里显示可核验摘要。</p>}</article>
      <article className="panel common-locations"><div className="panel-heading"><h2>常用地点</h2><Link to="/map">打开校园地图</Link></div><div>{commonLocations.map((item) => <Link key={item.id} to={`/map?destination=${encodeURIComponent(item.id)}&use_current=1`}><span aria-hidden="true">⌖</span><strong>{item.name}</strong><small>从我这里去</small></Link>)}{!commonLocations.length && <p className="empty-copy">当前校区还没有可直接导航的已核验地点。</p>}</div></article>
      {campus && <div className="data-notice"><strong>{campus.name}数据说明</strong><p>{campus.data_notice}</p><small>校区数据更新时间：{formatDate(campus.updated_at)}</small></div>}
    </section>
  );
}

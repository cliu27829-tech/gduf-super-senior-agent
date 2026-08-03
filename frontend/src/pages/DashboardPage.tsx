import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { EmptyState, Loading } from "../components/ProtectedRoute";
import { formatDate } from "../components/StatusBadge";
import type { Campus, Task } from "../types";

export default function DashboardPage() {
  const { user } = useAuth();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [campuses, setCampuses] = useState<Campus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => { Promise.all([api<Task[]>("/tasks"), api<Campus[]>("/campuses")]).then(([taskRows, campusRows]) => { setTasks(taskRows); setCampuses(campusRows); }).catch((reason) => setError(reason instanceof Error ? reason.message : "工作台加载失败")).finally(() => setLoading(false)); }, []);
  if (loading) return <Loading />;
  const now = Date.now();
  const today = tasks.filter((task) => task.deadline && new Date(task.deadline).toDateString() === new Date().toDateString() && task.status === "pending");
  const overdue = tasks.filter((task) => task.deadline && new Date(task.deadline).getTime() < now && task.status === "pending");
  const upcoming = tasks.filter((task) => task.deadline && new Date(task.deadline).getTime() >= now && new Date(task.deadline).getTime() < now + 7 * 86400000 && task.status === "pending");
  const campus = campuses.find((item) => item.id === user?.campus_id);
  return (
    <section className="page section-wrap">
      {error && <div className="error-banner" role="alert">{error}</div>}
      <div className="page-heading"><div><p className="eyebrow">我的工作台</p><h1>{user?.nickname || user?.username}，今天先做哪一件？</h1><p>{campus?.name || "尚未选择校区"} · 中国标准时间</p></div><Link className="button" to="/notifications">粘贴一条通知</Link></div>
      <div className="metric-grid"><article><span>今日任务</span><strong>{today.length}</strong><small>今天截止</small></article><article><span>即将截止</span><strong>{upcoming.length}</strong><small>未来 7 天</small></article><article className={overdue.length ? "danger-metric" : ""}><span>已逾期</span><strong>{overdue.length}</strong><small>需要尽快处理</small></article><article><span>全部任务</span><strong>{tasks.length}</strong><small>含已完成</small></article></div>
      <div className="dashboard-grid">
        <article className="panel"><div className="panel-heading"><h2>下一步</h2><Link to="/tasks">查看全部</Link></div>{upcoming.length ? <div className="task-stack">{upcoming.slice(0, 5).map((task) => <Link to="/tasks" className="task-row" key={task.id}><span className="task-dot" /><div><strong>{task.title}</strong><small>{formatDate(task.deadline)}</small></div><b>→</b></Link>)}</div> : <EmptyState title="暂时没有临近任务" detail="可以粘贴通知，确认后保存为任务。" />}</article>
        <article className="panel quick-panel"><h2>快捷入口</h2><Link to="/map"><span>⌖</span><div><strong>查校园地点</strong><small>来源与核验状态一起看</small></div></Link><Link to="/canteens"><span>食</span><div><strong>看饭堂</strong><small>没有实时菜单时不会编造</small></div></Link><Link to="/chat"><span>问</span><div><strong>问大师兄</strong><small>地点、办事、学习与生活</small></div></Link></article>
      </div>
      {campus && <div className="data-notice"><strong>{campus.name}数据说明</strong><p>{campus.data_notice}</p><small>校区数据更新时间：{formatDate(campus.updated_at)}</small></div>}
    </section>
  );
}

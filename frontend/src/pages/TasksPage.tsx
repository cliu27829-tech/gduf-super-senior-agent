import { useEffect, useState, type FormEvent } from "react";
import { api, apiFileUrl } from "../api";
import { EmptyState, Loading } from "../components/ProtectedRoute";
import { formatDate } from "../components/StatusBadge";
import type { Task } from "../types";

const views = [["all", "全部"], ["today", "今日"], ["week", "本周"], ["upcoming", "即将截止"], ["overdue", "已逾期"], ["completed", "已完成"]];
const emptyForm = { title: "", description: "", deadline: "", location: "", course: "", task_type: "general", materials: "", submission_target: "", submission_method: "", file_naming: "", source_text: "", source_url: "" };

export default function TasksPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [view, setView] = useState("all");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Task | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [selected, setSelected] = useState<string[]>([]);
  const [error, setError] = useState("");

  const load = async () => {
    setLoading(true);
    setError("");
    const path = view === "completed" ? "/tasks?status=completed" : `/tasks?view=${view}`;
    try {
      setTasks(await api<Task[]>(path));
    } catch (reason) {
      setTasks([]);
      setError(reason instanceof Error ? reason.message : "加载失败");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { void load(); }, [view]);

  const field = (key: keyof typeof form, value: string) => setForm((current) => ({ ...current, [key]: value }));
  const save = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    const payload = { ...form, deadline: form.deadline ? new Date(form.deadline).toISOString() : null, materials: form.materials.split(/[、,，]/).map((item) => item.trim()).filter(Boolean), confirmed: true, reminder_minutes: [1440, 180] };
    try {
      if (editing) await api(`/tasks/${editing.id}`, { method: "PATCH", body: JSON.stringify(payload) });
      else await api("/tasks", { method: "POST", body: JSON.stringify(payload) });
      setForm(emptyForm);
      setEditing(null);
      setShowForm(false);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "保存失败");
    } finally {
      setBusy(false);
    }
  };
  const beginEdit = (task: Task) => {
    setEditing(task);
    setForm({ title: task.title, description: task.description, deadline: task.deadline ? task.deadline.slice(0, 16) : "", location: task.location, course: task.course, task_type: task.task_type, materials: task.materials.join("、"), submission_target: task.submission_target, submission_method: task.submission_method, file_naming: task.file_naming, source_text: task.source_text, source_url: task.source_url });
    setShowForm(true);
  };
  const action = async (task: Task, name: "complete" | "reopen" | "delete") => {
    if (name === "delete" && !window.confirm(`确认删除任务“${task.title}”？此操作不能撤销。`)) return;
    setBusy(true);
    setError("");
    try {
      if (name === "delete") await api(`/tasks/${task.id}?confirmed=true`, { method: "DELETE" });
      else await api(`/tasks/${task.id}/${name}?confirmed=true`, { method: "POST" });
      setSelected((current) => current.filter((id) => id !== task.id));
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "操作失败");
    } finally {
      setBusy(false);
    }
  };
  const bulk = async (name: "complete" | "reopen" | "delete") => {
    if (!selected.length || (name === "delete" && !window.confirm(`确认删除选中的 ${selected.length} 条任务？此操作不能撤销。`))) return;
    setBusy(true);
    setError("");
    try {
      await api("/tasks/bulk", { method: "POST", body: JSON.stringify({ task_ids: selected, action: name, confirmed: true }) });
      setSelected([]);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "批量操作失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="page section-wrap">
      <div className="page-heading"><div><p className="eyebrow">任务中心</p><h1>把截止日期收进一张清单</h1><p>任务保存在账户数据库；主动提醒请把 ICS 导入系统日历。</p></div><button className="button" onClick={() => { setEditing(null); setForm(emptyForm); setShowForm(true); }}>＋ 新建任务</button></div>
      <div className="task-toolbar"><div className="filter-chips">{views.map(([value, label]) => <button key={value} className={view === value ? "active" : ""} onClick={() => setView(value)}>{label}</button>)}</div><a className="ghost-button compact" href={apiFileUrl("/tasks/export/ics")}>导出全部 ICS</a></div>
      {selected.length > 0 && <div className="bulk-bar"><strong>已选 {selected.length} 项</strong><button disabled={busy} onClick={() => void bulk("complete")}>完成</button><button disabled={busy} onClick={() => void bulk("reopen")}>重新打开</button><button disabled={busy} className="danger-link" onClick={() => void bulk("delete")}>删除</button></div>}
      {error && <div className="error-banner" role="alert">{error}</div>}
      {loading ? <Loading /> : tasks.length ? <div className="tasks-table"><div className="task-table-head"><span /><span>任务</span><span>截止时间</span><span>分类</span><span>状态</span><span>操作</span></div>{tasks.map((task) => <article className={`task-table-row ${task.status}`} key={task.id}>
        <input aria-label={`选择${task.title}`} type="checkbox" checked={selected.includes(task.id)} onChange={(event) => setSelected((current) => event.target.checked ? [...current, task.id] : current.filter((id) => id !== task.id))} />
        <div><strong>{task.title}</strong><small>{task.course || task.location || "未填写课程或地点"}</small>{(task.submission_target || task.submission_method) && <small>提交：{[task.submission_target, task.submission_method].filter(Boolean).join(" · ")}</small>} {task.source_text && <details><summary>通知原文</summary><p className="source-excerpt">{task.source_text}</p>{task.source_url && <a href={task.source_url} target="_blank" rel="noreferrer">打开来源链接</a>}</details>}</div>
        <span>{formatDate(task.deadline)}</span><span>{task.task_type}</span><span className={`task-status ${task.status}`}>{task.status === "completed" ? "已完成" : task.deadline && new Date(task.deadline) < new Date() ? "已逾期" : "待完成"}</span>
        <div className="row-actions"><button disabled={busy} onClick={() => beginEdit(task)}>编辑</button><button disabled={busy} onClick={() => void action(task, task.status === "completed" ? "reopen" : "complete")}>{task.status === "completed" ? "重开" : "完成"}</button><button disabled={busy} className="danger-link" onClick={() => void action(task, "delete")}>删除</button></div>
      </article>)}</div> : <EmptyState title="这个视图没有任务" detail="新建任务，或从校园通知生成任务预览。" />}
      {showForm && <div className="drawer-backdrop" onClick={() => setShowForm(false)}><form className="detail-drawer task-form-drawer" onSubmit={save} onClick={(event) => event.stopPropagation()}><button type="button" className="drawer-close" onClick={() => setShowForm(false)}>×</button><p className="eyebrow">{editing ? "编辑任务" : "新建任务"}</p><h2>{editing ? editing.title : "添加一条待办"}</h2>
        <label>标题<input required value={form.title} onChange={(event) => field("title", event.target.value)} /></label><label>截止时间<input type="datetime-local" value={form.deadline} onChange={(event) => field("deadline", event.target.value)} /></label>
        <div className="form-grid"><label>课程<input value={form.course} onChange={(event) => field("course", event.target.value)} /></label><label>类型<input value={form.task_type} onChange={(event) => field("task_type", event.target.value)} /></label></div>
        <label>地点<input value={form.location} onChange={(event) => field("location", event.target.value)} /></label><label>所需材料<input value={form.materials} onChange={(event) => field("materials", event.target.value)} placeholder="用顿号分隔" /></label>
        <div className="form-grid"><label>提交对象<input value={form.submission_target} onChange={(event) => field("submission_target", event.target.value)} /></label><label>提交方式<input value={form.submission_method} onChange={(event) => field("submission_method", event.target.value)} /></label></div>
        <label>文件命名<input value={form.file_naming} onChange={(event) => field("file_naming", event.target.value)} /></label><label>备注<textarea rows={3} value={form.description} onChange={(event) => field("description", event.target.value)} /></label>
        <label>通知原文<textarea rows={4} value={form.source_text} onChange={(event) => field("source_text", event.target.value)} /></label><label>来源链接<input type="url" value={form.source_url} onChange={(event) => field("source_url", event.target.value)} /></label>
        <button className="button full" disabled={busy}>{busy ? "正在保存…" : "保存任务"}</button><small>默认在 ICS 中设置提前 24 小时和 3 小时提醒。</small>
      </form></div>}
    </section>
  );
}

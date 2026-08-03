import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, apiFileUrl } from "../api";
import type { NotificationDraft, Task } from "../types";

export default function NotificationsPage() {
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [drafts, setDrafts] = useState<NotificationDraft[]>([]);
  const [warning, setWarning] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState<Task[]>([]);
  const parse = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError(""); setSaved([]);
    const form = new FormData(); form.append("text", text); if (file) form.append("file", file);
    try {
      const result = await api<{ drafts: NotificationDraft[]; extraction_mode: string; warning: string }>("/notifications/parse", { method: "POST", body: form });
      setDrafts(result.drafts); setWarning(result.warning);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "解析失败"); }
    finally { setBusy(false); }
  };
  const update = (index: number, key: keyof NotificationDraft, value: string) => setDrafts((current) => current.map((draft, itemIndex) => itemIndex === index ? { ...draft, [key]: key === "materials" ? value.split(/[、,，]/).map((item) => item.trim()).filter(Boolean) : value } : draft));
  const confirm = async () => {
    setBusy(true); setError("");
    try { setSaved(await api<Task[]>("/notifications/confirm", { method: "POST", body: JSON.stringify({ drafts, confirmed: true }) })); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "保存失败"); }
    finally { setBusy(false); }
  };
  return (
    <section className="page section-wrap notification-page">
      <div className="page-heading"><div><p className="eyebrow">通知转任务</p><h1>先预览，再确认保存</h1><p>解析阶段不会创建任务；日期不确定时必须由你确认。</p></div></div>
      <div className="workflow-steps"><span className="active">1 粘贴或上传</span><span className={drafts.length ? "active" : ""}>2 核对预览</span><span className={saved.length ? "active" : ""}>3 保存与导出</span></div>
      <form className="notification-input panel" onSubmit={parse}><label>通知文本<textarea rows={10} value={text} onChange={(e) => setText(e.target.value)} placeholder={'例如：\n关于课程作业提交的通知\n截止时间：9月3日下午5点\n材料：课程报告、附件\n提交方式：教学平台'} /></label><div className="upload-row"><label className="upload-box"><strong>上传 TXT 或 PDF</strong><small>最大 5 MB；图片 OCR 尚未启用</small><input type="file" accept=".txt,.pdf,text/plain,application/pdf" onChange={(e) => setFile(e.target.files?.[0] || null)} /></label>{file && <span>{file.name} · {(file.size / 1024).toFixed(1)} KB</span>}</div><button className="button" disabled={busy || (!text.trim() && !file)}>{busy ? "正在解析…" : "解析通知"}</button></form>
      {error && <div className="error-banner" role="alert">{error}</div>}
      {warning && <div className="data-notice"><strong>解析提示</strong><p>{warning}</p></div>}
      {drafts.length > 0 && <div className="draft-section"><div className="section-heading"><p className="eyebrow">任务预览</p><h2>逐项核对后再保存</h2></div>{drafts.map((draft, index) => <article className="draft-card" key={index}><header><span>任务 {index + 1}</span><strong>置信度 {Math.round(draft.confidence * 100)}%</strong></header><div className="form-grid"><label>标题<input value={draft.title} onChange={(e) => update(index, "title", e.target.value)} /></label><label>截止时间<input type="datetime-local" value={draft.deadline ? draft.deadline.slice(0, 16) : ""} onChange={(e) => update(index, "deadline", e.target.value ? new Date(e.target.value).toISOString() : "")} /></label><label>地点<input value={draft.location} onChange={(e) => update(index, "location", e.target.value)} /></label><label>材料<input value={draft.materials.join("、")} onChange={(e) => update(index, "materials", e.target.value)} /></label><label className="span-two">提交方式<input value={draft.submission_method} onChange={(e) => update(index, "submission_method", e.target.value)} /></label></div>{draft.date_explanation && <p className={draft.needs_confirmation ? "date-warning" : "date-note"}>{draft.date_explanation}</p>}</article>)}<button className="button" disabled={busy} onClick={() => void confirm()}>确认并保存 {drafts.length} 条任务</button></div>}
      {saved.length > 0 && <div className="success-panel"><span>✓</span><div><h2>任务已保存</h2><p>已写入你的账户数据库，退出后再次登录仍会存在。</p><div><Link className="button" to="/tasks">前往任务中心</Link><a className="ghost-button" href={apiFileUrl(`/tasks/export/ics?${saved.map((task) => `task_ids=${task.id}`).join("&")}`)}>下载 ICS 日历</a></div><small>ICS 含提前 24 小时和 3 小时提醒；当前没有网站关闭后的主动推送。</small></div></div>}
    </section>
  );
}


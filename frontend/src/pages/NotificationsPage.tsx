import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, apiFileUrl } from "../api";
import type { NotificationDraft, Task } from "../types";

type DraftKey = keyof NotificationDraft;

export default function NotificationsPage() {
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [drafts, setDrafts] = useState<NotificationDraft[]>([]);
  const [warning, setWarning] = useState("");
  const [mode, setMode] = useState("");
  const [reviewed, setReviewed] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState<Task[]>([]);

  const parse = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    setSaved([]);
    setReviewed(false);
    const form = new FormData();
    form.append("text", text);
    if (file) form.append("file", file);
    try {
      const result = await api<{ drafts: NotificationDraft[]; extraction_mode: string; warning: string }>("/notifications/parse", { method: "POST", body: form });
      setDrafts(result.drafts);
      setMode(result.extraction_mode);
      setWarning(result.warning);
    } catch (reason) {
      setDrafts([]);
      setError(reason instanceof Error ? reason.message : "解析失败");
    } finally {
      setBusy(false);
    }
  };

  const update = (index: number, key: DraftKey, value: string) => {
    setReviewed(false);
    setDrafts((current) => current.map((draft, itemIndex) => {
      if (itemIndex !== index) return draft;
      if (key === "materials") return { ...draft, materials: value.split(/[、,，]/).map((item) => item.trim()).filter(Boolean) };
      return { ...draft, [key]: value };
    }));
  };

  const confirm = async () => {
    if (!reviewed) {
      setError("请先勾选确认：你已核对所有字段和不确定日期。");
      return;
    }
    if (drafts.some((draft) => !draft.title.trim())) {
      setError("每条任务都必须填写标题。");
      return;
    }
    setBusy(true);
    setError("");
    try {
      setSaved(await api<Task[]>("/notifications/confirm", { method: "POST", body: JSON.stringify({ drafts, confirmed: true }) }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "保存失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="page section-wrap notification-page">
      <div className="page-heading"><div><p className="eyebrow">通知转任务</p><h1>先预览，再确认保存</h1><p>解析阶段不会创建任务；模型或规则提取的结果都必须由你核对。</p></div></div>
      <div className="workflow-steps"><span className="active">1 粘贴或上传</span><span className={drafts.length ? "active" : ""}>2 核对预览</span><span className={saved.length ? "active" : ""}>3 保存与导出</span></div>
      <form className="notification-input panel" onSubmit={parse}>
        <label>通知文本<textarea rows={10} value={text} onChange={(event) => setText(event.target.value)} placeholder={'例如：\n1. 课程报告下周五 17:00 前交到教学平台，命名为“学号-姓名”。\n2. 纸质材料月底前交到辅导员办公室。'} /></label>
        <div className="upload-row"><label className="upload-box"><strong>上传 TXT 或 PDF</strong><small>最大 5 MB；扫描图片 OCR 尚未启用</small><input type="file" accept=".txt,.pdf,text/plain,application/pdf" onChange={(event) => setFile(event.target.files?.[0] || null)} /></label>{file && <span>{file.name} · {(file.size / 1024).toFixed(1)} KB</span>}</div>
        <button className="button" disabled={busy || (!text.trim() && !file)}>{busy ? "正在解析…" : "解析通知"}</button>
      </form>
      {error && <div className="error-banner" role="alert">{error}</div>}
      {(warning || mode) && <div className="data-notice"><strong>解析提示</strong>{mode && <p>{mode === "llm" ? "已使用服务端 AI 结构化提取。" : "当前使用基础规则提取。"}</p>}{warning && <p>{warning}</p>}</div>}
      {drafts.length > 0 && <div className="draft-section">
        <div className="section-heading"><p className="eyebrow">任务预览</p><h2>逐项核对后再保存</h2></div>
        {drafts.map((draft, index) => <article className="draft-card" key={`${index}-${draft.source_text.slice(0, 20)}`}>
          <header><span>任务 {index + 1}</span><strong>置信度 {Math.round(draft.confidence * 100)}%</strong><button type="button" className="danger-link" onClick={() => { setDrafts((current) => current.filter((_, itemIndex) => itemIndex !== index)); setReviewed(false); }}>移除</button></header>
          <div className="form-grid">
            <label>标题<input required value={draft.title} onChange={(event) => update(index, "title", event.target.value)} /></label>
            <label>截止时间<input type="datetime-local" value={draft.deadline ? draft.deadline.slice(0, 16) : ""} onChange={(event) => update(index, "deadline", event.target.value ? new Date(event.target.value).toISOString() : "")} /></label>
            <label>地点<input value={draft.location} onChange={(event) => update(index, "location", event.target.value)} /></label>
            <label>材料<input value={draft.materials.join("、")} onChange={(event) => update(index, "materials", event.target.value)} /></label>
            <label>提交对象<input value={draft.submission_target} onChange={(event) => update(index, "submission_target", event.target.value)} placeholder="老师、辅导员、系统等" /></label>
            <label>提交方式<input value={draft.submission_method} onChange={(event) => update(index, "submission_method", event.target.value)} /></label>
            <label className="span-two">文件命名<input value={draft.file_naming} onChange={(event) => update(index, "file_naming", event.target.value)} /></label>
            <label className="span-two">备注<textarea rows={3} value={draft.notes} onChange={(event) => update(index, "notes", event.target.value)} /></label>
            <label className="span-two">来源链接<input type="url" value={draft.source_url} onChange={(event) => update(index, "source_url", event.target.value)} placeholder="可选" /></label>
          </div>
          {draft.date_explanation && <p className={draft.needs_confirmation ? "date-warning" : "date-note"}>{draft.date_explanation}</p>}
          <details><summary>查看对应通知原文</summary><p className="source-excerpt">{draft.source_text || "未提供原文"}</p></details>
        </article>)}
        <label className="confirmation-check"><input type="checkbox" checked={reviewed} onChange={(event) => setReviewed(event.target.checked)} /><span>我已逐项核对标题、截止时间、提交要求；不确定日期也已由我确认。</span></label>
        <button className="button" type="button" disabled={busy || !reviewed || !drafts.length} onClick={() => void confirm()}>确认并保存 {drafts.length} 条任务</button>
      </div>}
      {saved.length > 0 && <div className="success-panel"><span>✓</span><div><h2>任务已保存</h2><p>已写入你的账户数据库，退出后再次登录仍会存在。</p><div><Link className="button" to="/tasks">前往任务中心</Link><a className="ghost-button" href={apiFileUrl(`/tasks/export/ics?${saved.map((task) => `task_ids=${encodeURIComponent(task.id)}`).join("&")}`)}>下载 ICS 日历</a></div><small>ICS 含提前 24 小时和 3 小时提醒；当前没有网站关闭后的主动推送。</small></div></div>}
    </section>
  );
}

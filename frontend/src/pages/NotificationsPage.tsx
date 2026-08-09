import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, apiFileUrl } from "../api";
import type { NotificationActionItem, NotificationParseResult, Task } from "../types";

type ActionKey = keyof NotificationActionItem;
const splitList = (value: string) => value.split(/[；;、\n]/).map((item) => item.trim()).filter(Boolean);

export default function NotificationsPage() {
  const [text, setText] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<NotificationParseResult | null>(null);
  const [reviewed, setReviewed] = useState(false);
  const [allowExpired, setAllowExpired] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState<Task[]>([]);

  const parse = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    setSaved([]);
    setReviewed(false);
    setAllowExpired(false);
    const form = new FormData();
    form.append("text", text);
    form.append("source_url", sourceUrl);
    if (file) form.append("file", file);
    try {
      setResult(await api<NotificationParseResult>("/notifications/parse", { method: "POST", body: form, timeoutMs: 45000 }));
    } catch (reason) {
      setResult(null);
      setError(reason instanceof Error ? reason.message : "通知解析失败");
    } finally {
      setBusy(false);
    }
  };

  const update = (index: number, key: ActionKey, value: string | boolean | number) => {
    setReviewed(false);
    setResult((current) => {
      if (!current) return current;
      const listFields: ActionKey[] = ["audience", "conditions", "materials", "evidence_requirements", "notes"];
      const action_items = current.action_items.map((item, itemIndex) => {
        if (itemIndex !== index) return item;
        if (listFields.includes(key)) return { ...item, [key]: splitList(String(value)) };
        return { ...item, [key]: value };
      });
      return { ...current, action_items };
    });
  };

  const remove = (index: number) => {
    setResult((current) => current ? { ...current, action_items: current.action_items.filter((_, itemIndex) => itemIndex !== index) } : current);
    setReviewed(false);
  };

  const confirm = async () => {
    const actions = result?.action_items || [];
    if (!reviewed) return setError("请先确认你已经核对任务内容和日期。");
    if (!actions.length) return setError("没有可保存的执行任务。");
    if (actions.some((item) => !item.title.trim())) return setError("每条任务都必须填写标题。");
    if (actions.some((item) => item.is_expired) && !allowExpired) return setError("通知已过期，默认不保存。若确需补交，请手动勾选保存过期任务。");
    setBusy(true);
    setError("");
    try {
      setSaved(await api<Task[]>("/notifications/confirm", {
        method: "POST",
        body: JSON.stringify({ action_items: actions, confirmed: true, allow_expired: allowExpired }),
      }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "任务保存失败");
    } finally {
      setBusy(false);
    }
  };

  const hasExpired = Boolean(result?.action_items.some((item) => item.is_expired));

  return (
    <section className="page section-wrap notification-page">
      <div className="page-heading"><div><p className="eyebrow">通知转任务</p><h1>先看清规则，再保存要做的事</h1><p>系统会区分通知背景、重要规则和真正需要执行的任务；解析不会自动写入任务中心。</p></div></div>
      <div className="workflow-steps"><span className="active">1 粘贴或上传</span><span className={result ? "active" : ""}>2 核对结构化结果</span><span className={saved.length ? "active" : ""}>3 确认保存</span></div>

      <form className="notification-input panel" onSubmit={parse}>
        <label>通知原文<textarea rows={10} value={text} onChange={(event) => setText(event.target.value)} placeholder="粘贴完整通知，保留发布日期、报名条件、截止时间和提交要求。" /></label>
        <label>通知来源链接（可选）<input type="url" value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} placeholder="https://..." /></label>
        <div className="upload-row"><label className="upload-box"><strong>上传 TXT 或 PDF</strong><small>最大 5 MB；扫描图片暂不支持 OCR</small><input type="file" accept=".txt,.pdf,text/plain,application/pdf" onChange={(event) => setFile(event.target.files?.[0] || null)} /></label>{file && <span>{file.name} · {(file.size / 1024).toFixed(1)} KB</span>}</div>
        <button className="button" disabled={busy || (!text.trim() && !file)}>{busy ? "正在解析…" : "解析通知"}</button>
      </form>

      {error && <div className="error-banner" role="alert">{error}</div>}
      {result && <div className="data-notice"><strong>解析方式</strong><p>{result.extraction_mode === "llm" ? "服务端大模型结构化提取" : result.extraction_mode === "rules" ? "安全规则降级提取" : "未识别到可用内容"}</p>{result.warnings.map((warning) => <p key={warning}>{warning}</p>)}</div>}
      {hasExpired && <div className="error-banner expired-banner" role="alert"><strong>这条通知已经过期</strong><p>默认不会保存为待办，避免把历史截止日期误当成新任务。若你确认仍需补交，可在核对后手动选择保存。</p></div>}

      {result && <div className="draft-section">
        <section className="panel notification-summary" aria-labelledby="notice-summary-title">
          <p className="eyebrow">通知摘要</p><h2 id="notice-summary-title">{result.notice.title || "未识别标题"}</h2>
          <div className="summary-grid"><span><small>发布日期</small>{result.notice.notice_date_text || "未说明"}</span><span><small>发布方</small>{result.notice.publisher || "未识别"}</span><span><small>适用校区</small>{result.notice.campuses.join("、") || "未限定"}</span><span><small>适用对象</small>{result.notice.audience.join("、") || "未限定"}</span></div>
          {result.notice.summary && <p>{result.notice.summary}</p>}
        </section>

        <section className="panel"><p className="eyebrow">重要规则</p><h2>先确认是否符合条件</h2>{result.rules.length ? <ol className="notice-rule-list">{result.rules.map((rule) => <li key={rule}>{rule}</li>)}</ol> : <p>没有识别到独立规则。</p>}</section>

        <div className="section-heading"><p className="eyebrow">需要你做的事</p><h2>{result.action_items.length ? `识别到 ${result.action_items.length} 条可执行任务` : "没有识别到需要执行的任务"}</h2></div>
        {!result.action_items.length && <div className="empty-state panel"><p>这份内容可能只有说明性规则，系统不会为了“看起来成功”而生成虚假任务。</p></div>}
        {result.action_items.map((item, index) => <article className="draft-card" key={`${index}-${item.title}`}>
          <header><span>任务 {index + 1}</span><strong>{item.is_expired ? "已过期" : `置信度 ${Math.round(item.confidence * 100)}%`}</strong><button type="button" className="danger-link" onClick={() => remove(index)}>移除</button></header>
          <div className="form-grid">
            <label>任务标题<input required value={item.title} onChange={(event) => update(index, "title", event.target.value)} /></label>
            <label>截止时间<input type="datetime-local" value={item.deadline ? item.deadline.slice(0, 16) : ""} onChange={(event) => update(index, "deadline", event.target.value ? new Date(event.target.value).toISOString() : "")} /></label>
            <label className="span-two">要做什么<textarea rows={2} value={item.action} onChange={(event) => update(index, "action", event.target.value)} /></label>
            <label>适用对象<input value={item.audience.join("；")} onChange={(event) => update(index, "audience", event.target.value)} /></label>
            <label>执行地点<input value={item.location} onChange={(event) => update(index, "location", event.target.value)} /></label>
            <label className="span-two">报名或资格条件<input value={item.conditions.join("；")} onChange={(event) => update(index, "conditions", event.target.value)} /></label>
            <label>所需材料<input value={item.materials.join("；")} onChange={(event) => update(index, "materials", event.target.value)} /></label>
            <label>证明材料<input value={item.evidence_requirements.join("；")} onChange={(event) => update(index, "evidence_requirements", event.target.value)} /></label>
            <label>提交对象<input value={item.submission_target} onChange={(event) => update(index, "submission_target", event.target.value)} /></label>
            <label>提交方式<input value={item.submission_method} onChange={(event) => update(index, "submission_method", event.target.value)} /></label>
            <label className="span-two">文件命名<input value={item.file_naming} onChange={(event) => update(index, "file_naming", event.target.value)} /></label>
            <label className="span-two">备注<input value={item.notes.join("；")} onChange={(event) => update(index, "notes", event.target.value)} /></label>
            <label className="span-two">来源链接<input type="url" value={item.source_url} onChange={(event) => update(index, "source_url", event.target.value)} /></label>
          </div>
          {item.date_explanation && <p className={item.needs_confirmation || item.is_expired ? "date-warning" : "date-note"}>{item.date_explanation}</p>}
          <details><summary>查看对应通知原文</summary><p className="source-excerpt">{item.source_text || "未提供原文"}</p></details>
        </article>)}

        {result.action_items.length > 0 && <>
          <label className="confirmation-check"><input type="checkbox" checked={reviewed} onChange={(event) => setReviewed(event.target.checked)} /><span>我已核对任务、条件、截止时间、提交要求和证据材料。</span></label>
          {hasExpired && <label className="confirmation-check expired-confirmation"><input type="checkbox" checked={allowExpired} onChange={(event) => setAllowExpired(event.target.checked)} /><span>我仍要保存这条已过期任务</span></label>}
          <button className="button" type="button" disabled={busy || !reviewed || (hasExpired && !allowExpired)} onClick={() => void confirm()}>确认并保存 {result.action_items.length} 条任务</button>
        </>}
      </div>}

      {saved.length > 0 && <div className="success-panel"><span>✓</span><div><h2>任务已保存</h2><p>已写入你的任务中心，通知条件、证据要求和原文都会保留。</p><div><Link className="button" to="/tasks">前往任务中心</Link><a className="ghost-button" href={apiFileUrl(`/tasks/export/ics?${saved.map((task) => `task_ids=${encodeURIComponent(task.id)}`).join("&")}`)}>下载 ICS 日历</a></div></div></div>}
    </section>
  );
}

import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api";
import { EmptyState, Loading } from "../components/ProtectedRoute";
import type { Campus, ImportResult, KnowledgeSearchResult, KnowledgeSource } from "../types";

type Props = { mode: "import" | "sources" };

function messageOf(error: unknown): string {
  return error instanceof ApiError ? error.message : "请求失败，请稍后重试";
}

export default function KnowledgePage({ mode }: Props) {
  const [campuses, setCampuses] = useState<Campus[]>([]);
  const [campusId, setCampusId] = useState("");
  const [sources, setSources] = useState<KnowledgeSource[]>([]);
  const [selected, setSelected] = useState<KnowledgeSource | null>(null);
  const [loading, setLoading] = useState(mode === "sources");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<KnowledgeSearchResult[]>([]);
  const [filePreview, setFilePreview] = useState("");

  const refreshSources = async () => {
    setLoading(true);
    try {
      setSources(await api<KnowledgeSource[]>("/knowledge/sources"));
      setError("");
    } catch (reason) {
      setError(messageOf(reason));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void api<Campus[]>("/campuses").then(setCampuses).catch(() => setCampuses([]));
    if (mode === "sources") void refreshSources();
  }, [mode]);

  const showResult = (result: ImportResult) => {
    setNotice(`导入 ${result.imported} 篇，跳过重复 ${result.duplicates} 篇，失败 ${result.failed} 篇。`);
    setError(result.errors.join("；"));
  };

  const importFiles = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const input = event.currentTarget.elements.namedItem("files") as HTMLInputElement;
    if (!input.files?.length) return;
    const form = new FormData();
    Array.from(input.files).forEach((file) => form.append("files", file));
    if (campusId) form.append("campus_id", campusId);
    setBusy(true);
    try {
      const result = await api<ImportResult>("/knowledge/import/files", { method: "POST", body: form, timeoutMs: 120_000 });
      showResult(result);
      if (!result.failed) {
        input.value = "";
        setFilePreview("");
      }
    } catch (reason) {
      setError(messageOf(reason));
    } finally {
      setBusy(false);
    }
  };

  const importText = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    try {
      showResult(await api<ImportResult>("/knowledge/import/text", {
        method: "POST",
        body: JSON.stringify({
          title: String(form.get("title") || ""),
          content: String(form.get("content") || ""),
          campus_id: campusId || null,
          publisher: String(form.get("publisher") || ""),
        }),
        timeoutMs: 60_000,
      }));
      event.currentTarget.reset();
    } catch (reason) {
      setError(messageOf(reason));
    } finally {
      setBusy(false);
    }
  };

  const importUrl = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    try {
      showResult(await api<ImportResult>("/knowledge/import/url", {
        method: "POST",
        body: JSON.stringify({
          url: String(form.get("url") || ""),
          campus_id: campusId || null,
          publisher: String(form.get("publisher") || ""),
        }),
        timeoutMs: 60_000,
      }));
      event.currentTarget.reset();
    } catch (reason) {
      setError(messageOf(reason));
    } finally {
      setBusy(false);
    }
  };

  const search = async (event: FormEvent) => {
    event.preventDefault();
    if (!query.trim()) return;
    setBusy(true);
    try {
      const parameters = new URLSearchParams({ q: query.trim() });
      if (campusId) parameters.set("campus_id", campusId);
      setResults(await api<KnowledgeSearchResult[]>(`/knowledge/search?${parameters}`));
      setError("");
    } catch (reason) {
      setError(messageOf(reason));
    } finally {
      setBusy(false);
    }
  };

  const openSource = async (source: Pick<KnowledgeSource, "id">) => {
    try {
      setSelected(await api<KnowledgeSource>(`/knowledge/sources/${source.id}`));
    } catch (reason) {
      setError(messageOf(reason));
    }
  };

  const removeSource = async (source: KnowledgeSource) => {
    if (!window.confirm(`确认删除“${source.title}”及其检索索引吗？`)) return;
    try {
      await api(`/knowledge/sources/${source.id}?confirmed=true`, { method: "DELETE" });
      setSelected(null);
      setResults((current) => current.filter((item) => item.document_id !== source.id));
      await refreshSources();
    } catch (reason) {
      setError(messageOf(reason));
    }
  };

  const reindex = async () => {
    setBusy(true);
    try {
      const result = await api<{ indexed_documents: number }>("/knowledge/reindex", { method: "POST", timeoutMs: 120_000 });
      setNotice(`已重建 ${result.indexed_documents} 篇资料的中文检索索引。`);
      await refreshSources();
    } catch (reason) {
      setError(messageOf(reason));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="page section-wrap knowledge-page">
      <div className="page-heading">
        <div><p className="eyebrow">私有知识库</p><h1>{mode === "import" ? "导入你的校园资料" : "资料来源与检索"}</h1><p>原文只保存在你的账户下；未经管理员审核，不会变成其他用户的共享知识。</p></div>
        <div className="button-row">
          <Link className={mode === "import" ? "button compact" : "ghost-button compact"} to="/knowledge/import">导入资料</Link>
          <Link className={mode === "sources" ? "button compact" : "ghost-button compact"} to="/knowledge/sources">来源与检索</Link>
        </div>
      </div>
      <label className="field">适用校区<select aria-label="知识资料适用校区" value={campusId} onChange={(event) => setCampusId(event.target.value)}><option value="">全部校区</option>{campuses.map((campus) => <option key={campus.id} value={campus.id}>{campus.name}</option>)}</select></label>
      {notice && <div className="success-banner" role="status">{notice}</div>}
      {error && <div className="error-banner" role="alert">{error}</div>}

      {mode === "import" ? <div className="knowledge-grid">
        <form className="panel stack-form" onSubmit={importFiles}><p className="eyebrow">文件导入</p><h2>上传本地资料</h2><p>支持 Markdown、TXT、HTML/MHTML、PDF、DOCX、JSON、CSV；仅提取正文，不保存原始文件。</p><input name="files" aria-label="选择知识文件" type="file" multiple required accept=".md,.txt,.html,.htm,.mhtml,.pdf,.docx,.json,.csv" onChange={(event) => { const files = Array.from(event.target.files || []); const bytes = files.reduce((sum, file) => sum + file.size, 0); setFilePreview(files.length ? `待导入 ${files.length} 个文件，共 ${(bytes / 1024 / 1024).toFixed(2)} MB；提交后显示去重与失败统计。` : ""); }} />{filePreview && <small role="status">{filePreview}</small>}<button className="button" disabled={busy}>{busy ? "正在清洗并建立索引…" : "导入文件"}</button><small>失败文件会保留在选择框中，可修正后直接重试。</small></form>
        <form className="panel stack-form" onSubmit={importUrl}><p className="eyebrow">网页导入</p><h2>导入文章 URL</h2><label>文章地址<input name="url" type="url" required placeholder="https://…" /></label><label>发布者（可选）<input name="publisher" maxLength={255} /></label><button className="button" disabled={busy}>抓取并导入</button></form>
        <form className="panel stack-form" onSubmit={importText}><p className="eyebrow">正文导入</p><h2>粘贴文章正文</h2><label>标题<input name="title" required maxLength={255} /></label><label>发布者（可选）<input name="publisher" maxLength={255} /></label><label>正文<textarea name="content" required minLength={2} rows={10} /></label><button className="button" disabled={busy}>保存并建立索引</button></form>
      </div> : <>
        <form className="panel knowledge-search" onSubmit={search}><label>搜索你的私有资料和已公开校园知识<input value={query} onChange={(event) => setQuery(event.target.value)} required placeholder="例如：奖学金申请条件" /></label><button className="button compact" disabled={busy}>搜索</button><button className="ghost-button compact" type="button" disabled={busy} onClick={() => void reindex()}>重建索引</button></form>
        {results.length > 0 && <div className="panel"><div className="panel-heading"><h2>检索结果</h2><span>{results.length} 条</span></div><div className="source-list">{results.map((item) => <button key={item.document_id} onClick={() => void openSource({ id: item.document_id })}><strong>{item.title}</strong><small>{item.visibility === "private" ? "仅自己可见" : "共享资料"} · 匹配度 {item.score.toFixed(2)}</small><p>{item.snippet}</p></button>)}</div></div>}
        {loading ? <Loading /> : sources.length ? <div className="panel"><div className="panel-heading"><h2>资料来源</h2><span>{sources.length} 篇</span></div><div className="source-list">{sources.map((source) => <button key={source.id} onClick={() => void openSource(source)}><strong>{source.title}</strong><small>{source.visibility === "private" ? "仅自己可见" : "共享资料"} · {source.chunk_count} 个检索分块 · {source.source_type}</small></button>)}</div></div> : <EmptyState title="还没有资料" detail="先导入文件、文章 URL 或正文。" />}
      </>}

      {selected && <div className="drawer-backdrop" onClick={() => setSelected(null)}><aside className="detail-drawer" aria-label="知识来源详情" onClick={(event) => event.stopPropagation()}><button className="drawer-close" aria-label="关闭" onClick={() => setSelected(null)}>×</button><p className="eyebrow">{selected.visibility === "private" ? "仅自己可见" : "共享资料"}</p><h2>{selected.title}</h2><p>{selected.publisher || "发布者待补充"} · {selected.source_type}</p><details><summary>查看机器提取信息（待审核）</summary><dl>{Object.entries(selected.extracted_metadata || {}).filter(([, value]) => Array.isArray(value) ? value.length > 0 : Boolean(value)).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{Array.isArray(value) ? value.join("；") : String(value)}</dd></div>)}</dl></details><pre className="knowledge-content">{selected.content}</pre>{selected.visibility === "private" && <button className="danger-button" onClick={() => void removeSource(selected)}>删除资料</button>}</aside></div>}
    </section>
  );
}

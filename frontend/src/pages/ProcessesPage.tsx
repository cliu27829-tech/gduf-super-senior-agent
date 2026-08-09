import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { EmptyState, Loading } from "../components/ProtectedRoute";
import { formatDate, StatusBadge } from "../components/StatusBadge";
import type { CampusProcess, Task } from "../types";

export default function ProcessesPage() {
  const { user } = useAuth();
  const [rows, setRows] = useState<CampusProcess[]>([]);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<CampusProcess | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState<Task[]>([]);

  useEffect(() => {
    const params = new URLSearchParams();
    if (user?.campus_id) params.set("campus_id", user.campus_id);
    api<CampusProcess[]>(`/processes?${params.toString()}`).then(setRows).catch((reason) => {
      setError(reason instanceof Error ? reason.message : "办事流程加载失败");
    }).finally(() => setLoading(false));
  }, [user?.campus_id]);

  const filtered = useMemo(() => rows.filter((row) => `${row.title} ${row.category}`.toLowerCase().includes(query.toLowerCase())), [rows, query]);
  const saveAsTasks = async () => {
    if (!selected || !window.confirm(`确认把“${selected.title}”及其步骤保存到你的任务中心吗？`)) return;
    setBusy(true); setError("");
    try {
      const created = await api<Task[]>(`/processes/${selected.id}/create-tasks`, {
        method: "POST", body: JSON.stringify({ confirmed: true, include_overview: true }),
      });
      setSaved(created);
      setSelected(null);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "保存任务失败"); }
    finally { setBusy(false); }
  };

  return (
    <section className="page section-wrap">
      <div className="page-heading"><div><p className="eyebrow">校园办事</p><h1>按来源一步步把事情办完</h1><p>资料不完整时会明确标记待核验，不补写地点、费用或时限。</p></div></div>
      <label className="search-box"><span>⌕</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索校园卡、报修、证明…" /></label>
      {error && <div className="error-banner" role="alert">{error}</div>}
      {saved.length > 0 && <div className="success-banner" role="status">已保存 {saved.length} 条任务。<Link to="/tasks">前往任务中心</Link></div>}
      {loading ? <Loading /> : filtered.length ? <div className="process-grid">{filtered.map((item) => <button className="panel process-card" key={item.id} onClick={() => { setSelected(item); setSaved([]); }}><div className="panel-heading"><strong>{item.title}</strong><StatusBadge value={item.verification_status} /></div><p>{item.notes || item.steps[0]?.text || "查看结构化办理步骤"}</p><small>{item.category} · 核验：{formatDate(item.verified_at)}</small></button>)}</div> : <EmptyState title="暂无匹配流程" detail="当前校区缺少可靠资料时不会显示虚构流程。" />}
      {selected && <div className="drawer-backdrop" onClick={() => setSelected(null)}><aside className="detail-drawer" onClick={(event) => event.stopPropagation()}><button className="drawer-close" onClick={() => setSelected(null)}>×</button><p className="eyebrow">办事流程</p><h2>{selected.title}</h2><div className="badge-row"><StatusBadge value={selected.verification_status} /><StatusBadge value={selected.data_status} /></div><dl><dt>适用人群</dt><dd>{selected.audience || "待核验"}</dd><dt>办理地点</dt><dd>{selected.location || "待核验"}</dd><dt>开放时间</dt><dd>{selected.opening_hours || "待核验"}</dd><dt>联系电话</dt><dd>{selected.contact || "待核验"}</dd><dt>所需材料</dt><dd>{selected.materials.join("、") || "待核验"}</dd><dt>可信度</dt><dd>{Math.round(selected.confidence * 100)}%</dd></dl><h3>办理步骤</h3><ol>{selected.steps.map((step, index) => <li key={index}>{step.text || step.title}</li>)}</ol>{selected.notes && <p>{selected.notes}</p>}{selected.online_url && <a href={selected.online_url} target="_blank" rel="noreferrer">打开线上入口</a>}<div className="source-list"><h3>来源</h3>{selected.source ? <a href={selected.source.url} target="_blank" rel="noreferrer"><strong>{selected.source.title}</strong><small>{selected.source.publisher} · {selected.source.is_official ? "官方" : "非官方线索"}</small></a> : <p>暂无公开来源，内容仍待核验。</p>}</div><button className="button full" disabled={busy || !selected.steps.length} onClick={() => void saveAsTasks()}>{busy ? "保存中…" : "确认并保存为任务"}</button></aside></div>}
    </section>
  );
}

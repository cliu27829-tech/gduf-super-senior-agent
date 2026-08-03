import { useEffect, useMemo, useState, type FormEvent } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { api, apiFileUrl } from "../api";
import { EmptyState, Loading } from "../components/ProtectedRoute";
import { formatDate, StatusBadge } from "../components/StatusBadge";
import type { Campus, Location } from "../types";

type AdminRecord = Record<string, unknown>;
const sections = [
  ["", "仪表盘"], ["users", "用户"], ["campuses", "校区"], ["locations", "地点"], ["maps", "地图"],
  ["canteens", "饭堂"], ["stalls", "档口"], ["processes", "办事流程"], ["sources", "资料来源"],
  ["feedback", "纠错审核"], ["stale", "过期数据"], ["logs", "系统日志"], ["data", "导入导出"],
];

const managedSections = new Set(["campuses", "maps", "canteens", "stalls", "processes", "sources"]);

function recordTemplate(section: string, campuses: Campus[]): AdminRecord {
  const campusId = campuses[0]?.id || "REPLACE_WITH_CAMPUS_UUID";
  const templates: Record<string, AdminRecord> = {
    campuses: { slug: "new-campus", name: "新校区", address: "", data_notice: "数据待完善", is_active: true },
    maps: { campus_id: campusId, image_url: "https://", version: "", license_note: "来源与授权待核验", is_active: true },
    canteens: { campus_id: campusId, location_id: null, source_id: null, name: "新饭堂", floors: [], opening_hours: "", payment_methods: [], verification_status: "needs_verification", verified_at: null, confidence: 0, is_active: true, evidence: "", verification_note: "" },
    stalls: { canteen_id: "REPLACE_WITH_CANTEEN_ID", name: "新档口", floor: "", food_type: "", common_items: [], price_range: "", meal_periods: [], opening_hours: "", payment_methods: [], is_operating: null, verification_status: "needs_verification", verified_at: null, confidence: 0, is_active: true, evidence: "", verification_note: "" },
    processes: { campus_id: campusId, source_id: null, title: "新办事流程", category: "other", steps: [], materials: [], contact: "", verification_status: "needs_verification", verified_at: null, is_active: true, evidence: "", verification_note: "" },
    sources: { title: "新资料来源", url: "https://", publisher: "", source_type: "unverified", published_at: null, fetched_at: null, verified_at: null, confidence: 0, is_official: false },
  };
  return templates[section] || {};
}

function editableRecord(section: string, row: AdminRecord): AdminRecord {
  const template = recordTemplate(section, []);
  return Object.fromEntries(Object.keys(template).map((key) => [key, row[key] ?? template[key]]));
}

export default function AdminPage() {
  const location = useLocation();
  const section = location.pathname.replace(/^\/admin\/?/, "").split("/")[0];
  const [data, setData] = useState<unknown>(null);
  const [campuses, setCampuses] = useState<Campus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const endpoint = section ? `/admin/${section}` : "/admin/dashboard";
  const load = () => {
    if (section === "data") { setData(null); setLoading(false); return Promise.resolve(); }
    setLoading(true); setError("");
    return api(endpoint).then(setData).catch((reason) => setError(reason instanceof Error ? reason.message : "加载失败")).finally(() => setLoading(false));
  };
  useEffect(() => { void load(); api<Campus[]>("/campuses").then(setCampuses).catch(() => undefined); }, [section]);
  return (
    <section className="admin-layout section-wrap">
      <aside className="admin-sidebar"><div><span className="brand-mark small">管</span><strong>数据管理后台</strong></div><nav>{sections.map(([path, label]) => <NavLink end={path === ""} key={path} to={`/admin${path ? `/${path}` : ""}`}>{label}</NavLink>)}</nav></aside>
      <div className="admin-main"><div className="page-heading"><div><p className="eyebrow">管理员后台</p><h1>{sections.find(([value]) => value === section)?.[1] || "仪表盘"}</h1><p>所有写操作均记录管理员、实体、动作和时间；不会展示密码或 API Key。</p></div></div>{error && <div className="error-banner" role="alert">{error}</div>}{notice && <div className="success-banner" role="status">{notice}</div>}{loading ? <Loading /> : <AdminContent section={section} data={data} campuses={campuses} reload={load} setNotice={setNotice} setError={setError} />}</div>
    </section>
  );
}

function AdminContent({ section, data, campuses, reload, setNotice, setError }: { section: string; data: unknown; campuses: Campus[]; reload: () => Promise<unknown>; setNotice: (value: string) => void; setError: (value: string) => void }) {
  if (!section) return <Dashboard data={data as AdminRecord} />;
  if (section === "locations") return <LocationsAdmin rows={(data || []) as Location[]} campuses={campuses} reload={reload} setNotice={setNotice} setError={setError} />;
  if (section === "feedback") return <FeedbackAdmin rows={(data || []) as AdminRecord[]} reload={reload} setNotice={setNotice} />;
  if (section === "users") return <UsersAdmin rows={(data || []) as AdminRecord[]} reload={reload} />;
  if (section === "data") return <DataAdmin setNotice={setNotice} setError={setError} />;
  if (section === "logs") return <LogsAdmin data={(data || {}) as Record<string, AdminRecord[]>} />;
  const rows = Array.isArray(data) ? data as AdminRecord[] : [];
  if (managedSections.has(section)) return <ManagedRecords section={section} rows={rows} campuses={campuses} reload={reload} setNotice={setNotice} setError={setError} />;
  return <GenericTable rows={rows} section={section} />;
}

function Dashboard({ data }: { data: AdminRecord }) {
  const metrics = [["users", "用户"], ["active_users", "活跃账户"], ["locations", "地点"], ["canteens", "饭堂"], ["pending_feedback", "待审纠错"], ["stale_records", "过期/待核验"], ["recent_errors", "近 7 日错误"]];
  return <><div className="metric-grid admin-metrics">{metrics.map(([key, label]) => <article key={key}><span>{label}</span><strong>{String(data?.[key] ?? 0)}</strong></article>)}</div><div className="panel"><h2>数据发布原则</h2><div className="admin-principles"><p><strong>已核验</strong>必须填写证据、核验方法和备注。</p><p><strong>待核验</strong>可以保存，但前台必须展示状态。</p><p><strong>实时菜单</strong>在没有稳定数据源前始终关闭。</p><p><strong>用户隐私</strong>管理员也不能查看明文密码、Token 或 API Key。</p></div></div></>;
}

function LocationsAdmin({ rows, campuses, reload, setNotice, setError }: { rows: Location[]; campuses: Campus[]; reload: () => Promise<unknown>; setNotice: (value: string) => void; setError: (value: string) => void }) {
  const [show, setShow] = useState(false);
  const [form, setForm] = useState({ campus_id: campuses[0]?.id || "", name: "", category: "other", area: "", map_x: "", map_y: "", verification_status: "needs_verification", confidence: "0", evidence: "", verification_note: "" });
  useEffect(() => { if (!form.campus_id && campuses[0]) setForm((value) => ({ ...value, campus_id: campuses[0].id })); }, [campuses]);
  const save = async (event: FormEvent) => { event.preventDefault(); try { await api("/admin/locations", { method: "POST", body: JSON.stringify({ ...form, map_x: form.map_x ? Number(form.map_x) : null, map_y: form.map_y ? Number(form.map_y) : null, confidence: Number(form.confidence), aliases: [], services: [], payment_methods: [], source_ids: [] }) }); setShow(false); setNotice("地点已创建并写入审计日志"); await reload(); } catch (reason) { setError(reason instanceof Error ? reason.message : "保存失败"); } };
  const deactivate = async (id: string) => { await api(`/admin/locations/${id}`, { method: "DELETE" }); await reload(); };
  return <><div className="admin-actions"><button className="button" onClick={() => setShow(!show)}>＋ 添加地点</button><span>共 {rows.length} 条，含停用记录</span></div>{show && <form className="panel admin-form" onSubmit={save}><div className="form-grid"><label>校区<select value={form.campus_id} onChange={(e) => setForm({ ...form, campus_id: e.target.value })}>{campuses.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>地点名称<input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label><label>分类<input value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} /></label><label>区域<input value={form.area} onChange={(e) => setForm({ ...form, area: e.target.value })} /></label><label>示意 X（0-1）<input type="number" min="0" max="1" step="0.01" value={form.map_x} onChange={(e) => setForm({ ...form, map_x: e.target.value })} /></label><label>示意 Y（0-1）<input type="number" min="0" max="1" step="0.01" value={form.map_y} onChange={(e) => setForm({ ...form, map_y: e.target.value })} /></label><label>核验状态<select value={form.verification_status} onChange={(e) => setForm({ ...form, verification_status: e.target.value })}><option value="needs_verification">待核验</option><option value="verified">已核验</option></select></label><label>可信度<input type="number" min="0" max="1" step="0.05" value={form.confidence} onChange={(e) => setForm({ ...form, confidence: e.target.value })} /></label><label className="span-two">核验证据<input value={form.evidence} onChange={(e) => setForm({ ...form, evidence: e.target.value })} placeholder="标记已核验时必填" /></label><label className="span-two">核验备注<textarea value={form.verification_note} onChange={(e) => setForm({ ...form, verification_note: e.target.value })} /></label></div><button className="button">保存地点</button></form>}<div className="admin-table"><div className="admin-table-head"><span>地点</span><span>分类</span><span>核验</span><span>更新时间</span><span>操作</span></div>{rows.map((row) => <div className="admin-table-row" key={row.id}><div><strong>{row.name}</strong><small>{row.area || row.address}</small></div><span>{row.category}</span><StatusBadge value={row.is_active ? row.verification_status : "inactive"} /><span>{formatDate(row.updated_at)}</span><button className="danger-link" disabled={!row.is_active} onClick={() => void deactivate(row.id)}>停用</button></div>)}</div></>;
}

function FeedbackAdmin({ rows, reload, setNotice }: { rows: AdminRecord[]; reload: () => Promise<unknown>; setNotice: (value: string) => void }) {
  const review = async (id: string, action: "approve" | "reject") => { const note = window.prompt("填写审核备注（可选）") || ""; await api(`/admin/feedback/${id}/${action}`, { method: "POST", body: JSON.stringify({ note }) }); setNotice(`纠错已${action === "approve" ? "通过" : "拒绝"}`); await reload(); };
  return rows.length ? <div className="admin-table"><div className="admin-table-head four"><span>纠错内容</span><span>提交时间</span><span>状态</span><span>操作</span></div>{rows.map((row) => <div className="admin-table-row four" key={String(row.id)}><div><strong>{String(row.content)}</strong><small>{String(row.evidence_url || "无外部证据")}</small></div><span>{formatDate(String(row.created_at))}</span><StatusBadge value={String(row.status)} /><div><button onClick={() => void review(String(row.id), "approve")}>通过</button><button className="danger-link" onClick={() => void review(String(row.id), "reject")}>拒绝</button></div></div>)}</div> : <EmptyState title="没有待审纠错" detail="学生提交的地点纠错会出现在这里。" />;
}

function UsersAdmin({ rows, reload }: { rows: AdminRecord[]; reload: () => Promise<unknown> }) {
  const toggle = async (row: AdminRecord) => { await api(`/admin/users/${String(row.id)}`, { method: "PATCH", body: JSON.stringify({ is_active: !row.is_active }) }); await reload(); };
  return <div className="admin-table"><div className="admin-table-head four"><span>用户</span><span>角色</span><span>创建时间</span><span>状态</span></div>{rows.map((row) => <div className="admin-table-row four" key={String(row.id)}><div><strong>{String(row.nickname || row.username)}</strong><small>{String(row.email)}</small></div><span>{String(row.role)}</span><span>{formatDate(String(row.created_at))}</span><button onClick={() => void toggle(row)}>{row.is_active ? "停用" : "启用"}</button></div>)}</div>;
}

function DataAdmin({ setNotice, setError }: { setNotice: (value: string) => void; setError: (value: string) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const upload = async () => { if (!file) return; const form = new FormData(); form.append("file", file); try { const result = await api<{ created: number }>("/admin/data/import", { method: "POST", body: form }); setNotice(`导入完成：新增 ${result.created} 条地点`); } catch (reason) { setError(reason instanceof Error ? reason.message : "导入失败"); } };
  return <div className="profile-grid"><div className="panel"><h2>导入地点数据</h2><p>支持 UTF-8 CSV、JSON 和 GeoJSON，最大 5 MB。导入内容默认保留核验状态，不会自动变成“已核验”。</p><input type="file" accept=".csv,.json,.geojson" onChange={(e) => setFile(e.target.files?.[0] || null)} /><button className="button" onClick={() => void upload()} disabled={!file}>开始导入</button></div><div className="panel"><h2>导出当前数据</h2><p>导出包含地点、来源、可信度、核验状态和更新时间，可用于人工复核或迁移。</p><a className="ghost-button" href={apiFileUrl("/admin/data/export")}>下载 JSON</a></div></div>;
}

function LogsAdmin({ data }: { data: Record<string, AdminRecord[]> }) {
  return <div className="log-sections">{Object.entries(data).map(([name, rows]) => <div className="panel" key={name}><h2>{name}</h2>{rows.length ? rows.slice(0, 30).map((row, index) => <div className="log-row" key={String(row.id || index)}><strong>{String(row.action || row.event || row.status)}</strong><span>{String(row.summary || row.message || "")}</span><small>{formatDate(String(row.created_at || row.fetched_at || ""))}</small></div>) : <p>暂无记录</p>}</div>)}</div>;
}

function ManagedRecords({ section, rows, campuses, reload, setNotice, setError }: { section: string; rows: AdminRecord[]; campuses: Campus[]; reload: () => Promise<unknown>; setNotice: (value: string) => void; setError: (value: string) => void }) {
  const [editingId, setEditingId] = useState("");
  const [showEditor, setShowEditor] = useState(false);
  const [payload, setPayload] = useState(() => JSON.stringify(recordTemplate(section, campuses), null, 2));
  useEffect(() => { if (!showEditor) setPayload(JSON.stringify(recordTemplate(section, campuses), null, 2)); }, [section, campuses, showEditor]);
  const create = () => { setEditingId(""); setPayload(JSON.stringify(recordTemplate(section, campuses), null, 2)); setShowEditor(true); };
  const edit = (row: AdminRecord) => { setEditingId(String(row.id)); setPayload(JSON.stringify(editableRecord(section, row), null, 2)); setShowEditor(true); };
  const save = async (event: FormEvent) => {
    event.preventDefault(); setError("");
    try {
      const parsed = JSON.parse(payload) as AdminRecord;
      await api(`/admin/${section}${editingId ? `/${editingId}` : ""}`, { method: editingId ? "PATCH" : "POST", body: JSON.stringify(parsed) });
      setShowEditor(false); setNotice(`${editingId ? "更新" : "新增"}已保存并写入审计日志`); await reload();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "JSON 格式或提交内容有误"); }
  };
  const remove = async (row: AdminRecord) => {
    if (!window.confirm(`确认停用或删除「${String(row.name || row.title || row.id)}」？`)) return;
    try { await api(`/admin/${section}/${String(row.id)}`, { method: "DELETE" }); setNotice("操作已完成并写入审计日志"); await reload(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "操作失败"); }
  };
  return <><div className="admin-actions"><button className="button" onClick={create}>＋ 新增记录</button><span>共 {rows.length} 条；高级字段使用结构化 JSON，保存前由后端再次校验。</span></div>{showEditor && <form className="panel admin-form" onSubmit={save}><div className="panel-heading"><h2>{editingId ? "编辑记录" : "新增记录"}</h2><button type="button" onClick={() => setShowEditor(false)}>取消</button></div><label>结构化数据<textarea className="json-editor" rows={18} value={payload} onChange={(event) => setPayload(event.target.value)} spellCheck={false} /></label><small>“已核验”记录必须同时填写 evidence；时间使用 ISO 8601 格式。</small><button className="button">校验并保存</button></form>}<div className="managed-records"><GenericTable rows={rows} section={section} />{rows.map((row) => <div className="managed-row-actions" key={String(row.id)}><strong>{String(row.name || row.title || row.slug || row.id)}</strong><button onClick={() => edit(row)}>编辑</button><button className="danger-link" onClick={() => void remove(row)}>停用/删除</button></div>)}</div></>;
}

function GenericTable({ rows, section }: { rows: AdminRecord[]; section: string }) {
  const fields = useMemo(() => rows.length ? Object.keys(rows[0]).filter((key) => !["password_hash", "token_hash"].includes(key)).slice(0, 5) : [], [rows]);
  if (!rows.length) return <EmptyState title="暂无数据" detail={`${section} 暂无记录，可以通过对应 API 或导入功能补充。`} />;
  return <div className="generic-table"><table><thead><tr>{fields.map((field) => <th key={field}>{field}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={String(row.id || index)}>{fields.map((field) => <td key={field}>{typeof row[field] === "object" ? JSON.stringify(row[field]) : String(row[field] ?? "")}</td>)}</tr>)}</tbody></table></div>;
}

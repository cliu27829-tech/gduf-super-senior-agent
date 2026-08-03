import { useEffect, useMemo, useState, type FormEvent } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { EmptyState, Loading } from "../components/ProtectedRoute";
import { formatDate, StatusBadge } from "../components/StatusBadge";
import type { Campus, Location } from "../types";

const categories = [
  ["", "全部"], ["canteen", "饭堂"], ["teaching_building", "教学楼"], ["dormitory", "宿舍"],
  ["library", "图书馆"], ["express_station", "快递"], ["medical", "医务室"], ["supermarket", "超市"],
];

export default function MapPage() {
  const { user } = useAuth();
  const [campuses, setCampuses] = useState<Campus[]>([]);
  const [campusId, setCampusId] = useState(user?.campus_id || "");
  const [locations, setLocations] = useState<Location[]>([]);
  const [selected, setSelected] = useState<Location | null>(null);
  const [category, setCategory] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [feedback, setFeedback] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => { api<Campus[]>("/campuses").then((rows) => { setCampuses(rows); setCampusId((current) => current || rows[0]?.id || ""); }).catch((reason) => { setError(reason instanceof Error ? reason.message : "校区加载失败"); setLoading(false); }); }, []);
  useEffect(() => {
    if (!campusId) return;
    setLoading(true); setSelected(null); setError("");
    api<Location[]>(`/locations?campus_id=${encodeURIComponent(campusId)}`).then(setLocations).catch((reason) => { setLocations([]); setError(reason instanceof Error ? reason.message : "地点加载失败"); }).finally(() => setLoading(false));
  }, [campusId]);

  const filtered = useMemo(() => locations.filter((item) => {
    const haystack = [item.name, ...item.aliases, item.description, item.area, item.address].join(" ").toLowerCase();
    return (!category || item.category === category) && (!query || haystack.includes(query.toLowerCase()));
  }), [locations, category, query]);
  const campus = campuses.find((item) => item.id === campusId);
  const navigationUrl = selected ? (selected.latitude != null && selected.longitude != null
    ? `https://uri.amap.com/navigation?to=${selected.longitude},${selected.latitude},${encodeURIComponent(selected.name)}&mode=walk&callnative=0`
    : `https://www.amap.com/search?query=${encodeURIComponent(`${campus?.name || ""} ${selected.address} ${selected.name}`)}`) : "";
  const submitFeedback = async (event: FormEvent) => {
    event.preventDefault(); setMessage("");
    try {
      await api("/location-feedback", { method: "POST", body: JSON.stringify({ campus_id: campusId, location_id: selected?.id, content: feedback }) });
      setFeedback(""); setMessage("纠错已提交，等待管理员审核。");
    } catch (reason) { setMessage(reason instanceof Error ? reason.message : "提交失败"); }
  };
  return (
    <section className="page section-wrap map-page">
      <div className="page-heading"><div><p className="eyebrow">校园地图</p><h1>先选校区，再找准确地点</h1><p>示意坐标只表示相对位置；精确 GPS 和步行路线以外部地图为准。</p></div><select aria-label="选择校区" value={campusId} onChange={(e) => setCampusId(e.target.value)}>{campuses.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></div>
      <div className="map-toolbar"><label className="search-box"><span>⌕</span><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索教学楼、饭堂、快递…" /></label><div className="filter-chips">{categories.map(([value, label]) => <button key={value} className={category === value ? "active" : ""} onClick={() => setCategory(value)}>{label}</button>)}</div></div>
      {error && <div className="error-banner" role="alert">{error}</div>}
      {campus && <div className="data-notice compact-notice"><strong>{campus.name}</strong><p>{campus.data_notice}</p></div>}
      {loading ? <Loading /> : <div className="map-layout">
        <div className="schematic-map" aria-label={`${campus?.name || "校区"}示意地图`}>
          <div className="map-grid-lines" />
          <div className="map-caption"><strong>{campus?.name}</strong><span>校内示意图 · 非测绘地图</span></div>
          {filtered.filter((item) => item.map_x != null && item.map_y != null).map((item, index) => <button key={item.id} aria-label={`查看${item.name}`} className={`map-marker ${selected?.id === item.id ? "selected" : ""}`} style={{ left: `${item.map_x! * 100}%`, top: `${item.map_y! * 100}%` }} onClick={() => setSelected(item)}><span>{index + 1}</span><small>{item.name}</small></button>)}
          {!filtered.some((item) => item.map_x != null) && <EmptyState title="该筛选暂无示意点位" detail="管理员可以补充示意坐标；系统不会伪装成完整地图。" />}
        </div>
        <aside className="location-list"><div className="panel-heading"><h2>地点列表</h2><span>{filtered.length} 条</span></div>{filtered.length ? filtered.map((item) => <button className={selected?.id === item.id ? "location-row active" : "location-row"} key={item.id} onClick={() => setSelected(item)}><span className={`category-icon category-${item.category}`}>{item.category === "canteen" ? "食" : "⌖"}</span><div><strong>{item.name}</strong><small>{item.area || item.address || "位置待核验"}</small></div><StatusBadge value={item.verification_status} /></button>) : <EmptyState title="没有匹配地点" detail="换个关键词或切换分类试试。" />}</aside>
      </div>}
      {selected && <div className="drawer-backdrop" onClick={() => setSelected(null)}><aside className="detail-drawer" onClick={(e) => e.stopPropagation()} aria-label="地点详情"><button className="drawer-close" onClick={() => setSelected(null)} aria-label="关闭">×</button><p className="eyebrow">地点详情</p><h2>{selected.name}</h2><div className="badge-row"><StatusBadge value={selected.verification_status} /><StatusBadge value={selected.freshness_status} /><span className={`status-badge status-${selected.data_status}`}>{selected.data_status === "historical" ? "历史资料" : selected.data_status === "current" ? "当前资料" : "待核验"}</span></div>{selected.data_status === "historical" && <p className="date-warning">这是历史资料，位置或服务可能已经变化，请通过来源或校方电话再次确认。</p>}<dl><dt>区域</dt><dd>{selected.area || "待核验"}</dd><dt>详细位置</dt><dd>{[selected.address, selected.floor].filter(Boolean).join(" · ") || "待核验"}</dd><dt>别名</dt><dd>{selected.aliases.join("、") || "无"}</dd><dt>开放时间</dt><dd>{selected.opening_hours || "待核验"}</dd><dt>可办服务</dt><dd>{selected.services.join("、") || "待核验"}</dd><dt>资料核验</dt><dd>{formatDate(selected.verified_at)}</dd><dt>数据更新</dt><dd>{formatDate(selected.updated_at)}</dd><dt>可信度</dt><dd>{Math.round(selected.confidence * 100)}%</dd></dl><p>{selected.description || "暂无说明"}</p><a className="button full" href={navigationUrl} target="_blank" rel="noreferrer">打开外部地图查询</a><div className="source-list"><h3>数据来源</h3>{selected.sources.length ? selected.sources.map((source) => source.url ? <a href={source.url} target="_blank" rel="noreferrer" key={source.id}><strong>{source.title}</strong><small>{source.publisher || "来源待补充"} · {source.is_official ? "官方" : "非官方线索"}</small></a> : <div key={source.id}><strong>{source.title}</strong><small>{source.publisher || "来源待补充"}</small></div>) : <p>暂无可公开来源，条目仍待核验。</p>}</div><form className="feedback-form" onSubmit={submitFeedback}><h3>发现信息不准确？</h3><textarea minLength={5} required value={feedback} onChange={(e) => setFeedback(e.target.value)} placeholder="说明哪里不准确，最好附上可核验线索" /><button className="ghost-button" type="submit">提交纠错</button>{message && <small role="status">{message}</small>}</form></aside></div>}
    </section>
  );
}

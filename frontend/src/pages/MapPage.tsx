import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { AmapCanvas } from "../components/AmapCanvas";
import { EmptyState, Loading } from "../components/ProtectedRoute";
import { formatDate, StatusBadge } from "../components/StatusBadge";
import type { Campus, Location } from "../types";

const categories = [
  ["", "全部"], ["canteen", "饭堂"], ["teaching_building", "教学楼"], ["dormitory", "宿舍"],
  ["library", "图书馆"], ["express_station", "快递"], ["medical", "医务室"], ["supermarket", "超市"],
];

export default function MapPage() {
  const { user } = useAuth();
  const [searchParams] = useSearchParams();
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
  const [mapStatus, setMapStatus] = useState<{ provider: string; webservice_configured: boolean; security_proxy_configured: boolean } | null>(null);
  const [originId, setOriginId] = useState("");
  const [destinationId, setDestinationId] = useState("");
  const [route, setRoute] = useState<{ provider: string; distance_meters: number; duration_seconds: number; steps: { instruction: string }[]; polyline: number[][] } | null>(null);
  const [routeError, setRouteError] = useState("");
  const [routeBusy, setRouteBusy] = useState(false);

  useEffect(() => { api<Campus[]>("/campuses").then((rows) => { setCampuses(rows); setCampusId((current) => current || rows[0]?.id || ""); }).catch((reason) => { setError(reason instanceof Error ? reason.message : "校区加载失败"); setLoading(false); }); }, []);
  useEffect(() => { api<typeof mapStatus>("/map/status").then(setMapStatus).catch(() => setMapStatus(null)); }, []);
  useEffect(() => {
    if (!campusId) return;
    setLoading(true); setSelected(null); setError("");
    api<Location[]>(`/locations?campus_id=${encodeURIComponent(campusId)}`).then((rows) => {
      setLocations(rows);
      const requested = searchParams.get("location");
      if (requested) setSelected(rows.find((item) => item.id === requested) || null);
    }).catch((reason) => { setLocations([]); setError(reason instanceof Error ? reason.message : "地点加载失败"); }).finally(() => setLoading(false));
  }, [campusId, searchParams]);

  const filtered = useMemo(() => locations.filter((item) => {
    const haystack = [item.name, ...item.aliases, item.description, item.area, item.address].join(" ").toLowerCase();
    return (!category || item.category === category) && (!query || haystack.includes(query.toLowerCase()));
  }), [locations, category, query]);
  const campus = campuses.find((item) => item.id === campusId);
  const routable = locations.filter((item) => item.latitude != null && item.longitude != null && item.verification_status !== "needs_verification");
  const jsKeyConfigured = Boolean(String(import.meta.env.VITE_AMAP_JS_KEY || "").trim());
  const realMapEnabled = jsKeyConfigured && Boolean(mapStatus?.security_proxy_configured) && Boolean(mapStatus?.webservice_configured);
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
  const calculateRoute = async () => {
    const origin = locations.find((item) => item.id === originId);
    const destination = locations.find((item) => item.id === destinationId);
    if (!origin || !destination || origin.longitude == null || origin.latitude == null || destination.longitude == null || destination.latitude == null) {
      setRouteError("起点和终点都必须有经过核验的真实坐标");
      return;
    }
    setRouteBusy(true); setRouteError(""); setRoute(null);
    const params = new URLSearchParams({
      origin_longitude: String(origin.longitude), origin_latitude: String(origin.latitude),
      destination_longitude: String(destination.longitude), destination_latitude: String(destination.latitude),
    });
    try { setRoute(await api(`/map/walking-route?${params.toString()}`)); }
    catch (reason) { setRouteError(reason instanceof Error ? reason.message : "路线规划失败"); }
    finally { setRouteBusy(false); }
  };
  return (
    <section className="page section-wrap map-page">
      <div className="page-heading"><div><p className="eyebrow">校园地图</p><h1>先选校区，再找准确地点</h1><p>凭据齐全时加载高德真实道路底图；只有经过核验的 GPS 点位才能进入路线规划。</p></div><select aria-label="选择校区" value={campusId} onChange={(e) => setCampusId(e.target.value)}>{campuses.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></div>
      <div className="map-toolbar"><label className="search-box"><span>⌕</span><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索教学楼、饭堂、快递…" /></label><div className="filter-chips">{categories.map(([value, label]) => <button key={value} className={category === value ? "active" : ""} onClick={() => setCategory(value)}>{label}</button>)}</div></div>
      {error && <div className="error-banner" role="alert">{error}</div>}
      {campus && <div className="data-notice compact-notice"><strong>{campus.name}</strong><p>{campus.data_notice}</p></div>}
      {loading ? <Loading /> : <div className="map-layout">
        <div>
          {campus && realMapEnabled ? <AmapCanvas campus={campus} locations={filtered} selected={selected} route={route} onSelect={setSelected} /> : <div className="map-config-panel" role="status"><p className="eyebrow">真实地图未启用</p><h2>需要配置高德地图凭据</h2><p>地点文字查询仍可使用；当前不会用示意图冒充真实道路地图。</p><ul><li>前端：<code>VITE_AMAP_JS_KEY</code>（Web 端 JS API Key）</li><li>后端：<code>AMAP_WEBSERVICE_KEY</code></li><li>后端：<code>AMAP_SECURITY_CODE</code>（只由安全代理读取）</li></ul></div>}
          <div className="route-planner panel"><div className="panel-heading"><h2>步行路线</h2>{route && <span>{(route.distance_meters / 1000).toFixed(2)} km · 约 {Math.max(1, Math.round(route.duration_seconds / 60))} 分钟</span>}</div><div className="route-fields"><label>起点<select value={originId} onChange={(event) => setOriginId(event.target.value)}><option value="">选择有真实坐标的地点</option>{routable.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>终点<select value={destinationId} onChange={(event) => setDestinationId(event.target.value)}><option value="">选择有真实坐标的地点</option>{routable.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><button className="button compact" type="button" disabled={!realMapEnabled || routeBusy || !originId || !destinationId} onClick={() => void calculateRoute()}>{routeBusy ? "规划中…" : "规划步行路线"}</button></div>{!routable.length && <small>当前校区尚无经过核验的 GPS 点位，因此不能生成真实路线。</small>}{routeError && <p className="date-warning" role="alert">{routeError}</p>}{route?.steps.length ? <details><summary>查看路线步骤</summary><ol>{route.steps.map((step, index) => <li key={`${index}-${step.instruction}`}>{step.instruction}</li>)}</ol></details> : null}</div>
        </div>
        <aside className="location-list"><div className="panel-heading"><h2>地点列表</h2><span>{filtered.length} 条</span></div>{filtered.length ? filtered.map((item) => <button className={selected?.id === item.id ? "location-row active" : "location-row"} key={item.id} onClick={() => setSelected(item)}><span className={`category-icon category-${item.category}`}>{item.category === "canteen" ? "食" : "⌖"}</span><div><strong>{item.name}</strong><small>{item.area || item.address || "位置待核验"}</small></div><StatusBadge value={item.verification_status} /></button>) : <EmptyState title="没有匹配地点" detail="换个关键词或切换分类试试。" />}</aside>
      </div>}
      {selected && <div className="drawer-backdrop" onClick={() => setSelected(null)}><aside className="detail-drawer" onClick={(e) => e.stopPropagation()} aria-label="地点详情"><button className="drawer-close" onClick={() => setSelected(null)} aria-label="关闭">×</button><p className="eyebrow">地点详情</p><h2>{selected.name}</h2><div className="badge-row"><StatusBadge value={selected.verification_status} /><StatusBadge value={selected.freshness_status} /><span className={`status-badge status-${selected.data_status}`}>{selected.data_status === "historical" ? "历史资料" : selected.data_status === "current" ? "当前资料" : "待核验"}</span></div>{selected.data_status === "historical" && <p className="date-warning">这是历史资料，位置或服务可能已经变化，请通过来源或校方电话再次确认。</p>}<dl><dt>区域</dt><dd>{selected.area || "待核验"}</dd><dt>详细位置</dt><dd>{[selected.address, selected.floor].filter(Boolean).join(" · ") || "待核验"}</dd><dt>别名</dt><dd>{selected.aliases.join("、") || "无"}</dd><dt>开放时间</dt><dd>{selected.opening_hours || "待核验"}</dd><dt>可办服务</dt><dd>{selected.services.join("、") || "待核验"}</dd><dt>资料核验</dt><dd>{formatDate(selected.verified_at)}</dd><dt>数据更新</dt><dd>{formatDate(selected.updated_at)}</dd><dt>可信度</dt><dd>{Math.round(selected.confidence * 100)}%</dd></dl><p>{selected.description || "暂无说明"}</p><a className="button full" href={navigationUrl} target="_blank" rel="noreferrer">打开外部地图查询</a><div className="source-list"><h3>数据来源</h3>{selected.sources.length ? selected.sources.map((source) => source.url ? <a href={source.url} target="_blank" rel="noreferrer" key={source.id}><strong>{source.title}</strong><small>{source.publisher || "来源待补充"} · {source.is_official ? "官方" : "非官方线索"}</small></a> : <div key={source.id}><strong>{source.title}</strong><small>{source.publisher || "来源待补充"}</small></div>) : <p>暂无可公开来源，条目仍待核验。</p>}</div><form className="feedback-form" onSubmit={submitFeedback}><h3>发现信息不准确？</h3><textarea minLength={5} required value={feedback} onChange={(e) => setFeedback(e.target.value)} placeholder="说明哪里不准确，最好附上可核验线索" /><button className="ghost-button" type="submit">提交纠错</button>{message && <small role="status">{message}</small>}</form></aside></div>}
    </section>
  );
}

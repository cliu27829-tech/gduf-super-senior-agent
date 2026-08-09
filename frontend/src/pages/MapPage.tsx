import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { AmapCanvas, type MapRoute, type MapRouteRequest } from "../components/AmapCanvas";
import { EmptyState, Loading } from "../components/ProtectedRoute";
import { formatDate, StatusBadge } from "../components/StatusBadge";
import { LocationPermissionSheet, locationAccuracy, useGeolocation, type BrowserLocation } from "../location";
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
  const [originAddress, setOriginAddress] = useState("");
  const [destinationAddress, setDestinationAddress] = useState("");
  const [route, setRoute] = useState<MapRoute | null>(null);
  const [routeRequest, setRouteRequest] = useState<MapRouteRequest | null>(null);
  const [routeError, setRouteError] = useState("");
  const [routeBusy, setRouteBusy] = useState(false);
  const [locationSheetOpen, setLocationSheetOpen] = useState(false);
  const geolocation = useGeolocation();

  useEffect(() => { api<Campus[]>("/campuses").then((rows) => { setCampuses(rows); setCampusId((current) => current || rows[0]?.id || ""); }).catch((reason) => { setError(reason instanceof Error ? reason.message : "校区加载失败"); setLoading(false); }); }, []);
  useEffect(() => { api<typeof mapStatus>("/map/status").then(setMapStatus).catch(() => setMapStatus(null)); }, []);
  useEffect(() => {
    if (!campusId) return;
    setLoading(true); setSelected(null); setError("");
    api<Location[]>(`/locations?campus_id=${encodeURIComponent(campusId)}`).then((rows) => {
      setLocations(rows);
      const requested = searchParams.get("location");
      if (requested) setSelected(rows.find((item) => item.id === requested) || null);
      const requestedDestination = searchParams.get("destination");
      if (requestedDestination) {
        const destination = rows.find((item) => item.id === requestedDestination) || null;
        setSelected(destination);
        setDestinationId(destination?.id || "");
      }
    }).catch((reason) => { setLocations([]); setError(reason instanceof Error ? reason.message : "地点加载失败"); }).finally(() => setLoading(false));
  }, [campusId, searchParams]);

  const filtered = useMemo(() => locations.filter((item) => {
    const haystack = [item.name, ...item.aliases, item.description, item.area, item.address].join(" ").toLowerCase();
    return (!category || item.category === category) && (!query || haystack.includes(query.toLowerCase()));
  }), [locations, category, query]);
  const campus = campuses.find((item) => item.id === campusId);
  const routable = locations.filter((item) => item.latitude != null && item.longitude != null && item.coordinate_accuracy === "exact" && Boolean(item.coordinate_verified_at));
  const jsKeyConfigured = Boolean(String(import.meta.env.VITE_AMAP_JS_KEY || "").trim());
  const realMapEnabled = jsKeyConfigured && Boolean(mapStatus?.security_proxy_configured);
  useEffect(() => {
    if (campus) setOriginAddress(`${campus.name} ${campus.address}`.trim());
  }, [campus]);
  const canNavigateSelected = Boolean(selected && selected.latitude != null && selected.longitude != null && selected.coordinate_accuracy === "exact" && selected.coordinate_verified_at);
  const navigationUrl = selected ? (canNavigateSelected
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
    try {
      if (mapStatus?.webservice_configured) {
        setRoute(await api(`/map/walking-route?${params.toString()}`));
        setRouteBusy(false);
      } else {
        setRouteRequest({
          id: Date.now(),
          origin: [origin.longitude, origin.latitude],
          destination: [destination.longitude, destination.latitude],
        });
      }
    }
    catch (reason) { setRouteError(reason instanceof Error ? reason.message : "路线规划失败"); }
  };
  const calculateCurrentRoute = async (position: BrowserLocation, destinationLocationId: string) => {
    const accuracy = locationAccuracy(position.accuracy);
    if (accuracy.status === "low") {
      setRouteError(accuracy.message);
      setLocationSheetOpen(true);
      return;
    }
    const destination = locations.find((item) => item.id === destinationLocationId);
    if (!destination || destination.longitude == null || destination.latitude == null || destination.coordinate_accuracy !== "exact" || !destination.coordinate_verified_at) {
      setRouteError("这个目的地尚无经过核验的精确坐标，不能直接导航。你可以选择其他起点或提交纠错线索。");
      return;
    }
    setDestinationId(destination.id);
    setSelected(destination);
    setRouteBusy(true);
    setRouteError("");
    setRoute(null);
    if (mapStatus?.webservice_configured) {
      try {
        const result = await api<MapRoute>("/map/route-from-current", {
          method: "POST",
          body: JSON.stringify({ origin: position, destination_location_id: destination.id, mode: "walking" }),
          timeoutMs: 20_000,
        });
        setRoute(result);
        setRouteBusy(false);
        return;
      } catch (reason) {
        setRouteError(reason instanceof Error ? `${reason.message}，正在尝试浏览器高德路线。` : "后端路线不可用，正在尝试浏览器高德路线。");
      }
    }
    if (!realMapEnabled) {
      setRouteBusy(false);
      setRouteError("真实地图尚未配置，不能生成路线。系统不会用直线距离冒充步行路线。");
      return;
    }
    setRouteRequest({
      id: Date.now(),
      origin: [position.longitude, position.latitude],
      destination: [destination.longitude, destination.latitude],
    });
  };

  const requestCurrentPosition = (destinationLocationId?: string) => {
    if (destinationLocationId) setDestinationId(destinationLocationId);
    setLocationSheetOpen(true);
  };

  const allowCurrentPosition = async () => {
    try {
      const position = await geolocation.locate();
      const accuracy = locationAccuracy(position.accuracy);
      if (accuracy.status === "low") {
        setRouteError(accuracy.message);
        return;
      }
      setLocationSheetOpen(false);
      if (destinationId || selected?.id) await calculateCurrentRoute(position, destinationId || selected!.id);
    } catch (reason) {
      setRouteError(reason instanceof Error ? reason.message : "定位失败，请选择其他起点");
    }
  };

  const chooseManualOrigin = () => {
    setLocationSheetOpen(false);
    setRouteError("没事，也可以从下面选择一个经过核验的校园地点作为起点。");
    window.setTimeout(() => document.getElementById("manual-route")?.scrollIntoView({ behavior: "smooth", block: "center" }), 0);
  };

  useEffect(() => {
    const requestedDestination = searchParams.get("destination");
    if (!requestedDestination || !locations.length || searchParams.get("use_current") !== "1") return;
    if (geolocation.location) void calculateCurrentRoute(geolocation.location, requestedDestination);
    else setLocationSheetOpen(true);
  }, [locations, searchParams]);
  const calculateAddressRoute = () => {
    if (!originAddress.trim() || !destinationAddress.trim()) {
      setRouteError("请填写完整的起点和终点地址");
      return;
    }
    setRouteBusy(true); setRouteError(""); setRoute(null);
    setRouteRequest({
      id: Date.now(),
      originAddress: originAddress.trim(),
      destinationAddress: destinationAddress.trim(),
    });
  };
  const routeCalculated = (result: MapRoute) => {
    setRoute(result);
    setRouteRequest(null);
    setRouteBusy(false);
  };
  const jsRouteFailed = (detail: string) => {
    setRouteError(detail);
    setRouteRequest(null);
    setRouteBusy(false);
  };
  return (
    <section className="page section-wrap map-page">
      <div className="page-heading"><div><p className="eyebrow">校园地图</p><h1>先选校区，再找准确地点</h1><p>使用高德真实道路底图；校区中心由官方地址地理编码，其他地点只有经过核验的 GPS 点位才进入路线规划。</p></div><select aria-label="选择校区" value={campusId} onChange={(e) => setCampusId(e.target.value)}>{campuses.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></div>
      <div className="map-toolbar"><label className="search-box"><span>⌕</span><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索北教、北饭、图书馆…" /></label><button className="ghost-button map-my-location" type="button" onClick={() => requestCurrentPosition()}>⌖ 我的位置</button><div className="filter-chips">{categories.map(([value, label]) => <button key={value} className={category === value ? "active" : ""} onClick={() => setCategory(value)}>{label}</button>)}</div></div>
      {geolocation.location && <div className={`location-accuracy accuracy-${locationAccuracy(geolocation.location.accuracy).status}`} role="status"><span>⌖</span><strong>{locationAccuracy(geolocation.location.accuracy).message}</strong><small>仅保留在当前页面会话，刷新后会清除。</small></div>}
      {error && <div className="error-banner" role="alert">{error}</div>}
      {campus && <div className="data-notice compact-notice"><strong>{campus.name}</strong><p>{campus.data_notice}</p></div>}
      {loading ? <Loading /> : <div className="map-layout">
        <div>
          {campus && realMapEnabled ? <AmapCanvas campus={campus} locations={filtered} selected={selected} currentLocation={geolocation.location} route={route} routeRequest={routeRequest} onRouteCalculated={routeCalculated} onRouteError={jsRouteFailed} onSelect={setSelected} /> : <div className="map-config-panel" role="status"><p className="eyebrow">真实地图未启用</p><h2>需要配置高德地图凭据</h2><p>地点文字查询仍可使用；当前不会用示意图冒充真实道路地图。</p><ul><li>前端：<code>VITE_AMAP_JS_KEY</code>（Web 端 JS API Key）</li><li>后端：<code>AMAP_SECURITY_CODE</code>（只由安全代理读取）</li><li>可选增强：<code>AMAP_WEBSERVICE_KEY</code></li></ul></div>}
        <div className="route-planner panel" id="manual-route"><div className="panel-heading"><h2>步行路线</h2>{route && <span>{(route.distance_meters / 1000).toFixed(2)} km · 约 {Math.max(1, Math.round(route.duration_seconds / 60))} 分钟</span>}</div>{routable.length >= 2 ? <div className="route-fields"><label>起点<select value={originId} onChange={(event) => setOriginId(event.target.value)}><option value="">选择有真实坐标的地点</option>{routable.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>终点<select value={destinationId} onChange={(event) => setDestinationId(event.target.value)}><option value="">选择有真实坐标的地点</option>{routable.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><button className="button compact" type="button" disabled={!realMapEnabled || routeBusy || !originId || !destinationId} onClick={() => void calculateRoute()}>{routeBusy ? "规划中…" : "规划步行路线"}</button></div> : <div className="route-fields route-address-fields"><label>起点地址<input aria-label="路线起点地址" value={originAddress} onChange={(event) => setOriginAddress(event.target.value)} /></label><label>终点地址<input aria-label="路线终点地址" value={destinationAddress} onChange={(event) => setDestinationAddress(event.target.value)} placeholder="输入城市和详细地址" /></label><button className="button compact" type="button" disabled={!realMapEnabled || routeBusy || !originAddress.trim() || !destinationAddress.trim()} onClick={calculateAddressRoute}>{routeBusy ? "规划中…" : "规划步行路线"}</button></div>}{!mapStatus?.webservice_configured && realMapEnabled && <small>后端 WebService 未配置，地址解析和路线将使用高德浏览器 JS API。</small>}{routable.length < 2 && <small>当前校区缺少两个核验 GPS 点位；可输入地址，由高德实时地理编码后规划，不会写入未核验坐标。</small>}{routeError && <p className="date-warning" role="alert">{routeError}</p>}{route?.steps.length ? <details><summary>查看路线步骤</summary><ol>{route.steps.map((step, index) => <li key={`${index}-${step.instruction}`}>{step.instruction}</li>)}</ol></details> : null}</div>
        </div>
        <aside className="location-list"><div className="panel-heading"><h2>地点列表</h2><span>{filtered.length} 条</span></div>{filtered.length ? filtered.map((item) => <button className={selected?.id === item.id ? "location-row active" : "location-row"} key={item.id} onClick={() => setSelected(item)}><span className={`category-icon category-${item.category}`}>{item.category === "canteen" ? "食" : "⌖"}</span><div><strong>{item.name}</strong><small>{item.area || item.address || "位置待核验"}</small></div><StatusBadge value={item.verification_status} /></button>) : <EmptyState title="没有匹配地点" detail="换个关键词或切换分类试试。" />}</aside>
      </div>}
      {selected && <div className="drawer-backdrop" onClick={() => setSelected(null)}><aside className="detail-drawer map-bottom-sheet" onClick={(e) => e.stopPropagation()} aria-label="地点详情"><button className="drawer-close" onClick={() => setSelected(null)} aria-label="关闭">×</button><p className="eyebrow">地点详情</p><h2>{selected.name}</h2><div className="badge-row"><StatusBadge value={selected.verification_status} /><StatusBadge value={selected.freshness_status} /><span className={`status-badge status-${selected.data_status}`}>{selected.data_status === "historical" ? "历史资料" : selected.verification_status === "verified" ? "已核验" : "待核验"}</span></div>{selected.data_status === "historical" && <p className="date-warning">这是历史资料，位置或服务可能已经变化，请通过来源或校方电话再次确认。</p>}<dl><dt>区域</dt><dd>{selected.area || "待核验"}</dd><dt>详细位置</dt><dd>{[selected.address, selected.floor].filter(Boolean).join(" · ") || "待核验"}</dd><dt>位置状态</dt><dd>{selected.coordinate_accuracy === "exact" ? "精确点位" : selected.coordinate_accuracy === "approximate" ? "区域近似点" : "无可信坐标"}</dd><dt>信息来源</dt><dd>{selected.coordinate_source === "amap_verified" ? "高德地图核验" : selected.coordinate_source || "待补充"}</dd><dt>别名</dt><dd>{selected.aliases.join("、") || "无"}</dd><dt>开放时间</dt><dd>{selected.opening_hours || "待核验"}</dd><dt>可办服务</dt><dd>{selected.services.join("、") || "待核验"}</dd><dt>资料核验</dt><dd>{formatDate(selected.verified_at)}</dd><dt>位置确认</dt><dd>{formatDate(selected.coordinate_verified_at)}</dd></dl><p>{selected.description || "暂无说明"}</p><div className="location-actions"><button className="button full" disabled={!canNavigateSelected} onClick={() => requestCurrentPosition(selected.id)}>⌖ 从我这里去</button>{canNavigateSelected ? <a className="ghost-button full" href={navigationUrl} target="_blank" rel="noreferrer">在高德打开</a> : <a className="ghost-button full" href={navigationUrl} target="_blank" rel="noreferrer">仅搜索地点（点位待核验）</a>}</div><div className="source-list"><h3>数据来源</h3>{selected.sources.length ? selected.sources.map((source) => source.url ? <a href={source.url} target="_blank" rel="noreferrer" key={source.id}><strong>{source.title}</strong><small>{source.publisher || "来源待补充"} · {source.is_official ? "校方来源" : "地图数据来源"}</small></a> : <div key={source.id}><strong>{source.title}</strong><small>{source.publisher || "来源待补充"}</small></div>) : <p>暂无可公开来源，条目仍待核验。</p>}</div><form className="feedback-form" onSubmit={submitFeedback}><h3>发现信息不准确？</h3><textarea minLength={5} required value={feedback} onChange={(event) => setFeedback(event.target.value)} placeholder="说明哪里不准确，最好附上可核验线索" /><button className="ghost-button" type="submit">提交纠错</button>{message && <small role="status">{message}</small>}</form></aside></div>}
      <LocationPermissionSheet open={locationSheetOpen} destinationName={selected?.name} locating={geolocation.locating || routeBusy} onAllow={() => void allowCurrentPosition()} onManual={chooseManualOrigin} onClose={() => setLocationSheetOpen(false)} />
    </section>
  );
}

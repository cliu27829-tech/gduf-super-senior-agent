import AMapLoader from "@amap/amap-jsapi-loader";
import { useEffect, useRef, useState } from "react";
import { api, API_BASE_URL } from "../api";
import type { Location } from "../types";

type Point = { lng: number; lat: number };
type Overlay = { setPosition: (point: [number, number]) => void; getPosition: () => Point; on: (name: string, callback: () => void) => void };
type MapInstance = {
  add: (item: Overlay) => void;
  destroy: () => void;
  on: (name: string, callback: (event: { lnglat: Point }) => void) => void;
  setCenter: (point: [number, number]) => void;
  setZoom: (zoom: number) => void;
  setLayers: (layers: unknown[]) => void;
};
type Namespace = {
  Map: new (node: HTMLElement, options: Record<string, unknown>) => MapInstance;
  Marker: new (options: Record<string, unknown>) => Overlay;
  TileLayer: (new () => unknown) & { Satellite: new () => unknown };
  PlaceSearch: new (options: Record<string, unknown>) => {
    search: (query: string, callback: (status: string, result: { poiList?: { pois?: { id?: string; name?: string; location?: Point; address?: string }[] } }) => void) => void;
  };
  plugin: (names: string[], callback: () => void) => void;
};

export function AmapCalibrator({ location, onSaved }: { location: Location | null; onSaved: () => Promise<unknown> }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapInstance | null>(null);
  const markerRef = useRef<Overlay | null>(null);
  const amapRef = useRef<Namespace | null>(null);
  const [latitude, setLatitude] = useState("");
  const [longitude, setLongitude] = useState("");
  const [accuracy, setAccuracy] = useState<"exact" | "approximate" | "area_only">("exact");
  const [source, setSource] = useState("AMap admin calibration");
  const [evidence, setEvidence] = useState("");
  const [note, setNote] = useState("");
  const [poiId, setPoiId] = useState("");
  const [query, setQuery] = useState("");
  const [message, setMessage] = useState("");
  const [satellite, setSatellite] = useState(false);
  const jsKey = String(import.meta.env.VITE_AMAP_JS_KEY || "").trim();

  const applyPoint = (point: Point) => {
    setLongitude(point.lng.toFixed(6));
    setLatitude(point.lat.toFixed(6));
    markerRef.current?.setPosition([point.lng, point.lat]);
  };

  useEffect(() => {
    if (!containerRef.current || !jsKey) return;
    let disposed = false;
    window._AMapSecurityConfig = { serviceHost: `${API_BASE_URL || window.location.origin}/api/map/_AMapService` };
    void AMapLoader.load({ key: jsKey, version: "2.0", plugins: [] }).then((loaded: unknown) => {
      if (disposed || !containerRef.current) return;
      const AMap = loaded as Namespace;
      amapRef.current = AMap;
      const map = new AMap.Map(containerRef.current, { zoom: 17, viewMode: "2D" });
      mapRef.current = map;
      const marker = new AMap.Marker({ draggable: true, position: [113.380696, 23.202551] });
      marker.on("dragend", () => applyPoint(marker.getPosition()));
      markerRef.current = marker;
      map.add(marker);
      map.on("click", (event) => applyPoint(event.lnglat));
    }).catch(() => setMessage("高德地图加载失败，请检查 JS Key、白名单和安全代理。"));
    return () => { disposed = true; mapRef.current?.destroy(); mapRef.current = null; markerRef.current = null; };
  }, [jsKey]);

  useEffect(() => {
    if (!location) return;
    setLatitude(location.latitude == null ? "" : String(location.latitude));
    setLongitude(location.longitude == null ? "" : String(location.longitude));
    setAccuracy(location.coordinate_accuracy === "unknown" ? "exact" : location.coordinate_accuracy);
    setSource(location.coordinate_source || "AMap admin calibration");
    setNote(location.coordinate_note || "");
    setPoiId(location.amap_poi_id || "");
    setEvidence("");
    if (location.longitude != null && location.latitude != null) {
      const point: [number, number] = [location.longitude, location.latitude];
      markerRef.current?.setPosition(point);
      mapRef.current?.setCenter(point);
      mapRef.current?.setZoom(18);
    }
  }, [location]);

  const search = () => {
    const AMap = amapRef.current;
    if (!AMap || !query.trim()) return;
    AMap.plugin(["AMap.PlaceSearch"], () => {
      new AMap.PlaceSearch({ pageSize: 10, citylimit: false }).search(query.trim(), (status, result) => {
        const poi = result.poiList?.pois?.[0];
        if (status !== "complete" || !poi?.location) return setMessage("没有找到匹配 POI，请换用完整名称搜索。");
        applyPoint(poi.location);
        mapRef.current?.setCenter([poi.location.lng, poi.location.lat]);
        setPoiId(poi.id || "");
        setEvidence(`高德 POI：${poi.name || query}${poi.address ? `；${poi.address}` : ""}`);
        setNote(`管理员通过高德 POI 搜索并在地图中复核：${poi.name || query}`);
        setMessage("已定位首个 POI，请切换卫星图并拖动标记复核入口。");
      });
    });
  };

  const toggleLayer = () => {
    const AMap = amapRef.current;
    const map = mapRef.current;
    if (!AMap || !map) return;
    const next = !satellite;
    setSatellite(next);
    map.setLayers(next ? [new AMap.TileLayer.Satellite()] : [new AMap.TileLayer()]);
  };

  const save = async () => {
    if (!location) return setMessage("请先从上方选择一个地点。");
    if (!latitude || !longitude || !evidence.trim()) return setMessage("请点选坐标，并填写可追溯核验依据。");
    setMessage("正在保存…");
    try {
      await api(`/admin/locations/${location.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          latitude: Number(latitude), longitude: Number(longitude), coordinate_accuracy: accuracy,
          coordinate_source: source, coordinate_note: note, amap_poi_id: poiId,
          verification_status: accuracy === "area_only" ? "needs_verification" : "verified",
          verification_method: "admin_map_calibration", data_status: accuracy === "area_only" ? "needs_verification" : "admin_verified",
          confidence: accuracy === "exact" ? 0.95 : accuracy === "approximate" ? 0.8 : 0.5,
          evidence, verification_note: note,
        }),
      });
      await onSaved();
      setMessage("坐标、精度、来源和审计记录已保存。");
    } catch (reason) { setMessage(reason instanceof Error ? reason.message : "保存失败"); }
  };

  if (!jsKey) return <div className="data-notice"><strong>地图校准未启用</strong><p>请先配置前端 VITE_AMAP_JS_KEY；密钥不会由此表单写入数据库。</p></div>;
  return <section className="panel amap-calibrator"><div className="panel-heading"><div><p className="eyebrow">管理员坐标校准</p><h2>{location ? `校准：${location.name}` : "先选择待校准地点"}</h2></div><button type="button" className="ghost-button compact" onClick={toggleLayer}>{satellite ? "普通地图" : "卫星图"}</button></div>
    <div className="calibrator-search"><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索完整 POI 名称" /><button type="button" onClick={search}>搜索 POI</button></div>
    <div ref={containerRef} className="calibrator-map" aria-label="管理员高德地图点位校准" />
    <div className="form-grid"><label>纬度<input type="number" step="0.000001" value={latitude} onChange={(event) => setLatitude(event.target.value)} /></label><label>经度<input type="number" step="0.000001" value={longitude} onChange={(event) => setLongitude(event.target.value)} /></label>
      <label>坐标精度<select value={accuracy} onChange={(event) => setAccuracy(event.target.value as typeof accuracy)}><option value="exact">精确入口/建筑</option><option value="approximate">区域近似点</option><option value="area_only">仅确认区域</option></select></label><label>高德 POI ID<input value={poiId} onChange={(event) => setPoiId(event.target.value)} /></label>
      <label className="span-two">坐标来源<input value={source} onChange={(event) => setSource(event.target.value)} /></label><label className="span-two">核验依据<input required value={evidence} onChange={(event) => setEvidence(event.target.value)} placeholder="POI 名称、地址、现场照片或来源 URL" /></label><label className="span-two">核验备注<textarea value={note} onChange={(event) => setNote(event.target.value)} /></label>
    </div><button type="button" className="button" onClick={() => void save()} disabled={!location}>保存校准结果</button>{message && <p role="status">{message}</p>}
  </section>;
}

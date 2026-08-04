import AMapLoader from "@amap/amap-jsapi-loader";
import { useEffect, useRef, useState } from "react";
import { API_BASE_URL, api } from "../api";
import type { Campus, Location } from "../types";

type AMapNamespace = {
  Map: new (container: HTMLElement, options: Record<string, unknown>) => AMapInstance;
  Marker: new (options: Record<string, unknown>) => AMapOverlay;
  Polyline: new (options: Record<string, unknown>) => AMapOverlay;
  Geolocation: new (options: Record<string, unknown>) => { getCurrentPosition: () => void; on: (name: string, callback: (event: { position?: { lng: number; lat: number } }) => void) => void };
  plugin: (names: string[], callback: () => void) => void;
};
type AMapOverlay = { on?: (name: string, callback: () => void) => void };
type AMapInstance = {
  add: (overlay: AMapOverlay | AMapOverlay[]) => void;
  destroy: () => void;
  setCenter: (point: [number, number]) => void;
  setFitView: (overlays?: AMapOverlay[]) => void;
};

declare global {
  interface Window {
    _AMapSecurityConfig?: { serviceHost: string };
  }
}

type Route = { polyline: number[][]; distance_meters: number; duration_seconds: number } | null;

export function AmapCanvas({
  campus,
  locations,
  selected,
  route,
  onSelect,
}: {
  campus: Campus;
  locations: Location[];
  selected: Location | null;
  route: Route;
  onSelect: (location: Location) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<AMapInstance | null>(null);
  const amapRef = useRef<AMapNamespace | null>(null);
  const [error, setError] = useState("");
  const jsKey = String(import.meta.env.VITE_AMAP_JS_KEY || "").trim();

  useEffect(() => {
    if (!containerRef.current || !jsKey) return;
    let disposed = false;
    window._AMapSecurityConfig = {
      serviceHost: `${API_BASE_URL || window.location.origin}/api/map/_AMapService`,
    };
    AMapLoader.load({ key: jsKey, version: "2.0", plugins: [] })
      .then(async (loaded: unknown) => {
        if (disposed || !containerRef.current) return;
        const AMap = loaded as unknown as AMapNamespace;
        amapRef.current = AMap;
        const map = new AMap.Map(containerRef.current, { zoom: 16, viewMode: "2D" });
        mapRef.current = map;
        try {
          const point = await api<{ longitude: number; latitude: number }>(
            `/map/geocode?address=${encodeURIComponent(campus.address)}&city=${encodeURIComponent(campus.name.includes("肇庆") ? "肇庆" : campus.name.includes("清远") ? "清远" : "广州")}`,
          );
          if (!disposed) map.setCenter([point.longitude, point.latitude]);
        } catch (reason) {
          if (!disposed) setError(reason instanceof Error ? reason.message : "校区中心定位失败");
        }
      })
      .catch(() => { if (!disposed) setError("高德地图加载失败，请检查 JS Key、域名白名单和后端安全代理配置"); });
    return () => {
      disposed = true;
      mapRef.current?.destroy();
      mapRef.current = null;
      amapRef.current = null;
    };
  }, [campus.id, campus.address, campus.name, jsKey]);

  useEffect(() => {
    const map = mapRef.current;
    const AMap = amapRef.current;
    if (!map || !AMap) return;
    const markers = locations
      .filter((item) => item.longitude != null && item.latitude != null && item.verification_status !== "needs_verification")
      .map((item) => {
        const marker = new AMap.Marker({
          position: [item.longitude!, item.latitude!],
          title: item.name,
          label: { content: item.name, direction: "top" },
        });
        marker.on?.("click", () => onSelect(item));
        return marker;
      });
    if (markers.length) {
      map.add(markers);
      map.setFitView(markers);
    }
  }, [locations, onSelect]);

  useEffect(() => {
    const map = mapRef.current;
    const AMap = amapRef.current;
    if (!map || !AMap || !route?.polyline.length) return;
    const line = new AMap.Polyline({
      path: route.polyline,
      strokeColor: "#1677ff",
      strokeWeight: 7,
      strokeOpacity: 0.85,
      lineJoin: "round",
    });
    map.add(line);
    map.setFitView([line]);
  }, [route]);

  useEffect(() => {
    if (selected?.longitude != null && selected.latitude != null) {
      mapRef.current?.setCenter([selected.longitude, selected.latitude]);
    }
  }, [selected]);

  const locate = () => {
    const AMap = amapRef.current;
    const map = mapRef.current;
    if (!AMap || !map) return;
    AMap.plugin(["AMap.Geolocation"], () => {
      const geolocation = new AMap.Geolocation({ enableHighAccuracy: true, timeout: 10000 });
      geolocation.on("complete", (event) => {
        if (event.position) map.setCenter([event.position.lng, event.position.lat]);
      });
      geolocation.on("error", () => setError("浏览器定位失败，请检查定位权限"));
      geolocation.getCurrentPosition();
    });
  };

  return (
    <div className="real-map-shell">
      <div ref={containerRef} className="real-map" aria-label={`${campus.name}高德真实道路地图`} />
      <button className="ghost-button compact map-locate" type="button" onClick={locate}>定位我</button>
      {error && <div className="map-inline-error" role="alert">{error}</div>}
    </div>
  );
}

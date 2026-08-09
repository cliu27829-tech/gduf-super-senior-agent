import AMapLoader from "@amap/amap-jsapi-loader";
import { useEffect, useRef, useState } from "react";
import { API_BASE_URL } from "../api";
import type { Campus, Location } from "../types";
import type { BrowserLocation } from "../location";

type AMapNamespace = {
  Map: new (container: HTMLElement, options: Record<string, unknown>) => AMapInstance;
  Marker: new (options: Record<string, unknown>) => AMapOverlay;
  Polyline: new (options: Record<string, unknown>) => AMapOverlay;
  Circle: new (options: Record<string, unknown>) => AMapOverlay;
  Geocoder: new (options: Record<string, unknown>) => {
    getLocation: (address: string, callback: (status: string, result: GeocodeResult) => void) => void;
  };
  Walking: new (options?: Record<string, unknown>) => {
    search: (origin: [number, number], destination: [number, number], callback: (status: string, result: WalkingResult) => void) => void;
  };
  plugin: (names: string[], callback: () => void) => void;
};
type AMapOverlay = { on?: (name: string, callback: () => void) => void };
type AMapInstance = {
  add: (overlay: AMapOverlay | AMapOverlay[]) => void;
  remove: (overlay: AMapOverlay | AMapOverlay[]) => void;
  destroy: () => void;
  setCenter: (point: [number, number]) => void;
  setFitView: (overlays?: AMapOverlay[]) => void;
};
type GeocodeResult = { geocodes?: { location?: { lng: number; lat: number } }[] };
type WalkingResult = {
  routes?: {
    distance?: number;
    time?: number;
    steps?: { instruction?: string; path?: { lng: number; lat: number }[] }[];
  }[];
};

declare global {
  interface Window {
    _AMapSecurityConfig?: { serviceHost: string };
  }
}

export type MapRoute = { polyline: number[][]; distance_meters: number; duration_seconds: number; steps: { instruction: string }[] };
export type MapRouteRequest = {
  id: number;
  origin?: [number, number];
  destination?: [number, number];
  originAddress?: string;
  destinationAddress?: string;
};

export function AmapCanvas({
  campus,
  locations,
  selected,
  currentLocation,
  route,
  routeRequest,
  onRouteCalculated,
  onRouteError,
  onSelect,
}: {
  campus: Campus;
  locations: Location[];
  selected: Location | null;
  currentLocation: BrowserLocation | null;
  route: MapRoute | null;
  routeRequest: MapRouteRequest | null;
  onRouteCalculated: (route: MapRoute) => void;
  onRouteError: (message: string) => void;
  onSelect: (location: Location) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<AMapInstance | null>(null);
  const amapRef = useRef<AMapNamespace | null>(null);
  const markerOverlaysRef = useRef<AMapOverlay[]>([]);
  const routeOverlayRef = useRef<AMapOverlay | null>(null);
  const currentLocationOverlaysRef = useRef<AMapOverlay[]>([]);
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);
  const jsKey = String(import.meta.env.VITE_AMAP_JS_KEY || "").trim();

  useEffect(() => {
    if (!containerRef.current || !jsKey) return;
    let disposed = false;
    window._AMapSecurityConfig = {
      serviceHost: `${API_BASE_URL || window.location.origin}/api/map/_AMapService`,
    };
    const loadTimeout = window.setTimeout(() => {
      if (!disposed && !mapRef.current) setError("高德地图加载超时，请检查网络后刷新页面重试");
    }, 20_000);
    AMapLoader.load({ key: jsKey, version: "2.0", plugins: [] })
      .then((loadedNamespace: unknown) => {
        if (disposed || !containerRef.current) return;
        const AMap = loadedNamespace as unknown as AMapNamespace;
        amapRef.current = AMap;
        const map = new AMap.Map(containerRef.current, { zoom: 16, viewMode: "2D" });
        mapRef.current = map;
        setLoaded(true);
      })
      .catch(() => { if (!disposed) setError("高德地图加载失败，请检查 JS Key、域名白名单和后端安全代理配置"); })
      .finally(() => window.clearTimeout(loadTimeout));
    return () => {
      disposed = true;
      window.clearTimeout(loadTimeout);
      setLoaded(false);
      mapRef.current?.destroy();
      mapRef.current = null;
      amapRef.current = null;
    };
  }, [campus.id, jsKey]);

  useEffect(() => {
    const map = mapRef.current;
    const AMap = amapRef.current;
    if (!map || !AMap || !loaded) return;
    if (markerOverlaysRef.current.length) map.remove(markerOverlaysRef.current);
    const markers = locations
      .filter((item) => item.longitude != null && item.latitude != null && ["exact", "approximate"].includes(item.coordinate_accuracy) && Boolean(item.coordinate_verified_at))
      .map((item) => {
        const marker = new AMap.Marker({
          position: [item.longitude!, item.latitude!],
          title: item.name,
          label: { content: item.name, direction: "top" },
        });
        marker.on?.("click", () => onSelect(item));
        return marker;
      });
    const campusAnchor = locations.find((item) => item.name === campus.name && item.address && (item.longitude == null || item.latitude == null));
    const finish = (overlays: AMapOverlay[]) => {
      markerOverlaysRef.current = overlays;
      if (overlays.length) {
        map.add(overlays);
        map.setFitView(overlays);
      }
    };
    if (campusAnchor) {
      AMap.plugin(["AMap.Geocoder"], () => {
        const city = campus.name.includes("肇庆") ? "肇庆" : campus.name.includes("清远") ? "清远" : "广州";
        const geocoder = new AMap.Geocoder({ city });
        geocoder.getLocation(`${campus.name} ${campus.address}`, (status, result) => {
          const point = result.geocodes?.[0]?.location;
          if (status !== "complete" || !point) {
            finish(markers);
            setError("高德未能定位当前校区，请检查地址数据或 Key 配置");
            return;
          }
          map.setCenter([point.lng, point.lat]);
          const campusMarker = new AMap.Marker({
            position: [point.lng, point.lat], title: campusAnchor.name,
            label: { content: campusAnchor.name, direction: "top" },
          });
          campusMarker.on?.("click", () => onSelect(campusAnchor));
          finish([...markers, campusMarker]);
        });
      });
      return;
    }
    if (markers.length) {
      finish(markers);
    }
  }, [campus.address, campus.name, loaded, locations, onSelect]);

  useEffect(() => {
    const AMap = amapRef.current;
    if (!AMap || !loaded || !routeRequest) return;
    AMap.plugin(["AMap.Walking", "AMap.Geocoder"], () => {
      const walking = new AMap.Walking();
      const runWalking = (origin: [number, number], destination: [number, number]) => walking.search(origin, destination, (status, result) => {
        const first = result.routes?.[0];
        if (status !== "complete" || !first) {
          onRouteError("高德 JS 步行路线规划失败，请稍后重试");
          return;
        }
        const steps = (first.steps || []).map((step) => ({ instruction: step.instruction || "继续步行" }));
        const polyline = (first.steps || []).flatMap((step) => (step.path || []).map((point) => [point.lng, point.lat]));
        onRouteCalculated({
          distance_meters: Number(first.distance || 0),
          duration_seconds: Number(first.time || 0),
          steps,
          polyline,
        });
      });
      if (routeRequest.origin && routeRequest.destination) {
        runWalking(routeRequest.origin, routeRequest.destination);
        return;
      }
      if (!routeRequest.originAddress || !routeRequest.destinationAddress) {
        onRouteError("步行路线缺少起点或终点");
        return;
      }
      const city = campus.name.includes("肇庆") ? "肇庆" : campus.name.includes("清远") ? "清远" : "广州";
      const geocoder = new AMap.Geocoder({ city });
      const geocode = (address: string) => new Promise<[number, number]>((resolve, reject) => {
        geocoder.getLocation(address, (status, result) => {
          const point = result.geocodes?.[0]?.location;
          if (status === "complete" && point) resolve([point.lng, point.lat]);
          else reject(new Error("geocode_failed"));
        });
      });
      void Promise.all([geocode(routeRequest.originAddress), geocode(routeRequest.destinationAddress)])
        .then(([origin, destination]) => runWalking(origin, destination))
        .catch(() => onRouteError("高德未能解析起点或终点地址，请补充城市和详细地址"));
    });
  }, [campus.name, loaded, onRouteCalculated, onRouteError, routeRequest]);

  useEffect(() => {
    const map = mapRef.current;
    const AMap = amapRef.current;
    if (!map || !AMap) return;
    if (routeOverlayRef.current) {
      map.remove(routeOverlayRef.current);
      routeOverlayRef.current = null;
    }
    if (!route?.polyline.length) return;
    const line = new AMap.Polyline({
      path: route.polyline,
      strokeColor: "#1677ff",
      strokeWeight: 7,
      strokeOpacity: 0.85,
      lineJoin: "round",
    });
    routeOverlayRef.current = line;
    map.add(line);
    map.setFitView([line]);
  }, [route]);

  useEffect(() => {
    const map = mapRef.current;
    const AMap = amapRef.current;
    if (!map || !AMap || !loaded) return;
    if (currentLocationOverlaysRef.current.length) map.remove(currentLocationOverlaysRef.current);
    currentLocationOverlaysRef.current = [];
    if (!currentLocation) return;
    const point: [number, number] = [currentLocation.longitude, currentLocation.latitude];
    const accuracyCircle = new AMap.Circle({
      center: point,
      radius: currentLocation.accuracy,
      strokeColor: "#2563eb",
      strokeOpacity: 0.55,
      strokeWeight: 1,
      fillColor: "#3b82f6",
      fillOpacity: 0.12,
    });
    const currentMarker = new AMap.Marker({
      position: point,
      title: "我的位置",
      content: '<span class="amap-current-location" aria-label="我的位置"><i></i></span>',
      offset: [-11, -11],
      zIndex: 120,
    });
    currentLocationOverlaysRef.current = [accuracyCircle, currentMarker];
    map.add(currentLocationOverlaysRef.current);
    map.setCenter(point);
  }, [currentLocation, loaded]);

  useEffect(() => {
    if (selected?.longitude != null && selected.latitude != null) {
      mapRef.current?.setCenter([selected.longitude, selected.latitude]);
    }
  }, [selected]);

  return (
    <div className="real-map-shell">
      <div ref={containerRef} className="real-map" aria-label={`${campus.name}高德真实道路地图`} />
      {error && <div className="map-inline-error" role="alert">{error}</div>}
    </div>
  );
}

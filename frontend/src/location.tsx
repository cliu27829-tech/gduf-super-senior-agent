import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

export type BrowserLocation = {
  latitude: number;
  longitude: number;
  accuracy: number;
  captured_at: string;
};

type LocationState = {
  location: BrowserLocation | null;
  locating: boolean;
  error: string;
  locate: () => Promise<BrowserLocation>;
  clear: () => void;
};

const Context = createContext<LocationState | null>(null);

function publicGeolocationError(reason: GeolocationPositionError | Error): string {
  if ("code" in reason) {
    if (reason.code === reason.PERMISSION_DENIED) return "你没有允许定位。没事，也可以选择一个起点。";
    if (reason.code === reason.TIMEOUT) return "定位超时，请重新定位或选择其他起点。";
    if (reason.code === reason.POSITION_UNAVAILABLE) return "暂时无法获得当前位置，请选择其他起点。";
  }
  return reason.message || "定位失败，请稍后重试。";
}

export function LocationProvider({ children }: { children: ReactNode }) {
  const [location, setLocation] = useState<BrowserLocation | null>(null);
  const [locating, setLocating] = useState(false);
  const [error, setError] = useState("");

  const locate = () => new Promise<BrowserLocation>((resolve, reject) => {
    if (!navigator.geolocation) {
      const reason = new Error("当前浏览器不支持定位，请选择其他起点。");
      setError(reason.message);
      reject(reason);
      return;
    }
    setLocating(true);
    setError("");
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const next = {
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          accuracy: position.coords.accuracy,
          captured_at: new Date(position.timestamp || Date.now()).toISOString(),
        };
        setLocation(next);
        setLocating(false);
        resolve(next);
      },
      (reason) => {
        const message = publicGeolocationError(reason);
        setError(message);
        setLocating(false);
        reject(new Error(message));
      },
      { enableHighAccuracy: true, timeout: 10_000, maximumAge: 30_000 },
    );
  });

  const value = useMemo<LocationState>(
    () => ({ location, locating, error, locate, clear: () => { setLocation(null); setError(""); } }),
    [error, locating, location],
  );
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useGeolocation(): LocationState {
  const value = useContext(Context);
  if (!value) throw new Error("useGeolocation must be used inside LocationProvider");
  return value;
}

export function locationAccuracy(accuracy: number): { status: "accurate" | "approximate" | "low"; message: string } {
  if (accuracy <= 30) return { status: "accurate", message: "定位较准确" };
  if (accuracy <= 100) return { status: "approximate", message: `当前位置存在约 ${Math.round(accuracy)} 米偏差` };
  return { status: "low", message: "当前定位精度不太够，可以重新定位或手动选择起点。" };
}

export function LocationPermissionSheet({
  open,
  destinationName,
  locating,
  onAllow,
  onManual,
  onClose,
}: {
  open: boolean;
  destinationName?: string;
  locating: boolean;
  onAllow: () => void;
  onManual: () => void;
  onClose: () => void;
}) {
  if (!open) return null;
  return <div className="location-sheet-backdrop" role="presentation" onClick={onClose}>
    <section className="location-sheet" role="dialog" aria-modal="true" aria-labelledby="location-sheet-title" onClick={(event) => event.stopPropagation()}>
      <div className="location-sheet-handle" aria-hidden="true" />
      <span className="location-sheet-icon" aria-hidden="true">⌖</span>
      <div><p className="eyebrow">本次路线规划</p><h2 id="location-sheet-title">用你的当前位置规划路线？</h2></div>
      <p>{destinationName ? `我会从你现在的位置规划到${destinationName}。` : "我会使用当前位置规划这次路线。"}仅用于本次路线规划，不会保存你的实时位置。</p>
      <div className="location-sheet-actions">
        <button className="button full" onClick={onAllow} disabled={locating}>{locating ? "正在获取你的位置…" : "使用我的位置"}</button>
        <button className="ghost-button full" onClick={onManual} disabled={locating}>选择其他起点</button>
      </div>
      <button className="location-sheet-close" aria-label="关闭定位提示" onClick={onClose}>×</button>
    </section>
  </div>;
}

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LocationPermissionSheet, LocationProvider, locationAccuracy, useGeolocation } from "./location";

function Probe() {
  const state = useGeolocation();
  return <div><button onClick={() => void state.locate().catch(() => undefined)}>定位</button><output>{state.location ? `${state.location.latitude},${state.location.accuracy}` : state.error}</output></div>;
}

function geolocationWith(
  run: (success: PositionCallback, error: PositionErrorCallback | null) => void,
): Geolocation {
  return {
    getCurrentPosition: (success: PositionCallback, error: PositionErrorCallback | null) => run(success, error),
    watchPosition: vi.fn(),
    clearWatch: vi.fn(),
  } as unknown as Geolocation;
}

afterEach(() => vi.unstubAllGlobals());

describe("browser geolocation", () => {
  it("keeps a granted high-accuracy position in session memory", async () => {
    vi.stubGlobal("navigator", {
      ...navigator,
      geolocation: geolocationWith((success) => success({
        coords: { latitude: 23.716, longitude: 113.085, accuracy: 18 },
        timestamp: Date.now(),
      } as GeolocationPosition)),
    });
    render(<LocationProvider><Probe /></LocationProvider>);
    await userEvent.click(screen.getByRole("button", { name: "定位" }));
    expect(await screen.findByText("23.716,18")).toBeInTheDocument();
  });

  it.each([
    [1, "你没有允许定位"],
    [2, "暂时无法获得当前位置"],
    [3, "定位超时"],
  ])("shows a public fallback for geolocation error %s", async (code, copy) => {
    vi.stubGlobal("navigator", {
      ...navigator,
      geolocation: geolocationWith((_success, error) => error?.({
        code,
        message: "browser-internal-detail",
        PERMISSION_DENIED: 1,
        POSITION_UNAVAILABLE: 2,
        TIMEOUT: 3,
      } as GeolocationPositionError)),
    });
    render(<LocationProvider><Probe /></LocationProvider>);
    await userEvent.click(screen.getByRole("button", { name: "定位" }));
    expect(await screen.findByText(new RegExp(copy))).toBeInTheDocument();
    expect(screen.queryByText("browser-internal-detail")).not.toBeInTheDocument();
  });

  it("classifies accurate, approximate and unusable positions", () => {
    expect(locationAccuracy(30).status).toBe("accurate");
    expect(locationAccuracy(31).status).toBe("approximate");
    expect(locationAccuracy(100).message).toContain("100 米偏差");
    expect(locationAccuracy(101).status).toBe("low");
  });

  it("asks before locating and offers a manual origin", async () => {
    const allow = vi.fn();
    const manual = vi.fn();
    render(<LocationPermissionSheet open destinationName="北区教学楼" locating={false} onAllow={allow} onManual={manual} onClose={vi.fn()} />);
    expect(screen.getByText(/仅用于本次路线规划，不会保存/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "使用我的位置" }));
    await userEvent.click(screen.getByRole("button", { name: "选择其他起点" }));
    expect(allow).toHaveBeenCalledOnce();
    expect(manual).toHaveBeenCalledOnce();
  });
});

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import Settings, get_settings


class MapServiceError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.public_message = message
        self.status_code = status_code


@dataclass(slots=True)
class MapService:
    settings: Settings

    @classmethod
    def configured(cls) -> "MapService":
        return cls(get_settings())

    @property
    def webservice_configured(self) -> bool:
        return bool(self.settings.amap_webservice_key.strip())

    @property
    def security_proxy_configured(self) -> bool:
        return bool(self.settings.amap_security_code.strip())

    async def _request(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.webservice_configured:
            raise MapServiceError("后端尚未配置高德 WebService Key", 503)
        safe_params = {**params, "key": self.settings.amap_webservice_key, "output": "JSON"}
        timeout = httpx.Timeout(self.settings.amap_request_timeout_seconds)
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
                response = await client.get(f"{self.settings.amap_api_base_url.rstrip('/')}/{path.lstrip('/')}", params=safe_params)
                response.raise_for_status()
                payload = response.json()
        except httpx.TimeoutException as exc:
            raise MapServiceError("高德地图服务响应超时", 504) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise MapServiceError("高德地图服务暂时不可用") from exc
        if str(payload.get("status")) != "1":
            info = str(payload.get("info") or "地图服务返回错误")
            if "INVALID_USER_KEY" in info or "USERKEY" in info:
                raise MapServiceError("高德地图 Key 无效或无权调用此接口", 502)
            raise MapServiceError(f"高德地图服务未返回有效结果：{info}")
        return payload

    async def geocode(self, address: str, city: str = "广州") -> dict[str, Any]:
        payload = await self._request("v3/geocode/geo", {"address": address, "city": city})
        rows = payload.get("geocodes") or []
        if not rows:
            raise MapServiceError("没有找到匹配的地理编码结果", 404)
        item = rows[0]
        location = str(item.get("location") or "")
        try:
            longitude, latitude = (float(value) for value in location.split(",", 1))
        except (TypeError, ValueError) as exc:
            raise MapServiceError("地理编码结果缺少有效坐标") from exc
        return {
            "formatted_address": item.get("formatted_address") or address,
            "longitude": longitude,
            "latitude": latitude,
            "level": item.get("level") or "",
            "provider": "amap",
        }

    async def walking_route(
        self, origin_longitude: float, origin_latitude: float, destination_longitude: float, destination_latitude: float
    ) -> dict[str, Any]:
        payload = await self._request(
            "v3/direction/walking",
            {
                "origin": f"{origin_longitude:.6f},{origin_latitude:.6f}",
                "destination": f"{destination_longitude:.6f},{destination_latitude:.6f}",
            },
        )
        paths = (payload.get("route") or {}).get("paths") or []
        if not paths:
            raise MapServiceError("没有找到可用的步行路线", 404)
        path = paths[0]
        steps = path.get("steps") or []
        polyline: list[list[float]] = []
        for step in steps:
            for pair in str(step.get("polyline") or "").split(";"):
                if not pair:
                    continue
                try:
                    longitude, latitude = (float(value) for value in pair.split(",", 1))
                except ValueError:
                    continue
                point = [longitude, latitude]
                if not polyline or polyline[-1] != point:
                    polyline.append(point)
        return {
            "provider": "amap",
            "distance_meters": int(float(path.get("distance") or 0)),
            "duration_seconds": int(float(path.get("duration") or 0)),
            "steps": [
                {
                    "instruction": step.get("instruction") or "",
                    "road": step.get("road") or "",
                    "distance_meters": int(float(step.get("distance") or 0)),
                    "duration_seconds": int(float(step.get("duration") or 0)),
                }
                for step in steps
            ],
            "polyline": polyline,
        }

    @staticmethod
    def navigation_link(name: str, longitude: float, latitude: float) -> str:
        query = urlencode({"to": f"{longitude},{latitude},{name}", "mode": "walk", "callnative": "0"})
        return f"https://uri.amap.com/navigation?{query}"

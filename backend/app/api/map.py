from __future__ import annotations

from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from app.core.config import Settings, get_settings
from app.core.dependencies import CurrentUser
from app.services.map_service import MapService, MapServiceError


router = APIRouter(prefix="/map", tags=["map"])
SettingsDependency = Annotated[Settings, Depends(get_settings)]


@router.get("/status")
def map_status(settings: SettingsDependency) -> dict:
    return {
        "provider": "amap",
        "webservice_configured": bool(settings.amap_webservice_key.strip()),
        "security_proxy_configured": bool(settings.amap_security_code.strip()),
    }


@router.get("/geocode")
async def geocode(
    _user: CurrentUser,
    address: str = Query(min_length=2, max_length=255),
    city: str = Query(default="广州", min_length=1, max_length=50),
) -> dict:
    try:
        return await MapService.configured().geocode(address, city)
    except MapServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.public_message) from exc


@router.get("/walking-route")
async def walking_route(
    _user: CurrentUser,
    origin_longitude: float = Query(ge=-180, le=180),
    origin_latitude: float = Query(ge=-90, le=90),
    destination_longitude: float = Query(ge=-180, le=180),
    destination_latitude: float = Query(ge=-90, le=90),
) -> dict:
    try:
        return await MapService.configured().walking_route(
            origin_longitude, origin_latitude, destination_longitude, destination_latitude
        )
    except MapServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.public_message) from exc


@router.api_route("/_AMapService/{path:path}", methods=["GET"])
async def amap_security_proxy(path: str, request: Request, settings: SettingsDependency) -> Response:
    """Proxy only AMap JS API support calls while keeping securityJsCode server-side."""
    if not settings.amap_security_code.strip():
        raise HTTPException(status_code=503, detail="高德 JS API 安全代理尚未配置")
    if not path.startswith(("v3/", "v4/")) or ".." in path or "\\" in path:
        raise HTTPException(status_code=404, detail="不支持的高德代理路径")
    params = list(request.query_params.multi_items())
    params.append(("jscode", settings.amap_security_code))
    try:
        async with httpx.AsyncClient(timeout=settings.amap_request_timeout_seconds, follow_redirects=False) as client:
            upstream = await client.get(f"{settings.amap_api_base_url.rstrip('/')}/{path}", params=params)
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="高德安全代理响应超时") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="高德安全代理暂时不可用") from exc
    headers = {"content-type": upstream.headers.get("content-type", "application/json")}
    return Response(content=upstream.content, status_code=upstream.status_code, headers=headers)

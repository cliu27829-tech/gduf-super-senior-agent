from fastapi import APIRouter

from app.api import admin, agent, auth, campus, map, notifications, tasks


api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(agent.router)
api_router.include_router(notifications.router)
api_router.include_router(tasks.router)
api_router.include_router(campus.router)
api_router.include_router(map.router)
api_router.include_router(admin.router)

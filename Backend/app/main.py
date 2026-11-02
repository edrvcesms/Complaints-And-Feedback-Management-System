from fastapi import FastAPI, status
from fastapi.requests import Request
from contextlib import asynccontextmanager
from app.core.config import settings
import os
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import select
from app.utils.logger import logger
from app.utils.attachments import AttachmentSizeLimitMiddleware
from app.routers import user_auth_routes, user_routes, barangay_routes,chatbot_routes, complaint_routes, incident_routes, lgu_routes, notification_routes, announcement_routes, report_routes, app_feedback_routes, event_routes, sms_routes, categories_routes,emergency_routes, emergency_queues, web_push_routes, evacuation_centers_routes, dummy_account
from app.admin import _super_admin_routes as _super_admin
from app.utils.memory import MemoryMonitoringMiddleware
from app.database.database import AsyncSessionLocal
from app.core.redis import redis_client
scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application startup complete.")
    yield
    logger.info("Application shutdown complete.")

app = FastAPI(lifespan=lifespan)

default_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://cfms-stamaria.com",
    "http://localhost:19006",
    "http://127.0.0.1:19006",
    "https://www.cfms-stamaria.com",
    "https://cfms-stamaria.netlify.app"
]

raw_origins = os.getenv("CORS_ALLOWED_ORIGINS", "")
configured_origins = [
    origin.strip().rstrip("/")
    for origin in raw_origins.split(",")
    if origin.strip()
]
origins = list(dict.fromkeys([*default_origins, *configured_origins]))

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)
app.add_middleware(MemoryMonitoringMiddleware)

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/readyz")
async def readyz():
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(select(1))
        await redis_client.ping()
        return {"status": "ready"}
    except Exception:
        logger.exception("Readiness check failed")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not ready"},
        )

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Please Atry again later."},
)

logger.info("FastAPI application initialized.")

app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
app.add_middleware(AttachmentSizeLimitMiddleware)

app.include_router(user_auth_routes.router, prefix="/api/v1/auth", tags=["User Authentication"])
app.include_router(user_routes.router, prefix="/api/v1/users", tags=["Users"])
app.include_router(_super_admin.router, prefix="/api/v1/super-admin", tags=["Super Admin"])
app.include_router(complaint_routes.router, prefix="/api/v1/complaints", tags=["Complaints"])
app.include_router(barangay_routes.router, prefix="/api/v1/barangays", tags=["Barangays"])
app.include_router(incident_routes.router, prefix="/api/v1/incidents", tags=["Incidents"])
app.include_router(categories_routes.router, prefix="/api/v1/categories", tags=["Categories"])
app.include_router(sms_routes.router, prefix="/api/v1/sms", tags=["SMS"])
app.include_router(lgu_routes.router, prefix="/api/v1/lgu", tags=["LGU"])
app.include_router(notification_routes.router, prefix="/api/v1/notifications", tags=["Notifications"])
app.include_router(announcement_routes.router, prefix="/api/v1/announcements", tags=["Announcements"])
app.include_router(report_routes.router, prefix="/api/v1/reports", tags=["Reports"])
app.include_router(app_feedback_routes.router, prefix="/api/v1/app-feedback", tags=["App Feedback"])
app.include_router(event_routes.router, prefix="/api/v1/events", tags=["Events"])
app.include_router(chatbot_routes.router, prefix="/api/v1/chatbot", tags=["Chatbot"])
app.include_router(emergency_queues.router, prefix="/api/v1/emergency-queue", tags=["Emergency Queue"])
app.include_router(emergency_routes.router, prefix="/api/v1/emergency", tags=["Emergency"])
app.include_router(web_push_routes.router, prefix="/api/v1/web-push", tags=["Web Push"])
app.include_router(evacuation_centers_routes.router, prefix="/api/v1/evacuation-centers", tags=["Evacuation Centers"])
# app.include_router(dummy_account.router, prefix="/api/v1/dummy-accounts", tags=["Dummy Accounts"])

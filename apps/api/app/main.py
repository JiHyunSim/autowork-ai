from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.core.config import settings
from app.routers import auth, meetings, reports, emails


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작/종료 시 실행"""
    print(f"🚀 AutoWork AI API 시작 — {settings.ENVIRONMENT}")
    yield
    print("AutoWork AI API 종료")


app = FastAPI(
    title="AutoWork AI API",
    description="AI 업무 자동화 SaaS — 미팅 요약, 보고서 생성, 이메일 작성",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(meetings.router, prefix="/api/meetings", tags=["meetings"])
app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
app.include_router(emails.router, prefix="/api/emails", tags=["emails"])


@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "0.1.0"}

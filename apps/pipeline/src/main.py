"""AutoWork 파이프라인 API 서버 진입점"""
import structlog
import uvicorn
from fastapi import FastAPI

from src.api.routes import router

logger = structlog.get_logger(__name__)

app = FastAPI(
    title="AutoWork Pipeline API",
    description="콘텐츠 자동화 파이프라인 — n8n 연동 API",
    version="0.2.0",
)

app.include_router(router)


if __name__ == "__main__":
    logger.info("pipeline_server.start", port=8000)
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=False)

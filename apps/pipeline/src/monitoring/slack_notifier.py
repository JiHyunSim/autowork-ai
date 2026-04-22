"""Slack 알림 모듈 — 파이프라인 성공/실패 알림"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

import httpx
import structlog

from src.config import settings

logger = structlog.get_logger(__name__)


class SlackNotifier:
    """Slack Webhook 기반 파이프라인 알림"""

    def __init__(self, webhook_url: Optional[str] = None) -> None:
        self._webhook_url = webhook_url or settings.slack_webhook_url
        self._client = httpx.Client(timeout=10.0)

    def notify_daily_summary(self, stats: dict) -> bool:
        """일별 콘텐츠 생성 요약 알림

        Args:
            stats: {
                "date": "2026-04-22",
                "blog_generated": 5, "blog_published": 5, "blog_failed": 0,
                "youtube_generated": 1, "youtube_published": 1,
                "reels_generated": 1, "reels_published": 1,
                "affiliate_inserted": 4,
                "errors": [...]
            }
        """
        date = stats.get("date", datetime.now().strftime("%Y-%m-%d"))
        blog_pub = stats.get("blog_published", 0)
        blog_gen = stats.get("blog_generated", 0)
        yt_pub = stats.get("youtube_published", 0)
        reels_pub = stats.get("reels_published", 0)
        errors = stats.get("errors", [])
        affiliate = stats.get("affiliate_inserted", 0)

        status_icon = "✅" if not errors else "⚠️"
        error_text = ""
        if errors:
            error_lines = "\n".join(f"• {e}" for e in errors[:5])
            error_text = f"\n\n*오류 ({len(errors)}건)*:\n{error_lines}"

        text = (
            f"{status_icon} *AutoWork 일별 리포트 — {date}*\n\n"
            f"*블로그*: {blog_pub}/{blog_gen}개 발행\n"
            f"*유튜브*: {yt_pub}개 발행\n"
            f"*릴스*: {reels_pub}개 발행\n"
            f"*제휴 링크 삽입*: {affiliate}건"
            f"{error_text}"
        )
        return self._send(text)

    def notify_error(self, phase: str, error: str, context: dict | None = None) -> bool:
        """파이프라인 단계별 오류 알림"""
        ctx_text = ""
        if context:
            ctx_text = "\n" + "\n".join(f"• {k}: {v}" for k, v in context.items())
        text = (
            f"🚨 *파이프라인 오류 — {phase}*\n\n"
            f"```{error[:500]}```"
            f"{ctx_text}"
        )
        return self._send(text)

    def notify_pipeline_start(self, target_date: str) -> bool:
        """파이프라인 시작 알림"""
        text = f"🚀 *AutoWork 파이프라인 시작* — {target_date}"
        return self._send(text)

    def notify_pipeline_complete(self, target_date: str, duration_sec: float) -> bool:
        """파이프라인 완료 알림"""
        text = (
            f"✅ *AutoWork 파이프라인 완료* — {target_date}\n"
            f"소요 시간: {duration_sec:.1f}초"
        )
        return self._send(text)

    def _send(self, text: str) -> bool:
        if not self._webhook_url:
            logger.debug("slack_notifier.no_webhook_url")
            return False
        try:
            resp = self._client.post(
                self._webhook_url,
                content=json.dumps({"text": text}),
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            logger.info("slack_notifier.sent")
            return True
        except Exception as exc:
            logger.error("slack_notifier.error", error=str(exc))
            return False

    def close(self) -> None:
        self._client.close()

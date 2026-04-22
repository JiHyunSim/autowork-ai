"""E2E 파이프라인 실행기 — 전체 콘텐츠 발행 흐름을 단일 함수로 실행

Phase 순서:
  1. 트렌드 수집 (TrendCollector)
  2. 주제 큐 생성 (TopicSelector + ContentQueue)
  3-a. 블로그 생성 (BlogGenerator) + 제휴 링크 삽입 + 티스토리 발행
  3-b. 릴스 캡션 생성 (ReelsGenerator) + 인스타그램 발행
  3-c. (월/수/금) 유튜브 스크립트 생성 (YouTubeGenerator) + 유튜브 발행
  4. PipelineMonitor로 상태 기록 + Slack 알림
"""
from __future__ import annotations

import datetime
from typing import Optional

import structlog

from src.config import settings
from src.monitoring.pipeline_monitor import PipelineMonitor
from src.monitoring.slack_notifier import SlackNotifier

logger = structlog.get_logger(__name__)


class PipelineRunner:
    """전체 콘텐츠 발행 파이프라인 E2E 실행기"""

    YOUTUBE_DAYS = {0, 2, 4}  # 월=0, 수=2, 금=4 (weekday)

    def __init__(
        self,
        monitor: Optional[PipelineMonitor] = None,
        dry_run: bool = False,
    ) -> None:
        self._monitor = monitor or PipelineMonitor()
        self._dry_run = dry_run  # True: 실제 API 호출 없이 구조 검증만

    # ------------------------------------------------------------------ #
    # Entry point
    # ------------------------------------------------------------------ #

    def run(self, target_date: Optional[str] = None) -> dict:
        """전체 파이프라인 실행. 결과 stats dict 반환."""
        today = target_date or datetime.date.today().isoformat()
        weekday = datetime.date.fromisoformat(today).weekday()
        run_youtube = weekday in self.YOUTUBE_DAYS

        run_id = self._monitor.start_run(today)
        content_counts: dict = {
            "blog_generated": 0,
            "blog_published": 0,
            "blog_failed": 0,
            "youtube_generated": 0,
            "youtube_published": 0,
            "reels_generated": 0,
            "reels_published": 0,
            "affiliate_inserted": 0,
        }

        try:
            # Phase 1: 트렌드 수집
            trends = self._monitor.run_step_with_retry(
                step_name="trend_collect",
                fn=self._collect_trends,
                max_retries=2,
            )
            self._monitor.record_step(
                run_id, "trend_collect", success=True,
                result={"keyword_count": len(trends)},
            )

            # Phase 2: 큐 생성
            self._monitor.run_step_with_retry(
                step_name="queue_build",
                fn=self._build_queue,
                trends,
                today,
                max_retries=2,
            )
            self._monitor.record_step(run_id, "queue_build", success=True)

            # Phase 3-a: 블로그
            blog_result = self._monitor.run_step_with_retry(
                step_name="blog_generate",
                fn=self._generate_and_publish_blog,
                today,
            )
            content_counts["blog_generated"] = blog_result.get("generated", 0)
            content_counts["blog_failed"] = blog_result.get("failed", 0)
            content_counts["blog_published"] = blog_result.get("published", 0)
            content_counts["affiliate_inserted"] = blog_result.get("affiliate", 0)
            self._monitor.record_step(
                run_id, "blog_generate", success=True, result=blog_result
            )

            # Phase 3-b: 릴스
            reels_result = self._monitor.run_step_with_retry(
                step_name="reels_generate",
                fn=self._generate_and_publish_reels,
                today,
            )
            content_counts["reels_generated"] = reels_result.get("generated", 0)
            content_counts["reels_published"] = reels_result.get("published", 0)
            self._monitor.record_step(
                run_id, "reels_generate", success=True, result=reels_result
            )

            # Phase 3-c: 유튜브 (월/수/금만)
            if run_youtube:
                yt_result = self._monitor.run_step_with_retry(
                    step_name="youtube_generate",
                    fn=self._generate_and_publish_youtube,
                    today,
                )
                content_counts["youtube_generated"] = yt_result.get("generated", 0)
                content_counts["youtube_published"] = yt_result.get("published", 0)
                self._monitor.record_step(
                    run_id, "youtube_generate", success=True, result=yt_result
                )

        except Exception as exc:
            logger.error("pipeline_runner.failed", error=str(exc), date=today)
            self._monitor.record_step(
                run_id, "pipeline", success=False, error=str(exc)
            )

        finally:
            stats = {
                "date": today,
                **content_counts,
                "errors": [],
            }
            self._monitor.finish_run(run_id, stats)

        return stats

    # ------------------------------------------------------------------ #
    # 단계 구현
    # ------------------------------------------------------------------ #

    def _collect_trends(self) -> list:
        if self._dry_run:
            logger.info("pipeline_runner.dry_run.trend_collect")
            return [{"keyword": "AI 자동화", "source": "google_trends", "score": 0.9}]

        from src.trend import TrendCollector
        collector = TrendCollector()
        trends = collector.collect_all()
        return [
            {"keyword": t.keyword, "source": t.source, "score": t.score}
            for t in trends[:20]
        ]

    def _build_queue(self, trends: list, target_date: str) -> dict:
        if self._dry_run:
            logger.info("pipeline_runner.dry_run.queue_build")
            return {"topics": [], "saved_count": 0}

        from src.trend import ContentQueue
        import datetime as dt
        queue = ContentQueue()
        return queue.build_daily_queue(
            target_date=dt.date.fromisoformat(target_date)
        )

    def _generate_and_publish_blog(self, target_date: str) -> dict:
        if self._dry_run:
            logger.info("pipeline_runner.dry_run.blog")
            return {"generated": 5, "failed": 0, "published": 5, "affiliate": 4}

        from src.content import BlogGenerator
        from src.upload import TistoryUploader
        from src.affiliate import AffiliateLinkInserter

        generator = BlogGenerator()
        posts = generator.generate_from_queue(
            target_date=target_date,
            limit=settings.daily_blog_target,
        )
        generated = [p for p in posts if "error" not in p]
        failed = [p for p in posts if "error" in p]

        # 제휴 링크 삽입
        affiliate_count = 0
        inserter = AffiliateLinkInserter()
        try:
            for post in generated:
                try:
                    result = inserter.process_blog_post(
                        blog_post_id=post.get("id", ""),
                        content=post.get("content", ""),
                        title=post.get("title", ""),
                    )
                    if result.get("links_inserted", 0) > 0:
                        affiliate_count += 1
                except Exception as exc:
                    logger.warning(
                        "pipeline_runner.affiliate_skip",
                        post_id=post.get("id"),
                        error=str(exc),
                    )
        finally:
            inserter.close()

        # 티스토리 발행
        uploader = TistoryUploader()
        upload_results = uploader.upload_pending(limit=settings.daily_blog_target)
        published = sum(1 for r in upload_results if r.get("success"))

        return {
            "generated": len(generated),
            "failed": len(failed),
            "published": published,
            "affiliate": affiliate_count,
        }

    def _generate_and_publish_reels(self, target_date: str) -> dict:
        if self._dry_run:
            logger.info("pipeline_runner.dry_run.reels")
            return {"generated": 1, "published": 1}

        from src.content import ReelsGenerator
        from src.upload import InstagramUploader

        generator = ReelsGenerator()
        scripts = generator.generate_from_queue(
            target_date=target_date,
            limit=settings.daily_reels_target,
        )
        generated = [s for s in scripts if "error" not in s]

        uploader = InstagramUploader()
        upload_results = uploader.upload_pending(limit=settings.daily_reels_target)
        published = sum(1 for r in upload_results if r.get("success"))

        return {"generated": len(generated), "published": published}

    def _generate_and_publish_youtube(self, target_date: str) -> dict:
        if self._dry_run:
            logger.info("pipeline_runner.dry_run.youtube")
            return {"generated": 1, "published": 1}

        from src.content import YouTubeGenerator
        from src.upload import YouTubeUploader

        generator = YouTubeGenerator()
        scripts = generator.generate_from_queue(
            target_date=target_date,
            limit=1,
        )
        generated = [s for s in scripts if "error" not in s]

        uploader = YouTubeUploader()
        upload_results = uploader.upload_pending(limit=1)
        published = sum(1 for r in upload_results if r.get("success"))

        return {"generated": len(generated), "published": published}

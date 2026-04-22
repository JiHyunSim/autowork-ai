"""미팅 요약 서비스 — Whisper → Claude Sonnet 4.6 파이프라인"""
import json
import asyncio
from typing import AsyncGenerator
from fastapi import UploadFile
from supabase import Client
import anthropic
import openai

from app.core.config import settings

MEETING_SUMMARY_PROMPT = """당신은 한국 기업의 미팅 요약 전문가입니다.
아래 미팅 녹취 텍스트를 분석하여 다음 항목을 JSON 형식으로 반환하세요:

1. summary: 미팅 핵심 내용 요약 (3~5문장)
2. decisions: 미팅에서 결정된 사항 목록 (배열)
3. action_items: 담당자별 할 일 목록 (배열, 각 항목에 assignee, task, deadline 포함)
4. next_agenda: 다음 미팅 아젠다 제안 (배열)

반드시 유효한 JSON만 반환하세요.

미팅 녹취:
{transcript}
"""


class MeetingService:
    def __init__(self, supabase: Client):
        self.supabase = supabase
        self.anthropic = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.openai = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    async def create_meeting(self, user_id: str, title: str, file: UploadFile) -> dict:
        """미팅 레코드 생성 및 파일 업로드"""
        # Supabase Storage에 파일 업로드
        file_content = await file.read()
        file_path = f"meetings/{user_id}/{file.filename}"

        self.supabase.storage.from_("meeting-files").upload(
            path=file_path,
            file=file_content,
            file_options={"content-type": file.content_type},
        )

        # DB에 미팅 레코드 생성
        result = self.supabase.table("meeting_summaries").insert({
            "created_by": user_id,
            "team_id": await self._get_user_team(user_id),
            "title": title,
            "original_file_path": file_path,
            "status": "uploading",
        }).execute()

        return result.data[0]

    async def process_meeting(self, meeting_id: str):
        """Whisper → Claude 파이프라인 실행"""
        try:
            # 1단계: 상태 업데이트 → transcribing
            self._update_status(meeting_id, "transcribing")

            # 2단계: Whisper로 음성 → 텍스트
            transcript = await self._transcribe(meeting_id)

            # 3단계: 상태 업데이트 → summarizing
            self._update_status(meeting_id, "summarizing", transcript=transcript)

            # 4단계: Claude Sonnet 4.6으로 요약 생성
            summary_data = await self._summarize(transcript)

            # 5단계: DB 저장 → done
            self.supabase.table("meeting_summaries").update({
                "summary": summary_data.get("summary"),
                "action_items": summary_data.get("action_items", []),
                "decisions": summary_data.get("decisions", []),
                "status": "done",
            }).eq("id", meeting_id).execute()

        except Exception as e:
            self.supabase.table("meeting_summaries").update({
                "status": "failed",
            }).eq("id", meeting_id).execute()
            raise e

    async def _transcribe(self, meeting_id: str) -> str:
        """OpenAI Whisper API로 음성 → 텍스트"""
        meeting = self.supabase.table("meeting_summaries").select("*").eq("id", meeting_id).single().execute()
        file_path = meeting.data["original_file_path"]

        # Supabase Storage에서 파일 다운로드
        file_data = self.supabase.storage.from_("meeting-files").download(file_path)

        # Whisper API 호출
        transcript_response = await self.openai.audio.transcriptions.create(
            model=settings.WHISPER_MODEL,
            file=("meeting.mp3", file_data, "audio/mpeg"),
            language="ko",
            response_format="text",
        )

        return transcript_response

    async def _summarize(self, transcript: str) -> dict:
        """Claude Sonnet 4.6으로 미팅 요약 생성"""
        prompt = MEETING_SUMMARY_PROMPT.format(transcript=transcript)

        message = self.anthropic.messages.create(
            model=settings.CLAUDE_MODEL,  # claude-sonnet-4-6
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )

        content = message.content[0].text
        return json.loads(content)

    def _update_status(self, meeting_id: str, status: str, **kwargs):
        update_data = {"status": status, **kwargs}
        self.supabase.table("meeting_summaries").update(update_data).eq("id", meeting_id).execute()

    async def get_meeting(self, meeting_id: str, user_id: str) -> dict | None:
        result = self.supabase.table("meeting_summaries").select("*").eq("id", meeting_id).eq("created_by", user_id).single().execute()
        return result.data if result.data else None

    async def list_meetings(self, user_id: str, limit: int = 20) -> list[dict]:
        result = self.supabase.table("meeting_summaries").select("*").eq("created_by", user_id).order("created_at", desc=True).limit(limit).execute()
        return result.data or []

    async def stream_status(self, meeting_id: str, user_id: str) -> AsyncGenerator[str, None]:
        """미팅 처리 상태를 SSE로 스트리밍"""
        while True:
            meeting = await self.get_meeting(meeting_id, user_id)
            if not meeting:
                yield json.dumps({"error": "미팅을 찾을 수 없습니다"})
                break

            yield json.dumps({
                "status": meeting["status"],
                "summary": meeting.get("summary"),
            })

            if meeting["status"] in ("done", "failed"):
                break

            await asyncio.sleep(2)

    async def _get_user_team(self, user_id: str) -> str:
        """사용자의 팀 ID 조회"""
        result = self.supabase.table("team_members").select("team_id").eq("user_id", user_id).limit(1).single().execute()
        return result.data["team_id"]

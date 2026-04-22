"""미팅 요약 API 라우터"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.responses import StreamingResponse
from supabase import Client
from pydantic import BaseModel
from typing import Optional

from app.core.deps import get_current_user, get_supabase
from app.services.meeting_service import MeetingService

router = APIRouter()


class MeetingSummaryResponse(BaseModel):
    id: str
    title: str
    status: str
    summary: Optional[str] = None
    action_items: Optional[list] = None
    decisions: Optional[list] = None


@router.post("/upload", response_model=MeetingSummaryResponse)
async def upload_meeting(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = "미팅 요약",
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """미팅 녹취 파일 업로드 및 요약 시작"""
    # 지원 포맷 확인
    allowed_types = ["audio/mpeg", "audio/mp4", "audio/wav", "audio/m4a", "video/mp4"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 파일 형식: {file.content_type}. 지원 형식: mp3, mp4, m4a, wav"
        )

    service = MeetingService(supabase)
    meeting = await service.create_meeting(
        user_id=current_user["id"],
        title=title,
        file=file,
    )

    # 비동기로 AI 처리 시작
    background_tasks.add_task(service.process_meeting, meeting["id"])

    return MeetingSummaryResponse(**meeting)


@router.get("/{meeting_id}", response_model=MeetingSummaryResponse)
async def get_meeting(
    meeting_id: str,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """미팅 요약 결과 조회"""
    service = MeetingService(supabase)
    meeting = await service.get_meeting(meeting_id, current_user["id"])
    if not meeting:
        raise HTTPException(status_code=404, detail="미팅을 찾을 수 없습니다")
    return MeetingSummaryResponse(**meeting)


@router.get("/{meeting_id}/stream")
async def stream_meeting_status(
    meeting_id: str,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """SSE로 미팅 처리 상태 스트리밍"""
    service = MeetingService(supabase)

    async def event_generator():
        async for event in service.stream_status(meeting_id, current_user["id"]):
            yield f"data: {event}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


@router.get("/", response_model=list[MeetingSummaryResponse])
async def list_meetings(
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """내 미팅 목록 조회"""
    service = MeetingService(supabase)
    meetings = await service.list_meetings(current_user["id"], limit=limit)
    return [MeetingSummaryResponse(**m) for m in meetings]

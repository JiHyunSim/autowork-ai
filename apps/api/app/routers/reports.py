"""보고서 자동 생성 라우터"""
from fastapi import APIRouter, Depends, HTTPException
from supabase import Client
from pydantic import BaseModel
from typing import Optional
from datetime import date

from app.core.deps import get_current_user, get_supabase
from app.services.report_service import ReportService

router = APIRouter()


class ReportInput(BaseModel):
    title: str
    report_type: str = "weekly"  # weekly | daily | custom
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    team_inputs: list[dict]  # [{member_name, completed, in_progress, planned}]


class ReportResponse(BaseModel):
    id: str
    title: str
    report_type: str
    status: str
    content: Optional[str] = None


@router.post("/generate", response_model=ReportResponse)
async def generate_report(
    request: ReportInput,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """AI 보고서 자동 생성"""
    service = ReportService(supabase)
    report = await service.generate_report(
        user_id=current_user["id"],
        title=request.title,
        report_type=request.report_type,
        period_start=request.period_start,
        period_end=request.period_end,
        team_inputs=request.team_inputs,
    )
    return ReportResponse(**report)


@router.get("/{report_id}", response_model=ReportResponse)
async def get_report(
    report_id: str,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """보고서 조회"""
    result = supabase.table("reports").select("*").eq("id", report_id).eq("created_by", current_user["id"]).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="보고서를 찾을 수 없습니다")
    return ReportResponse(**result.data)


@router.get("/", response_model=list[ReportResponse])
async def list_reports(
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """보고서 목록 조회"""
    result = supabase.table("reports").select("*").eq("created_by", current_user["id"]).order("created_at", desc=True).limit(limit).execute()
    return [ReportResponse(**r) for r in (result.data or [])]

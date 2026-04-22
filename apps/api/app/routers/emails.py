"""이메일/제안서 자동 작성 라우터"""
from fastapi import APIRouter, Depends, HTTPException
from supabase import Client
from pydantic import BaseModel
from typing import Optional

from app.core.deps import get_current_user, get_supabase
from app.services.email_service import EmailService

router = APIRouter()


class EmailGenerateRequest(BaseModel):
    email_type: str  # cold | follow_up | thank_you | proposal
    recipient_name: str
    recipient_company: str
    context: Optional[str] = None
    language: str = "ko"  # ko | en | both


class EmailResponse(BaseModel):
    subject: str
    body: str
    language: str


@router.post("/generate", response_model=EmailResponse)
async def generate_email(
    request: EmailGenerateRequest,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """AI 이메일/제안서 자동 생성"""
    service = EmailService(supabase)
    result = await service.generate_email(
        user_id=current_user["id"],
        email_type=request.email_type,
        recipient_name=request.recipient_name,
        recipient_company=request.recipient_company,
        context=request.context,
        language=request.language,
    )
    return EmailResponse(**result)

"""인증 라우터 — Supabase Auth 기반"""
from fastapi import APIRouter, Depends, HTTPException
from supabase import Client
from pydantic import BaseModel, EmailStr

from app.core.deps import get_supabase

router = APIRouter()


class SignUpRequest(BaseModel):
    email: EmailStr
    password: str
    name: str


class SignInRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    user: dict


@router.post("/signup", response_model=AuthResponse)
async def sign_up(request: SignUpRequest, supabase: Client = Depends(get_supabase)):
    """이메일 회원가입"""
    try:
        response = supabase.auth.sign_up({
            "email": request.email,
            "password": request.password,
            "options": {
                "data": {"name": request.name}
            }
        })

        if not response.user:
            raise HTTPException(status_code=400, detail="회원가입 실패")

        # 기본 팀 생성
        team_result = supabase.table("teams").insert({
            "name": f"{request.name}의 팀",
            "plan": "starter",
            "owner_id": response.user.id,
        }).execute()

        team_id = team_result.data[0]["id"]

        # 팀 멤버 추가
        supabase.table("team_members").insert({
            "team_id": team_id,
            "user_id": response.user.id,
            "role": "owner",
        }).execute()

        # 14일 무료 체험 구독 생성
        from datetime import datetime, timedelta
        trial_end = (datetime.utcnow() + timedelta(days=14)).isoformat()
        supabase.table("subscriptions").insert({
            "team_id": team_id,
            "plan": "starter",
            "status": "trialing",
            "trial_end": trial_end,
        }).execute()

        return AuthResponse(
            access_token=response.session.access_token if response.session else "",
            user={"id": response.user.id, "email": response.user.email},
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/signin", response_model=AuthResponse)
async def sign_in(request: SignInRequest, supabase: Client = Depends(get_supabase)):
    """이메일 로그인"""
    try:
        response = supabase.auth.sign_in_with_password({
            "email": request.email,
            "password": request.password,
        })

        if not response.user or not response.session:
            raise HTTPException(status_code=401, detail="로그인 실패")

        return AuthResponse(
            access_token=response.session.access_token,
            user={"id": response.user.id, "email": response.user.email},
        )
    except Exception as e:
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다")


@router.post("/signout")
async def sign_out(supabase: Client = Depends(get_supabase)):
    """로그아웃"""
    supabase.auth.sign_out()
    return {"message": "로그아웃 성공"}

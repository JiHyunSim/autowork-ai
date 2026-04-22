"""보고서 자동 생성 서비스 — Claude Sonnet 4.6"""
import json
from typing import Optional
from datetime import date
from supabase import Client
import anthropic

from app.core.config import settings

WEEKLY_REPORT_PROMPT = """당신은 한국 기업의 전문 보고서 작성자입니다.
아래 팀원별 업무 현황을 취합하여 체계적인 주간 업무 보고서를 작성하세요.

**보고서 형식**:
1. 이번 주 팀 성과 요약 (3~5문장)
2. 팀원별 완료 업무
3. 진행 중인 주요 업무
4. 다음 주 계획
5. 이슈 및 리스크 (있는 경우)

**팀원 업무 현황**:
{team_inputs}

보고서 제목: {title}
기간: {period}

한국어로 전문적이고 간결하게 작성하세요.
"""

DAILY_STANDUP_PROMPT = """아래 팀원 업무 내용을 취합하여 간결한 데일리 스탠드업 요약을 작성하세요.

형식:
- 어제 완료한 일
- 오늘 할 일
- 블로커 (있는 경우)

{team_inputs}
"""


class ReportService:
    def __init__(self, supabase: Client):
        self.supabase = supabase
        self.anthropic = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    async def generate_report(
        self,
        user_id: str,
        title: str,
        report_type: str,
        period_start: Optional[date],
        period_end: Optional[date],
        team_inputs: list[dict],
    ) -> dict:
        """Claude Sonnet 4.6으로 보고서 생성"""
        # DB에 초기 레코드 생성
        team_id = await self._get_user_team(user_id)
        result = self.supabase.table("reports").insert({
            "team_id": team_id,
            "created_by": user_id,
            "title": title,
            "report_type": report_type,
            "period_start": str(period_start) if period_start else None,
            "period_end": str(period_end) if period_end else None,
            "status": "generating",
        }).execute()
        report_id = result.data[0]["id"]

        # 팀원 입력 포맷
        inputs_text = "\n\n".join([
            f"**{inp.get('member_name', '팀원')}**:\n"
            f"- 완료: {inp.get('completed', '없음')}\n"
            f"- 진행 중: {inp.get('in_progress', '없음')}\n"
            f"- 예정: {inp.get('planned', '없음')}"
            for inp in team_inputs
        ])

        # 프롬프트 선택
        if report_type == "daily":
            prompt = DAILY_STANDUP_PROMPT.format(team_inputs=inputs_text)
        else:
            period_str = ""
            if period_start and period_end:
                period_str = f"{period_start} ~ {period_end}"
            prompt = WEEKLY_REPORT_PROMPT.format(
                team_inputs=inputs_text,
                title=title,
                period=period_str,
            )

        # Claude Sonnet 4.6 호출
        message = self.anthropic.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}],
        )

        content = message.content[0].text

        # DB 업데이트
        self.supabase.table("reports").update({
            "content": content,
            "status": "done",
        }).eq("id", report_id).execute()

        return {
            "id": report_id,
            "title": title,
            "report_type": report_type,
            "status": "done",
            "content": content,
        }

    async def _get_user_team(self, user_id: str) -> str:
        result = self.supabase.table("team_members").select("team_id").eq("user_id", user_id).limit(1).single().execute()
        return result.data["team_id"]

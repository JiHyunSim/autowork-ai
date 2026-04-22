"""이메일/제안서 자동 작성 서비스 — Claude Sonnet 4.6"""
from supabase import Client
import anthropic

from app.core.config import settings

EMAIL_PROMPTS = {
    "cold": """당신은 한국 B2B 영업 전문가입니다.
아래 정보를 바탕으로 자연스럽고 전문적인 첫 영업 이메일을 작성하세요.

수신자: {recipient_name} ({recipient_company})
추가 컨텍스트: {context}

이메일은 다음 구조로 작성:
1. 간결한 자기소개 (1~2문장)
2. 상대방 회사에 맞춘 가치 제안 (2~3문장)
3. 다음 단계 제안 (미팅, 데모 요청)

제목과 본문을 JSON 형식으로 반환: {{"subject": "...", "body": "..."}}""",

    "follow_up": """이전 대화 이후 후속 이메일을 작성하세요.
수신자: {recipient_name} ({recipient_company})
컨텍스트: {context}

간결하고 action-oriented하게 작성. JSON 반환: {{"subject": "...", "body": "..."}}""",

    "proposal": """아래 정보를 바탕으로 전문적인 사업 제안서 이메일을 작성하세요.
수신자: {recipient_name} ({recipient_company})
제안 내용: {context}

구조:
1. 요약 (Executive Summary)
2. 문제 정의
3. 솔루션 제안
4. 기대 효과
5. 다음 단계

JSON 반환: {{"subject": "...", "body": "..."}}""",
}


class EmailService:
    def __init__(self, supabase: Client):
        self.supabase = supabase
        self.anthropic = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    async def generate_email(
        self,
        user_id: str,
        email_type: str,
        recipient_name: str,
        recipient_company: str,
        context: str | None,
        language: str = "ko",
    ) -> dict:
        """Claude Sonnet 4.6으로 이메일 생성"""
        prompt_template = EMAIL_PROMPTS.get(email_type, EMAIL_PROMPTS["cold"])
        prompt = prompt_template.format(
            recipient_name=recipient_name,
            recipient_company=recipient_company,
            context=context or "없음",
        )

        if language == "en":
            prompt += "\n\n영어로 작성하세요."
        elif language == "both":
            prompt += "\n\n한국어 버전과 영어 버전을 모두 작성하세요. JSON 키: ko_subject, ko_body, en_subject, en_body"

        message = self.anthropic.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )

        import json
        content = message.content[0].text

        # JSON 파싱 시도
        try:
            # 코드 블록 제거
            clean = content.replace("```json", "").replace("```", "").strip()
            parsed = json.loads(clean)
            return {
                "subject": parsed.get("subject", ""),
                "body": parsed.get("body", content),
                "language": language,
            }
        except json.JSONDecodeError:
            return {
                "subject": f"[{email_type.upper()}] {recipient_company} 제안",
                "body": content,
                "language": language,
            }

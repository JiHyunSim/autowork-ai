"""Claude API 커넥터 (claude-sonnet-4-6)"""
import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential
import structlog

from src.config import settings

logger = structlog.get_logger(__name__)


class ClaudeConnector:
    """Anthropic Claude API 연동 클래스"""

    def __init__(self) -> None:
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = settings.claude_model

    @retry(
        stop=stop_after_attempt(settings.claude_max_retries),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> str:
        """Claude API 호출 — 텍스트 생성"""
        logger.info("claude.generate", model=self.model, max_tokens=max_tokens)

        # 프롬프트 캐싱 활성화 (반복 system prompt 비용 절감)
        message = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_prompt}],
        )

        result = message.content[0].text
        logger.info(
            "claude.generate.done",
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
        )
        return result

    def generate_blog_post(self, topic: str, keywords: list[str]) -> dict:
        """블로그 포스트 생성"""
        system = (
            "당신은 한국 독자를 위한 SEO 최적화 블로그 포스트를 작성하는 전문 작가입니다. "
            "마크다운 형식으로 작성하며, 제목(H1), 소제목(H2/H3), 본문, 결론을 포함합니다. "
            "자연스러운 한국어를 사용하고, SEO를 위해 키워드를 적절히 배치합니다."
        )
        user = (
            f"주제: {topic}\n"
            f"핵심 키워드: {', '.join(keywords)}\n\n"
            "다음 형식으로 블로그 포스트를 작성해주세요:\n"
            "1. SEO 최적화 제목 (H1, 60자 이내)\n"
            "2. 메타 설명 (160자 이내)\n"
            "3. 본문 (1500~2000자, H2/H3 소제목 포함)\n"
            "4. 결론 및 CTA\n\n"
            "JSON 형식으로 반환: {\"title\": \"...\", \"meta_description\": \"...\", \"content\": \"...\", \"tags\": [...]}"
        )
        import json
        raw = self.generate(system, user, max_tokens=3000)
        # JSON 파싱 (마크다운 코드블록 제거)
        raw = raw.strip().removeprefix("```json").removesuffix("```").strip()
        return json.loads(raw)

    def generate_youtube_script(self, topic: str, keywords: list[str]) -> dict:
        """유튜브 스크립트 + 메타데이터 생성"""
        system = (
            "당신은 한국 유튜브 채널을 위한 영상 스크립트와 메타데이터를 작성하는 전문가입니다. "
            "시청자의 관심을 끄는 훅(Hook), 본론, 결론 구조로 작성합니다."
        )
        user = (
            f"주제: {topic}\n"
            f"핵심 키워드: {', '.join(keywords)}\n\n"
            "다음을 JSON으로 반환:\n"
            "{\n"
            '  "title": "유튜브 제목 (60자 이내, 클릭 유도)",\n'
            '  "description": "영상 설명 (500자, SEO 키워드 포함)",\n'
            '  "tags": ["태그1", "태그2", ...],\n'
            '  "script": "영상 스크립트 (5~7분 분량)",\n'
            '  "thumbnail_concept": "썸네일 컨셉 설명"\n'
            "}"
        )
        import json
        raw = self.generate(system, user, max_tokens=4000)
        raw = raw.strip().removeprefix("```json").removesuffix("```").strip()
        return json.loads(raw)

    def generate_reels_caption(self, topic: str, keywords: list[str]) -> dict:
        """인스타그램 릴스 캡션 + 해시태그 생성"""
        system = (
            "당신은 한국 인스타그램 릴스를 위한 캡션과 해시태그를 작성하는 소셜 미디어 전문가입니다. "
            "짧고 임팩트 있는 문구와 최적의 해시태그를 사용합니다."
        )
        user = (
            f"주제: {topic}\n"
            f"핵심 키워드: {', '.join(keywords)}\n\n"
            "다음을 JSON으로 반환:\n"
            "{\n"
            '  "caption": "릴스 캡션 (150자 이내, 이모지 포함)",\n'
            '  "hashtags": ["#태그1", "#태그2", ...],\n'
            '  "video_concept": "30초 릴스 영상 컨셉 설명"\n'
            "}"
        )
        import json
        raw = self.generate(system, user, max_tokens=1000)
        raw = raw.strip().removeprefix("```json").removesuffix("```").strip()
        return json.loads(raw)

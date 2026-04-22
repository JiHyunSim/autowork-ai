"""
credential_check.py — 외부 API 인증정보 사전 검증 스크립트

에이전트는 외부 API가 필요한 작업 시작 전 반드시 이 스크립트를 실행합니다.
누락된 인증정보가 있으면 exit(1)로 종료됩니다.

사용법:
    python check_credentials.py                  # 전체 검사
    python check_credentials.py --group youtube  # 특정 서비스만
"""
import os
import sys
import argparse
from pathlib import Path

# .env.local 자동 로드
ENV_FILE = Path("/Users/jihyunsim/jarvis/.env.local")

def load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    result = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip()
    return result

# 서비스별 필수 인증정보 정의
CREDENTIAL_GROUPS = {
    "anthropic": {
        "label": "Anthropic (Claude API)",
        "required": ["ANTHROPIC_API_KEY"],
        "how_to_get": "https://console.anthropic.com → API Keys",
    },
    "youtube": {
        "label": "YouTube Data API v3",
        "required": [
            "YOUTUBE_CLIENT_ID",
            "YOUTUBE_CLIENT_SECRET",
            "YOUTUBE_REFRESH_TOKEN",
            "YOUTUBE_CHANNEL_ID",
        ],
        "how_to_get": "Google Cloud Console → API & Services → YouTube Data API v3 → OAuth 2.0 클라이언트 생성",
    },
    "wordpress": {
        "label": "WordPress REST API",
        "required": [
            "WORDPRESS_URL",
            "WORDPRESS_USER",
            "WORDPRESS_APP_PASSWORD",
        ],
        "how_to_get": "WordPress 관리자 > Users > Profile > Application Passwords 생성",
    },
    "instagram": {
        "label": "Instagram Graph API",
        "required": [
            "INSTAGRAM_ACCESS_TOKEN",
            "INSTAGRAM_BUSINESS_ACCOUNT_ID",
            "FACEBOOK_APP_ID",
            "FACEBOOK_APP_SECRET",
        ],
        "how_to_get": "Facebook 개발자 콘솔 → 앱 생성 → Instagram Graph API 연동 (비즈니스 계정 필요)",
    },
    "coupang": {
        "label": "쿠팡 파트너스 API",
        "required": ["COUPANG_ACCESS_KEY", "COUPANG_SECRET_KEY"],
        "how_to_get": "https://partners.coupang.com → 마이페이지 → API 관리",
    },
    "naver": {
        "label": "네이버 DataLab",
        "required": ["NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET"],
        "how_to_get": "https://developers.naver.com → 애플리케이션 등록 → DataLab 검색어 트렌드 권한",
    },
    "supabase": {
        "label": "Supabase",
        "required": ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"],
        "how_to_get": "https://supabase.com → 프로젝트 생성 → Settings → API",
    },
    "slack": {
        "label": "Slack 알림",
        "required": ["SLACK_WEBHOOK_URL"],
        "how_to_get": "Slack 워크스페이스 → 앱 추가 → Incoming Webhooks → 채널 선택",
    },
}


def check_credentials(groups: list[str] | None = None) -> dict:
    """
    인증정보 검사 실행.
    Returns: {"ok": bool, "missing": [{group, label, keys, how_to_get}]}
    """
    env = load_env_file(ENV_FILE)
    # 환경변수도 확인 (docker/CI 환경 지원)
    for key in list(env.keys()):
        if not env[key]:
            env_val = os.environ.get(key, "")
            if env_val:
                env[key] = env_val

    target_groups = groups or list(CREDENTIAL_GROUPS.keys())
    missing = []

    for group_key in target_groups:
        if group_key not in CREDENTIAL_GROUPS:
            continue
        group = CREDENTIAL_GROUPS[group_key]
        missing_keys = [
            k for k in group["required"]
            if not env.get(k) and not os.environ.get(k)
        ]
        if missing_keys:
            missing.append({
                "group": group_key,
                "label": group["label"],
                "missing_keys": missing_keys,
                "how_to_get": group["how_to_get"],
            })

    return {"ok": len(missing) == 0, "missing": missing, "env_file": str(ENV_FILE)}


def print_report(result: dict) -> None:
    if result["ok"]:
        print("✅ 모든 인증정보가 설정되어 있습니다.")
        return

    print(f"❌ 누락된 인증정보가 있습니다. ({ENV_FILE})")
    print()
    for item in result["missing"]:
        print(f"  [{item['label']}]")
        for key in item["missing_keys"]:
            print(f"    - {key}")
        print(f"    발급 방법: {item['how_to_get']}")
        print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="인증정보 사전 검증")
    parser.add_argument(
        "--group",
        nargs="+",
        choices=list(CREDENTIAL_GROUPS.keys()),
        help="검사할 서비스 그룹 (생략 시 전체)",
    )
    parser.add_argument("--json", action="store_true", help="JSON 출력")
    args = parser.parse_args()

    result = check_credentials(args.group)

    if args.json:
        import json
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_report(result)

    sys.exit(0 if result["ok"] else 1)

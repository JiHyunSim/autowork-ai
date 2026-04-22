"""pytest 설정 — 환경 변수를 컬렉션 전에 설정"""
import os


def pytest_configure(config):
    """컬렉션 전에 필수 환경 변수 더미값 주입 (settings 모듈 임포트 타임에 필요)."""
    defaults = {
        "ANTHROPIC_API_KEY": "test-anthropic-key",
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "test-service-role-key",
    }
    for k, v in defaults.items():
        os.environ.setdefault(k, v)

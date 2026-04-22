"""Supabase 클라이언트 유틸리티"""
from functools import lru_cache
from supabase import create_client, Client

from src.config import settings


@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    """Supabase 클라이언트 싱글턴 반환"""
    return create_client(settings.supabase_url, settings.supabase_service_role_key)

"""
Supabase client singleton for database operations.
"""
from functools import lru_cache
from supabase import create_client, Client
import logfire

from backend.config.settings import settings


@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    """
    Returns a singleton Supabase client instance.
    Uses lru_cache to ensure only one client is created.
    Uses service role key if available, otherwise anon key.
    """
    key = settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_ANON_KEY
    logfire.info("Initializing Supabase client", url=settings.SUPABASE_URL)
    return create_client(settings.SUPABASE_URL, key)


def get_supabase() -> Client:
    """
    Dependency injection helper for FastAPI routes.
    Returns the singleton Supabase client.
    """
    return get_supabase_client()

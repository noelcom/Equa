from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

import anthropic
from fastapi import Depends, Header, HTTPException, status
from supabase import Client, create_client
from supabase_auth.errors import AuthError

from equa_backend.config import get_settings


@lru_cache
def get_supabase() -> Client:
    """Backendens klient mot Supabase, med service_role-nyckeln (ADR 0002)."""
    s = get_settings()
    return create_client(s.supabase_url, s.supabase_service_role_key)


def get_anthropic_client() -> anthropic.Anthropic:
    """Enda externa gränsen utöver Supabase. Ersätts av en fejk i testerna."""
    # Omförsöken sköts av pipelinen (med tydlig orsak vid slutligt fel), inte av SDK:t.
    return anthropic.Anthropic(api_key=get_settings().anthropic_api_key, max_retries=0)


@dataclass(frozen=True)
class CurrentUser:
    id: str


def get_current_user(
    supabase: Annotated[Client, Depends(get_supabase)],
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser:
    """Verifierar Supabase-token mot Supabase Auth och returnerar användaren."""
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Inte inloggad.")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise unauthorized
    token = authorization.split(" ", 1)[1].strip()
    try:
        res = supabase.auth.get_user(token)
    except AuthError:
        raise unauthorized from None
    if res is None or res.user is None:
        raise unauthorized
    return CurrentUser(id=res.user.id)

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from supabase import Client

from equa_backend.config import Settings, get_settings
from equa_backend.deps import CurrentUser, get_current_user, get_supabase
from equa_backend.quota import next_reset, remaining
from equa_backend.retention import default_retention_days, max_retention_days

router = APIRouter()


class Quota(BaseModel):
    limit: int
    # Kvoten minus månadens lyckade och de reserverade CV:na (GLOSSARY: Återstående kvot).
    remaining: int
    # När kvoten fylls på (första dagen i nästa månad, UTC).
    resets_at: datetime


class MeResponse(BaseModel):
    quota: Quota
    default_retention_days: int
    max_retention_days: int
    max_file_size_mb: int


@router.get("/me", response_model=MeResponse)
def me(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    supabase: Annotated[Client, Depends(get_supabase)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MeResponse:
    # Profilen skapas vid första inloggning med standardgränserna.
    supabase.table("profiles").upsert(
        {"id": user.id}, on_conflict="id", ignore_duplicates=True
    ).execute()
    row = (
        supabase.table("profiles").select("*").eq("id", user.id).single().execute().data
    )
    limit = row["cv_quota_limit"]
    stale_before = datetime.now(UTC) - timedelta(minutes=settings.stale_cv_minutes)
    return MeResponse(
        quota=Quota(
            limit=limit,
            remaining=remaining(supabase, user.id, limit, stale_before),
            resets_at=next_reset(),
        ),
        default_retention_days=default_retention_days(row),
        max_retention_days=max_retention_days(row),
        max_file_size_mb=row["max_file_size_mb"],
    )

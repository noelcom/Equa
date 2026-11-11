from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from supabase import Client

from equa_backend.config import Settings, get_settings
from equa_backend.deps import CurrentUser, get_current_user, get_supabase
from equa_backend.quota import remaining, used_this_month

router = APIRouter()


class Quota(BaseModel):
    limit: int
    used: int
    remaining: int


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
    used = used_this_month(supabase, user.id)
    stale_before = datetime.now(UTC) - timedelta(minutes=settings.stale_cv_minutes)
    return MeResponse(
        quota=Quota(
            limit=limit,
            used=used,
            remaining=remaining(supabase, user.id, limit, stale_before),
        ),
        default_retention_days=row["default_retention_days"],
        max_retention_days=row["max_retention_days"],
        max_file_size_mb=row["max_file_size_mb"],
    )

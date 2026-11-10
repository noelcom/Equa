from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from supabase import Client

from equa_backend.deps import CurrentUser, get_current_user, get_supabase

router = APIRouter()


class Quota(BaseModel):
    limit: int
    used: int


class MeResponse(BaseModel):
    quota: Quota
    default_retention_days: int
    max_retention_days: int
    max_file_size_mb: int


@router.get("/me", response_model=MeResponse)
def me(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    supabase: Annotated[Client, Depends(get_supabase)],
) -> MeResponse:
    # Profilen skapas vid första inloggning med standardgränserna.
    supabase.table("profiles").upsert(
        {"id": user.id}, on_conflict="id", ignore_duplicates=True
    ).execute()
    row = (
        supabase.table("profiles").select("*").eq("id", user.id).single().execute().data
    )
    return MeResponse(
        # Förbrukning räknas först när kandidater och användningslogg finns (#4, #7).
        quota=Quota(limit=row["cv_quota_limit"], used=0),
        default_retention_days=row["default_retention_days"],
        max_retention_days=row["max_retention_days"],
        max_file_size_mb=row["max_file_size_mb"],
    )

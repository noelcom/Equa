import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from supabase import Client

from equa_backend.deps import CurrentUser, get_current_user, get_supabase

router = APIRouter(prefix="/analyses")

BUCKET = "originals"
PDF_MAGIC = b"%PDF-"


class CandidateOut(BaseModel):
    # Anonym alias. Originalfilnamn visas aldrig (ADR 0004).
    alias: str


class AnalysisOut(BaseModel):
    id: str
    title: str
    job_ad: str
    expires_at: datetime
    created_at: datetime
    candidates: list[CandidateOut]


class AnalysisSummary(BaseModel):
    id: str
    title: str
    expires_at: datetime
    created_at: datetime
    candidate_count: int


def _alias(number: int) -> str:
    return f"Kandidat #{number}"


def _to_out(analysis: dict, candidates: list[dict]) -> AnalysisOut:
    return AnalysisOut(
        id=analysis["id"],
        title=analysis["title"],
        job_ad=analysis["job_ad"],
        expires_at=analysis["expires_at"],
        created_at=analysis["created_at"],
        candidates=[
            CandidateOut(alias=_alias(c["number"]))
            for c in sorted(candidates, key=lambda c: c["number"])
        ],
    )


def _profile(supabase: Client, user: CurrentUser) -> dict:
    # Profilen skapas vid första inloggning, men skapas här också ifall /me inte anropats.
    supabase.table("profiles").upsert(
        {"id": user.id}, on_conflict="id", ignore_duplicates=True
    ).execute()
    return (
        supabase.table("profiles").select("*").eq("id", user.id).single().execute().data
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=AnalysisOut)
def create_analysis(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    supabase: Annotated[Client, Depends(get_supabase)],
    title: Annotated[str, Form()],
    job_ad: Annotated[str, Form()],
    files: list[UploadFile],
) -> AnalysisOut:
    title, job_ad = title.strip(), job_ad.strip()
    if not title or not job_ad or not files:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Titel, arbetsannons och minst ett CV krävs.",
        )

    profile = _profile(supabase, user)
    max_bytes = profile["max_file_size_mb"] * 1024 * 1024

    # Validera alla filer innan något sparas, så en avvisad fil inte lämnar halva analyser.
    contents: list[bytes] = []
    for number, f in enumerate(files, start=1):
        # Vanlig def-endpoint: blockerande I/O körs i trådpool, inte på event-loopen.
        data = f.file.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE,
                f"Kandidat #{number} är större än den tillåtna filstorleken "
                f"på {profile['max_file_size_mb']} MB. Inga CV:n sparades.",
            )
        if not data.startswith(PDF_MAGIC):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Kandidat #{number} är inte en PDF-fil. Bara PDF stöds. Inga CV:n sparades.",
            )
        contents.append(data)

    expires_at = datetime.now(UTC) + timedelta(days=profile["default_retention_days"])
    analysis = (
        supabase.table("analysis_batches")
        .insert(
            {
                "user_id": user.id,
                "title": title,
                "job_ad": job_ad,
                "expires_at": expires_at.isoformat(),
            }
        )
        .execute()
        .data[0]
    )

    stored: list[str] = []
    try:
        rows = []
        for number, data in enumerate(contents, start=1):
            # Sökvägen innehåller aldrig originalfilnamnet.
            path = f"{user.id}/{analysis['id']}/{uuid.uuid4().hex}.pdf"
            # Registrera sökvägen före uppladdningen så en halvfärdig fil också städas.
            stored.append(path)
            supabase.storage.from_(BUCKET).upload(
                path, data, {"content-type": "application/pdf"}
            )
            rows.append(
                {"analysis_id": analysis["id"], "number": number, "original_path": path}
            )
        candidates = supabase.table("candidates").insert(rows).execute().data
    except Exception:
        # Städa upp så en misslyckad uppladdning inte lämnar kvar filer eller en tom analys.
        if stored:
            supabase.storage.from_(BUCKET).remove(stored)
        supabase.table("analysis_batches").delete().eq("id", analysis["id"]).execute()
        raise
    return _to_out(analysis, candidates)


@router.get("", response_model=list[AnalysisSummary])
def list_analyses(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    supabase: Annotated[Client, Depends(get_supabase)],
) -> list[AnalysisSummary]:
    rows = (
        supabase.table("analysis_batches")
        .select("id, title, expires_at, created_at, candidates(count)")
        .eq("user_id", user.id)
        .order("created_at", desc=True)
        .execute()
        .data
    )
    return [
        AnalysisSummary(
            id=r["id"],
            title=r["title"],
            expires_at=r["expires_at"],
            created_at=r["created_at"],
            candidate_count=r["candidates"][0]["count"],
        )
        for r in rows
    ]


@router.get("/{analysis_id}", response_model=AnalysisOut)
def get_analysis(
    analysis_id: uuid.UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    supabase: Annotated[Client, Depends(get_supabase)],
) -> AnalysisOut:
    # Filtrera på user_id: andras analyser ser ut som att de inte finns.
    rows = (
        supabase.table("analysis_batches")
        .select("*, candidates(number)")
        .eq("id", str(analysis_id))
        .eq("user_id", user.id)
        .execute()
        .data
    )
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Analysen finns inte.")
    return _to_out(rows[0], rows[0]["candidates"])

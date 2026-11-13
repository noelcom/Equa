import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

import anthropic
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import Response
from postgrest.exceptions import APIError
from pydantic import BaseModel
from storage3.exceptions import StorageException
from supabase import Client

from equa_backend import pipeline
from equa_backend.candidates import (
    FINISHED,
    IN_FLIGHT,
    Candidate,
    CandidateStatus,
    PipelineStep,
)
from equa_backend.config import Settings, get_settings
from equa_backend.deps import (
    CurrentUser,
    get_anthropic_client,
    get_current_user,
    get_supabase,
)
from equa_backend.export import XLSX_MEDIA_TYPE, build_workbook
from equa_backend.pipeline import BUCKET, Assessment
from equa_backend.quota import QuotaSnapshot, snapshot
from equa_backend.retention import (
    default_retention_days,
    delete_analysis,
    max_retention_days,
)

router = APIRouter(prefix="/analyses")

PDF_MAGIC = b"%PDF-"
# Postgres felkod för brott mot en unik-begränsning.
UNIQUE_VIOLATION = "23505"
FOREIGN_KEY_VIOLATION = "23503"


class CandidateOut(BaseModel):
    # Anonym alias. Originalfilnamn visas aldrig (ADR 0007).
    alias: str
    # Löpnummer i analysen. Adresserar kandidaten, t.ex. vid avslöja.
    number: int
    status: CandidateStatus
    # Aktuellt pipelinesteg medan kandidaten bearbetas.
    step: PipelineStep | None
    assessment: Assessment | None
    failure_reason: str | None


class Progress(BaseModel):
    total: int
    # Färdiga, antingen bedömda eller "kunde inte analyseras".
    finished: int


class AnalysisOut(BaseModel):
    id: str
    title: str
    job_ad: str
    expires_at: datetime
    created_at: datetime
    # ready: det finns CV:n att köra. running: en körning pågår. finished: inget mer att köra.
    state: Literal["ready", "running", "finished"]
    # CV:n som nästa körning tar: uppladdade, plus fastnade (se Candidate.is_runnable).
    runnable_count: int
    # Räcker kvoten till en körning av runnable_count CV:n?
    can_run: bool
    # Så många CV:n till kan läggas till utan att kvoten överskrids.
    addable_count: int
    progress: Progress
    # Leaderboard: bedömda kandidater efter poäng (högst först), därefter övriga
    # i nummerordning. Ingen kandidat filtreras bort (ADR 0003).
    candidates: list[CandidateOut]


class AnalysisSummary(BaseModel):
    id: str
    title: str
    expires_at: datetime
    created_at: datetime
    candidate_count: int


def _candidates(rows: list[dict]) -> list[Candidate]:
    return [Candidate.model_validate(row) for row in rows]


def _alias(number: int) -> str:
    return f"Kandidat #{number}"


def _candidate_out(c: Candidate) -> CandidateOut:
    assessment = None
    if c.status == "done":
        assessment = Assessment(
            score=c.score,
            years_experience=c.years_experience,
            education_match=c.education_match,
            concrete_results=c.concrete_results,
            key_skills=c.key_skills,
            missing_requirements=c.missing_requirements,
            rationale=c.rationale,
        )
    return CandidateOut(
        alias=_alias(c.number),
        number=c.number,
        status=c.status,
        step=c.step,
        assessment=assessment,
        failure_reason=c.failure_reason,
    )


def _rank_key(c: Candidate) -> tuple:
    # Bedömda först, högst poäng överst. Övriga (pågår, ej körda, misslyckade) efter, i nummerordning.
    if c.status == "done":
        return (0, -(c.score or 0), c.number)
    return (1, 0, c.number)


def _state(candidates: list[Candidate]) -> Literal["ready", "running", "finished"]:
    if any(c.status in IN_FLIGHT for c in candidates):
        return "running"
    if any(c.status == "uploaded" for c in candidates):
        return "ready"
    return "finished"


def _to_out(
    analysis: dict, candidates: list[Candidate], quota: QuotaSnapshot
) -> AnalysisOut:
    return AnalysisOut(
        id=analysis["id"],
        title=analysis["title"],
        job_ad=analysis["job_ad"],
        expires_at=analysis["expires_at"],
        created_at=analysis["created_at"],
        state=_state(candidates),
        runnable_count=quota.runnable_count(candidates),
        can_run=quota.can_run(candidates),
        addable_count=quota.addable_count(candidates),
        progress=Progress(
            total=len(candidates),
            finished=sum(c.status in FINISHED for c in candidates),
        ),
        candidates=[_candidate_out(c) for c in sorted(candidates, key=_rank_key)],
    )


def _profile(supabase: Client, user: CurrentUser) -> dict:
    # Profilen skapas vid första inloggning, men skapas här också ifall /me inte anropats.
    supabase.table("profiles").upsert(
        {"id": user.id}, on_conflict="id", ignore_duplicates=True
    ).execute()
    return (
        supabase.table("profiles").select("*").eq("id", user.id).single().execute().data
    )


def _quota(
    supabase: Client, user: CurrentUser, settings: Settings, profile: dict | None = None
) -> QuotaSnapshot:
    profile = profile or _profile(supabase, user)
    stale_before = datetime.now(UTC) - timedelta(minutes=settings.stale_cv_minutes)
    return snapshot(supabase, user.id, profile["cv_quota_limit"], stale_before)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=AnalysisOut)
def create_analysis(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    supabase: Annotated[Client, Depends(get_supabase)],
    settings: Annotated[Settings, Depends(get_settings)],
    title: Annotated[str, Form()],
    job_ad: Annotated[str, Form()],
    files: list[UploadFile],
    expires_at: Annotated[datetime | None, Form()] = None,
) -> AnalysisOut:
    title, job_ad = title.strip(), job_ad.strip()
    if not title or not job_ad or not files:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Titel, arbetsannons och minst ett CV krävs.",
        )

    profile = _profile(supabase, user)
    contents = _read_pdfs(files, profile, first_number=1)
    quota = _quota(supabase, user, settings, profile)
    _check_quota(quota, [], "create", adding=len(contents))

    now = datetime.now(UTC)
    if expires_at is None:
        expires_at = now + timedelta(days=default_retention_days(profile))
    else:
        expires_at = _checked_expiry(expires_at, profile)
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

    try:
        candidates = _store_candidates(
            supabase, user, analysis["id"], contents, first_number=1
        )
    except Exception:
        # Städa upp så en misslyckad uppladdning inte lämnar kvar en tom analys.
        supabase.table("analysis_batches").delete().eq("id", analysis["id"]).execute()
        raise
    return _to_out(analysis, candidates, quota)


@router.post(
    "/{analysis_id}/candidates",
    status_code=status.HTTP_201_CREATED,
    response_model=AnalysisOut,
)
def add_candidates(
    analysis_id: uuid.UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    supabase: Annotated[Client, Depends(get_supabase)],
    settings: Annotated[Settings, Depends(get_settings)],
    files: list[UploadFile],
) -> AnalysisOut:
    """Lägger till CV:n i en befintlig analys. De körs sedan via /run mot samma annons.

    Raderingsdatumet ändras inte.
    """
    analysis = _live_analysis(supabase, user, analysis_id)
    existing = _candidates(analysis["candidates"])
    first_number = max((c.number for c in existing), default=0) + 1
    profile = _profile(supabase, user)
    contents = _read_pdfs(files, profile, first_number)
    quota = _quota(supabase, user, settings, profile)
    _check_quota(quota, existing, "add", adding=len(contents))
    try:
        added = _store_candidates(
            supabase, user, analysis["id"], contents, first_number
        )
    except APIError as e:
        if e.code == FOREIGN_KEY_VIOLATION:
            # Analysen raderades medan filerna laddades upp (#18). Filerna är redan städade.
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Analysen finns inte."
            ) from None
        if e.code != UNIQUE_VIOLATION:
            raise
        # Ett samtidigt tillägg tog samma kandidatnummer. Filerna är redan städade.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "CV:n lades till samtidigt från ett annat håll. Försök igen.",
        ) from None
    return _to_out(analysis, existing + added, quota)


def _read_pdfs(
    files: list[UploadFile], profile: dict, first_number: int
) -> list[bytes]:
    """Läser och validerar alla filer innan något sparas.

    En avvisad fil lämnar då inga halva uppladdningar efter sig.
    """
    max_bytes = profile["max_file_size_mb"] * 1024 * 1024
    contents: list[bytes] = []
    for number, f in enumerate(files, start=first_number):
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
    return contents


def _store_candidates(
    supabase: Client,
    user: CurrentUser,
    analysis_id: str,
    contents: list[bytes],
    first_number: int,
) -> list[Candidate]:
    """Laddar upp originalfilerna och skapar kandidaterna. Städar filerna om något går fel."""
    stored: list[str] = []
    try:
        rows = []
        for number, data in enumerate(contents, start=first_number):
            # Sökvägen innehåller aldrig originalfilnamnet.
            path = f"{user.id}/{analysis_id}/{uuid.uuid4().hex}.pdf"
            # Registrera sökvägen före uppladdningen så en halvfärdig fil också städas.
            stored.append(path)
            supabase.storage.from_(BUCKET).upload(
                path, data, {"content-type": "application/pdf"}
            )
            rows.append(
                {"analysis_id": analysis_id, "number": number, "original_path": path}
            )
        return _candidates(supabase.table("candidates").insert(rows).execute().data)
    except Exception:
        if stored:
            supabase.storage.from_(BUCKET).remove(stored)
        raise


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
    settings: Annotated[Settings, Depends(get_settings)],
) -> AnalysisOut:
    # Filtrera på user_id: andras analyser ser ut som att de inte finns.
    analysis = _own_analysis(supabase, user, analysis_id)
    return _to_out(
        analysis,
        _candidates(analysis["candidates"]),
        _quota(supabase, user, settings),
    )


@router.post(
    "/{analysis_id}/run",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=AnalysisOut,
)
def run_analysis(
    analysis_id: uuid.UUID,
    background: BackgroundTasks,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    supabase: Annotated[Client, Depends(get_supabase)],
    anthropic_client: Annotated[anthropic.Anthropic, Depends(get_anthropic_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AnalysisOut:
    """Startar pipelinen för analysens ännu ej körda CV:n. Resultatet hämtas via GET."""
    analysis = _own_analysis(supabase, user, analysis_id)
    now = datetime.now(UTC)
    quota = _quota(supabase, user, settings)
    stale_before = quota.stale_before
    _check_quota(quota, _candidates(analysis["candidates"]), "run")
    # Atomära anspråk i databasen, så en dubbelklick inte kör samma CV två gånger.
    # Anspråket stämplar last_progress_at, så ett samtidigt anrop inte hittar CV:t som fastnat.
    claim = {"status": "queued", "step": None, "last_progress_at": now.isoformat()}
    cutoff = stale_before.isoformat()

    def claim_rows():
        return (
            supabase.table("candidates")
            .update(claim)
            .eq("analysis_id", str(analysis_id))
        )

    fresh = claim_rows().eq("status", "uploaded").execute().data
    # Återhämtning: CV:n som fastnat (t.ex. efter en omstart mitt i en körning) tas om.
    stuck = (
        claim_rows()
        .in_("status", list(IN_FLIGHT))
        .or_(f"last_progress_at.is.null,last_progress_at.lt.{cutoff}")
        .execute()
        .data
    )
    claimed = _candidates(fresh + stuck)
    if not claimed:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Det finns inga CV:n att köra just nu."
        )
    claimed_ids = {c.id for c in claimed}
    candidates = _candidates(analysis["candidates"])
    for c in candidates:
        if c.id in claimed_ids:
            c.status = "queued"
            c.last_progress_at = now
    background.add_task(
        pipeline.run_analysis,
        supabase,
        anthropic_client,
        settings,
        user.id,
        analysis["job_ad"],
        claimed,
    )
    # De körs nu och är reserverade, så återstående kvot har minskat med dem.
    quota = replace(quota, remaining=max(quota.remaining - len(claimed), 0))
    return _to_out(analysis, candidates, quota)


@router.get("/{analysis_id}/export")
def export_analysis(
    analysis_id: uuid.UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    supabase: Annotated[Client, Depends(get_supabase)],
) -> Response:
    """Excel med anonym alias och bedömning. Originalfilnamn finns aldrig med."""
    # Filtrerar på user_id: bara ägaren kan exportera, andras analyser ser ut som att de inte finns.
    analysis = _own_analysis(supabase, user, analysis_id)
    candidates = _candidates(analysis["candidates"])
    if _state(candidates) != "finished":
        # En halvfärdig fil vore missvisande: poängen och rangordningen kan ändras.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Analysen är inte klar än. Exportera när alla CV:n är färdiga.",
        )
    ranked = sorted(candidates, key=_rank_key)
    return Response(
        content=build_workbook(ranked, _alias),
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": 'attachment; filename="Equa-analys.xlsx"'},
    )


@router.get("/{analysis_id}/candidates/{number}/original")
def reveal_candidate(
    analysis_id: uuid.UUID,
    number: int,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    supabase: Annotated[Client, Depends(get_supabase)],
) -> Response:
    """Avslöja: originalfilen för en kandidat. Det enda sättet identiteten visas.

    Avslöjanden loggas medvetet inte (ADR 0007).
    """
    analysis = _own_analysis(supabase, user, analysis_id)
    candidate = next(
        (c for c in _candidates(analysis["candidates"]) if c.number == number), None
    )
    if candidate is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kandidaten finns inte.")
    try:
        data = supabase.storage.from_(BUCKET).download(candidate.original_path)
    except StorageException:
        # Originalfilen kan redan ha raderats (raderingsdatum, ADR 0007).
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Originalfilen finns inte längre."
        ) from None
    filename = f"Kandidat-{number}.pdf"
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _check_quota(
    quota: QuotaSnapshot,
    candidates: list[Candidate],
    mode: Literal["run", "create", "add"],
    adding: int = 0,
) -> None:
    """Stoppar en körning, ett skapande eller ett tillägg som skulle överskrida månadskvoten.

    Kontrollen utgår från antal uppladdade filer, eftersom utfallet inte är känt i förväg.
    Vid tillägg räknas analysens ej körda CV:n plus de nya, så det som laddas upp också
    går att köra. Det som faktiskt räknas mot kvoten är bara lyckade CV:n (se
    användningsloggen).
    """
    to_run = quota.runnable_count(candidates) + adding
    if not to_run or to_run <= quota.remaining:
        return  # inget att köra (/run svarar 409 nedan) eller så ryms det
    attempt, outcome = {
        "run": (f"du försöker köra {to_run} CV:n", "Inget kördes."),
        "create": (f"du försöker ladda upp {to_run} CV:n", "Inga CV:n sparades."),
        "add": (
            f"analysen skulle få {to_run} CV:n att köra",
            "Inga CV:n sparades.",
        ),
    }[mode]
    raise HTTPException(
        status.HTTP_403_FORBIDDEN,
        f"Kvoten räcker inte: {attempt} men du har "
        f"{quota.remaining} kvar av {quota.limit} den här månaden. {outcome}",
    )


class ExtendRequest(BaseModel):
    expires_at: datetime


def _checked_expiry(expires_at: datetime, profile: dict) -> datetime:
    """Validerar ett raderingsdatum mot taket, som räknas från idag (rullande tak, ADR 0007)."""
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    max_days = max_retention_days(profile)
    if expires_at <= datetime.now(UTC):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Raderingsdatumet måste ligga i framtiden.",
        )
    if expires_at > datetime.now(UTC) + timedelta(days=max_days):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Raderingsdatumet får ligga högst {max_days} dagar fram.",
        )
    return expires_at


@router.patch("/{analysis_id}", response_model=AnalysisOut)
def extend_analysis(
    analysis_id: uuid.UUID,
    body: ExtendRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    supabase: Annotated[Client, Depends(get_supabase)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AnalysisOut:
    """Flyttar fram raderingsdatumet, högst till taket räknat från idag (rullande tak)."""
    analysis = _live_analysis(supabase, user, analysis_id)
    expires_at = _checked_expiry(body.expires_at, _profile(supabase, user))
    if expires_at <= datetime.fromisoformat(analysis["expires_at"]):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Raderingsdatumet kan bara flyttas fram, inte tidigare.",
        )
    analysis["expires_at"] = (
        supabase.table("analysis_batches")
        .update({"expires_at": expires_at.isoformat()})
        .eq("id", str(analysis_id))
        .execute()
        .data[0]["expires_at"]
    )
    return _to_out(
        analysis,
        _candidates(analysis["candidates"]),
        _quota(supabase, user, settings),
    )


@router.delete("/{analysis_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_analysis_now(
    analysis_id: uuid.UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    supabase: Annotated[Client, Depends(get_supabase)],
) -> Response:
    """Radera direkt: analysen, kandidaterna och originalfilerna."""
    _own_analysis(supabase, user, analysis_id)
    delete_analysis(supabase, str(analysis_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _own_analysis(supabase: Client, user: CurrentUser, analysis_id: uuid.UUID) -> dict:
    # Filtrera på user_id: andras analyser ser ut som att de inte finns.
    rows = (
        supabase.table("analysis_batches")
        .select("*, candidates(*)")
        .eq("id", str(analysis_id))
        .eq("user_id", user.id)
        .execute()
        .data
    )
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Analysen finns inte.")
    return rows[0]


def _live_analysis(supabase: Client, user: CurrentUser, analysis_id: uuid.UUID) -> dict:
    """Egen analys som inte passerat raderingsdatumet.

    En utgången analys väntar bara på raderingsjobbet och kan inte återupplivas eller
    få nya CV:n.
    """
    analysis = _own_analysis(supabase, user, analysis_id)
    if datetime.fromisoformat(analysis["expires_at"]) <= datetime.now(UTC):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Analysen finns inte.")
    return analysis

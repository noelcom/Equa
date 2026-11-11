"""Kandidatens rad i databasen och dess tillstånd. Enda stället som definierar statusarna."""

from typing import Literal

from pydantic import BaseModel

# uploaded: uppladdad men inte körd. queued/processing: under körning.
# done: bedömd. failed: "Kunde inte analyseras" (eget tillstånd, aldrig poäng 0).
CandidateStatus = Literal["uploaded", "queued", "processing", "done", "failed"]
PipelineStep = Literal["pre_wash", "ai_wash", "safety_check", "assessment"]

IN_FLIGHT: tuple[CandidateStatus, ...] = ("queued", "processing")
FINISHED: tuple[CandidateStatus, ...] = ("done", "failed")


class Candidate(BaseModel):
    """En rad i `candidates`. Bedömningsfälten är satta först när status är `done`."""

    id: str
    number: int
    original_path: str
    status: CandidateStatus = "uploaded"
    step: PipelineStep | None = None
    score: int | None = None
    years_experience: int | None = None
    education_match: str | None = None
    concrete_results: str | None = None
    key_skills: list[str] | None = None
    missing_requirements: str | None = None
    rationale: str | None = None
    failure_reason: str | None = None

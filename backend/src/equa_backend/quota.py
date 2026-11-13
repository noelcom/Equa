"""Kvot och användningslogg. Enda stället som räknar förbrukning (GLOSSARY: Kvot)."""

from dataclasses import dataclass
from datetime import UTC, datetime

from supabase import Client

from equa_backend.candidates import IN_FLIGHT, Candidate

PAGE = 1000


def _month_start() -> str:
    now = datetime.now(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


def next_reset() -> datetime:
    """När kvoten fylls på: första dagen i nästa kalendermånad (UTC)."""
    now = datetime.now(UTC)
    year, month = (now.year + 1, 1) if now.month == 12 else (now.year, now.month + 1)
    return datetime(year, month, 1, tzinfo=UTC)


def used_this_month(supabase: Client, customer_id: str) -> int:
    """Lyckade CV:n i kalendermånaden (UTC), enligt användningsloggen.

    Loggen och inte kandidaterna är källan, eftersom kandidaterna raderas vid raderingsdatum.
    """
    total, offset = 0, 0
    while True:  # PostgREST ger högst 1000 rader per anrop
        rows = (
            supabase.table("usage_logs")
            .select("cv_count")
            .eq("customer_id", customer_id)
            .gte("created_at", _month_start())
            .order("created_at")
            .range(offset, offset + PAGE - 1)
            .execute()
            .data
        )
        total += sum(r["cv_count"] for r in rows)
        if len(rows) < PAGE:
            return total
        offset += PAGE


def count_reserved(supabase: Client, customer_id: str, stale_before: datetime) -> int:
    """CV:n som körs just nu (ej fastnade) i kundens analyser.

    De är inte loggade än men kan komma att räknas mot kvoten, så de reserveras.
    """
    rows = (
        supabase.table("analysis_batches")
        .select("candidates(status, last_progress_at)")
        .eq("user_id", customer_id)
        .in_("candidates.status", list(IN_FLIGHT))
        .execute()
        .data
    )
    in_flight = (c for r in rows for c in r["candidates"] if c["status"] in IN_FLIGHT)
    return sum(
        1
        for c in in_flight
        if c["last_progress_at"] is not None
        and datetime.fromisoformat(c["last_progress_at"]) >= stale_before
    )


def remaining(
    supabase: Client, customer_id: str, limit: int, stale_before: datetime
) -> int:
    """Återstående kvot, med pågående CV:n reserverade. Delas av /me och körningskontrollen."""
    used = used_this_month(supabase, customer_id)
    reserved = count_reserved(supabase, customer_id, stale_before)
    return max(limit - used - reserved, 0)


@dataclass(frozen=True)
class QuotaSnapshot:
    """Kvotläget i början av ett anrop. Den enda källan för kvotreglerna (ADR 0002).

    Reglerna ligger här, så att frontend bara visar färdiga svar.
    """

    limit: int
    remaining: int
    stale_before: datetime

    def runnable_count(self, candidates: list[Candidate]) -> int:
        return sum(c.is_runnable(self.stale_before) for c in candidates)

    def can_run(self, candidates: list[Candidate]) -> bool:
        return self.runnable_count(candidates) <= self.remaining

    def addable_count(self, candidates: list[Candidate]) -> int:
        """Så många CV:n till ryms, när analysens ej körda CV:n räknas med."""
        return max(self.remaining - self.runnable_count(candidates), 0)


def snapshot(
    supabase: Client, customer_id: str, limit: int, stale_before: datetime
) -> QuotaSnapshot:
    return QuotaSnapshot(
        limit, remaining(supabase, customer_id, limit, stale_before), stale_before
    )


def write_usage_log(
    supabase: Client,
    customer_id: str,
    cv_count: int,
    input_tokens: int,
    output_tokens: int,
) -> None:
    """Skriver en permanent rad per körning. Innehåller aldrig kandidatdata."""
    supabase.table("usage_logs").insert(
        {
            "customer_id": customer_id,
            "cv_count": cv_count,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }
    ).execute()

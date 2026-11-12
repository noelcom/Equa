"""Kvot och användningslogg. Enda stället som räknar förbrukning (GLOSSARY: Kvot)."""

from datetime import UTC, datetime

from supabase import Client

from equa_backend.candidates import IN_FLIGHT

PAGE = 1000


def _month_start() -> str:
    now = datetime.now(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


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


def reserved(supabase: Client, customer_id: str, stale_before: datetime) -> int:
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


def pending(supabase: Client, customer_id: str) -> int:
    """Uppladdade men ej körda CV:n i alla kundens analyser. Bara information, ingen kontroll."""
    return (
        supabase.table("candidates")
        .select("id, analysis_batches!inner(user_id)", count="exact")
        .eq("status", "uploaded")
        .eq("analysis_batches.user_id", customer_id)
        .limit(1)
        .execute()
        .count
        or 0
    )


def remaining(
    supabase: Client, customer_id: str, limit: int, stale_before: datetime
) -> int:
    """Återstående kvot, med pågående CV:n reserverade. Delas av /me och körningskontrollen."""
    used = used_this_month(supabase, customer_id)
    held = reserved(supabase, customer_id, stale_before)
    return max(limit - used - held, 0)


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

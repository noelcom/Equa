"""Radering av analyser, kandidater och originalfiler (ADR 0004).

Databasens `on delete cascade` tar bort kandidatraderna men inte storage-objekten,
så filerna tas bort uttryckligen och före raderna (sökvägarna finns bara i raderna).
Användningsloggen (`usage_logs`) rörs aldrig här: den ska överleva raderingen.
"""

import asyncio
import logging
from datetime import UTC, datetime

from supabase import Client

from equa_backend.pipeline import BUCKET

logger = logging.getLogger(__name__)

# Backendens tak för raderingstid. Profilen kan sänka det men aldrig höja det (ADR 0004).
SYSTEM_MAX_RETENTION_DAYS = 90
# Antal analyser som hämtas per omgång i jobbet.
PURGE_BATCH = 200


def max_retention_days(profile: dict) -> int:
    """Längsta tillåtna raderingstid: profilens tak, aldrig över systemets."""
    return min(profile["max_retention_days"], SYSTEM_MAX_RETENTION_DAYS)


def default_retention_days(profile: dict) -> int:
    """Förvalet, aldrig över taket (ADR 0004)."""
    return min(profile["default_retention_days"], max_retention_days(profile))


def delete_analysis(supabase: Client, analysis_id: str) -> None:
    """Raderar en analys med kandidater och originalfiler.

    Misslyckas filraderingen kastas felet och raderna behålls, så ett nytt försök
    fortfarande hittar sökvägarna i stället för att lämna föräldralösa filer.
    """
    rows = (
        supabase.table("candidates")
        .select("original_path")
        .eq("analysis_id", analysis_id)
        .execute()
        .data
    )
    paths = [r["original_path"] for r in rows]
    if paths:
        supabase.storage.from_(BUCKET).remove(paths)
    supabase.table("analysis_batches").delete().eq("id", analysis_id).execute()


def purge_expired(supabase: Client) -> int:
    """Raderar analyser vars raderingsdatum har passerat. Returnerar antalet raderade."""
    deleted = 0
    while True:
        expired = (
            supabase.table("analysis_batches")
            .select("id")
            .lte("expires_at", datetime.now(UTC).isoformat())
            .limit(PURGE_BATCH)
            .execute()
            .data
        )
        deleted_in_batch = 0
        for row in expired:
            try:
                delete_analysis(supabase, row["id"])
                deleted_in_batch += 1
            except Exception:
                # En analys som inte går att radera ska inte hindra övriga. Nästa körning provar igen.
                logger.exception("Kunde inte radera utgången analys %s", row["id"])
        deleted += deleted_in_batch
        # Fortsätt bara om omgången var full och något raderades, så en trasig rad inte ger evig loop.
        if len(expired) < PURGE_BATCH or not deleted_in_batch:
            return deleted


async def purge_loop(supabase: Client, interval_seconds: float) -> None:
    """Kör raderingsjobbet om och om igen. Det kan inte stängas av (ADR 0004)."""
    while True:
        try:
            await asyncio.to_thread(purge_expired, supabase)
        except Exception:
            logger.exception("Raderingsjobbet misslyckades")
        await asyncio.sleep(interval_seconds)

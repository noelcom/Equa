"""Radering av analyser, kandidater och originalfiler (ADR 0007).

Databasens `on delete cascade` tar bort kandidatraderna men inte storage-objekten,
så filerna tas bort uttryckligen: efter raden, genom att tömma analysens mapp (#18).
Användningsloggen (`usage_logs`) rörs aldrig här: den ska överleva raderingen.
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from supabase import Client

from equa_backend.pipeline import BUCKET, analysis_folder

logger = logging.getLogger(__name__)

# Backendens tak för raderingstid. Profilen kan sänka det men aldrig höja det (ADR 0007).
SYSTEM_MAX_RETENTION_DAYS = 90
# Antal analyser som hämtas per omgång i jobbet.
PURGE_BATCH = 200
# Antal poster per listning i lagringen.
LIST_PAGE = 100
# Antal analys-id per kontroll av föräldralösa mappar. Id:na går i URL:en, och 100 uuid
# ryms gott under längdgränsen.
ORPHAN_CHECK_BATCH = 100


def max_retention_days(profile: dict) -> int:
    """Längsta tillåtna raderingstid: profilens tak, aldrig över systemets."""
    return min(profile["max_retention_days"], SYSTEM_MAX_RETENTION_DAYS)


def default_retention_days(profile: dict) -> int:
    """Förvalet, aldrig över taket (ADR 0007)."""
    return min(profile["default_retention_days"], max_retention_days(profile))


def delete_analysis(supabase: Client, analysis_id: str) -> None:
    """Raderar en analys med kandidater och originalfiler.

    Raden raderas först och sedan allt i analysens mapp (#18). En uppladdning som hann
    lägga en fil i mappen fångas då av mappstädningen, och en som kommer efter faller på
    främmande nyckel och städar själv.

    Misslyckas filraderingen loggas felet men kastas inte: analysen är redan borta och
    raderingsjobbet tar bort mappar som saknar analys (`run_purge_job`).
    """
    rows = (
        supabase.table("analysis_batches")
        .select("user_id")
        .eq("id", analysis_id)
        .execute()
        .data
    )
    if not rows:
        return
    supabase.table("analysis_batches").delete().eq("id", analysis_id).execute()
    folder = analysis_folder(rows[0]["user_id"], analysis_id)
    try:
        _remove_folder(supabase, folder)
    except Exception:
        logger.exception(
            "Kunde inte ta bort %s, raderingsjobbet tar det senare", folder
        )


def remove_user_files(supabase: Client, user_id: str) -> None:
    """Tar bort alla användarens filer i lagringen. Kastar felet om något inte går att ta bort."""
    for name in _list_all(supabase, user_id):
        # Alla mappar under användaren, inte bara analysmappar.
        _remove_folder(supabase, f"{user_id}/{name}")


def _remove_folder(supabase: Client, folder: str) -> None:
    """Tar bort alla filer direkt i en mapp i lagringen."""
    bucket = supabase.storage.from_(BUCKET)
    previous: list[str] = []
    while True:
        # Listningen ger högst `limit` poster per anrop. Det som tas bort försvinner ur
        # listningen, så nästa anrop börjar alltid från början.
        names = [f["name"] for f in bucket.list(folder, {"limit": LIST_PAGE})]
        if not names:
            return
        if names == previous:
            # Borttagningen gick igenom utan att ta bort något. Stoppa i stället för att snurra.
            raise RuntimeError(f"Kunde inte tömma {folder} i lagringen")
        bucket.remove([f"{folder}/{n}" for n in names])
        previous = names


def run_purge_job(supabase: Client) -> None:
    """En körning av raderingsjobbet: utgångna analyser, sedan föräldralösa mappar."""
    _purge_expired_analyses(supabase)
    purge_orphaned_files(supabase)


def purge_orphaned_files(supabase: Client) -> None:
    """Tömmer varje mapp `{user_id}/{analysis_id}/` vars analys inte finns (#18).

    Fångar filer som blev kvar när en filradering misslyckades eller när en uppladdning
    hann före raderingen. En analys som håller på att skapas rörs inte: raden skapas
    innan filerna laddas upp.
    """
    for user_folder in _list_all(supabase, ""):
        folders = {
            name: analysis_folder(user_folder, name)
            for name in _list_all(supabase, user_folder)
            if _is_uuid(name)
        }
        ids = list(folders)
        existing: set[str] = set()
        for start in range(0, len(ids), ORPHAN_CHECK_BATCH):
            existing |= {
                r["id"]
                for r in supabase.table("analysis_batches")
                .select("id")
                .in_("id", ids[start : start + ORPHAN_CHECK_BATCH])
                .execute()
                .data
            }
        for analysis_id, folder in folders.items():
            if analysis_id in existing:
                continue
            try:
                _remove_folder(supabase, folder)
            except Exception:
                # En mapp som inte går att tömma ska inte hindra övriga. Nästa körning provar igen.
                logger.exception("Kunde inte ta bort föräldralösa filer i %s", folder)


def _list_all(supabase: Client, folder: str) -> list[str]:
    """Alla namn direkt under en mapp i lagringen, sida för sida."""
    bucket = supabase.storage.from_(BUCKET)
    names: list[str] = []
    while True:
        page = bucket.list(folder, {"limit": LIST_PAGE, "offset": len(names)})
        names += [f["name"] for f in page]
        if len(page) < LIST_PAGE:
            return names


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


def _purge_expired_analyses(supabase: Client) -> None:
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
        # Fortsätt bara om omgången var full och något raderades, så en trasig rad inte ger evig loop.
        if len(expired) < PURGE_BATCH or not deleted_in_batch:
            return


async def purge_loop(supabase: Client, interval_seconds: float) -> None:
    """Kör raderingsjobbet om och om igen. Det kan inte stängas av (ADR 0007)."""
    while True:
        try:
            await asyncio.to_thread(run_purge_job, supabase)
        except Exception:
            logger.exception("Raderingsjobbet misslyckades")
        await asyncio.sleep(interval_seconds)

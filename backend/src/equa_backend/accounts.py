"""Radering av ett användarkonto (#14, ADR 0007 och 0006).

Det görs bara av Equas ägare, via skriptet längst ned. Det finns inget API-anrop och inget UI.
Användningsloggen (`usage_logs`) rörs aldrig: den är permanent och anonym.
"""

import argparse
import logging
import sys

from supabase import Client

from equa_backend.deps import get_supabase
from equa_backend.retention import delete_analysis

logger = logging.getLogger(__name__)


def delete_account(supabase: Client, user_id: str) -> int:
    """Raderar kontots analyser, kandidater, originalfiler, profil och auth-användare.

    Analyserna raderas en i taget med `delete_analysis` (filer före rader). Misslyckas någon
    kastas felet direkt och auth-användaren lämnas kvar, så ingen fil blir föräldralös och en
    ny körning fortsätter där den slutade. Profilen följer med auth-användaren via cascade.
    Returnerar antalet raderade analyser.
    """
    analyses = (
        supabase.table("analysis_batches")
        .select("id")
        .eq("user_id", user_id)
        .execute()
        .data
    )
    for row in analyses:
        delete_analysis(supabase, row["id"])
    supabase.auth.admin.delete_user(user_id)
    return len(analyses)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m equa_backend.accounts",
        description=(
            "Raderar ett användarkonto med alla analyser, kandidater och originalfiler. "
            "Användningsloggen lämnas orörd. Körs av Equas ägare. Kontrollerar inte om en "
            "körning pågår, så kör det när kunden inte är aktiv. Misslyckas en radering "
            "stoppas skriptet och kontot lämnas kvar: kör om det."
        ),
    )
    parser.add_argument("user_id", help="Auth-användarens id (uuid)")
    args = parser.parse_args(argv)

    try:
        count = delete_account(get_supabase(), args.user_id)
    except Exception:
        logger.exception("Kontot %s raderades inte. Kör skriptet igen.", args.user_id)
        return 1
    print(f"Kontot {args.user_id} är raderat ({count} analyser).")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())

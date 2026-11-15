"""Excel-export av en analys: alias, bedömning och avslöjade identiteter, aldrig originalfilnamn (ADR 0007)."""

import io
from collections.abc import Callable

from openpyxl import Workbook

from equa_backend.candidates import Candidate
from equa_backend.identity import Identity

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

STATUS_LABELS = {
    "uploaded": "Ej körd",
    "queued": "Köad",
    "processing": "Pågår",
    "done": "Bedömd",
    "failed": "Kunde inte analyseras",
}

HEADER = [
    "Kandidat",
    "Namn",
    "E-post",
    "Telefon",
    "Status",
    "Poäng",
    "Års erfarenhet",
    "Utbildningsmatch",
    "Konkreta resultat",
    "Nyckelkompetenser",
    "Saknade krav",
    "Motivering",
]


def _row(
    c: Candidate,
    alias: Callable[[int], str],
    identity: Callable[[Candidate], Identity | None],
) -> list:
    who = identity(c) or Identity()
    lead = [alias(c.number), who.name, who.email, who.phone]
    if c.status != "done":
        return lead + [STATUS_LABELS[c.status]] + [None] * (len(HEADER) - 5)
    return lead + [
        STATUS_LABELS[c.status],
        c.score,
        c.years_experience,
        c.education_match,
        c.concrete_results,
        ", ".join(c.key_skills),
        c.missing_requirements,
        c.rationale,
    ]


def build_workbook(
    candidates: list[Candidate],
    alias: Callable[[int], str],
    identity: Callable[[Candidate], Identity | None],
) -> bytes:
    """Alla kandidater som en xlsx-fil, i den ordning de ges (leaderboardens).

    `alias` ger kandidatens anonyma namn utifrån löpnumret. `identity` ger uppgifterna
    för en avslöjad kandidat och None för övriga, vars celler blir tomma. Originalfilnamnet
    finns aldrig med.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Resultat"
    ws.append(HEADER)
    for c in candidates:
        ws.append(_row(c, alias, identity))
    # AI-text som börjar med "=" ska aldrig tolkas som formel i Excel.
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            if isinstance(cell.value, str):
                cell.data_type = "s"
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()

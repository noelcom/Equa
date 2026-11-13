"""Excel-export av en analys: anonym alias och bedömning, aldrig originalfilnamn (ADR 0007)."""

import io
from collections.abc import Callable

from openpyxl import Workbook

from equa_backend.candidates import Candidate

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
    "Status",
    "Poäng",
    "Års erfarenhet",
    "Utbildningsmatch",
    "Konkreta resultat",
    "Nyckelkompetenser",
    "Saknade krav",
    "Motivering",
]


def _row(c: Candidate, alias: Callable[[int], str]) -> list:
    if c.status != "done":
        return [alias(c.number), STATUS_LABELS[c.status]] + [None] * (len(HEADER) - 2)
    return [
        alias(c.number),
        STATUS_LABELS[c.status],
        c.score,
        c.years_experience,
        c.education_match,
        c.concrete_results,
        ", ".join(c.key_skills),
        c.missing_requirements,
        c.rationale,
    ]


def build_workbook(candidates: list[Candidate], alias: Callable[[int], str]) -> bytes:
    """Alla kandidater som en xlsx-fil, i den ordning de ges (leaderboardens).

    `alias` ger kandidatens anonyma namn utifrån löpnumret. Raden bär bara alias och
    bedömning, så inget i filen kan peka tillbaka på originalfilen.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Resultat"
    ws.append(HEADER)
    for c in candidates:
        ws.append(_row(c, alias))
    # AI-text som börjar med "=" ska aldrig tolkas som formel i Excel.
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            if isinstance(cell.value, str):
                cell.data_type = "s"
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()

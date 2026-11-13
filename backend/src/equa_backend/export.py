"""Excel-export av en analys: anonym alias och bedömning, aldrig originalfilnamn (ADR 0007)."""

import io

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


def build_workbook(candidates: list[Candidate], alias) -> bytes:
    """Alla kandidater, bedömda först med högst poäng överst, som en xlsx-fil.

    `candidates` ska redan vara i leaderboardens ordning. Raden bär bara alias och
    bedömning, så inget i filen kan peka tillbaka på originalfilen.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Resultat"
    ws.append(HEADER)
    for c in candidates:
        done = c.status == "done"
        ws.append(
            [
                alias(c.number),
                STATUS_LABELS[c.status],
                c.score if done else None,
                c.years_experience if done else None,
                c.education_match if done else None,
                c.concrete_results if done else None,
                ", ".join(c.key_skills) if done else None,
                c.missing_requirements if done else None,
                c.rationale if done else None,
            ]
        )
    # AI-text som börjar med "=" ska aldrig tolkas som formel i Excel.
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            if isinstance(cell.value, str):
                cell.data_type = "s"
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()

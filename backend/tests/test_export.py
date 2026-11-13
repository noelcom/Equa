"""Excel-export: analysen som anonym tabell med alias och bedömning."""

import io
import zipfile

from helpers import cv
from openpyxl import load_workbook

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _analysis(client, user, files):
    res = client.post(
        "/analyses",
        headers=user.auth,
        data={"title": "Backendutvecklare", "job_ad": "Vi söker en utvecklare."},
        files=[("files", (name, pdf, "application/pdf")) for name, pdf in files],
    )
    assert res.status_code == 201, res.text
    return res.json()


def _run(client, user, analysis_id):
    res = client.post(f"/analyses/{analysis_id}/run", headers=user.auth)
    assert res.status_code in (200, 202), res.text


def _export(client, user, analysis_id):
    return client.get(f"/analyses/{analysis_id}/export", headers=user.auth)


def _rows(res):
    sheet = load_workbook(io.BytesIO(res.content)).active
    header, *rows = [list(r) for r in sheet.iter_rows(values_only=True)]
    return header, [dict(zip(header, r)) for r in rows]


def test_export_has_alias_score_and_assessment_ranked_by_score(client, make_user):
    user = make_user()
    analysis = _analysis(
        client,
        user,
        [
            ("anna-andersson.pdf", cv("Kodare\nPOÄNG 40")),
            ("bo-berg.pdf", cv("Kodare\nPOÄNG 90")),
        ],
    )
    _run(client, user, analysis["id"])

    res = _export(client, user, analysis["id"])

    assert res.status_code == 200
    assert res.headers["content-type"] == XLSX
    assert "attachment" in res.headers["content-disposition"]
    header, rows = _rows(res)
    assert header[0] == "Kandidat"
    assert [r["Kandidat"] for r in rows] == ["Kandidat #2", "Kandidat #1"]
    assert [r["Poäng"] for r in rows] == [90, 40]
    top = rows[0]
    assert top["Års erfarenhet"] == 5
    assert top["Utbildningsmatch"] == "Relevant utbildning."
    assert top["Konkreta resultat"] == "Levererade flera projekt."
    assert top["Nyckelkompetenser"] == "Python, SQL"
    assert top["Saknade krav"] == "Inga större gap."
    assert top["Motivering"] == "Bra matchning mot annonsen."


def test_export_lists_every_candidate_including_ones_not_assessed(client, make_user):
    user = make_user()
    analysis = _analysis(client, user, [("cv.pdf", cv("Kodare\nPOÄNG 70"))])

    res = _export(client, user, analysis["id"])

    _, rows = _rows(res)
    assert [r["Kandidat"] for r in rows] == ["Kandidat #1"]
    assert rows[0]["Poäng"] is None


def test_export_never_contains_the_original_filename(client, make_user):
    user = make_user()
    analysis = _analysis(
        client,
        user,
        [("anna-andersson-cv.pdf", cv("Kodare\nPOÄNG 80"))],
    )
    _run(client, user, analysis["id"])

    res = _export(client, user, analysis["id"])

    assert res.status_code == 200
    # Sök i alla delar av xlsx-filen, inte bara i cellerna.
    with zipfile.ZipFile(io.BytesIO(res.content)) as z:
        everything = b"".join(z.read(name) for name in z.namelist()).lower()
    assert b"anna" not in everything
    assert b"andersson" not in everything
    assert b".pdf" not in everything
    assert "anna" not in res.headers["content-disposition"].lower()
    assert "Källfil" not in _rows(res)[0]


def test_export_text_that_looks_like_a_formula_stays_text(
    client, make_user, anthropic_fake
):
    user = make_user()
    anthropic_fake.assess_override = lambda text: {
        "score": 60,
        "years_experience": 1,
        "education_match": '=HYPERLINK("http://example.com")',
        "concrete_results": "x",
        "key_skills": [],
        "missing_requirements": "x",
        "rationale": "x",
    }
    analysis = _analysis(client, user, [("cv.pdf", cv("Kodare"))])
    _run(client, user, analysis["id"])

    res = _export(client, user, analysis["id"])

    sheet = load_workbook(io.BytesIO(res.content)).active
    cell = next(c for row in sheet.iter_rows(min_row=2) for c in row if c.column == 5)
    assert cell.data_type == "s"
    assert cell.value.startswith("=HYPERLINK")


def test_only_the_owner_can_export(client, make_user):
    owner, other = make_user(), make_user()
    analysis = _analysis(client, owner, [("cv.pdf", cv("Kodare\nPOÄNG 80"))])
    _run(client, owner, analysis["id"])

    res = _export(client, other, analysis["id"])

    # Andras analyser ser ut som att de inte finns.
    assert res.status_code == 404
    assert b"PK" != res.content[:2]


def test_export_requires_login(client, make_user):
    owner = make_user()
    analysis = _analysis(client, owner, [("cv.pdf", cv("CV"))])

    res = client.get(f"/analyses/{analysis['id']}/export")

    assert res.status_code == 401

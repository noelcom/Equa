"""Originalfilen går bara att ladda ner för en avslöjad kandidat (ADR 0007, 0009)."""

import logging

import pytest
from helpers import make_pdf


@pytest.fixture(autouse=True)
def _fake_anthropic(anthropic_fake):
    """Körningen i _create får aldrig nå riktiga Anthropic."""


def _create(client, user, files):
    res = client.post(
        "/analyses",
        headers=user.auth,
        data={"title": "Backendutvecklare", "job_ad": "Vi söker en utvecklare."},
        files=[("files", (name, data, "application/pdf")) for name, data in files],
    )
    assert res.status_code == 201
    analysis = res.json()
    # Avslöjande kräver en klar analys (lyckad eller ej), så kör den först.
    run = client.post(f"/analyses/{analysis['id']}/run", headers=user.auth)
    assert run.status_code in (200, 202), run.text
    return analysis


def _reveal_and_download(client, user, analysis_id, number):
    """Avslöjar kandidaten och laddar sedan ner originalfilen."""
    client.post(
        f"/analyses/{analysis_id}/candidates/{number}/reveal", headers=user.auth
    )
    # Nedladdningen prövas alltid, även när avslöjandet nekas (annan användare, okänd kandidat).
    return _download(client, user, analysis_id, number)


def _download(client, user, analysis_id, number):
    return client.get(
        f"/analyses/{analysis_id}/candidates/{number}/original", headers=user.auth
    )


def test_reveal_downloads_the_original_file_of_the_chosen_candidate(client, make_user):
    user = make_user()
    first, second = make_pdf("Första CV:t"), make_pdf("Andra CV:t")
    analysis = _create(
        client, user, [("anna-andersson.pdf", first), ("bo-berg.pdf", second)]
    )

    res = _reveal_and_download(client, user, analysis["id"], 2)

    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert res.content == second
    # Filnamnet är det anonyma aliaset, aldrig originalfilnamnet (ADR 0007).
    assert res.headers["content-disposition"] == 'attachment; filename="Kandidat-2.pdf"'


def test_another_user_cannot_reveal_the_candidate(client, make_user):
    owner, other = make_user(), make_user()
    analysis = _create(client, owner, [("cv.pdf", make_pdf("Hemligt CV"))])

    res = _reveal_and_download(client, other, analysis["id"], 1)

    # Andras analyser ser ut som att de inte finns.
    assert res.status_code == 404
    assert b"Hemligt" not in res.content


def test_reveal_requires_login(client, make_user):
    owner = make_user()
    analysis = _create(client, owner, [("cv.pdf", make_pdf("CV"))])

    res = client.get(f"/analyses/{analysis['id']}/candidates/1/original")

    assert res.status_code == 401


def test_reveal_of_unknown_candidate_is_404(client, make_user):
    user = make_user()
    analysis = _create(client, user, [("cv.pdf", make_pdf("CV"))])

    assert _reveal_and_download(client, user, analysis["id"], 2).status_code == 404


def test_reveal_is_not_logged(client, make_user, caplog):
    user = make_user()
    analysis = _create(client, user, [("cv.pdf", make_pdf("CV"))])
    caplog.clear()

    with caplog.at_level(logging.DEBUG, logger="equa_backend"):
        res = _reveal_and_download(client, user, analysis["id"], 1)

    assert res.status_code == 200
    assert [r for r in caplog.records if r.name.startswith("equa_backend")] == []


def test_reveal_of_already_deleted_original_is_404(client, make_user, admin):
    user = make_user()
    analysis = _create(client, user, [("cv.pdf", make_pdf("CV"))])
    path = (
        admin.table("candidates")
        .select("original_path")
        .eq("analysis_id", analysis["id"])
        .execute()
        .data[0]["original_path"]
    )
    admin.storage.from_("originals").remove([path])

    res = _reveal_and_download(client, user, analysis["id"], 1)

    assert res.status_code == 404


def test_reveal_after_expiry_date_is_404_as_for_other_expired_calls(
    client, make_user, admin
):
    user = make_user()
    analysis = _create(client, user, [("cv.pdf", make_pdf("CV"))])
    admin.table("analysis_batches").update(
        {"expires_at": "2000-01-01T00:00:00+00:00"}
    ).eq("id", analysis["id"]).execute()

    res = _reveal_and_download(client, user, analysis["id"], 1)

    assert res.status_code == 404
    assert res.json() == {"detail": "Analysen finns inte."}


def test_download_of_unrevealed_candidate_is_409(client, make_user):
    user = make_user()
    analysis = _create(client, user, [("cv.pdf", make_pdf("Hemligt CV"))])

    res = _download(client, user, analysis["id"], 1)

    assert res.status_code == 409
    assert res.json() == {"detail": "Kandidaten är inte avslöjad."}
    assert b"Hemligt" not in res.content


def test_download_only_unlocks_for_the_revealed_candidate(client, make_user):
    user = make_user()
    analysis = _create(
        client, user, [("a.pdf", make_pdf("Första")), ("b.pdf", make_pdf("Andra"))]
    )
    client.post(f"/analyses/{analysis['id']}/candidates/1/reveal", headers=user.auth)

    assert _download(client, user, analysis["id"], 1).status_code == 200
    assert _download(client, user, analysis["id"], 2).status_code == 409

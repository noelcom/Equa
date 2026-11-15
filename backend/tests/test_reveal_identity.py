"""Avslöja visar namnet: identiteten sparas krypterad och visas först efter avslöjandet (ADR 0009)."""

from datetime import datetime

from helpers import cv

NAME = "Anna Andersson"


def _create(client, user, files):
    res = client.post(
        "/analyses",
        headers=user.auth,
        data={"title": "Backendutvecklare", "job_ad": "Vi söker en utvecklare."},
        files=[("files", (n, data, "application/pdf")) for n, data in files],
    )
    assert res.status_code == 201, res.text
    return res.json()


def _run(client, user, analysis_id):
    res = client.post(f"/analyses/{analysis_id}/run", headers=user.auth)
    assert res.status_code in (200, 202), res.text
    return res


def _analysis_run(client, make_user, anthropic_fake):
    anthropic_fake.names = [NAME]
    user = make_user()
    analysis = _create(client, user, [("cv.pdf", cv(f"{NAME}\nUtvecklare.\nPOÄNG 70"))])
    _run(client, user, analysis["id"])
    return user, analysis["id"]


def _get(client, user, analysis_id):
    return client.get(f"/analyses/{analysis_id}", headers=user.auth)


def _reveal(client, user, analysis_id, number=1):
    return client.post(
        f"/analyses/{analysis_id}/candidates/{number}/reveal", headers=user.auth
    )


def test_name_never_reaches_the_assessment(client, make_user, anthropic_fake):
    _analysis_run(client, make_user, anthropic_fake)

    sent = anthropic_fake.texts_sent("assess")
    assert sent
    assert all(NAME not in text for text in sent)
    assert all("Andersson" not in text for text in sent)


def test_identity_is_stored_encrypted(client, make_user, anthropic_fake, admin):
    _, analysis_id = _analysis_run(client, make_user, anthropic_fake)

    row = (
        admin.table("candidates")
        .select("*")
        .eq("analysis_id", analysis_id)
        .execute()
        .data[0]
    )

    assert row["identity_encrypted"]
    assert "Andersson" not in str(row)
    assert NAME not in str(row)


def test_unrevealed_candidate_shows_no_identity_anywhere_in_the_response(
    client, make_user, anthropic_fake
):
    user, analysis_id = _analysis_run(client, make_user, anthropic_fake)

    res = _get(client, user, analysis_id)

    assert res.status_code == 200
    assert "Andersson" not in res.text
    candidate = res.json()["candidates"][0]
    assert candidate["identity"] is None
    assert candidate["revealed_at"] is None
    assert "identity_encrypted" not in res.text


def test_reveal_returns_identity_and_time(client, make_user, anthropic_fake):
    user, analysis_id = _analysis_run(client, make_user, anthropic_fake)

    res = _reveal(client, user, analysis_id)

    assert res.status_code == 200
    body = res.json()
    assert body["identity"] == {"name": NAME}
    datetime.fromisoformat(body["revealed_at"])


def test_analysis_shows_identity_after_reveal(client, make_user, anthropic_fake):
    user, analysis_id = _analysis_run(client, make_user, anthropic_fake)
    revealed = _reveal(client, user, analysis_id).json()

    candidate = _get(client, user, analysis_id).json()["candidates"][0]

    assert candidate["identity"] == {"name": NAME}
    assert candidate["revealed_at"] == revealed["revealed_at"]
    assert candidate["alias"] == "Kandidat #1"


def test_second_reveal_keeps_the_time(client, make_user, anthropic_fake):
    user, analysis_id = _analysis_run(client, make_user, anthropic_fake)

    first = _reveal(client, user, analysis_id).json()
    second = _reveal(client, user, analysis_id).json()

    assert second == first


def test_reveal_survives_a_rerun(client, make_user, anthropic_fake):
    user, analysis_id = _analysis_run(client, make_user, anthropic_fake)
    first = _reveal(client, user, analysis_id).json()

    res = client.put(
        f"/analyses/{analysis_id}/job_ad",
        headers=user.auth,
        json={"job_ad": "En helt ny annons."},
    )
    assert res.status_code == 202, res.text

    candidate = _get(client, user, analysis_id).json()["candidates"][0]
    assert candidate["revealed_at"] == first["revealed_at"]
    assert candidate["identity"] == {"name": NAME}


def test_reveal_requires_login(client, make_user, anthropic_fake):
    _, analysis_id = _analysis_run(client, make_user, anthropic_fake)

    res = client.post(f"/analyses/{analysis_id}/candidates/1/reveal")

    assert res.status_code == 401


def test_another_user_gets_404_and_reveals_nothing(client, make_user, anthropic_fake):
    _, analysis_id = _analysis_run(client, make_user, anthropic_fake)
    other = make_user()

    res = _reveal(client, other, analysis_id)

    assert res.status_code == 404
    assert "Andersson" not in res.text


def test_reveal_of_unknown_candidate_is_404(client, make_user, anthropic_fake):
    user, analysis_id = _analysis_run(client, make_user, anthropic_fake)

    assert _reveal(client, user, analysis_id, 2).status_code == 404


def test_reveal_after_expiry_is_denied(client, make_user, anthropic_fake, admin):
    user, analysis_id = _analysis_run(client, make_user, anthropic_fake)
    admin.table("analysis_batches").update(
        {"expires_at": "2000-01-01T00:00:00+00:00"}
    ).eq("id", analysis_id).execute()

    res = _reveal(client, user, analysis_id)

    assert res.status_code == 404
    assert "Andersson" not in res.text


def test_candidate_without_a_stored_name_reveals_an_empty_identity(
    client, make_user, anthropic_fake
):
    # Namnet kunde inte läsas ut: tvätten hittade inget namn att ersätta.
    user = make_user()
    analysis = _create(client, user, [("cv.pdf", cv("Utvecklare.\nPOÄNG 70"))])
    _run(client, user, analysis["id"])

    res = _reveal(client, user, analysis["id"])

    assert res.status_code == 200
    assert res.json()["identity"] == {"name": None}

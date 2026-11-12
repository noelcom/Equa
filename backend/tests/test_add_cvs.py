"""Lägg till CV:n i en befintlig analys genom HTTP-API:et."""

from datetime import UTC, datetime, timedelta

from helpers import cv

JOB_AD = "Vi söker en utvecklare med Kubernetes."


def _analysis(client, user, bodies):
    res = client.post(
        "/analyses",
        headers=user.auth,
        data={"title": "Backendutvecklare", "job_ad": JOB_AD},
        files=[
            ("files", (f"{i}.pdf", cv(body), "application/pdf"))
            for i, body in enumerate(bodies)
        ],
    )
    assert res.status_code == 201, res.text
    return res.json()


def _add(client, user, analysis_id, bodies):
    return client.post(
        f"/analyses/{analysis_id}/candidates",
        headers=user.auth,
        files=[
            ("files", (f"ny-{i}.pdf", cv(body), "application/pdf"))
            for i, body in enumerate(bodies)
        ],
    )


def _run(client, user, analysis_id):
    res = client.post(f"/analyses/{analysis_id}/run", headers=user.auth)
    assert res.status_code == 202, res.text


def _get(client, user, analysis_id):
    return client.get(f"/analyses/{analysis_id}", headers=user.auth).json()


def test_added_cvs_are_assessed_against_the_same_ad_and_the_leaderboard_is_reordered(
    client, make_user, anthropic_fake
):
    user = make_user()
    analysis = _analysis(client, user, ["Utvecklare.\nPOÄNG 40"])
    _run(client, user, analysis["id"])

    added = _add(client, user, analysis["id"], ["Utvecklare.\nPOÄNG 90"])
    assert added.status_code == 201, added.text
    assert added.json()["state"] == "ready"
    _run(client, user, analysis["id"])

    body = _get(client, user, analysis["id"])
    assert [(c["alias"], c["assessment"]["score"]) for c in body["candidates"]] == [
        ("Kandidat #2", 90),
        ("Kandidat #1", 40),
    ]
    assessed = [kw for kind, kw in anthropic_fake.calls if kind == "assess"]
    assert len(assessed) == 2
    assert assessed[0]["system"] == assessed[1]["system"]
    assert all(JOB_AD in str(kw) for kw in assessed)


def _set_quota(client, admin, user, limit):
    client.get("/me", headers=user.auth)  # skapar profilen
    admin.table("profiles").update({"cv_quota_limit": limit}).eq(
        "id", user.id
    ).execute()


def test_adding_more_cvs_than_the_quota_allows_is_refused_and_nothing_is_stored(
    client, make_user, admin
):
    user = make_user()
    _set_quota(client, admin, user, 3)
    # Två ej körda CV:n finns redan, så bara ett till ryms.
    analysis = _analysis(client, user, ["POÄNG 50", "POÄNG 60"])

    over = _add(client, user, analysis["id"], ["POÄNG 70", "POÄNG 80"])

    assert over.status_code == 403
    assert "kvot" in over.json()["detail"].lower()
    body = _get(client, user, analysis["id"])
    assert len(body["candidates"]) == 2
    files = admin.storage.from_("originals").list(f"{user.id}/{analysis['id']}")
    assert len(files) == 2

    ok = _add(client, user, analysis["id"], ["POÄNG 70"])

    assert ok.status_code == 201, ok.text
    assert len(ok.json()["candidates"]) == 3


def test_adding_cvs_leaves_the_deletion_date_unchanged(client, make_user):
    user = make_user()
    analysis = _analysis(client, user, ["POÄNG 50"])

    added = _add(client, user, analysis["id"], ["POÄNG 70"])

    assert added.status_code == 201, added.text
    assert added.json()["expires_at"] == analysis["expires_at"]
    assert _get(client, user, analysis["id"])["expires_at"] == analysis["expires_at"]


def test_cvs_cannot_be_added_to_another_users_or_an_expired_analysis(
    client, make_user, admin
):
    owner, other = make_user(), make_user()
    analysis = _analysis(client, owner, ["POÄNG 50"])

    assert _add(client, other, analysis["id"], ["POÄNG 70"]).status_code == 404

    # Utgången analys väntar bara på raderingsjobbet och tar inte emot nya CV:n.
    admin.table("analysis_batches").update(
        {"expires_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat()}
    ).eq("id", analysis["id"]).execute()

    assert _add(client, owner, analysis["id"], ["POÄNG 70"]).status_code == 404
    files = admin.storage.from_("originals").list(f"{owner.id}/{analysis['id']}")
    assert len(files) == 1

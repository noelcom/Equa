"""Ändra arbetsannons: alla CV:n körs om mot den nya texten (GLOSSARY: Arbetsannons)."""

from datetime import UTC, datetime

from helpers import cv

OLD_AD = "Vi söker en utvecklare."
NEW_AD = "Vi söker en tech lead med erfarenhet av Kubernetes."


def _analysis(client, user, bodies):
    res = client.post(
        "/analyses",
        headers=user.auth,
        data={"title": "Backendutvecklare", "job_ad": OLD_AD},
        files=[
            ("files", (f"{i}.pdf", cv(body), "application/pdf"))
            for i, body in enumerate(bodies)
        ],
    )
    assert res.status_code == 201, res.text
    return res.json()


def _run(client, user, analysis):
    res = client.post(f"/analyses/{analysis['id']}/run", headers=user.auth)
    assert res.status_code == 202, res.text


def _change_ad(client, user, analysis, job_ad):
    return client.put(
        f"/analyses/{analysis['id']}/job_ad",
        headers=user.auth,
        json={"job_ad": job_ad},
    )


def _get(client, user, analysis):
    return client.get(f"/analyses/{analysis['id']}", headers=user.auth).json()


def _set_quota(client, admin, user, limit):
    client.get("/me", headers=user.auth)  # skapar profilen
    admin.table("profiles").update({"cv_quota_limit": limit}).eq(
        "id", user.id
    ).execute()


def _remaining(client, user):
    return client.get("/me", headers=user.auth).json()["quota"]["remaining"]


def test_changing_the_ad_reruns_every_cv_against_the_new_text(
    client, make_user, anthropic_fake
):
    user = make_user()
    analysis = _analysis(client, user, ["POÄNG 50", "POÄNG 60"])
    _run(client, user, analysis)
    anthropic_fake.calls.clear()

    res = _change_ad(client, user, analysis, NEW_AD)

    assert res.status_code == 202, res.text
    assessed = anthropic_fake.texts_sent("assess")
    assert len(assessed) == 2
    assert all(NEW_AD in text and OLD_AD not in text for text in assessed)
    body = _get(client, user, analysis)
    assert body["job_ad"] == NEW_AD
    assert [c["status"] for c in body["candidates"]] == ["done", "done"]


def test_ad_is_not_changed_when_the_quota_cannot_cover_every_cv(
    client, make_user, admin, anthropic_fake
):
    user = make_user()
    _set_quota(client, admin, user, 3)
    analysis = _analysis(client, user, ["POÄNG 50", "POÄNG 60"])
    _run(client, user, analysis)  # 1 kvar, men omkörningen behöver 2
    before = _get(client, user, analysis)
    anthropic_fake.calls.clear()

    res = _change_ad(client, user, analysis, NEW_AD)

    assert res.status_code == 403
    detail = res.json()["detail"]
    assert "kvot" in detail.lower() and "2" in detail and "1 kvar" in detail
    assert anthropic_fake.calls == []
    assert _get(client, user, analysis) == before


def test_ad_cannot_be_changed_while_a_run_is_in_progress(
    client, make_user, admin, anthropic_fake
):
    user = make_user()
    analysis = _analysis(client, user, ["POÄNG 50", "POÄNG 60"])
    admin.table("candidates").update(
        {"status": "processing", "last_progress_at": datetime.now(UTC).isoformat()}
    ).eq("analysis_id", analysis["id"]).eq("number", 1).execute()

    res = _change_ad(client, user, analysis, NEW_AD)

    assert res.status_code == 409
    assert anthropic_fake.calls == []
    body = _get(client, user, analysis)
    assert body["job_ad"] == OLD_AD
    assert sorted(c["status"] for c in body["candidates"]) == ["processing", "uploaded"]


def test_unchanged_or_empty_ad_is_refused_and_nothing_is_rerun(
    client, make_user, anthropic_fake
):
    user = make_user()
    analysis = _analysis(client, user, ["POÄNG 50"])
    _run(client, user, analysis)
    before = _get(client, user, analysis)
    anthropic_fake.calls.clear()

    unchanged = _change_ad(client, user, analysis, f"  {OLD_AD}\n")
    empty = _change_ad(client, user, analysis, "   ")

    assert unchanged.status_code == 422
    assert "samma" in unchanged.json()["detail"].lower()
    assert empty.status_code == 422
    assert anthropic_fake.calls == []
    assert _get(client, user, analysis) == before


def test_failed_and_never_run_cvs_are_rerun_too_and_old_assessments_are_cleared(
    client, make_user
):
    user = make_user()
    # En PDF utan text kan inte läsas och blir "kunde inte analyseras".
    analysis = _analysis(client, user, ["POÄNG 50", ""])
    _run(client, user, analysis)
    added = client.post(
        f"/analyses/{analysis['id']}/candidates",
        headers=user.auth,
        files=[("files", ("3.pdf", cv("POÄNG 70"), "application/pdf"))],
    )
    assert added.status_code == 201, added.text

    res = _change_ad(client, user, analysis, NEW_AD)

    # Svaret visar läget när omkörningen startar: allt köat, inget gammalt kvar.
    started = res.json()
    assert started["state"] == "running"
    assert all(
        c["status"] == "queued"
        and c["assessment"] is None
        and c["failure_reason"] is None
        for c in started["candidates"]
    )
    body = _get(client, user, analysis)
    assert sorted(c["status"] for c in body["candidates"]) == ["done", "done", "failed"]


def test_rerun_counts_against_the_quota_again(client, make_user):
    user = make_user()
    analysis = _analysis(client, user, ["POÄNG 50", "POÄNG 60"])
    _run(client, user, analysis)
    assert _remaining(client, user) == 500 - 2

    _change_ad(client, user, analysis, NEW_AD)

    assert _remaining(client, user) == 500 - 4


def test_analysis_tells_whether_the_quota_covers_rerunning_every_cv(
    client, make_user, admin
):
    user = make_user()
    analysis = _analysis(client, user, ["POÄNG 50", "POÄNG 60"])
    assert analysis["can_rerun_all"] is True

    _set_quota(client, admin, user, 1)

    assert _get(client, user, analysis)["can_rerun_all"] is False


def test_only_the_owner_can_change_the_ad(client, make_user, anthropic_fake):
    alice, bob = make_user(), make_user()
    analysis = _analysis(client, alice, ["POÄNG 50"])

    res = _change_ad(client, bob, analysis, NEW_AD)

    assert res.status_code == 404
    assert anthropic_fake.calls == []
    assert _get(client, alice, analysis)["job_ad"] == OLD_AD

"""Kvot, användningslogg och körningskontroll genom HTTP-API:et."""

from helpers import cv

CANDIDATE_FIELDS = {"score", "name", "alias", "original_path", "job_ad", "rationale"}


def _analysis(client, user, bodies):
    res = client.post(
        "/analyses",
        headers=user.auth,
        data={"title": "Backendutvecklare", "job_ad": "Vi söker en utvecklare."},
        files=[
            ("files", (f"{i}.pdf", cv(body), "application/pdf"))
            for i, body in enumerate(bodies)
        ],
    )
    assert res.status_code == 201, res.text
    return res.json()


def _run(client, user, analysis):
    return client.post(f"/analyses/{analysis['id']}/run", headers=user.auth)


def _set_quota(client, admin, user, limit):
    client.get("/me", headers=user.auth)  # skapar profilen
    admin.table("profiles").update({"cv_quota_limit": limit}).eq(
        "id", user.id
    ).execute()


def _me(client, user):
    return client.get("/me", headers=user.auth).json()


def _logs(admin, user):
    return (
        admin.table("usage_logs").select("*").eq("customer_id", user.id).execute().data
    )


def test_run_over_quota_is_blocked_before_start(
    client, make_user, admin, anthropic_fake
):
    user = make_user()
    _set_quota(client, admin, user, 2)
    analysis = _analysis(client, user, ["POÄNG 50"] * 3)

    res = _run(client, user, analysis)

    assert res.status_code == 403
    assert "kvot" in res.json()["detail"].lower()
    assert anthropic_fake.calls == []
    body = client.get(f"/analyses/{analysis['id']}", headers=user.auth).json()
    assert body["state"] == "ready"
    assert all(c["status"] == "uploaded" for c in body["candidates"])
    assert _logs(admin, user) == []


def test_run_exactly_at_quota_is_allowed(client, make_user, admin):
    user = make_user()
    _set_quota(client, admin, user, 2)
    analysis = _analysis(client, user, ["POÄNG 50"] * 2)

    assert _run(client, user, analysis).status_code == 202

    me = _me(client, user)
    assert me["quota"] == {"limit": 2, "used": 2, "remaining": 0}


def test_quota_accumulates_across_analyses_in_the_month(client, make_user, admin):
    user = make_user()
    _set_quota(client, admin, user, 2)
    first = _analysis(client, user, ["POÄNG 50"] * 2)
    second = _analysis(client, user, ["POÄNG 50"])
    assert _run(client, user, first).status_code == 202

    res = _run(client, user, second)

    assert res.status_code == 403


def test_failed_cvs_do_not_count_against_quota(client, make_user, admin):
    user = make_user()
    _set_quota(client, admin, user, 2)
    # En PDF utan text kan inte läsas och blir "kunde inte analyseras".
    analysis = _analysis(client, user, ["POÄNG 50", ""])
    assert _run(client, user, analysis).status_code == 202

    body = client.get(f"/analyses/{analysis['id']}", headers=user.auth).json()
    assert sorted(c["status"] for c in body["candidates"]) == ["done", "failed"]
    assert _me(client, user)["quota"] == {"limit": 2, "used": 1, "remaining": 1}
    (log,) = _logs(admin, user)
    assert log["cv_count"] == 1


def test_usage_log_has_customer_time_count_and_tokens_but_no_candidate_data(
    client, make_user, admin
):
    user = make_user()
    analysis = _analysis(client, user, ["POÄNG 50", "POÄNG 60"])
    assert _run(client, user, analysis).status_code == 202

    (log,) = _logs(admin, user)

    assert log["cv_count"] == 2
    # Fejken svarar 100 in / 50 ut per anrop, två anrop (tvätt, bedömning) per CV.
    assert log["input_tokens"] == 400
    assert log["output_tokens"] == 200
    assert log["created_at"]
    assert not CANDIDATE_FIELDS & set(log)
    assert set(log) == {
        "id",
        "customer_id",
        "created_at",
        "cv_count",
        "input_tokens",
        "output_tokens",
    }


def test_usage_log_survives_deleting_the_analysis(client, make_user, admin):
    user = make_user()
    analysis = _analysis(client, user, ["POÄNG 50"])
    assert _run(client, user, analysis).status_code == 202

    admin.table("analysis_batches").delete().eq("id", analysis["id"]).execute()

    assert len(_logs(admin, user)) == 1
    assert _me(client, user)["quota"]["used"] == 1


def test_usage_from_previous_months_does_not_count(client, make_user, admin):
    user = make_user()
    _set_quota(client, admin, user, 1)
    admin.table("usage_logs").insert(
        {
            "customer_id": user.id,
            "created_at": "2020-01-15T12:00:00+00:00",
            "cv_count": 400,
            "input_tokens": 1,
            "output_tokens": 1,
        }
    ).execute()
    analysis = _analysis(client, user, ["POÄNG 50"])

    assert _me(client, user)["quota"]["used"] == 0
    assert _run(client, user, analysis).status_code == 202

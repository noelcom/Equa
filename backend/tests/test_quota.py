"""Kvot, användningslogg och körningskontroll genom HTTP-API:et."""

from datetime import UTC, datetime, timedelta

from helpers import cv

from equa_backend.config import get_settings

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
    me = client.get("/me", headers=user.auth).json()
    me["quota"].pop("resets_at")  # beror på dagens datum, testas i test_me
    return me


def _logs(admin, user):
    return (
        admin.table("usage_logs").select("*").eq("customer_id", user.id).execute().data
    )


def test_run_over_quota_is_blocked_before_start(
    client, make_user, admin, anthropic_fake
):
    user = make_user()
    analysis = _analysis(client, user, ["POÄNG 50"] * 3)
    # Kvoten sänks efter uppladdningen, så körningen är det som stoppas.
    _set_quota(client, admin, user, 2)

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
    assert me["quota"] == {
        "limit": 2,
        "used": 2,
        "remaining": 0,
        "reserved": 0,
        "pending": 0,
    }


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
    assert _me(client, user)["quota"] == {
        "limit": 2,
        "used": 1,
        "remaining": 1,
        "reserved": 0,
        "pending": 0,
    }
    (log,) = _logs(admin, user)
    assert log["cv_count"] == 1


def test_usage_log_has_customer_time_count_and_tokens_but_no_candidate_data(
    client, make_user, admin
):
    user = make_user()
    analysis = _analysis(client, user, ["POÄNG 50", "POÄNG 60"])
    assert _run(client, user, analysis).status_code == 202

    logs = _logs(admin, user)

    # En rad per CV, så att ett klart CV räknas direkt.
    assert [log["cv_count"] for log in logs] == [1, 1]
    for log in logs:
        # Fejken svarar 100 in / 50 ut per anrop, två anrop (tvätt, bedömning) per CV.
        assert log["input_tokens"] == 200
        assert log["output_tokens"] == 100
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


def _set_progress(admin, analysis, status, minutes_ago):
    last_progress_at = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    admin.table("candidates").update(
        {"status": status, "last_progress_at": last_progress_at.isoformat()}
    ).eq("analysis_id", analysis["id"]).execute()


def test_creating_over_the_quota_is_refused_and_nothing_is_stored(
    client, make_user, admin
):
    user = make_user()
    _set_quota(client, admin, user, 2)

    res = client.post(
        "/analyses",
        headers=user.auth,
        data={"title": "Backendutvecklare", "job_ad": "Vi söker en utvecklare."},
        files=[
            ("files", (f"{i}.pdf", cv("POÄNG 50"), "application/pdf")) for i in range(3)
        ],
    )

    assert res.status_code == 403
    assert "kvot" in res.json()["detail"].lower()
    assert client.get("/analyses", headers=user.auth).json() == []
    assert admin.storage.from_("originals").list(user.id) == []


def test_creating_an_analysis_exactly_at_the_quota_is_allowed(client, make_user, admin):
    user = make_user()
    _set_quota(client, admin, user, 2)

    assert len(_analysis(client, user, ["POÄNG 50"] * 2)["candidates"]) == 2


def test_me_reports_reserved_and_pending_cvs_across_all_analyses(
    client, make_user, admin
):
    user = make_user()
    running = _analysis(client, user, ["POÄNG 50"] * 2)
    _analysis(client, user, ["POÄNG 50"] * 3)  # väntar på körning
    _analysis(client, user, ["POÄNG 50"])  # väntar på körning
    _set_progress(admin, running, "processing", minutes_ago=1)

    quota = _me(client, user)["quota"]

    assert quota["reserved"] == 2
    assert quota["pending"] == 4
    assert quota["remaining"] == 500 - 2


def test_stuck_cv_is_not_reserved_nor_pending_but_is_runnable(client, make_user, admin):
    user = make_user()
    analysis = _analysis(client, user, ["POÄNG 50"])
    assert analysis["runnable_count"] == 1
    _set_progress(admin, analysis, "processing", minutes_ago=60)

    quota = _me(client, user)["quota"]
    body = client.get(f"/analyses/{analysis['id']}", headers=user.auth).json()

    assert quota["reserved"] == 0
    assert quota["pending"] == 0
    assert body["runnable_count"] == 1


def test_runnable_count_covers_uploaded_cvs_and_drops_to_zero_while_running(
    client, make_user, admin
):
    user = make_user()
    analysis = _analysis(client, user, ["POÄNG 50"] * 2)
    assert analysis["runnable_count"] == 2
    _set_progress(admin, analysis, "processing", minutes_ago=1)

    body = client.get(f"/analyses/{analysis['id']}", headers=user.auth).json()

    assert body["runnable_count"] == 0


def test_analysis_tells_whether_it_can_run_and_how_many_more_cvs_fit(
    client, make_user, admin
):
    user = make_user()
    analysis = _analysis(client, user, ["POÄNG 50"] * 3)
    assert analysis["can_run"] is True
    assert analysis["addable_count"] == 497

    _set_quota(client, admin, user, 2)
    body = client.get(f"/analyses/{analysis['id']}", headers=user.auth).json()

    assert body["can_run"] is False
    assert body["addable_count"] == 0


def test_run_response_counts_the_started_cvs_as_reserved(client, make_user, admin):
    user = make_user()
    _set_quota(client, admin, user, 5)
    analysis = _analysis(client, user, ["POÄNG 50"] * 2)

    body = _run(client, user, analysis).json()

    assert body["runnable_count"] == 0
    assert body["addable_count"] == 3


def test_cv_finished_mid_run_counts_as_used_before_the_run_ends(
    client, make_user, admin, anthropic_fake
):
    settings = get_settings().model_copy(update={"max_parallel_cvs": 1})
    client.app.dependency_overrides[get_settings] = lambda: settings
    user = make_user()
    analysis = _analysis(client, user, ["POÄNG 50", "POÄNG 60"])
    seen = []

    def read_quota(text):
        if "POÄNG 60" in text:  # det första CV:t är klart, det andra bedöms
            seen.append(_me(client, user)["quota"])

    anthropic_fake.on_assess = read_quota

    assert _run(client, user, analysis).status_code == 202

    (quota,) = seen
    assert quota["used"] == 1
    assert quota["reserved"] == 1
    assert quota["remaining"] == 500 - 2

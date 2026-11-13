"""Raderingsdatum, flytta fram, radera direkt och det schemalagda raderingsjobbet (ADR 0007)."""

from datetime import UTC, datetime, timedelta

from helpers import ClientWithFailingStorage, make_pdf

from equa_backend.retention import delete_analysis, purge_expired


def _create(client, user, expires_at=None, files=None):
    data = {"title": "Backendutvecklare", "job_ad": "Vi söker en utvecklare."}
    if expires_at is not None:
        data["expires_at"] = expires_at.isoformat()
    files = files or [("cv.pdf", make_pdf("Ett CV"))]
    return client.post(
        "/analyses",
        headers=user.auth,
        data=data,
        files=[("files", (n, d, "application/pdf")) for n, d in files],
    )


def _days_left(analysis: dict) -> float:
    expires = datetime.fromisoformat(analysis["expires_at"])
    return (expires - datetime.now(UTC)).total_seconds() / 86400


def _in(**delta) -> datetime:
    return datetime.now(UTC) + timedelta(**delta)


def test_default_retention_is_seven_days(client, make_user):
    res = _create(client, make_user())

    assert res.status_code == 201
    assert 6.99 < _days_left(res.json()) < 7.01


def test_all_choosable_times_work(client, make_user):
    user = make_user()
    for delta, expected in [
        ({"hours": 24}, 1),
        ({"days": 7}, 7),
        ({"days": 14}, 14),
        ({"days": 30}, 30),  # eget datum
    ]:
        res = _create(client, user, _in(**delta))
        assert res.status_code == 201, res.text
        assert abs(_days_left(res.json()) - expected) < 0.01


def test_custom_date_beyond_the_cap_is_rejected_and_the_cap_is_shown(
    client, make_user, admin
):
    user = make_user()

    res = _create(client, user, _in(days=91))

    assert res.status_code == 422
    assert "90" in res.json()["detail"]
    assert client.get("/analyses", headers=user.auth).json() == []
    # Taket exponeras för gränssnittet.
    assert client.get("/me", headers=user.auth).json()["max_retention_days"] == 90


def test_custom_date_in_the_past_is_rejected(client, make_user):
    res = _create(client, make_user(), _in(hours=-1))

    assert res.status_code == 422


def test_date_can_be_moved_forward_up_to_the_cap_but_never_over(client, make_user):
    user = make_user()
    analysis = _create(client, user).json()
    url = f"/analyses/{analysis['id']}"

    ok = client.patch(
        url, headers=user.auth, json={"expires_at": _in(days=60).isoformat()}
    )
    assert ok.status_code == 200
    assert abs(_days_left(ok.json()) - 60) < 0.01

    # Taket räknas från idag (ADR 0007): inget datum längre fram än 90 dagar godtas.
    over = client.patch(
        url, headers=user.auth, json={"expires_at": _in(days=91).isoformat()}
    )
    assert over.status_code == 422
    assert abs(_days_left(client.get(url, headers=user.auth).json()) - 60) < 0.01


def test_date_cannot_be_moved_backwards_with_patch(client, make_user):
    user = make_user()
    analysis = _create(client, user).json()

    res = client.patch(
        f"/analyses/{analysis['id']}",
        headers=user.auth,
        json={"expires_at": _in(days=2).isoformat()},
    )

    assert res.status_code == 422


def test_another_user_cannot_change_or_delete_the_analysis(client, make_user):
    owner, other = make_user(), make_user()
    analysis = _create(client, owner).json()
    url = f"/analyses/{analysis['id']}"

    patch = client.patch(
        url, headers=other.auth, json={"expires_at": _in(days=30).isoformat()}
    )
    delete = client.delete(url, headers=other.auth)

    assert patch.status_code == 404
    assert delete.status_code == 404
    assert client.get(url, headers=owner.auth).status_code == 200


def _file_exists(admin, path: str) -> bool:
    folder, name = path.rsplit("/", 1)
    return any(f["name"] == name for f in admin.storage.from_("originals").list(folder))


def _paths(admin, analysis_id: str) -> list[str]:
    rows = (
        admin.table("candidates")
        .select("original_path")
        .eq("analysis_id", analysis_id)
        .execute()
        .data
    )
    return [r["original_path"] for r in rows]


def test_delete_now_removes_analysis_candidates_and_original_files(
    client, make_user, admin
):
    user = make_user()
    analysis = _create(
        client, user, files=[("a.pdf", make_pdf("A")), ("b.pdf", make_pdf("B"))]
    ).json()
    paths = _paths(admin, analysis["id"])
    assert len(paths) == 2 and all(_file_exists(admin, p) for p in paths)

    res = client.delete(f"/analyses/{analysis['id']}", headers=user.auth)

    assert res.status_code == 204
    assert (
        client.get(f"/analyses/{analysis['id']}", headers=user.auth).status_code == 404
    )
    assert (
        admin.table("candidates")
        .select("id")
        .eq("analysis_id", analysis["id"])
        .execute()
        .data
        == []
    )
    assert not any(_file_exists(admin, p) for p in paths)


def test_delete_now_also_removes_files_without_a_candidate_row(
    client, make_user, admin
):
    # Läget när en uppladdning hunnit lägga en fil i mappen men inte skapat sin rad (#18).
    user = make_user()
    analysis = _create(client, user).json()
    stray = f"{user.id}/{analysis['id']}/pagaende-uppladdning.pdf"
    admin.storage.from_("originals").upload(
        stray, make_pdf("Mitt i uppladdningen"), {"content-type": "application/pdf"}
    )

    res = client.delete(f"/analyses/{analysis['id']}", headers=user.auth)

    assert res.status_code == 204
    assert not _file_exists(admin, stray)


def test_analysis_is_gone_even_if_the_files_cannot_be_removed(client, make_user, admin):
    user = make_user()
    analysis = _create(client, user).json()

    # Kastar inte: analysen är borta och raderingsjobbet tar filerna senare.
    delete_analysis(ClientWithFailingStorage(admin), analysis["id"])

    assert (
        client.get(f"/analyses/{analysis['id']}", headers=user.auth).status_code == 404
    )


def test_purge_job_deletes_expired_analyses_and_files_but_keeps_the_rest(
    client, make_user, admin
):
    user = make_user()
    expired = _create(client, user).json()
    kept = _create(client, user).json()
    expired_paths, kept_paths = _paths(admin, expired["id"]), _paths(admin, kept["id"])
    # Utgånget datum kan inte sättas via API:et, så det sätts direkt i databasen.
    admin.table("analysis_batches").update(
        {"expires_at": _in(minutes=-1).isoformat()}
    ).eq("id", expired["id"]).execute()

    purge_expired(admin)

    assert (
        client.get(f"/analyses/{expired['id']}", headers=user.auth).status_code == 404
    )
    assert (
        admin.table("candidates")
        .select("id")
        .eq("analysis_id", expired["id"])
        .execute()
        .data
        == []
    )
    assert not any(_file_exists(admin, p) for p in expired_paths)
    assert client.get(f"/analyses/{kept['id']}", headers=user.auth).status_code == 200
    assert all(_file_exists(admin, p) for p in kept_paths)


def test_purge_job_removes_folders_whose_analysis_is_gone_but_keeps_the_rest(
    client, make_user, admin
):
    user = make_user()
    orphaned = _create(client, user).json()
    kept = _create(client, user).json()
    orphaned_paths, kept_paths = (
        _paths(admin, orphaned["id"]),
        _paths(admin, kept["id"]),
    )
    # Läget efter en radering där filerna inte gick att ta bort.
    admin.table("analysis_batches").delete().eq("id", orphaned["id"]).execute()

    purge_expired(admin)

    assert not any(_file_exists(admin, p) for p in orphaned_paths)
    assert all(_file_exists(admin, p) for p in kept_paths)


def test_usage_log_survives_deletion(client, make_user, admin):
    user = make_user()
    analysis = _create(client, user).json()
    admin.table("usage_logs").insert(
        {"customer_id": user.id, "cv_count": 1, "input_tokens": 10, "output_tokens": 5}
    ).execute()
    admin.table("analysis_batches").update(
        {"expires_at": _in(minutes=-1).isoformat()}
    ).eq("id", analysis["id"]).execute()

    purge_expired(admin)
    second = _create(client, user).json()
    client.delete(f"/analyses/{second['id']}", headers=user.auth)

    logs = (
        admin.table("usage_logs")
        .select("cv_count")
        .eq("customer_id", user.id)
        .execute()
        .data
    )
    assert logs == [{"cv_count": 1}]


def test_expired_analysis_cannot_be_revived_before_the_job_runs(
    client, make_user, admin
):
    user = make_user()
    analysis = _create(client, user).json()
    admin.table("analysis_batches").update(
        {"expires_at": _in(minutes=-1).isoformat()}
    ).eq("id", analysis["id"]).execute()

    res = client.patch(
        f"/analyses/{analysis['id']}",
        headers=user.auth,
        json={"expires_at": _in(days=5).isoformat()},
    )

    assert res.status_code == 404


def test_analysis_older_than_the_cap_can_be_extended_to_the_cap_from_today_but_no_further(
    client, make_user, admin
):
    user = make_user()
    analysis = _create(client, user).json()
    url = f"/analyses/{analysis['id']}"
    # Analysen skapades för 100 dagar sedan och raderas snart (ADR 0007: rullande tak).
    admin.table("analysis_batches").update(
        {
            "created_at": _in(days=-100).isoformat(),
            "expires_at": _in(days=1).isoformat(),
        }
    ).eq("id", analysis["id"]).execute()

    over = client.patch(
        url, headers=user.auth, json={"expires_at": _in(days=91).isoformat()}
    )
    ok = client.patch(
        url, headers=user.auth, json={"expires_at": _in(days=89).isoformat()}
    )

    assert over.status_code == 422
    assert ok.status_code == 200
    assert abs(_days_left(ok.json()) - 89) < 0.01


def test_the_cap_sits_at_exactly_90_days_from_today(client, make_user):
    user = make_user()
    analysis = _create(client, user).json()
    url = f"/analyses/{analysis['id']}"

    # En minut på var sida om gränsen: tillräckligt nära för att fånga fel som
    # `> 89` eller `>= 90`, men med marginal för tiden testet och servern tar.
    over = client.patch(
        url,
        headers=user.auth,
        json={"expires_at": _in(days=90, minutes=1).isoformat()},
    )
    at_cap = client.patch(
        url,
        headers=user.auth,
        json={"expires_at": _in(days=90, minutes=-1).isoformat()},
    )

    assert over.status_code == 422
    assert at_cap.status_code == 200

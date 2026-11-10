from datetime import UTC, datetime, timedelta

PDF = b"%PDF-1.4\n% testfil\n%%EOF\n"


def _create(
    client,
    user,
    *,
    title="Backendutvecklare",
    job_ad="Vi söker en utvecklare.",
    files=None,
):
    files = files if files is not None else [("cv1.pdf", PDF), ("cv2.pdf", PDF)]
    return client.post(
        "/analyses",
        headers=user.auth,
        data={"title": title, "job_ad": job_ad},
        files=[
            ("files", (name, content, "application/pdf")) for name, content in files
        ],
    )


def test_create_analysis_with_several_cvs_gives_anonymous_candidates(client, make_user):
    user = make_user()

    res = _create(
        client, user, files=[("anna-andersson.pdf", PDF), ("bo-berg.pdf", PDF)]
    )

    assert res.status_code == 201
    body = res.json()
    assert body["title"] == "Backendutvecklare"
    assert body["job_ad"] == "Vi söker en utvecklare."
    assert body["candidates"] == [{"alias": "Kandidat #1"}, {"alias": "Kandidat #2"}]
    # Originalfilnamn läcker aldrig.
    assert "anna" not in res.text.lower()
    assert "andersson" not in res.text.lower()


def test_analysis_survives_reload(client, make_user):
    user = make_user()
    created = _create(client, user).json()

    fetched = client.get(f"/analyses/{created['id']}", headers=user.auth)
    listed = client.get("/analyses", headers=user.auth)

    assert fetched.status_code == 200
    assert fetched.json() == created
    assert [a["id"] for a in listed.json()] == [created["id"]]
    assert listed.json()[0]["candidate_count"] == 2


def test_original_is_stored_in_private_bucket_and_expires_after_default_retention(
    client, make_user, admin
):
    user = make_user()

    created = _create(client, user, files=[("cv.pdf", PDF)]).json()

    rows = (
        admin.table("candidates")
        .select("original_path")
        .eq("analysis_id", created["id"])
        .execute()
        .data
    )
    assert len(rows) == 1
    path = rows[0]["original_path"]
    assert "cv.pdf" not in path
    assert admin.storage.from_("originals").download(path) == PDF
    bucket = admin.storage.get_bucket("originals")
    assert bucket.public is False

    expires_at = datetime.fromisoformat(created["expires_at"])
    expected = datetime.now(UTC) + timedelta(days=7)
    assert abs(expires_at - expected) < timedelta(minutes=5)


def test_file_over_size_limit_is_rejected_with_clear_message_and_nothing_is_saved(
    client, make_user, admin
):
    user = make_user()
    client.get("/me", headers=user.auth)
    admin.table("profiles").update({"max_file_size_mb": 1}).eq("id", user.id).execute()
    too_big = b"%PDF-" + b"0" * (1024 * 1024 + 1)

    res = _create(client, user, files=[("ok.pdf", PDF), ("stor.pdf", too_big)])

    assert res.status_code == 413
    assert "1 MB" in res.json()["detail"]
    assert client.get("/analyses", headers=user.auth).json() == []


def test_non_pdf_is_rejected(client, make_user):
    user = make_user()

    res = _create(client, user, files=[("cv.pdf", b"det har ar inte en pdf")])

    assert res.status_code == 400
    assert "PDF" in res.json()["detail"]


def test_analysis_requires_title_ad_and_at_least_one_cv(client, make_user):
    user = make_user()

    assert _create(client, user, title="  ").status_code == 422
    assert _create(client, user, job_ad="").status_code == 422
    assert _create(client, user, files=[]).status_code == 422


def test_users_only_reach_their_own_analyses(client, make_user):
    alice, bob = make_user(), make_user()
    alices = _create(client, alice).json()

    assert client.get(f"/analyses/{alices['id']}", headers=bob.auth).status_code == 404
    assert client.get("/analyses", headers=bob.auth).json() == []
    assert client.get("/analyses", headers=alice.auth).json()[0]["id"] == alices["id"]


def test_analyses_require_login(client):
    assert client.get("/analyses").status_code == 401
    assert (
        client.post("/analyses", data={"title": "a", "job_ad": "b"}).status_code == 401
    )

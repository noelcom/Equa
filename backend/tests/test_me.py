from datetime import UTC, datetime


def test_first_login_creates_profile_with_default_limits(client, make_user):
    user = make_user()

    res = client.get("/me", headers=user.auth)

    assert res.status_code == 200
    body = res.json()
    resets_at = datetime.fromisoformat(body["quota"].pop("resets_at"))
    assert resets_at.day == 1 and resets_at > datetime.now(UTC)
    assert body == {
        "quota": {"limit": 500, "remaining": 500},
        "default_retention_days": 7,
        "max_retention_days": 90,
        "max_file_size_mb": 25,
    }


def test_request_without_login_is_rejected(client):
    assert client.get("/me").status_code == 401


def test_request_with_invalid_token_is_rejected(client):
    res = client.get("/me", headers={"Authorization": "Bearer inte-en-riktig-token"})

    assert res.status_code == 401


def test_each_user_only_sees_their_own_profile(client, make_user, admin):
    alice, bob = make_user(), make_user()
    client.get("/me", headers=alice.auth)
    client.get("/me", headers=bob.auth)
    # Equas ägare ändrar Bobs gränser direkt i Supabase.
    admin.table("profiles").update(
        {"cv_quota_limit": 50, "default_retention_days": 14}
    ).eq("id", bob.id).execute()

    alice_me = client.get("/me", headers=alice.auth).json()
    bob_me = client.get("/me", headers=bob.auth).json()

    assert alice_me["quota"]["limit"] == 500
    assert alice_me["default_retention_days"] == 7
    assert bob_me["quota"]["limit"] == 50
    assert bob_me["default_retention_days"] == 14

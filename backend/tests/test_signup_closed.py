import uuid

import httpx

from equa_backend.config import get_settings


def test_open_signup_is_disabled(admin):
    """Ingen öppen registrering (ADR 0006): bara inbjudna får konto."""
    s = get_settings()
    email = f"equa-test-{uuid.uuid4().hex[:12]}@example.com"

    res = httpx.post(
        f"{s.supabase_url}/auth/v1/signup",
        headers={"apikey": s.supabase_anon_key},
        json={"email": email, "password": uuid.uuid4().hex},
    )

    assert res.status_code >= 400
    users = admin.auth.admin.list_users()
    assert all(u.email != email for u in users)

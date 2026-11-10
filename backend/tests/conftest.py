"""Testinfrastruktur.

Testerna anropar backendens HTTP-API som en riktig inloggad användare och
fejkar bara Anthropic-klienten (specens två testgränser). Varje test skapar
egna användare och raderar dem efteråt, så annan data i projektet lämnas ifred.
"""

import uuid
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from supabase import Client, create_client

from equa_backend.app import create_app
from equa_backend.config import get_settings
from equa_backend.deps import get_anthropic_client


class FakeAnthropic:
    """Fejkad Anthropic-klient med förutbestämda svar. Fylls på i #4."""

    def __init__(self) -> None:
        self.responses: list[object] = []


@dataclass
class TestUser:
    id: str
    email: str
    token: str

    @property
    def auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


@pytest.fixture(scope="session")
def admin() -> Client:
    s = get_settings()
    return create_client(s.supabase_url, s.supabase_service_role_key)


@pytest.fixture
def make_user(admin: Client):
    """Skapar bekräftade testanvändare utan mejl och raderar dem efter testet."""
    s = get_settings()
    created: list[str] = []

    def _make() -> TestUser:
        email = f"equa-test-{uuid.uuid4().hex[:12]}@example.com"
        password = uuid.uuid4().hex
        res = admin.auth.admin.create_user(
            {"email": email, "password": password, "email_confirm": True}
        )
        created.append(res.user.id)
        anon = create_client(s.supabase_url, s.supabase_anon_key)
        session = anon.auth.sign_in_with_password(
            {"email": email, "password": password}
        )
        return TestUser(id=res.user.id, email=email, token=session.session.access_token)

    yield _make
    for user_id in created:
        # Databasraderna försvinner via cascade, men filerna i storage måste städas separat.
        analyses = (
            admin.table("analysis_batches")
            .select("candidates(original_path)")
            .eq("user_id", user_id)
            .execute()
            .data
        )
        paths = [c["original_path"] for a in analyses for c in a["candidates"]]
        if paths:
            admin.storage.from_("originals").remove(paths)
        admin.auth.admin.delete_user(user_id)


@pytest.fixture
def anthropic_fake() -> FakeAnthropic:
    return FakeAnthropic()


@pytest.fixture
def client(anthropic_fake: FakeAnthropic) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_anthropic_client] = lambda: anthropic_fake
    return TestClient(app)

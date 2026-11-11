"""Testinfrastruktur.

Testerna anropar backendens HTTP-API som en riktig inloggad användare och
fejkar bara Anthropic-klienten (specens två testgränser). Varje test skapar
egna användare och raderar dem efteråt, så annan data i projektet lämnas ifred.
"""

import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from helpers import score_marker
from supabase import Client, create_client

from equa_backend.app import create_app
from equa_backend.config import get_settings
from equa_backend.deps import get_anthropic_client


def _text_of(kwargs: dict) -> str:
    """All text som skickades i ett anrop (system + meddelanden), för fejken att läsa."""
    parts: list[str] = []
    system = kwargs.get("system")
    if isinstance(system, str):
        parts.append(system)
    elif system:
        parts += [block["text"] for block in system]
    for message in kwargs["messages"]:
        content = message["content"]
        if isinstance(content, str):
            parts.append(content)
        else:
            parts += [block["text"] for block in content]
    return "\n".join(parts)


@dataclass
class FakeAnthropic:
    """Fejkad Anthropic-klient med förutbestämda svar.

    Tvätt-anropet är `messages.create` (text), bedömningen är `messages.parse`
    (strukturerad utdata). Poängen läses ur CV-textens rad 'POÄNG n', så ett test
    bestämmer utfallet via CV:ts innehåll och inte via anropsordningen.
    """

    # Namn som den fejkade AI-tvätten byter mot [BORTTAGET].
    names: list[str] = field(default_factory=list)
    # Sekunder varje anrop tar, så parallella anrop hinner överlappa.
    delay: float = 0.0
    # Anropas med CV-texten innan en bedömning returneras (t.ex. för att läsa progress).
    on_assess: Callable[[str], None] | None = None
    # Åsidosätter tvättsvaret (får CV-texten, returnerar "tvättad" text).
    wash_override: Callable[[str], str] | None = None
    # Åsidosätter bedömningen (får CV-texten, returnerar fält eller kastar).
    assess_override: Callable[[str], dict] | None = None

    def __post_init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.max_in_flight = 0
        self._in_flight = 0
        self._lock = threading.Lock()
        self.messages = self

    def _enter(self, kind: str, kwargs: dict) -> None:
        with self._lock:
            self.calls.append((kind, kwargs))
            self._in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self._in_flight)
        if self.delay:
            time.sleep(self.delay)

    def _leave(self) -> None:
        with self._lock:
            self._in_flight -= 1

    def texts_sent(self, kind: str) -> list[str]:
        return [_text_of(kw) for k, kw in self.calls if k == kind]

    def create(self, **kwargs):
        self._enter("wash", kwargs)
        try:
            text = _text_of(kwargs)
            if self.wash_override:
                washed = self.wash_override(text)
            else:
                washed = text
                for name in self.names:
                    washed = washed.replace(name, "[BORTTAGET]")
            block = SimpleNamespace(type="text", text=washed)
            return SimpleNamespace(content=[block], usage=_usage())
        finally:
            self._leave()

    def parse(self, **kwargs):
        self._enter("assess", kwargs)
        try:
            text = _text_of(kwargs)
            if self.on_assess:
                self.on_assess(text)
            if self.assess_override:
                fields = self.assess_override(text)
            else:
                fields = {
                    "score": score_marker(text)
                    if score_marker(text) is not None
                    else 50,
                    "years_experience": 5,
                    "education_match": "Relevant utbildning.",
                    "concrete_results": "Levererade flera projekt.",
                    "key_skills": ["Python", "SQL"],
                    "missing_requirements": "Inga större gap.",
                    "rationale": "Bra matchning mot annonsen.",
                }
            parsed = kwargs["output_format"](**fields)
            return SimpleNamespace(parsed_output=parsed, usage=_usage())
        finally:
            self._leave()


def _usage() -> SimpleNamespace:
    return SimpleNamespace(
        input_tokens=100,
        output_tokens=50,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
    )


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

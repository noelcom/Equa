"""Inställningar som styr körningen ska avvisas om de är omöjliga."""

import pytest
from pydantic import ValidationError

from equa_backend.config import Settings


@pytest.mark.parametrize("value", [0, -1])
def test_parallel_limit_below_one_is_rejected(value):
    with pytest.raises(ValidationError):
        Settings(max_parallel_cvs=value)


@pytest.mark.parametrize("value", ["", "inte-en-nyckel", "kort"])
def test_invalid_identity_key_is_rejected(value):
    with pytest.raises(ValidationError):
        Settings(identity_key=value)


def test_missing_identity_key_is_rejected(monkeypatch):
    monkeypatch.delenv("IDENTITY_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            supabase_url="u",
            supabase_anon_key="a",
            supabase_service_role_key="s",
        )

"""Inställningar som styr körningen ska avvisas om de är omöjliga."""

import pytest
from pydantic import ValidationError

from equa_backend.config import Settings


@pytest.mark.parametrize("value", [0, -1])
def test_parallel_limit_below_one_is_rejected(value):
    with pytest.raises(ValidationError):
        Settings(max_parallel_cvs=value)

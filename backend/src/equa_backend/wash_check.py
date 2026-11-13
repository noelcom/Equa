"""Kontroller av AI-tvättens utfall mot kriteriet i ADR 0008 (#28).

Används av `scripts/wash_check.py`. Ren logik utan nätverksanrop.
"""

import re
from pathlib import Path

from equa_backend.anonymize import contains_contact_details

_PRONOUNS = re.compile(r"\b(?:han|hon|honom|henne|hans|hennes)\b", re.IGNORECASE)
# Sakinnehåll som ska stå kvar ordagrant: siffror, versaler (AWS) och interna versaler (PostgreSQL).
_FACTS = re.compile(
    r"\d+(?:[.,]\d+)?|\b[A-ZÅÄÖ]{2,}\b|\b[A-Za-zåäö]*[a-zåäö][A-ZÅÄÖ][A-Za-zåäö]*\b"
)


def load_identifiers(path: Path) -> list[str]:
    """Läser identifierare, en per rad. Tomma rader och rader som börjar med # hoppas över."""
    lines = (line.strip() for line in path.read_text(encoding="utf-8").splitlines())
    return [line for line in lines if line and not line.startswith("#")]


def find_leaked(washed: str, identifiers: list[str]) -> list[str]:
    """Det som borde ha tagits bort men finns kvar i den tvättade texten."""
    low = washed.casefold()
    leaks = [i for i in identifiers if i.casefold() in low]
    leaks += [f"pronomen: {m.group()}" for m in _PRONOUNS.finditer(washed)]
    if contains_contact_details(washed):
        leaks.append("kontaktuppgift")
    return leaks


def find_changed_facts(original: str, washed: str, identifiers: list[str]) -> list[str]:
    """Siffror och facktermer i originalet som saknas i den tvättade texten.

    Identifierarna tas bort ur originalet först, så att t.ex. dagen i ett födelsedatum
    inte räknas som sakinnehåll.
    """
    cleaned = original
    for ident in identifiers:
        cleaned = re.sub(re.escape(ident), " ", cleaned, flags=re.IGNORECASE)
    kept = set(_FACTS.findall(washed))
    missing: list[str] = []
    for fact in _FACTS.findall(cleaned):
        if fact not in kept and fact not in missing:
            missing.append(fact)
    return missing

"""Regelbaserad tvätt av kontaktuppgifter: förtvätten och säkerhetskontrollen.

Samma mönster används på båda ställena. Förtvätten tar bort det som kan fångas
med regex innan texten lämnar vår server. Säkerhetskontrollen kör mönstren igen
på den AI-tvättade texten som ett sista nät (GLOSSARY: Förtvätt, Säkerhetskontroll).

Namn, adresser, ålder och pronomen kan inte fångas med regex. Det är AI-tvättens jobb.
"""

import re

PLACEHOLDER = "[BORTTAGET]"

# Observera ordningen: de mest specifika mönstren först, så att t.ex. ett
# personnummer inte delvis fångas som ett telefonnummer.
_PATTERNS = [
    # Personnummer: ÅÅMMDD-NNNN, ÅÅÅÅMMDDNNNN, med - eller + som skiljetecken.
    re.compile(
        r"(?<!\d)(?:\d{2})?\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])[-+]?\d{4}(?!\d)"
    ),
    # E-postadresser.
    re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),
    # Webbadresser. Profiler på kända sajter fångas även utan http(s)://. Vanliga
    # toppdomäner som .net eller .js lämnas ifred så att "ASP.NET" och "Node.js" består.
    re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE),
    re.compile(
        r"\b(?:linkedin|github|gitlab|facebook|instagram|twitter|bitbucket|behance|dribbble)"
        r"\.com\S*",
        re.IGNORECASE,
    ),
    # Telefonnummer: internationella (+46 70 123 45 67) och svenska (070-123 45 67).
    # Kräver att numret inte följer på en siffra, punkt eller bindestreck, så att
    # årsintervall som "2018-2021" lämnas ifred.
    re.compile(r"(?<![\w.\-])\+\d(?:[ \-]?\(?\d\)?){7,13}"),
    re.compile(r"(?<![\w.\-])0\d(?:[ \-]?\d){7,9}(?!\d)"),
]


def pre_wash(text: str) -> str:
    """Byter ut e-post, telefon, personnummer och webbadresser mot [BORTTAGET]."""
    for pattern in _PATTERNS:
        text = pattern.sub(PLACEHOLDER, text)
    return text


def contains_contact_details(text: str) -> bool:
    """Sant om texten fortfarande innehåller något som förtvätten borde ha tagit bort."""
    return any(pattern.search(text) for pattern in _PATTERNS)

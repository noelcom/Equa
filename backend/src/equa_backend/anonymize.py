"""Regelbaserad tvätt av kontaktuppgifter: förtvätten och säkerhetskontrollen.

Samma mönster används på båda ställena. Förtvätten tar bort det som kan fångas
med regex innan texten lämnar vår server. Säkerhetskontrollen kör mönstren igen
på den AI-tvättade texten som ett sista nät (GLOSSARY: Förtvätt, Säkerhetskontroll).

Namn, adresser, ålder och pronomen kan inte fångas med regex. Det är AI-tvättens jobb.
"""

import re

PLACEHOLDER = "[BORTTAGET]"

# Personnummer: ÅÅMMDD-NNNN, ÅÅÅÅMMDDNNNN, med - eller + som skiljetecken.
_PERSONNUMMER = re.compile(
    r"(?<!\d)(?:\d{2})?\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])[-+]?\d{4}(?!\d)"
)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Telefonnummer: internationella (+46 70 123 45 67, 0046 70 ..., +46 (0)70 ...) och
# svenska (070-123 45 67, 070 - 123 45 67, (070) 123 45 67). Kräver att numret inte
# följer på en siffra, punkt eller bindestreck, så att årsintervall som
# "2018-2021" lämnas ifred.
_PHONE_PATTERNS = [
    re.compile(r"(?<![\w.\-])(?:\+|00)\d(?:[ \-]*[()]?\d[()]?){7,13}(?!\d)"),
    re.compile(r"(?<![\w.\-])\(?0(?:\)?[ \-]*\d){8,10}(?!\d)"),
]

# Observera ordningen: de mest specifika mönstren först, så att t.ex. ett
# personnummer inte delvis fångas som ett telefonnummer.
_PATTERNS = [
    _PERSONNUMMER,
    _EMAIL,
    # Webbadresser. Profiler på kända sajter fångas även utan http(s)://. Vanliga
    # toppdomäner som .net eller .js lämnas ifred så att "ASP.NET" och "Node.js" består.
    re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE),
    re.compile(
        r"\b(?:linkedin|github|gitlab|facebook|instagram|twitter|bitbucket|behance|dribbble)"
        r"\.com\S*",
        re.IGNORECASE,
    ),
    *_PHONE_PATTERNS,
]


def extract_contacts(text: str) -> tuple[str | None, str | None]:
    """Första e-postadressen och första telefonnumret i texten, i den ordningen.

    Körs på originaltexten före förtvätten. Personnummer räknas bort först så att de
    inte tas för telefonnummer.
    """
    text = _PERSONNUMMER.sub(PLACEHOLDER, text)
    email = _EMAIL.search(text)
    phones = [m for p in _PHONE_PATTERNS if (m := p.search(text))]
    phone = min(phones, key=lambda m: m.start(), default=None)
    return (
        email.group().strip() if email else None,
        phone.group().strip() if phone else None,
    )


def pre_wash(text: str) -> str:
    """Byter ut e-post, telefon, personnummer och webbadresser mot [BORTTAGET]."""
    for pattern in _PATTERNS:
        text = pattern.sub(PLACEHOLDER, text)
    return text


def contains_contact_details(text: str) -> bool:
    """Sant om texten fortfarande innehåller något som förtvätten borde ha tagit bort."""
    return any(pattern.search(text) for pattern in _PATTERNS)

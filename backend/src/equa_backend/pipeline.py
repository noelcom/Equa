"""Pipelinen som gör ett uppladdat CV till en anonym bedömning.

Steg per CV: förtvätt, AI-tvätt, säkerhetskontroll, bedömning. Den tvättade
texten finns bara i minnet under körningen och sparas aldrig (ADR 0004).
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import anthropic
from pydantic import BaseModel, Field, ValidationError
from supabase import Client, create_client

from equa_backend.anonymize import contains_contact_details, pre_wash
from equa_backend.candidates import Candidate
from equa_backend.config import Settings
from equa_backend.pdf import UnreadablePdf, pdf_to_text

BUCKET = "originals"
log = logging.getLogger(__name__)

WASH_INSTRUCTION = """\
Du är en strikt dataskydds-assistent. Din enda uppgift är att ta CV-texten och \
byta ut allt som kan identifiera personen mot "[BORTTAGET]": namn, fysiska \
adresser, ålder och födelsedatum, samt könspronomen (han/hon). Ändra ingenting i \
den professionella erfarenheten, utbildningen eller kompetenserna. Returnera \
enbart den tvättade texten, utan förklaringar."""

ASSESSMENT_INSTRUCTION = """\
Du är en objektiv, extremt analytisk och fördomsfri AI-rekryterare. Ditt uppdrag \
är att leta efter verklig kompetens och relevant erfarenhet. Du är stenhård och \
realistisk i din bedömning av ansvarsnivå och senioritet.

Tillvägagångssätt:
1. Analysera ansvarsnivå: stirra dig inte blind på att en bransch matchar. Om \
annonsen söker en ledare, chef eller specialist och kandidaten enbart har praktik \
eller instegsjobb ska poängen dras ner kraftigt.
2. Ignorera CV:ts design och format.
3. Värdera översättbara färdigheter och praktisk problemlösning, men respektera \
hårda krav.

Anonymitet: CV-texten är anonymiserad. Försök aldrig gissa namn, kön, ålder eller \
etnicitet, och låt det aldrig påverka bedömningen.

Poängskala (0-100):
- 0-30: långt ifrån kraven.
- 31-50: uppfyller vissa grundkrav men saknar rätt ansvarsnivå.
- 51-75: stark kandidat som uppfyller de flesta krav.
- 76-90: extremt kvalificerad, överträffar kraven.
- 91-100: perfekt, exceptionell matchning.

Skriv alla bedömningstexter på svenska."""


class Assessment(BaseModel):
    """Bedömningen av en kandidat. Fast schema som AI:n måste följa."""

    score: int = Field(ge=0, le=100, description="Matchningspoäng 0-100.")
    years_experience: int = Field(
        ge=0, description="Antal relevanta år i branschen enligt CV:t."
    )
    education_match: str = Field(description="Kort text om hur utbildningen matchar.")
    concrete_results: str = Field(
        description="Kort text om konkreta resultat och projekt."
    )
    key_skills: list[str] = Field(description="Nyckelkompetenser, en per post.")
    missing_requirements: str = Field(
        description="Kort text om vilka krav i annonsen som saknas."
    )
    rationale: str = Field(description="Motivering till poängen.")


class PipelineError(Exception):
    """Ett CV stoppades. `reason` är en kort standardtext utan CV-innehåll."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _set(supabase: Client, candidate_id: str, **fields) -> None:
    # claimed_at är en hjärtslagsstämpel: den visar att CV:t fortfarande arbetas på.
    fields["claimed_at"] = datetime.now(UTC).isoformat()
    supabase.table("candidates").update(fields).eq("id", candidate_id).execute()


TRANSIENT_REASON = "AI-tjänsten var tillfälligt otillgänglig. Försök igen senare."


def _is_transient(e: Exception) -> bool:
    if isinstance(e, anthropic.APIStatusError):
        return e.status_code in (408, 409, 429) or e.status_code >= 500
    return isinstance(e, anthropic.APIConnectionError)  # inkl. timeout


def _with_retry(settings: Settings, call):
    """Kör ett Anthropic-anrop och provar om tillfälliga fel med växande väntetid."""
    for attempt in range(1, settings.anthropic_max_attempts + 1):
        try:
            return call()
        except anthropic.APIError as e:
            if not _is_transient(e):
                raise
            if attempt == settings.anthropic_max_attempts:
                log.error(
                    "Anthropic otillgängligt efter %d försök: %s (status %s)",
                    attempt,
                    type(e).__name__,
                    getattr(e, "status_code", None),
                )
                raise PipelineError(TRANSIENT_REASON) from None
            time.sleep(settings.anthropic_retry_backoff_seconds * 2 ** (attempt - 1))


def _wash(client: anthropic.Anthropic, settings: Settings, text: str) -> str:
    response = _with_retry(
        settings,
        lambda: client.messages.create(
            model=settings.wash_model,
            max_tokens=8192,
            system=WASH_INSTRUCTION,
            messages=[{"role": "user", "content": text}],
        ),
    )
    if getattr(response, "stop_reason", None) == "max_tokens":
        # Ett avklippt CV skulle ge en orättvist låg poäng.
        raise PipelineError("CV:t var för långt för att anonymiseras.")
    washed = "".join(b.text for b in response.content if b.type == "text")
    if getattr(response, "stop_reason", None) == "refusal" or not washed.strip():
        # Ett tomt svar eller en vägran får aldrig matas vidare: en tom text skulle
        # ge en missvisande låg poäng i stället för "kunde inte analyseras".
        raise PipelineError("Kunde inte anonymiseras säkert.")
    return washed


def _assess(
    client: anthropic.Anthropic, settings: Settings, job_ad: str, washed: str
) -> Assessment:
    try:
        response = _with_retry(
            settings,
            lambda: client.messages.parse(
                model=settings.assessment_model,
                max_tokens=2000,
                system=[
                    {
                        "type": "text",
                        "text": ASSESSMENT_INSTRUCTION,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[
                    {
                        "role": "user",
                        "content": [
                            # Annonsen är gemensam för alla CV:n i analysen och cachas.
                            {
                                "type": "text",
                                "text": f"ARBETSANNONS:\n{job_ad}",
                                "cache_control": {"type": "ephemeral"},
                            },
                            {
                                "type": "text",
                                "text": f"KANDIDATENS ANONYMISERADE CV:\n{washed}",
                            },
                        ],
                    }
                ],
                output_format=Assessment,
            ),
        )
    except ValidationError:
        # AI-svaret följde inte schemat. Aldrig poäng 0: CV:t blir "kunde inte analyseras".
        raise PipelineError("Bedömningen kunde inte tolkas.") from None
    if response.parsed_output is None:
        raise PipelineError("Bedömningen kunde inte tolkas.")
    return response.parsed_output


def _process(
    client: anthropic.Anthropic,
    settings: Settings,
    job_ad: str,
    candidate: Candidate,
) -> None:
    candidate_id = candidate.id
    # En egen klient per CV: supabase-py garanterar inte trådsäkerhet, och sju trådar på
    # en delad HTTP/2-anslutning gav sporadiska "Server disconnected".
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    try:
        _set(supabase, candidate_id, status="processing", step="pre_wash")
        original = supabase.storage.from_(BUCKET).download(candidate.original_path)
        try:
            text = pdf_to_text(original)
        except UnreadablePdf:
            raise PipelineError(
                "Kunde inte läsa texten. Är CV:t en inskannad bild?"
            ) from None
        text = pre_wash(text)
        _set(supabase, candidate_id, step="ai_wash")
        washed = _wash(client, settings, text)
        _set(supabase, candidate_id, step="safety_check")
        if contains_contact_details(washed):
            raise PipelineError("Kunde inte anonymiseras säkert.")
        _set(supabase, candidate_id, step="assessment")
        assessment = _assess(client, settings, job_ad, washed)
        _set(
            supabase,
            candidate_id,
            status="done",
            step=None,
            failure_reason=None,
            **assessment.model_dump(),
        )
    except PipelineError as e:
        _set(
            supabase, candidate_id, status="failed", step=None, failure_reason=e.reason
        )
    except Exception as e:  # noqa: BLE001 - ett CV som kraschar ska aldrig stoppa de andra
        # Logga bara typen: undantagsmeddelanden och stackspår kan innehålla CV-text.
        log.error("Oväntat fel i pipelinen: %s", type(e).__name__)
        _set(
            supabase,
            candidate_id,
            status="failed",
            step=None,
            failure_reason="Oväntat fel vid analysen.",
        )


def run_analysis(
    supabase: Client,
    client: anthropic.Anthropic,
    settings: Settings,
    job_ad: str,
    candidates: list[Candidate],
) -> None:
    """Kör alla givna kandidater genom pipelinen, högst `max_parallel_cvs` åt gången."""
    with ThreadPoolExecutor(max_workers=settings.max_parallel_cvs) as pool:
        for candidate in candidates:
            pool.submit(_process, client, settings, job_ad, candidate)
    # Sista nätet: om en arbetare föll samtidigt som den försökte spara felet (t.ex. vid
    # ett nätverksavbrott) får CV:t inte stå som "pågår" för alltid.
    (
        supabase.table("candidates")
        .update(
            {
                "status": "failed",
                "step": None,
                "failure_reason": "Oväntat fel vid analysen.",
            }
        )
        .in_("id", [c.id for c in candidates])
        .in_("status", ["queued", "processing"])
        .execute()
    )

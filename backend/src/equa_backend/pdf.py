import io

from pdfminer.high_level import extract_text


class UnreadablePdf(Exception):
    """PDF:en gick inte att läsa eller saknar text (t.ex. en inskannad bild, ADR 0005)."""


def pdf_to_text(data: bytes) -> str:
    """Läser text ur en PDF lokalt. Bilder kastas, ingen OCR (ADR 0005)."""
    try:
        text = extract_text(io.BytesIO(data))
    except Exception as e:
        raise UnreadablePdf from e
    if not text.strip():
        raise UnreadablePdf
    return text

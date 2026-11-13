"""Delade testhjälpare."""

import re


def make_pdf(text: str) -> bytes:
    """Bygger en liten men giltig PDF med texten på egna rader (Helvetica, WinAnsi).

    Riktiga PDF:er behövs eftersom förtvätten läser texten lokalt. Bygger för hand
    för att slippa ett tungt PDF-bibliotek bara för testerna.
    """

    def escape(line: str) -> str:
        out = []
        for byte in line.encode("cp1252"):
            if byte in b"()\\" or byte > 126:
                out.append(f"\\{byte:03o}")
            else:
                out.append(chr(byte))
        return "".join(out)

    content = "BT /F1 11 Tf 14 TL 50 780 Td\n"
    content += "".join(f"({escape(line)}) Tj T*\n" for line in text.split("\n"))
    content += "ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            "/Contents 5 0 R /Resources << /Font << /F1 4 0 R >> >> >>"
        ),
        (
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
            "/Encoding /WinAnsiEncoding >>"
        ),
        f"<< /Length {len(content.encode('cp1252'))} >>\nstream\n{content}\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body.encode("cp1252") + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_at}\n%%EOF\n"
    ).encode()
    return bytes(out)


class _FailingStorage:
    """Storage där borttagning alltid misslyckas, i övrigt som den riktiga."""

    def __init__(self, real):
        self._real = real

    def from_(self, bucket):
        outer = self._real.from_(bucket)

        class Bucket:
            def __getattr__(self, name):
                return getattr(outer, name)

            def remove(self, paths):
                raise RuntimeError("Storage nere")

        return Bucket()


class ClientWithFailingStorage:
    """En Supabase-klient vars storage inte kan ta bort filer. Allt annat är riktigt."""

    def __init__(self, real):
        self._real = real
        self.storage = _FailingStorage(real.storage)

    def __getattr__(self, name):
        return getattr(self._real, name)


def file_exists(admin, path: str) -> bool:
    """Finns originalfilen i lagringen?"""
    folder, name = path.rsplit("/", 1)
    return any(f["name"] == name for f in admin.storage.from_("originals").list(folder))


def original_paths(admin, analysis_id: str) -> list[str]:
    """Sökvägarna till analysens originalfiler, enligt kandidatraderna."""
    rows = (
        admin.table("candidates")
        .select("original_path")
        .eq("analysis_id", analysis_id)
        .execute()
        .data
    )
    return [r["original_path"] for r in rows]


def user_original_paths(admin, user_id: str) -> list[str]:
    """Sökvägarna till originalfilerna i alla användarens analyser."""
    rows = (
        admin.table("analysis_batches")
        .select("candidates(original_path)")
        .eq("user_id", user_id)
        .execute()
        .data
    )
    return [c["original_path"] for a in rows for c in a["candidates"]]


def cv(body: str) -> bytes:
    """Ett CV som PDF. Raden 'POÄNG n' styr vilken poäng fejken ger."""
    return make_pdf(body)


def score_marker(text: str) -> int | None:
    match = re.search(r"POÄNG (\d+)", text)
    return int(match.group(1)) if match else None

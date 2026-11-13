"""Kontroll av AI-tvätten mot kriteriet i ADR 0008 (#28).

Tvättar varje CV (förtvätt plus AI-tvätt) och rapporterar
(a) identifierare som finns kvar: namn och adresser ur `identifierare.txt`, könspronomen
    och kontaktuppgifter, samt
(b) siffror och facktermer som försvunnit eller ändrats.
Båda ska vara noll. Siffror och facktermer är en grov kontroll: läs listan, den kan
innehålla falsklarm. Den fångar inte ändrade titlar eller omskrivna meningar.

Anropar riktiga Anthropic och kostar pengar, så skriptet ligger utanför pytest.
Användning (från backend/):
    uv run python scripts/wash_check.py [testdata-mapp]
Mappen ska innehålla cv-*.txt och identifierare.txt, en identifierare per rad (namn,
adresser, födelsedatum och annat som tvätten ska ta bort).
Avslutskoden är 1 om något läckte eller något sakinnehåll ändrades.
Ett CV som tvätten stoppar (för långt) hoppas över och räknas inte.
"""

import argparse
import sys
from pathlib import Path

import anthropic

from equa_backend.anonymize import pre_wash
from equa_backend.config import REPO_ROOT, get_settings
from equa_backend.pipeline import PipelineError, Usage, _wash
from equa_backend.wash_check import find_changed_facts, find_leaked, load_identifiers


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("data", nargs="?", type=Path, default=REPO_ROOT / "testdata")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.anthropic_api_key:
        print("ANTHROPIC_API_KEY saknas i .env", file=sys.stderr)
        return 1
    ids_file = args.data / "identifierare.txt"
    if not ids_file.exists():
        print(
            f"{ids_file} saknas: lista namn och adresser, en per rad", file=sys.stderr
        )
        return 1
    identifiers = load_identifiers(ids_file)
    cvs = sorted(args.data.glob("cv-*.txt"))
    if not cvs:
        print(f"Inga cv-*.txt i {args.data}", file=sys.stderr)
        return 1
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    print(f"Tvättmodell: {settings.wash_model}")
    bad = False
    for cv in cvs:
        text = pre_wash(cv.read_text(encoding="utf-8"))
        try:
            washed = _wash(client, settings, text, Usage())
        except PipelineError as e:
            print(f"{cv.name}: hoppas över ({e.reason})")
            continue
        leaks = find_leaked(washed, identifiers)
        changed = find_changed_facts(text, washed, identifiers)
        bad = bad or bool(leaks or changed)
        print(f"{cv.name}: {len(leaks)} kvar, {len(changed)} ändrade")
        if leaks:
            print(f"  kvar: {leaks}")
        if changed:
            print(f"  saknas efter tvätt: {changed}")
    print("Klarar kriteriet" if not bad else "Klarar inte kriteriet")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

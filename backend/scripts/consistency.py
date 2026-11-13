"""Konsekvenstest av bedömningssteget (#25, ADR 0008).

Tvättar varje CV en gång och kör sedan bedömningen två gånger på samma tvättade
text, så att skillnaden bara beror på bedömningssteget. Rapporterar största
poängskillnad mot kriteriet ±5.

Anropar riktiga Anthropic och kostar pengar, så skriptet ligger utanför pytest.
Användning (från backend/):
    uv run python scripts/consistency.py [testdata-mapp] [--runs N]
Mappen ska innehålla annons-techlead.txt och cv-*.txt. Standard är ../testdata.
Avslutskoden är 1 om någon skillnad överstiger gränsen.
Ett CV som tvätten stoppar (för långt) hoppas över och räknas inte.
"""

import argparse
import sys
from pathlib import Path

import anthropic

from equa_backend.anonymize import pre_wash
from equa_backend.config import REPO_ROOT, get_settings
from equa_backend.pipeline import PipelineError, Usage, _assess, _wash

MAX_DIFF = 5


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("data", nargs="?", type=Path, default=REPO_ROOT / "testdata")
    parser.add_argument(
        "--runs", type=int, default=2, help="bedömningar per CV (standard 2)"
    )
    args = parser.parse_args()
    if args.runs < 2:
        parser.error("--runs måste vara minst 2")

    settings = get_settings()
    if not settings.anthropic_api_key:
        print("ANTHROPIC_API_KEY saknas i .env", file=sys.stderr)
        return 1
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    job_ad = (args.data / "annons-techlead.txt").read_text(encoding="utf-8")
    cvs = sorted(args.data.glob("cv-*.txt"))
    if not cvs:
        print(f"Inga cv-*.txt i {args.data}", file=sys.stderr)
        return 1

    print(
        f"Bedömningsmodell: {settings.assessment_model}, tvättmodell: {settings.wash_model}"
    )
    worst = 0
    for cv in cvs:
        try:
            usage = Usage()
            washed = _wash(
                client, settings, pre_wash(cv.read_text(encoding="utf-8")), usage
            )
            scores = [
                _assess(client, settings, job_ad, washed, usage).score
                for _ in range(args.runs)
            ]
        except PipelineError as e:
            print(f"{cv.name}: hoppas över ({e.reason})")
            continue
        diff = max(scores) - min(scores)
        worst = max(worst, diff)
        verdict = "OK" if diff <= MAX_DIFF else "FÖR STOR"
        print(f"{cv.name}: poäng {scores}, skillnad {diff} ({verdict})")

    print(f"Största poängskillnad: {worst} (gräns ±{MAX_DIFF})")
    return 1 if worst > MAX_DIFF else 0


if __name__ == "__main__":
    sys.exit(main())

# Equa backend

FastAPI. Beroenden och körning går via `uv`. Bara `python` finns inte på PATH, så använd alltid `uv run python`.

Kommandon (från `backend/`):

- Starta: `uv run uvicorn equa_backend.app:app --port 8000`
- Tester: `uv run pytest` (hela sviten tar ca 6 minuter, eftersom den går mot riktiga Supabase. Enstaka nätverksfel som `httpx.Conn…` är flaky, kör om filen)
- En testfil: `uv run pytest tests/test_export.py -q`
- Lint: `uv run ruff check .` och `uv run ruff format .`

Profilraden skapas först vid första inloggningen, så kvoten (`cv_quota_limit`) kan bara sättas efter den.

Frontend: `npm run check` i `frontend/` (typkontroll och lint).

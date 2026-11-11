import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from equa_backend.config import get_settings
from equa_backend.deps import get_supabase
from equa_backend.retention import purge_loop
from equa_backend.routes import analyses, me


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Timvis raderingsjobb (ADR 0004). Går inte att stänga av. Flera instanser är ofarligt,
    # eftersom radering av redan raderade analyser är en tom operation.
    task = asyncio.create_task(
        purge_loop(get_supabase(), get_settings().purge_interval_seconds)
    )
    try:
        yield
    finally:
        task.cancel()


def create_app() -> FastAPI:
    app = FastAPI(title="Equa", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.include_router(me.router)
    app.include_router(analyses.router)
    return app


app = create_app()

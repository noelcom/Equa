from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from equa_backend.config import get_settings
from equa_backend.routes import me


def create_app() -> FastAPI:
    app = FastAPI(title="Equa")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.include_router(me.router)
    return app


app = create_app()

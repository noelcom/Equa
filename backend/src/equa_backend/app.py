from fastapi import FastAPI

from equa_backend.routes import me


def create_app() -> FastAPI:
    app = FastAPI(title="Equa")
    app.include_router(me.router)
    return app


app = create_app()

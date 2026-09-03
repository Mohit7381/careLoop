from fastapi import FastAPI

from app.api.routes_analysis import router as analysis_router
from app.config import get_settings
from app.db.base import init_db


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name)

    @app.on_event("startup")
    def _startup() -> None:
        init_db()

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(analysis_router)
    return app


app = create_app()

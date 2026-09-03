from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_analysis import router as analysis_router
from app.config import get_settings
from app.db.base import init_db


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name)

    # Hackathon-permissive: the UI runs on a different origin/port locally.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    def _startup() -> None:
        init_db()

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(analysis_router)
    return app


app = create_app()

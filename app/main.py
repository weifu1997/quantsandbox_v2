from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.experiments import router as experiments_router
from app.api.reports import router as reports_router
from app.api.tasks import router as tasks_router
from app.config.settings import get_settings
from app.db.session import init_db
from app.services.task_service import mark_interrupted_running_tasks


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    try:
        mark_interrupted_running_tasks()
    except Exception:
        import logging
        logging.getLogger(__name__).exception("failed to mark interrupted tasks on startup")
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(tasks_router)
    app.include_router(experiments_router)
    app.include_router(reports_router)
    return app


app = create_app()

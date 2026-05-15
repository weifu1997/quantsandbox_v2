from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.experiments import router as experiments_router
from app.api.reports import router as reports_router
from app.api.tasks import router as tasks_router
from app.config.settings import get_settings
from app.db.session import init_db
from app.services.task_service import mark_interrupted_running_tasks


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    mark_interrupted_running_tasks()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(tasks_router)
    app.include_router(experiments_router)
    app.include_router(reports_router)
    return app


app = create_app()

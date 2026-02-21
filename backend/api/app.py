"""
Main FastAPI application wiring for the modular API.

Routers, error handlers, and services are registered here while keeping the
entrypoint in backend/main.py unchanged.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - optional local dependency
    def load_dotenv(dotenv_path: str | Path, override: bool = False, *args, **kwargs):  # type: ignore[no-redef]
        """Fallback .env loader used only when python-dotenv is unavailable."""
        path = Path(dotenv_path)
        if not path.exists():
            return False
        loaded = False
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if not key:
                continue
            if override or key not in os.environ:
                os.environ[key] = value
                loaded = True
        return loaded

from api.database import close_pool, run_startup_migrations_if_enabled, warmup_connection
from api.errors.handlers import register_error_handlers
from api.routers.accounts import router as accounts_router
from api.routers.emails import router as emails_router
from api.routers.health import router as health_router
from api.routers.mailboxes import router as mailboxes_router

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise the database connection on startup and close pool on shutdown."""
    run_startup_migrations_if_enabled()
    warmup_connection()
    yield
    close_pool()


def create_app() -> FastAPI:
    """
    Build the FastAPI application with modular routers and error handlers.
    """
    app = FastAPI(title="MailApp API", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    app.include_router(health_router)
    app.include_router(mailboxes_router)
    app.include_router(accounts_router)
    app.include_router(emails_router)
    return app


app = create_app()

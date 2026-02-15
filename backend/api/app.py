"""
Main FastAPI application wiring for the modular API.

Routers, error handlers, and services are registered here while keeping the
entrypoint in backend/main.py unchanged.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.errors.handlers import register_error_handlers
from api.routers.accounts import router as accounts_router
from api.routers.emails import router as emails_router
from api.routers.health import router as health_router
from api.routers.mailboxes import router as mailboxes_router


def create_app() -> FastAPI:
    """
    Build the FastAPI application with modular routers and error handlers.
    """
    app = FastAPI(title="MailApp API")
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


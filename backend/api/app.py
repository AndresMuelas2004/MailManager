"""
Main FastAPI application wiring for the modular API.

Routers, error handlers, and services are registered here while keeping the
entrypoint in backend/main.py unchanged.
"""

from fastapi import FastAPI

from api.errors.handlers import register_error_handlers
from api.routers.accounts import router as accounts_router
from api.routers.emails import router as emails_router
from api.routers.health import router as health_router
from api.routers.users import router as users_router


def create_app() -> FastAPI:
    """
    Build the FastAPI application with modular routers and error handlers.
    """
    app = FastAPI(title="MailApp API")
    register_error_handlers(app)
    app.include_router(health_router)
    app.include_router(users_router)
    app.include_router(accounts_router)
    app.include_router(emails_router)
    return app


app = create_app()

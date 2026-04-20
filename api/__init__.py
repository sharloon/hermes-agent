"""Hermes Agent REST API — FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def create_app() -> FastAPI:
    from api.auth import router as auth_router
    from api.users import router as users_router
    from api.files import router as files_router
    from api.conversations import router as conv_router
    from api.skills import router as skills_router

    app = FastAPI(
        title="Hermes Agent API",
        version="1.0.0",
        description="Enterprise SaaS API for Hermes Agent",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
    app.include_router(users_router, prefix="/api/v1/users", tags=["users"])
    app.include_router(files_router, prefix="/api/v1/files", tags=["files"])
    app.include_router(conv_router, prefix="/api/v1/conversations", tags=["conversations"])
    app.include_router(skills_router, prefix="/api/v1/skills", tags=["skills"])

    return app


app = create_app()

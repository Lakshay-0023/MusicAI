"""Assembling the application.

This file only wires things together: it holds no logic of its own, so a route
can be added or moved without touching anything else.
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from ..config import settings
from .routes import analysis, jobs, stems, tracks


def create_app() -> FastAPI:
    app = FastAPI(title="Woodshed", description="Take a song apart, then practise inside it.")

    app.include_router(tracks.router)
    app.include_router(analysis.router)
    app.include_router(stems.router)
    app.include_router(jobs.router)

    # Mounted last: routes are matched in order, so the API wins and anything
    # else falls through to the front end.
    if settings.web_dir.exists():
        app.mount("/", StaticFiles(directory=settings.web_dir, html=True), name="web")

    return app


app = create_app()

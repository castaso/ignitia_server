"""FastAPI application entry point for ignitia_server.

The Flutter client is hard-coded to base URL ``http://<host>:86/api/``
(lib/repo/api_service.dart), so all routers are mounted under ``/api``.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import Base, engine
from .routers import attendance, employees, leave, login, overtime, payroll


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on first run. Use a migration tool (e.g. Alembic)
    # once the schema stabilises.
    Base.metadata.create_all(bind=engine)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="ignitia_server",
        description="Backend for the i_employment Flutter app, with "
        "server-side geo-fence + face verification to prevent proxy attendance.",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/")
    def root():
        return {
            "service": "ignitia_server",
            "docs": "/docs",
            "office": {
                "latitude": settings.OFFICE_LATITUDE,
                "longitude": settings.OFFICE_LONGITUDE,
                "radius_meters": settings.OFFICE_RADIUS_METERS,
            },
        }

    # Register routers under the /api prefix (matching the client base URL).
    for router in (
        login.router,
        attendance.router,
        employees.router,
        leave.router,
        overtime.router,
        payroll.router,
    ):
        app.include_router(router, prefix="/api")

    return app


app = create_app()

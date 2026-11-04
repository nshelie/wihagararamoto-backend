import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text
from app.core.database import engine
from app.models import tables
from app.routers import auth 
from app.routers import stations
from app.routers import updates
from app.routers import admin
from app.routers import manager

# Automatically trigger the physical creation of database tables if they do not exist
tables.Base.metadata.create_all(bind=engine)


def _ensure_schema_upgrades() -> None:
    """Add columns introduced after a database was first created (no migration tool yet)."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    if "users" in existing_tables:
        user_columns = {column["name"] for column in inspector.get_columns("users")}
        with engine.begin() as connection:
            if "password_hash" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR"))
            if "station_id" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN station_id VARCHAR"))

    if "stations" in existing_tables:
        station_columns = {column["name"] for column in inspector.get_columns("stations")}
        with engine.begin() as connection:
            if "manager_id" not in station_columns:
                connection.execute(text("ALTER TABLE stations ADD COLUMN manager_id VARCHAR"))
            if "landmark" not in station_columns:
                connection.execute(text("ALTER TABLE stations ADD COLUMN landmark VARCHAR"))
            if "latitude" not in station_columns:
                connection.execute(text("ALTER TABLE stations ADD COLUMN latitude FLOAT"))
            if "longitude" not in station_columns:
                connection.execute(text("ALTER TABLE stations ADD COLUMN longitude FLOAT"))
            # BUSY was merged into VERY_BUSY; keep old databases readable.
            connection.execute(
                text("UPDATE stations SET current_queue = 'VERY_BUSY' WHERE current_queue = 'BUSY'")
            )

    if "station_requests" in existing_tables:
        request_columns = {
            column["name"] for column in inspector.get_columns("station_requests")
        }
        with engine.begin() as connection:
            if "initial_batteries" not in request_columns:
                connection.execute(
                    text("ALTER TABLE station_requests ADD COLUMN initial_batteries INTEGER DEFAULT 0")
                )
            if "landmark" not in request_columns:
                connection.execute(text("ALTER TABLE station_requests ADD COLUMN landmark VARCHAR"))
            if "latitude" not in request_columns:
                connection.execute(text("ALTER TABLE station_requests ADD COLUMN latitude FLOAT"))
            if "longitude" not in request_columns:
                connection.execute(text("ALTER TABLE station_requests ADD COLUMN longitude FLOAT"))


_ensure_schema_upgrades()


def _bootstrap_demo_data() -> None:
    """Seed a fresh hosted database when SEED_DEMO=1 (idempotent)."""
    if os.getenv("SEED_DEMO", "").lower() not in {"1", "true", "yes"}:
        return
    from app.seed_admin import seed_admin
    from app.seed_stations import seed_test_stations

    seed_admin()
    seed_test_stations()


_bootstrap_demo_data()


app = FastAPI(
    title="WihagararaMoto API",
    description="Scalable three-tier backend engine managing battery station syncing.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register your operational API routing blocks cleanly
app.include_router(auth.router)
app.include_router(stations.router)
app.include_router(updates.router)
app.include_router(admin.router)
app.include_router(manager.router)

_web_dir = Path(__file__).resolve().parents[1] / "web_app"
if _web_dir.is_dir():
    app.mount("/app", StaticFiles(directory=_web_dir, html=True), name="web")

@app.get("/")
def read_root():
    return {
        "status": "online",
        "app_name": "WihagararaMoto Backend",
        "target_market": "Rwanda"
    }
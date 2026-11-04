import os
from pathlib import Path


def _load_env_file() -> None:
    """Load key=value pairs from the backend .env file without extra dependencies."""
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file()


_database_url = os.getenv("DATABASE_URL", "sqlite:///./wihagararamoto.db")
# Hosting dashboards sometimes hand out postgres:// URLs, which SQLAlchemy rejects.
if _database_url.startswith("postgres://"):
    _database_url = "postgresql://" + _database_url[len("postgres://"):]


class Settings:
    PROJECT_NAME = "WihagararaMoto Backend API"
    PROJECT_VERSION = "1.0.0"
    DATABASE_URL = _database_url


settings = Settings()

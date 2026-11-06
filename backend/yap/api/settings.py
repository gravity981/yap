"""Runtime settings from environment variables."""

import os
from dataclasses import dataclass
from pathlib import Path


def _flag(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).lower() == "true"


def _secret(name: str) -> str | None:
    """A secret from `<name>_FILE` (a Docker Compose secret, spec 2.6) or from `<name>`."""
    path = os.environ.get(f"{name}_FILE")
    if path:
        return Path(path).read_text().strip() or None
    return os.environ.get(name) or None


@dataclass(frozen=True)
class Settings:
    database_url: str
    app_env: str = "dev"  # dev | staging | prod
    migrate_on_startup: bool = True  # NFR-09
    static_dir: str | None = None  # built frontend; served by the app in production
    secret_key: str | None = None  # encrypts stored LLM API keys (REV-15)
    # Session cookie only over HTTPS; false for plain HTTP in the LAN (spec 2.6, NFR-02)
    cookie_secure: bool = True
    # The scheduled price update (PRC-07, spec 2.5); off unless started from the environment
    price_scheduler: bool = False

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            database_url=os.environ["DATABASE_URL"],
            app_env=os.environ.get("APP_ENV", "dev"),
            migrate_on_startup=_flag("MIGRATE_ON_STARTUP", True),
            static_dir=os.environ.get("STATIC_DIR") or None,
            secret_key=_secret("APP_SECRET_KEY"),
            cookie_secure=_flag("COOKIE_SECURE", True),
            price_scheduler=_flag("PRICE_SCHEDULER", True),
        )

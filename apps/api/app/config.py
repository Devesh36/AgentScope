"""Native defaults and fail-closed container configuration; never render secrets."""

import os
from functools import lru_cache
from pathlib import Path

from alembic.script import ScriptDirectory
from sqlalchemy import URL


@lru_cache(maxsize=1)
def migration_heads():
    """Read the packaged migration graph independently of the working directory."""
    try:
        heads = frozenset(
            ScriptDirectory(str(Path(__file__).resolve().parents[1] / "alembic")).get_heads()
        )
    except Exception as exc:  # Readiness must fail closed on invalid metadata.
        raise RuntimeError("Migration metadata unavailable") from exc
    if not heads:
        raise RuntimeError("Migration metadata unavailable")
    return heads


def secret_file(variable):
    path = os.getenv(variable)
    if not path:
        raise RuntimeError(f"Required configuration missing: {variable}")
    try:
        value = Path(path).read_text().strip()
    except OSError:
        raise RuntimeError(f"Required secret file unavailable: {variable}") from None
    if not value:
        raise RuntimeError(f"Required secret file empty: {variable}")
    return value


def database_url(local):
    if os.getenv("AGENTSCOPE_CONTAINER") == "1":
        for name in ("DATABASE_HOST", "DATABASE_NAME", "DATABASE_USER"):
            if not os.getenv(name):
                raise RuntimeError(f"Required configuration missing: {name}")
        return URL.create(
            "postgresql+psycopg",
            username=os.environ["DATABASE_USER"],
            password=secret_file("DATABASE_PASSWORD_FILE"),
            host=os.environ["DATABASE_HOST"],
            port=5432,
            database=os.environ["DATABASE_NAME"],
        )
    return os.getenv("DATABASE_URL", f"sqlite:///{local / 'agentscope.db'}")

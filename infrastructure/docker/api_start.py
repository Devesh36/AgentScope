"""Migrate per start, fail clearly, then replace PID 1 with the ASGI server."""

import os
import sys

try:
    from alembic import command
    from alembic.config import Config
    from app.config import secret_file
    from app.db import engine

    secret_file("AGENTSCOPE_ADMIN_TOKEN_FILE")
    command.upgrade(Config("alembic.ini"), "head")
    engine.dispose()
except Exception as exc:  # noqa: BLE001 — redact startup failures from third-party libraries
    # Third-party errors may include a DSN or SQL parameters; print only their class.
    detail = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
    print(
        f"AgentScope startup failed: database/migration/configuration unavailable ({detail})",
        file=sys.stderr,
    )
    sys.exit(1)

os.execvp("python", ["python", "/app/infrastructure/docker/api_server.py"])

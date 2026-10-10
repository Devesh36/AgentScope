"""Loaded only in applications explicitly launched by agentscope watch/run."""

try:
    from agentscope_runtime import bootstrap

    bootstrap()
except Exception:  # noqa: BLE001 - optional monitoring must never block startup
    # Monitoring must never prevent an application from starting.
    import sys

    print(
        "AgentScope: Python monitoring could not initialize; application startup continues.",
        file=sys.stderr,
    )

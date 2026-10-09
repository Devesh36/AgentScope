"""Drain SSE and the durable worker as soon as SIGTERM arrives."""

import uvicorn
from app.main import app


class LocalServer(uvicorn.Server):
    def handle_exit(self, sig, frame):
        app.state.draining = True
        if hasattr(app.state, "stop"):
            app.state.stop.set()
        super().handle_exit(sig, frame)


if __name__ == "__main__":
    LocalServer(
        uvicorn.Config(
            app,
            host="0.0.0.0",
            port=8000,
            workers=1,
            timeout_graceful_shutdown=20,
            access_log=False,
        )
    ).run()

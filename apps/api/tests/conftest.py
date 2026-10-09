import os
import tempfile
from pathlib import Path

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", f"sqlite:///{Path(tempfile.mkdtemp()) / 'test.db'}"
)
os.environ["AGENTSCOPE_ADMIN_TOKEN"] = "test-dashboard-token-not-a-real-credential"

import pytest
from app.db import Base, engine
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app, raise_server_exceptions=True) as value:
        yield value


@pytest.fixture
def headers(client):
    auth = {"Authorization": "Bearer test-dashboard-token-not-a-real-credential"}
    project = client.post(
        "/api/v1/projects", headers=auth, json={"name": "Test project"}
    ).json()
    return {**auth, "X-Project-ID": project["id"]}

import pytest
from fastapi.testclient import TestClient

from memory_agent.config import Settings
from memory_agent.main import create_app

ADMIN_KEY = "mak_test_admin_key"
ADMIN = {"Authorization": f"Bearer {ADMIN_KEY}"}


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(db_path=str(tmp_path / "memory.db"), admin_key=ADMIN_KEY)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def make_principal(client):
    """Create a principal with the given policies and return its auth headers."""

    def make(policies: list[dict], tags: dict | None = None) -> dict:
        body = {"name": "test", "policies": policies, "tags": tags or {}}
        response = client.post("/principals", json=body, headers=ADMIN)
        assert response.status_code == 201, response.text
        return {"Authorization": f"Bearer {response.json()['apiKey']}"}

    return make


def allow(action: str | list[str], resource: str = "*") -> dict:
    return {"Statement": [{"Effect": "Allow", "Action": action, "Resource": resource}]}

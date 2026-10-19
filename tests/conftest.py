import pytest
from fastapi.testclient import TestClient

from memory_agent.config import Settings
from memory_agent.main import create_app


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(db_path=str(tmp_path / "memory.db"))


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client

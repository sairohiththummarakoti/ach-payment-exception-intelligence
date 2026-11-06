from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ach_intelligence.api import create_app
from ach_intelligence.config import Settings


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}"))
    with TestClient(app) as test_client:
        yield test_client

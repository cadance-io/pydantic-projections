from __future__ import annotations

import pytest
from models import User


@pytest.fixture
def user() -> User:
    return User(id=1, name="Alice", email="alice@example.com", password_hash="secret")

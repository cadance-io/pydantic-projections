from __future__ import annotations

import pytest
from models import Account, User


@pytest.fixture
def user() -> User:
    return User(id=1, name="Alice", email="alice@example.com", password_hash="secret")


@pytest.fixture
def account() -> Account:
    return Account(
        id=1,
        email="alice@example.com",
        legacyID=7,
        password_hash="secret",
    )

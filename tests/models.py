from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, computed_field


class User(BaseModel):
    id: int
    name: str
    email: str
    password_hash: str

    @computed_field
    @property
    def display_name(self) -> str:
        return f"User: {self.name}"


class UserSummary(Protocol):
    id: int
    name: str


class UserMaybeName(Protocol):
    id: int
    name: str | None


class UserDisplay(Protocol):
    display_name: str


class Address(BaseModel):
    street: str
    zip_code: str
    country: str


class AddressSummary(Protocol):
    street: str
    zip_code: str


class UserWithAddress(BaseModel):
    id: int
    name: str
    address: Address
    past_addresses: list[Address] = []
    nicknames: dict[str, Address] = {}
    shipping: Address | None = None


class UserWithAddressSummary(Protocol):
    id: int
    name: str
    address: AddressSummary


class UserWithAddressList(Protocol):
    id: int
    past_addresses: list[AddressSummary]


class UserWithAddressDict(Protocol):
    id: int
    nicknames: dict[str, AddressSummary]


class UserWithOptionalAddress(Protocol):
    id: int
    shipping: AddressSummary | None

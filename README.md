# pydantic-projections

[![PyPI](https://img.shields.io/pypi/v/pydantic-projections.svg)](https://pypi.org/project/pydantic-projections/)
[![CI](https://github.com/cadance-io/pydantic-projections/actions/workflows/ci.yml/badge.svg)](https://github.com/cadance-io/pydantic-projections/actions/workflows/ci.yml)
[![Python](https://img.shields.io/pypi/pyversions/pydantic-projections.svg)](https://pypi.org/project/pydantic-projections/)

Elegant projection of Pydantic `BaseModel`s through Python `Protocol`s — serialise and deserialise only the fields a Protocol declares, nothing more.

## Install

```bash
uv add pydantic-projections
# or
pip install pydantic-projections
```

## Why

You have a fat `BaseModel` for internal use, and you want to expose only a subset of its fields over an API, to a logging system, or to a downstream consumer. Pydantic already lets you do this with `model_dump(include=...)`, but that's stringly-typed and type-unsafe. A `Protocol` describes the shape you want; `pydantic-projections` turns that Protocol into a real BaseModel at runtime, cached per `(protocol, frozen, config)` triple.

## Usage

```python
from typing import Protocol

from pydantic import BaseModel
from pydantic_projections import project, projection


class User(BaseModel):
    id: int
    name: str
    email: str
    password_hash: str


class UserSummary(Protocol):
    id: int
    name: str


user = User(id=1, name="Alice", email="a@b.c", password_hash="secret")

# One-shot: project an instance, get a BaseModel typed as UserSummary
summary = project(user, UserSummary)
summary.model_dump_json()
# -> '{"id":1,"name":"Alice"}'

# Get the reusable class (cached): useful for response_model, schema export, etc.
SummaryModel = projection(UserSummary)
SummaryModel.model_validate_json('{"id":1,"name":"Alice","extra":"ignored"}')
# -> extra fields are ignored
SummaryModel.model_json_schema()
# -> standard pydantic JSON schema
```

### Nested protocols and containers

Protocols can reference other Protocols. The projection is built recursively, so `list[P]`, `dict[str, P]`, `tuple[P, ...]`, `P | None`, `Union[P, ...]`, and plain `P` all work:

```python
class AddressSummary(Protocol):
    street: str
    zip_code: str


class UserWithAddresses(Protocol):
    id: int
    name: str
    address: AddressSummary
    past_addresses: list[AddressSummary]
    shipping: AddressSummary | None
```

### `@property`-style Protocols

Protocols that declare fields as properties are also supported — the property's return type is used:

```python
class UserDisplay(Protocol):
    @property
    def display_name(self) -> str: ...


project(user, UserDisplay).display_name
```

### Computed / derived fields on the source

`@computed_field` / `@property` declarations on the source model are readable through the projection, because validation runs with `from_attributes=True`:

```python
class User(BaseModel):
    id: int
    name: str

    @computed_field
    @property
    def display_name(self) -> str:
        return f"User: {self.name}"


class UserDisplay(Protocol):
    display_name: str


project(user, UserDisplay).display_name  # -> "User: Alice"
```

### Typing at the call site

`project(instance, Proto)` is typed to return `Proto`, so `summary.name` resolves to `str` in mypy/pyright without a cast. At runtime the object is a `BaseModel` subclass that structurally satisfies the Protocol.

### FastAPI `response_model`

`projection(Proto)` returns a real BaseModel class, so it drops into FastAPI's `response_model` unchanged — the endpoint's output is pruned to the Protocol's fields and the OpenAPI schema matches:

```python
from fastapi import FastAPI
from pydantic_projections import projection

app = FastAPI()


@app.get("/users/{id}", response_model=projection(UserSummary))
def get_user(id: int) -> User:
    return db.get_user(id)  # returns the fat User; caller sees only UserSummary's fields
```

### Config pass-through and `frozen`

Projections are **immutable by default** (`frozen=True`): a projection is a derived view of its source, so attempting `instance.x = ...` raises `ValidationError`. Opt back into mutation with `frozen=False` if you need it. Merge additional `ConfigDict` options (e.g. alias generator for camelCase output) via `config=`:

```python
from pydantic import ConfigDict
from pydantic.alias_generators import to_camel

CamelSummary = projection(
    UserSummary,
    config=ConfigDict(alias_generator=to_camel, populate_by_name=True),
)

MutableSummary = projection(UserSummary, frozen=False)
```

`frozen` and `config` propagate into every Protocol reachable from the outer one, so an alias generator applied at the top level also camelCases nested projections. `extra="ignore"` and `from_attributes=True` are hard invariants — user-supplied `ConfigDict` cannot override them.

Classes are cached per `(protocol, config, frozen)` triple; config values must be hashable.

### Error handling

`project()` wraps pydantic's `ValidationError` in a `ProjectionError` that carries the protocol, source type, and original validation error:

```python
from pydantic_projections import ProjectionError

try:
    project(partial_user, UserSummary)
except ProjectionError as e:
    e.protocol           # the Protocol class
    e.source_type        # type(instance)
    e.validation_error   # the underlying pydantic ValidationError
```

### JSON shortcut

```python
from pydantic_projections import project_json

project_json(user, UserSummary)                 # str
project_json(user, UserSummary, indent=2)       # forwards **kwargs to model_dump_json
```

### Cache management

```python
from pydantic_projections import cache_clear
cache_clear()  # useful in test fixtures or hot-reload workflows
```

## Semantics

- **Extras are ignored** on deserialisation (`extra="ignore"`). This is a hard invariant — passing `extra="forbid"` via `config=` does not override it.
- **`from_attributes=True`** — accepts dicts, JSON, or arbitrary objects that expose the Protocol's members. Also a hard invariant.
- **Projections are immutable by default** (`frozen=True`). Pass `frozen=False` for a mutable variant.
- **`frozen` and `config=` propagate to nested projections** — an alias generator or `frozen` flag applied at the top level also applies to every Protocol reachable through containers and unions.
- **Optional widening** is allowed: source `name: str` is accepted by a Protocol declaring `name: str | None`.
- **Narrowing** is not: if the source value is `None` for a Protocol field typed `str`, validation raises.
- **Classes are cached** per `(protocol, config, frozen)` via `functools.cache`.

## Limitations

- Cyclic Protocols (a Protocol that references itself transitively) are not supported and will recurse.
- Generic Protocols (`Protocol[T]`) with unresolved `TypeVar`s are not supported.
- Config values passed via `config=` must be hashable for caching.

## Development

```bash
uv sync
uv run pytest
uv run python scripts/validate_tests.py
uv run ruff check src/ tests/ scripts/
uv run mypy src/
uv run coverage run -m pytest && uv run coverage report
```

Tests use pytest-describe (`describe_`/`when_`/`with_`/`it_`). See `CLAUDE.md` for conventions.

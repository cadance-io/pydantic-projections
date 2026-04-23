# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `ProjectedResponse` — FastAPI response class that serializes a source instance through a Protocol straight to JSON bytes, bypassing FastAPI's `serialize_response` + `jsonable_encoder` + `json.dumps` chain. Benchmarked ~2–4× faster than the `response_model=projection(...)` baseline on raw ser/deser work (varies by FastAPI version and response shape). Raises `ProjectionError` at construction time if the source does not satisfy the Protocol. Import from `pydantic_projections` (lazy); requires the `fastapi` optional extra.
- `project_json_bytes(instance, protocol, **kwargs) -> bytes` — emits JSON bytes via the projection class's Rust-backed serializer, skipping the `str` intermediate that `model_dump_json().encode()` goes through.
- Optional `fastapi` install extra: `pip install pydantic-projections[fastapi]`.
- `benches/` suite driven by `pytest-benchmark` for measuring the projection and render paths.

### Changed
- `project()` and `project_json()` now invoke `__pydantic_validator__.validate_python` directly instead of going through `BaseModel.model_validate`. Observable behaviour is identical; per-call cost drops by roughly 1.3–1.5× depending on shape.

## [0.3.0] - 2026-04-22

### Changed
- **BREAKING**: `projection(...)` now defaults to `frozen=True`. A projection is a derived view of its source, so mutation is almost always a bug; projections are now immutable by default and are hashable (usable as `dict` keys / in `set`s). Pass `frozen=False` to restore the previous behaviour.

### Fixed
- `frozen` and `config=` now propagate into nested Protocol projections. Previously only the top-level projection inherited these settings, so an alias generator applied at the outer level silently skipped nested models and a frozen outer projection still permitted mutation of its inner projections.
- `ConfigDict(extra=...)` and `ConfigDict(from_attributes=...)` passed via `config=` no longer override the library's `extra="ignore"` / `from_attributes=True` invariants.

### Changed
- Nested projections are now cached under the outer `(frozen, config)` tuple, so each distinct outer configuration produces its own inner projection class. Previously all nested classes for a given Protocol were a single shared instance.

## [0.2.0] - 2026-04-22

### Added
- Nested Protocol projection: fields typed as other Protocols are recursively projected.
- Container support: `list[P]`, `dict[K, P]`, `tuple[P, ...]`, `P | None`, `Union[...]` are traversed and their inner Protocols substituted.
- Call-site typing: `project(instance, Proto)` is declared to return `P`, so mypy/pyright resolve attribute access without casts.
- `@property`-style Protocol declarations: `@property def x(self) -> T: ...` is supported alongside annotated attributes.
- Config pass-through via `projection(Proto, config=ConfigDict(...), frozen=bool)`.
- `ProjectionError` wraps `pydantic.ValidationError` with `protocol`, `source_type`, and `validation_error` attributes.
- `project_json(instance, Proto, **kwargs)` shortcut.
- `cache_clear()` for test fixtures and hot-reload workflows.
- MIT LICENSE and GitHub Actions CI workflow (Python 3.11 / 3.12 / 3.13).

### Changed
- Cache key is now `(protocol, frozen, sorted-config-items)`; non-hashable config values raise `TypeError`.

## [0.1.0] - 2026-04-22

### Added
- Initial release.
- `project(instance, Protocol)` and `projection(Protocol)` APIs.
- Extras ignored on deserialisation; `from_attributes=True` for dict / JSON / object inputs.
- Class caching per Protocol via `functools.cache`.
- pytest-describe test suite with AST-based structure validator.

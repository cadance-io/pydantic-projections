# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

# pydantic-projections

Elegant projection of Pydantic BaseModels through Python Protocols.

## Commands

- **Tests:** `uv run pytest`
- **Coverage:** `uv run coverage run -m pytest && uv run coverage report` (threshold 92%)
- **Lint:** `uv run ruff check src/ tests/`
- **Format:** `uv run ruff format src/ tests/`
- **Type check:** `uv run mypy src/`
- **Validate test shape:** `uv run python scripts/validate_tests.py`
- **CI locally:** the steps above match `.github/workflows/ci.yml` across Python 3.11–3.13

## Structure

- `src/pydantic_projections/` — library source
- `tests/` — BDD-style with pytest-describe (`describe_`/`when_`/`it_`)
- `tests/models.py` — shared `BaseModel` / `Protocol` fixtures used across tests
- `scripts/validate_tests.py` — enforces describe/when/it conventions
- `scripts/release.py` — release automation (see below)
- `.claude/hooks/validate_tests.py` — PostToolUse hook shim that runs the validator per-file

## Release

Use `uv run scripts/release.py {major|minor|patch|X.Y.Z}` — do not hand-edit version strings. The script bumps `pyproject.toml`, stamps `[Unreleased]` in `CHANGELOG.md` with today's date (and updates the footer compare links), runs `uv lock`, commits as `release: vX.Y.Z`, and tags. Preflight requires a clean working tree on `main` or any `release/*` branch, plus a non-empty `[Unreleased]` section. Add `--dry-run` to preview. After it runs, the final message prints the exact `git push origin <branch> vX.Y.Z` command, which triggers the publish workflow.

GitHub Releases are intentionally not created — PyPI + `CHANGELOG.md` are the canonical artifacts.

## Conventions

- Python 3.11+, line length 88
- Use `uv` to run all tooling (not bare `python` or `pytest`)
- Ruff for linting and formatting (config in `pyproject.toml`)
- mypy strict mode
- Tests: `describe_` groups by API surface, `when_` mirrors code branches, nested `with_`/`without_`/`for_` refine conditions, `it_` names the assertion. Never embed `_when_`/`_with_`/`_without_` in names — use a nested block instead. Test each behaviour once at the API boundary where it is consumed. Shared types in `tests/models.py`; shared fixtures in `tests/conftest.py`.

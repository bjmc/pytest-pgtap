# Changelog

## 0.3.0 (2026-05-29)

### Added

- **`pgtap_connection` fixture** — a new session-scoped fixture that controls how pytest-pgtap connects to Postgres. Override it in your `conftest.py` to supply a connection from any source, such as a [testcontainers](https://testcontainers-python.readthedocs.io/) session fixture, instead of relying on `--pgtap-uri` or libpq environment variables. See the README for usage.

## 0.2.0

Initial PyPI release.

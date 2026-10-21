# Changelog

## Unreleased

### Added

- **pytest markers on SQL file tests.** `-- pytest.mark.NAME` and `-- pytest.mark.NAME(...)` comments before the first line of SQL apply markers to that file's test, so `-m`, `skip` and `xfail` work for SQL files. See the README.

### Fixed

- **`@pytest.mark.pgtap` tests can take fixture arguments.** Previously a marked test that requested a fixture failed with `pgTAP setup failed: ... missing 1 required positional argument`, after the fixture had already run.

## 0.3.0 (2026-05-29)

### Added

- **`pgtap_connection` fixture** — a new session-scoped fixture that controls how pytest-pgtap connects to Postgres. Override it in your `conftest.py` to supply a connection from any source, such as a [testcontainers](https://testcontainers-python.readthedocs.io/) session fixture, instead of relying on `--pgtap-uri` or libpq environment variables. See the README for usage.

## 0.2.0

Initial PyPI release.

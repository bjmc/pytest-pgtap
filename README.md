# pytest-pgtap

pytest-pgtap is a pytest plugin for running [pgTAP](https://pgtap.org) tests against PostgreSQL.

It supports three different testing modalities.

It can be used as a replacement for [pg_prove](https://pgtap.org/pg_prove.html)...

1. To execute [SQL Test Scripts](https://pgtap.org/pg_prove.html#Test-Scripts) directly (`test_*.sql` files collected by pytest)
2. To [run xUnit test functions](https://pgtap.org/pg_prove.html#xUnit-Test-Functions) already defined in your database. (i.e `runtests()`)

   ...or...

3. As a pytest marker (`@pytest.mark.pgtap`) on pytest test cases to allow defining pgTAP tests in Python test files.

## Requirements

- Python 3.10+
- pytest
- PostgreSQL
- pgTAP extension installed in the target database

pytest-pgtap does not automatically install pgTAP. Install it in your Postgres instance first.

## Installation

Install from source:

```bash
pip install -e .
```

Or directly from GitHub:

```bash
pip install -U git+https://github.com/lmergner/pytest-pgtap.git
```

## Usage

### Connection

Set a connection URI explicitly:

```bash
pytest --pgtap-uri postgresql://user:pass@host:5432/dbname
```

Or rely on standard libpq environment variables (`PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`).

### Mode 1: SQL file tests

Any file named `test*.sql` is collected as a pytest item.

Example `tests/test_schema.sql`:

```sql
BEGIN;
SELECT plan(2);
SELECT has_table('public', 'users', 'users table exists');
SELECT has_column('public', 'users', 'email', 'users.email exists');
SELECT * FROM finish();
ROLLBACK;
```

Run:

```bash
pytest --pgtap-uri postgresql://user:pass@host:5432/dbname
```

### Mode 2: xUnit `runtests()` mode

Run pgTAP xUnit functions from a schema using pgTAP `runtests()`:

```bash
pytest --pgtap-uri postgresql://user:pass@host:5432/dbname --pgtap-schema mytests
```

Optional regex function filter:

```bash
pytest --pgtap-uri postgresql://user:pass@host:5432/dbname --pgtap-schema mytests --pgtap-match '^test_'
```

### Mode 3: Inline Python marker mode

Use `@pytest.mark.pgtap` on a Python test function that returns SQL assertions:

```python
import pytest


@pytest.mark.pgtap
def test_contacts_table():
    return [
        "SELECT has_table('public', 'contacts', 'contacts table exists');",
        "SELECT has_column('public', 'contacts', 'name', 'contacts.name exists');",
    ]
```

Returning a single SQL string is also supported.

## CLI options

- `--pgtap-uri`: Postgres connection URI (defaults to `DATABASE_URL` if set)
- `--pgtap-schema`: Enable xUnit mode by running `runtests(<schema>)`
- `--pgtap-match`: Regex filter used with `--pgtap-schema`

## Development

This project suggests [Hatch](https://hatch.pypa.io/) for automating development tasks:

```bash
hatch run dev:format
hatch run dev:lint
hatch run dev:test
```

### Using Podman instead of Docker

The test suite uses [testcontainers](https://testcontainers-python.readthedocs.io/) to spin up Postgres.
[If you use Podman](https://podman-desktop.io/tutorial/testcontainers-with-podman), enable the compatibility socket and set two environment variables:

```bash
systemctl --user enable --now podman.socket
export DOCKER_HOST=unix://$XDG_RUNTIME_DIR/podman/podman.sock
export TESTCONTAINERS_RYUK_DISABLED=true
```

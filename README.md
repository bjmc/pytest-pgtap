# pytest-pgtap

**What is pytest-pgtap?**

pytest-pgtap is a [pytest](https://docs.pytest.org/) plugin for running [pgTAP](https://pgtap.org) tests against [PostgreSQL](https://www.postgresql.org/). pgTAP is a mature and sadly underappreciated Postgres extension that enables [running unit tests for database constructs in the database itself.](https://www.capitalone.com/tech/software-engineering/automated-postgres-unit-testing/) You can use SQL to test your SQL.

You should read the [documentation for pgTAP](http://pgtap.org/documentation.html), which describes the functions and strategies for testing Postgres schemas, views, triggers, queries, etc.

**Why?**

I wanted a to run tests against my [Alembic](https://alembic.sqlalchemy.org/) revisions and pgTAP is a great tool, but I have no idea how to install a [CPAN](https://www.cpan.org/) package. Anyway, if you are testing a [Flask](https://flask.palletsprojects.com/) or [Django](https://www.djangoproject.com/) app (or whatever), it's easier to have a single test runner that fits easily into a Python toolchain. Hence a plugin for pytest.

**How?**

pytest-pgtap provides three entry points into the pgTAP test framework. It is designed to be a replacement for [pg_prove](https://pgtap.org/pg_prove.html), pgTAP's native test runner (which is written in Perl) that can...

1. Execute [SQL Test Scripts](https://pgtap.org/pg_prove.html#Test-Scripts) directly (`test_*.sql` files collected by pytest)
2. Or [run xUnit test functions](https://pgtap.org/pg_prove.html#xUnit-Test-Functions) already defined in your database. (i.e `runtests()`)

   ...it can also be used...

3. As a pytest marker (`@pytest.mark.pgtap`) on pytest test cases to allow defining pgTAP tests in Python test files alongside application tests.

## Requirements

- Python 3.10+
- pytest
- PostgreSQL
- pgTAP extension installed in the target database

pytest-pgtap does not automatically install pgTAP. [Install it in your Postgres instance first.](https://pgtap.org/documentation.html#addingpgtaptoadatabase)

## Installation

Install from source:

```bash
pip install -e .
```

Or directly from GitHub:

```bash
pip install -U git+https://github.com/lmergner/pytest-pgtap.git
```

**Note:** To report PgTAP results, this plugin relies on the [Pytest subtests](https://docs.pytest.org/en/stable/how-to/subtests.html) feature introduced in Pytest v9.
If you are using Pytest 8, you'll need to install the optional `subtests` dependency, that adds [pytest-subtests](https://pypi.org/project/pytest-subtests/) as an extra plugin for backwards-compatibility.

```bash
pip install -U "git+https://github.com/lmergner/pytest-pgtap.git#egg=pytest-pgtap[subtests]"
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

This project suggests [Hatch](https://hatch.pypa.io/) for managing your environment and automating development tasks:

```bash
hatch run dev:format
hatch run dev:lint
hatch run dev:test
hatch run docs:build
```

The test suite uses [testcontainers](https://testcontainers-python.readthedocs.io/) to spin up Postgres. You'll need [Docker](https://www.docker.com) or some other [OCI runtime](https://github.com/opencontainers/runtime-spec).

### Using Podman instead of Docker

[If you use Podman](https://podman-desktop.io/tutorial/testcontainers-with-podman), enable the compatibility socket and set two environment variables:

```bash
systemctl --user enable --now podman.socket
export DOCKER_HOST=unix://$XDG_RUNTIME_DIR/podman/podman.sock
export TESTCONTAINERS_RYUK_DISABLED=true
```

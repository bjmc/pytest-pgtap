"""Fixtures providing the database connection and pgTAP runner."""

import logging
from typing import Any

import psycopg
import pytest
from psycopg import OperationalError, ProgrammingError
from pytest import UsageError

from ..pgtap import Runner

logger = logging.getLogger(__name__)


@pytest.fixture(scope='session')
def pgtap_connection(request: pytest.FixtureRequest):
    """Provide the psycopg connection used by pytest-pgtap.

    Override this fixture to supply a connection from an external source
    (e.g. a testcontainers session fixture) instead of the default CLI /
    environment-variable based connection. The plugin will not interfere with
    the lifecycle of a connection it did not create.
    """
    config = request.config
    if db_uri := config.getoption('pgtap_uri'):
        try:
            conn = psycopg.connect(db_uri)
        except (OperationalError, ProgrammingError) as err:
            raise UsageError(f'Unable to connect to Postgres: {err}') from err
    else:
        # Connect relying on env vars:
        # https://www.postgresql.org/docs/current/libpq-envars.html
        try:
            conn = psycopg.connect()
        except OperationalError as err:
            logger.warning('pytest-pgtap: Unable to connect to Postgres: %s', err)
            yield None
            return
    with conn:
        yield conn


@pytest.fixture(scope='session')
def _pgtap_runner(
    pgtap_connection: psycopg.Connection[Any] | None,
) -> Runner | None:
    return Runner(pgtap_connection) if pgtap_connection is not None else None

from pathlib import Path
from psycopg import connect
from psycopg.abc import Query
import pytest
from typing import cast

from .conftest import assert_tap_outcomes

HERE = Path(__file__).parent


@pytest.fixture
def db_setup(database):
    with open(HERE / 'runtests_fixture.sql') as fh:
        with connect(database.get_connection_url()) as conn:
            conn.execute(cast(Query, fh.read()))
    return database


def test_run_sql_test(pytester, db_setup):
    r = pytester.runpytest(
        '-v', '--pgtap-uri', db_setup.get_connection_url(), '--pgtap-schema', 'mytests'
    )
    assert_tap_outcomes(r, passed=1)

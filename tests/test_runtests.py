from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest
from psycopg import connect

from .conftest import assert_tap_outcomes

if TYPE_CHECKING:
    from psycopg.abc import Query

FIXTURES_DIR = Path(__file__).parent / 'sql'


@pytest.fixture
def db_setup(database):
    with (
        (FIXTURES_DIR / 'runtests_fixture.sql').open() as fh,
        connect(database.get_connection_url()) as conn,
    ):
        conn.execute(cast('Query', fh.read()))
    return database


def test_run_sql_test(pytester, db_setup):
    r = pytester.runpytest(
        '-v', '--pgtap-uri', db_setup.get_connection_url(), '--pgtap-schema', 'mytests'
    )
    assert_tap_outcomes(r, passed=1)


def test_runtests_failure(pytester, db_setup):
    r = pytester.runpytest(
        '-v',
        '--pgtap-uri',
        db_setup.get_connection_url(),
        '--pgtap-schema',
        'testsuite_with_failure',
    )
    assert_tap_outcomes(r, failed=2)
    r.stdout.fnmatch_lines(['*testsuite_with_failure.test_count_two_dogs*'])


def test_runtests_match_filter(pytester, db_setup):
    r = pytester.runpytest(
        '-v',
        '--pgtap-uri',
        db_setup.get_connection_url(),
        '--pgtap-schema',
        'mixedtests',
        '--pgtap-match',
        '^test_two_cats$',
    )
    r.assert_outcomes(passed=1)
    assert 'mixedtests should fail' not in '\n'.join(r.stdout.lines)

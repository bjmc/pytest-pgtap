from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest
from psycopg import connect

from .conftest import assert_tap_outcomes
from .test_sql_markers import MODULE_FIXTURE_CONFTEST

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


def test_module_scoped_fixture_runs_for_runtests(pytester, db_setup):
    pytester.makeconftest(MODULE_FIXTURE_CONFTEST)
    r = pytester.runpytest(
        '-s', '--pgtap-uri', db_setup.get_connection_url(), '--pgtap-schema', 'mytests'
    )
    r.assert_outcomes(passed=1)
    r.stdout.fnmatch_lines(['*MODULE FIXTURE RAN*'])


def test_conftest_connection_override_can_install_runtests_suite(pytester, database):
    """A root conftest.py pgtap_connection override, and its fixtures, apply to runtests()."""
    pytester.makeconftest(
        f"""
        import psycopg
        import pytest

        URL = {database.get_connection_url()!r}

        @pytest.fixture(scope='session')
        def install_suite():
            with psycopg.connect(URL, autocommit=True) as conn:
                conn.execute(
                    "CREATE SCHEMA IF NOT EXISTS conftest_suite;"
                    "CREATE OR REPLACE FUNCTION conftest_suite.test_installed()"
                    " RETURNS SETOF text LANGUAGE sql AS $$ SELECT pass('installed') $$;"
                )

        @pytest.fixture(scope='session')
        def pgtap_connection(install_suite):
            with psycopg.connect(URL) as conn:
                yield conn
        """
    )
    r = pytester.runpytest('-v', '--pgtap-schema', 'conftest_suite')
    assert_tap_outcomes(r, passed=1)

# -*- coding: utf-8 -*-
# Copyright (c) 2018 Luke Mergner and contributors

from .conftest import assert_tap_outcomes

pytest_plugins = ['pytester']

SQL_TESTS = """
BEGIN;
    SELECT plan(2);
    SELECT fail('simple fail');
    SELECT pass('simple pass');
    SELECT * FROM finish();
ROLLBACK;
"""

PYTHON_TESTS = """
def test_pgtap_fixture(pgtap):
    assert pgtap(
        "select has_column('whatever.contacts', 'name', 'contacts should have a name');")
"""


def test_run_sql_test(pytester, database):
    pytester.makefile('.sql', test_sql_file=SQL_TESTS)
    r = pytester.runpytest('-v', '--pgtap-uri', database.get_connection_url())
    assert_tap_outcomes(r, failed=2, passed=1)


def test_wrong_plan(pytester, database):
    pytester.makefile('.sql', test_sql_file=SQL_TESTS.replace('plan(2)', 'plan(3)'))
    r = pytester.runpytest_inprocess('-v', '--pgtap-uri', database.get_connection_url())
    assert_tap_outcomes(r, failed=2, passed=1)
    r.stdout.fnmatch_lines(('*Bad plan. You planned 3 tests but actually ran 2.*',))


def test_env_var_connection(pytester, database, monkeypatch):
    envvars = {
        'PGHOST': database.get_container_host_ip(),
        'PGPORT': str(database.get_exposed_port(database.port)),
        'PGDATABASE': database.dbname,
        'PGUSER': database.username,
        'PGPASSWORD': database.password,
    }
    pytester.makefile('.sql', test_sql_file=SQL_TESTS)
    for key, val in envvars.items():
        monkeypatch.setenv(key, val)
    r = pytester.runpytest()
    assert_tap_outcomes(r, failed=2, passed=1)


def test_no_postgres_connection(pytester, monkeypatch):
    """If we collect test_*.sql files, but we don't have a database
    connection, those tests are skipped."""
    # Just in case we're in an environment configured with valid creds:
    monkeypatch.setenv('PGPASSWORD', 'badpassword')
    pytester.makefile('.sql', test_sql_file=SQL_TESTS)
    result = pytester.runpytest()
    result.assert_outcomes(skipped=1)


def test_bad_postgres_connection(pytester):
    """If the user passes pgtap-uri, they explicitly wanted to run
    pgtap tests, so we fail."""

    result = pytester.runpytest('-v', '--pgtap-uri', 'postgresql://bogus:user@localhost/invalid')
    assert result.ret != 0
    result.stderr.fnmatch_lines(['*Unable to connect to Postgres: connection failed*'])

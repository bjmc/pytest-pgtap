from textwrap import dedent

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

CMP_OK_FAIL_SQL = """
BEGIN;
    SELECT plan(1);
    SELECT cmp_ok(5, '<', 3, 'five should be less than three');
    SELECT * FROM finish();
ROLLBACK;
"""

ORPHANED_DIAGNOSTIC_SQL = """
BEGIN;
    SELECT diag('setup note before any test point');
    SELECT plan(2);
    SELECT pass('first test');
    SELECT fail('second test');
    SELECT * FROM finish();
ROLLBACK;
"""

# fail()/pass() always keep pgTAP's own finish() summary honest, so a real
# mismatch can only come from a diag() call crafted to look like one -- this
# fabricates that disagreement to exercise the safety net.
FAKE_SUMMARY_MISMATCH_SQL = """
BEGIN;
    SELECT plan(1);
    SELECT pass('actually passes');
    SELECT diag('Looks like you failed 5 tests of 1');
    SELECT * FROM finish();
ROLLBACK;
"""


def test_pgtap_connection_fixture_override(pytester, database):
    """A conftest that overrides pgtap_connection supplies the connection to our plugin."""
    pytester.makeconftest(
        dedent(f"""
        import psycopg
        import pytest

        @pytest.fixture(scope='session')
        def pgtap_connection():
            with psycopg.connect({database.get_connection_url()!r}) as conn:
                yield conn
        """)
    )
    pytester.makefile('.sql', test_sql_file=SQL_TESTS)
    r = pytester.runpytest('-v')
    assert_tap_outcomes(r, failed=2, passed=1)


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

    pytester.makefile('.sql', test_sql_file=SQL_TESTS)
    result = pytester.runpytest('-v', '--pgtap-uri', 'postgresql://bogus:user@localhost/invalid')
    assert result.ret != 0
    output = '\n'.join([*result.stdout.lines, *result.stderr.lines])
    assert 'Unable to connect to Postgres: connection failed' in output


def test_cmp_ok_diagnostic_reported_on_failure(pytester, database):
    """cmp_ok()'s actual/expected diagnostic lines surface in the failure message.

    pgTAP's cmp_ok() emits a `# ...` diagnostic block showing the actual and
    expected values on failure. TAP diagnostics aren't lexically bound to a
    test point by the spec, so tap-py's parser returns them as standalone
    Diagnostic lines rather than attaching them to the Result -- without the
    plugin applying its own trailing-association convention, it drops them
    silently.
    """
    pytester.makefile('.sql', test_sql_file=CMP_OK_FAIL_SQL)
    r = pytester.runpytest('-v', '--pgtap-uri', database.get_connection_url())
    assert_tap_outcomes(r, failed=2)
    r.stdout.fnmatch_lines(('*5*', '*<*', '*3*'))


def test_orphaned_diagnostic_added_to_report_section(pytester, database):
    """A diag() call with no preceding test point is surfaced, not dropped.

    TAP diagnostics before the first test point (or before plan()) have no
    Result to attach to. Rather than discard them, they're added as a report
    section on the item -- the same mechanism pytest uses internally for
    captured stdout/stderr -- so they show up in the failure output.
    """
    pytester.makefile('.sql', test_sql_file=ORPHANED_DIAGNOSTIC_SQL)
    r = pytester.runpytest('-v', '--pgtap-uri', database.get_connection_url())
    assert_tap_outcomes(r, failed=2, passed=1)
    r.stdout.fnmatch_lines(('*pgTAP diagnostics*', '*setup note before any test point*'))


def test_summary_mismatch_detected(pytester, database):
    """A pgTAP run summary that disagrees with our own count fails loudly.

    finish() reports its own failure count independently of how pytest-pgtap
    parsed the individual results. If they disagree, that's a bug in our TAP
    parsing -- most dangerously, under-counting failures and reporting green
    when pgTAP itself says something failed -- so it should fail the run
    rather than pass silently.
    """
    pytester.makefile('.sql', test_sql_file=FAKE_SUMMARY_MISMATCH_SQL)
    r = pytester.runpytest('-v', '--pgtap-uri', database.get_connection_url())
    assert r.ret != 0
    r.stdout.fnmatch_lines(('*points to*a bug in pytest-pgtap*',))


def test_no_pgtap_usage_no_connection_warning(pytester, monkeypatch):
    monkeypatch.setenv('PGPASSWORD', 'badpassword')
    pytester.makepyfile(
        test_plain="""
def test_plain():
    assert True
"""
    )

    result = pytester.runpytest('-v')
    result.assert_outcomes(passed=1)
    output = '\n'.join([*result.stdout.lines, *result.stderr.lines])
    assert 'Unable to connect to Postgres' not in output

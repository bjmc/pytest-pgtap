# Tests for `-- pytest.mark...` comments on SQL file tests

from textwrap import dedent

import pytest

pytest_plugins = ['pytester']

PASSING_SQL = """
BEGIN;
    SELECT plan(1);
    SELECT pass('passes');
    SELECT * FROM finish();
ROLLBACK;
"""

FAILING_SQL = """
BEGIN;
    SELECT plan(1);
    SELECT fail('fails');
    SELECT * FROM finish();
ROLLBACK;
"""


def _run(pytester, database, *args):
    return pytester.runpytest('--pgtap-uri', database.get_connection_url(), *args)


def test_marker_selects_with_m(pytester, database):
    pytester.makeini('[pytest]\nmarkers =\n    slow: slow tests\n')
    pytester.makefile(
        '.sql',
        test_fast=PASSING_SQL,
        test_slow='-- A leading description comment is fine\n-- pytest.mark.slow\n' + PASSING_SQL,
    )
    result = _run(pytester, database, '-m', 'not slow', '--strict-markers')
    result.assert_outcomes(passed=1, deselected=1)


def test_skip_marker_with_reason(pytester, database):
    pytester.makefile('.sql', test_skip='-- pytest.mark.skip(reason="not today")\n' + PASSING_SQL)
    result = _run(pytester, database, '-rs')
    result.assert_outcomes(skipped=1)
    result.stdout.fnmatch_lines(['*not today*'])


def test_xfail_marker(pytester, database):
    pytester.makefile(
        '.sql', test_xfail='-- pytest.mark.xfail(reason="known bug", strict=True)\n' + FAILING_SQL
    )
    result = _run(pytester, database)
    result.stdout.fnmatch_lines(['*1 xfailed*'])


def test_marker_comment_after_sql_is_ignored(pytester, database):
    sql = PASSING_SQL.replace('BEGIN;', 'BEGIN;\n-- pytest.mark.skip')
    pytester.makefile('.sql', test_late=sql)
    result = _run(pytester, database)
    result.assert_outcomes(passed=1)


@pytest.mark.parametrize(
    'marker',
    [
        'pytest.mark.skip(reason=open("x"))',
        'pytest.mark.xfail(strict=True, strict=False)',
    ],
)
def test_invalid_marker_is_a_collection_error(pytester, database, marker):
    pytester.makefile('.sql', test_bad=f'-- {marker}\n' + PASSING_SQL)
    result = _run(pytester, database)
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(['*test_bad.sql:1: invalid marker*'])


def test_usefixtures_marker_runs_fixture_before_sql(pytester, database):
    pytester.makeconftest(
        """
        import pytest

        @pytest.fixture
        def tagged_session(pgtap_connection):
            with pgtap_connection.transaction():
                pgtap_connection.execute(
                    "SELECT set_config('application_name', 'fixture_ran', false)"
                )
        """
    )
    sql = dedent("""
        -- pytest.mark.usefixtures("tagged_session")
        BEGIN;
            SELECT plan(1);
            SELECT is(current_setting('application_name'), 'fixture_ran', 'fixture ran first');
            SELECT * FROM finish();
        ROLLBACK;
    """)
    pytester.makefile('.sql', test_fixture=sql)
    result = _run(pytester, database)
    result.assert_outcomes(passed=1)


MODULE_FIXTURE_CONFTEST = """
    import pytest

    @pytest.fixture(scope='module', autouse=True)
    def module_setup():
        print('MODULE FIXTURE RAN')
"""


def test_module_scoped_fixture_runs_for_sql_file(pytester, database):
    pytester.makeconftest(MODULE_FIXTURE_CONFTEST)
    pytester.makefile('.sql', test_module=PASSING_SQL)
    result = _run(pytester, database, '-s')
    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(['*MODULE FIXTURE RAN*'])

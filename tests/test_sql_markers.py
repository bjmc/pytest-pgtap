# Tests for `-- pytest.mark...` comments on SQL file tests

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


def test_invalid_marker_is_a_collection_error(pytester, database):
    pytester.makefile('.sql', test_bad='-- pytest.mark.skip(reason=open("x"))\n' + PASSING_SQL)
    result = _run(pytester, database)
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(['*test_bad.sql:1: invalid marker*'])

# Tests for the pytest.mark.pgtap inline Python mode

from .conftest import assert_tap_outcomes

pytest_plugins = ['pytester']

MARKER_PASSING = """
import pytest

@pytest.mark.pgtap
def test_passing():
    return [
        "SELECT pass('first assertion');",
        "SELECT pass('second assertion');",
    ]
"""

MARKER_FAILING = """
import pytest

@pytest.mark.pgtap
def test_with_failure():
    return [
        "SELECT pass('good one');",
        "SELECT fail('bad one');",
    ]
"""

MARKER_SINGLE_STRING = """
import pytest

@pytest.mark.pgtap
def test_single_string():
    return "SELECT pass('solo assertion');"
"""


def test_marker_all_pass(pytester, database):
    pytester.makepyfile(test_example=MARKER_PASSING)
    r = pytester.runpytest('-v', '--pgtap-uri', database.get_connection_url())
    assert_tap_outcomes(r, passed=2)


def test_marker_with_failure(pytester, database):
    pytester.makepyfile(test_example=MARKER_FAILING)
    r = pytester.runpytest('-v', '--pgtap-uri', database.get_connection_url())
    assert_tap_outcomes(r, failed=2, passed=1)


def test_marker_single_string(pytester, database):
    pytester.makepyfile(test_example=MARKER_SINGLE_STRING)
    r = pytester.runpytest('-v', '--pgtap-uri', database.get_connection_url())
    assert_tap_outcomes(r, passed=1)


def test_marker_no_connection(pytester, monkeypatch):
    """Marked tests skip when no Postgres connection is available."""
    monkeypatch.setenv('PGPASSWORD', 'badpassword')
    pytester.makepyfile(test_example=MARKER_PASSING)
    result = pytester.runpytest()
    result.assert_outcomes(skipped=1)

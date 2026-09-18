"""
pgTAP plugin for pytest
"""

import logging
import os
import re
from contextlib import nullcontext
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, NamedTuple, cast

import psycopg
import pytest
from _pytest.fixtures import TopRequest
from _pytest.python import Function
from psycopg import OperationalError, ProgrammingError
from pytest import UsageError
from tap.line import Bail, Diagnostic, Plan, Result
from tap.parser import Parser

# Use native pytest.Subtests (9.0+), fall back to pytest-subtests plugin
try:
    from pytest import Subtests
except ImportError:
    try:
        from pytest_subtests import SubTests as Subtests
    except ImportError as exc:
        raise ImportError(
            'pytest-pgtap requires either pytest >= 9.0 (native subtests) '
            'or the pytest-subtests package'
        ) from exc

from .pgtap import Runner, wrap_plan

if TYPE_CHECKING:
    from psycopg.abc import Query

logger = logging.getLogger(__name__)

# pgTAP's finish() prints this run-level summary.
# We use it as a check on our own failure count.
_SUMMARY_RE = re.compile(r'^#\s*Looks like you failed (\d+) tests? of (\d+)\.?\s*$')


class PgTapError(Exception):
    pass


class BailoutError(PgTapError):
    """Raised when pg_tap runner bailed out."""

    def __init__(self, bail: Bail):
        super().__init__(f'TAP bailed out – {bail.reason}')
        self.bail = bail


class MissingPlanError(PgTapError):
    """Raised when no plan is found in the results."""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Shared TAP/subtest reporting
# ---------------------------------------------------------------------------


def _make_subtests(item: pytest.Item) -> Subtests:
    """Build a SubTests instance without the fixture machinery."""
    capman = item.config.pluginmanager.get_plugin('capturemanager')
    suspend_capture_ctx = capman.global_and_fixture_disabled if capman is not None else nullcontext
    fake_request = cast('Any', SimpleNamespace(node=item, config=item.config, session=item.session))
    return Subtests(item.ihook, suspend_capture_ctx, fake_request)  # pyright: ignore


class TestResult(NamedTuple):
    result: Result
    diagnostics: list[str]


class ParsedTap(NamedTuple):
    plan: Plan
    results: list[TestResult]
    orphaned_diagnostics: list[str]
    summary_failed: int | None
    summary_total: int | None


def _parse_tap(tap_lines: list[str]) -> ParsedTap:
    """
    Iterate through the parsed TAP output, grouping
    any results along with their diagnostic lines that
    pgTAP uses to include additional information about failures.

    Raises BailoutError() and MissingPlanError()
    """
    plan = None
    results: list[TestResult] = []
    orphaned_diagnostics: list[str] = []
    summary_failed: int | None = None
    summary_total: int | None = None

    parser = Parser()
    parsed = parser.parse_text('\n'.join(tap_lines))

    for item in parsed:
        match item:
            case Bail():
                raise BailoutError(item)
            case Plan():
                plan = item
            case Result():
                results.append(TestResult(item, []))
            case Diagnostic():
                if match := _SUMMARY_RE.match(item.text):
                    summary_failed, summary_total = int(match[1]), int(match[2])
                elif results:
                    results[-1].diagnostics.append(item.text)
                else:
                    orphaned_diagnostics.append(item.text)
    if plan is None:
        raise MissingPlanError()
    return ParsedTap(plan, results, orphaned_diagnostics, summary_failed, summary_total)


def _report_tap(item: pytest.Item, tap_lines: list[str], label: str):
    """Parse TAP output and report each result as a pytest subtest.

    Handles bail-out, missing plan, plan-skip, individual results, and
    plan-count mismatches.
    """
    try:
        tap = _parse_tap(tap_lines)
    except MissingPlanError:
        pytest.fail(f'{label}: no TAP plan found', pytrace=False)
    except BailoutError as err:
        pytest.fail(f'{label}: {err}', pytrace=False)

    if tap.orphaned_diagnostics:
        item.add_report_section('call', 'pgTAP diagnostics', '\n'.join(tap.orphaned_diagnostics))

    if tap.plan.skip:
        pytest.skip()

    n_failed = 0
    subtests = _make_subtests(item)
    for tr, diagnostics in tap.results:
        with subtests.test(msg=tr.description):
            if not tr.ok:
                n_failed += 1
                msg = f'{tr.number} – {tr.description}'
                if diagnostics:
                    msg += '\n' + '\n'.join(diagnostics)
                pytest.fail(msg, pytrace=False)

    n_expected, n_run = tap.plan.expected_tests, len(tap.results)
    if n_run != n_expected:
        pytest.fail(
            f'{label}: Bad plan. You planned {n_expected} tests but actually ran {n_run}.',
            pytrace=False,
        )

    # finish() reports its own independent failure count
    # this SHOULD always agree with ours
    if tap.summary_failed is not None and tap.summary_failed != n_failed:
        pytest.fail(
            f'{label}: pytest-pgtap counted {n_failed} failing test(s) but pgTAP '
            f'reported {tap.summary_failed} in its own summary -- this points to '
            'a bug in pytest-pgtap TAP parsing, not the SQL under test.',
            pytrace=False,
        )

    if n_failed:
        pytest.fail(f'{label} contains failures.', pytrace=False)


def _normalize_sql_lines(result: object) -> list[str]:
    if isinstance(result, str):
        return [result]
    if isinstance(result, list) and all(isinstance(line, str) for line in result):
        return cast('list[str]', result)
    raise TypeError('pytest.mark.pgtap tests must return a SQL string or list[str]')


# ---------------------------------------------------------------------------
# pytest hooks
# ---------------------------------------------------------------------------


def pytest_configure(config):
    config.addinivalue_line('markers', 'pgtap: mark a test as a pgTAP inline test')


def pytest_collect_file(parent, file_path):
    if file_path.suffix == '.sql' and file_path.name.startswith('test'):
        logger.debug('Collected %s in %s', file_path, parent)
        return PgTapFile.from_parent(parent, path=file_path)
    return None


def pytest_collection_modifyitems(session, config, items):
    schema = config.getoption('pgtap_schema')
    if schema:
        pattern = config.getoption('pgtap_match')
        runtests_item = PgTapRuntestsItem.from_parent(
            session,
            name=f'<pgTAP runtests({schema})>',
            schema=schema,
            pattern=pattern,
        )
        items.append(runtests_item)


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_call(item: pytest.Item):
    """Intercept tests marked with ``pytest.mark.pgtap``."""
    marker = item.get_closest_marker('pgtap')
    if marker is None or not isinstance(item, pytest.Function):
        yield
        return

    runner = item._request.getfixturevalue('_pgtap_runner')
    if not isinstance(runner, Runner):
        item.obj = lambda **kw: pytest.skip('pgTAP test skipped: no Postgres connection')
        yield
        return

    try:
        sql_lines = _normalize_sql_lines(item.obj())
        query = cast('Query', wrap_plan(*sql_lines))
        tap_lines = runner.run(query)
        item.obj = lambda **kw: _report_tap(item, tap_lines, item.name)
    except (psycopg.Error, ValueError, TypeError) as err:
        # Capture err by value in default param to avoid scope closure issues
        item.obj = lambda _err=err, **kw: pytest.fail(f'pgTAP setup failed: {_err}')

    yield


def pytest_addoption(parser):
    """pytest hook:  add options to the pytest cli"""
    group = parser.getgroup('pgtap', 'pgtap test runner')
    group.addoption(
        '--pgtap-uri',
        help='database uri, defaults to DATABASE_URL env',
        default=os.environ.get('DATABASE_URL'),
    )
    group.addoption(
        '--pgtap-schema',
        default=None,
        help='Schema in which to find xUnit tests; Run xUnit tests using runtests()',
    )
    group.addoption(
        '--pgtap-match',
        default=None,
        help='Regex pattern to filter xUnit test function names (used with --pgtap-schema)',
    )


def pytest_report_header(config):
    """pytest hook: return a string to be displayed as header info for terminal reporting"""
    return '\n'.join(
        [
            'pgTap Connection: {}'.format(config.getoption('pgtap_uri')),
            'pgTap Schema: {}'.format(
                config.getoption('pgtap_schema', default='runtests() disabled')
            ),
        ]
    )


# ---------------------------------------------------------------------------
# Mode 1: SQL file test items
# ---------------------------------------------------------------------------


class _FixtureItem(pytest.Item):
    """Mixin that gives a plain pytest.Item access to the fixture machinery.

    Normally only pytest.Function items participate in fixture setup. This
    mixin opts in by implementing setup() using internal pytest APIs that have
    been stable since pytest 7.
    """

    def setup(self):
        self._fixtureinfo = self.session._fixturemanager.getfixtureinfo(self, func=None, cls=None)
        self._request = TopRequest(cast(Function, self), _ispytest=True)


class PgTapFile(pytest.File):
    def collect(self):
        yield PgTapItem.from_parent(self, name=self.path.name)


class PgTapItem(_FixtureItem):
    def runtest(self):
        runner = self._request.getfixturevalue('_pgtap_runner')
        if not isinstance(runner, Runner):
            pytest.skip(f'PgTAP tests {self.path.name} skipped: no Postgres connection')
        tap_lines = runner.run(cast('Query', self.path.read_text()))
        _report_tap(self, tap_lines, self.path.name)

    def reportinfo(self):
        return self.path, None, self.name


# ---------------------------------------------------------------------------
# Mode 2: xUnit runtests() item
# ---------------------------------------------------------------------------


class PgTapRuntestsItem(_FixtureItem):
    def __init__(self, *, schema: str, pattern: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self.schema = schema
        self.pattern = pattern

    def runtest(self):
        runner = self._request.getfixturevalue('_pgtap_runner')
        if not isinstance(runner, Runner):
            pytest.skip('pgTAP runtests skipped: no Postgres connection')
        tap_lines = runner.runtests(schema=self.schema, pattern=self.pattern)
        _report_tap(self, tap_lines, self.name)

    def reportinfo(self):
        return '<pgtap>', None, self.name

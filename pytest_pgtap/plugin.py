"""
pgTAP plugin for pytest
"""

from contextlib import nullcontext
import logging
import os
import pytest
from pytest import Config, StashKey, UsageError
import psycopg
from psycopg.abc import Query
from psycopg import OperationalError, ProgrammingError
from tap.parser import Parser
from tap.line import Result, Bail, Plan
from types import SimpleNamespace

from typing import Any, Generator, cast

# Use native pytest.Subtests (9.0+), fall back to pytest-subtests plugin
try:
    from pytest import Subtests as Subtests
except ImportError:
    try:
        from pytest_subtests import SubTests as Subtests  # ty: ignore[unresolved-import]
    except ImportError as exc:
        raise ImportError(
            'pytest-pgtap requires either pytest >= 9.0 (native subtests) '
            'or the pytest-subtests package'
        ) from exc

from .pgtap import Runner, wrap_plan


logger = logging.getLogger(__name__)


class PgTapError(Exception):
    pass


_runner_key: StashKey[Runner | None] = StashKey()


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------


def get_runner(config: Config) -> Runner | None:
    if _runner_key in config.stash:
        return config.stash[_runner_key]

    if db_uri := config.getoption('pgtap_uri'):
        try:
            conn = psycopg.connect(db_uri)
        except (OperationalError, ProgrammingError) as err:
            raise UsageError(f'Unable to connect to Postgres: {err}') from err
    else:
        # Connect relying on env vars
        # https://www.postgresql.org/docs/current/libpq-envars.html
        try:
            conn = psycopg.connect()
        except OperationalError as err:
            logger.warning('pytest-pgtap: Unable to connect to Postgres: %s', err)
            return None
    return Runner(conn)


# ---------------------------------------------------------------------------
# Shared TAP/subtest reporting
# ---------------------------------------------------------------------------


def _make_subtests(item: pytest.Item) -> Subtests:
    """Build a SubTests instance without the fixture machinery."""
    capman = item.config.pluginmanager.get_plugin('capturemanager')
    if capman is not None:
        suspend_capture_ctx = capman.global_and_fixture_disabled
    else:
        suspend_capture_ctx = nullcontext
    fake_request = cast(Any, SimpleNamespace(node=item, config=item.config, session=item.session))
    return Subtests(item.ihook, suspend_capture_ctx, fake_request)  # pyright: ignore


def _report_tap(item: pytest.Item, tap_lines: list[str], label: str):
    """Parse TAP output and report each result as a pytest subtest.

    Handles bail-out, missing plan, plan-skip, individual results, and
    plan-count mismatches.
    """
    tap_output = '\n'.join(tap_lines)
    parser = Parser()
    results = list(parser.parse_text(tap_output))

    plan = next((r for r in results if isinstance(r, Plan)), None)
    test_results = [r for r in results if isinstance(r, Result)]
    bail = next((r for r in results if isinstance(r, Bail)), None)

    if bail:
        pytest.fail(f'{label}: TAP bailed out – {bail.reason}', pytrace=False)
    if not plan:
        pytest.fail(f'{label}: no TAP plan found', pytrace=False)

    if plan.skip:
        pytest.skip()

    failure = False
    subtests = _make_subtests(item)
    for tr in test_results:
        with subtests.test(msg=tr.description):
            if not tr.ok:
                failure = True
                pytest.fail(
                    f'{tr.number} – {tr.description}',
                    pytrace=False,
                )

    n_expected, n_run = plan.expected_tests, len(test_results)
    if n_run != n_expected:
        pytest.fail(
            f'{label}: Bad plan. You planned {n_expected} tests but actually ran {n_run}.',
            pytrace=False,
        )
    if failure:
        pytest.fail(f'{label} contains failures.', pytrace=False)


def _normalize_sql_lines(result: object) -> list[str]:
    if isinstance(result, str):
        return [result]
    if isinstance(result, list) and all(isinstance(line, str) for line in result):
        return cast(list[str], result)
    raise TypeError('pytest.mark.pgtap tests must return a SQL string or list[str]')


# ---------------------------------------------------------------------------
# pytest hooks
# ---------------------------------------------------------------------------


def pytest_configure(config):
    config.addinivalue_line('markers', 'pgtap: mark a test as a pgTAP inline test')
    runner = get_runner(config)
    config.stash[_runner_key] = runner
    if runner:
        config.add_cleanup(runner.close)


def pytest_collect_file(parent, file_path):
    if file_path.suffix == '.sql' and file_path.name.startswith('test'):
        logger.debug('Collected {} in {}', file_path, parent)
        return PgTapFile.from_parent(parent, path=file_path)


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

    runner = get_runner(item.config)
    if runner is None:
        item.obj = lambda **kw: pytest.skip('pgTAP test skipped: no Postgres connection')
        yield
        return

    try:
        sql_lines = _normalize_sql_lines(item.obj())
        query = cast(Query, wrap_plan(*sql_lines))
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
            'pgTap Connection: {0}'.format(config.getoption('pgtap_uri')),
            'pgTap Schema: {0}'.format(
                config.getoption('pgtap_schema', default='runtests() disabled')
            ),
        ]
    )


# ---------------------------------------------------------------------------
# Mode 1: SQL file test items
# ---------------------------------------------------------------------------


class PgTapFile(pytest.File):
    def collect(self):
        yield PgTapItem.from_parent(self, name=self.path.name)


class PgTapItem(pytest.Item):
    def runtest(self):
        runner = get_runner(self.config)
        if runner is None:
            pytest.skip(f'PgTAP tests {self.path.name} skipped: no Postgres connection')
        tap_lines = runner.run(cast(Query, self.path.read_text()))
        _report_tap(self, tap_lines, self.path.name)

    def reportinfo(self):
        return self.path, None, self.name


# ---------------------------------------------------------------------------
# Mode 2: xUnit runtests() item
# ---------------------------------------------------------------------------


class PgTapRuntestsItem(pytest.Item):
    def __init__(self, *, schema: str, pattern: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self.schema = schema
        self.pattern = pattern

    def runtest(self):
        runner = get_runner(self.config)
        if runner is None:
            pytest.skip('pgTAP runtests skipped: no Postgres connection')
        tap_lines = runner.runtests(schema=self.schema, pattern=self.pattern)
        _report_tap(self, tap_lines, self.name)

    def reportinfo(self):
        return '<pgtap>', None, self.name


# ---------------------------------------------------------------------------
# Session-scoped fixture (for users who want manual control)
# ---------------------------------------------------------------------------


@pytest.fixture(scope='session')
def pgtap_runner(request) -> Generator[Runner, None, None]:
    """create extension pgtap if not exists;

    run once before tests, but after pytest_configure hook
    """
    with psycopg.connect(request.config.getoption('pgtap_uri')) as conn:
        runner = Runner(conn)
        logger.debug('Creating the pgtap extension before tests...')
        runner.run('CREATE EXTENSION IF NOT EXISTS pgtap;')
        yield runner

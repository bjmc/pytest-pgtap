"""Mode 3: Python tests marked with ``pytest.mark.pgtap`` that return SQL."""

from typing import TYPE_CHECKING, cast

import psycopg
import pytest

from ..pgtap import Runner, wrap_plan
from .core import report_tap

if TYPE_CHECKING:
    from psycopg.abc import Query


def _normalize_sql_lines(result: object) -> list[str]:
    if isinstance(result, str):
        return [result]
    if isinstance(result, list) and all(isinstance(line, str) for line in result):
        return cast('list[str]', result)
    raise TypeError('pytest.mark.pgtap tests must return a SQL string or list[str]')


def pytest_configure(config):
    config.addinivalue_line('markers', 'pgtap: mark a test as a pgTAP inline test')


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
        # Pass fixtures the test requested, as pytest's own pytest_pyfunc_call does.
        funcargs = {name: item.funcargs[name] for name in item._fixtureinfo.argnames}
        sql_lines = _normalize_sql_lines(item.obj(**funcargs))
        query = cast('Query', wrap_plan(*sql_lines))
        tap_lines = runner.run(query)
        item.obj = lambda **kw: report_tap(item, tap_lines, item.name)
    except (psycopg.Error, ValueError, TypeError) as err:
        # Capture err by value in default param to avoid scope closure issues
        item.obj = lambda _err=err, **kw: pytest.fail(f'pgTAP setup failed: {_err}')

    yield

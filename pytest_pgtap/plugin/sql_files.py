"""Mode 1: SQL file tests, collected from ``test*.sql`` files."""

import ast
import logging
import re
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, cast

import pytest

from ..pgtap import Runner
from .core import _FixtureItem, _report_tap

if TYPE_CHECKING:
    from psycopg.abc import Query

logger = logging.getLogger(__name__)


def pytest_collect_file(parent, file_path):
    if file_path.suffix == '.sql' and file_path.name.startswith('test'):
        logger.debug('Collected %s in %s', file_path, parent)
        return PgTapFile.from_parent(parent, path=file_path)
    return None


_MARK_RE = re.compile(r'pytest\.mark\.(\w+)(\(.*\))?')


def _parse_mark(text: str) -> pytest.MarkDecorator:
    """Parse ``pytest.mark.NAME`` or ``pytest.mark.NAME(<literal args>)`` without eval()."""
    match = _MARK_RE.fullmatch(text)
    if not match:
        raise ValueError('expected pytest.mark.NAME or pytest.mark.NAME(...)')
    name, arglist = match.groups()
    # ast handles quoting and nesting in the arguments; literal_eval only accepts literals.
    tree = ast.parse(f'_{arglist or "()"}', mode='eval')
    compile(tree, '<marker>', 'eval')  # Python's own checks, e.g. repeated keywords; nothing runs.
    call = tree.body
    if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)):
        raise ValueError('expected a single argument list')  # noqa: TRY004 - bad input, not type
    kwargs: dict[str, Any] = {}
    for kw in call.keywords:
        if kw.arg is None:
            raise ValueError('**kwargs are not supported')
        kwargs[kw.arg] = ast.literal_eval(kw.value)
    args = [ast.literal_eval(arg) for arg in call.args]
    return getattr(pytest.mark, name).with_args(*args, **kwargs)


def _parse_marks(sql: str, filename: str) -> Iterator[pytest.MarkDecorator]:
    """Yield markers from ``-- pytest.mark...`` comments before the first line of SQL."""
    for lineno, line in enumerate(sql.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        if not line.startswith('--'):
            return
        text = line.removeprefix('--').strip()
        if text.startswith('pytest.mark.'):
            try:
                yield _parse_mark(text)
            except (SyntaxError, ValueError) as err:
                raise pytest.Collector.CollectError(
                    f'{filename}:{lineno}: invalid marker {text!r}: {err}'
                ) from err


class PgTapFile(pytest.File):
    def collect(self):
        item = PgTapItem.from_parent(self, name=self.path.name)
        for mark in _parse_marks(self.path.read_text(), self.path.name):
            item.add_marker(mark)
        yield item


class PgTapItem(_FixtureItem):
    def runtest(self):
        runner = self._request.getfixturevalue('_pgtap_runner')
        if not isinstance(runner, Runner):
            pytest.skip(f'PgTAP tests {self.path.name} skipped: no Postgres connection')
        tap_lines = runner.run(cast('Query', self.path.read_text()))
        _report_tap(self, tap_lines, self.path.name)

    def reportinfo(self):
        return self.path, 0, self.name

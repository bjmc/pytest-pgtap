"""Mode 2: xUnit tests run with pgTAP's ``runtests()``."""

import pytest

from ..pgtap import Runner
from .core import _FixtureItem, _report_tap


def _rootdir_node(session: pytest.Session) -> pytest.Collector:
    """Return the collected node for rootdir, whose conftest fixtures we want, or the session."""
    rootpath = session.config.rootpath
    for node in session._collection_cache:
        if isinstance(node, pytest.Directory) and node.path == rootpath:
            return node
    return session


def pytest_collection_modifyitems(session, config, items):
    schema = config.getoption('pgtap_schema')
    if schema:
        pattern = config.getoption('pgtap_match')
        # runtests() tests live in the database rather than in a file, so parent them to
        # rootdir: that makes fixtures from the root conftest.py (e.g. a pgtap_connection
        # override) apply to them.
        runtests_item = PgTapRuntestsItem.from_parent(
            _rootdir_node(session),
            name=f'<pgTAP runtests({schema})>',
            schema=schema,
            pattern=pattern,
        )
        items.append(runtests_item)


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

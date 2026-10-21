"""Shared by all pgTAP test modes: TAP parsing, subtest reporting and fixture support."""

import re
from contextlib import nullcontext
from types import SimpleNamespace
from typing import Any, NamedTuple, cast

import pytest
from _pytest.fixtures import TopRequest
from _pytest.python import Function
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


def report_tap(item: pytest.Item, tap_lines: list[str], label: str):
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


class FixtureItem(pytest.Item):
    """Mixin that gives a plain pytest.Item access to the fixture machinery.

    Normally only pytest.Function items participate in fixture setup. This
    mixin opts in by implementing setup() using internal pytest APIs that have
    been stable since pytest 7.
    """

    def setup(self):
        self._fixtureinfo = self.session._fixturemanager.getfixtureinfo(self, func=None, cls=None)
        self.fixturenames = self._fixtureinfo.names_closure
        self.funcargs: dict[str, object] = {}
        self._request = TopRequest(cast(Function, self), _ispytest=True)
        # Run requested fixtures (usefixtures markers, autouse), as Function.setup() does.
        self._request._fillfixtures()

    def getparent(self, cls):
        # pytest scopes module fixtures to the nearest pytest.Module, which these items
        # lack; let the SQL file (or the session, for runtests()) stand in for it.
        if cls is pytest.Module:
            return self.parent
        return super().getparent(cls)

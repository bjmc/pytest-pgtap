"""
pgTAP plugin for pytest

pytest loads hooks and fixtures by name from this module, so each one is re-exported here.
"""

from .core import BailoutError, MissingPlanError, ParsedTap, PgTapError, TestResult
from .fixtures import _pgtap_runner, pgtap_connection
from .marker import pytest_configure, pytest_runtest_call
from .options import pytest_addoption, pytest_report_header
from .runtests import PgTapRuntestsItem, pytest_collection_modifyitems
from .sql_files import PgTapFile, PgTapItem, pytest_collect_file

__all__ = [
    'BailoutError',
    'MissingPlanError',
    'ParsedTap',
    'PgTapError',
    'PgTapFile',
    'PgTapItem',
    'PgTapRuntestsItem',
    'TestResult',
    '_pgtap_runner',
    'pgtap_connection',
    'pytest_addoption',
    'pytest_collect_file',
    'pytest_collection_modifyitems',
    'pytest_configure',
    'pytest_report_header',
    'pytest_runtest_call',
]

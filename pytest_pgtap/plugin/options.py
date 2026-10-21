"""Command-line options and the terminal report header."""

import os


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

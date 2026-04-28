import os

import pytest
from testcontainers.postgres import PostgresContainer

pytest_plugins = ['pytester']

_PG_TAG = os.environ.get('PGTAP_PG_IMAGE_TAG', '18')


def assert_tap_outcomes(result, *, passed: int = 0, failed: int = 0):
    if failed:
        result.stdout.fnmatch_lines([f'*{failed} failed*'])
    elif passed:
        result.stdout.fnmatch_lines([f'*{passed} subtest*passed*'])


@pytest.fixture(scope='session')
def database():
    image = f'docker.io/pshaddel/postgres-pgtap:{_PG_TAG}'
    with PostgresContainer(image, driver=None) as postgres:
        yield postgres

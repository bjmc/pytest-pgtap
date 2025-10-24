"""
core functionality for pgTap python implementation
"""

from typing import Any

from psycopg.rows import scalar_row
from psycopg import Connection, sql, Cursor
from psycopg.abc import Query
from psycopg.pq import ExecStatus


class Runner:
    def __init__(self, connection: Connection[Any]):
        self.conn = connection

    def get_testnames_from_schema(self, schema: str) -> list[str]:
        return self.run(
            sql.SQL('SELECT findfuncs({schema}::name, {exclude})').format(
                schema=sql.Literal(schema),
                exclude=sql.Literal('^(startup|shutdown|setup|teardown)'),
            )
        )

    def runtests(self, schema: str | None = None, pattern: str | None = None) -> list[str]:
        # https://pgtap.org/documentation.html#runtests
        args = {'schema': sql.Literal(schema), 'pattern': sql.Literal(pattern)}
        if schema and pattern:
            func = sql.SQL('runtests({schema}, {pattern})').format(**args)
        elif schema:
            func = sql.SQL('runtests({schema}::name)').format(**args)
        elif pattern:
            func = sql.SQL('runtests({pattern})').format(**args)
        else:
            func = sql.SQL('runtests()')
        query = sql.SQL('SELECT * FROM {func}').format(func=func)
        return self.run(query)

    @staticmethod
    def _collectrows(cur: Cursor[Any]) -> list[str]:
        rows: list[str] = []
        more_results = True
        while more_results:
            if cur.pgresult and cur.pgresult.status == ExecStatus.TUPLES_OK:
                rows.extend(cur.fetchall())
            more_results = cur.nextset()
        return rows

    def run(self, query: Query) -> list[str]:
        with self.conn.transaction():
            cur = self.conn.cursor(row_factory=scalar_row)
            cur.execute(query)
            return self._collectrows(cur)

    def close(self):
        self.conn.close()


def wrap_plan(*lines: str) -> str:
    """Wrap in pgtap plan functions, assumes each line is a test"""
    # You can't run a pgTap query without a plan unless it's a
    # runtests() call to db test functions

    return '\n'.join(
        [
            'BEGIN;',
            'SELECT plan(%s);' % len(lines),
            *lines,
            'SELECT * FROM finish();',
            'ROLLBACK;',
        ]
    )

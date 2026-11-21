import logging
from typing import Any, Sequence

import psycopg
from psycopg import sql
from psycopg.pq import TransactionStatus
from psycopg.rows import dict_row, scalar_row, tuple_row
from .config import Configs
from .pool import PGPool
from .utils import (
    build_select_query,
    build_insert_query,
    build_update_query,
    build_delete_query,
    build_update_batch_query,
    build_upsert_batch_query,
    build_call_func_query,
    build_call_proc_query,
    _sql_table,
    _sql_returning,
)

log = logging.getLogger('caddix')


class CaddixError(Exception):
    def __init__(self, orig: Exception, stm: str, params: Any, verbose: bool = False):
        self.orig = orig
        if verbose:
            msg = [
                stm, str(params),
                f'{orig.__class__.__name__}: {orig}'
            ]
        else:
            diag = getattr(orig, 'diag', None)
            primary_msg = getattr(diag, 'message_primary', None) if diag else None
            if primary_msg:
                msg = [f'{orig.__class__.__name__}: {primary_msg}']
            else:
                msg = [f'{orig.__class__.__name__}']
        super().__init__('\n'.join(msg))


class CaddixSessionError(Exception):
    pass


# Backward compatibility aliases
TuskerError = CaddixError
TuskerSessionError = CaddixSessionError


class DatabaseSession:
    """
    Represents a database session to manage connections and execute queries.

    The DatabaseSession class facilitates interaction with a PostgreSQL database using a connection pool.
    It provides methods for executing queries, fetching results, and performing various database operations.
    This class also supports context management, which ensures that resources are properly cleaned up
    when the session scope completes.

    :ivar cursor_factory: Defines the row factory used for fetching results, allowing custom transformations
        of query results into specific formats or types.
    :type cursor_factory: callable
    :ivar con: The database connection object used for all database interactions through this session.
    :type con: psycopg.Connection
    :ivar cur: The database cursor used to execute and fetch query results.
    :type cur: psycopg.Cursor
    :ivar last_query: Stores the last executed query string. Useful for debugging or logging purposes.
    :type last_query: str
    """

    def __init__(self, configname='default', cursor_factory=None):
        self.configname = configname
        self.cnf = Configs.configs[configname]

        self.cursor_factory = self.cnf['default_rowfactory']
        if cursor_factory:
            self.cursor_factory = cursor_factory

        self.pool = PGPool(configname)
        self.con = self.pool.con
        self.cur = self.con.cursor()
        self.cur.row_factory = self.cursor_factory
        self.last_query: str | None = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        if hasattr(self, 'cur') and self.cur is not None and not self.cur.closed:
            try:
                self.cur.close()
            except psycopg.Error:
                pass
        if hasattr(self, 'con') and self.con is not None:
            try:
                if not self.con.closed:
                    self.con.rollback()
            except psycopg.Error:
                pass
            if hasattr(self, 'pool') and self.pool is not None:
                self.pool.release(self.con, self.pool.expire)
                self.pool = None

    @staticmethod
    def __kwargs__(kwargs):
        if not kwargs:
            return {}
        return {
            (k[1:] if k.startswith('_') and len(k) > 1 and not k.startswith('__') else k): v
            for k, v in kwargs.items()
        }

    def commit(self):
        self.con.commit()

    def rollback(self):
        self.con.rollback()

    def execute(self, query, *args, **kwargs):
        self.last_query = str(query)
        clean_kwargs = self.__kwargs__(kwargs)
        try:
            if args:
                params = args[0] if len(args) == 1 and isinstance(args[0], (tuple, list, dict)) else args
                self.cur.execute(query, params)
            elif clean_kwargs:
                self.cur.execute(query, clean_kwargs)
            else:
                self.cur.execute(query)
        except Exception as e:
            params = args if args else clean_kwargs
            raise CaddixError(e, self.last_query, params, verbose=self.cnf.get('verbose', False)) from None

    def executemany(self, query, values):
        self.last_query = str(query)
        verbose = self.cnf.get('verbose', False)
        try:
            self.cur.executemany(query, values)
        except Exception as e:
            raise CaddixError(e, self.last_query, values, verbose=verbose) from None

    # ===== fetch from cursor after executing =====

    def fetchone(self):
        if not self.cur.description:
            return None
        return self.cur.fetchone()

    def fetchall(self):
        if not self.cur.description:
            return []
        return self.cur.fetchall()

    def fetchmany(self, size):
        if not self.cur.description:
            return []
        return self.cur.fetchmany(size)

    def fetchscalar(self):
        if not self.cur.description:
            return None
        factory = self.cur.row_factory
        try:
            self.cur.row_factory = scalar_row
            return self.fetchone()
        finally:
            self.cur.row_factory = factory

    def fetchlist(self):
        if not self.cur.description:
            return []
        factory = self.cur.row_factory
        try:
            self.cur.row_factory = tuple_row
            res = self.fetchall()
            return [v[0] for v in res] if res else []
        finally:
            self.cur.row_factory = factory

    def fetchdict(self):
        if not self.cur.description:
            return {}
        factory = self.cur.row_factory
        try:
            self.cur.row_factory = tuple_row
            res = self.fetchall()
            return {k: v for k, v in res} if res else {}
        finally:
            self.cur.row_factory = factory

    # ===== execute and return fetched row/s =====

    def execute_fetchone(self, query, *args, **kwargs):
        self.execute(query, *args, **kwargs)
        return self.fetchone()

    def execute_fetchall(self, query, *args, **kwargs):
        self.execute(query, *args, **kwargs)
        return self.fetchall()

    def execute_fetchmany(self, query, size, *args, **kwargs):
        self.execute(query, *args, **kwargs)
        return self.fetchmany(size)

    def execute_fetchscalar(self, query, *args, **kwargs):
        self.execute(query, *args, **kwargs)
        return self.fetchscalar()

    def execute_fetchdict(self, query, *args, **kwargs):
        self.execute(query, *args, **kwargs)
        return self.fetchdict()

    def execute_fetchlist(self, query, *args, **kwargs):
        self.execute(query, *args, **kwargs)
        return self.fetchlist()

    def _execute_select(self, tablename: str, columns: Sequence[str] | str = ('*',), **kwargs):
        kwargs = self.__kwargs__(kwargs)
        query, params = build_select_query(con=self.con, tablename=tablename, columns=columns, **kwargs)
        self.execute(query, **params)

    def select_all(self, tablename: str, columns: Sequence[str] | str = ('*',), **kwargs):
        self._execute_select(tablename, columns=columns, **kwargs)
        return self.fetchall()

    def select_one(self, tablename: str, columns: Sequence[str] | str = ('*',), **kwargs):
        self._execute_select(tablename, columns=columns, **kwargs)
        return self.fetchone()

    def select_scalar(self, tablename: str, column: str, **kwargs):
        self._execute_select(tablename, columns=[column], **kwargs)
        return self.fetchscalar()

    def select_many(self, tablename: str, size: int, columns: Sequence[str] | str = ('*',), **kwargs):
        if size is None or size <= 0:
            raise CaddixSessionError('select_many() requires size > 0')
        self._execute_select(tablename, columns=columns, **kwargs)
        return self.fetchmany(size)

    def select_list(self, tablename: str, column: str, **kwargs):
        self._execute_select(tablename, columns=[column], **kwargs)
        return self.fetchlist()

    def select_dict(self, tablename: str, column_key: str, column_value: str, **kwargs):
        self._execute_select(tablename, columns=[column_key, column_value], **kwargs)
        return self.fetchdict()

    # ===== for easy data-manipulation =====

    def insert(self, tablename: str, returning=None, **kwargs):
        kwargs = self.__kwargs__(kwargs)
        query, safe_params = build_insert_query(self.con, tablename, kwargs, returning=returning)
        self.execute(query, **safe_params)
        if returning:
            return self.fetchone()
        return None

    def update(self, tablename: str, values: dict[str, Any] | None = None, returning=None, check_changes: bool = False, **kwargs):
        kwargs = self.__kwargs__(kwargs)
        values = {} if values is None else self.__kwargs__(values)
        query, safe_params, has_set = build_update_query(
            self.con, tablename, values, returning=returning, check_changes=check_changes, **kwargs
        )
        if not has_set:
            return [] if returning else 0

        self.execute(query, **safe_params)
        if returning:
            return self.fetchall()
        return None

    def delete(self, tablename: str, returning=None, allow_all: bool = False, **kwargs):
        kwargs = self.__kwargs__(kwargs)
        if not kwargs and not allow_all:
            raise CaddixSessionError(
                f"Deleting all rows from '{tablename}' without WHERE conditions is disabled by default. "
                f"Pass allow_all=True to confirm full table deletion."
            )
        query, safe_params = build_delete_query(self.con, tablename, returning=returning, **kwargs)
        self.execute(query, **safe_params)
        if returning:
            return self.fetchall()
        return None

    # ===== for easy bulk data-manipulation =====

    def insert_batch(self, tablename, values, returning=None):
        if not values:
            return 0

        clean_values = [self.__kwargs__(v) for v in values]
        first_row = clean_values[0]
        columns = list(first_row.keys())

        ret_sql = _sql_returning(returning)
        if not ret_sql:
            sql_copy = sql.SQL("COPY {table} ({cols}) FROM STDIN").format(
                table=_sql_table(tablename),
                cols=sql.SQL(", ").join(map(sql.Identifier, columns))
            )

            with self.cur.copy(sql_copy) as copy:
                for row in clean_values:
                    copy.write_row([row.get(col) for col in columns])

            return self.cur.rowcount

        columns_sql = sql.SQL(', ').join(map(sql.Identifier, columns))
        placeholders_sql = sql.SQL(', ').join(map(lambda c: sql.SQL("%({})s").format(sql.SQL(c)), columns))

        query = sql.SQL("INSERT INTO {table} ({cols}) VALUES ({vals})").format(
            table=_sql_table(tablename),
            cols=columns_sql,
            vals=placeholders_sql
        )

        query += sql.SQL(" RETURNING ") + ret_sql

        self.executemany(query, clean_values)
        return self.fetchall()

    def update_batch(self, tablename, values, update_columns, where_columns, returning=None, check_changes: bool = False):
        if not values:
            return 0

        clean_values = [self.__kwargs__(v) for v in values]
        first_row = clean_values[0]

        if update_columns == '*' or (isinstance(update_columns, (list, tuple)) and len(update_columns) == 1 and update_columns[0] == '*'):
            target_update_columns = [col for col in first_row.keys() if col not in where_columns]
        elif isinstance(update_columns, str):
            target_update_columns = [c.strip() for c in update_columns.split(',') if c.strip()]
        else:
            target_update_columns = list(update_columns)

        if isinstance(where_columns, str):
            target_where_columns = [c.strip() for c in where_columns.split(',') if c.strip()]
        else:
            target_where_columns = list(where_columns)

        for col in list(target_update_columns) + list(target_where_columns):
            if col not in first_row:
                raise CaddixSessionError(f'Column "{col}" not found in values')

        query = build_update_batch_query(
            self.con, tablename, target_update_columns, target_where_columns, returning=returning, check_changes=check_changes
        )

        self.executemany(query, clean_values)

        if returning:
            return self.fetchall()
        return self.cur.rowcount

    def upsert_batch(self, tablename, values, conflict_columns=None, update_columns='*', returning=None, conflict_target=None, check_changes: bool = False):
        if not values:
            return 0

        if conflict_columns is None and conflict_target is not None:
            conflict_columns = conflict_target

        if conflict_columns is None:
            raise CaddixSessionError('conflict_columns is required for upsert_batch')

        clean_values = [self.__kwargs__(v) for v in values]
        first_row = clean_values[0]
        columns = list(first_row.keys())

        if isinstance(conflict_columns, str):
            target_conflict_columns = [c.strip() for c in conflict_columns.split(',') if c.strip()]
        else:
            target_conflict_columns = list(conflict_columns)

        query = build_upsert_batch_query(
            self.con, tablename, columns, target_conflict_columns, update_columns=update_columns, returning=returning, check_changes=check_changes
        )

        self.executemany(query, clean_values)

        if returning:
            return self.fetchall()
        return self.cur.rowcount

    # ===== function & procedure execution =====

    def call_func(self, funcname: str, *args, **kwargs):
        """
        Executes a PostgreSQL function (SELECT * FROM funcname(...)) and returns all result rows.
        """
        return self.func_all(funcname, *args, **kwargs)

    def call_function(self, funcname: str, *args, **kwargs):
        """
        Alias for call_func.
        """
        return self.call_func(funcname, *args, **kwargs)

    def _execute_func(self, funcname: str, as_table: bool, *args, **kwargs):
        kwargs = self.__kwargs__(kwargs)
        query, params = build_call_func_query(self.con, funcname, as_table, *args, **kwargs)
        self.execute(query, **params)

    def func_all(self, funcname: str, *args, **kwargs):
        """
        Executes a PostgreSQL function and returns all result rows (via fetchall).
        """
        self._execute_func(funcname, True, *args, **kwargs)
        return self.fetchall()

    def func_one(self, funcname: str, *args, **kwargs):
        """
        Executes a PostgreSQL function and returns a single result row (via fetchone).
        """
        self._execute_func(funcname, True, *args, **kwargs)
        return self.fetchone()

    def func_scalar(self, funcname: str, *args, **kwargs):
        """
        Executes a PostgreSQL function (SELECT funcname(...)) and returns a single scalar value.
        """
        self._execute_func(funcname, False, *args, **kwargs)
        return self.fetchscalar()

    def func_many(self, funcname: str, size: int, *args, **kwargs):
        """
        Executes a PostgreSQL function and returns up to `size` result rows (via fetchmany).
        """
        if size is None or size <= 0:
            raise CaddixSessionError('func_many() requires size > 0')
        self._execute_func(funcname, True, *args, **kwargs)
        return self.fetchmany(size)

    def func_list(self, funcname: str, *args, **kwargs):
        """
        Executes a PostgreSQL function and returns the first column of all rows as a list.
        """
        self._execute_func(funcname, True, *args, **kwargs)
        return self.fetchlist()

    def func_dict(self, funcname: str, *args, **kwargs):
        """
        Executes a PostgreSQL function returning 2 columns and returns them as a key-value dictionary.
        """
        self._execute_func(funcname, True, *args, **kwargs)
        return self.fetchdict()

    def call_proc(self, procname: str, *args, **kwargs):
        """
        Executes a PostgreSQL stored procedure (CALL procname(...)).
        Returns output/INOUT parameters if any, or None.
        """
        kwargs = self.__kwargs__(kwargs)
        query, params = build_call_proc_query(self.con, procname, *args, **kwargs)
        self.execute(query, **params)
        if self.cur.description:
            return self.fetchone()
        return None

    def call_procedure(self, procname: str, *args, **kwargs):
        """
        Alias for call_proc.
        """
        return self.call_proc(procname, *args, **kwargs)

    # ===== other helpful thinks =====

    def exists(self, tablename: str, **kwargs) -> bool:
        try:
            self._execute_select(tablename, ('*',), **kwargs)
            return self.fetchone() is not None
        except CaddixError as e:
            if isinstance(getattr(e, 'orig', None), psycopg.errors.UndefinedTable):
                try:
                    if not self.con.closed and self.con.info.transaction_status != TransactionStatus.IDLE:
                        self.con.rollback()
                except psycopg.Error:
                    pass
                return False
            raise

    def tabledesc(self, tablename, asdict=False):
        factory = self.cur.row_factory
        try:
            self.cur.row_factory = dict_row
            self.execute("""
                         SELECT f.attname                                                            AS name,
                                pg_catalog.format_type(f.atttypid, f.atttypmod)                      AS type,
                                CASE WHEN f.attlen > -1 THEN f.attlen END                            AS length,
                                f.attnotnull                                                         AS notnull,
                                CASE WHEN p.contype = 'p' THEN true ELSE false END                   AS primarykey,
                                CASE WHEN p.contype = 'u' THEN true ELSE false END                   AS uniquekey,
                                CASE WHEN p.contype = 'f' THEN true ELSE false end                   AS foreignkey,
                                CASE WHEN f.atthasdef = 't' THEN pg_get_expr(d.adbin, d.adrelid) END AS default
                         FROM pg_attribute f
                                  JOIN pg_class c ON c.oid = f.attrelid
                                  JOIN pg_type t ON t.oid = f.atttypid
                                  LEFT JOIN pg_attrdef d ON d.adrelid = c.oid AND d.adnum = f.attnum
                                  LEFT JOIN pg_namespace n ON n.oid = c.relnamespace
                                  LEFT JOIN pg_constraint p ON p.conrelid = c.oid AND f.attnum = ANY (p.conkey)
                                  LEFT JOIN pg_class AS g ON p.confrelid = g.oid
                         WHERE c.relkind = 'r'::char
                           AND concat(n.nspname || '.' || c.relname) in (concat('public.' || %(tablename)s), %(tablename)s)
                           AND f.attnum > 0
                         ORDER BY f.attnum
                         """, tablename=tablename)
            rows = self.fetchall()
        finally:
            self.cur.row_factory = factory

        if asdict:
            return {
                row['name']: {
                    k: row[k] for k in ('type', 'length', 'notnull', 'primarykey', 'uniquekey', 'foreignkey', 'default')
                }
                for row in rows or []
            }
        return rows

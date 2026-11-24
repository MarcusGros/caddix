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
    """Wrap a psycopg execution error; ``orig`` retains the original exception.

    The message uses the server's primary diagnostic when available, otherwise
    the original error text. With ``verbose=True``, it includes the statement,
    parameters and original error instead; these may contain sensitive data.

    :param orig: Original psycopg exception.
    :param stm: Executed statement, or None.
    :param params: Parameters supplied to the failing operation.
    :param verbose: Include statement and parameters in the message.
    """

    def __init__(self, orig: Exception, stm: str | None, params: Any, verbose: bool = False):
        self.orig = orig
        if verbose:
            msg = [
                stm or '', str(params),
                f'{orig.__class__.__name__}: {orig}'
            ]
        else:
            diag = getattr(orig, 'diag', None)
            primary_msg = getattr(diag, 'message_primary', None) if diag else None
            if primary_msg:
                msg = [f'{orig.__class__.__name__}: {primary_msg}']
            elif str(orig):
                msg = [f'{orig.__class__.__name__}: {orig}']
            else:
                msg = [f'{orig.__class__.__name__}']
        super().__init__('\n'.join(msg))


class CaddixSessionError(Exception):
    """Report an invalid session configuration or API argument."""

    pass


class DatabaseSession:
    """Manage a pooled PostgreSQL connection and its cursor.

    The context manager closes the session on exit, even on an exception; it
    does not commit automatically. Commit explicitly to preserve changes.
    Query helpers use the configured row factory unless otherwise documented.
    Keyword column and parameter names with exactly one leading underscore
    have that underscore removed; double-leading underscores are unchanged.

    :param configname: Registered configuration name; defaults to ``default``.
    :param cursor_factory: Optional truthy psycopg row factory override.
    :raises CaddixSessionError: If the configuration is not registered.
    :ivar con: Pooled psycopg connection.
    :ivar cur: Cursor used by this session.
    :ivar cursor_factory: Selected row factory.
    :ivar last_query: Last query recorded by execute/executemany or a failed
        COPY, initially None; successful COPY does not update it.
    """

    def __init__(self, configname='default', cursor_factory=None):
        self.configname = configname
        if configname not in Configs.configs:
            raise CaddixSessionError(
                f"Database configuration '{configname}' not found. Please register it via caddix.Setup(...) first."
            )
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
        """Close the cursor, roll back the open connection and release it.

        Psycopg errors during cursor close or rollback are suppressed. Repeated
        calls do not release the connection again.
        """
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
        """Commit the connection's current transaction; psycopg errors propagate."""
        self.con.commit()

    def rollback(self):
        """Roll back the connection's current transaction; psycopg errors propagate."""
        self.con.rollback()

    def execute(self, query, *args, **kwargs):
        """Execute a psycopg query without fetching or committing.

        :param query: SQL string or psycopg composable.
        :param args: Positional parameters; a single tuple, list or dict is
            passed directly, otherwise the positional arguments form a tuple.
        :param kwargs: Named parameters, used only when no args are supplied.
        :raises CaddixError: If psycopg execution fails; ``orig`` is retained.
        :returns: None. ``last_query`` is updated before execution.
        """
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
        except psycopg.Error as e:
            params = args if args else clean_kwargs
            raise CaddixError(e, self.last_query, params, verbose=self.cnf.get('verbose', False)) from None

    def executemany(self, query, values):
        """Execute a query for each parameter set, without fetching or committing.

        :param query: SQL string or psycopg composable.
        :param values: Parameter sets passed unchanged to psycopg.
        :raises CaddixError: If psycopg execution fails.
        :returns: None. ``last_query`` is updated before execution.
        """
        self.last_query = str(query)
        verbose = self.cnf.get('verbose', False)
        try:
            self.cur.executemany(query, values)
        except psycopg.Error as e:
            raise CaddixError(e, self.last_query, values, verbose=verbose) from None

    # ===== fetch from cursor after executing =====

    def fetchone(self):
        """Fetch the next row, or None if exhausted or no result is available."""
        if not self.cur.description:
            return None
        return self.cur.fetchone()

    def fetchall(self):
        """Fetch all remaining rows, or an empty list if there is no result."""
        if not self.cur.description:
            return []
        return self.cur.fetchall()

    def fetchmany(self, size):
        """Fetch up to ``size`` remaining rows, or [] if there is no result."""
        if not self.cur.description:
            return []
        return self.cur.fetchmany(size)

    def fetchscalar(self):
        """Fetch the first column of the next row, or None if unavailable.

        Temporarily uses psycopg's scalar row factory and restores the previous
        factory even if fetching fails. SQL NULL also yields None.
        """
        if not self.cur.description:
            return None
        factory = self.cur.row_factory
        try:
            self.cur.row_factory = scalar_row
            return self.fetchone()
        finally:
            self.cur.row_factory = factory

    def fetchlist(self):
        """Fetch the first column of remaining rows as a list, or [].

        Temporarily uses tuple rows and restores the previous row factory.
        """
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
        """Fetch remaining two-column rows into a dict, or {}.

        Later duplicate keys overwrite earlier ones. Rows must unpack into two
        values and keys must be hashable. The previous row factory is restored.
        """
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
        """Execute with ``execute`` arguments, then return ``fetchone()``."""
        self.execute(query, *args, **kwargs)
        return self.fetchone()

    def execute_fetchall(self, query, *args, **kwargs):
        """Execute with ``execute`` arguments, then return ``fetchall()``."""
        self.execute(query, *args, **kwargs)
        return self.fetchall()

    def execute_fetchmany(self, query, size, *args, **kwargs):
        """Execute with ``execute`` arguments, then return ``fetchmany(size)``."""
        self.execute(query, *args, **kwargs)
        return self.fetchmany(size)

    def execute_fetchscalar(self, query, *args, **kwargs):
        """Execute with ``execute`` arguments, then return ``fetchscalar()``."""
        self.execute(query, *args, **kwargs)
        return self.fetchscalar()

    def execute_fetchdict(self, query, *args, **kwargs):
        """Execute with ``execute`` arguments, then return ``fetchdict()``."""
        self.execute(query, *args, **kwargs)
        return self.fetchdict()

    def execute_fetchlist(self, query, *args, **kwargs):
        """Execute with ``execute`` arguments, then return ``fetchlist()``."""
        self.execute(query, *args, **kwargs)
        return self.fetchlist()

    def _execute_select(self, tablename: str, columns: Sequence[str] | str = ('*',), **kwargs):
        kwargs = self.__kwargs__(kwargs)
        query, params = build_select_query(con=self.con, tablename=tablename, columns=columns, **kwargs)
        self.execute(query, **params)

    def select_all(self, tablename: str, columns: Sequence[str] | str = ('*',), **kwargs):
        """Select and fetch all matching rows from ``tablename``.

        :param columns: Column names, a comma-separated string, or ``*``.
        :param kwargs: ANDed equality filters; None means IS NULL. No filters
            selects all rows. See the class docstring for underscore handling.
        :returns: Remaining rows as a list, using the configured row factory.
        :raises CaddixError: If query execution fails.
        """
        self._execute_select(tablename, columns=columns, **kwargs)
        return self.fetchall()

    def select_one(self, tablename: str, columns: Sequence[str] | str = ('*',), **kwargs):
        """Select as in ``select_all`` and fetch one row, or None.

        No ordering or SQL LIMIT is added.
        """
        self._execute_select(tablename, columns=columns, **kwargs)
        return self.fetchone()

    def select_scalar(self, tablename: str, column: str, **kwargs):
        """Select ``column`` with ``select_all`` filters; return its first value or None."""
        self._execute_select(tablename, columns=[column], **kwargs)
        return self.fetchscalar()

    def select_many(self, tablename: str, size: int, columns: Sequence[str] | str = ('*',), **kwargs):
        """Select as in ``select_all`` and fetch up to ``size`` rows.

        :raises CaddixSessionError: If size is None or not positive.
        No SQL LIMIT or ordering is added.
        """
        if size is None or size <= 0:
            raise CaddixSessionError('select_many() requires size > 0')
        self._execute_select(tablename, columns=columns, **kwargs)
        return self.fetchmany(size)

    def select_list(self, tablename: str, column: str, **kwargs):
        """Select ``column`` with ``select_all`` filters and return its values as a list."""
        self._execute_select(tablename, columns=[column], **kwargs)
        return self.fetchlist()

    def select_dict(self, tablename: str, column_key: str, column_value: str, **kwargs):
        """Select two columns with ``select_all`` filters and return a dict.

        Duplicate keys overwrite earlier values; keys must be hashable.
        """
        self._execute_select(tablename, columns=[column_key, column_value], **kwargs)
        return self.fetchdict()

    # ===== for easy data-manipulation =====

    def insert(self, tablename: str, returning=None, **kwargs):
        """Insert one row from keyword column values.

        :param tablename: Table name, optionally schema-qualified.
        :param returning: Column names or ``*`` for RETURNING; falsy disables it.
        :param kwargs: Column values; see class docstring for underscore handling.
        :returns: One returned row if requested, otherwise None.
        :raises CaddixError: If execution fails. No commit is performed.
        """
        kwargs = self.__kwargs__(kwargs)
        query, safe_params = build_insert_query(self.con, tablename, kwargs, returning=returning)
        self.execute(query, **safe_params)
        if returning:
            return self.fetchone()
        return None

    def update(self, tablename: str, values: dict[str, Any] | None = None, returning=None, check_changes: bool = False, **kwargs):
        """Update rows using ``values`` and keyword equality filters.

        None filter values mean IS NULL; without filters all rows may be
        updated. With ``check_changes``, only rows distinct from at least one
        supplied value are updated. ``returning`` selects returned columns.

        :returns: Returned rows when requested, otherwise None; if ``values``
            is empty, no query runs and [] or 0 is returned respectively.
        :raises CaddixError: If execution fails. No commit is performed.
        """
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
        """Delete rows matching keyword equality filters (None means IS NULL).

        :param returning: Column names or ``*`` to fetch deleted rows.
        :param allow_all: Permit deletion without filters when true.
        :returns: Returned rows if requested, otherwise None; does not commit.
        :raises CaddixSessionError: If no filters are given and allow_all is false.
        :raises CaddixError: If execution fails.
        """
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
        """Insert mappings from ``values`` using first-row keys as columns.

        Without ``returning``, COPY is used; missing keys become None and extra
        keys are ignored. With ``returning``, psycopg ``executemany`` is used
        and then ``fetchall`` is called; result availability depends on psycopg.
        :returns: 0 for empty input, COPY rowcount without returning, otherwise
            the fetched rows. No commit is performed.
        :raises CaddixError: If COPY or execution raises a psycopg error.
        """
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

            try:
                with self.cur.copy(sql_copy) as copy:
                    for row in clean_values:
                        copy.write_row([row.get(col) for col in columns])
            except psycopg.Error as e:
                self.last_query = str(sql_copy)
                verbose = self.cnf.get('verbose', False)
                raise CaddixError(e, self.last_query, values, verbose=verbose) from None

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
        """Execute an update for each mapping in ``values``.

        Column arguments accept sequences or comma-separated strings;
        ``update_columns='*'`` derives columns from the first row excluding
        ``where_columns``. WHERE comparisons use SQL equality, including for
        None. ``check_changes`` adds IS DISTINCT FROM checks.

        :returns: 0 for empty input, otherwise cursor rowcount or, with
            ``returning``, the result of ``fetchall`` after ``executemany``.
            Result availability depends on psycopg; no commit is performed.
        :raises CaddixSessionError: If a specified column is absent from the first row.
        :raises CaddixError: If execution fails.
        """
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
        """Execute INSERT ON CONFLICT for each mapping in ``values``.

        Columns come from the first row. ``conflict_target`` is a fallback for
        ``conflict_columns`` when the latter is None. Column lists may be
        sequences or comma-separated strings. ``update_columns='*'`` updates
        non-conflict columns; None, '' or [] selects DO NOTHING. With
        ``check_changes``, updates require a distinct value.

        :returns: 0 for empty input, otherwise cursor rowcount or, with
            ``returning``, ``fetchall`` after ``executemany``. Result
            availability depends on psycopg; no commit is performed.
        :raises CaddixSessionError: If conflict columns are missing for nonempty input.
        :raises CaddixError: If execution fails.
        """
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
        """Call ``funcname`` via SELECT * FROM and fetch all rows.

        Positional and keyword arguments become positional and named PostgreSQL
        arguments, respectively; keyword names follow class underscore rules.
        :raises CaddixError: If execution fails. No commit is performed.
        """
        return self.func_all(funcname, *args, **kwargs)

    def call_function(self, funcname: str, *args, **kwargs):
        """Alias for ``call_func`` with the same arguments and result."""
        return self.call_func(funcname, *args, **kwargs)

    def _execute_func(self, funcname: str, as_table: bool, *args, **kwargs):
        kwargs = self.__kwargs__(kwargs)
        query, params = build_call_func_query(self.con, funcname, as_table, *args, **kwargs)
        self.execute(query, **params)

    def func_all(self, funcname: str, *args, **kwargs):
        """Call as in ``call_func`` and return all rows via ``fetchall``."""
        self._execute_func(funcname, True, *args, **kwargs)
        return self.fetchall()

    def func_one(self, funcname: str, *args, **kwargs):
        """Call as in ``call_func`` and return the first row, or None."""
        self._execute_func(funcname, True, *args, **kwargs)
        return self.fetchone()

    def func_scalar(self, funcname: str, *args, **kwargs):
        """Call via SELECT funcname(...) and return its first scalar value or None.

        Arguments are handled as in ``call_func``.
        """
        self._execute_func(funcname, False, *args, **kwargs)
        return self.fetchscalar()

    def func_many(self, funcname: str, size: int, *args, **kwargs):
        """Call as in ``call_func`` and fetch up to ``size`` rows.

        :raises CaddixSessionError: If size is None or not positive.
        """
        if size is None or size <= 0:
            raise CaddixSessionError('func_many() requires size > 0')
        self._execute_func(funcname, True, *args, **kwargs)
        return self.fetchmany(size)

    def func_list(self, funcname: str, *args, **kwargs):
        """Call as in ``call_func`` and return the first column as a list."""
        self._execute_func(funcname, True, *args, **kwargs)
        return self.fetchlist()

    def func_dict(self, funcname: str, *args, **kwargs):
        """Call as in ``call_func`` and convert two-column rows using ``fetchdict``."""
        self._execute_func(funcname, True, *args, **kwargs)
        return self.fetchdict()

    def call_proc(self, procname: str, *args, **kwargs):
        """Execute CALL for ``procname`` with arguments as in ``call_func``.

        :returns: The first result row if the cursor has a description,
            otherwise None. No commit is performed.
        :raises CaddixError: If execution fails.
        """
        kwargs = self.__kwargs__(kwargs)
        query, params = build_call_proc_query(self.con, procname, *args, **kwargs)
        self.execute(query, **params)
        if self.cur.description:
            return self.fetchone()
        return None

    def call_procedure(self, procname: str, *args, **kwargs):
        """Alias for ``call_proc`` with the same arguments and result."""
        return self.call_proc(procname, *args, **kwargs)

    # ===== other helpful thinks =====

    def exists(self, tablename: str, **kwargs) -> bool:
        """Return whether a row matches the ``select_all`` equality filters.

        An undefined table returns False and attempts to roll back any active
        transaction, potentially discarding unrelated uncommitted changes.
        Other execution errors propagate as ``CaddixError``.
        """
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
        """Read PostgreSQL catalog metadata for an ordinary table's columns.

        :param tablename: A schema-qualified name, or an unqualified public name.
        :param asdict: Return metadata keyed by column name instead of rows.
        :returns: Dict rows with name, type, length, notnull, primarykey,
            uniquekey, foreignkey and default; or a dict keyed by name with
            those fields except name. No matches yield [] or {}. Catalog joins
            can produce multiple rows per column; dict mode keeps the last.
        :raises CaddixError: If the catalog query fails.
        """
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

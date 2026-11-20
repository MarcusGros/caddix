from typing import Any, Sequence
from psycopg import sql


def _sql_table(tablename: str) -> sql.Identifier:
    return sql.Identifier(*tablename.split('.')) if '.' in tablename else sql.Identifier(tablename)


def _sql_returning(returning: Any) -> sql.Composable | None:
    if not returning:
        return None
    if isinstance(returning, str):
        if returning.strip() == '*':
            return sql.SQL('*')
        if ',' in returning:
            return sql.SQL(', ').join(sql.Identifier(c.strip()) for c in returning.split(',') if c.strip())
        return sql.Identifier(returning.strip())
    if isinstance(returning, (list, tuple, set)):
        items = list(returning)
        if len(items) == 1 and items[0] == '*':
            return sql.SQL('*')
        return sql.SQL(', ').join(sql.Identifier(str(c)) for c in items)
    return sql.Identifier(str(returning))


def build_where_clause(kwargs: dict[str, Any], prefix: str = 'w') -> tuple[sql.Composable | None, dict[str, Any]]:
    if not kwargs:
        return None, {}
    where_items = []
    safe_params = {}
    for i, (col, val) in enumerate(kwargs.items()):
        if val is None:
            where_items.append(sql.SQL("{} IS NULL").format(sql.Identifier(col)))
        else:
            safe_key = f"{prefix}{i}"
            safe_params[safe_key] = val
            where_items.append(sql.SQL("{} = %({})s").format(sql.Identifier(col), sql.SQL(safe_key)))
    return sql.SQL(' AND ').join(where_items), safe_params


def build_set_clause(values: dict[str, Any], prefix: str = 's') -> tuple[sql.Composable | None, dict[str, Any]]:
    if not values:
        return None, {}
    set_items = []
    safe_params = {}
    for i, (col, val) in enumerate(values.items()):
        safe_key = f"{prefix}{i}"
        safe_params[safe_key] = val
        set_items.append(sql.SQL("{} = %({})s").format(sql.Identifier(col), sql.SQL(safe_key)))
    return sql.SQL(', ').join(set_items), safe_params


def get_column_names(db, tablename: str) -> list[str]:
    parts = tablename.split('.', 1)
    if len(parts) == 2:
        schema, table = parts
        res = db.execute_fetchall(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = %(schema)s
              AND table_name = %(table)s
            ORDER BY ordinal_position
            """,
            schema=schema,
            table=table
        )
    else:
        table = parts[0]
        res = db.execute_fetchall(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE concat(table_schema || '.' || table_name) IN (concat('public.' || %(table)s), %(table)s)
               OR table_name = %(table)s
            ORDER BY ordinal_position
            """,
            table=table
        )
    if not res:
        return []
    if isinstance(res[0], dict):
        return [r['column_name'] for r in res]
    return [r[0] for r in res]


def simple_where_builder(**kwargs) -> str:
    if not kwargs:
        return ''
    tmp = []
    for k, v in kwargs.items():
        if v is None:
            tmp.append(f'"{k}" IS NULL')
        else:
            tmp.append(f'"{k}"=%({k})s')
    return 'WHERE ' + ' AND '.join(tmp)


def simple_query_builder(tablename: str, columns: Sequence[str] | str | None = None, **kwargs) -> str:
    if columns is None or columns == ['*'] or columns == ('*',) or columns == '*':
        cols_str = '*'
    elif isinstance(columns, str):
        cols_str = columns
    else:
        cols_str = ', '.join(f'"{c}"' if c != '*' else '*' for c in columns)

    if '.' in tablename:
        table_str = '.'.join(f'"{part}"' for part in tablename.split('.'))
    else:
        table_str = f'"{tablename}"'

    query = [f"SELECT {cols_str} FROM {table_str}"]
    if kwargs:
        where_clause = simple_where_builder(**kwargs)
        if where_clause:
            query.append(where_clause)
    return ' '.join(query)


def build_call_func_query(con, funcname: str, as_table: bool = True, *args, **kwargs):
    fn_sql = _sql_table(funcname)
    arg_items = []
    safe_params = {}

    for i, val in enumerate(args):
        safe_key = f"a{i}"
        safe_params[safe_key] = val
        arg_items.append(sql.SQL("%({})s").format(sql.SQL(safe_key)))

    for i, (k, val) in enumerate(kwargs.items()):
        safe_key = f"kw{i}"
        safe_params[safe_key] = val
        arg_items.append(sql.SQL("{} => %({})s").format(sql.Identifier(k), sql.SQL(safe_key)))

    args_sql = sql.SQL(', ').join(arg_items)
    if as_table:
        query = sql.SQL("SELECT * FROM {fn}({args})").format(fn=fn_sql, args=args_sql)
    else:
        query = sql.SQL("SELECT {fn}({args})").format(fn=fn_sql, args=args_sql)

    return query.as_string(con), safe_params


def build_call_proc_query(con, procname: str, *args, **kwargs):
    proc_sql = _sql_table(procname)
    arg_items = []
    safe_params = {}

    for i, val in enumerate(args):
        safe_key = f"a{i}"
        safe_params[safe_key] = val
        arg_items.append(sql.SQL("%({})s").format(sql.SQL(safe_key)))

    for i, (k, val) in enumerate(kwargs.items()):
        safe_key = f"kw{i}"
        safe_params[safe_key] = val
        arg_items.append(sql.SQL("{} => %({})s").format(sql.Identifier(k), sql.SQL(safe_key)))

    args_sql = sql.SQL(', ').join(arg_items)
    query = sql.SQL("CALL {proc}({args})").format(proc=proc_sql, args=args_sql)

    return query.as_string(con), safe_params


def build_select_query(con, tablename: str, columns: Sequence[str] | str | None = None, **kwargs):
    if columns is None or columns == ['*'] or columns == ('*',) or columns == '*':
        cols_sql = sql.SQL('*')
    elif isinstance(columns, str):
        if ',' in columns:
            cols_sql = sql.SQL(', ').join(sql.Identifier(c.strip()) for c in columns.split(',') if c.strip())
        else:
            cols_sql = sql.Identifier(columns.strip())
    elif isinstance(columns, (list, tuple, set)):
        items = list(columns)
        if len(items) == 1 and items[0] == '*':
            cols_sql = sql.SQL('*')
        else:
            cols_sql = sql.SQL(', ').join(map(sql.Identifier, items))
    else:
        cols_sql = sql.SQL('*')

    query = sql.SQL("SELECT {cols} FROM {table}").format(
        cols=cols_sql,
        table=_sql_table(tablename)
    )

    where_clause, safe_params = build_where_clause(kwargs, prefix='w')
    if where_clause:
        query += sql.SQL(" WHERE ") + where_clause

    return query.as_string(con), safe_params


def build_insert_query(con, tablename, values: dict, returning=None):
    safe_params = {}
    columns_sql = []
    values_sql = []

    for i, (k, v) in enumerate(values.items()):
        safe_key = f"p{i}"
        safe_params[safe_key] = v
        columns_sql.append(sql.Identifier(k))
        values_sql.append(sql.SQL("%({})s").format(sql.SQL(safe_key)))

    query = sql.SQL("INSERT INTO {table} ({cols}) VALUES ({vals})").format(
        table=_sql_table(tablename),
        cols=sql.SQL(', ').join(columns_sql),
        vals=sql.SQL(', ').join(values_sql)
    )

    ret_sql = _sql_returning(returning)
    if ret_sql:
        query += sql.SQL(" RETURNING ") + ret_sql

    return query.as_string(con), safe_params


def build_update_query(con, tablename, values: dict, returning=None, check_changes: bool = False, **kwargs):
    set_clause, set_params = build_set_clause(values, prefix='s')
    if not set_clause:
        return None, {}, False

    where_clause, where_params = build_where_clause(kwargs, prefix='w')
    safe_params = {**set_params, **where_params}

    query = sql.SQL("UPDATE {table} SET {set_clause}").format(
        table=_sql_table(tablename),
        set_clause=set_clause
    )

    where_conditions = []
    if where_clause:
        where_conditions.append(where_clause)

    if check_changes:
        distinct_items = [
            sql.SQL("{} IS DISTINCT FROM %({})s").format(sql.Identifier(col), sql.SQL(f"s{i}"))
            for i, col in enumerate(values.keys())
        ]
        if distinct_items:
            where_conditions.append(sql.SQL("(") + sql.SQL(" OR ").join(distinct_items) + sql.SQL(")"))

    if where_conditions:
        query += sql.SQL(" WHERE ") + sql.SQL(" AND ").join(where_conditions)

    ret_sql = _sql_returning(returning)
    if ret_sql:
        query += sql.SQL(" RETURNING ") + ret_sql

    return query.as_string(con), safe_params, True


def build_delete_query(con, tablename, returning=None, **kwargs):
    query = sql.SQL("DELETE FROM {table}").format(table=_sql_table(tablename))

    where_clause, safe_params = build_where_clause(kwargs, prefix='w')
    if where_clause:
        query += sql.SQL(" WHERE ") + where_clause

    ret_sql = _sql_returning(returning)
    if ret_sql:
        query += sql.SQL(" RETURNING ") + ret_sql

    return query.as_string(con), safe_params


def build_update_batch_query(con, tablename, update_columns, where_columns, returning=None, check_changes: bool = False):
    set_clause = sql.SQL(', ').join(
        [sql.SQL("{} = %({})s").format(sql.Identifier(col), sql.SQL(col)) for col in update_columns]
    )

    where_items = [sql.SQL("{} = %({})s").format(sql.Identifier(col), sql.SQL(col)) for col in where_columns]

    if check_changes:
        distinct_items = [
            sql.SQL("{} IS DISTINCT FROM %({})s").format(sql.Identifier(col), sql.SQL(col))
            for col in update_columns
        ]
        if distinct_items:
            where_items.append(sql.SQL("(") + sql.SQL(" OR ").join(distinct_items) + sql.SQL(")"))

    where_clause = sql.SQL(' AND ').join(where_items)

    query = sql.SQL("UPDATE {table} SET {set_clause} WHERE {where_clause}").format(
        table=_sql_table(tablename),
        set_clause=set_clause,
        where_clause=where_clause
    )

    ret_sql = _sql_returning(returning)
    if ret_sql:
        query += sql.SQL(" RETURNING ") + ret_sql

    return query.as_string(con)


def build_upsert_batch_query(con, tablename, columns, conflict_columns, update_columns='*', returning=None, check_changes: bool = False):
    cols_sql = sql.SQL(', ').join(map(sql.Identifier, columns))
    vals_sql = sql.SQL(', ').join(map(lambda c: sql.SQL("%({})s").format(sql.SQL(c)), columns))
    conflict_sql = sql.SQL(', ').join(map(sql.Identifier, conflict_columns))

    if update_columns is None or update_columns == '' or update_columns == []:
        action_sql = sql.SQL("DO NOTHING")
    else:
        if update_columns == '*' or (isinstance(update_columns, (list, tuple)) and len(update_columns) == 1 and update_columns[0] == '*'):
            target_update_columns = [col for col in columns if col not in conflict_columns]
        elif isinstance(update_columns, str):
            target_update_columns = [c.strip() for c in update_columns.split(',') if c.strip()]
        else:
            target_update_columns = list(update_columns)

        set_clause = sql.SQL(', ').join(
            [sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(col), sql.Identifier(col)) for col in target_update_columns]
        )
        if check_changes and target_update_columns:
            distinct_items = [
                sql.SQL("{table}.{col} IS DISTINCT FROM EXCLUDED.{col}").format(
                    table=_sql_table(tablename),
                    col=sql.Identifier(col)
                )
                for col in target_update_columns
            ]
            where_clause = sql.SQL(" WHERE (") + sql.SQL(" OR ").join(distinct_items) + sql.SQL(")")
            action_sql = sql.SQL("DO UPDATE SET {set_clause}{where_clause}").format(
                set_clause=set_clause,
                where_clause=where_clause
            )
        else:
            action_sql = sql.SQL("DO UPDATE SET {set_clause}").format(set_clause=set_clause)

    query = sql.SQL("INSERT INTO {table} ({cols}) VALUES ({vals}) ON CONFLICT ({conf}) {action}").format(
        table=_sql_table(tablename),
        cols=cols_sql,
        vals=vals_sql,
        conf=conflict_sql,
        action=action_sql
    )

    ret_sql = _sql_returning(returning)
    if ret_sql:
        query += sql.SQL(" RETURNING ") + ret_sql

    return query.as_string(con)

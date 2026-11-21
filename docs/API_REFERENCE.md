# Caddix - API Reference

Complete technical documentation of classes, methods, parameters, and exceptions provided by the `caddix` package.

---

## Table of Contents
- [1. Configuration: `caddix.Setup` / `Configs`](#1-configuration-caddixsetup--configs)
- [2. Connection Pool: `caddix.PGPool`](#2-connection-pool-caddixpgpool)
- [3. Session Management: `caddix.DatabaseSession`](#3-session-management-caddixdatabasesession)
  - [Initialization & Context Management](#initialization--context-management)
  - [Transactions](#transactions)
  - [Query Execution](#query-execution)
  - [Fetch Methods](#fetch-methods)
  - [Combined Execute & Fetch Methods](#combined-execute--fetch-methods)
  - [SQL-Free SELECT API](#sql-free-select-api)
  - [CRUD Methods (Insert, Update, Delete)](#crud-methods-insert-update-delete)
  - [Batch & Bulk Ingestion Methods](#batch--bulk-ingestion-methods)
  - [Functions & Stored Procedures](#functions--stored-procedures)
  - [Introspection & Utility Methods](#introspection--utility-methods)
- [4. Row Factories](#4-row-factories)
- [5. Exceptions](#5-exceptions)

---

## 1. Configuration: `caddix.Setup` / `Configs`

Class used to register and store PostgreSQL connection profiles.

```python
caddix.Setup(
    databasename: str,
    username: str,
    password: str,
    hostname: str,
    port: int = 5432,
    name: str = 'default',
    connect_timeout: int = 10,
    verbose: bool = True,
    application_name: str = 'python',
    ttl: int = 10,
    max_connections: int = 10,
    default_rowfactory: callable = dict_row
)
```

### Parameters:
- `databasename` *(str, required)*: Name of the PostgreSQL database.
- `username` *(str, required)*: Username for authentication.
- `password` *(str, required)*: Password for authentication.
- `hostname` *(str, required)*: Hostname or IP address of the database server.
- `port` *(int, optional)*: Port number of the PostgreSQL server. Default: `5432`.
- `name` *(str, optional)*: Unique identifier for this configuration profile. Default: `'default'`.
- `connect_timeout` *(int, optional)*: Connection timeout in seconds. Default: `10`.
- `verbose` *(bool, optional)*: When `True`, detailed SQL statements and parameters are included in error messages. Default: `True`.
- `application_name` *(str, optional)*: Application name reported to PostgreSQL logs and `pg_stat_activity`. Default: `'python'`.
- `ttl` *(int, optional)*: Time-to-Live for pooled connections in seconds. Expired connections are automatically reconnected. Default: `10`.
- `max_connections` *(int, optional)*: Maximum number of pooled connections. Default: `10`.
- `default_rowfactory` *(callable, optional)*: Default row factory for cursors (e.g. `dict_row`, `tuple_row`). Default: `dict_row`.

---

## 2. Connection Pool: `caddix.PGPool`

Manages connection pools associated with registered configuration profile names (`configname`).

```python
pool = caddix.PGPool(configname='default')
```

### Attributes & Methods:
- `configname`: Name of the configuration profile in use.
- `con`: The active `psycopg.Connection` instance.
- `expire`: Timestamp (`time.time()`) when the connection expires.
- `single_connect()`: Creates and returns a new unpooled standalone connection.
- Context Manager (`__enter__` / `__exit__`): Automatically checks in connection back into the queue upon exiting the block.

---

## 3. Session Management: `caddix.DatabaseSession`

The core interface for executing queries, database transactions, and data manipulation.

### Initialization & Context Management

```python
with caddix.DatabaseSession(configname='default', cursor_factory=None) as db:
    ...
```

- `configname` *(str, optional)*: Configuration profile name (from `Setup`). Default: `'default'`.
- `cursor_factory` *(callable, optional)*: Overrides the default row factory for this session.
- **Context Behavior**: On normal exit or unhandled exception, `con.rollback()` is automatically invoked. To persist changes, call `db.commit()` explicitly before leaving the context block.

---

### Transactions

#### `commit()`
Commits all changes in the current transaction to the database.
```python
db.commit()
```

---

### Query Execution

#### `execute(query: str, **kwargs)`
Executes a single parameterized SQL statement.
- `query` *(str)*: SQL query containing named placeholders (e.g. `%(user_id)s`).
- `**kwargs`: Parameter key-value pairs matching placeholders.
- *Error:* Raises `CaddixError` on SQL or database failure.

```python
db.execute("SELECT * FROM users WHERE active = %(active)s", active=True)
```

#### `executemany(query: str, values: list[dict])`
Executes a parameterized SQL statement across multiple parameter dictionaries.
- `query` *(str)*: SQL query string.
- `values` *(list[dict])*: List of parameter dictionaries.

```python
db.executemany(
    "INSERT INTO tags (name) VALUES (%(name)s)",
    [{'name': 'python'}, {'name': 'postgresql'}]
)
```

---

### Fetch Methods

Retrieve results after executing a query with `execute()`:

| Method | Return Type | Description |
|---|---|---|
| `fetchone()` | `dict` / Row Type / `None` | Returns the next row from the cursor or `None`. |
| `fetchall()` | `list` | Returns all remaining rows as a list. |
| `fetchmany(size: int)` | `list` | Returns up to `size` rows as a list. |
| `fetchscalar()` | `Any` | Returns the scalar value from the first column of the first row. |
| `fetchlist()` | `list[Any]` | Returns a flat list containing the first column from all rows. |
| `fetchdict()` | `dict[Any, Any]` | Returns a dictionary mapping column 1 (key) to column 2 (value). |

---

### Combined Execute & Fetch Methods

Convenience methods combining `execute()` and the respective fetch operation in a single call:

- `execute_fetchone(query, **kwargs)` -> Single row or `None`
- `execute_fetchall(query, **kwargs)` -> List of all rows
- `execute_fetchmany(query, size, **kwargs)` -> List of `size` rows
- `execute_fetchscalar(query, **kwargs)` -> Single scalar value
- `execute_fetchlist(query, **kwargs)` -> Flat list of column 1 values
- `execute_fetchdict(query, **kwargs)` -> Dictionary (column 1 -> column 2)

```python
user = db.execute_fetchone("SELECT * FROM users WHERE id = %(id)s", id=42)
count = db.execute_fetchscalar("SELECT COUNT(*) FROM users")
emails = db.execute_fetchlist("SELECT email FROM users WHERE active = %(active)s", active=True)
id_to_name = db.execute_fetchdict("SELECT id, name FROM users")
```

---

### SQL-Free SELECT API

Automatically builds and executes secure SELECT queries using `psycopg.sql.Identifier`:

#### `select_all(tablename, columns=['*'], **kwargs)`
Returns all rows matching the WHERE conditions.
```python
users = db.select_all('users', columns=['id', 'name'], active=True)
```

#### `select_one(tablename, columns=['*'], **kwargs)`
Returns the first matching row or `None`.
```python
user = db.select_one('users', id=1)
```

#### `select_many(tablename, size, columns=['*'], **kwargs)`
Returns up to `size` matching rows.
```python
top_users = db.select_many('users', 5, active=True)
```

#### `select_scalar(tablename, column, **kwargs)`
Returns a single scalar value of the specified column for one matching row.
```python
email = db.select_scalar('users', 'email', id=1)
```

#### `select_list(tablename, column, **kwargs)`
Returns all values of the specified column across matching rows as a list.
```python
emails = db.select_list('users', 'email', active=True)
```

#### `select_dict(tablename, column_key, column_value, **kwargs)`
Returns a dictionary mapping `column_key` to `column_value`.
```python
user_map = db.select_dict('users', 'id', 'email')
```

---

### CRUD Methods (Insert, Update, Delete)

#### `insert(tablename: str, returning: str = None, **kwargs)`
Inserts a single row.
- `returning`: Optional column expression for `RETURNING` (e.g. `'id'` or `'*'`).
- Returns the inserted row if `returning` is provided, otherwise `None`.
```python
new_id = db.insert('users', returning='id', name='Alice', email='alice@example.com')
db.commit()
```

#### `update(tablename: str, values: dict, returning: str = None, **kwargs)`
Updates rows matching the WHERE conditions in `**kwargs`.
- `values`: Dictionary of columns and new values to update.
- `returning`: Optional `RETURNING` expression.
- Returns list of updated rows if `returning` is provided, otherwise `None`.
```python
db.update('users', values={'active': False}, role='guest')
db.commit()
```

#### `delete(tablename: str, returning: str = None, allow_all: bool = False, **kwargs)`
Deletes rows matching the WHERE conditions in `**kwargs`.
- `returning`: Optional `RETURNING` expression.
- `allow_all`: Safety flag. Must be set to `True` to intentionally delete all rows when no WHERE conditions (`**kwargs`) are provided. Raises `CaddixSessionError` if omitted when deleting without conditions.
- Returns list of deleted rows if `returning` is provided, otherwise `None`.
```python
# Delete specific rows
db.delete('users', id=42)
db.commit()

# Delete all rows (requires allow_all=True)
db.delete('temp_logs', allow_all=True)
db.commit()
```

---

### Batch & Bulk Ingestion Methods

High-performance bulk operations for large datasets.

#### `insert_batch(tablename: str, values: list[dict], returning: str = None) -> int | list`
Inserts multiple rows in a batch.
- **Without `returning`**: Uses PostgreSQL's high-speed `COPY FROM STDIN` streaming protocol. Returns the count of inserted rows (`rowcount`).
- **With `returning`**: Uses parameterized `executemany` with `INSERT ... RETURNING` and returns the list of result rows.

```python
rows = [
    {'name': 'User 1', 'email': 'u1@example.com'},
    {'name': 'User 2', 'email': 'u2@example.com'}
]
count = db.insert_batch('users', rows)
db.commit()
```

#### `update_batch(tablename: str, values: list[dict], update_columns: list[str] | str, where_columns: list[str], returning: str = None) -> int | list`
Updates multiple rows in a batch.
- `update_columns`: List of columns to update or `'*'` for all columns except the WHERE keys.
- `where_columns`: List of columns used in the WHERE condition (e.g. `['id']`).
```python
updates = [
    {'id': 1, 'score': 100},
    {'id': 2, 'score': 150}
]
db.update_batch('users', updates, update_columns=['score'], where_columns=['id'])
db.commit()
```

#### `upsert_batch(tablename: str, values: list[dict], conflict_columns: list[str], update_columns: list[str] | str = '*', returning: str = None) -> int | list`
Inserts rows or updates existing rows upon key conflict (`INSERT ... ON CONFLICT (...) DO UPDATE SET ...`).
- `conflict_columns`: List of unique/primary key columns defining the conflict target.
- `update_columns`: Columns to update upon conflict or `'*'` for all other columns.
```python
users = [
    {'id': 1, 'name': 'Updated Alice', 'email': 'alice@example.com'},
    {'id': 2, 'name': 'New Bob', 'email': 'bob@example.com'}
]
db.upsert_batch('users', users, conflict_columns=['id'], update_columns=['name', 'email'])
db.commit()
```

---

### Functions & Stored Procedures

Caddix supports native and safe execution of PostgreSQL stored functions and procedures with positional and named arguments (`name => value`), schema prefixes, and automatic parameter sanitization.

#### `call_func(funcname: str, *args, **kwargs) -> list`
*Alias:* `call_function`  
Executes a PostgreSQL stored function (`SELECT * FROM funcname(...)`) and returns all rows.
```python
users = db.call_func('get_active_users', min_rank=2)
```

#### `func_all(funcname: str, *args, **kwargs) -> list`
Executes a function and returns all result rows as a list.
```python
users = db.func_all('get_active_users', min_rank=2)
```

#### `func_one(funcname: str, *args, **kwargs) -> dict | tuple | None`
Executes a function and returns a single row.
```python
user = db.func_one('get_user_profile', user_id=42)
```

#### `func_scalar(funcname: str, *args, **kwargs) -> Any`
Executes a scalar function (`SELECT funcname(...)`) and returns the scalar value.
```python
total = db.func_scalar('calculate_sum', 10, 25)  # 35
```

#### `func_many(funcname: str, size: int, *args, **kwargs) -> list`
Executes a function and returns up to `size` rows.
```python
batch = db.func_many('get_events', 100, status='PENDING')
```

#### `func_list(funcname: str, *args, **kwargs) -> list`
Executes a function and extracts the first column of all result rows into a flat list.
```python
ids = db.func_list('get_active_ids')  # [1, 2, 3]
```

#### `func_dict(funcname: str, *args, **kwargs) -> dict`
Executes a 2-column function and converts the results into a key-value dictionary.
```python
settings = db.func_dict('get_settings', category='network')  # {'port': 8080, 'host': '0.0.0.0'}
```

#### `call_proc(procname: str, *args, **kwargs) -> dict | None`
*Alias:* `call_procedure`  
Executes a PostgreSQL stored procedure (`CALL procname(...)`).
- Returns `None` if the procedure has no `OUT` parameters.
- Returns a dictionary of output values if `OUT`/`INOUT` parameters are present.
```python
# 1. Procedure without return values (data modification, commit required)
db.call_proc('cleanup_expired_tokens')
db.commit()

# 2. Procedure with OUT parameters
res = db.call_proc('calculate_stats', 5, 10, None, None)  # {'sum': 15, 'prod': 50}
```

---

### Introspection & Utility Methods

#### `exists(tablename: str, **kwargs) -> bool`
Efficiently tests whether at least one row matches the given conditions.
```python
if db.exists('users', email='alice@example.com'):
    print("User already exists")
```

#### `tabledesc(tablename: str, asdict: bool = False) -> list | dict`
Retrieves column metadata for a table directly from PostgreSQL system catalogs.
- Provides column name, type, length, nullability, primary key, unique constraint, foreign key, and default values.
- `asdict=True`: Returns a dictionary indexed by column names.
- `asdict=False`: Returns a list of column metadata dictionaries.

```python
desc = db.tabledesc('users', asdict=True)
print(desc['email']['type'])        # e.g. 'character varying(255)'
print(desc['id']['primarykey'])     # True
```

#### `DatabaseSession.__kwargs__(kwargs: dict) -> dict`
Static helper method: Strips leading underscores from parameter keys, allowing Python reserved keywords to be used safely as SQL column names (e.g. `_from` -> `from`, `_class` -> `class`).

---

## 4. Row Factories

Caddix re-exports row factories from `psycopg.rows`:

- `dict_row`: Rows as dictionaries (`{'col1': val1, 'col2': val2}`). *(Default)*
- `tuple_row`: Rows as standard tuples (`(val1, val2)`).
- `scalar_row`: Single scalar value from the first column.
- `class_row(cls)`: Automatically maps result columns to attributes of a class or `@dataclass`.
- `namedtuple_row`: Rows as named tuples (`Row(col1=val1, col2=val2)`).

```python
with caddix.DatabaseSession(cursor_factory=caddix.namedtuple_row) as db:
    user = db.select_one('users', id=1)
    print(user.name, user.email)
```

---

## 5. Exceptions

- `CaddixError(orig: Exception, stm: str, params: dict)`:
  Raised when an executed SQL statement encounters a database or driver error. Contains the original exception, the executed query string, and the parameter values.
- `CaddixSessionError`:
  Raised for logical or operational errors in session usage (e.g. missing required keys in batch updates or invalid arguments).

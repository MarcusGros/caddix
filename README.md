```
                 _     _ _      
  ___ __ _  __| | __| (_)_  __
 / __/ _` |/ _` |/ _` | \ \/ /
| (_| (_| | (_| | (_| | |>  < 
 \___\__,_|\__,_|\__,_|_/_/\_\
```

# Caddix - PostgreSQL Connection Assistant 

**Caddix** is a lightweight, high-performance Python helper library built on top of [psycopg 3](https://www.psycopg.org/psycopg3/docs/) designed to make interacting with PostgreSQL databases easier, faster, and safer.

This document serves as the **complete and self-contained User Manual** for caddix. It covers everything from installation and basic configuration to advanced bulk operations, custom object mapping, and real-world patterns.

---

## 📑 Table of Contents

1. [Key Features & Advantages](#-key-features--advantages)
2. [Installation & Requirements](#-installation--requirements)
3. [Quickstart Guide](#-quickstart-guide)
4. [Configuration Management (`caddix.Setup`)](#-configuration-management-caddixsetup)
   - [Basic Setup](#basic-setup)
   - [Managing Multiple Databases](#managing-multiple-databases)
   - [Configuration Parameters](#configuration-parameters)
5. [Connection Pool (`caddix.PGPool`)](#-connection-pool-caddixpgpool)
6. [Database Sessions & Transactions (`caddix.DatabaseSession`)](#-database-sessions--transactions-caddixdatabasesession)
   - [Context Manager & Rollback-by-Default](#context-manager--rollback-by-default)
   - [Committing Transactions](#committing-transactions)
   - [Explicit / Non-Context Usage](#explicit--non-context-usage)
7. [Executing Raw SQL Queries](#-executing-raw-sql-queries)
   - [Parameterized Execution (`execute`, `executemany`)](#parameterized-execution-execute-executemany)
   - [Cursor Fetch Methods](#cursor-fetch-methods)
   - [Combined Execute & Fetch Helpers](#combined-execute--fetch-helpers)
8. [SQL-Free Query Helpers (SELECT API)](#-sql-free-query-helpers-select-api)
   - [Selecting Rows (`select_all`, `select_one`, `select_many`)](#selecting-rows-select_all-select_one-select_many)
   - [Scalar, List & Dict SELECTs (`select_scalar`, `select_list`, `select_dict`)](#scalar-list--dict-selects-select_scalar-select_list-select_dict)
   - [Python Keywords as Column Names (`_from`, `_class`, etc.)](#python-keywords-as-column-names-_from-_class-etc)
   - [NULL Value Handling](#null-value-handling)
9. [Data Manipulation (CRUD)](#-data-manipulation-crud)
   - [Inserting Rows (`insert`)](#inserting-rows-insert)
   - [Updating Rows (`update`)](#updating-rows-update)
   - [Deleting Rows (`delete`)](#deleting-rows-delete)
10. [High-Performance Bulk Operations](#-high-performance-bulk-operations)
    - [Lightning-Fast Batch Insert with PostgreSQL COPY (`insert_batch`)](#lightning-fast-batch-insert-with-postgresql-copy-insert_batch)
    - [Batch Update (`update_batch`)](#batch-update-update_batch)
    - [Batch Upsert / ON CONFLICT (`upsert_batch`)](#batch-upsert--on-conflict-upsert_batch)
11. [Stored Functions & Procedures](#-stored-functions--procedures)
    - [Calling Functions (`func_scalar`, `func_one`, `func_all`, `call_func`)](#calling-functions-func_scalar-func_one-func_all-call_func)
    - [Positional and Named Arguments in Functions](#positional-and-named-arguments-in-functions)
    - [List and Dictionary Functions (`func_list`, `func_dict`)](#list-and-dictionary-functions-func_list-func_dict)
    - [Calling Stored Procedures (`call_proc`, `call_procedure`)](#calling-stored-procedures-call_proc-call_procedure)
12. [Result Mapping & Custom Row Factories](#-result-mapping--custom-row-factories)
    - [Dictionaries (`dict_row`)](#dictionaries-dict_row)
    - [Tuples & Scalars (`tuple_row`, `scalar_row`)](#tuples--scalars-tuple_row-scalar_row)
    - [NamedTuples (`namedtuple_row`)](#namedtuples-namedtuple_row)
    - [Dataclasses & Custom Classes (`class_row`)](#dataclasses--custom-classes-class_row)
13. [Database Introspection & Utilities](#-database-introspection--utilities)
    - [Check Existence (`exists`)](#check-existence-exists)
    - [Inspect Table Structure (`tabledesc`)](#inspect-table-structure-tabledesc)
14. [Error Handling & Debugging](#-error-handling--debugging)
15. [Complete Real-World Example](#-complete-real-world-example)
16. [Documentation & Deep Dives](#-documentation--deep-dives)
17. [Author & License](#-author--license)

---

## 🚀 Key Features & Advantages

- **Boilerplate-Free CRUD**: High-level Python methods for querying, inserting, updating, and deleting rows without writing raw SQL strings for simple tasks.
- **Built-in Connection Pooling**: Thread-safe connection pool with configurable Time-To-Live (`TTL`), automatic health checks, and reconnects.
- **Transaction Safety (Rollback-by-Default)**: Sessions automatically roll back uncommitted changes when exiting context manager blocks or on unhandled exceptions.
- **SQL-Injection Safe**: Secure SQL generation using `psycopg.sql.Identifier` and strict parameter binding.
- **Blazing Fast Mass Ingestion**: `insert_batch` leverages native PostgreSQL `COPY FROM STDIN` streaming for inserting thousands of records in milliseconds.
- **Rich Row Factories**: Easily map rows to Python `dict`, `tuple`, `namedtuple`, or custom `@dataclass` objects.
- **Keyword-Friendly**: Automatically handles Python reserved words in column names (e.g. `_from`, `_class`, `_import`).

---

## 📦 Installation & Requirements

Caddix requires **Python 3.10+** and **psycopg (version 3.x)**.

### Using `uv` (Recommended)

```bash
uv add caddix
```

Or install dependencies directly into your uv project:
```bash
uv add "psycopg[binary]"
```

*(Optional: If compiling psycopg with native C extensions, install `uv add "psycopg[c]"`).*

---

## ⚡ Quickstart Guide

Here is a 30-second quickstart demonstrating how simple it is to configure and use Caddix:

```python
import caddix

# 1. Configure the database connection
caddix.Setup(
    databasename='app_db',
    username='postgres',
    password='mysecretpassword',
    hostname='localhost',
    port=5432
)

# 2. Open a session and execute queries
with caddix.DatabaseSession() as db:
    # SQL-free query: fetches a single row as a dictionary
    user = db.select_one('users', id=1)
    print("User found:", user)

    # Insert a new record and commit
    db.insert('logs', message='User 1 logged in')
    db.commit()
```

---

## ⚙️ Configuration Management (`caddix.Setup`)

### Basic Setup

Before opening sessions, register your database connection details via `caddix.Setup`:

```python
import caddix

caddix.Setup(
    databasename='mydatabase',
    username='myusername',
    password='mysecretpassword',
    hostname='localhost',
    port=5432,
    connect_timeout=10,
    application_name='my_service',
    ttl=30,               # Reconnect after 30 seconds of inactivity
    max_connections=15,   # Pool queue capacity
    verbose=False         # Set to True for detailed query/param debug messages
)
```

### Managing Multiple Databases

You can register multiple independent database configurations using the `name` parameter:

```python
import caddix

# Primary read/write database (default)
caddix.Setup(
    name='default',
    databasename='production_db',
    username='app_user',
    password='app_password',
    hostname='primary-db.internal'
)

# Read-only replica or analytics database
caddix.Setup(
    name='analytics',
    databasename='warehouse_db',
    username='analyst',
    password='analyst_password',
    hostname='analytics-db.internal',
    ttl=60,
    max_connections=20
)

# Use the analytics database in a session
with caddix.DatabaseSession(configname='analytics') as db:
    report = db.execute_fetchall("SELECT date, SUM(revenue) FROM daily_sales GROUP BY date")
```

### Configuration Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `databasename` | `str` | *(required)* | Name of the PostgreSQL database. |
| `username` | `str` | *(required)* | Database user for authentication. |
| `password` | `str` | *(required)* | Database password for authentication. |
| `hostname` | `str` | *(required)* | Hostname or IP address of the database server. |
| `port` | `int` | `5432` | Port number of the PostgreSQL server. |
| `name` | `str` | `'default'` | Unique identifier for this configuration setup. |
| `connect_timeout` | `int` | `10` | Timeout in seconds when connecting to PostgreSQL. |
| `application_name` | `str` | `'python'` | Application name displayed in `pg_stat_activity` and logs. |
| `ttl` | `int` | `10` | Time-to-Live (in seconds) for pooled connections before refresh. |
| `max_connections` | `int` | `10` | Maximum number of active pooled connections in the queue. |
| `verbose` | `bool` | `False` | Include full SQL statement and parameters in exception messages (disabled by default; intended for developer debugging). |
| `default_rowfactory` | `callable` | `dict_row` | Default cursor row factory (`dict_row`, `tuple_row`, etc.). |

---

## 🏊 Connection Pool (`caddix.PGPool`)

Caddix manages connections via a thread-safe `queue.Queue` backed pool.

- **Automatic Lifecycle**: `DatabaseSession` automatically borrows a connection from the pool on enter and returns it on exit.
- **TTL Expiration**: If a borrowed connection has exceeded its TTL timestamp, it is cleanly closed and a fresh connection is established.
- **Standalone Connection**: You can obtain a direct, unmanaged `psycopg.Connection` using `single_connect()` if needed:
  ```python
  raw_conn = caddix.PGPool(configname='default').single_connect()
  ```

---

## 🔒 Database Sessions & Transactions (`caddix.DatabaseSession`)

`caddix.DatabaseSession` is your main gateway for executing queries and managing transactions.

### Context Manager & Rollback-by-Default

Caddix enforces a **safe-by-default** transaction model:

```python
with caddix.DatabaseSession() as db:
    db.insert('orders', user_id=42, total=99.95)
    # If an exception occurs, or if db.commit() is omitted,
    # Caddix automatically rolls back all changes upon leaving this block!
    db.commit()  # Explicitly commit to persist changes
```

### Committing Transactions

Call `db.commit()` at any logical checkpoint within your session to save your operations to disk.

```python
with caddix.DatabaseSession() as db:
    db.update('accounts', values={'balance': 100}, id=1)
    db.update('accounts', values={'balance': 200}, id=2)
    db.commit()
```

### Explicit / Non-Context Usage

While the `with` statement is strongly recommended, you can also manage sessions manually:

```python
db = caddix.DatabaseSession()
try:
    users = db.select_all('users', active=True)
    db.commit()
finally:
    db.con.rollback()
```

---

## 🔍 Executing Raw SQL Queries

For complex queries (JOINs, aggregations, window functions), you can execute raw SQL with secure named parameter binding.

### Parameterized Execution (`execute`, `executemany`)

```python
with caddix.DatabaseSession() as db:
    # Single query with named parameters %(param)s
    db.execute(
        """
        SELECT u.id, u.username, COUNT(o.id) AS order_count
        FROM users u
        LEFT JOIN orders o ON o.user_id = u.id
        WHERE u.created_at >= %(since)s
        GROUP BY u.id, u.username
        HAVING COUNT(o.id) > %(min_orders)s
        """,
        since='2025-01-01',
        min_orders=5
    )

    # Batch execution with executemany
    db.executemany(
        "INSERT INTO audit_log (action, user_id) VALUES (%(action)s, %(uid)s)",
        [
            {'action': 'LOGIN', 'uid': 1},
            {'action': 'LOGOUT', 'uid': 2},
        ]
    )
    db.commit()
```

### Cursor Fetch Methods

After calling `db.execute()`, fetch results using any of the specialized fetch helpers:

```python
with caddix.DatabaseSession() as db:
    db.execute("SELECT id, username, email FROM users WHERE role = %(role)s", role='admin')

    # 1. Fetch single row (as dict) or None
    first_admin = db.fetchone()

    # 2. Fetch all rows (as list of dicts)
    all_admins = db.fetchall()

    # 3. Fetch up to N rows
    batch = db.fetchmany(10)

    # 4. Fetch single scalar value from the first column of the first row
    db.execute("SELECT COUNT(*) FROM users")
    total_users = db.fetchscalar()  # e.g. 1500

    # 5. Fetch a flat list of values from the first column across all rows
    db.execute("SELECT email FROM users WHERE active = true")
    email_list = db.fetchlist()     # ['a@test.com', 'b@test.com', ...]

    # 6. Fetch a dictionary mapping column 1 (key) -> column 2 (value)
    db.execute("SELECT id, username FROM users")
    id_to_user_map = db.fetchdict() # {1: 'alice', 2: 'bob', ...}
```

### Combined Execute & Fetch Helpers

Execute SQL and fetch results in a single concise call:

```python
with caddix.DatabaseSession() as db:
    # Execute and fetch one row
    user = db.execute_fetchone("SELECT * FROM users WHERE id = %(id)s", id=42)

    # Execute and fetch all rows
    active_users = db.execute_fetchall("SELECT * FROM users WHERE active = %(a)s", a=True)

    # Execute and fetch multiple rows
    sample = db.execute_fetchmany("SELECT * FROM events", size=5)

    # Execute and fetch a scalar
    user_count = db.execute_fetchscalar("SELECT COUNT(*) FROM users")

    # Execute and fetch flat list
    emails = db.execute_fetchlist("SELECT email FROM users WHERE active = %(a)s", a=True)

    # Execute and fetch key-value dictionary
    sku_price_map = db.execute_fetchdict("SELECT sku, price FROM products")
```

---

## 🛠️ SQL-Free Query Helpers (SELECT API)

Caddix provides expressive, SQL-injection-proof helpers for common `SELECT` operations.

### Selecting Rows (`select_all`, `select_one`, `select_many`)

```python
with caddix.DatabaseSession() as db:
    # 1. select_all: get all matching records
    all_admins = db.select_all('users', role='admin', active=True)

    # Select specific columns only
    user_names = db.select_all('users', columns=['id', 'username'], active=True)

    # 2. select_one: get first matching record (or None)
    user = db.select_one('users', id=10)

    # 3. select_many: limit result set size
    recent_signups = db.select_many('users', size=5, active=True)
```

### Scalar, List & Dict SELECTs (`select_scalar`, `select_list`, `select_dict`)

```python
with caddix.DatabaseSession() as db:
    # Get a single column's value
    email = db.select_scalar('users', column='email', id=42)

    # Get a list of column values
    all_tags = db.select_list('tags', column='name', category='tech')

    # Get a dictionary mapping primary key to a column value
    id_name_dict = db.select_dict('users', column_key='id', column_value='username', active=True)
```

### Python Keywords as Column Names (`_from`, `_class`, etc.)

If your database table has column names that collide with Python reserved keywords (such as `from`, `class`, `type`, `import`, `order`, `group`), prefix the argument with an underscore `_`:

```python
with caddix.DatabaseSession() as db:
    # '_from' is automatically mapped to column 'from'
    # '_type' is automatically mapped to column 'type'
    messages = db.select_all('messages', _from='support@example.com', _type='urgent')
```

### NULL Value Handling

Passing `None` as a value automatically translates to SQL `IS NULL`:

```python
with caddix.DatabaseSession() as db:
    # Generates: WHERE deleted_at IS NULL AND verified = true
    active_users = db.select_all('users', deleted_at=None, verified=True)
```

---

## ✍️ Data Manipulation (CRUD)

### Inserting Rows (`insert`)

Insert single records and optionally return generated values (`id`, timestamps, etc.):

```python
with caddix.DatabaseSession() as db:
    # Simple insert
    db.insert('users', username='alice', email='alice@example.com', role='member')
    db.commit()

    # Insert with RETURNING (e.g. auto-incremented ID)
    result = db.insert('users', returning='id', username='bob', email='bob@example.com')
    print("New User ID:", result['id'])
    db.commit()

    # Insert with RETURNING all columns
    new_user = db.insert('users', returning='*', username='charlie', email='charlie@example.com')
    print("Created at:", new_user['created_at'])
    db.commit()
```

### Updating Rows (`update`)

Update rows matching specific filter criteria:

```python
with caddix.DatabaseSession() as db:
    # Update active status for guest accounts
    db.update('users', values={'active': False}, role='guest')
    db.commit()

    # Update with RETURNING clause
    updated_rows = db.update(
        'users',
        values={'last_login': '2025-11-19'},
        returning='id, email',
        id=42
    )
    db.commit()
```

### Deleting Rows (`delete`)

Delete specific rows matching filter arguments:

```python
with caddix.DatabaseSession() as db:
    # Delete specific user
    db.delete('users', id=99)
    db.commit()

    # Delete all inactive guest accounts
    db.delete('users', role='guest', active=False)
    db.commit()

    # Intentionally deleting all rows in a table requires allow_all=True
    db.delete('temp_logs', allow_all=True)
    db.commit()
```

> 🛡️ **Safety Guard**: Calling `db.delete('table_name')` without WHERE filter criteria will raise a `CaddixSessionError` to prevent accidental full-table data loss. To intentionally delete all rows, pass `allow_all=True`.

---

## ⚡ High-Performance Bulk Operations

When inserting or updating hundreds, thousands, or millions of records, standard loops are too slow. Caddix provides dedicated high-performance batch methods.

### Lightning-Fast Batch Insert with PostgreSQL COPY (`insert_batch`)

When `returning=None`, `insert_batch` uses PostgreSQL's native streaming **`COPY FROM STDIN`** protocol:

```python
records = [
    {'device_id': 1, 'temperature': 21.4, 'humidity': 45.2, 'recorded_at': '2025-11-19 12:00:00'},
    {'device_id': 2, 'temperature': 22.1, 'humidity': 43.8, 'recorded_at': '2025-11-19 12:00:01'},
    # ... thousands of sensor readings
]

with caddix.DatabaseSession() as db:
    # Ingests large datasets in milliseconds
    count = db.insert_batch('telemetry', records)
    db.commit()
    print(f"Successfully ingested {count} telemetry records.")
```

If you need returned IDs or values, pass `returning='id'`:
```python
with caddix.DatabaseSession() as db:
    new_ids = db.insert_batch('users', records, returning='id')
    db.commit()
```

### Batch Update (`update_batch`)

Update multiple records in a single batch query:

```python
updates = [
    {'id': 1, 'status': 'PROCESSED', 'attempts': 3},
    {'id': 2, 'status': 'FAILED', 'attempts': 5},
    {'id': 3, 'status': 'PROCESSED', 'attempts': 1},
]

with caddix.DatabaseSession() as db:
    # Update 'status' and 'attempts' matching by 'id'
    db.update_batch(
        'job_queue',
        values=updates,
        update_columns=['status', 'attempts'],
        where_columns=['id']
    )
    db.commit()
```

### Batch Upsert / ON CONFLICT (`upsert_batch`)

Insert rows or update them automatically on primary key or unique constraint conflicts (`INSERT ... ON CONFLICT DO UPDATE`):

```python
products = [
    {'sku': 'PRD-001', 'title': 'Mechanical Keyboard', 'price': 129.99, 'stock': 45},
    {'sku': 'PRD-002', 'title': 'Wireless Mouse', 'price': 39.99, 'stock': 120},
]

with caddix.DatabaseSession() as db:
    # If 'sku' conflicts, update 'price' and 'stock'
    db.upsert_batch(
        'products',
        values=products,
        conflict_columns=['sku'],
        update_columns=['price', 'stock']
    )
    db.commit()

    # Or update ALL non-conflict columns by passing update_columns='*'
    db.upsert_batch('products', products, conflict_columns=['sku'], update_columns='*')
    db.commit()
```

---

## ⚡ Stored Functions & Procedures

Caddix provides first-class, secure methods for executing PostgreSQL stored functions and stored procedures directly, eliminating the need to write boilerplate SQL (`SELECT * FROM ...` or `CALL ...`).

### Calling Functions (`func_scalar`, `func_one`, `func_all`, `call_func`)

Depending on what your PostgreSQL function returns, Caddix provides intuitive helper methods:

- **`func_scalar(funcname, *args, **kwargs)`**: Executes `SELECT funcname(...)` and returns a single scalar value.
- **`func_one(funcname, *args, **kwargs)`**: Executes `SELECT * FROM funcname(...)` and returns a single row.
- **`func_all(funcname, *args, **kwargs)`** (or **`call_func`** / **`call_function`**): Executes `SELECT * FROM funcname(...)` and returns all rows as a list.
- **`func_many(funcname, size, *args, **kwargs)`**: Executes `SELECT * FROM funcname(...)` and returns up to `size` rows.

```python
with caddix.DatabaseSession() as db:
    # 1. Scalar function: returns single value (e.g. integer)
    total = db.func_scalar('calculate_order_total', 101, discount=0.10)
    print("Total:", total)

    # 2. Table function returning a single row
    profile = db.func_one('get_user_profile', user_id=42)
    print("User profile:", profile)

    # 3. Table function returning multiple rows
    active_users = db.func_all('get_active_users', min_rank=3)
    # or using call_func:
    # active_users = db.call_func('get_active_users', min_rank=3)
    for u in active_users:
        print(u['id'], u['name'])
```

### Positional and Named Arguments in Functions

Caddix supports positional arguments (`*args`), PostgreSQL named arguments (`name => value` via `**kwargs`), and Python keyword sanitization (`_from`, `_class`, etc.):

```python
with caddix.DatabaseSession() as db:
    # Positional arguments: calculate_distance(lat1, lon1, lat2, lon2)
    dist = db.func_scalar('calculate_distance', 52.5200, 13.4050, 48.8566, 2.3522)

    # Named arguments (rendered safely as calculate_distance(lat1 => ..., ...))
    dist = db.func_scalar('calculate_distance', lat1=52.5200, lon1=13.4050, lat2=48.8566, lon2=2.3522)

    # Schema-qualified function names
    result = db.func_scalar('geo.calculate_distance', 52.52, 13.40, 48.85, 2.35)

    # Reserved Python keywords in argument names
    db.func_scalar('filter_logs', _from='2025-01-01', _to='2025-01-31')
```

### List and Dictionary Functions (`func_list`, `func_dict`)

- **`func_list(funcname, *args, **kwargs)`**: Extracts the first column of all returned rows into a flat Python list.
- **`func_dict(funcname, *args, **kwargs)`**: Converts 2-column result rows into a Python key-value dictionary.

```python
with caddix.DatabaseSession() as db:
    # Returns [101, 102, 103]
    active_ids = db.func_list('get_active_user_ids')

    # Function returning key/value pairs -> {'tax_rate': 0.19, 'currency': 'EUR'}
    settings = db.func_dict('get_app_settings', category='billing')
```

### Calling Stored Procedures (`call_proc`, `call_procedure`)

Use **`call_proc(procname, *args, **kwargs)`** (or alias **`call_procedure`**) to execute PostgreSQL stored procedures (`CALL proc(...)`):

- **Procedures without return values**: Executes the procedure and returns `None`.
- **Procedures with `OUT` / `INOUT` parameters**: Returns the output values as a dictionary (or row-factory format).

```python
with caddix.DatabaseSession() as db:
    # 1. Procedure performing database modifications (requires commit)
    db.call_proc('archive_old_records', threshold_days=90)
    db.commit()

    # 2. Procedure with OUT parameters (sum, prod)
    result = db.call_proc('calculate_stats', 10, 20, None, None)
    print("Stats:", result)  # {'sum': 30, 'prod': 200}
```

---

## 🎨 Result Mapping & Custom Row Factories

By default, Caddix returns rows as Python `dict` objects. You can easily switch to any psycopg-compatible row factory globally in `Setup` or per-session.

### Dictionaries (`dict_row`) - Default

```python
with caddix.DatabaseSession() as db:
    user = db.select_one('users', id=1)
    print(user['username'], user['email'])
```

### Tuples & Scalars (`tuple_row`, `scalar_row`)

```python
with caddix.DatabaseSession(cursor_factory=caddix.tuple_row) as db:
    row = db.select_one('users', id=1)
    print(row[0], row[1])  # (1, 'alice')
```

### NamedTuples (`namedtuple_row`)

```python
with caddix.DatabaseSession(cursor_factory=caddix.namedtuple_row) as db:
    user = db.select_one('users', id=1)
    print(user.id, user.username, user.email)
```

### Dataclasses & Custom Classes (`class_row`)

Automatically map query results directly into your Python `@dataclass` or custom classes:

```python
from dataclasses import dataclass
import caddix

@dataclass
class User:
    id: int
    username: str
    email: str
    active: bool

with caddix.DatabaseSession(cursor_factory=caddix.class_row(User)) as db:
    user_obj: User = db.select_one('users', id=1)
    print(isinstance(user_obj, User))  # True
    print(f"User: {user_obj.username} <{user_obj.email}>")
```

---

## 🔬 Database Introspection & Utilities

### Check Existence (`exists`)

Quickly check if at least one row matching your conditions exists:

```python
with caddix.DatabaseSession() as db:
    if db.exists('users', email='test@example.com'):
        print("An account with this email already exists.")
```

### Inspect Table Structure (`tabledesc`)

Read column names, data types, length, primary keys, foreign keys, and defaults directly from PostgreSQL's system catalog:

```python
with caddix.DatabaseSession() as db:
    # Get column metadata as a dictionary indexed by column name
    schema = db.tabledesc('users', asdict=True)
    
    print("Email type:", schema['email']['type'])          # e.g. 'character varying(255)'
    print("Is ID primary key?", schema['id']['primarykey']) # True
    print("Is email nullable?", not schema['email']['notnull'])
    print("Default value for created_at:", schema['created_at']['default'])
```

---

## 🛡️ Error Handling & Debugging

When a database error occurs (syntax error, constraint violation, connection issue), Caddix wraps the error in a descriptive `CaddixError` exception.

By default, `verbose=False` is set to prevent SQL queries and sensitive parameters from unintentionally leaking into application logs or production outputs.

When `verbose=True` is explicitly enabled (recommended during development and debugging), the error message contains:
1. The exact SQL statement that failed.
2. The parameters passed to the statement.
3. The original psycopg exception class and message.

When `verbose=False` (default), only the sanitized primary database error message is included in the exception text. The original exception object remains accessible via `e.orig`.

```python
import caddix

try:
    with caddix.DatabaseSession() as db:
        db.execute("SELECT * FROM non_existing_table WHERE id = %(id)s", id=123)
except caddix.CaddixError as e:
    print("--- Caddix SQL Error ---")
    print("Original Exception:", e.orig)
    print("Full Debug Message:\n", e)
```

### Session Validation Errors (`CaddixSessionError`)

Logical errors (e.g. calling `select_many()` without a size or missing columns during batch updates) raise a `CaddixSessionError`:

```python
try:
    with caddix.DatabaseSession() as db:
        db.select_many('users', size=None)
except caddix.CaddixSessionError as e:
    print("Session Error:", e)
```

---

## 💡 Complete Real-World Example

Here is a full, end-to-end example demonstrating user management with Caddix:

```python
from dataclasses import dataclass
import caddix

# 1. Setup Database Connection
caddix.Setup(
    databasename='myapp',
    username='postgres',
    password='secretpassword',
    hostname='localhost',
    port=5432,
    application_name='user_service',
    ttl=20
)

# 2. Define Domain Dataclass
@dataclass
class User:
    id: int
    username: str
    email: str
    role: str
    active: bool

def register_user(username: str, email: str, role: str = 'member') -> int:
    with caddix.DatabaseSession() as db:
        # Check if email is already taken
        if db.exists('users', email=email):
            raise ValueError(f"Email '{email}' is already registered.")

        # Insert new user and fetch generated ID
        result = db.insert('users', returning='id', username=username, email=email, role=role, active=True)
        db.commit()
        return result['id']

def get_active_admins() -> list[User]:
    # Query directly into Dataclass instances
    with caddix.DatabaseSession(cursor_factory=caddix.class_row(User)) as db:
        return db.select_all('users', role='admin', active=True)

def import_user_batch(user_records: list[dict]) -> int:
    with caddix.DatabaseSession() as db:
        # High-speed COPY ingestion
        count = db.insert_batch('users', user_records)
        db.commit()
        return count

# Run workflow
if __name__ == '__main__':
    new_id = register_user('marcus', 'marcus@example.com', role='admin')
    print(f"Registered admin with ID {new_id}")

    admins = get_active_admins()
    for admin in admins:
        print(f"Admin: {admin.username} ({admin.email})")
```

---

## 📚 Documentation & Deep Dives

For further reading, deep architectural details, and developer guidelines, explore the documents in the [`docs/`](https://github.com/MarcusGros/caddix/tree/main/docs) directory:

- [**Changelog**](https://github.com/MarcusGros/caddix/blob/main/CHANGELOG.md): Release history, breaking changes, and migration notes.
- [**API Reference**](https://github.com/MarcusGros/caddix/blob/main/docs/API_REFERENCE.md): Full technical reference of all classes, methods, parameters, and exceptions.
- [**Architecture & Internals**](https://github.com/MarcusGros/caddix/blob/main/docs/ARCHITECTURE.md): Component mapping, lifecycle workflows, and security architecture.
- [**Developer & Contributor Guide**](https://github.com/MarcusGros/caddix/blob/main/docs/DEVELOPER_GUIDE.md): Setup instructions, testing guidelines, and conventions for contributors.

---

## 👤 Author & License

- **Author**: Marcus Gros (`marcus-gros@freenet.de`)
- **Copyright**: 2026 Marcus Gros
- **License**: [MIT](https://github.com/MarcusGros/caddix/blob/main/LICENSE)

Have fun building fast, secure PostgreSQL applications with **Caddix**! 🐘

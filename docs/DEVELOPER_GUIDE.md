# Caddix - Developer Guide & Internals

This document is intended for **developers and maintainers** who want to contribute to the **Caddix** codebase, implement new features, or understand its internal architecture and execution flows.

---

## 1. Architectural Overview & Design Principles

Caddix is designed as a lightweight, high-performance abstraction layer built on top of `psycopg 3`. Its primary goal is to provide developers with maximum speed, safety, and productivity without compromising the full power and flexibility of PostgreSQL.

### Core Principles:
1. **No Heavy ORM Overhead**: Caddix deliberately avoids complex ORM layers, session-state tracking, and identity maps. It remains lightweight and close to raw SQL.
2. **Rollback-by-Default**: Every operation inside a `DatabaseSession` context block is rolled back upon exit (`con.rollback()`), unless explicitly committed via `db.commit()`.
3. **Thread Safety**: Connection pools are built on Python's standard `queue.Queue`, providing safe concurrent access across threads.
4. **Strict SQL Injection Prevention**: Dynamic queries are constructed strictly using `psycopg.sql.Identifier` for identifiers and parameterized placeholders (`%(w0)s`, `%(p0)s`, etc.) for values.
5. **PostgreSQL-Native Capabilities**: Direct utilization of PostgreSQL-specific features such as `COPY FROM STDIN` for ultra-fast bulk inserts and `ON CONFLICT DO UPDATE` for atomic upserts.

---

## 2. Project Structure & Module Responsibilities

```
caddix/
├── caddix/
│   ├── __init__.py       # Package entry point, versioning, public exports (__all__)
│   ├── base.py           # DatabaseSession, CaddixError, CaddixSessionError
│   ├── config.py         # Configs (Setup) – Configuration storage & DSN building
│   ├── pool.py           # PGPool – Connection lifecycle & queue management
│   ├── stores.py         # Global dictionaries (configs, queues)
│   └── utils.py          # SQL query builders & helper functions
├── Tests/
│   ├── test_batch_bulk.py
│   ├── test_config_pool.py
│   ├── test_crud_operations.py
│   ├── test_functions_procedures.py
│   ├── test_provocation_edge_cases.py
│   ├── test_row_factories.py
│   ├── test_security_penetration.py
│   ├── test_session_basics.py
│   └── test_stress_concurrency.py
├── docs/                 # User guide, API reference, architecture & developer documentation
│   ├── API_REFERENCE.md
│   ├── ARCHITECTURE.md
│   ├── DEVELOPER_GUIDE.md
│   └── USER_GUIDE.md
├── pyproject.toml        # Project configuration, dependencies & build metadata (PEP 621)
└── README.md             # Project overview, key features & quickstart guide
```

### Module Responsibilities in Detail:

- **`caddix/config.py` (`Configs` / `Setup`)**:
  - Stores database configurations in the class-level attribute `Configs.configs` keyed by unique configuration names (default: `'default'`).
  - Constructs formatted PostgreSQL connection strings / DSNs: `postgresql://user:pass@host:port/dbname?connect_timeout=...&application_name=...`.

- **`caddix/pool.py` (`PGPool`)**:
  - Manages dedicated connection queues (`queue.Queue`) per configuration name in `queues`.
  - Pairs each connection (`psycopg.Connection`) with an expiration timestamp (`expire = time.time() + ttl`).
  - Handles automatic reconnection and cleanup when a pooled connection has expired.

- **`caddix/base.py` (`DatabaseSession`)**:
  - The primary interface for database interactions.
  - Manages the lifecycle of connection (`con`) and cursor (`cur`, `psycopg.Cursor`).
  - Implements the Python context manager protocol (`__enter__`, `__exit__`).
  - Implements all CRUD, SELECT, fetch, batch, and function/procedure execution methods.

- **`caddix/utils.py`**:
  - `build_select_query(con, tablename, columns, **kwargs)`: Builds a parameterized SELECT query using `psycopg.sql.Identifier` and dynamic parameter mapping.
  - `build_call_func_query(con, funcname, as_table, *args, **kwargs)`: Constructs safe stored function calls (`SELECT * FROM fn(...)` or `SELECT fn(...)`) supporting positional and named parameters.
  - `build_call_proc_query(con, procname, *args, **kwargs)`: Constructs safe stored procedure calls (`CALL proc(...)`).
  - `simple_where_builder(**kwargs)` & `simple_query_builder(...)`: Utility query generators.

---

## 3. Internal Data Flows & Lifecycles

### 3.1 Initialization and Connection Retrieval
```
Application -> DatabaseSession(configname)
                    |
                    v
                 PGPool(configname)
                    |
                    +--> Retrieves (con, expire) from queue.Queue
                    |    If queue is empty: connects via psycopg.connect(dsn), expire = now + ttl
                    |    If expired (expire < now): closes connection, reconnects
                    |
                    v
                 DatabaseSession binds active con & cur
```

### 3.2 Dynamic Query Generation (`build_select_query`)
When calling `select_all('users', columns=['id', 'name'], active=True, deleted_at=None)`:
1. `columns` are transformed into `sql.Identifier('id'), sql.Identifier('name')`.
2. `tablename` is formatted as `sql.Identifier('users')`.
3. `kwargs` are iterated:
   - If the value is `None`, `sql.SQL("{} IS NULL").format(sql.Identifier(col))` is generated.
   - Otherwise, a secure parameter key (`w0`, `w1`, ...) is generated: `sql.SQL("{} = %(w0)s").format(sql.Identifier(col))`.
4. The final query object is rendered via `query.as_string(con)` and executed with the parameter mapping dictionary.

### 3.3 Python Reserved Keywords Handling (`__kwargs__`)
Python syntax does not allow reserved keywords like `from`, `class`, or `type` as direct keyword arguments in function calls.
`DatabaseSession.__kwargs__(kwargs)` inspects all passed keys:
- If a key starts with `_` (e.g. `_from`), the leading underscore is stripped (`from`) and mapped accordingly.

---

## 4. Bulk Operations & Performance Internals

### 4.1 `insert_batch`
- **Streaming Mode (`returning=None`)**:
  Utilizes PostgreSQL's native streaming protocol via `with self.cur.copy("COPY table (col1, col2) FROM STDIN") as copy:`.
  Calls `copy.write_row(...)` for each record. This eliminates SQL parsing overhead on the database server and provides maximum ingestion throughput.
- **Returning Mode (`returning='id'`)**:
  Falls back to parameterized `self.executemany("INSERT INTO table ... RETURNING id", values)` and returns the fetched rows.

### 4.2 `upsert_batch`
Builds a parameterized atomic statement:
`INSERT INTO {table} ({cols}) VALUES ({vals}) ON CONFLICT ({conf}) DO UPDATE SET {set_clause}`
where `set_clause` maps each non-conflict column to `col = EXCLUDED.col`.

---

## 5. Exception Architecture

- **`CaddixError`**:
  Raised by `execute()` and `executemany()` whenever a database or driver error occurs.
  - `e.orig`: The underlying `psycopg.Error` instance.
  - Output: Displays the executed SQL query, parameter values, and error category when `verbose=True` (default is `verbose=False` to prevent sensitive query leaks in production).
- **`CaddixSessionError`**:
  Raised for logical or usage errors within the session (e.g. missing required keys in batch updates or invalid arguments).

---

## 6. Development Environment & Testing

The project uses **[uv](https://docs.astral.sh/uv/)** as its environment and package manager.

### Prerequisites:
- Python 3.10 or higher.
- A running PostgreSQL instance (e.g., `localhost:5432`).
- A test database configured with credentials matching your test configuration.

### Setup Development Environment:
```bash
# Create virtual environment and install all dependencies including dev tools:
uv sync --extra dev
```

### Running Tests:
```bash
# Run full test suite with pytest:
uv run pytest

# Or run with standard unittest:
uv run python -m unittest discover -s Tests
```

### Building the Package:
```bash
uv build
```

---

## 7. Contribution & Coding Guidelines

1. **Row Factory Hygiene**:
   Methods that temporarily alter `self.cur.row_factory` (e.g. `fetchscalar`, `fetchlist`, `fetchdict`) **must** restore the cursor's original factory after retrieving results.
2. **Security First**:
   Never use raw string interpolation (e.g. `f"SELECT {col} FROM {table}"`) without proper `psycopg.sql.Identifier` wrapping and parameterized values.
3. **Documentation**:
   Every new public method added to `DatabaseSession` must be documented in `docs/USER_GUIDE.md` with usage examples and in `docs/API_REFERENCE.md`.
4. **Code Consistency**:
   Follow PEP 8 conventions, maintain comprehensive type annotations, and ensure all existing and new unit tests pass before submitting changes.

# Caddix - Architecture & Component Mapping

This document provides a comprehensive overview of the architecture, component mapping, and internal runtime workflows of the **Caddix** library.

---

## 1. Project Concept & Design Goals

**Caddix** is a lightweight, high-performance Python helper library built on top of `psycopg` (version 3) designed to simplify, accelerate, and secure interactions with PostgreSQL databases.

### Key Goals:
- **Boilerplate Reduction**: Intuitive Python methods for common CRUD workflows (`select_*`, `insert`, `update`, `delete`, `upsert_batch`).
- **Connection Pooling & Lifecycle**: Automated connection pool management with Time-to-Live (`TTL`) checks and reconnection handling via `PGPool`.
- **Query Security**: Automatic identifier escaping and parameter binding via `psycopg.sql` to prevent SQL injection vulnerabilities.
- **Transaction Safety**: Context manager (`DatabaseSession`) with a rollback-by-default strategy to prevent unintended database writes.
- **High Performance**: Native utilization of PostgreSQL's `COPY` protocol for high-throughput batch ingestion (`insert_batch`) and parameterized batch executions (`executemany`).

---

## 2. Component & Module Architecture

```
caddix/
│
├── __init__.py         # Package entry point, exports primary classes & row factories
├── config.py           # Configs (Setup) – Registration & management of DB configurations
├── pool.py             # PGPool – Thread-safe connection pool with queue & TTL management
├── base.py             # DatabaseSession, CaddixError, CaddixSessionError – Core public API
├── stores.py           # Global store dictionaries for registered configs and active pools
└── utils.py            # SQL query-building utilities with psycopg.sql
```

### High-Level Component Flow

```mermaid
graph TD
    UserApp[Application / Script] -->|1. Setup| Setup[caddix.Setup / Configs]
    UserApp -->|2. with DatabaseSession| DBSession[DatabaseSession]
    DBSession -->|3. Get Connection| Pool[PGPool]
    Pool -->|4. Reads DSN/TTL| Setup
    Pool -->|5. Manages Queues| PsycopgConn[psycopg.Connection]
    DBSession -->|6. Builds SQL safely| Utils[caddix.utils / psycopg.sql]
    DBSession -->|7. Executes via Cursor| PsycopgCur[psycopg.Cursor / RowFactory]
```

### Module Responsibilities

| Module | Primary Classes / Functions | Responsibility |
|---|---|---|
| `caddix/__init__.py` | Exports `Setup`, `DatabaseSession`, `PGPool`, row factories | Central import interface (`import caddix`) |
| `caddix/config.py` | `Configs` (alias `Setup`) | Stores connection parameters, builds DSN strings, manages timeouts & defaults |
| `caddix/pool.py` | `PGPool` | Provides thread-safe `psycopg.Connection` instances using `queue.Queue` with TTL-based expiration |
| `caddix/base.py` | `DatabaseSession`, `CaddixError`, `CaddixSessionError` | Context manager for executing queries, transactions, CRUD, and bulk operations |
| `caddix/utils.py` | `build_select_query`, `simple_where_builder`, `simple_query_builder`, `get_column_names` | Dynamic and secure SQL generation using `psycopg.sql.Identifier` |
| `caddix/stores.py` | `configs`, `queues` | Global registry storage for named configurations and connection queues |

---

## 3. Runtime Data Flows & Lifecycles

### 3.1 Configuration Setup (`caddix.Setup`)
1. The application invokes `caddix.Setup(...)`.
2. A PostgreSQL DSN string (`postgresql://user:pass@host:port/dbname?...`) is constructed along with configuration options and stored in `Configs.configs[name]`.
3. Multiple distinct configurations (e.g. `'default'`, `'analytics'`, `'replica'`) can be registered simultaneously.

### 3.2 Session Lifecycle (`caddix.DatabaseSession`)
1. `with caddix.DatabaseSession(configname='default') as db:`
2. `DatabaseSession.__init__` acquires a connection from `PGPool(configname)`.
3. `PGPool` checks the corresponding `queue.Queue`:
   - If a connection is available and valid (`expire >= time.time()`), it is checked out for reuse.
   - If the queue is empty or the connection has expired, a new connection is established via `psycopg.connect(dsn)` with `expire = time.time() + ttl`.
4. A cursor is initialized with the configured `row_factory` (e.g., `dict_row`, `tuple_row`, `namedtuple_row`).
5. Within the context block, the application executes queries, CRUD operations, or function calls.
6. **Transaction Completion**:
   - Calling `db.commit()` commits pending changes permanently.
   - When exiting the `with` block, `DatabaseSession.__exit__` automatically issues `self.con.rollback()`, ensuring any uncommitted changes are safely discarded (Rollback-by-Default).
7. The connection is returned to the pool's queue upon leaving the scope (`PGPool.__exit__`).

### 3.3 Query Security & Parameter Sanitization
1. Python reserved keywords (e.g., `from`, `class`, `type`) can be passed with a leading underscore (e.g., `_from='user@example.com'`).
2. `DatabaseSession.__kwargs__` strips the leading underscore, producing the proper column name `from`.
3. `build_select_query` wraps table and column names in `psycopg.sql.Identifier` and uses numbered placeholders (`%(w0)s`, `%(w1)s`) for values, guaranteeing protection against SQL injection.

---

## 4. API Capabilities Summary

| Category | Key Methods | Description |
|---|---|---|
| **Transactions** | `commit()` | Explicitly commits the current transaction to the database. |
| **Raw SQL Execution** | `execute()`, `executemany()` | Executes custom parameterized SQL queries with full placeholder binding. |
| **Cursor Fetching** | `fetchone()`, `fetchall()`, `fetchmany()`, `fetchscalar()`, `fetchlist()`, `fetchdict()` | Retrieves result rows from the last executed query in multiple structured formats. |
| **Combined Execute & Fetch** | `execute_fetchone()`, `execute_fetchall()`, `execute_fetchmany()`, `execute_fetchscalar()`, `execute_fetchlist()`, `execute_fetchdict()` | Executes a query and returns results in a single step. |
| **SQL-Free SELECT API** | `select_all()`, `select_one()`, `select_many()`, `select_scalar()`, `select_list()`, `select_dict()` | Automatically builds and runs secure SELECT statements based on filters and column lists. |
| **CRUD Operations** | `insert()`, `update()`, `delete()` | Standard insertion, update, and deletion operations with optional `RETURNING` support. |
| **High-Speed Bulk Ingestion** | `insert_batch()`, `update_batch()`, `upsert_batch()` | Fast batch execution leveraging `COPY FROM STDIN` streaming and atomic `ON CONFLICT DO UPDATE`. |
| **Stored Functions & Procedures** | `call_func()`, `call_proc()`, `func_all()`, `func_one()`, `func_scalar()`, `func_many()`, `func_list()`, `func_dict()` | Native and secure execution of PostgreSQL stored routines with positional and named arguments. |
| **Introspection & Utilities** | `exists()`, `tabledesc()`, `__kwargs__()` | Fast row existence checks, schema introspection from system catalogs, and parameter sanitization. |

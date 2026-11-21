<p align="center">
  <img src="https://raw.githubusercontent.com/MarcusGros/caddix/main/caddix.jpeg" alt="Caddix Logo" width="320" />
</p>

# Caddix - PostgreSQL Connection Assistant 

**Caddix** is a lightweight, high-performance Python helper library built on top of [psycopg 3](https://www.psycopg.org/psycopg3/docs/) designed to make interacting with PostgreSQL databases easier, faster, and safer.

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

Caddix requires **Python 3.10+**. The database driver **psycopg (version 3.x)** is automatically installed as a core dependency.

### Using `pip`

```bash
pip install caddix
```

### Using `uv` (Recommended)

```bash
uv add caddix
```

> 💡 **Performance Note**: For optimal performance without needing a local C compiler, you can optionally install the pre-compiled binary PostgreSQL driver via `pip install "psycopg[binary]"` or `uv add "psycopg[binary]"`.

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

## 📚 Documentation & Deep Dives

For in-depth guides, complete API listings, and developer documentation, explore our documentation suite:

- [**User Guide & Manual**](https://github.com/MarcusGros/caddix/blob/main/docs/USER_GUIDE.md): Comprehensive walkthrough covering configuration, connection pooling, transactions, raw SQL, CRUD helpers, bulk operations, stored procedures, and row factories.
- [**API Reference**](https://github.com/MarcusGros/caddix/blob/main/docs/API_REFERENCE.md): Full technical reference of all classes, methods, parameters, and exceptions.
- [**Architecture & Internals**](https://github.com/MarcusGros/caddix/blob/main/docs/ARCHITECTURE.md): Component mapping, lifecycle workflows, and security architecture.
- [**Developer & Contributor Guide**](https://github.com/MarcusGros/caddix/blob/main/docs/DEVELOPER_GUIDE.md): Setup instructions, testing guidelines, and conventions for contributors.
- [**Changelog**](https://github.com/MarcusGros/caddix/blob/main/CHANGELOG.md): Release history, breaking changes, and migration notes.

---

## 👤 Author & License

- **Author**: Marcus Gros
- **Copyright**: 2026 Marcus Gros
- **License**: [MIT](https://github.com/MarcusGros/caddix/blob/main/LICENSE)

Have fun building fast, secure PostgreSQL applications with **Caddix**! 🐘

---

<sub>*Logo AI-generated via <a href="https://perchance.org">perchance.org</a>*</sub>

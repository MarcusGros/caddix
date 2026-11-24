# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.1] - Unreleased

### Added
- Optional `client_encoding` in `Setup` to help Psycopg decode connection errors when the message encoding is known. It also affects successful sessions and is unset by default.
- Opt-in stress tests for concurrent sessions, pool reuse and mixed sequential and parallel workloads. All four passed on Linux across the 15 Python 3.10–3.14 and PostgreSQL 16–18 combinations; see the developer guide for details and limitations. The CI matrix also includes these tests.

### Changed
- Clarified that `max_connections` limits retained idle connections, not simultaneous connections, and that connection errors are raised directly by Psycopg.
- Improved public API docstrings for IDE documentation, completion, and code analysis.
- Documented Linux test results for all combinations of Python 3.10–3.14 and PostgreSQL 16–18; expanded the CI matrix accordingly.
- Simplified the testing and connection-error documentation.
- Fixed two broken documentation anchors in the API reference and user guide.
- Marked the package as Production/Stable in its PyPI classifier.

## [1.1.0] - 2026-11-21

### Added
- **Top-Level Exception Exports**: All Caddix exception classes (`CaddixError`, `CaddixSessionError`) are explicitly exported and directly accessible at module level as `caddix.CaddixError` and `caddix.CaddixSessionError`.
- **Accidental Deletion Protection in `delete()`**: Calling `DatabaseSession.delete('table_name')` without WHERE filter arguments now requires `allow_all=True`. Calling without conditions and without `allow_all=True` raises a `CaddixSessionError` to prevent accidental full-table data loss.
- **CI / CD Automation**: Added GitHub Actions workflows for matrix testing against PostgreSQL 16 (Python 3.10, 3.11, 3.12, 3.13) and automated PyPI Trusted Publishing (OIDC).
- **Changelog**: Added `CHANGELOG.md` tracking project history and releases.

### Changed
- **Streamlined Documentation & Query Guidance**: Refactored `README.md` to provide a concise overview and relocated the full User Manual to `docs/USER_GUIDE.md`. Added explicit guidance on the scope of the SQL-free SELECT API (exact equality and `IS NULL`), best practices for complex queries with parameterized Raw SQL, and a future outlook on potential query builder enhancements.
- **Default `verbose` Setting**: Changed the default value of `verbose` in `caddix.Setup` and `CaddixError` from `True` to `False`. Verbose mode is intended for developer debugging; disabling it by default prevents sensitive queries and parameters from leaking into production logs.
- **Robust Exception Handling**: Streamlined error wrapping across all session operations (including `insert_batch` via `COPY FROM STDIN`), improved informative message formatting for non-diagnostic exceptions in non-verbose mode, and added friendly `CaddixSessionError` messages for missing connection profiles.

---

## [1.0.0] - 2026-11-21

- initial release of **Caddix** (PostgreSQL Connection Assistant built on psycopg 3).
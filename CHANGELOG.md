# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - Unreleased

### Added
- **Top-Level Exception Exports**: All Caddix exception classes (`CaddixError`, `CaddixSessionError`) are explicitly exported and directly accessible at module level as `caddix.CaddixError` and `caddix.CaddixSessionError`.
- **Accidental Deletion Protection in `delete()`**: Calling `DatabaseSession.delete('table_name')` without WHERE filter arguments now requires `allow_all=True`. Calling without conditions and without `allow_all=True` raises a `CaddixSessionError` to prevent accidental full-table data loss.
- **CI / CD Automation**: Added GitHub Actions workflows for matrix testing against PostgreSQL 16 (Python 3.10, 3.11, 3.12, 3.13) and automated PyPI Trusted Publishing (OIDC).
- **Changelog**: Added `CHANGELOG.md` tracking project history and releases.

### Changed
- **Default `verbose` Setting**: Changed the default value of `verbose` in `caddix.Setup` and `CaddixError` from `True` to `False`. Verbose mode is intended for developer debugging; disabling it by default prevents sensitive queries and parameters from leaking into production logs.
- **Robust Exception Handling**: Streamlined error wrapping across all session operations (including `insert_batch` via `COPY FROM STDIN`), improved informative message formatting for non-diagnostic exceptions in non-verbose mode, and added friendly `CaddixSessionError` messages for missing connection profiles.

---

## [1.0.0] - 2026-11-21

- initial release of **Caddix** (PostgreSQL Connection Assistant built on psycopg 3).
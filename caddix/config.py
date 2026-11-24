from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row


class Configs:
    """Register a PostgreSQL connection profile (exported as ``caddix.Setup``).

    Profiles are stored by name and used by :class:`caddix.DatabaseSession`.
    No connection is opened during registration. If ``databasename`` is None,
    no profile is registered.

    :param databasename: PostgreSQL database name.
    :param username: Database user; None uses libpq's default.
    :param password: Database password; None uses libpq's default.
    :param hostname: Server host; None uses libpq's default.
    :param port: Server port, default 5432.
    :param name: Profile name, default ``'default'``.
    :param connect_timeout: Connection timeout in seconds.
    :param verbose: Include SQL and parameters in wrapped errors; may expose secrets.
    :param application_name: Application name reported to PostgreSQL.
    :param ttl: Lifetime of a pooled connection in seconds, checked on acquisition.
    :param max_connections: Maximum retained idle connections, not an active limit.
    :param default_rowfactory: Psycopg row factory used by new sessions.
    :param cursor_factory: If provided, overrides ``default_rowfactory``.
    :param client_encoding: PostgreSQL client encoding, or None to leave it unset.
        This also affects successful sessions and may help decode connection errors
        when their actual encoding is known.
    :ivar configs: Shared mapping of profile names to connection settings.
    """
    configs = {}

    def __init__(self, databasename=None, username=None, password=None, hostname=None, port=5432,
                 name='default', connect_timeout=10, verbose=False,
                 application_name='python', ttl=10, max_connections=10,
                 default_rowfactory=dict_row, cursor_factory=None, client_encoding=None):
        if cursor_factory is not None:
            default_rowfactory = cursor_factory

        if databasename is not None:
            self.configs[name] = {
                'dbname': databasename,
                'user': username,
                'dsn': make_conninfo(
                    dbname=databasename,
                    user=username,
                    password=password,
                    host=hostname,
                    port=port,
                    connect_timeout=connect_timeout,
                    application_name=application_name,
                    client_encoding=client_encoding
                ),
                'ttl': ttl,
                'default_rowfactory': default_rowfactory,
                'max_connections': max_connections,
                'verbose': verbose
            }

    def __getitem__(self, item):
        return self.configs[item]

    def __setitem__(self, key, value):
        self.configs[key] = value

    def __contains__(self, item):
        return item in self.configs

    def __len__(self):
        return len(self.configs)

    def get(self, item, default=None):
        return self.configs.get(item, default)

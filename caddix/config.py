from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row


class Configs:
    """
    Container for managing database configuration settings.

    The Configs class allows for easy creation, storage, and retrieval
    of database configuration settings. It supports setting up
    connections to PostgreSQL databases with customizable parameters
    such as timeout, application name, and maximum allowed connections.
    Multiple configurations can be managed under different names.

    :ivar configs: Stores all configurations with their respective names.
    :type configs: dict
    """
    configs = {}

    def __init__(self, databasename=None, username=None, password=None, hostname=None, port=5432,
                 name='default', connect_timeout=10, verbose=False,
                 application_name='python', ttl=10, max_connections=10,
                 default_rowfactory=dict_row, cursor_factory=None):
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
                    application_name=application_name
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

import queue
import time

import psycopg
from psycopg.pq import TransactionStatus

from .config import Configs


class PGPool:
    """
    Manages connections to a PostgreSQL database using a configurable connection pooling mechanism.

    This class provides a pooling mechanism for managing PostgreSQL database connections, which
    ensures that connections can be efficiently reused. It supports configurations that define
    connection details and time-to-live (TTL) values for individual connections. The pooling mechanism
    is implemented using Python's `queue.Queue` for thread-safety when accessing pooled connections.

    :ivar configname: The name of the configuration to use for the database connection.
    :type configname: str
    :ivar queue: A thread-safe queue used to store and manage connections for the specified configuration.
    :type queue: queue.Queue
    :ivar con: The current database connection object from the pool. A new connection may be created
               if no valid connection exists or if the TTL has expired.
    :type con: psycopg.Connection
    :ivar expire: The expiration time for the current connection. Connections are assigned a TTL
                  after which they are refreshed.
    :type expire: float
    """
    queues = {}

    def __init__(self, configname='default'):
        self.configname = configname
        if configname not in Configs.configs:
            raise KeyError(f"Database configuration '{configname}' not found. Please register it via caddix.Setup(...) first.")
        cnf = Configs.configs[configname]
        dsn = cnf['dsn']
        ttl = cnf.get('ttl', 10)
        max_connections = cnf.get('max_connections', 10)
        self.queue = self.queues.setdefault(configname, queue.Queue(maxsize=max_connections))

        self.con = None
        self.expire = None

        while True:
            try:
                con, expire = self.queue.get_nowait()
                # Discard closed or broken connections
                if con.closed or getattr(con, 'broken', False):
                    continue
                # Discard expired connections
                if expire < time.time():
                    try:
                        con.close()
                    except psycopg.Error:
                        pass
                    continue
                # Ensure clean transaction state
                try:
                    if con.info.transaction_status != TransactionStatus.IDLE:
                        con.rollback()
                except psycopg.Error:
                    try:
                        con.close()
                    except psycopg.Error:
                        pass
                    continue

                self.con = con
                self.expire = expire
                break
            except queue.Empty:
                self.con = psycopg.connect(conninfo=dsn)
                self.expire = time.time() + ttl
                break

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release(self.con, self.expire)

    def release(self, con, expire):
        if con is None or con.closed or getattr(con, 'broken', False):
            return
        try:
            self.queue.put_nowait((con, expire))
        except queue.Full:
            try:
                con.close()
            except psycopg.Error:
                pass

    def single_connect(self):
        return psycopg.connect(conninfo=Configs.configs[self.configname]['dsn'])

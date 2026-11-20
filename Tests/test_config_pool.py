import time
import threading
import unittest
import psycopg
from psycopg.rows import dict_row, tuple_row

import caddix
from caddix.config import Configs
from caddix.pool import PGPool


class TestConfigAndPool(unittest.TestCase):

    def test_setup_single_and_multi_config(self):
        # Default config
        caddix.Setup(
            databasename='caddix',
            hostname='localhost',
            username='caddix',
            password='caddix',
            verbose=True,
            ttl=5,
            max_connections=3
        )
        self.assertIn('default', caddix.Setup.configs)
        self.assertEqual(caddix.Setup.configs['default']['dbname'], 'caddix')
        self.assertEqual(caddix.Setup.configs['default']['user'], 'caddix')
        self.assertEqual(caddix.Setup.configs['default']['max_connections'], 3)
        self.assertEqual(caddix.Setup.configs['default']['ttl'], 5)

        # Secondary named config
        caddix.Setup(
            name='analytics_db',
            databasename='caddix',
            hostname='localhost',
            username='caddix',
            password='caddix',
            verbose=False,
            ttl=10,
            max_connections=10,
            cursor_factory=tuple_row
        )
        self.assertIn('analytics_db', caddix.Setup.configs)
        self.assertEqual(caddix.Setup.configs['analytics_db']['verbose'], False)
        self.assertEqual(caddix.Setup.configs['analytics_db']['default_rowfactory'], tuple_row)

    def test_dsn_escaping_special_characters(self):
        caddix.Setup(
            name='complex_auth',
            databasename='caddix',
            hostname='localhost',
            username='caddix',
            password='complex\'password"with spaces & symbols @#$%',
            verbose=True
        )
        dsn = caddix.Setup.configs['complex_auth']['dsn']
        self.assertIn("user=caddix", dsn)
        self.assertIn("dbname=caddix", dsn)
        self.assertIn("password='complex\\'password\"with spaces & symbols @#$%'", dsn)

    def test_configs_store_dict_interface(self):
        configs = Configs()
        configs['primary'] = {'dbname': 'db1', 'dsn': 'dbname=db1'}
        self.assertIn('primary', configs)
        self.assertEqual(configs['primary']['dbname'], 'db1')
        self.assertEqual(len(configs), len(Configs.configs))

    def test_pool_connection_creation_and_reuse(self):
        caddix.Setup(
            name='pool_test',
            databasename='caddix',
            hostname='localhost',
            username='caddix',
            password='caddix',
            max_connections=5,
            ttl=10
        )
        
        # Acquire connection via DatabaseSession
        with caddix.DatabaseSession('pool_test') as db1:
            con1_id = id(db1.con)
            db1.execute("SELECT 1")

        # Acquire again - should reuse the same connection
        with caddix.DatabaseSession('pool_test') as db2:
            con2_id = id(db2.con)
            db2.execute("SELECT 1")

        self.assertEqual(con1_id, con2_id)

    def test_pool_ttl_expiration(self):
        caddix.Setup(
            name='pool_ttl_test',
            databasename='caddix',
            hostname='localhost',
            username='caddix',
            password='caddix',
            max_connections=5,
            ttl=1  # 1 second TTL
        )
        
        with caddix.DatabaseSession('pool_ttl_test') as db1:
            con1_id = id(db1.con)

        # Wait for TTL to expire
        time.sleep(1.2)

        # Getting connection after TTL expired should discard old and create a fresh one
        with caddix.DatabaseSession('pool_ttl_test') as db2:
            con2_id = id(db2.con)

        self.assertNotEqual(con1_id, con2_id)

    def test_pool_thread_safety(self):
        caddix.Setup(
            name='pool_thread_test',
            databasename='caddix',
            hostname='localhost',
            username='caddix',
            password='caddix',
            max_connections=10,
            ttl=10
        )

        errors = []
        acquired_conns = []

        def worker():
            try:
                for _ in range(5):
                    with caddix.DatabaseSession('pool_thread_test') as db:
                        acquired_conns.append(id(db.con))
                        db.execute("SELECT 1")
                        res = db.fetchone()
                        if list(res.values())[0] != 1:
                            errors.append(f"Unexpected result: {res}")
                    time.sleep(0.01)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Thread safety errors occurred: {errors}")
        self.assertGreater(len(acquired_conns), 0)


if __name__ == '__main__':
    unittest.main()

"""Opt-in PostgreSQL integration tests: CADDIX_STRESS=1 python -m pytest Tests/test_stress.py.

Connection settings use PGDATABASE, PGHOST, PGPORT, PGUSER and PGPASSWORD,
falling back to the local test database used by the existing integration tests.
"""

import os
import queue
import random
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import caddix
from caddix.config import Configs
from caddix.pool import PGPool
from psycopg.types.numeric import Int4


@unittest.skipUnless(os.environ.get('CADDIX_STRESS') == '1', 'set CADDIX_STRESS=1 to run PostgreSQL stress tests')
class TestStressIntegration(unittest.TestCase):

    def setUp(self):
        suffix = uuid4().hex
        self.profile = 'stress_' + suffix
        self.table = 'public.caddix_stress_' + suffix
        self.procedure = 'public.caddix_stress_proc_' + suffix
        caddix.Setup(
            name=self.profile,
            databasename=os.environ.get('PGDATABASE', 'caddix'),
            hostname=os.environ.get('PGHOST', 'localhost'),
            port=int(os.environ.get('PGPORT', '5432')),
            username=os.environ.get('PGUSER', 'caddix'),
            password=os.environ.get('PGPASSWORD', 'caddix'),
            connect_timeout=5,
            max_connections=4,
            ttl=300,
        )
        self.addCleanup(self.cleanup_pool)
        with caddix.DatabaseSession(self.profile) as db:
            db.execute(f'CREATE TABLE {self.table} (worker integer, seq integer, payload text, PRIMARY KEY (worker, seq))')
            db.execute(f'CREATE PROCEDURE {self.procedure}() LANGUAGE plpgsql AS $$ BEGIN NULL; END $$')
            db.commit()
        self.addCleanup(self.cleanup_table)

    def cleanup_table(self):
        with caddix.DatabaseSession(self.profile) as db:
            db.execute(f'DROP PROCEDURE IF EXISTS {self.procedure}()')
            db.execute(f'DROP TABLE {self.table}')
            db.commit()

    def cleanup_pool(self):
        pool = PGPool.queues.pop(self.profile, None)
        try:
            if pool is not None:
                while True:
                    try:
                        con, _ = pool.get_nowait()
                    except queue.Empty:
                        break
                    con.close()
        finally:
            Configs.configs.pop(self.profile, None)

    def mixed_workload(self, worker_id):
        rng = random.Random(73129 + worker_id)
        expected = {}
        actions = ['crud', 'batch', 'fetch', 'function', 'metadata', 'error']
        for round_id in range(8):
            rng.shuffle(actions)
            for action in actions:
                seq = round_id * 10 + actions.index(action)
                payload = f"w{worker_id}-r{round_id}-'\\\n{rng.randrange(10000)}"
                with caddix.DatabaseSession(self.profile) as db:
                    if action == 'crud':
                        self.assertEqual(db.insert(self.table, returning=['payload'], worker=worker_id,
                                                   seq=seq, payload=payload), {'payload': payload})
                        self.assertTrue(db.exists(self.table, worker=worker_id, seq=seq))
                        self.assertEqual(db.select_scalar(self.table, 'payload', worker=worker_id, seq=seq), payload)
                        updated = payload + '-updated'
                        self.assertEqual(db.update(self.table, values={'payload': updated}, returning=['payload'],
                                                   worker=worker_id, seq=seq), [{'payload': updated}])
                        if round_id % 3 == 0:
                            self.assertEqual(db.delete(self.table, returning=['payload'], worker=worker_id,
                                                       seq=seq), [{'payload': updated}])
                        elif round_id % 3 == 1:
                            db.commit()
                            expected[seq] = updated
                        else:
                            db.rollback()
                        self.assertEqual(db.select_one(self.table, worker=worker_id, seq=seq),
                                         {'worker': worker_id, 'seq': seq, 'payload': expected[seq]}
                                         if seq in expected else None)
                    elif action == 'batch':
                        batch_seq = 10000 + seq * 10
                        records = [{'worker': worker_id, 'seq': batch_seq + i, 'payload': payload}
                                   for i in range(3)]
                        self.assertEqual(db.insert_batch(self.table, records), 3)
                        updates = [dict(row, payload=payload + '-batch') for row in records[:2]]
                        self.assertEqual(db.update_batch(self.table, updates, ['payload'], ['worker', 'seq']), 2)
                        upserts = [dict(records[0], payload=payload + '-upsert'),
                                   dict(records[2], seq=batch_seq + 3)]
                        self.assertEqual(db.upsert_batch(self.table, upserts, ['worker', 'seq']), 2)
                        self.assertEqual(db.select_dict(self.table, 'seq', 'payload', worker=worker_id,
                                                        seq=batch_seq), {batch_seq: payload + '-upsert'})
                        self.assertEqual(db.select_list(self.table, 'payload', worker=worker_id,
                                                        seq=batch_seq + 1), [payload + '-batch'])
                        self.assertEqual(db.select_many(self.table, 1, worker=worker_id, seq=batch_seq + 2),
                                         [records[2]])
                        if round_id % 2:
                            db.rollback()
                        else:
                            db.commit()
                            expected.update({batch_seq: payload + '-upsert', batch_seq + 1: payload + '-batch',
                                             batch_seq + 2: payload, batch_seq + 3: payload})
                    elif action == 'fetch':
                        query = 'SELECT n, n * 2 AS doubled FROM generate_series(1, 3) AS n ORDER BY n'
                        db.execute(query)
                        self.assertEqual(db.fetchone(), {'n': 1, 'doubled': 2})
                        self.assertEqual(db.fetchmany(1), [{'n': 2, 'doubled': 4}])
                        self.assertEqual(db.fetchall(), [{'n': 3, 'doubled': 6}])
                        self.assertIsNone(db.fetchone())
                        self.assertEqual(db.execute_fetchone(query), {'n': 1, 'doubled': 2})
                        self.assertEqual(len(db.execute_fetchall(query)), 3)
                        self.assertEqual(db.execute_fetchmany(query, 2),
                                         [{'n': 1, 'doubled': 2}, {'n': 2, 'doubled': 4}])
                        self.assertEqual(db.execute_fetchscalar('SELECT %s::int', worker_id), worker_id)
                        self.assertEqual(db.execute_fetchlist(query), [1, 2, 3])
                        self.assertEqual(db.execute_fetchdict(query), {1: 2, 2: 4, 3: 6})
                        db.executemany(f'INSERT INTO {self.table} (worker, seq, payload) VALUES (%s, %s, %s)',
                                       [(worker_id, seq, payload)])
                        db.rollback()
                    elif action == 'function':
                        self.assertEqual(db.func_scalar('pg_catalog.abs', -worker_id - 1), worker_id + 1)
                        self.assertEqual(db.func_list('pg_catalog.generate_series', Int4(1), Int4(3)), [1, 2, 3])
                        self.assertEqual(db.func_one('pg_catalog.generate_series', Int4(1), Int4(1)), {'generate_series': 1})
                        self.assertEqual(db.func_many('pg_catalog.generate_series', 2, Int4(1), Int4(3)),
                                         [{'generate_series': 1}, {'generate_series': 2}])
                        self.assertEqual(db.func_all('pg_catalog.generate_series', Int4(1), Int4(2)),
                                         [{'generate_series': 1}, {'generate_series': 2}])
                        self.assertEqual(db.call_func('pg_catalog.generate_series', Int4(1), Int4(1)), [{'generate_series': 1}])
                        self.assertEqual(db.call_function('pg_catalog.generate_series', Int4(1), Int4(1)), [{'generate_series': 1}])
                        self.assertEqual(db.func_dict('pg_catalog.json_each_text', '{"a":"b"}'), {'a': 'b'})
                        self.assertIsNone(db.call_proc(self.procedure))
                        self.assertIsNone(db.call_procedure(self.procedure))
                    elif action == 'metadata':
                        self.assertEqual(set(db.tabledesc(self.table, asdict=True)), {'worker', 'seq', 'payload'})
                        self.assertFalse(db.exists(self.table, worker=worker_id, seq=-1))
                        self.assertEqual(db.select_many(self.table, 1, worker=worker_id, seq=-1), [])
                        self.assertEqual(db.select_list(self.table, 'seq', worker=worker_id, seq=-1), [])
                        self.assertEqual(db.select_dict(self.table, 'seq', 'payload', worker=worker_id, seq=-1), {})
                    else:
                        db.insert(self.table, worker=worker_id, seq=seq, payload=payload)
                        with self.assertRaises(caddix.CaddixError):
                            db.execute('SELECT 1 / 0')
                        db.rollback()
                        self.assertFalse(db.exists(self.table, worker=worker_id, seq=seq))
        return {(worker_id, seq, value) for seq, value in expected.items()}

    def assert_mixed_workload(self, parallel):
        workers = 8
        if parallel:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                results = list(executor.map(self.mixed_workload, range(workers)))
        else:
            results = [self.mixed_workload(worker) for worker in range(workers)]
        expected = set().union(*results)
        with caddix.DatabaseSession(self.profile) as db:
            rows = db.select_all(self.table)
        self.assertEqual(len(rows), len(expected))
        self.assertEqual({(row['worker'], row['seq'], row['payload']) for row in rows}, expected)

    def test_seeded_mixed_sequential_workload(self):
        self.assert_mixed_workload(parallel=False)

    def test_seeded_mixed_parallel_workload(self):
        self.assert_mixed_workload(parallel=True)

    def test_parallel_crud_and_transaction_rollback(self):
        workers = 12
        iterations = 100
        barrier = threading.Barrier(workers, timeout=15)

        def worker(worker_id):
            with caddix.DatabaseSession(self.profile) as db:
                barrier.wait()
                for seq in range(iterations):
                    db.insert(self.table, worker=worker_id, seq=seq, payload='initial')
                    self.assertEqual(db.select_one(self.table, worker=worker_id, seq=seq)['payload'], 'initial')
                    db.update(self.table, values={'payload': 'updated'}, worker=worker_id, seq=seq)
                    if seq % 2:
                        db.rollback()
                    else:
                        db.commit()
                db.delete(self.table, worker=worker_id, seq=0)
                db.commit()
                db.insert(self.table, worker=worker_id, seq=99, payload='uncommitted')

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(worker, worker_id) for worker_id in range(workers)]
            for future in futures:
                future.result()

        with caddix.DatabaseSession(self.profile) as db:
            rows = db.select_all(self.table)
        actual = {(row['worker'], row['seq'], row['payload']) for row in rows}
        expected = {(worker, seq, 'updated') for worker in range(workers) for seq in range(2, iterations, 2)}
        self.assertEqual(len(rows), len(expected))
        self.assertEqual(actual, expected)

    def test_pool_reuse_after_failed_and_uncommitted_transactions(self):
        with caddix.DatabaseSession(self.profile) as db:
            connection = db.con
            backend_pid = db.execute_fetchscalar('SELECT pg_backend_pid()')
            db.insert(self.table, worker=1, seq=1, payload='discarded')

        for iteration in range(400):
            with caddix.DatabaseSession(self.profile) as db:
                self.assertIs(db.con, connection)
                self.assertEqual(db.execute_fetchscalar('SELECT pg_backend_pid()'), backend_pid)
                self.assertIsNone(db.select_one(self.table, worker=1, seq=1))
                db.insert(self.table, worker=1, seq=iteration + 10, payload='temporary')
                db.rollback()

        with self.assertRaises(caddix.CaddixError):
            with caddix.DatabaseSession(self.profile) as db:
                db.insert(self.table, worker=2, seq=1, payload='before error')
                db.execute('SELECT 1 / 0')

        with caddix.DatabaseSession(self.profile) as db:
            self.assertIs(db.con, connection)
            self.assertEqual(db.execute_fetchscalar('SELECT pg_backend_pid()'), backend_pid)
            self.assertEqual(db.select_all(self.table), [])
            db.insert(self.table, worker=3, seq=1, payload='committed')
            db.commit()

        with caddix.DatabaseSession(self.profile) as db:
            self.assertEqual(db.select_one(self.table, worker=3, seq=1)['payload'], 'committed')


if __name__ == '__main__':
    unittest.main()

import time
import threading
import unittest
import caddix
from caddix.base import DatabaseSession


class TestStressAndConcurrency(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        caddix.Setup(
            name='stress_pool',
            databasename='tusker',
            hostname='localhost',
            username='tusker',
            password='tusker',
            verbose=True,
            max_connections=15,
            ttl=30
        )

    def setUp(self):
        with DatabaseSession('stress_pool') as db:
            db.execute("DROP TABLE IF EXISTS test_stress_table CASCADE")
            db.execute("""
                CREATE TABLE test_stress_table (
                    id serial primary key,
                    worker_id int,
                    seq int,
                    payload text,
                    created_at timestamp default current_timestamp
                )
            """)
            db.commit()

    def test_high_concurrency_multi_threaded_crud(self):
        worker_count = 20
        ops_per_worker = 10
        errors = []

        def worker(w_id):
            try:
                for seq in range(ops_per_worker):
                    # Half of workers commit, half rollback
                    should_commit = (seq % 2 == 0)
                    with DatabaseSession('stress_pool') as db:
                        db.insert(
                            'test_stress_table',
                            worker_id=w_id,
                            seq=seq,
                            payload=f"Payload_W{w_id}_S{seq}"
                        )
                        if should_commit:
                            db.commit()

                    # Query random records
                    with DatabaseSession('stress_pool') as db:
                        _ = db.select_all('test_stress_table', worker_id=w_id)
            except Exception as e:
                errors.append(f"Worker {w_id} failed: {e}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(worker_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Stress test errors occurred: {errors}")

        # Verify persisted rows match the committed operations
        with DatabaseSession('stress_pool') as db:
            total_committed = db.execute_fetchscalar("SELECT COUNT(*) FROM test_stress_table")
            expected = worker_count * (ops_per_worker // 2)
            self.assertEqual(total_committed, expected)

    def test_rapid_session_recycling_loop(self):
        # Rapidly create and close 200 sessions to verify pool recycling and memory stability
        for i in range(200):
            with DatabaseSession('stress_pool') as db:
                val = db.execute_fetchscalar("SELECT %s", (i,))
                self.assertEqual(val, i)

    def test_large_batch_insert_streaming_stress(self):
        # 5,000 records inserted in a single COPY stream
        record_count = 5000
        batch_data = [
            {
                'worker_id': i % 10,
                'seq': i,
                'payload': f"Bulk_Stream_Data_Item_{i}_" + ("X" * 50)
            }
            for i in range(record_count)
        ]

        start_time = time.time()
        with DatabaseSession('stress_pool') as db:
            db.insert_batch('test_stress_table', batch_data)
            db.commit()
        duration = time.time() - start_time

        with DatabaseSession('stress_pool') as db:
            count = db.execute_fetchscalar("SELECT COUNT(*) FROM test_stress_table WHERE payload LIKE 'Bulk_Stream_Data_Item_%'")
            self.assertEqual(count, record_count)

        # Batch insert of 5,000 rows with COPY should complete very quickly (typically < 0.5s)
        self.assertLess(duration, 5.0, f"COPY batch insert took too long: {duration:.2f}s")

    def test_concurrent_reads_and_writes_isolation(self):
        stop_event = threading.Event()
        read_errors = []
        write_errors = []

        def reader():
            while not stop_event.is_set():
                try:
                    with DatabaseSession('stress_pool') as db:
                        rows = db.select_all('test_stress_table')
                        # Sanity check: every row must have worker_id
                        for r in rows:
                            if 'worker_id' not in r:
                                read_errors.append("Missing worker_id in read row")
                    time.sleep(0.005)
                except Exception as e:
                    read_errors.append(str(e))

        def writer():
            for i in range(20):
                try:
                    with DatabaseSession('stress_pool') as db:
                        db.insert('test_stress_table', worker_id=999, seq=i, payload=f"IsolatedWrite_{i}")
                        db.commit()
                    time.sleep(0.005)
                except Exception as e:
                    write_errors.append(str(e))

        readers = [threading.Thread(target=reader) for _ in range(4)]
        writers = [threading.Thread(target=writer) for _ in range(3)]

        for r in readers:
            r.start()
        for w in writers:
            w.start()

        for w in writers:
            w.join()

        stop_event.set()
        for r in readers:
            r.join()

        self.assertEqual(len(read_errors), 0, f"Read errors: {read_errors}")
        self.assertEqual(len(write_errors), 0, f"Write errors: {write_errors}")


if __name__ == '__main__':
    unittest.main()

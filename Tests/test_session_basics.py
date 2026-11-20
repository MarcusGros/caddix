import unittest
import caddix
from caddix.base import DatabaseSession, CaddixError, CaddixSessionError
from caddix.utils import get_column_names


class TestSessionBasics(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        caddix.Setup(
            databasename='tusker',
            hostname='localhost',
            username='tusker',
            password='tusker',
            verbose=True
        )

    def setUp(self):
        with DatabaseSession() as db:
            db.execute("DROP TABLE IF EXISTS test_session_table CASCADE")
            db.execute("""
                CREATE TABLE test_session_table (
                    id serial primary key,
                    title text,
                    is_active bool default true,
                    score int,
                    notes text
                )
            """)
            db.execute("INSERT INTO test_session_table (title, is_active, score, notes) VALUES ('Item A', true, 100, 'first')")
            db.execute("INSERT INTO test_session_table (title, is_active, score, notes) VALUES ('Item B', false, 200, 'second')")
            db.execute("INSERT INTO test_session_table (title, is_active, score, notes) VALUES ('Item C', true, 300, 'third')")
            db.execute("INSERT INTO test_session_table (title, is_active, score, notes) VALUES ('Item D', true, 400, 'fourth')")
            db.commit()

    def test_context_manager_auto_rollback(self):
        with DatabaseSession() as db:
            db.execute("INSERT INTO test_session_table (title, is_active, score) VALUES ('Uncommitted', true, 999)")
            # Exiting without db.commit()

        # In a new session, verify the record was rolled back
        with DatabaseSession() as db:
            db.execute("SELECT * FROM test_session_table WHERE title = 'Uncommitted'")
            self.assertIsNone(db.fetchone())

    def test_explicit_commit_persists_data(self):
        with DatabaseSession() as db:
            db.execute("INSERT INTO test_session_table (title, is_active, score) VALUES ('Committed', true, 777)")
            db.commit()

        with DatabaseSession() as db:
            db.execute("SELECT score FROM test_session_table WHERE title = 'Committed'")
            self.assertEqual(db.fetchscalar(), 777)

    def test_manual_rollback(self):
        with DatabaseSession() as db:
            db.execute("INSERT INTO test_session_table (title, is_active, score) VALUES ('WillRollback', true, 888)")
            db.rollback()
            db.execute("SELECT * FROM test_session_table WHERE title = 'WillRollback'")
            self.assertIsNone(db.fetchone())

    def test_raw_fetch_methods(self):
        with DatabaseSession() as db:
            db.execute("SELECT * FROM test_session_table ORDER BY id")
            
            # fetchone
            first = db.fetchone()
            self.assertEqual(first['title'], 'Item A')
            self.assertEqual(first['score'], 100)

            # fetchmany
            next_two = db.fetchmany(2)
            self.assertEqual(len(next_two), 2)
            self.assertEqual(next_two[0]['title'], 'Item B')
            self.assertEqual(next_two[1]['title'], 'Item C')

            # fetchall remainder
            rest = db.fetchall()
            self.assertEqual(len(rest), 1)
            self.assertEqual(rest[0]['title'], 'Item D')

    def test_fetchscalar_and_fetchlist(self):
        with DatabaseSession() as db:
            # fetchscalar
            db.execute("SELECT score FROM test_session_table WHERE id = 1")
            self.assertEqual(db.fetchscalar(), 100)

            # fetchlist
            db.execute("SELECT title FROM test_session_table ORDER BY id")
            self.assertEqual(db.fetchlist(), ['Item A', 'Item B', 'Item C', 'Item D'])

    def test_fetchdict(self):
        with DatabaseSession() as db:
            db.execute("SELECT title, score FROM test_session_table ORDER BY id")
            d = db.fetchdict()
            self.assertEqual(d, {
                'Item A': 100,
                'Item B': 200,
                'Item C': 300,
                'Item D': 400
            })

    def test_execute_and_fetch_convenience_methods(self):
        with DatabaseSession() as db:
            # execute_fetchone
            one = db.execute_fetchone("SELECT * FROM test_session_table WHERE id = 2")
            self.assertEqual(one['title'], 'Item B')

            # execute_fetchall
            all_rows = db.execute_fetchall("SELECT * FROM test_session_table ORDER BY id")
            self.assertEqual(len(all_rows), 4)

            # execute_fetchmany
            many_rows = db.execute_fetchmany("SELECT * FROM test_session_table ORDER BY id", 3)
            self.assertEqual(len(many_rows), 3)

            # execute_fetchscalar
            scalar = db.execute_fetchscalar("SELECT COUNT(*) FROM test_session_table")
            self.assertEqual(scalar, 4)

            # execute_fetchlist
            lst = db.execute_fetchlist("SELECT score FROM test_session_table ORDER BY id")
            self.assertEqual(lst, [100, 200, 300, 400])

            # execute_fetchdict
            dct = db.execute_fetchdict("SELECT title, score FROM test_session_table ORDER BY id")
            self.assertEqual(dct['Item C'], 300)

    def test_parameterized_queries_safety(self):
        with DatabaseSession() as db:
            # Positional parameter
            db.execute("SELECT title FROM test_session_table WHERE score = %s", (200,))
            self.assertEqual(db.fetchscalar(), 'Item B')

            # Named parameter via kwargs
            db.execute("SELECT title FROM test_session_table WHERE score = %(sc)s AND is_active = %(act)s", sc=300, act=True)
            self.assertEqual(db.fetchscalar(), 'Item C')

    def test_schema_introspection_exists(self):
        with DatabaseSession() as db:
            self.assertTrue(db.exists('test_session_table'))
            self.assertTrue(db.exists('public.test_session_table'))
            self.assertTrue(db.exists('test_session_table', title='Item A'))
            self.assertFalse(db.exists('test_session_table', title='Non-Existent'))
            self.assertFalse(db.exists('non_existent_table_xyz'))

    def test_schema_introspection_tabledesc(self):
        with DatabaseSession() as db:
            desc_dict = db.tabledesc('test_session_table', asdict=True)
            self.assertIn('id', desc_dict)
            self.assertIn('title', desc_dict)
            self.assertIn('is_active', desc_dict)
            self.assertIn('score', desc_dict)
            self.assertEqual(desc_dict['score']['type'], 'integer')
            self.assertEqual(desc_dict['title']['type'], 'text')

            desc_rows = db.tabledesc('test_session_table', asdict=False)
            col_names = [r['name'] for r in desc_rows]
            self.assertIn('title', col_names)

    def test_get_column_names_helper(self):
        with DatabaseSession() as db:
            cols = get_column_names(db, 'test_session_table')
            self.assertListEqual(sorted(cols), sorted(['id', 'title', 'is_active', 'score', 'notes']))


if __name__ == '__main__':
    unittest.main()

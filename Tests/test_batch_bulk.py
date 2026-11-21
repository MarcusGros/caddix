import unittest
import caddix
from caddix.base import DatabaseSession


class TestBatchAndBulk(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        caddix.Setup(
            databasename='caddix',
            hostname='localhost',
            username='caddix',
            password='caddix',
            verbose=True
        )

    def setUp(self):
        with DatabaseSession() as db:
            db.execute("DROP TABLE IF EXISTS test_batch_table CASCADE")
            db.execute("""
                CREATE TABLE test_batch_table (
                    id int primary key,
                    code text,
                    label text,
                    score int,
                    description text
                )
            """)
            db.commit()

    def test_insert_batch_basic(self):
        records = [
            {'id': 1, 'code': 'A1', 'label': 'Alpha', 'score': 100, 'description': 'First'},
            {'id': 2, 'code': 'B2', 'label': 'Beta', 'score': 200, 'description': 'Second'},
            {'id': 3, 'code': 'C3', 'label': 'Gamma', 'score': 300, 'description': 'Third'},
        ]
        with DatabaseSession() as db:
            db.insert_batch('test_batch_table', records)
            db.commit()

        with DatabaseSession() as db:
            count = db.execute_fetchscalar("SELECT COUNT(*) FROM test_batch_table")
            self.assertEqual(count, 3)
            row = db.select_one('test_batch_table', id=2)
            self.assertEqual(row['code'], 'B2')
            self.assertEqual(row['label'], 'Beta')

    def test_insert_batch_with_nulls(self):
        records = [
            {'id': 10, 'code': 'X1', 'label': 'NullScore', 'score': None, 'description': None},
            {'id': 20, 'code': 'X2', 'label': 'WithValue', 'score': 999, 'description': 'Has desc'},
        ]
        with DatabaseSession() as db:
            db.insert_batch('test_batch_table', records)
            db.commit()

        with DatabaseSession() as db:
            r1 = db.select_one('test_batch_table', id=10)
            self.assertIsNone(r1['score'])
            self.assertIsNone(r1['description'])

            r2 = db.select_one('test_batch_table', id=20)
            self.assertEqual(r2['score'], 999)

    def test_insert_batch_special_characters_escaping(self):
        records = [
            {'id': 100, 'code': 'TAB\tTEST', 'label': 'Line1\nLine2\r\nLine3', 'score': 1, 'description': 'Backslash\\and"quotes\'and emojis 🔥🚀🎉'},
            {'id': 101, 'code': 'JSON{"k":"v"}', 'label': '<xml>data</xml>', 'score': 2, 'description': 'Special ; -- DROP TABLE;'}
        ]
        with DatabaseSession() as db:
            db.insert_batch('test_batch_table', records)
            db.commit()

        with DatabaseSession() as db:
            r1 = db.select_one('test_batch_table', id=100)
            self.assertEqual(r1['code'], 'TAB\tTEST')
            self.assertEqual(r1['label'], 'Line1\nLine2\r\nLine3')
            self.assertEqual(r1['description'], 'Backslash\\and"quotes\'and emojis 🔥🚀🎉')

            r2 = db.select_one('test_batch_table', id=101)
            self.assertEqual(r2['description'], 'Special ; -- DROP TABLE;')

    def test_update_batch(self):
        # Insert initial data
        initial = [
            {'id': 1, 'code': 'C1', 'label': 'Old1', 'score': 10, 'description': 'init'},
            {'id': 2, 'code': 'C2', 'label': 'Old2', 'score': 20, 'description': 'init'},
            {'id': 3, 'code': 'C3', 'label': 'Old3', 'score': 30, 'description': 'init'},
        ]
        with DatabaseSession() as db:
            db.insert_batch('test_batch_table', initial)
            db.commit()

        # Update batch with update_columns and where_columns
        updates = [
            {'id': 1, 'label': 'New1', 'score': 110},
            {'id': 3, 'label': 'New3', 'score': 330},
        ]
        with DatabaseSession() as db:
            db.update_batch('test_batch_table', updates, update_columns=['label', 'score'], where_columns=['id'])
            db.commit()

        with DatabaseSession() as db:
            r1 = db.select_one('test_batch_table', id=1)
            self.assertEqual(r1['label'], 'New1')
            self.assertEqual(r1['score'], 110)

            # Unchanged row 2
            r2 = db.select_one('test_batch_table', id=2)
            self.assertEqual(r2['label'], 'Old2')
            self.assertEqual(r2['score'], 20)

            # Updated row 3
            r3 = db.select_one('test_batch_table', id=3)
            self.assertEqual(r3['label'], 'New3')
            self.assertEqual(r3['score'], 330)

    def test_update_batch_check_changes(self):
        initial = [
            {'id': 1, 'code': 'C1', 'label': 'L1', 'score': 10, 'description': 'init'},
            {'id': 2, 'code': 'C2', 'label': 'L2', 'score': 20, 'description': 'init'},
        ]
        with DatabaseSession() as db:
            db.insert_batch('test_batch_table', initial)
            db.commit()

        # Update where id=1 is identical, id=2 is changed
        updates = [
            {'id': 1, 'label': 'L1', 'score': 10},
            {'id': 2, 'label': 'L2_CHANGED', 'score': 20},
        ]
        with DatabaseSession() as db:
            count = db.update_batch(
                'test_batch_table', updates,
                update_columns=['label', 'score'],
                where_columns=['id'],
                check_changes=True
            )
            self.assertEqual(count, 1)

    def test_upsert_batch_check_changes(self):
        initial = [
            {'id': 1, 'code': 'U1', 'label': 'Orig1', 'score': 100, 'description': 'd1'},
        ]
        with DatabaseSession() as db:
            db.insert_batch('test_batch_table', initial)
            db.commit()

        upsert_data = [
            {'id': 1, 'code': 'U1', 'label': 'Orig1', 'score': 100, 'description': 'd1'},
        ]
        with DatabaseSession() as db:
            # When check_changes=True and row is identical, DO UPDATE WHERE is false
            ret = db.upsert_batch(
                'test_batch_table',
                upsert_data,
                conflict_target=['id'],
                update_columns=['code', 'label', 'score'],
                returning=['id', 'code'],
                check_changes=True
            )
            # Returning clause for unchanged row affected by DO UPDATE WHERE false in PG
            self.assertEqual(len(ret), 0)

    def test_executemany_error_reporting(self):
        with DatabaseSession() as db:
            bad_values = [{'id': 'not_an_int', 'code': 'ERR'}]
            with self.assertRaises(caddix.CaddixError) as ctx:
                db.executemany("INSERT INTO test_batch_table (id, code) VALUES (%(id)s, %(code)s)", bad_values)
            err_msg = str(ctx.exception)
            self.assertIn('not_an_int', err_msg)
            self.assertIn('ERR', err_msg)

    def test_upsert_batch_on_conflict_update(self):
        initial = [
            {'id': 1, 'code': 'U1', 'label': 'Orig1', 'score': 100, 'description': 'd1'},
            {'id': 2, 'code': 'U2', 'label': 'Orig2', 'score': 200, 'description': 'd2'},
        ]
        with DatabaseSession() as db:
            db.insert_batch('test_batch_table', initial)
            db.commit()

        # Upsert: 1 exists (update), 3 is new (insert)
        upsert_data = [
            {'id': 1, 'code': 'U1_MOD', 'label': 'Modified1', 'score': 999, 'description': 'd1_mod'},
            {'id': 3, 'code': 'U3_NEW', 'label': 'New3', 'score': 300, 'description': 'd3'},
        ]
        with DatabaseSession() as db:
            db.upsert_batch(
                'test_batch_table',
                upsert_data,
                conflict_target=['id'],
                update_columns=['code', 'label', 'score']
            )
            db.commit()

        with DatabaseSession() as db:
            # 1 should be updated (except description wasn't in update_columns)
            r1 = db.select_one('test_batch_table', id=1)
            self.assertEqual(r1['code'], 'U1_MOD')
            self.assertEqual(r1['label'], 'Modified1')
            self.assertEqual(r1['score'], 999)
            self.assertEqual(r1['description'], 'd1')

            # 3 should be inserted
            r3 = db.select_one('test_batch_table', id=3)
            self.assertEqual(r3['code'], 'U3_NEW')
            self.assertEqual(r3['label'], 'New3')

    def test_upsert_batch_on_conflict_nothing(self):
        initial = [
            {'id': 1, 'code': 'N1', 'label': 'Orig1', 'score': 10, 'description': 'd1'}
        ]
        with DatabaseSession() as db:
            db.insert_batch('test_batch_table', initial)
            db.commit()

        # Conflict -> do nothing (update_columns=None)
        upsert_data = [
            {'id': 1, 'code': 'N1_CHANGED', 'label': 'ShouldNotChange', 'score': 999, 'description': 'd1'},
            {'id': 2, 'code': 'N2', 'label': 'ShouldBeInserted', 'score': 20, 'description': 'd2'}
        ]
        with DatabaseSession() as db:
            db.upsert_batch(
                'test_batch_table',
                upsert_data,
                conflict_target='id',
                update_columns=None
            )
            db.commit()

        with DatabaseSession() as db:
            r1 = db.select_one('test_batch_table', id=1)
            self.assertEqual(r1['label'], 'Orig1')
            self.assertEqual(r1['score'], 10)

            r2 = db.select_one('test_batch_table', id=2)
            self.assertEqual(r2['label'], 'ShouldBeInserted')


    def test_insert_batch_error_reporting(self):
        with DatabaseSession() as db:
            bad_records = [{'id': 'not_an_int', 'code': 'ERR'}]
            with self.assertRaises(caddix.CaddixError) as ctx:
                db.insert_batch('test_batch_table', bad_records)
            self.assertTrue(isinstance(ctx.exception, caddix.CaddixError))


if __name__ == '__main__':
    unittest.main()

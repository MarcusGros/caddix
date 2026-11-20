from decimal import Decimal
import unittest
import psycopg
import caddix
from caddix.base import DatabaseSession, CaddixError, CaddixSessionError


class TestProvocationAndEdgeCases(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        caddix.Setup(
            name='prov_test',
            databasename='tusker',
            hostname='localhost',
            username='tusker',
            password='tusker',
            verbose=True
        )

    def setUp(self):
        with DatabaseSession('prov_test') as db:
            db.execute("DROP TABLE IF EXISTS test_prov_table CASCADE")
            db.execute("""
                CREATE TABLE test_prov_table (
                    id serial primary key,
                    "select" text,
                    "where" text,
                    "col with space" text,
                    "col-with-dash" text,
                    big_text text,
                    num_val numeric(18, 6),
                    flag bool,
                    payload jsonb
                )
            """)
            db.commit()

    def test_reserved_sql_and_unusual_column_identifiers(self):
        with DatabaseSession('prov_test') as db:
            # Columns "select", "where", "col with space", "col-with-dash"
            row = db.insert(
                'test_prov_table',
                returning='*',
                _select='SELECT_VALUE',
                _where='WHERE_VALUE',
                **{
                    'col with space': 'space val',
                    'col-with-dash': 'dash val',
                    'num_val': 123456789.123456,
                    'flag': True
                }
            )
            self.assertEqual(row['select'], 'SELECT_VALUE')
            self.assertEqual(row['where'], 'WHERE_VALUE')
            self.assertEqual(row['col with space'], 'space val')
            self.assertEqual(row['col-with-dash'], 'dash val')
            self.assertEqual(row['num_val'], Decimal('123456789.123456'))
            db.commit()

        # Query using the strange column names in filters
        with DatabaseSession('prov_test') as db:
            found = db.select_one('test_prov_table', **{'col-with-dash': 'dash val'})
            self.assertIsNotNone(found)
            self.assertEqual(found['select'], 'SELECT_VALUE')

            found_space = db.select_one('test_prov_table', **{'col with space': 'space val'})
            self.assertIsNotNone(found_space)

    def test_extreme_and_large_payloads(self):
        large_string = "A" * 500_000  # 500 KB string
        emoji_unicode = "🌟🔥🚀 Unicode Test: ᚛᚛ 漢字 русский العربية 𝄞 𠜎 𠜱"

        with DatabaseSession('prov_test') as db:
            db.insert('test_prov_table', big_text=large_string, _select=emoji_unicode)
            db.commit()

        with DatabaseSession('prov_test') as db:
            row = db.select_one('test_prov_table', _select=emoji_unicode)
            self.assertIsNotNone(row)
            self.assertEqual(len(row['big_text']), 500_000)
            self.assertEqual(row['select'], emoji_unicode)

    def test_null_versus_empty_string_handling(self):
        with DatabaseSession('prov_test') as db:
            # Empty string vs NULL
            db.insert('test_prov_table', _select='', _where=None, num_val=None)
            db.commit()

        with DatabaseSession('prov_test') as db:
            row = db.select_one('test_prov_table', _select='')
            self.assertIsNotNone(row)
            self.assertEqual(row['select'], '')
            self.assertIsNone(row['where'])
            self.assertIsNone(row['num_val'])

    def test_empty_lists_and_dicts_in_batch_operations(self):
        with DatabaseSession('prov_test') as db:
            # insert_batch with empty list
            db.insert_batch('test_prov_table', [])
            
            # update_batch with empty list
            db.update_batch('test_prov_table', [], update_columns=['select'], where_columns=['id'])

            # upsert_batch with empty list
            db.upsert_batch('test_prov_table', [], conflict_target='id')

    def test_provocation_invalid_function_and_procedure_calls(self):
        with DatabaseSession('prov_test') as db:
            # 1. Non-existent function
            with self.assertRaises(CaddixError):
                db.func_scalar('definitely_non_existent_fn_12345')

            # 2. Non-existent procedure
            with self.assertRaises(CaddixError):
                db.call_proc('definitely_non_existent_proc_12345')

            db.rollback()

            # 3. Create function that intentionally raises an exception
            db.execute("""
            CREATE OR REPLACE FUNCTION prov_throw_error() RETURNS void AS $$
            BEGIN
                RAISE EXCEPTION 'Simulated PL/pgSQL Failure';
            END;
            $$ LANGUAGE plpgsql;
            """)
            db.commit()

            with self.assertRaises(CaddixError) as ctx:
                db.func_scalar('prov_throw_error')
            self.assertIn("Simulated PL/pgSQL Failure", str(ctx.exception))

    def test_transaction_recovery_after_mid_session_crash(self):
        # 1. First session fails midway through a dirty transaction
        try:
            with DatabaseSession('prov_test') as db1:
                db1.insert('test_prov_table', _select='should_not_exist')
                # Trigger syntax error
                db1.execute("MALFORMED SQL STATEMENT WHICH FAILS")
        except CaddixError:
            pass

        # 2. Second session borrowed from pool must be completely healthy and clean
        with DatabaseSession('prov_test') as db2:
            dirty = db2.select_one('test_prov_table', _select='should_not_exist')
            self.assertIsNone(dirty)
            # A fresh insert in clean session must succeed
            db2.insert('test_prov_table', _select='clean_recovery')
            db2.commit()

        # 3. Verify clean insert persisted
        with DatabaseSession('prov_test') as db3:
            self.assertTrue(db3.exists('test_prov_table', _select='clean_recovery'))
            saved = db3.select_one('test_prov_table', _select='clean_recovery')
            self.assertIsNotNone(saved)

    def test_invalid_parameter_types_provocation(self):
        with DatabaseSession('prov_test') as db:
            # func_many with None size
            with self.assertRaises(CaddixSessionError):
                db.func_many('prov_throw_error', None)

            # select_many with None or invalid size
            with self.assertRaises(CaddixSessionError):
                db.select_many('test_prov_table', None)


if __name__ == '__main__':
    unittest.main()

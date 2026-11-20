import unittest
from dataclasses import dataclass
import psycopg
from psycopg.rows import class_row, tuple_row

import caddix


@dataclass
class UserRow:
    id: int
    name: str


class TestFunctionsAndProcedures(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        caddix.Setup(databasename='tusker', hostname='localhost', username='tusker', password='tusker', verbose=True)
        with caddix.DatabaseSession() as db:
            db.execute("DROP TABLE IF EXISTS test_fn_proc_table CASCADE")
            db.execute("CREATE TABLE test_fn_proc_table (id serial primary key, val text)")

            # Scalar function
            db.execute("""
            CREATE OR REPLACE FUNCTION test_calc_add(a int, b int) RETURNS int AS $$
            BEGIN
                RETURN a + b;
            END;
            $$ LANGUAGE plpgsql;
            """)

            # Table function
            db.execute("""
            CREATE OR REPLACE FUNCTION test_get_users(min_id int DEFAULT 0)
            RETURNS TABLE(id int, name text) AS $$
            BEGIN
                RETURN QUERY SELECT 1, 'Alice'::text
                             WHERE 1 >= min_id
                             UNION ALL
                             SELECT 2, 'Bob'::text
                             WHERE 2 >= min_id
                             UNION ALL
                             SELECT 3, 'Charlie'::text
                             WHERE 3 >= min_id;
            END;
            $$ LANGUAGE plpgsql;
            """)

            # Single row returning table function
            db.execute("""
            CREATE OR REPLACE FUNCTION test_get_user_by_id(u_id int)
            RETURNS TABLE(id int, name text) AS $$
            BEGIN
                RETURN QUERY SELECT u_id, ('User ' || u_id)::text;
            END;
            $$ LANGUAGE plpgsql;
            """)

            # Set of scalars
            db.execute("""
            CREATE OR REPLACE FUNCTION test_get_id_list()
            RETURNS SETOF int AS $$
            BEGIN
                RETURN NEXT 10;
                RETURN NEXT 20;
                RETURN NEXT 30;
            END;
            $$ LANGUAGE plpgsql;
            """)

            # Key-value function for func_dict
            db.execute("""
            CREATE OR REPLACE FUNCTION test_get_settings()
            RETURNS TABLE(k text, v int) AS $$
            BEGIN
                RETURN QUERY SELECT 'timeout'::text, 30
                             UNION ALL
                             SELECT 'retries'::text, 3;
            END;
            $$ LANGUAGE plpgsql;
            """)

            # Procedure without OUT parameters
            db.execute("""
            CREATE OR REPLACE PROCEDURE test_proc_insert(v_val text) AS $$
            BEGIN
                INSERT INTO test_fn_proc_table (val) VALUES (v_val);
            END;
            $$ LANGUAGE plpgsql;
            """)

            # Procedure with OUT/INOUT parameters
            db.execute("""
            CREATE OR REPLACE PROCEDURE test_proc_math(IN x int, IN y int, OUT sum int, OUT prod int) AS $$
            BEGIN
                sum := x + y;
                prod := x * y;
            END;
            $$ LANGUAGE plpgsql;
            """)

            db.commit()

    def test_func_scalar_positional(self):
        with caddix.DatabaseSession() as db:
            result = db.func_scalar('test_calc_add', 15, 27)
            self.assertEqual(result, 42)

    def test_func_scalar_named(self):
        with caddix.DatabaseSession() as db:
            result = db.func_scalar('test_calc_add', a=100, b=250)
            self.assertEqual(result, 350)

    def test_func_scalar_mixed_and_schema(self):
        with caddix.DatabaseSession() as db:
            result = db.func_scalar('public.test_calc_add', 20, b=30)
            self.assertEqual(result, 50)

    def test_func_all_and_call_func(self):
        with caddix.DatabaseSession() as db:
            users = db.func_all('test_get_users', min_id=2)
            self.assertEqual(len(users), 2)
            self.assertEqual(users[0], {'id': 2, 'name': 'Bob'})
            self.assertEqual(users[1], {'id': 3, 'name': 'Charlie'})

            # call_func / call_function alias
            users_call = db.call_func('test_get_users', 1)
            self.assertEqual(len(users_call), 3)

            users_alias = db.call_function('test_get_users', min_id=3)
            self.assertEqual(len(users_alias), 1)
            self.assertEqual(users_alias[0], {'id': 3, 'name': 'Charlie'})

    def test_func_one(self):
        with caddix.DatabaseSession() as db:
            user = db.func_one('test_get_user_by_id', 99)
            self.assertEqual(user, {'id': 99, 'name': 'User 99'})

    def test_func_many(self):
        with caddix.DatabaseSession() as db:
            users = db.func_many('test_get_users', 2, min_id=1)
            self.assertEqual(len(users), 2)
            self.assertEqual(users[0]['id'], 1)
            self.assertEqual(users[1]['id'], 2)

        with caddix.DatabaseSession() as db:
            with self.assertRaises(caddix.base.CaddixSessionError):
                db.func_many('test_get_users', None)

    def test_func_list(self):
        with caddix.DatabaseSession() as db:
            ids = db.func_list('test_get_id_list')
            self.assertEqual(ids, [10, 20, 30])

    def test_func_dict(self):
        with caddix.DatabaseSession() as db:
            settings = db.func_dict('test_get_settings')
            self.assertEqual(settings, {'timeout': 30, 'retries': 3})

    def test_func_with_custom_row_factory(self):
        with caddix.DatabaseSession(cursor_factory=class_row(UserRow)) as db:
            users = db.func_all('test_get_users', min_id=2)
            self.assertEqual(users, [UserRow(id=2, name='Bob'), UserRow(id=3, name='Charlie')])

    def test_func_with_keyword_sanitization(self):
        # Test reserved python keyword _from parameter
        with caddix.DatabaseSession() as db:
            # We can create a function taking parameter name 'from' in PG
            db.execute("""
            CREATE OR REPLACE FUNCTION test_keyword_fn("from" text) RETURNS text AS $$
            BEGIN
                RETURN 'FROM:' || "from";
            END;
            $$ LANGUAGE plpgsql;
            """)
            db.commit()

            res = db.func_scalar('test_keyword_fn', _from='sender@example.com')
            self.assertEqual(res, 'FROM:sender@example.com')

    def test_call_proc_no_out(self):
        with caddix.DatabaseSession() as db:
            ret = db.call_proc('test_proc_insert', 'hello_procedure')
            self.assertIsNone(ret)
            db.commit()

            row = db.select_one('test_fn_proc_table', val='hello_procedure')
            self.assertIsNotNone(row)
            self.assertEqual(row['val'], 'hello_procedure')

    def test_call_proc_with_out(self):
        with caddix.DatabaseSession() as db:
            ret = db.call_proc('test_proc_math', 6, 7, None, None)
            self.assertEqual(ret, {'sum': 13, 'prod': 42})

            # Named call
            ret_named = db.call_procedure('public.test_proc_math', x=10, y=5, sum=None, prod=None)
            self.assertEqual(ret_named, {'sum': 15, 'prod': 50})

    def test_func_error_handling(self):
        with caddix.DatabaseSession() as db:
            with self.assertRaises(caddix.base.CaddixError):
                db.func_scalar('non_existent_func_xyz', 1, 2)

            with self.assertRaises(caddix.base.CaddixError):
                db.call_proc('non_existent_proc_xyz', 1, 2)


if __name__ == '__main__':
    unittest.main()

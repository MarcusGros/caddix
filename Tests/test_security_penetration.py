import unittest
import caddix
from caddix.base import DatabaseSession, CaddixError


class TestSecurityPenetration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        caddix.Setup(
            name='pen_test_secure',
            databasename='caddix',
            hostname='localhost',
            username='caddix',
            password='caddix',
            verbose=True
        )
        caddix.Setup(
            name='pen_test_redacted',
            databasename='caddix',
            hostname='localhost',
            username='caddix',
            password='caddix',
            verbose=False
        )

    def setUp(self):
        with DatabaseSession('pen_test_secure') as db:
            db.execute("DROP TABLE IF EXISTS pen_target_table CASCADE")
            db.execute("DROP TABLE IF EXISTS pen_secret_table CASCADE")
            
            db.execute("CREATE TABLE pen_target_table (id serial primary key, username text, email text, role text, balance int)")
            db.execute("CREATE TABLE pen_secret_table (id serial primary key, secret_token text, api_key text)")

            db.execute("INSERT INTO pen_target_table (username, email, role, balance) VALUES ('victim', 'victim@corp.com', 'user', 1000)")
            db.execute("INSERT INTO pen_secret_table (secret_token, api_key) VALUES ('TOP_SECRET_HASH_99999', 'API_KEY_LIVE_ABC123')")
            db.commit()

    def test_sql_injection_in_table_name(self):
        with DatabaseSession('pen_test_secure') as db:
            # Table name injection attempt to drop secret table
            malicious_table = 'pen_target_table; DROP TABLE pen_secret_table; --'
            with self.assertRaises(CaddixError):
                db.select_all(malicious_table)

        # Secret table must still exist intact
        with DatabaseSession('pen_test_secure') as db:
            self.assertTrue(db.exists('pen_secret_table'))
            count = db.execute_fetchscalar("SELECT COUNT(*) FROM pen_secret_table")
            self.assertEqual(count, 1)

    def test_sql_injection_in_schema_qualified_table(self):
        with DatabaseSession('pen_test_secure') as db:
            malicious_schema_table = 'public.pen_target_table; DROP TABLE pen_secret_table; --'
            with self.assertRaises(CaddixError):
                db.select_one(malicious_schema_table, id=1)

        with DatabaseSession('pen_test_secure') as db:
            self.assertTrue(db.exists('pen_secret_table'))

    def test_sql_injection_in_columns_selection(self):
        with DatabaseSession('pen_test_secure') as db:
            # Attempt subquery injection in columns parameter
            malicious_col = 'username, (SELECT secret_token FROM pen_secret_table LIMIT 1) as leaked'
            with self.assertRaises(CaddixError):
                # Columns are formatted via Identifier, so this must be treated as a single quoted column identifier and fail
                db.select_all('pen_target_table', columns=[malicious_col])

    def test_sql_injection_in_returning_clause(self):
        with DatabaseSession('pen_test_secure') as db:
            # 1. Attempt injection via returning string
            malicious_returning = "id; DROP TABLE pen_secret_table; --"
            with self.assertRaises(CaddixError):
                db.insert('pen_target_table', returning=malicious_returning, username='attacker', role='user', balance=10)

            # 2. Attempt subquery extraction via returning list
            malicious_ret_list = ['id', '(SELECT secret_token FROM pen_secret_table LIMIT 1)']
            with self.assertRaises(CaddixError):
                db.insert('pen_target_table', returning=malicious_ret_list, username='attacker2', role='user', balance=20)

        # Confirm target & secret tables remain unmodified by attack
        with DatabaseSession('pen_test_secure') as db:
            self.assertTrue(db.exists('pen_secret_table'))

    def test_sql_injection_in_where_values(self):
        with DatabaseSession('pen_test_secure') as db:
            # Classical tautology attack: ' OR '1'='1
            injection_payload = "victim' OR '1'='1"
            res = db.select_all('pen_target_table', username=injection_payload)
            # Should safely find 0 rows (since no user is named literally "victim' OR '1'='1")
            self.assertEqual(len(res), 0)

            # Piggybacked query attack
            piggyback = "victim'; UPDATE pen_target_table SET balance = 999999 WHERE username='victim'; --"
            res_piggy = db.select_all('pen_target_table', username=piggyback)
            self.assertEqual(len(res_piggy), 0)

            # Confirm balance was NOT updated
            victim_row = db.select_one('pen_target_table', username='victim')
            self.assertEqual(victim_row['balance'], 1000)

    def test_sql_injection_in_update_values(self):
        with DatabaseSession('pen_test_secure') as db:
            # Malicious value attempting SQL breakout
            db.update(
                'pen_target_table',
                values={'email': "victim@corp.com', balance = 999999 WHERE username='victim' --"},
                username='victim'
            )
            db.commit()

        # Confirm the email is literally set to that string and balance did not change
        with DatabaseSession('pen_test_secure') as db:
            victim_row = db.select_one('pen_target_table', username='victim')
            self.assertEqual(victim_row['balance'], 1000)
            self.assertEqual(victim_row['email'], "victim@corp.com', balance = 999999 WHERE username='victim' --")

    def test_sql_injection_in_function_and_proc_calls(self):
        with DatabaseSession('pen_test_secure') as db:
            # Malicious function name
            malicious_fn = "public.gen_random_uuid(); DROP TABLE pen_secret_table; --"
            with self.assertRaises(CaddixError):
                db.func_scalar(malicious_fn)

            # Malicious argument name (kwargs key)
            with self.assertRaises(CaddixError):
                db.func_scalar('test_calc_add', **{"a, 1); DROP TABLE pen_secret_table; --": 42})

            db.rollback()

            # Malicious positional argument value (must be safely parameterized)
            db.execute("""
            CREATE OR REPLACE FUNCTION pen_echo_text(msg text) RETURNS text AS $$
            BEGIN
                RETURN msg;
            END;
            $$ LANGUAGE plpgsql;
            """)
            db.commit()

            evil_arg = "hello'; DROP TABLE pen_secret_table; --"
            echoed = db.func_scalar('pen_echo_text', evil_arg)
            self.assertEqual(echoed, evil_arg)

        with DatabaseSession('pen_test_secure') as db:
            self.assertTrue(db.exists('pen_secret_table'))

    def test_sql_injection_in_upsert_conflict_target(self):
        with DatabaseSession('pen_test_secure') as db:
            # Malicious conflict target attempting clause injection
            malicious_conflict = 'id) DO UPDATE SET balance = 999999; --'
            with self.assertRaises(CaddixError):
                db.upsert_batch(
                    'pen_target_table',
                    [{'id': 1, 'username': 'hacked'}],
                    conflict_target=[malicious_conflict],
                    update_columns=['username']
                )

    def test_data_leakage_redaction_when_verbose_is_false(self):
        with DatabaseSession('pen_test_redacted') as db:
            sensitive_token = "HIGHLY_CONFIDENTIAL_SUPER_SECRET_KEY_123456789"
            try:
                # Trigger a SQL error containing the secret token in params
                db.execute("SELECT * FROM non_existent_table WHERE token = %(secret)s", secret=sensitive_token)
                self.fail("Expected CaddixError")
            except CaddixError as e:
                error_str = str(e)
                # The sensitive query and token must NEVER leak into the error message
                self.assertNotIn(sensitive_token, error_str)
                self.assertNotIn("SELECT * FROM", error_str)

    def test_dsn_injection_with_malicious_credentials(self):
        # Attacker trying to inject connection options like sslmode=disable or host redirects
        caddix.Setup(
            name='pen_dsn_inject',
            databasename='caddix',
            hostname='localhost',
            username='caddix',
            password='secret_pwd\' host=evil.com port=6666 dbname=compromised \'',
            verbose=False
        )
        dsn = caddix.Setup.configs['pen_dsn_inject']['dsn']
        # Must be properly escaped so evil host is part of the password literal, not top-level param
        self.assertIn("password='secret_pwd\\' host=evil.com port=6666 dbname=compromised \\''", dsn)
        self.assertIn("user=caddix", dsn)
        self.assertIn("host=localhost", dsn)


if __name__ == '__main__':
    unittest.main()

from decimal import Decimal
import unittest
import caddix
from caddix.base import DatabaseSession


class TestCRUDOperations(unittest.TestCase):

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
            db.execute("DROP TABLE IF EXISTS test_crud_table CASCADE")
            db.execute("""
                CREATE TABLE test_crud_table (
                    id serial primary key,
                    name text,
                    category text,
                    price numeric(10, 2),
                    in_stock bool default true,
                    "from" text,
                    "order" int
                )
            """)
            db.execute("INSERT INTO test_crud_table (name, category, price, in_stock, \"from\", \"order\") VALUES ('Book A', 'books', 19.99, true, 'Berlin', 1)")
            db.execute("INSERT INTO test_crud_table (name, category, price, in_stock, \"from\", \"order\") VALUES ('Book B', 'books', 29.99, true, 'Munich', 2)")
            db.execute("INSERT INTO test_crud_table (name, category, price, in_stock, \"from\", \"order\") VALUES ('Pen X', 'stationery', 3.50, false, 'Hamburg', 3)")
            db.execute("INSERT INTO test_crud_table (name, category, price, in_stock, \"from\", \"order\") VALUES ('Notebook Y', 'stationery', 12.00, true, 'Berlin', 4)")
            db.commit()

    def test_select_all(self):
        with DatabaseSession() as db:
            # All rows
            all_rows = db.select_all('test_crud_table')
            self.assertEqual(len(all_rows), 4)

            # Filtered by category
            books = db.select_all('test_crud_table', category='books')
            self.assertEqual(len(books), 2)
            self.assertEqual(books[0]['name'], 'Book A')
            self.assertEqual(books[1]['name'], 'Book B')

            # Projected columns
            names = db.select_all('test_crud_table', columns=['name', 'price'], category='books')
            self.assertEqual(names[0], {'name': 'Book A', 'price': Decimal('19.99')})

    def test_select_one(self):
        with DatabaseSession() as db:
            row = db.select_one('test_crud_table', name='Pen X')
            self.assertIsNotNone(row)
            self.assertEqual(row['category'], 'stationery')
            self.assertFalse(row['in_stock'])

            # Not found returns None
            none_row = db.select_one('test_crud_table', name='Nonexistent')
            self.assertIsNone(none_row)

    def test_select_many(self):
        with DatabaseSession() as db:
            rows = db.select_many('test_crud_table', 2, category='books')
            self.assertEqual(len(rows), 2)

    def test_select_scalar(self):
        with DatabaseSession() as db:
            price = db.select_scalar('test_crud_table', 'price', name='Book A')
            self.assertEqual(price, Decimal('19.99'))

    def test_select_list(self):
        with DatabaseSession() as db:
            names = db.select_list('test_crud_table', 'name', in_stock=True)
            self.assertListEqual(names, ['Book A', 'Book B', 'Notebook Y'])

    def test_select_dict(self):
        with DatabaseSession() as db:
            catalog = db.select_dict('test_crud_table', 'name', 'price', category='books')
            self.assertEqual(catalog, {'Book A': Decimal('19.99'), 'Book B': Decimal('29.99')})

    def test_insert_with_various_returning_modes(self):
        with DatabaseSession() as db:
            # 1. Returning single column name
            ret1 = db.insert('test_crud_table', returning='id', name='Ruler Z', category='stationery', price=2.00)
            self.assertIn('id', ret1)

            # 2. Returning list of columns
            ret2 = db.insert('test_crud_table', returning=['id', 'name'], name='Eraser E', category='stationery', price=1.50)
            self.assertIn('id', ret2)
            self.assertEqual(ret2['name'], 'Eraser E')

            # 3. Returning '*'
            ret3 = db.insert('test_crud_table', returning='*', name='Mug M', category='merch', price=9.99)
            self.assertEqual(ret3['category'], 'merch')

            # 4. Returning None (no returning clause)
            ret_none = db.insert('test_crud_table', name='Folder F', category='stationery', price=4.00)
            self.assertIsNone(ret_none)

            db.commit()

        # Verify inserted count
        with DatabaseSession() as db:
            total = db.execute_fetchscalar("SELECT COUNT(*) FROM test_crud_table")
            self.assertEqual(total, 8)

    def test_update_operation(self):
        with DatabaseSession() as db:
            # Update price with returning
            res = db.update(
                'test_crud_table',
                values={'price': 24.99, 'in_stock': False},
                returning=['name', 'price', 'in_stock'],
                name='Book A'
            )
            self.assertEqual(len(res), 1)
            self.assertEqual(res[0]['name'], 'Book A')
            self.assertEqual(res[0]['price'], Decimal('24.99'))
            self.assertFalse(res[0]['in_stock'])

            # Update without returning returns None
            ret = db.update('test_crud_table', values={'in_stock': True}, category='stationery')
            self.assertIsNone(ret)
            db.commit()

        # Verify persistence
        with DatabaseSession() as db:
            row = db.select_one('test_crud_table', name='Book A')
            self.assertEqual(row['price'], Decimal('24.99'))

    def test_update_check_changes(self):
        with DatabaseSession() as db:
            # Updating with same values and check_changes=True -> returns empty list if returning, rowcount=0
            res = db.update(
                'test_crud_table',
                values={'price': 19.99, 'category': 'books'},
                returning=['id', 'name'],
                check_changes=True,
                name='Book A'
            )
            self.assertEqual(len(res), 0)

            # Updating with different value and check_changes=True -> performs update
            res = db.update(
                'test_crud_table',
                values={'price': 25.00},
                returning=['id', 'name', 'price'],
                check_changes=True,
                name='Book A'
            )
            self.assertEqual(len(res), 1)
            self.assertEqual(res[0]['price'], Decimal('25.00'))

    def test_delete_operation(self):
        with DatabaseSession() as db:
            # Delete single item
            db.delete('test_crud_table', name='Pen X')
            
            # Verify deleted
            self.assertIsNone(db.select_one('test_crud_table', name='Pen X'))

            # Delete by category
            db.delete('test_crud_table', category='books')
            books = db.select_all('test_crud_table', category='books')
            self.assertEqual(len(books), 0)
            db.commit()

    def test_reserved_keywords_in_column_names(self):
        with DatabaseSession() as db:
            # Columns "from" and "order"
            row = db.select_one('test_crud_table', _from='Berlin', _order=1)
            self.assertIsNotNone(row)
            self.assertEqual(row['name'], 'Book A')

            # Insert with leading underscores
            inserted = db.insert('test_crud_table', returning='*', name='Special Item', _from='Frankfurt', _order=99)
            self.assertEqual(inserted['from'], 'Frankfurt')
            self.assertEqual(inserted['order'], 99)

            # Update using leading underscore
            db.update('test_crud_table', values={'from': 'Cologne', 'order': 100}, name='Special Item')
            updated = db.select_one('test_crud_table', name='Special Item')
            self.assertEqual(updated['from'], 'Cologne')
            self.assertEqual(updated['order'], 100)


if __name__ == '__main__':
    unittest.main()

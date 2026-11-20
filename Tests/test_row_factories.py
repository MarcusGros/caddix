import unittest
from dataclasses import dataclass
from typing import Optional
import caddix
from caddix.base import DatabaseSession
from psycopg.rows import dict_row, tuple_row, scalar_row, namedtuple_row, class_row


@dataclass
class Product:
    id: int
    name: str
    price: float
    description: Optional[str] = None


class CustomRecord:
    def __init__(self, id, name, price, description=None):
        self.id = id
        self.name = name
        self.price = price
        self.description = description


class TestRowFactories(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        caddix.Setup(
            name='rf_default',
            databasename='tusker',
            hostname='localhost',
            username='tusker',
            password='tusker',
            verbose=True
        )

    def setUp(self):
        with DatabaseSession('rf_default') as db:
            db.execute("DROP TABLE IF EXISTS test_rf_table CASCADE")
            db.execute("""
                CREATE TABLE test_rf_table (
                    id serial primary key,
                    name text,
                    price numeric(10, 2),
                    description text
                )
            """)
            db.execute("INSERT INTO test_rf_table (name, price, description) VALUES ('Widget A', 10.50, 'Basic widget')")
            db.execute("INSERT INTO test_rf_table (name, price, description) VALUES ('Widget B', 25.00, 'Pro widget')")
            db.commit()

    def test_default_dict_row(self):
        with DatabaseSession('rf_default') as db:
            row = db.select_one('test_rf_table', name='Widget A')
            self.assertIsInstance(row, dict)
            self.assertEqual(row['name'], 'Widget A')
            self.assertEqual(row['price'], 10.50)

    def test_tuple_row_factory(self):
        with DatabaseSession('rf_default', cursor_factory=tuple_row) as db:
            row = db.select_one('test_rf_table', name='Widget A')
            self.assertIsInstance(row, tuple)
            self.assertEqual(row[1], 'Widget A')
            self.assertEqual(row[2], 10.50)

    def test_scalar_row_factory(self):
        with DatabaseSession('rf_default', cursor_factory=scalar_row) as db:
            db.execute("SELECT name FROM test_rf_table ORDER BY id")
            val = db.fetchone()
            self.assertEqual(val, 'Widget A')

    def test_namedtuple_row_factory(self):
        with DatabaseSession('rf_default', cursor_factory=namedtuple_row) as db:
            row = db.select_one('test_rf_table', name='Widget B')
            self.assertEqual(row.name, 'Widget B')
            self.assertEqual(row.price, 25.00)
            self.assertEqual(row.description, 'Pro widget')

    def test_class_row_dataclass(self):
        with DatabaseSession('rf_default', cursor_factory=class_row(Product)) as db:
            rows = db.select_all('test_rf_table')
            self.assertEqual(len(rows), 2)
            self.assertIsInstance(rows[0], Product)
            self.assertEqual(rows[0].name, 'Widget A')
            self.assertEqual(rows[0].price, 10.50)
            self.assertIsInstance(rows[1], Product)
            self.assertEqual(rows[1].name, 'Widget B')

    def test_class_row_custom_class(self):
        with DatabaseSession('rf_default', cursor_factory=class_row(CustomRecord)) as db:
            row = db.select_one('test_rf_table', id=1)
            self.assertIsInstance(row, CustomRecord)
            self.assertEqual(row.name, 'Widget A')

    def test_global_setup_row_factory_configuration(self):
        caddix.Setup(
            name='rf_global_tuple',
            databasename='tusker',
            hostname='localhost',
            username='tusker',
            password='tusker',
            cursor_factory=tuple_row
        )
        with DatabaseSession('rf_global_tuple') as db:
            row = db.select_one('test_rf_table', id=1)
            self.assertIsInstance(row, tuple)

    def test_row_factory_restoration_after_tabledesc(self):
        with DatabaseSession('rf_default', cursor_factory=tuple_row) as db:
            # tabledesc internally switches row_factory to get metadata
            desc = db.tabledesc('test_rf_table')
            self.assertIsNotNone(desc)
            # Must be restored to tuple_row
            self.assertEqual(db.cur.row_factory, tuple_row)

            # Query should still yield tuple
            row = db.select_one('test_rf_table', id=1)
            self.assertIsInstance(row, tuple)


if __name__ == '__main__':
    unittest.main()

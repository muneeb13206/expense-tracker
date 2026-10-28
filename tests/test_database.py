"""
Tests for the database layer.  Run from the project folder with:
    python -m unittest tests.test_database -v

Each test uses a temporary database file, so your real data is never touched.
"""
import os
import sqlite3
import tempfile
import unittest
from datetime import date, timedelta

from app import create_app
import database as db_layer
from database import ValidationError


def expense(**overrides):
    data = {"type": "expense", "amount": "250.50", "date": date.today().isoformat(),
            "category": "Food", "description": "Lunch"}
    data.update(overrides)
    return data


def income(**overrides):
    data = {"type": "income", "amount": "5000", "date": date.today().isoformat(),
            "source": "Salary", "description": "October pay"}
    data.update(overrides)
    return data


class DatabaseTestCase(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.app = create_app({"TESTING": True, "DATABASE": self.db_path,
                               "WTF_CSRF_ENABLED": False})
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()                 # closes the connection
        os.remove(self.db_path)


class TestSchema(DatabaseTestCase):
    def test_tables_and_views_created(self):
        names = {r["name"] for r in db_layer.get_db().execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
        for expected in ("categories", "transactions", "monthly_budgets",
                         "category_budgets", "income_records", "expense_records"):
            self.assertIn(expected, names)

    def test_default_categories_seeded(self):
        n = db_layer.get_db().execute("SELECT COUNT(*) AS n FROM categories").fetchone()["n"]
        self.assertEqual(n, len(db_layer.CATEGORIES))

    def test_init_db_twice_does_not_duplicate_categories(self):
        db_layer.init_db()
        n = db_layer.get_db().execute("SELECT COUNT(*) AS n FROM categories").fetchone()["n"]
        self.assertEqual(n, len(db_layer.CATEGORIES))

    def test_database_rejects_bad_rows_directly(self):
        raw = db_layer.get_db()
        with self.assertRaises(sqlite3.IntegrityError):   # negative amount
            raw.execute("INSERT INTO transactions (type, amount, date, source) "
                        "VALUES ('income', -5, '2026-01-01', 'x')")
        with self.assertRaises(sqlite3.IntegrityError):   # expense without category
            raw.execute("INSERT INTO transactions (type, amount, date) "
                        "VALUES ('expense', 5, '2026-01-01')")
        with self.assertRaises(sqlite3.IntegrityError):   # unknown category id
            raw.execute("INSERT INTO transactions (type, amount, date, category_id) "
                        "VALUES ('expense', 5, '2026-01-01', 999)")


class TestCrud(DatabaseTestCase):
    def test_add_and_get_expense(self):
        tx_id = db_layer.add_transaction(expense())
        row = db_layer.get_transaction(tx_id)
        self.assertEqual(row["type"], "expense")
        self.assertEqual(row["amount"], 250.50)
        self.assertEqual(row["category"], "Food")
        self.assertEqual(row["description"], "Lunch")
        self.assertEqual(row["is_sample"], 0)

    def test_add_and_get_income(self):
        row = db_layer.get_transaction(db_layer.add_transaction(income()))
        self.assertEqual(row["type"], "income")
        self.assertEqual(row["source"], "Salary")
        self.assertIsNone(row["category"])

    def test_update(self):
        tx_id = db_layer.add_transaction(expense())
        ok = db_layer.update_transaction(tx_id, expense(amount="99", category="Bills"))
        self.assertTrue(ok)
        row = db_layer.get_transaction(tx_id)
        self.assertEqual(row["amount"], 99)
        self.assertEqual(row["category"], "Bills")

    def test_update_can_change_type(self):
        tx_id = db_layer.add_transaction(expense())
        db_layer.update_transaction(tx_id, income())
        row = db_layer.get_transaction(tx_id)
        self.assertEqual(row["type"], "income")
        self.assertIsNone(row["category"])

    def test_update_missing_returns_false(self):
        self.assertFalse(db_layer.update_transaction(12345, expense()))

    def test_delete(self):
        tx_id = db_layer.add_transaction(expense())
        self.assertTrue(db_layer.delete_transaction(tx_id))
        self.assertIsNone(db_layer.get_transaction(tx_id))
        self.assertFalse(db_layer.delete_transaction(tx_id))

    def test_list_newest_first_and_limit(self):
        today = date.today()
        db_layer.add_transaction(expense(date=(today - timedelta(days=5)).isoformat()))
        db_layer.add_transaction(expense(date=today.isoformat()))
        rows = db_layer.list_transactions()
        self.assertEqual(len(rows), 2)
        self.assertGreaterEqual(rows[0]["date"], rows[1]["date"])
        self.assertEqual(len(db_layer.list_transactions(limit=1)), 1)
        self.assertEqual(db_layer.count_transactions(), 2)

    def test_views_show_correct_records(self):
        db_layer.add_transaction(expense())
        db_layer.add_transaction(income())
        raw = db_layer.get_db()
        self.assertEqual(len(raw.execute("SELECT * FROM income_records").fetchall()), 1)
        self.assertEqual(len(raw.execute("SELECT * FROM expense_records").fetchall()), 1)

class TestTypeFilter(DatabaseTestCase):
    def test_filter_and_count_by_type(self):
        db_layer.add_transaction(expense())
        db_layer.add_transaction(expense())
        db_layer.add_transaction(income())
        self.assertEqual(len(db_layer.list_transactions(tx_type="expense")), 2)
        self.assertEqual(len(db_layer.list_transactions(tx_type="income")), 1)
        self.assertEqual(len(db_layer.list_transactions(tx_type="bogus")), 3)
        self.assertEqual(db_layer.count_transactions("expense"), 2)
        self.assertEqual(db_layer.count_transactions(), 3)

class TestValidation(DatabaseTestCase):
    def assert_rejected(self, data, field):
        with self.assertRaises(ValidationError) as cm:
            db_layer.add_transaction(data)
        self.assertIn(field, cm.exception.errors)
        self.assertEqual(db_layer.count_transactions(), 0)   # nothing saved

    def test_bad_amounts(self):
        for bad in ("0", "-10", "abc", "", "NaN", "inf", "10.999", "99999999999"):
            with self.subTest(amount=bad):
                self.assert_rejected(expense(amount=bad), "amount")

    def test_bad_dates(self):
        future = (date.today() + timedelta(days=1)).isoformat()
        for bad in ("", "not-a-date", "2026-13-40", future, "1990-01-01"):
            with self.subTest(date=bad):
                self.assert_rejected(expense(date=bad), "date")

    def test_bad_type(self):
        self.assert_rejected(expense(type="gift"), "type")

    def test_expense_needs_valid_category(self):
        self.assert_rejected(expense(category=""), "category")
        self.assert_rejected(expense(category="Gambling"), "category")

    def test_income_needs_source(self):
        self.assert_rejected(income(source="   "), "source")

    def test_description_too_long(self):
        self.assert_rejected(expense(description="x" * 201), "description")

    def test_whitespace_is_trimmed(self):
        tx_id = db_layer.add_transaction(expense(description="  tea  ", amount=" 20 "))
        row = db_layer.get_transaction(tx_id)
        self.assertEqual(row["description"], "tea")
        self.assertEqual(row["amount"], 20)


class TestSecurity(DatabaseTestCase):
    def test_sql_injection_text_is_stored_harmlessly(self):
        evil = "x'); DROP TABLE transactions; --"
        tx_id = db_layer.add_transaction(expense(description=evil))
        self.assertEqual(db_layer.get_transaction(tx_id)["description"], evil)
        self.assertEqual(db_layer.count_transactions(), 1)   # table still exists


class TestSampleData(DatabaseTestCase):
    def test_seed_flags_rows_as_sample(self):
        added = db_layer.seed_sample_data()
        self.assertGreater(added, 20)
        flags = {r["is_sample"] for r in db_layer.list_transactions()}
        self.assertEqual(flags, {1})

    def test_seed_is_repeatable(self):
        first = db_layer.seed_sample_data()
        second = db_layer.seed_sample_data()
        self.assertEqual(first, second)
        self.assertEqual(db_layer.count_transactions(), second)

    def test_no_future_dates(self):
        db_layer.seed_sample_data()
        newest = db_layer.list_transactions(limit=1)[0]["date"]
        self.assertLessEqual(newest, date.today().isoformat())

    def test_clear_removes_only_sample_rows(self):
        real_id = db_layer.add_transaction(expense(description="my real lunch"))
        db_layer.seed_sample_data()
        removed = db_layer.clear_sample_data()
        self.assertGreater(removed, 0)
        self.assertEqual(db_layer.count_transactions(), 1)
        self.assertIsNotNone(db_layer.get_transaction(real_id))


class TestCli(DatabaseTestCase):
    def test_cli_commands(self):
        runner = self.app.test_cli_runner()
        self.assertIn("Added", runner.invoke(args=["seed-sample"]).output)
        self.assertIn("Removed", runner.invoke(args=["clear-sample"]).output)
        self.assertIn("initialised", runner.invoke(args=["init-db"]).output)


if __name__ == "__main__":
    unittest.main()
"""
Tests for the Add / Edit / Delete / List pages.
Run: python -m unittest tests.test_routes -v
Each test uses a temporary database, so your real data is never touched.
"""
import os
import re
import tempfile
import unittest
from datetime import date

from app import create_app
import database


def expense_form(**overrides):
    data = {"type": "expense", "amount": "250.50", "date": date.today().isoformat(),
            "category": "Food", "description": "Lunch"}
    data.update(overrides)
    return data


def income_form(**overrides):
    data = {"type": "income", "amount": "5000", "date": date.today().isoformat(),
            "source": "Salary", "description": "October pay"}
    data.update(overrides)
    return data


class RouteTestCase(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.app = create_app({"TESTING": True, "DATABASE": self.db_path,
                               "WTF_CSRF_ENABLED": False})
        self.client = self.app.test_client()

    def tearDown(self):
        os.remove(self.db_path)

    # helpers that talk to the database directly
    def add(self, form):
        with self.app.app_context():
            return database.add_transaction(form)

    def count(self, tx_type=None):
        with self.app.app_context():
            return database.count_transactions(tx_type)

    def fetch(self, tx_id):
        with self.app.app_context():
            row = database.get_transaction(tx_id)
            return dict(row) if row else None


class TestAdd(RouteTestCase):
    def test_form_page_loads(self):
        r = self.client.get("/transactions/add")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Add Transaction", r.data)

    def test_type_preselected_from_query(self):
        body = self.client.get("/transactions/add?type=income").get_data(as_text=True)
        self.assertRegex(body, r'value="income"\s+checked')

    def test_add_expense(self):
        r = self.client.post("/transactions/add", data=expense_form(), follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Lunch", r.data)
        self.assertIn("₹250.50".encode(), r.data)       # flash message and table amount
        self.assertEqual(self.count("expense"), 1)

    def test_add_income(self):
        r = self.client.post("/transactions/add", data=income_form(), follow_redirects=True)
        self.assertIn(b"Salary", r.data)
        self.assertEqual(self.count("income"), 1)

    def test_invalid_amount_shows_error_and_saves_nothing(self):
        r = self.client.post("/transactions/add", data=expense_form(amount="-5"))
        self.assertEqual(r.status_code, 400)
        self.assertIn(b"greater than zero", r.data)
        self.assertEqual(self.count(), 0)

    def test_missing_category_shows_error(self):
        r = self.client.post("/transactions/add", data=expense_form(category=""))
        self.assertEqual(r.status_code, 400)
        self.assertIn(b"valid category", r.data)

    def test_typed_values_are_kept_after_error(self):
        r = self.client.post("/transactions/add",
                             data=expense_form(amount="abc", description="keep me"))
        self.assertIn(b"keep me", r.data)

    def test_html_in_description_is_escaped(self):
        evil = "<script>alert(1)</script>"
        self.client.post("/transactions/add", data=expense_form(description=evil))
        body = self.client.get("/transactions").get_data(as_text=True)
        self.assertNotIn(evil, body)
        self.assertIn("&lt;script&gt;", body)

    def test_sql_text_is_stored_harmlessly(self):
        evil = "x'); DROP TABLE transactions; --"
        self.client.post("/transactions/add", data=expense_form(description=evil))
        self.assertEqual(self.count(), 1)


class TestEdit(RouteTestCase):
    def test_edit_page_is_prefilled(self):
        tx_id = self.add(expense_form(description="Pizza", amount="320"))
        r = self.client.get(f"/transactions/{tx_id}/edit")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Edit Transaction", r.data)
        self.assertIn(b"Pizza", r.data)
        self.assertIn(b"320.00", r.data)

    def test_edit_saves_changes(self):
        tx_id = self.add(expense_form())
        r = self.client.post(f"/transactions/{tx_id}/edit",
                             data=expense_form(amount="99", category="Bills"),
                             follow_redirects=True)
        self.assertIn(b"updated", r.data)
        row = self.fetch(tx_id)
        self.assertEqual(row["amount"], 99)
        self.assertEqual(row["category"], "Bills")

    def test_edit_with_invalid_data_changes_nothing(self):
        tx_id = self.add(expense_form())
        r = self.client.post(f"/transactions/{tx_id}/edit", data=expense_form(amount="0"))
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.fetch(tx_id)["amount"], 250.50)

    def test_edit_missing_transaction_is_404(self):
        self.assertEqual(self.client.get("/transactions/999/edit").status_code, 404)
        self.assertEqual(
            self.client.post("/transactions/999/edit", data=expense_form()).status_code, 404)


class TestDelete(RouteTestCase):
    def test_delete_removes_transaction(self):
        tx_id = self.add(expense_form())
        r = self.client.post(f"/transactions/{tx_id}/delete", follow_redirects=True)
        self.assertIn(b"deleted", r.data)
        self.assertIsNone(self.fetch(tx_id))

    def test_delete_missing_shows_error(self):
        r = self.client.post("/transactions/999/delete", follow_redirects=True)
        self.assertIn(b"no longer exists", r.data)

    def test_delete_requires_post(self):
        tx_id = self.add(expense_form())
        self.assertEqual(self.client.get(f"/transactions/{tx_id}/delete").status_code, 405)
        self.assertIsNotNone(self.fetch(tx_id))


class TestList(RouteTestCase):
    def test_empty_state(self):
        r = self.client.get("/transactions")
        self.assertIn(b"No transactions yet", r.data)

    def test_tabs_filter_by_type(self):
        self.add(expense_form(description="ExpenseRowMarker"))
        self.add(income_form(description="IncomeRowMarker"))
        both = self.client.get("/transactions").get_data(as_text=True)
        self.assertIn("ExpenseRowMarker", both)
        self.assertIn("IncomeRowMarker", both)
        only_income = self.client.get("/transactions?type=income").get_data(as_text=True)
        self.assertIn("IncomeRowMarker", only_income)
        self.assertNotIn("ExpenseRowMarker", only_income)
        only_expense = self.client.get("/transactions?type=expense").get_data(as_text=True)
        self.assertIn("ExpenseRowMarker", only_expense)
        self.assertNotIn("IncomeRowMarker", only_expense)

    def test_unknown_filter_falls_back_to_all(self):
        self.add(expense_form(description="ExpenseRowMarker"))
        body = self.client.get("/transactions?type=banana").get_data(as_text=True)
        self.assertIn("ExpenseRowMarker", body)

    def test_unknown_page_is_404(self):
        self.assertEqual(self.client.get("/nope").status_code, 404)


if __name__ == "__main__":
    unittest.main()
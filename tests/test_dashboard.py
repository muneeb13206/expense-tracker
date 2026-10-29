"""
Tests for the dashboard, summary calculations and budget status.
Run: python -m unittest tests.test_dashboard -v
Each test uses a temporary database, so your real data is never touched.
"""
import os
import tempfile
import unittest
from datetime import date, timedelta

from app import create_app
import database
from utils import budget_status


def this_month():
    return date.today().strftime("%Y-%m")


def last_month_date():
    """The last day of the previous month (always outside the current month)."""
    return (date.today().replace(day=1) - timedelta(days=1)).isoformat()


def expense_form(**overrides):
    data = {"type": "expense", "amount": "250.50", "date": date.today().isoformat(),
            "category": "Food", "description": "Lunch"}
    data.update(overrides)
    return data


def income_form(**overrides):
    data = {"type": "income", "amount": "5000", "date": date.today().isoformat(),
            "source": "Salary", "description": "Pay"}
    data.update(overrides)
    return data


class AppTestCase(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.app = create_app({"TESTING": True, "DATABASE": self.db_path,
                               "WTF_CSRF_ENABLED": False})
        self.client = self.app.test_client()

    def tearDown(self):
        os.remove(self.db_path)

    def add(self, form, sample=False):
        with self.app.app_context():
            return database.add_transaction(form, is_sample=sample)

    def set_budget(self, amount, month=None):
        with self.app.app_context():
            db = database.get_db()
            db.execute("INSERT INTO monthly_budgets (month, amount) VALUES (?, ?)",
                       (month or this_month(), amount))
            db.commit()

    def page(self):
        return self.client.get("/").get_data(as_text=True)


class TestTotals(AppTestCase):
    def test_empty_database_gives_zeros(self):
        with self.app.app_context():
            self.assertEqual(database.get_totals(),
                             {"income": 0.0, "expense": 0.0, "balance": 0.0})

    def test_all_time_and_monthly_totals(self):
        self.add(income_form(amount="10000"))
        self.add(expense_form(amount="2500"))
        self.add(expense_form(amount="400", date=last_month_date()))
        with self.app.app_context():
            all_time = database.get_totals()
            month = database.get_totals(this_month())
        self.assertEqual(all_time, {"income": 10000, "expense": 2900, "balance": 7100})
        self.assertEqual(month, {"income": 10000, "expense": 2500, "balance": 7500})

    def test_sums_are_rounded_to_two_decimals(self):
        for _ in range(3):
            self.add(expense_form(amount="0.10"))
        with self.app.app_context():
            self.assertEqual(database.get_totals()["expense"], 0.3)

    def test_month_bounds(self):
        self.assertEqual(database._month_bounds("2026-12"), ("2026-12-01", "2027-01-01"))
        self.assertEqual(database._month_bounds("2026-02"), ("2026-02-01", "2026-03-01"))

    def test_monthly_budget_lookup(self):
        with self.app.app_context():
            self.assertIsNone(database.get_monthly_budget(this_month()))
        self.set_budget(15000)
        with self.app.app_context():
            self.assertEqual(database.get_monthly_budget(this_month())["amount"], 15000)

    def test_sample_count(self):
        self.add(expense_form())
        self.add(expense_form(), sample=True)
        with self.app.app_context():
            self.assertEqual(database.count_sample_transactions(), 1)


class TestBudgetStatus(unittest.TestCase):
    def test_states(self):
        self.assertEqual(budget_status(100, 1000)["state"], "ok")
        self.assertEqual(budget_status(799, 1000)["state"], "ok")
        self.assertEqual(budget_status(800, 1000)["state"], "warning")
        self.assertEqual(budget_status(1000, 1000)["state"], "warning")
        self.assertEqual(budget_status(1000.01, 1000)["state"], "over")

    def test_numbers(self):
        status = budget_status(250, 1000)
        self.assertEqual(status["percent"], 25.0)
        self.assertEqual(status["remaining"], 750)
        over = budget_status(1500, 1000)
        self.assertEqual(over["remaining"], -500)
        self.assertEqual(over["bar_width"], 100)       # bar never overflows

    def test_no_budget_returns_none(self):
        self.assertIsNone(budget_status(50, None))
        self.assertIsNone(budget_status(50, 0))


class TestDashboard(AppTestCase):
    def test_empty_state_offers_sample_data(self):
        body = self.page()
        self.assertIn("Welcome to", body)
        self.assertIn("Load sample data", body)
        self.assertNotIn("Total Income", body)

    def test_summary_cards_show_real_numbers(self):
        self.add(income_form(amount="10000"))
        self.add(expense_form(amount="2500"))
        body = self.page()
        self.assertIn("₹10,000.00", body)    # total income
        self.assertIn("₹2,500.00", body)     # total expenses and month spending
        self.assertIn("₹7,500.00", body)     # balance

    def test_negative_balance_is_shown_with_minus(self):
        self.add(expense_form(amount="500"))
        self.assertIn("-₹500.00", self.page())

    def test_monthly_spending_excludes_other_months(self):
        self.add(expense_form(amount="111"))
        self.add(expense_form(amount="9999", date=last_month_date()))
        with self.app.app_context():
            self.assertEqual(database.get_totals(this_month())["expense"], 111)
            self.assertEqual(database.get_totals()["expense"], 10110)

    def test_no_budget_message(self):
        self.add(expense_form())
        body = self.page()
        self.assertIn("Set a monthly budget", body)

    def test_budget_ok(self):
        self.set_budget(1000)
        self.add(expense_form(amount="200"))
        body = self.page()
        self.assertIn("20.0%", body)
        self.assertIn("₹800.00 left of ₹1,000.00", " ".join(body.split()))
        self.assertNotIn("close to the limit", body)

    def test_budget_warning(self):
        self.set_budget(1000)
        self.add(expense_form(amount="850"))
        body = self.page()
        self.assertIn("85.0%", body)
        self.assertIn("close to the limit", body)

    def test_budget_exceeded(self):
        self.set_budget(1000)
        self.add(expense_form(amount="1200"))
        body = self.page()
        self.assertIn("exceeded", body)
        self.assertIn("over budget", body)

    def test_recent_transactions_limited_to_eight_newest(self):
        for i in range(10):
            self.add(expense_form(description=f"RowMarker{i:02d}"))
        body = self.page()
        self.assertIn("RowMarker09", body)
        self.assertIn("RowMarker02", body)
        self.assertNotIn("RowMarker01", body)
        self.assertNotIn("RowMarker00", body)

    def test_html_in_description_is_escaped(self):
        evil = "<b>bold</b>"
        self.add(expense_form(description=evil))
        body = self.page()
        self.assertNotIn(evil, body)
        self.assertIn("&lt;b&gt;", body)


class TestSampleDataRoutes(AppTestCase):
    def test_load_sample_data(self):
        r = self.client.post("/sample-data/load", follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        body = r.get_data(as_text=True)
        self.assertIn("Loaded", body)
        self.assertIn("Demo data is loaded", body)
        with self.app.app_context():
            self.assertGreater(database.count_sample_transactions(), 20)

    def test_clear_sample_keeps_real_data(self):
        self.add(expense_form(description="MyRealRow"))
        self.client.post("/sample-data/load")
        r = self.client.post("/sample-data/clear", follow_redirects=True)
        body = r.get_data(as_text=True)
        self.assertIn("Removed", body)
        self.assertIn("MyRealRow", body)
        self.assertNotIn("Demo data is loaded", body)
        with self.app.app_context():
            self.assertEqual(database.count_transactions(), 1)

    def test_routes_reject_get(self):
        self.assertEqual(self.client.get("/sample-data/load").status_code, 405)
        self.assertEqual(self.client.get("/sample-data/clear").status_code, 405)


if __name__ == "__main__":
    unittest.main()
"""
Tests for report queries, chart JSON routes and the Reports page.
Run: python -m unittest tests.test_reports -v
Each test uses a temporary database, so your real data is never touched.
"""
import os
import tempfile
import unittest
from datetime import date, timedelta

from app import create_app
import database
from utils import parse_iso_date, percent_change, read_date_range, report_presets


def today_iso():
    return date.today().isoformat()


def last_month_date():
    """The last day of the previous month."""
    return (date.today().replace(day=1) - timedelta(days=1)).isoformat()


def expense_form(**overrides):
    data = {"type": "expense", "amount": "100", "date": today_iso(),
            "category": "Food", "description": "Row"}
    data.update(overrides)
    return data


def income_form(**overrides):
    data = {"type": "income", "amount": "5000", "date": today_iso(),
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

    def add(self, form):
        with self.app.app_context():
            return database.add_transaction(form)

    def query(self, func, *args, **kwargs):
        with self.app.app_context():
            return func(*args, **kwargs)


class TestCategoryBreakdown(AppTestCase):
    def test_groups_sorts_and_percentages(self):
        self.add(expense_form(amount="100", category="Food"))
        self.add(expense_form(amount="50", category="Food"))
        self.add(expense_form(amount="300", category="Bills"))
        rows = self.query(database.get_category_breakdown)
        self.assertEqual([r["category"] for r in rows], ["Bills", "Food"])
        self.assertEqual([r["total"] for r in rows], [300, 150])
        self.assertEqual([r["count"] for r in rows], [1, 2])
        self.assertEqual([r["percent"] for r in rows], [66.7, 33.3])

    def test_income_is_not_counted(self):
        self.add(income_form(amount="9999"))
        self.assertEqual(self.query(database.get_category_breakdown), [])

    def test_date_range_includes_both_ends(self):
        self.add(expense_form(amount="10", date="2026-01-10", category="Food"))
        self.add(expense_form(amount="20", date="2026-01-15", category="Bills"))
        self.add(expense_form(amount="40", date="2026-01-20", category="Other"))
        self.add(expense_form(amount="80", date="2026-01-21", category="Shopping"))
        rows = self.query(database.get_category_breakdown, "2026-01-15", "2026-01-20")
        self.assertEqual({r["category"] for r in rows}, {"Bills", "Other"})

    def test_empty_database(self):
        self.assertEqual(self.query(database.get_category_breakdown), [])


class TestRangeTotals(AppTestCase):
    def test_inclusive_range_totals(self):
        self.add(income_form(amount="1000", date="2026-02-01"))
        self.add(expense_form(amount="300", date="2026-02-10"))
        self.add(expense_form(amount="700", date="2026-03-01"))
        totals = self.query(database.get_range_totals, "2026-02-01", "2026-02-10")
        self.assertEqual(totals, {"income": 1000, "expense": 300, "balance": 700})

    def test_first_transaction_date(self):
        self.assertIsNone(self.query(database.get_first_transaction_date))
        self.add(expense_form(date="2026-03-05"))
        self.add(expense_form(date="2026-01-02"))
        self.assertEqual(self.query(database.get_first_transaction_date), "2026-01-02")


class TestMonthlySeries(AppTestCase):
    def test_year_boundary_zero_fill_and_window(self):
        self.add(income_form(amount="999", date="2025-10-31"))     # before the window
        self.add(expense_form(amount="500", date="2025-12-10"))
        self.add(income_form(amount="1000", date="2026-01-05"))
        self.add(expense_form(amount="200", date="2026-02-01"))
        self.add(expense_form(amount="777", date="2026-03-05"))    # after the window
        series = self.query(database.get_monthly_series, 4, date(2026, 2, 15))
        self.assertEqual([m["month"] for m in series],
                         ["2025-11", "2025-12", "2026-01", "2026-02"])
        self.assertEqual([m["expense"] for m in series], [0, 500, 0, 200])
        self.assertEqual([m["income"] for m in series], [0, 0, 1000, 0])
        self.assertEqual(series[0]["label"], "Nov 2025")

    def test_recent_months_single(self):
        self.assertEqual(database._recent_months(1, date(2026, 10, 30)), ["2026-10"])


class TestHelpers(unittest.TestCase):
    def test_parse_iso_date(self):
        self.assertEqual(parse_iso_date("2026-10-30"), date(2026, 10, 30))
        for bad in ("", "abc", "2026-13-01", "1999-01-01", "2101-01-01", None):
            with self.subTest(value=bad):
                self.assertIsNone(parse_iso_date(bad))

    def test_read_date_range(self):
        self.assertEqual(read_date_range({}), (None, None, None))
        self.assertEqual(read_date_range({"start": "2026-01-01", "end": "2026-01-31"}),
                         ("2026-01-01", "2026-01-31", None))
        self.assertIsNotNone(read_date_range({"start": "nope"})[2])
        self.assertIsNotNone(read_date_range({"start": "2026-02-01", "end": "2026-01-01"})[2])

    def test_percent_change(self):
        self.assertEqual(percent_change(100, 150), 50.0)
        self.assertEqual(percent_change(200, 100), -50.0)
        self.assertIsNone(percent_change(0, 100))

    def test_report_presets(self):
        presets = report_presets(date(2026, 10, 30), "2026-03-02")
        by_label = {p["label"]: p for p in presets}
        self.assertEqual(presets[0]["label"], "This month")
        self.assertEqual((by_label["This month"]["start"], by_label["This month"]["end"]),
                         ("2026-10-01", "2026-10-30"))
        self.assertEqual((by_label["Last month"]["start"], by_label["Last month"]["end"]),
                         ("2026-09-01", "2026-09-30"))
        self.assertEqual(by_label["Last 30 days"]["start"], "2026-10-01")
        self.assertEqual(by_label["Last 3 months"]["start"], "2026-08-01")
        self.assertEqual(by_label["This year"]["start"], "2026-01-01")
        self.assertEqual(by_label["All time"]["start"], "2026-03-02")

    def test_report_presets_january(self):
        by_label = {p["label"]: p for p in report_presets(date(2026, 1, 15))}
        self.assertEqual(by_label["Last month"]["start"], "2025-12-01")
        self.assertEqual(by_label["Last 3 months"]["start"], "2025-11-01")


class TestChartApi(AppTestCase):
    def test_category_breakdown_json_uses_real_data(self):
        self.add(expense_form(amount="300", category="Bills"))
        self.add(expense_form(amount="150", category="Food"))
        r = self.client.get("/api/charts/category-breakdown")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.mimetype, "application/json")
        data = r.get_json()
        self.assertEqual(data["labels"], ["Bills", "Food"])
        self.assertEqual(data["values"], [300, 150])
        self.assertEqual(data["total"], 450)
        self.assertEqual(data["percents"], [66.7, 33.3])

    def test_category_breakdown_date_filter(self):
        self.add(expense_form(amount="300", category="Bills", date=last_month_date()))
        self.add(expense_form(amount="150", category="Food"))
        day = last_month_date()
        data = self.client.get(f"/api/charts/category-breakdown?start={day}&end={day}").get_json()
        self.assertEqual(data["labels"], ["Bills"])

    def test_category_breakdown_empty(self):
        data = self.client.get("/api/charts/category-breakdown").get_json()
        self.assertEqual(data["labels"], [])
        self.assertEqual(data["total"], 0)

    def test_invalid_dates_return_400_json(self):
        for url in ("/api/charts/category-breakdown?start=banana",
                    "/api/charts/category-breakdown?start=2026-02-01&end=2026-01-01"):
            with self.subTest(url=url):
                r = self.client.get(url)
                self.assertEqual(r.status_code, 400)
                self.assertIn("error", r.get_json())

    def test_monthly_summary(self):
        self.add(income_form(amount="1000"))
        self.add(expense_form(amount="250"))
        data = self.client.get("/api/charts/monthly-summary").get_json()
        self.assertEqual(len(data["labels"]), 6)
        self.assertEqual(data["income"][-1], 1000)     # newest month is last
        self.assertEqual(data["expense"][-1], 250)
        self.assertEqual(data["expense"][0], 0)
        short = self.client.get("/api/charts/monthly-summary?months=3").get_json()
        self.assertEqual(len(short["labels"]), 3)

    def test_monthly_summary_rejects_bad_months(self):
        for bad in ("0", "25", "abc", "-1", "1.5", ""):
            with self.subTest(months=bad):
                r = self.client.get(f"/api/charts/monthly-summary?months={bad}")
                self.assertEqual(r.status_code, 400)

    def test_api_responses_are_not_cached(self):
        r = self.client.get("/api/charts/monthly-summary")
        self.assertEqual(r.headers.get("Cache-Control"), "no-store")


class TestReportsPage(AppTestCase):
    def test_empty_state(self):
        body = self.client.get("/reports").get_data(as_text=True)
        self.assertIn("No data to report yet", body)
        self.assertNotIn("data-chart", body)

    def test_default_range_is_this_month_and_shows_highest_category(self):
        self.add(expense_form(amount="100", category="Food"))
        self.add(expense_form(amount="900", category="Bills"))
        body = self.client.get("/reports").get_data(as_text=True)
        self.assertIn(date.today().replace(day=1).isoformat(), body)
        self.assertIn("Highest Spending Category", body)
        self.assertIn("Bills", body)
        self.assertIn("₹1,000.00", body)               # total expenses
        self.assertIn("90.0%", body)                    # Bills share

    def test_canvases_point_at_api_routes(self):
        self.add(expense_form())
        body = self.client.get("/reports").get_data(as_text=True)
        self.assertEqual(body.count("data-chart="), 3)
        self.assertIn("/api/charts/category-breakdown", body)
        self.assertIn("/api/charts/monthly-summary", body)
        self.assertIn("js/charts.js", body)

    def test_custom_range_filters_data(self):
        day = last_month_date()
        self.add(expense_form(amount="700", category="Bills", date=day))
        self.add(expense_form(amount="100", category="Food"))
        body = self.client.get(f"/reports?start={day}&end={day}").get_data(as_text=True)
        self.assertIn("Bills", body)
        self.assertIn("₹700.00", body)
        self.assertNotIn("Food", body)

    def test_range_with_no_expenses(self):
        self.add(expense_form())
        body = self.client.get("/reports?start=2026-01-01&end=2026-01-02").get_data(as_text=True)
        self.assertIn("No expenses were recorded", body)

    def test_invalid_range_shows_error_and_falls_back(self):
        self.add(expense_form())
        body = self.client.get("/reports?start=bad&end=2026-01-01").get_data(as_text=True)
        self.assertIn("Invalid date range", body)
        self.assertIn(date.today().replace(day=1).isoformat(), body)

    def test_reversed_range_is_rejected(self):
        self.add(expense_form())
        body = self.client.get("/reports?start=2026-05-01&end=2026-04-01").get_data(as_text=True)
        self.assertIn("Invalid date range", body)

    def test_monthly_comparison(self):
        self.add(expense_form(amount="200", date=last_month_date()))
        self.add(expense_form(amount="300"))
        body = " ".join(self.client.get("/reports").get_data(as_text=True).split())
        self.assertIn("Monthly comparison", body)
        self.assertIn("+50.0%", body)                   # 200 -> 300

    def test_comparison_without_last_month_data_shows_dash(self):
        self.add(expense_form(amount="300"))
        body = self.client.get("/reports").get_data(as_text=True)
        self.assertIn("Monthly comparison", body)
        self.assertNotIn("+inf", body)

    def test_preset_links_present(self):
        self.add(expense_form())
        body = self.client.get("/reports").get_data(as_text=True)
        for label in ("This month", "Last month", "Last 30 days", "Last 3 months",
                      "This year", "All time"):
            self.assertIn(label, body)


class TestDashboardCharts(AppTestCase):
    def test_dashboard_has_two_charts(self):
        self.add(expense_form())
        body = self.client.get("/").get_data(as_text=True)
        self.assertEqual(body.count("data-chart="), 2)
        self.assertIn("js/charts.js", body)

    def test_empty_dashboard_loads_no_chart_scripts(self):
        body = self.client.get("/").get_data(as_text=True)
        self.assertNotIn("charts.js", body)


if __name__ == "__main__":
    unittest.main()
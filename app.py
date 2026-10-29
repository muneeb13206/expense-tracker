"""
Personal Expense Tracker and Budget Analyzer
--------------------------------------------
app.py : creates the Flask application, configures it securely,
         and registers all routes (URLs).

"""
import os
import secrets
from datetime import date, timedelta

from flask import (Flask, abort, flash, jsonify, redirect, render_template,
                   request, url_for)
from flask_wtf.csrf import CSRFProtect

import database
from utils import (budget_status, format_inr, percent_change, read_date_range,
                   report_presets)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")

csrf = CSRFProtect()  # protects every POST form against CSRF attacks


def load_secret_key() -> str:
    """
    Return a secret key used to sign session cookies and CSRF tokens.

    Priority:
      1. SECRET_KEY environment variable (best for deployment)
      2. A random key generated once and saved in instance/secret_key
         (so the key is never hard-coded in the source code)
    """
    env_key = os.environ.get("SECRET_KEY")
    if env_key:
        return env_key

    os.makedirs(INSTANCE_DIR, exist_ok=True)
    key_path = os.path.join(INSTANCE_DIR, "secret_key")
    if not os.path.exists(key_path):
        with open(key_path, "w") as f:
            f.write(secrets.token_hex(32))
    with open(key_path) as f:
        return f.read().strip()


def create_app(test_config=None) -> Flask:
    """Application factory: builds and returns a configured Flask app."""
    app = Flask(__name__, instance_path=INSTANCE_DIR)

    app.config.update(
        SECRET_KEY=load_secret_key(),
        DATABASE=os.path.join(INSTANCE_DIR, "expense_tracker.db"),  # used in Stage 2
        SESSION_COOKIE_HTTPONLY=True,      # JavaScript cannot read the cookie
        SESSION_COOKIE_SAMESITE="Lax",     # blocks most cross-site requests
        MAX_CONTENT_LENGTH=1 * 1024 * 1024,  # reject request bodies > 1 MB
    )

    if test_config:                      # tests can override settings
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)
    app.add_template_filter(format_inr, "inr")   # use as {{ amount|inr }}
    csrf.init_app(app)
    database.init_app(app)               # creates tables automatically
    register_routes(app)
    register_error_handlers(app)
    register_security_headers(app)
    return app


def register_routes(app: Flask) -> None:
    @app.context_processor
    def inject_globals():
        # Variables available in EVERY template
        today = date.today()
        return {"app_name": "ExpenseTracker", "current_year": today.year,
                "current_date": today.isoformat()}

    @app.route("/")
    def dashboard():
        today = date.today()
        month = today.strftime("%Y-%m")
        total_count = database.count_transactions()
        context = {"has_data": total_count > 0,
                   "sample_count": database.count_sample_transactions(),
                   "month_label": today.strftime("%B %Y")}
        if total_count:
            month_totals = database.get_totals(month)
            budget_row = database.get_monthly_budget(month)
            context.update(
                totals=database.get_totals(),
                month_totals=month_totals,
                budget=budget_status(month_totals["expense"],
                                     budget_row["amount"] if budget_row else None),
                recent=database.list_transactions(limit=8),
                chart_start=today.replace(day=1).isoformat(),
                chart_end=today.isoformat(),
            )
        return render_template("dashboard.html", active="dashboard", **context)

    @app.route("/sample-data/load", methods=["POST"])
    def load_sample():
        count = database.seed_sample_data()
        flash(f"Loaded {count} sample transactions. Your own data is untouched.", "success")
        return redirect(url_for("dashboard"))

    @app.route("/sample-data/clear", methods=["POST"])
    def clear_sample():
        count = database.clear_sample_data()
        flash(f"Removed {count} sample transactions.", "success")
        return redirect(url_for("dashboard"))

    @app.route("/transactions")
    def transactions():
        tx_type = request.args.get("type", "all")
        if tx_type not in ("income", "expense"):
            tx_type = "all"                      # ignore unknown values
        rows = database.list_transactions(tx_type=None if tx_type == "all" else tx_type)
        return render_template("transactions.html", active="transactions",
                               rows=rows, tx_type=tx_type)

    def render_form(form, errors, editing=False, tx_id=None):
        """Show the add/edit form (used for first display AND after errors)."""
        return render_template("add_transaction.html",
                               active="transactions" if editing else "add",
                               form=form, errors=errors, editing=editing,
                               tx_id=tx_id, categories=database.CATEGORIES)

    @app.route("/transactions/add", methods=["GET", "POST"])
    def add_transaction():
        if request.method == "POST":
            form = request.form.to_dict()
            try:
                new_id = database.add_transaction(form)
            except database.ValidationError as e:
                return render_form(form, e.errors), 400
            row = database.get_transaction(new_id)
            flash(f"{row['type'].capitalize()} of {format_inr(row['amount'])} added.",
                  "success")
            return redirect(url_for("transactions"))   # Post/Redirect/Get pattern

        tx_type = request.args.get("type")
        form = {"type": tx_type if tx_type in ("income", "expense") else "expense",
                "date": date.today().isoformat()}
        return render_form(form, {})

    @app.route("/transactions/<int:tx_id>/edit", methods=["GET", "POST"])
    def edit_transaction(tx_id):
        row = database.get_transaction(tx_id)
        if row is None:
            abort(404)
        if request.method == "POST":
            form = request.form.to_dict()
            try:
                database.update_transaction(tx_id, form)
            except database.ValidationError as e:
                return render_form(form, e.errors, editing=True, tx_id=tx_id), 400
            flash("Transaction updated.", "success")
            return redirect(url_for("transactions"))

        form = {"type": row["type"], "amount": f"{row['amount']:.2f}",
                "date": row["date"], "category": row["category"] or "",
                "source": row["source"] or "", "description": row["description"]}
        return render_form(form, {}, editing=True, tx_id=tx_id)

    @app.route("/transactions/<int:tx_id>/delete", methods=["POST"])
    def delete_transaction(tx_id):
        if database.delete_transaction(tx_id):
            flash("Transaction deleted.", "success")
        else:
            flash("That transaction no longer exists.", "error")
        return redirect(url_for("transactions"))

    @app.route("/budgets")
    def budgets():
        return render_template("budgets.html", active="budgets")

    @app.route("/reports")
    def reports():
        today = date.today()
        presets = report_presets(today, database.get_first_transaction_date())

        start, end, error = read_date_range(request.args)
        if error:
            flash("Invalid date range. Showing this month instead.", "error")
        if error or not (start and end):
            start, end = presets[0]["start"], presets[0]["end"]   # default: this month

        totals = database.get_range_totals(start, end)
        breakdown = database.get_category_breakdown(start, end)
        days = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1

        # This month (so far) compared with last month
        month_start = today.replace(day=1)
        last_month_end = month_start - timedelta(days=1)
        this_totals = database.get_totals(today.strftime("%Y-%m"))
        last_totals = database.get_totals(last_month_end.strftime("%Y-%m"))
        comparison = {
            "this_label": today.strftime("%B %Y"),
            "last_label": last_month_end.strftime("%B %Y"),
            "this": this_totals,
            "last": last_totals,
            "income_change": percent_change(last_totals["income"], this_totals["income"]),
            "expense_change": percent_change(last_totals["expense"], this_totals["expense"]),
        }

        return render_template(
            "reports.html", active="reports",
            has_data=database.count_transactions() > 0,
            start=start, end=end, presets=presets, days=days,
            totals=totals, breakdown=breakdown,
            top=breakdown[0] if breakdown else None,
            avg_daily=totals["expense"] / days,
            comparison=comparison,
        )

    # ---- JSON endpoints that feed the charts (read-only, real database data)
    def api_error(message):
        return jsonify(error=message), 400

    @app.route("/api/charts/category-breakdown")
    def api_category_breakdown():
        start, end, error = read_date_range(request.args)
        if error:
            return api_error(error)
        rows = database.get_category_breakdown(start, end)
        return jsonify(labels=[r["category"] for r in rows],
                       values=[r["total"] for r in rows],
                       percents=[r["percent"] for r in rows],
                       total=round(sum(r["total"] for r in rows), 2),
                       start=start, end=end)

    @app.route("/api/charts/monthly-summary")
    def api_monthly_summary():
        raw = request.args.get("months", "6")
        if not (raw.isascii() and raw.isdigit() and 1 <= int(raw) <= 24):
            return api_error("'months' must be a whole number from 1 to 24.")
        series = database.get_monthly_series(int(raw))
        return jsonify(labels=[m["label"] for m in series],
                       income=[m["income"] for m in series],
                       expense=[m["expense"] for m in series])


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(404)
    def not_found(e):
        return render_template("error.html", code=404,
                               message="The page you are looking for does not exist."), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return render_template("error.html", code=405,
                               message="That action is not allowed on this page."), 405

    @app.errorhandler(413)
    def too_large(e):
        return render_template("error.html", code=413,
                               message="The submitted data is too large."), 413

    @app.errorhandler(500)
    def server_error(e):
        # Never show stack traces to users
        return render_template("error.html", code=500,
                               message="Something went wrong on our side. Please try again."), 500


def register_security_headers(app: Flask) -> None:
    @app.after_request
    def add_headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "same-origin"
        if request.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"   # charts always show fresh data
        return resp


if __name__ == "__main__":
    # debug=True is for local development only. Never use it in production.
    create_app().run(host="127.0.0.1", port=5000, debug=True)
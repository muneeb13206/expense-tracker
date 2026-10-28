"""
Personal Expense Tracker and Budget Analyzer
app.py : creates the Flask application, configures it securely,
         and registers all routes (URLs).
"""
import os
import secrets
from datetime import date

from flask import Flask, abort, flash, redirect, render_template, request, url_for
from flask_wtf.csrf import CSRFProtect

import database
from utils import format_inr

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")

csrf = CSRFProtect()  # protects every POST form against CSRF attacks


def load_secret_key() -> str:
    """
    Return a secret key used to sign session cookies and CSRF tokens.
      1. SECRET_KEY environment variable (best for deployment)
      2. Otherwise a random key generated once and saved in instance/secret_key
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
        DATABASE=os.path.join(INSTANCE_DIR, "expense_tracker.db"),
        SESSION_COOKIE_HTTPONLY=True,        # JavaScript cannot read the cookie
        SESSION_COOKIE_SAMESITE="Lax",       # blocks most cross-site requests
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
        return render_template("dashboard.html", active="dashboard")

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
        return render_template("reports.html", active="reports")


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
        return resp


if __name__ == "__main__":
    # debug=True is for local development only. Never use it in production.
    create_app().run(host="127.0.0.1", port=5000, debug=True)
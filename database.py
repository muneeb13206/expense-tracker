"""
database.py - the SQLite database layer (the "Model" part of MVC)

Everything that touches the database lives in this file:
  * schema (tables, constraints, indexes, views)
  * connection handling
  * validation of data before it is saved
  * CRUD functions: add / get / update / delete / list transactions
  * sample-data helpers for demonstrations
  * command-line commands:  flask --app app init-db | seed-sample | clear-sample

SECURITY: every SQL statement uses "?" placeholders (parameterized queries),
so user input is never pasted into SQL text. This prevents SQL injection.
"""
import random
import sqlite3
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import click
from flask import current_app, g

# ---------------------------------------------------------------- constants
CATEGORIES = ["Food", "Transport", "Education", "Shopping",
              "Healthcare", "Entertainment", "Bills", "Other"]
MAX_AMOUNT = Decimal("1000000000")   # 100 crore upper limit, blocks absurd values

# ------------------------------------------------------------------- schema
SCHEMA = """
CREATE TABLE IF NOT EXISTS categories (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

-- ONE table for both income and expenses, separated by the 'type' column.
CREATE TABLE IF NOT EXISTS transactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    type        TEXT NOT NULL CHECK (type IN ('income', 'expense')),
    amount      REAL NOT NULL CHECK (amount > 0),
    date        TEXT NOT NULL
                CHECK (date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    category_id INTEGER REFERENCES categories(id),   -- used by expenses
    source      TEXT,                                -- used by income
    description TEXT NOT NULL DEFAULT '',
    is_sample   INTEGER NOT NULL DEFAULT 0 CHECK (is_sample IN (0, 1)),
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (
        (type = 'expense' AND category_id IS NOT NULL) OR
        (type = 'income'  AND source IS NOT NULL AND category_id IS NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_tx_date     ON transactions(date);
CREATE INDEX IF NOT EXISTS idx_tx_type     ON transactions(type);
CREATE INDEX IF NOT EXISTS idx_tx_category ON transactions(category_id);

-- Overall budget for one month, e.g. month = '2026-10'
CREATE TABLE IF NOT EXISTS monthly_budgets (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    month  TEXT NOT NULL UNIQUE CHECK (month GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]'),
    amount REAL NOT NULL CHECK (amount > 0)
);

-- Optional budget for one category in one month
CREATE TABLE IF NOT EXISTS category_budgets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    month       TEXT NOT NULL CHECK (month GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]'),
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    amount      REAL NOT NULL CHECK (amount > 0),
    UNIQUE (month, category_id)
);

-- Views give separate "income" and "expense" tables to read from,
-- without storing the data twice.
CREATE VIEW IF NOT EXISTS income_records AS
    SELECT id, amount, date, source, description
    FROM transactions WHERE type = 'income';

CREATE VIEW IF NOT EXISTS expense_records AS
    SELECT t.id, t.amount, t.date, c.name AS category, t.description
    FROM transactions t JOIN categories c ON c.id = t.category_id
    WHERE t.type = 'expense';
"""


# --------------------------------------------------------------- connection
def get_db():
    """Return this request's database connection (created on first use)."""
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row            # rows behave like dictionaries
        g.db.execute("PRAGMA foreign_keys = ON")  # SQLite needs this per connection
    return g.db


def close_db(exception=None):
    """Close the connection when the request ends."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create all tables (if missing) and insert the default categories."""
    db = get_db()
    db.executescript(SCHEMA)
    db.executemany("INSERT OR IGNORE INTO categories (name) VALUES (?)",
                   [(name,) for name in CATEGORIES])
    db.commit()


# --------------------------------------------------------------- validation
class ValidationError(Exception):
    """Raised when submitted data is invalid. .errors maps field -> message."""

    def __init__(self, errors):
        super().__init__("Invalid data")
        self.errors = errors


def validate_transaction(raw):
    """
    Check and clean user input. Returns (clean_data, errors).
    If 'errors' is not empty, the data must NOT be saved.
    """
    errors = {}
    clean = {"category": None, "source": None}

    # type
    t = str(raw.get("type", "")).strip().lower()
    if t not in ("income", "expense"):
        errors["type"] = "Type must be income or expense."
    clean["type"] = t

    # amount
    try:
        amount = Decimal(str(raw.get("amount", "")).strip())
        if not amount.is_finite():
            raise InvalidOperation
    except InvalidOperation:
        errors["amount"] = "Enter a valid number for the amount."
    else:
        if amount <= 0:
            errors["amount"] = "Amount must be greater than zero."
        elif amount > MAX_AMOUNT:
            errors["amount"] = "Amount is too large."
        elif amount != amount.quantize(Decimal("0.01")):
            errors["amount"] = "Amount can have at most 2 decimal places."
        else:
            clean["amount"] = float(amount)

    # date
    try:
        parsed = datetime.strptime(str(raw.get("date", "")).strip(), "%Y-%m-%d").date()
    except ValueError:
        errors["date"] = "Enter a valid date in YYYY-MM-DD format."
    else:
        if parsed > date.today():
            errors["date"] = "Date cannot be in the future."
        elif parsed.year < 2000:
            errors["date"] = "Date is too far in the past."
        else:
            clean["date"] = parsed.isoformat()

    # description (optional)
    description = str(raw.get("description", "")).strip()
    if len(description) > 200:
        errors["description"] = "Description must be 200 characters or fewer."
    clean["description"] = description

    # category (expenses) or source (income)
    if t == "expense":
        category = str(raw.get("category", "")).strip()
        if category not in CATEGORIES:
            errors["category"] = "Please choose a valid category."
        clean["category"] = category
    elif t == "income":
        source = str(raw.get("source", "")).strip()
        if not source:
            errors["source"] = "Please enter the income source."
        elif len(source) > 100:
            errors["source"] = "Source must be 100 characters or fewer."
        clean["source"] = source

    return clean, errors


def _category_id(db, name):
    """Look up a category's id from its name (None for income)."""
    if name is None:
        return None
    row = db.execute("SELECT id FROM categories WHERE name = ?", (name,)).fetchone()
    return row["id"] if row else None


# ------------------------------------------------------------- CRUD helpers
_SELECT = """
    SELECT t.id, t.type, t.amount, t.date, c.name AS category,
           t.source, t.description, t.is_sample, t.created_at
    FROM transactions t
    LEFT JOIN categories c ON c.id = t.category_id
"""


def add_transaction(raw, is_sample=False):
    """Validate and insert a transaction. Returns the new id."""
    clean, errors = validate_transaction(raw)
    if errors:
        raise ValidationError(errors)
    db = get_db()
    cur = db.execute(
        """INSERT INTO transactions
           (type, amount, date, category_id, source, description, is_sample)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (clean["type"], clean["amount"], clean["date"],
         _category_id(db, clean["category"]), clean["source"],
         clean["description"], 1 if is_sample else 0),
    )
    db.commit()
    return cur.lastrowid


def get_transaction(tx_id):
    """Return one transaction row, or None if it does not exist."""
    return get_db().execute(_SELECT + " WHERE t.id = ?", (tx_id,)).fetchone()


def update_transaction(tx_id, raw):
    """Validate and update a transaction. Returns True if a row was changed."""
    clean, errors = validate_transaction(raw)
    if errors:
        raise ValidationError(errors)
    db = get_db()
    cur = db.execute(
        """UPDATE transactions
           SET type = ?, amount = ?, date = ?, category_id = ?,
               source = ?, description = ?
           WHERE id = ?""",
        (clean["type"], clean["amount"], clean["date"],
         _category_id(db, clean["category"]), clean["source"],
         clean["description"], tx_id),
    )
    db.commit()
    return cur.rowcount > 0


def delete_transaction(tx_id):
    """Delete a transaction. Returns True if a row was removed."""
    db = get_db()
    cur = db.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
    db.commit()
    return cur.rowcount > 0


def list_transactions(limit=None, offset=0, tx_type=None):
    """
    Newest first. limit=None returns everything.
    tx_type='income' or 'expense' filters by type (anything else = all).
    """
    sql = _SELECT
    params = []
    if tx_type in ("income", "expense"):
        sql += " WHERE t.type = ?"
        params.append(tx_type)
    sql += " ORDER BY t.date DESC, t.id DESC LIMIT ? OFFSET ?"
    sql_limit = -1 if limit is None else int(limit)   # SQLite: -1 means no limit
    params += [sql_limit, int(offset)]
    return get_db().execute(sql, params).fetchall()


def count_transactions(tx_type=None):
    sql = "SELECT COUNT(*) AS n FROM transactions"
    params = []
    if tx_type in ("income", "expense"):
        sql += " WHERE type = ?"
        params.append(tx_type)
    return get_db().execute(sql, params).fetchone()["n"]


# -------------------------------------------------------------- sample data
# (category, possible descriptions, min amount, max amount)
_SAMPLE_EXPENSES = [
    ("Food", ["Groceries", "Lunch at canteen", "Dinner with friends", "Snacks"], 80, 900),
    ("Transport", ["Bus pass", "Auto fare", "Fuel", "Train ticket"], 30, 600),
    ("Education", ["Textbook", "Online course", "Stationery", "Exam fee"], 150, 2500),
    ("Shopping", ["Clothes", "Headphones", "Backpack", "Shoes"], 300, 3500),
    ("Healthcare", ["Pharmacy", "Doctor visit"], 100, 1200),
    ("Entertainment", ["Movie tickets", "Streaming subscription", "Game"], 100, 900),
    ("Bills", ["Mobile recharge", "Internet bill", "Electricity bill"], 200, 1800),
    ("Other", ["Gift", "Donation", "Miscellaneous"], 50, 700),
]


def clear_sample_data():
    """Delete ONLY rows flagged is_sample = 1. Real data is never touched."""
    db = get_db()
    cur = db.execute("DELETE FROM transactions WHERE is_sample = 1")
    db.commit()
    return cur.rowcount


def seed_sample_data(today=None):
    """
    Insert about 6 months of demo transactions, flagged is_sample = 1.
    Safe to run repeatedly: old sample rows are replaced, not duplicated.
    """
    rng = random.Random(42)            # fixed seed -> same demo data every time
    today = today or date.today()
    clear_sample_data()
    count = 0

    for months_back in range(5, -1, -1):
        year, month = divmod(today.year * 12 + today.month - 1 - months_back, 12)
        month += 1

        def day_in_month(d):
            dt = date(year, month, d)
            return dt if dt <= today else None   # never create future dates

        # Income
        dt = day_in_month(1)
        if dt:
            add_transaction({"type": "income", "amount": "25000", "date": dt.isoformat(),
                             "source": "Pocket money / Salary",
                             "description": "Monthly allowance"}, is_sample=True)
            count += 1
        if rng.random() < 0.4:
            dt = day_in_month(rng.randint(5, 25))
            if dt:
                add_transaction({"type": "income",
                                 "amount": f"{rng.randint(30, 80) * 100}",
                                 "date": dt.isoformat(), "source": "Freelance",
                                 "description": "Part-time project"}, is_sample=True)
                count += 1

        # Expenses
        for _ in range(14):
            category, descriptions, low, high = rng.choice(_SAMPLE_EXPENSES)
            dt = day_in_month(rng.randint(1, 28))
            if not dt:
                continue
            add_transaction({"type": "expense",
                             "amount": f"{rng.uniform(low, high):.2f}",
                             "date": dt.isoformat(), "category": category,
                             "description": rng.choice(descriptions)}, is_sample=True)
            count += 1
    return count


# ------------------------------------------------------------------ CLI
@click.command("init-db")
def init_db_command():
    """Create the database tables."""
    init_db()
    click.echo("Database initialised.")


@click.command("seed-sample")
def seed_sample_command():
    """Load demo transactions (flagged as sample data)."""
    click.echo(f"Added {seed_sample_data()} sample transactions.")


@click.command("clear-sample")
def clear_sample_command():
    """Remove demo transactions only."""
    click.echo(f"Removed {clear_sample_data()} sample transactions.")


def init_app(app):
    """Connect this module to the Flask app."""
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.cli.add_command(seed_sample_command)
    app.cli.add_command(clear_sample_command)
    with app.app_context():
        init_db()          # tables are created automatically on startup
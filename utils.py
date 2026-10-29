"""utils.py - small helper functions shared by the app and its templates."""
from datetime import date, datetime, timedelta


def format_inr(value):
    """
    Format a number as Indian rupees with lakh/crore digit grouping.
        1234.5    -> ₹1,234.50
        125000    -> ₹1,25,000.00
        12345678  -> ₹1,23,45,678.00
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "₹0.00"
    sign = "-" if number < 0 else ""
    whole, decimals = f"{abs(number):.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]     # last 3 digits, then groups of 2
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return f"{sign}₹{whole}.{decimals}"


def budget_status(spent, budget):
    """
    Compare spending with a budget. Returns None when no budget is set.
    state: 'ok' (under 80%), 'warning' (80% up to the limit), 'over' (above the limit)
    """
    if not budget or budget <= 0:
        return None
    if spent > budget:
        state = "over"
    elif spent >= 0.8 * budget:
        state = "warning"
    else:
        state = "ok"
    percent = round(spent / budget * 100, 1)
    return {"budget": budget, "spent": spent, "percent": percent,
            "remaining": round(budget - spent, 2), "state": state,
            "bar_width": min(percent, 100)}


def parse_iso_date(text):
    """'2026-10-30' -> date object, or None if it is not a valid date (years 2000-2100)."""
    try:
        parsed = datetime.strptime(str(text).strip(), "%Y-%m-%d").date()
    except ValueError:
        return None
    return parsed if 2000 <= parsed.year <= 2100 else None


def read_date_range(args):
    """
    Read the optional 'start' and 'end' query parameters (YYYY-MM-DD).
    Returns (start, end, error): start/end are ISO strings or None.
    """
    found = {}
    for name in ("start", "end"):
        raw = args.get(name)
        if raw in (None, ""):
            continue
        parsed = parse_iso_date(raw)
        if parsed is None:
            return None, None, f"'{name}' must be a valid date in YYYY-MM-DD format."
        found[name] = parsed
    start, end = found.get("start"), found.get("end")
    if start and end and start > end:
        return None, None, "'start' must not be after 'end'."
    return (start.isoformat() if start else None,
            end.isoformat() if end else None,
            None)


def percent_change(old, new):
    """Percentage change from old to new, or None when old is zero."""
    if not old:
        return None
    return round((new - old) / old * 100, 1)


def report_presets(today, first_date=None):
    """Quick date ranges for the Reports page. The first item is the default."""
    month_start = today.replace(day=1)
    prev_end = month_start - timedelta(days=1)
    prev_start = prev_end.replace(day=1)
    year, month = divmod(today.year * 12 + today.month - 1 - 2, 12)
    three_months_start = date(year, month + 1, 1)
    first = parse_iso_date(first_date) if first_date else None

    ranges = [
        ("This month", month_start, today),
        ("Last month", prev_start, prev_end),
        ("Last 30 days", today - timedelta(days=29), today),
        ("Last 3 months", three_months_start, today),
        ("This year", today.replace(month=1, day=1), today),
        ("All time", first or month_start, today),
    ]
    return [{"label": label, "start": start.isoformat(), "end": end.isoformat()}
            for label, start, end in ranges]
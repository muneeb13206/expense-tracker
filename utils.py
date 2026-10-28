"""utils.py - small helper functions shared by the app and its templates."""


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
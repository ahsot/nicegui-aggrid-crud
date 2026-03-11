"""
formatters.py
=============
Two responsibilities:

    1. cast_row_types(row, table_model)
       Reverses the JSON round-trip type loss that occurs when row data
       travels browser -> Python.

       JSON has no Decimal type — everything numeric becomes a float.
       float("33.33") == 33.3299999999999982946974341757595539...
       Decimal(str(33.33)) == Decimal("33.33")  ✓

       We inspect the SQLModel field annotations to know which fields
       need re-casting, so this function works for any table model
       without any manual configuration.

    2. normalise_row(row)
       Light cleanup applied to every inbound row before it reaches
       submit_row — strips UI-only fields, converts empty strings to
       None, and normalises sentinel values like "NaT".

NiceGUI / AG Grid round-trip type loss summary
-----------------------------------------------
    DB type      | JSON (browser)  | After cast_row_types
    -------------|-----------------|---------------------
    Decimal      | float           | Decimal  (via str)
    int          | float           | int
    date         | str (ISO)       | str  (service layer parses)
    datetime     | str (ISO)       | str  (service layer parses)
    Enum         | str             | str  (service layer coerces)
    bool         | bool            | bool
    None / null  | null            | None
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, get_args, get_origin, Union


# ---------------------------------------------------------------------------
# cast_row_types
# ---------------------------------------------------------------------------

def cast_row_types(row: dict, table_model) -> dict:
    """
    Re-cast row values to their SQLModel field types after the JSON
    round-trip through the browser.

    Parameters
    ----------
    row : dict
        The row dict as received from the grid (post-browser).
    table_model : SQLModel class
        Used to introspect field annotations.

    Returns
    -------
    dict
        A new dict with corrected types. Fields not present in the
        table model (e.g. UI-only display columns) are left untouched.
    """
    result = dict(row)

    for field_name, field in table_model.model_fields.items():
        if field_name not in result or result[field_name] is None:
            continue

        annotation = _unwrap_optional(field.annotation)
        value      = result[field_name]

        try:
            if annotation is Decimal:
                # CRITICAL: Decimal(str(value)) not Decimal(value)
                # Decimal(33.33) inherits float imprecision.
                # Decimal("33.33") is exact.
                result[field_name] = Decimal(str(value))

            elif annotation is int and not isinstance(value, bool):
                result[field_name] = int(value)

            elif annotation is bool and not isinstance(value, bool):
                result[field_name] = str(value).lower() in ("true", "1", "yes")

            elif annotation is datetime and isinstance(value, str):
                # Parse ISO string back to datetime — SQLAlchemy requires
                # a real datetime object, not a string.
                # Strip trailing Z or timezone offset for simplicity.
                clean = value.replace("Z", "").split("+")[0]
                # Handle both with and without microseconds
                for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
                    try:
                        result[field_name] = datetime.strptime(clean, fmt)
                        break
                    except ValueError:
                        continue

            elif annotation is date and isinstance(value, str):
                # Parse ISO date string back to date object
                result[field_name] = date.fromisoformat(value)

        except (ValueError, TypeError, InvalidOperation):
            # Leave the value as-is if casting fails — the service layer
            # or database will surface a meaningful error.
            pass

    return result


# ---------------------------------------------------------------------------
# normalise_row
# ---------------------------------------------------------------------------

_SENTINEL_NULLS = {"NaT", "None", "null", "nan", ""}


def normalise_row(row: dict, ui_only_fields: set[str] | None = None) -> dict:
    """
    Light cleanup applied to every row before it reaches submit_row.

    - Removes UI-only display columns (e.g. product_name in ShoppingCart
      where product_id is the real FK — but only if explicitly flagged).
    - Converts empty strings and sentinel null values to None.

    Parameters
    ----------
    row : dict
    ui_only_fields : set[str] | None
        Field names that exist in the grid for display purposes only
        and should be stripped before writing to the database.
        Example: {"product_name"} for ShoppingCart where product_id
        is the real FK and product_name is a vlookup display column.

    Returns
    -------
    dict
        Cleaned row dict.
    """
    result = {}
    drop   = ui_only_fields or set()

    for key, value in row.items():
        if key in drop:
            continue
        if isinstance(value, str) and value in _SENTINEL_NULLS:
            result[key] = None
        else:
            result[key] = value

    return result


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _unwrap_optional(annotation: Any) -> Any:
    """
    Unwrap Optional[X] (which is Union[X, None]) to return X.
    Returns the annotation unchanged if it is not Optional.
    """
    if get_origin(annotation) is Union:
        args = [a for a in get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return args[0]
    return annotation
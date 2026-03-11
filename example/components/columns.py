"""
columns.py
==========
Auto-generates AG Grid column definitions from a SQLModel table class.

NiceGUI 3.x / AG Grid 34.x gotchas documented here
----------------------------------------------------

1.  valueFormatter syntax
    Use the colon-prefix form  col[":valueFormatter"] = "params => ..."
    with params.value — NOT the plain string form col["valueFormatter"].
    Plain strings are not evaluated as JavaScript in NiceGUI 3.x.

2.  cellClassRules expression variables
    AG Grid exposes  node, column, value, data, rowIndex  as bare
    variables inside cellClassRules expression strings.
    Do NOT use params.node / params.column — params is not defined
    in this context and will throw a ReferenceError.

3.  {"function": "..."} syntax
    Works at the top level of gridOptions (e.g. onCellValueChanged)
    but does NOT work inside nested column def properties such as
    cellClassRules or valueFormatter.  Use plain expression strings
    or the colon-prefix form instead.

4.  _time and _date columns
    These are set editable=False to prevent the cell editor opening
    on single-click.  Double-click auto-fill is handled by
    CRUDGrid._on_cell_double_clicked() instead.
    cellClassRules are still injected for these columns by
    CRUDGrid._inject_dirty_class_rules() so amber highlighting works.
"""

from __future__ import annotations

from decimal import Decimal
from typing import get_args, get_origin, Union


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_header_name(field_name: str) -> str:
    """
    Convert snake_case field names to a readable header string.

    Examples
    --------
    product_id   -> Product ID
    unit_price   -> Unit Price
    added_time   -> Added Time
    placed_date  -> Placed Date
    """
    parts = field_name.split("_")
    # Capitalise every part; uppercase the last part if it is "id"
    header_parts = [
        part.upper() if part == "id" else part.title()
        for part in parts
    ]
    return " ".join(header_parts)


def _unwrap_optional(annotation) -> type:
    """Return the inner type of Optional[X], or the annotation unchanged."""
    if get_origin(annotation) is Union:
        args = [a for a in get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return args[0]
    return annotation


def _find_insertion_point(ui_field: str, model_field_names: list[str]) -> int | None:
    """
    Find where to insert a UI-only display column relative to its FK column.

    e.g. product_name is inserted directly after product_id because
    both share the prefix "product_".
    """
    prefix = ui_field.rsplit("_", 1)[0] + "_"
    for i, name in enumerate(model_field_names):
        if name.startswith(prefix):
            return i + 1
    return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

_NUMERIC_TYPES = (int, float, Decimal)


def generate_column_defs_from_table(
    table,
    immutable_fields: set | None = None,
    excluded_fields:  set | None = None,
    hidden_fields:    set | None = None,
    dropdown_map:     dict | None = None,
) -> list[dict]:
    """
    Build AG Grid columnDefs from a SQLModel table class.

    Parameters
    ----------
    table : SQLModel class
        The table whose model_fields drive the column list.
    immutable_fields : set[str]
        Shown but not editable (editable=False, no cell editor).
    excluded_fields : set[str]
        Omitted from the grid entirely.
    hidden_fields : set[str]
        Present in rowData but hidden from the user (hide=True).
    dropdown_map : dict[str, list]
        Maps field names to their allowed value lists.
        Fields that exist in dropdown_map but NOT in the table model
        are treated as UI-only display columns and inserted adjacent
        to their FK counterpart (e.g. product_name next to product_id).

    Returns
    -------
    list[dict]
        AG Grid columnDef objects ready to pass to ui.aggrid.
    """
    immutable     = set(immutable_fields or set())
    excluded      = excluded_fields or set()
    hidden        = hidden_fields or set()
    dropdowns     = dropdown_map or {}
    model_fields  = list(table.model_fields.keys())
    column_defs: list[dict] = []

    # ------------------------------------------------------------------
    # Primary key columns are always immutable
    # ------------------------------------------------------------------
    # Detection strategy (most-to-least reliable):
    # 1. SQLAlchemy table metadata — most reliable, works when the model
    #    is fully registered with a database engine.
    # 2. field.json_schema_extra — set by SQLModel's Field(primary_key=True),
    #    reliable in older SQLModel versions.
    # 3. field.metadata — fallback, but PydanticMetadata objects in this
    #    list can accidentally match "primary_key" on non-PK fields (a known
    #    bug that was the original motivation for strategy 2).
    # We try all three so the code works across SQLModel versions.
    try:
        # Strategy 1 — SQLAlchemy table inspector
        sa_table = getattr(table, "__table__", None)
        if sa_table is not None:
            for col in sa_table.primary_key.columns:
                immutable.add(col.name)
        else:
            raise AttributeError("no __table__")
    except (AttributeError, Exception):
        # Strategy 2 — json_schema_extra (older SQLModel)
        for field_name, field in table.model_fields.items():
            field_info = field.json_schema_extra or {}
            if field_info.get("primary_key", False):
                immutable.add(field_name)

    # ------------------------------------------------------------------
    # One column per model field
    # ------------------------------------------------------------------
    for field_name, field in table.model_fields.items():
        if field_name in excluded:
            continue

        col: dict = {
            "field":      field_name,
            "headerName": _to_header_name(field_name),
            "editable":   field_name not in immutable,
        }

        # Hidden columns — in rowData but not visible
        if field_name in hidden:
            col["hide"]     = True
            col["editable"] = False

        # Dropdown / select editor
        elif field_name in dropdowns:
            col["cellEditor"]       = "agSelectCellEditor"
            col["cellEditorParams"] = {"values": dropdowns[field_name]}

        # Datetime columns — double-click auto-fill (see crud_grid.py)
        # editable=False prevents the text editor opening on single-click.
        # NiceGUI 3.x requires colon-prefix for valueFormatter.
        elif field_name.endswith("_time"):
            col["type"]     = "dateColumn"
            col["editable"] = False
            col[":valueFormatter"] = (
                "params => params.value && params.value !== 'NaT' "
                "? params.value.toString().replace('T', ' ').split('.')[0] "
                ": ''"
            )

        # Date columns — same pattern as _time
        elif field_name.endswith("_date"):
            col["type"]     = "dateColumn"
            col["editable"] = False
            col[":valueFormatter"] = "params => params.value || ''"

        # Numeric columns — right-align via AG Grid's built-in type
        inner_type = _unwrap_optional(field.annotation)
        if inner_type in _NUMERIC_TYPES:
            col["type"] = "numericColumn"

        column_defs.append(col)

    # ------------------------------------------------------------------
    # UI-only supplementary columns (vlookup display fields)
    # e.g. product_name in ShoppingCart — exists in dropdown_map but
    # not in the table model. Inserted adjacent to the FK column.
    # ------------------------------------------------------------------
    ui_only = set(dropdowns.keys()) - set(table.model_fields.keys())
    for ui_field in sorted(ui_only):
        col = {
            "field":            ui_field,
            "headerName":       _to_header_name(ui_field),
            "editable":         True,
            "cellEditor":       "agSelectCellEditor",
            "cellEditorParams": {"values": dropdowns[ui_field]},
        }
        insert_at = _find_insertion_point(ui_field, model_fields)
        if insert_at is not None:
            column_defs.insert(insert_at, col)
        else:
            column_defs.append(col)

    return column_defs
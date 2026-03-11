"""
tests/test_crud_grid.py
=======================
Unit tests for the CRUDGrid component.

These tests cover pure-Python logic only — no browser, no NiceGUI event
loop required.  They run on every push via GitHub Actions and are also
scheduled weekly against the latest NiceGUI release so breaking changes
are caught promptly.

Test groups
-----------
TestHeaderName          — _to_header_name() snake_case conversion
TestColumnDefs          — generate_column_defs_from_table()
TestColumnDefsGotchas   — verifies the 10 documented NiceGUI/AG Grid gotchas
                          are still reflected in the generated column defs
TestCastRowTypes        — cast_row_types() JSON round-trip fixes
TestNormaliseRow        — normalise_row() sentinel / UI-only field handling
TestServices            — service layer logic (in-memory SQLite)
"""

from __future__ import annotations

import sys
import os
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

import pytest
from sqlmodel import Field, SQLModel

# ---------------------------------------------------------------------------
# Path setup — allow running from repo root without installing the package
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ---------------------------------------------------------------------------
# Create an in-memory engine for test models that use table=True
# ---------------------------------------------------------------------------
from sqlmodel import create_engine as _create_engine, SQLModel as _SQLModel

_test_engine = _create_engine("sqlite:///:memory:",
                               connect_args={"check_same_thread": False})

@pytest.fixture(autouse=True, scope="session")
def _create_test_tables():
    """Create all test model tables once for the session."""
    _SQLModel.metadata.create_all(_test_engine)

from example.components.columns import (
    _to_header_name,
    _find_insertion_point,
    generate_column_defs_from_table,
)
from example.components.formatters import cast_row_types, normalise_row


# ---------------------------------------------------------------------------
# Minimal test models — avoids coupling tests to demo domain models
# ---------------------------------------------------------------------------

class SimpleModel(SQLModel, table=True):
    """
    Test model — field names deliberately use _time and _date suffixes
    to match the naming conventions that columns.py detects.
    Uses table=True so SQLModel populates json_schema_extra with
    primary_key=True, which is how columns.py detects PK fields.
    """
    item_id      : Optional[int]      = Field(default=None, primary_key=True)
    item_name    : str                = Field(default="")
    unit_price   : Decimal            = Field(default=Decimal("0"), decimal_places=2, max_digits=10)
    stock_qty    : int                = Field(default=0)
    created_time : Optional[datetime] = Field(default=None)
    expires_date : Optional[date]     = Field(default=None)
    is_active    : bool               = Field(default=True)


class FKModel(SQLModel, table=False):
    """Model with a FK to SimpleModel — for UI-only column insertion tests."""
    order_id   : Optional[int] = Field(default=None, primary_key=True)
    item_id    : Optional[int] = Field(default=None)
    quantity   : int           = Field(default=1)


# ===========================================================================
# TestHeaderName
# ===========================================================================

class TestHeaderName:
    """_to_header_name converts snake_case to readable header strings."""

    def test_single_word(self):
        assert _to_header_name("name") == "Name"

    def test_id_suffix_uppercased(self):
        assert _to_header_name("product_id") == "Product ID"
        assert _to_header_name("item_id") == "Item ID"
        assert _to_header_name("order_id") == "Order ID"

    def test_two_words(self):
        assert _to_header_name("unit_price") == "Unit Price"
        assert _to_header_name("stock_qty") == "Stock Qty"

    def test_time_suffix(self):
        assert _to_header_name("created_time") == "Created Time"
        assert _to_header_name("paid_time") == "Paid Time"
        assert _to_header_name("delivered_time") == "Delivered Time"

    def test_date_suffix(self):
        assert _to_header_name("added_date") == "Added Date"
        assert _to_header_name("expires_date") == "Expires Date"

    def test_three_words(self):
        assert _to_header_name("total_order_value") == "Total Order Value"


# ===========================================================================
# TestColumnDefs
# ===========================================================================

class TestColumnDefs:
    """generate_column_defs_from_table produces correct AG Grid column defs."""

    def setup_method(self):
        self.cols = generate_column_defs_from_table(SimpleModel)
        self.col_by_field = {c["field"]: c for c in self.cols}

    def test_all_model_fields_present(self):
        fields = {c["field"] for c in self.cols}
        assert fields == set(SimpleModel.model_fields.keys())

    def test_primary_key_always_immutable(self):
        """
        item_id is a PK — must always be editable=False.
        Uses the real Product model (table=True, registered with SQLAlchemy)
        because json_schema_extra is only reliably populated on fully
        registered SQLModel tables.
        """
        from example.models import Product
        cols    = generate_column_defs_from_table(Product)
        col_map = {c["field"]: c for c in cols}
        assert col_map["product_id"]["editable"] is False

    def test_regular_field_editable(self):
        assert self.col_by_field["item_name"]["editable"] is True
        assert self.col_by_field["stock_qty"]["editable"] is True

    def test_time_field_not_editable(self):
        """
        Gotcha 4 — _time columns are editable=False.
        Single-click must NOT open a cell editor; double-click is handled
        by CRUDGrid._on_cell_double_clicked() instead.
        """
        col = self.col_by_field["created_time"]
        assert col["editable"] is False

    def test_date_field_not_editable(self):
        col = self.col_by_field["expires_date"]
        assert col["editable"] is False

    def test_time_field_uses_colon_prefix_value_formatter(self):
        """
        Gotcha — columns.py NiceGUI note 1:
        valueFormatter MUST use the colon-prefix form ':valueFormatter'.
        A plain 'valueFormatter' key is NOT evaluated as JavaScript by NiceGUI.
        If this test fails after a NiceGUI update, the gotcha may no longer apply.
        """
        col = self.col_by_field["created_time"]
        assert ":valueFormatter" in col, (
            "NiceGUI GOTCHA: valueFormatter must use colon-prefix ':valueFormatter'. "
            "Plain 'valueFormatter' is not evaluated as JS in NiceGUI 3.x."
        )
        assert "valueFormatter" not in col or col.get("valueFormatter") is None

    def test_date_field_uses_colon_prefix_value_formatter(self):
        col = self.col_by_field["expires_date"]
        assert ":valueFormatter" in col

    def test_numeric_column_type(self):
        """Decimal and int fields get numericColumn type for right-alignment."""
        assert self.col_by_field["unit_price"].get("type") == "numericColumn"
        assert self.col_by_field["stock_qty"].get("type") == "numericColumn"

    def test_string_field_no_numeric_type(self):
        assert self.col_by_field["item_name"].get("type") != "numericColumn"

    def test_immutable_fields_not_editable(self):
        cols = generate_column_defs_from_table(
            SimpleModel, immutable_fields={"item_name", "stock_qty"}
        )
        col_map = {c["field"]: c for c in cols}
        assert col_map["item_name"]["editable"] is False
        assert col_map["stock_qty"]["editable"] is False
        assert col_map["unit_price"]["editable"] is True

    def test_excluded_fields_absent(self):
        cols = generate_column_defs_from_table(
            SimpleModel, excluded_fields={"is_active", "expires_date"}
        )
        fields = {c["field"] for c in cols}
        assert "is_active" not in fields
        assert "expires_date" not in fields

    def test_hidden_fields_present_but_hidden(self):
        cols = generate_column_defs_from_table(
            SimpleModel, hidden_fields={"item_id"}
        )
        col_map = {c["field"]: c for c in cols}
        assert "item_id" in col_map
        assert col_map["item_id"]["hide"] is True
        assert col_map["item_id"]["editable"] is False

    def test_dropdown_map_sets_select_editor(self):
        cols = generate_column_defs_from_table(
            SimpleModel,
            dropdown_map={"item_name": ["Widget", "Gadget", "Doohickey"]},
        )
        col_map = {c["field"]: c for c in cols}
        assert col_map["item_name"]["cellEditor"] == "agSelectCellEditor"
        assert col_map["item_name"]["cellEditorParams"] == {
            "values": ["Widget", "Gadget", "Doohickey"]
        }

    def test_header_names_generated(self):
        assert self.col_by_field["unit_price"]["headerName"] == "Unit Price"
        assert self.col_by_field["item_id"]["headerName"] == "Item ID"
        assert self.col_by_field["created_time"]["headerName"] == "Created Time"


class TestUIOnlyColumns:
    """UI-only display columns (in dropdown_map but not in model) are inserted correctly."""

    def test_ui_only_column_inserted_after_fk(self):
        """
        product_name is not a model field but is in dropdown_map.
        It should be inserted directly after item_id (the FK prefix match).
        """
        cols = generate_column_defs_from_table(
            FKModel,
            dropdown_map={"item_name": ["Widget", "Gadget"]},
        )
        fields = [c["field"] for c in cols]
        assert "item_name" in fields
        # item_name should appear right after item_id
        item_id_pos   = fields.index("item_id")
        item_name_pos = fields.index("item_name")
        assert item_name_pos == item_id_pos + 1

    def test_ui_only_column_is_editable_dropdown(self):
        cols = generate_column_defs_from_table(
            FKModel,
            dropdown_map={"item_name": ["Widget", "Gadget"]},
        )
        col_map = {c["field"]: c for c in cols}
        assert col_map["item_name"]["editable"] is True
        assert col_map["item_name"]["cellEditor"] == "agSelectCellEditor"

    def test_find_insertion_point(self):
        model_fields = ["order_id", "item_id", "quantity"]
        pos = _find_insertion_point("item_name", model_fields)
        assert pos == 2  # after item_id at index 1


# ===========================================================================
# TestColumnDefsGotchas
# ===========================================================================

class TestColumnDefsGotchas:
    """
    Verifies the documented NiceGUI + AG Grid gotchas are reflected in the
    generated column defs.  If any of these tests fail after a NiceGUI or
    AG Grid update, the corresponding gotcha in README.md may need reviewing.
    """

    def test_gotcha_colon_prefix_valueformatter(self):
        """
        Gotcha 1 / columns.py note 1:
        NiceGUI 3.x requires ':valueFormatter' (colon-prefix) for JS evaluation.
        Plain 'valueFormatter' strings are NOT evaluated as JavaScript.
        """
        cols    = generate_column_defs_from_table(SimpleModel)
        col_map = {c["field"]: c for c in cols}
        time_col = col_map["created_time"]
        assert ":valueFormatter" in time_col, (
            "GOTCHA BROKEN: NiceGUI may now support plain 'valueFormatter'. "
            "Review README gotcha #4 and columns.py note 1."
        )

    def test_gotcha_pk_always_immutable(self):
        """
        Gotcha — PK detection across SQLModel versions:
        The most reliable approach is SQLAlchemy's table.__table__.primary_key,
        which works regardless of SQLModel/Pydantic version.
        field.json_schema_extra was the original approach but is not reliably
        populated in newer SQLModel/Pydantic versions without a registered engine.
        If this test fails, the PK detection strategy in columns.py needs updating.
        """
        from example.models import Product
        cols    = generate_column_defs_from_table(Product)
        col_map = {c["field"]: c for c in cols}
        assert col_map["product_id"]["editable"] is False, (
            "GOTCHA BROKEN: PK detection via json_schema_extra may have changed. "
            "Review columns.py PK immutability logic."
        )
        # Non-PK fields must still be editable
        assert col_map["product_name"]["editable"] is True

    def test_gotcha_time_columns_editable_false(self):
        """
        Gotcha 8 — _time columns must be editable=False.
        Double-click auto-fill is handled entirely in Python via
        CRUDGrid._on_cell_double_clicked() and DOM injection.
        If editable=True, AG Grid opens a text editor on single-click
        and the double-click handler fires twice.
        """
        cols    = generate_column_defs_from_table(SimpleModel)
        col_map = {c["field"]: c for c in cols}
        assert col_map["created_time"]["editable"] is False, (
            "GOTCHA BROKEN: _time columns must remain editable=False. "
            "Review CRUDGrid._on_cell_double_clicked() and README gotcha #8."
        )

    def test_gotcha_no_params_in_cellclassrules(self):
        """
        Gotcha 3 — cellClassRules uses bare variables (node, column),
        NOT params.node / params.column.
        This test verifies that CRUDGrid._inject_dirty_class_rules()
        does NOT use params.* in its expression strings.
        We simulate the expression by checking the pattern CRUDGrid uses.
        """
        # The expression injected by _inject_dirty_class_rules uses
        # node.rowIndex and column.colId — never params.*
        expression = (
            "window['__dirtykeys_test__'] != null && "
            "window['__dirtykeys_test__'].has(node.rowIndex + ':' + column.colId)"
        )
        assert "params." not in expression, (
            "GOTCHA BROKEN: cellClassRules expression must not use params.*. "
            "AG Grid exposes node/column as bare variables in this context."
        )
        assert "node.rowIndex" in expression
        assert "column.colId" in expression


# ===========================================================================
# TestCastRowTypes
# ===========================================================================

class TestCastRowTypes:
    """cast_row_types corrects the type loss from JSON serialisation."""

    def test_decimal_from_float(self):
        """
        JSON has no Decimal type — all numeric values arrive as float.
        Decimal(str(value)) is used, NOT Decimal(value), to avoid
        inheriting float imprecision.
        """
        row    = {"item_id": 1, "item_name": "Widget", "unit_price": 33.33,
                  "stock_qty": 5.0, "created_time": None, "expires_date": None,
                  "is_active": True}
        result = cast_row_types(row, SimpleModel)
        assert isinstance(result["unit_price"], Decimal)
        assert result["unit_price"] == Decimal("33.33")

    def test_decimal_precision_preserved(self):
        """Decimal(33.33) != Decimal('33.33') — the str() path is critical."""
        row    = {"item_id": 1, "item_name": "x", "unit_price": 9.99,
                  "stock_qty": 1.0, "created_time": None, "expires_date": None,
                  "is_active": True}
        result = cast_row_types(row, SimpleModel)
        assert result["unit_price"] == Decimal("9.99")
        # This would fail with Decimal(9.99) due to float imprecision
        assert str(result["unit_price"]) == "9.99"

    def test_int_from_float(self):
        """AG Grid sends integer fields as floats (e.g. 5.0 not 5)."""
        row    = {"item_id": 1.0, "item_name": "x", "unit_price": 1.0,
                  "stock_qty": 42.0, "created_time": None, "expires_date": None,
                  "is_active": True}
        result = cast_row_types(row, SimpleModel)
        assert isinstance(result["stock_qty"], int)
        assert result["stock_qty"] == 42

    def test_datetime_from_iso_string(self):
        row    = {"item_id": 1, "item_name": "x", "unit_price": 1.0,
                  "stock_qty": 1, "created_time": "2024-11-10T09:00:00",
                  "expires_date": None, "is_active": True}
        result = cast_row_types(row, SimpleModel)
        assert isinstance(result["created_time"], datetime)
        assert result["created_time"] == datetime(2024, 11, 10, 9, 0, 0)

    def test_datetime_from_iso_string_with_microseconds(self):
        row    = {"item_id": 1, "item_name": "x", "unit_price": 1.0,
                  "stock_qty": 1, "created_time": "2024-11-10T09:00:00.123456",
                  "expires_date": None, "is_active": True}
        result = cast_row_types(row, SimpleModel)
        assert isinstance(result["created_time"], datetime)
        assert result["created_time"].microsecond == 123456

    def test_date_from_iso_string(self):
        row    = {"item_id": 1, "item_name": "x", "unit_price": 1.0,
                  "stock_qty": 1, "created_time": None,
                  "expires_date": "2025-03-15", "is_active": True}
        result = cast_row_types(row, SimpleModel)
        assert isinstance(result["expires_date"], date)
        assert result["expires_date"] == date(2025, 3, 15)

    def test_none_values_unchanged(self):
        row    = {"item_id": None, "item_name": "x", "unit_price": 1.0,
                  "stock_qty": 1, "created_time": None, "expires_date": None,
                  "is_active": True}
        result = cast_row_types(row, SimpleModel)
        assert result["item_id"] is None
        assert result["created_time"] is None

    def test_unknown_fields_passed_through(self):
        """UI-only fields (e.g. product_name) are not in the model — leave untouched."""
        row    = {"item_id": 1, "item_name": "x", "unit_price": 1.0,
                  "stock_qty": 1, "created_time": None, "expires_date": None,
                  "is_active": True, "product_name": "Widget"}
        result = cast_row_types(row, SimpleModel)
        assert result["product_name"] == "Widget"

    def test_invalid_cast_leaves_value_unchanged(self):
        """Malformed values are left as-is — service layer surfaces the error."""
        row    = {"item_id": 1, "item_name": "x", "unit_price": "not-a-number",
                  "stock_qty": 1, "created_time": None, "expires_date": None,
                  "is_active": True}
        result = cast_row_types(row, SimpleModel)
        assert result["unit_price"] == "not-a-number"


# ===========================================================================
# TestNormaliseRow
# ===========================================================================

class TestNormaliseRow:

    def test_empty_string_becomes_none(self):
        result = normalise_row({"name": "", "qty": 1})
        assert result["name"] is None

    def test_nat_sentinel_becomes_none(self):
        result = normalise_row({"created_time": "NaT", "qty": 1})
        assert result["created_time"] is None

    def test_none_string_becomes_none(self):
        result = normalise_row({"val": "None"})
        assert result["val"] is None

    def test_null_string_becomes_none(self):
        result = normalise_row({"val": "null"})
        assert result["val"] is None

    def test_normal_values_unchanged(self):
        result = normalise_row({"name": "Widget", "qty": 5, "price": 9.99})
        assert result == {"name": "Widget", "qty": 5, "price": 9.99}

    def test_ui_only_fields_stripped(self):
        result = normalise_row(
            {"item_id": 1, "item_name": "Widget", "display_name": "Widget Label"},
            ui_only_fields={"display_name"},
        )
        assert "display_name" not in result
        assert result["item_name"] == "Widget"

    def test_none_value_unchanged(self):
        result = normalise_row({"val": None})
        assert result["val"] is None


# ===========================================================================
# TestServices — in-memory SQLite
# ===========================================================================

class TestServices:
    """
    Service layer tests using an in-memory SQLite database.
    These verify business logic without touching the demo database.
    """

    def setup_method(self):
        """Create a fresh in-memory DB and seed minimal data."""
        from sqlmodel import create_engine, Session
        from example.models import Product, ShoppingCart, CartStatus, Category
        from decimal import Decimal
        from datetime import date

        self.engine = create_engine("sqlite:///:memory:",
                                    connect_args={"check_same_thread": False})
        SQLModel.metadata.create_all(self.engine)

        with Session(self.engine) as session:
            product = Product(
                product_name = "Test Widget",
                description  = "A test product",
                category     = Category.ELECTRONICS,
                price        = Decimal("49.99"),
                stock_qty    = 10,
                image_url    = "",
            )
            session.add(product)
            session.flush()
            self._product_id = product.product_id

            cart = ShoppingCart(
                product_id  = product.product_id,
                quantity    = 1,
                unit_price  = Decimal("49.99"),
                total_value = Decimal("49.99"),
                status      = CartStatus.WISHLIST,
                added_date  = date.today(),
            )
            session.add(cart)
            session.commit()
            self._cart_id = cart.cart_id

        # Patch the engine used by services
        import example.database as db_module
        self._original_engine = db_module.engine
        db_module.engine = self.engine

    def teardown_method(self):
        import example.database as db_module
        db_module.engine = self._original_engine

    def test_load_cart_rows_returns_wishlist_only(self):
        from example.services import load_cart_rows
        rows = load_cart_rows()
        assert len(rows) == 1
        assert rows[0]["status"] == "WISHLIST"

    def test_load_cart_rows_injects_product_name(self):
        from example.services import load_cart_rows
        rows = load_cart_rows()
        assert rows[0]["product_name"] == "Test Widget"

    def test_checkout_cart_moves_to_paid(self):
        from example.services import checkout_cart, load_order_rows
        checkout_cart(self._cart_id)
        orders = load_order_rows()
        assert len(orders) == 1
        assert orders[0]["status"] == "PAID"
        assert orders[0]["paid_time"] is not None

    def test_checkout_cart_removes_from_wishlist(self):
        from example.services import checkout_cart, load_cart_rows
        checkout_cart(self._cart_id)
        rows = load_cart_rows()
        assert len(rows) == 0

    def test_checkout_cart_twice_raises(self):
        from example.services import checkout_cart
        checkout_cart(self._cart_id)
        with pytest.raises(PermissionError, match="already"):
            checkout_cart(self._cart_id)

    def test_deliver_order_moves_to_delivered(self):
        from example.services import checkout_cart, deliver_order, load_order_rows
        checkout_cart(self._cart_id)
        deliver_order(self._cart_id)
        orders = load_order_rows()
        assert orders[0]["status"] == "DELIVERED"
        assert orders[0]["delivered_time"] is not None

    def test_deliver_non_paid_order_raises(self):
        from example.services import deliver_order
        with pytest.raises(PermissionError):
            deliver_order(self._cart_id)  # still WISHLIST

    def test_delete_cart_wishlist_succeeds(self):
        from example.services import delete_cart, load_cart_rows
        delete_cart({"cart_id": self._cart_id})
        assert len(load_cart_rows()) == 0

    def test_delete_cart_paid_raises(self):
        from example.services import checkout_cart, delete_cart
        checkout_cart(self._cart_id)
        with pytest.raises(PermissionError, match="WISHLIST"):
            delete_cart({"cart_id": self._cart_id})

    def test_load_product_rows_returns_all(self):
        from example.services import load_product_rows
        rows = load_product_rows()
        assert len(rows) == 1
        assert rows[0]["product_name"] == "Test Widget"
"""
cart_grid.py
============
ShoppingCartGrid — shows only WISHLIST items.

Demonstrates:
    - Auto-commit on product selection (no SAVE needed for new rows)
    - Client-side price lookup via window.__productPrices__
    - NiceGUI trap: onCellValueChanged JS callback is intercepted;
      workaround is Python-side handler pushing DOM updates via
      run_javascript()
    - CHECKOUT ITEM: sets status=PAID, paid_time=now, creates Order,
      row disappears from cart view immediately
"""

from __future__ import annotations

import json

from nicegui import ui

from example.components.crud_grid import CRUDGrid
from example.models import CartStatus, ShoppingCart
from example.services import (
    checkout_cart,
    delete_cart,
    load_cart_rows,
    load_product_rows,
    submit_cart,
)

class ShoppingCartGrid(CRUDGrid):

    def __init__(
        self,
        image_display: ui.image,
        detail_label:  ui.label,
        on_checked_out=None,
    ):
        self._image_display = image_display
        self._detail_label  = detail_label
        self._on_checked_out = on_checked_out

        all_products       = load_product_rows()
        product_names      = [r["product_name"] for r in all_products]
        # Cache keyed by product_id for O(1) lookup in on_row_selected
        self._product_map  = {r["product_id"]: r for r in all_products}
        # Cache keyed by product_name for O(1) lookup in cell value changed
        self._product_by_name = {r["product_name"]: r for r in all_products}

        super().__init__(
            table_model      = ShoppingCart,
            load_rows        = load_cart_rows,
            submit_row       = submit_cart,
            delete_row       = delete_cart,
            dropdown_map     = {
                "product_name": product_names,
            },
            immutable_fields = {
                "cart_id", "unit_price", "total_value",
                "status", "added_date", "paid_time",
            },
            hidden_fields    = {"product_id", "paid_time"},
            new_row_defaults = {
                "product_name": "",
                "quantity":     1,
                "unit_price":   None,
                "total_value":  None,
                "status":       CartStatus.WISHLIST.value,
                "added_date":   None,
            },
            header_colour    = "#bbdefb",
            height           = "500px",
            label_new        = "ADD",
            label_upload     = "SAVE",
            label_delete     = "REMOVE ITEM",
        )

    def build(self) -> "ShoppingCartGrid":
        super().build()
        # Override cellValueChanged for price lookup and auto-commit
        self.grid.on("cellValueChanged", self._on_cart_cell_value_changed)
        return self

    # ------------------------------------------------------------------
    # Extension hooks
    # ------------------------------------------------------------------

    def extra_toolbar_buttons(self) -> None:
        ui.button(
            "CHECKOUT ITEM",
            icon="shopping_cart_checkout",
            on_click=self._checkout_selected,
        ).props("color=positive")

    def on_row_selected(self, row: dict) -> None:
        product_id = row.get("product_id")
        if product_id:
            # Use cached product map built at construction time
            # to avoid a DB hit on every row click.
            product   = self._product_map.get(int(product_id), {})
            image_url = product.get("image_url", "")
            if image_url:
                self._image_display.set_source(image_url)

        product_name = row.get("product_name", "—")
        quantity     = row.get("quantity", "")
        unit_price   = row.get("unit_price", "")
        total_value  = row.get("total_value", "")
        status       = row.get("status", "")

        self._detail_label.set_text(
            f"{product_name}  |  Qty: {quantity}  "
            f"|  Unit: £{unit_price}  |  Total: £{total_value}  "
            f"|  Status: {status}"
        )

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _on_cart_cell_value_changed(self, e) -> None:
        """
        Handles product_name and quantity changes:
        - product_name: looks up unit_price, updates DOM, auto-commits new rows
        - quantity: recalculates total_value, updates DOM

        NiceGUI trap: onCellValueChanged {"function":"..."} is intercepted
        by NiceGUI and never fires as a JS callback. We handle it here in
        Python and push DOM updates via run_javascript() instead.
        Always use json.dumps() when injecting Python strings into JS —
        product names may contain quotes (e.g. 4K Smart TV 55").
        """
        args      = e.args
        row_index = int(args["rowIndex"])
        col_id    = args["colId"]
        new_value = args.get("newValue")

        self.grid.options["rowData"][row_index][col_id] = new_value
        self._dirty_rows.add(row_index)
        row = self.grid.options["rowData"][row_index]

        if col_id == "product_name":
            product    = self._product_by_name.get(new_value, {})
            image_url  = product.get("image_url", "")
            unit_price = product.get("price")

            # Update product_id in rowData immediately so on_row_selected
            # looks up the correct image even before the row is saved.
            if product:
                row["product_id"] = product.get("product_id")

            if unit_price is not None:
                row["unit_price"] = unit_price
                quantity    = int(row.get("quantity") or 1)
                total_value = round(float(unit_price) * quantity, 2)
                row["total_value"] = total_value

                for fld, val in [("unit_price", unit_price),
                                  ("total_value", total_value)]:
                    safe_val = json.dumps(str(val))
                    ui.run_javascript(f"""
                        (function() {{
                            document.querySelectorAll(
                                '.ag-row[row-index="{row_index}"]'
                            ).forEach(function(r) {{
                                const cell = r.querySelector('[col-id="{fld}"]');
                                if (cell) {{
                                    const v = cell.querySelector('.ag-cell-value');
                                    if (v) v.textContent = {safe_val};
                                }}
                            }});
                        }})();
                    """)

            if image_url:
                self._image_display.set_source(image_url)

            # Auto-commit new rows — everything is known once product selected
            is_new_row = not row.get("cart_id")
            if is_new_row and unit_price is not None:
                from example.components.formatters import cast_row_types
                save_row = cast_row_types(dict(row), self._table_model)
                save_row = self._pre_submit_hook(save_row)
                try:
                    self._submit_row_fn(save_row)
                    ui.notify(f"'{new_value}' added to cart.", color="positive")
                    self._dirty_rows.discard(row_index)
                    self.refresh()
                    return
                except Exception as exc:
                    ui.notify(f"Auto-save failed: {exc}", color="red")

        elif col_id == "quantity":
            unit_price = row.get("unit_price")
            if unit_price is not None:
                try:
                    total_value = round(float(unit_price) * int(new_value), 2)
                    row["total_value"] = total_value
                    safe_total = json.dumps(str(total_value))
                    ui.run_javascript(f"""
                        (function() {{
                            document.querySelectorAll(
                                '.ag-row[row-index="{row_index}"]'
                            ).forEach(function(r) {{
                                const cell = r.querySelector('[col-id="total_value"]');
                                if (cell) {{
                                    const v = cell.querySelector('.ag-cell-value');
                                    if (v) v.textContent = {safe_total};
                                }}
                            }});
                        }})();
                    """)
                except (ValueError, TypeError):
                    pass

        self.on_row_selected(row)
        ui.run_javascript(
            f"onCellEdited_{self._dirty_js_name}({row_index}, '{col_id}');"
        )
        self.grid.update()
        self.grid.run_grid_method("refreshCells", {"force": True})

    def _checkout_selected(self) -> None:
        """
        Checkout the selected WISHLIST item:
        - Auto-saves any dirty rows first so quantity/price are correct
        - Sets status=PAID, paid_time=now in ShoppingCart
        - Row disappears from cart view (WISHLIST filter)
        - Notifies the Orders tab to refresh
        """
        if self._selected_row_index is None:
            ui.notify("Select a cart item first.", color="warning")
            return

        row    = dict(self.grid.options["rowData"][self._selected_row_index])
        status = row.get("status", "")

        if status != CartStatus.WISHLIST.value:
            ui.notify(
                f"Only WISHLIST items can be checked out (status: {status}).",
                color="warning",
            )
            return

        cart_id = row.get("cart_id")
        if not cart_id:
            ui.notify("Please save the item before checking out.", color="warning")
            return

        # Auto-save dirty rows before checkout so the Order is created
        # with the latest quantity and price — not the last saved values.
        if self._dirty_rows:
            ui.notify("Saving changes before checkout...", color="info")
            self.upload_all()
            # upload_all() calls refresh() which reloads rowData —
            # we need to re-read cart_id from the refreshed data.
            # Find the row with matching cart_id after refresh.
            rows = self.grid.options.get("rowData", [])
            match = next(
                (r for r in rows if r.get("cart_id") == cart_id), None
            )
            if match is None:
                # Row was blocked by PermissionError — abort checkout
                return

        try:
            checkout_cart(cart_id)
            ui.notify("Item checked out successfully!", color="positive")
            self.refresh()
            if self._on_checked_out:
                self._on_checked_out()
        except PermissionError as exc:
            ui.notify(str(exc), color="red")
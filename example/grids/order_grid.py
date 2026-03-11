"""
order_grid.py
=============
OrderGrid — PAID and DELIVERED orders from ShoppingCart.

Demonstrates two patterns for triggering server-side side-effects:

    1. Double-click delivered_time  — direct JS DOM update
    2. Status dropdown → DELIVERED  — cellValueChanged + DOM update

Both paths call deliver_order() and immediately update the
delivered_time and status cells via run_javascript() DOM injection
without waiting for a full grid refresh.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from nicegui import ui

from example.components.crud_grid import CRUDGrid
from example.models import CartStatus, ShoppingCart
from example.services import deliver_order, load_order_rows, submit_order


class OrderGrid(CRUDGrid):

    def __init__(
        self,
        product_label:       ui.label,
        on_navigate_product=None,
    ):
        self._product_label      = product_label
        self._on_navigate_product = on_navigate_product  # callable(product_id)

        super().__init__(
            table_model     = ShoppingCart,
            load_rows       = load_order_rows,
            submit_row      = submit_order,
            delete_row      = None,
            hidden_fields   = {"added_date"},
            label_new       = None,
            label_upload    = None,
            dropdown_map    = {
                "status": [CartStatus.PAID.value, CartStatus.DELIVERED.value],
            },
            immutable_fields = {
                "cart_id",
                "product_id",     # FK reference — display only
                "quantity",
                "unit_price",
                "total_value",
                "paid_time",      # set server-side on checkout
                "delivered_time", # set server-side via deliver_order()
            },
            header_colour   = "#f3e5f5",
            height          = "500px",
        )

    def build(self) -> "OrderGrid":
        super().build()
        self.grid.on("cellDoubleClicked", self._on_order_double_clicked)
        self.grid.on("cellValueChanged",  self._on_order_cell_value_changed)
        return self

    # ------------------------------------------------------------------
    # Extension hooks
    # ------------------------------------------------------------------

    def on_row_selected(self, row: dict) -> None:
        self._product_label.set_text(row.get("product_name", "—"))

    # ------------------------------------------------------------------
    # Pattern 1 — double-click delivered_time
    # ------------------------------------------------------------------

    def _on_order_double_clicked(self, e) -> None:
        """
        Double-click on the delivered_time column of a PAID order:
        - delivered_time is immutable so no cell editor opens
        - The double-click is a deliberate 'mark as delivered' gesture
        - Calls deliver_order() then injects the timestamp into the DOM

        Demonstrates: intentional double-click action with immediate
        DOM update — no SAVE button required for a single-field event.
        """
        args      = e.args
        row_index = int(args["rowIndex"])
        col_id    = args["colId"]

        # Cross-tab navigation — double-click product_id goes to Products tab
        if col_id == "product_id":
            row        = self.grid.options["rowData"][row_index]
            product_id = row.get("product_id")
            if product_id and self._on_navigate_product:
                self._on_navigate_product(product_id)
            return

        if col_id != "delivered_time":
            return

        row    = self.grid.options["rowData"][row_index]
        status = row.get("status", "")

        if status != CartStatus.PAID.value:
            ui.notify(
                f"Only PAID orders can be delivered (status: {status}).",
                color="warning",
            )
            return

        cart_id = row.get("cart_id")
        if not cart_id:
            ui.notify("Cart ID not found.", color="red")
            return

        try:
            delivered_at = deliver_order(cart_id)
        except PermissionError as exc:
            ui.notify(str(exc), color="red")
            return

        self._update_delivery_dom(row_index, delivered_at)
        ui.notify("Order marked as delivered!", color="positive")
        self.refresh()

    # ------------------------------------------------------------------
    # Pattern 2 — status dropdown → DELIVERED
    # ------------------------------------------------------------------

    def _on_order_cell_value_changed(self, e) -> None:
        """
        Status dropdown changed to DELIVERED:
        - Validates the new value is a known CartStatus enum member
        - Calls deliver_order() server-side
        - Injects delivered_time into the DOM immediately

        Demonstrates: enum validation server-side + DOM side-effect
        when a dropdown drives a business event.

        NiceGUI trap: cellValueChanged is intercepted by NiceGUI so we
        register this via grid.on() rather than a {"function": "..."}
        in the column definition.
        """
        args      = e.args
        row_index = int(args["rowIndex"])
        col_id    = args["colId"]
        new_value = args.get("newValue")

        if col_id != "status":
            return

        row           = self.grid.options["rowData"][row_index]
        original_status = row.get("status", CartStatus.PAID.value)  # capture BEFORE overwrite
        self.grid.options["rowData"][row_index][col_id] = new_value
        cart_id = row.get("cart_id")

        if new_value == CartStatus.DELIVERED.value:
            try:
                delivered_at = deliver_order(cart_id)
            except PermissionError as exc:
                ui.notify(str(exc), color="red")
                # Revert dropdown in DOM back to PAID
                ui.run_javascript(f"""
                    (function() {{
                        document.querySelectorAll(
                            '.ag-row[row-index="{row_index}"]'
                        ).forEach(function(r) {{
                            const cell = r.querySelector('[col-id="status"]');
                            if (cell) {{
                                const v = cell.querySelector('.ag-cell-value');
                                if (v) v.textContent = 'PAID';
                            }}
                        }});
                    }})();
                """)
                self.grid.options["rowData"][row_index]["status"] = CartStatus.PAID.value
                self.grid.update()
                return

            self._update_delivery_dom(row_index, delivered_at)
            ui.notify("Order marked as delivered!", color="positive")
            self.refresh()
        else:
            ui.notify(
                f"Only PAID → DELIVERED is permitted. "
                f"Attempted: {new_value}",
                color="warning",
            )
            # Revert to the status the row had before the user changed it
            safe_val = json.dumps(original_status)
            self.grid.options["rowData"][row_index]["status"] = original_status
            ui.run_javascript(f"""
                (function() {{
                    document.querySelectorAll(
                        '.ag-row[row-index="{row_index}"]'
                    ).forEach(function(r) {{
                        const cell = r.querySelector('[col-id="status"]');
                        if (cell) {{
                            const v = cell.querySelector('.ag-cell-value');
                            if (v) v.textContent = {safe_val};
                        }}
                    }});
                }})();
            """)
            self.grid.update()

    # ------------------------------------------------------------------
    # Shared DOM update
    # ------------------------------------------------------------------

    def _update_delivery_dom(self, row_index: int, delivered_at: datetime) -> None:
        """
        Push delivered_time and status=DELIVERED into both cells immediately.
        Called by both delivery patterns so the DOM update is consistent.
        """
        ts = delivered_at.strftime("%Y-%m-%dT%H:%M:%S")
        ui.run_javascript(f"""
            (function() {{
                document.querySelectorAll(
                    '.ag-row[row-index="{row_index}"]'
                ).forEach(function(r) {{
                    const dtCell = r.querySelector('[col-id="delivered_time"]');
                    if (dtCell) {{
                        const v = dtCell.querySelector('.ag-cell-value');
                        if (v) v.textContent = '{ts}';
                    }}
                    const stCell = r.querySelector('[col-id="status"]');
                    if (stCell) {{
                        const sv = stCell.querySelector('.ag-cell-value');
                        if (sv) sv.textContent = 'DELIVERED';
                    }}
                }});
            }})();
        """)
"""
product_grid.py — read-only product catalogue.
Demonstrates: fully immutable grid, ui.image + ui.label on row select.
"""

from __future__ import annotations

from nicegui import ui

from example.components.crud_grid import CRUDGrid
from example.models import Product
from example.services import load_product_rows


class ProductGrid(CRUDGrid):

    def __init__(self, image_display: ui.image, detail_label: ui.label,
                 detail_description: ui.label):
        self._image_display     = image_display
        self._detail_label      = detail_label
        self._detail_description = detail_description

        super().__init__(
            table_model   = Product,
            load_rows     = load_product_rows,
            submit_row    = None,
            delete_row    = None,
            hidden_fields = {"image_url"},
            header_colour = "#c8e6c9",
            height        = "500px",
        )

    def select_by_product_id(self, product_id: int) -> None:
        """
        Scroll to and select the row matching product_id.
        Called from OrderGrid when user double-clicks the product_id column.
        product_id is cast to int for comparison since JSON round-trip
        may deliver it as a string.
        """
        target = int(product_id)
        rows   = self.grid.options.get("rowData", [])
        for i, row in enumerate(rows):
            if int(row.get("product_id") or 0) == target:
                self._selected_row_index = i
                self.on_row_selected(row)
                self.grid.run_grid_method("ensureIndexVisible", i, "middle")
                ui.run_javascript(f"""
                    (function() {{
                        document.querySelectorAll('.ag-row').forEach(function(r) {{
                            r.classList.remove('ag-row-selected');
                        }});
                        const row = document.querySelector('.ag-row[row-index="{i}"]');
                        if (row) row.classList.add('ag-row-selected');
                    }})();
                """)
                break

    def on_row_selected(self, row: dict) -> None:
        image_url = row.get("image_url") or ""
        if image_url:
            self._image_display.set_source(image_url)

        self._detail_label.set_text(
            f"{row.get('product_name', '')}  |  "
            f"{row.get('category', '')}  |  "
            f"£{row.get('price', '')}  |  "
            f"Stock: {row.get('stock_qty', '')}"
        )
        self._detail_description.set_text(row.get("description", ""))
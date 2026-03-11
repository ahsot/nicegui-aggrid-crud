"""
main.py — entry point for the nicegui-aggrid-crud demo.
"""

from __future__ import annotations

from nicegui import ui

from example.database import init_db
from example.grids.cart_grid import ShoppingCartGrid
from example.grids.order_grid import OrderGrid
from example.grids.product_grid import ProductGrid


@ui.page("/")
def index() -> None:
    ui.query("body").style("background-color: #f5f5f5;")

    with ui.column().classes("w-full max-w-7xl mx-auto p-4 gap-4"):

        ui.label("🛒  NiceGUI AG Grid CRUD Demo").classes("text-2xl font-bold")
        ui.label(
            "A reusable CRUDGrid component — NiceGUI + AG Grid + SQLModel."
        ).classes("text-sm text-gray-500")

        with ui.tabs().classes("w-full") as tabs:
            tab_products = ui.tab("Products")
            tab_cart     = ui.tab("Shopping Cart")
            tab_orders   = ui.tab("Orders")

        # Declare at function scope so all tab panels can reference each other
        product_grid: ProductGrid
        order_grid:   OrderGrid

        with ui.tab_panels(tabs, value=tab_products).classes("w-full"):

            # ----------------------------------------------------------
            # Products
            # ----------------------------------------------------------
            with ui.tab_panel(tab_products):
                with ui.column().classes("w-full gap-2"):
                    with ui.row().classes("items-start gap-4"):
                        product_image = ui.image("").classes(
                            "w-48 h-32 object-cover rounded shadow"
                        )
                        with ui.column().classes("gap-1 justify-center"):
                            product_name_label = ui.label("← click a row").classes(
                                "text-base font-bold"
                            )
                            product_desc_label = ui.label("").classes(
                                "text-sm text-gray-500"
                            ).style("min-height: 2.5rem;")
                    product_grid = ProductGrid(
                        image_display      = product_image,
                        detail_label       = product_name_label,
                        detail_description = product_desc_label,
                    )
                    product_grid.build()

            # ----------------------------------------------------------
            # Shopping Cart
            # ----------------------------------------------------------
            with ui.tab_panel(tab_cart):
                with ui.column().classes("w-full gap-2"):
                    with ui.row().classes("items-start gap-4"):
                        cart_image = ui.image("").classes(
                            "w-48 h-32 object-cover rounded shadow"
                        )
                        with ui.column().classes("gap-1 justify-center"):
                            cart_name_label = ui.label("← click a row").classes(
                                "text-base font-bold"
                            )

                    def on_checked_out() -> None:
                        order_grid.refresh()

                    cart_grid = ShoppingCartGrid(
                        image_display  = cart_image,
                        detail_label   = cart_name_label,
                        on_checked_out = on_checked_out,
                    )
                    cart_grid.build()

            # ----------------------------------------------------------
            # Orders
            # ----------------------------------------------------------
            with ui.tab_panel(tab_orders):
                with ui.column().classes("w-full gap-2"):
                    order_name_label = ui.label("← click a row").classes(
                        "text-base font-bold"
                    )
                    ui.label(
                        "💡 Double-click Delivered Time on a PAID order to mark as delivered  "
                        "|  Double-click Product ID to navigate to the product"
                    ).classes("text-xs text-gray-500 italic")

                    def navigate_to_product(product_id: int) -> None:
                        """Switch to Products tab and select the matching row."""
                        tabs.set_value(tab_products)
                        product_grid.select_by_product_id(product_id)

                    order_grid = OrderGrid(
                        product_label        = order_name_label,
                        on_navigate_product  = navigate_to_product,
                    )
                    order_grid.build()


if __name__ in ("__main__", "__mp_main__", "example.main"):
    init_db(start_afresh=True)
    ui.run(
        title  = "NiceGUI AG Grid CRUD Demo",
        port   = 8080,
        reload = False,
    )
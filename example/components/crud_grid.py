"""
crud_grid.py
============
A reusable NiceGUI / AG Grid CRUD component built on SQLModel.

Quick start — no subclass needed
---------------------------------
    from example.components.crud_grid import CRUDGrid
    from example.models import Product
    from example.services import load_product_rows, submit_product

    CRUDGrid(
        table_model  = Product,
        load_rows    = load_product_rows,
        submit_row   = submit_product,
    ).build()

Subclass for custom behaviour
------------------------------
    class ShoppingCartGrid(CRUDGrid):

        def extra_toolbar_buttons(self) -> None:
            ui.button("FULFIL", icon="check", on_click=self._fulfil_selected)

        def on_row_selected(self, row: dict) -> None:
            # Drive a linked ui.label / ui.image on the same page
            self._detail_label.set_text(row.get("product_name", ""))

NiceGUI 3.x / AG Grid 34.x implementation notes
-------------------------------------------------
These behaviours differ from AG Grid's own documentation and cost
significant debugging time — documented here for the community.

1.  onCellValueChanged is intercepted by NiceGUI for its own Python
    event system.  You cannot attach a JS callback to it via the
    {"function": "..."} wrapper.  Use grid.on("cellValueChanged", ...)
    to receive the event in Python instead.

2.  onGridReady is owned by NiceGUI internally.  Adding a second
    onGridReady handler causes "originalOnGridReady is not a function".
    Never add onGridReady to gridOptions.

3.  cellClassRules expression strings use bare variables:
        node, column, value, data, rowIndex
    NOT params.node / params.column.  params is not defined in this
    context and will throw a ReferenceError.

4.  {"function": "..."} works at the top level of gridOptions but does
    NOT work inside nested column def properties (cellClassRules,
    valueFormatter etc.).  Use plain expression strings or the
    colon-prefix ":key" form instead.

5.  getRowId cannot be set via any NiceGUI syntax without breaking row
    creation.  Use grid.update() instead of applyTransaction.

6.  firstDataRendered re-fires on every grid.update(), not just the
    initial load.  Guard autoSizeAllColumns with a boolean flag.

7.  ui.on() listens on NiceGUI's WebSocket, NOT on browser window
    events.  window.dispatchEvent() will never reach Python.
    Use grid.on("eventName", handler) for grid events.

8.  Dirty cell display for non-editable columns (_time, _date):
    Because these columns have editable=False, AG Grid will not open
    a cell editor.  We write directly to the cell's DOM textContent
    via ui.run_javascript() after updating Python-side rowData.
"""

from __future__ import annotations

import uuid
from typing import Any, Callable

from nicegui import ui

from .columns import generate_column_defs_from_table
from .formatters import cast_row_types


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

_GRID_CSS = """
.edited-cell {
    background-color: #fff3cd !important;
    border-left: 3px solid #ffca2c !important;
}
"""

# ---------------------------------------------------------------------------
# JS — dirty cell tracking
# ---------------------------------------------------------------------------

# Note: _DIRTY_TRACKING_JS is now generated per-instance in build()
# so each grid has its own scoped dirty key Set — see _dirty_js_name.


# ---------------------------------------------------------------------------
# CRUDGrid
# ---------------------------------------------------------------------------

class CRUDGrid:
    """
    Generic AG Grid CRUD component for NiceGUI.

    Parameters
    ----------
    table_model : SQLModel class
        Used by generate_column_defs_from_table to auto-build column defs.
    load_rows : Callable[[], list[dict]]
        Returns the current rowData from whatever source you like.
    submit_row : Callable[[dict], Any]
        Called once per dirty row on Upload.  Raise PermissionError to
        block a specific row — the grid notifies and continues.
    delete_row : Callable[[dict], Any] | None
        Called when the user deletes the selected row.  Raise
        PermissionError to block deletion.  If None, the DELETE button
        is not shown.
    pre_submit_hook : Callable[[dict], dict] | None
        Optional transform applied to each dirty row before submit_row
        is called (e.g. resolve product_name -> product_id).
    dropdown_map : dict[str, list] | None
        Maps field names to their allowed value lists.  Also drives
        UI-only vlookup display columns (see columns.py).
    excluded_fields : set[str] | None
        Fields omitted from the grid entirely.
    hidden_fields : set[str] | None
        Fields in rowData but hidden from the user.
    immutable_fields : set[str] | None
        Fields shown but not editable.
    new_row_defaults : dict | None
        Default values for a freshly inserted blank row.
    header_colour : str
        CSS colour for the AG Grid header background.
        Useful when multiple grids are visible — give each a distinct
        colour so the user knows which table they are editing.
    height : str
        CSS height of the grid element (default "600px").
    """

    def __init__(
        self,
        table_model,
        load_rows:        Callable[[], list[dict]],
        submit_row:       Callable[[dict], Any] | None,
        delete_row:       Callable[[dict], Any] | None = None,
        pre_submit_hook:  Callable[[dict], dict] | None = None,
        dropdown_map:     dict | None = None,
        excluded_fields:  set | None = None,
        hidden_fields:    set | None = None,
        immutable_fields: set | None = None,
        new_row_defaults: dict | None = None,
        header_colour:    str = "#d6d6d6",
        height:           str = "600px",
        label_new:        str = "NEW",
        label_upload:     str = "UPLOAD",
        label_delete:     str = "DELETE",
    ):
        self._table_model      = table_model
        self._load_rows        = load_rows
        self._submit_row_fn    = submit_row  # None = read-only grid
        self._delete_row_fn    = delete_row
        self._pre_submit_hook  = pre_submit_hook or (lambda row: row)
        self._dropdown_map     = dropdown_map or {}
        self._excluded_fields  = excluded_fields or set()
        self._hidden_fields    = hidden_fields or set()
        self._immutable_fields = immutable_fields or set()
        self._new_row_defaults = new_row_defaults or {}
        self._header_colour    = header_colour
        self._height           = height

        self._label_new        = label_new
        self._label_upload     = label_upload
        self._label_delete     = label_delete

        self._dirty_rows:       set[int] = set()
        self._selected_row_index: int | None = None
        self._autofitted:       bool = False
        # Unique identifiers per instance:
        # _grid_class  — scopes CSS header colour
        # _dirty_js_name — scopes the JS dirty-key Set so grids on the
        #   same page don't share highlight state (window.__dirtykeys__
        #   is global — each grid needs its own named Set)
        _uid = uuid.uuid4().hex[:8]
        self._grid_class:    str = f"crud-grid-{_uid}"
        self._dirty_js_name: str = f"__dirtykeys_{_uid}__"

        self.grid: ui.aggrid | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self) -> "CRUDGrid":
        """Render the toolbar and grid into the current NiceGUI container."""
        ui.add_css(_GRID_CSS)
        # Per-instance dirty tracking — scoped to this grid's unique name
        _dirty_js = f"""
<script>
window["{self._dirty_js_name}"] = window["{self._dirty_js_name}"] || new Set();
function onCellEdited_{self._dirty_js_name}(rowIndex, colId) {{
    window["{self._dirty_js_name}"].add(rowIndex + ':' + colId);
}}
function clearDirtyKeys_{self._dirty_js_name}() {{
    window["{self._dirty_js_name}"].clear();
}}
</script>
"""
        ui.add_head_html(_dirty_js)
        # Scoped to this instance's unique class — prevents the last
        # grid's header colour overriding all others on the page.
        ui.add_css(f"""
            .ag-theme-balham {{
                --ag-font-size: 12px;
                --ag-row-height: 26px;
                --ag-header-height: 32px;
            }}
            .{self._grid_class} {{
                --ag-header-background-color: {self._header_colour};
            }}
        """)

        self._build_toolbar()

        column_defs = generate_column_defs_from_table(
            self._table_model,
            immutable_fields = self._immutable_fields,
            excluded_fields  = self._excluded_fields,
            hidden_fields    = self._hidden_fields,
            dropdown_map     = self._dropdown_map,
        )
        self._inject_dirty_class_rules(column_defs)

        self.grid = (
            ui.aggrid({
                "columnDefs":    column_defs,
                "rowData":       self._load_rows(),
                "defaultColDef": {"filter": False, "sortable": True},
                "columnTypes": {
                    "dateColumn": {"sortable": True},
                },
                "rowSelection": {
                    "mode": "singleRow",
                    "enableSelectionWithoutKeys": True,
                    "checkboxes": False,
                },
                "singleClickEdit":              True,
                "stopEditingWhenCellsLoseFocus": True,
                "autoSizeStrategy": {
                    "type": "fitCellContents",
                },
                # Capture params.api on first cell edit so we have a
                # reference to the AG Grid API for direct row model updates.
                "onCellValueChanged": {
                    "function": "if(!window.__gridApi__) window.__gridApi__ = params.api"
                },
            })
            .classes(f"ag-theme-balham {self._grid_class}")
            .style(f"height: {self._height};")
        )

        self.grid.on("cellValueChanged",  self._on_cell_value_changed)
        self.grid.on("cellDoubleClicked", self._on_cell_double_clicked)
        self.grid.on("firstDataRendered", self._on_first_data_rendered)
        # cellClicked avoids the circular JSON serialisation error that
        # rowClicked causes — AG Grid's full event object contains internal
        # references (context, beans) that cannot be serialised to JSON.
        # We read only rowIndex from args and look up the row in Python.
        self.grid.on("cellClicked", self._on_cell_clicked)

        return self

    def refresh(self) -> None:
        """Reload data from source and reset all dirty state."""
        if self.grid is None:
            return
        self.grid.options["rowData"] = self._load_rows()
        self.grid.update()
        self._dirty_rows.clear()
        self._selected_row_index = None
        ui.run_javascript(f"clearDirtyKeys_{self._dirty_js_name}()")
        self.grid.run_grid_method("refreshCells", {"force": True})


    def upload_all(self) -> None:
        """
        Submit every dirty row.  PermissionErrors are caught per-row so
        one blocked row does not prevent others from being saved.
        """
        if self._submit_row_fn is None:
            ui.notify("This grid is read-only.", color="warning")
            return
        if not self._dirty_rows:
            ui.notify("Nothing to upload.", color="info")
            return

        success, skipped = 0, 0
        for row_index in sorted(self._dirty_rows):
            row = dict(self.grid.options["rowData"][row_index])
            row = cast_row_types(row, self._table_model)
            row = self._pre_submit_hook(row)
            try:
                self._submit_row_fn(row)
                success += 1
            except PermissionError as exc:
                ui.notify(str(exc), color="orange")
                skipped += 1

        ui.notify(
            f"Upload complete — {success} saved, {skipped} skipped.",
            color="positive" if skipped == 0 else "warning",
        )
        self.refresh()

    def add_new_row(self, defaults: dict | None = None) -> None:
        """Insert a blank row at the top of the grid."""
        row = {**self._new_row_defaults, **(defaults or {})}
        self.grid.options["rowData"].insert(0, row)
        self.grid.update()
        # Re-index existing dirty rows displaced by the insertion
        self._dirty_rows = {i + 1 for i in self._dirty_rows}
        self._dirty_rows.add(0)
        ui.notify("New row added — fill in the fields and click UPLOAD.")

    def delete_selected_row(self) -> None:
        """Delete the currently selected row."""
        if self._selected_row_index is None:
            ui.notify("Select a row first.", color="warning")
            return
        row = dict(self.grid.options["rowData"][self._selected_row_index])
        row = cast_row_types(row, self._table_model)
        try:
            if self._delete_row_fn:
                self._delete_row_fn(row)
            self.grid.options["rowData"].pop(self._selected_row_index)
            self._dirty_rows.discard(self._selected_row_index)
            self._selected_row_index = None
            self.grid.update()
            ui.notify("Row deleted.", color="positive")
        except PermissionError as exc:
            ui.notify(str(exc), color="red")

    # ------------------------------------------------------------------
    # Extension hooks (override in subclasses)
    # ------------------------------------------------------------------

    def on_row_selected(self, row: dict) -> None:
        """
        Called whenever the user clicks a row.
        Override to drive linked components (ui.label, ui.image etc.).
        """
        pass

    def extra_toolbar_buttons(self) -> None:
        """Override to add domain-specific buttons to the toolbar."""
        pass

    # ------------------------------------------------------------------
    # Private — toolbar
    # ------------------------------------------------------------------

    def _build_toolbar(self) -> None:
        with ui.row().classes("w-full items-center gap-2 pb-2"):
            ui.button("REFRESH", icon="refresh", on_click=lambda: self.refresh())
            if self._submit_row_fn is not None and self._label_new is not None:
                ui.button(self._label_new,    icon="add",    on_click=lambda: self.add_new_row())
            if self._submit_row_fn is not None and self._label_upload is not None:
                ui.button(self._label_upload, icon="upload", on_click=lambda: self.upload_all())
            if self._delete_row_fn is not None and self._label_delete is not None:
                ui.button(self._label_delete, icon="delete",
                          on_click=lambda: self.delete_selected_row()
                          ).props("color=negative")
            self.extra_toolbar_buttons()

    # ------------------------------------------------------------------
    # Private — column def helpers
    # ------------------------------------------------------------------

    def _inject_dirty_class_rules(self, column_defs: list[dict]) -> None:
        """
        Add cellClassRules to editable columns and date/time columns.

        AG Grid evaluates the expression string with node, column, value,
        data, rowIndex as bare variables — NOT as params.node etc.
        The {"function": ...} NiceGUI wrapper does not work inside nested
        column def properties so we use a plain expression string.
        """
        js_name = self._dirty_js_name
        expression = (
            f"window['{js_name}'] != null && "
            f"window['{js_name}'].has(node.rowIndex + ':' + column.colId)"
        )
        for col in column_defs:
            field          = col.get("field", "")
            is_editable    = col.get("editable", False)
            is_dblclick    = field.endswith("_time") or field.endswith("_date")
            if is_editable or is_dblclick:
                col.setdefault("cellClassRules", {})
                col["cellClassRules"]["edited-cell"] = expression

    # ------------------------------------------------------------------
    # Private — event handlers
    # ------------------------------------------------------------------

    def _on_first_data_rendered(self, _) -> None:
        """
        On initial load — select the first row so linked components
        (ui.image, ui.label) are populated immediately rather than
        showing empty placeholders.
        autoSizeAllColumns is handled by autoSizeStrategy in grid options.
        """
        if not self._autofitted:
            self._autofitted = True
            rows = self.grid.options.get("rowData", [])
            if rows:
                self._selected_row_index = 0
                self.on_row_selected(rows[0])

    def _on_cell_clicked(self, e) -> None:
        row_index = e.args.get("rowIndex")
        if row_index is None:
            return
        self._selected_row_index = int(row_index)
        # Look up the row in Python-side rowData — never trust e.args["data"]
        # as it may contain circular references from AG Grid internals.
        row = self.grid.options["rowData"][self._selected_row_index]
        self.on_row_selected(row)

    def _on_cell_value_changed(self, e) -> None:
        args      = e.args
        row_index = int(args["rowIndex"])
        col_id    = args["colId"]
        new_value = args.get("newValue")

        self.grid.options["rowData"][row_index][col_id] = new_value
        self._dirty_rows.add(row_index)
        # Mark dirty BEFORE grid.update() so cellClassRules finds the key
        # during the redraw triggered by update().
        ui.run_javascript(
            f"onCellEdited_{self._dirty_js_name}({row_index}, '{col_id}');"
        )
        self.grid.update()
        self.grid.run_grid_method("refreshCells", {"force": True})

    def _on_cell_double_clicked(self, e) -> None:
        """
        Auto-fill *_time and *_date columns on double-click.

        These columns are editable=False so AG Grid never opens a cell
        editor.  We update Python-side rowData and then write directly
        to the cell's DOM textContent via run_javascript, bypassing the
        AG Grid row model entirely.  This is necessary because the AG
        Grid API is not reliably accessible from NiceGUI's JS context.
        """
        from datetime import date, datetime, timezone

        args      = e.args
        row_index = int(args["rowIndex"])
        col_id    = args["colId"]

        if col_id.endswith("_time"):
            new_value = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        elif col_id.endswith("_date"):
            new_value = date.today().isoformat()
        else:
            return

        self.grid.options["rowData"][row_index][col_id] = new_value
        self._dirty_rows.add(row_index)

        ui.run_javascript(
            f"onCellEdited_{self._dirty_js_name}({row_index}, '{col_id}');"
        )

        # Write directly to the DOM cell — AG Grid's own row model update
        # path is not accessible without a reliable handle to params.api.
        ui.run_javascript(f"""
            (function() {{
                const rows = document.querySelectorAll(
                    '.ag-row[row-index="{row_index}"]'
                );
                rows.forEach(function(row) {{
                    const cell = row.querySelector('[col-id="{col_id}"]');
                    if (cell) {{
                        const val = cell.querySelector('.ag-cell-value');
                        if (val) val.textContent = '{new_value}';
                    }}
                }});
            }})();
        """)
        self.grid.run_grid_method("refreshCells", {"force": True})
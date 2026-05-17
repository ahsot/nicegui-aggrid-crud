"""
grid_policy.py
==============
GridDesignPolicy — a dataclass that captures every visual and layout
decision for a CRUDGrid instance, completely separate from behaviour.

Why this exists
---------------
CRUDGrid is a behavioural component. It should not decide what it looks
like — that is the host application's responsibility. By passing a
GridDesignPolicy into CRUDGrid, the host app controls the entire visual
contract in one place. CRUDGrid complies; it never hardcodes colours,
sizes, or theme names.

Usage
-----
    # Use the built-in default (light theme, neutral colours):
    grid = CRUDGrid(...).build()

    # Use a custom policy:
    from example.components.grid_policy import GridDesignPolicy
    policy = GridDesignPolicy(ag_theme="ag-theme-balham-dark")
    grid = CRUDGrid(..., design=policy).build()

    # Define one policy for your whole app and reuse it:
    MY_APP_POLICY = GridDesignPolicy(
        ag_theme          = "ag-theme-balham-dark",
        header_colour     = "#1e2235",
        dirty_cell_bg     = "#3a3000",
        dirty_cell_border = "#ffca2c",
    )
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GridDesignPolicy:
    """
    All visual and layout decisions for a CRUDGrid instance.

    Attributes
    ----------
    ag_theme : str
        AG Grid theme class applied to the grid container.
        Use "ag-theme-balham" for light or "ag-theme-balham-dark" for dark.

    font_size : str
        CSS font size for grid cells and headers.

    row_height : str
        CSS height of each data row.

    header_height : str
        CSS height of the column header row.

    header_colour : str
        CSS colour for the grid header background.
        Useful when multiple grids are on the same page — give each a
        distinct colour so the user can tell them apart at a glance.

    height : str
        CSS height of the grid container element.

    dirty_cell_bg : str
        Background colour applied to cells that have been edited but
        not yet saved.  Choose a colour with sufficient contrast against
        your theme — amber works on both light and dark themes with the
        right shade.

    dirty_cell_border : str
        Left-border colour applied alongside dirty_cell_bg.

    btn_refresh_colour : str
        Quasar colour name for the REFRESH toolbar button.

    btn_new_colour : str
        Quasar colour name for the NEW toolbar button.

    btn_upload_colour : str
        Quasar colour name for the UPLOAD toolbar button.

    btn_delete_colour : str
        Quasar colour name for the DELETE toolbar button.
        Conventionally "negative" (red) — change only if your design
        system uses a different convention for destructive actions.
    """

    # ------------------------------------------------------------------ #
    # AG Grid theme                                                        #
    # ------------------------------------------------------------------ #
    ag_theme: str = "ag-theme-balham"

    # ------------------------------------------------------------------ #
    # AG Grid sizing                                                       #
    # ------------------------------------------------------------------ #
    font_size: str = "12px"
    row_height: str = "26px"
    header_height: str = "32px"

    # ------------------------------------------------------------------ #
    # Colours                                                              #
    # ------------------------------------------------------------------ #
    header_colour: str = "#d6d6d6"
    height: str = "600px"
    dirty_cell_bg: str = "#fff3cd"
    dirty_cell_border: str = "#ffca2c"

    # ------------------------------------------------------------------ #
    # Toolbar button colours (Quasar colour names)                        #
    # ------------------------------------------------------------------ #
    btn_refresh_colour: str = "primary"
    btn_new_colour: str = "positive"
    btn_upload_colour: str = "primary"
    btn_delete_colour: str = "negative"

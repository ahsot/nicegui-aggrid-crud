"""
services.py
===========
Data access for Product and ShoppingCart.

ShoppingCart serves double duty:
    - Shopping Cart tab: WHERE status = WISHLIST
    - Orders tab:        WHERE status != WISHLIST
"""

from __future__ import annotations

import json
from datetime import datetime, date, timezone
from decimal import Decimal

from sqlmodel import select

from .database import get_session
from .models import CartStatus, Product, ShoppingCart


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalise_value(v) -> object:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return float(v)
    if hasattr(v, "value"):
        return v.value
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


def _row_to_dict(obj, extra: dict | None = None) -> dict:
    # Access model_fields from the class, not the instance —
    # Pydantic V2.11 deprecates instance-level model_fields access.
    row = {f: _normalise_value(getattr(obj, f)) for f in obj.__class__.model_fields}
    if extra:
        row.update(extra)
    return row


def _product_map() -> dict[str, int]:
    with get_session() as session:
        return {p.product_name: p.product_id
                for p in session.exec(select(Product)).all()}


def _reverse_product_map() -> dict[int, str]:
    return {v: k for k, v in _product_map().items()}


def _product_prices() -> dict[str, Decimal]:
    with get_session() as session:
        return {p.product_name: p.price
                for p in session.exec(select(Product)).all()}


def get_product_prices_js() -> str:
    """JS to set window.__productPrices__ for client-side price lookup."""
    prices = _product_prices()
    entries = ", ".join(
        f'{json.dumps(name)}: {float(price)}'
        for name, price in prices.items()
    )
    return f"window.__productPrices__ = {{{entries}}};"


# ---------------------------------------------------------------------------
# Product
# ---------------------------------------------------------------------------

def load_product_rows() -> list[dict]:
    with get_session() as session:
        return [_row_to_dict(p)
                for p in session.exec(
                    select(Product).order_by(Product.product_id)
                ).all()]


# ---------------------------------------------------------------------------
# Shopping Cart — WISHLIST only
# ---------------------------------------------------------------------------

def load_cart_rows() -> list[dict]:
    reverse_map = _reverse_product_map()
    with get_session() as session:
        carts = session.exec(
            select(ShoppingCart)
            .where(ShoppingCart.status == CartStatus.WISHLIST)
            .order_by(ShoppingCart.cart_id.desc())
        ).all()
        return [
            _row_to_dict(c, extra={
                "product_name": reverse_map.get(c.product_id, ""),
            })
            for c in carts
        ]


def submit_cart(row: dict) -> None:
    """Upsert a WISHLIST cart row. unit_price and total_value always recalculated."""
    product_map    = _product_map()
    product_prices = _product_prices()

    with get_session() as session:
        cart_id = row.get("cart_id")
        if cart_id:
            cart = session.get(ShoppingCart, cart_id)
            if cart is None:
                raise PermissionError(f"Cart {cart_id} not found.")
            if cart.status != CartStatus.WISHLIST:
                raise PermissionError(
                    f"Cart {cart_id} has status {cart.status.value} "
                    f"and cannot be modified."
                )
            product_name = row.get("product_name", "")
            if product_name in product_map:
                cart.product_id = product_map[product_name]
                cart.unit_price = product_prices[product_name]
            if "quantity" in row and row["quantity"] is not None:
                cart.quantity = int(row["quantity"])
            if row.get("added_date"):
                cart.added_date = row["added_date"]
            if cart.unit_price and cart.quantity:
                cart.total_value = Decimal(str(cart.unit_price)) * int(cart.quantity)
        else:
            product_name = row.get("product_name", "")
            product_id   = product_map.get(product_name)
            unit_price   = product_prices.get(product_name)
            quantity     = int(row.get("quantity", 1))
            cart = ShoppingCart(
                product_id  = product_id,
                quantity    = quantity,
                unit_price  = unit_price,
                total_value = Decimal(str(unit_price)) * quantity if unit_price else None,
                status      = CartStatus.WISHLIST,
                added_date  = date.today(),
                paid_time   = None,
            )
            session.add(cart)
        session.commit()


def delete_cart(row: dict) -> None:
    """Delete — only WISHLIST items."""
    cart_id = row.get("cart_id")
    if not cart_id:
        raise PermissionError("Cannot delete without a cart_id.")
    with get_session() as session:
        cart = session.get(ShoppingCart, cart_id)
        if cart is None:
            return
        if cart.status != CartStatus.WISHLIST:
            raise PermissionError(
                f"Only WISHLIST items can be removed "
                f"(status: {cart.status.value})."
            )
        session.delete(cart)
        session.commit()


def checkout_cart(cart_id: int) -> None:
    """Move WISHLIST → PAID, set paid_time."""
    with get_session() as session:
        cart = session.get(ShoppingCart, cart_id)
        if cart is None:
            raise PermissionError(f"Cart {cart_id} not found.")
        if cart.status != CartStatus.WISHLIST:
            raise PermissionError(f"Cart {cart_id} is already {cart.status.value}.")
        cart.status    = CartStatus.PAID
        cart.paid_time = datetime.now(timezone.utc)
        session.commit()


# ---------------------------------------------------------------------------
# Orders — non-WISHLIST ShoppingCart rows
# ---------------------------------------------------------------------------

def load_order_rows() -> list[dict]:
    """All PAID and DELIVERED carts — the Orders view."""
    reverse_map = _reverse_product_map()
    with get_session() as session:
        carts = session.exec(
            select(ShoppingCart)
            .where(ShoppingCart.status != CartStatus.WISHLIST)
            .order_by(ShoppingCart.cart_id.desc())
        ).all()
        return [
            _row_to_dict(c, extra={
                "product_name": reverse_map.get(c.product_id, ""),
            })
            for c in carts
        ]


def deliver_order(cart_id: int) -> datetime:
    """
    Move PAID → DELIVERED, set delivered_time.
    Returns the delivered_time so the caller can update the DOM immediately.
    Raises PermissionError if the order is not in PAID status.
    """
    with get_session() as session:
        cart = session.get(ShoppingCart, cart_id)
        if cart is None:
            raise PermissionError(f"Order {cart_id} not found.")
        if cart.status != CartStatus.PAID:
            raise PermissionError(
                f"Only PAID orders can be delivered "
                f"(status: {cart.status.value})."
            )
        now = datetime.now(timezone.utc)
        cart.status         = CartStatus.DELIVERED
        cart.delivered_time = now
        session.commit()
        return now


def submit_order(row: dict) -> None:
    """
    Handle status changes on Orders via the dropdown.
    Only PAID → DELIVERED is permitted.
    delivered_time is always set server-side — never trusted from browser.
    Raises PermissionError for any other transition.
    """
    cart_id    = row.get("cart_id")
    new_status = row.get("status", "")

    # Validate the status value is a known enum member
    valid = {s.value for s in CartStatus}
    if new_status not in valid:
        raise PermissionError(
            f"'{new_status}' is not a valid status. "
            f"Allowed values: {', '.join(sorted(valid))}"
        )

    if new_status == CartStatus.DELIVERED.value:
        deliver_order(cart_id)
    else:
        raise PermissionError(
            f"Orders can only be moved to DELIVERED from PAID. "
            f"Requested: {new_status}"
        )
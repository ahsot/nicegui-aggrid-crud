"""
models.py
=========
Two tables — Product and ShoppingCart.

Deliberately simple DB design so the focus stays on the CRUDGrid
component mechanics, not on schema complexity.

    Product       — read-only catalogue (20 seed items)
    ShoppingCart  — full order lifecycle:
                    WISHLIST → PAID → DELIVERED
"""

from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


class Category(str, Enum):
    ELECTRONICS  = "ELECTRONICS"
    ACCESSORIES  = "ACCESSORIES"
    AUDIO        = "AUDIO"
    COMPUTING    = "COMPUTING"
    PHOTOGRAPHY  = "PHOTOGRAPHY"


class CartStatus(str, Enum):
    WISHLIST  = "WISHLIST"
    PAID      = "PAID"
    DELIVERED = "DELIVERED"


class Product(SQLModel, table=True):
    product_id   : Optional[int]  = Field(default=None, primary_key=True)
    product_name : str            = Field(index=True)
    description  : str
    category     : Category
    price        : Decimal        = Field(decimal_places=2, max_digits=10)
    stock_qty    : int            = Field(default=0)
    image_url    : str            = Field(default="")


class ShoppingCart(SQLModel, table=True):
    cart_id        : Optional[int]      = Field(default=None, primary_key=True)
    product_id     : Optional[int]      = Field(default=None, foreign_key="product.product_id")
    quantity       : int                = Field(default=1)
    unit_price     : Optional[Decimal]  = Field(default=None, decimal_places=2, max_digits=10)
    total_value    : Optional[Decimal]  = Field(default=None, decimal_places=2, max_digits=10)
    status         : CartStatus         = Field(default=CartStatus.WISHLIST)
    added_date     : Optional[date]     = Field(default=None)
    paid_time      : Optional[datetime] = Field(default=None)
    delivered_time : Optional[datetime] = Field(default=None)
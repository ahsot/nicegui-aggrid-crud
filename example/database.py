"""
database.py
===========
Engine, session, and seed data for the two-table demo.
"""

from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine, select

from .models import Category, CartStatus, Product, ShoppingCart

_DB_PATH = Path(__file__).parent.parent / "db" / "demo.db"
_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    f"sqlite:///{_DB_PATH}",
    echo=False,
    connect_args={"check_same_thread": False},
)


def get_session() -> Session:
    return Session(engine)


_SEED_PRODUCTS = [
    dict(product_name="4K Smart TV 55\"",      description="Ultra HD smart TV with HDR and built-in streaming apps",  category=Category.ELECTRONICS,  price=Decimal("699.99"),  stock_qty=15),
    dict(product_name="Wireless Charger Pad",  description="10W fast wireless charging pad, Qi compatible",           category=Category.ELECTRONICS,  price=Decimal("29.99"),   stock_qty=80),
    dict(product_name="Smart Doorbell",        description="HD video doorbell with motion detection and night vision", category=Category.ELECTRONICS,  price=Decimal("149.99"),  stock_qty=30),
    dict(product_name="Robot Vacuum",          description="Auto-mapping robot vacuum with app control",               category=Category.ELECTRONICS,  price=Decimal("349.99"),  stock_qty=20),
    dict(product_name="Smart Thermostat",      description="Learning thermostat, saves energy automatically",          category=Category.ELECTRONICS,  price=Decimal("199.99"),  stock_qty=25),
    dict(product_name="USB-C Hub 7-in-1",      description="7-port USB-C hub with HDMI, SD card and USB-A ports",     category=Category.ACCESSORIES,  price=Decimal("49.99"),   stock_qty=60),
    dict(product_name="Laptop Stand",          description="Adjustable aluminium laptop stand, foldable",              category=Category.ACCESSORIES,  price=Decimal("39.99"),   stock_qty=50),
    dict(product_name="Mechanical Keyboard",   description="TKL mechanical keyboard, Cherry MX brown switches",        category=Category.ACCESSORIES,  price=Decimal("89.99"),   stock_qty=35),
    dict(product_name="Ergonomic Mouse",       description="Vertical ergonomic mouse, reduces wrist strain",           category=Category.ACCESSORIES,  price=Decimal("59.99"),   stock_qty=45),
    dict(product_name="Monitor Light Bar",     description="LED light bar for monitors, no glare design",              category=Category.ACCESSORIES,  price=Decimal("44.99"),   stock_qty=40),
    dict(product_name="Noise Cancelling Headphones", description="Over-ear ANC headphones, 30hr battery",             category=Category.AUDIO,        price=Decimal("249.99"),  stock_qty=28),
    dict(product_name="Bluetooth Speaker",     description="Portable waterproof speaker, 360 sound",                  category=Category.AUDIO,        price=Decimal("79.99"),   stock_qty=55),
    dict(product_name="Studio Microphone",     description="USB condenser microphone for podcasting and streaming",    category=Category.AUDIO,        price=Decimal("119.99"),  stock_qty=22),
    dict(product_name="Earbuds Pro",           description="True wireless earbuds with ANC and transparency mode",     category=Category.AUDIO,        price=Decimal("179.99"),  stock_qty=40),
    dict(product_name="DAC Amplifier",         description="Desktop headphone amplifier with DAC, balanced output",    category=Category.AUDIO,        price=Decimal("159.99"),  stock_qty=18),
    dict(product_name="Portable SSD 1TB",      description="USB-C portable SSD, 1050MB/s read speed",                 category=Category.COMPUTING,    price=Decimal("109.99"),  stock_qty=35),
    dict(product_name="RAM 32GB DDR5",         description="32GB DDR5 6000MHz desktop RAM kit",                        category=Category.COMPUTING,    price=Decimal("89.99"),   stock_qty=30),
    dict(product_name="Mini PC",               description="Intel N100 mini PC, 16GB RAM, 512GB SSD",                  category=Category.COMPUTING,    price=Decimal("299.99"),  stock_qty=12),
    dict(product_name="Mirrorless Camera",     description="24MP APS-C mirrorless camera body, 4K video",              category=Category.PHOTOGRAPHY,  price=Decimal("899.99"),  stock_qty=10),
    dict(product_name="Webcam 4K",             description="4K 30fps webcam with autofocus and built-in ring light",   category=Category.PHOTOGRAPHY,  price=Decimal("129.99"),  stock_qty=38),
]


def _image_url(product_name: str) -> str:
    seed = product_name.lower().replace(" ", "-").replace('"', "")
    return f"https://picsum.photos/seed/{seed}/300/200"


_SEED_CARTS = [
    dict(product_name="Portable SSD 1TB",            quantity=1, status=CartStatus.DELIVERED, paid_time=datetime(2024,11,10,9,0),    delivered_time=datetime(2024,11,18,10,15)),
    dict(product_name="Mechanical Keyboard",         quantity=1, status=CartStatus.DELIVERED, paid_time=datetime(2024,12,20,11,0),   delivered_time=datetime(2024,12,22,14,30)),
    dict(product_name="Noise Cancelling Headphones", quantity=1, status=CartStatus.PAID,      paid_time=datetime(2026,1,23,10,18),   delivered_time=None),
    dict(product_name="USB-C Hub 7-in-1",            quantity=2, status=CartStatus.WISHLIST,  paid_time=None,                        delivered_time=None),
    dict(product_name="Earbuds Pro",                 quantity=1, status=CartStatus.WISHLIST,  paid_time=None,                        delivered_time=None),    
]


def init_db(start_afresh: bool = False) -> None:
    """
    Create tables and seed data.
    start_afresh=True drops and recreates all tables first.
    """
    if start_afresh:
        SQLModel.metadata.drop_all(engine)
        print("All tables dropped.")

    SQLModel.metadata.create_all(engine)

    with get_session() as session:
        if not start_afresh and session.exec(select(Product)).first() is not None:
            return

        products: dict[str, Product] = {}
        for p in _SEED_PRODUCTS:
            product = Product(**p, image_url=_image_url(p["product_name"]))
            session.add(product)
            products[p["product_name"]] = product
        session.flush()

        for c in _SEED_CARTS:
            product    = products[c["product_name"]]
            unit_price = product.price
            quantity   = c["quantity"]
            paid_time  = c["paid_time"]
            session.add(ShoppingCart(
                product_id     = product.product_id,
                quantity       = quantity,
                unit_price     = unit_price,
                total_value    = unit_price * quantity,
                status         = c["status"],
                added_date     = paid_time.date() if paid_time else date.today(),
                paid_time      = paid_time,
                delivered_time = c["delivered_time"],
            ))

        session.commit()
        print(f"Database seeded at {_DB_PATH}")
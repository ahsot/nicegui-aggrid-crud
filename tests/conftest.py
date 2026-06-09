"""
conftest.py
===========
Pytest configuration for tests directory.

Conditionally skips async tests when running on CI environments.
"""

import os

import pytest


def pytest_configure(config):
    """
    Add custom markers and configure pytest.
    """
    config.addinivalue_line(
        "markers", "asyncio: mark test as requiring asyncio support (skipped on CI)"
    )


def pytest_collection_modifyitems(config, items):
    """
    Skip async tests on CI environments if pytest-asyncio is not available.
    """
    # Check if we're running on CI
    is_ci = os.getenv("CI") == "true"

    if is_ci:
        # Check if pytest-asyncio is available
        try:
            import pytest_asyncio  # noqa: F401

            asyncio_available = True
        except ImportError:
            asyncio_available = False

        if not asyncio_available:
            # Skip all tests marked with asyncio
            skip_marker = pytest.mark.skip(reason="pytest-asyncio not available on CI")
            for item in items:
                if "asyncio" in item.keywords:
                    item.add_marker(skip_marker)

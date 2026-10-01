"""Shared fixtures for the AURORA backend test suite.

Two rules these tests must respect:

1. Nothing writes to the real ``backend/data`` tree — ``STORAGE_ROOT`` is
   redirected to a throwaway directory for every test.
2. The suite must not need PostgreSQL or Redis. ``app.main`` does, but no
   test imports it, so a database-less run stays possible.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Make `import app...` work regardless of the working directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Settings are constructed lazily; supply non-secret fallbacks so importing
# the services never depends on a particular working directory holding .env.
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://aurora:aurora@localhost:5432/aurora"
)
os.environ.setdefault("AURORA_JWT_SECRET", "test-only-secret")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from app.config import get_settings  # noqa: E402


@pytest.fixture(autouse=True)
def storage_root(tmp_path, monkeypatch):
    """Point STORAGE_ROOT at a fresh directory for the duration of a test."""
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "data"))
    get_settings.cache_clear()
    yield tmp_path / "data"
    get_settings.cache_clear()


@pytest.fixture
def roi_shape():
    from app.utils.constants import ROI_SHAPE

    return ROI_SHAPE


@pytest.fixture
def filler():
    """A deterministic field of the requested shape with a marker value."""

    def _make(shape, value: float = 0.25) -> np.ndarray:
        return np.full(shape, value, dtype=np.float32)

    return _make

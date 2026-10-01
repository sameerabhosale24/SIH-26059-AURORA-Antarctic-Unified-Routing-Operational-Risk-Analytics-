"""Base class every AURORA data source adapter implements.

Contract — non-negotiable:

* ``is_configured()`` reports whether the credentials (or local files) the
  source needs are present. It never touches the network.
* ``fetch()`` raises :class:`NotImplementedError` when the source is not
  configured, so a half-set-up deployment fails loudly instead of silently
  ingesting nothing.
* ``regrid()`` is a pure, idempotent function of its argument. Same input,
  same output, no I/O, no clock, no randomness.
* Missing data is ``None`` or NaN. Zeros are a legitimate SIC value (open
  water) and must never double for "unknown".
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import date
from typing import Any

import numpy as np


class DataSource(ABC):
    """One remote or local source of gridded fields."""

    #: Short identifier, used for logs and as the default ``data_version`` key.
    name: str = "source"

    #: Human label for the health endpoint.
    label: str = ""

    def __repr__(self) -> str:  # pragma: no cover — debugging aid
        return f"<{type(self).__name__} name={self.name!r} configured={self.is_configured()}>"

    @property
    def logger(self) -> logging.Logger:
        return logging.getLogger(f"aurora.adapter.{self.name}")

    @abstractmethod
    def is_configured(self) -> bool:
        """True when every credential / file this source needs is present."""

    @abstractmethod
    async def fetch(self, day: date) -> Any:
        """Download the raw payload for ``day``.

        Raises ``NotImplementedError`` when :meth:`is_configured` is False.
        """

    @abstractmethod
    def regrid(self, raw: Any) -> np.ndarray:
        """Resample ``raw`` onto the ROI grid, shape ``[101, 361]`` (or
        ``[C, 101, 361]`` for a multi-channel source)."""

    def version_key(self) -> str:
        """``data_version`` row this source feeds."""
        return self.name

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------
    def _require_configured(self) -> None:
        if not self.is_configured():
            self.logger.warning("adapter %s not configured", self.name)
            raise NotImplementedError(
                f"adapter {self.name} is not configured — set its credentials "
                "in backend/.env (see backend/.env.example)"
            )

    async def fetch_if_available(self, day: date) -> Any | None:
        """Fetch, or log and return ``None`` when unconfigured.

        This is the path the scheduler uses: an unconfigured source is a
        normal, reportable state, not an exception. It never fabricates data.
        """
        if not self.is_configured():
            self.logger.warning("adapter %s not configured", self.name)
            return None
        return await self.fetch(day)

    def _roi_shape_error(self, shape: tuple[int, ...]) -> ValueError:
        from app.utils.constants import ROI_SHAPE

        return ValueError(
            f"adapter {self.name} regridded to {shape}, expected {ROI_SHAPE}"
        )

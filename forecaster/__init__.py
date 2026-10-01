"""Repo-root import shim — NOT part of the installed package.

The installable package lives in ``forecaster/src/`` and is mapped onto the
import name ``forecaster`` by ``pyproject.toml``
(``package-dir = {"forecaster" = "src"}``).

This file only takes effect when the REPOSITORY ROOT is itself on
``sys.path`` (e.g. ``uvicorn`` or ``python -m pytest`` started from the repo
root): Python then resolves ``import forecaster`` to this directory *before*
consulting the installed package, and without this file the result would be
an empty namespace package.

It re-exports exactly the same public API as ``src/__init__.py`` and aliases
the internal submodules so ``forecaster.<module>`` resolves to the same
module objects in both import modes.
"""

import importlib
import sys

from .src.predict import predict, ForecastOutput
from .src.model import ConvLSTMForecaster, ConvLSTMCell

__all__ = ["predict", "ForecastOutput", "ConvLSTMForecaster", "ConvLSTMCell"]

for _name in (
    "artifacts_loader",
    "confidence",
    "conformal",
    "constants",
    "model",
    "predict",
    "scaler",
):
    sys.modules[f"{__name__}.{_name}"] = importlib.import_module(
        f".src.{_name}", __name__
    )
del _name

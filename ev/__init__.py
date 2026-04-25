"""EV calculator package.

The two model files (``percentile calc v1.py`` and ``sell probablity model.py``)
have spaces in their names and cannot be imported with normal ``from ev.x import y``
syntax. This module loads them once via ``importlib`` and re-exports the public
functions so callers can do ``from ev import value_listing, estimate_sell_probability``.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

_HERE = Path(__file__).resolve().parent


def _load(filename: str, module_name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, _HERE / filename)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_percentile = _load("percentile calc v1.py", "ev._percentile_calc_v1")
_sell_prob = _load("sell probablity model.py", "ev._sell_probability_model")

value_listing = _percentile.value_listing
process_scrape = _percentile.process_scrape
estimate_sell_probability = _sell_prob.estimate_sell_probability

__all__ = [
    "value_listing",
    "process_scrape",
    "estimate_sell_probability",
]

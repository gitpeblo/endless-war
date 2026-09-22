"""Configuration loading.

Balancing values live in config/default.toml, never hardcoded in systems.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "default.toml"


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Load and return the TOML configuration as a plain dict."""
    target = path or DEFAULT_CONFIG_PATH
    with target.open("rb") as handle:
        return tomllib.load(handle)

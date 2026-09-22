"""Persistence interface placeholders."""

from pathlib import Path


class SaveStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        """Create database/schema when persistence is implemented."""
        self.path.parent.mkdir(parents=True, exist_ok=True)

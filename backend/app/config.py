"""Filesystem locations for the application, independent of the current cwd."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _project_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    database_path: Path
    derived_dir: Path


def settings_from_env(overrides: dict | None = None) -> Settings:
    overrides = overrides or {}
    data_dir = _project_path(overrides.get("DATA_DIR", os.getenv("DATA_DIR", "data")))
    derived_dir = _project_path(
        overrides.get("DERIVED_DIR", os.getenv("DERIVED_DIR", "backend/derived"))
    )
    database_path = Path(overrides.get("DATABASE_PATH", derived_dir / "sdoc.sqlite3"))
    if not database_path.is_absolute():
        database_path = _project_path(database_path)
    return Settings(
        data_dir=data_dir.resolve(),
        database_path=database_path.resolve(),
        derived_dir=derived_dir.resolve(),
    )

"""Shared helpers for testing standalone scripts under /scripts."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Callable
from uuid import uuid4

import pytest


@pytest.fixture
def load_script_module() -> Callable[[str], ModuleType]:
    """Return a helper that imports a script file as a fresh module."""

    scripts_dir = Path(__file__).resolve().parents[3] / "scripts"

    def _load(script_filename: str) -> ModuleType:
        script_path = scripts_dir / script_filename
        module_name = f"test_script_{script_filename.replace('.', '_')}_{uuid4().hex}"
        spec = importlib.util.spec_from_file_location(module_name, script_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Failed to create import spec for {script_path}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    return _load

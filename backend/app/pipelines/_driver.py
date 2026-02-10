"""Hamilton driver factory for the grievance analytics project."""

from __future__ import annotations

from types import ModuleType

from hamilton import driver


def build_driver(
    *modules: ModuleType,
    config: dict | None = None,
) -> driver.Driver:
    """
    Build a Hamilton Driver from the given node modules.

    Parameters
    ----------
    *modules : ModuleType
        Hamilton node modules (each .py file whose top-level functions become nodes).
    config : dict | None
        Hamilton config dict for @config.when decorators.
    """
    return (
        driver.Builder()
        .with_modules(*modules)
        .with_config(config or {})
        .build()
    )

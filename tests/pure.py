"""Load the Home Assistant-free modules by path.

The package's __init__ imports Home Assistant, so
``custom_components.envisalink_field_programmer`` cannot be imported on a
workstation without it. client.py, const.py, models.py, state_machine.py and
field_programming.py are deliberately free of that import; this registers a
stand-in package whose __path__ points at the component directory, so their
relative imports resolve and they load exactly as written.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
COMPONENT = ROOT / "custom_components" / "envisalink_field_programmer"

_PACKAGE = "envisalink_field_programmer_pure"


def load(name: str) -> types.ModuleType:
    """Import custom_components/envisalink_field_programmer/<name>.py without Home Assistant."""
    if _PACKAGE not in sys.modules:
        package = types.ModuleType(_PACKAGE)
        package.__path__ = [str(COMPONENT)]
        sys.modules[_PACKAGE] = package
    full = f"{_PACKAGE}.{name}"
    if full in sys.modules:
        return sys.modules[full]
    spec = importlib.util.spec_from_file_location(full, COMPONENT / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[full] = module
    spec.loader.exec_module(module)
    return module

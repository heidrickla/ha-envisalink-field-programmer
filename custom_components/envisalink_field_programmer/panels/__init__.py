"""Panel model + dialect registry.

Public entry points:

  * :data:`MODELS` -- every supported :class:`PanelModel`, ordered for display.
  * :func:`get_model` -- resolve a model id (or alias) to its :class:`PanelModel`.
  * :func:`get_dialect` -- the :class:`PanelDialect` for a model id.
  * :data:`DEFAULT_MODEL_ID` -- the VISTA-21iP, this integration's origin panel.
"""
from __future__ import annotations

from .base import (
    GuidedOp,
    PanelDialect,
    PanelFamily,
    PanelModel,
    TimingFieldDef,
    Verification,
    ZoneTypeDef,
)
from .dsc import DSC_DIALECT, DSC_MODELS
from .vista import COMMERCIAL_VISTA_DIALECT, VISTA_DIALECT, VISTA_MODELS

MODELS: tuple[PanelModel, ...] = VISTA_MODELS + DSC_MODELS

DEFAULT_MODEL_ID = "vista_21ip"

# Dialects are keyed by dialect id. A model uses its own ``dialect_id`` if set,
# otherwise its family's default (family value == that dialect's key).
_DIALECTS: dict[str, PanelDialect] = {
    PanelFamily.VISTA.value: VISTA_DIALECT,
    "vista_commercial": COMMERCIAL_VISTA_DIALECT,
    PanelFamily.DSC_POWERSERIES.value: DSC_DIALECT,
}

# Build a lookup covering canonical ids and every alias, case/spacing tolerant.
_BY_KEY: dict[str, PanelModel] = {}
for _model in MODELS:
    for _key in (_model.model_id, *_model.aliases):
        _BY_KEY[_key.lower()] = _model


def _normalize(model_id: str) -> str:
    return model_id.strip().lower().replace(" ", "").replace("_", "").replace("-", "")


# Second, punctuation-insensitive index so "VISTA-20P", "vista_20p", "20p" all hit.
_BY_NORMALIZED: dict[str, PanelModel] = {}
for _model in MODELS:
    for _key in (_model.model_id, *_model.aliases):
        _BY_NORMALIZED.setdefault(_normalize(_key), _model)


def get_model(model_id: str | None) -> PanelModel:
    """Resolve a stored model id or alias to a :class:`PanelModel`.

    Falls back to the default (VISTA-21iP) for ``None``/empty, and raises
    :class:`KeyError` for a non-empty but unrecognized id so a typo surfaces
    loudly rather than silently arming the wrong dialect.
    """
    if not model_id:
        return _BY_KEY[DEFAULT_MODEL_ID.lower()]
    key = model_id.lower()
    if key in _BY_KEY:
        return _BY_KEY[key]
    norm = _normalize(model_id)
    if norm in _BY_NORMALIZED:
        return _BY_NORMALIZED[norm]
    raise KeyError(f"Unknown panel model {model_id!r}")


def get_dialect(model_id: str | None) -> PanelDialect:
    """Return the dialect for a model id (default panel for ``None``)."""
    model = get_model(model_id)
    return _DIALECTS[model.dialect_id or model.family.value]


def model_choices() -> dict[str, str]:
    """``{model_id: label}`` for building the config-flow dropdown."""
    return {m.model_id: m.label for m in MODELS}


__all__ = [
    "DEFAULT_MODEL_ID",
    "MODELS",
    "GuidedOp",
    "PanelDialect",
    "PanelFamily",
    "PanelModel",
    "TimingFieldDef",
    "Verification",
    "ZoneTypeDef",
    "get_dialect",
    "get_model",
    "model_choices",
]

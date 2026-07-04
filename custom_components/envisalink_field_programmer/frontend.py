"""Serve the bundled Lovelace card and register it as a frontend resource.

The card is built ahead of time (see www/envisalink-field-programmer-card/
at the repo root for source + build tooling) and its output is committed
straight into this package at
``www/envisalink-field-programmer-card.js``. That placement matters: HACS
only installs the ``custom_components/<domain>`` tree for an
``integration``-category repository, so the compiled asset has to live
inside it, not in a top-level ``www/`` folder, or it would never reach a
user's Home Assistant install.

Registering it here means users get the card automatically after
installing/reloading the integration -- no manual "add Lovelace resource"
step.
"""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

URL_BASE = "/envisalink_field_programmer_static"
CARD_FILENAME = "envisalink-field-programmer-card.js"
_REGISTERED_KEY = f"{DOMAIN}_frontend_registered"


async def async_register_frontend(hass: HomeAssistant) -> None:
    """Idempotently mount and register the bundled card, once per HA run.

    This is a "nice to have": the alarm/zone entities and services are
    fully functional without the card. A failure here (e.g. the `http`
    component not being loaded, as happens in some test/minimal setups)
    must never fail the whole config entry setup, so every failure mode is
    caught and logged rather than raised.
    """
    if hass.data.get(_REGISTERED_KEY):
        return

    if hass.http is None:
        _LOGGER.debug(
            "hass.http is not available; skipping the frontend card "
            "registration (entities and services are unaffected)."
        )
        return

    www_dir = Path(__file__).parent / "www"
    card_path = www_dir / CARD_FILENAME
    if not card_path.is_file():
        _LOGGER.warning(
            "Card asset missing at %s; the Lovelace card will not be "
            "available. Run `npm run build` in "
            "www/envisalink-field-programmer-card/ and reinstall.",
            card_path,
        )
        return

    try:
        try:
            from homeassistant.components.http import StaticPathConfig

            await hass.http.async_register_static_paths(
                [StaticPathConfig(URL_BASE, str(www_dir), cache_headers=True)]
            )
        except ImportError:
            # Home Assistant core < 2024.7 does not have StaticPathConfig.
            hass.http.register_static_path(URL_BASE, str(www_dir), cache_headers=True)

        add_extra_js_url(hass, f"{URL_BASE}/{CARD_FILENAME}")
        hass.data[_REGISTERED_KEY] = True
    except Exception:  # noqa: BLE001
        _LOGGER.warning(
            "Could not register the frontend card asset; entities and "
            "services are unaffected.",
            exc_info=True,
        )

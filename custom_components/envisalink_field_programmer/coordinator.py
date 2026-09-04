"""Coordinator that owns the EnvisalinkClient connection and VistaState.

This is a push-driven (``iot_class: local_push``) coordinator: instead of
polling on an interval, it keeps a long-lived TCP session open and updates
listeners whenever the Envisalink reports a state change. Two things are
still sent on a timer, since the protocol offers no better alternative:

  * a keepalive poll, purely to detect a silently-dead connection and
    trigger reconnection.
  * a zone timer dump request (``%FF``), the only authoritative source of
    zone open/closed state for a Honeywell panel over this protocol (see
    state_machine.py) -- the panel doesn't push zone changes on its own.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .client import EnvisalinkClient, TPIError, TPIEvent
from .const import (
    DEFAULT_KEEPALIVE_INTERVAL,
    RECONNECT_BACKOFF_MAX,
    RECONNECT_BACKOFF_MIN,
    ZONE_TIMER_DUMP_INTERVAL,
)
from .models import VistaState
from .panels import get_dialect, get_model
from .state_machine import apply_event

_LOGGER = logging.getLogger(__name__)

type VistaConsoleConfigEntry = ConfigEntry[VistaConsoleCoordinator]


class VistaConsoleCoordinator(DataUpdateCoordinator[VistaState]):
    """Owns the connection lifecycle and current state snapshot."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: VistaConsoleConfigEntry,
        *,
        host: str,
        port: int,
        password: str,
        num_partitions: int,
        num_zones: int,
        keepalive_interval: int = DEFAULT_KEEPALIVE_INTERVAL,
        installer_code: str | None = None,
        panel_model: str | None = None,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"envisalink_field_programmer:{host}",
            config_entry=entry,
            update_interval=None,
        )
        self.entry = entry
        self._host = host
        self._port = port
        self._password = password
        self._keepalive_interval = keepalive_interval
        # Only needed for the field-programming layer (opening Program Mode);
        # arm/disarm/status/bypass never use it. See programming.py.
        self.installer_code = installer_code
        # Which panel model/dialect this entry drives. Defaults to the
        # VISTA-21iP (see panels/) so pre-existing entries with no stored
        # model behave exactly as before.
        self.panel_model = get_model(panel_model)
        self.dialect = get_dialect(panel_model)
        self.data = VistaState.create(num_partitions, num_zones)

        self.client = EnvisalinkClient(
            host,
            port,
            password,
            event_callback=self._handle_event,
            disconnect_callback=self._handle_disconnect,
        )

        self._periodic_task: asyncio.Task[None] | None = None
        self._reconnect_task: asyncio.Task[None] | None = None
        self._backoff = RECONNECT_BACKOFF_MIN
        self._shutting_down = False
        self.last_event: TPIEvent | None = None
        self._remove_stop_listener: Callable[[], None] | None = None

    async def async_setup(self) -> None:
        """Establish the initial connection. Raises on failure.

        A failure after login closes the socket before re-raising: the
        Envisalink admits one TPI client at a time, so a half-open session
        left behind would make every retry fail as "cannot connect".
        """
        await self.client.connect()
        self.data.system.connected = True
        try:
            await self.client.dump_zone_timers()
        except (TPIError, OSError):
            # Through async_shutdown so the read loop's disconnect callback
            # sees the shutting-down flag and does not start a reconnect.
            self.data.system.connected = False
            await self.async_shutdown()
            raise
        self._periodic_task = self.entry.async_create_background_task(
            self.hass, self._periodic_loop(), name=f"{self.name} periodic"
        )
        # Belt-and-suspenders: async_shutdown() is normally reached via
        # async_unload_entry(), but that isn't guaranteed on every teardown
        # path (e.g. a core stop without an explicit entry unload). Without
        # this, the keepalive/reconnect tasks below just keep running
        # against a socket nothing is listening on anymore.
        self._remove_stop_listener = self.hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STOP, self._handle_hass_stop
        )

    async def _handle_hass_stop(self, _event: Event) -> None:
        await self.async_shutdown()

    async def async_shutdown(self) -> None:
        self._shutting_down = True
        if self._remove_stop_listener is not None:
            self._remove_stop_listener()
            self._remove_stop_listener = None
        for task in (self._periodic_task, self._reconnect_task):
            if task is not None:
                task.cancel()
        await self.client.disconnect()

    async def _async_update_data(self) -> VistaState:
        # Push-driven: nothing to actively fetch. Listeners are refreshed
        # via async_set_updated_data() from _handle_event() as events arrive.
        return self.data

    def _handle_event(self, event: TPIEvent) -> None:
        self.last_event = event
        apply_event(self.data, event)
        self.async_set_updated_data(self.data)

    def _handle_disconnect(self, error: Exception | None) -> None:
        self.data.system.connected = False
        self.async_set_updated_data(self.data)
        if self._shutting_down:
            return
        # Once per outage; the retries below log at debug and the recovery
        # is logged once when it happens.
        _LOGGER.info("Lost the connection to the Envisalink at %s: %s", self._host, error)
        self._reconnect_task = self.entry.async_create_background_task(
            self.hass, self._reconnect_loop(), name=f"{self.name} reconnect"
        )

    async def _periodic_loop(self) -> None:
        """Keepalive + zone timer dump, both on their own cadence."""
        try:
            next_keepalive = self._keepalive_interval
            next_zone_dump = ZONE_TIMER_DUMP_INTERVAL
            tick = min(self._keepalive_interval, ZONE_TIMER_DUMP_INTERVAL)
            while True:
                await asyncio.sleep(tick)
                next_keepalive -= tick
                next_zone_dump -= tick
                if not self.client.connected:
                    continue
                if next_keepalive <= 0:
                    next_keepalive = self._keepalive_interval
                    try:
                        await self.client.keep_alive()
                    except Exception:  # noqa: BLE001
                        _LOGGER.debug("Keepalive poll failed", exc_info=True)
                if next_zone_dump <= 0:
                    next_zone_dump = ZONE_TIMER_DUMP_INTERVAL
                    try:
                        await self.client.dump_zone_timers()
                    except Exception:  # noqa: BLE001
                        _LOGGER.debug("Zone timer dump request failed", exc_info=True)
        except asyncio.CancelledError:
            raise

    async def _reconnect_loop(self) -> None:
        try:
            while not self._shutting_down:
                await asyncio.sleep(self._backoff)
                try:
                    await self.client.connect()
                except Exception as err:  # noqa: BLE001
                    _LOGGER.debug("Envisalink Field Programmer reconnect attempt failed: %s", err)
                    self._backoff = min(self._backoff * 2, RECONNECT_BACKOFF_MAX)
                    continue
                self._backoff = RECONNECT_BACKOFF_MIN
                self.data.system.connected = True
                _LOGGER.info("Reconnected to the Envisalink at %s", self._host)
                try:
                    await self.client.dump_zone_timers()
                except (TPIError, OSError):
                    _LOGGER.debug("Zone timer dump after reconnect failed", exc_info=True)
                self.async_set_updated_data(self.data)
                return
        except asyncio.CancelledError:
            raise

    # -- High level actions used by entity platforms -----------------------

    async def async_arm_away(self, partition: int, code: str) -> None:
        await self._async_send_arm_disarm_keystrokes(partition, f"{code}2")

    async def async_arm_stay(self, partition: int, code: str) -> None:
        await self._async_send_arm_disarm_keystrokes(partition, f"{code}3")

    async def async_arm_night(self, partition: int, code: str) -> None:
        await self._async_send_arm_disarm_keystrokes(partition, f"{code}33")

    async def async_disarm(self, partition: int, code: str) -> None:
        await self._async_send_arm_disarm_keystrokes(partition, f"{code}1")

    async def _async_send_arm_disarm_keystrokes(self, partition: int, keys: str) -> None:
        """Arm/disarm by typing the user code + mode digit(s), like a real keypad.

        Routed through the same guardrail as every other keystroke send
        (see programming.py) for defense in depth, even though a plain
        code+digit sequence is extremely unlikely to collide with the
        Program Mode trigger pattern it guards against.
        """
        from .programming import async_send_guarded_keystrokes  # avoid import cycle

        await async_send_guarded_keystrokes(
            self.client,
            partition,
            keys,
            installer_code=self.installer_code,
            dialect=self.dialect,
        )

    async def async_toggle_zone_bypass(self, zone_number: int) -> None:
        """Toggle bypass on a single zone via the standard *1zz# keypad sequence.

        The real protocol has no acknowledgement that ties back to which
        zone got bypassed, so the resulting ``bypassed`` flag is set
        optimistically here and only cleared later once the partition's
        bypass icon flag reports no bypass active (see state_machine.py).
        """
        from .programming import async_send_guarded_keystrokes  # avoid import cycle

        zone = self.data.zone(zone_number)
        keys = f"*1{zone_number:02d}#"
        await async_send_guarded_keystrokes(self.client, zone.partition, keys, dialect=self.dialect)
        zone.bypassed = not zone.bypassed
        self.async_set_updated_data(self.data)

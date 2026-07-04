"""Coordinator that owns the EnvisalinkClient connection and VistaState.

This is a push-driven (``iot_class: local_push``) coordinator: instead of
polling on an interval, it keeps a long-lived TCP session open and updates
listeners whenever the Envisalink reports a state change. A lightweight
poll (TPI command 000) is still sent on ``keepalive_interval`` purely to
detect a silently-dead connection and trigger reconnection.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .client import EnvisalinkClient, TPIEvent
from .const import (
    DEFAULT_KEEPALIVE_INTERVAL,
    RECONNECT_BACKOFF_MAX,
    RECONNECT_BACKOFF_MIN,
)
from .models import VistaState
from .state_machine import apply_event

_LOGGER = logging.getLogger(__name__)

_CODE_REQUEST_CODES = {"900", "921", "922"}


class VistaConsoleCoordinator(DataUpdateCoordinator[VistaState]):
    """Owns the connection lifecycle and current state snapshot."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        *,
        host: str,
        port: int,
        password: str,
        num_partitions: int,
        num_zones: int,
        keepalive_interval: int = DEFAULT_KEEPALIVE_INTERVAL,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"vista_console:{host}",
            config_entry=entry,
            update_interval=None,
        )
        self._host = host
        self._port = port
        self._password = password
        self._keepalive_interval = keepalive_interval
        self.data = VistaState.create(num_partitions, num_zones)

        self.client = EnvisalinkClient(
            host,
            port,
            password,
            event_callback=self._handle_event,
            disconnect_callback=self._handle_disconnect,
        )

        self._keepalive_task: asyncio.Task | None = None
        self._reconnect_task: asyncio.Task | None = None
        self._backoff = RECONNECT_BACKOFF_MIN
        self._shutting_down = False
        self._code_request_waiters: list[asyncio.Future[str]] = []
        self.last_event: TPIEvent | None = None
        self._remove_stop_listener: Callable[[], None] | None = None

    async def async_setup(self) -> None:
        """Establish the initial connection. Raises on failure."""
        await self.client.connect()
        self.data.system.connected = True
        await self.client.status_report()
        self._keepalive_task = self.hass.loop.create_task(self._keepalive_loop())
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
        for task in (self._keepalive_task, self._reconnect_task):
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
        if event.code in _CODE_REQUEST_CODES:
            self._resolve_code_waiters(event.code)
        self.async_set_updated_data(self.data)

    def _handle_disconnect(self, error: Exception | None) -> None:
        self.data.system.connected = False
        self.async_set_updated_data(self.data)
        if self._shutting_down:
            return
        _LOGGER.warning("Vista Console lost connection to %s: %s", self._host, error)
        self._reconnect_task = self.hass.loop.create_task(self._reconnect_loop())

    async def _keepalive_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._keepalive_interval)
                if self.client.connected:
                    try:
                        await self.client.poll()
                    except Exception:  # noqa: BLE001
                        _LOGGER.debug("Keepalive poll failed", exc_info=True)
        except asyncio.CancelledError:
            raise

    async def _reconnect_loop(self) -> None:
        try:
            while not self._shutting_down:
                await asyncio.sleep(self._backoff)
                try:
                    await self.client.connect()
                except Exception as err:  # noqa: BLE001
                    _LOGGER.debug("Vista Console reconnect attempt failed: %s", err)
                    self._backoff = min(self._backoff * 2, RECONNECT_BACKOFF_MAX)
                    continue
                self._backoff = RECONNECT_BACKOFF_MIN
                self.data.system.connected = True
                await self.client.status_report()
                self.async_set_updated_data(self.data)
                return
        except asyncio.CancelledError:
            raise

    def _resolve_code_waiters(self, code: str) -> None:
        waiters, self._code_request_waiters = self._code_request_waiters, []
        for waiter in waiters:
            if not waiter.done():
                waiter.set_result(code)

    async def async_wait_for_code_request(self, timeout: float = 10) -> str:
        """Block until the panel asks us for a code (900/921/922), or time out."""
        waiter: asyncio.Future[str] = self.hass.loop.create_future()
        self._code_request_waiters.append(waiter)
        try:
            return await asyncio.wait_for(waiter, timeout=timeout)
        finally:
            if waiter in self._code_request_waiters:
                self._code_request_waiters.remove(waiter)

    # -- High level actions used by entity platforms -----------------------

    async def async_arm_away(self, partition: int) -> None:
        await self.client.arm_away(partition)

    async def async_arm_stay(self, partition: int) -> None:
        await self.client.arm_stay(partition)

    async def async_arm_night(self, partition: int) -> None:
        await self.client.arm_zero_entry(partition)

    async def async_disarm(self, partition: int, code: str) -> None:
        await self.client.disarm(partition, code)

    async def async_toggle_zone_bypass(self, zone_number: int) -> None:
        """Toggle bypass on a single zone via the standard *1zz# keypad sequence.

        Routed through the same guardrail every other keystroke send goes
        through (see programming.py), even though this particular sequence
        is an ordinary end-user operation with no installer-mode risk.
        """
        from .programming import async_send_guarded_keystrokes  # avoid import cycle

        zone = self.data.zone(zone_number)
        keys = f"*1{zone_number:02d}#"
        await async_send_guarded_keystrokes(self.client, zone.partition, keys)

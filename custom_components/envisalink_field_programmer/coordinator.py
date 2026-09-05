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
import contextlib
import logging
from collections.abc import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .client import EnvisalinkClient, TPIError, TPIEvent
from .const import (
    DEFAULT_KEEPALIVE_INTERVAL,
    DOMAIN,
    ISSUE_TPI_SESSION_BUSY,
    RECONNECT_BACKOFF_MAX,
    RECONNECT_BACKOFF_MIN,
    RECONNECT_FAILURES_BEFORE_ISSUE,
    SETUP_RETRY_DELAY,
    ZONE_TIMER_DUMP_INTERVAL,
)
from .models import VistaState
from .panels import get_dialect, get_model
from .state_machine import apply_event

_LOGGER = logging.getLogger(__name__)

type VistaConsoleConfigEntry = ConfigEntry[VistaConsoleCoordinator]


async def _cancel_and_wait(task: asyncio.Task[None] | None) -> None:
    """Cancel a background task and wait for the cancellation to land.

    Everything this coordinator cancels can be holding a socket to the
    module, which admits exactly one TPI client. Returning before the
    cancellation has actually taken effect hands the next caller a module
    that still thinks its one slot is busy.
    """
    if task is None or task.done():
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


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
        self._failed_reconnects = 0
        # One issue per entry, so two Envisalinks do not overwrite each other.
        self.issue_id = f"{ISSUE_TPI_SESSION_BUSY}_{entry.entry_id}"
        self._shutting_down = False
        # Set while something else is deliberately borrowing the module's one
        # TPI session (the reconfigure flow's probe), so the disconnect that
        # causes does not start a reconnect that would take the session back.
        self._session_released = False
        self.last_event: TPIEvent | None = None
        self._remove_stop_listener: Callable[[], None] | None = None

    async def async_setup(self) -> None:
        """Establish the initial connection. Raises on failure.

        A failure after login closes the socket before re-raising: the
        Envisalink admits one TPI client at a time, so a half-open session
        left behind would make every retry fail as "cannot connect".

        The first connect is the one that races whatever held the session
        before it -- usually the config flow's own probe -- so it is the one
        that gets a second attempt before the entry is failed. Home
        Assistant's retry would also recover, five seconds later and with a
        failed entry in between.
        """
        await self.client.connect_with_retry(SETUP_RETRY_DELAY)
        self.data.system.connected = True
        self.async_clear_connection_issue()
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

    async def async_release_session(self) -> None:
        """Give up the module's single TPI session until told to take it back.

        The Envisalink admits one TPI client at a time, so the reconfigure
        flow cannot prove a login while this coordinator is connected. It
        calls this first, probes, and then either reloads the entry (which
        connects afresh) or calls async_resume_session() because the probe
        failed and the entry is staying as it is.

        A reconnect already in flight is cancelled and then awaited out.
        Cancelling alone is not enough: the reconnect could be sitting inside
        client.connect(), part-way through a login on a socket the client does
        not own yet, and the probe would dial into a module that still has its
        one slot taken. Awaiting the cancellation makes connect() finish
        closing that socket before the probe goes anywhere near the module.
        """
        self._session_released = True
        reconnect_task = self._reconnect_task
        self._reconnect_task = None
        await _cancel_and_wait(reconnect_task)
        await self.client.disconnect()

    async def async_resume_session(self) -> None:
        """Take the session back after async_release_session().

        Reconnects at once, because the entry is loaded and its entities are
        unavailable meanwhile. A module that is not ready yet falls back to
        the usual reconnect loop rather than being left down.
        """
        self._session_released = False
        if self._shutting_down or self.client.connected:
            return
        try:
            await self.client.connect()
        except (TPIError, OSError) as err:
            _LOGGER.debug("Could not take the TPI session back immediately: %s", err)
            self._backoff = RECONNECT_BACKOFF_MIN
            self._reconnect_task = self.entry.async_create_background_task(
                self.hass, self._reconnect_loop(), name=f"{self.name} reconnect"
            )
            return
        self.data.system.connected = True
        self.async_clear_connection_issue()
        try:
            await self.client.dump_zone_timers()
        except (TPIError, OSError):
            _LOGGER.debug("Zone timer dump after taking the session back failed", exc_info=True)
        self.async_set_updated_data(self.data)

    async def _handle_hass_stop(self, _event: Event) -> None:
        await self.async_shutdown()

    def _async_raise_connection_issue(self) -> None:
        """Name the usual cause of a long outage: the single TPI session.

        The Envisalink admits one TPI client at a time, so an integration,
        app or portal session left connected looks exactly like an
        unreachable host. That is something the user can act on, which is
        what a repair issue is for.
        """
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            self.issue_id,
            is_fixable=False,
            issue_domain=DOMAIN,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_TPI_SESSION_BUSY,
            translation_placeholders={"host": self._host, "title": self.entry.title},
        )

    def async_clear_connection_issue(self) -> None:
        """Drop the issue once the Envisalink answers again."""
        ir.async_delete_issue(self.hass, DOMAIN, self.issue_id)

    async def async_shutdown(self) -> None:
        self._shutting_down = True
        if self._remove_stop_listener is not None:
            self._remove_stop_listener()
            self._remove_stop_listener = None
        tasks = (self._periodic_task, self._reconnect_task)
        self._periodic_task = None
        self._reconnect_task = None
        for task in tasks:
            # Awaited out for the same reason the release path does it: a
            # reconnect cancelled inside client.connect() has a socket of its
            # own open, and only letting the cancellation land closes it.
            await _cancel_and_wait(task)
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
        if self._shutting_down or self._session_released:
            # Deliberate: the entry is going away, or the reconfigure flow is
            # borrowing the module's one session and will hand it back.
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
            while not self._shutting_down and not self._session_released:
                await asyncio.sleep(self._backoff)
                try:
                    await self.client.connect()
                except Exception as err:  # noqa: BLE001
                    _LOGGER.debug("Envisalink Field Programmer reconnect attempt failed: %s", err)
                    self._failed_reconnects += 1
                    if self._failed_reconnects == RECONNECT_FAILURES_BEFORE_ISSUE:
                        self._async_raise_connection_issue()
                    self._backoff = min(self._backoff * 2, RECONNECT_BACKOFF_MAX)
                    continue
                self._failed_reconnects = 0
                self._backoff = RECONNECT_BACKOFF_MIN
                self.data.system.connected = True
                self.async_clear_connection_issue()
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

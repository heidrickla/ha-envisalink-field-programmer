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
import re
import time
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import replace
from typing import override
from uuid import uuid4

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .client import (
    EnvisalinkClient,
    KeyTyper,
    TPICommandRefused,
    TPIError,
    TPIEvent,
    TPINotSent,
)
from .const import (
    DEFAULT_KEEPALIVE_INTERVAL,
    DOMAIN,
    ISSUE_PROGRAM_MODE_UNKNOWN,
    ISSUE_TPI_SESSION_BUSY,
    PARTITION_REPORT_TIMEOUT,
    PROGRAM_MODE_REPORT_TIMEOUT,
    RECONNECT_BACKOFF_MAX,
    RECONNECT_BACKOFF_MIN,
    RECONNECT_FAILURES_BEFORE_ISSUE,
    SETUP_RETRY_DELAY,
    ZONE_TIMER_DUMP_INTERVAL,
)
from .field_programming import ProgrammingForm, ProgrammingResult
from .models import KeypadUse, ProgramMode, VistaState
from .panels import PanelFamily, get_dialect, get_model
from .program_mode_state import (
    Holder,
    ModeEvent,
    ModeRefusal,
    ModeState,
    Refusal,
    transition,
)
from .state_machine import (
    ProgramModeReport,
    apply_event,
    invalid_keypad_field,
    program_mode_report,
)

_LOGGER = logging.getLogger(__name__)

# The user code an arm or disarm types before its mode digit. VISTA user codes
# are four digits; DSC PowerSeries takes four or six. ASCII digits only.
_USER_CODE = re.compile(r"[0-9]{4}")
_DSC_USER_CODE = re.compile(r"[0-9]{4}|[0-9]{6}")

type VistaConsoleConfigEntry = ConfigEntry[VistaConsoleCoordinator]


class HeldKeypad:
    """The keypad, held for one sequence on one partition.

    Calling it types keys. Each key passes the coordinator's Program Mode gate
    at the instant it is written, with no await in between, so a report that
    lands while the key waits for the command lock or an earlier ack is seen
    before the key goes out.
    """

    def __init__(
        self,
        coordinator: VistaConsoleCoordinator,
        partition: int,
        use: KeypadUse,
        type_keys: KeyTyper,
    ) -> None:
        self._coordinator = coordinator
        self._partition = partition
        self._type_keys = type_keys
        self.use = use
        self.written = 0
        self.operation_id = str(uuid4())
        self.session_revision = coordinator._session_revision
        self.entry_length = 0
        # Keys whose write has begun. The gate passes and the write follows with
        # no await between, so each may have reached the panel whether or not
        # its acknowledgement came; a refusal, or a write that never happened,
        # takes its key back out.
        self.attempted = 0
        # The coordinator's change count and doubt generation when this
        # sequence's start raised the doubt, and its change count when the panel
        # reported this sequence's entry open.
        self.raised_at: int | None = None
        self.raised_generation: str | None = None
        self.opened_at: int | None = None

    async def __call__(self, keys: str) -> None:
        for key in keys:
            try:
                await self._type_keys(
                    self._partition, key, self._gate, self._accepted, self._refused
                )
            except TPICommandRefused, TPINotSent:
                self.attempted = self.written
                raise

    def _accepted(self) -> None:
        self.written += 1
        self.attempted = self.written

    def _refused(self) -> None:
        self.attempted = self.written

    def _gate(self) -> None:
        self._coordinator._before_key(self)

    def holder(self) -> Holder:
        """What this sequence has sent, for the decision on who owns a 627."""
        return Holder(
            self.operation_id,
            installer=self.use is KeypadUse.INSTALLER,
            entry_length=self.entry_length,
            written=self.written,
        )

    def program_mode_opened(self) -> None:
        """Bind the keys after a guided entry to the Program Mode the panel just reported."""
        self._coordinator._bind_open_program_mode(self)


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
        # Which panel model/dialect this entry drives. An entry with no stored
        # model resolves to the VISTA-21iP (see panels/).
        self.panel_model = get_model(panel_model)
        self.dialect = get_dialect(panel_model)
        self.num_partitions = num_partitions
        self.data = VistaState.create(num_partitions, num_zones)
        # What the device page's programming entities hold, and what became of
        # the last press of a programming button. Neither is panel state: the
        # panel cannot be read back, so these describe this integration's own
        # form and its own last attempt. Entities pick both up through the
        # coordinator's listeners, which a press notifies.
        self.programming = ProgrammingForm()
        self.last_programming_result: ProgrammingResult | None = None

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
        self._session_revision = 0
        self.last_event: TPIEvent | None = None
        self.program_mode_issue_id = f"{ISSUE_PROGRAM_MODE_UNKNOWN}_{entry.entry_id}"
        self._mode_store: Store[dict[str, object]] = Store(
            hass, 1, f"{DOMAIN}.program_mode.{entry.entry_id}"
        )
        self._mode = ModeState()
        self._mode_save_task: asyncio.Task[None] | None = None
        # The newest state revision the store is known to hold.
        self._durable_revision = -1
        self._less_cautious_pending = False
        self._pending_mode_events: list[Callable[[], None]] = []
        self._mode_save_error_revision: int | None = None
        self.rejected_keypad_updates: dict[str, int] = {}
        self._last_keypad_rejection_warning: dict[str, float] = {}
        self._partition_reported = asyncio.Event()
        self._program_mode_changed: asyncio.Event | None = None
        # The sequence that has typed installer or guided keys and still holds
        # the keypad: an armed report does not settle a doubt it raised.
        self._typing_holder: HeldKeypad | None = None
        self._keypad_holder: HeldKeypad | None = None
        self.data.system.program_mode = self.program_mode
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
        stored = await self._mode_store.async_load()
        if stored is not None:
            self._mode = transition(ModeState.restore(stored), ModeEvent.RELOAD)
        elif ir.async_get(self.hass).async_get_issue(
            DOMAIN, self.program_mode_issue_id
        ):
            self._mode = ModeState.restore({"mode": "doubt"})
        self._sync_mode()
        if self._mode.mode is not ProgramMode.CLOSED:
            await self._mode_store.async_save(self._mode.stored())
        await self.client.connect_with_retry(SETUP_RETRY_DELAY)
        await self._async_session_established(strict=True)
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
        self._session_revision += 1
        self.data.forget_partition_reports()
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
        await self._async_session_established(fold=ModeEvent.RECONNECT)

    async def _async_session_established(
        self, *, fold: ModeEvent | None = None, strict: bool = False
    ) -> None:
        """Everything a new session needs, whichever way it came about.

        The session is up; a reconnect folds into the Program Mode state. The
        push stream will not repeat what the panel reported before, so the zone
        timers and every partition's keypad are asked for. At first setup a
        failed zone dump fails the entry, through async_shutdown so the read
        loop's disconnect callback sees the shutting-down flag and does not
        start a reconnect; anywhere else the next timer retries it.
        """
        self.data.system.connected = True
        self._session_revision += 1
        self.data.forget_partition_reports()
        if fold is not None:
            self._transition(fold)
        self.async_clear_connection_issue()
        try:
            await self.client.dump_zone_timers()
        except TPIError, OSError:
            if strict:
                self.data.system.connected = False
                await self.async_shutdown()
                raise
            _LOGGER.debug("Zone timer dump after connecting failed", exc_info=True)
        await self._async_request_partition_reports(sorted(self.data.partitions))
        self.async_set_updated_data(self.data)

    async def _async_request_partition_reports(self, partitions: Sequence[int]) -> None:
        """Ask the module for each partition's keypad report, leaving it on 1.

        The TPI has no status request. ^01 names a partition without typing a
        key, so it is the one command that can ask; whether the EnvisaLink then
        sends that partition's %00 update has not been verified on hardware. A
        failed or unanswered request is not an error here: the keypad use that
        needs the report refuses, and says so, when none comes.
        """
        if not partitions or not self.client.connected:
            return
        order = sorted(partitions, reverse=True)
        if 1 not in order:
            order.append(1)
        try:
            for number in order:
                await self.client.change_default_partition(number)
        except TPIError, OSError:
            _LOGGER.debug("Partition report request failed", exc_info=True)

    def _unreported(self, partitions: Sequence[int]) -> list[int]:
        return [n for n in partitions if not self.data.partition(n).fresh]

    @staticmethod
    def _raise_report_pending(partition: int) -> None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="partition_report_pending",
            translation_placeholders={"partition": str(partition)},
        )

    async def _async_require_fresh_reports(self, partitions: Sequence[int]) -> None:
        """Have a fresh report of each partition, asking for what is missing.

        Waits a bounded time for the answers. A partition still silent is not
        taken as disarmed or as absent; the refusal names it.
        """
        missing = self._unreported(partitions)
        if not missing:
            return
        await self._async_request_partition_reports(missing)
        with contextlib.suppress(TimeoutError):
            async with asyncio.timeout(PARTITION_REPORT_TIMEOUT):
                while self._unreported(partitions):
                    self._partition_reported.clear()
                    await self._partition_reported.wait()
        still = self._unreported(partitions)
        if still:
            self._raise_report_pending(still[0])

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

    @override
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
        await self._await_mode_saved()

    @override
    async def _async_update_data(self) -> VistaState:
        # Push-driven: nothing to actively fetch. Listeners are refreshed
        # via async_set_updated_data() from _handle_event() as events arrive.
        return self.data

    @property
    def program_mode(self) -> ProgramMode:
        """Current state from the single owner."""
        return self._mode.mode

    @property
    def program_mode_changes(self) -> int:
        return self._mode.revision

    async def async_wait_for_program_mode(self, is_open: bool, timeout: float) -> bool:
        """Wait until the stored state says Program Mode is open, or closed."""
        target = ProgramMode.OPEN if is_open else ProgramMode.CLOSED
        try:
            async with asyncio.timeout(timeout):
                while self.program_mode is not target:
                    changed = asyncio.Event()
                    self._program_mode_changed = changed
                    try:
                        await changed.wait()
                    finally:
                        self._program_mode_changed = None
        except TimeoutError:
            return False
        return True

    def _transition(
        self,
        event: ModeEvent,
        *,
        operation_id: str | None = None,
        generation: str | None = None,
        revision: int | None = None,
        entry_complete: bool = False,
        holding: bool = False,
        installer: bool = False,
        everyday: bool = False,
        holder: Holder | None = None,
    ) -> None:
        """Apply the only state transition and publish its result."""
        if self._less_cautious_pending:
            if event is ModeEvent.REPAIR_CONFIRM:
                raise ModeRefusal(Refusal.STALE)
            self._pending_mode_events.append(
                lambda: self._transition(
                    event,
                    operation_id=operation_id,
                    generation=generation,
                    revision=revision,
                    entry_complete=entry_complete,
                    holding=holding,
                    installer=installer,
                    everyday=everyday,
                    holder=holder,
                )
            )
            return
        new = transition(
            self._mode,
            event,
            operation_id=operation_id,
            generation=generation,
            revision=revision,
            entry_complete=entry_complete,
            holding=holding,
            installer=installer,
            everyday=everyday,
            holder=holder,
        )
        if new == self._mode:
            return
        previous = self._mode_save_task
        less_cautious = (
            new.mode is ProgramMode.CLOSED and self._mode.mode is not ProgramMode.CLOSED
        )
        if less_cautious:
            self._less_cautious_pending = True
        else:
            self._mode = new
            self._sync_mode()

        async def save() -> None:
            if previous is not None:
                try:
                    await asyncio.shield(previous)
                except asyncio.CancelledError:
                    if not previous.done():
                        raise
                    # A cancelled predecessor cannot poison subsequent saves.
                except Exception:  # noqa: BLE001
                    _LOGGER.exception("Earlier Program Mode save failed")
            # Read back here, in the chain: a later save waits for this one, so
            # the store holds this record or a newer one, and a failure never
            # blocks the saves behind it.
            try:
                await self._mode_store.async_save(new.stored())
                stored = await self._mode_store.async_load()
            except asyncio.CancelledError:
                self._mode_save_error_revision = new.revision
                if less_cautious:
                    self._settle_less_cautious(new, verified=False)
                raise
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Could not save the Program Mode state")
                self._mode_save_error_revision = new.revision
                if less_cautious:
                    self._settle_less_cautious(new, verified=False)
                return
            verified = stored == new.stored() or (
                stored is not None and int(str(stored["revision"])) > new.revision
            )
            if verified:
                self._durable_revision = max(self._durable_revision, new.revision)
                self._mode_save_error_revision = None
            else:
                self._mode_save_error_revision = new.revision
            if less_cautious:
                self._settle_less_cautious(new, verified=verified)

        self._mode_save_task = self.hass.async_create_task(save())

    async def _await_mode_saved(self) -> None:
        while self._mode_save_task is not None:
            task = self._mode_save_task
            await asyncio.shield(task)
            if task is self._mode_save_task:
                return

    def _settle_less_cautious(self, new: ModeState, *, verified: bool) -> None:
        # A failed save still consumes its revision; queued panel events then
        # fold over the state that actually survived that save.
        self._mode = new if verified else replace(self._mode, revision=new.revision)
        self._less_cautious_pending = False
        self._sync_mode()
        pending, self._pending_mode_events = self._pending_mode_events, []
        for apply_pending in pending:
            apply_pending()

    def _sync_mode(self) -> None:
        """Mirror the authoritative state to the issue and entities."""
        mode = self._mode
        if mode.mode is ProgramMode.CLOSED or self._typing_holder is not None:
            ir.async_delete_issue(self.hass, DOMAIN, self.program_mode_issue_id)
        else:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                self.program_mode_issue_id,
                data={
                    "entry_id": self.entry.entry_id,
                    "generation": mode.generation,
                    "revision": mode.revision,
                    "saw_627": mode.saw_627,
                },
                is_fixable=True,
                is_persistent=True,
                issue_domain=DOMAIN,
                severity=ir.IssueSeverity.ERROR,
                translation_key=ISSUE_PROGRAM_MODE_UNKNOWN,
                translation_placeholders={"title": self.entry.title},
            )
        self.data.system.program_mode = mode.mode
        if self._program_mode_changed is not None:
            self._program_mode_changed.set()
        self.async_set_updated_data(self.data)

    @contextlib.asynccontextmanager
    async def async_keypad(
        self, partition: int, use: KeypadUse = KeypadUse.EVERYDAY
    ) -> AsyncIterator[HeldKeypad]:
        """Hold the keypad for one sequence on ``partition``, or refuse it.

        Every keystroke writer takes the keypad here. A partition above the
        entry's count is refused: nothing reports its state. Every key then
        passes _before_key at its write.
        """
        async with self.client.keypad() as type_keys:
            if not 1 <= partition <= self.num_partitions:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="partition_not_configured",
                    translation_placeholders={
                        "partition": str(partition),
                        "count": str(self.num_partitions),
                    },
                )
            keypad = HeldKeypad(self, partition, use, type_keys)
            self._keypad_holder = keypad
            try:
                if use is KeypadUse.EVERYDAY:
                    self._begin_everyday(keypad)
                    await self._async_require_fresh_reports([partition])
                else:
                    await self._async_begin_typing(keypad)
                yield keypad
            finally:
                # Finish under the keypad lock even if the caller is cancelled
                # again while a durable state transition is still pending.
                cleanup = self.hass.async_create_task(self._finish_keypad(keypad))
                cancelled = False
                while not cleanup.done():
                    try:
                        await asyncio.shield(cleanup)
                    except asyncio.CancelledError:
                        cancelled = True
                cleanup.result()
                if cancelled:
                    raise asyncio.CancelledError

    async def _finish_keypad(self, keypad: HeldKeypad) -> None:
        try:
            if self._typing_holder is keypad:
                try:
                    await self._await_mode_saved()
                    if keypad.attempted == 0:
                        await self._no_key_sent(keypad)
                finally:
                    self._transition(
                        ModeEvent.OPERATION_END,
                        operation_id=keypad.operation_id,
                    )
            elif keypad.use is KeypadUse.EVERYDAY:
                self._transition(
                    ModeEvent.OPERATION_END,
                    operation_id=keypad.operation_id,
                    everyday=True,
                )
        finally:
            try:
                if self._typing_holder is keypad:
                    self._typing_holder = None
                    self._sync_mode()
            finally:
                if self._keypad_holder is keypad:
                    self._keypad_holder = None

    def _begin_everyday(self, keypad: HeldKeypad) -> None:
        try:
            self._transition(
                ModeEvent.OPERATION_START,
                operation_id=keypad.operation_id,
                everyday=True,
            )
        except ModeRefusal as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="program_mode_not_closed",
            ) from err

    def _require_closed(self) -> None:
        if self.program_mode is not ProgramMode.CLOSED:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="program_mode_not_closed",
            )

    async def _async_begin_typing(self, keypad: HeldKeypad) -> None:
        """Raise the doubt for a guided or installer sequence and make it durable.

        A guided entry needs Program Mode closed and a fresh report of every
        partition, asked for before anything is raised so that a refusal leaves
        no doubt behind.
        """
        if keypad.use is KeypadUse.PROGRAMMING:
            self._require_closed()
            await self._async_require_fresh_reports(sorted(self.data.partitions))
            self._require_closed()
            self._require_disarmed(part_way=False)
        self._typing_holder = keypad
        was_closed = self.program_mode is ProgramMode.CLOSED
        self._transition(
            ModeEvent.OPERATION_START,
            operation_id=keypad.operation_id,
            installer=keypad.use is KeypadUse.INSTALLER,
        )
        if was_closed:
            keypad.raised_at = self.program_mode_changes
            keypad.raised_generation = self._mode.generation
        revision = self._mode.revision
        await self._await_mode_saved()
        if self._durable_revision < revision:
            await self._no_key_sent(keypad)
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="program_mode_storage_failed",
            )

    async def _no_key_sent(self, keypad: HeldKeypad) -> None:
        self._transition(
            ModeEvent.NO_KEY_SENT,
            operation_id=keypad.operation_id,
            generation=keypad.raised_generation,
        )
        await self._await_mode_saved()

    def _before_key(self, keypad: HeldKeypad) -> None:
        """Check session, report and mode immediately before every key write."""
        if (
            self._less_cautious_pending
            or keypad.session_revision != self._session_revision
            or self._session_released
            or not self.client.connected
        ):
            self._program_mode_lost()
        if not self.data.partition(keypad._partition).fresh:
            self._raise_report_pending(keypad._partition)
        mode = self.program_mode
        if keypad.use is KeypadUse.EVERYDAY:
            if mode is not ProgramMode.CLOSED:
                if keypad.written:
                    raise HomeAssistantError(
                        translation_domain=DOMAIN, translation_key="program_mode_opened"
                    )
                raise ServiceValidationError(
                    translation_domain=DOMAIN, translation_key="program_mode_not_closed"
                )
        elif keypad.use is KeypadUse.PROGRAMMING and keypad.opened_at is None:
            if (
                mode is not ProgramMode.DOUBT
                or self._mode.operation_id != keypad.operation_id
                or self.program_mode_changes != keypad.raised_at
            ):
                self._program_mode_lost()
        elif keypad.use is KeypadUse.PROGRAMMING and (
            mode is not ProgramMode.OPEN
            or self.program_mode_changes != keypad.opened_at
            or self._mode.operation_id != keypad.operation_id
        ):
            self._program_mode_lost()
        # KEY_WRITE below checks the installer's operation binding.
        if keypad.use is KeypadUse.PROGRAMMING:
            self._require_disarmed(part_way=keypad.written > 0)
        try:
            transition(
                self._mode,
                ModeEvent.KEY_WRITE,
                operation_id=keypad.operation_id
                if keypad.use is not KeypadUse.EVERYDAY
                else None,
                entry_complete=keypad.opened_at is not None,
                installer=keypad.use is KeypadUse.INSTALLER,
            )
        except ModeRefusal:
            self._program_mode_lost()
        keypad.attempted = keypad.written + 1

    def _bind_open_program_mode(self, keypad: HeldKeypad) -> None:
        # The entry's own 627 is the one change after the doubt its first key
        # raised; anything between, a dropped session included, is not its own.
        if (
            self.program_mode is not ProgramMode.OPEN
            or keypad.raised_at is None
            or self._mode.operation_id != keypad.operation_id
        ):
            self._program_mode_lost()
        # The owner can only be bound by its own complete entry; the next
        # key gate checks the session and this OPEN revision again.
        keypad.opened_at = self.program_mode_changes

    @staticmethod
    def _program_mode_lost() -> None:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="program_mode_lost",
            translation_placeholders={"seconds": str(PROGRAM_MODE_REPORT_TIMEOUT)},
        )

    def _require_disarmed(self, *, part_way: bool) -> None:
        """Refuse while any tracked partition is armed or arming, or unreported.

        The keypad would take the entry as a user code, and Program Mode
        governs the whole panel, not one partition.
        """
        for number, state in sorted(self.data.partitions.items()):
            if not state.fresh:
                self._raise_report_pending(number)
            if state.armed or state.exit_delay:
                placeholders = {"partition": str(number)}
                if part_way:
                    raise HomeAssistantError(
                        translation_domain=DOMAIN,
                        translation_key="partition_armed_part_way",
                        translation_placeholders=placeholders,
                    )
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="partition_armed",
                    translation_placeholders=placeholders,
                )

    async def async_confirm_program_mode_closed(
        self, generation: str, revision: int
    ) -> None:
        """Accept only the exact doubt the repair was opened for, while idle.

        Raises ModeRefusal; its reason says which of held, settled or stale.
        """
        self._transition(
            ModeEvent.REPAIR_CONFIRM,
            generation=generation,
            revision=revision,
            holding=self._keypad_holder is not None,
        )
        await self._await_mode_saved()
        if self._mode_save_error_revision == revision + 1:
            raise ModeRefusal(Refusal.STORAGE_FAILED)
        if (
            self._mode.mode is not ProgramMode.CLOSED
            or self._mode.revision != revision + 1
            or self._durable_revision < revision + 1
        ):
            raise ModeRefusal(Refusal.STALE)

    def _handle_event(self, event: TPIEvent) -> None:
        if event.code == "%00":
            invalid = invalid_keypad_field(event)
            if invalid is not None:
                field, length = invalid
                self.rejected_keypad_updates[field] = (
                    self.rejected_keypad_updates.get(field, 0) + 1
                )
                now = time.monotonic()
                last = self._last_keypad_rejection_warning.get(field)
                if last is None or now - last >= 60:
                    _LOGGER.warning(
                        "Rejected %%00 keypad update: invalid %s (length %d)",
                        field,
                        length,
                    )
                    self._last_keypad_rejection_warning[field] = now
                return
        self.last_event = event
        apply_event(self.data, event)
        report = program_mode_report(event, self.num_partitions)
        if report is ProgramModeReport.OPENED:
            holder = self._typing_holder
            self._transition(
                ModeEvent.OPEN_REPORT,
                holder=holder.holder() if holder is not None else None,
            )
        elif report is ProgramModeReport.CLOSED:
            self._transition(ModeEvent.CLOSE_REPORT)
        elif report is ProgramModeReport.ARMED:
            self._transition(
                ModeEvent.ARMED_REPORT, holding=self._keypad_holder is not None
            )
        elif event.code == "%00":
            self._transition(ModeEvent.DISARMED_REPORT)
        if event.code == "%00":
            # apply_event made the reported partition fresh.
            self._partition_reported.set()
        self.async_set_updated_data(self.data)

    def _handle_disconnect(self, error: Exception | None) -> None:
        self._session_revision += 1
        self.data.system.connected = False
        self.data.forget_partition_reports()
        self._transition(ModeEvent.DISCONNECT)
        if self._shutting_down or self._session_released:
            # Deliberate: the entry is going away, or the reconfigure flow is
            # borrowing the module's one session and will hand it back.
            return
        # Once per outage; the retries below log at debug and the recovery
        # is logged once when it happens.
        _LOGGER.info(
            "Lost the connection to the Envisalink at %s: %s", self._host, error
        )
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
                    _LOGGER.debug(
                        "Envisalink Field Programmer reconnect attempt failed: %s", err
                    )
                    self._failed_reconnects += 1
                    if self._failed_reconnects == RECONNECT_FAILURES_BEFORE_ISSUE:
                        self._async_raise_connection_issue()
                    self._backoff = min(self._backoff * 2, RECONNECT_BACKOFF_MAX)
                    continue
                self._failed_reconnects = 0
                self._backoff = RECONNECT_BACKOFF_MIN
                _LOGGER.info("Reconnected to the Envisalink at %s", self._host)
                await self._async_session_established(fold=ModeEvent.RECONNECT)
                return
        except asyncio.CancelledError:
            raise

    # -- High level actions used by entity platforms -----------------------

    async def async_arm_away(self, partition: int, code: str) -> None:
        await self._async_send_arm_disarm_keystrokes(
            partition, f"{self._user_code(code)}2"
        )

    async def async_arm_stay(self, partition: int, code: str) -> None:
        await self._async_send_arm_disarm_keystrokes(
            partition, f"{self._user_code(code)}3"
        )

    async def async_arm_night(self, partition: int, code: str) -> None:
        await self._async_send_arm_disarm_keystrokes(
            partition, f"{self._user_code(code)}33"
        )

    async def async_disarm(self, partition: int, code: str) -> None:
        await self._async_send_arm_disarm_keystrokes(
            partition, f"{self._user_code(code)}1"
        )

    def _user_code(self, code: str) -> str:
        """The code as one keypad user code, or a refusal before anything is sent.

        Anything longer reaches other keypad functions: on a VISTA the master
        code followed by 8 and a user number changes a user code.
        """
        pattern = (
            _DSC_USER_CODE
            if self.dialect.family is PanelFamily.DSC_POWERSERIES
            else _USER_CODE
        )
        if not pattern.fullmatch(code):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_user_code",
            )
        return code

    async def _async_send_arm_disarm_keystrokes(
        self, partition: int, keys: str
    ) -> None:
        """Arm/disarm by typing the user code + mode digit(s), like a real keypad.

        Routed through the same guardrail as every other keystroke send
        (see programming.py) for defense in depth, even though a plain
        code+digit sequence is extremely unlikely to collide with the
        Program Mode trigger pattern it guards against.
        """
        from .programming import async_send_guarded_keystrokes  # avoid import cycle

        await async_send_guarded_keystrokes(self, partition, keys)

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
        await async_send_guarded_keystrokes(self, zone.partition, keys)
        zone.bypassed = not zone.bypassed
        self.async_set_updated_data(self.data)

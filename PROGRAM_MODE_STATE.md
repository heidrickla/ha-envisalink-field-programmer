# Program Mode state

The coordinator owns one state value. `CLOSED` permits ordinary keys. `OPEN` means Contact ID 627 was seen; it has the current guided operation's id only when that operation's entry caused the report. `DOUBT` has a generation, the operation id if one holds the keypad, and `saw_627`, which records whether any 627 arrived since this doubt began. Neither an issue deletion nor a reconnect is evidence that the panel left Program Mode.

The state transition function takes every event. A change also advances a revision used by each key gate. An operation receives a unique id; its entry keys require its own unchanged doubt, and its menu keys require its own unchanged `OPEN`. A `627` before the final entry key is sent cannot bind to that operation; the final acknowledgement may follow the report. Every write, including an overrun retry, rechecks the gate under the command lock. A `00` acknowledgement increments the count of keys accepted by the module.

| Event | CLOSED | OPEN | DOUBT |
|---|---|---|---|
| Operation start | Guided or installer: create a new doubt generation with operation id; ordinary: unchanged | Refuse guided or ordinary; installer keeps the unsafe state and binds its id | Refuse guided or ordinary; installer keeps the unsafe state and binds its id |
| Key write | Ordinary allowed; guided requires its own durable doubt first | Guided menu keys require the operation whose 627 opened this state and an unchanged revision; confirmed installer keys require their active holder | Guided entry keys require the operation that raised this doubt and an unchanged revision; confirmed installer keys require their active holder |
| Key refused by the module | Unchanged | Unchanged | The originating operation's first key may return to `CLOSED` only when no key was acknowledged and no 627 was seen; an acknowledged prefix keeps the doubt |
| 627 | New `OPEN` with no operation owner | New `OPEN`, invalidating a prior binding | `OPEN` for the holder only if its entry is complete; otherwise `OPEN` without a bound owner; `saw_627=true` |
| 628 | `CLOSED` with a new revision | `CLOSED` | `CLOSED` |
| Armed report for a tracked partition | Unchanged | Unchanged | `CLOSED` only if `saw_627=false` and no operation holds the keypad |
| Disarmed report | Unchanged | Unchanged | Unchanged |
| Disconnect | Unchanged state, new revision; all partitions become unknown | `DOUBT` with `saw_627=true`, new revision; all partitions become unknown | Preserve generation, operation id, and `saw_627`; new revision; all partitions become unknown |
| Reconnect | Unchanged state, new revision; partitions remain unknown until their own fresh reports | Treat as disconnect before reconnect | Unchanged state, new revision; partitions remain unknown until their own fresh reports |
| Reload or restart | Restore durable state; all partitions unknown | Restore as `DOUBT`, preserving `saw_627` | Restore generation and `saw_627`; old operation id cannot authorize new keys |
| Repair confirm | Refused as stale | `CLOSED` only if idle and the generation matches | `CLOSED` only if no operation holds the keypad and the flow's generation equals the current generation; otherwise abort with a readable reason |
| Operation end | Unchanged | A guided or installer operation becomes `DOUBT` with `saw_627=true` unless 628 arrived; an ordinary operation leaves `OPEN` | A guided or installer operation clears its id but preserves generation and `saw_627`; an ordinary operation leaves `DOUBT` |

The doubt and its generation and `saw_627` are saved in the integration's own Home Assistant storage before the first key, with that save awaited before the key phase. The repair issue mirrors them for display and carries the generation captured by its confirm flow. An active operation's doubt appears in the System trouble diagnostic as installers_mode, not as an ERROR repair; if it ends in doubt, the ERROR repair appears. The repair registry's delayed save is never the safety store. A stale flow or a flow submitted while the keypad is held aborts and leaves doubt intact.

After any disconnect or reload, each partition's arm state is unknown until its first fresh panel report. Guided entry refuses an unknown partition with a waiting-for-panel-report message. A disarm or arm is also held while Program Mode is in doubt. A user may settle an ended doubt by checking the physical keypad, leaving Program Mode with `*99` if necessary, and confirming the current repair. A later 628 settles it automatically.

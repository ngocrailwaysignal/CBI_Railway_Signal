# CBI Railway Signal System Architecture

This document describes the current architecture of the `CBI_Railway_Signal` application based on the actual codebase.

The goals of this document are to clarify:
- the boundaries between packages;
- the data flow from layout -> runtime -> journal -> SmartIO;
- the responsibility of each major component;
- the dependency rules that should remain stable as the system evolves.

The system is currently split into the following major blocks:
- `core/`: interlocking rules, domain models, compiler, and pure runtime engines.
- `runtime_session/`: a stateful local runtime session, runtime-facing read model, snapshot restore, and runtime mutation boundary.
- `simulation/`: pure simulation behavior such as train lifecycle and time-stepped execution.
- `products/generic_application/`: application-level orchestration, command journaling, checkpoints, and recovery.
- `integrations/smartio/`: SmartIO communication over WebSocket and envelope <-> runtime command translation.
- `products/specific_application/`: station-specific layout and editor logic.
- `ui/`: UI orchestration, operating modes, and user-to-service integration.

## 1. Architecture Overview

The system can be understood as four main layers:

1. Pure domain/runtime logic layer:
   `core/domain`, `core/runtime`, `core/compiler`, `core/application/use_cases`
2. Stateful runtime session layer:
   `runtime_session`
3. Pure simulation behavior layer:
   `simulation`
4. Application orchestration and realtime persistence layer:
   `products/generic_application`
5. External integration and presentation layer:
   `integrations/smartio`, `ui`, `products/specific_application`

The main system flow is:

```text
User / SmartIO Web
        |
        v
UI Controllers / SmartIO Coordinator
        |
        v
RuntimeWorkspaceService  <---->  RuntimeJournal / Recovery
        |
        v
RuntimeSession
        |
        v
SimulationEngine
        |
        v
RouteDispatcher / LockingEngine / SafetyMonitor
        |
        v
RailwayTopology + Route + Train
```

## 2. Bounded Contexts and Responsibilities

### 2.1 `layout_context`

Primary responsibilities:
- creating, editing, and validating the station layout;
- managing static topology before entering runtime;
- providing layout data for the UI and SmartIO snapshots.

Related modules:
- `products/specific_application/editor_service.py`
- `products/specific_application/station_layout.py`
- `ui/views/canvas_editor_view.py`
- `core/domain/model/topology.py`
- `core/application/serialization/layout_payload_serializer.py`

Inputs/Outputs:
- input: canvas editor actions, `layout.json`;
- output: `RailwayTopology`, layout payload for web/runtime.

### 2.2 `interlocking_compile_context`

Primary responsibilities:
- compiling topology into a deterministic interlocking specification;
- generating route candidates and conflict/flank/overlap rules;
- producing artifacts that can be saved and loaded later.

Related modules:
- `core/compiler/route_compiler.py`
- `core/compiler/interlocking_table.py`
- `core/compiler/spec_models.py`
- `products/generic_application/service.py`

Inputs/Outputs:
- input: `RailwayTopology`, overlap parameters;
- output: `InterlockingSpec`, interlocking table rows, `interlocking_spec.json`.

### 2.3 `runtime_control_context`

Primary responsibilities:
- setting routes, cancelling routes, emergency releasing routes;
- enforcing interlocking on sections, points, and signals;
- updating occupancy, timed release, and approach locking;
- monitoring safety and triggering fail-safe STOP when necessary.

Related modules:
- `core/runtime/route_engine.py`
- `core/runtime/route_dispatcher.py`
- `core/runtime/locking_engine.py`
- `core/runtime/occupancy_reconciler.py`
- `core/runtime/safety_monitor.py`
- `core/runtime/timed_release.py`
- `core/runtime/sequence_locking.py`
- `core/domain/lifecycle/approach_locking.py`

Critical rules:
- runtime does not allow direct external writes to `locked_by`, `signal.aspect`, or `signal.route_id`;
- every state mutation must go through a validated command boundary;
- when unsafe conditions are detected, all signals are forced to STOP.

### 2.4 `simulation_workspace_context`

Primary responsibilities:
- driving pure simulation behavior for the active runtime session;
- creating/updating trains and advancing simulation ticks;
- hydrating simulation-facing state through the runtime session boundary;
- delegating on the mutable runtime session instead of owning it.

Related modules:
- `simulation/engine.py`
- `simulation/train_lifecycle.py`
- `simulation/snapshot_hydrator.py`
- `runtime_session/session.py`
- `runtime_session/read_model.py`

Architectural meaning:
- `RuntimeSession` is the single stateful runtime session inside the desktop app;
- `SimulationEngine` is a collaborator that advances train movement and time-stepped behavior;
- `runtime_session/` is the execution layer for runtime use cases in `products/generic_application`.

### 2.5 `runtime_orchestration_context`

Primary responsibilities:
- managing the runtime session lifecycle for the active workspace;
- receiving commands from the UI or SmartIO, journaling them, executing them, and generating events;
- creating checkpoint snapshots and restoring on restart;
- providing runtime health to the UI and transport layer.

Related modules:
- `products/generic_application/runtime_workspace_service.py`
- `products/generic_application/runtime_realtime.py`
- `products/generic_application/profile.py`

Architectural meaning:
- `RuntimeWorkspaceService` is the central runtime facade;
- it decides which commands are journaled, which events are emitted, and when checkpoints are created;
- `RuntimeSession` does not write journals by itself, and the UI is not allowed to mutate runtime state directly.

### 2.6 `integration_context`

Primary responsibilities:
- connecting to the SmartIO system over WebSocket;
- validating envelopes, parsing messages, and retrying connections;
- translating SmartIO events into typed runtime commands;
- sending `command_result`, `runtime_event`, and `runtime_snapshot` outward.

Related modules:
- `integrations/smartio/protocol.py`
- `integrations/smartio/runtime_bridge.py`
- `integrations/smartio/qt_ws_client.py`
- `ui/controllers/runtime_workspace_controller.py`

Architectural meaning:
- SmartIO does not directly manipulate topology or the locking engine;
- all changes still go through `RuntimeWorkspaceService.submit_command(...)`;
- the bridge is responsible only for protocol normalization and error mapping to `SmartIOProtocolError`.

### 2.7 `presentation_context`

Primary responsibilities:
- managing Design / Simulation / Runtime modes;
- binding user actions to the application and runtime services;
- presenting the read model, runtime health, and SmartIO status.

Related modules:
- `ui/controllers/main_window_controller.py`
- `ui/controllers/runtime_workspace_controller.py`
- `ui/controllers/workspace_state_coordinator.py`
- `ui/presenters/route_presenter.py`
- `ui/views/main_window_view.py`
- `ui/views/canvas_editor_view.py`

## 3. Core Components

### 3.1 `RailwayTopology`

`RailwayTopology` is the foundational station model.

It manages:
- graph nodes and edges;
- signals, sections, and points;
- topology-related validations;
- JSON import/export.

Topology is used throughout design, compile, simulation, runtime, and serialization.

It is the structural source of truth for the system.

### 3.2 `RuntimeSession`

`runtime_session/session.py` defines the `RuntimeSession` class, which is the stateful runtime session.

In `__post_init__`, it initializes:
- `RouteEngine`
- `LockingEngine`
- `RouteDispatcher`
- `OccupancyReconciler`
- `SafetyMonitor`
- `RuntimeCommandHandler`
- `RuntimeTrainLifecycle`
- `RuntimeSnapshotHydrator`
- `SimulationEngine`

`RuntimeSession` exposes a high-level runtime interface:
- `set_route(...)`
- `cancel_route(...)`
- `set_section_occupied(...)`
- `set_point_position(...)`
- `upsert_train(...)`
- `remove_train(...)`
- `hydrate_snapshot(...)`
- `step()`

`step()` delegates pure simulation behavior to `SimulationEngine`, which is responsible for:
- incrementing `tick`;
- updating time locking before and after train movement;
- moving each train on its active route;
- running `SafetyMonitor.detect_unsafe_conditions(...)`;
- raising fail-safe behavior and throwing `RuntimeError` on unsafe conditions.

### 3.3 `RuntimeWorkspaceService`

`products/generic_application/runtime_workspace_service.py` is the runtime facade for the entire desktop app.

Primary responsibilities:
- ensuring the runtime session exists via `ensure_session(topology)`;
- submitting commands with an idempotency key (`source_id`, `command_id`);
- appending to `runtime_commands.jsonl`;
- executing commands;
- generating `RuntimeEvent` and appending to `runtime_events.jsonl`;
- checkpointing snapshots into `runtime_snapshots.jsonl`;
- restoring the session from snapshots plus event replay;
- tracking `RuntimeHealth`.

Architectural role:
- the transaction boundary for runtime commands;
- an anti-corruption layer between UI/transport and the runtime session;
- the place that owns `stream_seq` for a lightweight event-sourcing model.

### 3.4 `RuntimeJournal` and `RuntimeRecoveryService`

`products/generic_application/runtime_realtime.py` contains the realtime primitives:
- `RuntimeCommand`
- `RuntimeEvent`
- `RuntimeCommandResult`
- `RuntimeHealth`
- `RuntimeJournal`
- `RuntimeRecoveryService`

`RuntimeJournal` is an append-only JSONL store:
- `runtime_commands.jsonl`
- `runtime_events.jsonl`
- `runtime_snapshots.jsonl`

Important properties:
- it can truncate an invalid tail when reading partially written JSONL files;
- it stores commands and events separately;
- snapshots do not replace events; they only act as checkpoints for faster restore.

`RuntimeRecoveryService.restore(...)` performs:
1. load the latest snapshot;
2. compare `topology_revision`;
3. hydrate the session from the snapshot;
4. replay events with `command_status == "applied"` after the snapshot `stream_seq`.

If the topology revision mismatches or replay fails:
- the session is marked as `degraded`;
- the runtime may be forced into a fail-safe STOP state.

## 4. Main Operational Flows

### 4.1 From Layout to Runtime

1. The UI/editor creates or modifies `RailwayTopology`.
2. `GenericApplicationService` loads/saves topology and can compile the spec.
3. When entering Simulation/Runtime, `RuntimeWorkspaceService.ensure_session(topology)` creates `RuntimeSession`.
4. The session may be restored from checkpoints and the event journal.
5. The UI receives `RuntimeViewState` for rendering.

### 4.2 Setting a Route from the UI

```text
UI action
-> RuntimeWorkspaceService.submit_command(kind="set_route")
-> SetOrReuseRouteUseCase
-> RuntimeSession.set_route(...)
-> RouteDispatcher + LockingEngine
-> RuntimeEvent(applied/rejected)
-> checkpoint snapshot if interval reached
-> UI refresh RuntimeViewState
```

The result of the command is more than just the route:
- it also creates an audit event;
- it updates the stream sequence;
- it may create a new snapshot;
- it is cached to avoid reprocessing duplicate commands.

### 4.3 Step Runtime

`step_runtime` is the command that advances the simulation cycle.

It:
- is journaled like any other command;
- calls `RuntimeSession.step()`;
- returns a new `RuntimeViewState` and `tick`;
- rejects the command and records the error message in the event if a safety issue occurs.

### 4.4 Manual Override / Occupancy Update

The system allows controlled updates:
- `set_section_occupied`
- `set_point_position`
- `upsert_train`
- `remove_train`
- `apply_state_update`

But direct writes into interlocking-controlled fields are blocked:
- `locked_by` cannot be set directly;
- `signal.aspect` cannot be set directly;
- `signal.route_id` cannot be set directly.

This ensures:
- interlocking logic remains centralized in the engine;
- the transport layer cannot break safety invariants.

## 5. SmartIO Integration

### 5.1 `SmartIOWebSocketClient`

`integrations/smartio/qt_ws_client.py` is the Qt WebSocket adapter.

Main functions:
- opening and closing the connection;
- reconnect backoff;
- parsing text JSON;
- validating the envelope schema.

The normalized envelope format is:

```json
{
  "type": "command | state_update | runtime_snapshot | runtime_event | command_result | hello | error | ack",
  "payload": {},
  "ts": 0
}
```

It emits the following Qt signals:
- `event_received`
- `status_changed`
- `error_occurred`

It contains no interlocking logic.

### 5.2 `SmartIORuntimeBridge`

`integrations/smartio/runtime_bridge.py` performs three main tasks:
- converting `command` envelopes into runtime commands;
- converting `state_update` envelopes into the `apply_state_update` command;
- validating dangerous payloads and raising `SmartIOProtocolError`.

Typical mappings:
- `command(type=signal, action=set_aspect, value=PROCEED)` -> `set_route`
- `command(type=signal, action=set_aspect, value=STOP)` -> `cancel_route`
- `command(type=point, action=set_position)` -> `set_point_position`
- `state_update` -> `apply_state_update`

The bridge also supports:
- resolving routes by `route_id` or by the `entry_signal/exit_signal` pair;
- ignoring stale train `route_id` values when the route has already been auto-released by CBI;
- blocking direct state writes into sensitive fields.

### 5.3 `SmartIORuntimeCoordinator`

`ui/controllers/runtime_workspace_controller.py` owns the SmartIO connection lifecycle in the UI layer.

Responsibilities:
- creating the `SmartIOWebSocketClient`;
- deciding which modes are allowed to keep the connection alive;
- sending `hello` after connection;
- receiving socket events and mapping them to `RuntimeWorkspaceService.submit_command(...)`;
- sending back `command_result`;
- publishing pending `runtime_event` messages and `runtime_snapshot` on a heartbeat;
- aggregating `runtime_health`.

Current operating rules:
- Runtime mode: accepts transport commands and publishes snapshots;
- Simulation mode: only keeps the connection if the endpoint is local (`localhost`/`127.0.0.1`);
- outside valid modes, SmartIO commands are rejected.

## 6. Data and Artifacts

### 6.1 Design Artifacts

- `layout.json`: the static station topology.
- `interlocking_spec.json`: the compiled route/conflict/flank/overlap result.

### 6.2 Runtime Artifacts

- `runtime_snapshot.json`: a standalone runtime state snapshot.
- `runtime_commands.jsonl`: the append-only command journal.
- `runtime_events.jsonl`: the append-only event audit log.
- `runtime_snapshots.jsonl`: the append-only checkpoint snapshot stream.

### 6.3 Important Metadata Fields

Runtime snapshots and events carry:
- `stream_seq`: the event order in the runtime stream;
- `topology_revision`: the fingerprint of the current topology;
- `snapshot_version`: the snapshot schema version.

Purpose:
- enabling safe recovery;
- preventing replay of events from a different topology;
- supporting debugging and synchronization with external clients.

## 7. Recovery and Health Model

The system treats the CBI desktop application as the highest-authority runtime node.

Principles:
- every accepted command is journaled;
- every processed command generates a `RuntimeEvent`;
- snapshots are treated as derived state, not the original source of truth;
- on restart, the system restores from the latest snapshot and then replays applied events.

`RuntimeHealth` tracks:
- `topology_revision`
- `stream_seq`
- `last_applied_command_at`
- `last_snapshot_at`
- `last_command_id`
- `last_command_status`
- `degraded_reason`

The `degraded` state can appear when:
- the checkpoint revision does not match;
- recovery fails;
- transport heartbeat/snapshot becomes stale in Runtime mode.

## 8. Folder Structure

```text
core/
  application/
    dto/
    mode_policy/
    serialization/
    use_cases/
  compiler/
  domain/
    lifecycle/
    model/
    policy/
  infrastructure/
    clocks/
    persistence/
  runtime/

runtime_session/
  command_gateway.py
  read_model.py
  session.py

simulation/
  engine.py
  snapshot_hydrator.py
  train_lifecycle.py

products/generic_application/
  profile.py
  runtime_realtime.py
  runtime_workspace_service.py
  service.py

integrations/
  smartio/
    protocol.py
    qt_ws_client.py
    runtime_bridge.py

products/specific_application/
  editor_service.py
  station_layout.py

ui/
  controllers/
  presenters/
  views/
```

## 9. Dependency Rules

### 9.1 `core/*`

- must not depend on `ui/*`, `runtime_session/*`, `simulation/*`, or `integrations/*`;
- contains logic that can be tested independently;
- defines domain models, runtime rules, compiler logic, and use cases.

### 9.2 `simulation/*`

- may depend on `core/domain/*`, `core/runtime/*`, and `runtime_session/*`;
- should not contain UI or transport logic;
- is the home of pure simulation behavior.

### 9.3 `products/generic_application/*`

- may use `core/*`, `runtime_session/*`, `simulation/*`, and `products/generic_product/*`;
- is the orchestration and persistence workflow layer;
- should not contain widget or UI code.

### 9.4 `integrations/*`

- should communicate only with application-level services and ports;
- must not directly manipulate `LockingEngine` internals through raw state mutation;
- every interaction must pass through the protocol and command boundary.

### 9.5 `ui/*`

- may depend on `products/specific_application/*`, `products/generic_application/*`, `runtime_session/*`, and `integrations/*`;
- should focus on orchestration and presentation;
- should not place interlocking rules inside controllers or views.

## 10. Extension Guidelines

1. Add new commands through `RuntimeWorkspaceService.submit_command(...)` instead of mutating state directly.
2. If a command has business meaning, place the logic in `core/application/use_cases` or `core/runtime`.
3. If state can no longer be restored from older events, bump `snapshot_version` and update the hydrator.
4. External integrations should go through an anti-corruption layer similar to `SmartIORuntimeBridge`.
5. New safety rules must be enforced in the engine/monitor, not in the UI.

## 11. Summary

The current `CBI_Railway_Signal` architecture revolves around a stateful runtime session (`RuntimeSession`) wrapped by an orchestration layer with journaling and recovery (`RuntimeWorkspaceService`).

`core/` holds pure interlocking and compiler logic; `runtime_session/` holds mutable runtime state and the runtime-facing read model; `simulation/` holds pure simulation behavior; `products/generic_application/` owns the command stream, checkpoints, and recovery; `integrations/smartio/` owns the external transport protocol; `ui/` mainly orchestrates and presents.

This separation helps the system:
- preserve safety invariants;
- support runtime auditing and recovery;
- make external integrations easier to extend;
- prevent domain logic from leaking into the UI or transport layer.

# Hybrid CBI Architecture

The project now separates interlocking logic, local runtime simulation, runtime journal/recovery, and SmartIO integration into distinct packages:
- `core/`: pure interlocking/domain/compiler/runtime services.
- `simulation/`: stateful local runtime session and UI read model.
- `generic_application/`: runtime workspace orchestration, command dispatch, journal, and recovery.
- `integrations/smartio/`: SmartIO protocol bridge and Qt WebSocket adapter.

## Bounded Contexts

### 1) `layout_context`
Responsibility:
- Edit and validate topology/configuration.

Key modules:
- `specific_application/editor_service.py`
- `specific_application/station_layout.py`
- `ui/views/canvas_editor_view.py`

### 2) `interlocking_compile_context`
Responsibility:
- Compile `layout.json` into deterministic `interlocking_spec.json`.

Key modules:
- `core/compiler/route_compiler.py`
- `core/compiler/spec_models.py`

### 3) `runtime_control_context`
Responsibility:
- Route set/cancel/release, lifecycle transitions, occupancy reconcile, and fail-safe monitoring.

Key modules:
- `core/runtime/route_dispatcher.py`
- `core/runtime/occupancy_reconciler.py`
- `core/runtime/safety_monitor.py`
- `core/runtime/locking_engine.py`

### 4) `simulation_workspace_context`
Responsibility:
- Own one local runtime session, train lifecycle, snapshot hydrate/replay, and build read-only runtime state for UI.
- Recover authoritative runtime state from checkpoint + event journal.

Key modules:
- `simulation/session.py`
- `simulation/train_lifecycle.py`
- `simulation/snapshot_hydrator.py`
- `simulation/read_model.py`
- `generic_application/runtime_workspace_service.py`
- `generic_application/runtime_realtime.py`

### 5) `integration_context`
Responsibility:
- Translate SmartIO envelopes to runtime commands, manage WebSocket connectivity, and publish runtime events/snapshots.

Key modules:
- `integrations/smartio/runtime_bridge.py`
- `integrations/smartio/qt_ws_client.py`
- `ui/controllers/runtime_workspace_controller.py`

### 6) `presentation_context`
Responsibility:
- GUI orchestration for Design / Simulation / Runtime modes.

Key modules:
- `ui/controllers/main_window_controller.py`
- `ui/views/main_window_view.py`
- `ui/views/canvas_editor_view.py`
- `ui/presenters/route_presenter.py`

## Folder Structure

```text
core/
  domain/
    model/
    policy/
    lifecycle/
  application/
    use_cases/
    dto/
    mode_policy/
  compiler/
  runtime/
  infrastructure/
    persistence/
    clocks/

simulation/
  session.py
  command_gateway.py
  train_lifecycle.py
  snapshot_hydrator.py
  read_model.py

integrations/
  smartio/
    protocol.py
    runtime_bridge.py
    qt_ws_client.py
```

## Data Artifacts

- `layout.json`: static design topology.
- `interlocking_spec.json`: compiled route/conflict/flank/overlap spec.
- `runtime_snapshot.json`: runtime state snapshot (occupancy, locks, active routes, trains, signals).
- `runtime_commands.jsonl`: append-only command journal for runtime mutations.
- `runtime_events.jsonl`: append-only applied/rejected runtime event audit log.
- `runtime_snapshots.jsonl`: checkpoint snapshots with `stream_seq` and `topology_revision`.

Persistence adapters:
- `core/infrastructure/persistence/interlocking_spec_repository.py`
- `core/infrastructure/persistence/runtime_snapshot_repository.py`

## Application Layer

- `generic_application/service.py` remains the topology/compiler/persistence facade.
- `generic_application/runtime_workspace_service.py` owns local runtime session lifecycle, validated command dispatch, checkpointing, and runtime health.
- `generic_application/runtime_realtime.py` provides append-only journal and restore/replay primitives.
- `ui/controllers/main_window_controller.py` and `ui/controllers/runtime_workspace_controller.py` adapt UI intents to application/runtime services.

## Realtime Model

- CBI desktop is the single authoritative runtime node.
- External/Web changes arrive as validated runtime commands.
- Every processed command is journaled and produces one command result plus one runtime event audit record.
- Runtime snapshots are derived checkpoints tagged with `snapshot_version`, `stream_seq`, and `topology_revision`.
- Recovery restores from the latest checkpoint and replays later applied events.

## Dependency Direction Rules

- `ui/*` may depend on `specific_application/*`, `generic_application/*`, `simulation/*`, and `integrations/*` via controllers/services.
- `generic_application/*` may depend on `core/*`, `simulation/*`, and `generic_product/*`.
- `simulation/*` may depend on `core/domain/*` and `core/runtime/*` services.
- `integrations/*` may depend on `simulation/*` and application/runtime ports.
- `core/*` must not depend on `ui/*`, `simulation/*`, or `integrations/*`.
- `generic_product/*` should remain UI-agnostic and station-agnostic.

# Hybrid CBI Architecture

The project follows a hybrid model:
- **Design-time** is route-oriented: compile layout into interlocking routes, conflict matrix, flank and overlap requirements.
- **Runtime** is geographical/state-driven: lock/release follows live occupancy, approach-lock state, timers, and fail-safe monitoring.

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
- Route set/cancel/release, lifecycle transitions, occupancy reconcile, and safety monitor.

Key modules:
- `core/runtime/route_dispatcher.py`
- `core/runtime/occupancy_reconciler.py`
- `core/runtime/safety_monitor.py`
- `core/locking_engine.py`
- `core/simulation.py`

### 4) `presentation_context`
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
```

```text
ui/
  controllers/
  views/
  presenters/
```

## Data Artifacts

- `layout.json`: static design topology.
- `interlocking_spec.json`: compiled route/conflict/flank/overlap spec.
- `runtime_snapshot.json`: runtime state snapshot (occupancy, locks, active routes, trains, signals).

Persistence adapters:
- `core/infrastructure/persistence/interlocking_spec_repository.py`
- `core/infrastructure/persistence/runtime_snapshot_repository.py`

## Application Layer

`generic_application/service.py` is the facade called by UI and exposes:
- route set/reuse, cancel, simulation start use-cases
- manual occupancy override use-case
- mode policy for 3 UI modes
- compile/load/save interlocking spec
- build/load/save runtime snapshot

## Runtime Decomposition Notes

- `core/runtime/simulation.py` remains the public runtime orchestration API.
- Internal collaborators are split into focused modules:
  - `core/runtime/command_handler.py`
  - `core/runtime/train_lifecycle.py`
  - `core/runtime/snapshot_hydrator.py`
- `core/runtime/locking_engine.py` keeps public behavior while delegating internals to:
  - `core/runtime/sequence_locking.py`
  - `core/runtime/timed_release.py`

## Dependency Direction Rules

- `ui/*` may depend on `specific_application/*`, `generic_application/*`, and `core/application/*`.
- `core/application/*` may depend on `core/domain/*`, `core/runtime/*`, `core/compiler/*`, and `core/infrastructure/*`.
- `core/domain/*` must not depend on `ui/*` or `specific_application/*`.
- `core/infrastructure/*` must not depend on `ui/*`.
- `generic_product/*` should remain UI-agnostic and station-agnostic.

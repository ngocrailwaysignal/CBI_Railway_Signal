# CBI Railway Signal

Desktop application for CBI interlocking simulation, station layout editing, and runtime orchestration.

## What This Project Does

`CBI_Railway_Signal` is a desktop system that combines three concerns in one codebase:

- design and validation of a station layout;
- compilation of that layout into interlocking/runtime artifacts;
- simulation and operation of the runtime state through a UI and SmartIO integration.

At a high level, the project lets you:

- model a railway topology with sections, points, and signals;
- compute valid routes and interlocking constraints;
- start and control a simulation session;
- persist runtime commands, events, and snapshots;
- expose runtime state to external integrations.

The main desktop entrypoint is [main.py](/Users/Storm/Desktop/CBI_Railway_Signal/main.py).

## Architecture Summary

The codebase is split into a small number of architectural areas with fairly clear boundaries:

- `core/`
  Pure domain logic and compiler logic. This is the most reusable part of the system and should stay free from UI-specific concerns.
- `kernel/`
  Runtime engines for locking, routing, safety, and occupancy plus product rules.
- `runtime/`
  Stateful runtime session, application use cases, workspace orchestration, and the runtime-facing read model.
- `simulation/`
  Simulation helpers such as train lifecycle and snapshot hydration.
- `infrastructure/`
  Persistence adapters and clocks.
- `integration/`
  External integration code, currently centered around SmartIO communication.
- `ui/`
  PyQt6 controllers, presenters, and views.

The main flow is:

```text
User / SmartIO
      |
      v
UI Controllers / Runtime Coordinator
      |
      v
RuntimeWorkspaceService
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
RailwayTopology + Routes + Trains
```

## Project Structure

```text
core/
  compiler/             Route compiler and interlocking spec generation
  domain/               Topology, policies, and lifecycle rules

kernel/
  locking_engine/       Route locking and release logic
  occupancy_engine/     Occupancy reconciliation
  route_dispatcher/     Route finding and dispatching
  safety_engine/        Safety checks and fail-safe monitoring

runtime/
  application/          Application use cases and serialization helpers
  specific_application/ Station-specific editor and layout logic
  runtime_controller.py Stateful runtime session
  runtime_cycle.py      Simulation tick engine
  command_bus.py        Runtime command gateway

simulation/             Train lifecycle and snapshot hydration helpers
infrastructure/         Persistence adapters and clocks
integration/            SmartIO protocol and bridge code
ui/                     PyQt controllers, presenters, and views
tests/                  Automated tests
data/                   Sample layouts and runtime data
tool/                   Tooling and helper assets
```

## Important Runtime Concepts

### RailwayTopology

`RailwayTopology` is the structural source of truth for the station model. It represents nodes, edges, signals, sections, and points, and is reused across editing, compilation, simulation, runtime, and serialization.

### RuntimeSession

`runtime/runtime_controller.py` defines the stateful runtime session. It is responsible for:

- holding the active runtime state;
- applying route, occupancy, point, and train commands;
- hydrating snapshots;
- exposing the runtime-facing read model.

This is the execution layer used by the application orchestration code and the SmartIO bridge.

### SimulationEngine

`runtime/runtime_cycle.py` defines the simulation engine. It is responsible for:

- advancing train movement with `step()`;
- updating time-based progression for the current runtime session;
- running safety checks during time-stepped simulation behavior.

It does not own journaling, recovery, or workspace orchestration.

### RuntimeWorkspaceService

`runtime/workspace_service.py` is the runtime facade used by the desktop app. It is the key boundary between UI/integration code and the simulation engine.

It is responsible for:

- creating or restoring the runtime session;
- accepting commands from UI and integrations;
- journaling commands and runtime events;
- creating runtime checkpoints;
- restoring state after restart;
- exposing runtime health and view state.

If you are trying to understand how runtime actions should enter the system, this service is usually the first file to inspect.

## Package Dependency Intent

The intended dependency direction is:

- `core/` should remain the most stable and reusable layer;
- `kernel/` may depend on `core/domain` and `infrastructure/clocks`;
- `runtime/` may orchestrate `core/`, `kernel/`, `simulation/`, and `infrastructure/`;
- `simulation/` may depend on `core/` and collaborate with `runtime/`;
- `ui/` and `integration/` should go through runtime services rather than mutating runtime state directly.

In practice, the design goal is that UI and SmartIO do not write runtime internals directly. Changes should go through command-oriented boundaries such as `RuntimeWorkspaceService`.

## Requirements

- Python 3.11+
- PyQt6
- pytest for running tests

The repository includes project metadata and tool configuration in [pyproject.toml](/Users/Storm/Desktop/CBI_Railway_Signal/pyproject.toml), but it does not currently include a pinned `requirements.txt`.

## Getting Started

Create and activate a virtual environment, then install the dependencies your environment needs. A typical local setup is:

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -U pip
python -m pip install PyQt6 pytest
```

If your environment already manages dependencies another way, adapt the commands accordingly.

## Running the Application

Start the desktop application with:

```bash
python main.py
```

`main.py` creates a `QApplication`, builds a `GenericApplicationProfile`, and opens the main PyQt window.

## Running Tests

Run the full test suite with:

```bash
python -m pytest
```

Run the runtime workspace tests only with:

```bash
python -m pytest tests/test_runtime_workspace.py
```

## Key Files to Read First

If you are new to the repository, these files are the best starting points:

- [main.py](/Users/Storm/Desktop/CBI_Railway_Signal/main.py)
  Desktop entrypoint.
- [runtime/workspace_service.py](/Users/Storm/Desktop/CBI_Railway_Signal/runtime/workspace_service.py)
  Main runtime orchestration facade.
- [runtime/application_service.py](/Users/Storm/Desktop/CBI_Railway_Signal/runtime/application_service.py)
  Generic application service layer.
- [runtime/specific_application/editor_service.py](/Users/Storm/Desktop/CBI_Railway_Signal/runtime/specific_application/editor_service.py)
  Station-specific editor behavior.
- [runtime/runtime_controller.py](/Users/Storm/Desktop/CBI_Railway_Signal/runtime/runtime_controller.py)
  Stateful runtime session.
- [runtime/runtime_cycle.py](/Users/Storm/Desktop/CBI_Railway_Signal/runtime/runtime_cycle.py)
  Pure simulation stepping behavior.
- [core/compiler/route_compiler.py](/Users/Storm/Desktop/CBI_Railway_Signal/core/compiler/route_compiler.py)
  Route compilation and interlocking-related logic.
- [tests/test_runtime_workspace.py](/Users/Storm/Desktop/CBI_Railway_Signal/tests/test_runtime_workspace.py)
  Practical examples of how the runtime workspace is used.

## Data and Persistence

The repository includes a `data/` directory for layouts and runtime-related persisted artifacts. Runtime orchestration also uses command/event/snapshot journaling to support recovery and replay behavior.

If you change runtime persistence behavior, review both:

- runtime journaling and recovery in `infrastructure/event_store.py`;
- runtime state and view model code in `runtime/`;
- simulation stepping and train lifecycle behavior in `simulation/`.

## SmartIO Integration

SmartIO-related integration code lives under `integration/smartio_adapter/`.

This integration is responsible for:

- receiving and validating external messages;
- translating envelopes into typed runtime actions;
- emitting command results, runtime events, and runtime snapshots outward.

The intended architecture is that SmartIO integration does not directly manipulate topology or runtime internals. It should pass through the same orchestration boundary as the UI.

## Additional Documentation

Detailed architecture references are available in:

- [ARCHITECTURE.md](/Users/Storm/Desktop/CBI_Railway_Signal/ARCHITECTURE.md)
- [ARCHITECTURE.vi.md](/Users/Storm/Desktop/CBI_Railway_Signal/ARCHITECTURE.vi.md)

Use the README for orientation and setup; use the architecture documents for deeper package responsibilities and dependency rules.

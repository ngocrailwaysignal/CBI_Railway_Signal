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
  Pure domain logic, compiler logic, runtime engines, and application use cases. This is the most reusable part of the system and should stay free from UI-specific concerns.
- `runtime_session/`
  The stateful runtime session for CBI. This layer owns mutable runtime state, route/occupancy/point/train mutations, snapshot restore, and the runtime-facing read model.
- `simulation/`
  Pure simulation behavior layered on top of the runtime session. This layer owns train lifecycle, simulation stepping, and other time-driven simulation concerns.
- `products/generic_application/`
  Application-level orchestration for the runtime workspace. This layer owns command journaling, checkpointing, recovery, profiles, and the main runtime facade.
- `products/generic_product/`
  Reusable product rules and product kernel behavior that support route/runtime use cases.
- `products/specific_application/`
  Station-specific editor and layout logic. This is where app-specific or domain-specific layout behavior lives.
- `integrations/`
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
  application/          Application use cases and serialization helpers
  compiler/             Route compiler and interlocking spec generation
  domain/               Topology, policies, and lifecycle rules
  infrastructure/       Persistence, clocks, and infrastructure adapters
  runtime/              Runtime engines and safety/interlocking behavior

products/
  generic_application/  Runtime facade, journaling, recovery, profiles
  generic_product/      Product kernel and reusable product rules
  specific_application/ Station-specific editor and layout logic

runtime_session/        Stateful CBI runtime session and runtime view state
simulation/             Pure simulation stepping and train lifecycle
integrations/           SmartIO protocol and bridge code
ui/                     PyQt controllers, presenters, and views
tests/                  Automated tests
data/                   Sample layouts and runtime data
tools/                  Tooling and helper assets
```

## Important Runtime Concepts

### RailwayTopology

`RailwayTopology` is the structural source of truth for the station model. It represents nodes, edges, signals, sections, and points, and is reused across editing, compilation, simulation, runtime, and serialization.

### RuntimeSession

`runtime_session/session.py` defines the stateful runtime session. It is responsible for:

- holding the active runtime state;
- applying route, occupancy, point, and train commands;
- hydrating snapshots;
- exposing the runtime-facing read model.

This is the execution layer used by the application orchestration code and the SmartIO bridge.

### SimulationEngine

`simulation/engine.py` defines the pure simulation engine. It is responsible for:

- advancing train movement with `step()`;
- updating time-based progression for the current runtime session;
- running safety checks during time-stepped simulation behavior.

It does not own journaling, recovery, or workspace orchestration.

### RuntimeWorkspaceService

`products/generic_application/runtime_workspace_service.py` is the runtime facade used by the desktop app. It is the key boundary between UI/integration code and the simulation engine.

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
- `runtime_session/` may depend on `core/` and `simulation/`;
- `simulation/` may depend on `core/` and collaborate with `runtime_session/`;
- `products/generic_application/` may orchestrate `core/`, `runtime_session/`, `simulation/`, and `products/generic_product/`;
- `products/specific_application/` may add station-specific behavior without pulling UI concerns into `core/`;
- `ui/` and `integrations/` should go through application/runtime services rather than mutating runtime state directly.

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
- [products/generic_application/runtime_workspace_service.py](/Users/Storm/Desktop/CBI_Railway_Signal/products/generic_application/runtime_workspace_service.py)
  Main runtime orchestration facade.
- [products/generic_application/service.py](/Users/Storm/Desktop/CBI_Railway_Signal/products/generic_application/service.py)
  Generic application service layer.
- [products/specific_application/editor_service.py](/Users/Storm/Desktop/CBI_Railway_Signal/products/specific_application/editor_service.py)
  Station-specific editor behavior.
- [runtime_session/session.py](/Users/Storm/Desktop/CBI_Railway_Signal/runtime_session/session.py)
  Stateful runtime session.
- [simulation/engine.py](/Users/Storm/Desktop/CBI_Railway_Signal/simulation/engine.py)
  Pure simulation stepping behavior.
- [core/compiler/route_compiler.py](/Users/Storm/Desktop/CBI_Railway_Signal/core/compiler/route_compiler.py)
  Route compilation and interlocking-related logic.
- [tests/test_runtime_workspace.py](/Users/Storm/Desktop/CBI_Railway_Signal/tests/test_runtime_workspace.py)
  Practical examples of how the runtime workspace is used.

## Data and Persistence

The repository includes a `data/` directory for layouts and runtime-related persisted artifacts. Runtime orchestration also uses command/event/snapshot journaling to support recovery and replay behavior.

If you change runtime persistence behavior, review both:

- runtime journaling and recovery in `products/generic_application/`;
- runtime state and view model code in `runtime_session/`;
- simulation stepping and train lifecycle behavior in `simulation/`.

## SmartIO Integration

SmartIO-related integration code lives under `integrations/smartio/`.

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

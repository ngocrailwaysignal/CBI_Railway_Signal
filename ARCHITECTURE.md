# CBI Railway Signal System Architecture

This document describes the current architecture of the `CBI_Railway_Signal` application based on the code in this repository. It focuses on actual package boundaries, runtime control flow, journaling, recovery, and SmartIO integration rather than an abstract reference architecture.

## Terminology Convention

This document keeps the following bilingual terminology aligned:
- `route` -> `hành trình`
- `point` / `turnout` -> `ghi`
- `signal aspect` -> `trạng thái tín hiệu`
- `conflict` -> `xung đột`
- `flank protection` -> `bảo vệ sườn`
- `overlap` -> `vùng chồng lấn`
- `movement authority` -> `quyền di chuyển`
- `degraded mode` / degraded runtime state -> `chế độ suy giảm` / `trạng thái suy giảm`

## 1. Architectural Intent

The codebase is designed around one primary idea: a station layout should be the shared source of truth across design, route compilation, runtime control, simulation, persistence, and integration. Instead of duplicating separate data models for each concern, the system carries one topology forward and applies stricter orchestration boundaries when moving from design-time to runtime behavior.

The main architectural goals are:
- keep topology and route semantics deterministic;
- centralize runtime mutations behind one command boundary;
- make runtime evolution replayable through journaled commands/events/snapshots;
- allow external integration without exposing unsafe direct state writes;
- separate package responsibilities so that domain, engine, runtime, integration, and UI concerns remain understandable.

## 2. System Layers

The system can be read as six cooperating layers:

1. Domain and compiler layer
   Located in `core/`. It defines topology, rail elements, routes, trains, conflict/flank/overlap policy, and interlocking specification generation.
2. Kernel engine layer
   Located in `kernel/`. It contains the operational engines that dispatch routes, lock elements, reconcile occupancy, and detect unsafe state.
3. Runtime orchestration layer
   Located in `runtime/`. It creates the stateful session, exposes use cases, builds read models, and provides the command/journal boundary.
4. Simulation layer
   Located in `simulation/` plus parts of `runtime/runtime_cycle.py`. It handles train lifecycle and time-stepped behavior.
5. Infrastructure layer
   Located in `infrastructure/`. It provides event journaling, recovery, snapshot repositories, and clocks.
6. Integration and presentation layer
   Located in `integration/` and `ui/`. It adapts transport and user interaction into runtime operations.

High-level flow:

```text
Layout Editor / SmartIO / UI Action
              |
              v
Application Services / Controllers
              |
              v
RuntimeWorkspaceService
              |
              v
RuntimeSession
              |
              v
Kernel Engines
              |
              v
RailwayTopology + Active Route State + Train State
              |
              +--> Runtime View State
              +--> Runtime Journal
              +--> SmartIO Outbound Payloads
```

## 3. Bounded Contexts and Responsibilities

### 3.1 `layout_context`

Purpose:
- create and edit the station topology before runtime operation;
- serialize and deserialize layout JSON;
- supply topology payloads to the UI and other services.

Key modules:
- `runtime/specific_application/editor_service.py`
- `runtime/specific_application/station_layout.py`
- `core/domain/model/topology.py`
- `runtime/application/serialization/layout_payload_serializer.py`
- `ui/views/canvas_editor_view.py`

Inputs:
- canvas editing actions;
- layout JSON files;
- property updates from the UI.

Outputs:
- validated `RailwayTopology` objects;
- persisted layout JSON;
- layout payloads for UI display and SmartIO local export.

Boundary rules:
- this context owns structural editing, not runtime route activation;
- it may set up sections, signals, points, and graph connections;
- it must not bypass runtime mode policy by manually forcing route state.

Example runtime impact:
- the topology created here becomes the basis for route search, topology revision hashing, and runtime recovery compatibility.

### 3.2 `interlocking_compile_context`

Purpose:
- derive deterministic interlocking-oriented route information from one topology snapshot;
- produce route candidates and related conflict/overlap/flank constraints;
- generate artifacts suitable for display or persistence.

Key modules:
- `core/compiler/route_compiler.py`
- `core/compiler/interlocking_table.py`
- `core/compiler/spec_models.py`
- `runtime/application_service.py`
- `kernel/product_kernel.py`

Inputs:
- `RailwayTopology`
- requested overlap length
- optional station id for spec output

Outputs:
- route search results;
- interlocking table rows;
- `InterlockingSpec` records;
- exported `interlocking_spec.json`-style artifacts.

Boundary rules:
- compilation is deterministic from topology plus overlap parameters;
- compile-time logic computes what is allowed, but it does not itself activate a runtime route;
- runtime dynamic state such as current train position or stream sequence is not authored here.

Example runtime impact:
- the resulting route rows define which points must lock, which sections become part of a route, and which routes conflict at runtime.

### 3.3 `runtime_control_context`

Purpose:
- enforce route setting and route cancellation rules;
- maintain active locking state for points, sections, and routes;
- reconcile section occupancy and detect unsafe state;
- expose safe runtime operations for manual updates and train management.

Key modules:
- `runtime/runtime_controller.py`
- `kernel/route_dispatcher/route_engine.py`
- `kernel/route_dispatcher/route_dispatcher.py`
- `kernel/locking_engine/locking_engine.py`
- `kernel/occupancy_engine/occupancy_reconciler.py`
- `kernel/safety_engine/safety_monitor.py`
- `core/domain/lifecycle/approach_locking.py`
- `core/domain/lifecycle/route_lifecycle_fsm.py`

Inputs:
- typed runtime commands such as set route, set point position, section occupancy updates, and train updates;
- topology created by the layout context;
- timing configuration such as approach lock duration and overlap release delay.

Outputs:
- active routes in the locking engine;
- signal aspect and route id assignments;
- occupied/free section state;
- train runtime state;
- safety violations when detected.

Boundary rules:
- direct writes to protected runtime fields are intentionally restricted;
- runtime control logic is engine-driven and command-driven, not view-driven;
- `signal.aspect`, `signal.route_id`, and `locked_by` must be changed through validated runtime flow, not arbitrary transport payloads.

Example runtime impact:
- when a route is activated, this context updates signal authority, point locking, approach lock state, and later route release behavior.

### 3.4 `simulation_workspace_context`

Purpose:
- drive time-stepped behavior of the active runtime session;
- maintain train lifecycle while a route is active;
- support runtime snapshot hydration and simulation-oriented view state.

Key modules:
- `runtime/runtime_cycle.py`
- `simulation/train_simulator.py`
- `simulation/environment_simulator.py`
- `runtime/read_model.py`

Inputs:
- `step_runtime` command;
- train creation/update inputs;
- active route state from the locking engine;
- snapshot payloads.

Outputs:
- updated runtime tick;
- advanced train positions;
- occupancy changes caused by train movement;
- runtime snapshot and view state payloads.

Boundary rules:
- simulation advances only inside the runtime session boundary;
- simulation must respect locking and safety constraints rather than invent its own authority model;
- route auto-release is a runtime consequence, not an independent UI action.

Example runtime impact:
- each tick updates time locking, advances trains, and may trigger fail-safe STOP if the resulting state becomes inconsistent.

### 3.5 `runtime_orchestration_context`

Purpose:
- manage lifecycle of the active runtime session for a workspace;
- journal command processing and create replayable events;
- checkpoint snapshots and restore session state after restart;
- expose runtime health and read models to controllers and transport.

Key modules:
- `runtime/workspace_service.py`
- `infrastructure/event_store.py`
- `runtime/profile.py`
- `runtime/application/use_cases/*`

Inputs:
- topology for session creation;
- runtime commands from UI or SmartIO;
- existing journal files on disk;
- profile defaults.

Outputs:
- `RuntimeCommandResult`
- `RuntimeEvent`
- runtime snapshot dictionaries;
- `RuntimeHealth`
- cached duplicate-command results.

Boundary rules:
- this context owns `stream_seq`, command caching, and journal append order;
- `RuntimeSession` does not write directly to the journal;
- callers should treat this context as the transaction boundary around runtime mutation.

Example runtime impact:
- duplicate commands are detected here by `(source_id, command_id)` and are returned as `stale` instead of being executed again.

### 3.6 `integration_context`

Purpose:
- connect the application to SmartIO over WebSocket;
- validate transport envelopes and normalize transport errors;
- map transport payloads into runtime commands and state updates;
- publish outbound command results, runtime events, and runtime snapshots.

Key modules:
- `integration/smartio_adapter/protocol.py`
- `integration/smartio_adapter/runtime_bridge.py`
- `integration/smartio_adapter/qt_ws_client.py`
- `ui/controllers/runtime_workspace_controller.py`

Inputs:
- inbound WebSocket text messages;
- SmartIO envelope payloads for `command`, `state_update`, and runtime snapshot;
- runtime health and view state from the orchestration context.

Outputs:
- runtime command requests;
- SmartIO protocol errors when payloads are invalid;
- outbound event envelopes carrying results and snapshots.

Boundary rules:
- transport payloads cannot directly write protected route-locking state;
- signal aspect authority must be expressed through route intent, not field assignment;
- state update payloads are allowed to modify only the subset of runtime state the bridge explicitly permits.

Example runtime impact:
- a SmartIO `state_update` with train changes can update train state incrementally, but a direct `signal.aspect` write is rejected.

### 3.7 `presentation_context`

Purpose:
- manage the desktop UI, user interaction, and visual state;
- synchronize operating mode with available controls;
- render runtime state, interlocking rows, and SmartIO connection status.

Key modules:
- `ui/views/main_window_view.py`
- `ui/views/canvas_editor_view.py`
- `ui/controllers/main_window_controller.py`
- `ui/controllers/runtime_workspace_controller.py`
- `ui/controllers/workspace_state_coordinator.py`
- `ui/presenters/route_presenter.py`

Inputs:
- user gestures and form updates;
- runtime view state and health;
- SmartIO connection events;
- mode policy outputs.

Outputs:
- layout edits;
- runtime command requests;
- user-visible summaries, logs, and route previews.

Boundary rules:
- the UI should request runtime behavior through controllers/services rather than mutating runtime entities itself;
- mode policy determines which operations are enabled;
- presentation code is a consumer of state, not the owner of runtime truth.

## 4. Core Runtime Components

### 4.1 `RailwayTopology`

`RailwayTopology` is the shared structural model used throughout the repository. It holds:
- graph nodes and directed connections;
- dictionaries of signals and sections;
- points and their orientation/position data;
- validation helpers for signal configuration and route requests;
- JSON import/export logic;
- runtime occupancy and locking state embedded on the rail elements.

Architectural significance:
- there is no separate topology for design and runtime;
- topology revision is computed from the serialized structure and used to validate recovery compatibility;
- the same object shape underpins editor behavior, route search, snapshots, and SmartIO export.

### 4.2 `RuntimeSession`

`RuntimeSession` is the stateful runtime implementation. It assembles:
- routing logic via route engine and dispatcher;
- route locking and release behavior;
- occupancy reconciliation;
- safety monitoring;
- train lifecycle helpers;
- simulation stepping.

It exposes the operational API that the workspace service ultimately drives:
- `set_route(...)`
- `cancel_route(...)`
- `set_section_occupied(...)`
- `set_point_position(...)`
- `upsert_train(...)`
- `remove_train(...)`
- `hydrate_snapshot(...)`
- `step()`

Architectural significance:
- this is the mutable runtime state owner;
- it does not own journaling policy;
- it is the place where runtime commands become concrete engine mutations.

### 4.3 `SimulationEngine`

`SimulationEngine` performs step-based runtime progression.

Its behavior is not limited to train movement. One step can affect:
- approach locking timers;
- overlap release timing;
- section occupancy transitions;
- signal safety validation;
- route lifecycle cleanup;
- runtime tick count.

Architectural significance:
- simulation is fully coupled to runtime state correctness;
- every tick is a safety-relevant event, not merely a visualization update.

### 4.4 `RuntimeWorkspaceService`

`RuntimeWorkspaceService` is the most important coordination boundary in the runtime architecture.

It is responsible for:
- creating the runtime session on demand;
- restoring session state from journal when possible;
- applying runtime profile timing defaults;
- processing commands in a stable order;
- recording commands and events;
- creating snapshots;
- exposing view state and health;
- providing higher-level helper methods used by the UI.

Architectural significance:
- UI code and SmartIO code converge here;
- the service guards against duplicate command execution;
- it is the only layer that fully understands command ids, event stream sequence, recovery, and session lifecycle together.

### 4.5 `RuntimeJournal` and `RuntimeRecoveryService`

These infrastructure primitives implement an append-only event-journal pattern.

Journal artifacts:
- `runtime_commands.jsonl`
- `runtime_events.jsonl`
- `runtime_snapshots.jsonl`

Recovery algorithm:
1. Load latest valid snapshot from `runtime_snapshots.jsonl`.
2. Read `topology_revision` from the snapshot.
3. Refuse normal restoration if the snapshot revision differs from the current topology revision.
4. Hydrate the runtime session from the snapshot.
5. Load events after the snapshot `stream_seq`.
6. Replay only events whose `command_status` is `applied`.

Architectural significance:
- snapshots shorten restore time;
- events preserve replayable command history after the checkpoint;
- invalid JSON tail data can be truncated while reading;
- degraded recovery state is surfaced through `RuntimeHealth`.

## 5. Command Flow and Journaling

`RuntimeWorkspaceService.submit_command(...)` is the canonical entry point for runtime mutations.

Detailed flow:
1. Ensure a runtime session exists for the provided topology.
2. Normalize the incoming command into a `RuntimeCommand`.
3. Determine actual `command_id` and `source_id`.
4. Check the processed-command cache keyed by `(source_id, command_id)`.
5. If a cached result exists, return a `stale` response without re-execution.
6. Append the command to `runtime_commands.jsonl`.
7. Execute the command against the runtime session.
8. Capture either successful payload or rejection message.
9. Increment `stream_seq`.
10. Append a `RuntimeEvent` to `runtime_events.jsonl`.
11. Cache the processed result for future duplicate detection.
12. Optionally checkpoint a runtime snapshot based on profile settings.

Conceptual command result states:
- `applied`: the command executed successfully and produced a journaled runtime event.
- `rejected`: the command failed validation or runtime execution.
- `stale`: the command was identified as a duplicate and not executed again.

Why this matters:
- idempotent transport behavior becomes possible for SmartIO and controllers;
- replay and diagnostics can inspect both commands and outcomes separately;
- stream ordering is explicit and recoverable.

## 6. Runtime Internals and Engine Collaboration

The runtime works because several engines collaborate rather than one monolithic class doing everything.

### Route search and dispatch

The route dispatcher layer:
- validates route candidates against topology and runtime context;
- finds feasible paths between entry and exit signals;
- coordinates handoff to locking logic once a route is selected.

### Locking and release

The locking engine:
- locks required points and route sections;
- assigns signal authority to active routes;
- manages route lifecycle state;
- handles cancellation, emergency release, timed release, and overlap release;
- tracks approach lock state and sequence-based release state.

### Occupancy reconciliation

The occupancy engine:
- helps reconcile section occupancy with train movement and manual updates;
- ensures runtime state remains structurally coherent when trains move or disappear.

### Safety monitoring

`SafetyMonitor` validates fail-safe conditions such as:
- more than one train occupying the same section;
- a train claiming a section that is not marked occupied;
- a signal showing `PROCEED` without a locked route;
- invalid point position while the point is locked.

If the runtime becomes unsafe, fail-safe behavior forces signals to STOP and clears route authority indicators.

### Train lifecycle

`RuntimeTrainLifecycle` in `simulation/train_simulator.py` handles:
- create/update behavior for trains;
- route assignment or reassignment;
- train removal;
- current-section vacancy handling;
- route-aware train placement checks.

### Simulation step

`SimulationEngine` ties the above together:
- update timing and release state;
- advance trains;
- trigger occupancy changes;
- detect unsafe conditions;
- keep the runtime tick consistent.

## 7. Operational Flows

### 7.1 Layout to runtime

```text
Load or edit layout
      |
      v
RailwayTopology ready
      |
      v
RuntimeWorkspaceService.ensure_session(...)
      |
      +--> create RuntimeSession
      +--> configure timing from profile
      +--> compute topology_revision
      +--> attempt journal recovery
      |
      v
Runtime ready or degraded
```

### 7.2 Set route flow

```text
set_route request
      |
      v
Workspace service submits command
      |
      v
RuntimeSession.set_route(...)
      |
      v
RouteDispatcher finds route
      |
      v
LockingEngine locks route/points/sections
      |
      v
Signals updated to reflect active authority
      |
      v
Applied RuntimeEvent + updated view state
```

### 7.3 Step runtime flow

```text
step_runtime
    |
    v
SimulationEngine.step()
    |
    +--> update time locking
    +--> move trains
    +--> reconcile occupancy
    +--> detect unsafe conditions
    |
    +--> if unsafe: fail-safe STOP
    |
    v
Tick + read model + journaled event
```

### 7.4 Snapshot publish flow

```text
Checkpoint requested or checkpoint interval reached
                     |
                     v
build_runtime_snapshot(...)
                     |
                     v
append to runtime_snapshots.jsonl
                     |
                     v
update RuntimeHealth.last_snapshot_at
                     |
                     v
optional outbound SmartIO runtime_snapshot
```

### 7.5 Recovery flow

```text
Application restart / session recreation
                 |
                 v
Load latest snapshot
                 |
                 +--> no snapshot: start clean session
                 |
                 +--> revision mismatch: degraded runtime
                 |
                 v
Hydrate snapshot
                 |
                 v
Replay applied events after snapshot stream_seq
                 |
                 v
Recovered session or degraded runtime health
```

## 8. Runtime Read Model, Snapshot, and Health

### Runtime view state

`runtime/read_model.py` builds `RuntimeViewState`, which is a UI-facing summary rather than the full mutable runtime object graph.

It includes conceptual slices such as:
- active routes;
- trains;
- occupancy state;
- signal state;
- tick count.

This keeps the presentation layer focused on rendering and inspection rather than direct engine interaction.

### Runtime snapshot

`build_runtime_snapshot(...)` serializes the runtime into a transport- and persistence-friendly dictionary with:
- `snapshot_version`
- `stream_seq`
- `topology_revision`
- `tick`
- `routes`
- `trains`
- `occupancy`
- `signal_state`

This snapshot is intentionally runtime-only. It does not redefine the layout itself; instead, it assumes a compatible topology already exists.

### Runtime health

`RuntimeHealth` communicates orchestration-level status:
- topology revision currently in use;
- latest stream sequence;
- timestamps for last applied command and last snapshot;
- last command id and command status;
- `degraded_reason`.

Degraded health does not mean the application crashes. It means the runtime detected a recovery or consistency problem that must be surfaced to operators and possibly handled in fail-safe fashion.

## 9. SmartIO Protocol Handling and Safety

The SmartIO architecture exists to allow transport interoperability without diluting runtime safety rules.

Inbound envelope handling:
- `command` is parsed into `{command_id, source_id, kind, payload, ts}`;
- `state_update` is normalized into an internal `apply_state_update` command;
- runtime snapshot payloads can hydrate the current session.

Key validation and safety rules:
- malformed envelopes raise `SmartIOProtocolError`;
- `state_update` must be an object payload;
- direct updates to `locked_by` are blocked;
- direct signal writes to `aspect` and `route_id` are blocked;
- train payloads require valid identifiers and sections;
- stale route ids in train updates may be tolerated in a narrow fallback case when a route has auto-released;
- route id mismatches in signal proceed handling or snapshot restoration are treated as inconsistency errors.

Outbound payloads:
- command result status for transport acknowledgement;
- runtime events for external subscribers;
- runtime snapshots for state synchronization.

Architectural consequence:
- SmartIO is an adapter around runtime semantics, not a replacement for them.

## 10. Dependency Rules

The current architecture is clearest when these dependency expectations are preserved:
- `core/` should remain free of UI and transport concerns.
- `kernel/` should operate on domain/runtime entities, not on presentation widgets.
- `runtime/` may coordinate kernel and infrastructure but should not absorb UI-specific logic.
- `integration/` should translate protocol payloads into runtime operations, not implement business rules that belong in kernel/runtime.
- `ui/` should render and request actions, not become the source of truth for route state.

A useful rule of thumb:
- if the logic defines railway meaning, it likely belongs in `core/` or `kernel/`;
- if it defines command orchestration, recovery, or session lifecycle, it likely belongs in `runtime/`;
- if it defines transport parsing, it likely belongs in `integration/`;
- if it defines screen behavior, it belongs in `ui/`.

## 11. Extension Guidelines

When extending the system, these placement guidelines reduce architectural drift:

- Add new topology element semantics in `core/domain/model/` and related policy modules.
- Add new deterministic route or interlocking derivation in `core/compiler/` or `kernel/product_kernel.py`.
- Add new runtime mutation flows through `runtime/application/use_cases/`, `runtime/workspace_service.py`, and `RuntimeSession`.
- Add new persistence or replay concerns in `infrastructure/`.
- Add new SmartIO message shapes in `integration/smartio_adapter/` after deciding how they map into safe runtime commands.
- Add new UI actions through controllers that call existing runtime boundaries rather than bypassing them.

If a new feature requires changing safety behavior, evaluate:
1. where the invariant truly belongs,
2. how it affects snapshots and replay,
3. whether transport and UI are still prevented from bypassing it.

## 12. Key References

- [README.md](/e:/Documents/DO_AN/CBI_Railway_Signal/README.md:1) for project overview, runtime commands, and developer workflow.
- [INTERLOCKING_PRINCIPLES.md](/e:/Documents/DO_AN/CBI_Railway_Signal/INTERLOCKING_PRINCIPLES.md:1) for signalling principles and their mapping to the codebase.
- `tests/test_runtime_workspace.py` for executable examples of route lifecycle, snapshot round-trip, and SmartIO-related runtime behavior.

---

## Tiếng Việt

Tài liệu này mô tả kiến trúc hiện tại của `CBI_Railway_Signal` dựa trên code trong repository. Trọng tâm là ranh giới package, luồng runtime, journaling, recovery, và tích hợp SmartIO theo đúng implementation hiện tại thay vì một kiến trúc tham chiếu trừu tượng.

### Quy ước thuật ngữ

Tài liệu kiến trúc dùng thống nhất các cách dịch sau:
- `route` -> `hành trình`
- `point` / `turnout` -> `ghi`
- `signal aspect` -> `trạng thái tín hiệu`
- `conflict` -> `xung đột`
- `flank protection` -> `bảo vệ sườn`
- `overlap` -> `vùng chồng lấn`
- `movement authority` -> `quyền di chuyển`
- `degraded mode` hoặc degraded runtime state -> `chế độ suy giảm` hoặc `trạng thái suy giảm`

### 1. Chủ đích kiến trúc

Codebase được thiết kế quanh một ý tưởng chính: sơ đồ ga phải là nguồn dữ liệu chung cho thiết kế, biên dịch route, điều khiển runtime, mô phỏng, persistence, và integration. Thay vì duy trì nhiều mô hình dữ liệu khác nhau cho từng mối quan tâm, hệ thống mang một topology thống nhất xuyên suốt và áp dụng các ranh giới điều phối chặt chẽ hơn khi chuyển từ design-time sang runtime.

Các mục tiêu kiến trúc chính:
- giữ topology và ngữ nghĩa route có tính xác định;
- tập trung mọi mutation runtime vào một command boundary;
- làm cho tiến hóa runtime có thể replay qua journal command/event/snapshot;
- cho phép tích hợp ngoài mà không lộ cơ chế ghi trực tiếp không an toàn;
- tách trách nhiệm package sao cho domain, engine, runtime, integration, và UI vẫn dễ hiểu.

### 2. Các lớp hệ thống

Hệ thống có thể được đọc như 6 lớp phối hợp:

1. Lớp domain và compiler
   Nằm trong `core/`. Định nghĩa topology, rail element, route, train, policy conflict/flank/overlap, và sinh interlocking specification.
2. Lớp kernel engine
   Nằm trong `kernel/`. Chứa các engine vận hành để dispatch route, khóa phần tử, hòa giải occupancy, và phát hiện trạng thái không an toàn.
3. Lớp điều phối runtime
   Nằm trong `runtime/`. Tạo stateful session, cung cấp use case, build read model, và làm command/journal boundary.
4. Lớp mô phỏng
   Nằm trong `simulation/` cùng một phần ở `runtime/runtime_cycle.py`. Xử lý lifecycle train và hành vi bước thời gian.
5. Lớp hạ tầng
   Nằm trong `infrastructure/`. Cung cấp event journal, recovery, snapshot repository, và clock.
6. Lớp tích hợp và trình bày
   Nằm trong `integration/` và `ui/`. Chuyển transport và tương tác người dùng thành runtime operation.

Luồng mức cao:

```text
Layout Editor / SmartIO / UI Action
              |
              v
Application Services / Controllers
              |
              v
RuntimeWorkspaceService
              |
              v
RuntimeSession
              |
              v
Kernel Engines
              |
              v
RailwayTopology + Active Route State + Train State
              |
              +--> Runtime View State
              +--> Runtime Journal
              +--> SmartIO Outbound Payloads
```

### 3. Bounded context và trách nhiệm

#### 3.1 `layout_context`

Mục đích:
- tạo và chỉnh topology của ga trước khi vào runtime;
- serialize và deserialize layout JSON;
- cung cấp payload topology cho UI và các service khác.

Module chính:
- `runtime/specific_application/editor_service.py`
- `runtime/specific_application/station_layout.py`
- `core/domain/model/topology.py`
- `runtime/application/serialization/layout_payload_serializer.py`
- `ui/views/canvas_editor_view.py`

Đầu vào:
- thao tác chỉnh trên canvas;
- file layout JSON;
- cập nhật thuộc tính từ UI.

Đầu ra:
- đối tượng `RailwayTopology` đã kiểm tra;
- layout JSON được persist;
- payload layout cho hiển thị UI và export SmartIO local.

Ranh giới:
- context này sở hữu chỉnh sửa cấu trúc, không sở hữu kích hoạt route runtime;
- nó có thể tạo section, signal, point, và graph connection;
- nó không được vượt mode policy bằng cách ép state route thủ công.

Tác động runtime:
- topology được tạo ở đây trở thành nền tảng cho route search, topology revision hash, và kiểm tra tương thích khi recovery.

#### 3.2 `interlocking_compile_context`

Mục đích:
- suy ra dữ liệu route mang ý nghĩa liên khóa từ một snapshot topology;
- sinh route candidate cùng ràng buộc conflict/overlap/flank;
- tạo artifact có thể hiển thị hoặc persist.

Module chính:
- `core/compiler/route_compiler.py`
- `core/compiler/interlocking_table.py`
- `core/compiler/spec_models.py`
- `runtime/application_service.py`
- `kernel/product_kernel.py`

Đầu vào:
- `RailwayTopology`
- overlap length được yêu cầu
- station id tùy chọn cho output spec

Đầu ra:
- kết quả route search;
- interlocking table rows;
- bản ghi `InterlockingSpec`;
- artifact kiểu `interlocking_spec.json`.

Ranh giới:
- quá trình compile là xác định từ topology cộng với tham số overlap;
- logic compile tính cái gì được phép, nhưng không tự kích hoạt route runtime;
- trạng thái động như vị trí train hiện tại hoặc `stream_seq` không được tạo ở đây.

Tác động runtime:
- các row route tạo ra quy định point nào phải khóa, section nào thuộc route, và route nào xung đột ở runtime.

#### 3.3 `runtime_control_context`

Mục đích:
- thực thi quy tắc đặt route và hủy route;
- duy trì trạng thái khóa của point, section, và route;
- hòa giải occupancy và phát hiện trạng thái không an toàn;
- cung cấp runtime operation an toàn cho cập nhật thủ công và quản lý train.

Module chính:
- `runtime/runtime_controller.py`
- `kernel/route_dispatcher/route_engine.py`
- `kernel/route_dispatcher/route_dispatcher.py`
- `kernel/locking_engine/locking_engine.py`
- `kernel/occupancy_engine/occupancy_reconciler.py`
- `kernel/safety_engine/safety_monitor.py`
- `core/domain/lifecycle/approach_locking.py`
- `core/domain/lifecycle/route_lifecycle_fsm.py`

Đầu vào:
- các runtime command có kiểu rõ ràng như set route, set point position, occupancy update, train update;
- topology được tạo từ layout context;
- cấu hình timing như approach lock duration và overlap release delay.

Đầu ra:
- active route trong locking engine;
- gán signal aspect và route id;
- trạng thái occupied/free của section;
- trạng thái runtime của train;
- cảnh báo an toàn nếu phát hiện.

Ranh giới:
- ghi trực tiếp vào các trường runtime được bảo vệ là cố ý bị hạn chế;
- logic điều khiển runtime được dẫn dắt bởi engine và command, không bởi view;
- `signal.aspect`, `signal.route_id`, và `locked_by` phải được thay đổi qua runtime flow đã kiểm tra, không phải payload transport tùy ý.

Tác động runtime:
- khi route được kích hoạt, context này cập nhật signal authority, point locking, approach lock state, và hành vi giải phóng route về sau.

#### 3.4 `simulation_workspace_context`

Mục đích:
- điều khiển hành vi theo bước thời gian của runtime session đang hoạt động;
- duy trì lifecycle train trong khi route còn active;
- hỗ trợ hydrate snapshot và state phục vụ mô phỏng.

Module chính:
- `runtime/runtime_cycle.py`
- `simulation/train_simulator.py`
- `simulation/environment_simulator.py`
- `runtime/read_model.py`

Đầu vào:
- lệnh `step_runtime`;
- đầu vào tạo/cập nhật train;
- trạng thái route active từ locking engine;
- payload snapshot.

Đầu ra:
- tick runtime đã cập nhật;
- vị trí train sau khi tiến;
- thay đổi occupancy do train dịch chuyển;
- payload runtime snapshot và view state.

Ranh giới:
- mô phỏng chỉ được tiến bên trong runtime session boundary;
- mô phỏng phải tôn trọng locking và safety constraint;
- việc auto-release route là hệ quả của runtime, không phải một action UI độc lập.

Tác động runtime:
- mỗi tick cập nhật time locking, di chuyển tàu, và có thể kích hoạt fail-safe STOP nếu trạng thái trở nên không nhất quán.

#### 3.5 `runtime_orchestration_context`

Mục đích:
- quản lý vòng đời runtime session của một workspace;
- ghi journal quá trình xử lý command và tạo event có thể replay;
- checkpoint snapshot và restore session sau khi khởi động lại;
- cung cấp runtime health và read model cho controller và transport.

Module chính:
- `runtime/workspace_service.py`
- `infrastructure/event_store.py`
- `runtime/profile.py`
- `runtime/application/use_cases/*`

Đầu vào:
- topology để tạo session;
- runtime command từ UI hoặc SmartIO;
- các file journal đã tồn tại trên đĩa;
- giá trị mặc định từ profile.

Đầu ra:
- `RuntimeCommandResult`
- `RuntimeEvent`
- dictionary runtime snapshot;
- `RuntimeHealth`
- cache của processed command để phát hiện trùng lặp.

Ranh giới:
- context này sở hữu `stream_seq`, command cache, và thứ tự append vào journal;
- `RuntimeSession` không tự ghi journal;
- caller nên coi đây là transaction boundary quanh mọi runtime mutation.

Tác động runtime:
- command trùng theo `(source_id, command_id)` được phát hiện ở đây và trả về `stale` thay vì chạy lại.

#### 3.6 `integration_context`

Mục đích:
- kết nối ứng dụng với SmartIO qua WebSocket;
- kiểm tra envelope transport và chuẩn hóa lỗi transport;
- ánh xạ payload transport thành runtime command và state update;
- phát command result, runtime event, và runtime snapshot ra ngoài.

Module chính:
- `integration/smartio_adapter/protocol.py`
- `integration/smartio_adapter/runtime_bridge.py`
- `integration/smartio_adapter/qt_ws_client.py`
- `ui/controllers/runtime_workspace_controller.py`

Đầu vào:
- WebSocket text message đi vào;
- payload SmartIO cho `command`, `state_update`, và runtime snapshot;
- runtime health và view state từ orchestration context.

Đầu ra:
- yêu cầu runtime command;
- `SmartIOProtocolError` khi payload không hợp lệ;
- envelope event gửi ra chứa kết quả và snapshot.

Ranh giới:
- payload transport không thể ghi trực tiếp vào trạng thái khóa route được bảo vệ;
- authority của signal phải được diễn đạt qua ý định route, không phải gán field;
- state update chỉ được sửa tập con trạng thái runtime mà bridge cho phép.

Tác động runtime:
- một `state_update` từ SmartIO có thể cập nhật train tăng dần, nhưng ghi trực tiếp `signal.aspect` sẽ bị từ chối.

#### 3.7 `presentation_context`

Mục đích:
- quản lý UI desktop, tương tác người dùng, và trạng thái hiển thị;
- đồng bộ operating mode với các control cho phép;
- render runtime state, interlocking row, và trạng thái kết nối SmartIO.

Module chính:
- `ui/views/main_window_view.py`
- `ui/views/canvas_editor_view.py`
- `ui/controllers/main_window_controller.py`
- `ui/controllers/runtime_workspace_controller.py`
- `ui/controllers/workspace_state_coordinator.py`
- `ui/presenters/route_presenter.py`

Đầu vào:
- thao tác người dùng và cập nhật form;
- runtime view state và health;
- sự kiện kết nối SmartIO;
- kết quả từ mode policy.

Đầu ra:
- chỉnh sửa layout;
- yêu cầu runtime command;
- log, summary, và route preview hiển thị cho người dùng.

Ranh giới:
- UI nên yêu cầu hành vi runtime qua controller/service thay vì tự sửa runtime entity;
- mode policy quyết định thao tác nào được bật;
- code trình bày là nơi tiêu thụ state, không phải nơi sở hữu runtime truth.

### 4. Thành phần runtime cốt lõi

#### 4.1 `RailwayTopology`

`RailwayTopology` là mô hình cấu trúc dùng chung xuyên suốt repository. Nó chứa:
- node đồ thị và kết nối có hướng;
- dictionary của signal và section;
- point cùng dữ liệu orientation/position;
- helper kiểm tra cấu hình tín hiệu và yêu cầu route;
- logic import/export JSON;
- trạng thái occupancy và locking của runtime được gắn trực tiếp lên rail element.

Ý nghĩa kiến trúc:
- không có một topology riêng cho design và runtime;
- topology revision được tính từ cấu trúc serialize và dùng để kiểm tra tương thích recovery;
- cùng một hình dạng đối tượng làm nền cho editor, route search, snapshot, và SmartIO export.

#### 4.2 `RuntimeSession`

`RuntimeSession` là cài đặt runtime có trạng thái. Nó lắp ghép:
- logic route qua route engine và dispatcher;
- hành vi khóa và giải phóng route;
- occupancy reconciliation;
- safety monitoring;
- helper cho lifecycle train;
- cơ chế step mô phỏng.

Nó cung cấp API vận hành mà workspace service sẽ gọi:
- `set_route(...)`
- `cancel_route(...)`
- `set_section_occupied(...)`
- `set_point_position(...)`
- `upsert_train(...)`
- `remove_train(...)`
- `hydrate_snapshot(...)`
- `step()`

Ý nghĩa kiến trúc:
- đây là nơi sở hữu trạng thái runtime có thể thay đổi;
- nó không sở hữu chính sách journaling;
- đây là nơi command runtime được biến thành mutation engine cụ thể.

#### 4.3 `SimulationEngine`

`SimulationEngine` thực hiện tiến runtime theo bước.

Hành vi của nó không chỉ là di chuyển tàu. Một bước có thể tác động tới:
- timer của approach locking;
- thời điểm overlap release;
- chuyển đổi occupancy của section;
- kiểm tra an toàn của signal;
- dọn dẹp vòng đời route;
- bộ đếm tick của runtime.

Ý nghĩa kiến trúc:
- mô phỏng gắn chặt với tính đúng đắn của runtime;
- mỗi tick là một sự kiện liên quan tới an toàn, không chỉ là cập nhật hiển thị.

#### 4.4 `RuntimeWorkspaceService`

`RuntimeWorkspaceService` là ranh giới điều phối quan trọng nhất trong kiến trúc runtime.

Nó chịu trách nhiệm:
- tạo runtime session khi cần;
- restore state từ journal nếu có thể;
- áp dụng timing mặc định từ profile;
- xử lý command theo thứ tự ổn định;
- ghi command và event;
- tạo snapshot;
- cung cấp view state và health;
- cung cấp helper cấp cao cho UI.

Ý nghĩa kiến trúc:
- code UI và code SmartIO gặp nhau ở đây;
- service này bảo vệ hệ thống khỏi chạy lặp command trùng;
- đây là lớp duy nhất hiểu đồng thời command id, event stream sequence, recovery, và session lifecycle.

#### 4.5 `RuntimeJournal` và `RuntimeRecoveryService`

Các primitive hạ tầng này triển khai mô hình event journal append-only.

Artifact journal:
- `runtime_commands.jsonl`
- `runtime_events.jsonl`
- `runtime_snapshots.jsonl`

Thuật toán recovery:
1. Nạp snapshot hợp lệ mới nhất từ `runtime_snapshots.jsonl`.
2. Đọc `topology_revision` trong snapshot.
3. Từ chối restore bình thường nếu revision khác với topology hiện tại.
4. Hydrate runtime session từ snapshot.
5. Nạp các event sau `stream_seq` của snapshot.
6. Replay chỉ các event có `command_status = applied`.

Ý nghĩa kiến trúc:
- snapshot giúp rút ngắn thời gian khôi phục;
- event giữ được lịch sử command có thể replay sau checkpoint;
- phần đuôi JSON hỏng có thể bị cắt bỏ khi đọc;
- trạng thái degraded của recovery được bộc lộ qua `RuntimeHealth`.

### 5. Luồng command và journaling

`RuntimeWorkspaceService.submit_command(...)` là điểm vào chuẩn cho mọi runtime mutation.

Luồng chi tiết:
1. Đảm bảo đã có runtime session cho topology được cung cấp.
2. Chuẩn hóa command đầu vào thành `RuntimeCommand`.
3. Xác định `command_id` và `source_id` thực tế.
4. Kiểm tra processed-command cache với khóa `(source_id, command_id)`.
5. Nếu đã có kết quả cache, trả `stale` và không chạy lại.
6. Append command vào `runtime_commands.jsonl`.
7. Thực thi command trên runtime session.
8. Ghi nhận payload thành công hoặc thông điệp lỗi.
9. Tăng `stream_seq`.
10. Append `RuntimeEvent` vào `runtime_events.jsonl`.
11. Cache kết quả đã xử lý để chống chạy trùng về sau.
12. Tùy profile, có thể checkpoint runtime snapshot.

Các trạng thái kết quả ở mức khái niệm:
- `applied`: command chạy thành công và tạo runtime event được journal.
- `rejected`: command thất bại ở bước kiểm tra hoặc thực thi runtime.
- `stale`: command bị nhận diện là trùng và không được chạy lại.

Vì sao điều này quan trọng:
- hành vi idempotent trở nên khả thi cho SmartIO và controller;
- replay và chẩn đoán có thể xem tách biệt giữa command và outcome;
- thứ tự stream trở nên tường minh và có thể khôi phục.

### 6. Runtime internals và phối hợp engine

Runtime hoạt động đúng vì nhiều engine cùng phối hợp, không phải một class khổng lồ làm mọi thứ.

#### Tìm và dispatch route

Lớp route dispatcher:
- kiểm tra route candidate theo topology và ngữ cảnh runtime;
- tìm path khả thi giữa tín hiệu vào và ra;
- phối hợp bàn giao sang locking logic khi đã chọn route.

#### Locking và release

Locking engine:
- khóa point bắt buộc và section thuộc route;
- gán authority của signal cho active route;
- quản lý route lifecycle state;
- xử lý cancel, emergency release, timed release, và overlap release;
- theo dõi approach lock state và sequence-based release state.

#### Occupancy reconciliation

Occupancy engine:
- hỗ trợ hòa giải occupancy section với chuyển động tàu và cập nhật thủ công;
- bảo đảm trạng thái runtime còn nhất quán về mặt cấu trúc khi train di chuyển hoặc biến mất.

#### Safety monitoring

`SafetyMonitor` kiểm tra các điều kiện fail-safe như:
- có nhiều hơn một tàu trên cùng một section;
- một tàu báo đang ở section nhưng section lại không được đánh dấu occupied;
- tín hiệu đang `PROCEED` nhưng không có route bị khóa;
- point có vị trí không hợp lệ trong khi đang bị khóa.

Nếu runtime trở nên không an toàn, hành vi fail-safe sẽ ép tín hiệu về STOP và xóa chỉ thị route authority.

#### Train lifecycle

`RuntimeTrainLifecycle` trong `simulation/train_simulator.py` xử lý:
- tạo/cập nhật train;
- gán hoặc gán lại route;
- xóa train;
- làm trống section hiện tại của train;
- kiểm tra hợp lệ việc đặt train theo route.

#### Bước mô phỏng

`SimulationEngine` buộc các thành phần trên làm việc chung:
- cập nhật timing và release state;
- di chuyển train;
- kích hoạt occupancy changes;
- phát hiện unsafe conditions;
- giữ `tick` của runtime nhất quán.

### 7. Luồng vận hành

#### 7.1 Từ layout đến runtime

```text
Load hoặc chỉnh layout
        |
        v
RailwayTopology sẵn sàng
        |
        v
RuntimeWorkspaceService.ensure_session(...)
        |
        +--> tạo RuntimeSession
        +--> cấu hình timing từ profile
        +--> tính topology_revision
        +--> thử journal recovery
        |
        v
Runtime sẵn sàng hoặc degraded
```

#### 7.2 Luồng đặt route

```text
Yêu cầu set_route
       |
       v
Workspace service submit command
       |
       v
RuntimeSession.set_route(...)
       |
       v
RouteDispatcher tìm route
       |
       v
LockingEngine khóa route/point/section
       |
       v
Signal được cập nhật authority
       |
       v
RuntimeEvent applied + view state mới
```

#### 7.3 Luồng step runtime

```text
step_runtime
    |
    v
SimulationEngine.step()
    |
    +--> update time locking
    +--> move trains
    +--> reconcile occupancy
    +--> detect unsafe conditions
    |
    +--> nếu unsafe: fail-safe STOP
    |
    v
Tick + read model + event được journal
```

#### 7.4 Luồng publish snapshot

```text
Yêu cầu checkpoint hoặc đủ ngưỡng checkpoint
                      |
                      v
build_runtime_snapshot(...)
                      |
                      v
append vào runtime_snapshots.jsonl
                      |
                      v
cập nhật RuntimeHealth.last_snapshot_at
                      |
                      v
có thể phát SmartIO runtime_snapshot
```

#### 7.5 Luồng recovery

```text
Khởi động lại ứng dụng / tạo lại session
                   |
                   v
Nạp snapshot mới nhất
                   |
                   +--> không có snapshot: bắt đầu session sạch
                   |
                   +--> revision mismatch: runtime degraded
                   |
                   v
Hydrate snapshot
                   |
                   v
Replay applied event sau snapshot stream_seq
                   |
                   v
Session được khôi phục hoặc runtime health degraded
```

### 8. Read model, snapshot, và health của runtime

#### Runtime view state

`runtime/read_model.py` xây dựng `RuntimeViewState`, đây là bản tóm tắt phục vụ UI chứ không phải toàn bộ đồ thị runtime có thể mutate.

Nó gồm các lát cắt khái niệm như:
- active routes;
- trains;
- occupancy state;
- signal state;
- tick count.

Nhờ vậy lớp trình bày tập trung vào render và quan sát thay vì tương tác trực tiếp với engine.

#### Runtime snapshot

`build_runtime_snapshot(...)` serialize runtime thành một dictionary phù hợp cho transport và persistence với các trường:
- `snapshot_version`
- `stream_seq`
- `topology_revision`
- `tick`
- `routes`
- `trains`
- `occupancy`
- `signal_state`

Snapshot này chỉ chứa runtime-only state. Nó không định nghĩa lại layout; thay vào đó nó giả định topology tương thích đã tồn tại.

#### Runtime health

`RuntimeHealth` truyền đạt trạng thái ở mức orchestration:
- topology revision đang dùng;
- stream sequence mới nhất;
- timestamp command áp dụng gần nhất và snapshot gần nhất;
- id và trạng thái command gần nhất;
- `degraded_reason`.

Trạng thái degraded không có nghĩa ứng dụng sập. Nó có nghĩa runtime đã phát hiện vấn đề recovery hoặc consistency cần được lộ ra cho người vận hành và có thể phải xử lý theo fail-safe.

### 9. Xử lý giao thức SmartIO và an toàn

Kiến trúc SmartIO tồn tại để cho phép tương tác transport mà không làm loãng các quy tắc an toàn của runtime.

Xử lý envelope đi vào:
- `command` được parse thành `{command_id, source_id, kind, payload, ts}`;
- `state_update` được chuẩn hóa thành command nội bộ `apply_state_update`;
- payload runtime snapshot có thể hydrate session hiện tại.

Các quy tắc kiểm tra và an toàn chính:
- envelope sai định dạng sẽ ném `SmartIOProtocolError`;
- `state_update` phải là object payload;
- cập nhật trực tiếp `locked_by` bị chặn;
- ghi trực tiếp vào `aspect` và `route_id` của signal bị chặn;
- payload train phải có identifier và section hợp lệ;
- route id cũ trong cập nhật train có thể được chấp nhận trong một fallback hẹp khi route đã auto-release;
- route id không khớp trong xử lý signal proceed hoặc snapshot restore được coi là lỗi bất nhất.

Payload đi ra:
- command result status để xác nhận transport;
- runtime event cho subscriber ngoài;
- runtime snapshot để đồng bộ trạng thái.

Hệ quả kiến trúc:
- SmartIO là lớp adapter bao quanh ngữ nghĩa runtime, không thay thế nó.

### 10. Quy tắc phụ thuộc

Kiến trúc hiện tại rõ ràng nhất khi các kỳ vọng phụ thuộc sau được giữ:
- `core/` nên tránh phụ thuộc vào UI và transport.
- `kernel/` nên làm việc với thực thể domain/runtime, không nên biết widget trình bày.
- `runtime/` có thể điều phối kernel và infrastructure nhưng không nên hấp thụ logic quá đặc thù UI.
- `integration/` nên dịch payload giao thức thành runtime operation, không nên cài business rule lẽ ra thuộc kernel/runtime.
- `ui/` nên render và yêu cầu hành động, không nên trở thành nguồn truth của route state.

Một quy tắc thực dụng:
- nếu logic định nghĩa ý nghĩa đường sắt, nhiều khả năng nó thuộc `core/` hoặc `kernel/`;
- nếu nó định nghĩa command orchestration, recovery, hoặc session lifecycle, nhiều khả năng nó thuộc `runtime/`;
- nếu nó định nghĩa transport parsing, nó thuộc `integration/`;
- nếu nó định nghĩa hành vi màn hình, nó thuộc `ui/`.

### 11. Hướng dẫn mở rộng

Khi mở rộng hệ thống, các quy tắc đặt logic sau giúp tránh trôi kiến trúc:

- Thêm ngữ nghĩa topology mới trong `core/domain/model/` và các policy liên quan.
- Thêm logic route/interlocking mang tính xác định trong `core/compiler/` hoặc `kernel/product_kernel.py`.
- Thêm luồng runtime mutation mới qua `runtime/application/use_cases/`, `runtime/workspace_service.py`, và `RuntimeSession`.
- Thêm concern về persistence hoặc replay trong `infrastructure/`.
- Thêm message shape SmartIO mới trong `integration/smartio_adapter/` sau khi xác định rõ nó ánh xạ thành command runtime an toàn nào.
- Thêm UI action mới qua controller gọi vào runtime boundary hiện có thay vì đi tắt.

Nếu một tính năng mới làm thay đổi hành vi an toàn, hãy đánh giá:
1. invariant đó thật sự thuộc về lớp nào,
2. nó ảnh hưởng snapshot và replay ra sao,
3. UI và transport còn bị ngăn không cho vượt qua nó hay không.

### 12. Tham chiếu chính

- [README.md](/e:/Documents/DO_AN/CBI_Railway_Signal/README.md:1) cho tổng quan dự án, runtime command, và luồng làm việc cho lập trình viên.
- [INTERLOCKING_PRINCIPLES.md](/e:/Documents/DO_AN/CBI_Railway_Signal/INTERLOCKING_PRINCIPLES.md:1) cho nguyên lý tín hiệu và ánh xạ sang codebase.
- `tests/test_runtime_workspace.py` như ví dụ thực thi cho route lifecycle, snapshot round-trip, và hành vi runtime liên quan SmartIO.

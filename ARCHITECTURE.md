# CBI Railway Signal System Architecture

This document describes the current architecture of the `CBI_Railway_Signal` application based on the codebase in this repository.

Goals:
- Clarify boundaries between packages and layers.
- Describe the end-to-end data flow from layout to runtime to journaling to SmartIO.
- Capture command execution, journaling, and recovery rules.
- Document protocol handling, safety enforcement, and simulation semantics.

## 1. System Layers

The system is organized into five layers:
1. Pure domain and compiler logic (`core/domain`, `core/compiler`).
2. Runtime engine layer (`kernel`).
3. Stateful runtime session and application layer (`runtime`, `runtime/application`).
4. Simulation helpers (`simulation`).
5. Integration and presentation layer (`integration`, `ui`, with `infrastructure` support).

High-level flow (command path):

```text
User / SmartIO
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
RouteDispatcher / LockingEngine / SafetyMonitor
    |
    v
RailwayTopology + Route + Train
```

Simulation tick path (only when `step_runtime` is invoked):

```text
UI action (step_runtime)
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
RailwayTopology + Route + Train
```

## 2. Bounded Contexts and Responsibilities

### 2.1 layout_context

Responsibilities:
- Create, edit, and validate station layouts.
- Manage static topology before entering runtime.
- Provide layout payloads for UI and SmartIO snapshots.

Related modules:
- `runtime/specific_application/editor_service.py`
- `runtime/specific_application/station_layout.py`
- `ui/views/canvas_editor_view.py`
- `core/domain/model/topology.py`
- `runtime/application/serialization/layout_payload_serializer.py`

Inputs and outputs:
- Input: canvas editor actions, `layout.json`.
- Output: `RailwayTopology`, layout payloads for UI and SmartIO.

### 2.2 interlocking_compile_context

Responsibilities:
- Compile topology into a deterministic interlocking specification.
- Generate route candidates and conflict, flank, and overlap rules.
- Produce artifacts that can be saved and reloaded.

Related modules:
- `core/compiler/route_compiler.py`
- `core/compiler/interlocking_table.py`
- `core/compiler/spec_models.py`
- `runtime/application_service.py`

Inputs and outputs:
- Input: `RailwayTopology`, overlap parameters.
- Output: `InterlockingSpec`, interlocking table rows, `interlocking_spec.json`.

### 2.3 runtime_control_context

Responsibilities:
- Set routes, cancel routes, and emergency release routes.
- Enforce interlocking on sections, points, and signals.
- Update occupancy, timed release, and approach locking.
- Monitor safety and trigger fail-safe STOP when needed.

Related modules:
- `kernel/route_dispatcher/route_engine.py`
- `kernel/route_dispatcher/route_dispatcher.py`
- `kernel/locking_engine/locking_engine.py`
- `kernel/occupancy_engine/occupancy_reconciler.py`
- `kernel/safety_engine/safety_monitor.py`
- `kernel/locking_engine/timed_release.py`
- `kernel/locking_engine/sequence_locking.py`
- `core/domain/lifecycle/approach_locking.py`

Safety rules:
- Direct writes to `locked_by`, `signal.aspect`, or `signal.route_id` are blocked.
- All state mutations go through validated command boundaries.
- Unsafe conditions force all signals to STOP.

### 2.4 simulation_workspace_context

Responsibilities:
- Drive time-stepped simulation for the active runtime session.
- Create and update trains and advance simulation ticks.
- Hydrate simulation-facing state through the runtime session boundary.

Related modules:
- `runtime/runtime_cycle.py`
- `simulation/train_simulator.py`
- `simulation/environment_simulator.py`
- `runtime/runtime_controller.py`
- `runtime/read_model.py`

Architectural meaning:
- `RuntimeSession` is the single stateful runtime session in the desktop app.
- `SimulationEngine` advances train movement and time-based behavior.
- `runtime/` remains the execution layer for runtime use cases.

### 2.5 runtime_orchestration_context

Responsibilities:
- Manage runtime session lifecycle per workspace.
- Accept commands from UI or SmartIO, journal them, execute them, and emit events.
- Create checkpoint snapshots and restore on restart.
- Provide runtime health for UI and transport.

Related modules:
- `runtime/workspace_service.py`
- `infrastructure/event_store.py`
- `runtime/profile.py`

Architectural meaning:
- `RuntimeWorkspaceService` is the runtime facade and transaction boundary.
- `RuntimeSession` does not journal on its own.
- UI and transport do not mutate runtime state directly.

### 2.6 integration_context

Responsibilities:
- Connect to SmartIO over WebSocket.
- Validate envelopes, parse messages, and handle reconnect.
- Translate SmartIO events into typed runtime commands.
- Send `command_result`, `runtime_event`, and `runtime_snapshot` outward.

Related modules:
- `integration/smartio_adapter/protocol.py`
- `integration/smartio_adapter/runtime_bridge.py`
- `integration/smartio_adapter/qt_ws_client.py`
- `ui/controllers/runtime_workspace_controller.py`

Architectural meaning:
- SmartIO does not directly manipulate topology or locking engines.
- All changes pass through `RuntimeWorkspaceService.submit_command(...)`.
- The bridge normalizes protocol and maps errors to `SmartIOProtocolError`.

### 2.7 presentation_context

Responsibilities:
- Manage Design, Simulation, and Runtime modes.
- Bind user actions to application and runtime services.
- Present read models, runtime health, and SmartIO status.

Related modules:
- `ui/controllers/main_window_controller.py`
- `ui/controllers/runtime_workspace_controller.py`
- `ui/controllers/workspace_state_coordinator.py`
- `ui/presenters/route_presenter.py`
- `ui/views/main_window_view.py`
- `ui/views/canvas_editor_view.py`

## 3. Core Runtime Components

### 3.1 RailwayTopology

`RailwayTopology` (see `core/domain/model/topology.py`) manages:
- Graph nodes and edges.
- Signals, sections, and points.
- Topology validation.
- JSON import and export.

It is the structural source of truth across design, compile, simulation, and runtime.

### 3.2 RuntimeSession

`RuntimeSession` (see `runtime/runtime_controller.py`) initializes and coordinates engines:
- `RouteEngine`, `LockingEngine`, `RouteDispatcher`.
- `OccupancyReconciler`, `SafetyMonitor`.
- `RuntimeCommandHandler`, `RuntimeTrainLifecycle`, `RuntimeSnapshotHydrator`.
- `SimulationEngine`.

Runtime commands include:
- `set_route`, `cancel_route`.
- `set_section_occupied`, `set_point_position`.
- `upsert_train`, `remove_train`.
- `hydrate_snapshot`, `step`.

### 3.3 SimulationEngine

`SimulationEngine` (see `runtime/runtime_cycle.py`) implements time-stepped behavior:
- Increments `tick` each step.
- Updates time locking before and after train movement.
- Steps each train along its active route.
- Runs `SafetyMonitor.detect_unsafe_conditions(...)`.
- On unsafe conditions, forces all signals to STOP and raises `RuntimeError`.

### 3.4 RuntimeWorkspaceService

`RuntimeWorkspaceService` (see `runtime/workspace_service.py`) is the command boundary for UI and SmartIO:
- Creates or restores a runtime session.
- Journals commands, emits events, and checkpoints snapshots.
- Enforces idempotency and stream ordering (`stream_seq`).
- Exposes runtime view state and health.

### 3.5 RuntimeJournal and Recovery

`RuntimeJournal` and `RuntimeRecoveryService` (see `infrastructure/event_store.py`) manage append-only JSONL streams:
- `runtime_commands.jsonl`
- `runtime_events.jsonl`
- `runtime_snapshots.jsonl`

Recovery algorithm:
1. Load the latest snapshot.
2. Compare `topology_revision`.
3. Hydrate the session from snapshot.
4. Replay events with `command_status == "applied"` after snapshot `stream_seq`.

If recovery fails or topology revisions mismatch, the session becomes degraded and may be forced to STOP.

## 4. Command Flow and Journaling

`RuntimeWorkspaceService.submit_command(...)` is the canonical entry point for command processing.

Command execution steps:
1. Normalize `source_id`, `command_id`, and payload.
2. Return a cached result for duplicate (`source_id`, `command_id`) pairs.
3. Append `RuntimeCommand` to `runtime_commands.jsonl`.
4. Execute the command handler and capture result or error.
5. Increment `stream_seq` and append a `RuntimeEvent` to `runtime_events.jsonl`.
6. Cache the `RuntimeCommandResult` and update runtime health metadata.
7. Optionally checkpoint a snapshot based on `runtime_snapshot_checkpoint_interval`.

Event payloads include a summarized result for faster external consumption.

## 5. Operational Flows

### 5.1 Layout to Runtime

1. UI/editor creates or updates `RailwayTopology`.
2. `GenericApplicationService` loads/saves topology and compiles interlocking specs.
3. Entering Simulation or Runtime calls `RuntimeWorkspaceService.ensure_session(topology)`.
4. Recovery restores snapshots and replays applied events.
5. UI renders `RuntimeViewState` from `runtime/read_model.py`.

### 5.2 Set Route Flow

```text
UI or SmartIO command
-> RuntimeWorkspaceService.submit_command(kind="set_route")
-> SetOrReuseRouteUseCase
-> RuntimeSession.set_route(...)
-> RouteDispatcher + LockingEngine
-> RuntimeEvent(applied/rejected)
-> Snapshot checkpoint if interval reached
-> Updated RuntimeViewState
```

### 5.3 Step Runtime Flow

```text
UI action
-> RuntimeWorkspaceService.submit_command(kind="step_runtime")
-> RuntimeSession.step()
-> SimulationEngine.step()
-> SafetyMonitor.detect_unsafe_conditions()
-> RuntimeEvent(applied/rejected)
-> Updated RuntimeViewState and tick
```

### 5.4 Snapshot Publish Flow

```text
SmartIO coordinator heartbeat
-> drain_pending_runtime_events()
-> send runtime_event envelopes
-> checkpoint_runtime_snapshot()
-> attach layout payload
-> send runtime_snapshot envelope
```

## 6. SmartIO Protocol Handling and Safety

SmartIO envelope schema:

```json
{
  "type": "command | state_update | runtime_snapshot | runtime_event | command_result | hello | error | ack",
  "payload": {},
  "ts": 0
}
```

Protocol handling rules:
- `command` envelopes are translated into runtime commands.
- `state_update` envelopes are translated into `apply_state_update` commands.
- Envelopes are validated before processing.

Safety enforcement:
- Direct updates to `locked_by` are rejected for sections and points.
- Direct updates to `signal.aspect` or `signal.route_id` are rejected.
- Unsafe runtime conditions trigger fail-safe STOP.

Transport acceptance by mode:
- Runtime mode accepts SmartIO commands and publishes snapshots.
- Simulation mode accepts SmartIO commands only for local endpoints.

## 7. Data Artifacts and Metadata

Design artifacts:
- `layout.json` for station topology.
- `interlocking_spec.json` for compiled routes and conflicts.

Runtime artifacts:
- `runtime_snapshot.json` for standalone snapshots.
- `runtime_commands.jsonl`, `runtime_events.jsonl`, `runtime_snapshots.jsonl` for journaling.

Key metadata fields:
- `stream_seq` for event ordering.
- `topology_revision` for snapshot and replay safety.
- `snapshot_version` for schema evolution.

## 8. Dependency Rules

- `core/` must not depend on `ui/`, `runtime/`, `simulation/`, or `integration/`.
- `kernel/` may depend on `core/domain/` and `infrastructure/clocks/`.
- `runtime/` may depend on `core/`, `kernel/`, `simulation/`, and `infrastructure/`.
- `simulation/` may depend on `core/` and collaborate with `runtime/`.
- `integration/` should communicate only through application-level services and ports.
- `ui/` should orchestrate and present, not contain interlocking rules.

## 9. Extension Guidelines

1. Add new commands through `RuntimeWorkspaceService.submit_command(...)`.
2. Place business logic in `runtime/application/use_cases/` or `kernel/`.
3. Bump `snapshot_version` if old events cannot restore state.
4. Keep external integrations behind an anti-corruption layer like `SmartIORuntimeBridge`.
5. Enforce new safety rules inside engines or monitors, not in UI.

## 10. Key References

- [main.py](main.py)
- [runtime/workspace_service.py](runtime/workspace_service.py)
- [runtime/runtime_controller.py](runtime/runtime_controller.py)
- [runtime/runtime_cycle.py](runtime/runtime_cycle.py)
- [infrastructure/event_store.py](infrastructure/event_store.py)
- [integration/smartio_adapter/runtime_bridge.py](integration/smartio_adapter/runtime_bridge.py)
- [ui/controllers/runtime_workspace_controller.py](ui/controllers/runtime_workspace_controller.py)

## Tiếng Việt

Tài liệu này mô tả kiến trúc hiện tại của ứng dụng `CBI_Railway_Signal` dựa trên code trong repository.

Mục tiêu:
- Làm rõ ranh giới giữa các package và lớp.
- Mô tả luồng dữ liệu từ layout đến runtime đến journaling đến SmartIO.
- Nêu quy tắc thực thi command, journaling, và recovery.
- Tài liệu hóa xử lý protocol, thực thi an toàn, và hành vi mô phỏng.

### 1. Các lớp hệ thống

Hệ thống được tổ chức thành 5 lớp:
1. Logic miền và compiler thuần (`core/domain`, `core/compiler`).
2. Lớp engine runtime (`kernel`).
3. Lớp runtime session và application (`runtime`, `runtime/application`).
4. Helper mô phỏng (`simulation`).
5. Lớp tích hợp và trình bày (`integration`, `ui`, có hỗ trợ từ `infrastructure`).

Luồng tổng quát (đường lệnh):

```text
User / SmartIO
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
RouteDispatcher / LockingEngine / SafetyMonitor
    |
    v
RailwayTopology + Route + Train
```

Luồng tick mô phỏng (chỉ khi gọi `step_runtime`):

```text
UI action (step_runtime)
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
RailwayTopology + Route + Train
```

### 2. Bounded contexts và trách nhiệm

#### 2.1 layout_context

Trách nhiệm:
- Tạo, chỉnh sửa, và kiểm tra layout ga.
- Quản lý topology tĩnh trước khi vào runtime.
- Cung cấp layout payload cho UI và SmartIO snapshot.

Module liên quan:
- `runtime/specific_application/editor_service.py`
- `runtime/specific_application/station_layout.py`
- `ui/views/canvas_editor_view.py`
- `core/domain/model/topology.py`
- `runtime/application/serialization/layout_payload_serializer.py`

Đầu vào và đầu ra:
- Đầu vào: thao tác canvas editor, `layout.json`.
- Đầu ra: `RailwayTopology`, layout payload cho UI và SmartIO.

#### 2.2 interlocking_compile_context

Trách nhiệm:
- Biên dịch topology thành đặc tả liên khóa xác định.
- Sinh route candidates và quy tắc conflict, flank, overlap.
- Tạo artifact có thể lưu và tải lại.

Module liên quan:
- `core/compiler/route_compiler.py`
- `core/compiler/interlocking_table.py`
- `core/compiler/spec_models.py`
- `runtime/application_service.py`

Đầu vào và đầu ra:
- Đầu vào: `RailwayTopology`, tham số overlap.
- Đầu ra: `InterlockingSpec`, bảng interlocking, `interlocking_spec.json`.

#### 2.3 runtime_control_context

Trách nhiệm:
- Đặt route, hủy route, và emergency release route.
- Thực thi liên khóa trên sections, points, và signals.
- Cập nhật occupancy, timed release, và approach locking.
- Giám sát an toàn và kích hoạt fail-safe STOP khi cần.

Module liên quan:
- `kernel/route_dispatcher/route_engine.py`
- `kernel/route_dispatcher/route_dispatcher.py`
- `kernel/locking_engine/locking_engine.py`
- `kernel/occupancy_engine/occupancy_reconciler.py`
- `kernel/safety_engine/safety_monitor.py`
- `kernel/locking_engine/timed_release.py`
- `kernel/locking_engine/sequence_locking.py`
- `core/domain/lifecycle/approach_locking.py`

Quy tắc an toàn:
- Chặn ghi trực tiếp vào `locked_by`, `signal.aspect`, hoặc `signal.route_id`.
- Mọi thay đổi trạng thái phải qua command boundary có kiểm tra.
- Khi phát hiện điều kiện unsafe, mọi signal bị đưa về STOP.

#### 2.4 simulation_workspace_context

Trách nhiệm:
- Vận hành mô phỏng theo tick cho runtime session đang hoạt động.
- Tạo và cập nhật trains và tiến hành simulation ticks.
- Hydrate trạng thái mô phỏng qua runtime session boundary.

Module liên quan:
- `runtime/runtime_cycle.py`
- `simulation/train_simulator.py`
- `simulation/environment_simulator.py`
- `runtime/runtime_controller.py`
- `runtime/read_model.py`

Ý nghĩa kiến trúc:
- `RuntimeSession` là runtime session stateful duy nhất trong desktop app.
- `SimulationEngine` điều khiển train movement và time-based behavior.
- `runtime/` vẫn là lớp thực thi use case runtime.

#### 2.5 runtime_orchestration_context

Trách nhiệm:
- Quản lý vòng đời runtime session theo workspace.
- Nhận command từ UI hoặc SmartIO, journal, thực thi, và phát event.
- Tạo checkpoint snapshot và phục hồi khi khởi động lại.
- Cung cấp runtime health cho UI và transport.

Module liên quan:
- `runtime/workspace_service.py`
- `infrastructure/event_store.py`
- `runtime/profile.py`

Ý nghĩa kiến trúc:
- `RuntimeWorkspaceService` là facade và ranh giới transaction.
- `RuntimeSession` không tự journal.
- UI và transport không được sửa state trực tiếp.

#### 2.6 integration_context

Trách nhiệm:
- Kết nối SmartIO qua WebSocket.
- Validate envelope, parse message, và xử lý reconnect.
- Chuyển SmartIO events thành runtime commands có kiểu.
- Gửi `command_result`, `runtime_event`, và `runtime_snapshot` ra ngoài.

Module liên quan:
- `integration/smartio_adapter/protocol.py`
- `integration/smartio_adapter/runtime_bridge.py`
- `integration/smartio_adapter/qt_ws_client.py`
- `ui/controllers/runtime_workspace_controller.py`

Ý nghĩa kiến trúc:
- SmartIO không thao tác trực tiếp vào topology hoặc locking engines.
- Mọi thay đổi đi qua `RuntimeWorkspaceService.submit_command(...)`.
- Bridge chuẩn hóa protocol và ánh xạ lỗi về `SmartIOProtocolError`.

#### 2.7 presentation_context

Trách nhiệm:
- Quản lý mode Design, Simulation, và Runtime.
- Liên kết hành động người dùng với application và runtime services.
- Trình bày read model, runtime health, và trạng thái SmartIO.

Module liên quan:
- `ui/controllers/main_window_controller.py`
- `ui/controllers/runtime_workspace_controller.py`
- `ui/controllers/workspace_state_coordinator.py`
- `ui/presenters/route_presenter.py`
- `ui/views/main_window_view.py`
- `ui/views/canvas_editor_view.py`

### 3. Thành phần runtime cốt lõi

#### 3.1 RailwayTopology

`RailwayTopology` (xem `core/domain/model/topology.py`) quản lý:
- Graph nodes và edges.
- Signals, sections, và points.
- Topology validation.
- Import và export JSON.

Đây là nguồn cấu trúc chuẩn xuyên suốt thiết kế, biên dịch, mô phỏng, và runtime.

#### 3.2 RuntimeSession

`RuntimeSession` (xem `runtime/runtime_controller.py`) khởi tạo và điều phối các engine:
- `RouteEngine`, `LockingEngine`, `RouteDispatcher`.
- `OccupancyReconciler`, `SafetyMonitor`.
- `RuntimeCommandHandler`, `RuntimeTrainLifecycle`, `RuntimeSnapshotHydrator`.
- `SimulationEngine`.

Các runtime command gồm:
- `set_route`, `cancel_route`.
- `set_section_occupied`, `set_point_position`.
- `upsert_train`, `remove_train`.
- `hydrate_snapshot`, `step`.

#### 3.3 SimulationEngine

`SimulationEngine` (xem `runtime/runtime_cycle.py`) thực hiện hành vi theo tick:
- Tăng `tick` mỗi bước.
- Cập nhật time locking trước và sau khi train di chuyển.
- Step mỗi train trên route đang hoạt động.
- Chạy `SafetyMonitor.detect_unsafe_conditions(...)`.
- Khi unsafe, ép mọi signal về STOP và ném `RuntimeError`.

#### 3.4 RuntimeWorkspaceService

`RuntimeWorkspaceService` (xem `runtime/workspace_service.py`) là command boundary cho UI và SmartIO:
- Tạo hoặc phục hồi runtime session.
- Journal command, phát event, và checkpoint snapshot.
- Thực thi idempotency và stream ordering (`stream_seq`).
- Cung cấp runtime view state và health.

#### 3.5 RuntimeJournal và Recovery

`RuntimeJournal` và `RuntimeRecoveryService` (xem `infrastructure/event_store.py`) quản lý các JSONL append-only:
- `runtime_commands.jsonl`
- `runtime_events.jsonl`
- `runtime_snapshots.jsonl`

Thuật toán recovery:
1. Tải snapshot mới nhất.
2. So sánh `topology_revision`.
3. Hydrate session từ snapshot.
4. Replay event với `command_status == "applied"` sau `stream_seq` của snapshot.

Nếu recovery thất bại hoặc topology revision không khớp, session bị degraded và có thể bị ép STOP.

### 4. Luồng command và journaling

`RuntimeWorkspaceService.submit_command(...)` là điểm vào chuẩn cho xử lý command.

Các bước thực thi command:
1. Chuẩn hóa `source_id`, `command_id`, và payload.
2. Trả kết quả cache cho cặp (`source_id`, `command_id`) trùng.
3. Append `RuntimeCommand` vào `runtime_commands.jsonl`.
4. Thực thi command và ghi kết quả hoặc lỗi.
5. Tăng `stream_seq` và append `RuntimeEvent` vào `runtime_events.jsonl`.
6. Cache `RuntimeCommandResult` và cập nhật metadata runtime health.
7. Checkpoint snapshot theo `runtime_snapshot_checkpoint_interval`.

Event payload chứa bản tóm tắt kết quả để tiêu thụ nhanh hơn từ bên ngoài.

### 5. Luồng vận hành

#### 5.1 Từ layout đến runtime

1. UI/editor tạo hoặc cập nhật `RailwayTopology`.
2. `GenericApplicationService` load/save topology và compile interlocking spec.
3. Khi vào Simulation hoặc Runtime, gọi `RuntimeWorkspaceService.ensure_session(topology)`.
4. Recovery phục hồi snapshot và replay event đã áp dụng.
5. UI render `RuntimeViewState` từ `runtime/read_model.py`.

#### 5.2 Luồng đặt route

```text
UI hoặc SmartIO command
-> RuntimeWorkspaceService.submit_command(kind="set_route")
-> SetOrReuseRouteUseCase
-> RuntimeSession.set_route(...)
-> RouteDispatcher + LockingEngine
-> RuntimeEvent(applied/rejected)
-> Snapshot checkpoint nếu đến chu kỳ
-> RuntimeViewState cập nhật
```

#### 5.3 Luồng step runtime

```text
UI action
-> RuntimeWorkspaceService.submit_command(kind="step_runtime")
-> RuntimeSession.step()
-> SimulationEngine.step()
-> SafetyMonitor.detect_unsafe_conditions()
-> RuntimeEvent(applied/rejected)
-> RuntimeViewState và tick cập nhật
```

#### 5.4 Luồng publish snapshot

```text
SmartIO coordinator heartbeat
-> drain_pending_runtime_events()
-> gửi runtime_event envelopes
-> checkpoint_runtime_snapshot()
-> gắn layout payload
-> gửi runtime_snapshot envelope
```

### 6. Xử lý protocol SmartIO và an toàn

Schema envelope SmartIO:

```json
{
  "type": "command | state_update | runtime_snapshot | runtime_event | command_result | hello | error | ack",
  "payload": {},
  "ts": 0
}
```

Quy tắc xử lý protocol:
- Envelope `command` được chuyển thành runtime command.
- Envelope `state_update` được chuyển thành lệnh `apply_state_update`.
- Envelope được validate trước khi xử lý.

Thực thi an toàn:
- Chặn cập nhật trực tiếp `locked_by` cho sections và points.
- Chặn cập nhật trực tiếp `signal.aspect` hoặc `signal.route_id`.
- Điều kiện unsafe kích hoạt fail-safe STOP.

Chấp nhận transport theo mode:
- Runtime mode nhận SmartIO commands và publish snapshots.
- Simulation mode chỉ nhận SmartIO commands với endpoint local.

### 7. Artifact dữ liệu và metadata

Artifact thiết kế:
- `layout.json` cho topology ga.
- `interlocking_spec.json` cho route/conflict đã compile.

Artifact runtime:
- `runtime_snapshot.json` cho snapshot độc lập.
- `runtime_commands.jsonl`, `runtime_events.jsonl`, `runtime_snapshots.jsonl` cho journaling.

Trường metadata chính:
- `stream_seq` cho thứ tự event.
- `topology_revision` để an toàn snapshot và replay.
- `snapshot_version` cho tiến hóa schema.

### 8. Quy tắc phụ thuộc

- `core/` không được phụ thuộc `ui/`, `runtime/`, `simulation/`, hoặc `integration/`.
- `kernel/` có thể phụ thuộc `core/domain/` và `infrastructure/clocks/`.
- `runtime/` có thể phụ thuộc `core/`, `kernel/`, `simulation/`, và `infrastructure/`.
- `simulation/` có thể phụ thuộc `core/` và cộng tác với `runtime/`.
- `integration/` chỉ nên giao tiếp qua application-level services và ports.
- `ui/` chỉ nên điều phối và trình bày, không đặt luật liên khóa trong UI.

### 9. Hướng dẫn mở rộng

1. Thêm command mới qua `RuntimeWorkspaceService.submit_command(...)`.
2. Đặt logic nghiệp vụ trong `runtime/application/use_cases/` hoặc `kernel/`.
3. Tăng `snapshot_version` nếu event cũ không thể phục hồi state.
4. Giữ tích hợp ngoài qua anti-corruption layer như `SmartIORuntimeBridge`.
5. Thực thi quy tắc an toàn mới trong engine hoặc monitor, không phải UI.

### 10. Tham chiếu chính

- [main.py](main.py)
- [runtime/workspace_service.py](runtime/workspace_service.py)
- [runtime/runtime_controller.py](runtime/runtime_controller.py)
- [runtime/runtime_cycle.py](runtime/runtime_cycle.py)
- [infrastructure/event_store.py](infrastructure/event_store.py)
- [integration/smartio_adapter/runtime_bridge.py](integration/smartio_adapter/runtime_bridge.py)
- [ui/controllers/runtime_workspace_controller.py](ui/controllers/runtime_workspace_controller.py)

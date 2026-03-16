# CBI Railway Signal

Desktop application for CBI interlocking simulation, station layout editing, and runtime orchestration.

## Overview

`CBI_Railway_Signal` combines layout design, interlocking compilation, runtime orchestration, and SmartIO integration into a single PyQt6 desktop application.

Core capabilities:
- Design and validate station layouts (signals, sections, points, topology graph).
- Compile interlocking rules and route specifications from the layout.
- Orchestrate a stateful runtime session with journaling and recovery.
- Simulate train movement and enforce safety constraints.
- Integrate with SmartIO over WebSocket for external control and telemetry.

The desktop entrypoint is [main.py](main.py).

## Architecture Map

The repository is organized into clear layers with explicit responsibilities:
- `core/` - Pure domain models and compiler logic.
- `kernel/` - Runtime engines for routing, locking, occupancy, and safety.
- `runtime/` - Stateful session, application use cases, read models, and workspace orchestration.
- `simulation/` - Simulation helpers and snapshot hydration.
- `infrastructure/` - Persistence adapters and clocks.
- `integration/` - SmartIO protocol handling and runtime bridge.
- `ui/` - PyQt6 controllers, presenters, and views.

High-level flow (command path):

```text
User / SmartIO
    |
    v
UI Controllers / SmartIO Coordinator
    |
    v
RuntimeWorkspaceService
    |
    v
RuntimeSession
    |
    v
RouteDispatcher / LockingEngine / SafetyMonitor
    |
    v
RailwayTopology + Routes + Trains
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
  command_bus.py        Runtime command gateway
  read_model.py         Runtime-facing view state
  runtime_controller.py Stateful runtime session
  runtime_cycle.py      Simulation tick engine
  workspace_service.py  Runtime orchestration facade
  profile.py            Runtime profile defaults
  application_service.py

simulation/             Train lifecycle and snapshot hydration helpers
infrastructure/         Persistence adapters and clocks
integration/            SmartIO protocol and bridge code
ui/                     PyQt controllers, presenters, and views
tests/                  Automated tests
data/                   Sample layouts and runtime data
```

## Key Runtime Concepts

### RailwayTopology

`RailwayTopology` (see `core/domain/model/topology.py`) is the structural source of truth for the station model. It represents nodes, edges, signals, sections, and points. The same topology object is reused across editing, compilation, simulation, runtime, and serialization.

### RuntimeSession

`RuntimeSession` (see `runtime/runtime_controller.py`) owns mutable runtime state and delegates behavior to engines. It exposes methods such as `set_route`, `cancel_route`, `set_section_occupied`, `set_point_position`, `upsert_train`, `remove_train`, `hydrate_snapshot`, and `step`.

### SimulationEngine

`SimulationEngine` (see `runtime/runtime_cycle.py`) is responsible for time-stepped behavior. Each tick updates time locking, advances trains, runs safety checks, and can trigger fail-safe STOP.

### RuntimeWorkspaceService

`RuntimeWorkspaceService` (see `runtime/workspace_service.py`) is the orchestration boundary used by both UI and SmartIO. It creates or restores a session, journals commands/events/snapshots, enforces idempotency, and provides runtime view state and health.

### RuntimeJournal and Recovery

`RuntimeJournal` and `RuntimeRecoveryService` (see `infrastructure/event_store.py`) store append-only `runtime_commands.jsonl`, `runtime_events.jsonl`, and `runtime_snapshots.jsonl` and restore sessions by applying the latest snapshot then replaying applied events.

## Runtime Command Surface

All external interactions should go through `RuntimeWorkspaceService.submit_command(...)` or higher-level helpers on the same service.

| Command kind | Purpose | Source |
| --- | --- | --- |
| `set_route` | Compute and lock a route for entry/exit signals. | UI, SmartIO command
| `cancel_active_routes` | Cancel all active routes. | UI
| `emergency_release_active_routes` | Force-release all active routes. | UI
| `start_route_simulation` | Prepare route and train for simulation playback. | UI
| `set_section_occupied` | Manual occupancy override for a section. | UI
| `set_point_position` | Move a point through the locking engine. | UI, SmartIO command
| `upsert_train` | Create or update a train instance. | UI, SmartIO state_update
| `remove_train` | Remove a train instance. | UI, SmartIO state_update
| `step_runtime` | Advance simulation by one tick. | UI
| `apply_state_update` | Apply SmartIO state updates for sections, points, trains. | SmartIO state_update
| `hydrate_snapshot` | Apply a runtime snapshot payload. | SmartIO runtime_snapshot

SmartIO `state_update` envelopes are converted into `apply_state_update` commands by the SmartIO bridge.

## Modes and Capabilities

Mode permissions are defined in `runtime/application/mode_policy/policy.py`.

| Mode | Can edit layout | Can manual override | Can set route | Can cancel route | Can start simulation |
| --- | --- | --- | --- | --- | --- |
| `DESIGN_LAYOUT` | Yes | Yes | No | No | No |
| `SIMULATION` | No | Yes | Yes | Yes | Yes |
| `RUNTIME` | No | No | Yes | Yes | No |

## Configuration

Defaults live in `runtime/profile.py` (`GenericApplicationProfile`). Key settings include:

| Field | Default | Purpose |
| --- | --- | --- |
| `time_lock_seconds` | `2.0` | Approach time lock duration.
| `default_overlap_length` | `1` | Default overlap length when computing routes.
| `overlap_release_seconds` | `2.0` | Overlap release delay.
| `smart_io_ws_url` | `wss://cbi-smartio.onrender.com/smartio` | SmartIO WebSocket endpoint.
| `smart_io_snapshot_heartbeat_seconds` | `5.0` | Snapshot publish interval.
| `smart_io_runtime_stale_seconds` | `15.0` | Transport stale threshold.
| `runtime_journal_dir` | `data/runtime_journal` | Journal directory.
| `runtime_snapshot_checkpoint_interval` | `1` | Snapshot checkpoint cadence (per stream_seq).

These defaults can be overridden by constructing `GenericApplicationProfile` differently in application code.

## Getting Started

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -U pip
python -m pip install PyQt6 pytest
```

## Running the Application

```bash
python main.py
```

`main.py` creates a `QApplication`, builds a `GenericApplicationProfile`, and opens the main window.

## Running Tests

```bash
python -m pytest
```

```bash
python -m pytest tests/test_runtime_workspace.py
```

## Data and Persistence

Static layouts and runtime artifacts are stored under `data/`.

Key locations:
- `data/station_layout/` for sample layouts.
- `data/_smartio_local/` for local SmartIO payload samples.
- `data/runtime_journal/` for runtime command/event/snapshot JSONL streams.

The runtime journal files are:
- `runtime_commands.jsonl`
- `runtime_events.jsonl`
- `runtime_snapshots.jsonl`

## SmartIO Integration

SmartIO integration lives under `integration/smartio_adapter/` and is coordinated by `ui/controllers/runtime_workspace_controller.py`.

Key behaviors:
- WebSocket envelopes are validated before processing.
- `command` envelopes are converted into runtime commands.
- `state_update` envelopes are converted into `apply_state_update` commands.
- Direct writes to interlocking fields such as `locked_by`, `signal.aspect`, or `signal.route_id` are blocked.

## Additional Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md)
- [ARCHITECTURE.vi.md](ARCHITECTURE.vi.md)

## Tiếng Việt

### Tổng quan

`CBI_Railway_Signal` kết hợp thiết kế layout, biên dịch liên khóa, điều phối runtime, và tích hợp SmartIO trong một ứng dụng desktop PyQt6.

Năng lực chính:
- Thiết kế và kiểm tra layout ga (signal, section, point, đồ thị topology).
- Biên dịch các quy tắc liên khóa và đặc tả route từ layout.
- Điều phối một runtime session stateful với journaling và phục hồi.
- Mô phỏng chuyển động tàu và thực thi các ràng buộc an toàn.
- Tích hợp SmartIO qua WebSocket cho điều khiển và telemetry bên ngoài.

Điểm vào của ứng dụng desktop là [main.py](main.py).

### Bản đồ kiến trúc

Repository được tổ chức theo các lớp với trách nhiệm rõ ràng:
- `core/` - Mô hình miền thuần và logic compiler.
- `kernel/` - Các engine runtime cho routing, locking, occupancy, và safety.
- `runtime/` - Runtime session, use case ứng dụng, read model, và orchestration.
- `simulation/` - Helper mô phỏng và snapshot hydration.
- `infrastructure/` - Persistence adapters và clocks.
- `integration/` - Xử lý protocol SmartIO và runtime bridge.
- `ui/` - Controller, presenter, và view PyQt6.

Luồng tổng quát (đường lệnh):

```text
User / SmartIO
    |
    v
UI Controllers / SmartIO Coordinator
    |
    v
RuntimeWorkspaceService
    |
    v
RuntimeSession
    |
    v
RouteDispatcher / LockingEngine / SafetyMonitor
    |
    v
RailwayTopology + Routes + Trains
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
RailwayTopology + Routes + Trains
```

### Cấu trúc dự án

```text
core/
  compiler/             Route compiler và sinh đặc tả liên khóa
  domain/               Topology, policy, và lifecycle rules

kernel/
  locking_engine/       Logic locking và release route
  occupancy_engine/     Reconcile occupancy
  route_dispatcher/     Tìm và dispatch route
  safety_engine/        Kiểm tra an toàn và fail-safe

runtime/
  application/          Use case ứng dụng và helper serialization
  specific_application/ Logic editor và layout theo ga
  command_bus.py        Runtime command gateway
  read_model.py         Runtime-facing view state
  runtime_controller.py Runtime session stateful
  runtime_cycle.py      Engine tick mô phỏng
  workspace_service.py  Runtime orchestration facade
  profile.py            Runtime profile mặc định
  application_service.py

simulation/             Helper train lifecycle và snapshot hydration
infrastructure/         Persistence adapters và clocks
integration/            SmartIO protocol và bridge code
ui/                     Controller, presenter, và view PyQt
tests/                  Kiểm thử tự động
data/                   Layout mẫu và runtime data
```

### Các khái niệm runtime chính

#### RailwayTopology

`RailwayTopology` (xem `core/domain/model/topology.py`) là nguồn cấu trúc chuẩn của mô hình nhà ga. Nó đại diện cho node, edge, signal, section, và point. Cùng một topology được tái sử dụng xuyên suốt editing, compilation, simulation, runtime, và serialization.

#### RuntimeSession

`RuntimeSession` (xem `runtime/runtime_controller.py`) sở hữu trạng thái runtime có thể thay đổi và ủy quyền hành vi cho các engine. Nó cung cấp các phương thức như `set_route`, `cancel_route`, `set_section_occupied`, `set_point_position`, `upsert_train`, `remove_train`, `hydrate_snapshot`, và `step`.

#### SimulationEngine

`SimulationEngine` (xem `runtime/runtime_cycle.py`) chịu trách nhiệm hành vi theo tick. Mỗi tick cập nhật time locking, di chuyển tàu, chạy kiểm tra an toàn, và có thể kích hoạt fail-safe STOP.

#### RuntimeWorkspaceService

`RuntimeWorkspaceService` (xem `runtime/workspace_service.py`) là ranh giới orchestration dùng bởi cả UI và SmartIO. Nó tạo hoặc phục hồi session, journal command/event/snapshot, thực thi idempotency, và cung cấp runtime view state cùng health.

#### RuntimeJournal và phục hồi

`RuntimeJournal` và `RuntimeRecoveryService` (xem `infrastructure/event_store.py`) lưu các file append-only `runtime_commands.jsonl`, `runtime_events.jsonl`, và `runtime_snapshots.jsonl`, rồi phục hồi session bằng cách áp dụng snapshot mới nhất và replay các event đã áp dụng.

### Bề mặt lệnh runtime

Mọi tương tác từ bên ngoài nên đi qua `RuntimeWorkspaceService.submit_command(...)` hoặc các helper cao hơn trên cùng service.

| Loại lệnh | Mục đích | Nguồn |
| --- | --- | --- |
| `set_route` | Tính toán và khóa route cho cặp signal vào/ra. | UI, lệnh SmartIO
| `cancel_active_routes` | Hủy toàn bộ route đang hoạt động. | UI
| `emergency_release_active_routes` | Giải phóng khẩn cấp toàn bộ route đang hoạt động. | UI
| `start_route_simulation` | Chuẩn bị route và tàu cho mô phỏng. | UI
| `set_section_occupied` | Override occupancy thủ công cho một section. | UI
| `set_point_position` | Chuyển point qua locking engine. | UI, lệnh SmartIO
| `upsert_train` | Tạo hoặc cập nhật train. | UI, SmartIO state_update
| `remove_train` | Xóa train. | UI, SmartIO state_update
| `step_runtime` | Tăng một tick mô phỏng. | UI
| `apply_state_update` | Áp dụng state update SmartIO cho sections, points, trains. | SmartIO state_update
| `hydrate_snapshot` | Áp dụng payload snapshot runtime. | SmartIO runtime_snapshot

Các envelope `state_update` từ SmartIO được chuyển thành lệnh `apply_state_update` bởi SmartIO bridge.

### Chế độ và năng lực

Quyền theo mode được định nghĩa tại `runtime/application/mode_policy/policy.py`.

| Chế độ | Có thể chỉnh layout | Có thể override thủ công | Có thể đặt route | Có thể hủy route | Có thể bắt đầu mô phỏng |
| --- | --- | --- | --- | --- | --- |
| `DESIGN_LAYOUT` | Có | Có | Không | Không | Không |
| `SIMULATION` | Không | Có | Có | Có | Có |
| `RUNTIME` | Không | Không | Có | Có | Không |

### Cấu hình

Giá trị mặc định nằm trong `runtime/profile.py` (`GenericApplicationProfile`). Các thiết lập chính gồm:

| Trường | Mặc định | Mục đích |
| --- | --- | --- |
| `time_lock_seconds` | `2.0` | Thời lượng khóa thời gian tiếp cận.
| `default_overlap_length` | `1` | Độ dài overlap mặc định khi tính route.
| `overlap_release_seconds` | `2.0` | Độ trễ release overlap.
| `smart_io_ws_url` | `wss://cbi-smartio.onrender.com/smartio` | Endpoint WebSocket SmartIO.
| `smart_io_snapshot_heartbeat_seconds` | `5.0` | Chu kỳ publish snapshot.
| `smart_io_runtime_stale_seconds` | `15.0` | Ngưỡng stale của transport.
| `runtime_journal_dir` | `data/runtime_journal` | Thư mục journal.
| `runtime_snapshot_checkpoint_interval` | `1` | Chu kỳ checkpoint snapshot (theo stream_seq).

Các giá trị mặc định có thể được ghi đè bằng cách khởi tạo `GenericApplicationProfile` khác trong code ứng dụng.

### Bắt đầu

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -U pip
python -m pip install PyQt6 pytest
```

### Chạy ứng dụng

```bash
python main.py
```

`main.py` tạo `QApplication`, xây dựng `GenericApplicationProfile`, và mở cửa sổ chính.

### Chạy kiểm thử

```bash
python -m pytest
```

```bash
python -m pytest tests/test_runtime_workspace.py
```

### Dữ liệu và lưu trữ

Layout tĩnh và runtime artifact được lưu trong `data/`.

Các vị trí chính:
- `data/station_layout/` cho layout mẫu.
- `data/_smartio_local/` cho payload SmartIO local.
- `data/runtime_journal/` cho các stream JSONL command/event/snapshot.

Các file journal runtime:
- `runtime_commands.jsonl`
- `runtime_events.jsonl`
- `runtime_snapshots.jsonl`

### Tích hợp SmartIO

Tích hợp SmartIO nằm trong `integration/smartio_adapter/` và được điều phối bởi `ui/controllers/runtime_workspace_controller.py`.

Hành vi chính:
- WebSocket envelope được validate trước khi xử lý.
- Envelope `command` được chuyển thành runtime command.
- Envelope `state_update` được chuyển thành lệnh `apply_state_update`.
- Các ghi trực tiếp vào `locked_by`, `signal.aspect`, hoặc `signal.route_id` bị chặn.

### Tài liệu bổ sung

- [ARCHITECTURE.md](ARCHITECTURE.md)
- [ARCHITECTURE.vi.md](ARCHITECTURE.vi.md)

# CBI Railway Signal

Desktop application for CBI interlocking simulation, station layout editing, runtime orchestration, and SmartIO integration.

## Overview

`CBI_Railway_Signal` is a PyQt6 desktop system that combines three concerns that are usually documented separately:
- station layout authoring,
- interlocking-oriented route compilation,
- stateful runtime control and simulation.

The repository is structured as an executable engineering model of a railway signalling workstation rather than a collection of disconnected demos. A user can design a topology, derive route and conflict information from that topology, create a runtime session, execute safe route commands, simulate train movement, and exchange state with SmartIO through one consistent application boundary.

At a practical level, the project addresses these needs:
- represent signals, sections, points, and topology connections in one source of truth;
- derive deterministic route candidates and locking requirements from that topology;
- execute route setting and cancellation through validated command boundaries instead of direct field mutation;
- maintain a replayable runtime journal with checkpoint snapshots;
- expose runtime state to both local UI and external transport without bypassing interlocking rules.

The desktop entrypoint is [main.py](/e:/Documents/DO_AN/CBI_Railway_Signal/main.py:1).

## Terminology Convention

The English and Vietnamese sections use these preferred term pairs consistently:

| English term | Preferred Vietnamese term |
| --- | --- |
| `route` | `hành trình` |
| `point` / `turnout` | `ghi` |
| `signal aspect` | `trạng thái tín hiệu` |
| `conflict` | `xung đột` |
| `flank protection` | `bảo vệ sườn` |
| `overlap` | `vùng chồng lấn` |
| `movement authority` | `quyền di chuyển` |
| `limit of movement authority` | `giới hạn quyền di chuyển` |
| `track circuit` | `mạch đường ray` |
| `axle counter` | `thiết bị đếm trục` |
| `degraded mode` | `chế độ suy giảm` |

## Problem Statement and Goals

The core problem in a CBI-style signalling application is not only finding a path between two signals. The system must also guarantee that the requested movement authority remains compatible with:
- current section occupancy,
- point positions and point locking,
- conflicting routes,
- flank protection,
- overlap requirements,
- runtime recovery and external synchronization.

This repository therefore aims to provide:
1. A design-time model for creating and validating a station layout.
2. A compile-time model for generating interlocking-oriented route information from that layout.
3. A runtime model for safe route activation, simulation, and recovery.
4. An integration layer for SmartIO messages without allowing direct unsafe writes into protected runtime fields.
5. A UI workflow suitable for both demonstration and further academic/project extension.

## Functional Scope

The current codebase supports these major capabilities:
- Create, edit, load, and save station layout topology.
- Validate signal pairs and search for feasible routes.
- Generate interlocking rows and route specifications from topology.
- Create one active runtime session per workspace topology.
- Set routes, reuse existing active routes, cancel routes, or emergency-release them.
- Apply manual occupancy or point updates where mode policy allows it.
- Start train simulation on a route and advance the runtime step-by-step.
- Build runtime snapshots and restore from journaled checkpoint state.
- Receive SmartIO commands and state updates through a WebSocket bridge.
- Publish runtime events, command results, and runtime snapshots outward.

Out of scope in the current implementation:
- full field deployment logic for real signalling hardware;
- multi-workspace concurrent runtime execution inside the same desktop process;
- explicit rich route taxonomy beyond the current route and locking model;
- direct external control of protected signal or lock fields.

## Operating Modes

Mode permissions are defined in `runtime/application/mode_policy/policy.py`.

| Mode | Intended use | Layout edits | Manual state override | Set route | Cancel route | Start simulation | SmartIO state update applied | Runtime snapshot emitted |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `DESIGN_LAYOUT` | Create and refine topology before runtime | Yes | Yes | No | No | No | No | No |
| `SIMULATION` | Local route testing and train playback | No | Yes | Yes | Yes | Yes | No | No |
| `RUNTIME` | Runtime control with external synchronization | No | No | Yes | Yes | No | Yes | Yes |

Interpretation:
- `DESIGN_LAYOUT` treats the layout as the primary artifact and blocks runtime route operations.
- `SIMULATION` allows local experimentation and manual override because the desktop app is the source of truth.
- `RUNTIME` is stricter: state updates and snapshot publication are part of the transport contract, so manual local override is disabled.

## Architecture Map

The repository is organized into clear layers with explicit responsibilities:
- `core/` - Pure domain models, policies, and compiler logic.
- `kernel/` - Engines that enforce route dispatch, locking, occupancy, and safety.
- `runtime/` - Stateful session handling, command orchestration, use cases, and read models.
- `simulation/` - Train lifecycle and environment simulation helpers.
- `infrastructure/` - Journaling, recovery, repositories, and clocks.
- `integration/` - SmartIO protocol handling and runtime bridge code.
- `ui/` - PyQt6 views, presenters, and controllers.

High-level command flow:

```text
User Action / SmartIO Envelope
            |
            v
UI Controller / SmartIO Coordinator
            |
            v
RuntimeWorkspaceService.submit_command(...)
            |
            v
RuntimeSession
            |
            v
RouteDispatcher / LockingEngine / OccupancyReconciler / SafetyMonitor
            |
            v
RailwayTopology + Active Routes + Trains
            |
            v
Journaled Event + Optional Snapshot + Runtime View State
```

Simulation step flow:

```text
step_runtime
    |
    v
RuntimeWorkspaceService
    |
    v
RuntimeSession.step()
    |
    v
SimulationEngine
    |
    +--> update timed release / approach locking
    +--> advance trains
    +--> reconcile occupancy
    +--> run safety checks
    |
    v
Updated runtime view state
```

## End-to-End Workflow

The intended end-to-end usage of the system is:

1. Build or load a station layout.
   The layout editor creates a `RailwayTopology` containing sections, approach sections, points, signals, and graph connections.
2. Validate topology and signal pairs.
   The application checks structural issues and verifies that requested entry/exit signal pairs are meaningful.
3. Compile route and interlocking information.
   Compiler and kernel services derive route candidates, overlap data, required point positions, and conflicting route information.
4. Create or restore a runtime session.
   `RuntimeWorkspaceService.ensure_session(...)` creates a `RuntimeSession`, configures timing, computes topology revision, and attempts recovery from the runtime journal.
5. Execute runtime commands through one boundary.
   UI and SmartIO commands are translated into typed runtime operations instead of mutating protected topology fields directly.
6. Journal command results and snapshots.
   Commands are appended to `runtime_commands.jsonl`, results become `runtime_events.jsonl`, and snapshots are checkpointed into `runtime_snapshots.jsonl`.
7. Observe state locally or through integration.
   The UI consumes runtime view state, while SmartIO can receive command results, runtime events, and runtime snapshots in runtime mode.

## Project Structure

```text
core/
  compiler/             Interlocking spec generation and route compilation
  domain/
    lifecycle/          Route lifecycle and approach locking state logic
    model/              Topology, elements, route, and train entities
    policy/             Conflict, overlap, and flank protection policies

kernel/
  route_dispatcher/     Route search and dispatch orchestration
  locking_engine/       Route locking, sectional release, timed release
  occupancy_engine/     Occupancy reconciliation helpers
  safety_engine/        Fail-safe runtime validation
  product_kernel.py     Product-level composition of routing rules

runtime/
  application/          DTOs, mode policy, helpers, serialization, use cases
  specific_application/ Station editor and layout application services
  runtime_controller.py RuntimeSession implementation
  runtime_cycle.py      SimulationEngine
  workspace_service.py  Runtime orchestration and journal boundary
  read_model.py         Runtime view state for UI
  profile.py            Runtime defaults and integration configuration

simulation/             Train lifecycle and environment simulation
infrastructure/         Event journal, snapshot repositories, clocks
integration/            SmartIO WebSocket protocol and bridge
ui/                     Main window, canvas editor, presenters, controllers
tests/                  Runtime integration-style tests
data/                   Sample layouts, SmartIO fixtures, runtime journal data
```

## Key Runtime Concepts

### RailwayTopology

`RailwayTopology` in `core/domain/model/topology.py` is the structural source of truth of the station model.

It is responsible for:
- storing graph nodes and connections;
- holding typed railway elements such as `TrackSection`, `ApproachSection`, `Point`, and `Signal`;
- validating signal configuration and signal pairs;
- exporting/importing layout JSON;
- carrying runtime-relevant occupancy and lock state on the same structural model.

This shared topology object is reused across editing, route search, compilation, simulation, snapshot hydration, and SmartIO-facing serialization.

### RuntimeSession

`RuntimeSession` in `runtime/runtime_controller.py` owns the mutable runtime state for one active topology.

It coordinates:
- route creation and cancellation,
- point movement and section occupancy changes,
- train creation, reassignment, and removal,
- snapshot hydration,
- simulation stepping.

Its public command surface includes `set_route`, `cancel_route`, `set_section_occupied`, `set_point_position`, `upsert_train`, `remove_train`, `hydrate_snapshot`, and `step`.

### SimulationEngine

`SimulationEngine` in `runtime/runtime_cycle.py` is the step-based engine used when the runtime advances.

Each step can:
- increment the runtime tick;
- update timed and approach locking behavior;
- move trains along active routes;
- trigger occupancy transitions;
- call `SafetyMonitor.detect_unsafe_conditions(...)`;
- force fail-safe STOP if unsafe state is detected.

This makes simulation a runtime concern, not a separate disconnected subsystem.

### RuntimeWorkspaceService

`RuntimeWorkspaceService` in `runtime/workspace_service.py` is the orchestration facade used by the UI and SmartIO coordinator.

It is the canonical boundary for:
- session creation and recovery;
- command deduplication by `(source_id, command_id)`;
- command journaling and event creation;
- snapshot checkpointing;
- exposing runtime view state and runtime health;
- translating external requests into validated runtime actions.

External callers should not manipulate runtime state by bypassing this service.

### RuntimeJournal and Recovery

`RuntimeJournal` and `RuntimeRecoveryService` in `infrastructure/event_store.py` provide append-only persistence for runtime state transitions.

The journal consists of:
- `runtime_commands.jsonl` for submitted commands;
- `runtime_events.jsonl` for applied/rejected command outcomes;
- `runtime_snapshots.jsonl` for checkpoint snapshots.

Recovery behavior:
1. Load the latest valid snapshot.
2. Compare snapshot `topology_revision` with the current topology revision.
3. Hydrate the runtime session from the snapshot.
4. Replay only events whose `command_status` is `applied` and whose `stream_seq` is after the checkpoint.

If recovery fails, or if the checkpoint revision does not match the current topology revision, the runtime health becomes degraded and the session may be forced into fail-safe STOP.

## Runtime Command Surface

All external interactions should go through `RuntimeWorkspaceService.submit_command(...)` or higher-level helper methods that delegate into it.

| Command kind | Purpose | Typical inputs | Resulting effect |
| --- | --- | --- | --- |
| `set_route` | Compute and lock a route between entry/exit signals. | `entry_signal_id`, `exit_signal_id`, `overlap_length` | Activates route, locks points/sections, updates signal state |
| `cancel_active_routes` | Cancel all active routes using normal cancellation rules. | none or route context | Attempts route release subject to locking rules |
| `emergency_release_active_routes` | Force release active routes under emergency procedure. | none or route context | Clears active routes more aggressively than normal cancellation |
| `start_route_simulation` | Create route and place a train for simulation playback. | signal pair, overlap, train speed | Creates active route and train state |
| `set_section_occupied` | Manual occupancy update through runtime boundary. | `section_id`, `occupied` | Changes section occupancy and may remove trains in some cases |
| `set_point_position` | Move a point through locking validation. | `point_id`, `position` | Updates point position if locking rules allow it |
| `upsert_train` | Create or update train runtime state. | `train_id`, `current_section`, `route_id`, `speed` | Adds or modifies a train record |
| `remove_train` | Remove one train from runtime state. | `train_id` | Deletes the train record |
| `step_runtime` | Advance the runtime by one simulation tick. | optional tick intent | Updates trains, locking, safety, and read model |
| `apply_state_update` | Apply SmartIO incremental section/point/train updates. | state update payload | Updates allowed mutable state through bridge rules |
| `hydrate_snapshot` | Apply a full runtime snapshot payload. | runtime snapshot payload | Rebuilds runtime state from checkpoint-style data |

Important behavioral notes:
- Duplicate commands with the same `(source_id, command_id)` are not re-executed. They return a `stale` result derived from the cached processed command result.
- Commands may produce `applied` or `rejected` runtime events.
- Every processed command advances `stream_seq`, which is then used by recovery and transport consumers.

## SmartIO Integration

SmartIO integration lives under `integration/smartio_adapter/` and is coordinated by `ui/controllers/runtime_workspace_controller.py`.

Supported SmartIO-facing concepts:
- inbound `command` envelope;
- inbound `state_update` envelope;
- inbound `runtime_snapshot` hydration path;
- outbound `command_result`;
- outbound `runtime_event`;
- outbound `runtime_snapshot`.

Key protocol rules enforced by the bridge:
- `command` envelopes must include `command_id`, `source_id`, `kind`, and `payload`.
- `state_update` payloads are converted into an internal `apply_state_update` command shape.
- Direct writes to `locked_by` are blocked.
- Direct writes to `signal.aspect` or `signal.route_id` are blocked.
- Train updates must contain valid `id` and `current_section`.
- Route mismatches during signal command handling or snapshot hydrate are treated as protocol consistency errors.

Architectural meaning:
- SmartIO is allowed to request operations.
- SmartIO is not allowed to bypass interlocking logic.
- The runtime bridge exists to translate transport payloads into safe runtime mutations.

## Data and Persistence

Static and runtime data live under `data/`.

Key locations:
- `data/station_layout/` contains sample layout JSON files used for loading and demonstration.
- `data/_smartio_local/` contains SmartIO-related sample payloads and local integration fixtures.
- `data/runtime_journal/` contains persisted command, event, and snapshot streams.

Runtime snapshot shape at a conceptual level:
- `snapshot_version`
- `stream_seq`
- `topology_revision`
- `tick`
- `routes`
- `trains`
- `occupancy`
- `signal_state`

Runtime health tracks:
- current topology revision,
- latest processed stream sequence,
- last applied command timestamp,
- last snapshot timestamp,
- last command id and status,
- `degraded_reason` when recovery or consistency problems occur.

## Developer-Oriented Getting Started

Environment requirements:
- Python `>=3.11`
- PyQt6 for desktop UI
- pytest for test execution

Basic setup:

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -U pip
python -m pip install PyQt6 pytest
```

Optional developer tools reflected in `pyproject.toml`:
- `ruff`
- `mypy`

The repository declares project metadata in [pyproject.toml](/e:/Documents/DO_AN/CBI_Railway_Signal/pyproject.toml:1).

## Running the Application

```bash
python main.py
```

`main.py` builds the PyQt application, creates a `GenericApplicationProfile`, and opens the main window with the editor, routing, runtime, and SmartIO-related UI controls.

## Running Tests

Run the full test suite:

```bash
python -m pytest
```

Run the runtime workspace tests directly:

```bash
python -m pytest tests/test_runtime_workspace.py
```

The current automated tests focus on runtime orchestration behavior such as:
- route lifecycle and route reuse,
- runtime session port compatibility,
- simulation start and snapshot round-trip,
- SmartIO incremental train updates,
- targeted train removal,
- runtime snapshot defaults.

## Sample Layouts and Fixtures

Useful sample assets in the repository:
- `data/station_layout/main_layout.json`
- `data/station_layout/test.json`
- `data/_smartio_local/main_layout_smartio_local.json`
- `data/_smartio_local/test_smartio_local.json`

They are useful for:
- validating layout load/save behavior,
- route search demonstrations,
- SmartIO local integration tests,
- runtime recovery and snapshot experiments.

## Additional Documentation

- [ARCHITECTURE.md](/e:/Documents/DO_AN/CBI_Railway_Signal/ARCHITECTURE.md:1) for subsystem boundaries, runtime flow, journaling, and SmartIO architecture.
- [INTERLOCKING_PRINCIPLES.md](/e:/Documents/DO_AN/CBI_Railway_Signal/INTERLOCKING_PRINCIPLES.md:1) for signalling principles, route safety semantics, and code mapping.

---

# CBI Railway Signal

Ứng dụng desktop cho mô phỏng liên khóa CBI, biên tập sơ đồ ga, điều phối runtime, và tích hợp SmartIO.

## Quy ước thuật ngữ

Bản tiếng Việt dùng thống nhất các cặp thuật ngữ sau:

| Thuật ngữ tiếng Anh | Cách dịch ưu tiên |
| --- | --- |
| `route` | `hành trình` |
| `point` / `turnout` | `ghi` |
| `signal aspect` | `trạng thái tín hiệu` |
| `conflict` | `xung đột` |
| `flank protection` | `bảo vệ sườn` |
| `overlap` | `vùng chồng lấn` |
| `movement authority` | `quyền di chuyển` |
| `limit of movement authority` | `giới hạn quyền di chuyển` |
| `track circuit` | `mạch đường ray` |
| `axle counter` | `thiết bị đếm trục` |
| `degraded mode` | `chế độ suy giảm` |

## Tổng quan

`CBI_Railway_Signal` là một hệ thống PyQt6 desktop kết hợp ba nhóm bài toán vốn thường bị tách rời khi mô tả:
- biên tập sơ đồ hạ tầng nhà ga,
- biên dịch route và dữ liệu liên khóa từ sơ đồ đó,
- điều khiển runtime có trạng thái cùng mô phỏng vận hành.

Dự án này được tổ chức như một mô hình kỹ thuật có thể chạy được của một workstation tín hiệu đường sắt, chứ không phải tập hợp các ví dụ rời rạc. Người dùng có thể thiết kế topology, suy ra route và xung đột từ topology đó, tạo runtime session, thực thi lệnh đặt route an toàn, mô phỏng chạy tàu, và trao đổi trạng thái với SmartIO qua một ranh giới ứng dụng thống nhất.

Ở mức thực tế, dự án giải quyết các nhu cầu sau:
- biểu diễn tín hiệu, section, point, và liên kết topology trong một nguồn dữ liệu chuẩn;
- sinh các route khả dụng và yêu cầu khóa một cách xác định từ topology;
- thực thi đặt route và hủy route qua ranh giới lệnh đã kiểm tra hợp lệ, thay vì sửa trực tiếp thuộc tính của đối tượng;
- duy trì runtime journal có thể replay cùng với checkpoint snapshot;
- công bố trạng thái runtime cho cả UI nội bộ lẫn hệ thống ngoài mà không bỏ qua quy tắc liên khóa.

Điểm vào desktop là [main.py](/e:/Documents/DO_AN/CBI_Railway_Signal/main.py:1).

## Bài toán và mục tiêu

Bài toán cốt lõi trong một ứng dụng tín hiệu kiểu CBI không chỉ là tìm một đường đi giữa hai tín hiệu. Hệ thống còn phải đảm bảo rằng quyền chạy tàu được cấp vẫn tương thích với:
- trạng thái chiếm dụng section hiện tại;
- vị trí point và trạng thái khóa point;
- các route xung đột;
- bảo vệ flank;
- yêu cầu overlap;
- phục hồi runtime và đồng bộ với hệ thống ngoài.

Vì vậy, repo này hướng tới các mục tiêu:
1. Cung cấp mô hình thiết kế để tạo và kiểm tra sơ đồ ga.
2. Cung cấp mô hình biên dịch để sinh thông tin route và liên khóa từ sơ đồ đó.
3. Cung cấp mô hình runtime để kích hoạt route, mô phỏng, và phục hồi trạng thái.
4. Cung cấp lớp tích hợp SmartIO nhưng không cho phép ghi trực tiếp vào các trường runtime được bảo vệ.
5. Cung cấp luồng thao tác UI phù hợp cho trình diễn và mở rộng tiếp theo trong đồ án.

## Phạm vi chức năng

Codebase hiện tại hỗ trợ các khả năng chính sau:
- Tạo, chỉnh sửa, nạp, và lưu topology của ga.
- Kiểm tra cặp tín hiệu và tìm route khả thi.
- Sinh interlocking rows và route specification từ topology.
- Tạo một runtime session hoạt động cho mỗi workspace topology.
- Đặt route, tái sử dụng route đang hoạt động, hủy route, hoặc emergency release.
- Áp dụng cập nhật occupancy hoặc point thủ công ở các mode cho phép.
- Khởi động mô phỏng tàu trên route và cho runtime tiến từng bước.
- Tạo runtime snapshot và phục hồi từ journal checkpoint.
- Nhận lệnh và state update SmartIO qua WebSocket bridge.
- Phát ra runtime event, command result, và runtime snapshot ra ngoài.

Các nội dung chưa nằm trong phạm vi hiện tại:
- logic triển khai đầy đủ cho phần cứng tín hiệu thực tế ngoài hiện trường;
- chạy đồng thời nhiều runtime workspace trong cùng một tiến trình desktop;
- phân loại route phong phú hơn ngoài mô hình route và khóa hiện có;
- điều khiển trực tiếp các trường tín hiệu hoặc lock đã được bảo vệ.

## Các mode vận hành

Quyền theo mode được định nghĩa trong `runtime/application/mode_policy/policy.py`.

| Mode | Mục đích | Sửa layout | Override trạng thái thủ công | Đặt route | Hủy route | Bắt đầu mô phỏng | Áp dụng state update SmartIO | Phát runtime snapshot |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `DESIGN_LAYOUT` | Tạo và chỉnh topology trước khi vào runtime | Có | Có | Không | Không | Không | Không | Không |
| `SIMULATION` | Thử route và playback chạy tàu cục bộ | Không | Có | Có | Có | Có | Không | Không |
| `RUNTIME` | Điều khiển runtime có đồng bộ ngoài | Không | Không | Có | Có | Không | Có | Có |

Cách hiểu:
- `DESIGN_LAYOUT` coi layout là artifact trung tâm và chặn các thao tác route runtime.
- `SIMULATION` cho phép thử nghiệm cục bộ và override thủ công vì desktop app là nguồn trạng thái chính.
- `RUNTIME` chặt chẽ hơn: state update và snapshot publication là một phần của hợp đồng transport nên override cục bộ bị tắt.

## Bản đồ kiến trúc

Repository được tổ chức thành các lớp với trách nhiệm rõ ràng:
- `core/` - mô hình miền thuần, policy, và logic compiler.
- `kernel/` - các engine thực thi route dispatch, locking, occupancy, và safety.
- `runtime/` - session có trạng thái, điều phối command, use case, và read model.
- `simulation/` - helper cho lifecycle tàu và mô phỏng môi trường.
- `infrastructure/` - journaling, recovery, repository, và clock.
- `integration/` - xử lý giao thức SmartIO và runtime bridge.
- `ui/` - view, presenter, và controller PyQt6.

Luồng lệnh tổng quát:

```text
Thao tác người dùng / SmartIO Envelope
                 |
                 v
UI Controller / SmartIO Coordinator
                 |
                 v
RuntimeWorkspaceService.submit_command(...)
                 |
                 v
RuntimeSession
                 |
                 v
RouteDispatcher / LockingEngine / OccupancyReconciler / SafetyMonitor
                 |
                 v
RailwayTopology + Active Routes + Trains
                 |
                 v
Event được journal + Snapshot tùy chọn + Runtime View State
```

Luồng step mô phỏng:

```text
step_runtime
    |
    v
RuntimeWorkspaceService
    |
    v
RuntimeSession.step()
    |
    v
SimulationEngine
    |
    +--> cập nhật timed release / approach locking
    +--> di chuyển tàu
    +--> hòa giải occupancy
    +--> chạy safety checks
    |
    v
Runtime view state mới
```

## Quy trình đầu-cuối

Luồng sử dụng đầy đủ của hệ thống như sau:

1. Tạo mới hoặc nạp sơ đồ ga.
   Trình biên tập layout tạo `RailwayTopology` chứa section, approach section, point, signal, và các kết nối đồ thị.
2. Kiểm tra topology và cặp tín hiệu.
   Ứng dụng phát hiện lỗi cấu hình và kiểm tra xem cặp tín hiệu đầu vào/đầu ra có hợp lệ hay không.
3. Biên dịch route và thông tin liên khóa.
   Compiler và kernel suy ra route, overlap, vị trí point bắt buộc, và thông tin route xung đột.
4. Tạo hoặc phục hồi runtime session.
   `RuntimeWorkspaceService.ensure_session(...)` tạo `RuntimeSession`, cấu hình timing, tính topology revision, rồi thử phục hồi từ runtime journal.
5. Thực thi lệnh runtime qua một ranh giới thống nhất.
   UI và SmartIO đều được chuyển thành runtime operation có kiểu rõ ràng, thay vì sửa trực tiếp các trường topology được bảo vệ.
6. Ghi journal command, event, và snapshot.
   Lệnh được thêm vào `runtime_commands.jsonl`, kết quả thành `runtime_events.jsonl`, và snapshot checkpoint vào `runtime_snapshots.jsonl`.
7. Quan sát trạng thái qua UI hoặc integration.
   UI tiêu thụ runtime view state, còn SmartIO có thể nhận command result, runtime event, và runtime snapshot khi ở runtime mode.

## Cấu trúc dự án

```text
core/
  compiler/             Sinh interlocking spec và route compilation
  domain/
    lifecycle/          Logic vòng đời route và approach locking
    model/              Thực thể topology, element, route, train
    policy/             Conflict, overlap, và flank protection policy

kernel/
  route_dispatcher/     Tìm route và điều phối route
  locking_engine/       Khóa route, sectional release, timed release
  occupancy_engine/     Helper hòa giải occupancy
  safety_engine/        Kiểm tra fail-safe runtime
  product_kernel.py     Ghép các quy tắc sản phẩm ở mức hệ thống

runtime/
  application/          DTO, mode policy, helper, serialization, use case
  specific_application/ Dịch vụ editor và layout cấp ứng dụng
  runtime_controller.py Cài đặt RuntimeSession
  runtime_cycle.py      SimulationEngine
  workspace_service.py  Điều phối runtime và journal boundary
  read_model.py         Runtime view state cho UI
  profile.py            Giá trị mặc định runtime và cấu hình integration

simulation/             Lifecycle tàu và mô phỏng môi trường
infrastructure/         Event journal, snapshot repository, clock
integration/            SmartIO WebSocket protocol và bridge
ui/                     Main window, canvas editor, presenter, controller
tests/                  Kiểm thử kiểu tích hợp cho runtime
data/                   Layout mẫu, fixture SmartIO, dữ liệu runtime journal
```

## Các khái niệm runtime chính

### RailwayTopology

`RailwayTopology` trong `core/domain/model/topology.py` là nguồn dữ liệu cấu trúc chuẩn của mô hình ga.

Nó chịu trách nhiệm:
- lưu các node đồ thị và liên kết giữa chúng;
- giữ các phần tử đường sắt có kiểu như `TrackSection`, `ApproachSection`, `Point`, và `Signal`;
- kiểm tra cấu hình tín hiệu và cặp tín hiệu;
- import/export JSON cho layout;
- mang cả trạng thái runtime như occupancy và lock trên cùng mô hình cấu trúc.

Đối tượng topology dùng chung này được tái sử dụng trong biên tập, tìm route, compiler, mô phỏng, hydrate snapshot, và serialization cho SmartIO.

### RuntimeSession

`RuntimeSession` trong `runtime/runtime_controller.py` sở hữu trạng thái runtime có thể thay đổi cho một topology đang hoạt động.

Nó điều phối:
- tạo và hủy route,
- di chuyển point và cập nhật occupancy section,
- tạo, gán lại, và xóa train,
- hydrate snapshot,
- step mô phỏng.

Bề mặt lệnh công khai của nó gồm `set_route`, `cancel_route`, `set_section_occupied`, `set_point_position`, `upsert_train`, `remove_train`, `hydrate_snapshot`, và `step`.

### SimulationEngine

`SimulationEngine` trong `runtime/runtime_cycle.py` là bộ máy step-based dùng khi runtime tiến trạng thái.

Mỗi bước có thể:
- tăng `tick` runtime;
- cập nhật timed locking và approach locking;
- di chuyển train dọc route đang hoạt động;
- kích hoạt chuyển đổi occupancy;
- gọi `SafetyMonitor.detect_unsafe_conditions(...)`;
- ép toàn bộ tín hiệu về STOP khi phát hiện trạng thái không an toàn.

Điều này cho thấy mô phỏng là một phần của runtime, không phải một subsystem tách rời.

### RuntimeWorkspaceService

`RuntimeWorkspaceService` trong `runtime/workspace_service.py` là facade điều phối được dùng bởi UI và SmartIO coordinator.

Đây là ranh giới chuẩn cho:
- tạo session và phục hồi;
- khử trùng lặp command theo `(source_id, command_id)`;
- journaling command và tạo event;
- checkpoint snapshot;
- cung cấp runtime view state và runtime health;
- chuyển yêu cầu bên ngoài thành runtime action đã được kiểm tra.

Các caller bên ngoài không nên thao tác runtime state bằng cách đi vòng qua service này.

### RuntimeJournal và Recovery

`RuntimeJournal` và `RuntimeRecoveryService` trong `infrastructure/event_store.py` cung cấp cơ chế lưu vết append-only cho các chuyển đổi trạng thái runtime.

Journal gồm:
- `runtime_commands.jsonl` cho command được gửi vào;
- `runtime_events.jsonl` cho kết quả `applied` hoặc `rejected`;
- `runtime_snapshots.jsonl` cho checkpoint snapshot.

Hành vi phục hồi:
1. Nạp snapshot hợp lệ mới nhất.
2. So sánh `topology_revision` của snapshot với revision topology hiện tại.
3. Hydrate runtime session từ snapshot.
4. Replay chỉ các event có `command_status = applied` và có `stream_seq` sau checkpoint.

Nếu phục hồi thất bại, hoặc checkpoint không khớp revision với topology hiện tại, runtime health sẽ chuyển sang degraded và session có thể bị ép về trạng thái fail-safe STOP.

## Bề mặt lệnh runtime

Mọi tương tác bên ngoài nên đi qua `RuntimeWorkspaceService.submit_command(...)` hoặc các helper cấp cao gọi xuống nó.

| Command kind | Mục đích | Input điển hình | Ảnh hưởng |
| --- | --- | --- | --- |
| `set_route` | Tính và khóa route giữa tín hiệu vào/ra | `entry_signal_id`, `exit_signal_id`, `overlap_length` | Kích hoạt route, khóa point/section, cập nhật trạng thái tín hiệu |
| `cancel_active_routes` | Hủy mọi route đang hoạt động theo quy tắc bình thường | không có hoặc ngữ cảnh route | Thử giải phóng route theo locking rules |
| `emergency_release_active_routes` | Force release route đang hoạt động theo thủ tục khẩn cấp | không có hoặc ngữ cảnh route | Xóa route đang hoạt động mạnh hơn hủy bình thường |
| `start_route_simulation` | Tạo route và đặt train để chạy mô phỏng | cặp tín hiệu, overlap, train speed | Tạo route active và trạng thái train |
| `set_section_occupied` | Cập nhật occupancy thủ công qua runtime boundary | `section_id`, `occupied` | Đổi trạng thái occupied và có thể loại train trong một số tình huống |
| `set_point_position` | Chuyển point qua kiểm tra locking | `point_id`, `position` | Cập nhật vị trí point nếu quy tắc khóa cho phép |
| `upsert_train` | Tạo mới hoặc cập nhật train runtime | `train_id`, `current_section`, `route_id`, `speed` | Thêm hoặc sửa bản ghi train |
| `remove_train` | Xóa một train khỏi runtime state | `train_id` | Xóa bản ghi train |
| `step_runtime` | Cho runtime tiến một tick mô phỏng | tùy chọn ý định tick | Cập nhật train, locking, safety, và read model |
| `apply_state_update` | Áp dụng cập nhật section/point/train từ SmartIO | payload state update | Cập nhật trạng thái cho phép theo quy tắc bridge |
| `hydrate_snapshot` | Áp dụng payload runtime snapshot đầy đủ | payload snapshot | Dựng lại runtime state từ dữ liệu checkpoint |

Các điểm hành vi quan trọng:
- Command trùng cùng `(source_id, command_id)` sẽ không được chạy lại. Kết quả trả về là `stale` dựa trên processed command result đã cache.
- Mỗi command xử lý sẽ sinh runtime event ở trạng thái `applied` hoặc `rejected`.
- Mỗi command đã xử lý đều làm tăng `stream_seq`, đây là chỉ số được dùng cho recovery và transport.

## Tích hợp SmartIO

Phần tích hợp SmartIO nằm trong `integration/smartio_adapter/` và được điều phối bởi `ui/controllers/runtime_workspace_controller.py`.

Các khái niệm SmartIO hiện có:
- envelope vào loại `command`;
- envelope vào loại `state_update`;
- đường hydrate cho `runtime_snapshot`;
- dữ liệu ra loại `command_result`;
- dữ liệu ra loại `runtime_event`;
- dữ liệu ra loại `runtime_snapshot`.

Những quy tắc giao thức chính mà bridge áp đặt:
- `command` bắt buộc có `command_id`, `source_id`, `kind`, và `payload`.
- `state_update` được chuyển thành lệnh nội bộ `apply_state_update`.
- Ghi trực tiếp vào `locked_by` bị chặn.
- Ghi trực tiếp vào `signal.aspect` hoặc `signal.route_id` bị chặn.
- Cập nhật train phải có `id` và `current_section` hợp lệ.
- Route không nhất quán khi xử lý signal command hoặc hydrate snapshot sẽ bị coi là lỗi consistency của giao thức.

Ý nghĩa kiến trúc:
- SmartIO được phép yêu cầu thao tác.
- SmartIO không được phép bỏ qua logic liên khóa.
- Runtime bridge tồn tại để chuyển payload transport thành mutation runtime an toàn.

## Dữ liệu và lưu trữ

Dữ liệu tĩnh và dữ liệu runtime nằm dưới `data/`.

Các vị trí đáng chú ý:
- `data/station_layout/` chứa các file layout JSON mẫu dùng để nạp và trình diễn.
- `data/_smartio_local/` chứa payload mẫu và fixture phục vụ tích hợp SmartIO cục bộ.
- `data/runtime_journal/` chứa các stream command, event, và snapshot đã persist.

Cấu trúc khái niệm của runtime snapshot:
- `snapshot_version`
- `stream_seq`
- `topology_revision`
- `tick`
- `routes`
- `trains`
- `occupancy`
- `signal_state`

Runtime health theo dõi:
- topology revision hiện tại,
- stream sequence đã xử lý gần nhất,
- thời điểm command được áp dụng gần nhất,
- thời điểm snapshot gần nhất,
- id và trạng thái command gần nhất,
- `degraded_reason` khi có vấn đề phục hồi hoặc nhất quán dữ liệu.

## Bắt đầu cho lập trình viên

Yêu cầu môi trường:
- Python `>=3.11`
- PyQt6 cho giao diện desktop
- pytest để chạy kiểm thử

Thiết lập cơ bản:

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -U pip
python -m pip install PyQt6 pytest
```

Các tool phát triển tùy chọn đã được phản ánh trong `pyproject.toml`:
- `ruff`
- `mypy`

Repository khai báo metadata trong [pyproject.toml](/e:/Documents/DO_AN/CBI_Railway_Signal/pyproject.toml:1).

## Chạy ứng dụng

```bash
python main.py
```

`main.py` khởi tạo ứng dụng PyQt, tạo `GenericApplicationProfile`, và mở main window với editor, routing, runtime, và các điều khiển liên quan tới SmartIO.

## Chạy kiểm thử

Chạy toàn bộ test:

```bash
python -m pytest
```

Chạy trực tiếp test runtime workspace:

```bash
python -m pytest tests/test_runtime_workspace.py
```

Bộ test tự động hiện tại tập trung vào các hành vi điều phối runtime như:
- vòng đời route và tái sử dụng route;
- tương thích với `RuntimeSessionPort`;
- khởi động mô phỏng và round-trip snapshot;
- cập nhật train tăng dần từ SmartIO;
- xóa đúng train được chỉ định;
- giá trị mặc định của runtime snapshot.

## Layout và fixture mẫu

Các tài nguyên mẫu hữu ích trong repo:
- `data/station_layout/main_layout.json`
- `data/station_layout/test.json`
- `data/_smartio_local/main_layout_smartio_local.json`
- `data/_smartio_local/test_smartio_local.json`

Chúng hữu ích cho:
- kiểm tra load/save layout;
- trình diễn route search;
- thử nghiệm tích hợp SmartIO cục bộ;
- thí nghiệm với recovery và runtime snapshot.

## Tài liệu bổ sung

- [ARCHITECTURE.md](/e:/Documents/DO_AN/CBI_Railway_Signal/ARCHITECTURE.md:1) cho ranh giới subsystem, runtime flow, journaling, và kiến trúc SmartIO.
- [INTERLOCKING_PRINCIPLES.md](/e:/Documents/DO_AN/CBI_Railway_Signal/INTERLOCKING_PRINCIPLES.md:1) cho nguyên lý tín hiệu, ngữ nghĩa an toàn của route, và ánh xạ sang code.

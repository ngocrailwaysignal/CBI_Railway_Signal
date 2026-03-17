# Kiến trúc hệ thống CBI Railway Signal

Tài liệu này mô tả kiến trúc hiện tại của ứng dụng `CBI_Railway_Signal` theo mã nguồn thực tế.

Mục tiêu của tài liệu là làm rõ:
- ranh giới giữa các package;
- luồng dữ liệu từ layout -> runtime -> journal -> SmartIO;
- trách nhiệm của từng thành phần chính;
- các quy tắc phụ thuộc cần giữ ổn định khi mở rộng hệ thống.

Hệ thống hiện được tách thành các khối chính sau:
- `core/`: luật liên khóa, domain model, và compiler thuần logic.
- `kernel/`: runtime engines cho locking, routing, safety, occupancy.
- `runtime/`: runtime session, use case ứng dụng, và orchestration.
- `simulation/`: helper mô phỏng như train lifecycle và snapshot hydration.
- `infrastructure/`: persistence adapters và clocks.
- `integration/`: giao tiếp SmartIO qua WebSocket và chuyển đổi envelope <-> runtime command.
- `ui/`: điều phối giao diện, mode vận hành, và kết nối người dùng với service.

## 1. Tổng quan kiến trúc

Có thể hình dung hệ thống theo 5 lớp chính:

1. Lớp domain/compiler thuần logic:
   `core/domain`, `core/compiler`
2. Lớp kernel runtime engine:
   `kernel`
3. Lớp runtime session và application:
   `runtime`, `runtime/application`
4. Lớp helper mô phỏng:
   `simulation`
5. Lớp tích hợp bên ngoài và presentation (kèm hạ tầng persistence):
   `integration`, `ui`, `infrastructure`

Luồng chính của hệ thống (tách rõ command và mô phỏng theo tick):

Luồng command từ SmartIO/UI:

```text
SmartIO / UI
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

Luồng mô phỏng theo tick (khi gọi `step()`/`run()`):

```text
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

## 2. Bounded contexts và trách nhiệm

### 2.1 `layout_context`

Phụ trách chính:
- tạo, sửa, và validate sơ đồ ga;
- quản lý topology tĩnh trước khi vào runtime;
- cung cấp dữ liệu layout cho UI và SmartIO snapshot.

Module liên quan:
- `runtime/specific_application/editor_service.py`
- `runtime/specific_application/station_layout.py`
- `ui/views/canvas_editor_view.py`
- `core/domain/model/topology.py`
- `runtime/application/serialization/layout_payload_serializer.py`

Đầu vào/Đầu ra:
- đầu vào: thao tác từ canvas editor, file `layout.json`;
- đầu ra: `RailwayTopology`, layout payload cho web/runtime.

### 2.2 `interlocking_compile_context`

Phụ trách chính:
- biên dịch topology thành interlocking specification xác định;
- sinh route candidates, conflict/flank/overlap rules;
- tạo artifact có thể lưu trữ và tải lại.

Module liên quan:
- `core/compiler/route_compiler.py`
- `core/compiler/interlocking_table.py`
- `core/compiler/spec_models.py`
- `runtime/application_service.py`

Đầu vào/Đầu ra:
- đầu vào: `RailwayTopology`, tham số overlap;
- đầu ra: `InterlockingSpec`, interlocking table rows, `interlocking_spec.json`.

### 2.3 `runtime_control_context`

Phụ trách chính:
- đặt route, hủy route, emergency release;
- liên khóa section/point/signal;
- cập nhật occupancy, timed release, approach locking;
- giám sát an toàn và kích hoạt fail-safe STOP khi cần.

Module liên quan:
- `kernel/route_dispatcher/route_engine.py`
- `kernel/route_dispatcher/route_dispatcher.py`
- `kernel/locking_engine/locking_engine.py`
- `kernel/occupancy_engine/occupancy_reconciler.py`
- `kernel/safety_engine/safety_monitor.py`
- `kernel/locking_engine/timed_release.py`
- `kernel/locking_engine/sequence_locking.py`
- `core/domain/lifecycle/approach_locking.py`

Quy tắc quan trọng:
- runtime không cho ghi trực tiếp vào `locked_by`, `signal.aspect`, `signal.route_id` từ bên ngoài;
- mọi đột biến trạng thái phải đi qua command có validate;
- khi phát hiện unsafe condition, toàn bộ signal bị đưa về STOP.

### 2.4 `simulation_workspace_context`

Phụ trách chính:
- chạy hành vi mô phỏng thuần cho runtime session hiện tại;
- tạo/cập nhật train, thực hiện step, hydrate snapshot;
- cộng tác với runtime session thay vì sở hữu runtime boundary;
- không còn là implementation trực tiếp của `RuntimeSessionPort`.

Module liên quan:
- `runtime/runtime_cycle.py`
- `simulation/train_simulator.py`
- `simulation/environment_simulator.py`
- `runtime/runtime_controller.py`
- `runtime/read_model.py`

Ý nghĩa kiến trúc:
- `RuntimeSession` là runtime session stateful duy nhất trong desktop app;
- `SimulationEngine` là collaborator để chạy train movement và time-stepped behavior;
- `runtime/` là lớp thực thi cho các runtime use case trong workspace service.

### 2.5 `runtime_orchestration_context`

Phụ trách chính:
- quản lý vòng đời runtime session theo workspace hiện tại;
- nhận command từ UI hoặc SmartIO, journal hóa, thực thi, và tạo event;
- tạo snapshot checkpoint và phục hồi khi khởi động lại;
- cung cấp runtime health cho UI/transport.

Module liên quan:
- `runtime/workspace_service.py`
- `infrastructure/event_store.py`
- `runtime/profile.py`

Ý nghĩa kiến trúc:
- `RuntimeWorkspaceService` là facade trung tâm cho runtime;
- đây là nơi quyết định command nào được ghi journal, event nào được phát ra, và khi nào checkpoint được tạo;
- `RuntimeSession` không tự ghi journal, và UI không được phép đột biến state trực tiếp.

### 2.6 `integration_context`

Phụ trách chính:
- kết nối WebSocket tới hệ thống SmartIO;
- validate envelope, parse message, retry kết nối;
- chuyển SmartIO event thành runtime command typed;
- gửi `command_result`, `runtime_event`, `runtime_snapshot` ra bên ngoài.

Module liên quan:
- `integration/smartio_adapter/protocol.py`
- `integration/smartio_adapter/runtime_bridge.py`
- `integration/smartio_adapter/qt_ws_client.py`
- `ui/controllers/runtime_workspace_controller.py`

Ý nghĩa kiến trúc:
- SmartIO không thao tác trực tiếp vào topology hay locking engine;
- tất cả thay đổi vẫn phải chạy qua `RuntimeWorkspaceService.submit_command(...)`;
- bridge chỉ làm nhiệm vụ chuẩn hóa giao thức và ánh xạ lỗi về `SmartIOProtocolError`.

### 2.7 `presentation_context`

Phụ trách chính:
- quản lý chế độ Design / Simulation / Runtime;
- bind action của người dùng với application service và runtime service;
- hiển thị read model, runtime health, và trạng thái SmartIO.

Module liên quan:
- `ui/controllers/main_window_controller.py`
- `ui/controllers/runtime_workspace_controller.py`
- `ui/controllers/workspace_state_coordinator.py`
- `ui/presenters/route_presenter.py`
- `ui/views/main_window_view.py`
- `ui/views/canvas_editor_view.py`

## 3. Thành phần cốt lõi

### 3.1 `RailwayTopology`

`RailwayTopology` là mô hình cơ sở của nhà ga.

Nó quản lý:
- graph node/edge;
- signal, section, point;
- các validate liên quan đến topology;
- import/export JSON.

Topology được dùng xuyên suốt ở design, compile, simulation, runtime, và serialization.

Đây là "nguồn sự thật cấu trúc" của hệ thống.

### 3.2 `RuntimeSession`

`runtime/runtime_controller.py` định nghĩa class `RuntimeSession`, là runtime session stateful.

Trong `__post_init__`, nó khởi tạo:
- `RouteEngine`
- `LockingEngine`
- `RouteDispatcher`
- `OccupancyReconciler`
- `SafetyMonitor`
- `RuntimeCommandHandler`
- `RuntimeTrainLifecycle`
- `RuntimeSnapshotHydrator`
- `SimulationEngine`

`RuntimeSession` cung cấp giao diện runtime cấp cao:
- `set_route(...)`
- `cancel_route(...)`
- `set_section_occupied(...)`
- `set_point_position(...)`
- `upsert_train(...)`
- `remove_train(...)`
- `hydrate_snapshot(...)`
- `step()`

`step()` ủy quyền hành vi mô phỏng thuần cho `SimulationEngine`, nơi chịu trách nhiệm:
- tăng `tick`;
- cập nhật time locking trước và sau train movement;
- cho từng train di chuyển trên route đang active;
- chạy `SafetyMonitor.detect_unsafe_conditions(...)`;
- nếu có lỗi, bật fail-safe và ném `RuntimeError`.

### 3.3 `RuntimeWorkspaceService`

`runtime/workspace_service.py` là runtime facade của toàn bộ desktop app.

Nhiệm vụ chính:
- đảm bảo tồn tại session qua `ensure_session(topology)`;
- submit command với idempotency key (`source_id`, `command_id`);
- append `runtime_commands.jsonl`;
- thực thi command;
- sinh `RuntimeEvent` và append `runtime_events.jsonl`;
- checkpoint snapshot vào `runtime_snapshots.jsonl`;
- phục hồi session từ snapshot + event replay;
- theo dõi `RuntimeHealth`.

Vai trò kiến trúc:
- transaction boundary cho runtime command;
- anti-corruption layer giữa UI/transport và runtime session;
- nơi giữ `stream_seq` cho mô hình event-sourcing nhẹ.

### 3.4 `RuntimeJournal` và `RuntimeRecoveryService`

`infrastructure/event_store.py` chứa các primitive realtime:
- `RuntimeCommand`
- `RuntimeEvent`
- `RuntimeCommandResult`
- `RuntimeHealth`
- `RuntimeJournal`
- `RuntimeRecoveryService`

`RuntimeJournal` là append-only JSONL store:
- `runtime_commands.jsonl`
- `runtime_events.jsonl`
- `runtime_snapshots.jsonl`

Tính chất quan trọng:
- có khả năng cắt bỏ invalid tail khi đọc JSONL bị ghi dở;
- lưu command và event tách riêng;
- snapshot không thay thế event, snapshot chỉ là checkpoint để restore nhanh hơn.

`RuntimeRecoveryService.restore(...)` thực hiện:
1. tải snapshot mới nhất;
2. so sánh `topology_revision`;
3. hydrate session từ snapshot;
4. replay các event có `command_status == "applied"` sau `stream_seq` của snapshot.

Nếu topology revision lệch nhau hoặc replay thất bại:
- session được đánh dấu `degraded`;
- runtime có thể bị đưa về trạng thái fail-safe STOP.

## 4. Luồng nghiệp vụ chính

### 4.1 Từ layout đến runtime

1. UI/editor tạo hoặc sửa `RailwayTopology`.
2. `GenericApplicationService` load/save topology và có thể compile spec.
3. Khi vào Simulation/Runtime, `RuntimeWorkspaceService.ensure_session(topology)` tạo `RuntimeSession`.
4. Session có thể được phục hồi từ checkpoint và event journal.
5. UI nhận `RuntimeViewState` để render.

### 4.2 Đặt route từ UI

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

Kết quả của command không chỉ là route:
- nó còn tạo event audit;
- cập nhật stream sequence;
- có thể tạo snapshot mới;
- được cache để tránh xử lý lại command trùng lặp.

### 4.3 Step runtime

`step_runtime` là command chạy chu kỳ mô phỏng.

Nó:
- được journal như command bình thường;
- gọi `RuntimeSession.step()`;
- trả về `RuntimeViewState` mới và `tick`;
- nếu có sự cố an toàn, command bị reject và message lỗi được đưa vào event.

### 4.4 Manual override / occupancy update

Hệ thống cho phép thay đổi có kiểm soát:
- `set_section_occupied`
- `set_point_position`
- `upsert_train`
- `remove_train`
- `apply_state_update`

Nhưng các ghi trực tiếp vào khóa liên động bị chặn:
- không được set `locked_by`;
- không được set trực tiếp `signal.aspect`;
- không được set trực tiếp `signal.route_id`.

Điều này bảo đảm:
- logic liên khóa vẫn tập trung ở engine;
- transport layer không phá vỡ safety invariants.

## 5. Tích hợp SmartIO

### 5.1 `SmartIOWebSocketClient`

`integration/smartio_adapter/qt_ws_client.py` là adapter Qt WebSocket.

Chức năng chính:
- mở/đóng kết nối;
- reconnect backoff;
- parse text JSON;
- validate schema envelope.

Envelope chuẩn có dạng:

```json
{
  "type": "command | state_update | runtime_snapshot | runtime_event | command_result | hello | error | ack",
  "payload": {},
  "ts": 0
}
```

Nó phát các Qt signal:
- `event_received`
- `status_changed`
- `error_occurred`

Nó không chứa logic liên khóa.

### 5.2 `SmartIORuntimeBridge`

`integration/smartio_adapter/runtime_bridge.py` làm 3 việc chính:
- chuyển envelope `command` thành runtime command;
- chuyển envelope `state_update` thành command `apply_state_update`;
- validate payload nguy hiểm và ném `SmartIOProtocolError`.

Mapping tiêu biểu:
- `command(type=signal, action=set_aspect, value=PROCEED)` -> `set_route`
- `command(type=signal, action=set_aspect, value=STOP)` -> `cancel_route`
- `command(type=point, action=set_position)` -> `set_point_position`
- `state_update` -> `apply_state_update`

Bridge còn hỗ trợ:
- resolve route theo `route_id` hoặc cặp `entry_signal/exit_signal`;
- bỏ qua `route_id` stale của train nếu route đã auto-release bên CBI;
- chặn direct state write vào các trường nhạy cảm.

### 5.3 `SmartIORuntimeCoordinator`

`ui/controllers/runtime_workspace_controller.py` sở hữu vòng đời kết nối SmartIO trong UI layer.

Trách nhiệm:
- tạo `SmartIOWebSocketClient`;
- quyết định mode nào được giữ kết nối;
- gửi `hello` khi connect;
- nhận event từ socket và map sang `RuntimeWorkspaceService.submit_command(...)`;
- gửi lại `command_result`;
- publish `runtime_event` pending và `runtime_snapshot` theo heartbeat;
- tổng hợp `runtime_health`.

Điều kiện vận hành hiện tại:
- Runtime mode: cho phép nhận transport command và publish snapshot;
- Simulation mode: chỉ giữ kết nối nếu endpoint là local (`localhost`/`127.0.0.1`);
- ngoài các mode hợp lệ, command từ SmartIO sẽ bị reject.

## 6. Dữ liệu và artifact

### 6.1 Artifact thiết kế

- `layout.json`: topology tĩnh của nhà ga.
- `interlocking_spec.json`: kết quả compile route/conflict/flank/overlap.

### 6.2 Artifact runtime

- `runtime_snapshot.json`: snapshot đơn lẻ của runtime state.
- `runtime_commands.jsonl`: command journal append-only.
- `runtime_events.jsonl`: event audit append-only.
- `runtime_snapshots.jsonl`: chuỗi checkpoint snapshot append-only.

### 6.3 Trường meta quan trọng

Runtime snapshot và event mang theo:
- `stream_seq`: thứ tự sự kiện trong dòng runtime;
- `topology_revision`: fingerprint của topology hiện tại;
- `snapshot_version`: version schema snapshot.

Tác dụng:
- cho phép recovery an toàn;
- tránh replay event của topology khác;
- hỗ trợ debug và đồng bộ với client ngoài.

## 7. Recovery và health model

Hệ thống xem desktop CBI là runtime node có thẩm quyền cao nhất.

Nguyên tắc:
- mọi command hợp lệ đều được journal;
- mọi command sau xử lý đều sinh `RuntimeEvent`;
- snapshot được xem là derived state, không phải sự thật gốc;
- khi restart, hệ thống restore từ snapshot mới nhất rồi replay event applied.

`RuntimeHealth` theo dõi:
- `topology_revision`
- `stream_seq`
- `last_applied_command_at`
- `last_snapshot_at`
- `last_command_id`
- `last_command_status`
- `degraded_reason`

Trạng thái `degraded` có thể xuất hiện khi:
- checkpoint không khớp revision;
- recovery thất bại;
- transport heartbeat/snapshot bị stale trong Runtime mode.

## 8. Cấu trúc thư mục

```text
core/
  compiler/
  domain/
    lifecycle/
    model/
    policy/
kernel/
  locking_engine/
  occupancy_engine/
  route_dispatcher/
  safety_engine/

runtime/
  application/
    dto/
    mode_policy/
    serialization/
    use_cases/
  specific_application/
  command_bus.py
  read_model.py
  runtime_controller.py
  runtime_cycle.py
  workspace_service.py
  profile.py
  application_service.py

simulation/
  environment_simulator.py
  train_simulator.py

infrastructure/
  clocks/
  snapshot_store/
  event_store.py

integration/
  smartio_adapter/
    protocol.py
    qt_ws_client.py
    runtime_bridge.py

ui/
  controllers/
  presenters/
  views/
```

## 9. Quy tắc phụ thuộc

### 9.1 `core/*`

- không phụ thuộc vào `ui/*`, `runtime/*`, `simulation/*`, `integration/*`;
- chứa logic có thể test độc lập;
- là nơi định nghĩa domain model và compiler (có thể dùng kernel product rules khi compile route).

### 9.2 `kernel/*`

- được phép phụ thuộc vào `core/domain/*` và `infrastructure/clocks/*`;
- chứa runtime engines cho locking/routing/safety/occupancy;
- không nên chứa logic giao diện hay transport.

### 9.3 `runtime/*`

- được phép dùng `core/*`, `kernel/*`, `simulation/*`, `infrastructure/*`;
- là lớp orchestration/runtime workflow;
- không nên chứa widget/UI code.

### 9.4 `simulation/*`

- được phép phụ thuộc vào `core/*` và cộng tác với `runtime/*`;
- không nên chứa logic giao diện hay transport;
- là nơi tập hợp hành vi mô phỏng thuần.

### 9.5 `integration/*`

- chỉ nên nói chuyện với service/port cấp application;
- không được can thiệp trực tiếp vào nội bộ `LockingEngine` bằng cách đột biến raw state;
- mọi interaction phải qua protocol và command boundary.

### 9.6 `ui/*`

- được phép phụ thuộc vào `runtime/*`, `runtime/specific_application/*`, và `integration/*`;
- chỉ nên điều phối và trình bày;
- không nên đặt luật liên khóa trong controller/view.

## 10. Nguyên tắc mở rộng

1. Thêm command mới qua `RuntimeWorkspaceService.submit_command(...)` thay vì sửa state trực tiếp.
2. Nếu command có ý nghĩa nghiệp vụ, đặt logic ở `runtime/application/use_cases` hoặc `kernel/*`.
3. Nếu không thể phục hồi state từ event cũ, tăng `snapshot_version` và cập nhật hydrator.
4. Mọi tích hợp bên ngoài nên đi qua anti-corruption layer tương tự `SmartIORuntimeBridge`.
5. Mọi quy tắc safety mới phải được thực thi trong engine/monitor, không đặt ở UI.

## 11. Tóm tắt

Kiến trúc hiện tại của `CBI_Railway_Signal` xoay quanh một runtime session stateful (`RuntimeSession`) được bao bọc bởi một lớp orchestration có journal/recovery (`RuntimeWorkspaceService`).

`core/` giữ logic liên khóa và compiler thuần; `kernel/` giữ runtime engines; `runtime/` giữ mutable runtime state và runtime-facing read model; `simulation/` giữ hành vi mô phỏng thuần; `infrastructure/` giữ persistence adapters; `integration/` giữ giao thức kết nối bên ngoài; `ui/` chủ yếu điều phối và hiển thị.

Cách tách này giúp hệ thống:
- bảo toàn safety invariant;
- hỗ trợ runtime audit và recovery;
- dễ mở rộng thêm giao tiếp bên ngoài;
- tránh để logic miền bị phân tán vào UI hay transport layer.

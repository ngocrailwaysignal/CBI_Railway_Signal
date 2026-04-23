# Interlocking Principles

This document explains the interlocking principles relevant to the project and maps them to the current implementation. It is intentionally written in a "principle -> operational meaning -> code mapping" style so that it is useful both as academic background and as engineering documentation.

## Terminology Convention

This document uses the following preferred term pairs:
- `turnout` / `point` -> `ghi`
- `route` -> `hành trình`
- `signal aspect` -> `trạng thái tín hiệu`
- `conflict` -> `xung đột`
- `flank protection` -> `bảo vệ sườn`
- `overlap` -> `vùng chồng lấn`
- `movement authority` -> `quyền di chuyển`
- `limit of movement authority` -> `giới hạn quyền di chuyển`
- `track circuit` -> `mạch đường ray`
- `axle counter` -> `thiết bị đếm trục`
- `degraded mode` -> `chế độ suy giảm`

## 1. Context: Why Interlocking Exists

Interlocking exists to ensure that movement authority is granted only when the infrastructure, the route, and the surrounding operational context are all compatible with safe movement. In practical terms, a route is not just a path in a graph. It is a temporary safety contract that binds together:
- signal authority,
- track clearance,
- turnout/point position and locking,
- conflict exclusion,
- flank protection,
- overlap and release rules.

In this project, those ideas are represented in software by combining:
- structural topology in `core/domain/model/topology.py`,
- route and policy derivation in `core/compiler/*` and `core/domain/policy/*`,
- route activation and release logic in `kernel/locking_engine/*`,
- runtime orchestration in `runtime/workspace_service.py`,
- transport adaptation in `integration/smartio_adapter/runtime_bridge.py`.

## 2. Signals, Blocks, and Track Clear Detection

Before interlocking can govern movement, the system needs three foundations:
- a signal system that expresses movement authority,
- a partitioning of the railway into track sections or blocks,
- a method for determining whether those sections are clear or occupied.

Operational meaning:
- A signal should not display authority to proceed if the protected route is not secured.
- A section that is occupied must affect route availability and release timing.
- Trains, occupancy state, and route state must remain mutually consistent.

Code mapping:
- signals, sections, approach sections, and points are part of `RailwayTopology`;
- occupancy and lock state live on the same model objects and are used by runtime engines;
- `SafetyMonitor` checks whether train position claims agree with occupancy state;
- SmartIO is not allowed to bypass this by directly writing protected signal fields.

## 3. Core Interlocking Principles

### 3.1 Safe Route Conditions

Principle:
A route may only be cleared when all safety conditions are satisfied.

Operational meaning:
- The requested path must exist.
- The sections on that route must be clear, or otherwise compatible with the active runtime context.
- Every required point must be in the correct position and remain lockable.
- Conflicting routes must not already hold incompatible authority.
- Flank protection and overlap requirements must be satisfied.

Code mapping:
- route derivation starts in `core/compiler/route_compiler.py` and `core/compiler/interlocking_table.py`;
- route feasibility is coordinated by `kernel/route_dispatcher/*`;
- locking and route activation are enforced by `kernel/locking_engine/locking_engine.py`;
- conflict, flank, and overlap policy live in `core/domain/policy/*`.

Architectural consequence:
- a route request is treated as a safety-sensitive operation, not a simple graph lookup.

### 3.2 Route Classes and Operational Intent

Principle:
Railway practice distinguishes different movement intents, for example main movements and shunting movements, because they may require different authority semantics.

Operational meaning in this project:
- the current implementation focuses on one general route and locking model;
- explicit separate shunt-route entities are not yet modeled;
- however, the software still distinguishes safe interlocking intent from lower-level direct state manipulation.

That distinction matters because:
- setting a route grants structured movement authority;
- manual section or point updates are limited maintenance/simulation tools;
- direct signal aspect forcing is intentionally blocked from SmartIO state updates.

Code mapping:
- route intent is expressed through runtime commands such as `set_route`;
- manual and simulation-oriented operations live in `runtime/application/use_cases/*`;
- transport restrictions are enforced in `integration/smartio_adapter/runtime_bridge.py`.

### 3.3 Point Locking

Principle:
Before a route is cleared, all points that influence that route must be set and locked in the correct position. They must remain protected while the movement authority is valid.

Operational meaning:
- point state is not merely informational;
- once a route depends on a point, that point becomes part of the route protection envelope;
- point movement while locked must be prevented or tightly controlled.

Code mapping:
- required point positions are derived from route compilation output;
- `Route.all_required_point_positions()` contributes the lock requirements;
- `LockingEngine.lock_route(...)` applies point locking;
- `LockingEngine.set_point_position(...)` validates whether the requested move is legal.

Why it matters:
- if point locking were bypassed, the route could remain apparently valid while the physical path it assumes no longer exists.

### 3.4 Route Locking

Principle:
Once a route has been granted, it remains locked for as long as the movement authority and associated safety conditions require.

Operational meaning:
- route locking is stronger than route discovery;
- signals, points, and sections must reflect that the route is active;
- route lifecycle matters over time, not just at the instant of creation.

In this project:
- route lifecycle state is tracked in the runtime;
- active routes are maintained by the locking engine;
- signal authority is coupled to route activation.

Code mapping:
- route lifecycle transitions are modeled in `core/domain/lifecycle/route_lifecycle_fsm.py`;
- active route handling is centralized in `kernel/locking_engine/locking_engine.py`;
- runtime orchestration of route commands occurs in `runtime/workspace_service.py`.

### 3.5 Route Release

Principle:
A route must not remain locked longer than necessary, but it also must not be released earlier than safety permits.

Operational meaning:
- release can be triggered by train progression, occupancy changes, or explicit cancellation procedures;
- release often occurs in phases rather than one instant global unlock;
- overlap may remain protected after the main route body has been traversed.

Code mapping:
- route cancellation and emergency release are available as separate runtime use cases;
- release timing is configured via `GenericApplicationProfile`;
- overlap release scheduling and cleanup are handled in the locking engine;
- section-based release logic is supported by sequence locking and sectional release behavior.

This is why the project distinguishes:
- normal cancellation,
- emergency release,
- timed release,
- overlap release,
- sequence or sectional release.

### 3.6 Conflicting Routes

Principle:
Conflicting routes must not be active at the same time, even if they do not rely on exactly the same point positions.

Operational meaning:
- conflict is about movement incompatibility, not only about object identity;
- two routes may conflict because they cross, overlap, oppose, or violate clearance requirements.

Code mapping:
- conflict derivation is handled in route compilation and policy logic;
- `core/domain/policy/conflict_policy.py` contains conflict checks;
- compiled interlocking rows carry `conflicting_routes`;
- the locking engine prevents activation of incompatible routes.

Architectural consequence:
- conflict checking belongs to interlocking logic, not to the UI.

### 3.7 Flank Protection

Principle:
Even when the main route is itself clear, surrounding infrastructure may need to be positioned to guard against side or converging movement.

Operational meaning:
- a safe route includes protection against unintended lateral entry;
- protective point positions may exist outside the direct traveled path;
- the path the train uses is not the only path the interlocking must reason about.

Code mapping:
- flank protection rules are computed in `core/domain/policy/flank_policy.py`;
- route compilation includes flank implications in the generated route requirements;
- locking logic ultimately enforces the positions needed for route activation.

Why this matters academically and practically:
- it demonstrates that interlocking is not just path reservation;
- it is a protection envelope around the movement authority.

### 3.8 Overlap and Control Length

Principle:
The route beyond the stop point often includes additional protected distance so that a train overrunning the intended stopping point does not immediately create a collision hazard.

Operational meaning:
- overlap is additional controlled length beyond the nominal route path;
- overlap influences what must remain reserved and how release should be timed;
- overlap is a configurable operational parameter in this project.

Code mapping:
- overlap length is part of route requests and compilation;
- `GenericApplicationProfile.default_overlap_length` supplies a default;
- `Route` stores both `path` and `overlap_path`;
- locking and release behavior use overlap-aware route state.

## 4. Additional Runtime Safety Concepts

### 4.1 Approach Locking

Principle:
If a train is already approaching a route, unsafe late cancellation must be prevented or delayed.

Operational meaning:
- route cancellation should not immediately succeed if the train is already committed to the approach;
- the system may require time-based release after cancellation is requested;
- approach occupancy influences cancellation semantics.

Code mapping:
- approach locking state is modeled in `core/domain/lifecycle/approach_locking.py`;
- route-level approach status is exposed through the locking engine;
- `RuntimeWorkspaceService.approach_lock_details(...)` surfaces state and remaining time to higher layers.

Practical effect:
- the runtime distinguishes between "route exists", "route is cancelable", and "route is protected by approach locking".

### 4.2 Timed Release

Principle:
Some release actions should occur only after a configured delay rather than immediately when a request is made.

Operational meaning:
- time is part of interlocking behavior, not just a UI concern;
- cancellation and overlap release may remain pending for a period;
- deterministic timing settings are required for repeatable runtime behavior.

Code mapping:
- profile fields such as `time_lock_seconds` and `overlap_release_seconds` configure timing;
- `kernel/locking_engine/timed_release.py` and related locking-engine methods manage release timing;
- `SimulationEngine` and `RuntimeWorkspaceService.update_time_locking()` advance the timing logic.

### 4.3 Sectional and Sequence Release

Principle:
As a train progresses through a route, parts of the route may become releasable before the whole route is finished.

Operational meaning:
- route release can follow train progression section by section;
- the release order matters;
- occupancy changes influence when protection can be removed from earlier parts of the path.

Code mapping:
- sequence tracking is implemented in `kernel/locking_engine/sequence_locking.py`;
- the locking engine marks occupied sequence sections and attempts release as the train vacates them;
- train stepping in `core/domain/model/train.py` and `simulation/train_simulator.py` contributes the runtime transitions that make this possible.

### 4.4 Fail-Safe STOP

Principle:
When runtime state becomes inconsistent or unsafe, the system should move toward the safest available state.

Operational meaning:
- unsafe runtime conditions must not silently persist;
- signal authority should be withdrawn if the system no longer trusts its own state;
- failure handling is part of the interlocking story.

Code mapping:
- `kernel/safety_engine/safety_monitor.py` detects unsafe conditions;
- unsafe examples include multiple trains on one section, signal `PROCEED` without a locked route, or locked points in invalid positions;
- `SafetyMonitor.enforce_fail_safe_stop(...)` forces signals to STOP and clears route authority indicators;
- recovery degradation in `RuntimeWorkspaceService.ensure_session(...)` can also force fail-safe STOP.

### 4.5 Manual Override and Its Limits

Principle:
Manual intervention may be necessary for simulation, testing, or maintenance-like scenarios, but it must not collapse the distinction between intended control and protected interlocking state.

Operational meaning:
- a manual override is not permission to bypass all safety rules;
- mode policy controls when manual state changes are allowed;
- even permitted manual changes are still routed through runtime logic.

Code mapping:
- mode policy is defined in `runtime/application/mode_policy/policy.py`;
- manual override use cases live in `runtime/application/use_cases/manual_override.py`;
- runtime workspace helpers expose controlled manual section occupancy changes;
- SmartIO direct writes to protected lock or signal fields remain blocked even when some other state updates are allowed.

### 4.6 Interlocking Intent vs Direct State Write

Principle:
In a safe signalling system, it matters whether the system receives an operational intent or a low-level state overwrite.

Operational meaning:
- "set route from signal A to signal B" is an interlocking intent;
- "write signal S1 to PROCEED regardless of route state" is a direct state write;
- the first can be validated against route, conflict, and locking rules;
- the second bypasses those rules and is therefore unsafe.

Code mapping:
- `set_route` and related runtime commands express intent;
- SmartIO `command` envelopes can map into those runtime intents;
- SmartIO `state_update` envelopes are intentionally restricted from writing protected route-locking fields.

## 5. Operational Flows

### 5.1 Route Setting and Locking

```text
UI / SmartIO requests set_route
             |
             v
RuntimeWorkspaceService.submit_command
             |
             v
RuntimeSession.set_route(...)
             |
             v
RouteDispatcher searches feasible path
             |
             v
LockingEngine validates and locks route
             |
             +--> lock required points
             +--> lock route sections
             +--> assign signal route authority
             +--> register route lifecycle/approach state
             |
             v
Route becomes active
```

### 5.2 Normal Cancellation and Approach Locking

```text
Route active
    |
    v
Cancellation requested
    |
    +--> if no approach lock: route may release normally
    |
    +--> if approach lock active:
            wait for time-based release conditions
    |
    v
LockingEngine updates route lifecycle
    |
    v
Sections/points/signals released when safe
```

### 5.3 Emergency Release

```text
Route active but urgent release requested
               |
               v
Emergency release use case
               |
               v
LockingEngine.emergency_release_route(...)
               |
               v
Route authority withdrawn more aggressively
               |
               v
Runtime event recorded
```

### 5.4 Train Movement and Sectional Release

```text
Train assigned to active route
           |
           v
SimulationEngine.step()
           |
           +--> train moves to next section
           +--> previous section may vacate
           +--> occupancy updated
           +--> sequence release attempted
           |
           v
Earlier route sections may unlock when safe
```

### 5.5 SmartIO State Update

```text
SmartIO state_update arrives
            |
            v
runtime_bridge.command_from_state_update(...)
            |
            v
apply_state_update runtime command
            |
            +--> sections: occupied allowed
            +--> points: position allowed through runtime validation
            +--> trains: incremental upsert/remove
            +--> signals/locked_by direct writes blocked
            |
            v
Runtime state updated without bypassing protected semantics
```

### 5.6 Snapshot Hydration

```text
Snapshot payload received
          |
          v
RuntimeSession.hydrate_snapshot(...)
          |
          +--> restore routes
          +--> restore trains
          +--> restore occupancy
          +--> restore signal state
          |
          v
Runtime session resumes from checkpoint-compatible state
```

## 6. Mapping to the Codebase

### 6.1 Structural model

- `core/domain/model/topology.py`
- `core/domain/model/elements.py`
- `core/domain/model/route.py`
- `core/domain/model/train.py`

These modules define the things that interlocking operates on.

### 6.2 Policy and lifecycle

- `core/domain/policy/conflict_policy.py`
- `core/domain/policy/flank_policy.py`
- `core/domain/policy/overlap_policy.py`
- `core/domain/lifecycle/approach_locking.py`
- `core/domain/lifecycle/route_lifecycle_fsm.py`

These modules define the invariants that explain why one route can or cannot exist safely.

### 6.3 Compilation and route derivation

- `core/compiler/route_compiler.py`
- `core/compiler/interlocking_table.py`
- `core/compiler/spec_models.py`
- `kernel/product_kernel.py`
- `kernel/route_dispatcher/*`

These modules derive route candidates, interlocking tables, and route requirements from topology.

### 6.4 Runtime enforcement

- `kernel/locking_engine/locking_engine.py`
- `kernel/locking_engine/sequence_locking.py`
- `kernel/locking_engine/timed_release.py`
- `kernel/occupancy_engine/occupancy_reconciler.py`
- `kernel/safety_engine/safety_monitor.py`
- `runtime/runtime_controller.py`
- `runtime/runtime_cycle.py`

These modules turn interlocking principles into executable runtime behavior.

### 6.5 Orchestration, journal, and recovery

- `runtime/workspace_service.py`
- `infrastructure/event_store.py`
- `runtime/application/serialization/runtime_snapshot_serializer.py`

These modules explain how route control becomes replayable runtime state.

### 6.6 Transport adaptation

- `integration/smartio_adapter/runtime_bridge.py`
- `integration/smartio_adapter/protocol.py`
- `integration/smartio_adapter/qt_ws_client.py`

These modules explain how external transport can interact with runtime without direct unsafe state mutation.

## 7. Relationship to Tests

The project includes executable evidence for several interlocking-related behaviors in `tests/test_runtime_workspace.py`.

The tests demonstrate concepts such as:
- route lifecycle and route reuse;
- simulation start and train creation;
- runtime snapshot round-trip through the SmartIO runtime bridge;
- incremental SmartIO train updates that do not delete unrelated trains;
- targeted train removal using `removed_train_ids`;
- required default fields in an empty runtime snapshot.

These tests are important because they show that the documentation is not merely aspirational. The repository already contains runtime scenarios that exercise command handling, snapshot restore, and transport-facing state updates.

## 8. References

- *Railway Signalling Principles*, Edition 3.0, Jörn Pachl (2024).
- DOI: https://doi.org/10.24355/dbbs.084-202405240811-0
- [README.md](/e:/Documents/DO_AN/CBI_Railway_Signal/README.md:1)
- [ARCHITECTURE.md](/e:/Documents/DO_AN/CBI_Railway_Signal/ARCHITECTURE.md:1)

---

# Nguyên lý liên khóa

Tài liệu này giải thích các nguyên lý liên khóa có liên quan tới dự án và ánh xạ chúng sang implementation hiện tại. Nó được viết theo kiểu "nguyên lý -> ý nghĩa vận hành -> ánh xạ mã nguồn" để vừa hữu ích cho phần cơ sở học thuật, vừa hữu ích như tài liệu kỹ thuật.

## Quy ước thuật ngữ

Tài liệu này dùng thống nhất các cặp thuật ngữ sau:
- `turnout` / `point` -> `ghi`
- `route` -> `hành trình`
- `signal aspect` -> `trạng thái tín hiệu`
- `conflict` -> `xung đột`
- `flank protection` -> `bảo vệ sườn`
- `overlap` -> `vùng chồng lấn`
- `movement authority` -> `quyền di chuyển`
- `limit of movement authority` -> `giới hạn quyền di chuyển`
- `track circuit` -> `mạch đường ray`
- `axle counter` -> `thiết bị đếm trục`
- `degraded mode` -> `chế độ suy giảm`

## 1. Bối cảnh: vì sao cần liên khóa

Liên khóa tồn tại để bảo đảm quyền di chuyển chỉ được cấp khi hạ tầng, hành trình (`route`), và ngữ cảnh vận hành xung quanh đều tương thích với chuyển động an toàn. Ở mức thực tế, một hành trình không chỉ là một đường đi trên đồ thị. Nó là một hợp đồng an toàn tạm thời ràng buộc đồng thời:
- authority của tín hiệu,
- tình trạng thanh thoát tuyến,
- vị trí và khóa ghi (`point`),
- loại trừ hành trình xung đột,
- bảo vệ sườn (`flank protection`),
- quy tắc vùng chồng lấn (`overlap`) và release.

Trong dự án này, các ý tưởng đó được biểu diễn trong phần mềm bằng cách kết hợp:
- topology cấu trúc trong `core/domain/model/topology.py`,
- suy ra route và policy trong `core/compiler/*` và `core/domain/policy/*`,
- logic kích hoạt và giải phóng route trong `kernel/locking_engine/*`,
- điều phối runtime trong `runtime/workspace_service.py`,
- lớp thích nghi transport trong `integration/smartio_adapter/runtime_bridge.py`.

## 2. Tín hiệu, block, và phát hiện thanh thoát tuyến

Trước khi liên khóa có thể điều khiển chuyển động, hệ thống cần ba nền tảng:
- một hệ thống tín hiệu biểu diễn quyền chạy tàu,
- một cách chia tuyến đường sắt thành section hoặc block,
- một cơ chế xác định section đang trống hay bị chiếm dụng.

Ý nghĩa vận hành:
- tín hiệu không được hiển thị quyền chạy nếu route được bảo vệ chưa thật sự được chốt;
- một section đang occupied phải ảnh hưởng đến khả dụng của route và thời điểm release;
- trạng thái tàu, occupancy, và route phải luôn nhất quán với nhau.

Ánh xạ mã nguồn:
- signal, section, approach section, và point là một phần của `RailwayTopology`;
- trạng thái occupancy và lock nằm ngay trên các đối tượng mô hình này và được runtime engine sử dụng;
- `SafetyMonitor` kiểm tra xem vị trí train khai báo có khớp với occupancy hay không;
- SmartIO không được phép bỏ qua việc này bằng cách ghi trực tiếp vào trường tín hiệu được bảo vệ.

## 3. Các nguyên lý liên khóa cốt lõi

### 3.1 Điều kiện an toàn của route

Nguyên lý:
Một route chỉ được mở khi mọi điều kiện an toàn đều thỏa mãn.

Ý nghĩa vận hành:
- đường đi được yêu cầu phải tồn tại;
- các section trên route phải đang trống, hoặc ít nhất tương thích với ngữ cảnh runtime hiện tại;
- mọi point bắt buộc phải ở đúng vị trí và có thể khóa được;
- các route xung đột không được nắm authority không tương thích;
- flank protection và overlap phải được thỏa mãn.

Ánh xạ mã nguồn:
- việc suy ra route bắt đầu trong `core/compiler/route_compiler.py` và `core/compiler/interlocking_table.py`;
- khả năng thực thi route được điều phối bởi `kernel/route_dispatcher/*`;
- khóa và kích hoạt route được thực thi bởi `kernel/locking_engine/locking_engine.py`;
- policy conflict, flank, và overlap nằm trong `core/domain/policy/*`.

Hệ quả kiến trúc:
- yêu cầu route được coi là thao tác nhạy cảm về an toàn, không phải chỉ là truy vấn đồ thị.

### 3.2 Phân loại route và ý định vận hành

Nguyên lý:
Trong thực hành đường sắt, các ý định vận động khác nhau như chạy tàu chính hay dồn dịch thường được phân biệt vì chúng có thể cần ngữ nghĩa authority khác nhau.

Ý nghĩa vận hành trong dự án này:
- implementation hiện tại tập trung vào một mô hình route và khóa tổng quát;
- chưa có thực thể shunt-route tách riêng;
- tuy vậy, phần mềm vẫn phân biệt giữa ý định liên khóa an toàn với thao tác ghi trạng thái trực tiếp ở mức thấp.

Sự khác biệt này quan trọng vì:
- đặt route là hành động cấp movement authority có cấu trúc;
- cập nhật section hoặc point thủ công chỉ là công cụ hỗ trợ mô phỏng/bảo trì;
- ép trực tiếp signal aspect bị chặn trong SmartIO state update.

Ánh xạ mã nguồn:
- ý định route được biểu diễn qua runtime command như `set_route`;
- thao tác thủ công và mô phỏng nằm trong `runtime/application/use_cases/*`;
- hạn chế transport được thực thi trong `integration/smartio_adapter/runtime_bridge.py`.

### 3.3 Khóa point

Nguyên lý:
Trước khi route được mở, mọi point ảnh hưởng tới route phải được đặt đúng vị trí và khóa. Chúng phải được bảo vệ trong suốt thời gian authority còn hiệu lực.

Ý nghĩa vận hành:
- trạng thái point không chỉ để hiển thị;
- khi route phụ thuộc vào một point, point đó trở thành một phần của vùng bảo vệ route;
- chuyển point khi đang bị khóa phải bị ngăn hoặc bị kiểm soát rất chặt.

Ánh xạ mã nguồn:
- vị trí point bắt buộc được suy ra từ kết quả route compilation;
- `Route.all_required_point_positions()` đóng góp các yêu cầu khóa;
- `LockingEngine.lock_route(...)` áp dụng khóa point;
- `LockingEngine.set_point_position(...)` kiểm tra xem yêu cầu chuyển point có hợp lệ hay không.

Vì sao điều này quan trọng:
- nếu bỏ qua khóa point, route có thể nhìn như vẫn hợp lệ trong khi đường vật lý mà nó giả định đã không còn đúng.

### 3.4 Khóa route

Nguyên lý:
Khi một route đã được cấp, nó phải tiếp tục bị khóa trong suốt khoảng thời gian mà authority và các điều kiện an toàn liên quan còn yêu cầu.

Ý nghĩa vận hành:
- khóa route mạnh hơn hành động tìm route;
- tín hiệu, point, và section phải phản ánh rằng route đang active;
- vòng đời route quan trọng theo thời gian, không chỉ tại thời điểm tạo ra.

Trong dự án này:
- trạng thái vòng đời route được theo dõi ở runtime;
- active route do locking engine quản lý;
- authority của signal gắn chặt với việc route được kích hoạt.

Ánh xạ mã nguồn:
- chuyển trạng thái vòng đời route được mô hình trong `core/domain/lifecycle/route_lifecycle_fsm.py`;
- xử lý active route tập trung ở `kernel/locking_engine/locking_engine.py`;
- điều phối command route ở `runtime/workspace_service.py`.

### 3.5 Giải phóng route

Nguyên lý:
Route không được giữ khóa lâu hơn mức cần thiết, nhưng cũng không được giải phóng sớm hơn khi an toàn chưa cho phép.

Ý nghĩa vận hành:
- release có thể được kích hoạt bởi tiến trình tàu, thay đổi occupancy, hoặc thủ tục hủy route rõ ràng;
- release thường diễn ra theo pha chứ không phải một lần mở khóa toàn cục;
- overlap có thể vẫn cần được bảo vệ sau khi phần chính của route đã được đi qua.

Ánh xạ mã nguồn:
- hủy route và emergency release là các use case runtime tách biệt;
- thời gian release được cấu hình trong `GenericApplicationProfile`;
- lập lịch overlap release và dọn dẹp được xử lý trong locking engine;
- logic release theo section được hỗ trợ bởi sequence locking và sectional release.

Đây là lý do dự án phân biệt:
- hủy bình thường,
- emergency release,
- timed release,
- overlap release,
- sequence hoặc sectional release.

### 3.6 Route xung đột

Nguyên lý:
Các route xung đột không được cùng active một lúc, ngay cả khi chúng không dùng chính xác cùng một vị trí point.

Ý nghĩa vận hành:
- conflict nói về sự không tương thích của chuyển động, không chỉ là trùng đối tượng;
- hai route có thể xung đột vì cắt nhau, chồng nhau, đối nghịch, hoặc vi phạm yêu cầu clearance.

Ánh xạ mã nguồn:
- việc suy ra xung đột được xử lý trong compiler và policy;
- `core/domain/policy/conflict_policy.py` chứa các kiểm tra conflict;
- interlocking row đã biên dịch mang theo `conflicting_routes`;
- locking engine ngăn route không tương thích được kích hoạt.

Hệ quả kiến trúc:
- kiểm tra xung đột thuộc về logic liên khóa, không thuộc UI.

### 3.7 Bảo vệ flank

Nguyên lý:
Ngay cả khi route chính đang trống, hạ tầng xung quanh vẫn có thể cần được đặt ở vị trí bảo vệ để ngăn chuyển động bên sườn hoặc hội tụ.

Ý nghĩa vận hành:
- một route an toàn phải bao gồm bảo vệ chống xâm nhập bên cạnh ngoài ý muốn;
- vị trí point bảo vệ có thể nằm ngoài đường tàu trực tiếp đi qua;
- đường đi của tàu không phải là đường duy nhất mà liên khóa phải xem xét.

Ánh xạ mã nguồn:
- quy tắc flank protection được tính trong `core/domain/policy/flank_policy.py`;
- route compilation đưa hệ quả flank vào yêu cầu route được sinh ra;
- locking logic thực thi các vị trí cần thiết để route có thể active.

Vì sao điều này quan trọng cả về học thuật lẫn thực hành:
- nó cho thấy liên khóa không chỉ là giữ chỗ đường đi;
- nó là một vùng bảo vệ bao quanh movement authority.

### 3.8 Overlap và control length

Nguyên lý:
Phần route phía sau điểm dừng thường bao gồm một đoạn bảo vệ bổ sung để nếu tàu vượt quá vị trí dự kiến thì không lập tức tạo nguy cơ va chạm.

Ý nghĩa vận hành:
- overlap là chiều dài kiểm soát bổ sung sau path danh nghĩa;
- overlap ảnh hưởng đến cái gì phải tiếp tục được giữ chỗ và release phải diễn ra thế nào;
- overlap là tham số vận hành có thể cấu hình trong dự án này.

Ánh xạ mã nguồn:
- overlap length là một phần của yêu cầu route và quá trình compile;
- `GenericApplicationProfile.default_overlap_length` cung cấp mặc định;
- `Route` lưu cả `path` và `overlap_path`;
- hành vi khóa và release dùng trạng thái route có hiểu overlap.

## 4. Các khái niệm an toàn runtime bổ sung

### 4.1 Approach locking

Nguyên lý:
Nếu tàu đã đang tiếp cận route, việc hủy route muộn theo cách không an toàn phải bị ngăn hoặc trì hoãn.

Ý nghĩa vận hành:
- hủy route không nên thành công ngay nếu tàu đã bị "commit" vào đoạn tiếp cận;
- hệ thống có thể yêu cầu release theo thời gian sau khi có yêu cầu hủy;
- occupancy ở đoạn approach ảnh hưởng đến ngữ nghĩa hủy route.

Ánh xạ mã nguồn:
- trạng thái approach locking được mô hình trong `core/domain/lifecycle/approach_locking.py`;
- trạng thái approach ở mức route được locking engine cung cấp;
- `RuntimeWorkspaceService.approach_lock_details(...)` đưa trạng thái và thời gian còn lại lên các lớp cao hơn.

Hiệu ứng thực tế:
- runtime phân biệt giữa "route đang tồn tại", "route có thể hủy", và "route đang được bảo vệ bởi approach locking".

### 4.2 Timed release

Nguyên lý:
Một số hành động release chỉ nên xảy ra sau một khoảng trễ cấu hình thay vì ngay khi có yêu cầu.

Ý nghĩa vận hành:
- thời gian là một phần của hành vi liên khóa, không chỉ là concern của UI;
- việc hủy và overlap release có thể ở trạng thái chờ trong một khoảng;
- cần các thiết lập timing xác định để runtime có hành vi lặp lại được.

Ánh xạ mã nguồn:
- các field profile như `time_lock_seconds` và `overlap_release_seconds` cấu hình timing;
- `kernel/locking_engine/timed_release.py` và các method liên quan của locking engine quản lý logic release theo thời gian;
- `SimulationEngine` và `RuntimeWorkspaceService.update_time_locking()` làm tiến logic theo thời gian.

### 4.3 Sectional và sequence release

Nguyên lý:
Khi tàu tiến dần qua route, một số phần của route có thể trở nên giải phóng được trước khi toàn bộ route kết thúc.

Ý nghĩa vận hành:
- route release có thể đi theo từng section;
- thứ tự release có ý nghĩa;
- thay đổi occupancy quyết định khi nào có thể bỏ bảo vệ khỏi các phần đầu của path.

Ánh xạ mã nguồn:
- tracking theo chuỗi được cài trong `kernel/locking_engine/sequence_locking.py`;
- locking engine đánh dấu section đã occupied và thử release khi tàu rời section;
- bước train trong `core/domain/model/train.py` và `simulation/train_simulator.py` tạo ra các chuyển đổi runtime cần thiết để việc này xảy ra.

### 4.4 Fail-safe STOP

Nguyên lý:
Khi trạng thái runtime trở nên bất nhất hoặc không an toàn, hệ thống phải đi về trạng thái an toàn nhất có thể.

Ý nghĩa vận hành:
- điều kiện runtime không an toàn không được tồn tại lặng lẽ;
- authority của tín hiệu phải bị rút lại nếu hệ thống không còn tin tưởng vào chính trạng thái của nó;
- xử lý lỗi là một phần của câu chuyện liên khóa.

Ánh xạ mã nguồn:
- `kernel/safety_engine/safety_monitor.py` phát hiện unsafe conditions;
- ví dụ unsafe gồm nhiều tàu trên cùng một section, tín hiệu `PROCEED` nhưng không có locked route, hoặc point bị khóa ở vị trí không hợp lệ;
- `SafetyMonitor.enforce_fail_safe_stop(...)` ép tín hiệu về STOP và xóa chỉ thị authority của route;
- trạng thái degraded trong recovery của `RuntimeWorkspaceService.ensure_session(...)` cũng có thể ép fail-safe STOP.

### 4.5 Manual override và giới hạn của nó

Nguyên lý:
Can thiệp thủ công có thể cần cho mô phỏng, test, hoặc tình huống giống bảo trì, nhưng nó không được làm sụp đổ ranh giới giữa điều khiển có chủ đích và trạng thái liên khóa được bảo vệ.

Ý nghĩa vận hành:
- manual override không phải là quyền bỏ qua toàn bộ quy tắc an toàn;
- mode policy quyết định khi nào việc đổi state thủ công được cho phép;
- kể cả khi được cho phép, thay đổi vẫn phải đi qua logic runtime.

Ánh xạ mã nguồn:
- mode policy được định nghĩa trong `runtime/application/mode_policy/policy.py`;
- use case manual override nằm trong `runtime/application/use_cases/manual_override.py`;
- helper của runtime workspace cung cấp thao tác đổi occupancy section một cách có kiểm soát;
- SmartIO vẫn không được ghi trực tiếp vào trường lock hoặc signal được bảo vệ, kể cả khi một số state update khác được cho phép.

### 4.6 Ý định liên khóa so với ghi trạng thái trực tiếp

Nguyên lý:
Trong một hệ thống tín hiệu an toàn, điều quan trọng không chỉ là giá trị cuối cùng, mà là hệ thống nhận được ý định vận hành hay một lệnh ghi đè trạng thái mức thấp.

Ý nghĩa vận hành:
- "đặt route từ tín hiệu A đến tín hiệu B" là ý định liên khóa;
- "ghi tín hiệu S1 thành PROCEED bất kể trạng thái route" là ghi trạng thái trực tiếp;
- loại thứ nhất có thể được kiểm tra theo route, conflict, và locking rule;
- loại thứ hai bỏ qua các quy tắc đó nên là không an toàn.

Ánh xạ mã nguồn:
- `set_route` và các runtime command liên quan biểu diễn ý định;
- envelope `command` của SmartIO có thể được ánh xạ thành các ý định runtime này;
- envelope `state_update` của SmartIO bị hạn chế có chủ đích để không ghi vào các trường route-locking được bảo vệ.

## 5. Luồng vận hành

### 5.1 Đặt route và khóa

```text
UI / SmartIO yêu cầu set_route
              |
              v
RuntimeWorkspaceService.submit_command
              |
              v
RuntimeSession.set_route(...)
              |
              v
RouteDispatcher tìm path khả thi
              |
              v
LockingEngine kiểm tra và khóa route
              |
              +--> khóa point bắt buộc
              +--> khóa section thuộc route
              +--> gán authority route cho signal
              +--> đăng ký lifecycle/approach state
              |
              v
Route trở thành active
```

### 5.2 Hủy bình thường và approach locking

```text
Route đang active
     |
     v
Yêu cầu hủy
     |
     +--> nếu không có approach lock: route có thể release bình thường
     |
     +--> nếu approach lock đang active:
             chờ điều kiện release theo thời gian
     |
     v
LockingEngine cập nhật route lifecycle
     |
     v
Section/point/signal được giải phóng khi an toàn
```

### 5.3 Emergency release

```text
Route đang active nhưng cần giải phóng khẩn
                  |
                  v
Emergency release use case
                  |
                  v
LockingEngine.emergency_release_route(...)
                  |
                  v
Route authority bị rút mạnh hơn hủy bình thường
                  |
                  v
Runtime event được ghi lại
```

### 5.4 Di chuyển tàu và sectional release

```text
Train được gán cho route active
             |
             v
SimulationEngine.step()
             |
             +--> train đi sang section tiếp theo
             +--> section trước có thể được giải phóng
             +--> occupancy được cập nhật
             +--> thử sequence release
             |
             v
Các section đầu route có thể mở khóa khi an toàn
```

### 5.5 SmartIO state update

```text
SmartIO state_update đi vào
            |
            v
runtime_bridge.command_from_state_update(...)
            |
            v
runtime command apply_state_update
            |
            +--> sections: cho phép đổi occupied
            +--> points: cho phép đổi position qua runtime validation
            +--> trains: upsert/remove tăng dần
            +--> signals/locked_by: ghi trực tiếp bị chặn
            |
            v
Runtime state được cập nhật mà không vượt qua ngữ nghĩa được bảo vệ
```

### 5.6 Hydrate snapshot

```text
Nhận payload snapshot
        |
        v
RuntimeSession.hydrate_snapshot(...)
        |
        +--> phục hồi routes
        +--> phục hồi trains
        +--> phục hồi occupancy
        +--> phục hồi signal state
        |
        v
Runtime session tiếp tục từ trạng thái tương thích checkpoint
```

## 6. Ánh xạ tới codebase

### 6.1 Mô hình cấu trúc

- `core/domain/model/topology.py`
- `core/domain/model/elements.py`
- `core/domain/model/route.py`
- `core/domain/model/train.py`

Các module này định nghĩa những gì mà liên khóa tác động lên.

### 6.2 Policy và lifecycle

- `core/domain/policy/conflict_policy.py`
- `core/domain/policy/flank_policy.py`
- `core/domain/policy/overlap_policy.py`
- `core/domain/lifecycle/approach_locking.py`
- `core/domain/lifecycle/route_lifecycle_fsm.py`

Các module này định nghĩa các invariant giải thích vì sao một route có thể hoặc không thể tồn tại an toàn.

### 6.3 Compilation và suy ra route

- `core/compiler/route_compiler.py`
- `core/compiler/interlocking_table.py`
- `core/compiler/spec_models.py`
- `kernel/product_kernel.py`
- `kernel/route_dispatcher/*`

Các module này suy ra route candidate, interlocking table, và yêu cầu route từ topology.

### 6.4 Thực thi runtime

- `kernel/locking_engine/locking_engine.py`
- `kernel/locking_engine/sequence_locking.py`
- `kernel/locking_engine/timed_release.py`
- `kernel/occupancy_engine/occupancy_reconciler.py`
- `kernel/safety_engine/safety_monitor.py`
- `runtime/runtime_controller.py`
- `runtime/runtime_cycle.py`

Các module này biến nguyên lý liên khóa thành hành vi runtime có thể chạy được.

### 6.5 Điều phối, journal, và recovery

- `runtime/workspace_service.py`
- `infrastructure/event_store.py`
- `runtime/application/serialization/runtime_snapshot_serializer.py`

Các module này giải thích cách điều khiển route trở thành runtime state có thể replay.

### 6.6 Thích nghi transport

- `integration/smartio_adapter/runtime_bridge.py`
- `integration/smartio_adapter/protocol.py`
- `integration/smartio_adapter/qt_ws_client.py`

Các module này giải thích cách transport bên ngoài có thể tương tác với runtime mà không gây direct unsafe state mutation.

## 7. Liên hệ với kiểm thử

Dự án đã có bằng chứng thực thi cho nhiều hành vi liên khóa trong `tests/test_runtime_workspace.py`.

Các test thể hiện những khái niệm như:
- route lifecycle và route reuse;
- bắt đầu mô phỏng và tạo train;
- round-trip runtime snapshot qua SmartIO runtime bridge;
- cập nhật train tăng dần từ SmartIO mà không xóa train không liên quan;
- xóa đúng train mục tiêu bằng `removed_train_ids`;
- các field mặc định bắt buộc trong runtime snapshot rỗng.

Những test này quan trọng vì chúng cho thấy tài liệu không chỉ mang tính định hướng. Repository đã có các kịch bản runtime thực thi command handling, snapshot restore, và state update hướng transport.

## 8. Tài liệu tham khảo

- *Railway Signalling Principles*, Edition 3.0, Jörn Pachl (2024).
- DOI: https://doi.org/10.24355/dbbs.084-202405240811-0
- [README.md](/e:/Documents/DO_AN/CBI_Railway_Signal/README.md:1)
- [ARCHITECTURE.md](/e:/Documents/DO_AN/CBI_Railway_Signal/ARCHITECTURE.md:1)

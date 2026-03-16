# Interlocking Principles

This document provides a detailed explanation of interlocking principles based on *Railway Signalling Principles, Edition 3.0* (Jörn Pachl) and maps those principles to how this project implements them.

## 1. Context: Signals, Blocks, and Track Clear Detection

Interlocking is built on the ability to **grant movement authority safely**. That requires:
- Signals and aspects to indicate authority and restrictions.
- Blocks/sections to separate movements.
- Reliable track clear detection (e.g., track circuits or axle counters).

**From RSP 3.0:**
- Signals control movement authority and provide approach information.
- Fixed block operation remains the most common principle for train separation.
- Track clear detection is typically achieved by **track circuits** or **axle counters**.

**In this project:**
- Signals, sections, and points are modeled in `core/domain/model/*` as part of `RailwayTopology`.
- Section occupancy is enforced via `kernel/locking_engine` and reconciled in `kernel/occupancy_engine`.
- External systems cannot directly set `signal.aspect`, `signal.route_id`, or `locked_by` (see SmartIO state update restrictions).

## 2. Core Interlocking Principles

### 2.1 Safe Route Conditions

**RSP 3.0 principle:** A route may be cleared only when all safety conditions are satisfied:
- All points are set and locked in the correct position.
- Conflicting moves are locked out.
- The route is protected against flank movements.
- All track sections within the route are clear.

**In this project:**
- Route computation and conflict rules originate in `core/compiler/*`.
- `kernel/route_dispatcher` and `kernel/locking_engine` enforce route locking.
- Occupancy is validated per section; conflicts are prevented by locking rules.

### 2.2 Route Classes (Main vs Shunt)

**RSP 3.0 principle:**
- **Main routes** govern train movements under main signals.
- **Shunt routes** govern shunting movements under shunting signals.

**In this project:**
- Route class is implicit in how the route is requested and enforced (no explicit shunt route model yet).
- Manual overrides and limited commands (`set_section_occupied`, `set_point_position`) align with shunting-like operations but are bounded by interlocking safety rules.

### 2.3 Point Locking

**RSP 3.0 principle:**
- Before a route is cleared, all points must be locked in the correct position.
- Points must remain locked for as long as a train has authority over them.

**In this project:**
- `kernel/locking_engine` owns the authoritative lock state for points.
- Direct `locked_by` updates from UI or SmartIO are rejected.

### 2.4 Route Locking and Release

**RSP 3.0 principle:**
- Route locking remains active while a train has authority to move on the route.
- **Approach locking** prevents unsafe cancellation when a train is approaching.
- **Emergency release** is possible under controlled procedures.

**In this project:**
- Approach locking logic is implemented in `core/domain/lifecycle/approach_locking.py`.
- Timed releases are implemented in `kernel/locking_engine/timed_release.py`.
- Route cancellation and emergency release are implemented in `runtime/application/use_cases/*`.

### 2.5 Conflicting Routes

**RSP 3.0 principle:**
- Conflicting routes must lock each other out, even when points do not differ in position.
- Opposing or intersecting routes require explicit conflict locking.

**In this project:**
- Route conflicts are computed in `core/compiler/interlocking_table.py` and enforced in `kernel/locking_engine`.
- The locking engine ensures only non-conflicting routes can be active simultaneously.

### 2.6 Flank Protection

**RSP 3.0 principle:**
- A route must be protected against inadvertent movements from converging tracks.
- Flank protection can be provided by points, derailers, or signals.

**In this project:**
- Flank protection rules are part of compiled interlocking specifications.
- `core/domain/policy/flank_policy.py` and related compiler logic capture flank constraints.

### 2.7 Overlaps and Control Length

**RSP 3.0 principle:**
- The **control length** beyond a signal must be clear before the signal is cleared.
- **Overlap** provides additional safety in case a train overruns a signal.

**In this project:**
- Overlap length is part of route computation and locking rules.
- Release timing is configured in `GenericApplicationProfile` and enforced by the locking engine.

## 3. Operational Flows (ASCII)

### 3.1 Route Setting and Locking

```text
UI/SmartIO set_route
    |
    v
RuntimeWorkspaceService.submit_command
    |
    v
SetOrReuseRouteUseCase
    |
    v
RouteDispatcher -> LockingEngine
    |
    v
Active Route + Locked Points/Sections + Signal Aspect
```

### 3.2 Route Release and Approach Locking

```text
Route active
    |
    v
Train approaches -> approach locking active
    |
    v
Train clears sections -> timed release
    |
    v
Route released or emergency release
```

### 3.3 Conflict + Flank Protection

```text
Request route A
    |
    v
Conflict/flank checks
    |
    +--> lock out conflicting route B
    |
    v
Route A active
```

## 4. Mapping to Codebase

- **Topology & Signals:** `core/domain/model/*`
- **Route compilation & conflicts:** `core/compiler/*`
- **Route dispatch & locking:** `kernel/route_dispatcher/*`, `kernel/locking_engine/*`
- **Safety enforcement:** `kernel/safety_engine/*`
- **Runtime command boundary & journaling:** `runtime/workspace_service.py`, `infrastructure/event_store.py`

## 5. References

- *Railway Signalling Principles*, Edition 3.0, Jörn Pachl (2024).
- DOI: https://doi.org/10.24355/dbbs.084-202405240811-0

---

# Nguyên lý liên khóa

Tài liệu này giải thích chi tiết các nguyên lý liên khóa dựa trên *Railway Signalling Principles, Edition 3.0* (Jörn Pachl) và ánh xạ các nguyên lý đó vào cách dự án này triển khai.

## 1. Bối cảnh: Tín hiệu, block, và phát hiện rỗng tuyến

Liên khóa dựa trên khả năng **cấp quyền chạy tàu an toàn**. Điều này đòi hỏi:
- Tín hiệu và biểu thị để chỉ thị quyền chạy và hạn chế.
- Block/section để tách các chuyển động.
- Phát hiện thanh thoát tuyến tin cậy (track circuits hoặc axle counters).

**Theo RSP 3.0:**
- Tín hiệu kiểm soát quyền chạy và cung cấp thông tin tiếp cận.
- Vận hành theo block cố định vẫn là nguyên lý phổ biến nhất để giãn cách tàu.
- Phát hiện rỗng tuyến thường dùng **track circuits** hoặc **axle counters**.

**Trong dự án này:**
- Tín hiệu, section, point được mô hình trong `core/domain/model/*` như một phần của `RailwayTopology`.
- Chiếm dụng section được thực thi qua `kernel/locking_engine` và `kernel/occupancy_engine`.
- Hệ thống bên ngoài không thể set trực tiếp `signal.aspect`, `signal.route_id`, hoặc `locked_by`.

## 2. Các nguyên lý liên khóa cốt lõi

### 2.1 Điều kiện an toàn của route

**Nguyên lý RSP 3.0:** Một route chỉ được mở khi mọi điều kiện an toàn thỏa mãn:
- Tất cả point đã đặt và khóa đúng vị trí.
- Các chuyển động xung đột bị khóa loại.
- Route được bảo vệ flank.
- Mọi section trong route đều thanh thoát.

**Trong dự án này:**
- Tính route và xung đột do `core/compiler/*` sinh ra.
- `kernel/route_dispatcher` và `kernel/locking_engine` thực thi khóa route.
- Occupancy được kiểm tra theo section, xung đột bị chặn bởi locking rules.

### 2.2 Phân loại route (main vs shunt)

**Nguyên lý RSP 3.0:**
- **Main routes** cho tàu chạy chính.
- **Shunt routes** cho thao tác dồn dịch.

**Trong dự án này:**
- Chưa có model tách riêng shunt route

### 2.3 Khóa point

**Nguyên lý RSP 3.0:**
- Trước khi mở route, mọi point phải được khóa đúng vị trí.
- Point phải giữ khóa cho đến khi tàu không còn quyền chạy trên chúng.

**Trong dự án này:**
- `kernel/locking_engine` là nơi giữ trạng thái khóa point chuẩn.

### 2.4 Khóa route và giải phóng

**Nguyên lý RSP 3.0:**
- Khóa route duy trì khi tàu còn quyền chạy.
- **Approach locking** ngăn hủy route khi tàu đang tiếp cận.
- **Emergency release** cho phép giải phóng theo quy trình kiểm soát.

**Trong dự án này:**
- Approach locking ở `core/domain/lifecycle/approach_locking.py`.
- Timed release ở `kernel/locking_engine/timed_release.py`.
- Hủy route và emergency release ở `runtime/application/use_cases/*`.

### 2.5 Route xung đột

**Nguyên lý RSP 3.0:**
- Route xung đột phải khóa lẫn nhau, kể cả khi point không khác vị trí.
- Các route đối đầu hoặc giao cắt cần khóa xung đột riêng.

**Trong dự án này:**
- Xung đột được tính trong `core/compiler/interlocking_table.py` và thực thi bởi `kernel/locking_engine`.
- Locking engine đảm bảo chỉ route không xung đột mới hoạt động đồng thời.

### 2.6 Bảo vệ flank

**Nguyên lý RSP 3.0:**
- Route phải được bảo vệ khỏi chuyển động bên sườn.
- Flank protection có thể dùng point, derailers, hoặc tín hiệu.

**Trong dự án này:**
- Quy tắc bảo vệ flank thông qua point là một phần của interlocking spec được compile.
- `core/domain/policy/flank_policy.py` và compiler liên quan nắm giữ các ràng buộc.

### 2.7 Overlap và control length

**Nguyên lý RSP 3.0:**
- **Control length** sau tín hiệu phải rỗng trước khi mở tín hiệu.
- **Overlap** tăng an toàn khi tàu vượt tín hiệu.

**Trong dự án:**
- Độ dài overlap là một phần của tính route và khóa.
- Timing release được cấu hình qua `GenericApplicationProfile` và thực thi trong locking engine.

## 3. Luồng vận hành (ASCII)

### 3.1 Đặt route và khóa

```text
UI set_route
    |
    v
RuntimeWorkspaceService.submit_command
    |
    v
SetOrReuseRouteUseCase
    |
    v
RouteDispatcher -> LockingEngine
    |
    v
Active Route + Locked Points/Sections + Signal Aspect
```

### 3.2 Giải phóng route và approach locking

```text
Route active
    |
    v
Train approaches -> approach locking active
    |
    v
Train clears sections -> timed release
    |
    v
Route released or emergency release
```

### 3.3 Xung đột + flank protection

```text
Request route A
    |
    v
Conflict/flank checks
    |
    +--> lock out conflicting route B
    |
    v
Route A active
```

## 4. Ánh xạ tới codebase

- **Topology & Signals:** `core/domain/model/*`
- **Compile route & xung đột:** `core/compiler/*`
- **Dispatch & locking:** `kernel/route_dispatcher/*`, `kernel/locking_engine/*`
- **Safety:** `kernel/safety_engine/*`
- **Command boundary & journaling:** `runtime/workspace_service.py`, `infrastructure/event_store.py`

## 5. Tài liệu tham khảo

- *Railway Signalling Principles*, Edition 3.0, Jörn Pachl (2024).
- DOI: https://doi.org/10.24355/dbbs.084-202405240811-0

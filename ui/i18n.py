"""Centralized UI translations for English and Vietnamese."""

from __future__ import annotations

from typing import Final

DEFAULT_LANGUAGE: Final[str] = "en"
SUPPORTED_LANGUAGES: Final[tuple[str, str]] = ("en", "vi")

TRANSLATIONS: Final[dict[str, dict[str, str]]] = {
    "app.window_title": {
        "en": "Computer-Based Interlocking",
        "vi": "Hệ Thông Liên Khóa Vi Tính",
    },
    "language.label": {
        "en": "Language",
        "vi": "Ngôn ngữ",
    },
    "language.option.en": {
        "en": "English",
        "vi": "Tiếng Anh",
    },
    "language.option.vi": {
        "en": "Vietnamese",
        "vi": "Tiếng Việt",
    },
    "toolbar.main": {
        "en": "Main",
        "vi": "Chính",
    },
    "toolbar.new_layout": {
        "en": "New Layout",
        "vi": "Tạo sơ đồ mới",
    },
    "toolbar.save_layout": {
        "en": "Save Layout",
        "vi": "Lưu sơ đồ",
    },
    "toolbar.load_layout": {
        "en": "Load Layout",
        "vi": "Mở sơ đồ",
    },
    "toolbar.connect_mode": {
        "en": "Connect Mode",
        "vi": "Chế độ nối",
    },
    "toolbar.set_route": {
        "en": "Set Route",
        "vi": "Thiết lập hành trình",
    },
    "toolbar.cancel_route": {
        "en": "Cancel Route",
        "vi": "Hủy hành trình",
    },
    "toolbar.emergency_release": {
        "en": "Emergency Release",
        "vi": "Giải phóng khẩn cấp",
    },
    "toolbar.start_simulation": {
        "en": "Start Simulation",
        "vi": "Bắt đầu mô phỏng",
    },
    "toolbar.stop_simulation": {
        "en": "Stop Simulation",
        "vi": "Dừng mô phỏng",
    },
    "toolbar.open_smartio_local": {
        "en": "Open SmartIO Local",
        "vi": "Mở SmartIO Local",
    },
    "button.find_route": {
        "en": "Find Route",
        "vi": "Tìm hành trình",
    },
    "button.set_route": {
        "en": "Set Route",
        "vi": "Thiết lập hành trình",
    },
    "button.cancel_route": {
        "en": "Cancel Route",
        "vi": "Hủy hành trình",
    },
    "button.emergency_release": {
        "en": "Emergency Release",
        "vi": "Giải phóng khẩn cấp",
    },
    "button.start_simulation": {
        "en": "Start Simulation",
        "vi": "Bắt đầu mô phỏng",
    },
    "button.stop_sim_short": {
        "en": "Stop Sim",
        "vi": "Dừng mô phỏng",
    },
    "button.open_smartio_local": {
        "en": "Open SmartIO Local",
        "vi": "Mở SmartIO Local",
    },
    "button.apply": {
        "en": "Apply",
        "vi": "Áp dụng",
    },
    "mode.design_layout": {
        "en": "Design Layout",
        "vi": "Thiết kế sa bàn",
    },
    "mode.simulation": {
        "en": "Simulation",
        "vi": "Mô phỏng",
    },
    "mode.runtime": {
        "en": "Runtime",
        "vi": "Vận hành",
    },
    "mode.status": {
        "en": "Mode: {mode}",
        "vi": "Chế độ: {mode}",
    },
    "workspace.group": {
        "en": "Workspace",
        "vi": "Không gian làm việc",
    },
    "workspace.summary.design_layout": {
        "en": "Build topology and interlocking assets.",
        "vi": "Xây dựng topology và dữ liệu liên khóa.",
    },
    "workspace.summary.simulation": {
        "en": "Train movement sandbox with manual state override.",
        "vi": "Môi trường mô phỏng chạy tàu với ghi đè trạng thái thủ công.",
    },
    "workspace.summary.runtime": {
        "en": "Operational mode with strict manual state safety.",
        "vi": "Chế độ vận hành với ràng buộc an toàn trạng thái thủ công.",
    },
    "route_finder.group": {
        "en": "Route Finder",
        "vi": "Tìm hành trình",
    },
    "route_finder.instructions": {
        "en": "Select Entry and Exit signals, then run route search.",
        "vi": "Chọn tín hiệu vào và ra, sau đó tìm hành trình.",
    },
    "route_finder.placeholder": {
        "en": "Route search steps will appear here.",
        "vi": "Các bước tìm hành trình sẽ hiển thị tại đây.",
    },
    "interlocking_table.group": {
        "en": "Interlocking Table",
        "vi": "Bảng liên khóa",
    },
    "interlocking_table.header.no": {
        "en": "NO",
        "vi": "STT",
    },
    "interlocking_table.header.route": {
        "en": "Route",
        "vi": "Hành trình",
    },
    "interlocking_table.header.signal": {
        "en": "Signal",
        "vi": "Tín hiệu",
    },
    "interlocking_table.header.point": {
        "en": "Point",
        "vi": "Ghi",
    },
    "interlocking_table.header.opposing_signal": {
        "en": "Opposing Signal",
        "vi": "Tín hiệu đối hướng",
    },
    "interlocking_table.header.track": {
        "en": "Track",
        "vi": "Đường chạy",
    },
    "interlocking_table.header.approach_lock_track": {
        "en": "Approach Locking\nTrack",
        "vi": "Khóa tiếp cận\nPhân khu",
    },
    "interlocking_table.header.approach_lock_release": {
        "en": "Approach Locking\nRelease Time",
        "vi": " Thời gian giải phóng\n Khóa tiếp cận ",
    },
    "interlocking_table.header.destination_track": {
        "en": "Destination Track",
        "vi": "Phân khu đích",
    },
    "interlocking_table.header.flank_point": {
        "en": "Flank Point",
        "vi": "Ghi sườn",
    },
    "interlocking_table.header.overlap": {
        "en": "Overlap",
        "vi": "Vùng Chồng lấn",
    },
    "interlocking_table.header.overlap_release": {
        "en": "Overlap\nRelease Time",
        "vi": "Thời gian giải phóng\nVùng chồng lấn",
    },
    "field.entry": {
        "en": "Entry",
        "vi": "Vào",
    },
    "field.exit": {
        "en": "Exit",
        "vi": "Ra",
    },
    "field.overlap": {
        "en": "Overlap",
        "vi": "Chồng lấn",
    },
    "field.approach_release": {
        "en": "Approach release",
        "vi": "Thời gian giải phóng khóa tiếp cận",
    },
    "field.overlap_release": {
        "en": "Overlap release",
        "vi": "Thời gian giải phóng chồng lấn",
    },
    "field.id": {
        "en": "ID",
        "vi": "ID",
    },
    "field.length": {
        "en": "Length",
        "vi": "Chiều dài",
    },
    "field.state": {
        "en": "State",
        "vi": "Trạng thái",
    },
    "field.locked_by": {
        "en": "Locked by",
        "vi": "Khóa bởi",
    },
    "field.position": {
        "en": "Position",
        "vi": "Vị trí",
    },
    "field.symbol": {
        "en": "Symbol",
        "vi": "Ký hiệu",
    },
    "field.normal_to": {
        "en": "Normal ->",
        "vi": "Định vị ->",
    },
    "field.reverse_to": {
        "en": "Reverse ->",
        "vi": "Phản vị ->",
    },
    "field.protects": {
        "en": "Protects",
        "vi": "Bảo vệ",
    },
    "field.approach_section": {
        "en": "Approach section",
        "vi": "Khu đoạn tiếp cận",
    },
    "field.direction": {
        "en": "Direction",
        "vi": "Hướng",
    },
    "field.aspect": {
        "en": "Aspect",
        "vi": "Chỉ thị",
    },
    "field.text": {
        "en": "Text",
        "vi": "Nội dung",
    },
    "field.font_size": {
        "en": "Font size",
        "vi": "Cỡ chữ",
    },
    "field.element_id_placeholder": {
        "en": "Element ID",
        "vi": "Mã phần tử",
    },
    "unit.seconds_suffix": {
        "en": " s",
        "vi": " s",
    },
    "state.free": {
        "en": "FREE",
        "vi": "Thanh Thoát",
    },
    "state.occupied": {
        "en": "OCCUPIED",
        "vi": "Chiếm Dụng",
    },
    "point_position.normal": {
        "en": "NORMAL",
        "vi": "Định vị",
    },
    "point_position.reverse": {
        "en": "REVERSE",
        "vi": "Phản vị",
    },
    "signal_direction.left": {
        "en": "LEFT",
        "vi": "TRÁI",
    },
    "signal_direction.right": {
        "en": "RIGHT",
        "vi": "PHẢI",
    },
    "route_lifecycle.reserved": {
        "en": "RESERVED",
        "vi": "DỰ TRỮ",
    },
    "route_lifecycle.cleared_reversible": {
        "en": "CLEARED_REVERSIBLE",
        "vi": "ĐÃ THIẾT LẬP",
    },
    "route_lifecycle.approach_locked": {
        "en": "APPROACH_LOCKED",
        "vi": "KHÓA TIẾP CẬN",
    },
    "route_lifecycle.train_in_route": {
        "en": "TRAIN_IN_ROUTE",
        "vi": "TÀU TRONG HÀNH TRÌNH",
    },
    "route_lifecycle.releasing": {
        "en": "RELEASING",
        "vi": "ĐANG giải phóng",
    },
    "route_lifecycle.released": {
        "en": "RELEASED",
        "vi": "ĐÃ giải phóng",
    },
    "approach_lock_state.route_set": {
        "en": "ROUTE_SET",
        "vi": "ĐÃ ĐẶT HÀNH TRÌNH",
    },
    "approach_lock_state.approach_locked": {
        "en": "APPROACH_LOCKED",
        "vi": "KHÓA TIẾP CẬN",
    },
    "approach_lock_state.time_locked": {
        "en": "TIME_LOCKED",
        "vi": "KHÓA THỜI GIAN",
    },
    "signal_aspect.stop": {
        "en": "STOP",
        "vi": "DỪNG",
    },
    "signal_aspect.proceed": {
        "en": "PROCEED",
        "vi": "ĐI",
    },
    "palette.components": {
        "en": "Components",
        "vi": "Thành phần",
    },
    "palette.hint": {
        "en": "Drag modules to canvas (or double-click to add). Use Add text label for drawing notes. Right-click or use Delete/F2 to edit.",
        "vi": "Kéo thả phần tử vào canvas (hoặc nhấp đôi để thêm). Dùng Nhãn chữ để ghi chú bản vẽ. Bấm chuột phải hoặc Delete/F2 để sửa.",
    },
    "palette.component.section": {
        "en": "Section",
        "vi": "Khu đoạn",
    },
    "palette.component.approach": {
        "en": "Approach",
        "vi": "Khu đoạn tiếp cận",
    },
    "palette.component.point": {
        "en": "Point",
        "vi": "Ghi",
    },
    "palette.component.signal": {
        "en": "Signal",
        "vi": "Tín hiệu",
    },
    "palette.add_label": {
        "en": "Add text label",
        "vi": "Thêm nhãn chữ",
    },
    "properties.title": {
        "en": "Properties",
        "vi": "Thuộc tính",
    },
    "properties.placeholder": {
        "en": "Select a block to edit its properties.",
        "vi": "Chọn một phần tử để chỉnh sửa thuộc tính.",
    },
    "dialog.new_layout.title": {
        "en": "New layout",
        "vi": "Tạo sơ đồ mới",
    },
    "dialog.new_layout.message": {
        "en": "Clear current layout and start a new one?",
        "vi": "Xóa sơ đồ hiện tại và tạo sơ đồ mới?",
    },
    "dialog.connect_mode.title": {
        "en": "Connect mode",
        "vi": "Chế độ nối",
    },
    "dialog.connect_mode.only_design_layout": {
        "en": "Connect mode is available only in Design Layout workspace.",
        "vi": "Chế độ nối chỉ khả dụng trong không gian Thiết kế sa bàn.",
    },
    "dialog.cannot_add_component.title": {
        "en": "Cannot add component",
        "vi": "Không thể thêm phần tử",
    },
    "dialog.cannot_add_label.title": {
        "en": "Cannot add text label",
        "vi": "Không thể thêm nhãn chữ",
    },
    "dialog.property_update_failed.title": {
        "en": "Property update failed",
        "vi": "Cập nhật thuộc tính thất bại",
    },
    "dialog.save_layout.title": {
        "en": "Save Layout",
        "vi": "Lưu sơ đồ",
    },
    "dialog.load_layout.title": {
        "en": "Load Layout",
        "vi": "Mở sơ đồ",
    },
    "dialog.file_filter.json": {
        "en": "JSON Files (*.json)",
        "vi": "Tập tin JSON (*.json)",
    },
    "dialog.save_failed.title": {
        "en": "Save failed",
        "vi": "Lưu thất bại",
    },
    "dialog.load_failed.title": {
        "en": "Load failed",
        "vi": "Mở thất bại",
    },
    "dialog.load_occupancy.title": {
        "en": "Load occupancy state",
        "vi": "Tải trạng thái chiếm dụng",
    },
    "dialog.load_occupancy.message": {
        "en": "Restore OCCUPIED/FREE states from file?\nRoute locks and signal route states are always reset on load.",
        "vi": "Khôi phục trạng thái CHIẾM DỤNG/THANH THOÁT từ tập tin?\nKhóa hành trình và trạng thái tín hiệu sẽ luôn được đặt lại khi mở.",
    },
    "dialog.find_route.title": {
        "en": "Find Route",
        "vi": "Tìm hành trình",
    },
    "dialog.find_route.select_both": {
        "en": "Please select both Entry and Exit signals.",
        "vi": "Vui lòng chọn cả tín hiệu vào và ra.",
    },
    "dialog.find_route.same_signal": {
        "en": "Entry and Exit must be different signals.",
        "vi": "Tín hiệu vào và ra phải khác nhau.",
    },
    "dialog.find_route.no_valid_route": {
        "en": "No valid route is defined for {entry} -> {exit} in the current interlocking table.",
        "vi": "Không có hành trình hợp lệ cho {entry} -> {exit} trong bảng liên khóa hiện tại.",
    },
    "dialog.route_unavailable.title": {
        "en": "Route unavailable",
        "vi": "Không tìm thấy hành trình",
    },
    "dialog.set_route.title": {
        "en": "Set Route",
        "vi": "Thiết lập hành trình",
    },
    "dialog.set_route.switch_workspace": {
        "en": "Switch to Simulation or Runtime workspace to set routes.",
        "vi": "Chuyển sang không gian Mô phỏng hoặc Vận hành để thiết lập hành trình.",
    },
    "dialog.set_route.failed_title": {
        "en": "Set Route failed",
        "vi": "Thiết lập hành trình thất bại",
    },
    "dialog.simulation.title": {
        "en": "Simulation",
        "vi": "Mô phỏng",
    },
    "dialog.simulation.switch_workspace": {
        "en": "Switch to Simulation workspace to start or stop train simulation.",
        "vi": "Chuyển sang không gian Mô phỏng để bắt đầu hoặc dừng mô phỏng tàu.",
    },
    "dialog.simulation.select_both": {
        "en": "Please choose both Entry and Exit signals.",
        "vi": "Vui lòng chọn cả tín hiệu vào và ra.",
    },
    "dialog.simulation.same_signal": {
        "en": "Entry and Exit must be different signals.",
        "vi": "Tín hiệu vào và ra phải khác nhau.",
    },
    "dialog.simulation.at_least_two_signals": {
        "en": "At least two signals are required.",
        "vi": "Cần tối thiểu hai tín hiệu.",
    },
    "dialog.simulation.set_route_first": {
        "en": "Please Set Route first for the selected Entry/Exit before starting simulation.",
        "vi": "Vui lòng thiết lập hành trình cho cặp Vào/Ra đã chọn trước khi mô phỏng.",
    },
    "dialog.simulation_failed.title": {
        "en": "Simulation failed",
        "vi": "Mô phỏng thất bại",
    },
    "dialog.runtime_requires_smartio.title": {
        "en": "Runtime unavailable",
        "vi": "Không thể vào Runtime",
    },
    "dialog.runtime_requires_smartio.message": {
        "en": "Runtime workspace requires SmartIO connection.\nURL: {url}\nCurrent state: {state}",
        "vi": "Workspace Runtime yêu cầu kết nối SmartIO.\nURL: {url}\nTrạng thái hiện tại: {state}",
    },
    "dialog.smartio_local_failed.title": {
        "en": "SmartIO Local failed",
        "vi": "SmartIO Local kh?ng kh?i ??ng ???c",
    },
    "dialog.fail_safe_stop.title": {
        "en": "Fail-safe STOP",
        "vi": "Dừng an toàn",
    },
    "dialog.cancel_route.title": {
        "en": "Cancel route",
        "vi": "Hủy hành trình",
    },
    "dialog.cancel_route.some_locked": {
        "en": "Some routes remain locked:\n{details}",
        "vi": "Một số hành trình vẫn đang bị khóa:\n{details}",
    },
    "dialog.emergency_release.title": {
        "en": "Emergency route release",
        "vi": "Giải phóng hành trình khẩn cấp",
    },
    "dialog.emergency_release.password_prompt": {
        "en": "Enter emergency release password:",
        "vi": "Nhập mật khẩu giải phóng khẩn cấp:",
    },
    "dialog.emergency_release.password_invalid": {
        "en": "Invalid emergency release password.",
        "vi": "Mật khẩu giải phóng khẩn cấp không đúng.",
    },
    "dialog.emergency_release.some_failed": {
        "en": "Some routes could not be emergency-released:\n{details}",
        "vi": "Một số hành trình không thể giải phóng khẩn cấp:\n{details}",
    },
    "dialog.invalid_signal_config.message": {
        "en": "Invalid signal/topology configuration:\n{issues}",
        "vi": "Cấu hình tín hiệu/topology không hợp lệ:\n{issues}",
    },
    "status.loaded_sample_layout": {
        "en": "Loaded sample layout: {path}",
        "vi": "Đã tải sơ đồ mẫu: {path}",
    },
    "status.started_new_empty_layout": {
        "en": "Started a new empty layout",
        "vi": "Đã tạo sơ đồ Thanh Thoát mới",
    },
    "status.component_added": {
        "en": "Added {element_type}",
        "vi": "Đã thêm {element_type}",
    },
    "status.label_added": {
        "en": "Added text label",
        "vi": "Đã thêm nhãn chữ",
    },
    "status.simulation_stopped_workspace": {
        "en": "Simulation stopped after leaving Simulation workspace.",
        "vi": "Đã dừng mô phỏng sau khi rời khỏi không gian Mô phỏng.",
    },
    "status.workspace_mode": {
        "en": "Workspace mode: {mode}",
        "vi": "Chế độ không gian làm việc: {mode}",
    },
    "status.updated_element": {
        "en": "Updated {element_id}",
        "vi": "Đã cập nhật {element_id}",
    },
    "status.saved_layout": {
        "en": "Saved layout to {path}",
        "vi": "Đã lưu sơ đồ tới {path}",
    },
    "status.loaded_layout": {
        "en": "Loaded layout from {path}",
        "vi": "Đã mở sơ đồ từ {path}",
    },
    "status.preview_route": {
        "en": "Preview route: {entry} -> {exit}",
        "vi": "Xem trước hành trình: {entry} -> {exit}",
    },
    "status.route_set": {
        "en": "Route set: {entry} -> {exit}",
        "vi": "Đã thiết lập hành trình: {entry} -> {exit}",
    },
    "status.route_already_active": {
        "en": "Route already active: {entry} -> {exit}",
        "vi": "Hành trình đã hoạt động: {entry} -> {exit}",
    },
    "status.simulation_running": {
        "en": "Simulation running: {entry} -> {exit}, route={route_id}, train={train_id}, start={start}",
        "vi": "Đang mô phỏng: {entry} -> {exit}, route={route_id}, train={train_id}, start={start}",
    },
    "status.simulation_stopped": {
        "en": "Simulation stopped",
        "vi": "Đã dừng mô phỏng",
    },
    "status.simulation_halted_fail_safe": {
        "en": "Simulation halted by fail-safe",
        "vi": "Mô phỏng đã dừng bởi cơ chế fail-safe",
    },
    "status.simulation_complete": {
        "en": "Simulation complete",
        "vi": "Mô phỏng hoàn tất",
    },
    "status.cancel_route_disabled": {
        "en": "Cancel route is disabled in Design Layout workspace",
        "vi": "Không thể hủy hành trình trong không gian Thiết kế sa bàn",
    },
    "status.no_active_simulation_routes": {
        "en": "No active simulation routes to cancel",
        "vi": "Không có hành trình mô phỏng đang hoạt động để hủy",
    },
    "status.no_active_routes": {
        "en": "No active routes to cancel",
        "vi": "Không có hành trình đang hoạt động để hủy",
    },
    "status.cancelled_all_active_routes": {
        "en": "Cancelled all active routes",
        "vi": "Đã hủy tất cả hành trình đang hoạt động",
    },
    "status.emergency_release_disabled": {
        "en": "Emergency release is disabled in Design Layout workspace",
        "vi": "Không thể giải phóng khẩn cấp trong không gian Thiết kế sa bàn",
    },
    "status.emergency_released_all_active_routes": {
        "en": "Emergency released all active routes",
        "vi": "Đã giải phóng khẩn cấp tất cả hành trình đang hoạt động",
    },
    "status.smartio_error": {
        "en": "SmartIO error: {message}",
        "vi": "SmartIO error: {message}",
    },
    "status.smartio_local_started": {
        "en": "SmartIO Local started with {path} at {url}",
        "vi": "SmartIO Local ?? kh?i ??ng v?i {path} t?i {url}",
    },
    "status.smartio_local_opened": {
        "en": "Opened SmartIO Local at {url}",
        "vi": "?? m? SmartIO Local t?i {url}",
    },
    "status.smartio_local_failed": {
        "en": "SmartIO Local failed to start",
        "vi": "SmartIO Local kh?ng kh?i ??ng ???c",
    },
    "status.runtime_requires_smartio": {
        "en": "Runtime requires SmartIO connected (current: {state})",
        "vi": "Runtime yêu cầu SmartIO đã kết nối (hiện tại: {state})",
    },
    "runtime.smartio.status": {
        "en": "SmartIO: {state}",
        "vi": "SmartIO: {state}",
    },
    "smartio.state.connected": {
        "en": "connected",
        "vi": "connected",
    },
    "smartio.state.connecting": {
        "en": "connecting",
        "vi": "connecting",
    },
    "smartio.state.disconnected": {
        "en": "disconnected",
        "vi": "disconnected",
    },
    "smartio.state.reconnecting": {
        "en": "reconnecting in {seconds}s",
        "vi": "reconnecting in {seconds}s",
    },
    "smartio.state.error": {
        "en": "error",
        "vi": "error",
    },
    "smartio.state.disabled": {
        "en": "disabled (missing URL)",
        "vi": "disabled (missing URL)",
    },
    "main.lock.layout_edit_reason": {
        "en": "Switch to Design Layout workspace to modify topology and static properties.",
        "vi": "Chuyển sang không gian Thiết kế sa bàn để sửa topology và thuộc tính tĩnh.",
    },
    "main.tooltip.component_insertion_disabled": {
        "en": "Component insertion is available only in Design Layout workspace.",
        "vi": "Chỉ có thể chèn phần tử trong không gian Thiết kế sa bàn.",
    },
    "main.lock.runtime_edit_reason": {
        "en": "Manual occupied/locked_by editing is blocked in Runtime workspace.",
        "vi": "Không cho phép sửa occupied/locked_by thủ công trong không gian Vận hành.",
    },
    "canvas.menu.edit_properties": {
        "en": "Edit properties",
        "vi": "Sửa thuộc tính",
    },
    "canvas.menu.rename": {
        "en": "Rename",
        "vi": "Đổi tên",
    },
    "canvas.menu.delete": {
        "en": "Delete",
        "vi": "Xóa",
    },
    "canvas.menu.delete_connection": {
        "en": "Delete connection",
        "vi": "Xóa kết nối",
    },
    "canvas.menu.connect_pair": {
        "en": "Connect {source} to {target}",
        "vi": "Nối {source} tới {target}",
    },
    "canvas.dialog.cannot_add_component.title": {
        "en": "Cannot add component",
        "vi": "Không thể thêm phần tử",
    },
    "canvas.dialog.connection_rejected.title": {
        "en": "Connection rejected",
        "vi": "Kết nối bị từ chối",
    },
    "canvas.dialog.rename_element.title": {
        "en": "Rename element",
        "vi": "Đổi tên phần tử",
    },
    "canvas.dialog.rename_element.prompt": {
        "en": "New ID:",
        "vi": "ID mới:",
    },
    "canvas.dialog.rename_failed.title": {
        "en": "Rename failed",
        "vi": "Đổi tên thất bại",
    },
    "canvas.dialog.edit_element.title": {
        "en": "Edit {element_id}",
        "vi": "Sửa {element_id}",
    },
    "canvas.dialog.property_update_failed.title": {
        "en": "Property update failed",
        "vi": "Cập nhật thuộc tính thất bại",
    },
    "canvas.message.connect_start_select_target": {
        "en": "Connect mode: start {node_id}. Click target node to create connection.",
        "vi": "Chế độ nối: bắt đầu từ {node_id}. Bấm vào nút đích để tạo kết nối.",
    },
    "canvas.message.connect_start_select_another": {
        "en": "Connect mode: start {node_id}. Click another node as target.",
        "vi": "Chế độ nối: bắt đầu từ {node_id}. Bấm vào nút khác làm đích.",
    },
    "canvas.message.connected_pair": {
        "en": "Connected {source} to {target}",
        "vi": "Đã nối {source} tới {target}",
    },
    "canvas.message.undo_completed": {
        "en": "Undo completed",
        "vi": "Hoàn tác thành công",
    },
    "canvas.message.nothing_to_undo": {
        "en": "Nothing to undo",
        "vi": "Không có gì để hoàn tác",
    },
    "canvas.message.redo_completed": {
        "en": "Redo completed",
        "vi": "Làm lại thành công",
    },
    "canvas.message.nothing_to_redo": {
        "en": "Nothing to redo",
        "vi": "Không có gì để làm lại",
    },
    "canvas.message.connect_mode_canceled_source": {
        "en": "Connect mode: canceled source selection",
        "vi": "Chế độ nối: đã hủy chọn nút nguồn",
    },
    "canvas.message.connect_mode_on": {
        "en": "Connect mode ON: click source node, then target node",
        "vi": "Bật chế độ nối: bấm nút nguồn, sau đó bấm nút đích",
    },
    "canvas.message.connect_mode_off": {
        "en": "Connect mode OFF",
        "vi": "Tắt chế độ nối",
    },
    "canvas.message.manual_free_removed_trains": {
        "en": "Manual FREE on {section_id}: removed train(s) {train_ids} from simulation state.",
        "vi": "Đặt THANH THOÁT thủ công tại {section_id}: đã xóa tàu {train_ids} khỏi trạng thái mô phỏng.",
    },
    "canvas.lock.layout_editing_locked": {
        "en": "Layout editing is locked.",
        "vi": "Đang khóa chỉnh sửa bố cục.",
    },
    "canvas.lock.runtime_lock_active": {
        "en": "Runtime lock active",
        "vi": "Đang khóa trong chế độ vận hành",
    },
    "canvas.action.add_components": {
        "en": "add components",
        "vi": "thêm phần tử",
    },
    "canvas.action.create_connections": {
        "en": "create connections",
        "vi": "tạo kết nối",
    },
    "canvas.action.rename_elements": {
        "en": "rename elements",
        "vi": "đổi tên phần tử",
    },
    "canvas.action.delete_elements_or_connections": {
        "en": "delete elements or connections",
        "vi": "xóa phần tử hoặc kết nối",
    },
    "canvas.action.delete_elements": {
        "en": "delete elements",
        "vi": "xóa phần tử",
    },
    "canvas.action.delete_connections": {
        "en": "delete connections",
        "vi": "xóa kết nối",
    },
    "canvas.error.layout_edit_locked": {
        "en": "Cannot {action} while layout editing is locked. {reason}",
        "vi": "Không thể {action} khi đang khóa chỉnh sửa bố cục. {reason}",
    },
    "canvas.error.select_exactly_two_modules": {
        "en": "Select exactly 2 modules to connect",
        "vi": "Hãy chọn đúng 2 phần tử để nối",
    },
    "canvas.error.unsupported_element_type": {
        "en": "Unsupported element type: {element_type}",
        "vi": "Loại phần tử không được hỗ trợ: {element_type}",
    },
    "canvas.error.element_id_exists": {
        "en": "Element id already exists: {element_id}",
        "vi": "ID phần tử đã tồn tại: {element_id}",
    },
    "canvas.error.connection_requires_existing_nodes": {
        "en": "Connection requires existing source and target nodes",
        "vi": "Kết nối yêu cầu nút nguồn và nút đích đã tồn tại",
    },
    "canvas.error.cannot_self_connect": {
        "en": "Cannot self-connect",
        "vi": "Không thể tự nối với chính nó",
    },
    "canvas.error.cannot_connect_label": {
        "en": "Text labels are visual only and cannot be connected.",
        "vi": "Nhãn chữ chỉ dùng để hiển thị và không thể nối.",
    },
    "canvas.error.unknown_element": {
        "en": "Unknown element {element_id}",
        "vi": "Không tìm thấy phần tử {element_id}",
    },
    "canvas.error.point_locked_by": {
        "en": "Point {point_id} is locked by {locked_by}. Unlock before moving.",
        "vi": "Ghi {point_id} đang bị khóa bởi {locked_by}. Hãy mở khóa trước khi chuyển.",
    },
    "canvas.error.protects_invalid": {
        "en": "Protects must reference an existing track section or point node",
        "vi": "Protects phải trỏ đến khu đoạn hoặc nút ghi đã tồn tại",
    },
    "canvas.error.approach_section_invalid": {
        "en": "Approach section must reference an existing ApproachSection node",
        "vi": "Khu đoạn tiếp cận phải trỏ đến nút ApproachSection đã tồn tại",
    },
    "canvas.error.approach_section_rear_side": {
        "en": "Approach section must be on the rear side of the signal direction",
        "vi": "Khu đoạn tiếp cận phải nằm ở phía sau theo hướng của tín hiệu",
    },
    "canvas.error.cannot_edit_length_locked": {
        "en": "Cannot edit length while layout editing is locked. {reason}",
        "vi": "Không thể sửa chiều dài khi đang khóa chỉnh sửa bố cục. {reason}",
    },
    "canvas.error.cannot_edit_point_symbol_locked": {
        "en": "Cannot edit point symbol while layout editing is locked. {reason}",
        "vi": "Không thể sửa ký hiệu ghi khi đang khóa chỉnh sửa bố cục. {reason}",
    },
    "canvas.error.cannot_edit_point_targets_locked": {
        "en": "Cannot edit point targets while layout editing is locked. {reason}",
        "vi": "Không thể sửa điểm đích của ghi khi đang khóa chỉnh sửa bố cục. {reason}",
    },
    "canvas.error.cannot_edit_signal_protection_locked": {
        "en": "Cannot edit signal protection while layout editing is locked. {reason}",
        "vi": "Không thể sửa bảo vệ tín hiệu khi đang khóa chỉnh sửa bố cục. {reason}",
    },
    "canvas.error.cannot_edit_signal_approach_locked": {
        "en": "Cannot edit signal approach section while layout editing is locked. {reason}",
        "vi": "Không thể sửa khu đoạn tiếp cận của tín hiệu khi đang khóa chỉnh sửa bố cục. {reason}",
    },
    "canvas.error.cannot_edit_signal_direction_locked": {
        "en": "Cannot edit signal direction while layout editing is locked. {reason}",
        "vi": "Không thể sửa hướng tín hiệu khi đang khóa chỉnh sửa bố cục. {reason}",
    },
    "canvas.error.cannot_edit_occupied_runtime": {
        "en": "Cannot edit occupied while runtime is active. {reason}",
        "vi": "Không thể sửa occupied khi đang vận hành. {reason}",
    },
    "canvas.error.cannot_edit_locked_by_runtime": {
        "en": "Cannot edit locked_by while runtime is active. {reason}",
        "vi": "Không thể sửa locked_by khi đang vận hành. {reason}",
    },
    "route_log.section.summary": {
        "en": "[ROUTE SUMMARY]",
        "vi": "[TÓM TẮT HÀNH TRÌNH]",
    },
    "route_log.section.path_lock": {
        "en": "[PATH & LOCK]",
        "vi": "[ĐƯỜNG ĐI & KHÓA]",
    },
    "route_log.section.safety_conflict": {
        "en": "[SAFETY & CONFLICT]",
        "vi": "[AN TOÀN & XUNG ĐỘT]",
    },
    "route_log.label.route": {
        "en": "Route",
        "vi": "Hành trình",
    },
    "route_log.label.entry": {
        "en": "Entry",
        "vi": "Vào",
    },
    "route_log.label.exit": {
        "en": "Exit",
        "vi": "Ra",
    },
    "route_log.label.direction": {
        "en": "Direction",
        "vi": "Hướng",
    },
    "route_log.label.lifecycle": {
        "en": "Lifecycle",
        "vi": "Vòng đời",
    },
    "route_log.label.search_order": {
        "en": "Search order",
        "vi": "Thứ tự tìm kiếm",
    },
    "route_log.label.locked_path": {
        "en": "Locked path",
        "vi": "Đường chạy đã khóa",
    },
    "route_log.label.overlap": {
        "en": "Overlap",
        "vi": "Chồng lấn",
    },
    "route_log.label.destination_track": {
        "en": "Destination track",
        "vi": "Đường chạy đích",
    },
    "route_log.label.point_locks": {
        "en": "Point locks",
        "vi": "Khóa ghi",
    },
    "route_log.label.flank_points": {
        "en": "Flank points",
        "vi": "Ghi sườn",
    },
    "route_log.label.flank_monitored_sections": {
        "en": "Flank monitored sections",
        "vi": "Khu đoạn sườn được giám sát",
    },
    "route_log.label.opposing_signals": {
        "en": "Opposing signals",
        "vi": "Tín hiệu đối hướng",
    },
    "route_log.label.conflicting_routes": {
        "en": "Conflicting routes",
        "vi": "Hành trình xung đột",
    },
    "route_log.label.approach_locking_section": {
        "en": "Approach locking section",
        "vi": "Khu đoạn khóa tiếp cận",
    },
    "route_log.label.approach_lock_state": {
        "en": "Approach lock state",
        "vi": "Trạng thái khóa tiếp cận",
    },
    "route_log.label.overlap_release": {
        "en": "Overlap release",
        "vi": "Giải phóng chồng lấn",
    },
    "route_log.entry_line": {
        "en": "{entry_signal} protects {entry_protects}",
        "vi": "{entry_signal} bảo vệ {entry_protects}",
    },
    "route_log.exit_line": {
        "en": "{exit_signal} protects {exit_protects}",
        "vi": "{exit_signal} bảo vệ {exit_protects}",
    },
    "route_log.approach_lock_remaining": {
        "en": "{state} ({seconds:.1f}s remaining)",
        "vi": "{state} (còn {seconds:.1f}s)",
    },
}


def normalize_language(language: str | None) -> str:
    if language is None:
        return DEFAULT_LANGUAGE
    language_code = str(language).strip().lower()
    if language_code.startswith("vi"):
        return "vi"
    return "en"


class UITranslator:
    """Translate UI text with keyed messages."""

    def __init__(self, language: str = DEFAULT_LANGUAGE) -> None:
        self._language = normalize_language(language)

    @property
    def language(self) -> str:
        return self._language

    def set_language(self, language: str) -> str:
        self._language = normalize_language(language)
        return self._language

    def t(self, key: str, **kwargs: object) -> str:
        translated = TRANSLATIONS.get(key)
        if translated is None:
            template = key
        else:
            template = translated.get(self._language) or translated.get(DEFAULT_LANGUAGE) or key
        if not kwargs:
            return template
        try:
            return template.format(**kwargs)
        except Exception:
            return template

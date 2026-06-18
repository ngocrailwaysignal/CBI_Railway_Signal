const SUPPORTED_LANGUAGES = new Set(["en", "vi"]);
const STORAGE_KEY = "cbi.webclient.language";

const STRINGS = {
  en: {
    "language.label": "Language",
    "language.en": "English",
    "language.vi": "Vietnamese",
    "viewer.title": "Dispatcher Viewer",
    "viewer.heading": "Dispatcher",
    "viewer.open_editor": "Open Editor",
    "viewer.hide_routes": "Hide Routes",
    "viewer.show_routes": "Show Routes",
    "viewer.hide_debug": "Hide Debug",
    "viewer.show_debug": "Show Debug",
    "viewer.waiting_runtime": "WAITING RUNTIME",
    "viewer.live_runtime": "LIVE RUNTIME",
    "viewer.runtime_error": "RUNTIME ERROR",
    "viewer.runtime_feed": "Runtime Feed",
    "viewer.waiting_for_runtime": "Waiting For Runtime",
    "viewer.loading_runtime": "Loading runtime feed...",
    "viewer.workspace_suffix": "workspace",
    "viewer.routes": "routes",
    "viewer.trains": "trains",
    "viewer.occupied": "occupied",
    "viewer.updated": "updated",
    "route.error.cannot_lock_route": "Cannot lock route: {reason}",
    "route.error.already_active": "Route {route_id} is already active",
    "route.error.unknown_point": "Route refers to unknown point {point_id}",
    "route.error.point_locked": "Point {point_id} is locked by {locked_by}",
    "route.error.section_locked": "Section {section_id} is already locked by {locked_by}",
    "route.error.occupied_by_train": "Route {route_id} is occupied by train on sections: {sections}",
    "route.error.section_multiple_active_routes": "Section {section_id} belongs to multiple active routes: {routes}",
    "viewer.route": "Route",
    "viewer.entry": "Entry",
    "viewer.exit": "Exit",
    "viewer.tracks": "Tracks",
    "viewer.points": "Points",
    "viewer.set_route": "Set Route",
    "viewer.cancel_routes": "Cancel Routes",
    "viewer.controls_waiting": "Runtime controls waiting...",
    "viewer.fit": "Fit",
    "viewer.fit_title": "Fit schematic",
    "viewer.zoom_out": "Zoom out",
    "viewer.zoom_in": "Zoom in",
    "viewer.dispatcher_board": "Dispatcher Board",
    "viewer.no_diagram": "No Dispatcher Diagram Authored",
    "viewer.clean_track_hint":
      "Clean track is green, occupied track is red, and active routes extend across the full path.",
    "viewer.no_schematic_hint":
      "No dispatcher schematic exists yet. Open /dispatcher/editor to draw and bind the board.",
    "viewer.select_route": "Select route",
    "viewer.controls_disabled": "Route controls disabled for this workspace mode.",
    "viewer.no_routes": "No interlocking routes available.",
    "viewer.empty_board": "No dispatcher schematic. Open /dispatcher/editor to create one.",
    "viewer.feed_error": "Runtime feed error: {message}",
    "viewer.command_error": "Runtime feed error.",
    "viewer.select_interlocking_route": "Select an interlocking route.",
    "viewer.entry_exit_different": "Entry and exit signals must be different.",
    "viewer.queue_set_route": "Queueing set route command...",
    "viewer.command_queued": "Command queued. Waiting for runtime...",
    "viewer.set_route_rejected": "Set route rejected.",
    "viewer.route_applied": "Route command applied: {entry} -> {exit}",
    "viewer.result_pending": "Command queued; runtime result pending.",
    "viewer.queue_cancel_routes": "Queueing cancel routes command...",
    "viewer.cancel_rejected": "Cancel routes rejected.",
    "viewer.cancel_applied": "Cancel routes applied. Cancelled: {count}",
    "editor.title": "Dispatcher Editor",
    "editor.heading": "Dispatcher Editor",
    "editor.subtitle":
      "Draw the station schematic manually, then bind each visual element to CBI IDs.",
    "editor.open_viewer": "Open Viewer",
    "editor.save_schematic": "Save Schematic",
    "editor.clear_canvas": "Clear Canvas",
    "editor.reload": "Reload",
    "editor.toolbox": "Toolbox",
    "editor.track_section": "Track Section",
    "editor.signal": "Signal",
    "editor.point": "Point",
    "editor.label": "Label",
    "editor.block_marker": "Block Marker",
    "editor.toolbox_hint":
      "Drag a tool onto the board or click a tool to insert it at the center.",
    "editor.canvas": "Canvas",
    "editor.snap_to_grid": "Snap To Grid",
    "editor.grid_size": "Grid Size",
    "editor.canvas_width": "Canvas Width",
    "editor.canvas_height": "Canvas Height",
    "editor.show_debug_ids": "Show Debug IDs",
    "editor.status": "Status",
    "editor.layout_file": "Layout File",
    "editor.loading": "Loading dispatcher schematic...",
    "editor.authoring_surface": "Authoring Surface",
    "editor.canvas_heading": "Dispatcher Schematic Canvas",
    "editor.board_hint":
      "Shift/Ctrl click to multi-select, drag selected elements to move, and use handles to rotate or reshape.",
    "editor.inspector": "Inspector",
    "editor.empty_board": "Drag elements here to author the dispatcher schematic.",
    "editor.select_to_edit": "Select one or more elements to edit geometry and CBI bindings.",
    "editor.elements_selected": "{count} elements selected. Drag to move as a group.",
    "editor.elements_selected_title": "{count} Elements Selected",
    "editor.element_id": "Element ID",
    "editor.position": "Position",
    "editor.rotate": "Rotate {degrees} deg",
    "editor.track_style": "Track Style",
    "editor.stroke_width": "Stroke Width",
    "editor.mast": "Mast",
    "editor.arm": "Arm",
    "editor.branch_side": "Branch Side",
    "editor.straight": "Straight",
    "editor.branch": "Branch",
    "editor.text": "Text",
    "editor.font_size": "Font Size",
    "editor.align": "Align",
    "editor.tone": "Tone",
    "editor.width": "Width",
    "editor.height": "Height",
    "editor.cbi_binding": "CBI Binding ({type})",
    "editor.no_ids": "No {type} IDs available from the current CBI layout.",
    "editor.binding_hint": "Click one {type} ID below to bind it to the selected element.",
    "editor.unbound": "Unbound ({type})",
    "editor.filter_ids": "Filter {type} IDs",
    "editor.available_ids": "Available IDs",
    "editor.unbind": "Unbind",
    "editor.used_by": "Currently used by {owners}",
    "editor.used_by_this": "used by this element",
    "editor.delete_this": "Delete This Element",
    "editor.quick_actions": "Editor quick actions",
    "editor.undo": "Undo",
    "editor.redo": "Redo",
    "editor.copy": "Copy",
    "editor.paste": "Paste",
    "editor.duplicate": "Duplicate",
    "editor.delete": "Delete",
    "editor.delete_selected": "Delete Selected",
    "editor.select_all": "Select All",
    "editor.next_unbound": "Next Unbound",
    "editor.batch_transform": "Batch Transform",
    "editor.align_selection": "Align Selection",
    "editor.align_left": "Left",
    "editor.align_center_x": "Center X",
    "editor.align_right": "Right",
    "editor.align_top": "Top",
    "editor.align_center_y": "Center Y",
    "editor.align_bottom": "Bottom",
    "editor.shortcut_hint": "Shortcuts: Ctrl+Z undo, Ctrl+D duplicate, arrows nudge. Alt/Space drag pans.",
    "editor.selection_count": "{count} selected",
    "editor.no_selection": "No selection",
    "editor.added_element": "Added {kind}.",
    "editor.deleted_elements": "Deleted {count} element(s).",
    "editor.copied_elements": "Copied {count} element(s).",
    "editor.pasted_elements": "Pasted {count} element(s).",
    "editor.duplicated_elements": "Duplicated {count} element(s).",
    "editor.selected_all": "Selected {count} element(s).",
    "editor.undo_completed": "Undo completed.",
    "editor.redo_completed": "Redo completed.",
    "editor.aligned_elements": "Aligned selected elements.",
    "editor.no_unbound_elements": "No unbound bindable elements.",
    "editor.selected_unbound": "Selected next unbound element: {id}",
    "editor.canvas_cleared": "Canvas cleared. Save to persist the empty schematic.",
    "editor.loaded": "Dispatcher schematic loaded.",
    "editor.load_failed": "Load failed: {message}",
    "editor.saving": "Saving dispatcher schematic...",
    "editor.saved": "Dispatcher schematic saved.",
    "editor.save_failed": "Save failed: {message}",
    "editor.already_empty": "Canvas is already empty.",
    "editor.confirm_clear":
      "Clear the entire dispatcher canvas? This removes all elements until you reload or save.",
  },
  vi: {
    "language.label": "Ngôn ngữ",
    "language.en": "Tiếng Anh",
    "language.vi": "Tiếng Việt",
    "viewer.title": "Màn hình điều độ",
    "viewer.heading": "Điều độ",
    "viewer.open_editor": "Mở trình chỉnh sửa",
    "viewer.hide_routes": "Ẩn hành trình",
    "viewer.show_routes": "Hiện hành trình",
    "viewer.hide_debug": "Ẩn debug",
    "viewer.show_debug": "Hiện debug",
    "viewer.waiting_runtime": "ĐANG CHỜ VẬN HÀNH",
    "viewer.live_runtime": "ĐANG VẬN HÀNH",
    "viewer.runtime_error": "LỖI VẬN HÀNH",
    "viewer.runtime_feed": "Dữ liệu vận hành",
    "viewer.waiting_for_runtime": "Đang chờ vận hành",
    "viewer.loading_runtime": "Đang tải dữ liệu vận hành...",
    "viewer.workspace_suffix": "không gian",
    "viewer.routes": "hành trình",
    "viewer.trains": "tàu",
    "viewer.occupied": "chiếm dụng",
    "viewer.updated": "cập nhật",
    "viewer.route": "Hành trình",
    "viewer.entry": "Vào",
    "viewer.exit": "Ra",
    "viewer.tracks": "Phân khu",
    "viewer.points": "Ghi",
    "route.error.cannot_lock_route": "Không thể khóa hành trình: {reason}",
    "route.error.already_active": "Hành trình {route_id} đã đang hoạt động",
    "route.error.unknown_point": "Hành trình tham chiếu tới ghi không tồn tại: {point_id}",
    "route.error.point_locked": "Ghi {point_id} đang bị khóa bởi {locked_by}",
    "route.error.section_locked": "Phân đoạn {section_id} đã bị khóa bởi {locked_by}",
    "route.error.occupied_by_train": "Hành trình {route_id} đang có tàu chiếm dụng tại các phân đoạn: {sections}",
    "route.error.section_multiple_active_routes": "Phân đoạn {section_id} thuộc nhiều hành trình đang hoạt động: {routes}",
    "viewer.set_route": "Thiết lập hành trình",
    "viewer.cancel_routes": "Hủy hành trình",
    "viewer.controls_waiting": "Đang chờ điều khiển vận hành...",
    "viewer.fit": "Vừa",
    "viewer.fit_title": "Căn vừa sơ đồ",
    "viewer.zoom_out": "Thu nhỏ",
    "viewer.zoom_in": "Phóng to",
    "viewer.dispatcher_board": "Bảng điều độ",
    "viewer.no_diagram": "Chưa có sơ đồ điều độ",
    "viewer.clean_track_hint":
      "Phân khu thanh thoát có màu xanh, phân khu chiếm dụng có màu đỏ, hành trình đang hoạt động kéo dài theo toàn tuyến.",
    "viewer.no_schematic_hint":
      "Chưa có sơ đồ điều độ. Mở /dispatcher/editor để vẽ và gán phần tử.",
    "viewer.select_route": "Chọn hành trình",
    "viewer.controls_disabled": "Điều khiển hành trình bị tắt trong chế độ không gian này.",
    "viewer.no_routes": "Không có hành trình liên khóa khả dụng.",
    "viewer.empty_board": "Chưa có sơ đồ điều độ. Mở /dispatcher/editor để tạo.",
    "viewer.feed_error": "Lỗi dữ liệu vận hành: {message}",
    "viewer.command_error": "Lỗi dữ liệu vận hành.",
    "viewer.select_interlocking_route": "Chọn một hành trình liên khóa.",
    "viewer.entry_exit_different": "Tín hiệu vào và ra phải khác nhau.",
    "viewer.queue_set_route": "Đang đưa lệnh thiết lập hành trình vào hàng đợi...",
    "viewer.command_queued": "Lệnh đã vào hàng đợi. Đang chờ vận hành...",
    "viewer.set_route_rejected": "Thiết lập hành trình bị từ chối.",
    "viewer.route_applied": "Đã áp dụng lệnh hành trình: {entry} -> {exit}",
    "viewer.result_pending": "Lệnh đã vào hàng đợi; đang chờ kết quả vận hành.",
    "viewer.queue_cancel_routes": "Đang đưa lệnh hủy hành trình vào hàng đợi...",
    "viewer.cancel_rejected": "Hủy hành trình bị từ chối.",
    "viewer.cancel_applied": "Đã áp dụng hủy hành trình. Đã hủy: {count}",
    "editor.title": "Trình chỉnh sửa điều độ",
    "editor.heading": "Trình chỉnh sửa điều độ",
    "editor.subtitle":
      "Vẽ sơ đồ ga thủ công, sau đó gán từng phần tử hiển thị với ID CBI.",
    "editor.open_viewer": "Mở màn hình xem",
    "editor.save_schematic": "Lưu sơ đồ",
    "editor.clear_canvas": "Xóa canvas",
    "editor.reload": "Tải lại",
    "editor.toolbox": "Hộp công cụ",
    "editor.track_section": "Phân khu",
    "editor.signal": "Tín hiệu",
    "editor.point": "Ghi",
    "editor.label": "Nhãn",
    "editor.block_marker": "Mốc block",
    "editor.toolbox_hint": "Kéo công cụ vào bảng hoặc bấm công cụ để chèn tại tâm.",
    "editor.canvas": "Canvas",
    "editor.snap_to_grid": "Bám lưới",
    "editor.grid_size": "Cỡ lưới",
    "editor.canvas_width": "Rộng canvas",
    "editor.canvas_height": "Cao canvas",
    "editor.show_debug_ids": "Hiện ID debug",
    "editor.status": "Trạng thái",
    "editor.layout_file": "Tệp sơ đồ",
    "editor.loading": "Đang tải sơ đồ điều độ...",
    "editor.authoring_surface": "Vùng soạn thảo",
    "editor.canvas_heading": "Canvas sơ đồ điều độ",
    "editor.board_hint":
      "Shift/Ctrl bấm để chọn nhiều, kéo phần tử đã chọn để di chuyển, dùng tay nắm để xoay hoặc chỉnh hình.",
    "editor.inspector": "Thuộc tính",
    "editor.empty_board": "Kéo phần tử vào đây để tạo sơ đồ điều độ.",
    "editor.select_to_edit": "Chọn một hoặc nhiều phần tử để sửa hình học và gán CBI.",
    "editor.elements_selected": "Đã chọn {count} phần tử. Kéo để di chuyển theo nhóm.",
    "editor.elements_selected_title": "{count} phan tu da chon",
    "editor.element_id": "ID phần tử",
    "editor.position": "Vị trí",
    "editor.rotate": "Xoay {degrees} độ",
    "editor.track_style": "Kiểu phân khu",
    "editor.stroke_width": "Độ dày nét",
    "editor.mast": "Cột",
    "editor.arm": "Cần",
    "editor.branch_side": "Nhánh rẽ",
    "editor.straight": "Thẳng",
    "editor.branch": "Nhánh",
    "editor.text": "Nội dung",
    "editor.font_size": "Cỡ chữ",
    "editor.align": "Căn chỉnh",
    "editor.tone": "Tông màu",
    "editor.width": "Chiều rộng",
    "editor.height": "Chiều cao",
    "editor.cbi_binding": "Gán CBI ({type})",
    "editor.no_ids": "Không có ID {type} từ sơ đồ CBI hiện tại.",
    "editor.binding_hint": "Bấm một ID {type} bên dưới để gán cho phần tử đã chọn.",
    "editor.unbound": "Chưa gán ({type})",
    "editor.filter_ids": "Lọc ID {type}",
    "editor.available_ids": "ID khả dụng",
    "editor.unbind": "Bỏ gán",
    "editor.used_by": "Đang được dùng bởi {owners}",
    "editor.used_by_this": "đang dùng bởi phần tử này",
    "editor.delete_this": "Xóa phần tử này",
    "editor.quick_actions": "Thao tac nhanh editor",
    "editor.undo": "Hoan tac",
    "editor.redo": "Lam lai",
    "editor.copy": "Sao chep",
    "editor.paste": "Dan",
    "editor.duplicate": "Nhan ban",
    "editor.delete": "Xoa",
    "editor.delete_selected": "Xoa phan tu da chon",
    "editor.select_all": "Chon tat ca",
    "editor.next_unbound": "Chua gan tiep",
    "editor.batch_transform": "Chinh hang loat",
    "editor.align_selection": "Can phan tu da chon",
    "editor.align_left": "Trai",
    "editor.align_center_x": "Giua X",
    "editor.align_right": "Phai",
    "editor.align_top": "Tren",
    "editor.align_center_y": "Giua Y",
    "editor.align_bottom": "Duoi",
    "editor.shortcut_hint": "Phim tat: Ctrl+Z hoan tac, Ctrl+D nhan ban, phim mui ten dich chuyen. Alt/Space keo de pan.",
    "editor.selection_count": "Da chon {count}",
    "editor.no_selection": "Chua chon",
    "editor.added_element": "Da them {kind}.",
    "editor.deleted_elements": "Da xoa {count} phan tu.",
    "editor.copied_elements": "Da sao chep {count} phan tu.",
    "editor.pasted_elements": "Da dan {count} phan tu.",
    "editor.duplicated_elements": "Da nhan ban {count} phan tu.",
    "editor.selected_all": "Da chon {count} phan tu.",
    "editor.undo_completed": "Da hoan tac.",
    "editor.redo_completed": "Da lam lai.",
    "editor.aligned_elements": "Da can phan tu da chon.",
    "editor.no_unbound_elements": "Khong con phan tu co the gan ma chua gan.",
    "editor.selected_unbound": "Da chon phan tu chua gan tiep theo: {id}",
    "editor.canvas_cleared": "Đã xóa canvas. Lưu để giữ sơ đồ trống.",
    "editor.loaded": "Đã tải sơ đồ điều độ.",
    "editor.load_failed": "Tải thất bại: {message}",
    "editor.saving": "Đang lưu sơ đồ điều độ...",
    "editor.saved": "Đã lưu sơ đồ điều độ.",
    "editor.save_failed": "Lưu thất bại: {message}",
    "editor.already_empty": "Canvas đã trống.",
    "editor.confirm_clear":
      "Xóa toàn bộ canvas điều độ? Tất cả phần tử sẽ bị xóa cho đến khi tải lại hoặc lưu.",
  },
};

function normalizeLanguage(language) {
  const value = String(language || "").trim().toLowerCase();
  return value.startsWith("vi") ? "vi" : "en";
}

function resolveInitialLanguage() {
  const params = new URLSearchParams(window.location.search);
  const queryLanguage = params.get("lang");
  if (queryLanguage && SUPPORTED_LANGUAGES.has(normalizeLanguage(queryLanguage))) {
    return normalizeLanguage(queryLanguage);
  }
  const storedLanguage = window.localStorage?.getItem(STORAGE_KEY);
  if (storedLanguage && SUPPORTED_LANGUAGES.has(normalizeLanguage(storedLanguage))) {
    return normalizeLanguage(storedLanguage);
  }
  return normalizeLanguage(window.navigator?.language);
}

let currentLanguage = resolveInitialLanguage();
setLanguage(currentLanguage);

export function getCurrentLanguage() {
  return currentLanguage;
}

export function setLanguage(language) {
  currentLanguage = normalizeLanguage(language);
  window.localStorage?.setItem(STORAGE_KEY, currentLanguage);
  document.documentElement.lang = currentLanguage;
  return currentLanguage;
}

export function t(key, params = {}) {
  const table = STRINGS[currentLanguage] || STRINGS.en;
  let template = table[key] || STRINGS.en[key] || key;
  Object.entries(params).forEach(([name, value]) => {
    template = template.replaceAll(`{${name}}`, String(value));
  });
  return template;
}

export function applyStaticTranslations(root = document) {
  document.documentElement.lang = currentLanguage;
  root.querySelectorAll("[data-i18n]").forEach((element) => {
    element.textContent = t(element.dataset.i18n);
  });
  root.querySelectorAll("[data-i18n-title]").forEach((element) => {
    element.title = t(element.dataset.i18nTitle);
  });
  root.querySelectorAll("[data-i18n-aria-label]").forEach((element) => {
    element.setAttribute("aria-label", t(element.dataset.i18nAriaLabel));
  });
  root.querySelectorAll("[data-i18n-placeholder]").forEach((element) => {
    element.placeholder = t(element.dataset.i18nPlaceholder);
  });
}

export function initLanguageSelector(onChange) {
  const selector = document.getElementById("languageSelect");
  if (!selector) {
    return;
  }
  selector.value = currentLanguage;
  selector.addEventListener("change", () => {
    setLanguage(selector.value);
    applyStaticTranslations();
    onChange?.(currentLanguage);
  });
}

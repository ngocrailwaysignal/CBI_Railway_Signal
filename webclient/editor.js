import {
  clientPointToSvgPoint,
  createEmptyDispatcherView,
  createBoardCamera,
  createSvgElement,
  deepClone,
  getElementLocalBounds,
  normalizeDispatcherView,
  renderDispatcherBoard,
  snapValue,
} from "/dispatcher-core.js";
import { applyStaticTranslations, initLanguageSelector, t } from "/i18n.js";

const board = document.getElementById("editorBoard");
const boardViewport = document.getElementById("boardViewport");
const statusText = document.getElementById("editorStatus");
const selectionStatusText = document.getElementById("editorSelectionStatus");
const layoutPathText = document.getElementById("layoutPathText");
const saveButton = document.getElementById("saveLayoutBtn");
const clearButton = document.getElementById("clearCanvasBtn");
const reloadButton = document.getElementById("reloadLayoutBtn");
const showDebugToggle = document.getElementById("editorShowDebug");
const snapToggle = document.getElementById("snapToggle");
const gridSizeInput = document.getElementById("gridSizeInput");
const canvasWidthInput = document.getElementById("canvasWidthInput");
const canvasHeightInput = document.getElementById("canvasHeightInput");
const inspector = document.getElementById("inspectorPanel");
const fitBoardBtn = document.getElementById("fitBoardBtn");
const zoomInBtn = document.getElementById("zoomInBtn");
const zoomOutBtn = document.getElementById("zoomOutBtn");
const undoBtn = document.getElementById("editorUndoBtn");
const redoBtn = document.getElementById("editorRedoBtn");
const copyBtn = document.getElementById("editorCopyBtn");
const pasteBtn = document.getElementById("editorPasteBtn");
const duplicateBtn = document.getElementById("editorDuplicateBtn");
const deleteBtn = document.getElementById("editorDeleteBtn");
const selectAllBtn = document.getElementById("editorSelectAllBtn");
const nextUnboundBtn = document.getElementById("editorNextUnboundBtn");

const TOOLBOX_SELECTOR = "[data-tool-kind]";
const HISTORY_LIMIT = 100;
const PASTE_OFFSET_STEPS = 1;
const SHORTCUT_HINT_KEY = "editor.shortcut_hint";

const state = {
  layoutPath: "",
  bindable: { sections: [], points: [], signals: [] },
  view: createEmptyDispatcherView(),
  selectedIds: new Set(),
  showDebug: false,
  drag: null,
  marquee: null,
  clipboard: [],
  history: { undo: [], redo: [] },
  dirty: false,
};
const boardCamera = createBoardCamera(board, boardViewport, { minScale: 0.45, maxScale: 4 });
let lastCanvasSignature = "";
let lastStatus = { key: "editor.loading", params: {}, kind: "info" };
let spacePanActive = false;

function setStatus(message, kind = "info") {
  statusText.textContent = message;
  statusText.dataset.kind = kind;
}

function setTranslatedStatus(key, params = {}, kind = "info") {
  lastStatus = { key, params, kind };
  setStatus(t(key, params), kind);
}

function updateSelectionStatus() {
  if (!selectionStatusText) {
    return;
  }
  const count = state.selectedIds.size;
  const selectionText = count
    ? t("editor.selection_count", { count })
    : t("editor.no_selection");
  selectionStatusText.textContent = `${selectionText} · ${t(SHORTCUT_HINT_KEY)}`;
}

function updateQuickActionButtons() {
  undoBtn && (undoBtn.disabled = !state.history.undo.length);
  redoBtn && (redoBtn.disabled = !state.history.redo.length);
  copyBtn && (copyBtn.disabled = !state.selectedIds.size);
  duplicateBtn && (duplicateBtn.disabled = !state.selectedIds.size);
  deleteBtn && (deleteBtn.disabled = !state.selectedIds.size);
  pasteBtn && (pasteBtn.disabled = !state.clipboard.length);
  selectAllBtn && (selectAllBtn.disabled = !state.view.elements.length);
  nextUnboundBtn && (nextUnboundBtn.disabled = !findNextUnboundElement());
  updateSelectionStatus();
}

function markDirty(isDirty = true) {
  state.dirty = isDirty;
  saveButton.disabled = !isDirty;
  updateQuickActionButtons();
}

function currentGridSize() {
  return Number(state.view.canvas.grid_size || 20);
}

function snapCoordinate(value) {
  return snapValue(value, currentGridSize(), Boolean(state.view.canvas.snap_enabled));
}

function findElement(elementId) {
  return state.view.elements.find((element) => element.id === elementId) || null;
}

function selectedElements() {
  return state.view.elements.filter((element) => state.selectedIds.has(element.id));
}

function snapshotEditorState() {
  return {
    view: deepClone(state.view),
    selectedIds: Array.from(state.selectedIds),
  };
}

function snapshotSignature(snapshot) {
  return JSON.stringify({
    view: snapshot.view,
    selectedIds: snapshot.selectedIds,
  });
}

function pushUndoSnapshot(snapshot) {
  state.history.undo.push(snapshot);
  if (state.history.undo.length > HISTORY_LIMIT) {
    state.history.undo.shift();
  }
  state.history.redo = [];
  updateQuickActionButtons();
}

function restoreEditorSnapshot(snapshot) {
  state.view = normalizeDispatcherView(snapshot.view || {});
  const ids = new Set(state.view.elements.map((element) => element.id));
  state.selectedIds = new Set((snapshot.selectedIds || []).filter((elementId) => ids.has(elementId)));
  markDirty(true);
  repaint();
}

function mutateView(mutator, { statusKey = "", statusParams = {} } = {}) {
  const before = snapshotEditorState();
  const beforeSignature = snapshotSignature(before);
  mutator();
  state.view = normalizeDispatcherView(state.view);
  const ids = new Set(state.view.elements.map((element) => element.id));
  state.selectedIds = new Set(Array.from(state.selectedIds).filter((elementId) => ids.has(elementId)));
  const after = snapshotEditorState();
  if (snapshotSignature(after) === beforeSignature) {
    repaint();
    return false;
  }
  pushUndoSnapshot(before);
  markDirty(true);
  if (statusKey) {
    setTranslatedStatus(statusKey, statusParams);
  }
  repaint();
  return true;
}

function clearHistory() {
  state.history.undo = [];
  state.history.redo = [];
  updateQuickActionButtons();
}

function buildBindingUsageIndex() {
  const usage = {
    section: new Map(),
    signal: new Map(),
    point: new Map(),
  };
  state.view.elements.forEach((element) => {
    const binding = element.binding;
    if (!binding?.cbi_type || !binding?.cbi_id) {
      return;
    }
    const bucket = usage[binding.cbi_type];
    if (!bucket) {
      return;
    }
    if (!bucket.has(binding.cbi_id)) {
      bucket.set(binding.cbi_id, []);
    }
    bucket.get(binding.cbi_id).push(element.id);
  });
  return usage;
}

function updateCanvasControls() {
  canvasWidthInput.value = String(Math.round(state.view.canvas.width));
  canvasHeightInput.value = String(Math.round(state.view.canvas.height));
  gridSizeInput.value = String(Math.round(state.view.canvas.grid_size));
  snapToggle.checked = Boolean(state.view.canvas.snap_enabled);
  showDebugToggle.checked = state.showDebug;
}

function repaintBoard() {
  renderDispatcherBoard(board, state.view, { routes: [], trains: [], occupancyById: new Map(), signalStateById: new Map() }, {
    showGrid: true,
    showDebug: state.showDebug,
    showRoutes: false,
    selectedIds: state.selectedIds,
    emptyStateText: t("editor.empty_board"),
  });
  boardCamera.setCanvas(state.view.canvas);
  boardCamera.apply();
  decorateSelectionHandles();
  decorateMarquee();
}

function repaint({ fit = false } = {}) {
  const canvasSignature = `${state.view.canvas.width}x${state.view.canvas.height}`;
  repaintBoard();
  if (fit || canvasSignature !== lastCanvasSignature) {
    boardCamera.fit();
  }
  lastCanvasSignature = canvasSignature;
  updateInspector();
  updateCanvasControls();
  updateQuickActionButtons();
}

function updateInspector() {
  const selected = selectedElements();
  inspector.replaceChildren();
  if (!selected.length) {
    inspector.appendChild(buildInspectorEmpty(t("editor.select_to_edit")));
    return;
  }
  if (selected.length > 1) {
    inspector.appendChild(buildMultiSelectEditor(selected));
    return;
  }

  const element = selected[0];
  const panel = document.createElement("div");
  panel.className = "inspector-stack";
  panel.appendChild(buildInspectorSummary(element));
  panel.appendChild(buildField(t("editor.element_id"), buildReadonlyValue(element.id)));
  panel.appendChild(buildPositionEditor(element));

  const bindingField = buildBindingEditor(element);
  if (bindingField) {
    panel.appendChild(bindingField);
  }
  appendGeometryFields(panel, element);

  panel.appendChild(buildElementActions());

  inspector.appendChild(panel);
}

function buildInspectorSummary(element) {
  const summary = document.createElement("div");
  summary.className = "inspector-summary";

  const kind = document.createElement("strong");
  kind.textContent = formatKindLabel(element.kind);
  summary.appendChild(kind);

  const meta = document.createElement("span");
  meta.textContent = t("editor.rotate", { degrees: Math.round(Number(element.rotation || 0)) });
  summary.appendChild(meta);

  return summary;
}

function buildMultiSelectEditor(selected) {
  const panel = document.createElement("div");
  panel.className = "inspector-stack";

  const summary = document.createElement("div");
  summary.className = "inspector-summary";
  const title = document.createElement("strong");
  title.textContent = t("editor.elements_selected_title", { count: selected.length });
  summary.appendChild(title);
  const meta = document.createElement("span");
  meta.textContent = t("editor.elements_selected", { count: selected.length });
  summary.appendChild(meta);
  panel.appendChild(summary);

  const moveRow = document.createElement("div");
  moveRow.className = "inspector-inline-grid";
  moveRow.appendChild(buildInlineNumberField("dX", 0, (value) => batchMoveSelected(value, 0), { step: 1 }));
  moveRow.appendChild(buildInlineNumberField("dY", 0, (value) => batchMoveSelected(0, value), { step: 1 }));
  moveRow.appendChild(buildInlineNumberField("Rot", 0, (value) => batchRotateSelected(value), { step: 15 }));
  panel.appendChild(buildFieldGroup(t("editor.batch_transform"), moveRow));

  const alignRow = document.createElement("div");
  alignRow.className = "button-row compact-button-row";
  [
    ["left", "editor.align_left"],
    ["center-x", "editor.align_center_x"],
    ["right", "editor.align_right"],
    ["top", "editor.align_top"],
    ["center-y", "editor.align_center_y"],
    ["bottom", "editor.align_bottom"],
  ].forEach(([mode, labelKey]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "ghost compact-action";
    button.textContent = t(labelKey);
    button.addEventListener("click", () => alignSelectedElements(mode));
    alignRow.appendChild(button);
  });
  panel.appendChild(buildFieldGroup(t("editor.align_selection"), alignRow));

  const actionRow = document.createElement("div");
  actionRow.className = "button-row";
  const duplicateButton = document.createElement("button");
  duplicateButton.type = "button";
  duplicateButton.className = "ghost";
  duplicateButton.textContent = t("editor.duplicate");
  duplicateButton.addEventListener("click", duplicateSelectedElements);
  actionRow.appendChild(duplicateButton);

  const deleteButton = document.createElement("button");
  deleteButton.type = "button";
  deleteButton.className = "danger-button";
  deleteButton.textContent = t("editor.delete_selected");
  deleteButton.addEventListener("click", deleteSelectedElements);
  actionRow.appendChild(deleteButton);
  panel.appendChild(actionRow);

  return panel;
}

function buildPositionEditor(element) {
  const wrapper = document.createElement("div");
  wrapper.className = "inspector-field";

  const title = document.createElement("span");
  title.className = "inspector-label";
  title.textContent = t("editor.position");
  wrapper.appendChild(title);

  const row = document.createElement("div");
  row.className = "inspector-inline-grid";
  row.appendChild(buildInlineNumberField("X", element.position.x, (value) => updateElement(element.id, (draft) => {
    draft.position.x = snapCoordinate(value);
  })));
  row.appendChild(buildInlineNumberField("Y", element.position.y, (value) => updateElement(element.id, (draft) => {
    draft.position.y = snapCoordinate(value);
  })));
  row.appendChild(buildInlineNumberField("Rot", element.rotation, (value) => updateElement(element.id, (draft) => {
    draft.rotation = value;
  })));
  wrapper.appendChild(row);
  return wrapper;
}

function appendGeometryFields(panel, element) {
  if (element.kind === "track_section") {
    panel.appendChild(
      buildField(
        t("editor.track_style"),
        buildSelect(["main", "siding", "yard", "approach"], element.style.variant || "main", (value) => updateElement(element.id, (draft) => {
          draft.style.variant = value;
        })),
      ),
    );
    panel.appendChild(
      buildField(t("editor.stroke_width"), buildNumberInput(element.geometry.stroke_width, (value) => updateElement(element.id, (draft) => {
        draft.geometry.stroke_width = Math.max(1, value);
      }))),
    );
    return;
  }
  if (element.kind === "signal") {
    panel.appendChild(
      buildField(t("editor.mast"), buildNumberInput(element.geometry.mast, (value) => updateElement(element.id, (draft) => {
        draft.geometry.mast = Math.max(8, value);
      }))),
    );
    panel.appendChild(
      buildField(t("editor.arm"), buildNumberInput(element.geometry.arm, (value) => updateElement(element.id, (draft) => {
        draft.geometry.arm = Math.max(6, value);
      }))),
    );
    return;
  }
  if (element.kind === "point") {
    panel.appendChild(
      buildField(
        t("editor.branch_side"),
        buildSelect(["up", "down"], element.geometry.branch_side || "up", (value) => updateElement(element.id, (draft) => {
          draft.geometry.branch_side = value;
        })),
      ),
    );
    panel.appendChild(
      buildField(t("editor.straight"), buildNumberInput(element.geometry.straight, (value) => updateElement(element.id, (draft) => {
        draft.geometry.straight = Math.max(12, value);
      }))),
    );
    panel.appendChild(
      buildField(t("editor.branch"), buildNumberInput(element.geometry.branch, (value) => updateElement(element.id, (draft) => {
        draft.geometry.branch = Math.max(12, value);
      }))),
    );
    return;
  }
  if (element.kind === "label") {
    panel.appendChild(
      buildField(
        t("editor.text"),
        buildTextarea(String(element.geometry.text || ""), (value) => updateElement(element.id, (draft) => {
          draft.geometry.text = value;
        })),
      ),
    );
    panel.appendChild(
      buildField(t("editor.font_size"), buildNumberInput(element.geometry.font_size, (value) => updateElement(element.id, (draft) => {
        draft.geometry.font_size = Math.max(8, value);
      }))),
    );
    panel.appendChild(
      buildField(
        t("editor.align"),
        buildSelect(["start", "middle", "end"], element.geometry.align || "middle", (value) => updateElement(element.id, (draft) => {
          draft.geometry.align = value;
        })),
      ),
    );
    panel.appendChild(
      buildField(
        t("editor.tone"),
        buildSelect(["bright", "muted", "amber", "steel"], element.style.tone || "bright", (value) => updateElement(element.id, (draft) => {
          draft.style.tone = value;
        })),
      ),
    );
    return;
  }
  panel.appendChild(
    buildField(t("editor.width"), buildNumberInput(element.geometry.width, (value) => updateElement(element.id, (draft) => {
      draft.geometry.width = Math.max(8, value);
    }))),
  );
  panel.appendChild(
    buildField(t("editor.height"), buildNumberInput(element.geometry.height, (value) => updateElement(element.id, (draft) => {
      draft.geometry.height = Math.max(8, value);
    }))),
  );
  panel.appendChild(
    buildField(
      t("editor.tone"),
      buildSelect(["steel", "bright", "muted"], element.style.tone || "steel", (value) => updateElement(element.id, (draft) => {
        draft.style.tone = value;
      })),
    ),
  );
}

function buildBindingEditor(element) {
  const options = element.kind === "track_section" || element.kind === "block_marker"
    ? state.bindable.sections
    : element.kind === "signal"
      ? state.bindable.signals
      : element.kind === "point"
        ? state.bindable.points
        : null;
  if (!options) {
    return null;
  }
  const cbiType = element.kind === "signal" ? "signal" : element.kind === "point" ? "point" : "section";
  const usage = buildBindingUsageIndex();
  const field = document.createElement("div");
  field.className = "inspector-field";

  const title = document.createElement("span");
  title.className = "inspector-label";
  title.textContent = t("editor.cbi_binding", { type: cbiType });
  field.appendChild(title);

  if (!options.length) {
    field.appendChild(buildReadonlyValue(t("editor.no_ids", { type: cbiType })));
    return field;
  }

  const hint = document.createElement("p");
  hint.className = "hint";
  hint.textContent = t("editor.binding_hint", { type: cbiType });
  field.appendChild(hint);

  field.appendChild(buildReadonlyValue(element.binding?.cbi_id || t("editor.unbound", { type: cbiType })));
  field.appendChild(buildBindingSearch(options, element.binding?.cbi_id || "", cbiType, element.id, usage));
  field.appendChild(buildBindingSuggestions(options, element.binding?.cbi_id || "", cbiType, element.id, usage));
  return field;
}

function buildInspectorEmpty(text) {
  const div = document.createElement("div");
  div.className = "inspector-empty";
  div.textContent = text;
  return div;
}

function buildField(labelText, control) {
  const wrapper = document.createElement("label");
  wrapper.className = "inspector-field";
  const title = document.createElement("span");
  title.className = "inspector-label";
  title.textContent = labelText;
  wrapper.appendChild(title);
  wrapper.appendChild(control);
  return wrapper;
}

function buildFieldGroup(labelText, control) {
  const wrapper = document.createElement("div");
  wrapper.className = "inspector-field";
  const title = document.createElement("span");
  title.className = "inspector-label";
  title.textContent = labelText;
  wrapper.appendChild(title);
  wrapper.appendChild(control);
  return wrapper;
}

function buildReadonlyValue(text) {
  const div = document.createElement("div");
  div.className = "readonly-value";
  div.textContent = text;
  return div;
}

function buildInlineNumberField(labelText, value, onChange, config = {}) {
  const field = document.createElement("label");
  field.className = "inspector-inline-field";
  const label = document.createElement("span");
  label.className = "inspector-inline-label";
  label.textContent = labelText;
  field.appendChild(label);
  field.appendChild(buildNumberInput(value, onChange, config));
  return field;
}

function buildNumberInput(value, onChange, { step = 5 } = {}) {
  const input = document.createElement("input");
  input.type = "number";
  input.step = String(step);
  input.value = String(Math.round(Number(value || 0) * 100) / 100);
  input.addEventListener("change", () => onChange(Number(input.value || 0)));
  return input;
}

function buildTextarea(value, onChange) {
  const textarea = document.createElement("textarea");
  textarea.rows = 3;
  textarea.value = value;
  textarea.dataset.editorTextArea = "true";
  textarea.addEventListener("change", () => onChange(textarea.value));
  return textarea;
}

function buildSelect(options, value, onChange, config = {}) {
  const select = document.createElement("select");
  options.forEach((optionValue) => {
    const option = document.createElement("option");
    option.value = optionValue;
    option.textContent = config.labels?.[optionValue] || optionValue || t("editor.unbind");
    select.appendChild(option);
  });
  select.value = value;
  select.addEventListener("change", () => onChange(select.value));
  return select;
}

function buildBindingSearch(options, selectedValue, cbiType, elementId, usage) {
  const input = document.createElement("input");
  input.type = "search";
  input.placeholder = t("editor.filter_ids", { type: cbiType });
  input.value = selectedValue || "";
  const assignBestMatch = () => {
    const query = input.value.trim().toLowerCase();
    if (!query) {
      return false;
    }
    const exact = options.find((optionValue) => optionValue.toLowerCase() === query);
    const prefix = options.find((optionValue) => optionValue.toLowerCase().startsWith(query));
    const candidate = exact || prefix;
    if (!candidate) {
      return false;
    }
    assignBinding(elementId, cbiType, candidate, usage);
    return true;
  };
  input.addEventListener("input", () => {
    const chips = input.parentElement?.querySelector?.(".binding-chip-list");
    if (!chips) {
      return;
    }
    const query = input.value.trim().toLowerCase();
    chips.querySelectorAll(".binding-chip").forEach((chip) => {
      const text = String(chip.dataset.bindingId || "").toLowerCase();
      chip.hidden = Boolean(query) && !text.includes(query);
    });
  });
  input.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") {
      return;
    }
    if (assignBestMatch()) {
      event.preventDefault();
    }
  });
  input.addEventListener("change", () => {
    assignBestMatch();
  });
  return input;
}

function buildBindingSuggestions(options, selectedValue, cbiType, elementId, usage) {
  const wrapper = document.createElement("div");
  wrapper.className = "binding-suggestions";

  const actions = document.createElement("div");
  actions.className = "binding-actions";

  const title = document.createElement("span");
  title.className = "inspector-label";
  title.textContent = t("editor.available_ids");
  actions.appendChild(title);

  const clearButton = document.createElement("button");
  clearButton.type = "button";
  clearButton.className = "ghost binding-clear-button";
  clearButton.textContent = t("editor.unbind");
  clearButton.disabled = !selectedValue;
  clearButton.addEventListener("click", () => assignBinding(elementId, cbiType, ""));
  actions.appendChild(clearButton);

  wrapper.appendChild(actions);

  const list = document.createElement("div");
  list.className = "binding-chip-list";
  options.forEach((optionValue) => {
    const owners = usage[cbiType]?.get(optionValue) || [];
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = `binding-chip${optionValue === selectedValue ? " active" : ""}${owners.length ? " used" : ""}`;
    chip.dataset.bindingId = optionValue;
    chip.title = owners.length ? t("editor.used_by", { owners: owners.join(", ") }) : "";

    const idText = document.createElement("span");
    idText.className = "binding-chip-id";
    idText.textContent = optionValue;
    chip.appendChild(idText);

    if (owners.length) {
      const meta = document.createElement("span");
      meta.className = "binding-chip-meta";
      meta.textContent = owners.includes(elementId) && owners.length === 1
        ? t("editor.used_by_this")
        : t("editor.used_by", { owners: owners.join(", ") });
      chip.appendChild(meta);
    }

    chip.addEventListener("click", () => assignBinding(elementId, cbiType, optionValue, usage));
    list.appendChild(chip);
  });
  wrapper.appendChild(list);
  return wrapper;
}

function assignBinding(elementId, cbiType, value, usage = buildBindingUsageIndex()) {
  updateElement(elementId, (draft) => {
    if (!value) {
      draft.binding = null;
      return;
    }
    draft.binding = { cbi_type: cbiType, cbi_id: value };
  });
}

function buildElementActions() {
  const row = document.createElement("div");
  row.className = "button-row";

  const deleteButton = document.createElement("button");
  deleteButton.type = "button";
  deleteButton.className = "danger-button";
  deleteButton.textContent = t("editor.delete_this");
  deleteButton.addEventListener("click", () => deleteSelectedElements());
  row.appendChild(deleteButton);

  return row;
}

function formatKindLabel(kind) {
  const labels = {
    block_marker: t("editor.block_marker"),
    label: t("editor.label"),
    point: t("editor.point"),
    signal: t("editor.signal"),
    track_section: t("editor.track_section"),
  };
  if (labels[kind]) {
    return labels[kind];
  }
  return String(kind || "")
    .split("_")
    .filter(Boolean)
    .map((token) => token.charAt(0).toUpperCase() + token.slice(1))
    .join(" ");
}

function createElementAt(kind, position) {
  const count = state.view.elements.filter((element) => element.kind === kind).length + 1;
  const base = {
    id: `${kind}-${count}`,
    kind,
    position: {
      x: snapCoordinate(position.x),
      y: snapCoordinate(position.y),
    },
    rotation: 0,
    style: {},
    z_index: state.view.elements.length,
    binding: null,
  };
  if (kind === "track_section") {
    return {
      ...base,
      geometry: {
        points: [{ x: 0, y: 0 }, { x: 180, y: 0 }],
        stroke_width: 4,
        marker_spacing: 48,
      },
      style: { variant: "main" },
    };
  }
  if (kind === "signal") {
    return {
      ...base,
      geometry: { mast: 18, arm: 14, head_radius: 5.5, label_offset: 20 },
    };
  }
  if (kind === "point") {
    return {
      ...base,
      geometry: { trunk: 24, straight: 58, branch: 50, diverge: 22, branch_side: "up" },
    };
  }
  if (kind === "label") {
    return {
      ...base,
      geometry: { text: t("editor.label").toUpperCase(), font_size: 28, align: "middle" },
      style: { tone: "bright" },
    };
  }
  return {
    ...base,
    geometry: { width: 42, height: 18, radius: 8 },
    style: { tone: "steel" },
  };
}

function updateElement(elementId, updater) {
  mutateView(() => {
    const element = findElement(elementId);
    if (!element) {
      return;
    }
    updater(element);
  });
}

function commitDragMutation() {
  state.view = normalizeDispatcherView(state.view);
  markDirty(true);
  repaint();
}

function addElement(kind, position) {
  mutateView(() => {
    const element = createElementAt(kind, position);
    state.view.elements.push(element);
    state.selectedIds = new Set([element.id]);
  }, { statusKey: "editor.added_element", statusParams: { kind: formatKindLabel(kind) } });
}

function clearCanvas() {
  mutateView(() => {
    const nextView = createEmptyDispatcherView();
    nextView.canvas = {
      ...nextView.canvas,
      ...deepClone(state.view.canvas),
    };
    state.view = nextView;
    state.selectedIds.clear();
  }, { statusKey: "editor.canvas_cleared" });
}

function deleteSelectedElements() {
  if (!state.selectedIds.size) {
    return;
  }
  const count = state.selectedIds.size;
  mutateView(() => {
    state.view.elements = state.view.elements.filter((element) => !state.selectedIds.has(element.id));
    state.selectedIds.clear();
  }, { statusKey: "editor.deleted_elements", statusParams: { count } });
}

function makeUniqueElementId(baseId) {
  const existing = new Set(state.view.elements.map((element) => element.id));
  const cleaned = String(baseId || "element").replace(/-\d+$/, "");
  let index = 1;
  let candidate = `${cleaned}-${index}`;
  while (existing.has(candidate)) {
    index += 1;
    candidate = `${cleaned}-${index}`;
  }
  return candidate;
}

function copySelectedElements() {
  const selected = selectedElements();
  if (!selected.length) {
    return;
  }
  state.clipboard = selected.map((element) => deepClone(element));
  setTranslatedStatus("editor.copied_elements", { count: state.clipboard.length });
  updateQuickActionButtons();
}

function pasteElements(sourceElements = state.clipboard, { statusKey = "editor.pasted_elements" } = {}) {
  if (!sourceElements.length) {
    return;
  }
  const offset = currentGridSize() * PASTE_OFFSET_STEPS;
  const pastedCount = sourceElements.length;
  const changed = mutateView(() => {
    const nextSelection = new Set();
    sourceElements.forEach((source) => {
      const clone = deepClone(source);
      clone.id = makeUniqueElementId(clone.id);
      clone.position = {
        x: snapCoordinate(Number(clone.position?.x || 0) + offset),
        y: snapCoordinate(Number(clone.position?.y || 0) + offset),
      };
      clone.binding = null;
      clone.z_index = state.view.elements.length;
      state.view.elements.push(clone);
      nextSelection.add(clone.id);
    });
    state.selectedIds = nextSelection;
  });
  if (changed) {
    setTranslatedStatus(statusKey, { count: pastedCount });
  }
}

function duplicateSelectedElements() {
  const selected = selectedElements();
  if (!selected.length) {
    return;
  }
  pasteElements(selected, { statusKey: "editor.duplicated_elements" });
}

function cutSelectedElements() {
  if (!state.selectedIds.size) {
    return;
  }
  copySelectedElements();
  deleteSelectedElements();
}

function selectAllElements() {
  state.selectedIds = new Set(state.view.elements.map((element) => element.id));
  repaint();
  setTranslatedStatus("editor.selected_all", { count: state.selectedIds.size });
}

function nudgeSelectedElements(deltaX, deltaY) {
  if (!state.selectedIds.size) {
    return;
  }
  mutateView(() => {
    selectedElements().forEach((element) => {
      element.position.x = snapCoordinate(Number(element.position.x || 0) + deltaX);
      element.position.y = snapCoordinate(Number(element.position.y || 0) + deltaY);
    });
  });
}

function batchMoveSelected(deltaX, deltaY) {
  nudgeSelectedElements(deltaX, deltaY);
}

function batchRotateSelected(deltaDegrees) {
  if (!state.selectedIds.size) {
    return;
  }
  mutateView(() => {
    selectedElements().forEach((element) => {
      element.rotation = Number(element.rotation || 0) + deltaDegrees;
    });
  });
}

function selectionBounds() {
  const bounds = selectedElements().map(getElementGlobalBounds);
  if (!bounds.length) {
    return null;
  }
  return {
    minX: Math.min(...bounds.map((bound) => bound.minX)),
    minY: Math.min(...bounds.map((bound) => bound.minY)),
    maxX: Math.max(...bounds.map((bound) => bound.maxX)),
    maxY: Math.max(...bounds.map((bound) => bound.maxY)),
  };
}

function alignSelectedElements(mode) {
  const target = selectionBounds();
  if (!target || state.selectedIds.size < 2) {
    return;
  }
  const targetCenterX = (target.minX + target.maxX) / 2;
  const targetCenterY = (target.minY + target.maxY) / 2;
  mutateView(() => {
    selectedElements().forEach((element) => {
      const bounds = getElementGlobalBounds(element);
      if (mode === "left") {
        element.position.x += target.minX - bounds.minX;
      } else if (mode === "right") {
        element.position.x += target.maxX - bounds.maxX;
      } else if (mode === "top") {
        element.position.y += target.minY - bounds.minY;
      } else if (mode === "bottom") {
        element.position.y += target.maxY - bounds.maxY;
      } else if (mode === "center-x") {
        element.position.x += targetCenterX - (bounds.minX + bounds.maxX) / 2;
      } else if (mode === "center-y") {
        element.position.y += targetCenterY - (bounds.minY + bounds.maxY) / 2;
      }
      element.position.x = snapCoordinate(element.position.x);
      element.position.y = snapCoordinate(element.position.y);
    });
  }, { statusKey: "editor.aligned_elements" });
}

function undoEditorAction() {
  const snapshot = state.history.undo.pop();
  if (!snapshot) {
    return;
  }
  state.history.redo.push(snapshotEditorState());
  restoreEditorSnapshot(snapshot);
  setTranslatedStatus("editor.undo_completed");
}

function redoEditorAction() {
  const snapshot = state.history.redo.pop();
  if (!snapshot) {
    return;
  }
  state.history.undo.push(snapshotEditorState());
  restoreEditorSnapshot(snapshot);
  setTranslatedStatus("editor.redo_completed");
}

function isBindableElement(element) {
  return ["track_section", "signal", "point", "block_marker"].includes(element?.kind);
}

function findNextUnboundElement() {
  if (!state.view.elements.length) {
    return null;
  }
  const ordered = state.view.elements.filter((element) => isBindableElement(element) && !element.binding);
  if (!ordered.length) {
    return null;
  }
  const selectedIndexes = Array.from(state.selectedIds)
    .map((elementId) => state.view.elements.findIndex((element) => element.id === elementId))
    .filter((index) => index >= 0);
  const startIndex = selectedIndexes.length ? Math.max(...selectedIndexes) : -1;
  return ordered.find((element) => state.view.elements.indexOf(element) > startIndex) || ordered[0];
}

function selectNextUnboundElement() {
  const element = findNextUnboundElement();
  if (!element) {
    setTranslatedStatus("editor.no_unbound_elements");
    return;
  }
  state.selectedIds = new Set([element.id]);
  repaint();
  setTranslatedStatus("editor.selected_unbound", { id: element.id });
}

function focusSelectedLabelText() {
  const selected = selectedElements();
  if (selected.length !== 1 || selected[0].kind !== "label") {
    return false;
  }
  const textarea = inspector.querySelector("textarea[data-editor-text-area='true']");
  if (!textarea) {
    return false;
  }
  textarea.focus();
  textarea.select();
  return true;
}

function setSelection(elementId, { additive = false, toggle = false } = {}) {
  if (!additive && !toggle) {
    state.selectedIds = elementId ? new Set([elementId]) : new Set();
  } else {
    const next = new Set(state.selectedIds);
    if (toggle && next.has(elementId)) {
      next.delete(elementId);
    } else if (elementId) {
      next.add(elementId);
    }
    state.selectedIds = next;
  }
  repaint();
  updateQuickActionButtons();
}

function decorateSelectionHandles() {
  selectedElements().forEach((element) => {
    const group = board.querySelector(`[data-element-id="${CSS.escape(element.id)}"]`);
    if (!group) {
      return;
    }
    const bounds = getElementLocalBounds(element);
    const rotateHandle = createSvgElement("circle", {
      cx: (bounds.minX + bounds.maxX) / 2,
      cy: bounds.minY - 26,
      r: 7,
      class: "editor-handle rotate-handle",
    });
    rotateHandle.dataset.handle = "rotate";
    rotateHandle.dataset.elementId = element.id;
    group.appendChild(rotateHandle);

    if (element.kind === "track_section") {
      const points = element.geometry.points;
      const first = points[0];
      const last = points[points.length - 1];
      const startHandle = createSvgElement("circle", {
        cx: first.x,
        cy: first.y,
        r: 7,
        class: "editor-handle point-handle",
      });
      startHandle.dataset.handle = "track-start";
      startHandle.dataset.elementId = element.id;
      group.appendChild(startHandle);
      const endHandle = createSvgElement("circle", {
        cx: last.x,
        cy: last.y,
        r: 7,
        class: "editor-handle point-handle",
      });
      endHandle.dataset.handle = "track-end";
      endHandle.dataset.elementId = element.id;
      group.appendChild(endHandle);
    }
    if (element.kind === "block_marker") {
      const resizeHandle = createSvgElement("rect", {
        x: bounds.maxX + 4,
        y: bounds.maxY + 4,
        width: 10,
        height: 10,
        class: "editor-handle resize-handle",
      });
      resizeHandle.dataset.handle = "block-resize";
      resizeHandle.dataset.elementId = element.id;
      group.appendChild(resizeHandle);
    }
  });
}

function rotateLocalPoint(element, point) {
  const radians = (Number(element.rotation || 0) * Math.PI) / 180;
  const cos = Math.cos(radians);
  const sin = Math.sin(radians);
  return {
    x: element.position.x + point.x * cos - point.y * sin,
    y: element.position.y + point.x * sin + point.y * cos,
  };
}

function getElementGlobalBounds(element) {
  const bounds = getElementLocalBounds(element);
  const corners = [
    { x: bounds.minX, y: bounds.minY },
    { x: bounds.maxX, y: bounds.minY },
    { x: bounds.maxX, y: bounds.maxY },
    { x: bounds.minX, y: bounds.maxY },
  ].map((point) => rotateLocalPoint(element, point));
  const xs = corners.map((point) => point.x);
  const ys = corners.map((point) => point.y);
  return {
    minX: Math.min(...xs),
    minY: Math.min(...ys),
    maxX: Math.max(...xs),
    maxY: Math.max(...ys),
  };
}

function normalizeRect(startPoint, endPoint) {
  return {
    minX: Math.min(startPoint.x, endPoint.x),
    minY: Math.min(startPoint.y, endPoint.y),
    maxX: Math.max(startPoint.x, endPoint.x),
    maxY: Math.max(startPoint.y, endPoint.y),
  };
}

function rectsIntersect(left, right) {
  return left.minX <= right.maxX
    && left.maxX >= right.minX
    && left.minY <= right.maxY
    && left.maxY >= right.minY;
}

function decorateMarquee() {
  if (!state.marquee) {
    return;
  }
  const rect = normalizeRect(state.marquee.startPoint, state.marquee.currentPoint);
  board.appendChild(createSvgElement("rect", {
    x: rect.minX,
    y: rect.minY,
    width: rect.maxX - rect.minX,
    height: rect.maxY - rect.minY,
    class: "editor-marquee-box",
  }));
}

function clientToSvgPoint(clientX, clientY) {
  return clientPointToSvgPoint(board, clientX, clientY);
}

function isEditableTarget(target) {
  const tagName = String(target?.tagName || "").toLowerCase();
  return target?.isContentEditable
    || tagName === "input"
    || tagName === "select"
    || tagName === "textarea";
}

function globalToLocal(element, globalPoint) {
  const radians = (-Number(element.rotation || 0) * Math.PI) / 180;
  const dx = globalPoint.x - element.position.x;
  const dy = globalPoint.y - element.position.y;
  const cos = Math.cos(radians);
  const sin = Math.sin(radians);
  return {
    x: dx * cos - dy * sin,
    y: dx * sin + dy * cos,
  };
}

function beginMoveDrag(pointerId, startPoint) {
  const originals = selectedElements().map((element) => ({
    id: element.id,
    x: element.position.x,
    y: element.position.y,
  }));
  state.drag = { type: "move", pointerId, startPoint, originals, before: snapshotEditorState(), changed: false };
}

function beginHandleDrag(pointerId, elementId, handle, startPoint) {
  const element = findElement(elementId);
  if (!element) {
    return;
  }
  state.drag = {
    type: handle,
    pointerId,
    elementId,
    startPoint,
    startElement: deepClone(element),
    before: snapshotEditorState(),
    changed: false,
  };
}

function beginMarquee(pointerId, startPoint, additive = false) {
  state.marquee = {
    pointerId,
    startPoint,
    currentPoint: startPoint,
    additive,
    baseSelection: new Set(state.selectedIds),
  };
  repaintBoard();
}

function handlePointerMove(event) {
  if (state.marquee && state.marquee.pointerId === event.pointerId) {
    state.marquee.currentPoint = clientToSvgPoint(event.clientX, event.clientY);
    const rect = normalizeRect(state.marquee.startPoint, state.marquee.currentPoint);
    const next = state.marquee.additive ? new Set(state.marquee.baseSelection) : new Set();
    state.view.elements.forEach((element) => {
      if (rectsIntersect(rect, getElementGlobalBounds(element))) {
        next.add(element.id);
      }
    });
    state.selectedIds = next;
    repaintBoard();
    updateInspector();
    updateQuickActionButtons();
    event.preventDefault();
    return;
  }
  if (!state.drag && boardCamera.pan(event)) {
    event.preventDefault();
    return;
  }
  if (!state.drag || state.drag.pointerId !== event.pointerId) {
    return;
  }
  const currentPoint = clientToSvgPoint(event.clientX, event.clientY);
  if (state.drag.type === "move") {
    const deltaX = currentPoint.x - state.drag.startPoint.x;
    const deltaY = currentPoint.y - state.drag.startPoint.y;
    state.drag.originals.forEach((original) => {
      const element = findElement(original.id);
      if (!element) {
        return;
      }
      element.position.x = snapCoordinate(original.x + deltaX);
      element.position.y = snapCoordinate(original.y + deltaY);
    });
    state.drag.changed = true;
    markDirty(true);
    repaintBoard();
    return;
  }

  const element = findElement(state.drag.elementId);
  if (!element) {
    return;
  }
  if (state.drag.type === "rotate") {
    const angle = Math.atan2(currentPoint.y - element.position.y, currentPoint.x - element.position.x) * (180 / Math.PI);
    element.rotation = state.view.canvas.snap_enabled ? Math.round(angle / 15) * 15 : angle;
    state.drag.changed = true;
    markDirty(true);
    repaintBoard();
    return;
  }
  if (state.drag.type === "track-start" || state.drag.type === "track-end") {
    const local = globalToLocal(element, currentPoint);
    const points = element.geometry.points;
    const index = state.drag.type === "track-start" ? 0 : points.length - 1;
    points[index] = {
      x: snapCoordinate(local.x),
      y: snapCoordinate(local.y),
    };
    state.drag.changed = true;
    markDirty(true);
    repaintBoard();
    return;
  }
  if (state.drag.type === "block-resize") {
    const local = globalToLocal(element, currentPoint);
    element.geometry.width = Math.max(8, snapCoordinate(local.x));
    element.geometry.height = Math.max(8, snapCoordinate(local.y));
    state.drag.changed = true;
    markDirty(true);
    repaintBoard();
  }
}

function handlePointerUp(event) {
  if (state.marquee && state.marquee.pointerId === event.pointerId) {
    state.marquee = null;
    repaint();
    event.preventDefault();
    return;
  }
  if (!state.drag && boardCamera.endPan(event)) {
    event.preventDefault();
    return;
  }
  if (!state.drag || state.drag.pointerId !== event.pointerId) {
    return;
  }
  const drag = state.drag;
  state.drag = null;
  if (drag.changed) {
    pushUndoSnapshot(drag.before);
    commitDragMutation();
  } else {
    repaint();
  }
}

async function loadDispatcherLayout() {
  setTranslatedStatus("editor.loading");
  try {
    const response = await fetch("/api/dispatcher-layout", { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const payload = await response.json();
    state.layoutPath = String(payload.layout_path || "");
    state.bindable = payload.bindable || { sections: [], points: [], signals: [] };
    state.view = normalizeDispatcherView(payload.dispatcher_view || {});
    state.selectedIds.clear();
    layoutPathText.textContent = state.layoutPath || "-";
    clearHistory();
    markDirty(false);
    setTranslatedStatus("editor.loaded");
    repaint({ fit: true });
  } catch (error) {
    setTranslatedStatus(
      "editor.load_failed",
      { message: error instanceof Error ? error.message : String(error) },
      "error",
    );
  }
}

async function saveDispatcherLayout() {
  setTranslatedStatus("editor.saving");
  saveButton.disabled = true;
  try {
    const response = await fetch("/api/dispatcher-layout", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dispatcher_view: state.view }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || `HTTP ${response.status}`);
    }
    state.view = normalizeDispatcherView(payload.dispatcher_view || {});
    markDirty(false);
    setTranslatedStatus("editor.saved");
    repaint();
    window.location.href = "/dispatcher?saved=1";
  } catch (error) {
    markDirty(true);
    setTranslatedStatus(
      "editor.save_failed",
      { message: error instanceof Error ? error.message : String(error) },
      "error",
    );
  }
}

function confirmAndClearCanvas() {
  if (!state.view.elements.length) {
    setTranslatedStatus("editor.already_empty");
    return;
  }
  const confirmed = window.confirm(t("editor.confirm_clear"));
  if (!confirmed) {
    return;
  }
  clearCanvas();
}

document.querySelectorAll(TOOLBOX_SELECTOR).forEach((button) => {
  button.setAttribute("draggable", "true");
  button.addEventListener("dragstart", (event) => {
    event.dataTransfer?.setData("text/plain", String(button.dataset.toolKind || ""));
  });
  button.addEventListener("click", () => {
    const rect = board.getBoundingClientRect();
    addElement(String(button.dataset.toolKind || ""), clientToSvgPoint(rect.left + rect.width / 2, rect.top + rect.height / 2));
  });
});

boardViewport.addEventListener("dragover", (event) => {
  event.preventDefault();
});

boardViewport.addEventListener("drop", (event) => {
  event.preventDefault();
  const kind = event.dataTransfer?.getData("text/plain");
  if (!kind) {
    return;
  }
  addElement(kind, clientToSvgPoint(event.clientX, event.clientY));
});

board.addEventListener("pointerdown", (event) => {
  if (event.button !== 0) {
    return;
  }
  const handleTarget = event.target.closest?.("[data-handle]");
  if (handleTarget) {
    const elementId = handleTarget.dataset.elementId;
    const handle = handleTarget.dataset.handle;
    if (elementId && handle) {
      beginHandleDrag(event.pointerId, elementId, handle, clientToSvgPoint(event.clientX, event.clientY));
      board.setPointerCapture(event.pointerId);
    }
    event.stopPropagation();
    event.preventDefault();
    return;
  }

  const group = event.target.closest?.("[data-element-id]");
  if (!group) {
    const shouldPan = event.altKey || spacePanActive;
    if (shouldPan && boardCamera.beginPan(event)) {
      board.setPointerCapture(event.pointerId);
      event.preventDefault();
      return;
    }
    const additive = event.shiftKey || event.ctrlKey || event.metaKey;
    if (!additive) {
      setSelection("", {});
    }
    beginMarquee(event.pointerId, clientToSvgPoint(event.clientX, event.clientY), additive);
    board.setPointerCapture(event.pointerId);
    event.preventDefault();
    return;
  }
  const elementId = group.dataset.elementId;
  if (!elementId) {
    return;
  }
  const additive = event.shiftKey || event.ctrlKey || event.metaKey;
  if (!state.selectedIds.has(elementId) || additive) {
    setSelection(elementId, { additive, toggle: additive });
  }
  beginMoveDrag(event.pointerId, clientToSvgPoint(event.clientX, event.clientY));
  board.setPointerCapture(event.pointerId);
  event.preventDefault();
});

board.addEventListener("pointermove", handlePointerMove);
board.addEventListener("pointerup", handlePointerUp);
board.addEventListener("pointercancel", handlePointerUp);
board.addEventListener("wheel", (event) => boardCamera.wheel(event), { passive: false });
fitBoardBtn?.addEventListener("click", () => boardCamera.fit());
zoomInBtn?.addEventListener("click", () => {
  const rect = boardViewport.getBoundingClientRect();
  boardCamera.zoomAt(rect.left + rect.width / 2, rect.top + rect.height / 2, 1.2);
});
zoomOutBtn?.addEventListener("click", () => {
  const rect = boardViewport.getBoundingClientRect();
  boardCamera.zoomAt(rect.left + rect.width / 2, rect.top + rect.height / 2, 1 / 1.2);
});
undoBtn?.addEventListener("click", undoEditorAction);
redoBtn?.addEventListener("click", redoEditorAction);
copyBtn?.addEventListener("click", copySelectedElements);
pasteBtn?.addEventListener("click", () => pasteElements());
duplicateBtn?.addEventListener("click", duplicateSelectedElements);
deleteBtn?.addEventListener("click", deleteSelectedElements);
selectAllBtn?.addEventListener("click", selectAllElements);
nextUnboundBtn?.addEventListener("click", selectNextUnboundElement);
window.addEventListener("resize", () => boardCamera.apply());

document.addEventListener("keydown", (event) => {
  if (event.code === "Space" && !isEditableTarget(event.target)) {
    spacePanActive = true;
  }
  if (isEditableTarget(event.target)) {
    return;
  }

  const modifier = event.ctrlKey || event.metaKey;
  const key = event.key.toLowerCase();
  if (modifier && key === "z") {
    if (event.shiftKey) {
      redoEditorAction();
    } else {
      undoEditorAction();
    }
    event.preventDefault();
    return;
  }
  if (modifier && key === "y") {
    redoEditorAction();
    event.preventDefault();
    return;
  }
  if (modifier && key === "c") {
    copySelectedElements();
    event.preventDefault();
    return;
  }
  if (modifier && key === "x") {
    cutSelectedElements();
    event.preventDefault();
    return;
  }
  if (modifier && key === "v") {
    pasteElements();
    event.preventDefault();
    return;
  }
  if (modifier && key === "d") {
    duplicateSelectedElements();
    event.preventDefault();
    return;
  }
  if (modifier && key === "a") {
    selectAllElements();
    event.preventDefault();
    return;
  }
  if (event.key === "Escape") {
    if (state.drag) {
      restoreEditorSnapshot(state.drag.before || snapshotEditorState());
      state.drag = null;
    } else if (state.marquee) {
      state.marquee = null;
      repaint();
    } else if (state.selectedIds.size) {
      setSelection("", {});
    }
    event.preventDefault();
    return;
  }
  if (event.key === "Enter" && focusSelectedLabelText()) {
    event.preventDefault();
    return;
  }
  const nudgeDistance = event.shiftKey ? currentGridSize() : 1;
  const nudgeMap = {
    ArrowLeft: [-nudgeDistance, 0],
    ArrowRight: [nudgeDistance, 0],
    ArrowUp: [0, -nudgeDistance],
    ArrowDown: [0, nudgeDistance],
  };
  if (event.key in nudgeMap && state.selectedIds.size) {
    const [deltaX, deltaY] = nudgeMap[event.key];
    nudgeSelectedElements(deltaX, deltaY);
    event.preventDefault();
    return;
  }
  if ((event.key === "Delete" || event.key === "Backspace") && state.selectedIds.size) {
    deleteSelectedElements();
    event.preventDefault();
  }
});

document.addEventListener("keyup", (event) => {
  if (event.code === "Space") {
    spacePanActive = false;
  }
});

saveButton.addEventListener("click", saveDispatcherLayout);
clearButton.addEventListener("click", confirmAndClearCanvas);
reloadButton.addEventListener("click", loadDispatcherLayout);
showDebugToggle.addEventListener("change", () => {
  state.showDebug = showDebugToggle.checked;
  repaint();
});
snapToggle.addEventListener("change", () => {
  state.view.canvas.snap_enabled = snapToggle.checked;
  markDirty(true);
  repaint();
});
gridSizeInput.addEventListener("change", () => {
  state.view.canvas.grid_size = Math.max(4, Number(gridSizeInput.value || 20));
  markDirty(true);
  repaint();
});
canvasWidthInput.addEventListener("change", () => {
  state.view.canvas.width = Math.max(640, Number(canvasWidthInput.value || 3840));
  markDirty(true);
  repaint();
});
canvasHeightInput.addEventListener("change", () => {
  state.view.canvas.height = Math.max(480, Number(canvasHeightInput.value || 1800));
  markDirty(true);
  repaint();
});

applyStaticTranslations();
initLanguageSelector(() => {
  repaint();
  setTranslatedStatus(lastStatus.key, lastStatus.params, lastStatus.kind);
});

loadDispatcherLayout();

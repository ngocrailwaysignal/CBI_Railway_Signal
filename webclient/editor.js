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

const board = document.getElementById("editorBoard");
const boardViewport = document.getElementById("boardViewport");
const statusText = document.getElementById("editorStatus");
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

const TOOLBOX_SELECTOR = "[data-tool-kind]";

const state = {
  layoutPath: "",
  bindable: { sections: [], points: [], signals: [] },
  view: createEmptyDispatcherView(),
  selectedIds: new Set(),
  showDebug: false,
  drag: null,
  dirty: false,
};
const boardCamera = createBoardCamera(board, boardViewport, { minScale: 0.45, maxScale: 4 });
let lastCanvasSignature = "";

function setStatus(message, kind = "info") {
  statusText.textContent = message;
  statusText.dataset.kind = kind;
}

function markDirty(isDirty = true) {
  state.dirty = isDirty;
  saveButton.disabled = !isDirty;
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
    emptyStateText: "Drag elements here to author the dispatcher schematic.",
  });
  boardCamera.setCanvas(state.view.canvas);
  boardCamera.apply();
  decorateSelectionHandles();
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
}

function updateInspector() {
  const selected = selectedElements();
  inspector.replaceChildren();
  if (!selected.length) {
    inspector.appendChild(buildInspectorEmpty("Select one or more elements to edit geometry and CBI bindings."));
    return;
  }
  if (selected.length > 1) {
    inspector.appendChild(buildInspectorEmpty(`${selected.length} elements selected. Drag to move as a group.`));
    return;
  }

  const element = selected[0];
  const panel = document.createElement("div");
  panel.className = "inspector-stack";
  panel.appendChild(buildInspectorSummary(element));
  panel.appendChild(buildField("Element ID", buildReadonlyValue(element.id)));
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
  meta.textContent = `Rotate ${Math.round(Number(element.rotation || 0))} deg`;
  summary.appendChild(meta);

  return summary;
}

function buildPositionEditor(element) {
  const wrapper = document.createElement("div");
  wrapper.className = "inspector-field";

  const title = document.createElement("span");
  title.className = "inspector-label";
  title.textContent = "Position";
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
        "Track Style",
        buildSelect(["main", "siding", "yard", "approach"], element.style.variant || "main", (value) => updateElement(element.id, (draft) => {
          draft.style.variant = value;
        })),
      ),
    );
    panel.appendChild(
      buildField("Stroke Width", buildNumberInput(element.geometry.stroke_width, (value) => updateElement(element.id, (draft) => {
        draft.geometry.stroke_width = Math.max(1, value);
      }))),
    );
    return;
  }
  if (element.kind === "signal") {
    panel.appendChild(
      buildField("Mast", buildNumberInput(element.geometry.mast, (value) => updateElement(element.id, (draft) => {
        draft.geometry.mast = Math.max(8, value);
      }))),
    );
    panel.appendChild(
      buildField("Arm", buildNumberInput(element.geometry.arm, (value) => updateElement(element.id, (draft) => {
        draft.geometry.arm = Math.max(6, value);
      }))),
    );
    return;
  }
  if (element.kind === "point") {
    panel.appendChild(
      buildField(
        "Branch Side",
        buildSelect(["up", "down"], element.geometry.branch_side || "up", (value) => updateElement(element.id, (draft) => {
          draft.geometry.branch_side = value;
        })),
      ),
    );
    panel.appendChild(
      buildField("Straight", buildNumberInput(element.geometry.straight, (value) => updateElement(element.id, (draft) => {
        draft.geometry.straight = Math.max(12, value);
      }))),
    );
    panel.appendChild(
      buildField("Branch", buildNumberInput(element.geometry.branch, (value) => updateElement(element.id, (draft) => {
        draft.geometry.branch = Math.max(12, value);
      }))),
    );
    return;
  }
  if (element.kind === "label") {
    panel.appendChild(
      buildField(
        "Text",
        buildTextarea(String(element.geometry.text || ""), (value) => updateElement(element.id, (draft) => {
          draft.geometry.text = value;
        })),
      ),
    );
    panel.appendChild(
      buildField("Font Size", buildNumberInput(element.geometry.font_size, (value) => updateElement(element.id, (draft) => {
        draft.geometry.font_size = Math.max(8, value);
      }))),
    );
    panel.appendChild(
      buildField(
        "Align",
        buildSelect(["start", "middle", "end"], element.geometry.align || "middle", (value) => updateElement(element.id, (draft) => {
          draft.geometry.align = value;
        })),
      ),
    );
    panel.appendChild(
      buildField(
        "Tone",
        buildSelect(["bright", "muted", "amber", "steel"], element.style.tone || "bright", (value) => updateElement(element.id, (draft) => {
          draft.style.tone = value;
        })),
      ),
    );
    return;
  }
  panel.appendChild(
    buildField("Width", buildNumberInput(element.geometry.width, (value) => updateElement(element.id, (draft) => {
      draft.geometry.width = Math.max(8, value);
    }))),
  );
  panel.appendChild(
    buildField("Height", buildNumberInput(element.geometry.height, (value) => updateElement(element.id, (draft) => {
      draft.geometry.height = Math.max(8, value);
    }))),
  );
  panel.appendChild(
    buildField(
      "Tone",
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
  title.textContent = `CBI Binding (${cbiType})`;
  field.appendChild(title);

  if (!options.length) {
    field.appendChild(buildReadonlyValue(`No ${cbiType} IDs available from the current CBI layout.`));
    return field;
  }

  const hint = document.createElement("p");
  hint.className = "hint";
  hint.textContent = `Click one ${cbiType} ID below to bind it to the selected element.`;
  field.appendChild(hint);

  field.appendChild(buildReadonlyValue(element.binding?.cbi_id || `Unbound (${cbiType})`));
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
  textarea.addEventListener("change", () => onChange(textarea.value));
  return textarea;
}

function buildSelect(options, value, onChange, config = {}) {
  const select = document.createElement("select");
  options.forEach((optionValue) => {
    const option = document.createElement("option");
    option.value = optionValue;
    option.textContent = config.labels?.[optionValue] || optionValue || "Unbound";
    select.appendChild(option);
  });
  select.value = value;
  select.addEventListener("change", () => onChange(select.value));
  return select;
}

function buildBindingSearch(options, selectedValue, cbiType, elementId, usage) {
  const input = document.createElement("input");
  input.type = "search";
  input.placeholder = `Filter ${cbiType} IDs`;
  input.value = selectedValue || "";
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
  input.addEventListener("change", () => {
    const exact = options.find((optionValue) => optionValue.toLowerCase() === input.value.trim().toLowerCase());
    if (!exact) {
      return;
    }
    assignBinding(elementId, cbiType, exact, usage);
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
  title.textContent = "Available IDs";
  actions.appendChild(title);

  const clearButton = document.createElement("button");
  clearButton.type = "button";
  clearButton.className = "ghost binding-clear-button";
  clearButton.textContent = "Unbind";
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
    chip.title = owners.length ? `Currently used by ${owners.join(", ")}` : "";

    const idText = document.createElement("span");
    idText.className = "binding-chip-id";
    idText.textContent = optionValue;
    chip.appendChild(idText);

    if (owners.length) {
      const meta = document.createElement("span");
      meta.className = "binding-chip-meta";
      meta.textContent = owners.includes(elementId) && owners.length === 1
        ? "used by this element"
        : `used by ${owners.join(", ")}`;
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
  deleteButton.textContent = "Delete This Element";
  deleteButton.addEventListener("click", () => deleteSelectedElements());
  row.appendChild(deleteButton);

  return row;
}

function formatKindLabel(kind) {
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
      geometry: { text: "LABEL", font_size: 28, align: "middle" },
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
  const element = findElement(elementId);
  if (!element) {
    return;
  }
  updater(element);
  state.view = normalizeDispatcherView(state.view);
  markDirty(true);
  repaint();
}

function commitDragMutation() {
  state.view = normalizeDispatcherView(state.view);
  markDirty(true);
  repaint();
}

function addElement(kind, position) {
  const element = createElementAt(kind, position);
  state.view.elements.push(element);
  state.selectedIds = new Set([element.id]);
  state.view = normalizeDispatcherView(state.view);
  markDirty(true);
  repaint();
}

function clearCanvas() {
  const nextView = createEmptyDispatcherView();
  nextView.canvas = {
    ...nextView.canvas,
    ...deepClone(state.view.canvas),
  };
  state.view = normalizeDispatcherView(nextView);
  state.selectedIds.clear();
  markDirty(true);
  setStatus("Canvas cleared. Save to persist the empty schematic.");
  repaint();
}

function deleteSelectedElements() {
  if (!state.selectedIds.size) {
    return;
  }
  state.view.elements = state.view.elements.filter((element) => !state.selectedIds.has(element.id));
  state.selectedIds.clear();
  state.view = normalizeDispatcherView(state.view);
  markDirty(true);
  repaint();
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

function clientToSvgPoint(clientX, clientY) {
  return clientPointToSvgPoint(board, clientX, clientY);
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
  state.drag = { type: "move", pointerId, startPoint, originals };
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
  };
}

function handlePointerMove(event) {
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
    markDirty(true);
    repaintBoard();
    return;
  }
  if (state.drag.type === "block-resize") {
    const local = globalToLocal(element, currentPoint);
    element.geometry.width = Math.max(8, snapCoordinate(local.x));
    element.geometry.height = Math.max(8, snapCoordinate(local.y));
    markDirty(true);
    repaintBoard();
  }
}

function handlePointerUp(event) {
  if (!state.drag && boardCamera.endPan(event)) {
    event.preventDefault();
    return;
  }
  if (!state.drag || state.drag.pointerId !== event.pointerId) {
    return;
  }
  state.drag = null;
  commitDragMutation();
}

async function loadDispatcherLayout() {
  setStatus("Loading dispatcher schematic...");
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
    markDirty(false);
    setStatus("Dispatcher schematic loaded.");
    repaint({ fit: true });
  } catch (error) {
    setStatus(`Load failed: ${error instanceof Error ? error.message : String(error)}`, "error");
  }
}

async function saveDispatcherLayout() {
  setStatus("Saving dispatcher schematic...");
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
    setStatus("Dispatcher schematic saved.");
    repaint();
    window.location.href = "/dispatcher?saved=1";
  } catch (error) {
    markDirty(true);
    setStatus(`Save failed: ${error instanceof Error ? error.message : String(error)}`, "error");
  }
}

function confirmAndClearCanvas() {
  if (!state.view.elements.length) {
    setStatus("Canvas is already empty.");
    return;
  }
  const confirmed = window.confirm("Clear the entire dispatcher canvas? This removes all elements until you reload or save.");
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
    setSelection("", {});
    if (boardCamera.beginPan(event)) {
      board.setPointerCapture(event.pointerId);
      event.preventDefault();
    }
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
window.addEventListener("resize", () => boardCamera.apply());

document.addEventListener("keydown", (event) => {
  if ((event.key === "Delete" || event.key === "Backspace") && state.selectedIds.size) {
    deleteSelectedElements();
    event.preventDefault();
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
  state.view.canvas.width = Math.max(640, Number(canvasWidthInput.value || 1920));
  markDirty(true);
  repaint();
});
canvasHeightInput.addEventListener("change", () => {
  state.view.canvas.height = Math.max(480, Number(canvasHeightInput.value || 900));
  markDirty(true);
  repaint();
});

loadDispatcherLayout();

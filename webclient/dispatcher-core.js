const SVG_NS = "http://www.w3.org/2000/svg";

export const DEFAULT_CANVAS = {
  width: 1920,
  height: 900,
  grid_size: 20,
  snap_enabled: true,
  background: "#050607",
};

const DEFAULT_TRACK_STYLE = {
  main: { stroke: "#54f27b" },
  siding: { stroke: "#54f27b" },
  yard: { stroke: "#54f27b" },
  approach: { stroke: "#54f27b" },
};

export function createSvgElement(tagName, attrs = {}) {
  const node = document.createElementNS(SVG_NS, tagName);
  Object.entries(attrs).forEach(([key, value]) => {
    if (value === undefined || value === null) {
      return;
    }
    node.setAttribute(key, String(value));
  });
  return node;
}

export function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export function deepClone(value) {
  return JSON.parse(JSON.stringify(value));
}

export function createEmptyDispatcherView() {
  return {
    canvas: { ...DEFAULT_CANVAS },
    elements: [],
  };
}

export function normalizeDispatcherView(rawView, uiPositions = {}) {
  if (!isRecord(rawView)) {
    return createEmptyDispatcherView();
  }
  const source = Array.isArray(rawView.elements)
    ? rawView
    : migrateLegacyDispatcherView(rawView, uiPositions);
  const canvasSource = isRecord(source.canvas) ? source.canvas : {};
  const canvas = {
    width: coerceNumber(canvasSource.width, DEFAULT_CANVAS.width, 640),
    height: coerceNumber(canvasSource.height, DEFAULT_CANVAS.height, 480),
    grid_size: coerceNumber(canvasSource.grid_size, DEFAULT_CANVAS.grid_size, 4),
    snap_enabled: Boolean(canvasSource.snap_enabled ?? DEFAULT_CANVAS.snap_enabled),
    background: String(canvasSource.background || DEFAULT_CANVAS.background),
  };
  const ids = new Set();
  const elements = [];
  const sourceElements = Array.isArray(source.elements) ? source.elements : [];
  sourceElements.forEach((item, index) => {
    if (!isRecord(item)) {
      return;
    }
    const normalized = normalizeElement(item, index);
    if (ids.has(normalized.id)) {
      normalized.id = `${normalized.id}-${index + 1}`;
    }
    ids.add(normalized.id);
    elements.push(normalized);
  });
  elements.sort((left, right) => {
    const zDiff = Number(left.z_index || 0) - Number(right.z_index || 0);
    return zDiff || String(left.id).localeCompare(String(right.id));
  });
  return { canvas, elements };
}

export function normalizeRuntimeState(payload) {
  const runtime = isRecord(payload) ? payload : {};
  const layout = isRecord(runtime.layout) ? runtime.layout : {};
  const dispatcherView = normalizeDispatcherView(layout.dispatcher_view, layout.ui_positions || {});
  const routes = Array.isArray(runtime.routes) ? runtime.routes.filter(isRecord) : [];
  const sections = Array.isArray(layout.sections) ? layout.sections.filter(isRecord) : [];
  const signals = Array.isArray(layout.signals) ? layout.signals.filter(isRecord) : [];
  const edges = Array.isArray(layout.edges) ? layout.edges : [];
  const trains = Array.isArray(runtime.trains) ? runtime.trains.filter(isRecord) : [];
  const occupancy = Array.isArray(runtime.occupancy) ? runtime.occupancy.filter(isRecord) : [];
  const signalState = Array.isArray(runtime.signal_state) ? runtime.signal_state.filter(isRecord) : [];
  const occupancyById = new Map();
  occupancy.forEach((item) => {
    const itemId = String(item.id || "").trim();
    if (itemId) {
      occupancyById.set(itemId, item);
    }
  });
  const signalStateById = new Map();
  signalState.forEach((item) => {
    const itemId = String(item.id || "").trim();
    if (itemId) {
      signalStateById.set(itemId, item);
    }
  });
  return {
    raw: runtime,
    layout,
    dispatcherView,
    sections,
    signals,
    edges,
    routes,
    trains,
    occupancy,
    occupancyById,
    signalState,
    signalStateById,
  };
}

export function renderDispatcherBoard(svg, dispatcherView, runtimeState, options = {}) {
  const view = normalizeDispatcherView(dispatcherView);
  const runtime = runtimeState || normalizeRuntimeState({});
  const showGrid = Boolean(options.showGrid);
  const showDebug = Boolean(options.showDebug);
  const showRoutes = options.showRoutes !== false;
  const showTrains = Boolean(options.showTrains);
  const selectedIds = options.selectedIds instanceof Set ? options.selectedIds : new Set();

  svg.replaceChildren();
  svg.setAttribute("viewBox", `0 0 ${view.canvas.width} ${view.canvas.height}`);
  svg.setAttribute("preserveAspectRatio", "xMidYMid meet");

  const defs = buildDefs();
  svg.appendChild(defs);
  svg.appendChild(
    createSvgElement("rect", {
      x: 0,
      y: 0,
      width: view.canvas.width,
      height: view.canvas.height,
      fill: view.canvas.background || DEFAULT_CANVAS.background,
    }),
  );
  if (showGrid) {
    svg.appendChild(buildGrid(view.canvas.width, view.canvas.height, view.canvas.grid_size));
  }

  const trackBindings = new Map();
  view.elements.forEach((element) => {
    const group = renderElement(element, runtime, { showDebug, showRoutes, selected: selectedIds.has(element.id) });
    if (group) {
      svg.appendChild(group);
    }
    if (element.kind === "track_section" && element.binding?.cbi_type === "section") {
      const bindingId = element.binding.cbi_id;
      if (!trackBindings.has(bindingId)) {
        trackBindings.set(bindingId, []);
      }
      trackBindings.get(bindingId).push(element);
    }
  });

  if (showRoutes) {
    renderActiveRoutes(svg, runtime, trackBindings);
  }
  if (showTrains) {
    renderTrains(svg, runtime, trackBindings);
  }
  if (!view.elements.length && options.emptyStateText) {
    svg.appendChild(
      createSvgElement("text", {
        x: view.canvas.width / 2,
        y: view.canvas.height / 2,
        class: "empty-board-text",
        "text-anchor": "middle",
      }),
    ).textContent = options.emptyStateText;
  }
}

export function getElementLocalBounds(element) {
  if (!element || !element.kind) {
    return { minX: 0, minY: 0, maxX: 0, maxY: 0 };
  }
  if (element.kind === "track_section") {
    const points = Array.isArray(element.geometry?.points) ? element.geometry.points : [];
    const xs = points.map((point) => Number(point.x || 0));
    const ys = points.map((point) => Number(point.y || 0));
    return {
      minX: Math.min(...xs),
      minY: Math.min(...ys),
      maxX: Math.max(...xs),
      maxY: Math.max(...ys),
    };
  }
  if (element.kind === "signal") {
    const mast = Number(element.geometry?.mast || 18);
    const arm = Number(element.geometry?.arm || 14);
    const headRadius = Number(element.geometry?.head_radius || 5.5);
    const labelOffset = Number(element.geometry?.label_offset || 20);
    return {
      minX: -8,
      minY: -mast / 2 - 8,
      maxX: arm + labelOffset + headRadius + 36,
      maxY: mast / 2 + 8,
    };
  }
  if (element.kind === "point") {
    const branch = Number(element.geometry?.branch || 50);
    const diverge = Number(element.geometry?.diverge || 22);
    const straight = Number(element.geometry?.straight || 58);
    return {
      minX: -6,
      minY: -diverge - 8,
      maxX: Math.max(branch, straight) + 8,
      maxY: diverge + 8,
    };
  }
  if (element.kind === "block_marker") {
    const width = Number(element.geometry?.width || 42);
    const height = Number(element.geometry?.height || 18);
    return { minX: 0, minY: 0, maxX: width, maxY: height };
  }
  const fontSize = Number(element.geometry?.font_size || 28);
  const text = String(element.geometry?.text || "");
  const longest = text.split("\n").reduce((max, line) => Math.max(max, line.length), 1);
  return {
    minX: -(longest * fontSize * 0.32),
    minY: -fontSize,
    maxX: longest * fontSize * 0.32,
    maxY: fontSize * Math.max(text.split("\n").length, 1),
  };
}

export function snapValue(value, gridSize, enabled = true) {
  if (!enabled || !Number.isFinite(gridSize) || gridSize <= 1) {
    return value;
  }
  return Math.round(value / gridSize) * gridSize;
}

export function globalPointToLocal(group, svg, clientX, clientY) {
  const svgPoint = svg.createSVGPoint();
  svgPoint.x = clientX;
  svgPoint.y = clientY;
  const transformed = svgPoint.matrixTransform(group.getScreenCTM().inverse());
  return { x: transformed.x, y: transformed.y };
}

function normalizeElement(rawElement, index) {
  const kind = String(rawElement.kind || "").trim().toLowerCase();
  const id = String(rawElement.id || `${kind || "element"}-${index + 1}`).trim() || `element-${index + 1}`;
  const positionSource = isRecord(rawElement.position) ? rawElement.position : {};
  const position = {
    x: coerceNumber(positionSource.x, 0),
    y: coerceNumber(positionSource.y, 0),
  };
  const rotation = coerceNumber(rawElement.rotation, 0);
  const geometry = normalizeGeometry(kind, rawElement.geometry);
  const style = isRecord(rawElement.style) ? deepClone(rawElement.style) : {};
  const binding = isRecord(rawElement.binding) &&
    String(rawElement.binding.cbi_type || "").trim() &&
    String(rawElement.binding.cbi_id || "").trim()
      ? {
          cbi_type: String(rawElement.binding.cbi_type).trim().toLowerCase(),
          cbi_id: String(rawElement.binding.cbi_id).trim(),
        }
      : null;
  return {
    id,
    kind,
    position,
    rotation,
    geometry,
    style,
    z_index: Math.round(coerceNumber(rawElement.z_index, index)),
    binding,
  };
}

function normalizeGeometry(kind, geometry) {
  const source = isRecord(geometry) ? geometry : {};
  if (kind === "track_section") {
    const points = Array.isArray(source.points) && source.points.length >= 2
      ? source.points.map((point) => ({ x: coerceNumber(point?.x, 0), y: coerceNumber(point?.y, 0) }))
      : [{ x: 0, y: 0 }, { x: 160, y: 0 }];
    return {
      points,
      stroke_width: coerceNumber(source.stroke_width, 4, 1),
      marker_spacing: coerceNumber(source.marker_spacing, 48, 8),
    };
  }
  if (kind === "signal") {
    return {
      mast: coerceNumber(source.mast, 18, 8),
      arm: coerceNumber(source.arm, 14, 6),
      head_radius: coerceNumber(source.head_radius, 5.5, 3),
      label_offset: coerceNumber(source.label_offset, 20, 6),
    };
  }
  if (kind === "point") {
    const branchSide = String(source.branch_side || "up").trim().toLowerCase() === "down" ? "down" : "up";
    return {
      trunk: coerceNumber(source.trunk, 24, 8),
      straight: coerceNumber(source.straight, 58, 12),
      branch: coerceNumber(source.branch, 50, 12),
      diverge: coerceNumber(source.diverge, 22, 8),
      branch_side: branchSide,
    };
  }
  if (kind === "label") {
    const align = String(source.align || "middle").trim().toLowerCase();
    return {
      text: String(source.text || "LABEL"),
      font_size: coerceNumber(source.font_size, 28, 8),
      align: ["start", "middle", "end"].includes(align) ? align : "middle",
    };
  }
  return {
    width: coerceNumber(source.width, 42, 8),
    height: coerceNumber(source.height, 18, 8),
    radius: coerceNumber(source.radius, 8, 0),
  };
}

function migrateLegacyDispatcherView(rawView, uiPositions) {
  const view = createEmptyDispatcherView();
  let zIndex = 0;
  const segments = Array.isArray(rawView.segments) ? rawView.segments : [];
  segments.forEach((segment) => {
    if (!isRecord(segment) || !Array.isArray(segment.points) || segment.points.length < 2) {
      return;
    }
    const absolutePoints = segment.points
      .map((point) => coerceLegacyPoint(point, uiPositions))
      .filter(Boolean);
    if (absolutePoints.length < 2) {
      return;
    }
    const xs = absolutePoints.map((point) => point.x);
    const ys = absolutePoints.map((point) => point.y);
    const minX = Math.min(...xs);
    const minY = Math.min(...ys);
    const relativePoints = absolutePoints.map((point) => ({ x: point.x - minX, y: point.y - minY }));
    const stateSourceIds = Array.isArray(segment.state_source_ids)
      ? segment.state_source_ids.map((item) => String(item || "").trim()).filter(Boolean)
      : [];
    view.elements.push({
      id: String(segment.id || `segment-${zIndex + 1}`),
      kind: "track_section",
      position: { x: minX, y: minY },
      rotation: 0,
      geometry: {
        points: relativePoints,
        stroke_width: 4,
        marker_spacing: 42,
      },
      style: { variant: String(segment.kind || "main").trim().toLowerCase() || "main" },
      z_index: zIndex,
      binding: stateSourceIds.length === 1 ? { cbi_type: "section", cbi_id: stateSourceIds[0] } : null,
    });
    zIndex += 1;
  });
  const signalSymbols = Array.isArray(rawView.signal_symbols) ? rawView.signal_symbols : [];
  signalSymbols.forEach((signalSymbol) => {
    if (!isRecord(signalSymbol)) {
      return;
    }
    const signalId = String(signalSymbol.signal_id || "").trim();
    if (!signalId) {
      return;
    }
    const direction = String(signalSymbol.direction || "RIGHT").trim().toUpperCase();
    view.elements.push({
      id: `signal-${signalId}`,
      kind: "signal",
      position: { x: coerceNumber(signalSymbol.x, 0), y: coerceNumber(signalSymbol.y, 0) },
      rotation: direction === "LEFT" ? 180 : 0,
      geometry: { mast: 18, arm: 14, head_radius: 5.5, label_offset: 20 },
      style: {},
      z_index: 500 + zIndex,
      binding: { cbi_type: "signal", cbi_id: signalId },
    });
    zIndex += 1;
  });
  const annotations = Array.isArray(rawView.annotations) ? rawView.annotations : [];
  annotations.forEach((annotation) => {
    if (!isRecord(annotation)) {
      return;
    }
    const kind = String(annotation.kind || "text").trim().toLowerCase();
    if (kind === "pill") {
      view.elements.push({
        id: String(annotation.id || `block-${zIndex + 1}`),
        kind: "block_marker",
        position: { x: coerceNumber(annotation.x, 0), y: coerceNumber(annotation.y, 0) },
        rotation: 0,
        geometry: {
          width: coerceNumber(annotation.width, 42, 8),
          height: 18,
          radius: 8,
        },
        style: { tone: String(annotation.tone || "steel").trim().toLowerCase() || "steel" },
        z_index: 700 + zIndex,
        binding: null,
      });
    } else {
      view.elements.push({
        id: String(annotation.id || `label-${zIndex + 1}`),
        kind: "label",
        position: { x: coerceNumber(annotation.x, 0), y: coerceNumber(annotation.y, 0) },
        rotation: 0,
        geometry: {
          text: String(annotation.text || ""),
          font_size: sizeTokenToFont(annotation.size),
          align: normalizeTextAnchor(annotation.align),
        },
        style: { tone: String(annotation.tone || "bright").trim().toLowerCase() || "bright" },
        z_index: 650 + zIndex,
        binding: null,
      });
    }
    zIndex += 1;
  });
  return view;
}

function coerceLegacyPoint(point, uiPositions) {
  if (!isRecord(point)) {
    return null;
  }
  if (typeof point.x === "number" || typeof point.y === "number") {
    return { x: coerceNumber(point.x, 0), y: coerceNumber(point.y, 0) };
  }
  const nodeId = String(point.node_id || "").trim();
  const position = nodeId ? uiPositions?.[nodeId] : null;
  if (Array.isArray(position) && position.length >= 2) {
    return { x: coerceNumber(position[0], 0), y: coerceNumber(position[1], 0) };
  }
  return null;
}

function renderElement(element, runtime, options) {
  const group = createSvgElement("g", {
    class: `dispatcher-element kind-${element.kind}`,
    transform: `translate(${element.position.x} ${element.position.y}) rotate(${element.rotation})`,
    "data-element-id": element.id,
    "data-kind": element.kind,
  });
  if (element.kind === "track_section") {
    renderTrackSection(group, element, runtime, options);
  } else if (element.kind === "signal") {
    renderSignal(group, element, runtime, options);
  } else if (element.kind === "point") {
    renderPoint(group, element, runtime, options);
  } else if (element.kind === "label") {
    renderLabel(group, element);
  } else if (element.kind === "block_marker") {
    renderBlockMarker(group, element);
  }
  if (options.selected) {
    group.appendChild(buildSelectionOutline(element));
  }
  return group;
}

function renderTrackSection(group, element, runtime, options) {
  const polylinePoints = element.geometry.points.map((point) => `${point.x},${point.y}`).join(" ");
  const bindingId = element.binding?.cbi_id || "";
  const runtimeItem = bindingId ? runtime.occupancyById.get(bindingId) : null;
  const occupied = Boolean(runtimeItem?.occupied);
  const variant = String(element.style?.variant || "main").trim().toLowerCase();
  const trackStyle = DEFAULT_TRACK_STYLE[variant] || DEFAULT_TRACK_STYLE.main;
  const width = Number(element.geometry.stroke_width || 4);
  const baseColor = occupied ? "#ff655b" : trackStyle.stroke;
  const visualWidth = occupied ? width + 2.5 : width;

  group.appendChild(
    createSvgElement("polyline", {
      points: polylinePoints,
      fill: "none",
      style: `stroke:${baseColor};stroke-width:${visualWidth};`,
      stroke: baseColor,
      "stroke-width": visualWidth,
      "stroke-linecap": "square",
      "stroke-linejoin": "round",
      class: "track-base",
      filter: occupied ? "url(#dispatcherGlow)" : undefined,
    }),
  );

  const ticks = createTickMarks(element.geometry.points, visualWidth, baseColor);
  if (ticks) {
    group.appendChild(ticks);
  }
  if (options.showDebug && bindingId) {
    const mid = polylineMidpoint(element.geometry.points);
    group.appendChild(
      createSvgElement("text", {
        x: mid.x,
        y: mid.y - 12,
        class: "dispatcher-debug-label",
        "text-anchor": "middle",
      }),
    ).textContent = bindingId;
  }
}

function renderSignal(group, element, runtime) {
  const geometry = element.geometry;
  const mast = Number(geometry.mast || 18);
  const arm = Number(geometry.arm || 14);
  const headRadius = Number(geometry.head_radius || 5.5);
  const labelOffset = Number(geometry.label_offset || 20);
  const bindingId = element.binding?.cbi_id || "";
  const runtimeSignal = bindingId ? runtime.signalStateById.get(bindingId) : null;
  const aspect = String(runtimeSignal?.aspect || "STOP").toUpperCase();
  const color = aspect === "PROCEED" ? "#54f27b" : "#ff655b";

  group.appendChild(
    createSvgElement("line", {
      x1: 0,
      y1: -mast / 2,
      x2: 0,
      y2: mast / 2,
      class: "dispatcher-signal-mast",
    }),
  );
  group.appendChild(
    createSvgElement("line", {
      x1: 0,
      y1: 0,
      x2: arm,
      y2: 0,
      class: "dispatcher-signal-arm",
    }),
  );
  group.appendChild(
    createSvgElement("circle", {
      cx: arm,
      cy: 0,
      r: headRadius,
      fill: color,
      stroke: color,
      filter: "url(#dispatcherGlow)",
    }),
  );
  if (bindingId) {
    const label = createSvgElement("text", {
      x: arm + labelOffset,
      y: 4,
      class: "dispatcher-signal-label",
      "text-anchor": "start",
    });
    label.textContent = bindingId;
    group.appendChild(label);
  }
}

function renderPoint(group, element, runtime, options) {
  const geometry = element.geometry;
  const trunk = Number(geometry.trunk || 24);
  const straight = Number(geometry.straight || 58);
  const branch = Number(geometry.branch || 50);
  const diverge = Number(geometry.diverge || 22);
  const branchDirection = geometry.branch_side === "down" ? 1 : -1;
  const bindingId = element.binding?.cbi_id || "";
  const runtimePoint = bindingId ? runtime.occupancyById.get(bindingId) : null;
  const position = String(runtimePoint?.position || "NORMAL").toUpperCase();
  const locked = Boolean(runtimePoint?.locked_by);

  const toeX = 0;
  const straightX = trunk + straight;
  const branchX = trunk + branch;
  const branchY = diverge * branchDirection;

  group.appendChild(
    createSvgElement("line", {
      x1: 0,
      y1: 0,
      x2: trunk,
      y2: 0,
      class: "dispatcher-point-stock",
    }),
  );
  group.appendChild(
    createSvgElement("line", {
      x1: trunk,
      y1: 0,
      x2: straightX,
      y2: 0,
      class: `dispatcher-point-blade ${position === "NORMAL" ? "active" : ""}`,
      stroke: position === "NORMAL" ? "#54f27b" : undefined,
      filter: position === "NORMAL" ? "url(#dispatcherRouteGlow)" : undefined,
    }),
  );
  group.appendChild(
    createSvgElement("line", {
      x1: trunk,
      y1: 0,
      x2: branchX,
      y2: branchY,
      class: `dispatcher-point-blade ${position === "REVERSE" ? "active" : ""}`,
      stroke: position === "REVERSE" ? "#54f27b" : undefined,
      filter: position === "REVERSE" ? "url(#dispatcherRouteGlow)" : undefined,
    }),
  );
  if (locked) {
    group.appendChild(
      createSvgElement("circle", {
        cx: trunk - 6,
        cy: -10,
        r: 4,
        fill: "#ff655b",
        filter: "url(#dispatcherGlow)",
      }),
    );
  }
  if (options.showDebug && bindingId) {
    const text = createSvgElement("text", {
      x: trunk + 14,
      y: branchY < 0 ? -12 : 18,
      class: "dispatcher-debug-label",
      "text-anchor": "middle",
    });
    text.textContent = bindingId;
    group.appendChild(text);
  }
}

function renderLabel(group, element) {
  const fontSize = Number(element.geometry.font_size || 28);
  const align = normalizeTextAnchor(element.geometry.align);
  const tone = String(element.style?.tone || "bright").trim().toLowerCase();
  const label = createSvgElement("text", {
    x: 0,
    y: 0,
    "text-anchor": align,
    class: `dispatcher-label tone-${tone}`,
    "font-size": fontSize,
  });
  const lines = String(element.geometry.text || "").split("\n");
  lines.forEach((line, lineIndex) => {
    const tspan = createSvgElement("tspan", {
      x: 0,
      dy: lineIndex === 0 ? 0 : fontSize * 1.05,
    });
    tspan.textContent = line;
    label.appendChild(tspan);
  });
  group.appendChild(label);
}

function renderBlockMarker(group, element) {
  const width = Number(element.geometry.width || 42);
  const height = Number(element.geometry.height || 18);
  const radius = Number(element.geometry.radius || 8);
  const tone = String(element.style?.tone || "steel").trim().toLowerCase();
  group.appendChild(
    createSvgElement("rect", {
      x: 0,
      y: 0,
      width,
      height,
      rx: radius,
      ry: radius,
      class: `dispatcher-block tone-${tone}`,
    }),
  );
}

function renderTrains(svg, runtime, trackBindings) {
  const placedBySection = new Map();
  runtime.trains.forEach((train) => {
    const sectionId = String(train.current_section || "").trim();
    if (!sectionId || !trackBindings.has(sectionId)) {
      return;
    }
    const elements = trackBindings.get(sectionId);
    if (!elements || !elements.length) {
      return;
    }
    const element = elements[0];
    const localMid = polylineMidpoint(element.geometry.points);
    const offsetIndex = placedBySection.get(sectionId) || 0;
    placedBySection.set(sectionId, offsetIndex + 1);
    const globalMid = localToGlobal(element, {
      x: localMid.x + 22 * offsetIndex,
      y: localMid.y - 18 - 20 * offsetIndex,
    });
    const tag = createSvgElement("g", {
      class: "dispatcher-train-tag",
      transform: `translate(${globalMid.x} ${globalMid.y})`,
    });
    tag.appendChild(
      createSvgElement("rect", {
        x: -22,
        y: -11,
        width: Math.max(48, String(train.id || "TR").length * 8 + 14),
        height: 22,
        rx: 6,
        ry: 6,
        class: "dispatcher-train-chip",
      }),
    );
    const label = createSvgElement("text", {
      x: 0,
      y: 4,
      "text-anchor": "middle",
      class: "dispatcher-train-label",
    });
    label.textContent = String(train.id || "TR");
    tag.appendChild(label);
    svg.appendChild(tag);
  });
}

function buildDefs() {
  const defs = createSvgElement("defs");
  defs.appendChild(
    createSvgElement("marker", {
      id: "dispatcherRouteArrow",
      viewBox: "0 0 12 12",
      refX: 10,
      refY: 6,
      markerWidth: 12,
      markerHeight: 12,
      orient: "auto",
      markerUnits: "strokeWidth",
    }),
  );
  defs.lastChild.appendChild(
    createSvgElement("path", {
      d: "M 0 1 L 11 6 L 0 11 z",
      fill: "#54f27b",
    }),
  );
  const glow = createSvgElement("filter", { id: "dispatcherGlow" });
  glow.appendChild(createSvgElement("feGaussianBlur", { stdDeviation: 4, result: "blur" }));
  glow.appendChild(createSvgElement("feMerge", {}));
  glow.lastChild.appendChild(createSvgElement("feMergeNode", { in: "blur" }));
  glow.lastChild.appendChild(createSvgElement("feMergeNode", { in: "SourceGraphic" }));
  defs.appendChild(glow);
  const routeGlow = createSvgElement("filter", { id: "dispatcherRouteGlow" });
  routeGlow.appendChild(createSvgElement("feGaussianBlur", { stdDeviation: 5, result: "blur" }));
  routeGlow.appendChild(createSvgElement("feMerge", {}));
  routeGlow.lastChild.appendChild(createSvgElement("feMergeNode", { in: "blur" }));
  routeGlow.lastChild.appendChild(createSvgElement("feMergeNode", { in: "SourceGraphic" }));
  defs.appendChild(routeGlow);
  return defs;
}

function buildGrid(width, height, gridSize) {
  const group = createSvgElement("g", { class: "dispatcher-grid" });
  for (let x = 0; x <= width; x += gridSize) {
    group.appendChild(createSvgElement("line", { x1: x, y1: 0, x2: x, y2: height }));
  }
  for (let y = 0; y <= height; y += gridSize) {
    group.appendChild(createSvgElement("line", { x1: 0, y1: y, x2: width, y2: y }));
  }
  return group;
}

function buildSelectionOutline(element) {
  const bounds = getElementLocalBounds(element);
  const group = createSvgElement("g", { class: "dispatcher-selection" });
  group.appendChild(
    createSvgElement("rect", {
      x: bounds.minX - 10,
      y: bounds.minY - 10,
      width: bounds.maxX - bounds.minX + 20,
      height: bounds.maxY - bounds.minY + 20,
      rx: 10,
      ry: 10,
      class: "dispatcher-selection-box",
    }),
  );
  return group;
}

function createTickMarks(points, width, color = "rgba(245, 247, 251, 0.9)") {
  if (!Array.isArray(points) || points.length < 2) {
    return null;
  }
  const totalLength = polylineLength(points);
  if (totalLength < 8) {
    return null;
  }
  const group = createSvgElement("g", { class: "dispatcher-track-ticks", style: `--track-tick-stroke:${color};` });
  [totalLength / 3, (totalLength * 2) / 3].forEach((distance) => {
    const marker = pointAndNormalAtDistance(points, distance);
    if (!marker) {
      return;
    }
      group.appendChild(
        createSvgElement("line", {
          x1: marker.point.x - marker.normal.x * (width * 1.6),
          y1: marker.point.y - marker.normal.y * (width * 1.6),
          x2: marker.point.x + marker.normal.x * (width * 1.6),
          y2: marker.point.y + marker.normal.y * (width * 1.6),
          stroke: color,
        }),
      );
    });
  return group.childNodes.length ? group : null;
}

function polylineLength(points) {
  let total = 0;
  for (let index = 0; index < points.length - 1; index += 1) {
    const start = points[index];
    const end = points[index + 1];
    total += Math.hypot(end.x - start.x, end.y - start.y);
  }
  return total;
}

function pointAndNormalAtDistance(points, distance) {
  let walked = 0;
  for (let index = 0; index < points.length - 1; index += 1) {
    const start = points[index];
    const end = points[index + 1];
    const dx = end.x - start.x;
    const dy = end.y - start.y;
    const segmentLength = Math.hypot(dx, dy);
    if (segmentLength < 1) {
      walked += segmentLength;
      continue;
    }
    if (walked + segmentLength >= distance || index === points.length - 2) {
      const distanceOnSegment = Math.max(0, Math.min(segmentLength, distance - walked));
      const ratio = segmentLength ? distanceOnSegment / segmentLength : 0;
      return {
        point: {
          x: start.x + dx * ratio,
          y: start.y + dy * ratio,
        },
        normal: {
          x: -dy / segmentLength,
          y: dx / segmentLength,
        },
      };
    }
    walked += segmentLength;
  }
  return null;
}

function routeHasElementBinding(route, bindingId) {
  if (!isRecord(route)) {
    return false;
  }
  const fullPath = Array.isArray(route.full_path) ? route.full_path : [];
  const path = Array.isArray(route.path) ? route.path : [];
  const overlapPath = Array.isArray(route.overlap_path) ? route.overlap_path : [];
  return [...fullPath, ...path, ...overlapPath].map((value) => String(value || "")).includes(bindingId);
}

function polylineMidpoint(points) {
  if (!Array.isArray(points) || !points.length) {
    return { x: 0, y: 0 };
  }
  if (points.length === 1) {
    return { x: points[0].x, y: points[0].y };
  }
  const totalLength = points.slice(0, -1).reduce((sum, point, index) => {
    const next = points[index + 1];
    return sum + Math.hypot(next.x - point.x, next.y - point.y);
  }, 0);
  const target = totalLength / 2;
  let walked = 0;
  for (let index = 0; index < points.length - 1; index += 1) {
    const start = points[index];
    const end = points[index + 1];
    const segmentLength = Math.hypot(end.x - start.x, end.y - start.y);
    if (walked + segmentLength >= target) {
      const ratio = segmentLength ? (target - walked) / segmentLength : 0;
      return {
        x: start.x + (end.x - start.x) * ratio,
        y: start.y + (end.y - start.y) * ratio,
      };
    }
    walked += segmentLength;
  }
  return { x: points[points.length - 1].x, y: points[points.length - 1].y };
}

export function localToGlobal(element, point) {
  const radians = (Number(element.rotation || 0) * Math.PI) / 180;
  const cos = Math.cos(radians);
  const sin = Math.sin(radians);
  return {
    x: element.position.x + point.x * cos - point.y * sin,
    y: element.position.y + point.x * sin + point.y * cos,
  };
}

function renderActiveRoutes(svg, runtime, trackBindings) {
  effectiveRoutes(runtime).forEach((route) => {
    const routeBindings = orderedRouteBindings(route);
    const routeSegments = [];
    routeBindings.forEach((bindingId) => {
      const boundElements = trackBindings.get(bindingId) || [];
      boundElements.forEach((element) => routeSegments.push(element));
    });
    routeSegments.forEach((element, index) => {
      const globalPoints = element.geometry.points.map((point) => localToGlobal(element, point));
      svg.appendChild(
        createSvgElement("polyline", {
          points: globalPoints.map((point) => `${point.x},${point.y}`).join(" "),
          fill: "none",
          stroke: "#7dff98",
          "stroke-width": Number(element.geometry.stroke_width || 4) + 2.8,
          "stroke-linecap": "round",
          "stroke-linejoin": "round",
          class: "dispatcher-route-line",
          filter: "url(#dispatcherRouteGlow)",
          "marker-mid": "url(#dispatcherRouteArrow)",
          "marker-end": index === routeSegments.length - 1 ? "url(#dispatcherRouteArrow)" : undefined,
        }),
      );
    });
  });
}

function effectiveRoutes(runtime) {
  if (Array.isArray(runtime.routes) && runtime.routes.length) {
    return runtime.routes;
  }
  const inferredRouteIds = new Set();
  runtime.trains.forEach((train) => {
    const routeId = String(train.route_id || "").trim();
    if (routeId) {
      inferredRouteIds.add(routeId);
    }
  });
  runtime.occupancy.forEach((item) => {
    const routeId = String(item.locked_by || "").trim();
    if (routeId) {
      inferredRouteIds.add(routeId);
    }
  });
  runtime.signalState.forEach((item) => {
    const routeId = String(item.route_id || "").trim();
    if (routeId) {
      inferredRouteIds.add(routeId);
    }
  });
  return Array.from(inferredRouteIds)
    .map((routeId) => inferRouteFromLayout(routeId, runtime))
    .filter(Boolean);
}

function inferRouteFromLayout(routeId, runtime) {
  const signalIds = runtime.signals.map((signal) => String(signal.id || "").trim()).filter(Boolean);
  const signalPair = parseRouteSignalIds(routeId, signalIds);
  if (!signalPair) {
    return null;
  }
  const signalsById = new Map(runtime.signals.map((signal) => [String(signal.id || "").trim(), signal]));
  const entrySignal = signalsById.get(signalPair.entrySignalId);
  const exitSignal = signalsById.get(signalPair.exitSignalId);
  const startSection = String(entrySignal?.protects || "").trim();
  const endSection = String(exitSignal?.protects || "").trim();
  if (!startSection || !endSection) {
    return null;
  }
  const path = findTopologyPath(runtime.edges, startSection, endSection)
    .filter((nodeId) => runtime.sections.some((section) => String(section.id || "").trim() === nodeId));
  if (!path.length) {
    return null;
  }
  return {
    id: routeId,
    entry_signal_id: signalPair.entrySignalId,
    exit_signal_id: signalPair.exitSignalId,
    path,
    full_path: path,
    overlap_path: [],
    lifecycle_state: "INFERRED",
    status: "ACTIVE",
  };
}

function parseRouteSignalIds(routeId, signalIds) {
  const token = String(routeId || "").trim();
  if (!token.startsWith("R_")) {
    return null;
  }
  const tail = token.slice(2);
  for (const entrySignalId of signalIds) {
    const prefix = `${entrySignalId}_`;
    if (!tail.startsWith(prefix)) {
      continue;
    }
    const remaining = tail.slice(prefix.length);
    for (const exitSignalId of signalIds) {
      const exitPrefix = `${exitSignalId}_`;
      if (remaining.startsWith(exitPrefix)) {
        return { entrySignalId, exitSignalId };
      }
    }
  }
  return null;
}

function findTopologyPath(edges, startNodeId, endNodeId) {
  const adjacency = new Map();
  (Array.isArray(edges) ? edges : []).forEach((edge) => {
    if (!Array.isArray(edge) || edge.length < 2) {
      return;
    }
    const left = String(edge[0] || "").trim();
    const right = String(edge[1] || "").trim();
    if (!left || !right) {
      return;
    }
    if (!adjacency.has(left)) {
      adjacency.set(left, []);
    }
    if (!adjacency.has(right)) {
      adjacency.set(right, []);
    }
    adjacency.get(left).push(right);
    adjacency.get(right).push(left);
  });
  const queue = [[startNodeId]];
  const visited = new Set([startNodeId]);
  while (queue.length) {
    const path = queue.shift();
    const current = path[path.length - 1];
    if (current === endNodeId) {
      return path;
    }
    (adjacency.get(current) || []).forEach((neighbor) => {
      if (visited.has(neighbor)) {
        return;
      }
      visited.add(neighbor);
      queue.push([...path, neighbor]);
    });
  }
  return [startNodeId];
}

function orderedRouteBindings(route) {
  if (!isRecord(route)) {
    return [];
  }
  const result = [];
  const seen = new Set();
  [...(Array.isArray(route.full_path) ? route.full_path : []), ...(Array.isArray(route.overlap_path) ? route.overlap_path : [])]
    .map((value) => String(value || "").trim())
    .filter(Boolean)
    .forEach((value) => {
      if (!seen.has(value)) {
        seen.add(value);
        result.push(value);
      }
    });
  if (result.length) {
    return result;
  }
  return (Array.isArray(route.path) ? route.path : [])
    .map((value) => String(value || "").trim())
    .filter(Boolean);
}


function normalizeTextAnchor(value) {
  const token = String(value || "middle").trim().toLowerCase();
  if (token === "start" || token === "end") {
    return token;
  }
  return "middle";
}

function sizeTokenToFont(value) {
  const token = String(value || "").trim().toLowerCase();
  if (token === "sm") {
    return 18;
  }
  if (token === "lg") {
    return 30;
  }
  if (token === "xl") {
    return 38;
  }
  return 24;
}

function coerceNumber(value, fallback, minimum = Number.NEGATIVE_INFINITY) {
  const number = Number(value);
  if (Number.isFinite(number)) {
    return Math.max(minimum, number);
  }
  return Math.max(minimum, fallback);
}

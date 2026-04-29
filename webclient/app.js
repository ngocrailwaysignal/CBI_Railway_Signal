const SVG_NS = "http://www.w3.org/2000/svg";
const POLL_INTERVAL_MS = 1000;
const STALE_AFTER_MS = 3200;
const TRACK_MARKER_SPACING = 44;
const TRACK_MARKER_LENGTH = 14;
const ANNOTATION_SIZES = {
  sm: 14,
  md: 19,
  lg: 25,
  xl: 38,
};

const board = document.getElementById("dispatcherBoard");
const scenarioTitle = document.getElementById("scenarioTitle");
const routeList = document.getElementById("routeList");
const eventLog = document.getElementById("eventLog");
const connectionPill = document.getElementById("connectionPill");
const routeMetric = document.getElementById("routeMetric");
const trainMetric = document.getElementById("trainMetric");
const occupancyMetric = document.getElementById("occupancyMetric");
const streamMetric = document.getElementById("streamMetric");
const clockText = document.getElementById("clockText");
const transportHint = document.getElementById("transportHint");
const workspaceModeText = document.getElementById("workspaceModeText");
const updatedAtText = document.getElementById("updatedAtText");
const cycleSceneBtn = document.getElementById("cycleSceneBtn");
const toggleRoutesBtn = document.getElementById("toggleRoutesBtn");
const debugLabelsBtn = document.getElementById("debugLabelsBtn");

const demoDispatcherView = {
  display: {
    show_debug_ids_default: false,
  },
  segments: [
    {
      id: "north-outer",
      kind: "yard",
      points: [{ x: 72, y: 150 }, { x: 210, y: 150 }, { x: 280, y: 92 }, { x: 520, y: 92 }, { x: 590, y: 150 }, { x: 1810, y: 150 }],
      state_source_ids: ["S12", "S14", "P2", "S4", "2", "S7"],
    },
    {
      id: "north-inner",
      kind: "yard",
      points: [{ x: 72, y: 205 }, { x: 182, y: 205 }, { x: 290, y: 320 }, { x: 505, y: 320 }, { x: 680, y: 205 }, { x: 1810, y: 205 }],
      state_source_ids: ["S14", "S2", "P2", "S4", "2"],
    },
    {
      id: "west-upper",
      kind: "approach",
      points: [{ x: -10, y: 258 }, { x: 160, y: 258 }, { x: 405, y: 258 }, { x: 560, y: 132 }],
      state_source_ids: ["AS1", "S1", "P1", "S2"],
    },
    {
      id: "west-lower",
      kind: "approach",
      points: [{ x: -10, y: 312 }, { x: 165, y: 312 }, { x: 410, y: 312 }, { x: 560, y: 205 }],
      state_source_ids: ["AS1", "S1", "P1", "S10"],
    },
    {
      id: "left-branch",
      kind: "yard",
      points: [{ x: 122, y: 380 }, { x: 182, y: 380 }, { x: 276, y: 312 }],
      state_source_ids: ["S12", "S14", "P2"],
    },
    {
      id: "main-upper",
      kind: "main",
      points: [{ x: 36, y: 468 }, { x: 165, y: 468 }, { x: 260, y: 502 }, { x: 418, y: 502 }, { x: 495, y: 468 }, { x: 1820, y: 468 }],
      state_source_ids: ["S1", "P1", "S10", "1", "S8", "P3", "S9"],
    },
    {
      id: "main-lower",
      kind: "main",
      points: [{ x: 36, y: 528 }, { x: 192, y: 528 }, { x: 274, y: 590 }, { x: 456, y: 590 }, { x: 532, y: 528 }, { x: 1820, y: 528 }],
      state_source_ids: ["S10", "1", "S8", "P3", "S9"],
    },
    {
      id: "yard-ladder",
      kind: "yard",
      points: [{ x: 36, y: 580 }, { x: 126, y: 580 }, { x: 220, y: 580 }, { x: 400, y: 580 }, { x: 482, y: 528 }],
      state_source_ids: ["S10", "P1", "S2"],
    },
    {
      id: "south-main",
      kind: "siding",
      points: [
        { x: 40, y: 642 },
        { x: 640, y: 642 },
        { x: 764, y: 734 },
        { x: 1018, y: 734 },
        { x: 1144, y: 690 },
        { x: 1556, y: 690 },
        { x: 1712, y: 690 },
        { x: 1828, y: 734 },
        { x: 1990, y: 734 },
      ],
      state_source_ids: ["S14", "S12", "2", "S7", "AS2"],
    },
    {
      id: "south-diverge",
      kind: "siding",
      points: [{ x: 640, y: 642 }, { x: 760, y: 642 }, { x: 856, y: 690 }, { x: 1018, y: 690 }],
      state_source_ids: ["S14", "P2", "S4"],
    },
    {
      id: "east-diverge",
      kind: "main",
      points: [{ x: 1348, y: 468 }, { x: 1424, y: 528 }, { x: 1614, y: 528 }],
      state_source_ids: ["S8", "P3", "S9"],
    },
    {
      id: "east-tail",
      kind: "siding",
      points: [{ x: 1556, y: 690 }, { x: 1706, y: 690 }, { x: 1828, y: 734 }],
      state_source_ids: ["S9", "AS2"],
    },
  ],
  signal_symbols: [
    { signal_id: "A", x: 150, y: 205, direction: "RIGHT" },
    { signal_id: "Y", x: 175, y: 380, direction: "LEFT" },
    { signal_id: "N2", x: 690, y: 205, direction: "LEFT" },
    { signal_id: "N1", x: 520, y: 642, direction: "LEFT" },
    { signal_id: "G2", x: 1135, y: 205, direction: "RIGHT" },
    { signal_id: "G1", x: 1575, y: 468, direction: "RIGHT" },
    { signal_id: "F", x: 1450, y: 205, direction: "LEFT" },
  ],
  annotations: [
    { id: "jersey", kind: "text", text: "JERSEY\nAVENUE", x: 86, y: 432, tone: "bright", size: "lg", align: "start" },
    { id: "branch-a", kind: "text", text: "<<Millstone Branch", x: 156, y: 412, tone: "amber", size: "sm", align: "start" },
    { id: "branch-b", kind: "text", text: "<<County Yard", x: 152, y: 444, tone: "amber", size: "sm", align: "start" },
    { id: "county", kind: "text", text: "B\nCOUNTY", x: 306, y: 370, tone: "bright", size: "xl" },
    { id: "brunswick", kind: "text", text: "NEW\nBRUNSWICK", x: 574, y: 372, tone: "bright", size: "md" },
    { id: "edison", kind: "text", text: "C\nEDISON", x: 712, y: 364, tone: "bright", size: "xl" },
    { id: "edison-sub", kind: "text", text: "General Tire>>\nNational Can>>", x: 718, y: 440, tone: "amber", size: "sm" },
    { id: "lincoln", kind: "text", text: "D\nLINCOLN", x: 1116, y: 356, tone: "bright", size: "xl" },
    { id: "metro", kind: "text", text: "METRO\nPARK", x: 1450, y: 392, tone: "bright", size: "md" },
    { id: "menlo", kind: "text", text: "E\nMENLO", x: 1360, y: 526, tone: "bright", size: "xl" },
    { id: "iselin", kind: "text", text: "F\nISELIN", x: 1482, y: 530, tone: "bright", size: "xl" },
    { id: "platform-west", kind: "pill", text: "", x: 142, y: 456, tone: "steel", width: 44 },
    { id: "platform-mid", kind: "pill", text: "", x: 520, y: 456, tone: "steel", width: 42 },
    { id: "platform-east", kind: "pill", text: "", x: 1414, y: 456, tone: "steel", width: 42 },
    { id: "platform-south-a", kind: "pill", text: "", x: 520, y: 634, tone: "steel", width: 40 },
    { id: "platform-south-b", kind: "pill", text: "", x: 1412, y: 634, tone: "steel", width: 40 },
  ],
};

const demoLayout = {
  sections: [
    { id: "S1", kind: "track", occupied: false, locked_by: null, length: 100 },
    { id: "S2", kind: "track", occupied: false, locked_by: null, length: 100 },
    { id: "S4", kind: "track", occupied: false, locked_by: null, length: 100 },
    { id: "2", kind: "track", occupied: false, locked_by: null, length: 100 },
    { id: "S7", kind: "track", occupied: false, locked_by: null, length: 100 },
    { id: "S8", kind: "track", occupied: false, locked_by: null, length: 100 },
    { id: "S9", kind: "track", occupied: false, locked_by: null, length: 100 },
    { id: "1", kind: "track", occupied: false, locked_by: null, length: 100 },
    { id: "S10", kind: "track", occupied: false, locked_by: null, length: 100 },
    { id: "S12", kind: "track", occupied: false, locked_by: null, length: 100 },
    { id: "S14", kind: "track", occupied: false, locked_by: null, length: 100 },
    { id: "AS1", kind: "approach", occupied: false, locked_by: null, length: 100 },
    { id: "AS2", kind: "approach", occupied: false, locked_by: null, length: 100 },
  ],
  points: [
    { id: "P2", position: "NORMAL", symbol_orientation: "LEFT", locked_by: null },
    { id: "P1", position: "NORMAL", symbol_orientation: "RIGHT", locked_by: null },
    { id: "P3", position: "NORMAL", symbol_orientation: "UP", locked_by: null },
  ],
  signals: [
    { id: "A", aspect: "STOP", direction: "RIGHT", protects: "S1", approach_section: "AS1", route_id: null },
    { id: "F", aspect: "STOP", direction: "LEFT", protects: "S9", approach_section: "AS2", route_id: null },
    { id: "N2", aspect: "STOP", direction: "LEFT", protects: "S4", approach_section: "", route_id: null },
    { id: "G2", aspect: "STOP", direction: "RIGHT", protects: "S7", approach_section: "", route_id: null },
    { id: "G1", aspect: "STOP", direction: "RIGHT", protects: "S8", approach_section: "", route_id: null },
    { id: "N1", aspect: "STOP", direction: "LEFT", protects: "S10", approach_section: "", route_id: null },
    { id: "Y", aspect: "STOP", direction: "LEFT", protects: "S12", approach_section: "", route_id: null },
  ],
  edges: [
    ["S1", "P1"],
    ["S2", "P2"],
    ["S7", "P3"],
    ["S8", "P3"],
    ["P2", "S4"],
    ["P2", "S14"],
    ["P1", "S2"],
    ["P1", "S10"],
    ["P3", "S9"],
  ],
  signal_links: [
    ["1", "G1"],
    ["1", "N1"],
    ["2", "G2"],
    ["2", "N2"],
    ["AS1", "A"],
    ["AS2", "F"],
    ["S10", "N1"],
    ["S14", "Y"],
  ],
  ui_positions: {
    S1: [-250, -175],
    S2: [-125, -300],
    S4: [50, -400],
    2: [300, -400],
    S7: [575, -400],
    S8: [600, -175],
    S9: [875, -175],
    1: [300, -175],
    S10: [25, -175],
    S12: [-575, -400],
    S14: [-250, -400],
    AS1: [-475, -175],
    AS2: [1025, -175],
    P2: [-125, -400],
    P1: [-125, -175],
    P3: [725, -175],
    A: [-375, -125],
    F: [975, -275],
    N2: [175, -525],
    G2: [450, -275],
    G1: [450, -125],
    N1: [150, -250],
    Y: [-400, -400],
  },
  dispatcher_view: demoDispatcherView,
};

const demoScenarios = [
  {
    name: "Demo Through Route",
    stream_seq: "demo-a",
    routes: [
      {
        id: "R-A-N1",
        entry_signal_id: "A",
        exit_signal_id: "N1",
        full_path: ["S1", "P1", "S10"],
        lifecycle_state: "locked",
        status: "ACTIVE",
      },
    ],
    trains: [{ id: "NJ7817", current_section: "S10", speed: 42.0, route_id: "R-A-N1" }],
    occupiedIds: ["S1", "S10"],
    pointPositions: { P1: "NORMAL", P2: "NORMAL", P3: "NORMAL" },
    signalAspects: { A: "PROCEED", N1: "STOP", F: "STOP", Y: "STOP", G1: "STOP", G2: "STOP", N2: "STOP" },
    alerts: [
      { level: "info", title: "Demo feed", detail: "Fallback topology is active while waiting for Runtime." },
      { level: "info", title: "Route set", detail: "Route A -> N1 is shown as one active mainline movement." },
    ],
  },
  {
    name: "Demo Diverging Route",
    stream_seq: "demo-b",
    routes: [
      {
        id: "R-A-Y",
        entry_signal_id: "A",
        exit_signal_id: "Y",
        full_path: ["S1", "P1", "S2", "P2", "S14"],
        lifecycle_state: "locked",
        status: "ACTIVE",
      },
    ],
    trains: [{ id: "B3-C2", current_section: "S2", speed: 18.0, route_id: "R-A-Y" }],
    occupiedIds: ["S1", "S2", "S14"],
    pointPositions: { P1: "REVERSE", P2: "NORMAL", P3: "NORMAL" },
    signalAspects: { A: "PROCEED", Y: "STOP", F: "STOP", N1: "STOP", G1: "STOP", G2: "STOP", N2: "STOP" },
    alerts: [
      { level: "warn", title: "Diverging move", detail: "Points P1/P2 are aligned for the route toward Y." },
      { level: "info", title: "Occupied blocks", detail: "S1, S2, and S14 are marked occupied in the demo." },
    ],
  },
  {
    name: "Demo Eastbound",
    stream_seq: "demo-c",
    routes: [
      {
        id: "R-F-G1",
        entry_signal_id: "F",
        exit_signal_id: "G1",
        full_path: ["S9", "P3", "S8", "1"],
        lifecycle_state: "running",
        status: "ACTIVE",
      },
    ],
    trains: [{ id: "B2-LN", current_section: "S8", speed: 36.0, route_id: "R-F-G1" }],
    occupiedIds: ["S8", "S9", "1"],
    pointPositions: { P1: "NORMAL", P2: "NORMAL", P3: "REVERSE" },
    signalAspects: { F: "PROCEED", G1: "PROCEED", A: "STOP", N1: "STOP", Y: "STOP", G2: "STOP", N2: "STOP" },
    alerts: [
      { level: "info", title: "Eastbound run", detail: "Route F -> G1 uses the eastern side of the topology." },
      { level: "warn", title: "Stale fallback", detail: "Live data has not arrived yet, so the board stays on demo." },
    ],
  },
];

const state = {
  scenarioIndex: 0,
  showRoutes: true,
  showDebugIds: false,
  debugInitialized: false,
  logs: [],
  runtimeState: null,
  feedStatus: "waiting",
  polling: false,
  lastErrorText: "",
};

function svgElement(name, attrs = {}, textContent = "") {
  const element = document.createElementNS(SVG_NS, name);
  Object.entries(attrs).forEach(([key, value]) => {
    if (value !== undefined && value !== null) {
      element.setAttribute(key, String(value));
    }
  });
  if (textContent) {
    element.textContent = textContent;
  }
  return element;
}

function pushLog(level, title, detail) {
  const current = state.logs[0];
  if (current && current.level === level && current.title === title && current.detail === detail) {
    return;
  }
  state.logs.unshift({ level, title, detail });
  state.logs = state.logs.slice(0, 8);
}

function updateClock() {
  const formatter = new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZone: "Asia/Bangkok",
  });
  clockText.textContent = formatter.format(new Date());
}

function formatTimestamp(unixSeconds) {
  if (!Number.isFinite(unixSeconds) || unixSeconds <= 0) {
    return "--";
  }
  const formatter = new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZone: "Asia/Bangkok",
  });
  return formatter.format(new Date(unixSeconds * 1000));
}

function secondsSince(unixSeconds) {
  if (!Number.isFinite(unixSeconds) || unixSeconds <= 0) {
    return Number.POSITIVE_INFINITY;
  }
  return Math.max(0, (Date.now() - unixSeconds * 1000) / 1000);
}

function isRecord(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function normalizePointReference(value, uiPositions) {
  if (Array.isArray(value) && value.length >= 2) {
    return [Number(value[0]), Number(value[1])];
  }
  if (!isRecord(value)) {
    return null;
  }
  if (value.node_id && Array.isArray(uiPositions?.[value.node_id])) {
    const [x, y] = uiPositions[value.node_id];
    return [Number(x), Number(y)];
  }
  if (Number.isFinite(Number(value.x)) && Number.isFinite(Number(value.y))) {
    return [Number(value.x), Number(value.y)];
  }
  return null;
}

function normalizeDispatcherView(rawView, uiPositions, signals) {
  if (!isRecord(rawView)) {
    return null;
  }

  const segments = Array.isArray(rawView.segments)
    ? rawView.segments
        .filter(isRecord)
        .map((segment, index) => {
          const points = Array.isArray(segment.points)
            ? segment.points.map((point) => normalizePointReference(point, uiPositions)).filter(Boolean)
            : [];
          if (points.length < 2) {
            return null;
          }
          return {
            id: String(segment.id || `segment-${index}`),
            kind: String(segment.kind || "main").trim().toLowerCase() || "main",
            points,
            stateSourceIds: Array.isArray(segment.state_source_ids)
              ? segment.state_source_ids.map((item) => String(item))
              : [],
            showMarkers: segment.show_markers !== false,
            markerSpacing: Number(segment.marker_spacing || TRACK_MARKER_SPACING),
            markerLength: Number(segment.marker_length || TRACK_MARKER_LENGTH),
          };
        })
        .filter(Boolean)
    : [];

  const signalSymbols = Array.isArray(rawView.signal_symbols)
    ? rawView.signal_symbols
        .filter(isRecord)
        .map((symbol) => {
          const signalId = String(symbol.signal_id || "").trim();
          const position = normalizePointReference(symbol, uiPositions);
          if (!signalId || !position) {
            return null;
          }
          const sourceSignal = signals.find((signal) => String(signal.id) === signalId);
          return {
            signalId,
            x: position[0],
            y: position[1],
            direction: String(symbol.direction || sourceSignal?.direction || "RIGHT").toUpperCase(),
            label: String(symbol.label || signalId),
            labelDx: Number(symbol.label_dx || 0),
            labelDy: Number(symbol.label_dy || 0),
          };
        })
        .filter(Boolean)
    : [];

  const annotations = Array.isArray(rawView.annotations)
    ? rawView.annotations
        .filter(isRecord)
        .map((annotation, index) => {
          const position = normalizePointReference(annotation, uiPositions);
          if (!position) {
            return null;
          }
          return {
            id: String(annotation.id || `annotation-${index}`),
            kind: String(annotation.kind || "text").trim().toLowerCase(),
            text: String(annotation.text || ""),
            x: position[0],
            y: position[1],
            tone: String(annotation.tone || "muted").trim().toLowerCase() || "muted",
            align: String(annotation.align || "middle").trim().toLowerCase() || "middle",
            size: String(annotation.size || "md").trim().toLowerCase() || "md",
            width: Number(annotation.width || 0),
          };
        })
        .filter(Boolean)
    : [];

  return {
    segments,
    signalSymbols,
    annotations,
    display: isRecord(rawView.display) ? { ...rawView.display } : {},
  };
}

function normalizeRuntimeState(payload) {
  if (!payload || typeof payload !== "object") {
    return null;
  }
  const layout = payload.layout;
  if (!layout || typeof layout !== "object" || typeof layout.ui_positions !== "object") {
    return null;
  }

  const sections = Array.isArray(layout.sections) ? layout.sections.filter(isRecord) : [];
  const points = Array.isArray(layout.points) ? layout.points.filter(isRecord) : [];
  const signals = Array.isArray(layout.signals) ? layout.signals.filter(isRecord) : [];
  const edges = Array.isArray(layout.edges) ? layout.edges.filter(Array.isArray) : [];
  const signalLinks = Array.isArray(layout.signal_links) ? layout.signal_links.filter(Array.isArray) : [];
  const occupancy = Array.isArray(payload.occupancy) ? payload.occupancy.filter(isRecord) : [];
  const occupancyById = new Map();
  occupancy.forEach((item) => {
    occupancyById.set(String(item.id || ""), item);
  });
  sections.forEach((section) => {
    if (!occupancyById.has(String(section.id))) {
      occupancyById.set(String(section.id), section);
    }
  });
  points.forEach((point) => {
    if (!occupancyById.has(String(point.id))) {
      occupancyById.set(String(point.id), point);
    }
  });

  const signalStateSource = Array.isArray(payload.signal_state) ? payload.signal_state.filter(isRecord) : [];
  const signalStateById = new Map();
  signalStateSource.forEach((item) => {
    signalStateById.set(String(item.id || ""), item);
  });
  const signalState = signals.map((signal) => {
    const current = signalStateById.get(String(signal.id || ""));
    const normalized = {
      id: String(signal.id || ""),
      aspect: String(current?.aspect || signal.aspect || "STOP").toUpperCase(),
      route_id: current?.route_id ?? signal.route_id ?? null,
      direction: String(signal.direction || "RIGHT").toUpperCase(),
    };
    signalStateById.set(normalized.id, normalized);
    return normalized;
  });

  const routes = Array.isArray(payload.routes) ? payload.routes.filter(isRecord) : [];
  const trains = Array.isArray(payload.trains) ? payload.trains.filter(isRecord) : [];
  const generatedAt = Number(payload.generated_at ?? 0);
  const streamSeq = payload.stream_seq ?? payload.streamSeq ?? "demo";
  const workspaceMode = String(payload.workspace_mode || "runtime").trim().toLowerCase() || "runtime";
  const topologyRevision = String(payload.topology_revision || "").trim();
  const dispatcherView = normalizeDispatcherView(layout.dispatcher_view, layout.ui_positions, signals);

  return {
    name: String(payload.display_name || ""),
    layout: {
      sections,
      points,
      signals,
      edges,
      signalLinks,
      uiPositions: layout.ui_positions,
      dispatcherView,
    },
    routes,
    trains,
    occupancy,
    occupancyById,
    signalState,
    signalStateById,
    generatedAt,
    streamSeq,
    workspaceMode,
    topologyRevision,
    occupiedCount: Array.from(occupancyById.values()).filter((item) => item?.occupied).length,
    alerts: Array.isArray(payload.alerts) ? payload.alerts.filter(isRecord) : [],
  };
}

function buildDemoRuntimeState(index) {
  const scenario = demoScenarios[index];
  const sectionOccupancy = demoLayout.sections.map((section) => ({
    id: section.id,
    occupied: scenario.occupiedIds.includes(section.id),
    locked_by: scenario.routes[0]?.id || null,
  }));
  const pointOccupancy = demoLayout.points.map((point) => ({
    id: point.id,
    position: scenario.pointPositions[point.id] || point.position || "NORMAL",
    locked_by: scenario.routes[0]?.id || null,
  }));
  const signalState = demoLayout.signals.map((signal) => ({
    id: signal.id,
    aspect: scenario.signalAspects[signal.id] || "STOP",
    route_id: scenario.routes.find((route) => route.entry_signal_id === signal.id)?.id || null,
  }));
  return normalizeRuntimeState({
    display_name: scenario.name,
    layout: demoLayout,
    routes: scenario.routes,
    trains: scenario.trains,
    occupancy: [...sectionOccupancy, ...pointOccupancy],
    signal_state: signalState,
    stream_seq: scenario.stream_seq,
    workspace_mode: "demo",
    topology_revision: "demo-layout",
    generated_at: 0,
    alerts: scenario.alerts,
  });
}

function currentBoardState() {
  return state.runtimeState || buildDemoRuntimeState(state.scenarioIndex);
}

function boardHasLiveData() {
  return Boolean(state.runtimeState);
}

function ensureDebugModeDefault(boardState) {
  if (state.debugInitialized) {
    return;
  }
  const defaultFlag = Boolean(boardState.layout.dispatcherView?.display?.show_debug_ids_default);
  state.showDebugIds = defaultFlag;
  state.debugInitialized = true;
}

function updateFeedPresentation() {
  const boardState = currentBoardState();
  const live = boardHasLiveData();
  const ageSeconds = live ? secondsSince(boardState.generatedAt) : null;
  const isStale = live && ageSeconds * 1000 > STALE_AFTER_MS;

  if (!live) {
    connectionPill.textContent = state.feedStatus === "error" ? "RUNTIME ERROR" : "WAITING RUNTIME";
    connectionPill.className = `status-pill ${state.feedStatus === "error" ? "error" : "waiting"}`;
    transportHint.textContent =
      state.feedStatus === "error"
        ? `Runtime feed error. ${state.lastErrorText || "Waiting for the next successful poll."}`
        : "Polling /api/runtime-state every 1s. Demo board stays visible until Runtime writes one live payload.";
    workspaceModeText.textContent = "demo";
    updatedAtText.textContent = "--";
    return;
  }

  connectionPill.textContent = isStale ? "STALE SNAPSHOT" : "RUNTIME LIVE";
  connectionPill.className = `status-pill ${isStale ? "stale" : "connected"}`;
  transportHint.textContent = isStale
    ? `No fresh runtime update for ${ageSeconds.toFixed(1)}s. Showing the last good snapshot from Runtime.`
    : `Polling /api/runtime-state every 1s. Last runtime payload age ${ageSeconds.toFixed(1)}s.`;
  workspaceModeText.textContent = boardState.workspaceMode;
  updatedAtText.textContent = formatTimestamp(boardState.generatedAt);
}

function renderAll() {
  const boardState = currentBoardState();
  ensureDebugModeDefault(boardState);
  updateFeedPresentation();
  renderBoard(boardState);
  renderSidebar(boardState);
}

function computeBounds(positions) {
  const values = Object.values(positions).filter(Array.isArray);
  const xs = values.map((value) => Number(value[0]));
  const ys = values.map((value) => Number(value[1]));
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  return { minX, minY, width: Math.max(1, maxX - minX), height: Math.max(1, maxY - minY) };
}

function positionFor(positions, nodeId) {
  const value = positions?.[nodeId];
  if (!Array.isArray(value) || value.length < 2) {
    return null;
  }
  return [Number(value[0]), Number(value[1])];
}

function dedupeAdjacent(points) {
  return points.filter((point, index) => {
    if (index === 0) {
      return true;
    }
    const previous = points[index - 1];
    return previous[0] !== point[0] || previous[1] !== point[1];
  });
}

function asNodeList(fullPath, path, overlapPath) {
  if (Array.isArray(fullPath) && fullPath.length) {
    return fullPath.map((item) => String(item));
  }
  const result = [];
  if (Array.isArray(path)) {
    result.push(...path.map((item) => String(item)));
  }
  if (Array.isArray(overlapPath)) {
    result.push(...overlapPath.map((item) => String(item)));
  }
  return result;
}

function signalStemGeometry(direction, [x, y]) {
  const token = String(direction || "").toUpperCase();
  if (token === "LEFT") {
    return { x1: x + 7, y1: y, x2: x + 20, y2: y };
  }
  if (token === "UP") {
    return { x1: x, y1: y + 7, x2: x, y2: y + 20 };
  }
  if (token === "DOWN") {
    return { x1: x, y1: y - 7, x2: x, y2: y - 20 };
  }
  return { x1: x - 20, y1: y, x2: x - 7, y2: y };
}

function signalAspectClass(aspect) {
  const token = String(aspect || "").toUpperCase();
  if (!token || token === "STOP") {
    return "red";
  }
  if (token.includes("YELLOW") || token.includes("CAUTION")) {
    return "amber";
  }
  return "green";
}

function shortAspect(aspect) {
  const token = String(aspect || "").toUpperCase();
  if (!token) {
    return "STOP";
  }
  if (token === "PROCEED") {
    return "GO";
  }
  return token;
}

function normalizeVector(dx, dy) {
  const length = Math.hypot(dx, dy);
  if (!length) {
    return null;
  }
  return [dx / length, dy / length];
}

function scaleVector(vector, distance) {
  return [vector[0] * distance, vector[1] * distance];
}

function addUndirectedEdge(neighborMap, sourceId, targetId) {
  if (!neighborMap.has(sourceId)) {
    neighborMap.set(sourceId, new Set());
  }
  neighborMap.get(sourceId).add(targetId);
}

function buildNeighborMap(layout) {
  const neighborMap = new Map();
  layout.edges.forEach(([sourceId, targetId]) => {
    addUndirectedEdge(neighborMap, String(sourceId), String(targetId));
    addUndirectedEdge(neighborMap, String(targetId), String(sourceId));
  });
  return neighborMap;
}

function candidateVectorsForNode(nodeId, neighborMap, positions) {
  const center = positionFor(positions, nodeId);
  if (!center) {
    return [];
  }
  return Array.from(neighborMap.get(String(nodeId)) || [])
    .map((neighborId) => {
      const target = positionFor(positions, neighborId);
      if (!target) {
        return null;
      }
      const vector = normalizeVector(target[0] - center[0], target[1] - center[1]);
      if (!vector) {
        return null;
      }
      return {
        neighborId,
        target,
        vector,
        distance: distanceBetween(center, target),
      };
    })
    .filter(Boolean);
}

function pickOpposingPair(candidates) {
  if (candidates.length < 2) {
    return null;
  }
  let bestPair = null;
  let bestScore = Number.POSITIVE_INFINITY;
  for (let index = 0; index < candidates.length - 1; index += 1) {
    for (let next = index + 1; next < candidates.length; next += 1) {
      const first = candidates[index];
      const second = candidates[next];
      const score = first.vector[0] * second.vector[0] + first.vector[1] * second.vector[1];
      if (score < bestScore) {
        bestScore = score;
        bestPair = [first, second];
      }
    }
  }
  return bestPair;
}

function inferSectionStroke(sectionId, neighborMap, positions) {
  const center = positionFor(positions, sectionId);
  if (!center) {
    return null;
  }
  const candidates = candidateVectorsForNode(sectionId, neighborMap, positions);
  if (!candidates.length) {
    return null;
  }

  if (candidates.length === 1) {
    const candidate = candidates[0];
    const reach = Math.min(34, Math.max(16, candidate.distance * 0.42));
    const [dx, dy] = scaleVector(candidate.vector, reach);
    return {
      x1: center[0] - dx,
      y1: center[1] - dy,
      x2: center[0] + dx,
      y2: center[1] + dy,
    };
  }

  const pair = pickOpposingPair(candidates);
  if (!pair) {
    return null;
  }
  const [left, right] = pair;
  const leftReach = Math.min(34, Math.max(16, left.distance * 0.44));
  const rightReach = Math.min(34, Math.max(16, right.distance * 0.44));
  const [leftDx, leftDy] = scaleVector(left.vector, leftReach);
  const [rightDx, rightDy] = scaleVector(right.vector, rightReach);
  return {
    x1: center[0] + leftDx,
    y1: center[1] + leftDy,
    x2: center[0] + rightDx,
    y2: center[1] + rightDy,
  };
}

function renderTopologySection(layer, section, boardState, neighborMap) {
  const stroke = inferSectionStroke(section.id, neighborMap, boardState.layout.uiPositions);
  if (!stroke) {
    return;
  }
  const runtimeSection = boardState.occupancyById.get(String(section.id)) || section;
  const occupied = Boolean(runtimeSection.occupied);
  const locked = Boolean(runtimeSection.locked_by);
  const classNames = ["topology-section"];
  if (occupied) {
    classNames.push("occupied");
  }
  if (locked) {
    classNames.push("locked");
  }
  layer.appendChild(svgElement("line", { ...stroke, class: classNames.join(" ") }));

  if (state.showDebugIds) {
    layer.appendChild(
      svgElement(
        "text",
        {
          x: (stroke.x1 + stroke.x2) / 2,
          y: (stroke.y1 + stroke.y2) / 2 - 11,
          class: "debug-label",
          "text-anchor": "middle",
        },
        section.id,
      ),
    );
  }
}

function bladeEndpoint(center, target, factor = 0.42, minDistance = 22, maxDistance = 34) {
  const vector = normalizeVector(target[0] - center[0], target[1] - center[1]);
  if (!vector) {
    return null;
  }
  const distance = distanceBetween(center, target);
  const reach = Math.min(maxDistance, Math.max(minDistance, distance * factor));
  const [dx, dy] = scaleVector(vector, reach);
  return [center[0] + dx, center[1] + dy];
}

function renderTopologyPoint(layer, point, boardState, neighborMap) {
  const center = positionFor(boardState.layout.uiPositions, point.id);
  if (!center) {
    return;
  }
  const neighborIds = Array.from(neighborMap.get(String(point.id)) || []);
  const branchTargets = {
    NORMAL: point.facing_connections?.NORMAL ? positionFor(boardState.layout.uiPositions, point.facing_connections.NORMAL) : null,
    REVERSE: point.facing_connections?.REVERSE ? positionFor(boardState.layout.uiPositions, point.facing_connections.REVERSE) : null,
  };
  const branchIds = new Set(
    Object.values(point.facing_connections || {})
      .filter(Boolean)
      .map((item) => String(item)),
  );
  const trunkId = neighborIds.find((neighborId) => !branchIds.has(String(neighborId)));
  const trunkTarget = trunkId ? positionFor(boardState.layout.uiPositions, trunkId) : null;
  const runtimePoint = boardState.occupancyById.get(String(point.id)) || point;
  const currentPosition = String(runtimePoint.position || point.position || "NORMAL").toUpperCase().startsWith("R") ? "REVERSE" : "NORMAL";
  const locked = Boolean(runtimePoint.locked_by);

  if (trunkTarget) {
    const trunkEnd = bladeEndpoint(center, trunkTarget, 0.4, 20, 30);
    if (trunkEnd) {
      layer.appendChild(svgElement("line", { x1: center[0], y1: center[1], x2: trunkEnd[0], y2: trunkEnd[1], class: "topology-point-stock" }));
    }
  }

  ["NORMAL", "REVERSE"].forEach((positionToken) => {
    const branchTarget = branchTargets[positionToken];
    if (!branchTarget) {
      return;
    }
    const branchEnd = bladeEndpoint(center, branchTarget);
    if (!branchEnd) {
      return;
    }
    const classNames = ["topology-point-blade"];
    if (positionToken === currentPosition) {
      classNames.push("active");
    } else {
      classNames.push("inactive");
    }
    if (locked) {
      classNames.push("locked");
    }
    layer.appendChild(svgElement("line", { x1: center[0], y1: center[1], x2: branchEnd[0], y2: branchEnd[1], class: classNames.join(" ") }));
  });

  layer.appendChild(svgElement("circle", { cx: center[0], cy: center[1], r: 3.3, class: `topology-point-core${locked ? " locked" : ""}` }));

  if (state.showDebugIds) {
    layer.appendChild(svgElement("text", { x: center[0], y: center[1] - 12, class: "debug-label", "text-anchor": "middle" }, point.id));
  }
}

function renderTopologySignalLinks(layer, boardState) {
  boardState.layout.signalLinks.forEach(([sourceId, signalId]) => {
    const source = positionFor(boardState.layout.uiPositions, sourceId);
    const signal = positionFor(boardState.layout.uiPositions, signalId);
    if (!source || !signal) {
      return;
    }
    layer.appendChild(svgElement("line", { x1: source[0], y1: source[1], x2: signal[0], y2: signal[1], class: "topology-signal-link" }));
  });
}

function renderTopologySignals(layer, boardState) {
  boardState.signalState.forEach((signal) => {
    const position = positionFor(boardState.layout.uiPositions, signal.id);
    if (!position) {
      return;
    }
    const geometry = signalStemGeometry(signal.direction, position);
    layer.appendChild(svgElement("line", { ...geometry, class: "dispatcher-signal-stub" }));
    layer.appendChild(svgElement("circle", { cx: position[0], cy: position[1], r: 6.6, class: `dispatcher-signal-head ${signalAspectClass(signal.aspect)}` }));
    if (state.showDebugIds) {
      layer.appendChild(
        svgElement(
          "text",
          {
            x: position[0] + (String(signal.direction).toUpperCase() === "LEFT" ? 20 : -20),
            y: position[1] - 10,
            class: "debug-label",
            "text-anchor": String(signal.direction).toUpperCase() === "LEFT" ? "start" : "end",
          },
          signal.id,
        ),
      );
    }
  });
}

function renderTopologyRoutes(layer, boardState) {
  if (!state.showRoutes) {
    return;
  }
  boardState.routes.forEach((route) => {
    const nodeOrder = [route.entry_signal_id, ...asNodeList(route.full_path, route.path, route.overlap_path), route.exit_signal_id];
    const points = dedupeAdjacent(nodeOrder.map((nodeId) => positionFor(boardState.layout.uiPositions, nodeId)).filter(Boolean));
    if (points.length < 2) {
      return;
    }
    layer.appendChild(svgElement("polyline", { points: polylinePoints(points), class: "dispatcher-route" }));
    const [labelX, labelY] = polylineMidpoint(points);
    const label = String(route.id || "route");
    const width = Math.max(46, label.length * 8 + 20);
    const group = svgElement("g", { class: "dispatcher-route-tag", transform: `translate(${labelX}, ${labelY - 22})` });
    group.appendChild(svgElement("rect", { x: -width / 2, y: -11, width, height: 20, rx: 6 }));
    group.appendChild(svgElement("text", { x: 0, y: 4, "text-anchor": "middle" }, label));
    layer.appendChild(group);
  });
}

function renderTopologyTrains(layer, boardState) {
  boardState.trains.forEach((train) => {
    const position = positionFor(boardState.layout.uiPositions, train.current_section);
    if (!position) {
      return;
    }
    const label = String(train.id || "TRAIN");
    const width = Math.max(56, label.length * 8 + 18);
    const group = svgElement("g", { class: "dispatcher-train", transform: `translate(${position[0]}, ${position[1] - 24})` });
    group.appendChild(svgElement("rect", { x: -width / 2, y: -12, width, height: 20, rx: 5 }));
    group.appendChild(svgElement("text", { x: 0, y: 3, "text-anchor": "middle" }, label));
    layer.appendChild(group);
  });
}

function renderTopologyBoard(boardState) {
  const positions = boardState.layout?.uiPositions ?? {};
  const nodeIds = Object.keys(positions);
  board.replaceChildren();
  if (!nodeIds.length) {
    board.setAttribute("viewBox", "0 0 1200 800");
    board.appendChild(svgElement("text", { x: 600, y: 400, class: "board-empty" }, "No layout data"));
    return;
  }

  const bounds = computeBounds(positions);
  board.setAttribute("viewBox", `${bounds.minX - 140} ${bounds.minY - 140} ${bounds.width + 280} ${bounds.height + 280}`);

  const neighborMap = buildNeighborMap(boardState.layout);
  const root = svgElement("g", { class: "dispatcher-root topology-root" });
  const trackLayer = svgElement("g");
  const trackMarkerLayer = svgElement("g");
  const sectionLayer = svgElement("g");
  const routeLayer = svgElement("g");
  const signalLinkLayer = svgElement("g");
  const pointLayer = svgElement("g");
  const signalLayer = svgElement("g");
  const trainLayer = svgElement("g");

  boardState.layout.edges.forEach(([fromId, toId]) => {
    const from = positionFor(positions, fromId);
    const to = positionFor(positions, toId);
    if (!from || !to) {
      return;
    }
    const points = [from, to];
    trackLayer.appendChild(svgElement("polyline", { points: polylinePoints(points), class: "dispatcher-track kind-main" }));
    buildTrackMarkers(points, TRACK_MARKER_SPACING, TRACK_MARKER_LENGTH).forEach((marker) => {
      trackMarkerLayer.appendChild(svgElement("line", { ...marker, class: "dispatcher-track-marker" }));
    });
  });

  boardState.layout.sections.forEach((section) => renderTopologySection(sectionLayer, section, boardState, neighborMap));
  renderTopologyRoutes(routeLayer, boardState);
  renderTopologySignalLinks(signalLinkLayer, boardState);
  boardState.layout.points.forEach((point) => renderTopologyPoint(pointLayer, point, boardState, neighborMap));
  renderTopologySignals(signalLayer, boardState);
  renderTopologyTrains(trainLayer, boardState);

  root.append(trackLayer, trackMarkerLayer, sectionLayer, routeLayer, signalLinkLayer, pointLayer, signalLayer, trainLayer);
  board.appendChild(root);
}

function distanceBetween(from, to) {
  return Math.hypot(to[0] - from[0], to[1] - from[1]);
}

function polylineLength(points) {
  let total = 0;
  for (let index = 1; index < points.length; index += 1) {
    total += distanceBetween(points[index - 1], points[index]);
  }
  return total;
}

function pointAndNormalAtDistance(points, distance) {
  let remaining = distance;
  for (let index = 1; index < points.length; index += 1) {
    const from = points[index - 1];
    const to = points[index];
    const segmentLength = distanceBetween(from, to);
    if (segmentLength <= 0) {
      continue;
    }
    if (remaining <= segmentLength || index === points.length - 1) {
      const ratio = Math.max(0, Math.min(1, remaining / segmentLength));
      const x = from[0] + (to[0] - from[0]) * ratio;
      const y = from[1] + (to[1] - from[1]) * ratio;
      const dx = to[0] - from[0];
      const dy = to[1] - from[1];
      const length = Math.max(1, Math.hypot(dx, dy));
      return {
        point: [x, y],
        normal: [-dy / length, dx / length],
      };
    }
    remaining -= segmentLength;
  }
  return {
    point: points[points.length - 1],
    normal: [0, -1],
  };
}

function polylineMidpoint(points) {
  const total = polylineLength(points);
  if (!total) {
    return points[0];
  }
  return pointAndNormalAtDistance(points, total / 2).point;
}

function buildTrackMarkers(points, spacing, length) {
  const total = polylineLength(points);
  if (total < spacing * 1.4) {
    return [];
  }
  const markers = [];
  for (let distance = spacing; distance < total - spacing * 0.4; distance += spacing) {
    const { point, normal } = pointAndNormalAtDistance(points, distance);
    markers.push({
      x1: point[0] - normal[0] * (length / 2),
      y1: point[1] - normal[1] * (length / 2),
      x2: point[0] + normal[0] * (length / 2),
      y2: point[1] + normal[1] * (length / 2),
    });
  }
  return markers;
}

function polylinePoints(points) {
  return points.map(([x, y]) => `${x},${y}`).join(" ");
}

function routeNodes(route) {
  return new Set(
    [route.entry_signal_id, ...asNodeList(route.full_path, route.path, route.overlap_path), route.exit_signal_id]
      .filter(Boolean)
      .map((item) => String(item)),
  );
}

function segmentMatchesRoute(segment, route) {
  const nodes = routeNodes(route);
  return segment.stateSourceIds.some((id) => nodes.has(String(id)));
}

function dispatcherSegmentState(segment, boardState) {
  const occupied = segment.stateSourceIds.some((id) => Boolean(boardState.occupancyById.get(id)?.occupied));
  const locked = segment.stateSourceIds.some((id) => Boolean(boardState.occupancyById.get(id)?.locked_by));
  const activeRouteIds = boardState.routes.filter((route) => segmentMatchesRoute(segment, route)).map((route) => route.id || "route");
  return {
    occupied,
    locked,
    active: activeRouteIds.length > 0,
    activeRouteIds,
  };
}

function annotationAnchor(align) {
  if (align === "start" || align === "left") {
    return "start";
  }
  if (align === "end" || align === "right") {
    return "end";
  }
  return "middle";
}

function renderAnnotation(layer, annotation) {
  const tone = annotation.tone || "muted";
  const size = annotation.size || "md";

  if (annotation.kind === "pill" || annotation.kind === "chip") {
    const text = annotation.text || "";
    const width = annotation.width || Math.max(32, text.length * 8 + 26);
    const height = annotation.kind === "chip" ? 24 : 18;
    const group = svgElement("g", {
      class: `dispatcher-pill tone-${tone} kind-${annotation.kind}`,
      transform: `translate(${annotation.x}, ${annotation.y})`,
    });
    group.appendChild(svgElement("rect", { x: -width / 2, y: -height / 2, width, height, rx: height / 2 }));
    if (text) {
      group.appendChild(
        svgElement(
          "text",
          {
            x: 0,
            y: 4,
            class: `dispatcher-pill-text tone-${tone} size-${size}`,
            "text-anchor": "middle",
          },
          text,
        ),
      );
    }
    layer.appendChild(group);
    return;
  }

  const text = svgElement("text", {
    x: annotation.x,
    y: annotation.y,
    class: `dispatcher-annotation tone-${tone} size-${size}`,
    "text-anchor": annotationAnchor(annotation.align),
  });
  const lines = String(annotation.text || "").split("\n");
  const fontSize = ANNOTATION_SIZES[size] || ANNOTATION_SIZES.md;
  lines.forEach((line, index) => {
    const span = svgElement("tspan", { x: annotation.x, dy: index === 0 ? 0 : fontSize * 0.95 }, line);
    text.appendChild(span);
  });
  layer.appendChild(text);
}

function renderSignalSymbol(layer, symbol, boardState) {
  const current = boardState.signalStateById.get(symbol.signalId) || { aspect: "STOP", direction: symbol.direction };
  const direction = String(symbol.direction || current.direction || "RIGHT").toUpperCase();
  const group = svgElement("g", { class: "dispatcher-signal", transform: `translate(${symbol.x}, ${symbol.y})` });
  let stub;
  if (direction === "LEFT") {
    stub = { x1: 18, y1: 0, x2: 6, y2: 0 };
  } else {
    stub = { x1: -18, y1: 0, x2: -6, y2: 0 };
  }
  group.appendChild(svgElement("line", { ...stub, class: "dispatcher-signal-stub" }));
  group.appendChild(svgElement("circle", { cx: 0, cy: 0, r: 6.8, class: `dispatcher-signal-head ${signalAspectClass(current.aspect)}` }));
  if (state.showDebugIds) {
    group.appendChild(
      svgElement(
        "text",
        {
          x: symbol.labelDx || (direction === "LEFT" ? 26 : -26),
          y: (symbol.labelDy || -10),
          class: "debug-label debug-signal",
          "text-anchor": direction === "LEFT" ? "start" : "end",
        },
        symbol.label,
      ),
    );
  }
  layer.appendChild(group);
}

function dispatcherBounds(dispatcherView) {
  const positions = [];
  dispatcherView.segments.forEach((segment) => positions.push(...segment.points));
  dispatcherView.signalSymbols.forEach((symbol) => positions.push([symbol.x, symbol.y]));
  dispatcherView.annotations.forEach((annotation) => positions.push([annotation.x, annotation.y]));
  const xs = positions.map((item) => item[0]);
  const ys = positions.map((item) => item[1]);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  return { minX, minY, width: Math.max(1, maxX - minX), height: Math.max(1, maxY - minY) };
}

function renderDispatcherRouteTags(layer, boardState, dispatcherView) {
  if (!state.showRoutes) {
    return;
  }
  boardState.routes.forEach((route) => {
    const matchedSegments = dispatcherView.segments.filter((segment) => segmentMatchesRoute(segment, route));
    if (!matchedSegments.length) {
      return;
    }
    const anchorSegment = matchedSegments[Math.floor(matchedSegments.length / 2)];
    const [x, y] = polylineMidpoint(anchorSegment.points);
    const label = String(route.id || "route");
    const width = Math.max(44, label.length * 8 + 18);
    const group = svgElement("g", {
      class: "dispatcher-route-tag",
      transform: `translate(${x}, ${y - 22})`,
    });
    group.appendChild(svgElement("rect", { x: -width / 2, y: -11, width, height: 20, rx: 6 }));
    group.appendChild(svgElement("text", { x: 0, y: 4, "text-anchor": "middle" }, label));
    layer.appendChild(group);
  });
}

function trainAnchor(train, boardState, dispatcherView) {
  const sectionId = String(train.current_section || "");
  const preferredSegment = dispatcherView.segments.find((segment) => segment.stateSourceIds.includes(sectionId));
  if (preferredSegment) {
    return polylineMidpoint(preferredSegment.points);
  }
  return positionFor(boardState.layout.uiPositions, sectionId);
}

function renderDispatcherDebug(layer, boardState, dispatcherView) {
  if (!state.showDebugIds) {
    return;
  }
  dispatcherView.segments.forEach((segment) => {
    if (!segment.stateSourceIds.length) {
      return;
    }
    const [x, y] = polylineMidpoint(segment.points);
    layer.appendChild(
      svgElement(
        "text",
        {
          x,
          y: y - 10,
          class: "debug-label",
          "text-anchor": "middle",
        },
        segment.stateSourceIds.join("/"),
      ),
    );
  });
}

function renderDispatcherBoard(boardState) {
  const dispatcherView = boardState.layout.dispatcherView;
  const bounds = dispatcherBounds(dispatcherView);
  board.replaceChildren();
  board.setAttribute("viewBox", `${bounds.minX - 80} ${bounds.minY - 80} ${bounds.width + 160} ${bounds.height + 160}`);

  const root = svgElement("g", { class: "dispatcher-root" });
  const baseLayer = svgElement("g");
  const markerLayer = svgElement("g");
  const stateLayer = svgElement("g");
  const routeLayer = svgElement("g");
  const annotationLayer = svgElement("g");
  const signalLayer = svgElement("g");
  const trainLayer = svgElement("g");
  const debugLayer = svgElement("g");

  dispatcherView.segments.forEach((segment) => {
    const baseLine = svgElement("polyline", {
      points: polylinePoints(segment.points),
      class: `dispatcher-track kind-${segment.kind}`,
    });
    baseLayer.appendChild(baseLine);
    if (segment.showMarkers) {
      buildTrackMarkers(segment.points, segment.markerSpacing, segment.markerLength).forEach((marker) => {
        markerLayer.appendChild(svgElement("line", { ...marker, class: "dispatcher-track-marker" }));
      });
    }
  });

  dispatcherView.segments.forEach((segment) => {
    const segmentState = dispatcherSegmentState(segment, boardState);
    if (segmentState.occupied) {
      stateLayer.appendChild(
        svgElement("polyline", {
          points: polylinePoints(segment.points),
          class: "dispatcher-overlay occupied",
        }),
      );
    }
    if (segmentState.locked) {
      stateLayer.appendChild(
        svgElement("polyline", {
          points: polylinePoints(segment.points),
          class: "dispatcher-overlay locked",
        }),
      );
    }
    if (segmentState.active && state.showRoutes) {
      routeLayer.appendChild(
        svgElement("polyline", {
          points: polylinePoints(segment.points),
          class: "dispatcher-route",
        }),
      );
    }
  });

  dispatcherView.annotations.forEach((annotation) => renderAnnotation(annotationLayer, annotation));
  renderDispatcherRouteTags(annotationLayer, boardState, dispatcherView);
  dispatcherView.signalSymbols.forEach((symbol) => renderSignalSymbol(signalLayer, symbol, boardState));

  boardState.trains.forEach((train) => {
    const anchor = trainAnchor(train, boardState, dispatcherView);
    if (!anchor) {
      return;
    }
    const label = String(train.id || "TRAIN");
    const width = Math.max(56, label.length * 8 + 18);
    const group = svgElement("g", { class: "dispatcher-train", transform: `translate(${anchor[0]}, ${anchor[1] - 2})` });
    group.appendChild(svgElement("rect", { x: -width / 2, y: -12, width, height: 20, rx: 5 }));
    group.appendChild(svgElement("text", { x: 0, y: 3, "text-anchor": "middle" }, label));
    trainLayer.appendChild(group);
  });

  renderDispatcherDebug(debugLayer, boardState, dispatcherView);

  root.append(baseLayer, markerLayer, stateLayer, routeLayer, annotationLayer, signalLayer, trainLayer, debugLayer);
  board.appendChild(root);
}

function renderLegacyBoard(boardState) {
  const layout = boardState.layout;
  const positions = layout?.uiPositions ?? {};
  const nodeIds = Object.keys(positions);

  board.replaceChildren();
  if (!nodeIds.length) {
    board.setAttribute("viewBox", "0 0 1200 800");
    board.appendChild(svgElement("text", { x: 600, y: 400, class: "board-empty" }, "No layout data"));
    return;
  }

  const bounds = computeBounds(positions);
  board.setAttribute("viewBox", `${bounds.minX - 120} ${bounds.minY - 120} ${bounds.width + 240} ${bounds.height + 240}`);

  const root = svgElement("g");
  const trackLayer = svgElement("g");
  const signalLinkLayer = svgElement("g");
  const routeLayer = svgElement("g");
  const sectionLayer = svgElement("g");
  const pointLayer = svgElement("g");
  const signalLayer = svgElement("g");
  const trainLayer = svgElement("g");

  layout.edges.forEach((edge) => {
    const [fromId, toId] = edge;
    const from = positionFor(positions, fromId);
    const to = positionFor(positions, toId);
    if (!from || !to) {
      return;
    }
    trackLayer.appendChild(svgElement("line", { x1: from[0], y1: from[1], x2: to[0], y2: to[1], class: "track-edge" }));
  });

  layout.signalLinks.forEach((edge) => {
    const [fromId, toId] = edge;
    const from = positionFor(positions, fromId);
    const to = positionFor(positions, toId);
    if (!from || !to) {
      return;
    }
    signalLinkLayer.appendChild(svgElement("line", { x1: from[0], y1: from[1], x2: to[0], y2: to[1], class: "signal-link" }));
  });

  if (state.showRoutes) {
    boardState.routes.forEach((route) => {
      const nodeOrder = [route.entry_signal_id, ...asNodeList(route.full_path, route.path, route.overlap_path), route.exit_signal_id];
      const points = dedupeAdjacent(nodeOrder.map((nodeId) => positionFor(positions, nodeId)).filter(Boolean));
      if (points.length < 2) {
        return;
      }
      routeLayer.appendChild(svgElement("polyline", { points: polylinePoints(points), class: "route-line green" }));
      const midpoint = points[Math.floor(points.length / 2)];
      routeLayer.appendChild(svgElement("text", { x: midpoint[0], y: midpoint[1] - 16, class: "route-caption" }, route.id || "route"));
    });
  }

  layout.sections.forEach((section) => {
    const position = positionFor(positions, section.id);
    if (!position) {
      return;
    }
    const runtimeSection = boardState.occupancyById.get(section.id) || section;
    const occupied = Boolean(runtimeSection.occupied);
    const locked = Boolean(runtimeSection.locked_by);
    sectionLayer.appendChild(
      svgElement("rect", {
        x: position[0] - 34,
        y: position[1] - 12,
        width: 68,
        height: 24,
        rx: 8,
        class: `section-node${occupied ? " occupied" : ""}${locked ? " locked" : ""}`,
      }),
    );
    sectionLayer.appendChild(svgElement("text", { x: position[0], y: position[1] + 5, class: "section-label" }, section.id));
  });

  layout.points.forEach((point) => {
    const position = positionFor(positions, point.id);
    if (!position) {
      return;
    }
    const runtimePoint = boardState.occupancyById.get(point.id) || point;
    const positionToken = String(runtimePoint.position || point.position || "NORMAL").toUpperCase().startsWith("R") ? "R" : "N";
    const locked = Boolean(runtimePoint.locked_by);
    pointLayer.appendChild(svgElement("circle", { cx: position[0], cy: position[1], r: 14, class: `point-node${locked ? " locked" : ""}` }));
    pointLayer.appendChild(svgElement("text", { x: position[0], y: position[1] + 4, class: "point-token" }, positionToken));
    pointLayer.appendChild(svgElement("text", { x: position[0], y: position[1] + 28, class: "point-label" }, point.id));
  });

  boardState.signalState.forEach((signal) => {
    const position = positionFor(positions, signal.id);
    if (!position) {
      return;
    }
    const geometry = signalStemGeometry(signal.direction, position);
    signalLayer.appendChild(svgElement("line", { ...geometry, class: "signal-stem" }));
    signalLayer.appendChild(svgElement("circle", { cx: position[0], cy: position[1], r: 6.5, class: `signal-head ${signalAspectClass(signal.aspect)}` }));
    signalLayer.appendChild(svgElement("text", { x: position[0] + 10, y: position[1] - 10, class: "signal-label" }, `${signal.id} ${shortAspect(signal.aspect)}`));
  });

  boardState.trains.forEach((train) => {
    const position = positionFor(positions, train.current_section);
    if (!position) {
      return;
    }
    const chip = svgElement("g", { class: "train-chip", transform: `translate(${position[0]}, ${position[1] - 28})` });
    chip.appendChild(svgElement("rect", { x: -28, y: -10, width: 64, height: 20, rx: 4 }));
    chip.appendChild(svgElement("text", { x: 4, y: 4, "text-anchor": "middle" }, train.id || "TRAIN"));
    trainLayer.appendChild(chip);
  });

  root.append(trackLayer, signalLinkLayer, routeLayer, sectionLayer, pointLayer, signalLayer, trainLayer);
  board.appendChild(root);
}

function renderBoard(boardState) {
  renderTopologyBoard(boardState);
}

function buildEmptyListItem(title, detail) {
  const item = document.createElement("li");
  const head = document.createElement("div");
  head.className = "route-item-head";
  const titleNode = document.createElement("span");
  titleNode.className = "route-item-title";
  titleNode.textContent = title;
  head.appendChild(titleNode);
  const copy = document.createElement("span");
  copy.className = "route-item-copy";
  copy.textContent = detail;
  item.append(head, copy);
  return item;
}

function renderSidebar(boardState) {
  const live = boardHasLiveData();
  const isStale = live && secondsSince(boardState.generatedAt) * 1000 > STALE_AFTER_MS;

  scenarioTitle.textContent = live
    ? `Runtime ${boardState.topologyRevision ? boardState.topologyRevision.slice(0, 8) : "snapshot"}${isStale ? " (stale)" : ""}`
    : boardState.name || "Demo";

  routeMetric.textContent = String(boardState.routes.length);
  trainMetric.textContent = String(boardState.trains.length);
  occupancyMetric.textContent = String(boardState.occupiedCount);
  streamMetric.textContent = String(boardState.streamSeq);

  cycleSceneBtn.disabled = live;
  toggleRoutesBtn.textContent = state.showRoutes ? "Hide Routes" : "Show Routes";
  if (debugLabelsBtn) {
    debugLabelsBtn.textContent = state.showDebugIds ? "Hide Debug" : "Show Debug";
  }

  routeList.replaceChildren();
  const routesToShow = boardState.routes.map((route) => ({
    title: route.id || "route",
    detail: `${route.entry_signal_id || "?"} -> ${route.exit_signal_id || "?"} | ${route.lifecycle_state || route.status || "active"}`,
    tag: live ? "live" : "demo",
    color: live ? (isStale ? "amber" : "green") : "blue",
  }));

  if (!routesToShow.length) {
    routeList.appendChild(buildEmptyListItem("No routes visible.", "Waiting for Runtime or cycling demo data."));
  } else {
    routesToShow.forEach((route) => {
      const item = document.createElement("li");
      const head = document.createElement("div");
      head.className = "route-item-head";
      const title = document.createElement("span");
      title.className = "route-item-title";
      title.textContent = route.title;
      const tag = document.createElement("span");
      tag.className = `route-tag ${route.color}`;
      tag.textContent = route.tag;
      head.append(title, tag);
      const copy = document.createElement("span");
      copy.className = "route-item-copy";
      copy.textContent = route.detail;
      item.append(head, copy);
      routeList.appendChild(item);
    });
  }

  eventLog.replaceChildren();
  const demoAlerts = live ? [] : boardState.alerts;
  const entries = [...state.logs, ...demoAlerts].slice(0, 8);
  entries.forEach((entry) => {
    const item = document.createElement("li");
    const head = document.createElement("div");
    head.className = "log-item-head";
    const title = document.createElement("span");
    title.className = "log-item-title";
    title.textContent = entry.title;
    const tag = document.createElement("span");
    tag.className = `log-tag ${entry.level}`;
    tag.textContent = entry.level;
    head.append(title, tag);
    const copy = document.createElement("span");
    copy.className = "log-item-copy";
    copy.textContent = entry.detail;
    item.append(head, copy);
    eventLog.appendChild(item);
  });
}

async function responseErrorText(response) {
  const body = await response.text();
  try {
    const payload = JSON.parse(body);
    const detail = String(payload.detail || payload.error || "").trim();
    return `Runtime feed ${response.status}: ${detail || "unavailable"}`;
  } catch (_error) {
    return `Runtime feed ${response.status}: ${body || response.statusText}`;
  }
}

function refreshFeedStatus() {
  if (!state.runtimeState) {
    return;
  }
  const stale = secondsSince(state.runtimeState.generatedAt) * 1000 > STALE_AFTER_MS;
  if (stale) {
    if (state.feedStatus !== "stale") {
      pushLog(
        "warn",
        "Runtime feed",
        `Snapshot is stale for ${secondsSince(state.runtimeState.generatedAt).toFixed(1)}s; keeping the last good board state.`,
      );
    }
    state.feedStatus = "stale";
    return;
  }
  state.feedStatus = "live";
}

async function pollRuntimeState() {
  if (state.polling) {
    return;
  }
  state.polling = true;
  try {
    const response = await fetch("./api/runtime-state", { cache: "no-store" });
    if (response.status === 204) {
      if (!state.runtimeState) {
        state.feedStatus = "waiting";
      }
      state.lastErrorText = "";
      return;
    }
    if (!response.ok) {
      throw new Error(await responseErrorText(response));
    }
    const payload = await response.json();
    const normalized = normalizeRuntimeState(payload);
    if (!normalized) {
      throw new Error("Runtime feed payload is missing layout/ui_positions.");
    }
    const previousState = state.runtimeState;
    state.runtimeState = normalized;
    state.lastErrorText = "";

    if (!previousState) {
      pushLog("info", "Runtime feed", "First live snapshot loaded from /api/runtime-state.");
    } else if (previousState.streamSeq !== normalized.streamSeq) {
      pushLog("info", "Runtime update", `${normalized.routes.length} routes | ${normalized.trains.length} trains | seq ${normalized.streamSeq}`);
    } else if (secondsSince(previousState.generatedAt) * 1000 > STALE_AFTER_MS) {
      pushLog("info", "Runtime feed", "Fresh runtime updates resumed.");
    }
  } catch (error) {
    const message = String(error);
    if (message !== state.lastErrorText) {
      pushLog("error", "Runtime feed", message);
      state.lastErrorText = message;
    }
    if (!state.runtimeState) {
      state.feedStatus = "error";
    }
  } finally {
    refreshFeedStatus();
    renderAll();
    state.polling = false;
  }
}

function applyScenario(index, reason) {
  state.scenarioIndex = index;
  pushLog("info", "Demo", reason);
  renderAll();
}

cycleSceneBtn.addEventListener("click", () => {
  const nextIndex = (state.scenarioIndex + 1) % demoScenarios.length;
  applyScenario(nextIndex, `Switched to ${demoScenarios[nextIndex].name}.`);
});

toggleRoutesBtn.addEventListener("click", () => {
  state.showRoutes = !state.showRoutes;
  pushLog("info", "Board", state.showRoutes ? "Route overlay is visible." : "Route overlay is hidden.");
  renderAll();
});

if (debugLabelsBtn) {
  debugLabelsBtn.addEventListener("click", () => {
    state.showDebugIds = !state.showDebugIds;
    pushLog("info", "Board", state.showDebugIds ? "Debug labels are visible." : "Debug labels are hidden.");
    renderAll();
  });
}

pushLog("info", "Runtime feed", "Polling /api/runtime-state every second.");
updateClock();
renderAll();
pollRuntimeState();
window.setInterval(() => {
  updateClock();
  refreshFeedStatus();
  renderAll();
  pollRuntimeState();
}, POLL_INTERVAL_MS);

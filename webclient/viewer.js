import { normalizeRuntimeState, renderDispatcherBoard } from "/dispatcher-core.js";

const board = document.getElementById("dispatcherBoard");
const boardFrame = document.querySelector(".board-frame");
const connectionPill = document.getElementById("connectionPill");
const routeMetric = document.getElementById("routeMetric");
const trainMetric = document.getElementById("trainMetric");
const occupancyMetric = document.getElementById("occupancyMetric");
const workspaceModeText = document.getElementById("workspaceModeText");
const updatedAtText = document.getElementById("updatedAtText");
const transportHint = document.getElementById("transportHint");
const debugLabelsBtn = document.getElementById("debugLabelsBtn");
const toggleRoutesBtn = document.getElementById("toggleRoutesBtn");
const clockText = document.getElementById("clockText");
const scenarioTitle = document.getElementById("scenarioTitle");
const routeSelect = document.getElementById("routeSelect");
const routeEntryText = document.getElementById("routeEntryText");
const routeExitText = document.getElementById("routeExitText");
const routeTracksText = document.getElementById("routeTracksText");
const routePointsText = document.getElementById("routePointsText");
const setRouteBtn = document.getElementById("setRouteBtn");
const cancelRoutesBtn = document.getElementById("cancelRoutesBtn");
const commandStatusText = document.getElementById("commandStatusText");

let latestRuntime = normalizeRuntimeState({});
let latestDispatcherView = latestRuntime.dispatcherView;
let showDebug = false;
let showRoutes = true;
let runtimeLive = false;
let boardZoom = 1;
let isBoardDragging = false;
let dragStartX = 0;
let dragStartScrollLeft = 0;

function setCommandStatus(text, kind = "") {
  if (!commandStatusText) {
    return;
  }
  commandStatusText.textContent = text;
  if (kind) {
    commandStatusText.dataset.kind = kind;
  } else {
    delete commandStatusText.dataset.kind;
  }
}

function tickClock() {
  const formatter = new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone: "Asia/Bangkok",
  });
  clockText.textContent = formatter.format(new Date());
}

function setConnectionState(kind, text) {
  connectionPill.textContent = text;
  connectionPill.className = `status-pill ${kind}`;
}

function updateMeta(runtime) {
  routeMetric.textContent = String(runtime.routes.length);
  trainMetric.textContent = String(runtime.trains.length);
  occupancyMetric.textContent = String(
    Array.from(runtime.occupancyById.values()).filter((item) => item?.occupied).length,
  );
  workspaceModeText.textContent = String(runtime.raw.workspace_mode || "waiting");
  if (runtime.raw.generated_at) {
    updatedAtText.textContent = new Date(Number(runtime.raw.generated_at) * 1000).toLocaleTimeString("en-GB");
  } else {
    updatedAtText.textContent = "--";
  }
  scenarioTitle.textContent = runtime.dispatcherView.elements.length
    ? "Dispatcher Board"
    : "No Dispatcher Diagram Authored";
  transportHint.textContent = runtime.dispatcherView.elements.length
    ? "Clean track is green, occupied track is red, and active routes extend across the full path."
    : "No dispatcher schematic exists yet. Open /dispatcher/editor to draw and bind the board.";
  updateCommandControls(runtime);
}

function interlockingRouteOptions(runtime) {
  return runtime.interlockingRows
    .map((row, index) => ({
      index,
      routeName: String(row.route_name || "").trim(),
      entrySignal: String(row.entry_signal || "").trim(),
      exitSignal: String(row.exit_signal || "").trim(),
      lockedSections: Array.isArray(row.locked_sections) ? row.locked_sections.map(String) : [],
      requiredPoints: row.required_points && typeof row.required_points === "object" ? row.required_points : {},
    }))
    .filter((row) => row.routeName && row.entrySignal && row.exitSignal);
}

function repopulateRouteSelect(routes, previousValue) {
  if (!routeSelect) {
    return;
  }
  const nextValues = ["", ...routes.map((route) => route.routeName)];
  const currentValues = Array.from(routeSelect.options).map((option) => option.value);
  if (
    currentValues.length === nextValues.length
    && currentValues.every((value, index) => value === nextValues[index])
  ) {
    if (previousValue && routes.some((route) => route.routeName === previousValue)) {
      routeSelect.value = previousValue;
    }
    return;
  }
  routeSelect.replaceChildren();
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "Select route";
  routeSelect.appendChild(placeholder);
  routes.forEach((route) => {
    const option = document.createElement("option");
    option.value = route.routeName;
    option.textContent = `${route.entrySignal} -> ${route.exitSignal}`;
    routeSelect.appendChild(option);
  });
  if (previousValue && routes.some((route) => route.routeName === previousValue)) {
    routeSelect.value = previousValue;
  }
}

function selectedRoute(runtime = latestRuntime) {
  const routeName = String(routeSelect?.value || "").trim();
  if (!routeName) {
    return null;
  }
  return interlockingRouteOptions(runtime).find((route) => route.routeName === routeName) || null;
}

function formatPointLocks(requiredPoints) {
  const entries = Object.entries(requiredPoints || {});
  if (!entries.length) {
    return "--";
  }
  return entries.map(([pointId, position]) => `${pointId}:${position}`).join(", ");
}

function updateRouteReadout(route) {
  if (routeEntryText) routeEntryText.textContent = route?.entrySignal || "--";
  if (routeExitText) routeExitText.textContent = route?.exitSignal || "--";
  if (routeTracksText) routeTracksText.textContent = route?.lockedSections?.length ? route.lockedSections.join(" -> ") : "--";
  if (routePointsText) routePointsText.textContent = route ? formatPointLocks(route.requiredPoints) : "--";
}

function updateCommandControls(runtime) {
  const routes = interlockingRouteOptions(runtime);
  const previousRoute = routeSelect?.value || "";
  repopulateRouteSelect(routes, previousRoute);

  const mode = String(runtime.raw.workspace_mode || "").toLowerCase();
  const canControlRuntime = runtimeLive && ["simulation", "runtime"].includes(mode);
  const canSetRoute = canControlRuntime && routes.length > 0;
  const route = selectedRoute(runtime);
  const routeReady = canSetRoute && Boolean(route);
  if (routeSelect) routeSelect.disabled = !canSetRoute;
  if (setRouteBtn) setRouteBtn.disabled = !routeReady;
  if (cancelRoutesBtn) cancelRoutesBtn.disabled = !canControlRuntime || runtime.routes.length === 0;
  updateRouteReadout(route);
  if (!canControlRuntime) {
    setCommandStatus(runtimeLive ? "Route controls disabled for this workspace mode." : "Runtime controls waiting...");
  } else if (!routes.length) {
    setCommandStatus("No interlocking routes available.");
  }
}

function applyBoardZoom() {
  if (!board) {
    return;
  }
  board.style.transform = `scale(${boardZoom})`;
}

function zoomBoardFromWheel(event) {
  if (!boardFrame) {
    return;
  }
  event.preventDefault();
  const previousZoom = boardZoom;
  const factor = event.deltaY < 0 ? 1.12 : 1 / 1.12;
  boardZoom = Math.min(3, Math.max(0.35, boardZoom * factor));
  if (boardZoom === previousZoom) {
    return;
  }
  applyBoardZoom();
}

function isInteractiveBoardTarget(target) {
  return Boolean(target?.closest?.("button, input, select, textarea, a, label"));
}

function beginBoardDrag(event) {
  if (!boardFrame || event.button !== 0 || isInteractiveBoardTarget(event.target)) {
    return;
  }
  isBoardDragging = true;
  dragStartX = event.clientX;
  dragStartScrollLeft = boardFrame.scrollLeft;
  boardFrame.classList.add("is-dragging");
  event.preventDefault();
}

function dragBoard(event) {
  if (!boardFrame || !isBoardDragging) {
    return;
  }
  const deltaX = event.clientX - dragStartX;
  boardFrame.scrollLeft = dragStartScrollLeft - deltaX;
  event.preventDefault();
}

function endBoardDrag() {
  if (!boardFrame || !isBoardDragging) {
    return;
  }
  isBoardDragging = false;
  boardFrame.classList.remove("is-dragging");
}

function repaint() {
  renderDispatcherBoard(board, latestDispatcherView, latestRuntime, {
    showDebug,
    showRoutes,
    showTrains: false,
    emptyStateText: "No dispatcher schematic. Open /dispatcher/editor to create one.",
  });
  updateMeta({
    ...latestRuntime,
    dispatcherView: latestDispatcherView,
  });
}

async function loadDispatcherLayout() {
  const response = await fetch("/api/dispatcher-layout", { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Dispatcher layout HTTP ${response.status}`);
  }
  const payload = await response.json();
  latestDispatcherView = normalizeRuntimeState({
    layout: { dispatcher_view: payload.dispatcher_view || {} },
  }).dispatcherView;
}

async function loadRuntimeState() {
  try {
    const [runtimeResponse] = await Promise.all([
      fetch("/api/runtime-state", { cache: "no-store" }),
      loadDispatcherLayout(),
    ]);
    if (runtimeResponse.status === 204) {
      latestRuntime = normalizeRuntimeState({});
      runtimeLive = false;
      setConnectionState("waiting", "WAITING RUNTIME");
      repaint();
      return;
    }
    if (!runtimeResponse.ok) {
      throw new Error(`HTTP ${runtimeResponse.status}`);
    }
    const payload = await runtimeResponse.json();
    latestRuntime = normalizeRuntimeState(payload);
    runtimeLive = true;
    setConnectionState("live", "LIVE RUNTIME");
    repaint();
  } catch (error) {
    runtimeLive = false;
    setConnectionState("error", "RUNTIME ERROR");
    transportHint.textContent = `Runtime feed error: ${error instanceof Error ? error.message : String(error)}`;
    updateCommandControls(latestRuntime);
    setCommandStatus("Runtime feed error.", "error");
  }
}

async function waitForCommandResult(commandId) {
  const deadline = Date.now() + 5000;
  while (Date.now() < deadline) {
    const response = await fetch("/api/runtime-command-results", { cache: "no-store" });
    if (response.ok) {
      const payload = await response.json();
      const result = Array.isArray(payload.results)
        ? payload.results.find((item) => String(item.command_id || "") === commandId)
        : null;
      if (result) {
        return result;
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 350));
  }
  return null;
}

async function sendRuntimeCommand(kind, payload = {}) {
  const response = await fetch("/api/runtime-command", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind, payload }),
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(result.detail || result.error || `HTTP ${response.status}`);
  }
  return result;
}

async function submitSetRoute() {
  const route = selectedRoute();
  const entrySignalId = route?.entrySignal || "";
  const exitSignalId = route?.exitSignal || "";
  if (!entrySignalId || !exitSignalId) {
    setCommandStatus("Select an interlocking route.", "error");
    return;
  }
  if (entrySignalId === exitSignalId) {
    setCommandStatus("Entry and exit signals must be different.", "error");
    return;
  }
  try {
    setCommandStatus("Queueing set route command...");
    const queued = await sendRuntimeCommand("set_route", {
      entry_signal_id: entrySignalId,
      exit_signal_id: exitSignalId,
    });
    setCommandStatus("Command queued. Waiting for runtime...");
    const commandResult = await waitForCommandResult(String(queued.command_id || ""));
    if (commandResult?.status === "rejected") {
      setCommandStatus(commandResult.message || "Set route rejected.", "error");
    } else if (commandResult?.status === "applied") {
      setCommandStatus(`Route command applied: ${entrySignalId} -> ${exitSignalId}`, "ok");
    } else {
      setCommandStatus("Command queued; runtime result pending.");
    }
    await loadRuntimeState();
  } catch (error) {
    setCommandStatus(error instanceof Error ? error.message : String(error), "error");
  }
}

async function submitCancelRoutes() {
  try {
    setCommandStatus("Queueing cancel routes command...");
    const queued = await sendRuntimeCommand("cancel_active_routes", {});
    setCommandStatus("Command queued. Waiting for runtime...");
    const commandResult = await waitForCommandResult(String(queued.command_id || ""));
    if (commandResult?.status === "rejected") {
      setCommandStatus(commandResult.message || "Cancel routes rejected.", "error");
    } else if (commandResult?.status === "applied") {
      const cancelled = commandResult.payload?.cancelled_routes ?? 0;
      setCommandStatus(`Cancel routes applied. Cancelled: ${cancelled}`, "ok");
    } else {
      setCommandStatus("Command queued; runtime result pending.");
    }
    await loadRuntimeState();
  } catch (error) {
    setCommandStatus(error instanceof Error ? error.message : String(error), "error");
  }
}

debugLabelsBtn?.addEventListener("click", () => {
  showDebug = !showDebug;
  debugLabelsBtn.textContent = showDebug ? "Hide Debug" : "Show Debug";
  repaint();
});

toggleRoutesBtn?.addEventListener("click", () => {
  showRoutes = !showRoutes;
  toggleRoutesBtn.textContent = showRoutes ? "Hide Routes" : "Show Routes";
  repaint();
});

routeSelect?.addEventListener("change", () => updateCommandControls(latestRuntime));
setRouteBtn?.addEventListener("click", submitSetRoute);
cancelRoutesBtn?.addEventListener("click", submitCancelRoutes);
boardFrame?.addEventListener("wheel", zoomBoardFromWheel, { passive: false });
boardFrame?.addEventListener("mousedown", beginBoardDrag);
boardFrame?.addEventListener("mousemove", dragBoard);
boardFrame?.addEventListener("mouseup", endBoardDrag);
boardFrame?.addEventListener("mouseleave", endBoardDrag);

tickClock();
applyBoardZoom();
setInterval(tickClock, 1000);
loadRuntimeState();
setInterval(loadRuntimeState, 1000);

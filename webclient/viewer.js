import { createBoardCamera, normalizeRuntimeState, renderDispatcherBoard } from "/dispatcher-core.js";
import { applyStaticTranslations, initLanguageSelector, t } from "/i18n.js";

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
const fitBoardBtn = document.getElementById("fitBoardBtn");
const zoomInBtn = document.getElementById("zoomInBtn");
const zoomOutBtn = document.getElementById("zoomOutBtn");

let latestRuntime = normalizeRuntimeState({});
let latestDispatcherView = latestRuntime.dispatcherView;
let showDebug = false;
let showRoutes = true;
let runtimeLive = false;
const boardCamera = createBoardCamera(board, boardFrame, { minScale: 0.45, maxScale: 4 });
let lastLayoutSignature = "";

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
    ? t("viewer.dispatcher_board")
    : t("viewer.no_diagram");
  transportHint.textContent = runtime.dispatcherView.elements.length
    ? t("viewer.clean_track_hint")
    : t("viewer.no_schematic_hint");
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
  placeholder.textContent = t("viewer.select_route");
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
    translatedCommandStatus(runtimeLive ? "viewer.controls_disabled" : "viewer.controls_waiting");
  } else if (!routes.length) {
    translatedCommandStatus("viewer.no_routes");
  }
}

function isInteractiveBoardTarget(target) {
  return Boolean(target?.closest?.("button, input, select, textarea, a, label"));
}

function beginBoardPan(event) {
  if (!boardFrame || isInteractiveBoardTarget(event.target)) {
    return;
  }
  if (boardCamera.beginPan(event)) {
    boardFrame.setPointerCapture?.(event.pointerId);
    event.preventDefault();
  }
}


function localizedRouteError(message) {
  const text = String(message || "").trim();
  if (!text) {
    return "";
  }
  const cannotLockPrefix = "Cannot lock route: ";
  if (text.startsWith(cannotLockPrefix)) {
    return t("route.error.cannot_lock_route", {
      reason: localizedRouteError(text.slice(cannotLockPrefix.length)),
    });
  }
  const patterns = [
    [/^Route (.+) is already active$/, "route.error.already_active", ["route_id"]],
    [/^Route refers to unknown point (.+)$/, "route.error.unknown_point", ["point_id"]],
    [/^Point (.+?) (?:is )?(?:already )?locked by (.+)$/, "route.error.point_locked", ["point_id", "locked_by"]],
    [/^(?:Flank section|Section) (.+?) (?:is )?(?:already )?locked by (.+)$/, "route.error.section_locked", ["section_id", "locked_by"]],
    [/^Route (.+) is occupied by train on sections: (.+)$/, "route.error.occupied_by_train", ["route_id", "sections"]],
    [/^Section (.+) belongs to multiple active routes: (.+)$/, "route.error.section_multiple_active_routes", ["section_id", "routes"]],
  ];
  for (const [pattern, key, fields] of patterns) {
    const match = text.match(pattern);
    if (match) {
      const params = Object.fromEntries(fields.map((field, index) => [field, match[index + 1]]));
      return t(key, params);
    }
  }
  return text;
}

function translatedCommandStatus(key, params = {}, kind = "") {
  setCommandStatus(t(key, params), kind);
}

function panBoard(event) {
  if (boardCamera.pan(event)) {
    event.preventDefault();
  }
}

function endBoardPan(event) {
  if (boardCamera.endPan(event)) {
    event.preventDefault();
  }
}

function repaint() {
  const previousSignature = lastLayoutSignature;
  renderDispatcherBoard(board, latestDispatcherView, latestRuntime, {
    showDebug,
    showRoutes,
    showTrains: false,
    emptyStateText: t("viewer.empty_board"),
  });
  const canvas = latestDispatcherView.canvas;
  lastLayoutSignature = `${canvas.width}x${canvas.height}:${latestDispatcherView.elements.length}`;
  boardCamera.setCanvas(canvas);
  if (lastLayoutSignature !== previousSignature) {
    boardCamera.fit();
  } else {
    boardCamera.apply();
  }
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
      setConnectionState("waiting", t("viewer.waiting_runtime"));
      repaint();
      return;
    }
    if (!runtimeResponse.ok) {
      throw new Error(`HTTP ${runtimeResponse.status}`);
    }
    const payload = await runtimeResponse.json();
    latestRuntime = normalizeRuntimeState(payload);
    runtimeLive = true;
    setConnectionState("live", t("viewer.live_runtime"));
    repaint();
  } catch (error) {
    runtimeLive = false;
    setConnectionState("error", t("viewer.runtime_error"));
    transportHint.textContent = t("viewer.feed_error", {
      message: error instanceof Error ? error.message : String(error),
    });
    updateCommandControls(latestRuntime);
    translatedCommandStatus("viewer.command_error", {}, "error");
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
    translatedCommandStatus("viewer.select_interlocking_route", {}, "error");
    return;
  }
  if (entrySignalId === exitSignalId) {
    translatedCommandStatus("viewer.entry_exit_different", {}, "error");
    return;
  }
  try {
    translatedCommandStatus("viewer.queue_set_route");
    const queued = await sendRuntimeCommand("set_route", {
      entry_signal_id: entrySignalId,
      exit_signal_id: exitSignalId,
    });
    translatedCommandStatus("viewer.command_queued");
    const commandResult = await waitForCommandResult(String(queued.command_id || ""));
    if (commandResult?.status === "rejected") {
      setCommandStatus(localizedRouteError(commandResult.message) || t("viewer.set_route_rejected"), "error");
    } else if (commandResult?.status === "applied") {
      translatedCommandStatus(
        "viewer.route_applied",
        { entry: entrySignalId, exit: exitSignalId },
        "ok",
      );
    } else {
      translatedCommandStatus("viewer.result_pending");
    }
    await loadRuntimeState();
  } catch (error) {
    setCommandStatus(localizedRouteError(error instanceof Error ? error.message : String(error)), "error");
  }
}

async function submitCancelRoutes() {
  try {
    translatedCommandStatus("viewer.queue_cancel_routes");
    const queued = await sendRuntimeCommand("cancel_active_routes", {});
    translatedCommandStatus("viewer.command_queued");
    const commandResult = await waitForCommandResult(String(queued.command_id || ""));
    if (commandResult?.status === "rejected") {
      setCommandStatus(localizedRouteError(commandResult.message) || t("viewer.cancel_rejected"), "error");
    } else if (commandResult?.status === "applied") {
      const cancelled = commandResult.payload?.cancelled_routes ?? 0;
      translatedCommandStatus("viewer.cancel_applied", { count: cancelled }, "ok");
    } else {
      translatedCommandStatus("viewer.result_pending");
    }
    await loadRuntimeState();
  } catch (error) {
    setCommandStatus(localizedRouteError(error instanceof Error ? error.message : String(error)), "error");
  }
}

debugLabelsBtn?.addEventListener("click", () => {
  showDebug = !showDebug;
  debugLabelsBtn.textContent = showDebug ? t("viewer.hide_debug") : t("viewer.show_debug");
  repaint();
});

toggleRoutesBtn?.addEventListener("click", () => {
  showRoutes = !showRoutes;
  toggleRoutesBtn.textContent = showRoutes ? t("viewer.hide_routes") : t("viewer.show_routes");
  repaint();
});

routeSelect?.addEventListener("change", () => updateCommandControls(latestRuntime));
setRouteBtn?.addEventListener("click", submitSetRoute);
cancelRoutesBtn?.addEventListener("click", submitCancelRoutes);
boardFrame?.addEventListener("wheel", (event) => boardCamera.wheel(event), { passive: false });
boardFrame?.addEventListener("pointerdown", beginBoardPan);
boardFrame?.addEventListener("pointermove", panBoard);
boardFrame?.addEventListener("pointerup", endBoardPan);
boardFrame?.addEventListener("pointercancel", endBoardPan);
fitBoardBtn?.addEventListener("click", () => boardCamera.fit());
zoomInBtn?.addEventListener("click", () => {
  const rect = boardFrame.getBoundingClientRect();
  boardCamera.zoomAt(rect.left + rect.width / 2, rect.top + rect.height / 2, 1.2);
});
zoomOutBtn?.addEventListener("click", () => {
  const rect = boardFrame.getBoundingClientRect();
  boardCamera.zoomAt(rect.left + rect.width / 2, rect.top + rect.height / 2, 1 / 1.2);
});
window.addEventListener("resize", () => boardCamera.apply());

applyStaticTranslations();
initLanguageSelector(() => {
  debugLabelsBtn.textContent = showDebug ? t("viewer.hide_debug") : t("viewer.show_debug");
  toggleRoutesBtn.textContent = showRoutes ? t("viewer.hide_routes") : t("viewer.show_routes");
  repaint();
});

tickClock();
setInterval(tickClock, 1000);
loadRuntimeState();
setInterval(loadRuntimeState, 1000);

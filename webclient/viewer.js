import { normalizeRuntimeState, renderDispatcherBoard } from "/dispatcher-core.js";

const board = document.getElementById("dispatcherBoard");
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

let latestRuntime = normalizeRuntimeState({});
let latestDispatcherView = latestRuntime.dispatcherView;
let showDebug = false;
let showRoutes = true;

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
      setConnectionState("waiting", "WAITING RUNTIME");
      repaint();
      return;
    }
    if (!runtimeResponse.ok) {
      throw new Error(`HTTP ${runtimeResponse.status}`);
    }
    const payload = await runtimeResponse.json();
    latestRuntime = normalizeRuntimeState(payload);
    setConnectionState("live", "LIVE RUNTIME");
    repaint();
  } catch (error) {
    setConnectionState("error", "RUNTIME ERROR");
    transportHint.textContent = `Runtime feed error: ${error instanceof Error ? error.message : String(error)}`;
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

tickClock();
setInterval(tickClock, 1000);
loadRuntimeState();
setInterval(loadRuntimeState, 1000);

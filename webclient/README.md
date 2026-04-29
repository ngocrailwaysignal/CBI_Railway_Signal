# Webclient Dispatcher

Webclient now works as a live monitor for the CBI Runtime workspace.

- Entering `Runtime` workspace in the desktop app now auto-starts the local webclient server and
  opens the browser once at `http://127.0.0.1:8091/`.
- The desktop app writes `data/runtime_journal/webclient_runtime_state.json`.
- `webclient/serve.py` exposes that file at `GET /api/runtime-state`.
- The browser polls the endpoint every second and renders the current topology, routes, trains,
  points, occupancy, and signals directly from the runtime payload.
- If the feed stops updating, the board keeps the last good snapshot and marks it as stale.
- Demo data remains available only as a fallback before the first live payload appears.

Run:

```bash
python webclient/serve.py
```

Then open `http://127.0.0.1:8091`.
<!-- Webclient mới đang chạy tại:

http://127.0.0.1:8091/dispatcher
http://127.0.0.1:8091/dispatcher/editor -->
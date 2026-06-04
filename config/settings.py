"""Typed defaults for operational CBI simulation settings."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True, frozen=True)
class TimingConfig:
    """Runtime timing defaults."""

    time_lock_seconds: float = 60.0
    default_overlap_length: int = 1
    overlap_release_seconds: float = 60.0
    runtime_snapshot_checkpoint_interval: int = 1


@dataclass(slots=True, frozen=True)
class PathConfig:
    """Repository-relative path defaults."""

    default_layout_path: str = "data/station_layout/main_layout.json"
    runtime_journal_dir: str = "data/runtime_journal"
    smartio_local_layout_dir: str = "data/_smartio_local"


@dataclass(slots=True, frozen=True)
class SmartIOConfig:
    """SmartIO endpoint and reconnect defaults."""

    remote_ws_url: str = "wss://cbi-smartio.onrender.com/smartio"
    local_host: str = "127.0.0.1"
    local_port: int = 8088
    local_ws_path: str = "/smartio"
    auto_connect: bool = True
    reconnect_enabled: bool = True
    reconnect_max_seconds: float = 30.0
    snapshot_heartbeat_seconds: float = 5.0
    runtime_stale_seconds: float = 15.0

    @property
    def local_http_url(self) -> str:
        return f"http://{self.local_host}:{self.local_port}/"

    @property
    def local_ws_url(self) -> str:
        return f"ws://{self.local_host}:{self.local_port}{self.local_ws_path}"


@dataclass(slots=True, frozen=True)
class WebclientConfig:
    """Dispatcher webclient process defaults."""

    host: str = "127.0.0.1"
    port: int = 8091
    runtime_publish_interval_ms: int = 1000
    process_start_timeout_ms: int = 3000
    process_stop_timeout_ms: int = 1500

    @property
    def http_url(self) -> str:
        return f"http://{self.host}:{self.port}/"


@dataclass(slots=True, frozen=True)
class AppConfig:
    """Top-level application defaults."""

    name: str = "CBI Simulation"
    ui_language: str = "en"
    emergency_release_password: str = "cbi123"
    timing: TimingConfig = field(default_factory=TimingConfig)
    paths: PathConfig = field(default_factory=PathConfig)
    smartio: SmartIOConfig = field(default_factory=SmartIOConfig)
    webclient: WebclientConfig = field(default_factory=WebclientConfig)


DEFAULT_APP_CONFIG = AppConfig()

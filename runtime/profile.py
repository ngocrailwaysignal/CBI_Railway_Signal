"""Operational profile for generic application behavior."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from config import DEFAULT_APP_CONFIG

if TYPE_CHECKING:
    from kernel.product_kernel import ProductRules


@dataclass(slots=True, frozen=True)
class GenericApplicationProfile:
    """Country/operator-specific behavior without station-specific data."""

    name: str = DEFAULT_APP_CONFIG.name
    time_lock_seconds: float = DEFAULT_APP_CONFIG.timing.time_lock_seconds
    default_overlap_length: int = DEFAULT_APP_CONFIG.timing.default_overlap_length
    overlap_release_seconds: float = DEFAULT_APP_CONFIG.timing.overlap_release_seconds
    load_runtime_state: bool = False
    load_occupancy: bool = True
    include_runtime_state: bool = False
    include_occupancy: bool = True
    ui_language: str = DEFAULT_APP_CONFIG.ui_language
    smart_io_ws_url: str = DEFAULT_APP_CONFIG.smartio.remote_ws_url
    smart_io_auto_connect: bool = DEFAULT_APP_CONFIG.smartio.auto_connect
    smart_io_reconnect_enabled: bool = DEFAULT_APP_CONFIG.smartio.reconnect_enabled
    smart_io_reconnect_max_seconds: float = DEFAULT_APP_CONFIG.smartio.reconnect_max_seconds
    smart_io_snapshot_heartbeat_seconds: float = (
        DEFAULT_APP_CONFIG.smartio.snapshot_heartbeat_seconds
    )
    smart_io_runtime_stale_seconds: float = DEFAULT_APP_CONFIG.smartio.runtime_stale_seconds
    smart_io_local_host: str = DEFAULT_APP_CONFIG.smartio.local_host
    smart_io_local_port: int = DEFAULT_APP_CONFIG.smartio.local_port
    smart_io_local_ws_path: str = DEFAULT_APP_CONFIG.smartio.local_ws_path
    emergency_release_password: str = DEFAULT_APP_CONFIG.emergency_release_password
    default_layout_path: str = DEFAULT_APP_CONFIG.paths.default_layout_path
    runtime_journal_dir: str = DEFAULT_APP_CONFIG.paths.runtime_journal_dir
    smartio_local_layout_dir: str = DEFAULT_APP_CONFIG.paths.smartio_local_layout_dir
    webclient_host: str = DEFAULT_APP_CONFIG.webclient.host
    webclient_port: int = DEFAULT_APP_CONFIG.webclient.port
    webclient_runtime_publish_interval_ms: int = (
        DEFAULT_APP_CONFIG.webclient.runtime_publish_interval_ms
    )
    process_start_timeout_ms: int = DEFAULT_APP_CONFIG.webclient.process_start_timeout_ms
    process_stop_timeout_ms: int = DEFAULT_APP_CONFIG.webclient.process_stop_timeout_ms
    runtime_snapshot_checkpoint_interval: int = (
        DEFAULT_APP_CONFIG.timing.runtime_snapshot_checkpoint_interval
    )

    def to_product_rules(self) -> ProductRules:
        """Map application profile options into product-kernel rules."""
        from kernel.product_kernel import ProductRules

        return ProductRules(
            time_lock_seconds=self.time_lock_seconds,
            default_overlap_length=self.default_overlap_length,
            overlap_release_seconds=self.overlap_release_seconds,
        )

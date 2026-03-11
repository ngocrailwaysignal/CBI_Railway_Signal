"""Operational profile for generic application behavior."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from generic_product import ProductRules


@dataclass(slots=True, frozen=True)
class GenericApplicationProfile:
    """Country/operator-specific behavior without station-specific data."""

    name: str = "Default"
    time_lock_seconds: float = 2.0
    default_overlap_length: int = 1
    overlap_release_seconds: float = 2.0
    load_runtime_state: bool = False
    load_occupancy: bool = True
    include_runtime_state: bool = False
    include_occupancy: bool = True
    ui_language: str = "en"
    smart_io_ws_url: str = "wss://cbi-smartio.onrender.com/smartio"
    smart_io_auto_connect: bool = True
    smart_io_reconnect_enabled: bool = True
    smart_io_reconnect_max_seconds: float = 30.0
    smart_io_snapshot_heartbeat_seconds: float = 5.0
    smart_io_runtime_stale_seconds: float = 15.0
    emergency_release_password: str = "cbi123"
    runtime_journal_dir: str = "data/runtime_journal"
    runtime_snapshot_checkpoint_interval: int = 1

    def to_product_rules(self) -> ProductRules:
        """Map application profile options into product-kernel rules."""
        from generic_product import ProductRules

        return ProductRules(
            time_lock_seconds=self.time_lock_seconds,
            default_overlap_length=self.default_overlap_length,
            overlap_release_seconds=self.overlap_release_seconds,
        )

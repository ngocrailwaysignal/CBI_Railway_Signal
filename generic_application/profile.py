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
    time_lock_seconds: float = 30.0
    default_overlap_length: int = 0
    overlap_release_seconds: float = 0.0
    load_runtime_state: bool = False
    load_occupancy: bool = True
    include_runtime_state: bool = False
    include_occupancy: bool = True

    def to_product_rules(self) -> ProductRules:
        """Map application profile options into product-kernel rules."""
        from generic_product import ProductRules

        return ProductRules(
            time_lock_seconds=self.time_lock_seconds,
            default_overlap_length=self.default_overlap_length,
            overlap_release_seconds=self.overlap_release_seconds,
        )

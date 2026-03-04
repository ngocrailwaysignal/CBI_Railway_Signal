"""Formatting helpers for route-related UI output."""

from __future__ import annotations

from core.domain.model.elements import PointPosition
from core.domain.model.route import Route
from ui.i18n import UITranslator


class RoutePresenter:
    """Formats route/interlocking details for logs and labels."""

    def __init__(self, translator: UITranslator) -> None:
        self._translator = translator

    def set_translator(self, translator: UITranslator) -> None:
        self._translator = translator

    def _t(self, key: str, **kwargs: object) -> str:
        return self._translator.t(key, **kwargs)

    @staticmethod
    def format_point_locks(required_points: dict[str, PointPosition]) -> str:
        if not required_points:
            return "-"
        return ", ".join(
            f"{point_id}:{position.value}"
            for point_id, position in sorted(required_points.items())
        )

    @staticmethod
    def _format_items(items: list[str] | tuple[str, ...] | set[str] | None) -> str:
        if not items:
            return "-"
        normalized = [str(item).strip() for item in items if str(item).strip()]
        return ", ".join(normalized) if normalized else "-"

    @staticmethod
    def _format_path(path: list[str] | None) -> str:
        if not path:
            return "-"
        return " -> ".join(path)

    def build_route_search_log(
        self,
        route: Route,
        search_order: list[str],
        *,
        route_label: str | None = None,
        entry_protects: str | None = None,
        exit_protects: str | None = None,
        direction: str | None = None,
        lifecycle: str | None = None,
        destination_track: str | None = None,
        opposing_signals: list[str] | None = None,
        conflicting_routes: list[str] | None = None,
        approach_lock_state: str | None = None,
        approach_lock_remaining_seconds: float | None = None,
        overlap_release_seconds: float | None = None,
    ) -> str:
        try:
            point_locks = self.format_point_locks(route.all_required_point_positions)
        except ValueError:
            point_locks = self.format_point_locks(route.required_point_positions)
        flank_points = self.format_point_locks(route.flank_point_positions)
        flank_sections = self._format_items(route.monitored_flank_sections)
        overlap_release_text = (
            f"{float(overlap_release_seconds):.1f}s"
            if overlap_release_seconds is not None
            else "-"
        )
        if approach_lock_state:
            if approach_lock_remaining_seconds is not None and approach_lock_remaining_seconds > 0.0:
                approach_lock_text = self._t(
                    "route_log.approach_lock_remaining",
                    state=approach_lock_state,
                    seconds=float(approach_lock_remaining_seconds),
                )
            else:
                approach_lock_text = approach_lock_state
        else:
            approach_lock_text = "-"

        route_display = route_label or f"{route.entry_signal_id}->{route.exit_signal_id}"
        entry_display = self._t(
            "route_log.entry_line",
            entry_signal=route.entry_signal_id,
            entry_protects=entry_protects or "-",
        )
        exit_display = self._t(
            "route_log.exit_line",
            exit_signal=route.exit_signal_id,
            exit_protects=exit_protects or "-",
        )

        return "\n".join(
            [
                self._t("route_log.section.summary"),
                f"{self._t('route_log.label.route')}: {route_display}",
                f"{self._t('route_log.label.entry')}: {entry_display}",
                f"{self._t('route_log.label.exit')}: {exit_display}",
                f"{self._t('route_log.label.direction')}: {direction or '-'}",
                f"{self._t('route_log.label.lifecycle')}: {lifecycle or '-'}",
                "",
                self._t("route_log.section.path_lock"),
                f"{self._t('route_log.label.search_order')}: {self._format_path(search_order)}",
                f"{self._t('route_log.label.locked_path')}: {self._format_path(route.path)}",
                f"{self._t('route_log.label.overlap')}: {self._format_path(route.overlap_path)}",
                f"{self._t('route_log.label.destination_track')}: {destination_track or '-'}",
                f"{self._t('route_log.label.point_locks')}: {point_locks}",
                f"{self._t('route_log.label.flank_points')}: {flank_points}",
                f"{self._t('route_log.label.flank_monitored_sections')}: {flank_sections}",
                "",
                self._t("route_log.section.safety_conflict"),
                f"{self._t('route_log.label.opposing_signals')}: {self._format_items(opposing_signals)}",
                f"{self._t('route_log.label.conflicting_routes')}: {self._format_items(conflicting_routes)}",
                f"{self._t('route_log.label.approach_locking_section')}: {route.approach_locking_section or '-'}",
                f"{self._t('route_log.label.approach_lock_state')}: {approach_lock_text}",
                f"{self._t('route_log.label.overlap_release')}: {overlap_release_text}",
            ]
        )

    def build_interlocking_row_search_log(
        self,
        *,
        route_id: str,
        route_label: str,
        entry_signal: str,
        exit_signal: str,
        entry_protects: str,
        exit_protects: str,
        direction: str,
        approach_locking_section: str,
        search_order: list[str],
        locked_path: list[str],
        overlap_path: list[str],
        destination_track: str,
        point_locks: dict[str, PointPosition],
        flank_point_locks: dict[str, PointPosition],
        monitored_flank_sections: list[str] | None,
        opposing_signals: list[str] | None,
        conflicting_routes: list[str] | None,
        overlap_release_seconds: float | None,
    ) -> str:
        synthetic_route = Route(
            id=route_id,
            entry_signal_id=entry_signal,
            exit_signal_id=exit_signal,
            path=list(locked_path),
            overlap_path=list(overlap_path),
            required_point_positions=dict(point_locks),
            flank_point_positions=dict(flank_point_locks),
            monitored_flank_sections=list(monitored_flank_sections or []),
            approach_locking_section=approach_locking_section or None,
        )
        return self.build_route_search_log(
            synthetic_route,
            search_order,
            route_label=route_label,
            entry_protects=entry_protects,
            exit_protects=exit_protects,
            direction=direction,
            lifecycle="-",
            destination_track=destination_track,
            opposing_signals=list(opposing_signals or []),
            conflicting_routes=list(conflicting_routes or []),
            approach_lock_state="-",
            approach_lock_remaining_seconds=None,
            overlap_release_seconds=overlap_release_seconds,
        )


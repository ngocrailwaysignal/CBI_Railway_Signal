"""Normalization and validation helpers for the web dispatcher editor."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

ELEMENT_KINDS = {"track_section", "signal", "point", "label", "block_marker"}
DEFAULT_CANVAS = {
    "width": 1920.0,
    "height": 900.0,
    "grid_size": 20.0,
    "snap_enabled": True,
    "background": "#050607",
}


def create_empty_dispatcher_view() -> dict[str, Any]:
    return {
        "canvas": dict(DEFAULT_CANVAS),
        "elements": [],
    }


def build_bindable_catalog(layout_document: dict[str, Any]) -> dict[str, list[str]]:
    sections = []
    for item in layout_document.get("sections", []):
        if isinstance(item, dict) and str(item.get("id", "")).strip():
            sections.append(str(item["id"]))
    points = []
    for item in layout_document.get("points", []):
        if isinstance(item, dict) and str(item.get("id", "")).strip():
            points.append(str(item["id"]))
    signals = []
    for item in layout_document.get("signals", []):
        if isinstance(item, dict) and str(item.get("id", "")).strip():
            signals.append(str(item["id"]))
    return {
        "sections": sorted(set(sections)),
        "points": sorted(set(points)),
        "signals": sorted(set(signals)),
    }


def normalize_dispatcher_view(
    raw_view: Any,
    *,
    bindable_catalog: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    bindable_catalog = bindable_catalog or {"sections": [], "points": [], "signals": []}
    if not isinstance(raw_view, dict):
        return create_empty_dispatcher_view()
    if "elements" not in raw_view:
        raw_view = _migrate_legacy_dispatcher_view(raw_view)
    canvas_source = raw_view.get("canvas", {})
    canvas = {
        "width": _coerce_float(
            _pick(canvas_source, "width"), DEFAULT_CANVAS["width"], minimum=640.0
        ),
        "height": _coerce_float(
            _pick(canvas_source, "height"), DEFAULT_CANVAS["height"], minimum=480.0
        ),
        "grid_size": _coerce_float(
            _pick(canvas_source, "grid_size"),
            DEFAULT_CANVAS["grid_size"],
            minimum=4.0,
        ),
        "snap_enabled": bool(_pick(canvas_source, "snap_enabled", DEFAULT_CANVAS["snap_enabled"])),
        "background": str(_pick(canvas_source, "background", DEFAULT_CANVAS["background"]))[:64],
    }
    normalized_elements: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(raw_view.get("elements", [])):
        if not isinstance(item, dict):
            continue
        element = _normalize_element(item, index=index, bindable_catalog=bindable_catalog)
        element_id = element["id"]
        if element_id in seen_ids:
            raise ValueError(f"Duplicate dispatcher element id: {element_id}")
        seen_ids.add(element_id)
        normalized_elements.append(element)
    normalized_elements.sort(key=lambda element: (int(element.get("z_index", 0)), element["id"]))
    return {
        "canvas": canvas,
        "elements": normalized_elements,
    }


def _normalize_element(
    raw_element: dict[str, Any],
    *,
    index: int,
    bindable_catalog: dict[str, list[str]],
) -> dict[str, Any]:
    kind = str(raw_element.get("kind", "")).strip().lower()
    if kind not in ELEMENT_KINDS:
        raise ValueError(f"Unsupported dispatcher element kind: {kind or '<empty>'}")
    element_id = str(raw_element.get("id", f"{kind}-{index + 1}")).strip()
    if not element_id:
        raise ValueError("Dispatcher element id is required")

    position_source = raw_element.get("position", {})
    position = {
        "x": _coerce_float(_pick(position_source, "x"), 0.0),
        "y": _coerce_float(_pick(position_source, "y"), 0.0),
    }
    rotation = _coerce_float(raw_element.get("rotation"), 0.0)
    z_index = int(_coerce_float(raw_element.get("z_index"), float(index)))
    style = (
        deepcopy(raw_element.get("style", {})) if isinstance(raw_element.get("style"), dict) else {}
    )
    geometry = _normalize_geometry(kind, raw_element.get("geometry", {}))
    binding = _normalize_binding(kind, raw_element.get("binding"), bindable_catalog)
    return {
        "id": element_id,
        "kind": kind,
        "position": position,
        "rotation": rotation,
        "geometry": geometry,
        "style": style,
        "z_index": z_index,
        "binding": binding,
    }


def _normalize_geometry(kind: str, raw_geometry: Any) -> dict[str, Any]:
    raw_geometry = raw_geometry if isinstance(raw_geometry, dict) else {}
    if kind == "track_section":
        points = raw_geometry.get("points", [])
        if not isinstance(points, list) or len(points) < 2:
            points = [{"x": 0.0, "y": 0.0}, {"x": 160.0, "y": 0.0}]
        normalized_points = [_normalize_point(point) for point in points]
        return {
            "points": normalized_points,
            "stroke_width": _coerce_float(raw_geometry.get("stroke_width"), 4.0, minimum=1.0),
            "marker_spacing": _coerce_float(raw_geometry.get("marker_spacing"), 48.0, minimum=8.0),
        }
    if kind == "signal":
        return {
            "mast": _coerce_float(raw_geometry.get("mast"), 18.0, minimum=8.0),
            "arm": _coerce_float(raw_geometry.get("arm"), 14.0, minimum=6.0),
            "head_radius": _coerce_float(raw_geometry.get("head_radius"), 5.5, minimum=3.0),
            "label_offset": _coerce_float(raw_geometry.get("label_offset"), 20.0, minimum=6.0),
        }
    if kind == "point":
        branch_side = str(raw_geometry.get("branch_side", "up")).strip().lower()
        if branch_side not in {"up", "down"}:
            branch_side = "up"
        return {
            "trunk": _coerce_float(raw_geometry.get("trunk"), 24.0, minimum=8.0),
            "straight": _coerce_float(raw_geometry.get("straight"), 58.0, minimum=12.0),
            "branch": _coerce_float(raw_geometry.get("branch"), 50.0, minimum=12.0),
            "diverge": _coerce_float(raw_geometry.get("diverge"), 22.0, minimum=8.0),
            "branch_side": branch_side,
        }
    if kind == "label":
        return {
            "text": str(raw_geometry.get("text", "LABEL")),
            "font_size": _coerce_float(raw_geometry.get("font_size"), 28.0, minimum=8.0),
            "align": str(raw_geometry.get("align", "middle")).strip().lower(),
        }
    return {
        "width": _coerce_float(raw_geometry.get("width"), 42.0, minimum=8.0),
        "height": _coerce_float(raw_geometry.get("height"), 18.0, minimum=8.0),
        "radius": _coerce_float(raw_geometry.get("radius"), 8.0, minimum=0.0),
    }


def _normalize_binding(
    kind: str,
    raw_binding: Any,
    bindable_catalog: dict[str, list[str]],
) -> dict[str, str] | None:
    if raw_binding in (None, ""):
        return None
    if not isinstance(raw_binding, dict):
        raise ValueError(f"Invalid binding for dispatcher element kind {kind}")
    cbi_type = str(raw_binding.get("cbi_type", "")).strip().lower()
    cbi_id = str(raw_binding.get("cbi_id", "")).strip()
    if kind in {"label", "block_marker"} and not cbi_type and not cbi_id:
        return None
    if not cbi_type or not cbi_id:
        raise ValueError(f"Dispatcher binding requires cbi_type and cbi_id for {kind}")
    allowed_types = {
        "track_section": {"section"},
        "signal": {"signal"},
        "point": {"point"},
        "label": set(),
        "block_marker": {"section"},
    }
    if cbi_type not in allowed_types.get(kind, set()):
        raise ValueError(f"Binding type {cbi_type} is not valid for {kind}")
    catalog_key = f"{cbi_type}s"
    if cbi_id not in set(bindable_catalog.get(catalog_key, [])):
        raise ValueError(f"Unknown {cbi_type} binding id: {cbi_id}")
    return {"cbi_type": cbi_type, "cbi_id": cbi_id}


def _migrate_legacy_dispatcher_view(raw_view: dict[str, Any]) -> dict[str, Any]:
    canvas = dict(DEFAULT_CANVAS)
    elements: list[dict[str, Any]] = []
    z_index = 0

    for segment in raw_view.get("segments", []):
        if not isinstance(segment, dict):
            continue
        points = [
            _normalize_point(point)
            for point in segment.get("points", [])
            if isinstance(point, dict)
        ]
        if len(points) < 2:
            continue
        xs = [point["x"] for point in points]
        ys = [point["y"] for point in points]
        min_x = min(xs)
        min_y = min(ys)
        relative_points = [{"x": point["x"] - min_x, "y": point["y"] - min_y} for point in points]
        state_source_ids = [
            str(item).strip() for item in segment.get("state_source_ids", []) if str(item).strip()
        ]
        binding = None
        if len(state_source_ids) == 1:
            binding = {"cbi_type": "section", "cbi_id": state_source_ids[0]}
        elements.append(
            {
                "id": str(segment.get("id", f"segment-{z_index + 1}")),
                "kind": "track_section",
                "position": {"x": min_x, "y": min_y},
                "rotation": 0.0,
                "geometry": {
                    "points": relative_points,
                    "stroke_width": 4.0,
                    "marker_spacing": 42.0,
                },
                "style": {
                    "variant": str(segment.get("kind", "main")).strip().lower() or "main",
                },
                "z_index": z_index,
                "binding": binding,
            }
        )
        z_index += 1

    for signal_symbol in raw_view.get("signal_symbols", []):
        if not isinstance(signal_symbol, dict):
            continue
        signal_id = str(signal_symbol.get("signal_id", "")).strip()
        if not signal_id:
            continue
        direction = str(signal_symbol.get("direction", "RIGHT")).strip().upper()
        elements.append(
            {
                "id": f"signal-{signal_id}",
                "kind": "signal",
                "position": {
                    "x": _coerce_float(signal_symbol.get("x"), 0.0),
                    "y": _coerce_float(signal_symbol.get("y"), 0.0),
                },
                "rotation": 180.0 if direction == "LEFT" else 0.0,
                "geometry": {"mast": 18.0, "arm": 14.0, "head_radius": 5.5, "label_offset": 20.0},
                "style": {},
                "z_index": 500 + z_index,
                "binding": {"cbi_type": "signal", "cbi_id": signal_id},
            }
        )
        z_index += 1

    for annotation in raw_view.get("annotations", []):
        if not isinstance(annotation, dict):
            continue
        kind = str(annotation.get("kind", "text")).strip().lower()
        element_id = (
            str(annotation.get("id", f"annotation-{z_index + 1}")).strip()
            or f"annotation-{z_index + 1}"
        )
        position = {
            "x": _coerce_float(annotation.get("x"), 0.0),
            "y": _coerce_float(annotation.get("y"), 0.0),
        }
        if kind == "pill":
            elements.append(
                {
                    "id": element_id,
                    "kind": "block_marker",
                    "position": position,
                    "rotation": 0.0,
                    "geometry": {
                        "width": _coerce_float(annotation.get("width"), 40.0, minimum=8.0),
                        "height": 18.0,
                        "radius": 8.0,
                    },
                    "style": {
                        "tone": str(annotation.get("tone", "steel")).strip().lower() or "steel"
                    },
                    "z_index": 700 + z_index,
                    "binding": None,
                }
            )
        else:
            elements.append(
                {
                    "id": element_id,
                    "kind": "label",
                    "position": position,
                    "rotation": 0.0,
                    "geometry": {
                        "text": str(annotation.get("text", "")),
                        "font_size": _size_token_to_font(annotation.get("size")),
                        "align": _align_token(annotation.get("align")),
                    },
                    "style": {
                        "tone": str(annotation.get("tone", "bright")).strip().lower() or "bright"
                    },
                    "z_index": 650 + z_index,
                    "binding": None,
                }
            )
        z_index += 1

    return {"canvas": canvas, "elements": elements}


def _size_token_to_font(raw_size: Any) -> float:
    token = str(raw_size or "").strip().lower()
    mapping = {"sm": 18.0, "md": 24.0, "lg": 30.0, "xl": 38.0}
    return mapping.get(token, 24.0)


def _align_token(raw_align: Any) -> str:
    token = str(raw_align or "middle").strip().lower()
    if token in {"start", "middle", "end"}:
        return token
    return "middle"


def _normalize_point(raw_point: Any) -> dict[str, float]:
    if not isinstance(raw_point, dict):
        return {"x": 0.0, "y": 0.0}
    if "node_id" in raw_point:
        # Legacy dispatcher_view could reference topology nodes directly. The web editor v1 stores
        # only concrete coordinates, so unknown node references degrade to origin until edited.
        return {
            "x": _coerce_float(raw_point.get("x"), 0.0),
            "y": _coerce_float(raw_point.get("y"), 0.0),
        }
    return {
        "x": _coerce_float(raw_point.get("x"), 0.0),
        "y": _coerce_float(raw_point.get("y"), 0.0),
    }


def _coerce_float(value: Any, default: float, *, minimum: float | None = None) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)
    if minimum is not None and number < minimum:
        return float(minimum)
    return number


def _pick(container: Any, key: str, default: Any = None) -> Any:
    if isinstance(container, dict):
        return container.get(key, default)
    return default

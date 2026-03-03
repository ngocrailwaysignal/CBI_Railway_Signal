# Layered Architecture

The simulator is organized into 3 layers to separate reusable interlocking logic, operator profile rules, and station-specific data.

## 1. Generic Product

Path: `generic_product/`

Purpose:
- Contains core reusable interlocking kernel behavior.
- No dependency on one station layout file or one operator profile.

Main module:
- `generic_product/kernel.py`
  - `ProductRules`: product defaults (`time_lock_seconds`, `default_overlap_length`)
  - `GenericProductKernel`: route finding, route setting, simulation creation, interlocking-table generation

## 2. Generic Application

Path: `generic_application/`

Purpose:
- Applies operator/country policy on top of the product kernel.
- Defines application profile defaults for load/save/runtime behavior.

Main modules:
- `generic_application/profile.py`
  - `GenericApplicationProfile`
- `generic_application/service.py`
  - `GenericApplicationService`
  - Wraps product kernel with profile settings.

## 3. Specific Application

Path: `specific_application/`

Purpose:
- Handles one concrete station layout (track plan + element data).
- Supports editor-facing load/save/new operations.

Main modules:
- `specific_application/station_layout.py`
  - `StationLayout`
- `specific_application/editor_service.py`
  - `SpecificLayoutEditorService`

## UI Integration

`ui/main_window.py` now uses:
- `GenericApplicationService` for route/interlocking/simulation use-cases.
- `SpecificLayoutEditorService` for station layout load/save/new.
- Runtime timing controls (approach-lock release and overlap release) are configured from UI and applied through `GenericApplicationService`.

`main.py` is responsible for selecting the `GenericApplicationProfile` and injecting it into `MainWindow`.

`ui/canvas_editor.py` remains the drawing/editor surface and topology mutator. JSON persistence is handled by the specific/generic application services.

"""Migrate a layout JSON file to the current signal-link schema.

By default this script exports static layout only:
- keeps OCCUPIED/FREE track state
- clears route locks and active signal route state
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.topology import RailwayTopology


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate layout JSON to the current schema"
    )
    parser.add_argument("input", type=Path, help="Input layout JSON path")
    parser.add_argument("output", type=Path, help="Output layout JSON path")
    parser.add_argument(
        "--keep-runtime",
        action="store_true",
        help="Preserve runtime state (locks, signal route_id/aspect) in output",
    )
    parser.add_argument(
        "--clear-occupancy",
        action="store_true",
        help="Force all track sections to FREE in output",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    topology = RailwayTopology.load_from_json(
        args.input,
        load_runtime_state=args.keep_runtime,
        load_occupancy=not args.clear_occupancy,
    )
    topology.export_to_json(
        args.output,
        include_runtime_state=args.keep_runtime,
        include_occupancy=not args.clear_occupancy,
    )

    print(f"Migrated: {args.input} -> {args.output}")
    print(
        "Options:"
        f" keep_runtime={args.keep_runtime},"
        f" keep_occupancy={not args.clear_occupancy}"
    )


if __name__ == "__main__":
    main()

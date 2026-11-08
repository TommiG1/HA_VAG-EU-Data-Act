#!/usr/bin/env python3
"""Fail if any integration module is below the Silver coverage floor."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--min",
        type=float,
        default=95.0,
        help="Minimum percent covered per module (default: 95)",
    )
    parser.add_argument(
        "--coverage-json",
        type=Path,
        default=Path("coverage.json"),
        help="Path to coverage.json from `coverage json`",
    )
    args = parser.parse_args()

    if not args.coverage_json.is_file():
        print(f"Missing {args.coverage_json}; run `coverage json` first", file=sys.stderr)
        return 2

    data = json.loads(args.coverage_json.read_text(encoding="utf-8"))
    failures: list[str] = []
    for path, info in sorted(data.get("files", {}).items()):
        if "cupra_eu_data_act" not in path or not path.endswith(".py"):
            continue
        name = path.rsplit("cupra_eu_data_act/", 1)[-1]
        pct = float(info["summary"]["percent_covered"])
        if pct + 1e-9 < args.min:
            failures.append(f"{name}: {pct:.1f}%")

    if failures:
        print(f"Modules below {args.min:.0f}% coverage:", file=sys.stderr)
        for line in failures:
            print(f"  {line}", file=sys.stderr)
        return 1

    total = float(data["totals"]["percent_covered"])
    print(f"All modules ≥ {args.min:.0f}% (total {total:.1f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

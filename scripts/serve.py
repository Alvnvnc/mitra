#!/usr/bin/env python3
"""Run the Mitra dashboard.

    python scripts/serve.py                      # uses MITRA_DATA_DIR or data/
    MITRA_DATA_DIR=data/demo python scripts/serve.py --demo --port 8080

`--demo` turns on the rate limiter and the synthetic-data banner. For a public
demo also set MITRA_DASHBOARD_TOKEN so a random visitor cannot write memory.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    import mitra  # noqa: F401
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the Mitra dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--demo", action="store_true", help="enable demo mode + rate limits")
    parser.add_argument("--scheduler", action="store_true", help="enable the in-process scheduler")
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    if args.data_dir:
        os.environ["MITRA_DATA_DIR"] = str(Path(args.data_dir).resolve())
    if args.demo:
        os.environ["MITRA_DEMO_MODE"] = "1"
    if args.scheduler:
        os.environ["MITRA_ENABLE_SCHEDULER"] = "1"

    import uvicorn

    target = "mitra.web.app:create_app"
    if args.reload:
        uvicorn.run(target, factory=True, host=args.host, port=args.port, reload=True)
    else:
        from mitra.web.app import create_app

        uvicorn.run(create_app(), host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

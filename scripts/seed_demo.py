#!/usr/bin/env python3
"""Seed the synthetic demo instance.

All content is fictional and labelled as such in the UI. The code paths
(ledger, evidence gate, approval inbox, policy engine) are the real ones.

    python scripts/seed_demo.py --fresh
    MITRA_DATA_DIR=data/demo python scripts/serve.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import mitra  # noqa: F401
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mitra.demo_data import seed

DEFAULT_DIR = Path(__file__).resolve().parents[1] / "data" / "demo"


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed Mitra's synthetic demo data")
    parser.add_argument("--data-dir", default=str(DEFAULT_DIR))
    parser.add_argument("--fresh", action="store_true", help="delete the target directory first")
    args = parser.parse_args()
    root = seed(Path(args.data_dir), fresh=args.fresh)
    print(f"seeded synthetic demo at {root}")
    print(f'run:  MITRA_DATA_DIR="{root}" python scripts/serve.py')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

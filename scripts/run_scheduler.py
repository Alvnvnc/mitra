#!/usr/bin/env python3
"""Jalankan scheduler minimal Mitra.

    .venv/bin/python scripts/run_scheduler.py --once        # satu kali tick
    .venv/bin/python scripts/run_scheduler.py --interval 60 # terus-menerus

Scheduler memanggil pipeline yang sama dengan demo: resolusi instruksi ->
eksekusi skill -> gerbang bukti -> pengiriman. Satu komitmen gagal tidak
menghentikan loop; kegagalannya tercatat sebagai event + NOTICE.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import mitra  # noqa: F401
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mitra.config import get_settings
from mitra.ledger import Ledger
from mitra.models.router import ModelRouter
from mitra.scheduler import run_forever, tick


def main() -> int:
    parser = argparse.ArgumentParser(description="Scheduler minimal Mitra")
    parser.add_argument("--data-dir", default=None, help="default: MITRA_DATA_DIR dari .env")
    parser.add_argument("--interval", type=int, default=60, help="detik antar-tick")
    parser.add_argument("--once", action="store_true", help="jalankan satu tick lalu keluar")
    args = parser.parse_args()

    settings = get_settings()
    data_dir = Path(args.data_dir).resolve() if args.data_dir else Path(settings.mitra_data_dir)
    ledger = Ledger(data_dir / "ledger.db")
    try:
        router = ModelRouter()
    except RuntimeError as exc:
        print(f"router tidak tersedia: {exc}")
        ledger.close()
        return 2

    try:
        if args.once:
            outcomes = tick(ledger, router=router, outbox_dir=data_dir / "outbox")
            if not outcomes:
                print("tidak ada komitmen yang jatuh tempo.")
            for outcome in outcomes:
                print(f"{outcome.commitment_id} -> {outcome.state}: {outcome.detail}")
        else:
            run_forever(
                ledger,
                router=router,
                interval_s=args.interval,
                outbox_dir=data_dir / "outbox",
            )
    finally:
        ledger.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
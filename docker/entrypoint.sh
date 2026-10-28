#!/bin/sh
# Container entrypoint: seed the synthetic demo once, then hand over to CMD.
set -e

if [ "${MITRA_DEMO_MODE}" = "1" ] && [ ! -f "${MITRA_DATA_DIR}/ledger.db" ]; then
    echo "[mitra] empty data dir — seeding the synthetic demo"
    python scripts/seed_demo.py --data-dir "${MITRA_DATA_DIR}"
fi

exec "$@"

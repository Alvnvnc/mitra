#!/usr/bin/env python3
"""Demo irisan vertikal Mitra — satu alur lengkap: "ringkasan proyek harian".

Menunjukkan tiga janji (draf W2, menunggu gate W1):

  1. O1 — instruksi berversi: perubahan "mulai besok" tidak langsung berlaku;
     eksekusi selalu memakai versi yang efektif saat itu.
  2. O2 — gerbang bukti: ringkasan harus lolos cek deterministik sebelum
     status "selesai"; model tidak boleh mengklaim sendiri.
  3. O3 — pengiriman terpisah: hasil bisa terverifikasi tetapi gagal terkirim;
     kegagalan itu terlihat (fallback NOTICE + event), bukan senyap.

Jalankan:
    .venv/bin/python scripts/demo_vertical_slice.py --fresh

Tanpa TELEGRAM_BOT_TOKEN demo tetap berjalan penuh — justru memperlihatkan
tahap pengiriman yang gagal secara eksplisit.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    import mitra  # noqa: F401
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mitra.ledger import Ledger
from mitra.models.router import ModelRouter
from mitra.runner import run_commitment_once

TITLE = "Ringkasan proyek harian"
WIB = ZoneInfo("Asia/Jakarta")


def _hr(title: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def _wib(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=WIB).strftime("%Y-%m-%d %H:%M %Z")


def main() -> int:
    parser = argparse.ArgumentParser(description="Demo irisan vertikal Mitra")
    parser.add_argument("--data-dir", default=None, help="default: <repo>/data/demo")
    parser.add_argument("--fresh", action="store_true", help="hapus data demo dulu")
    parser.add_argument("--repo", default=None, help="repo yang dirangkum (default: repo ini)")
    args = parser.parse_args()

    repo_root = Path(args.repo).resolve() if args.repo else Path(__file__).resolve().parents[1]
    data_dir = Path(args.data_dir).resolve() if args.data_dir else repo_root / "data" / "demo"
    if args.fresh and data_dir.exists():
        shutil.rmtree(data_dir)
    ledger = Ledger(data_dir / "ledger.db")
    print(f"ledger: {data_dir / 'ledger.db'}")

    now = datetime.now(UTC).astimezone(WIB)

    # 1) komitmen ---------------------------------------------------------------
    _hr("1) Komitmen")
    existing = [c for c in ledger.list_commitments() if c.title == TITLE]
    if existing:
        commitment_id = existing[0].id
        print(f"memakai komitmen yang ada: {commitment_id}")
    else:
        commitment_id = ledger.add_commitment(
            title=TITLE,
            skill="daily_digest",
            schedule="07:30",
            timezone_name="Asia/Jakarta",
            delivery_channel="telegram",
        )
        print(f"komitmen dibuat: {commitment_id} (harian 07:30 WIB, kanal Telegram)")

    # 2) instruksi berversi ------------------------------------------------------
    _hr("2) Instruksi berversi (O1)")
    versions = ledger.list_instruction_versions(commitment_id)
    if not versions:
        v1 = ledger.add_instruction_version(
            commitment_id,
            content=(
                "Setiap hari 07:30 WIB: ringkasan progres proyek "
                "(bullet, Bahasa Indonesia, maks 150 kata), kirim ke Telegram."
            ),
            params={"max_words": 150, "since_hours": 72},
            effective_from=now - timedelta(days=1),
        )
        print(f"instruksi v1 dibuat (aktif): id={v1}")
        versions = ledger.list_instruction_versions(commitment_id)
    if len(versions) == 1:
        tomorrow_8 = (now + timedelta(days=1)).replace(
            hour=8, minute=0, second=0, microsecond=0
        )
        v2 = ledger.add_instruction_version(
            commitment_id,
            content="Mulai besok: kirim 08.00 WIB (bukan 07:30). Sisanya tetap.",
            params={"max_words": 150, "since_hours": 72},
            effective_from=tomorrow_8,
        )
        print(f"instruksi v2 dibuat (berlaku besok 08.00): id={v2}")
        versions = ledger.list_instruction_versions(commitment_id)

    print("\nversi instruksi tersimpan:")
    for version in versions:
        print(f"  v{version.id}: efektif {_wib(version.effective_from)} | {version.content[:64]}")

    resolved_now = ledger.resolve_instruction(commitment_id, at=now)
    check_next = (now + timedelta(days=1)).replace(hour=8, minute=30, second=0, microsecond=0)
    resolved_next = ledger.resolve_instruction(commitment_id, at=check_next)
    print(f"  -> resolusi sekarang    : v{resolved_now.id}")
    print(f"  -> resolusi besok 08:30 : v{resolved_next.id} (perubahan berlaku tepat waktu)")

    # 3) eksekusi ----------------------------------------------------------------
    _hr("3) Eksekusi nyata (fakta git -> Nemotron -> bukti)")
    try:
        router = ModelRouter()
    except RuntimeError as exc:
        print(f"tidak bisa membuat router: {exc}")
        print("salin .env.example ke .env dan isi NEBIUS_API_KEY.")
        ledger.close()
        return 2

    outcome = run_commitment_once(
        ledger,
        commitment_id,
        router=router,
        repo_root=repo_root,
        outbox_dir=data_dir / "outbox",
        now=now,
    )
    print(f"run_id            : {outcome.run_id}")
    print(f"instruksi dipakai : v{outcome.instruction_version_id}")
    print(f"status akhir      : {outcome.state}")
    print(f"detail            : {outcome.detail}")

    if outcome.run_id:
        # 4) bukti ---------------------------------------------------------------
        _hr("4) Bukti & hasil cek (O2)")
        for item in ledger.evidence_for_run(outcome.run_id):
            print(
                f"  #{item.id} {item.kind:8s} cek={item.check_result:7s} "
                f"sha256={(item.sha256 or '-')[:12]} | {item.check_detail[:70]}"
            )
            if item.path:
                print(f"       file: {item.path}")

        # 5) pengiriman ----------------------------------------------------------
        _hr("5) Pengiriman (O3)")
        run = ledger.get_run(outcome.run_id)
        print(f"status run   : {run.state}")
        print(f"delivered_at : {run.delivered_at}")
        print(f"receipt      : {run.delivery_receipt}")
        if outcome.notice_path:
            print(f"NOTICE       : {outcome.notice_path}")
            print("--- isi notice ---")
            print(outcome.notice_path.read_text(encoding="utf-8"))

        # 6) jejak ---------------------------------------------------------------
        _hr("6) Jejak event terakhir")
        for event in reversed(ledger.events(limit=10)):
            print(f"  {event['at']}  {event['kind']:18s} {event['detail'] or ''}")

    # 7) biaya --------------------------------------------------------------------
    _hr("7) Biaya inferensi")
    print(router.stats.summary())

    print("\nCatatan: tanpa TELEGRAM_BOT_TOKEN tahap pengiriman gagal dan itu TERLIHAT")
    print("(delivery_failed + NOTICE). Setelah token diisi, jalur yang sama mengirim nyata.")
    ledger.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
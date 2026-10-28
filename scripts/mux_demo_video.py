"""Compose the final walkthrough: title card, burned-in captions, end card.

    python scripts/mux_demo_video.py --raw /tmp/demo.webm --out docs/media/demo-walkthrough.mp4

Silent by design: the captions carry the storyline, so a voice-over can be added
later without fighting a second audio track.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / ".design" / "video"


def run(args: list[str]) -> None:
    subprocess.run(args, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", default="/tmp/opencode/demo-raw.webm")
    parser.add_argument("--out", default="docs/media/demo-walkthrough.mp4")
    parser.add_argument("--seconds", type=float, default=182.0)
    parser.add_argument("--crf", type=int, default=25)
    args = parser.parse_args()

    raw = Path(args.raw)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    captions = json.loads((ASSETS / "captions.json").read_text(encoding="utf-8"))
    title = ASSETS / "title.png"
    end = ASSETS / "end.png"
    for path in [title, end, *[Path(c["path"]) for c in captions]]:
        if not path.exists():
            raise SystemExit(f"missing asset: {path} — run scripts/build_video_assets.py")

    with tempfile.TemporaryDirectory(prefix="mitra-video-") as tmp:
        tmpdir = Path(tmp)
        main_clip = tmpdir / "main.mp4"
        end_clip = tmpdir / "end.mp4"

        # ---- body: title card + captions over the screen recording
        inputs: list[str] = ["-i", str(raw)]
        inputs += ["-loop", "1", "-i", str(title)]
        for caption in captions:
            inputs += ["-loop", "1", "-i", str(Path(caption["path"]))]

        filters = ["[0:v]scale=1440:900,setsar=1,fps=25[base]"]
        current = "base"
        # title card: 0 → 2.8s
        filters.append(f"[{current}][1:v]overlay=0:0:enable='between(t,0,2.8)'[v0]")
        current = "v0"
        for index, caption in enumerate(captions):
            node = f"c{index}"
            source = index + 2
            filters.append(
                f"[{current}][{source}:v]overlay=0:0:enable="
                f"'between(t,{caption['start']},{caption['end']})'[{node}]"
            )
            current = node
        filters.append(f"[{current}]format=yuv420p[vout]")

        run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                *inputs,
                "-filter_complex",
                ";".join(filters),
                "-map",
                "[vout]",
                "-t",
                str(args.seconds),
                "-c:v",
                "libx264",
                "-preset",
                "slow",
                "-crf",
                str(args.crf),
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                "-an",
                str(main_clip),
            ]
        )

        # ---- end card: 4s, fade in, same encoding parameters
        run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-loop",
                "1",
                "-t",
                "4",
                "-i",
                str(end),
                "-vf",
                "scale=1440:900,setsar=1,fps=25,fade=t=in:st=0:d=0.45,format=yuv420p",
                "-c:v",
                "libx264",
                "-preset",
                "slow",
                "-crf",
                str(args.crf),
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                "-an",
                str(end_clip),
            ]
        )

        # ---- concat
        listing = tmpdir / "list.txt"
        listing.write_text(
            f"file '{main_clip}'\nfile '{end_clip}'\n",
            encoding="utf-8",
        )
        run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(listing),
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(out),
            ]
        )

    size = out.stat().st_size / 1e6
    duration = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            str(out),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    print(f"wrote {out} ({size:.1f} MB, {float(duration):.1f}s)")
    if shutil.which("ffmpeg") is None:  # pragma: no cover - defensive
        raise SystemExit("ffmpeg disappeared")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

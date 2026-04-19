#!/usr/bin/env python3
"""
Burmese short-video caption tool.

Features:
- Reads SRT.
- Shortens long captions to a max character limit.
- Reflows long captions into multiple subtitle cues.
- Auto-adjusts cue timing when a caption is split.
- Burns subtitles into video with ffmpeg.
- Supports custom fonts dir, center/middle placement, text color, outline, and background box.
"""

from __future__ import annotations

import argparse
import os
import re
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List


SRT_PATTERN = re.compile(
    r"\s*(\d+)\s*\n"
    r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})\s*\n"
    r"(.*?)(?=\n\s*\n|\Z)",
    re.DOTALL,
)


@dataclass
class Cue:
    index: int
    start_ms: int
    end_ms: int
    text: str


def srt_time_to_ms(ts: str) -> int:
    hh, mm, rest = ts.split(":")
    ss, ms = rest.split(",")
    return (
        int(hh) * 3600 * 1000
        + int(mm) * 60 * 1000
        + int(ss) * 1000
        + int(ms)
    )


def ms_to_srt_time(ms: int) -> str:
    ms = max(0, ms)
    hh = ms // 3_600_000
    ms %= 3_600_000
    mm = ms // 60_000
    ms %= 60_000
    ss = ms // 1_000
    ms %= 1_000
    return f"{hh:02d}:{mm:02d}:{ss:02d},{ms:03d}"


def parse_srt(content: str) -> List[Cue]:
    cues: List[Cue] = []
    for m in SRT_PATTERN.finditer(content):
        idx = int(m.group(1))
        start = srt_time_to_ms(m.group(2))
        end = srt_time_to_ms(m.group(3))
        text = m.group(4).strip().replace("\n", " ")
        cues.append(Cue(idx, start, end, text))

    if not cues:
        raise ValueError("No valid SRT cues found. Please check input file format.")
    return cues


def split_text_to_chunks(text: str, max_chars: int) -> List[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return [""]

    words = text.split(" ")
    chunks: List[str] = []
    current = ""

    for word in words:
        if not current:
            if len(word) <= max_chars:
                current = word
            else:
                # fallback for very long token (no spaces)
                for i in range(0, len(word), max_chars):
                    part = word[i : i + max_chars]
                    if len(part) == max_chars:
                        chunks.append(part)
                    else:
                        current = part
        else:
            candidate = f"{current} {word}"
            if len(candidate) <= max_chars:
                current = candidate
            else:
                chunks.append(current)
                if len(word) <= max_chars:
                    current = word
                else:
                    for i in range(0, len(word), max_chars):
                        part = word[i : i + max_chars]
                        if len(part) == max_chars:
                            chunks.append(part)
                        else:
                            current = part

    if current:
        chunks.append(current)

    return chunks


def rebalance_min_chars(chunks: List[str], min_chars: int, max_chars: int) -> List[str]:
    if min_chars <= 0 or len(chunks) < 2:
        return chunks

    out = chunks[:]
    i = len(out) - 1
    while i > 0:
        if len(out[i]) < min_chars:
            combined = f"{out[i-1]} {out[i]}".strip()
            if len(combined) <= max_chars:
                out[i - 1] = combined
                del out[i]
        i -= 1

    return out


def split_cue(cue: Cue, max_chars: int, min_chars: int) -> List[Cue]:
    chunks = split_text_to_chunks(cue.text, max_chars)
    chunks = rebalance_min_chars(chunks, min_chars=min_chars, max_chars=max_chars)

    if len(chunks) == 1:
        return [Cue(cue.index, cue.start_ms, cue.end_ms, chunks[0])]

    total = max(1, cue.end_ms - cue.start_ms)
    lengths = [max(1, len(c)) for c in chunks]
    unit = total / sum(lengths)

    out: List[Cue] = []
    start = cue.start_ms
    for idx, (chunk, l) in enumerate(zip(chunks, lengths), start=1):
        if idx == len(chunks):
            end = cue.end_ms
        else:
            end = int(round(start + l * unit))
            if end <= start:
                end = start + 1
        out.append(Cue(0, start, end, chunk))
        start = end

    return out


def rebuild_cues(cues: Iterable[Cue], max_chars: int, min_chars: int) -> List[Cue]:
    merged: List[Cue] = []
    for cue in cues:
        merged.extend(split_cue(cue, max_chars=max_chars, min_chars=min_chars))

    for i, cue in enumerate(merged, start=1):
        cue.index = i
    return merged


def write_srt(cues: Iterable[Cue], path: Path) -> None:
    lines: List[str] = []
    for cue in cues:
        lines.append(str(cue.index))
        lines.append(f"{ms_to_srt_time(cue.start_ms)} --> {ms_to_srt_time(cue.end_ms)}")
        lines.append(cue.text)
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def ass_color(color: str, alpha: str = "00") -> str:
    m = {
        "white": "FFFFFF",
        "black": "000000",
        "red": "FF0000",
        "green": "00FF00",
        "yellow": "FFFF00",
    }
    rgb = m[color.lower()]
    rr, gg, bb = rgb[0:2], rgb[2:4], rgb[4:6]
    return f"&H{alpha}{bb}{gg}{rr}"


def build_subtitles_filter(
    srt_path: Path,
    fonts_dir: Path | None,
    font_name: str | None,
    text_color: str,
    outline_color: str,
    bg_color: str,
    outline: float,
    use_box: bool,
    font_size: int,
    margin_v: int,
) -> str:
    style = [
        "Alignment=5",  # middle center
        f"Fontsize={font_size}",
        f"PrimaryColour={ass_color(text_color)}",
        f"OutlineColour={ass_color(outline_color)}",
        f"BackColour={ass_color(bg_color, alpha='40')}",
        f"Outline={outline}",
        "Shadow=0",
        f"MarginV={margin_v}",
        f"BorderStyle={3 if use_box else 1}",
    ]
    if font_name:
        style.append(f"FontName={font_name}")

    srt_escaped = str(srt_path).replace("\\", "/").replace(":", "\\:")
    parts = [f"subtitles='{srt_escaped}'"]

    if fonts_dir:
        fonts_escaped = str(fonts_dir).replace("\\", "/").replace(":", "\\:")
        parts.append(f"fontsdir='{fonts_escaped}'")

    parts.append(f"force_style='{','.join(style)}'")
    return ":".join(parts)


def run_ffmpeg(input_video: Path, output_video: Path, subtitles_filter: str, crf: int, preset: str) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_video),
        "-vf",
        subtitles_filter,
        "-c:v",
        "libx264",
        "-preset",
        preset,
        "-crf",
        str(crf),
        "-c:a",
        "copy",
        str(output_video),
    ]

    print("Running:")
    print(" ".join(shlex.quote(c) for c in cmd))
    proc = subprocess.run(cmd)
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg failed. Make sure ffmpeg is installed and available in PATH.")


def validate_path(path: Path, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{label} not found: {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Shorten Burmese SRT and burn into video with ffmpeg.")
    parser.add_argument("--input-video", required=True, type=Path)
    parser.add_argument("--input-srt", required=True, type=Path)
    parser.add_argument("--output-video", required=True, type=Path)

    parser.add_argument("--max-chars", type=int, default=18, help="Maximum characters per caption chunk.")
    parser.add_argument("--min-chars", type=int, default=0, help="Optional minimum characters when rebalancing chunks.")

    parser.add_argument("--fonts-dir", type=Path, default=None, help="Folder containing custom font files.")
    parser.add_argument("--font-name", type=str, default=None, help="Exact font family name for ASS style.")

    parser.add_argument("--text-color", choices=["red", "green", "yellow", "white", "black"], default="white")
    parser.add_argument("--outline-color", choices=["red", "green", "yellow", "white", "black"], default="black")
    parser.add_argument("--bg-color", choices=["red", "green", "yellow", "white", "black"], default="black")
    parser.add_argument("--outline", type=float, default=2.0)
    parser.add_argument("--use-box", action="store_true", help="Enable opaque background box behind captions.")

    parser.add_argument("--font-size", type=int, default=18)
    parser.add_argument("--margin-v", type=int, default=20, help="Vertical margin from center anchoring.")

    parser.add_argument("--preset", default="medium", help="ffmpeg x264 preset.")
    parser.add_argument("--crf", type=int, default=20, help="ffmpeg CRF quality (lower is higher quality).")

    parser.add_argument(
        "--save-processed-srt",
        type=Path,
        default=None,
        help="Optional output path for processed/shortened SRT. Defaults to temp file.",
    )

    args = parser.parse_args()

    validate_path(args.input_video, "Input video")
    validate_path(args.input_srt, "Input SRT")
    if args.fonts_dir is not None:
        validate_path(args.fonts_dir, "Fonts directory")

    if args.max_chars <= 0:
        raise ValueError("--max-chars must be > 0")
    if args.min_chars < 0:
        raise ValueError("--min-chars must be >= 0")

    raw_srt = args.input_srt.read_text(encoding="utf-8-sig")
    cues = parse_srt(raw_srt)
    processed = rebuild_cues(cues, max_chars=args.max_chars, min_chars=args.min_chars)

    temp_file = None
    out_srt = args.save_processed_srt
    if out_srt is None:
        tmp = tempfile.NamedTemporaryFile(prefix="processed_", suffix=".srt", delete=False)
        temp_file = Path(tmp.name)
        tmp.close()
        out_srt = temp_file

    write_srt(processed, out_srt)

    subtitles_filter = build_subtitles_filter(
        srt_path=out_srt,
        fonts_dir=args.fonts_dir,
        font_name=args.font_name,
        text_color=args.text_color,
        outline_color=args.outline_color,
        bg_color=args.bg_color,
        outline=args.outline,
        use_box=args.use_box,
        font_size=args.font_size,
        margin_v=args.margin_v,
    )

    try:
        run_ffmpeg(
            input_video=args.input_video,
            output_video=args.output_video,
            subtitles_filter=subtitles_filter,
            crf=args.crf,
            preset=args.preset,
        )
    finally:
        if temp_file and temp_file.exists():
            os.unlink(temp_file)

    print(f"Done. Output video: {args.output_video}")
    if args.save_processed_srt:
        print(f"Processed SRT saved: {args.save_processed_srt}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)

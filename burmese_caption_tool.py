#!/usr/bin/env python3
"""
Burmese short-video caption tool.

Features:
- Reads SRT.
- Shortens long captions by splitting at word boundaries (spaces only).
- Never breaks individual words - keeps them intact.
- Auto-adjusts cue timing when a caption is split.
- Burns subtitles into video with ffmpeg.
- Supports custom fonts dir, center/middle placement, text color, outline, and background box.
- Auto-detects font name from TTF files.
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
from typing import Iterable, List, Optional


try:
    from fontTools.ttLib import TTFont
    HAS_FONTTOOLS = True
except ImportError:
    HAS_FONTTOOLS = False


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


def split_at_spaces_only(text: str, max_len: int) -> List[str]:
    """
    Split text at spaces only. Never breaks individual words.
    If a single word is longer than max_len, it stays as one caption.
    """
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return [""]

    words = text.split(" ")
    chunks: List[str] = []
    current = ""
    current_len = 0

    for word in words:
        word = word.strip()
        if not word:
            continue
        
        word_len = len(word)
        
        if not current:
            current = word
            current_len = word_len
        elif current_len + 1 + word_len <= max_len:
            current = current + " " + word
            current_len = current_len + 1 + word_len
        else:
            # Start new chunk with this word
            chunks.append(current)
            current = word
            current_len = word_len

    if current:
        chunks.append(current)

    return chunks


def split_cue(cue: Cue, max_len: int) -> List[Cue]:
    """
    Split a cue at word boundaries only.
    """
    text = cue.text.strip()
    if not text:
        return [Cue(cue.index, cue.start_ms, cue.end_ms, "")]
    
    if len(text) <= max_len:
        return [Cue(cue.index, cue.start_ms, cue.end_ms, text)]

    chunks = split_at_spaces_only(text, max_len)

    if len(chunks) == 1:
        return [Cue(cue.index, cue.start_ms, cue.end_ms, chunks[0])]

    # Distribute timing proportionally by character count
    total_duration = max(1, cue.end_ms - cue.start_ms)
    chunk_lengths = [len(c) for c in chunks]
    total_len = sum(chunk_lengths)
    
    out: List[Cue] = []
    start = cue.start_ms
    
    for i, chunk in enumerate(chunks):
        if i == len(chunks) - 1:
            end = cue.end_ms
        else:
            duration = int((chunk_lengths[i] / total_len) * total_duration)
            end = min(start + duration, cue.end_ms - 1)
            if end <= start:
                end = start + 1
        
        out.append(Cue(0, start, end, chunk))
        start = end

    return out


def rebuild_cues(cues: Iterable[Cue], max_len: int) -> List[Cue]:
    """
    Rebuild cues by splitting long captions at spaces only.
    """
    merged: List[Cue] = []
    for cue in cues:
        if len(cue.text) <= max_len:
            merged.append(Cue(0, cue.start_ms, cue.end_ms, cue.text))
        else:
            merged.extend(split_cue(cue, max_len))

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


def get_font_name_from_ttf(font_path: Path) -> Optional[str]:
    """
    Extract the font family name from a TTF file using fontTools.
    """
    if not HAS_FONTTOOLS:
        return None
    
    try:
        font = TTFont(str(font_path))
        # Get the best family name
        family_name = font['name'].getBestFamilyName()
        font.close()
        return family_name
    except Exception as e:
        print(f"Warning: Could not read font name from {font_path}: {e}")
        return None


def find_font_in_directory(fonts_dir: Path) -> tuple[Optional[Path], Optional[str]]:
    """
    Find the first TTF file in a directory and return its path and name.
    Returns (font_path, font_name) or (None, None) if no TTF found.
    """
    if not fonts_dir.exists():
        return None, None
    
    # Look for TTF files recursively
    ttf_files = list(fonts_dir.rglob("*.ttf")) + list(fonts_dir.rglob("*.TTF"))
    
    if not ttf_files:
        return None, None
    
    # Use the first TTF file found
    font_path = ttf_files[0]
    
    # Try to get the actual font name from the file
    if HAS_FONTTOOLS:
        font_name = get_font_name_from_ttf(font_path)
        if font_name:
            return font_path.parent, font_name
    
    # Fallback: use the filename without extension
    font_name = font_path.stem
    return font_path.parent, font_name


def build_subtitles_filter(
    srt_path: Path,
    fonts_dir: Optional[Path],
    font_name: Optional[str],
    text_color: str,
    outline_color: str,
    bg_color: str,
    outline: float,
    use_box: bool,
    font_size: int,
    margin_v: int,
) -> str:
    style = [
        "Alignment=10",  # middle center for 9:16 videos
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

    parser.add_argument("--max-len", type=int, default=14, 
                       help="Maximum characters per caption chunk (default 14).")
    parser.add_argument("--font-size", type=int, default=14,
                       help="Font size (default 14).")

    parser.add_argument("--fonts-dir", type=Path, default=None, 
                       help="Folder containing custom font files. Will auto-detect font name if not specified.")
    parser.add_argument("--font-name", type=str, default=None, 
                       help="Exact font family name for ASS style. Auto-detected from TTF if not provided.")

    parser.add_argument("--text-color", choices=["red", "green", "yellow", "white", "black"], default="white")
    parser.add_argument("--outline-color", choices=["red", "green", "yellow", "white", "black"], default="black")
    parser.add_argument("--bg-color", choices=["red", "green", "yellow", "white", "black"], default="black")
    parser.add_argument("--outline", type=float, default=1.5)
    parser.add_argument("--use-box", action="store_true", help="Enable opaque background box behind captions.")

    parser.add_argument("--margin-v", type=int, default=50, help="Vertical margin from center.")

    parser.add_argument("--preset", default="medium", help="ffmpeg x264 preset.")
    parser.add_argument("--crf", type=int, default=20, help="ffmpeg CRF quality (lower is higher quality).")

    parser.add_argument(
        "--save-processed-srt",
        type=Path,
        default=None,
        help="Optional output path for processed/shortened SRT.",
    )

    args = parser.parse_args()

    validate_path(args.input_video, "Input video")
    validate_path(args.input_srt, "Input SRT")
    if args.fonts_dir is not None:
        validate_path(args.fonts_dir, "Fonts directory")

    if args.max_len <= 0:
        raise ValueError("--max-len must be > 0")

    # Auto-detect font if directory provided but no font name
    fonts_dir = args.fonts_dir
    font_name = args.font_name
    
    if fonts_dir and not font_name:
        detected_dir, detected_name = find_font_in_directory(fonts_dir)
        if detected_name:
            fonts_dir = detected_dir
            font_name = detected_name
            print(f"Auto-detected font: {font_name}")
            print(f"Font directory: {fonts_dir}")
        else:
            print(f"Warning: Could not auto-detect font name from {fonts_dir}")

    raw_srt = args.input_srt.read_text(encoding="utf-8-sig")
    cues = parse_srt(raw_srt)
    processed = rebuild_cues(cues, max_len=args.max_len)

    temp_file = None
    out_srt = args.save_processed_srt
    if out_srt is None:
        tmp = tempfile.NamedTemporaryFile(prefix="processed_", suffix=".srt", delete=False)
        temp_file = Path(tmp.name)
        tmp.close()
        out_srt = temp_file

    write_srt(processed, out_srt)
    print(f"Processed {len(cues)} original cues into {len(processed)} output cues")

    subtitles_filter = build_subtitles_filter(
        srt_path=out_srt,
        fonts_dir=fonts_dir,
        font_name=font_name,
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

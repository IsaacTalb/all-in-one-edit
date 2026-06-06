"""Stage command runners for the daily pipeline."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Tuple

from pipeline_paths import GCLOUD_SRT_DIR, PROJECT_ROOT, RAW_AUDIO_DIR, RAW_SCRIPT_MM_DIR, RAW_SRT_DIR, RAW_VIDEO_DIR, RESULTS_DIR
from pipeline_utils import run_command



def download_video(url: str, output_path: Path, logger) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "yt-dlp",
        "-o",
        str(output_path),
        url,
    ]
    run_command(cmd, logger, cwd=PROJECT_ROOT)
    return output_path



def extract_mp3(video_path: Path, output_path: Path, logger) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-acodec",
        "libmp3lame",
        str(output_path),
    ]
    run_command(cmd, logger, cwd=PROJECT_ROOT)
    return output_path



def transcribe_audio(audio_path: Path, output_path: Path, logger) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    whisper_exe = os.environ.get("WHISPER_EXE", "whisper")
    model = os.environ.get("WHISPER_MODEL", "small")
    cmd = [
        whisper_exe,
        str(audio_path),
        "--model",
        model,
        "--output_format",
        "srt",
        "--output_dir",
        str(output_path.parent),
    ]
    run_command(cmd, logger, cwd=PROJECT_ROOT)
    produced = output_path.parent / f"{audio_path.stem}.srt"
    if produced.exists() and produced != output_path:
        produced.replace(output_path)
    return output_path



def convert_srt_to_burmese_script(srt_path: Path, output_path: Path, logger) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    gemini_script = PROJECT_ROOT / "raw_video_and_SRT" / "raw_script_mm_codex" / "raw_script_mm_codex.py"
    cmd = [
        "python",
        str(gemini_script),
        str(srt_path),
        str(output_path),
    ]
    run_command(cmd, logger, cwd=PROJECT_ROOT)
    return output_path



def generate_gcloud_audio_and_better_srt(script_path: Path, audio_output: Path, srt_output: Path, logger) -> Tuple[Path, Path]:
    audio_output.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "python",
        str(PROJECT_ROOT / "raw_video_and_SRT" / "raw_gcloud_audio_and_genai_srt" / "gcloud_audio_and_genai_srt.py"),
        str(script_path),
        str(audio_output),
        str(srt_output),
    ]
    run_command(cmd, logger, cwd=PROJECT_ROOT)
    return audio_output, srt_output



def build_final_video(video_path: Path, srt_path: Path, output_path: Path, logger) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "python",
        str(PROJECT_ROOT / "burmese_caption_tool.py"),
        "--input-video",
        str(video_path),
        "--input-srt",
        str(srt_path),
        "--output-video",
        str(output_path),
        "--fonts-dir",
        str(PROJECT_ROOT / "MMFreeFonts_CC"),
        "--use-box",
        "--save-processed-srt",
        str(output_path.with_suffix(".processed.srt")),
    ]
    run_command(cmd, logger, cwd=PROJECT_ROOT)
    return output_path

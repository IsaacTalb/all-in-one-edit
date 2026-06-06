"""Shared path and stage configuration for the all-in-one-edit pipeline.

This module centralizes the workflow directories so every stage script can use the
same filesystem layout.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(r"C:\isc-kfc\all-in-one-edit")
RAW_ROOT = PROJECT_ROOT / "raw_video_and_SRT"
RESULTS_DIR = PROJECT_ROOT / "results"

RAW_VIDEO_DIR = RAW_ROOT / "raw_video" / "raw_video_folder"
RAW_AUDIO_DIR = RAW_ROOT / "raw_audio_eng_mp3" / "audio_eng_mp3_folder"
RAW_SRT_DIR = RAW_ROOT / "raw_srt_eng_whisper"
RAW_SCRIPT_MM_DIR = RAW_ROOT / "raw_script_mm_codex" / "raw_script_mm_codex_folder"
GCLOUD_SRT_DIR = RAW_ROOT / "raw_gcloud_audio_and_genai_srt" / "gcloud_audio_and_genai_srt_folder"

GOOGLE_SHEET_ID_ENV = "GOOGLE_SHEET_ID"
GEMINI_API_KEY_ENV = "GEMINI_API_KEY"
GOOGLE_APPLICATION_CREDENTIALS_ENV = "GOOGLE_APPLICATION_CREDENTIALS"


@dataclass(frozen=True)
class PipelineItem:
    row_id: str
    url: str
    status: str
    source_name: str = ""


def ensure_directories() -> None:
    for path in [
        RAW_ROOT,
        RESULTS_DIR,
        RAW_VIDEO_DIR,
        RAW_AUDIO_DIR,
        RAW_SRT_DIR,
        RAW_SCRIPT_MM_DIR,
        GCLOUD_SRT_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)


__all__ = [
    "PROJECT_ROOT",
    "RAW_ROOT",
    "RESULTS_DIR",
    "RAW_VIDEO_DIR",
    "RAW_AUDIO_DIR",
    "RAW_SRT_DIR",
    "RAW_SCRIPT_MM_DIR",
    "GCLOUD_SRT_DIR",
    "GOOGLE_SHEET_ID_ENV",
    "GEMINI_API_KEY_ENV",
    "GOOGLE_APPLICATION_CREDENTIALS_ENV",
    "PipelineItem",
    "ensure_directories",
]

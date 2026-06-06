"""Daily orchestration entrypoint for the all-in-one-edit workflow."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, List, Sequence

from pipeline_paths import (
    GCLOUD_SRT_DIR,
    RAW_AUDIO_DIR,
    RAW_ROOT,
    RAW_SCRIPT_MM_DIR,
    RAW_SRT_DIR,
    RAW_VIDEO_DIR,
    RESULTS_DIR,
    PipelineItem,
    ensure_directories,
)
from pipeline_utils import build_logger, retry
from sheets_integration import SheetsError, fetch_sheet_rows, update_sheet_row_status
from stages import (
    build_final_video,
    convert_srt_to_burmese_script,
    download_video,
    extract_mp3,
    generate_gcloud_audio_and_better_srt,
    transcribe_audio,
)


DEFAULT_DAILY_BATCH_SIZE = 5
STATE_FILE = RAW_ROOT / "pipeline_state.json"
LOG_FILE = RAW_ROOT / "logs" / "daily_pipeline.log"


@dataclass
class StageResult:
    name: str
    ok: bool
    detail: str = ""



def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"runs": []}



def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")



def discover_pending_items(sheet_rows: Sequence[dict], limit: int = DEFAULT_DAILY_BATCH_SIZE) -> List[PipelineItem]:
    pending: List[PipelineItem] = []
    for row in sheet_rows:
        status = str(row.get("Status", "")).strip().lower()
        if status != "pending":
            continue
        pending.append(
            PipelineItem(
                row_id=str(row.get("RowID", row.get("id", ""))),
                url=str(row.get("URL", row.get("url", ""))).strip(),
                status="Pending",
                source_name=str(row.get("Title", row.get("title", ""))).strip(),
            )
        )
        if len(pending) >= limit:
            break
    return pending



def run_pipeline(items: Iterable[PipelineItem], logger) -> List[StageResult]:
    ensure_directories()
    results: List[StageResult] = []
    for index, item in enumerate(items, start=1):
        logger.info("Processing item %s: %s", index, item.url)
        try:
            video_path = retry(lambda: download_video(item.url, RAW_VIDEO_DIR / f"raw_video_{index}.mp4", logger), logger=logger)
            audio_path = retry(lambda: extract_mp3(video_path, RAW_AUDIO_DIR / f"raw_audio_eng_{index}.mp3", logger), logger=logger)
            srt_path = retry(lambda: transcribe_audio(audio_path, RAW_SRT_DIR / f"raw_srt_eng_{index}.srt", logger), logger=logger)
            script_path = retry(lambda: convert_srt_to_burmese_script(srt_path, RAW_SCRIPT_MM_DIR / f"raw_script_mm_{index}.txt", logger), logger=logger)
            gcloud_audio_path = GCLOUD_SRT_DIR / f"gcloud_audio_{index}.mp3"
            gcloud_srt_path = GCLOUD_SRT_DIR / f"gcloud_srt_{index}.srt"
            retry(lambda: generate_gcloud_audio_and_better_srt(script_path, gcloud_audio_path, gcloud_srt_path, logger), logger=logger)
            final_video = retry(lambda: build_final_video(video_path, gcloud_srt_path, RESULTS_DIR / f"final_content_{index}.mp4", logger), logger=logger)
            results.append(StageResult(name=f"item_{index}", ok=True, detail=f"final={final_video.name}"))
        except Exception as exc:
            results.append(StageResult(name=f"item_{index}", ok=False, detail=str(exc)))
            raise
    return results



def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Daily orchestrator for the all-in-one-edit workflow.")
    parser.add_argument("--dry-run", action="store_true", help="Only inspect rows and persist state.")
    parser.add_argument("--limit", type=int, default=DEFAULT_DAILY_BATCH_SIZE, help="Number of pending rows to process.")
    parser.add_argument("--sheet-id", default=None, help="Google Sheet ID override.")
    parser.add_argument("--worksheet", default="Sheet1", help="Worksheet/tab name.")
    return parser



def main() -> int:
    args = build_arg_parser().parse_args()
    ensure_directories()
    logger = build_logger(LOG_FILE)

    state = load_state()

    sheet_id = args.sheet_id or __import__("os").environ.get("GOOGLE_SHEET_ID")
    if not sheet_id:
        raise RuntimeError("GOOGLE_SHEET_ID is required.")

    rows = fetch_sheet_rows(sheet_id, args.worksheet)
    items = discover_pending_items(rows, limit=args.limit)

    if not items:
        state["runs"].append({"items": [], "status": "no-pending-items"})
        save_state(state)
        return 0

    if args.dry_run:
        state["runs"].append({"items": [asdict(item) for item in items], "status": "dry-run", "staged": True})
        save_state(state)
        return 0

    run_results = run_pipeline(items, logger)
    for item in items:
        if item.row_id:
            update_sheet_row_status(sheet_id, args.worksheet, item.row_id, "Done")

    state["runs"].append({
        "items": [asdict(item) for item in items],
        "status": "completed",
        "results": [asdict(result) for result in run_results],
    })
    save_state(state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

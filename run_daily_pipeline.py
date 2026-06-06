"""Entry point for the daily all-in-one-edit pipeline."""

from __future__ import annotations

import argparse
from pathlib import Path

from daily_pipeline import main as run_daily_pipeline
from pipeline_utils import build_logger



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the daily content pipeline.")
    parser.add_argument("--log-file", type=Path, default=Path(r"C:\isc-kfc\all-in-one-edit\logs\daily_pipeline.log"))
    return parser



def main() -> int:
    args = build_parser().parse_args()
    build_logger(args.log_file)
    return run_daily_pipeline()


if __name__ == "__main__":
    raise SystemExit(main())

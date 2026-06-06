"""Utility helpers for stage execution and retries."""

from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path
from typing import Iterable, Sequence


LOGGER_NAME = "all_in_one_edit"



def build_logger(log_path: Path | None = None) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    logger.addHandler(stream)

    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger



def run_command(command: Sequence[str], logger: logging.Logger, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    logger.info("Running command: %s", " ".join(command))
    completed = subprocess.run(command, cwd=str(cwd) if cwd else None, capture_output=True, text=True)
    if completed.stdout:
        logger.info(completed.stdout.strip())
    if completed.stderr:
        logger.warning(completed.stderr.strip())
    if completed.returncode != 0:
        raise subprocess.CalledProcessError(completed.returncode, command, completed.stdout, completed.stderr)
    return completed



def retry(fn, *, attempts: int = 3, delay_seconds: float = 2.0, logger: logging.Logger | None = None):
    last_exc = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:  # pragma: no cover - helper scaffold
            last_exc = exc
            if logger:
                logger.warning("Attempt %s/%s failed: %s", attempt, attempts, exc)
            if attempt < attempts:
                time.sleep(delay_seconds)
    raise last_exc

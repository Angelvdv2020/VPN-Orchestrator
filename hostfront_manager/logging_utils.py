from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path


def setup_logging(log_dir: Path, debug: bool = False) -> tuple[logging.Logger, Path]:
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        log_dir = Path("./logs")
        log_dir.mkdir(parents=True, exist_ok=True)

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_file = log_dir / f"run-{run_id}.log"

    logger = logging.getLogger("hostfront-manager")
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    sh = logging.StreamHandler()
    sh.setLevel(logging.DEBUG if debug else logging.INFO)
    sh.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(sh)

    return logger, log_file

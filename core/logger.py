"""실행 로그 + 실패 기사 덤프."""
import json
import logging
from datetime import datetime
from pathlib import Path

import config


def get_logger(name: str = "trend") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    today = datetime.now().strftime("%Y%m%d")
    fh = logging.FileHandler(config.LOG_DIR / f"collect_{today}.log", encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    return logger


def dump_failed(stage: str, payload: dict) -> None:
    """실패 기사/단계 원본을 data/failed/ 에 저장."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path: Path = config.FAILED_DIR / f"{stage}_{ts}.json"
    try:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                        encoding="utf-8")
    except Exception:
        pass

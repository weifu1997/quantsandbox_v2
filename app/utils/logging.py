from __future__ import annotations

import logging


def setup_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_duration(logger: logging.Logger, label: str, seconds: float, extra: dict | None = None) -> None:
    payload = extra or {}
    logger.info("%s finished in %.3fs | %s", label, seconds, payload)

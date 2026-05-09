from __future__ import annotations

import logging


LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def configure_logging(level_name: str) -> None:
    """Configure lightweight console logging for backend and uvicorn loggers."""
    level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format=LOG_FORMAT,
    )
    logging.getLogger("backend").setLevel(level)
    logging.getLogger("uvicorn").setLevel(level)

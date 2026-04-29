from __future__ import annotations

import json
import logging
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
from queue import Queue
from typing import Any

from backend2.config import DEFAULT_LOG_LEVEL, LOG_FILE_PATH


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "timestamp": self.formatTime(record, self.datefmt),
        }
        if hasattr(record, "event"):
            payload["event"] = record.event
        if hasattr(record, "extra_data") and isinstance(record.extra_data, dict):
            payload.update(record.extra_data)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


_queue_listener: QueueListener | None = None


def configure_logging() -> None:
    global _queue_listener

    LOG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(DEFAULT_LOG_LEVEL.upper())

    if root_logger.handlers:
        return

    queue: Queue = Queue(-1)
    queue_handler = QueueHandler(queue)

    stream_handler = logging.StreamHandler()
    file_handler = RotatingFileHandler(LOG_FILE_PATH, maxBytes=2_000_000, backupCount=5, encoding="utf-8")

    formatter = JsonFormatter()
    stream_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)

    _queue_listener = QueueListener(queue, stream_handler, file_handler, respect_handler_level=True)
    _queue_listener.start()

    root_logger.addHandler(queue_handler)


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)

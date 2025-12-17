from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Iterable, Optional


def build_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """기본 로거를 생성합니다(노트북/스크립트 공용)."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(level)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(handler)
    return logger


@dataclass(frozen=True)
class RetryConfig:
    """네트워크/페이지 로딩 등 재시도 설정."""

    max_retries: int = 3
    base_sleep_sec: float = 0.7
    max_sleep_sec: float = 5.0


def sleep_backoff(attempt: int, base: float = 0.7, max_sleep: float = 5.0) -> None:
    """재시도 간격(선형 backoff)을 적용합니다."""
    delay = min(max_sleep, base * attempt)
    time.sleep(delay)


def first_non_empty(values: Iterable[Optional[str]]) -> str:
    """여러 후보 중 첫 번째 유효(비어있지 않은) 문자열을 반환합니다."""
    for v in values:
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return ""


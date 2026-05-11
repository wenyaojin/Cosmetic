import logging
import sys
from app.core.config import get_settings


def setup_logging() -> logging.Logger:
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger("cosmetic")
    root.setLevel(level)
    root.addHandler(handler)
    root.propagate = False
    return root


logger = setup_logging()


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"cosmetic.{name}")

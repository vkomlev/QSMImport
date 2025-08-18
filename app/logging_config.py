import logging
import os
from logging.handlers import RotatingFileHandler
from .config import Settings


def setup_logging(settings: Settings) -> None:
    """
    Конфигурирует логирование:
    - Уровень из settings.log_level
    - RotatingFileHandler: 3 копии по 5MB
    - Формат: время, уровень, модуль, сообщение
    """
    os.makedirs(settings.log_dir, exist_ok=True)
    log_path = os.path.join(settings.log_dir, settings.log_file)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = RotatingFileHandler(
        log_path,
        maxBytes=settings.log_max_bytes,
        backupCount=settings.log_backup_count,
        encoding="utf-8",
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    root.handlers.clear()
    root.addHandler(handler)

    # Доп: дублировать в консоль при запуске CLI
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

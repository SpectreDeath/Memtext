"""Logging configuration for memtext."""

import logging
import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Optional


DEFAULT_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def get_log_dir() -> Path:
    """Get the logging directory."""
    log_dir = Path.cwd() / ".context" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def setup_logger(
    name: str = "memtext",
    level: int = logging.INFO,
    log_file: Optional[Path] = None,
    json_format: bool = False,
) -> logging.Logger:
    """Set up a logger with file and console handlers.

    Args:
        name: Logger name
        level: Logging level
        log_file: Optional path to log file
        json_format: Use JSON formatting for file logs

    Returns:
        Configured logger
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if logger.handlers:
        logger.handlers.clear()

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)
    console_formatter = logging.Formatter(DEFAULT_FORMAT, DATE_FORMAT)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)

        if json_format:

            class JSONFormatter(logging.Formatter):
                def format(self, record):
                    return json.dumps(
                        {
                            "timestamp": datetime.now().isoformat(),
                            "level": record.levelname,
                            "name": record.name,
                            "message": record.getMessage(),
                            "module": record.module,
                            "function": record.funcName,
                            "line": record.lineno,
                        }
                    )

            file_formatter: logging.Formatter = JSONFormatter()
        else:
            file_formatter = logging.Formatter(DEFAULT_FORMAT, DATE_FORMAT)

        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    return logger


def get_default_logger() -> logging.Logger:
    """Get the default memtext logger."""
    return logging.getLogger("memtext")


def configure_from_env():
    """Configure logging from environment variables.

    Environment variables:
        MEMTEXT_LOG_LEVEL: DEBUG, INFO, WARNING, ERROR
        MEMTEXT_LOG_FILE: Path to log file
        MEMTEXT_LOG_JSON: Use JSON format (true/false)
    """
    import os

    level_name = os.environ.get("MEMTEXT_LOG_LEVEL", "INFO")
    level = getattr(logging, level_name.upper(), logging.INFO)

    log_file_path = os.environ.get("MEMTEXT_LOG_FILE")
    log_file = Path(log_file_path) if log_file_path else None

    json_format = os.environ.get("MEMTEXT_LOG_JSON", "false").lower() == "true"

    return setup_logger(
        name="memtext",
        level=level,
        log_file=log_file,
        json_format=json_format,
    )


class LogContext:
    """Context manager for temporary log level changes."""

    def __init__(self, logger: logging.Logger, level: int):
        self.logger = logger
        self.level = level
        self.old_level: Optional[int] = None

    def __enter__(self):
        self.old_level = self.logger.level
        self.logger.setLevel(self.level)
        return self.logger

    def __exit__(self, exc_type, exc_val, exc_tb):
        assert self.old_level is not None, "old_level should be set in __enter__"
        self.logger.setLevel(self.old_level)


def log_command(command: str, args: Optional[dict] = None):
    """Log a command execution.

    Args:
        command: Command name
        args: Command arguments
    """
    logger = get_default_logger()
    logger.info(f"Command: {command}")
    if args:
        logger.debug(f"Args: {args}")


def log_error(error: Exception, context: Optional[str] = None):
    """Log an error with context.

    Args:
        error: Exception that occurred
        context: Additional context about where the error occurred
    """
    logger = get_default_logger()
    msg = f"Error: {type(error).__name__}: {error}"
    if context:
        msg = f"{context}: {msg}"
    logger.error(msg, exc_info=True)

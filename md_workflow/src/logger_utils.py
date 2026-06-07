import logging
import sys


class ColorFormatter(logging.Formatter):
    # ANSI Escape Codes
    grey = "\x1b[38;20m"
    blue = "\x1b[34;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    format_str = "%(asctime)s: %(message)s"

    FORMATS = {
        logging.DEBUG: grey + format_str + reset,
        logging.INFO: blue + format_str + reset,
        logging.WARNING: yellow + format_str + reset,
        logging.ERROR: red + format_str + reset,
        logging.CRITICAL: bold_red + format_str + reset,
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


def setup_logger(name=None, log_path=None):
    """Sets up a logger. If name is None, configures the root logger."""
    logger = logging.getLogger(name)
    # Clear existing handlers to avoid duplicates
    if logger.hasHandlers():
        logger.handlers.clear()

    logger.setLevel(logging.INFO)
    
    # Console Handler
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(ColorFormatter())
    logger.addHandler(stream_handler)

    # File Handler
    if log_path:
        file_handler = logging.FileHandler(log_path, mode='a')
        # Plain formatter for file (no ANSI colors)
        file_formatter = logging.Formatter("%(asctime)s: %(message)s")
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    if name is not None:
        logger.propagate = False

    # If this is the root logger, prevent other libraries from being too chatty
    if name is None:
        logging.getLogger("rdkit").setLevel(logging.WARNING)

    return logger

import sys
import logging
import logging.config
import environ

env = environ.Env()

LOGGING_LEVEL = env.str("LOGGING_LEVEL", "INFO")

DEFAULT_LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "format": "%(asctime)s %(levelname)s %(processName)s %(thread)d %(name)s %(message)s",
            "class": "pythonjsonlogger.jsonlogger.JsonFormatter",
        },
    },
    "handlers": {
        "console": {
            "level": LOGGING_LEVEL,
            "class": "logging.StreamHandler",
            "stream": sys.stdout,
            "formatter": "json",
        },
    },
    "loggers": {
        "": {
            "handlers": ["console"],
            "level": LOGGING_LEVEL,
        },
        # Reduce flood of debug messages from following modules when in debug mode
        "mode.timers": {
            "handlers": ["console"],
            "level": "WARNING",
        },
        "aiokafka.consumer.fetcher": {
            "handlers": ["console"],
            "level": "INFO",
        },
        "aiokafka.conn": {
            "handlers": ["console"],
            "level": "INFO",
        },
        "aiokafka.consumer.group_coordinator": {
            "handlers": ["console"],
            "level": "INFO",
        },
    },
}

is_initialized = False


def init():
    global is_initialized

    if is_initialized:
        return

    logging.config.dictConfig(DEFAULT_LOGGING)

    is_initialized = True

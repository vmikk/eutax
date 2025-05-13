"""
Structured logging configuration

Provides a consistent, timezone-aware, structured logging setup for:
- HTTP access logs (uvicorn)
- API request/response logging (via middleware)
- Background job logging (runner)
- System events and errors

Features:
- JSON-formatted logs for machine processing
- Pretty console output for development
- Timezone-aware timestamps (configured in eutax.yaml)
- Log file rotation with timestamp-based naming
- Context-aware logging with tags and metadata
"""

import os
import logging
import logging.config
from pathlib import Path
from datetime import datetime
import time
from typing import Any, Dict, Optional
import json

from uvicorn.logging import AccessFormatter
from zoneinfo import ZoneInfo
import structlog
from pythonjsonlogger import jsonlogger
from rich.logging import RichHandler

from app.config.config import load_config

# Custom JSON formatter with timezone support
class TimezoneAwareJsonFormatter(jsonlogger.JsonFormatter):
    """
    Custom JSON formatter that adds timezone-aware timestamps
    and properly formats log records with appropriate contexts.
    """
    def __init__(self, tz=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tz = None
        if tz:
            try:
                self.tz = ZoneInfo(tz)
            except Exception:
                pass

    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        
        # Add timestamp with proper timezone
        if self.tz:
            log_record['timestamp'] = datetime.fromtimestamp(record.created, tz=self.tz).isoformat()
        else:
            log_record['timestamp'] = datetime.fromtimestamp(record.created).isoformat()
        
        # Always include log level as a consistent field
        log_record['level'] = record.levelname
        
        # Add logger name as event source
        log_record['logger'] = record.name
        
        # Clean up context - remove empty fields
        for field in list(log_record.keys()):
            if log_record[field] is None or log_record[field] == '':
                del log_record[field]

# Timezone-aware access log formatter
def get_access_formatter(fmt=None, datefmt=None, use_colors=False, tz=None):
    """
    Factory to create an AccessFormatter with timezone-aware timestamps.
    """
    formatter = AccessFormatter(fmt=fmt, datefmt=datefmt, use_colors=use_colors)
    if tz:
        try:
            zone = ZoneInfo(tz)
            # Override converter to localize timestamp to the specified timezone
            def converter(timestamp):
                dt = datetime.fromtimestamp(timestamp, tz=zone)
                return dt.timetuple()
            formatter.converter = converter
        except Exception:
            pass
    return formatter

# Structlog processors
def drop_empty_keys(_, __, event_dict):
    """Remove keys with None or empty string values from structlog event dict"""
    for key in list(event_dict.keys()):
        if event_dict[key] is None or event_dict[key] == '':
            del event_dict[key]
    return event_dict

def add_timestamp_processor(_, __, event_dict):
    """Add properly formatted timestamp to structlog events"""
    config = load_config()
    logging_cfg = config.get("logging", {})
    log_timezone = logging_cfg.get("timezone", None)
    
    if log_timezone:
        try:
            zone = ZoneInfo(log_timezone)
            event_dict["timestamp"] = datetime.now(zone).isoformat()
        except Exception:
            event_dict["timestamp"] = datetime.now().isoformat()
    else:
        event_dict["timestamp"] = datetime.now().isoformat()
    
    return event_dict

def add_log_source(logger, _, event_dict):
    """Add source information to structlog event"""
    event_dict["logger"] = logger.name
    return event_dict

# Main setup function
def setup_logging():
    """
    Setup structured logging for the application:
    - JSON file logs with context-aware fields
    - Pretty console output for development
    - Timezone-aware timestamps
    - Log file rotation with timestamp-based naming
    - Contextual log attributes based on the source (HTTP, job, system)
    """
    # Load YAML config for logging
    config = load_config()
    logging_cfg = config.get("logging", {})
    log_level = logging_cfg.get("level", "INFO").upper()
    log_datefmt = logging_cfg.get("datefmt", "%Y-%m-%d %H:%M:%S")
    log_timezone = logging_cfg.get("timezone", None)
    backup_count = logging_cfg.get("backupCount", 14)

    # Ensure logs directory exists
    logs_dir = Path(os.environ.get("LOG_DIR", "wd/logs"))
    logs_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate a timestamp-based log filename
    log_timestamp = datetime.now().strftime("%Y%m%d")
    log_filename = f"{log_timestamp}_eutax.json"

    # Configure Python logging
    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "access": {
                "()": "app.logging_config.get_access_formatter",
                "fmt": '%(levelprefix)s %(asctime)s :: %(client_addr)s - "%(request_line)s" %(status_code)s',
                "datefmt": log_datefmt,
                "tz": log_timezone,
                "use_colors": True,
            },
            "json": {
                "()": "app.logging_config.TimezoneAwareJsonFormatter",
                "fmt": "%(timestamp)s %(level)s %(logger)s %(message)s %(context)s",
                "json_ensure_ascii": False,
                "tz": log_timezone,
            },
            "rich": {
                "datefmt": log_datefmt,
            }
        },
        "handlers": {
            "access": {
                "class": "logging.StreamHandler",
                "formatter": "access",
                "stream": "ext://sys.stdout",
            },
            "console": {
                "class": "rich.logging.RichHandler",
                "level": log_level,
                "rich_tracebacks": True,
                "formatter": "rich",
            },
            "file": {
                "class": "logging.handlers.TimedRotatingFileHandler",
                "level": log_level,
                "formatter": "json",
                "filename": str(logs_dir / log_filename),
                "when": "midnight",
                "backupCount": backup_count,
                "encoding": "utf-8",
            },
        },
        "loggers": {
            "uvicorn.access": {
                "handlers": ["access", "file"],
                "level": "INFO",
                "propagate": False,
            },
            "eutax": {
                "handlers": ["console", "file"],
                "level": log_level,
                "propagate": False,
            },
            "eutax.requests": {
                "handlers": ["console", "file"],
                "level": log_level,
                "propagate": False,
            },
            "eutax.jobs": {
                "handlers": ["console", "file"],
                "level": log_level,
                "propagate": False,
            },
            "eutax.auth": {
                "handlers": ["console", "file"],
                "level": log_level,
                "propagate": False,
            },
            "eutax.system": {
                "handlers": ["console", "file"],
                "level": log_level,
                "propagate": False,
            },
            "": {
                "handlers": ["console", "file"],
                "level": log_level,
                "propagate": True,
            },
        },
    }
    logging.config.dictConfig(logging_config)

    # Configure structlog processors
    shared_processors = [
        structlog.stdlib.add_log_level,
        add_log_source,
        add_timestamp_processor,
        structlog.stdlib.add_logger_name,
        drop_empty_keys,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        context_class=structlog.threadlocal.wrap_dict(dict),
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

# Helper function to get a logger with the correct context
def get_logger(name="eutax", **initial_context):
    """
    Get a structured logger with initial context values.
    
    Args:
        name: Logger name (should be one of: eutax, eutax.requests, eutax.jobs, eutax.auth, eutax.system)
        **initial_context: Initial context values to bind
        
    Returns:
        A structured logger with bound context
    """
    logger = structlog.get_logger(name)
    if initial_context:
        logger = logger.bind(**initial_context)
    return logger

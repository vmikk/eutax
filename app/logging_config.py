"""
Logging configuration (timezone-aware timestamps)
"""

from uvicorn.logging import AccessFormatter
from datetime import datetime
from zoneinfo import ZoneInfo

def get_access_formatter(fmt=None, datefmt=None, use_colors=False, tz=None):
    """
    Factory to create an AccessFormatter with timezone-aware timestamps.
    """
    formatter = AccessFormatter(fmt=fmt, datefmt=datefmt, use_colors=use_colors)
    if tz:
        try:
            zone = ZoneInfo(tz)
        except Exception:
            zone = None
        if zone:
            # Override converter to localize timestamp to the specified timezone
            def converter(timestamp):
                dt = datetime.fromtimestamp(timestamp, tz=zone)
                return dt.timetuple()
            formatter.converter = converter
    return formatter

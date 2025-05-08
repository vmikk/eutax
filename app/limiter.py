"""
Limiter module for rate limiting API endpoints
"""

from slowapi import Limiter
from slowapi.util import get_remote_address
from app.config.config import load_config

# Load rate limits from configuration
_config = load_config()
rate_limits = _config.get('rate_limits', {})

# Initialize a Limiter instance for slowapi
limiter = Limiter(key_func=get_remote_address, headers_enabled=True)

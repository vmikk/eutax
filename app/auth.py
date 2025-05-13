"""
Authentication module for EUTAX API - handles API key validation
and provides dependencies for protecting routes.
"""

import os
from fastapi import Depends, HTTPException, status, Request
from fastapi.security.api_key import APIKeyHeader
from app.logging_config import get_logger

# Create logger
logger = get_logger("eutax.auth")

# Get API key from Docker secrets first, then fall back to environment variable
API_KEY = ""
secrets_path = "/run/secrets/api_key"

if os.path.exists(secrets_path):
    try:
        with open(secrets_path, "r") as f:
            API_KEY = f.read().strip()
    except Exception as e:
        error_msg = f"Could not read API key from Docker secrets: {e}"
        logger.error(error_msg, event_type="auth_config_error", error=str(e))
        print(f"Warning: {error_msg}")
        
# If not found in secrets, check environment variable
if not API_KEY:
    API_KEY = os.environ.get("API_KEY", "")

# Set up API key header checker (`auto_error=False` allows to handle the error)
api_key_header = APIKeyHeader(name="X-API-KEY", auto_error=False)

async def verify_api_key(api_key: str = Depends(api_key_header), request: Request = None) -> None:
    """
    Dependency that ensures the incoming request has the correct API key header.
    Raises a 401 if it's missing or incorrect.
    
    NB! If API_KEY environment variable is empty or not set, authentication is skipped!
    """
    # Skip verification if no API key is configured
    if not API_KEY:
        logger.debug("Authentication bypassed - no API key configured", 
                   event_type="auth_bypass")
        return
    
    # Extract request context for logging    
    request_id = request.headers.get("X-Request-ID", None) if request else None
    client_ip = request.client.host if request else None
    path = request.url.path if request else None
    
    # Check if API key is valid
    if api_key != API_KEY:
        # Log the authentication failure with request details
        logger.warning(
            "Authentication failed - invalid API key",
            event_type="auth_failed",
            request_id=request_id,
            client_ip=client_ip,
            path=path
        )
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": 401,
                    "message": "Unauthorized"
                }
            }
        )
    
    # Log successful authentication
    logger.debug(
        "Authentication successful",
        event_type="auth_success",
        request_id=request_id,
        client_ip=client_ip,
        path=path
    )

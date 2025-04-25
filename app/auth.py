"""
Authentication module for EUTAX API - handles API key validation
and provides dependencies for protecting routes.
"""

import os
from fastapi import Depends, HTTPException, status
from fastapi.security.api_key import APIKeyHeader

# Get API key from Docker secrets first, then fall back to environment variable
API_KEY = ""
secrets_path = "/run/secrets/api_key"

if os.path.exists(secrets_path):
    try:
        with open(secrets_path, "r") as f:
            API_KEY = f.read().strip()
    except Exception as e:
        print(f"Warning: Could not read API key from Docker secrets: {e}")
        
# If not found in secrets, check environment variable
if not API_KEY:
    API_KEY = os.environ.get("API_KEY", "")

# Set up API key header checker (`auto_error=False` allows to handle the error)
api_key_header = APIKeyHeader(name="X-API-KEY", auto_error=False)

async def verify_api_key(api_key: str = Depends(api_key_header)) -> None:
    """
    Dependency that ensures the incoming request has the correct API key header.
    Raises a 401 if it's missing or incorrect.
    
    NB! If API_KEY environment variable is empty or not set, authentication is skipped!
    """
    # Skip verification if no API key is configured
    if not API_KEY:
        return
        
    if api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": 401,
                    "message": "Unauthorized"
                }
            }
        )

"""
Main application file for EUTAX API - initializes FastAPI app, sets up middleware, 
includes routers, and defines basic endpoints.
"""

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel
from typing import Dict
import os

from app.routers import uploads, jobs, refdbs
from app.auth import verify_api_key, API_KEY
from slowapi import _rate_limit_exceeded_handler
from slowapi.middleware import SlowAPIMiddleware
from app.limiter import limiter
from slowapi.errors import RateLimitExceeded
from app.logging_config import setup_logging, get_logger
setup_logging()

import structlog
import uuid
from fastapi import Request, Response
import time

# root structlog logger
logger = get_logger("eutax.system")

# ANSI escape codes for colored output
class Colors:
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    RESET = "\033[0m"

# Check if docs should be disabled
DISABLE_DOCS = os.getenv("DISABLE_DOCS", "false").lower() == "true"

# Create FastAPI app
app = FastAPI(
    title="EUTAX",
    description="API for taxonomic annotation of DNA sequences",
    version="0.0.1",
    docs_url=None if DISABLE_DOCS else "/docs",
    redoc_url=None if DISABLE_DOCS else "/redoc",
    openapi_url=None if DISABLE_DOCS else "/openapi.json",
)

@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """
    Middleware to add request logging and context tracking
    """
    # Generate a request ID
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    
    # Create a request-specific logger with context
    request_logger = get_logger(
        "eutax.requests", 
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        client_ip=request.client.host,
        query_params=str(request.query_params) if request.query_params else None
    )

    # Log the start of the request
    request_logger.info(
        f"Request started: {request.method} {request.url.path}",
        event_type="request_started"
    )
    
    # Record the start time
    start_time = time.time()
    
    # Process the request, catching any exceptions
    try:
        response = await call_next(request)
        
        # Calculate request processing time
        process_time = time.time() - start_time
        
        # Add the request ID to the response headers
        response.headers["X-Request-ID"] = request_id
        
        # Log the response
        request_logger.info(
            f"Request completed: {request.method} {request.url.path}",
            event_type="request_completed",
            status_code=response.status_code,
            duration_ms=round(process_time * 1000, 2)
        )
        
        return response
        
    except Exception as e:
        # Calculate request processing time
        process_time = time.time() - start_time
        
        # Log the exception
        request_logger.error(
            f"Request failed: {request.method} {request.url.path}",
            event_type="request_failed",
            error=str(e),
            error_type=type(e).__name__,
            duration_ms=round(process_time * 1000, 2),
            exc_info=True
        )
        
        # Re-raise the exception to let FastAPI handle it
        raise

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # allows requests from any origin. TODO: restrict to known origins
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Add GZipMiddleware to compress responses
app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=5)

# Create protected routers with API key authentication
protected_uploads_router = uploads.router
protected_jobs_router = jobs.router
protected_refdbs_router = refdbs.router

# Create router for unprotected endpoints
from fastapi import APIRouter
unprotected_router = APIRouter()

# Job count endpoint (unprotected)
@unprotected_router.get("/job_count", response_model=Dict[str, int])
async def get_job_count():
    """
    Get the total number of jobs executed.
    """
    from app import db_storage
    count = await db_storage.get_job_count()
    return {"count": count}

# Include routers
app.include_router(protected_uploads_router, prefix="/api/v1", tags=["Uploads"], dependencies=[Depends(verify_api_key)])
app.include_router(protected_jobs_router, prefix="/api/v1", tags=["Jobs"], dependencies=[Depends(verify_api_key)])
app.include_router(protected_refdbs_router, prefix="/api/v1", tags=["Reference Databases"], dependencies=[Depends(verify_api_key)])
app.include_router(unprotected_router, prefix="/api/v1", tags=["Public"])

# Integrate slowapi rate limiting
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

class HealthResponse(BaseModel):
    status: str
    version: str
    services: Dict[str, str]

@app.get("/", tags=["Root"])
async def root():
    if DISABLE_DOCS:
        return {"message": "EUTAX API. Access to this endpoint is restricted, unauthorized requests will be logged."} 
    else:
        return {"message": "Welcome to EUTAX - the taxonomic annotation API for DNA sequences. Visit /docs or /redoc for API documentation."}

@app.get("/api/v1/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """
    Check if the server is running and all services are operational.
    Returns status information about the API and its dependent services.
    """
    return HealthResponse(
        status="healthy",
        version="0.0.1",
        services={
            "database": "operational",
            "annotation_services": "operational"
        }
    ) 

@app.on_event("startup")
async def startup_event():
    """
    Log API authentication status on startup
    """
    if API_KEY:
        # Determine the source of the API key
        secrets_path = "/run/secrets/api_key"
        api_key_source = "Docker secrets" if os.path.exists(secrets_path) else "environment variable"
        
        print(f"{Colors.GREEN}API KEY IS SET - Protected endpoints require authentication{Colors.RESET}")
        print(f"{Colors.BLUE}API key loaded from: {api_key_source}{Colors.RESET}")
        
        # Log using structured logger
        logger.info(
            "API started with authentication enabled",
            event_type="api_startup",
            auth_enabled=True,
            auth_source=api_key_source
        )
    else:
        print(f"{Colors.RED}WARNING: API KEY IS NOT SET - ALL ENDPOINTS ARE UNPROTECTED!{Colors.RESET}")
        print(f"{Colors.RED}To enable authentication, set the API_KEY environment variable or use Docker secrets{Colors.RESET}")
        
        # Log using structured logger
        logger.warning(
            "API started without authentication",
            event_type="api_startup",
            auth_enabled=False
        )

    # Log documentation status
    if DISABLE_DOCS:
        print(f"{Colors.YELLOW}API documentation (Swagger UI, ReDoc) is DISABLED{Colors.RESET}")
        logger.info("API documentation is disabled", event_type="api_startup", docs_enabled=False)
    else:
        print(f"{Colors.BLUE}API documentation is ENABLED - available at /docs and /redoc{Colors.RESET}")
        logger.info("API documentation is enabled", event_type="api_startup", docs_enabled=True)
        
@app.on_event("shutdown")
async def shutdown_event():
    """
    Log API shutdown
    """
    logger.info("API shutting down", event_type="api_shutdown")



"""
Main application file for EUTAX API - initializes FastAPI app, sets up middleware, 
includes routers, and defines basic endpoints.
"""

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel
from typing import Dict
import logging
import logging.config
import os

from app.routers import uploads, jobs, refdbs
from app.auth import verify_api_key, API_KEY

# Define custom logging configuration with timestamps
log_config = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "access": {
            "()": "uvicorn.logging.AccessFormatter",
            "fmt": '%(levelprefix)s %(asctime)s :: %(client_addr)s - "%(request_line)s" %(status_code)s',
            "datefmt": "%Y-%m-%d %H:%M:%S",
            "use_colors": True
        },
    },
    "handlers": {
        "access": {
            "formatter": "access",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
        },
    },
    "loggers": {
        "uvicorn.access": {
            "handlers": ["access"],
            "level": "INFO",
            "propagate": False
        },
    },
}

# Configure logging
logging.config.dictConfig(log_config)
logger = logging.getLogger("eutax")

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
    else:
        print(f"{Colors.RED}WARNING: API KEY IS NOT SET - ALL ENDPOINTS ARE UNPROTECTED!{Colors.RESET}")
        print(f"{Colors.RED}To enable authentication, set the API_KEY environment variable or use Docker secrets{Colors.RESET}") 

    # Log documentation status
    if DISABLE_DOCS:
        print(f"{Colors.YELLOW}API documentation (Swagger UI, ReDoc) is DISABLED{Colors.RESET}")
    else:
        print(f"{Colors.BLUE}API documentation is ENABLED - available at /docs and /redoc{Colors.RESET}")


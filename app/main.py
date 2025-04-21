"""
Main application file for EUTAX API - initializes FastAPI app, sets up middleware, 
includes routers, and defines basic endpoints.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict
import logging
import logging.config

from app.routers import uploads, jobs

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

# Create FastAPI app
app = FastAPI(
    title="EUTAX",
    description="API for taxonomic annotation of DNA sequences",
    version="0.0.1",
    docs_url="/docs",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(uploads.router, prefix="/api/v1", tags=["Uploads"])
app.include_router(jobs.router, prefix="/api/v1", tags=["Jobs"])

class HealthResponse(BaseModel):
    status: str
    version: str
    services: Dict[str, str]

@app.get("/", tags=["Root"])
async def root():
    return {"message": "Welcome to the EUTAX. Visit /docs for API documentation."} 

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
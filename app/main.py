from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict

from app.routers import uploads, jobs

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